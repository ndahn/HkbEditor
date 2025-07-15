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
from hkb_editor.hkb.hkb_flags import hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags


def run(
    ctx: TemplateContext,
    base_name: str,
    event: Event,
    base_jump: Literal["Jump_N", "Jump_F", "Jump_D"] = "Jump_D",
    enable_jump_attacks: bool = True,
    jump_front_anim: Animation = None,
    jump_back_anim: Animation = None,
    jump_left_anim: Animation = None,
    jump_right_anim: Animation = None,
):
    """New Jump Slot

    Creates a new TAE slot for jump animations with support for jump attacks.

    If you define an animation for one of the directions it will be the only slot used for this direction. Otherwise the regular slots for this direction are used, taken from the "base_jump". These are in Elden Ring 202020 - 202023 (front, back, left, right). If jump attacks are enabled, the new jump behaviors will support all jump attacks already registered for the base jump.

    Note that directional jumps are not available for "Jump_N" (neutral jumps). Use "Jump_F" (walking) or "Jump_D" (running) instead if you want those. In vanilla ER there is no difference between walking and running jumps regarding what they enable.

    Author: Raster

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    name : str
        Name of your new jump. Will be used for CMSGs, States, etc.
    base_jump : Literal[f&quot;Jump_N&quot;, &quot;Jump_F&quot;, &quot;Jump_D&quot;], optional
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
    # Helper functions
    def get_binding_set(model_query: str) -> str:
        model_obj = ctx.find(model_query)
        return model_obj["variableBindingSet"].get_value()

    def get_generators(model_query: str) -> list[str]:
        model_obj = ctx.find(model_query)
        generators = model_obj["generators"]
        return [ptr.get_value() for ptr in generators]

    ####
    # Jump with added attack
    ####
    if enable_jump_attacks:
        # TODO make more use of ctx.make_copy

        # Normal/Hard Attack Right
        change_transition_blend = ctx.find(
            f"'{base_jump} Selector_NormalAttack_Right'"
        )["generatorChangedTransitionEffect"].get_value()

        hand_nh_right_normal_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_NormalAttack_Right",
            generators=get_generators(f"'{base_jump} Selector_NormalAttack_Right'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_NormalAttack_Right'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_hard_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_HardAttack_Right",
            generators=get_generators(f"'{base_jump} Selector_HardAttack_Right'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_HardAttack_Right'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_normal_dual_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_NormalAttack_Dual",
            generators=get_generators(f"'{base_jump} Selector_NormalAttack_Dual'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_NormalAttack_Dual'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_magic_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_N-HAttack_Right",
            generators=get_generators(f"'{base_jump} Selector_N-HAttack_Right'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_N-HAttack_Right'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttackFormRequest
            name=f"{base_name} Selector_N-HAttack_Right",
            generators=[
                hand_nh_right_normal_selector,
                hand_nh_right_hard_selector,
                hand_nh_right_normal_dual_selector,
                hand_nh_right_magic_selector,
            ],
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_N-HAttack_Right'"
            ),
        )

        ### Hard Attack Both
        hand_nh_right_normal_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_NormalAttack_Both",
            generators=get_generators(f"'{base_jump} Selector_NormalAttack_Both'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_NormalAttack_Both'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_right_hard_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_HardAttack_Both",
            generators=get_generators(f"'{base_jump} Selector_HardAttack_Both'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_HardAttack_Both'"
            ),
            selectedIndexCanChangeAfterActivate=True, # TODO copy from base jump
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_N-HAttack_Both",
            generators=[
                hand_nh_right_normal_both_selector,
                hand_nh_right_hard_both_selector,
            ],
            # TODO bindingSet
        )

        # TODO Selector_Magic_Right

        # Magic Left
        # TODO compare to vanilla one
        hand_magic_left_anim_id = ctx.find("JumpMagic_N_Left_CMSG")[
            "animId"
        ].get_value()
        hand_magic_left_cmsg = ctx.new_cmsg(
            hand_magic_left_anim_id,
            name=f"{base_name}_Left_CMSG",
            generators=get_generators("JumpMagic_N_Left_CMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
        )

        hand_magic_left_start_land_anim_id = ctx.find(
            "JumpMagic_N_Left_Start_LandCMSG"
        )["animId"].get_value()
        hand_magic_left_start_land_cmsg = ctx.new_cmsg(
            hand_magic_left_start_land_anim_id,
            name=f"{base_name}_Left_Start_LandCMSG",
            generators=get_generators("JumpMagic_N_Left_Start_LandCMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )

        hand_magic_left_start_land_high_anim_id = ctx.find(
            "JumpMagic_N_Left_Start_Land_High_CMSG"
        )["animId"].get_value()
        hand_magic_left_start_land_high_cmsg = ctx.new_cmsg(
            hand_magic_left_start_land_high_anim_id,
            name=f"{base_name}_Left_Start_Land_High_CMSG",
            generators=get_generators("JumpMagic_N_Left_Start_Land_High_CMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )

        hand_magic_left_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_Magic_Left",
            generators=[
                hand_magic_left_cmsg,
                hand_magic_left_start_land_cmsg,
                hand_magic_left_start_land_high_cmsg,
            ],
            generatorChangedTransitionEffect=change_transition_blend,
        )

        # Attack Both Left
        hand_nh_left_normal_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_NormalAttack_BothLeft",
            generators=get_generators(f"'{base_jump} Selector_NormalAttack_BothLeft'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_NormalAttack_BothLeft'"
            ),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_left_hard_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{base_name} Selector_HardAttack_BothLeft",
            generators=get_generators(f"'{base_jump} Selector_HardAttack_BothLeft'"),
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_HardAttack_BothLeft'"
            ),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_both_left_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttackFormRequest
            name=f"{base_name} Selector_N-HAttack_BothLeft",
            generators=[
                hand_nh_left_normal_both_selector,
                hand_nh_left_hard_both_selector,
            ],
            variableBindingSet=get_binding_set(
                f"'{base_jump} Selector_N-HAttack_BothLeft'"
            ),
        )

        # Top-level selector for jump attacks
        handcondition_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_HandCondition
            name=f"{base_name} HandCondition Selector",
            generators=[
                hand_nh_right_selector,
                hand_nh_both_selector,
                hand_magic_left_selector,
                hand_nh_both_left_selector,
            ],
            variableBindingSet=get_binding_set(f"'{base_jump} HandCondition Selector'"),
        )

        # Jump Attack Layer
        attack_jumpnormal_evt = ctx.event("Event_JumpNormalAttack_Add", create=False)

        # A bit difficult to query, we need the parent layer of the selector we are imitating
        model_selector = ctx.find(f"'{base_jump} HandCondition Selector'")
        model_selector_parent_query = (
            f"type_name:hkbLayer generator:{model_selector.object_id}"
        )

        layer1_jumpattack_add = ctx.new_layer(
            generator=handcondition_selector,
            weight=0.99,
            fadeInDuration=0.3,
            onEventId=attack_jumpnormal_evt,
            fadeInOutCurve=BlendCurve.LINEAR,
            variableBindingSet=get_binding_set(model_selector_parent_query),
        )

    ####
    # Regular Directional Jumps
    ####
    if base_jump != "Jump_N":
        # Front
        if jump_front_anim:
            jump_front_clips = [ctx.new_clip(jump_front_anim)]
            jump_front_anim_id = jump_front_anim.anim_id
        else:
            jump_front_clips = get_generators(f"'{base_jump}_Direction_Front_CMSG'")
            jump_front_anim_id = 202020

        jump_front_cmsg = ctx.new_cmsg(
            jump_front_anim_id,
            name=f"{base_name}_Direction_Front_CMSG",
            generators=jump_front_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Back
        if jump_back_anim:
            jump_back_clips = [ctx.new_clip(jump_back_anim)]
            jump_back_anim_id = jump_back_anim.anim_id
        else:
            jump_back_clips = get_generators(f"'{base_jump}_Direction_Back_CMSG'")
            jump_back_anim_id = 202021

        jump_back_cmsg = ctx.new_cmsg(
            jump_back_anim_id,
            name=f"{base_name}_Direction_BackCMSG",
            generators=jump_back_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Left
        if jump_left_anim:
            jump_left_clips = [ctx.new_clip(jump_left_anim)]
            jump_left_anim_id = jump_left_anim.anim_id
        else:
            jump_left_clips = get_generators(f"'{base_jump}_Direction_Left_CMSG'")
            jump_left_anim_id = 202022

        jump_left_cmsg = ctx.new_cmsg(
            jump_left_anim_id,
            name=f"{base_name}_Direction_Left_CMSG",
            generators=jump_left_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Right
        if jump_right_anim:
            jump_right_clips = [ctx.new_clip(jump_right_anim)]
            jump_right_anim_id = jump_right_anim.anim_id
        else:
            jump_right_clips = get_generators(f"'{base_jump}_Direction_Right_CMSG'")
            jump_right_anim_id = 202023

        jump_right_cmsg = ctx.new_cmsg(
            jump_right_anim_id,
            name=f"{base_name}_Direction_Right_CMSG",
            generators=jump_right_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Jump Direction Selector
        direction_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpDirection
            name=f"{base_name}_Direction_MSG",
            generators=[
                jump_front_cmsg,
                jump_back_cmsg,
                jump_left_cmsg,
                jump_right_cmsg,
            ],
            variableBindingSet=get_binding_set(f"{base_jump}_Direction_MSG"),
        )

        # Regular Jump Layer
        # A bit difficult to query, we need the parent layer of the selector we are imitating
        model_selector = ctx.find(f"{base_jump}_Direction_MSG")
        model_selector_parent_query = (
            f"type_name:hkbLayer generator:{model_selector.object_id}"
        )

        layer2_direction = ctx.new_layer(
            generator=direction_selector,
            useMotion=True,
            weight=0.01,
            onByDefault=True,
            fadeInOutCurve=BlendCurve.LINEAR,
            variableBindingSet=get_binding_set(model_selector_parent_query),
        )

    # Assemble layers
    all_layers = []

    if enable_jump_attacks:
        all_layers.append(layer1_jumpattack_add)

    if base_jump != "Jump_N":
        all_layers.append(layer2_direction)

    layer_gen = ctx.new_layer_generator(
        name=f"{base_name} LayerGenerator",
        layers=all_layers,
    )

    # Finally generate the new state for the state machine
    jump_sm = ctx.find("'NewJump StateMachine'")
    jump_event = ctx.event(event)
    state_id = ctx.get_next_state_id(jump_sm)

    default_transitions = ctx.find("DefaultTransition")
    wildcard_transition = ctx.new_transition_info(
        state_id,
        jump_event, 
        transition=default_transitions,
        flags=TransitionInfoFlags(3584),
    )
    ctx.array_add(jump_sm, "wildcardTransitions/transitions", wildcard_transition)

    # Transition to jump loop (?)
    jump_loop_transition_effect = ctx.new_record(
        "CustomTransitionEffect",
        "<new>",
        name=f"{base_name}_to_Jump_Loop",
        duration=0.5,
        alignmentBone=-1,
    )

    jump_loop_state = ctx.find("Jump_Loop type_name:hkbStateMachine::StateInfo")
    jump_loop_transition = ctx.new_transition_info(
        jump_loop_state["stateId"].get_value(),
        "W_RideJump",  # Not sure why, but this is how it is
        transition=jump_loop_transition_effect,
    )
    state_transitions = ctx.new_transition_info_array(transitions=[jump_loop_transition])

    state = ctx.new_statemachine_state(
        state_id,  # TODO raster used 39643 here, just an unused one?
        name=base_name,
        transitions=state_transitions,
        generator=layer_gen,
    )
    ctx.array_add(jump_sm, "states", state)
