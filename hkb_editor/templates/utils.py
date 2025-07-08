from typing import Any
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import Tagfile, HavokBehavior, HkbRecord, HkbPointer, HkbArray
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
)


def get_object(
    tagfile: Tagfile, obj: HkbRecord | str, default: Any = None
) -> HkbRecord:
    if obj is None:
        return None

    if isinstance(obj, HkbRecord):
        return obj

    if obj in tagfile.objects:
        # Is it an object ID?
        return tagfile.objects[obj]

    # Assume it's a query string
    return next(tagfile.query(obj), default)


def get_next_state_id(statemachine: HkbRecord | str) -> int:
    statemachine = get_object(statemachine.tagfile, statemachine)

    max_id = 0
    state_ptr: HkbPointer

    for state_ptr in statemachine["states"]:
        state = state_ptr.get_target()
        state_id = state["stateId"].get_value()
        max_id = max(max_id, state_id)

    return max_id + 1


def bind_variable(
    behavior: HavokBehavior,
    hkb_object: HkbRecord,
    path: str,
    variable: str | int,
) -> None:
    binding_set_ptr: HkbPointer = hkb_object["variableBindingSet"]
    
    if not binding_set_ptr.get_value():
        # Need to create a new variable binding set first
        binding_set_type_id = behavior.type_registry.find_first_type_by_name(
            "hkbVariableBindingSet"
        )

        binding_set = HkbRecord.new(
            behavior, 
            binding_set_type_id,
            {
                "indexOfBindingToEnable": -1,
            },
            object_id = behavior.new_id(),
        )

        behavior.add_object(binding_set)
        binding_set_ptr.set_value(binding_set.object_id)
    else:
        binding_set = binding_set_ptr.get_target()

    if isinstance(variable, str):
        variable = behavior.find_variable(variable)

    bindings: HkbArray = binding_set["bindings"]
    for bind in bindings:
        if bind["memberPath"] == path:
            # Binding for this path already exists, update it
            bind["variableIndex"] = variable
            break
    else:
        # Create a new binding for the path
        bind = HkbRecord.new(
            behavior,
            bindings.element_type_id,
            {
                "memberPath": path,
                "variableIndex": variable,
                "bitIndex": -1,
                "binding_type": 0,
            }
        )
        bindings.append(bind)


# FIXME are these useful?
# Offer common defaults and highlight required settings, 
# but also need an explicit behavior


def new_cmsg(
    behavior: HavokBehavior,
    *,
    object_id: str = "<new>",
    name: str = "",
    animId: int | str = 0,
    generators: list[HkbRecord | str] = None,
    offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
    enableScript: bool = True,
    enableTae: bool = True,
    checkAnimEndSlotNo: int = -1,
    **kwargs
) -> HkbRecord:
    cmsg_type_id = behavior.type_registry.find_first_type_by_name(
        "CustomManualSelectorGenerator"
    )

    if isinstance(animId, str):
        # Assume it's an animation name
        animId = int(animId.split("_")[-1])

    if generators:
        generators = [get_object(obj) for obj in generators]

    cmsg = HkbRecord.new(
        behavior,
        cmsg_type_id,
        {
            "name": name,
            "generators": generators,
            "offsetType": offsetType.value,
            "animId": animId,
            "enableScript": enableScript,
            "enableTae": enableTae,
            "checkAnimEndSlotNo": checkAnimEndSlotNo,
            **kwargs,
        },
        object_id=object_id,
    )

    if object_id:
        behavior.add_object(cmsg)
        undo_manager.on_create_object(behavior, cmsg)

    return cmsg


def new_clip(
    behavior: HavokBehavior,
    animation: int | str,
    *,
    object_id: str = "<new>",
    name: str = None,
    playbackSpeed: int = 1,
    **kwargs
) -> HkbRecord:
    clip_type_id = behavior.type_registry.find_first_type_by_name("hkbClipGenerator")

    if isinstance(animation, int):
        anim_name = behavior.get_animation(animation)
        anim_id = animation
    else:
        anim_name = animation
        anim_id = behavior.find_animation(animation)

    if name is None:
        name = anim_name

    clip = HkbRecord.new(
        behavior,
        clip_type_id,
        {
            "name": name,
            "animationName": anim_name,
            "playbackSpeed": playbackSpeed,
            "animationInternalId": anim_id,
            **kwargs,
        },
        object_id=object_id,
    )

    if object_id:
        behavior.add_object(clip)
        undo_manager.on_create_object(behavior, clip)

    return clip


def new_statemachine_state(
    behavior: HavokBehavior,
    stateId: int,
    *,
    object_id: str = "<new>",
    name: str = "",
    transitions: HkbRecord | str = None,
    generator: HkbRecord | str = None,
    probability: float = 1.0,
    enable: bool = True,
    **kwargs
) -> HkbRecord:
    state_type_id = behavior.type_registry.find_first_type_by_name(
        "hkbStateMachine::StateInfo"
    )

    transition = get_object(transition)
    generator = get_object(generator)

    state = HkbRecord.new(
        behavior,
        state_type_id,
        {
            "stateId": stateId,
            "name": name,
            "transitions": transitions.object_id if transition else None,
            "generator": generator.object_id if generator else None,
            "probability": probability,
            "enable": enable,
            **kwargs,
        },
        object_id=object_id,
    )

    if object_id:
        behavior.add_object(state)
        undo_manager.on_create_object(behavior, state)

    return state


def new_transition_info_array(
    behavior: HavokBehavior,
    toStateId: int,
    eventId: str | int,
    *,
    object_id: str = "<new>",
    transition: HkbRecord | str = None,
    **kwargs
) -> HkbRecord:
    transition_info_array_type_id = behavior.type_registry.find_first_type_by_name(
        "hkbStateMachine::TransitionInfoArray"
    )

    if transition is None:
        transition = next(behavior.query("name:DefaultTransition"), None)

    transition_info_array = HkbRecord.new(
        behavior,
        transition_info_array_type_id,
        {
            "toStateId": toStateId,
            "eventId": eventId,
            "transition": transition.object_id if transition else None,
            **kwargs,
        },
        object_id=object_id,
    )

    if object_id:
        behavior.add_object(transition_info_array)
        undo_manager.on_create_object(behavior, transition_info_array)

    return transition_info_array


def new_blender_generator_child(
    behavior: HavokBehavior,
    cmsg: HkbRecord | str,
    *,
    object_id: str = "<new>",
    weight: float = 0.0,
    worldFromModelWeight: int = 1,
    **kwargs
) -> HkbRecord:
    blender_child_type_id = behavior.type_registry.find_first_type_by_name(
        "hkbBlenderGeneratorChild"
    )

    if transition is None:
        transition = next(behavior.query("name:DefaultTransition"), None)
        if transition:
            transition = transition.object_id

    cmsg = get_object(cmsg)

    blender_child = HkbRecord.new(
        behavior,
        blender_child_type_id,
        {
            "generator": cmsg.object_id if cmsg else None,
            "weight": weight,
            "worldFromModelWeight": worldFromModelWeight,
            **kwargs,
        },
        object_id=object_id,
    )

    if object_id:
        behavior.add_object(blender_child)
        undo_manager.on_create_object(behavior, blender_child)

    return blender_child
