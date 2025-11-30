import logging
import re
from pathlib import Path
import networkx as nx

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)
from .update_name_ids import get_nameidfile_folder


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
        wildcard_state_ids = {}

        for idx, trans in enumerate(transitions):
            sid = trans["toStateId"].get_value()
            
            if sid in wildcard_state_ids:
                wildcard_state_ids.setdefault(sid, []).append(idx)

            if sid not in states:
                logger.error(
                    f"{sm_name}: wildcard transition {idx} has invalid toStateId {sid}"
                )

        for sid, wcidx in wildcard_state_ids.items():
            if len(wcidx) > 1:
                logger.warning(f"{sm_name}: state ID {sid} has multiple wildcard transitions: {wcidx}")

        # NOTE it's fine for states to *not* have a wildcard transition


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
                has_nullptr = False
                for ptr in array:
                    if not ptr.is_set():
                        # Can still be okay if only null pointers follow
                        has_nullptr = True
                    elif has_nullptr:
                        # Found a value after a null pointer, this will usually cause the game 
                        # to crash when accessed
                        logger.error(f"Pointer array {obj.object_id}/{path} contains non-terminal null-pointers, this is probably bad")
                        break
                else:
                    if has_nullptr:
                        logger.warning(f"Pointer array {obj.object_id}/{path} contains terminal null-pointers, might be okay")

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

    root = behavior.behavior_root
    #root_sm: HkbRecord = behavior_graph["rootGenerator"].get_target()
    g = behavior.build_graph(root.object_id)

    unmapped_ids = set(behavior.objects.keys()).difference(g.nodes)
    abandoned = [behavior.objects[oid] for oid in unmapped_ids]

    if abandoned:
        logger.warning(f"The following objects are abandoned: {[str(o) for o in abandoned]}")

    cycles = list(nx.simple_cycles(g))
    if cycles:
        logger.warning("Behavior graph contains cycles:")
        for cycle in cycles:
            logger.warning(f"- {cycle}")


def check_nameid_files(behavior: HavokBehavior, root_logger: logging.Logger) -> None:
    logger = root_logger.getChild("nameidfiles")
    path = get_nameidfile_folder(behavior)

    if not path:
        logger.warning("Could not get folder of name ID files")
        return

    def check_nameidfile_contents(file_path: Path, values: list[str]):
        line_pattern = re.compile(r"([0-9]+)\s*=\s*\"(.+)\"")
        registered = set()
        expected = 0

        # Read the file contents
        with file_path.open(errors="ignore") as f:
            for line in f.readlines():
                line = line.strip()

                if line.startswith("\x00"):
                    break

                if line.startswith("Num "):
                    expected = int(line.split("=")[-1])
                    continue

                match = re.match(line_pattern, line)
                if match:
                    # idx = int(match.group(1))
                    name = match.group(2)
                    registered.add(name)

        if len(registered) != expected:
            logger.error(f"{file_path.name} has wrong number of entries: expected {expected}, but found {len(registered)}")

        # Are all our values contained?
        if not registered.issuperset(values):
            logger.error(f"{file_path.name} is missing entries, please run File -> Update name ID files")

    stateids_file = path / "statenameid.txt"
    if stateids_file.is_file():
        statenames = [
            obj["name"].get_value()
            for obj in behavior.query("type_name='hkbStateMachine::StateInfo'")
        ]
        check_nameidfile_contents(stateids_file, statenames)
    else:
        logger.error(f"{stateids_file} not found, please copy it from the game folder")

    eventids_file = path / "eventnameid.txt"
    if eventids_file.is_file():
        eventnames = behavior.get_events()
        check_nameidfile_contents(eventids_file, eventnames)
    else:
        logger.error(f"{eventids_file} not found, please copy it from the game folder")

    variableids_file = path / "variablenameid.txt"
    if variableids_file.is_file():
        variablenames = behavior.get_variables()
        check_nameidfile_contents(variableids_file, variablenames)
    else:
        logger.error(f"{variableids_file} not found, please copy it from the game folder")


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

    logger.info("-> checking name ID files...")
    check_graph(behavior, logger)
