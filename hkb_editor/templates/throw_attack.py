from hkb_editor.templates import *


# The template context will always be the first argument to the run function. 
# Additional arguments will be exposed in the GUI dialog based on their type.
# The type is taken from either the type hint, docstring, or default value. 
# If the type cannot be resolved it will result in an error. The following 
# types are supported:
# - simple types (int, float, bool, str)
# - choices (Literal of simple types)
# - known constants (Animation, Event, Variable)
# - other behavior objects (HkbRecord)
def run(ctx: TemplateContext, throw_id: float, cmsg_name: str, animation: Animation):
    """Grab/Throw Behavior

    Creates a new throw attack behavior.

    Author: FloppyDonuts

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    throw_id : float
        The ID of the new throw attack.
    cmsg_name : str
        Name of the CMSG.
    animation : Animation
        The animation to use.
    """
    # Create objects. They'll be added to the behavior automatically
    blender = ctx.create(
        "hkbBlenderGeneratorChild",
        # No need to use placeholder.value when passing as an attribute
        weight=throw_id,
        worldFromModelWeight=1.0,
    )
    cmsg = ctx.create(
        "CustomManualSelectorGenerator",
        name=cmsg_name,
        offsetType=18,
        animEndEventType=2,
        enableScript=True,
        enableTae=True,
        changeTypeOfSelectedIndexAfterActivate=1,
        checkAnimEndSlotNo=-1,
    )
    clip = ctx.create(
        "hkbClipGenerator",
        name=animation.value + ".hkx",
        animationName=animation.value.name,
        playbackSpeed=1,
        animationInternalId=animation.value.index,
    )

    # Link the objects together and to their already existing parent
    parent = ctx.find("name:ThrowAtk_Blend")

    # Right now it's possible to set these directly on the objects. This is not
    # recommended, as it will circumvent the undo manager. I might change this 
    # in the future and make it impossible.
    ctx.array_add(cmsg, "generators", clip.object_id)
    ctx.set(blender, "generator", cmsg)
    ctx.array_add(parent, "children", blender.object_id)
