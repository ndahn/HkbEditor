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
    origin_state: HkbRecord,  # TODO restrict to StateInfo objects
    animation: Animation = None,
    event: Event = None,
    offset_type: int = 15,  # TODO figure out how to use templates in the UI here, e.g. CmsgOffsetType.WEAPON_CATEGORY_RIGHT,
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
        TODO I think this determines how a clip is selected (e.g. based on the right hand's TAE category).
    """
    sm = ctx.find("name:AddDamage_SM")
    state_id = ctx.get_next_state_id(sm)

    default_transition = ctx.find("name:TaeBlend")
    transition = ctx.new_transition_info(
        origin_state["stateId"].get_value(),
        event,
        transition=default_transition,
        flags=TransitionInfoFlags(3584),
    )
    ctx.array_add(sm, "wildcardTransitions/transitions", transition)

    clip = ctx.new_clip(animation)
    cmsg = ctx.new_cmsg(
        animation.anim_id,
        name=f"{base_name}_CMSG",
        generators=[clip],
        offsetType=offset_type,
    )

    autotrans_event = ctx.event(f"{base_name}_to_DefaultDamageAdd")
    blend_transition = ctx.find("name:StateToStateBlend")
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
