from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
)


def run(
    ctx: TemplateContext,
    cmsg_name: str = "Throw40168_CMSG",
    animation: Animation = "a000_040168",
    #throw_sm: HkbRecord = "name:ThrowAtk_Blend",
):
    """Throw Attack Behavior

    Creates a new throw attack behavior (i.e. grabbing an enemy).

    TODO: more documentation, what does it do, how to use it in game, etc.

    Author: FloppyDonuts

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    cmsg_name : str
        Name of the CMSG.
    animation : Animation
        The animation to use.
    """
    throw_id = int(animation.name.split("_")[1])

    try:
        # Check if the throw ID is already in use somewhere
        ctx.find(f"type_name:hkbBlenderGeneratorChild,weight:{throw_id}")
        raise ValueError(f"throw_id {throw_id} already in use")
    except KeyError:
        pass

    blender = ctx.new(
        "hkbBlenderGeneratorChild",
        weight=throw_id,
        worldFromModelWeight=1.0,
    )
    cmsg = ctx.new(
        "CustomManualSelectorGenerator",
        name=cmsg_name,
        animId=throw_id,
        offsetType=18,
        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        enableScript=True,
        enableTae=True,
        changeTypeOfSelectedIndexAfterActivate=1,
        checkAnimEndSlotNo=-1,
    )
    clip = ctx.new(
        "hkbClipGenerator",
        name=animation.name,
        animationName=animation.name,
        playbackSpeed=1,
        animationInternalId=animation.index,
    )

    # TODO only exists in Elden Ring, can this be used for Sekiro?
    parent = ctx.find("name:ThrowAtk_Blend")

    ctx.set(blender, generator=cmsg.object_id)
    ctx.array_add(cmsg, "generators", clip.object_id)
    ctx.array_add(parent, "children", blender.object_id)
