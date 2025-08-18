import ctypes

from .windows_api import (
    kernel32,
    MEMORY_BASIC_INFORMATION,
    MEM_COMMIT,
    PAGE_EXECUTE,
    PAGE_EXECUTE_READ,
    PAGE_EXECUTE_READWRITE,
    PAGE_EXECUTE_WRITECOPY,
    PAGE_GUARD,
)
from .memory import MemoryOperations


class AOBScanner:
    """Array of Bytes (AOB) scanner for finding byte patterns in process memory."""

    PAGE_EXECUTE_ANY = (
        PAGE_EXECUTE
        | PAGE_EXECUTE_READ
        | PAGE_EXECUTE_READWRITE
        | PAGE_EXECUTE_WRITECOPY
    )

    def __init__(self, process_handle: int, base_address: int, module_size: int):
        """Initialize scanner with process memory regions that contain executable code."""
        self.mem_regions = []
        self.read_memory = {}

        mem_region_addr = base_address
        main_module_end = base_address + module_size

        # Scan all executable memory regions within the module
        while mem_region_addr < main_module_end:
            mem_info = MEMORY_BASIC_INFORMATION()
            query_result = kernel32.VirtualQueryEx(
                process_handle,
                ctypes.c_void_p(mem_region_addr),
                ctypes.byref(mem_info),
                ctypes.sizeof(mem_info),
            )

            if query_result == 0:
                break

            # Only scan committed, executable memory regions without guard pages
            if (
                (mem_info.State & MEM_COMMIT)
                and (mem_info.Protect & PAGE_GUARD) == 0
                and (mem_info.Protect & self.PAGE_EXECUTE_ANY)
            ):
                self.mem_regions.append(mem_info)
                region_data = MemoryOperations.read_bytes(
                    process_handle, mem_info.BaseAddress, mem_info.RegionSize
                )
                self.read_memory[mem_info.BaseAddress] = region_data

            mem_region_addr = mem_info.BaseAddress + mem_info.RegionSize

    def scan(self, pattern: list[int]) -> int:
        """
        Scan for a byte pattern across all loaded memory regions.
        Returns the absolute address of the first match, or 0 if not found.
        """
        for base_address, memory_data in self.read_memory.items():
            index = self._search_pattern(memory_data, pattern)
            if index != -1:
                return base_address + index
        return 0

    def _search_pattern(self, data: bytes, pattern: list[int]) -> int:
        """Search for a pattern within a single memory region. None values act as wildcards."""
        data_len = len(data)
        pattern_len = len(pattern)

        for i in range(data_len - pattern_len + 1):
            match = True
            for j in range(pattern_len):
                if pattern[j] is not None and pattern[j] != data[i + j]:
                    match = False
                    break
            if match:
                return i
        return -1

    @staticmethod
    def parse_pattern(pattern_string: str) -> list[int]:
        """Convert a hex string pattern to a list suitable for scanning. '?' or '??' represent wildcards."""
        items = pattern_string.split()
        pattern = []
        for item in items:
            if item in ("?", "??"):
                pattern.append(None)
            else:
                pattern.append(int(item, 16))
        return pattern
