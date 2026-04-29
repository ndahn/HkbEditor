from typing import Literal
from hkb_editor.hkb import HkbPointer
from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)
from hkb_editor.hkb.hkb_flags import hkbBlenderGenerator_Flags as BlendFlags


def run(
    ctx: TemplateContext,
    base_name: str,
    anim_selector: CmsgOffsetType = CmsgOffsetType.WEAPON_CATEGORY_RIGHT,
    function_call: bool = False,
    anim1_name: str = "Start",
    anim1: Animation = None,
    anim2_name: str = "Light",
    anim2: Animation = None,
    anim3_name: str = "Heavy",
    anim3: Animation = None,
    anim4_name: str = "Reload",
    anim4: Animation = None,
    anim5_name: str = "End",
    anim5: Animation = None,
    loop: Animation = None,
    move_loop: Animation = None,
    motion_blend: Literal["walk", "stance", "no-blend"] = "walk",
):
    """Halfblend Action

    Creates a new action that can be done while moving.

    The regular animation slots are all meant for oneshot animations, e.g. firing a crossbow. Only slots with an animation *and* name will be generated. If you need a looping animation place it in the `loop` slot (for the idle) and `loop_move` for when you're moving. The `motion_blend` attribute decides which movement type to use.

    At the end this template will print some HKS definitions you will need to execute your halfblend with `ExecEventHalfBlend`.

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/halfblend_slot/

    Author: Managarm

    Status: confident

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    base_name : str
        The names of generated nodes and events will be derived from this.
    anim_selector : CmsgOffsetType, optional
        How the CMSGs will select their clips (when multiple animations are registered).
    function_call : bool, optional
        Call a <base_name>_Activate() HKS function whenever the halfblend activates.
    anim1_name : str, optional
        Suffix of nodes in animation slot 1.
    anim1 : Animation, optional
        Animation to use for animation slot 1.
    anim2_name : str, optional
        Suffix of nodes in animation slot 2.
    anim2 : Animation, optional
        Animation to use for animation slot 2.
    anim3_name : str, optional
        Suffix of nodes in animation slot 3.
    anim3 : Animation, optional
        Animation to use for animation slot 3.
    anim4_name : str, optional
        Suffix of nodes in animation slot 4.
    anim4 : Animation, optional
        Animation to use for animation slot 4.
    anim5_name : str, optional
        Suffix of nodes in animation slot 5.
    anim5 : Animation, optional
        Animation to use for animation slot 5.
    loop : Animation, optional
        Looping idle animation.
    move_loop : Animation, optional
        Looping animation while moving. Only used if loop is also set.
    motion_blend : Literal[&quot;walk&quot;, &quot;stance&quot;, &quot;no, optional
        Which movement type to blend while in the move_loop animation.

    """
    # Definitions the user needs for HKS
    def0 = f"{base_name.upper()}_DEF0"
    hks_definitions: list[str] = []
    hks_functions: list[str] = []

    upper_sm = ctx.find("name=Upper_SM")

    action_state_id = ctx.get_next_state_id(upper_sm)
    action_state = ctx.new_statemachine_state(action_state_id, name=base_name)
    hks_definitions.append(f"{def0} = {action_state_id}")

    # NOTE: no wildcard transition needed due to how halfblends work
    ctx.array_add(upper_sm, "states", action_state)

    # Many halfblends use an additional function to setup stuff when activated
    # (since the SM's initial state isn't predefined)
    if function_call:
        hks_common_func = f"{base_name.replace(' ', '_')}_Activate()"
        script_gen = ctx.new_record(
            "hkbScriptGenerator",
            "<new>",
            name=f"{base_name} Script",
            onActivateScript=hks_common_func,
        )
        action_state["generator"] = script_gen
        action_parent: HkbPointer = script_gen["child"]
        hks_functions.append(hks_common_func)
    else:
        action_parent: HkbPointer = action_state["generator"]

    # New SM for this action
    action_sm = ctx.new_statemachine(0, f"{base_name}_SM")
    ctx.bind_variable(action_sm, "startStateId", "UpperDefaultState01")
    action_parent.set_value(action_sm)

    # Create the desired state chains
    default_transition = ctx.get_default_transition_effect()

    def add_definition(event: Event, suffix: str, state_id: int) -> None:
        """Example:
        ```lua
        ATTACKCROSSBOWRIGHTSTART_DEF1 = 0
        Event_AttackCrossbowRightStart = {
            "W_AttackCrossbowRightStart",
            ATTACKCROSSBOWRIGHT_DEF0,
            ATTACKCROSSBOWRIGHTSTART_DEF1
        }
        ```
        """

        def1 = f"{base_name.upper()}_{suffix.upper()}_DEF1"
        hks_definitions.append(f"{def1} = {state_id}")
        hks_definitions.append(
            f'Event_{base_name}_{suffix} = {{"{event.name}", {def0}, {def1}}}'
        )

    def add_function(suffix: str) -> None:
        hks_functions.append(
            f"{base_name.replace(' ', '_')}_{suffix.replace(' ', '_')}"
        )

    def make_action_state(
        anim: Animation, suffix: str
    ) -> tuple[HkbRecord, HkbRecord, HkbRecord]:
        state_id = ctx.get_next_state_id(action_sm)
        state, cmsg, clip = ctx.create_state_chain(
            state_id,
            ctx.animation(anim),
            f"{base_name}_{suffix}",
            cmsg_kwargs={
                "offsetType": anim_selector,
                "animeEndEventType": AnimeEndEventType.NONE,
                "changeTypeOfSelectedIndexAfterActivate": ChangeType.SELF_TRANSITION,
            },
        )

        event = ctx.event(f"W_{base_name}_{suffix}")
        ctx.register_wildcard_transition(
            action_sm,
            state_id,
            event,
            transition_effect=default_transition,
        )
        ctx.array_add(action_sm, "states", state)

        add_definition(event, suffix, state_id)
        add_function(suffix)
        return (state, cmsg, clip)

    for anim, suffix in [
        (anim1, anim1_name),
        (anim2, anim2_name),
        (anim3, anim3_name),
        (anim4, anim4_name),
        (anim5, anim5_name),
    ]:
        if anim and suffix:
            make_action_state(anim, suffix)

    if loop:
        loop_state_id = ctx.get_next_state_id(action_sm)
        loop_state = ctx.new_statemachine_state(loop_state_id, name=f"{base_name}_Loop")

        loop_event = ctx.event(f"W_{base_name}_Loop")
        ctx.register_wildcard_transition(
            action_sm,
            loop_state_id,
            loop_event,
            transition_effect=default_transition,
        )
        ctx.array_add(action_sm, "states", loop_state)
        add_definition(loop_event, "Loop", loop_state_id)

        # Manual selector to transition between idle and moving
        loop_sel = ctx.new_manual_selector(
            "LocomotionState",
            name=f"{base_name}_Loop Selector",
            selectedIndexCanChangeAfterActivate=True,
            generatorChangedTransitionEffect=ctx.find("Duration7_Sync"),
        )
        loop_state["generator"] = loop_sel

        # CMSG for animation while not moving. Yes, single play - it's magic
        loop_clip = ctx.new_clip(loop, mode=PlaybackMode.LOOPING)
        loop_cmsg = ctx.new_cmsg(
            loop.anim_id,
            name=f"{base_name}_LoopIdle_CMSG",
            generators=[loop_clip],
            offsetType=anim_selector,
            animeEndEventType=AnimeEndEventType.NONE,
            changeTypeOfSelectedIndexAfterActivate=ChangeType.SELF_TRANSITION,
        )
        ctx.array_add(loop_sel, "generators", loop_cmsg)

        # Additional loop animation while moving, blended with the move type
        if move_loop and motion_blend != "no-blend":
            # While moving the animation is blended with the move type
            action_blend_child, _, _ = ctx.create_blend_chain(
                ctx.animation(move_loop),
                blend_weight=1,
                cmsg_name=f"{base_name}_LoopMove_CMSG",
                offsetType=anim_selector,
            )

            if motion_blend == "walk":
                # Used by crossbow attacks
                move_sel = ctx.find("name=Move_motion")
            elif motion_blend == "stance":
                # Used by stance AOWs
                move_sel = ctx.find("name=MoveStance_selector")
            else:
                raise ValueError(f"Unknown loop_move_blend {motion_blend}")

            move_blend_child = ctx.new_blender_generator_child(move_sel, weight=0)

            loop_blend = ctx.new_blender_generator(
                [action_blend_child, move_blend_child],
                name=f"{base_name}_Loop Blend",
                indexOfSyncMasterChild=1,
                flags=BlendFlags.SYNC | BlendFlags.PARAMETRIC_BLEND,
            )
            ctx.array_add(loop_sel, "generators", loop_blend)

    msg = f"""Success! Copy the following lines and add them to your HKS:

{"\n".join(hks_definitions)}

To execute your halfblend action, call `ExecEventHalfBlend` with any of the `Event_*` definitions.
In addition you should create the following HKS functions:

{"\n".join(hks_functions)}
"""
    ctx.logger.info(msg)
