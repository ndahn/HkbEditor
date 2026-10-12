import logging

from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.hkb.hkb_enums import hkbClipGenerator_PlaybackMode as PlaybackMode
from hkb_editor.hkb.hkb_flags import hkbClipGenerator_Flags as ClipFlags
from hkb_editor.templates.common import CommonActionsMixin, Animation


logger = logging.getLogger(__name__)


def validate_clip_animations(animations: list[str]) -> list[str]:
    """Strip empty lines and verify the animation names.

    Raises ValueError if the list is empty or a name is malformed.
    """
    names = [line.strip() for line in animations if line.strip()]

    if not names:
        raise ValueError("No animations added")

    for name in names:
        if not Animation.is_valid_name(name):
            raise ValueError(f"Invalid animation {name}")

    return names


def register_clips(
    behavior: HavokBehavior,
    animations: list[str],
    *,
    playback_mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
    flags: ClipFlags = ClipFlags.NONE,
    starttime_variable: str = None,
    reuse_clips: bool = False,
) -> list[HkbRecord]:
    """Create a ClipGenerator per animation and attach it to matching CMSGs.

    CMSGs are matched on ``animId``; animations with no CMSG are skipped with
    a warning.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    animations : list of str
        Animation names, already validated.
    playback_mode : PlaybackMode
        Playback mode for the new clips.
    flags : ClipFlags
        Clip flags for the new clips.
    starttime_variable : str, optional
        Bind the clips' ``startTime`` to this variable.
    reuse_clips : bool
        Share one clip instance between CMSGs of the same animation. Rarely
        useful and can cause self transition problems (e.g. dodge stutter).

    Returns
    -------
    list of HkbRecord
        The clips that were created.
    """
    util = CommonActionsMixin(behavior)
    clips: dict[Animation, HkbRecord] = {}
    cmsg_groups: dict[int, list[HkbRecord]] = {}

    with behavior.transaction():
        for name in animations:
            anim = util.animation(name)
            cmsgs = cmsg_groups.get(anim.anim_id)
            clip = None

            if not cmsgs:
                cmsgs = list(
                    behavior.query(
                        f"type_name=CustomManualSelectorGenerator animId={anim.anim_id}"
                    )
                )

            if not cmsgs:
                logger.warning(f"Could not find any CMSGs for {anim}")
                continue

            cmsg_groups[anim.anim_id] = cmsgs

            if reuse_clips:
                clip = clips.get(anim)

            if not clip:
                clip = util.new_clip(anim, mode=playback_mode, flags=flags)

                if starttime_variable:
                    util.bind_variable(clip, "startTime", starttime_variable)

                clips[anim] = clip

            for cmsg in cmsgs:
                cmsg["generators"].append(clip)

    return list(clips.values())
