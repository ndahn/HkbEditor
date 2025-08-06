from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as CmsgChangeType,
)


def run(
    ctx: TemplateContext,
    base_name: str,
    grab_anim: Animation,
    death_anim: Animation,
    death_idle_anim: Animation,
    create_hold_anim: bool = False,
):
    """Grab Victim Behavior

    Creates a new grab victim behavior (i.e. being grabbed by an enemy).

    Throws and grabs are controlled by the ThrowParam table of the regulation.bin. After adding a new victim grab behavior, create new rows as needed and set the "defAnimId" field to the animation ID of your grab_anim (ignoring the aXXX part, i.e. a000_070970 becomes 70970).

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
    throw_def = ctx.find("name:ThrowDefBase_Blend")
    throw_death = ctx.find("name:ThrowDeath_Blend")
    throw_death_idle = ctx.find("name:ThrowDeathIdle_Blend")

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
            replanningAI=True,
            userData=user_data,
        )
        blender = ctx.new_blender_generator_child(
            cmsg,
            weight=grab_anim.anim_id,
        )

        ctx.array_add(parent, "children", blender)
    
    if create_hold_anim:
        hold_anim = ctx.animation(f"a{grab_anim.category}_{grab_anim.anim_id + 4}")
        hold_anim_blend = ctx.find("name:ThrowDefHold_Blend")
        user_data = ctx.get(hold_anim_blend, "children:0/generator/userData", default=0)

        clip = ctx.new_clip(hold_anim)
        cmsg = ctx.new_cmsg(
            hold_anim.anim_id,
            name=f"ThrowDefHold{base_name}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            replanningAI=True,
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
