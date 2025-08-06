from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
    base_anim_id: int = 3091,
    num_attacks: int = 10,
):
    """Generate NPC Attacks

    Creates CMSGs for NPCs starting at a000_{base_anim_id} and will cover a000 to a005. 
    
    TODO more details

    Author: FloppyDonuts
    
    Status: untested

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_anim_id : int, optional
        Base animation ID (e.g. 3091 for a000_003091).
    num_attacks : int, optional
        How many new CMSGs to generate.
    """
    statemachine = ctx.find("Attack_SM")
    base_state_id = ctx.get_next_state_id(statemachine)

    for i in range(num_attacks):
        anim_id = base_anim_id + i
        state_id = base_state_id + i

        # TODO check if these already exist
        clips = [
            ctx.new_clip(f"a00{i}_{anim_id + i:06}")
            for i in range(6)
        ]
        cmsg = ctx.new_cmsg(
            anim_id,
            name=f"Attack{anim_id}_CMSG",
            generators=clips,
            offsetType=CmsgOffsetType.ANIM_ID,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.SELF_TRANSITION,
        )
        state = ctx.new_statemachine_state(
            stateId=state_id,
            name=f"Attack{anim_id}",
            generator=cmsg,
        )

        ctx.array_add(statemachine, "states", state)
