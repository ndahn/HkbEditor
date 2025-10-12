from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
    roll_name: str,
    roll_front_anim: Animation = None,
    roll_back_anim: Animation = None,
    roll_left_anim: Animation = None,
    roll_right_anim: Animation = None,
):
    """Custom Roll
    
    Creates a new rolling/evasion animations for players. After running this script you can enable the new rolling animations by modifying the variable "EvasionWeightIndex". 
    
    If you have not added new rolling animations before, your new roll will be on index 4. Otherwise check the "Rolling_Selector" object to figure out how many other variants already exist. Your new roll will be that number +1. 
    
    To enable your new roll, add something as follows in SetWeightIndex() of your c0000.hks:
    
    ```
    -- Adjust speffect ID as needed
    if env(GetSpEffectID, 123456) == TRUE then 
        SetVariable("EvasionWeightIndex", 4)
    end 
    ```


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
        [roll_front_anim, roll_back_anim, roll_left_anim, roll_right_anim],
        ["Front", "Back", "Left", "Right"],
    ):
        if not anim:
            continue

        clip = ctx.new_clip(anim)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{roll_name}{direction}_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.SELF_TRANSITION,
            checkAnimEndSlotNo=1,
            userData="24313856",
        )
        new_roll_cmsgs.append(cmsg)

    new_roll_msg = ctx.new_selector(
        "RollingDirectionIndex",
        name=f"{roll_name} Selector",
        generators=new_roll_cmsgs,
        generatorChangedTransitionEffect=default_transition,
    )

    roll_msg = ctx.find("name=Rolling_Selector", start_from=evasion_sm)
    ctx.array_add(roll_msg, "generators", new_roll_msg)

    # Self transition
    new_roll_selftrans_cmsgs = []
    for anim, direction in zip(
        [roll_front_anim, roll_back_anim, roll_left_anim, roll_right_anim],
        ["Front", "Back", "Left", "Right"],
    ):
        if not anim:
            continue

        clip = ctx.new_clip(anim)
        cmsg = ctx.new_cmsg(
            anim.anim_id,
            name=f"{roll_name}{direction}_SelfTrans_CMSG",
            generators=[clip],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            changeTypeOfSelectedIndexAfterActivate=ChangeIndexType.NONE,
            checkAnimEndSlotNo=1,
            userData="24313857",
        )
        new_roll_selftrans_cmsgs.append(cmsg)

    new_roll_selftrans_msg = ctx.new_selector(
        "RollingDirectionIndex_SelfTrans",
        name=f"{roll_name}_Selftrans Selector",
        generators=new_roll_selftrans_cmsgs,
    )

    roll_selftrans_msg = ctx.find("name=Rolling_Selftrans_Selector", start_from=evasion_sm)
    ctx.array_add(roll_selftrans_msg, "generators", new_roll_selftrans_msg)
