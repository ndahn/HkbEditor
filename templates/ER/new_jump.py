from typing import Literal
from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    hkbTransitionEffect_SelfTransitionMode as SelfTransitionMode,
    hkbTransitionEffect_EventMode as EventMode,
    hkbBlendingTransitionEffect_EndMode as EndMode,
    hkbBlendCurveUtils_BlendCurve as BlendCurve,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)


def run(
    ctx: TemplateContext,
    jump_name: str,
    event: Event,
    base_jump: Literal["Jump_N", "Jump_F", "Jump_D"] = "Jump_D",
    enable_jump_attacks: bool = True,
    jump_front_anim: Animation = None,
    jump_back_anim: Animation = None,
    jump_left_anim: Animation = None,
    jump_right_anim: Animation = None,
):
    """Custom Jump

    Creates a new TAE slot for jump animations with support for directional jumps and jump attacks.

    # Details
    If you define an animation for one of the directions it will be the only slot used for this direction. Otherwise the regular slots for this direction are used, taken from the "base_jump". These are in Elden Ring 202020 - 202023 (front, back, left, right). If jump attacks are enabled, the new jump behaviors will support all jump attacks already registered for the base jump.

    Note that directional jumps are not available for "Jump_N" (neutral jumps). Use "Jump_F" (walking) or "Jump_D" (running) instead if you want those. The main difference is whether you can change direction after the jump started.

    # How to use
    After this template has succeeded you can make use of the new behaviors by adding the following in your HKS:

    Add the following code to your `ExecJump` function, replacing the SpEffect ID and event with values appropriate for your behavior.
    ```
    if env(GetSpEffectID, 480098) == TRUE then
        if env(IsAIJumpRequested) == TRUE then
            act(NotifyAIOfJumpState)
        end

        act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
        SetAIActionState()
        ExecEvent("W_RasterSurgeSprintJump_S")

    return TRUE
    ```

    Then add the following code on the global level, renaming the functions to match the `base_name` you specified.
    ```
    function RasterSurgeSprintJump_S_onActivate()
        act(AIJumpState)
        SetAIActionState()
    end

    function RasterSurgeSprintJump_S_onUpdate()
        SetAIActionState()
        JUMP_STATE_1 = 0
        JUMP_STATE_2 = 0
        JUMP_STATE_3 = 1

        if GetVariable("JumpAttackForm") == 0 then
            act(LockonFixedAngleCancel)
        end
        
        if JumpCommonFunction(2) == TRUE then
            return
        end
    end

    function RasterSurgeSprintJump_S_onDeactivate()
        act(DisallowAdditiveTurning, FALSE)
    end
    ```


    Author: Raster
    
    Status: verified

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    name : str
        Name of your new jump. Will be used for CMSGs, States, etc.
    jump_name : Literal[f&quot;Jump_N&quot;, &quot;Jump_F&quot;, &quot;Jump_D&quot;], optional
        The jump behavior to use for unspecified directions.
    jump_front_anim : Animation, optional
        Animation slot to use for forward jumps. Register clips from default slot if not specified.
    jump_back_anim : Animation, optional
        Animation slot to use for backwards jumps. Register clips from default slot if not specified.
    jump_left_anim : Animation, optional
        Animation slot to use for jumps to the left. Register clips from default slot if not specified.
    jump_right_anim : Animation, optional
        Animation slot to use for jumps to the right. Register clips from default slot if not specified.
    """
    jump_sm = ctx.find("name='NewJump StateMachine'")

    # Helper functions
    def isolate_binding_set(record: HkbRecord):
        # To allow for easier customization each selector will have its own binding set
        bindings = record["variableBindingSet"].get_target()
        if not bindings:
            return

        new_bindings = ctx.make_copy(bindings)
        ctx.set(record, variableBindingSet=new_bindings)

    ####
    # Jump with added attack
    ####
    if enable_jump_attacks:
        # Normal/Hard Attack Right
        hand_nh_right_normal_selector = ctx.make_copy(
            f"'{base_jump} Selector_NormalAttack_Right'",
            name=f"{jump_name} Selector_NormalAttack_Right",
        )

        hand_nh_right_hard_selector = ctx.make_copy(
            f"'{base_jump} Selector_HardAttack_Right'",
            name=f"{jump_name} Selector_HardAttack_Right",
        )

        hand_nh_right_normal_dual_selector = ctx.make_copy(
            f"'{base_jump} Selector_NormalAttack_Dual'",
            name=f"{jump_name} Selector_NormalAttack_Dual",
        )

        hand_nh_right_magic_selector = ctx.make_copy(
            f"'{base_jump} Selector_Magic_Right'",
            name=f"{jump_name} Selector_Magic_Right",
        )

        hand_nh_right_selector = ctx.make_copy(
            f"'{base_jump} Selector_N-HAttack_Right'",
            name=f"{jump_name} Selector_N-HAttack_Right",
            generators=[
                hand_nh_right_normal_selector,
                hand_nh_right_hard_selector,
                hand_nh_right_normal_dual_selector,
                hand_nh_right_magic_selector,
            ],
        )

        isolate_binding_set(hand_nh_right_normal_selector)
        isolate_binding_set(hand_nh_right_hard_selector)
        isolate_binding_set(hand_nh_right_normal_dual_selector)
        isolate_binding_set(hand_nh_right_magic_selector)
        isolate_binding_set(hand_nh_right_selector)

        ### Hard Attack Both
        hand_nh_right_normal_both_selector = ctx.make_copy(
            f"'{base_jump} Selector_NormalAttack_Both'",
            name=f"{jump_name} Selector_NormalAttack_Both",
        )

        hand_nh_right_hard_both_selector = ctx.make_copy(
            f"'{base_jump} Selector_HardAttack_Both'",
            name=f"{jump_name} Selector_HardAttack_Both",
        )

        hand_nh_both_selector = ctx.make_copy(
            f"'{base_jump} Selector_N-HAttack_Both'",
            name=f"{jump_name} Selector_N-HAttack_Both",
            generators=[
                hand_nh_right_normal_both_selector,
                hand_nh_right_hard_both_selector,
            ],
        )

        isolate_binding_set(hand_nh_right_normal_both_selector)
        isolate_binding_set(hand_nh_right_hard_both_selector)
        isolate_binding_set(hand_nh_both_selector)

        # Magic Left
        base_jump_magic = (
            base_jump.rsplit("_", maxsplit=1)[0]
            + "Magic_"
            + base_jump.rsplit("_", maxsplit=1)[1]
        )

        hand_magic_left_cmsg = ctx.make_copy(
            f"'{base_jump_magic}_Left_CMSG'",
            # Slightly different naming scheme, but we can't enforce the base name
            # to follow a compatible pattern
            name=f"{jump_name}_Magic_Left_CMSG",
        )

        hand_magic_left_start_land_cmsg = ctx.make_copy(
            f"'{base_jump_magic}_Left_Start_LandCMSG'",
            name=f"{jump_name}_Magic_Left_Start_LandCMSG",
        )

        hand_magic_left_start_land_high_cmsg = ctx.make_copy(
            f"'{base_jump_magic}_Left_Start_Land_High_CMSG'",
            name=f"{jump_name}_Magic_Left_Start_Land_High_CMSG",
        )

        hand_magic_left_selector = ctx.make_copy(
            f"'{base_jump} Selector_Magic_Left'",
            name=f"{jump_name} Selector_Magic_Left",
            generators=[
                hand_magic_left_cmsg,
                hand_magic_left_start_land_cmsg,
                hand_magic_left_start_land_high_cmsg,
            ],
        )

        isolate_binding_set(hand_magic_left_selector)

        # Attack Both Left
        hand_nh_left_normal_both_selector = ctx.make_copy(
            f"'{base_jump} Selector_NormalAttack_BothLeft'",
            name=f"{jump_name} Selector_NormalAttack_BothLeft",
        )

        hand_nh_left_hard_both_selector = ctx.make_copy(
            f"'{base_jump} Selector_HardAttack_BothLeft'",
            name=f"{jump_name} Selector_HardAttack_BothLeft",
        )

        hand_nh_both_left_selector = ctx.make_copy(
            f"'{base_jump} Selector_N-HAttack_BothLeft'",
            name=f"{jump_name} Selector_N-HAttack_BothLeft",
            generators=[
                hand_nh_left_normal_both_selector,
                hand_nh_left_hard_both_selector,
            ],
        )

        isolate_binding_set(hand_nh_left_normal_both_selector)
        isolate_binding_set(hand_nh_left_hard_both_selector)
        isolate_binding_set(hand_nh_both_left_selector)

        # Top-level selector for jump attacks
        handcondition_selector = ctx.make_copy(
            f"'{base_jump} HandCondition Selector'",
            name=f"{jump_name} HandCondition Selector",
            generators=[
                hand_nh_right_selector,
                hand_nh_both_selector,
                hand_magic_left_selector,
                hand_nh_both_left_selector,
            ],
        )

        isolate_binding_set(handcondition_selector)

        # Jump Attack Layer

        # A bit difficult to query, we need the parent layer of the selector we are imitating
        handcondition_selector_orig = ctx.find(f"name='{base_jump} HandCondition Selector'", start_from=jump_sm)

        layer1_jumpattack_add = ctx.make_copy(
            f"type_name=hkbLayer generator={handcondition_selector_orig.object_id}",
            generator=handcondition_selector,
        )

        isolate_binding_set(layer1_jumpattack_add)

    ####
    # Regular Directional Jumps
    ####
    if base_jump != "Jump_N":
        # Front
        if jump_front_anim:
            jump_front_anim_id = jump_front_anim.anim_id
            jump_front_clips = [ctx.new_clip(jump_front_anim)]
        else:
            jump_front_anim_id = 202020
            jump_front_clips = [
                ptr.get_value()
                for ptr in ctx.get(f"'{base_jump}_Direction_Front_CMSG'", "generators")
            ]

        jump_front_cmsg = ctx.make_copy(
            f"'{base_jump}_Direction_Front_CMSG'",
            name=f"'{jump_name}_Direction_Front_CMSG'",
            animId=jump_front_anim_id,
            generators=jump_front_clips,
        )

        # Back
        if jump_back_anim:
            jump_back_anim_id = jump_back_anim.anim_id
            jump_back_clips = [ctx.new_clip(jump_back_anim)]
        else:
            jump_back_anim_id = 202021
            jump_back_clips = [
                ptr.get_value()
                for ptr in ctx.get(f"'{base_jump}_Direction_Back_CMSG'", "generators")
            ]

        jump_back_cmsg = ctx.make_copy(
            f"'{base_jump}_Direction_Back_CMSG'",
            name=f"'{jump_name}_Direction_Back_CMSG'",
            animId=jump_back_anim_id,
            generators=jump_back_clips,
        )

        # Left
        if jump_left_anim:
            jump_left_anim_id = jump_left_anim.anim_id
            jump_left_clips = [ctx.new_clip(jump_left_anim)]
        else:
            jump_left_anim_id = 202022
            jump_left_clips = [
                ptr.get_value()
                for ptr in ctx.get(f"'{base_jump}_Direction_Left_CMSG'", "generators")
            ]

        jump_left_cmsg = ctx.make_copy(
            f"'{base_jump}_Direction_Left_CMSG'",
            name=f"'{jump_name}_Direction_Left_CMSG'",
            animId=jump_left_anim_id,
            generators=jump_left_clips,
        )

        # Right
        if jump_right_anim:
            jump_right_anim_id = jump_right_anim.anim_id
            jump_right_clips = [ctx.new_clip(jump_right_anim)]
        else:
            jump_right_anim_id = 202023
            jump_right_clips = [
                ptr.get_value()
                for ptr in ctx.get(f"'{base_jump}_Direction_Right_CMSG'", "generators")
            ]

        jump_right_cmsg = ctx.make_copy(
            f"'{base_jump}_Direction_Right_CMSG'",
            name=f"'{jump_name}_Direction_Right_CMSG'",
            animId=jump_right_anim_id,
            generators=jump_right_clips,
        )

        # Jump Direction Selector
        direction_selector = ctx.make_copy(
            f"'{base_jump}_Direction_MSG'",
            name=f"{jump_name}_Direction_MSG",
            generators=[
                jump_front_cmsg,
                jump_back_cmsg,
                jump_left_cmsg,
                jump_right_cmsg,
            ],
        )

        isolate_binding_set(direction_selector)

        # Regular Jump Layer

        # A bit difficult to query, we need the parent layer of the selector we are imitating
        direction_selector_orig = ctx.find(f"name='{base_jump}_Direction_MSG'", start_from=jump_sm)

        layer2_direction = ctx.make_copy(
            f"type_name=hkbLayer generator={direction_selector_orig.object_id}",
            generator=direction_selector,
        )

        isolate_binding_set(layer2_direction)

    # Assemble layers
    all_layers = []

    if enable_jump_attacks:
        all_layers.append(layer1_jumpattack_add)

    if base_jump != "Jump_N":
        all_layers.append(layer2_direction)

    layer_gen = ctx.new_layer_generator(
        name=f"{jump_name} LayerGenerator",
        layers=all_layers,
    )

    # Finally generate the new state for the state machine
    # Transition to jump loop
    jump_loop_transition_effect = ctx.new_record(
        "CustomTransitionEffect",
        "<new>",
        name=f"{jump_name}_to_Jump_Loop",
        duration=0.5,
        alignmentBone=-1,
    )

    jump_loop_state = ctx.find("name=Jump_Loop type_name=hkbStateMachine::StateInfo", start_from=jump_sm)

    # Not sure why we're using W_RideJump, but this is how the template was. Other
    # jumps are using e.g. Jump_F_to_Jump_Loop
    jump_loop_transition = ctx.new_transition_info(
        jump_loop_state["stateId"].get_value(),
        "W_RideJump",
        transition=jump_loop_transition_effect,
    )
    # Jump states have their own transition info arrays. Typically used for CMSGS that 
    # have FIRE_NEXT_STATE as their end action
    state_transitions = ctx.new_transition_info_array(
        transitions=[jump_loop_transition]
    )

    state_id = ctx.get_next_state_id(jump_sm)
    state = ctx.new_stateinfo(
        state_id,
        name=jump_name,
        transitions=state_transitions,
        generator=layer_gen,
    )
    ctx.array_add(jump_sm, "states", state)
    ctx.register_wildcard_transition(jump_sm, state_id, event, flags=3584)
