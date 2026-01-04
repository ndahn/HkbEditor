from typing import Annotated

from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)


def run(
    ctx: TemplateContext,
    animation: Animation,
    game_event_id: int = 70000,
    transition_effect: Annotated[HkbRecord, "hkbTransitionEffect"] = "DefaultTransition",
):
    """Game Event (Player)

    Create a game event that can be triggered from HKS, EMEVD, ESD, objects, etc. The new event will be called `W_Event<game_event_id>`.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/er/game_event_player/
    
    Author: FloppyDonuts
    
    Status: hopeful

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    game_event_id : int, optional
        ID of the event. 
    animation : Animation, optional
        The event animation. Usually placed in a000.
    transition_effect : Annotated[HkbRecord, &quot;hkbTransitionEffect&quot;], optional
        Transition effect to use. If not specified, the default transition will be used.
    """
    event_sm = ctx.find("name=Event_SM")
    state_id = ctx.get_next_state_id(event_sm)

    if ctx.find(f"name=Event{game_event_id}", default=None):
        raise ValueError(f"Event{game_event_id} already exists!")

    if not transition_effect:
        transition_effect = ctx.find("name=DefaultTransition")
    
    state, _, _ = ctx.create_state_chain(
        state_id,
        animation,
        f"Event{game_event_id}",
        cmsg_kwargs={

        },
    )

    ctx.register_wildcard_transition(
        event_sm,
        state_id,
        f"W_Event{game_event_id}",
        transition_effect=transition_effect,
    )
    ctx.array_add(event_sm, "states", state)
