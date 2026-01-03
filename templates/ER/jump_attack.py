import logging

from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)


def run(
    ctx: TemplateContext,
    attack_name: str,
    anim_fall: Animation,  # 31030
    anim_loop: Animation,  # 31060
    anim_landing: Animation,  # 31070
    anim_landing_high: Animation = None,  # 31070
    jump_types: str = "NFD",
    cmsg_offset_type: CmsgOffsetType = CmsgOffsetType.WEAPON_CATEGORY_RIGHT,
    enable_swings: bool = False,
    anim_swingend_low: Animation = None,
    anim_swingend_high: Animation = None,
    anim_swingend_idle: Animation = None,
    anim_swingend_high_idle: Animation = None,
):
    """New Jump Attack Type

    Creates an entirely new jump attack type, e.g. left-handed jump attacks. The behavior can be activated by setting the JumpAttackForm and JumpAttack_HandCondition variables in the appropriate places.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/jump_attack/

    Author: Managarm
    
    Status: needs testing

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    attack_name : str
        The name of the jump attack, used for naming new objects.
    anim_fall: Animation
        Animation to play when attacking in air.
    anim_loop : Animation
        Animation to stay in after an attack during the Jump_Loop.
    anim_landing: Animation
        Animation to play when attacking while landing.
    anim_landing_high: Animation, optional
        Animation to play when attacking while landing from a high jump.
    jump_types: str, optional
        The jump types to add the attack to. Should usually cover all base jumps (Neutral, Forward, Dash).
    cmsg_offset_type : CmsgOffsetType, optional
        How the generated CMSGs will select their clips.
    enable_swings : bool, optional
        Whether to enable swing variations (controlled by the SwingPose variable). If disabled a single CMSG with for anim_fall will be added instead.
    anim_swingend_low : Animation, optional
        Swing variation to use at the end of a low jump. Will use anim_fall if not set. Normal attacks use e.g. 31071 here.
    anim_swingend_high : Animation, optional
        Swing variation to use at the end of a high jump. Will use anim_fall if not set. Normal attacks use e.g. 31072 here.
    anim_swingend_idle : Animation, optional
        Swing variation to use at the end of a low jump to idle. Will use anim_fall if not set. Normal attacks use e.g. 31081 here.
    anim_swingend_high_idle : Animation, optional
        Swing variation to use at the end of a high jump to idle. Will use anim_fall if not set. Normal attacks use e.g. 31082 here.
    """
    # TODO update new_jump to use a single letter so its compatible with this
    if not jump_types:
        raise ValueError("Must select at least one jump type.")

    if not anim_landing_high:
        anim_landing_high = anim_landing

    jump_sm = ctx.find("name='NewJump StateMachine'")
    landing_transition_effect = ctx.find(
        "name=JumpAttack_Condition", start_from=jump_sm
    )

    form_index = -1
    hand_condition_index = -1

    def get_generator_index(selector: HkbRecord, reference: int) -> int:
        num_gen = len(selector["generators"])
        if reference >= 0 and reference != num_gen:
            raise ValueError(
                f"Found different number of hand conditions on {jump_handcondition_msg}"
            )

        return num_gen

    # Attacks during the regular jump
    for jt in jump_types:
        # Attack CMSGs
        jump_falling_cmsg = ctx.new_cmsg(
            anim_fall,
            name=f"JumpAttack_{jt}_{attack_name}_CMSG",
            generators=[ctx.new_clip(anim_fall)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        )

        jump_landing_cmsg = ctx.new_cmsg(
            anim_landing,
            name=f"JumpAttack_{jt}_{attack_name}_LandCMSG",
            generators=[ctx.new_clip(anim_landing)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )

        jump_landing_high_cmsg = ctx.new_cmsg(
            anim_landing_high,
            name=f"JumpAttack_{jt}_{attack_name}_Land_High_CMSG",
            generators=[ctx.new_clip(anim_landing_high)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )

        # TODO check if already exists
        # Landing selector
        jump_landing_msg = ctx.new_manual_selector(
            "JumpAttack_Land",
            name=f"Jump_{jt} Selector_{attack_name}",
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=landing_transition_effect,
            generators=[
                jump_falling_cmsg,
                jump_landing_cmsg,
                jump_landing_high_cmsg,
            ],
        )

        # TODO check if already exists
        # Form selector
        jump_formrequest_msg = ctx.new_manual_selector(
            "JumpAttackFormRequest",
            name=f"Jump_{jt} Selector_N-H_{attack_name}",
            generators=[
                jump_landing_msg,
            ],
        )

        jump_handcondition_msg = ctx.find(
            f"'Jump_{jt} HandCondition Selector'", start_from=jump_sm
        )
        ctx.array_add(jump_handcondition_msg, "generators", jump_formrequest_msg)

    # Jump loop
    loop_cmsg = ctx.new_cmsg(
        anim_loop,
        name=f"Jump_Loop_{attack_name}_CMSG",
        generators=[ctx.new_clip(anim_loop, mode=PlaybackMode.LOOPING)],
        offsetType=cmsg_offset_type,
        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        userData=18350084,
    )

    loop_handcondition_msg = ctx.new_manual_selector(
        "JumpAttack_HandCondition",
        name=f"Jump_Loop_{attack_name}_HandCondition Selector",
        generators=[loop_cmsg],
    )

    loop_msg = ctx.find("'Jump_Loop Selector'", start_from=jump_sm)
    ctx.array_add(loop_msg, "generators", loop_handcondition_msg)

    # Landing attacks
    for jt in jump_types:
        if enable_swings:
            swing_cmsgs = []

            for swing_type, swing_anim in [
                ("Start_Low", anim_fall),
                ("Start_High", anim_fall),
                ("End_Low", anim_swingend_low),
                ("End_High", anim_swingend_high),
                ("End_Idle", anim_swingend_idle),
                ("End_High_Idle", anim_swingend_high_idle),
            ]:
                if not swing_anim:
                    swing_anim = anim_fall

                swing_cmsgs.append(
                    ctx.new_cmsg(
                        swing_anim,
                        name=f"Jump_Land_{jt}_{attack_name}_Swing{swing_type}",
                        generators=[ctx.new_clip(swing_anim)],
                        offsetType=cmsg_offset_type,
                        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
                        userData=18350087,
                    )
                )

            swing_msg = ctx.new_manual_selector(
                "SwingPose",
                name=f"Jump_Land_Common_{attack_name}_Swing_Selector",
                generators=swing_cmsgs,
            )
        else:
            swing_msg = ctx.new_cmsg(
                anim_fall,
                name=f"Jump_Land_{jt}_{attack_name}_Swing_CMSG",
                generators=[ctx.new_clip(anim_fall)],
                offsetType=cmsg_offset_type,
                animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
                userData=18350087,
            )

        swing_handcondition_msg = ctx.new_manual_selector(
            "JumpAttack_HandCondition",
            name=f"Jump_Land_Common_{attack_name}_Swing_HandConditionSelector",
            generators=[swing_msg],
        )

        swing_landing_msg = ctx.find(f"'Jump_Land_{jt} Selector'", start_from=jump_sm)
        ctx.array_add(swing_landing_msg, "generators", swing_handcondition_msg)

    # Start falling attacks
    for jt in jump_types:
        fall_falling_cmsg = ctx.new_cmsg(
            anim_fall,
            name=f"JumpAttack_Start_{jt}_FallingCMSG",
            generators=[ctx.new_clip(anim_fall)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        )

        fall_land_cmsg = ctx.new_cmsg(
            anim_landing,
            name=f"JumpAttack_Start_{jt}_LandCMSG00",
            generators=[ctx.new_clip(anim_landing)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
            userData=18350090,
        )

        fall_land_high_cmsg = ctx.new_cmsg(
            anim_landing_high,
            name=f"JumpAttack_Start_{jt}_Land_High_CMSG00",
            generators=[ctx.new_clip(anim_landing_high)],
            offsetType=cmsg_offset_type,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
            userData=18350090,
        )

        fall_landing_msg = ctx.new_manual_selector(
            "JumpAttack_Land",
            name=f"JumpAttack_Start_Falling_{jt}_N_{attack_name}_ConditionSelector",
            generators=[
                fall_falling_cmsg,
                fall_land_cmsg,
                fall_land_high_cmsg,
            ],
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=landing_transition_effect,
        )

        fall_formrequest_msg = ctx.new_manual_selector(
            "JumpAttackFormRequest",
            name=f"JumpAttack_Start_Falling_{jt}_N-H_{attack_name}",
            generators=[fall_landing_msg],
        )

        fall_selector_lookup = {
            "N": "'JumpAttack_Start_Falling HandCondition Selector'",
            "F": "'JumpAttack_Start_Falling_F  HandCondition Selector'",
            "D": "'JumpAttack_Start_Falling_D HandCondition Selector'",
        }

        fall_handcondition_msg = ctx.find(fall_selector_lookup[jt], start_from=jump_sm)
        ctx.array_add(fall_handcondition_msg, "generators", fall_formrequest_msg)

    # Jump F landing attack
    landf_cmsg = ctx.new_cmsg(
        anim_landing,
        name=f"JumpAttack_Land_F_{attack_name}_LandCMSG",
        generators=[ctx.new_clip(anim_landing)],
        offsetType=cmsg_offset_type,
        animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        userData=18350097,
    )

    landf_formrequest_msg = ctx.new_manual_selector(
        "JumpAttackFormRequest",
        name=f"Jump_Attack_Land_F {attack_name} Selector",
        generators=[landf_cmsg],
    )

    landf_handcondition_msg = ctx.find(
        "'Jump_Attack_Land_F HandCondition Selector'", start_from=jump_sm
    )
    ctx.array_add(landf_handcondition_msg, "generators", landf_formrequest_msg)

    # logging.getLogger().info(
    #     f"Added new jump attack '{attack_name}':"
    #     f"  JumpAttack_HandCondition: {hand_condition_index}"
    #     f"  JumpAttackForm: "
    # )
