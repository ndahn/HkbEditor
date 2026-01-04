from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionFlags,
)


def run(
    ctx: TemplateContext,
    event1: Event,
    anim_start: Animation,
    event2: Event,
    anim_loop: Animation,
    anim_end: Animation,
    gesture_id: int = 91,
):
    """New Gesture

    IMPORTANT: Work in progress, this will NOT work yet!

    Generates new gesture states for a gesture consisting of a loop start, loop, and loop end. To use the gesture, fire the event1 from hks.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/er/gesture/

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    event1 : Event
        Loop start event.
    anim_start : Animation
        Loop start animation.
    event2 : Event
        Loop event.
    anim_loop : Animation
        Loop animation.
    anim_end : Animation
        Loop end animation.
    gesture_id : int, optional
        The gesture ID, corresponds to TAE 300 + X.
    """
    # TODO this probably needs a rewrite and generalization, as I mixed up regular gestures and event gestures (or did I?)
    gesture_base_name = f"Gesture_{gesture_id:03}"

    event_gesture_sm = ctx.find("name=EventGesture_SM")
    gesture_sm = ctx.find("name=Gesture_SM")

    state1_id = ctx.get_next_state_id(event_gesture_sm)
    state2_id = state1_id + 1
    transition_effect = ctx.find("name=Duration0_Reset")

    # Setup new statemachine state transitions

    # State 1: start, state 2: loop
    # Creates an automatic transition between the states
    transition_event = ctx.event(f"{event1.name}_to_{event2.name}")

    transition_flags = TransitionFlags(3584)

    trans1 = ctx.new_transition_info(
        toStateId=state1_id,
        eventId=event1,
        transition=transition_effect,
        flags=transition_flags,
    )

    trans2 = ctx.new_transition_info(
        toStateId=state2_id,
        eventId=event2,
        transition=transition_effect,
        flags=transition_flags,
    )

    # add states to wildcard_transitions
    ctx.array_add(event_gesture_sm, "wildcardTransitions/transitions", trans1)
    ctx.array_add(event_gesture_sm, "wildcardTransitions/transitions", trans2)

    ####
    # Start to loop
    ####
    default_transition = ctx.get_default_transition_effect()
    transition_info = ctx.new_transition_info(
        toStateId=state2_id,
        eventId=transition_event,
        transition=default_transition,
    )
    transitions = ctx.new_transition_info_array(
        transitions=[transition_info]
    )

    # TODO use?
    # state1, state1_cmsg, state1_clip = ctx.create_state_chain(
    #     state1_id,
    #     anim_start,
    #     event1.name,
    #     state_transitions=transitions,
    #     cmsg_enable_script=False,
    #     offsetType=CmsgOffsetType.IDLE_CATEGORY,
    # )

    state1_clip = ctx.new_clip(anim_start.index)
    state1_cmsg = ctx.new_cmsg(
        anim_start.anim_id,
        name=f"{event1.name}_CMSG",
        generators=[state1_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        enableScript=False,
    )
    state1 = ctx.new_statemachine_state(
        stateId=state1_id,
        name=event1.name,
        generator=state1_cmsg,
        transitions=transitions,
    )

    ctx.array_add(gesture_sm, "states", state1)

    # Blending
    start_blend_common_clip = ctx.new_clip(anim_start.index)
    
    # TODO use?
    # start_blend01, start_blend01_cmsg = ctx.create_blend_chain(
    #     start_blend_common_clip,
    #     anim_start.index,
    #     f"{gesture_base_name}_LoopStart",
    #     blend_weight=gesture_id,
    #     cmsg_enable_script=False,
    #     cmsg_enable_tae=False,
    #     offsetType=CmsgOffsetType.IDLE_CATEGORY,
    #     nimeEndEventType=AnimeEndEventType.NONE,
    # )

    start_blend01_cmsg = ctx.new_cmsg(
        anim_start.anim_id,
        name=f"{gesture_base_name}_LoopStart",
        generators=[start_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        enableScript=False,
        enableTae=False,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    start_blend01 = ctx.new_blender_generator_child(
        start_blend01_cmsg,
        weight=gesture_id,
    )
    blend01_gen = ctx.find("name='GestureLoopStart Blend01'", start_from=gesture_sm)
    ctx.array_add(blend01_gen, "children", start_blend01)


    start_blend00_cmsg = ctx.new_cmsg(
        anim_start.anim_id,
        name=f"{gesture_base_name}_LoopStart00",
        generators=[start_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        checkAnimEndSlotNo=1,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    start_blend00 = ctx.new_blender_generator_child(
        start_blend00_cmsg,
        weight=gesture_id,
    )
    start_blend00_gen = ctx.find("name='GestureLoopStart Blend00'", start_from=gesture_sm)
    ctx.array_add(start_blend00_gen, "children", start_blend00)

    ####
    # Loop anim
    ####
    state2_clip = ctx.new_clip(anim_loop.index, mode=PlaybackMode.LOOPING)
    state2_cmsg = ctx.new_cmsg(
        anim_loop.anim_id,
        name=f"{event2.name}_CMSG",
        generators=[state2_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        enableScript=False,
    )
    state2 = ctx.new_statemachine_state(
        stateId=state2_id,
        name=event2.name,
        generator=state2_cmsg,
        transitions=transitions,
    )

    ctx.array_add(gesture_sm, "states", state2)

    # Blending
    loop_blend_common_clip = ctx.new_clip(anim_loop.index, mode=PlaybackMode.LOOPING)
    
    loop_blend00_cmsg = ctx.new_cmsg(
        anim_loop.anim_id,
        name=f"{gesture_base_name}_Loop",
        generators=[loop_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        enableScript=False,
        enableTae=False,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    loop_blend00 = ctx.new_blender_generator_child(
        loop_blend00_cmsg,
        weight=gesture_id,
    )
    loop_blend00_gen = ctx.find("name='GestureLoop Blend00'", start_from=gesture_sm)
    ctx.array_add(loop_blend00_gen, "children", loop_blend00)

    loop_blend02_cmsg = ctx.new_cmsg(
        anim_loop.anim_id,
        name=f"{gesture_base_name}_Loop02",
        generators=[loop_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        checkAnimEndSlotNo=1,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    loop_blend02 = ctx.new_blender_generator_child(
        loop_blend02_cmsg,
        weight=gesture_id,
    )
    loop_blend02_gen = ctx.find("name='GestureLoop Blend02'", start_from=gesture_sm)
    ctx.array_add(loop_blend02_gen, "children", loop_blend02)

    # TODO this seems disconnected from the rest, not even a state or dedicated event?
    ####
    # Loop end
    ####
    end_blend_common_clip = ctx.new_clip(anim_end.index)
    
    end_blend01_cmsg = ctx.new_cmsg(
        anim_end.anim_id,
        name=f"{gesture_base_name}_LoopEnd",
        generators=[end_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        enableScript=False,
        enableTae=False,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    end_blend01 = ctx.new_blender_generator_child(
        end_blend01_cmsg,
        weight=gesture_id,
    )
    end_blend01_gen = ctx.find("name='GestureLoopEnd Blend01'", start_from=gesture_sm)
    ctx.array_add(end_blend01_gen, "children", end_blend01)

    end_blend00_cmsg = ctx.new_cmsg(
        anim_end.anim_id,
        name=f"{gesture_base_name}_LoopEnd00",
        generators=[end_blend_common_clip],
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        checkAnimEndSlotNo=1,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    end_blend00 = ctx.new_blender_generator_child(
        end_blend00_cmsg,
        weight=gesture_id,
    )
    end_blend00_gen = ctx.find("name='GestureLoopEnd Blend00'", start_from=gesture_sm   )
    ctx.array_add(end_blend00_gen, "children", end_blend00)
