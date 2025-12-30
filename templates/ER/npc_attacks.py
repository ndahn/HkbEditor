from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
    anim_id_start: int = 3050,
    anim_id_step: int = 1,
    num_attacks: int = 1,
    category: int = 0,
):
    """New NPC Attacks

    Creates num_attacks new NPC attack slots starting at aXXX_YYYYYY, where X is the category and Y anim_id_start. For each subsequent attack Y increases by 1. For each additional category X increases by 1.

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
    attack_sm = ctx.find("name=Attack_SM")
    transition_effect = ctx.find("name=DefaultTransition")
    state_id = ctx.get_next_state_id(attack_sm)

    for anim_id in range(
        anim_id_start, anim_id_start + anim_id_step * num_attacks, anim_id_step
    ):
        anim = Animation.make_name(category, anim_id)
        name = f"Attack{anim_id}"
        event = ctx.event(f"W_{name}")

        if ctx.find(f"animationName={anim}", default=None):
            # Already exists, nothing to do
            ctx.logger.info(f"Attack {name} already exists")
            pass
        elif cmsg := ctx.find(f"animId={anim_id}", start_from=attack_sm, default=None):
            # CMSG for animId exists, but no clip for this category
            ctx.logger.info(f"Registering new clip for {anim}")
            ctx.array_add(cmsg, "generators", ctx.new_clip(anim))
        else:
            # Nothing exists yet, create the entire thing
            ctx.logger.info(f"Creating new slot {name}")
            state, _, _ = ctx.create_state_chain(
                state_id,
                anim,
                name,
                cmsg_kwargs={
                    "offsetType": CmsgOffsetType.ANIM_ID,
                    "animeEndEventType": AnimeEndEventType.FIRE_IDLE_EVENT,
                    "changeTypeOfSelectedIndexAfterActivate": ChangeIndexType.SELF_TRANSITION,
                },
            )

            ctx.array_add(attack_sm, "states", state)
            ctx.register_wildcard_transition(
                attack_sm, state_id, event, transition_effect=transition_effect
            )

            state_id = state_id + 1
