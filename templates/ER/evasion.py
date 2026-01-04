from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
    name: str,
    front_anim: Animation = None,
    back_anim: Animation = None,
    left_anim: Animation = None,
    right_anim: Animation = None,
):
    """Evasion
    
    Creates a new rolling/evasion animations for players. After running this script you can enable the new rolling animations by modifying the `EvasionWeightIndex` variable in HKS. 
    
    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/evasion/

    Author: Shiki

    Status: untested

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    roll_name : str
        The name of your new roll.
    roll_front_anim : Animation, optional
        Animation to use for rolling forward.
    roll_back_anim : Animation, optional
        Animation to use for rolling backwards.
    roll_left_anim : Animation, optional
        Animation to use for rolling left.
    roll_right_anim : Animation, optional
        Animation to use for rolling right.
    """
    evasion_sm = ctx.find("name=Evasion_SM")
    default_transition = ctx.get_default_transition_effect()

    # Create the new roll
    new_roll_cmsgs = []
    for anim, direction in zip(
        [front_anim, back_anim, left_anim, right_anim],
        ["Front", "Back", "Left", "Right"],
    ):
        if not anim:
            continue

        clip = ctx.new_clip(anim)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{name}{direction}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.SELF_TRANSITION,
            checkAnimEndSlotNo=1,
            userData="24313856",
        )
        new_roll_cmsgs.append(cmsg)

    new_roll_msg = ctx.new_manual_selector(
        "RollingDirectionIndex",
        name=f"{name} Selector",
        generators=new_roll_cmsgs,
        generatorChangedTransitionEffect=default_transition,
    )

    roll_msg = ctx.find("name=Rolling_Selector", start_from=evasion_sm)
    ctx.array_add(roll_msg, "generators", new_roll_msg)

    # Self transition
    new_roll_selftrans_cmsgs = []
    for anim, direction in zip(
        [front_anim, back_anim, left_anim, right_anim],
        ["Front", "Back", "Left", "Right"],
    ):
        if not anim:
            continue

        clip = ctx.new_clip(anim)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{name}{direction}_SelfTrans_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.NONE,
            checkAnimEndSlotNo=1,
            userData="24313857",
        )
        new_roll_selftrans_cmsgs.append(cmsg)

    new_roll_selftrans_msg = ctx.new_manual_selector(
        "RollingDirectionIndex_SelfTrans",
        name=f"{name}_Selftrans Selector",
        generators=new_roll_selftrans_cmsgs,
    )

    roll_selftrans_msg = ctx.find("name=Rolling_Selftrans_Selector", start_from=evasion_sm)
    ctx.array_add(roll_selftrans_msg, "generators", new_roll_selftrans_msg)

    roll_index = len(roll_msg["generators"])
    ctx.log(f"Index of new evasion {name}: {roll_index}")
