from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)


def run(
    ctx: TemplateContext,
):
    """NPC Summons

    Makes an NPC summonable if it isn't already. Summons are activated by firing `W_BuddyGenerate` and `W_BuddyDisappear` (or `W_Event1830` and `W_Event1840` for EMEVD and co).

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/npc_summons/

    Author: FloppyDonuts

    Status: confirmed

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    """
    master_sm = ctx.find("name=Master_SM")
    default_transition = ctx.find("name=DefaultTransition")

    try:
        # Check if it already exists
        ctx.find("name=BuddyGenerate", start_from=master_sm)
        ctx.logger.info("BuddyGenerate already exists, nothing to do")
    except KeyError:
        summon_stateid = ctx.get_next_state_id(master_sm)
        summon_state, _, _ = ctx.create_state_chain(
            summon_stateid,
            "a000_001830",
            "BuddyGenerate",
            cmsg_kwargs={
                "offsetType": CmsgOffsetType.ANIM_ID,
                "animeEndEventType": AnimeEndEventType.FIRE_IDLE_EVENT,
                "changeTypeOfSelectedIndexAfterActivate": ChangeIndexType.SELF_TRANSITION,
                "checkAnimEndSlotNo": 1,
            },
        )

        ctx.array_add(master_sm, "states", summon_state)
        ctx.register_wildcard_transition(
            master_sm,
            summon_stateid,
            "W_BuddyGenerate",
            transition_effect=default_transition,
        )
        ctx.register_wildcard_transition(
            master_sm,
            summon_stateid,
            "W_Event1830",
            transition_effect=default_transition,
        )
        

    try:
        # Check if it already exists
        ctx.find("name=BuddyDisappear", start_from=master_sm)
        ctx.logger.info("BuddyDisappear already exists, nothing to do")
    except KeyError:
        disappear_stateid = ctx.get_next_state_id(master_sm)
        disappear_state, _, _ = ctx.create_state_chain(
            disappear_stateid,
            "a000_001840",
            "BuddyDisappear",
            cmsg_kwargs={
                "offsetType": CmsgOffsetType.ANIM_ID,
                "animeEndEventType": AnimeEndEventType.FIRE_IDLE_EVENT,
                "changeTypeOfSelectedIndexAfterActivate": ChangeIndexType.SELF_TRANSITION,
                "checkAnimEndSlotNo": 1,
            },
        )

        ctx.array_add(master_sm, "states", disappear_state)
        ctx.register_wildcard_transition(
            master_sm,
            disappear_stateid,
            "W_BuddyDisappear",
            transition_effect=default_transition,
        )
        ctx.register_wildcard_transition(
            master_sm,
            disappear_stateid,
            "W_Event1840",
            transition_effect=default_transition,
        )
