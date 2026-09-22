import csv
import io

from hkb_editor.hkb.hkb_types import HkbArray, HkbRecord


def auto_mirror_bones(bones: list[str]) -> dict[int, str]:
    """Guess each bone's mirror from its ``L_``/``R_`` or ``_L``/``_R`` affix.

    Returns a mapping of bone index to mirror bone name, leaving out bones
    with no recognizable affix or no existing counterpart.
    """
    known = set(bones)
    pairs: dict[int, str] = {}

    for idx, bone in enumerate(bones):
        if bone.startswith("L_"):
            alt_bone = "R_" + bone[2:]
        elif bone.startswith("R_"):
            alt_bone = "L_" + bone[2:]
        elif bone.endswith("_L"):
            alt_bone = bone[:-2] + "_R"
        elif bone.endswith("_R"):
            alt_bone = bone[:-2] + "_L"
        else:
            continue

        if alt_bone in known:
            pairs[idx] = alt_bone

    return pairs


def update_bone_pair_map(
    mirror_info: HkbRecord, bones: list[str], mirrors: list[str]
) -> None:
    """Write the mirror pairings into a ``hkbMirroredSkeletonInfo``.

    ``mirrors`` holds the mirror bone name for each index of ``bones``.
    Raises ValueError naming the offending entry if a name is unknown.
    """
    pair_map: HkbArray = mirror_info["bonePairMap"]

    for idx in range(len(pair_map)):
        alt_bone = mirrors[idx]
        try:
            pair_map[idx] = bones.index(alt_bone)
        except ValueError:
            raise ValueError(
                f"{alt_bone} ({idx}) is not a valid bone name"
            ) from None


def bone_pairs_to_csv(bones: list[str], mirrors: list[str]) -> str:
    """Render the pairings as CSV with index, bone, mirror index, mirror bone."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["idx", "bone", "mirror_idx", "mirror_bone"])

    for idx, bone in enumerate(bones):
        alt_bone = mirrors[idx]
        writer.writerow([idx, bone, bones.index(alt_bone), alt_bone])

    return output.getvalue()
