import logging

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)


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
            state_info = state_ptr.get_target()
            if state_info:
                states[state_info["stateId"].get_value()] = state_info

        transition_info = sm["wildcardTransitions"].get_target()
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
                logger.warning(f"Pointer {obj.object_id}/{path} has non-existing target {target_id}")



def validate_behavior(behavior: HavokBehavior) -> None:
    logger = logging.getLogger("verify")
    
    check_xml(behavior, logger)
    check_statemachines(behavior, logger)
    check_attributes(behavior, logger)
