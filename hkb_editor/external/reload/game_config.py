"""
Game Configuration Module

Contains all game-specific data including AOB patterns, memory offsets,
shellcode templates, and process names. This allows easy adaptation to
different game versions or other games using the same engine.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GameConfig:
    """Configuration for a specific game version."""

    # Process information
    process_names: list[str]
    """List of possible process names (without .exe extension)"""

    # AOB patterns for memory scanning
    world_chr_man_aob: str
    """Pattern to find the WorldChrMan pointer"""

    world_chr_man_jump_start: int
    """Offset to start of relative address in WorldChrMan pattern"""

    world_chr_man_jump_end: int
    """Offset to end of instruction in WorldChrMan pattern"""

    world_chr_man_struct_offset: int
    """Offset within WorldChrMan structure"""

    # Optional crash fix
    crash_patch_aob: Optional[str] = None
    """Pattern to find crash patch location (optional)"""

    crash_patch_jump_end: Optional[int] = None
    """Offset from end of pattern to patch location"""

    crash_patch_bytes: Optional[bytes] = None
    """Bytes to write for crash fix"""

    # Shellcode template
    shellcode_template: bytes = None
    """Raw shellcode bytes with placeholders for addresses"""

    shellcode_data_offset: int = 2
    """Offset in shellcode where data setup address is patched (8 bytes)"""

    shellcode_ptr_offset: int = 12
    """Offset in shellcode where WorldChrMan pointer is patched (8 bytes)"""


# Elden Ring version 1.07+
ELDEN_RING_1_07 = GameConfig(
    process_names=["eldenring", "start_protected_game"],
    world_chr_man_aob="48 8B 05 ?? ?? ?? ?? 48 85 C0 74 0F 48 39 88",
    world_chr_man_jump_start=3,
    world_chr_man_jump_end=7,
    world_chr_man_struct_offset=0x1E668,
    crash_patch_aob="80 65 ?? FD 48 C7 45 ?? 07 00 00 00 ?? 8D 45 48 4C 89 60 ?? 48 83 78 ?? 08 72 03 48 8B 00 66 44 89 20 49 8B 8F ?? ?? ?? ?? 48 8B 01 48 ?? ??",
    crash_patch_jump_end=3,
    crash_patch_bytes=b"\x48\x31\xd2",
    # fmt: off
    shellcode_template=bytes([
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
    ]),
    # fmt: on
    shellcode_data_offset=2,
    shellcode_ptr_offset=12,
)


# Elden Ring version 1.06 and earlier
ELDEN_RING_1_06 = GameConfig(
    process_names=["eldenring", "start_protected_game"],
    world_chr_man_aob="48 8B 05 ?? ?? ?? ?? 48 85 C0 74 0F 48 39 88",
    world_chr_man_jump_start=3,
    world_chr_man_jump_end=7,
    world_chr_man_struct_offset=0x185C0,
    crash_patch_aob="80 65 ?? FD 48 C7 45 ?? 07 00 00 00 ?? 8D 45 48 4C 89 60 ?? 48 83 78 ?? 08 72 03 48 8B 00 66 44 89 20 49 8B 8F ?? ?? ?? ?? 48 8B 01 48 ?? ??",
    crash_patch_jump_end=3,
    crash_patch_bytes=b"\x48\x31\xd2",
    # fmt: off
    shellcode_template=bytes([
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
    ]),
    # fmt: on
    shellcode_data_offset=2,
    shellcode_ptr_offset=12,
)


# All available configurations (ordered by preference - newest first)
ALL_CONFIGS = [
    ELDEN_RING_1_07,
    ELDEN_RING_1_06,
]

# Default configuration (latest version)
DEFAULT_CONFIG = ELDEN_RING_1_07
