from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)


def run(
    ctx: TemplateContext,
    base_anim_id: int = 3040,
    num_attacks: int = 1,
    categories: int = 1,
):
    """New NPC Attacks

    Creates CMSGs for NPCs starting at aXXX_YYYYYY, where X is 0 and Y is your base_anim_id. For each subsequent attack Y increases by 1. For each additional category X increases by 1.

    For every Y a wildcard transition is created using the default transition effect and a new event called 'W_Attack<Y>'.

    Author: FloppyDonuts

    Status: verified

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_anim_id : int, optional
        Base animation ID (e.g. 3091 for a000_003091).
    num_attacks : int, optional
        How many new CMSGs to generate.
    categories : int, optional
        Categories to create clip generators for. Don't generate clip generators if this is 0.
    """
    statemachine = ctx.find("name=Attack_SM")
    base_state_id = ctx.get_next_state_id(statemachine)

    transition_flags = (
        TransitionInfoFlags.ALLOW_SELF_TRANSITION_BY_TRANSITION_FROM_ANY_STATE
        | TransitionInfoFlags.IS_LOCAL_WILDCARD
        | TransitionInfoFlags.IS_GLOBAL_WILDCARD
    )

    for attack_idx in range(num_attacks):
        state_id = base_state_id + attack_idx
        anim_id = base_anim_id + attack_idx
        event = ctx.event(f"W_Attack{anim_id}")

        clips = []
        for cat in range(categories):
            anim = Animation.make_name(cat, anim_id)
            clips.append(ctx.new_clip(anim))

        cmsg = ctx.new_cmsg(
            anim_id,
            name=f"Attack{anim_id}_CMSG",
            generators=clips,
            offsetType=CmsgOffsetType.ANIM_ID,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.SELF_TRANSITION,
        )
        state = ctx.new_stateinfo(
            stateId=state_id,
            name=f"Attack{anim_id}",
            generator=cmsg,
        )

        ctx.array_add(statemachine, "states", state)
        ctx.register_wildcard_transition(
            statemachine, state_id, event, flags=transition_flags
        )
