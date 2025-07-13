from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)
from hkb_editor.hkb.hkb_flags import hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags


def run(
    ctx: TemplateContext,
    base_name: str = "Attack",
    action_offset: int = 3,
    anim_start: int = 3000,
    num_anims: int = 10,
    create_attack_event: bool = True,
    create_regular_event: bool = True,
):
    """New NPC Animations

    This template allows you to register in the 3000~3109 range for any enemy. New events can be called by AI and events. Note that this should be used on a c9997.xml behavior.

    For every animation generated, two corresponding events are generated: W_Attack<anim_id> and W_Event<anim_id>, where <anim_id> is the animation ID (the Y part in aXXX_YYYYYY minus leading zeros).

    Author: Ionian

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_name : str, optional
        This string will be used for e.g. CMSG names.
    action_offset : int, optional
        The TAE range to register new animations in (e.g. 3 = a300).
    anim_start : int, optional
        ID at which to start registering new animations (the Y part in aXXX_YYYYYY).
    num_anims : int, optional
        How many new animations to generate.
    create_attack_event : bool, optional
        Create the corresponding W_Attack<anim_id> events.
    create_regular_event : bool, optional
        Create the corresponding W_Event<anim_id> events
    """
    if not 0 <= action_offset <= 3:
        raise ValueError("Action offset must be within 0~3")

    if anim_start < 3000 or anim_start + num_anims > 3109:
        raise ValueError("Actions must be within 3000~3109")

    # NOTE Yes, Sekiro has a typo here
    sm = ctx.find("DefualtAttack_SM")
    state_id = ctx.get_next_state_id(sm)

    default_transition = ctx.find("type_name:CustomTransitionEffect DefaultTransition")

    # Register new animations
    for x in range(anim_start, anim_start + num_anims):
        animation_name = f"a{action_offset}00_{x:06}"
        try:
            ctx.get_animation(animation_name)
        except ValueError:
            # Action already exists, continue
            ctx.logger.debug(f"Animation {animation_name} already exists")
            continue
        
        anim = ctx.new_animation(animation_name)

        clip = ctx.new_clip(anim)
        cmsg = ctx.new_cmsg(
            name=f"{base_name}{anim.anim_id}_CMSG",
            animId=anim,
            generators=[clip],
            offsetType=CmsgOffsetType.ANIM_ID,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.SELF_TRANSITION,
        )
        state = ctx.new_statemachine_state(
            state_id,
            name=f"{base_name}{anim.anim_id}",
            generator=cmsg,
        )
        ctx.array_add(sm, "states", state.object_id)

        transition_flags = TransitionInfoFlags(3584)

        if create_attack_event:
            attack_event = ctx.new_event(f"W_Attack{anim.anim_id}")
            transition = ctx.new_transition_info(
                state_id,
                attack_event,
                transition=default_transition,
                flags=transition_flags,
            )
            ctx.array_add(sm, "wildcardTransitions", transition)

        if create_regular_event:
            attack_event = ctx.new_event(f"W_Event{anim.anim_id}")
            transition = ctx.new_transition_info(
                state_id,
                attack_event,
                transition=default_transition,
                flags=transition_flags,
            )
            ctx.array_add(sm, "wildcardTransitions", transition)

        # One state per animation
        state_id += 1


    # TODO tell user about event_names.txt
    # We could generate the event_names, etc when those arrays are modified?
