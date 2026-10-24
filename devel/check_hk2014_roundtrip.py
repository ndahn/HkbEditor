"""Checks that a hk2014 packfile survives the conversion to hk2018 and back.

The result should be identical to the input (apart from line endings). Differences
are either a bug in the converter, or something havok writes differently than the
converter expects, e.g. the line breaks of arrays.

Usage (from the repository root):
    python devel/check_hk2014_roundtrip.py test/c0000_ds3.xml
"""

import sys
import difflib
from pathlib import Path

# Allow running without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

from hkb_editor.hkb.tagfile_convert import hk2014_to_2018, hk2018_to_2014


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1])
    original = path.read_bytes().decode("utf-8").replace("\r\n", "\n")

    tagfile = hk2014_to_2018(path)
    result = hk2018_to_2014(tagfile)

    if original.strip() == result.strip():
        print("Identical")
        return 0

    diff = list(
        difflib.unified_diff(
            original.splitlines(), result.splitlines(), "original", "converted", lineterm=""
        )
    )
    print("\n".join(diff[:100]))
    if len(diff) > 100:
        print(f"... and {len(diff) - 100} more lines")

    return 1


if __name__ == "__main__":
    sys.exit(main())
