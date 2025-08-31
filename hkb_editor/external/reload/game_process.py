"""
Elden Ring Character Reload Tool

This module provides functionality to dynamically reload character files in Elden Ring
by manipulating the game's memory and injecting code to trigger the reload mechanism.

Key components:
- AOBScanner: Searches for byte patterns in process memory
- MemoryManager: Handles process attachment and memory operations
- ChrReloader: Coordinates the character reload process


> This code is a port of A1steaksa's HKS-Hotloader functionality
> https://github.com/A1steaksa/Elden-Ring-HKS-Hotloader
"""

import logging
import struct
import psutil

from .windows_api import (
    kernel32,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_READ,
    PROCESS_VM_WRITE,
    PROCESS_VM_OPERATION,
    PAGE_EXECUTE_READWRITE,
    PAGE_READWRITE,
)
from .memory import MemoryOperations
from .aob_scanner import AOBScanner


WorldChrManPtr_AOB = "48 8B 05 ?? ?? ?? ?? 48 85 C0 74 0F 48 39 88"
WorldChrManPtr_JumpStart = 3
WorldChrManPtr_JumpEnd = 7
WorldChrMan_StructOffset = 0x1E668

CrashPatchOffset_AOB = "80 65 ?? FD 48 C7 45 ?? 07 00 00 00 ?? 8D 45 48 4C 89 60 ?? 48 83 78 ?? 08 72 03 48 8B 00 66 44 89 20 49 8B 8F ?? ?? ?? ?? 48 8B 01 48 ?? ??"
CrashPatchOffset_JumpEnd = 3
CrashPatchOffset_Bytes = b"\x48\x31\xd2"


class MemoryManager:
    """Manages process attachment and memory scanning operations."""

    def __init__(self):
        self.process_handle = 0
        self.base_address = 0
        self.attached_process = None
        self.world_chr_man_ptr = 0
        self.crash_fix_ptr = 0

        self.logger = logging.getLogger("ChrReloader")
        self.logger.setLevel(logging.INFO)

    def attach_to_process(self, process_name: str) -> bool:
        """Attach to the specified process and find its base address."""
        if self.attached_process and self.attached_process.is_running():
            return True

        self._cleanup()

        # Find and attach to process
        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info["name"].lower() == f"{process_name}.exe":
                try:
                    self.attached_process = proc
                    self.base_address = self._find_base_address(proc, process_name)

                    # Open process with required permissions
                    self.process_handle = kernel32.OpenProcess(
                        PROCESS_QUERY_INFORMATION
                        | PROCESS_VM_READ
                        | PROCESS_VM_WRITE
                        | PROCESS_VM_OPERATION,
                        False,
                        proc.pid,
                    )

                    if self.process_handle:
                        self.logger.debug(
                            f"Attached to {process_name} (PID: {proc.pid}, Base: 0x{self.base_address:X})"
                        )
                        self._scan_game_patterns()
                        return True
                    else:
                        self.logger.error(f"Failed to open process handle for PID {proc.pid}")

                except Exception as e:
                    self.logger.error(f"Error attaching to process: {e}")
                    self._cleanup()

        return False

    def _find_base_address(self, proc: psutil.Process, process_name: str) -> int:
        """Find the base address of the main executable module."""
        # Method 1: Try memory_maps() with grouped=False
        try:
            for mmap in proc.memory_maps(grouped=False):
                if process_name.lower() in mmap.path.lower():
                    addr_parts = mmap.addr.split("-")
                    base_addr = int(addr_parts[0], 16)
                    self.logger.debug(f"Found base address via memory_maps: 0x{base_addr:X}")
                    return base_addr
        except Exception as e:
            self.logger.warning(f"Memory maps method failed: {e}")

        # Method 2: Try using exe() to get the main executable info
        try:
            exe_path = proc.exe()
            for mmap in proc.memory_maps(grouped=False):
                if exe_path.lower() in mmap.path.lower():
                    addr_parts = mmap.addr.split("-")
                    base_addr = int(addr_parts[0], 16)
                    self.logger.debug(f"Found base address via exe path: 0x{base_addr:X}")
                    return base_addr
        except Exception as e:
            self.logger.warning(f"Exe path method failed: {e}")

        # Method 3: Use common default base address for Windows executables
        default_base = 0x140000000
        self.logger.warning(f"Using default base address: 0x{default_base:X}")
        return default_base

    def _scan_game_patterns(self):
        """Scan for required game patterns and addresses."""
        try:
            # Determine module size for scanning
            module_size = self._get_module_size()
            self.logger.debug(
                f"Creating AOB scanner for base: 0x{self.base_address:X}, size: 0x{module_size:X}"
            )

            # Create AOB scanner
            scanner = AOBScanner(self.process_handle, self.base_address, module_size)

            # Find WorldChrMan pointer
            self._find_world_chr_man_pointer(scanner)

            # Find crash patch location
            self._find_crash_patch_location(scanner)

        except Exception as e:
            self.logger.error(f"Error scanning patterns: {e}")
            import traceback

            traceback.print_exc()

    def _get_module_size(self) -> int:
        """Get the actual size of the main module, or return a default."""
        try:
            for mmap in self.attached_process.memory_maps(grouped=False):
                if any(
                    name in mmap.path.lower()
                    for name in ["eldenring.exe", "start_protected_game.exe"]
                ):
                    addr_parts = mmap.addr.split("-")
                    start_addr = int(addr_parts[0], 16)
                    end_addr = int(addr_parts[1], 16)
                    if start_addr == self.base_address:
                        return end_addr - start_addr
        except Exception as e:
            self.logger.error(f"Could not get module size: {e}")

        return 0x10000000  # Default large size

    def _find_world_chr_man_pointer(self, scanner: AOBScanner):
        """Find the WorldChrMan pointer using AOB scanning."""
        self.logger.debug(f"Scanning for WorldChrMan with pattern: {WorldChrManPtr_AOB}")

        pointer_addr = self._scan_relative_address(
            scanner,
            WorldChrManPtr_AOB,
            WorldChrManPtr_JumpStart,
            WorldChrManPtr_JumpEnd,
        )

        if pointer_addr:
            self.logger.debug(f"Found WorldChrMan pattern at: 0x{pointer_addr:X}")
            # Read the actual pointer value
            actual_ptr = MemoryOperations.read_int64(self.process_handle, pointer_addr)
            self.world_chr_man_ptr = actual_ptr
            self.logger.debug(f"WorldChrMan pointer value: 0x{self.world_chr_man_ptr:X}")
        else:
            self.logger.error("Could not find WorldChrMan pattern")

    def _find_crash_patch_location(self, scanner: AOBScanner):
        """Find the crash patch location using AOB scanning."""
        pattern = AOBScanner.parse_pattern(CrashPatchOffset_AOB)

        self.logger.debug(f"Scanning for crash patch with pattern: {CrashPatchOffset_AOB}")
        crash_location = scanner.scan(pattern)

        if crash_location:
            self.crash_fix_ptr = (
                crash_location + len(pattern) - CrashPatchOffset_JumpEnd
            )
            self.logger.debug(f"Found crash patch at: 0x{self.crash_fix_ptr:X}")
        else:
            self.logger.error("Could not find crash patch pattern")

    def _scan_relative_address(
        self, scanner: AOBScanner, pattern_str: str, addr_offset: int, end_offset: int
    ) -> int:
        """Scan for a pattern and resolve a relative address within it."""
        pattern = AOBScanner.parse_pattern(pattern_str)
        location = scanner.scan(pattern)

        if location == 0:
            self.logger.error(f"AOB pattern not found: {pattern_str}")
            return 0

        self.logger.debug(f"AOB pattern found at: 0x{location:X}")

        # Read the relative address (32-bit)
        rel_addr_location = location + addr_offset
        rel_addr = MemoryOperations.read_uint32(self.process_handle, rel_addr_location)

        # Calculate absolute address: instruction_end + relative_offset
        instruction_end = location + end_offset
        absolute_addr = (instruction_end + rel_addr) & 0xFFFFFFFFFFFFFFFF

        self.logger.debug(
            f"Relative address: 0x{rel_addr:X}, Instruction end: 0x{instruction_end:X}"
        )
        self.logger.debug(f"Calculated absolute address: 0x{absolute_addr:X}")

        return absolute_addr

    def _cleanup(self):
        """Clean up resources and reset state."""
        if self.process_handle:
            kernel32.CloseHandle(self.process_handle)
            self.process_handle = 0
        self.attached_process = None
        self.world_chr_man_ptr = 0
        self.crash_fix_ptr = 0


class ChrReloader:
    """Handles the character reload process by injecting code into the game."""

    def __init__(self):
        self.memory_manager = MemoryManager()
        self.logger = logging.getLogger("ChrReloader")
        self.logger.setLevel(logging.INFO)

    def reload_character(self, chr_name: str) -> bool:
        """
        Reload the specified character file by injecting shellcode into the game process.

        Args:
            chr_name: Name of the character file to reload (e.g., "c0000")

        Returns:
            True if the reload was initiated successfully, False otherwise
        """
        chr_name_bytes = chr_name.encode("utf-16le")

        # Attach to Elden Ring process
        if not self.memory_manager.attach_to_process("eldenring"):
            if not self.memory_manager.attach_to_process("start_protected_game"):
                raise ValueError("Unable to find Elden Ring process")

        if not self.memory_manager.process_handle:
            raise ValueError("No process handle available")

        # Allocate memory for shellcode and data structures
        chr_reload = MemoryOperations.allocate_memory(
            self.memory_manager.process_handle, 256, PAGE_EXECUTE_READWRITE
        )
        chr_reload_data_setup = MemoryOperations.allocate_memory(
            self.memory_manager.process_handle, 256, PAGE_READWRITE
        )

        if not chr_reload or not chr_reload_data_setup:
            raise ValueError("Failed to allocate memory")

        try:
            if not self.memory_manager.world_chr_man_ptr:
                raise ValueError("Could not find WorldChrMan pointer")

            # Setup data structure for character reload
            if not self._setup_reload_data(chr_reload_data_setup, chr_name_bytes):
                raise ValueError("Failed to setup reload data")

            # Apply crash fix if available
            self._apply_crash_fix()

            # Create and execute shellcode
            if not self._execute_reload_shellcode(
                chr_reload, chr_reload_data_setup
            ):
                raise ValueError("Shellcode execution failed")

            return True
        finally:
            # Clean up allocated memory
            if chr_reload:
                MemoryOperations.free_memory(
                    self.memory_manager.process_handle, chr_reload, 256
                )
            if chr_reload_data_setup:
                MemoryOperations.free_memory(
                    self.memory_manager.process_handle, chr_reload_data_setup, 256
                )

    def _setup_reload_data(self, data_setup_addr: int, chr_name_bytes: bytes) -> bool:
        """Setup the data structure required for character reload."""
        data_pointer_addr = (
            self.memory_manager.world_chr_man_ptr + WorldChrMan_StructOffset
        )

        self.logger.debug(f"Reading data pointer from: 0x{data_pointer_addr:X}")
        first_level_ptr = MemoryOperations.read_int64(
            self.memory_manager.process_handle, data_pointer_addr
        )
        self.logger.debug(f"First level pointer: 0x{first_level_ptr:X}")

        if first_level_ptr == 0:
            self.logger.error("First level pointer is null")
            return False

        data_pointer = MemoryOperations.read_int64(
            self.memory_manager.process_handle, first_level_ptr
        )
        self.logger.debug(f"Final data pointer: 0x{data_pointer:X}")

        if data_pointer == 0:
            self.logger.error("Final data pointer is null")
            return False

        # Write data structure
        MemoryOperations.write_int64(
            self.memory_manager.process_handle, data_setup_addr + 0x8, data_pointer
        )
        MemoryOperations.write_int64(
            self.memory_manager.process_handle,
            data_setup_addr + 0x58,
            data_setup_addr + 0x100,
        )
        MemoryOperations.write_int8(
            self.memory_manager.process_handle, data_setup_addr + 0x70, 0x1F
        )
        MemoryOperations.write_bytes(
            self.memory_manager.process_handle, data_setup_addr + 0x100, chr_name_bytes
        )

        return True

    def _apply_crash_fix(self):
        """Apply crash fix patch if available."""
        if self.memory_manager.crash_fix_ptr:
            self.logger.debug(f"Applying crash fix at: 0x{self.memory_manager.crash_fix_ptr:X}")
            MemoryOperations.write_bytes(
                self.memory_manager.process_handle,
                self.memory_manager.crash_fix_ptr,
                CrashPatchOffset_Bytes,
            )
        else:
            self.logger.warning("Warning: No crash fix pointer found")

    def _execute_reload_shellcode(
        self, shellcode_addr: int, data_setup_addr: int
    ) -> bool:
        """Generate and execute the shellcode for character reload."""
        # Determine game version and generate appropriate shellcode
        game_version = 1_07_00_00  # Assume latest version

        if game_version >= 1_07_00_00:
            # fmt: off
            shellcode = bytearray([
                0x48, 0xBB, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # mov rbx,0000000000000000 (ChrReload_DataSetup)
                0x48, 0xB9, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # mov rcx,0000000000000000 (WorldChrMan)
                0x48, 0x8B, 0x91, 0x68, 0xE6, 0x01, 0x00,  # mov rdx,[rcx+0001E668]
                0x48, 0x89, 0x1A,  # mov [rdx],rbx
                0x48, 0x89, 0x13,  # mov [rbx],rdx
                0x48, 0x8B, 0x91, 0x68, 0xE6, 0x01, 0x00,  # mov rdx,[rcx+0001E668]
                0x48, 0x89, 0x5A, 0x08,  # mov [rdx+08],rbx
                0x48, 0x89, 0x53, 0x08,  # mov [rbx+08],rdx
                0xC7, 0x81, 0x70, 0xE6, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # mov [rcx+0001E670],00000001 { 1 }
                0xC7, 0x81, 0x78, 0xE6, 0x01, 0x00, 0x00, 0x00, 0x20, 0x41,  # mov [rcx+0001E678],41200000 { 10.00 }
                0xC3,  # ret
            ])
            # fmt: on
        else:
            # fmt: off
            shellcode = bytearray([
                0x48, 0xBB, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # mov rbx,0000000000000000 (ChrReload_DataSetup)
                0x48, 0xB9, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # mov rcx,0000000000000000 (WorldChrMan)
                0x48, 0x8B, 0x91, 0xC0, 0x85, 0x01, 0x00,  # mov rdx,[rcx+000185C0]
                0x48, 0x89, 0x1A,  # mov [rdx],rbx
                0x48, 0x89, 0x13,  # mov [rbx],rdx
                0x48, 0x8B, 0x91, 0xC0, 0x85, 0x01, 0x00,  # mov rdx,[rcx+000185C0]
                0x48, 0x89, 0x5A, 0x08,  # mov [rdx+08],rbx
                0x48, 0x89, 0x53, 0x08,  # mov [rbx+08],rdx
                0xC7, 0x81, 0xC8, 0x85, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  # mov [rcx+000185C8],00000001 { 1 }
                0xC7, 0x81, 0xD0, 0x85, 0x01, 0x00, 0x00, 0x00, 0x20, 0x41,  # mov [rcx+000185D0],41200000 { 10.00 }
                0xC3,  # ret
            ])
            # fmt: on

        # Patch addresses into shellcode
        data_setup_bytes = struct.pack("<Q", data_setup_addr & 0xFFFFFFFFFFFFFFFF)
        shellcode[2:10] = data_setup_bytes

        world_chr_man_bytes = struct.pack(
            "<Q", self.memory_manager.world_chr_man_ptr & 0xFFFFFFFFFFFFFFFF
        )
        shellcode[12:20] = world_chr_man_bytes

        self.logger.debug(f"Writing shellcode to: 0x{shellcode_addr:X}")
        self.logger.debug(f"Shellcode size: {len(shellcode)} bytes")

        # Write shellcode to allocated memory
        if not MemoryOperations.write_bytes(
            self.memory_manager.process_handle, shellcode_addr, bytes(shellcode)
        ):
            self.logger.error("Failed to write shellcode")
            return False

        # Create and execute remote thread
        thread_handle = MemoryOperations.create_remote_thread(
            self.memory_manager.process_handle, shellcode_addr
        )

        if thread_handle:
            self.logger.debug(f"Created remote thread: 0x{thread_handle:X}")
            wait_result = MemoryOperations.wait_for_thread(thread_handle)
            self.logger.debug(f"Thread wait result: {wait_result}")
            MemoryOperations.close_handle(thread_handle)
            return True
        else:
            self.logger.error("Failed to create remote thread")
            return False


def reload_character(chr_name: str = "c0000") -> bool:
    """
    Convenience function to reload a character file.
    
    Args:
        chr_name: Name of the character file to reload (e.g., "c0000")
        
    Returns:
        True if the reload was initiated successfully, False otherwise
    """
    reloader = ChrReloader()
    return reloader.reload_character(chr_name)


if __name__ == "__main__":
    # Example usage: Reload the default character file
    success = reload_character("c0000")
    if success:
        print("Character reload initiated successfully")
    else:
        print("Character reload failed")
