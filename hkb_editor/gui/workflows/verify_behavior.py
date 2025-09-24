import logging

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)


def _safe_pointer_get(ptr: HkbPointer) -> HkbRecord:
    if not ptr.is_set():
        return None

    val = ptr.get_value()
    return ptr.tagfile.objects.get(val)


def check_xml(behavior: HavokBehavior, root_logger: logging.Logger) -> None:
    logger = root_logger.getChild("xml")
    hollow = behavior._tree.xpath(".//object[not(.//record)]")

    # This is a bug that happens when an xml element is moved instead of copied
    if hollow:
        hollow_ids = [x.get("id") for x in hollow]
        logger.critical(
            f"The xml structure contains hollow object tags: {hollow_ids}"
        )


def check_statemachines(behavior: HavokBehavior, root_logger: logging.Logger) -> None:
    logger = root_logger.getChild("statemachines")

    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    statemachines = behavior.find_objects_by_type(sm_type, include_derived=True)

    # Verify that the TransitionInfoArray entries refer to existing StateInfos
    for sm in statemachines:
        sm_name = sm["name"].get_value()
        states: dict[int, HkbRecord] = {}

        for state_ptr in sm["states"]:
            state_info = _safe_pointer_get(state_ptr)
            if state_info:
                states[state_info["stateId"].get_value()] = state_info

        transition_info = _safe_pointer_get(sm["wildcardTransitions"])
        if not transition_info:
            continue

        transitions: HkbArray = transition_info["transitions"]

        for idx, trans in enumerate(transitions):
            sid = trans["toStateId"].get_value()

            if sid not in states:
                logger.error(
                    f"{sm_name}: wildcard transition {idx} has invalid toStateId {sid}"
                )

        # NOTE it's fine for states to not have a wildcard transition


def check_attributes(behavior: HavokBehavior, root_logger: logging.Logger) -> None:
    logger = root_logger.getChild("attributes")

    for xmlobj in behavior._tree.xpath(".//object"):
        obj = HkbRecord.from_object(behavior, xmlobj)

        # Verify that all pointers have valid targets
        ptr: HkbPointer
        for path, ptr in obj.find_fields_by_type(HkbPointer):
            target_id = ptr.get_value()
            if target_id and target_id not in behavior.objects:
                logger.error(f"Pointer {obj.object_id}/{path} has non-existing target {target_id}")

        array: HkbArray
        for path, array in obj.find_fields_by_type(HkbArray):
            if array.is_pointer_array:
                for ptr in array:
                    if not ptr.is_set():
                        # Will cause the game to crash if it's a statemachine
                        logger.warning(f"Pointer array {obj.object_id}/{path} contains null-pointers")
                        break

        if obj.type_name in event_attributes:
            paths = event_attributes[obj.type_name]
            for path, idx in obj.get_fields(paths, resolve=True).items():
                if idx >= 0 and not behavior.get_event(idx, None):
                    logger.warning(f"Object {str(obj)} references missing event {idx}")

        if obj.type_name in variable_attributes:
            paths = variable_attributes[obj.type_name]
            for path, idx in obj.get_fields(paths, resolve=True).items():
                if idx >= 0 and not behavior.get_variable(idx, None):
                    logger.warning(f"Object {str(obj)} references missing variable {idx}")

        if obj.type_name in animation_attributes:
            paths = animation_attributes[obj.type_name]
            for path, idx in obj.get_fields(paths, resolve=True).items():
                if idx >= 0 and not behavior.get_animation(idx, None):
                    logger.warning(f"Object {str(obj)} references missing animation {idx}")


def check_graph(behavior: HavokBehavior, root_logger: logging.Logger) -> None:
    logger = root_logger.getChild("attributes")

    root = behavior.find_first_by_type_name("hkRootLevelContainer")
    #root_sm: HkbRecord = behavior_graph["rootGenerator"].get_target()
    g = behavior.build_graph(root.object_id)

    unmapped_ids = set(behavior.objects.keys()).difference(g.nodes)
    abandoned = [behavior.objects[oid] for oid in unmapped_ids]

    if abandoned:
        logger.warning(f"The following objects are abandoned: {[str(o) for o in abandoned]}")


def verify_behavior(behavior: HavokBehavior) -> None:
    logger = logging.getLogger("verify")
    
    logger.info("-> checking xml syntax...")
    check_xml(behavior, logger)
    
    logger.info("-> checking statemachines and states...")
    check_statemachines(behavior, logger)
    
    logger.info("-> checking object attributes...")
    check_attributes(behavior, logger)

    logger.info("-> checking graph structure...")
    check_graph(behavior, logger)
