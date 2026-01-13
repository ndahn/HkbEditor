"""
Game Character Reload Tool

This module provides functionality to dynamically reload character files in games
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
from .game_config import GameConfig, DEFAULT_CONFIG, ALL_CONFIGS


class MemoryManager:
    """Manages process attachment and memory scanning operations."""

    def __init__(self, config: GameConfig):
        self.config = config
        self.process_handle = 0
        self.base_address = 0
        self.attached_process = None
        self.world_chr_man_ptr = 0
        self.crash_fix_ptr = 0

        self.logger = logging.getLogger("ChrReloader")
        self.logger.setLevel(logging.INFO)

    def attach_to_process(self):
        """Attach to the game process and find its base address."""
        if self.attached_process and self.attached_process.is_running():
            return

        self._cleanup()

        # Try each process name in the configuration
        for process_name in self.config.process_names:
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"].lower() == f"{process_name}.exe":
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

                    if not self.process_handle:
                        self._cleanup()
                        raise RuntimeError(f"Failed to open process handle for PID {proc.pid}")

                    self.logger.debug(
                        f"Attached to {process_name} (PID: {proc.pid}, Base: 0x{self.base_address:X})"
                    )
                    self._scan_game_patterns()
                    return

        process_list = ", ".join([f"'{name}.exe'" for name in self.config.process_names])
        raise RuntimeError(f"Game process not found. Tried: {process_list}")

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
        module_size = self._get_module_size()
        self.logger.debug(
            f"Creating AOB scanner for base: 0x{self.base_address:X}, size: 0x{module_size:X}"
        )

        scanner = AOBScanner(self.process_handle, self.base_address, module_size)

        # Find WorldChrMan pointer
        self._find_world_chr_man_pointer(scanner)
        if not self.world_chr_man_ptr:
            raise RuntimeError("Could not find WorldChrMan pattern")

        # Find crash patch location (optional)
        if self.config.crash_patch_aob:
            self._find_crash_patch_location(scanner)

    def _get_module_size(self) -> int:
        """Get the actual size of the main module, or return a default."""
        try:
            for mmap in self.attached_process.memory_maps(grouped=False):
                # Check against all configured process names
                if any(name in mmap.path.lower() for name in self.config.process_names):
                    addr_parts = mmap.addr.split("-")
                    start_addr = int(addr_parts[0], 16)
                    end_addr = int(addr_parts[1], 16)
                    if start_addr == self.base_address:
                        return end_addr - start_addr
        except Exception as e:
            self.logger.debug(f"Could not get module size: {e}")

        return 0x10000000  # Default large size

    def _find_world_chr_man_pointer(self, scanner: AOBScanner):
        """Find the WorldChrMan pointer using AOB scanning."""
        self.logger.debug(f"Scanning for WorldChrMan with pattern: {self.config.world_chr_man_aob}")

        pointer_addr = self._scan_relative_address(
            scanner,
            self.config.world_chr_man_aob,
            self.config.world_chr_man_jump_start,
            self.config.world_chr_man_jump_end,
        )

        if pointer_addr:
            self.logger.debug(f"Found WorldChrMan pattern at: 0x{pointer_addr:X}")
            actual_ptr = MemoryOperations.read_int64(self.process_handle, pointer_addr)
            self.world_chr_man_ptr = actual_ptr
            self.logger.debug(f"WorldChrMan pointer value: 0x{self.world_chr_man_ptr:X}")

    def _find_crash_patch_location(self, scanner: AOBScanner):
        """Find the crash patch location using AOB scanning."""
        pattern = AOBScanner.parse_pattern(self.config.crash_patch_aob)

        self.logger.debug(f"Scanning for crash patch with pattern: {self.config.crash_patch_aob}")
        crash_location = scanner.scan(pattern)

        if crash_location:
            self.crash_fix_ptr = crash_location + len(pattern) - self.config.crash_patch_jump_end
            self.logger.debug(f"Found crash patch at: 0x{self.crash_fix_ptr:X}")
        else:
            self.logger.warning("Could not find crash patch pattern")

    def _scan_relative_address(
        self, scanner: AOBScanner, pattern_str: str, jump_start: int, jump_end: int
    ) -> int:
        """Scan for a pattern and calculate relative address."""
        pattern = AOBScanner.parse_pattern(pattern_str)
        address = scanner.scan(pattern)

        if not address:
            return 0

        # Read the relative offset
        offset_addr = address + jump_start
        relative_offset = MemoryOperations.read_uint32(self.process_handle, offset_addr)

        # Calculate absolute address
        next_instruction = address + jump_end
        return next_instruction + relative_offset

    def _cleanup(self):
        """Clean up process resources."""
        if self.process_handle:
            MemoryOperations.close_handle(self.process_handle)
            self.process_handle = 0
        self.attached_process = None
        self.world_chr_man_ptr = 0
        self.crash_fix_ptr = 0


class ChrReloader:
    """Handles the character reload process."""

    def __init__(self, config: GameConfig = None):
        if config is None:
            config = detect_game_config()
        self.config = config
        self.memory_manager = MemoryManager(self.config)
        self.logger = logging.getLogger("ChrReloader")
        self.logger.setLevel(logging.INFO)

    def reload_character(self, chr_name: str = "c0000"):
        """
        Reload a character file in the game.

        Args:
            chr_name: Name of the character file to reload (e.g., "c0000")
        """
        chr_name_bytes = chr_name.encode("utf-16-le") + b"\x00\x00"

        # Attach to game process
        if not self.memory_manager.process_handle:
            self.memory_manager.attach_to_process()

        if not self.memory_manager.process_handle:
            raise RuntimeError("No process handle available")

        # Allocate memory for shellcode and data structures
        chr_reload = MemoryOperations.allocate_memory(
            self.memory_manager.process_handle, 256, PAGE_EXECUTE_READWRITE
        )
        chr_reload_data_setup = MemoryOperations.allocate_memory(
            self.memory_manager.process_handle, 256, PAGE_READWRITE
        )

        if not chr_reload or not chr_reload_data_setup:
            raise RuntimeError("Failed to allocate memory")

        try:
            # Setup data structure for character reload
            self._setup_reload_data(chr_reload_data_setup, chr_name_bytes)

            # Apply crash fix if available
            self._apply_crash_fix()

            # Create and execute shellcode
            self._execute_reload_shellcode(chr_reload, chr_reload_data_setup)

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

    def _setup_reload_data(self, data_setup_addr: int, chr_name_bytes: bytes):
        """Setup the data structure required for character reload."""
        data_pointer_addr = (
            self.memory_manager.world_chr_man_ptr + self.config.world_chr_man_struct_offset
        )

        self.logger.debug(f"Reading data pointer from: 0x{data_pointer_addr:X}")
        first_level_ptr = MemoryOperations.read_int64(
            self.memory_manager.process_handle, data_pointer_addr
        )
        self.logger.debug(f"First level pointer: 0x{first_level_ptr:X}")

        if not first_level_ptr:
            raise RuntimeError("First level pointer is null")

        data_pointer = MemoryOperations.read_int64(
            self.memory_manager.process_handle, first_level_ptr
        )
        self.logger.debug(f"Final data pointer: 0x{data_pointer:X}")

        if not data_pointer:
            raise RuntimeError("Final data pointer is null")

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

    def _apply_crash_fix(self):
        """Apply crash fix patch if available."""
        if self.memory_manager.crash_fix_ptr and self.config.crash_patch_bytes:
            self.logger.debug(
                f"Applying crash fix at: 0x{self.memory_manager.crash_fix_ptr:X}"
            )
            MemoryOperations.write_bytes(
                self.memory_manager.process_handle,
                self.memory_manager.crash_fix_ptr,
                self.config.crash_patch_bytes,
            )
        else:
            self.logger.warning("Warning: No crash fix available")

    def _execute_reload_shellcode(self, shellcode_addr: int, data_setup_addr: int):
        """Generate and execute the shellcode for character reload."""
        # Get shellcode template from configuration
        shellcode = bytearray(self.config.shellcode_template)

        # Patch data setup address into shellcode
        data_setup_bytes = struct.pack("<Q", data_setup_addr & 0xFFFFFFFFFFFFFFFF)
        offset = self.config.shellcode_data_offset
        shellcode[offset:offset + 8] = data_setup_bytes

        # Patch WorldChrMan pointer into shellcode
        world_chr_man_bytes = struct.pack(
            "<Q", self.memory_manager.world_chr_man_ptr & 0xFFFFFFFFFFFFFFFF
        )
        offset = self.config.shellcode_ptr_offset
        shellcode[offset:offset + 8] = world_chr_man_bytes

        self.logger.debug(f"Writing shellcode to: 0x{shellcode_addr:X}")
        self.logger.debug(f"Shellcode size: {len(shellcode)} bytes")

        # Write shellcode to allocated memory
        if not MemoryOperations.write_bytes(
            self.memory_manager.process_handle, shellcode_addr, bytes(shellcode)
        ):
            raise RuntimeError("Failed to write shellcode")

        # Create and execute remote thread
        thread_handle = MemoryOperations.create_remote_thread(
            self.memory_manager.process_handle, shellcode_addr
        )

        if not thread_handle:
            raise RuntimeError("Failed to create remote thread")

        self.logger.debug(f"Created remote thread: 0x{thread_handle:X}")
        wait_result = MemoryOperations.wait_for_thread(thread_handle)
        self.logger.debug(f"Thread wait result: {wait_result}")
        MemoryOperations.close_handle(thread_handle)


def detect_game_config() -> GameConfig:
    """
    Detect which game configuration to use based on running processes.
    
    Returns:
        GameConfig: The first configuration that matches a running process.
        
    Raises:
        RuntimeError: If no matching game process is found.
    """
    running_processes = {proc.info["name"].lower() for proc in psutil.process_iter(["name"])}
    
    for config in ALL_CONFIGS:
        for process_name in config.process_names:
            if f"{process_name}.exe" in running_processes:
                return config
    
    raise RuntimeError("No supported game process found")


def reload_character(chr_name: str = "c0000", config: GameConfig = None) -> ChrReloader:
    """
    Convenience function to reload a character.

    Args:
        chr_name: Name of the character to reload (e.g., "c0000")
        config: Game configuration. If None, automatically detects based on running processes.
    """
    if config is None:
        config = detect_game_config()
    
    reloader = ChrReloader(config)
    reloader.reload_character(chr_name)
    return reloader


if __name__ == "__main__":
    # Example usage: Reload the default character
    try:
        reload_character("c0000")
        print("Character reload initiated successfully")
    except Exception as e:
        print(f"Character reload failed: {e}")