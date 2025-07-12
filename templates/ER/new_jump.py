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


def run(
    ctx: TemplateContext,
    name: str,
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
    jump_sm = ctx.find("NewJump StateMachine")

    # Transition
    transition_effect = ctx.new_record(
        "CustomTransitionEffect",
        name=f"{name}_to_Jump_Loop",
        duration=0.5,
        selfTransitionMode=SelfTransitionMode.CONTINUE_IF_CYCLIC_BLEND_IF_ACYCLIC,
        eventMode=EventMode.DEFAULT,
        endMode=EndMode.NONE,
        blendCurve=BlendCurve.SMOOTH,
        alignmentBone=-1,
    )

    jump_loop_state = ctx.find("Jump_Loop type_name:hkbStateMachine::StateInfo")
    trans = ctx.new_transition_info(
        jump_loop_state["stateId"],
        "W_RideJump",
        transition=transition_effect.object_id,
    )
    transitions = ctx.new_transition_info_array(transitions=[trans])

    state_id = ctx.get_next_state_id(jump_sm)
    state = ctx.new_statemachine_state(
        state_id, # TODO raster used 39643 here, just an unused one?
        name=name,
        transitions=transitions,
        generator=None,  # set later
    )

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
        change_transition_blend = ctx.find("Selector_NormalAttack_Right")[
            "generatorChangedTransitionEffect"
        ].get_value()

        hand_nh_right_normal_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_NormalAttack_Right",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_BothLeft"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_BothLeft"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_hard_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_HardAttack_Right",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_BothLeft"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_BothLeft"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_normal_dual_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_NormalAttack_Dual",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_Right"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_Right"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_magic_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_N-HAttack_Right",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_Right"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_Right"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_right_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttackFormRequest
            name=f"{name} Selector_N-HAttack_Right",
            generators=[
                hand_nh_right_normal_selector,
                hand_nh_right_hard_selector,
                hand_nh_right_normal_dual_selector,
                hand_nh_right_magic_selector,
            ],
            variableBindingSet=get_binding_set(f"{base_jump} Selector_N-HAttack_Right"),
        )

        ### Hard Attack Both
        hand_nh_right_normal_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_NormalAttack_Both",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_Both"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_Both"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_right_hard_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_HardAttack_Both",
            generators=get_generators(f"{base_jump} Selector_HardAttack_Both"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_HardAttack_Both"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_N-HAttack_Both",
            generators=[
                hand_nh_right_normal_both_selector,
                hand_nh_right_hard_both_selector,
            ],
        )

        # Magic Left
        hand_magic_left_cmsg = ctx.new_cmsg(
            name=f"{name}_Left_CMSG",
            animId=45172,
            generators=get_generators("JumpMagic_N_Left_CMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
        )
        hand_magic_left_start_land_cmsg = ctx.new_cmsg(
            name=f"{name}_Left_Start_LandCMSG",
            animId=45174,
            generators=get_generators("JumpMagic_N_Left_Start_LandCMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )
        hand_magic_left_start_land_high_cmsg = ctx.new_cmsg(
            name=f"{name}_Left_Start_Land_High_CMSG",
            animId=45174,
            generators=get_generators("JumpMagic_N_Left_Start_Land_High_CMSG"),
            offsetType=CmsgOffsetType.MAGIC_CATEGORY,
            animeEndEventType=AnimeEndEventType.FIRE_IDLE_EVENT,
        )

        hand_magic_left_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_Magic_Left",
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
            name=f"{name} Selector_NormalAttack_BothLeft",
            generators=get_generators(f"{base_jump} Selector_NormalAttack_BothLeft"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_NormalAttack_BothLeft"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )
        hand_nh_left_hard_both_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_Land
            name=f"{name} Selector_HardAttack_BothLeft",
            generators=get_generators(f"{base_jump} Selector_HardAttack_BothLeft"),
            variableBindingSet=get_binding_set(f"{base_jump} Selector_HardAttack_BothLeft"),
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=change_transition_blend,
        )

        hand_nh_both_left_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttackFormRequest
            name=f"{name} Selector_N-HAttack_BothLeft",
            generators=[
                hand_nh_left_normal_both_selector,
                hand_nh_left_hard_both_selector,
            ],
            variableBindingSet=get_binding_set(f"{base_jump} Selector_N-HAttack_BothLeft")
        )

        # Top-level selector for jump attacks
        handcondition_selector = ctx.new_selector(
            None,  # we use an existing binding set with @JumpAttack_HandCondition
            name=f"{name} HandCondition Selector",
            generators=[
                hand_nh_right_selector,
                hand_nh_both_selector,
                hand_magic_left_selector,
                hand_nh_both_left_selector
            ],
            variableBindingSet=get_binding_set(f"{base_jump} HandCondition Selector"),
        )

        # Jump Attack Layer
        attack_jumpnormal_evt = ctx.get_event("Event_JumpNormalAttack_Add")
        
        # A bit difficult to query, we need the parent layer of the selector we are imitating
        model_selector = ctx.find(f"{base_jump} HandCondition Selector")
        model_selector_parent_query = f"type_name:hkbLayer generator:{model_selector.object_id}"

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
        else:
            jump_front_clips = get_generators(f"{base_jump}_Direction_Front_CMSG")
            jump_front_anim = 202020

        jump_front_cmsg = ctx.new_cmsg(
            name=f"{name}_Direction_Front_CMSG",
            animId=jump_front_anim,
            generators=jump_front_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Back
        if jump_back_anim:
            jump_back_clips = [ctx.new_clip(jump_back_anim)]
        else:
            jump_back_clips = get_generators(f"{base_jump}_Direction_Back_CMSG")
            jump_back_anim = 202021

        jump_back_cmsg = ctx.new_cmsg(
            name=f"{name}_Direction_BackCMSG",
            animId=jump_back_anim,
            generators=jump_back_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Left
        if jump_left_anim:
            jump_left_clips = [ctx.new_clip(jump_left_anim)]
        else:
            jump_left_clips = get_generators(f"{base_jump}_Direction_Left_CMSG")
            jump_left_anim = 202022

        jump_left_cmsg = ctx.new_cmsg(
            name=f"{name}_Direction_Left_CMSG",
            animId=jump_left_anim,
            generators=jump_left_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Right
        if jump_right_anim:
            jump_right_clips = [ctx.new_clip(jump_right_anim)]
        else:
            jump_right_clips = get_generators(f"{base_jump}_Direction_Right_CMSG")
            jump_right_anim = 202023

        jump_right_cmsg = ctx.new_cmsg(
            name=f"{name}_Direction_Right_CMSG",
            animId=jump_right_anim,
            generators=jump_right_clips,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        # Jump Direction Selector
        direction_selector = ctx.new_selector(
            None, # we use an existing binding set with @JumpDirection
            name=f"{name}_Direction_MSG",
            generators=[
                jump_front_cmsg,
                jump_back_cmsg,
                jump_left_cmsg,
                jump_right_cmsg,
            ],
            variableBindingSet=get_binding_set("Jump_F_Direction_MSG"),
        )

        # Regular Jump Layer
        # A bit difficult to query, we need the parent layer of the selector we are imitating
        model_selector = ctx.find(f"{base_jump}_Direction_MSG")
        model_selector_parent_query = f"type_name:hkbLayer generator:{model_selector.object_id}"

        layer2 = ctx.new_layer(
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
        all_layers.append(layer2)

    layer_gen = ctx.new_layer_generator(
        name=f"{name}_LayerGenerator",
        layers=all_layers,
    )

    ctx.set(state, "generator", layer_gen.object_id)
