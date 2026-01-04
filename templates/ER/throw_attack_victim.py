from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as CmsgChangeType,
    CustomManualSelectorGenerator_ReplanningAI as ReplanningAI,
)


def run(
    ctx: TemplateContext,
    base_name: str,
    grab_anim: Animation,
    can_escape: bool = False,
):
    """Throw Attack (Victim)

    Creates a new throw victim behavior (i.e. being grabbed by an enemy).

    This template will create either 3 or 5 animations depending on the `can_escape` setting:
    - grab_anim + 0: grab animation
    - grab_anim + 1: animation used when the character dies during the grab
    - grab_anim + 2: animation looped after the death animation
    - grab_anim + 3: escape animation, triggered by `W_ThrowEscape` in HKS
    - grab_anim + 4: hold animation, used when the escape fails and usually the same as +0

    Throws are controlled by the `ThrowParam` table of the regulation.bin. After adding a new victim behavior, create new rows as needed and set the `defAnimId` field to the animation ID of your `grab_anim` (ignoring the aXXX part, i.e. a000_070970 becomes 70970).

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/throw_attack_victim/

    Author: FloppyDonuts

    Status: verified

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_name : str
        A prefix added to the generated CMSGs.
    grab_anim : Animation
        Animation used while the grab is ongoing.
    death_anim : Animation
        Animation used when the victim dies during the grab.
    death_idle_anim : Animation
        Animation used after the death animation finishes.
    create_hold_anim : bool, optional
        An additional animation to adjust the grab animation. This animation will be your grab_anim + 4. See SetThrowDefBlendWeight in your hks.
    """
    throw_sm = ctx.find("name=Throw_SM")

    throw_def = ctx.find("name=ThrowDefBase_Blend", start_from=throw_sm)
    throw_death = ctx.find("name=ThrowDeath_Blend", start_from=throw_sm)
    throw_death_idle = ctx.find("name=ThrowDeathIdle_Blend", start_from=throw_sm)

    death_anim = ctx.animation(
        Animation.make_name(grab_anim.category, grab_anim.anim_id + 1)
    )
    death_idle_anim = ctx.animation(
        Animation.make_name(grab_anim.category, grab_anim.anim_id + 2)
    )

    variations = [
        (
            grab_anim,
            throw_def,
            "Throw",
            AnimeEndEventType.FIRE_IDLE_EVENT,
        ),
        (
            death_anim,
            throw_death,
            "ThrowDeath",
            AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        ),
        (
            death_idle_anim,
            throw_death_idle,
            "ThrowDeathIdle",
            AnimeEndEventType.NONE,
        ),
    ]

    for anim, parent, prefix, end_event_type in variations:
        # At least the CMSGs in ThrowDeathIdle_Blend seems to use a common userData field
        user_data = ctx.get(parent, "children:0/generator/userData", default=0)

        clip = ctx.new_clip(anim.index)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{prefix}{base_name}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=end_event_type,
            replanningAI=ReplanningAI.ENABLE,
            userData=user_data,
        )
        blender = ctx.new_blender_generator_child(
            cmsg,
            weight=grab_anim.anim_id,
        )

        ctx.array_add(parent, "children", blender)

    if can_escape:
        # Escape animation
        escape_anim = ctx.animation(
            Animation.make_name(grab_anim.category, grab_anim.anim_id + 3)
        )
        escape_anim_blend = ctx.find("name=ThrowEscape_Blend", start_from=throw_sm)
        user_data = ctx.get(
            escape_anim_blend, "children:0/generator/userData", default=0
        )

        clip = ctx.new_clip(escape_anim)
        cmsg = ctx.new_cmsg(
            escape_anim.anim_id,
            name=f"ThrowEscape{base_name}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
            replanningAI=ReplanningAI.ENABLE,
            userData=user_data,
        )
        blender = ctx.new_blender_generator_child(
            cmsg,
            weight=grab_anim.anim_id,
        )

        ctx.array_add(escape_anim_blend, "children", blender)

        # Hold animation
        hold_anim = ctx.animation(
            Animation.make_name(grab_anim.category, grab_anim.anim_id + 4)
        )
        hold_anim_blend = ctx.find("name=ThrowDefHold_Blend", start_from=throw_sm)
        user_data = ctx.get(hold_anim_blend, "children:0/generator/userData", default=0)

        clip = ctx.new_clip(hold_anim)
        cmsg = ctx.new_cmsg(
            hold_anim.anim_id,
            name=f"ThrowDefHold{base_name}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            replanningAI=ReplanningAI.ENABLE,
            userData=user_data,
            changeTypeOfSelectedIndexAfterActivate=CmsgChangeType.SELF_TRANSITION,
            enableScript=False,
        )

        ctx.bind_variable(cmsg, "enableTae", "IsEnableTAEThrowHold")

        blender = ctx.new_blender_generator_child(
            cmsg,
            weight=grab_anim.anim_id,
        )

        ctx.array_add(hold_anim_blend, "children", blender)
