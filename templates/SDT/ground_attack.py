from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)
from hkb_editor.hkb.hkb_flags import hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags


def run(
    ctx: TemplateContext,
    base_name: str,
    animation: Animation,
    event: Event,
):
    """New Ground Attack

    Creates a new attack slot that can be executed while on the ground.

    Author: Igor

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_name : str
        The name of your new attack.
    animation : Animation
        The animation to use.
    event : Event
        The event to trigger the animation.
    """
    sm = ctx.find("name=GroundAttack_SM")
    state_id = ctx.get_next_state_id(sm)

    default_transition = ctx.find("name=TaeBlend")
    transition = ctx.new_transition_info(
        state_id, 
        event,
        transition=default_transition,
        flags=TransitionInfoFlags(3584),
    )
    ctx.array_add(sm, "wildcardTransitions/transitions", transition)

    clip = ctx.new_clip(animation)
    cmsg = ctx.new_cmsg(
        animId=animation.anim_id,
        name=f"{base_name}_CMSG",
        generators=[clip],
    )
    state = ctx.new_statemachine_state(
        state_id,
        name=base_name,
        generator=cmsg,
    )
    ctx.array_add(sm, "states", state)
