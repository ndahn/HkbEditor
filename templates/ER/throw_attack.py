from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
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

    clip = ctx.new_clip(animation.index)
    cmsg = ctx.new_cmsg(
        name=cmsg_name,
        animId=throw_id,
        generators=[clip],
        offsetType=CmsgOffsetType.SWORD_ARTS_CATEGORY,
        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        changeTypeOfSelectedIndexAfterActivate=1,
    )
    blender = ctx.new_blender_generator_child(
        cmsg,
        weight=throw_id,
    )

    parent = ctx.find("name:ThrowAtk_Blend")
    ctx.array_add(parent, "children", blender.object_id)
