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
    """NPC Attack Slots

    Creates new NPC attack slots starting at aXXX_YYYYYY, where X is the category and Y equals `anim_id_start + anim_id_step * i` and `i` going from 0 to num_attacks (exclusive). The attacks will be associated with the events `W_AttackYYYYYY` and `W_EventYYYYYY` (leading 0s not included).

    NOTE that NPC attacks should be in the range from 3000 to 3100. Attacks outside this range need special changes in the HKS to be useful.

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/npc_attack_slots/

    Author: FloppyDonuts

    Status: verified

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    anim_id_start : int, optional
        First animation ID to create an attack for.
    anim_id_step : int, optional
        How much to increase the animation ID for each subsequent new attack.
    num_attacks : int, optional
        How many new CMSGs to generate.
    category : int, optional
        Category to create the clip generators for.
    """
    attack_sm = ctx.find("name=Attack_SM")
    transition_effect = ctx.find("name=DefaultTransition")
    state_id = ctx.get_next_state_id(attack_sm)

    for anim_id in range(
        anim_id_start, anim_id_start + anim_id_step * num_attacks, anim_id_step
    ):
        anim = Animation.make_name(category, anim_id)
        name = f"Attack{anim_id}"

        if not 3000 <= anim_id <= 3099:
            ctx.logger.warning(f"{name} is outside the typical NPC attack slot range")

        if ctx.find(f"animationName={anim}", default=None):
            # Already exists, nothing to do
            ctx.logger.info(f"{name} already exists")
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
                attack_sm, state_id, f"W_Attack{anim_id}", transition_effect=transition_effect
            )
            # Useful for EMEVD and AI
            ctx.register_wildcard_transition(
                attack_sm, state_id, f"W_Event{anim_id}", transition_effect=transition_effect
            )

            state_id = state_id + 1
