from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
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
    throw_def = ctx.find("name:ThrowDef")
    throw_death = ctx.find("name:ThrowDeath")
    throw_death_idle = ctx.find("name:ThrowDeathIdle")

    variations = [
        (grab_anim, throw_def, "Throw", AnimeEndEventType.FIRE_IDLE_EVENT),
        (death_anim, throw_death, "ThrowDeath", AnimeEndEventType.FIRE_NEXT_STATE_EVENT),
        (death_idle_anim, throw_death_idle, "ThrowDeathIdle", AnimeEndEventType.NONE),
    ]

    grab_id = int(grab_anim.name.split("_")[1])

    for anim, parent, prefix, end_event_type in variations:
        anim_id = int(anim.name.split("_")[1])

        blender = ctx.new(
            "hkbBlenderGeneratorChild",
            weight=grab_id,
            worldFromModelWeight=1,
        )

        cmsg = ctx.new(
            "CustomManualSelectorGenerator",
            name=f"{prefix}{base_name}_CMSG",
            offsetType=11,
            animId=anim_id,
            animeEndEventType=end_event_type,
            enableScript=True,
            enableTae=True,
            checkAnimEndSlotNo=-1,
        )

        clip = ctx.new(
            "hkbClipGenerator",
            name=anim.name,
            animationName=anim.name,
            playbackSpeed=1,
            animationInternalId=anim.index,
        )

        ctx.set(blender, generator=cmsg.object_id)
        ctx.array_add(cmsg, "generators", clip.object_id)
        ctx.array_add(parent, "children", blender.object_id)
