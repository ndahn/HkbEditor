from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
)


def run(
    ctx: TemplateContext,
    cmsg_name: str = "Throw40168_CMSG",
    animation: Animation = "a000_040168",
):
    """Throw Attack (Attacker)

    Creates a new throw attack behavior (i.e. grabbing an enemy).

    Throws and grabs are controlled by the `ThrowParam` table of the regulation.bin. After adding a new attacker throw, create new rows as needed and set the "atkAnimId" field to the animation ID of your `grab_anim` (ignoring the aXXX part, i.e. a000_004170 becomes 4170).

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/throw_attack_attacker/

    Author: FloppyDonuts
    
    Status: confident

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    cmsg_name : str
        Name of the CMSG.
    animation : Animation
        The animation to use.
    """
    throw_sm = ctx.find("name=Throw_SM")
    throw_id = int(animation.name.split("_")[1])

    try:
        # Check if the throw ID is already in use somewhere
        ctx.find(f"type_name=hkbBlenderGeneratorChild weight={throw_id}", start_from=throw_sm)
        raise ValueError(f"throw_id {throw_id} already in use")
    except KeyError:
        pass

    clip = ctx.new_clip(animation.index)
    cmsg = ctx.new_cmsg(
        throw_id,
        name=cmsg_name,
        generators=[clip],
        offsetType=CmsgOffsetType.SWORD_ARTS_CATEGORY,
        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        changeTypeOfSelectedIndexAfterActivate=1,
    )
    blender = ctx.new_blender_generator_child(
        cmsg,
        weight=throw_id,
    )

    parent = ctx.find("name=ThrowAtk_Blend", start_from=throw_sm)
    ctx.array_add(parent, "children", blender)
