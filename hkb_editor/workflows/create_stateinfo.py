from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as OffsetType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)
from hkb_editor.templates.common import CommonActionsMixin, Event, Animation


def get_statemachines(behavior: HavokBehavior) -> list[HkbRecord]:
    """All hkbStateMachine records in the behavior."""
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    return list(behavior.find_objects_by_type(sm_type))


def create_stateinfo(
    behavior: HavokBehavior,
    statemachine_name: str,
    base_name: str,
    animation: Animation,
    event: Event,
    *,
    playback_mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
    animation_end_event_type: AnimeEndEventType = AnimeEndEventType.FIRE_IDLE_EVENT,
    offset_type: OffsetType = OffsetType.IDLE_CATEGORY,
    enable_tae: bool = True,
    enable_script: bool = True,
    transition_effect: HkbRecord = None,
    copy_transition_effect: bool = True,
    transition_flags: TransitionInfoFlags = TransitionInfoFlags(3584),
) -> tuple[HkbRecord, HkbRecord, HkbRecord]:
    """Create a new animation slot: StateInfo, CMSG and ClipGenerator.

    The state is registered as a wildcard transition on the named state
    machine, so it can be triggered from HKS through ``event``.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    statemachine_name : str
        Name of the hkbStateMachine to attach the state to.
    base_name : str
        Used to name the CMSG, ClipGenerator and TransitionInfo.
    animation : Animation
        Animation the ClipGenerator plays.
    event : Event
        Event that activates the new state.
    playback_mode : PlaybackMode
        ClipGenerator playback mode.
    animation_end_event_type : AnimeEndEventType
        What the CMSG does when the animation ends.
    offset_type : OffsetType
        How the CMSG picks the clip to activate.
    enable_tae : bool
        Whether the CMSG should use the TAE.
    enable_script : bool
        Whether the CMSG should call HKS functions (onUpdate and co.).
    transition_effect : HkbRecord, optional
        How animations blend when transitioning into the new state.
    copy_transition_effect : bool
        Copy the transition effect instead of reusing the instance.
    transition_flags : TransitionInfoFlags
        Flags for the new TransitionInfo.

    Returns
    -------
    tuple
        The new ``(state, cmsg, clip)``.
    """
    util = CommonActionsMixin(behavior)

    statemachine = next(
        behavior.query(f"name='{statemachine_name}' type_name=hkbStateMachine")
    )
    new_state_id = util.get_next_state_id(statemachine)

    with behavior.transaction():
        state, cmsg, clip = util.create_state_chain(
            new_state_id,
            animation,
            base_name,
            cmsg_kwargs={
                "animeEndEventType": animation_end_event_type,
                "offsetType": offset_type,
                "enableTae": enable_tae,
                "enableScript": enable_script,
            },
            clip_kwargs={"mode": playback_mode},
        )

        util.add_wildcard_state(
            statemachine,
            state,
            event,
            transition_effect=transition_effect,
            copy_transition_effect=copy_transition_effect,
            flags=transition_flags,
        )

    return state, cmsg, clip
