from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)


def run(
    ctx: TemplateContext,
    name: str,
    front: Animation,
    back: Animation,
    left: Animation,
    right: Animation,
):
    """New Stance Move Type

    Creates a new behavior for moving while in a stance. Imagine the difference between moving in unsheathe vs. a bear wanting to hug you.

    Once this template succeeds it will tell you an index of your new stance move type. This index should be used in hks to activate the move type while an speffect is active. Find the function `SetMoveType` and add a new condition to it as below:

    ```
    -- Replace with your speffect ID!
    elseif env(GetSpEffectID, 123456) == TRUE then
        SetVariable("MoveType", ConvergeValue(1, hkbGetVariable("MoveType"), 5, 5))
        SetVariable("StanceMoveType", <index>)  -- your index goes here!
    ...
    ```

    Author: Managarm

    Status: hopeful

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    front : Animation
        Forward moving animation.
    back : Animation
        Backward moving animation.
    left : Animation
        Left moving animation.
    right : Animation
        Right moving animation.
    """

    def create_stancemove_blender(sync: bool) -> HkbRecord:
        # Blending transition effects
        dur0 = ctx.find("name=Duration0")
        
        if sync:
            dur7 = ctx.find("name=Duration7_Sync")
            suffix = ""
        else:
            dur7 = ctx.find("name=Duration7_Sync00")
            suffix = "00"

        # All stance moves by FS use the same clip node for both blend layers. I tend to avoid
        # doing this, but it feels like it might be important here
        anims = {
            "Front": (front, ctx.new_clip(front, mode=PlaybackMode.LOOPING)),
            "Back": (back, ctx.new_clip(back, mode=PlaybackMode.LOOPING)),
            "Left": (left, ctx.new_clip(left, mode=PlaybackMode.LOOPING)),
            "Right": (right, ctx.new_clip(right, mode=PlaybackMode.LOOPING)),
        }

        # motion blend layer
        motion_cmsgs = []
        for direction, (anim, clip) in anims.items():
            cmsg = ctx.new_cmsg(
                anim,
                name=f"{name}_{direction}_CMSG{suffix}",
                generators=[clip],
                enableScript=False,
                enableTae=False,
                offsetType=CmsgOffsetType.IDLE_CATEGORY,
                animeEndEventType=AnimeEndEventType.NONE,
            )
            motion_cmsgs.append(cmsg)

        motion_msg = ctx.new_selector(
            "MoveDirection",
            name=f"{name}_motion{suffix}",
            generators=motion_cmsgs,
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=dur0,
        )

        motion_blend_child = ctx.new_blender_generator_child(motion_msg, weight=0.01, worldFromModelWeight=1.0)

        # anim blend layer
        anim_cmsgs = []
        for direction, (anim, clip) in anims.items():
            cmsg = ctx.new_cmsg(
                anim, 
                name=f"{name}_{direction}_anim_CMSG{suffix}",
                generators=[clip],
                enableScript=False,
                offsetType=CmsgOffsetType.IDLE_CATEGORY,
                animeEndEventType=AnimeEndEventType.NONE,
            )
            anim_cmsgs.append(cmsg)

        anim_msg = ctx.new_selector(
            "MoveDirection",
            name=f"{name}_anime{suffix}",
            generators=anim_cmsgs,
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=dur7,
        )

        anim_blend_child = ctx.new_blender_generator_child(anim_msg, weight=1.0, worldFromModelWeight=0.0)

        # Bundle the blend children in a blender generator and add it to the stance move selector
        return ctx.new_blender_generator(
            [motion_blend_child, anim_blend_child],
            blendParameter=1.0,
            name=f"{name}_Blend{suffix}"
        )

    stance_blend = create_stancemove_blender(True)
    stancemove_msg = ctx.find("name=StanceMove_Selector")
    move_type_idx = ctx.array_add(stancemove_msg, "generators", stance_blend)

    stance_blend_nosync = create_stancemove_blender(False)
    stancemove_msg_nosync = ctx.find("name=StanceMoveNoSync_Selector")
    move_type_idx_nosync = ctx.array_add(stancemove_msg_nosync, "generators", stance_blend_nosync)

    if move_type_idx != move_type_idx_nosync:
        ctx.logger.warning("NOTE: children of StanceMove_Selector and StanceMoveNoSync_Selector don't match, this will probably cause problems!")

    ctx.logger.info(f"Index of new StanceMoveType {name}: {move_type_idx}")
