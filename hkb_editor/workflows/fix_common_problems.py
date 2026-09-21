import logging

from hkb_editor.hkb import HavokBehavior, HkbArray, HkbPointer
from hkb_editor.templates.common import Animation


logger = logging.getLogger("fix_common_problems")


def fix_array_null_pointers(behavior: HavokBehavior) -> int:
    """Drop unset pointers from generator arrays. Returns how many."""
    issues = 0

    for record in behavior:
        array: HkbArray
        for path, array in record.find_fields_by_class(HkbArray):
            # Some pointer arrays in the root objects must not be altered, so we
            # limit it to generators for now where we know how they work
            if not path.endswith("generators"):
                continue

            if array.is_pointer_array:
                invalid = []
                for idx, ptr in enumerate(array):
                    if not ptr.is_set():
                        invalid.append(idx)

                for idx in reversed(invalid):
                    array.pop(idx)

                issues += len(invalid)

    logger.info(f"Removed {issues} stray null pointers from arrays")
    return issues


def fix_clip_animation_ids(behavior: HavokBehavior) -> int:
    """Point every clip generator at the right animation index.

    Missing animations are registered along the way. Returns how many clip
    generators were corrected.
    """
    issues = 0
    new_anims = 0

    for record in behavior:
        if record.type_name == "hkbClipGenerator":
            anim_name = record["animationName"].get_value()
            if not Animation.is_valid_name(anim_name):
                logger.warning(f"{record} has invalid animationName {anim_name}")
                continue

            anim_id = record["animationInternalId"].get_value()
            true_anim_id = behavior.find_animation(anim_name, None)

            if anim_id != true_anim_id:
                if true_anim_id is None:
                    true_anim_id = behavior.create_animation(anim_name)
                    new_anims += 1

                record["animationInternalId"] = true_anim_id
                issues += 1

    logger.info(f"Added {new_anims} missing animation IDs")
    logger.info(f"Fixed {issues} clip generators")
    return issues


def clear_invalid_pointers(behavior: HavokBehavior) -> int:
    """Unset pointers referencing object IDs that don't exist. Returns how many."""
    invalid = 0

    for record in behavior.objects.values():
        ptr: HkbPointer
        for _, ptr in record.find_fields_by_class(HkbPointer):
            oid = ptr.get_value()
            if oid:
                try:
                    behavior.objects[oid]
                except KeyError:
                    ptr.set_value(None)
                    invalid += 1

    logger.info(f"Unset {invalid} invalid pointers")
    return invalid


def remove_orphans(behavior: HavokBehavior) -> int:
    """Delete objects unreachable from the behavior root. Returns how many."""
    root = behavior.behavior_root
    g = behavior.build_graph(root.object_id)

    unmapped_ids = set(behavior.objects.keys()).difference(g.nodes)
    orphans = [behavior.objects[oid] for oid in unmapped_ids]

    for obj in orphans:
        behavior.delete_object(obj)

    logger.info(f"Removed {len(orphans)} abandoned objects")
    return len(orphans)


# Fix key -> (label, tooltip, enabled by default, function)
COMMON_PROBLEMS = {
    "array_null_pointers": (
        "Remove null pointers from generators",
        "Null pointers inside generator arrays can cause game crashes when "
        "accessed. When removed from manual selectors this will change array "
        "indices.",
        True,
        fix_array_null_pointers,
    ),
    "clip_animation_ids": (
        "Fix clip animation IDs",
        "ClipGenerators refer to an entry in the animations array that is not "
        "updated by ERClipGenerator. This ensures that this array contains all "
        "animations and references are valid.",
        True,
        fix_clip_animation_ids,
    ),
    "clear_invalid_pointers": (
        "Clear invalid pointers",
        "Any pointers referencing non-existing object IDs will prevent "
        "converting the behavior back to havok format.",
        True,
        clear_invalid_pointers,
    ),
    "remove_orphans": (
        "Remove orphaned objects",
        "Removes all objects that are not referenced by any other object. The "
        "behavior root items are protected.",
        False,
        remove_orphans,
    ),
}


def fix_common_problems(behavior: HavokBehavior, fixes: list[str]) -> int:
    """Run the named fixes in one transaction. Returns the total issue count."""
    total = 0

    with behavior.transaction():
        for key in fixes:
            total += COMMON_PROBLEMS[key][3](behavior)

    logger.info(f"Fixed {total} issues")
    return total
