from typing import Callable
import logging

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.templates.common import CommonActionsMixin, Animation


logger = logging.getLogger(__name__)


def validate_animation_names(
    behavior: HavokBehavior, names: list[str]
) -> list[str]:
    """Strip and verify animation names. Raises ValueError on an unknown one."""
    valid = set(behavior.get_animations())
    selected = []

    for anim in names:
        anim = anim.strip()
        if not anim:
            continue

        if anim not in valid:
            raise ValueError(f"{anim} is not an existing animation")

        selected.append(anim)

    return selected


def duplicate_clip_category(
    behavior: HavokBehavior,
    animations: list[str],
    target_category: int,
    *,
    replace_existing: bool = False,
    on_warning: Callable[[str], None] = None,
) -> list[HkbRecord]:
    """Copy every clip of ``animations`` into a new animation category.

    For each animation a counterpart in ``target_category`` is created, and
    every ClipGenerator referencing the original is duplicated inside each of
    its parents. Animation entries are only created where clips actually
    exist.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    animations : list of str
        Source animation names, already validated.
    target_category : int
        The aXXX category to copy into.
    replace_existing : bool
        Overwrite clips that already target the new animation instead of
        skipping them.
    on_warning : callable, optional
        Called with a message when a parent has to be skipped.

    Returns
    -------
    list of HkbRecord
        The clips that were created or overwritten.
    """
    util = CommonActionsMixin(behavior)
    copies: list[HkbRecord] = []

    def warn(msg: str) -> None:
        logger.warning(msg)
        if on_warning:
            on_warning(msg)

    with behavior.transaction():
        all_clips = behavior.query("type=hkbClipGenerator")

        for anim_name in animations:
            # Find all clips using this animation
            anim_clips = [
                c for c in all_clips if c["animationName"].get_value() == anim_name
            ]
            anim = util.animation(anim_name, create=False)
            new_anim_name = Animation.make_name(target_category, anim.anim_id)

            for clip in anim_clips:
                # Only create animation entries when there are actually clips for them
                new_anim = util.animation(new_anim_name)

                # Duplicate the clip in each of its parents
                parents = behavior.get_immediate_parents(clip)
                clip_copy = None

                for parent in parents:
                    generators: HkbArray[HkbPointer] = parent.get_field(
                        "generators", None
                    )
                    if not generators:
                        warn(
                            f"Could not determine generator field for "
                            f"{clip.object_id} in parent {parent}"
                        )
                        continue

                    skip = False
                    for ptr in generators:
                        target = ptr.get_target()
                        if target["animationName"].get_value() == new_anim_name:
                            if replace_existing:
                                util.copy_attributes(clip, target)
                                copies.append(target)

                            skip = True
                            break

                    if skip:
                        continue

                    # Make a copy if we don't have one already. All parents are
                    # referencing the same instance, so we will do the same.
                    if not clip_copy:
                        new_name = (
                            clip["name"]
                            .get_value()
                            .replace(f"a{anim.category}_", f"a{new_anim.category}")
                        )
                        clip_copy: HkbRecord = util.make_copy(
                            clip,
                            name=new_name,
                            animationName=new_anim.name,
                            animationInternalId=new_anim.index,
                        )
                        copies.append(clip_copy)

                    # Add the copy to the parent's generators
                    generators.append(clip_copy)

    return copies
