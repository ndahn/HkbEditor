from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
)


def run(
    ctx: TemplateContext,
    grab_anim: Animation,
    death_anim: Animation,
    death_idle_anim: Animation,
    base_name: str,
):
    """Grab Victim Behavior

    Creates a new grab victim behavior (i.e. being grabbed by an enemy).

    TODO long description, how to use, etc.

    Author: FloppyDonuts

    Parameters
    ----------
    ctx : TemplateContext
        _description_
    grab_anim : Animation
        _description_
    death_anim : Animation
        _description_
    death_idle_anim : Animation
        _description_
    base_name : str
        _description_
    """
    throw_def = ctx.find("name:ThrowDef_Blend")
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

    grab_id = int(grab_anim.name.split("_")[1])

    for anim, parent, prefix, end_event_type in variations:
        clip = ctx.new_clip(anim.index)
        print("###", anim)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{prefix}{base_name}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=end_event_type,
        )
        blender = ctx.new_blender_generator_child(
            cmsg,
            weight=grab_id,
        )

        ctx.array_add(parent, "children", blender)
