from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


# Every template MUST have a function called "run"
def run(
    ctx: TemplateContext,
    event_start_id: int = 20000,
    num_events: int = 1,
    category: int = 0,
):
    """Game Event (NPC)

    Create a range of NPC game events that can be triggered from HKS, EMEVD, ESD, objects, etc. The event IDs will also correspond to the animation IDs. The new events will be called `W_Event<event_id>`.

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/game_event_npc/

    Author: VIVID

    Status: confirmed

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    event_start_id : int, optional
        ID of the first event, should be >= 20000.
    num_events : int, optional
        How many events to create.
    category : int, optional
        The animation category to use.
    """
    event_single_sm = ctx.find("name=EventSingle_SM")
    transition_effect = ctx.find("name=DefaultTransition")
    state_id = ctx.get_next_state_id(event_single_sm)

    for eventid in range(event_start_id, event_start_id + num_events):
        anim = Animation.make_name(category, eventid)
        name = f"Event{eventid}"

        if not 20000 <= eventid:
            ctx.logger.warning(f"{name} is outside NPC event slot range")

        if ctx.find(f"animationName={anim}", default=None):
            ctx.logger.info(f"{name} Event Already Exist")
            continue
        elif cmsg := ctx.find(
            f"animId={eventid}", start_from=event_single_sm, default=None
        ):
            ctx.logger.info(f"Registering new clip for {anim}")
            ctx.array_add(cmsg, "generators", ctx.new_clip(anim))
        else:
            ctx.logger.info(f"Creating new slot {name}")
            state, _, _ = ctx.create_state_chain(
                state_id,
                anim,
                name,
                cmsg_kwargs={
                    "offsetType": CmsgOffsetType.ANIM_ID,
                    "animeEndEventType": AnimeEndEventType.NONE,
                    "changeTypeOfSelectedIndexAfterActivate": ChangeIndexType.SELF_TRANSITION,
                    "checkAnimEndSlotNo": 1,
                },
            )

            ctx.array_add(event_single_sm, "states", state)
            ctx.register_wildcard_transition(
                event_single_sm,
                state_id,
                f"W_Event{eventid}",
                transition_effect=transition_effect,
            )

            state_id = state_id + 1
