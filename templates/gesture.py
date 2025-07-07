from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as EndEventType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfo_Flags as TransitionFlags,
)


def _make_state_chain(
    ctx: TemplateContext, anim: Animation, event: Event, state_id: int
):
    name = event.name.strip("W_")

    clip = ctx.create(
        "hkbClipGenerator",
        name=anim.name,
        animationName=anim.name,
        playbackSpeed=1,
        animationInternalId=anim.index,
    )

    cmsg = ctx.create(
        "CustomManualSelectorGenerator",
        name=name + "_CMSG",
        generators=[clip.object_id],  # TODO verify this works
        offsetType=11,
        animId=int(anim.name.split("_")[1]),
        enableScript=False,
        enableTae=False,
        checkAnimEndSlotNo=-1,
    )

    state = ctx.create(
        "hkbStateMachine::StateInfo",
        transitions=None,
        generator=cmsg.object_id,
        name=name,
        stateId=state_id,
        probability=1,
        enable=True,
    )

    return state, cmsg, clip


def _make_blender_chain(
    ctx: TemplateContext, anim: Animation, common_clip: HkbRecord, gesture_id: int
):
    cmsg = ctx.create(
        "CustomManualSelectorGenerator",
        name=f"Gesture_{anim.name}_LoopStart",
        generators=[common_clip.object_id],
        offsetType=11,
        animId=int(anim.name.split("_")[1]),
        animeEndEventType=EndEventType.NONE,
        enableScript=False,
        enableTae=False,
        checkAnimEndSlotNo=-1,
    )

    blend = ctx.create(
        "hkbBlenderGeneratorChild",
        generator=cmsg.object_id,
        weight=gesture_id,
        worldFromModelWeight=1,
    )

    return blend, cmsg


def run(
    ctx: TemplateContext,
    event1_name: str,
    anim_start: Animation,
    event2_name: str,
    anim_loop: Animation,
    anim_end: Animation,
    gesture_id: int = 91,
):
    gesture_sm = ctx.find("name:EventGesture_SM")
    state1_id = utils.get_next_state_id(gesture_sm)
    state2_id = state1_id + 1

    # Setup new statemachine state transitions
    wildcard_transitions = gesture_sm["wildcardTransitions"].get_target()

    # State 1: start, state 2: loop
    event1 = ctx.new_event(event1_name)
    event2 = ctx.new_event(event2_name)
    # Creates an automatic transition between the states
    transition_event = ctx.new_event(f"{event1_name}_to_{event2_name}")

    flags = TransitionFlags(3584)

    trans1 = ctx.create(
        "hkbStateMachine::TransitionInfo",
        generate_id=False,
        transition="object9398",  # TODO
        eventId=event1.index,
        toStateId=state1_id,
        flags=flags,
    )

    trans2 = ctx.create(
        "hkbStateMachine::TransitionInfo",
        generate_id=False,
        transition="object9398",  # TODO
        eventId=event2.index,
        toStateId=state2_id,
        flags=flags,
    )

    # add states to wildcard_transitions
    ctx.array_add(wildcard_transitions, "transitions", trans1)
    ctx.array_add(wildcard_transitions, "transitions", trans2)

    ####
    # Start to loop
    ####
    state1, state1_cmsg, state1_clip = _make_state_chain(
        ctx, anim_start, event1, state1_id
    )
    default_transition = ctx.find("name:DefaultTransition")
    transition_info = ctx.create(
        "hkbStateMachine::TransitionInfoArray",
        transition=default_transition.object_id,
        eventId=transition_event.index,
        toStateId=state2_id,
    )

    ctx.set(state1, transitions=transition_info.object_id)
    ctx.set(
        state1_cmsg,
        enableTae=True,
        animeEndEventType=EndEventType.FIRE_NEXT_STATE_EVENT,
    )
    ctx.array_add(gesture_sm, "states", state1)

    # Blending
    start_blend_clip = ctx.create(
        "hkbClipGenerator",
        name=anim_start.name,
        animationName=anim_start.name,
        playbackSpeed=1,
        animationInternalId=anim_start.index,
    )

    start_blend01, start_blend01_cmsg = _make_blender_chain(
        ctx, anim_start, start_blend_clip, gesture_id
    )
    blend01_gen = ctx.find("name:GestureLoopStart Blend01")
    ctx.array_add(blend01_gen, "children", start_blend01.object_id)

    start_blend00, start_blend00_cmsg = _make_blender_chain(
        ctx, anim_start, start_blend_clip, gesture_id
    )
    ctx.set(start_blend00_cmsg, enableScript=True, enableTae=True, checkAnimEndSlotNo=1)
    start_blend00_gen = ctx.find("name:GestureLoopStart Blend00")
    ctx.array_add(start_blend00_gen, "children", start_blend01.object_id)

    ####
    # Loop anim
    ####
    state2, cmsg2, clip2 = _make_state_chain(ctx, anim_loop, event2, state2_id)
    ctx.set(cmsg2, enableTae=True)
    ctx.set(clip2, mode=1)  # Looping
    ctx.array_add(gesture_sm, "states", state2)

    # Blending
    loop_blend_clip = ctx.create(
        "hkbClipGenerator",
        name=anim_loop.name,
        animationName=anim_loop.name,
        playbackSpeed=1,
        animationInternalId=anim_loop.index,
        mode=1,  # looping
    )

    loop_blend00, loop_blend00_cmsg = _make_blender_chain(
        ctx, anim_loop, loop_blend_clip, gesture_id
    )
    loop_blend00_gen = ctx.find("name:GestureLoop Blend00")
    ctx.array_add(loop_blend00_gen, "children", loop_blend00.object_id)

    loop_blend02, loop_blend02_cmsg = _make_blender_chain(
        ctx, anim_loop, loop_blend_clip, gesture_id
    )
    ctx.set(loop_blend02_cmsg, enableScript=True, enableTae=True, checkAnimEndSlotNo=1)
    loop_blend02_gen = ctx.find("name:GestureLoop Blend02")
    ctx.array_add(loop_blend02_gen, "children", loop_blend02.object_id)

    # TODO this seems disconnected from the rest, not even a state or dedicated event?
    ####
    # Loop end
    ####
    end_blend_clip = ctx.create(
        "hkbClipGenerator",
        name=anim_end.name,
        animationName=anim_end.name,
        playbackSpeed=1,
        animationInternalId=anim_end.index,
    )

    end_blend01, end_blend01_cmsg = _make_blender_chain(
        ctx, anim_end, end_blend_clip, gesture_id
    )
    end_blend01_gen = ctx.find("name:GestureLoopEnd Blend01")
    ctx.array_add(end_blend01_gen, "children", end_blend01.object_id)

    end_blend00, end_blend00_cmsg = _make_blender_chain(
        ctx, anim_end, end_blend_clip, gesture_id
    )
    ctx.set(end_blend00_cmsg, enableScript=True, enableTae=True, checkAnimEndSlotNo=1)
    end_blend00_gen = ctx.find("name:GestureLoopEnd Blend00")
    ctx.array_add(end_blend00_gen, "children", end_blend00.object_id)
