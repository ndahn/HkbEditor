import ctypes
import struct
from ctypes import wintypes

from .windows_api import kernel32, MEM_COMMIT, MEM_RELEASE, MEM_RESERVE


class MemoryOperations:
    """Low-level memory operations wrapper for Windows API calls."""

    @staticmethod
    def read_bytes(handle: int, address: int, length: int) -> bytes:
        """Read raw bytes from process memory."""
        buffer = ctypes.create_string_buffer(length)
        bytes_read = ctypes.c_size_t()
        success = kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(address), buffer, length, ctypes.byref(bytes_read)
        )
        return buffer.raw[: bytes_read.value] if success else b""

    @staticmethod
    def write_bytes(handle: int, address: int, data: bytes) -> bool:
        """Write raw bytes to process memory."""
        bytes_written = ctypes.c_size_t()
        return bool(
            kernel32.WriteProcessMemory(
                handle,
                ctypes.c_void_p(address),
                data,
                len(data),
                ctypes.byref(bytes_written),
            )
        )

    @staticmethod
    def read_uint32(handle: int, address: int) -> int:
        """Read a 32-bit unsigned integer from process memory."""
        data = MemoryOperations.read_bytes(handle, address, 4)
        return struct.unpack("<I", data)[0] if len(data) == 4 else 0

    @staticmethod
    def read_int64(handle: int, address: int) -> int:
        """Read a 64-bit integer from process memory."""
        data = MemoryOperations.read_bytes(handle, address, 8)
        return struct.unpack("<Q", data)[0] if len(data) == 8 else 0

    @staticmethod
    def write_int64(handle: int, address: int, value: int) -> bool:
        """Write a 64-bit integer to process memory."""
        data = struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)
        return MemoryOperations.write_bytes(handle, address, data)

    @staticmethod
    def write_int8(handle: int, address: int, value: int) -> bool:
        """Write an 8-bit integer to process memory."""
        data = struct.pack("<B", value & 0xFF)
        return MemoryOperations.write_bytes(handle, address, data)

    @staticmethod
    def allocate_memory(handle: int, size: int, protect: int) -> int:
        """Allocate memory in the target process."""
        return kernel32.VirtualAllocEx(
            handle, None, size, MEM_COMMIT | MEM_RESERVE, protect
        )

    @staticmethod
    def free_memory(handle: int, address: int, size: int) -> bool:
        """Free allocated memory in the target process."""
        return bool(kernel32.VirtualFreeEx(handle, address, size, MEM_RELEASE))

    @staticmethod
    def create_remote_thread(handle: int, start_address: int) -> int:
        """Create and start a thread in the target process."""
        thread_id = wintypes.DWORD()
        return kernel32.CreateRemoteThread(
            handle, None, 0, start_address, None, 0, ctypes.byref(thread_id)
        )

    @staticmethod
    def wait_for_thread(handle: int, timeout: int = 30000) -> int:
        """Wait for a thread to complete with specified timeout."""
        return kernel32.WaitForSingleObject(handle, timeout)

    @staticmethod
    def close_handle(handle: int) -> bool:
        """Close a Windows handle."""
        return bool(kernel32.CloseHandle(handle))
