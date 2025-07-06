from hkb_editor.templates import *


def run(ctx: TemplateContext, throw_id: int, cmsg_name: str, animation: Animation):
    """Grab/Throw Behavior

    Creates a new throw attack behavior.
    
    TODO: more documentation, what does it do, how to use it in game, etc.

    Author: FloppyDonuts

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    throw_id : int
        The ID of the new throw attack.
    cmsg_name : str
        Name of the CMSG.
    animation : Animation
        The animation to use.
    """
    blender = ctx.create(
        "hkbBlenderGeneratorChild",
        weight=throw_id,
        worldFromModelWeight=1.0,
    )
    cmsg = ctx.create(
        "CustomManualSelectorGenerator",
        name=cmsg_name,
        offsetType=18,
        animeEndEventType=2,
        enableScript=True,
        enableTae=True,
        changeTypeOfSelectedIndexAfterActivate=1,
        checkAnimEndSlotNo=-1,
    )
    clip = ctx.create(
        "hkbClipGenerator",
        name=animation.name + ".hkx",
        animationName=animation.name,
        playbackSpeed=1,
        animationInternalId=animation.index,
    )

    # TODO only exists in Elden Ring, can this be used for Sekiro?
    parent = ctx.find("name:ThrowAtk_Blend")

    ctx.array_add(cmsg, "generators", clip.object_id)
    ctx.set(blender, generator=cmsg.object_id)
    ctx.array_add(parent, "children", blender.object_id)
