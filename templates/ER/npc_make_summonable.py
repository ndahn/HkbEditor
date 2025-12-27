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
    """Make NPC Summonable

    Makes an NPC summonable if it isn't already. This will create the BuddyGenerate and BuddyDisappear states in the Master_SM, which are activated by firing W_BuddyGenerate and W_BuddyDisappear.

    Author: FloppyDonuts & Managarm

    Status: hopeful

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    """
    master_sm = ctx.find("name=Master_SM")
    default_transition = ctx.find("name=DefaultTransition")

    try:
        # Check if it already exists
        ctx.find("name=BuddyGenerate")
    except KeyError:
        pass
    else:
        summon_stateid = ctx.get_next_state_id(master_sm)
        ctx.create_state_chain(
            summon_stateid,
            "a000_001830",
            "BuddyGenerate",
            cmsg_kwargs={
                "offsetType": CmsgOffsetType.ANIM_ID,
                "animeEndEventType": AnimeEndEventType.FIRE_IDLE_EVENT,
                "changeTypeOfSelectedIndex": ChangeIndexType.SELF_TRANSITION,
                "checkAnimEndSlotNo": 1,
            },
        )

        ctx.register_wildcard_transition(
            master_sm,
            summon_stateid,
            "W_BuddyGenerate",
            transition_effect=default_transition,
        )

    try:
        # Check if it already exists
        ctx.find("name=BuddyDisappear")
    except KeyError:
        pass
    else:
        summon_stateid = ctx.get_next_state_id(master_sm)
        ctx.create_state_chain(
            summon_stateid,
            "a000_001840",
            "BuddyDisappear",
            cmsg_kwargs={
                "offsetType": CmsgOffsetType.ANIM_ID,
                "animeEndEventType": AnimeEndEventType.FIRE_IDLE_EVENT,
                "changeTypeOfSelectedIndex": ChangeIndexType.SELF_TRANSITION,
                "checkAnimEndSlotNo": 1,
            },
        )

        ctx.register_wildcard_transition(
            master_sm,
            summon_stateid,
            "W_BuddyDisappear",
            transition_effect=default_transition,
        )
