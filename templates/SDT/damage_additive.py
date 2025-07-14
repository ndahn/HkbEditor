from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)
from hkb_editor.hkb.hkb_flags import hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags


def run(
    ctx: TemplateContext,
    base_name: str,
    origin_state: HkbRecord = HkbRecordSpec("", "hkbStateMachine::StateInfo"),
    animation: Animation = None,
    event: Event = None,
    offset_type: CmsgOffsetType = CmsgOffsetType.WEAPON_CATEGORY_RIGHT,  # TODO support in UI
):
    """Damage Additive

    Creates a transition to add an additive damage animation on top of another one.

    Author: Igor

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_name : str
        The name of your damage state.
    origin_state : HkbRecord
        The behavior state to add the damage animation to.
    animation : Animation
        The additive animation to use.
    event : Event
        The event to trigger the damage animation.
    offset_type : CmsgOffsetType, optional
        TODO
    """
    sm = ctx.find("AddDamage_SM")
    state_id = ctx.get_next_state_id(sm)

    default_transition = ctx.find("TaeBlend")
    transition = ctx.new_transition_info(
        origin_state["stateId"].get_value(),
        event,
        transition=default_transition,
        flags=TransitionInfoFlags(3584),
    )
    ctx.array_add(sm, "wildcardTransitions", transition)

    clip = ctx.new_clip(animation)
    cmsg = ctx.new_cmsg(
        name=f"{base_name}_CMSG",
        animId=animation,
        generators=[clip],
        offsetType=offset_type,
    )

    autotrans_event = ctx.event(f"{base_name}_to_DefaultDamageAdd")
    blend_transition = ctx.find("StateToStateBlend")
    state_transition = ctx.new_transition_info(
        state_id,
        autotrans_event,
        transition=blend_transition,
    )
    transitioninfo_array = ctx.new_transition_info_array(transitions=[state_transition])

    state = ctx.new_statemachine_state(
        state_id,  # TODO Igor has toStateId here?
        name=base_name,
        generator=cmsg,
        transitions=transitioninfo_array,
    )
    ctx.array_add(sm, "states", state)
