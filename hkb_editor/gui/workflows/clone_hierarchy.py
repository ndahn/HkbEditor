from typing import Any, Callable
import logging
from dataclasses import dataclass, field
import re
from ast import literal_eval
from copy import deepcopy
from enum import Enum
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.xml import get_xml_parser, add_type_comments
from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)
from hkb_editor.hkb import HkbPointer, HkbRecord, HkbArray, XmlValueHandler
from hkb_editor.hkb.type_registry import TypeMismatch
from hkb_editor.gui import style
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.helpers import common_loading_indicator, add_paragraphs


class MergeAction(Enum):
    NEW = 0
    REUSE = 1
    IGNORE = 2
    SKIP = 3


@dataclass
class Resolution:
    original: Any = None
    action: MergeAction = MergeAction.NEW
    result: Any = None


@dataclass
class MergeResult:
    root_id: str = None
    root_meta: dict[str:Any] = field(default_factory=dict)
    events: dict[int, Resolution] = field(default_factory=dict)
    variables: dict[int, Resolution] = field(default_factory=dict)
    animations: dict[int, Resolution] = field(default_factory=dict)
    type_map: dict[str, Resolution] = field(default_factory=dict)
    objects: dict[str, Resolution] = field(default_factory=dict)
    pin_objects: bool = True


def copy_hierarchy(start_obj: HkbRecord) -> str:
    behavior = start_obj.tagfile
    start_id = start_obj.object_id

    root = behavior.find_first_by_type_name("hkRootLevelContainer")
    root_graph = behavior.build_graph(root.object_id)
    hierarchy_graph = root_graph.subgraph(
        {start_id} | nx.descendants(root_graph, start_id)
    )

    root_meta: dict[str, list] = {}
    events: dict[int, str] = {}
    variables: dict[int, HkbVariable] = {}
    animations: dict[int, str] = {}
    objects: list[HkbRecord] = []
    type_map: dict[str, str] = {}

    todo = [start_id]

    while todo:
        oid = todo.pop()

        obj = behavior.objects.get(oid)
        if not obj:
            continue

        # Make sure to handle paths with * wildcards
        if obj.type_name in event_attributes:
            paths = event_attributes[obj.type_name]
            for evt in obj.get_fields(paths, resolve=True).values():
                if evt >= 0:
                    event_name = behavior.get_event(evt, None)
                    events[evt] = event_name or ""

        if obj.type_name in variable_attributes:
            paths = variable_attributes[obj.type_name]
            for var in obj.get_fields(paths, resolve=True).values():
                if var >= 0:
                    variable = behavior.get_variable(var, None)
                    variables[var] = variable or ""

        if obj.type_name in animation_attributes:
            paths = animation_attributes[obj.type_name]
            for anim in obj.get_fields(paths, resolve=True).values():
                if anim >= 0:
                    animation_name = behavior.get_animation(anim, None)
                    animations[anim] = animation_name or ""

        objects.append(obj)
        type_map[obj.type_id] = obj.type_name

        # Element types need to be remapped, too. Pointers on the other hand are okay since they
        # don't save their subtype in the xml.
        array: HkbArray
        for _, array in obj.find_fields_by_type(HkbArray):
            type_map[array.element_type_id] = array.element_type_name

        todo.extend(hierarchy_graph.successors(oid))

    # The root object might need additional data to be merged correctly
    if start_obj.type_name == "hkbStateMachine::StateInfo":
        # Include the wildcard transition info
        sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
        root_sm = next(behavior.find_hierarchy_parents_for(start_obj, sm_type))
        transition_info: HkbRecord = root_sm["wildcardTransitions"].get_target()
        state_id = start_obj["stateId"].get_value()

        transition: HkbRecord
        for transition in transition_info["transitions"]:
            if transition["toStateId"].get_value() == state_id:
                meta_wildcards = root_meta.setdefault("wildcard_transitions", [])
                meta_wildcards.append(transition)

                transition_effect: HkbRecord = transition["transition"].get_target()
                if transition_effect and transition_effect not in objects:
                    objects.append(transition_effect)

                    if transition_effect.type_id not in type_map:
                        type_map[transition_effect.type_id] = (
                            transition_effect.type_name
                        )

                trans_event_idx = transition["eventId"].get_value()
                trans_event_name = behavior.get_event(trans_event_idx, None)
                events[trans_event_idx] = trans_event_name

    # Create using the parser so we can use our guarded xml element class
    xml_root = ET.fromstring(b"<behavior_hierarchy/>", get_xml_parser())
    xml_root_meta = ET.SubElement(xml_root, "root_meta", root_id=start_id)
    xml_events = ET.SubElement(xml_root, "events")
    xml_variables = ET.SubElement(xml_root, "variables")
    xml_animations = ET.SubElement(xml_root, "animations")
    xml_types = ET.SubElement(xml_root, "types")
    xml_objects = ET.SubElement(
        xml_root, "objects", graph=str(nx.to_edgelist(hierarchy_graph))
    )

    # Root Meta
    # Find paths through the behavior graph that lead to the start object. This is the
    # only reliable way of locating an object
    root_paths = nx.all_shortest_paths(root_graph, root.object_id, start_id)
    for path in root_paths:
        chain = []
        for idx, node_id in enumerate(path[:-1]):
            obj: HkbRecord = behavior.objects[node_id]
            next_id = path[idx + 1]
            for attr_path, ptr in obj.find_fields_by_type(HkbPointer):
                if ptr.get_value() == next_id:
                    chain.append(attr_path)
                    break

        if chain:
            ET.SubElement(xml_root_meta, "path").text = str(chain)

    # Additional metadata for potentially reconstructing the root node
    for key, items in root_meta.items():
        meta_group = ET.SubElement(xml_root_meta, key)

        for item in items:
            if isinstance(item, XmlValueHandler):
                meta_group.append(deepcopy(item.element))
            else:
                ET.SubElement(meta_group, "item", value=str(item))

    # Events
    for idx, evt in events.items():
        ET.SubElement(xml_events, "event", idx=str(idx), name=evt)

    # Variables
    for idx, var in variables.items():
        # Need to include ALL variable attributes so we can reconsruct it if needed
        if var:
            ET.SubElement(
                xml_variables,
                "variable",
                idx=str(idx),
                name=var.name,
                vtype=var.vtype.name,
                min=str(var.vmin),
                max=str(var.vmax),
                default=str(var.default),
            )
        else:
            ET.SubElement(xml_variables, "variable", idx=str(idx), name="")

    # Animations
    for idx, anim in animations.items():
        ET.SubElement(xml_animations, "animation", idx=str(idx), name=anim)

    # Types
    for type_id, type_name in type_map.items():
        ET.SubElement(xml_types, "type", id=type_id, name=type_name)

    # Objects
    for obj in objects:
        # Be careful not to remove the object elements from their original xml doc!
        xml_objects.append(deepcopy(obj.as_object()))

    add_type_comments(xml_root, behavior)
    ET.indent(xml_root)
    ret = ET.tostring(xml_root, pretty_print=True, encoding="unicode")
    logging.getLogger().info(f"Serialized {len(objects)} objects")

    return ret


def import_hierarchy(
    behavior: HavokBehavior,
    xml: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    interactive: bool = True,
):
    try:
        xmldoc = ET.fromstring(xml, get_xml_parser())
    except Exception as e:
        raise ValueError(f"Failed to parse hierarchy: {e}")

    root_id = xmldoc.find("root_meta").get("root_id")
    logger = logging.getLogger()

    def resolve_root_path(root_path: list[str]) -> HkbPointer:
        target_obj = behavior_root
        target_ptr: HkbPointer

        # Follow the chain
        for path in root_path[-1]:
            target_ptr = target_obj.get_field(path)
            new_target_obj = target_ptr.get_target()

            if new_target_obj is None:
                logger.warning(
                    f"Failed to resolve root path {target_obj}/{path}: target is None"
                )
                return None

            target_obj = new_target_obj

        # Check if the last path component went into a pointer array. If so, append
        # and return a new pointer.
        target_path = root_path[-1]
        if re.match(r"^.*:[0-9]+$", target_path):
            target_path = target_path.rsplit(":", maxsplit=1)[0]

        return target_obj, target_path

    def update_target_pointers(hierarchy: MergeResult):
        hierarchy_root = hierarchy.objects[root_id]
        if not hierarchy_root.result or hierarchy_root.action != MergeAction.NEW:
            return

        target_id = hierarchy_root.result.object_id

        for target_obj, target_path in targets:
            try:
                ptr: HkbPointer = target_obj.get_field(target_path)
                old_value = ptr.get_value()
                ptr.set_value(target_id)
                undo_manager.on_update_value(ptr, old_value, target_id)
            except ValueError as e:
                logger.warning(f"Pointer update failed: {e}")

        if callback:
            callback(hierarchy)

    with undo_manager.combine():
        # The taret object may be attached in more than one place
        targets = []

        behavior_root = behavior.find_first_by_type_name("hkRootLevelContainer")

        for path_elem in xmldoc.xpath(".//root_meta/path"):
            try:
                root_path: list[str] = literal_eval(path_elem.text)
            except Exception:
                logger.warning(f"Failed to parse root path {path_elem.text}")
                continue

            target = resolve_root_path(root_path)
            if target:
                targets.append(target)

        if not targets:
            logger.warning("Reference analysis did not result in any targets")
            return

        target_obj, target_path = targets[0]

        paste_hierarchy(
            behavior,
            xmldoc,
            target_obj,
            target_path,
            update_target_pointers,
            children_only=False,
            interactive=interactive,
        )


def paste_hierarchy(
    behavior: HavokBehavior,
    xml: str | ET._Element,
    target_record: HkbRecord,
    target_path: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    interactive: bool = True,
) -> MergeResult:
    if isinstance(xml, str):
        try:
            xmldoc = ET.fromstring(xml, get_xml_parser())
        except Exception as e:
            raise ValueError(f"Failed to parse hierarchy: {e}")
    else:
        xmldoc = xml

    if xmldoc.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    root_id = xmldoc.find("root_meta").get("root_id")
    root_type = xmldoc.xpath(f".//object[@id='{root_id}']")[0].get("typeid")
    root_type_name = xmldoc.xpath(f".//type[@id='{root_type}']")[0].get("name")

    # Check if the target pointer is compatible with the hierarchy root
    target_pointer = target_record.get_field(target_path)

    if not isinstance(target_pointer, HkbPointer):
        raise ValueError(
            f"Target {target_record.object_id}/{target_path} is not a pointer (is {target_pointer})"
        )

    try:
        mapped_root_type = behavior.type_registry.find_first_type_by_name(
            root_type_name
        )
        if not target_pointer.will_accept(mapped_root_type):
            raise ValueError(
                f"Hierarchy is not compatible with target pointer: expected {target_pointer.subtype_name}, but got {mapped_root_type} ({root_type_name})"
            )
    except StopIteration:
        raise ValueError(
            f"Could not map object type {root_type} ({root_type_name}) to a known type ID"
        )

    loading = common_loading_indicator("Analyzing hierarchy")
    try:
        hierarchy = find_conflicts(behavior, xmldoc, target_record)
    finally:
        dpg.delete_item(loading)

    def add_objects():
        new_root: HkbRecord = hierarchy.objects[root_id].result
        if new_root:
            # Events, variables, etc. have already been created as needed,
            # just need to add the objects
            for res in hierarchy.objects.values():
                obj: HkbRecord = res.result
                # Objects with action <reuse> and <skip> should not be added
                if obj and res.action == MergeAction.NEW:
                    behavior.add_object(obj)

            target_pointer = target_record.get_field(target_path)
            target_pointer.set_value(new_root)

        if target_record.type_name == "hkbStateMachine":
            fix_state_ids(target_record)

        if callback:
            callback(hierarchy)

    if interactive:
        open_merge_hierarchy_dialog(
            behavior, xmldoc, hierarchy, target_record, add_objects
        )
    else:
        with undo_manager.guard(behavior):
            resolve_conflicts(behavior, target_record, hierarchy)
            hierarchy.pin_objects = True
            add_objects()


def paste_children(
    behavior: HavokBehavior,
    xml: str | ET._Element,
    target_record: HkbRecord,
    target_path: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    interactive: bool = True,
) -> MergeResult:
    logger = logging.getLogger()

    def add_children():
        nonlocal target_path

        root_id = xmldoc.find("root_meta").get("root_id")
        results.objects[root_id].action = MergeAction.SKIP

        source_obj: HkbRecord = results.objects[root_id].original
        root_children = set()
        for _, ptr in source_obj.find_fields_by_type(HkbPointer):
            if ptr.is_set():
                root_children.add(ptr.get_value())

        target_array = target_record.get_field(target_path)

        if isinstance(target_array, HkbPointer):
            target_path = target_path.rsplit(":", maxsplit=1)
            target_array = target_record.get_field(target_path)

        if not isinstance(target_array, HkbArray):
            raise ValueError(
                f"Cloning children failed because the target is nota HkbArray (is {target_array})"
            )

        refptr = HkbPointer.new(behavior, target_array.element_type_id)

        for res in results.objects.values():
            obj: HkbRecord = res.result
            if obj and res.action == MergeAction.NEW:
                if obj.object_id in root_children:
                    if refptr.will_accept(obj):
                        behavior.add_object(obj)
                        target_array.append(obj.object_id)
                    else:
                        res.action = MergeAction.SKIP
                        logger.warning(
                            f"Skipping incompatible hierarchy child {str(obj)}"
                        )
                else:
                    behavior.add_object(obj)

        # If we copy only the root's children we should merge the relevant wildcard transitions
        if source_obj.type_name == "hkbStateMachine":
            logger.info("Fixing state IDs and wildcard transitions")
            transfer_wildcard_transitions(behavior, results, source_obj, target_record)
            fix_state_ids(target_record)

        if callback:
            callback(results)
    
    # Parse the xml
    if isinstance(xml, str):
        try:
            xmldoc = ET.fromstring(xml, get_xml_parser())
        except Exception as e:
            raise ValueError("Clipboard data is not a valid hierarchy") from e
    else:
        xmldoc = xml

    if xmldoc.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    # Search for conflicts
    loading = common_loading_indicator("Analyzing hierarchy")
    try:
        results = find_conflicts(behavior, xmldoc, target_record)
        root_id = xmldoc.find("root_meta").get("root_id")
        results.objects[root_id].action = MergeAction.IGNORE
    finally:
        dpg.delete_item(loading)

    # Let the user decide what to transfer, or just transfer everything
    if interactive:
        open_merge_hierarchy_dialog(
            behavior, xmldoc, results, target_record, add_children
        )
    else:
        with undo_manager.guard(behavior):
            resolve_conflicts(behavior, target_record, results)
            results.pin_objects = True
            add_children()


def find_conflicts(
    behavior: HavokBehavior, xml: ET.Element, target_record: HkbRecord
) -> MergeResult:
    hierarchy = MergeResult()

    def _find_index_attribute_conflicts(
        behavior: HavokBehavior, xml: ET._Element, hierarchy: MergeResult
    ) -> None:
        # For events, variables and animations we check if there is already one with a matching name.
        # If there is no match it probably has to be created. If it exists but the index is different
        # we still treat it as a conflict, albeit one that has a likely solution.

        # Events
        for evt in xml.findall(".//event"):
            idx = int(evt.get("idx"))
            name = evt.get("name")

            if name:
                match_idx = behavior.find_event(name, -1)
                action = MergeAction.NEW if match_idx < 0 else MergeAction.REUSE
                hierarchy.events[idx] = Resolution((idx, name), action, (match_idx, name))
            else:
                hierarchy.events[idx] = Resolution((idx, name), MergeAction.SKIP, (-1, None))

        # Variables
        for var in xml.findall(".//variable"):
            idx = int(var.get("idx"))
            name = var.get("name")

            if name:
                vtype = VariableType[var.get("vtype")]
                vmin = var.get("min")
                vmax = var.get("max")
                default = var.get("default")

                try:
                    default = literal_eval(default)
                except ValueError:
                    # Assume it's a string
                    pass

                var = HkbVariable(name, vtype, vmin, vmax, default)
                match_idx = behavior.find_variable(name, -1)

                if match_idx < 0:
                    hierarchy.variables[idx] = Resolution((idx, var), MergeAction.NEW, (-1, var))
                else:
                    hierarchy.variables[idx] = Resolution(
                        (idx, var), MergeAction.REUSE, (match_idx, var)
                    )
            else:
                hierarchy.variables[idx] = Resolution((idx, var), MergeAction.SKIP, (-1, None))

        # Animations
        for anim in xml.findall(".//animation"):
            idx = int(anim.get("idx"))
            name = anim.get("name")

            if name:
                match_idx = behavior.find_animation(name, -1)
                action = MergeAction.NEW if match_idx < 0 else MergeAction.REUSE
                hierarchy.animations[idx] = Resolution(
                    (idx, name), action, (match_idx, name)
                )
            else:
                hierarchy.animations[idx] = Resolution((idx, name), MergeAction.SKIP, (-1, None))


    def _find_type_conflicts(
        behavior: HavokBehavior, xml: ET._Element, hierarchy: MergeResult
    ) -> None:
        logger = logging.getLogger()

        # Every type should have a corresponding match by name, even when the type IDs disagree
        for type_info in xml.findall(".//type"):
            tid = type_info.get("id")
            name = type_info.get("name")

            try:
                new_id = behavior.type_registry.find_first_type_by_name(name)
            except StopIteration:
                raise ValueError(f"Could not resolve type {tid} ({name})")

            if new_id != tid:
                logger.debug(f"Remapping object type {tid} ({name}) to {new_id}")

            hierarchy.type_map[tid] = Resolution((tid, name), MergeAction.REUSE, (new_id, name))


    def _find_object_conflicts(
        behavior: HavokBehavior, xml: ET.Element, hierarchy: MergeResult
    ) -> None:
        logger = logging.getLogger()
        mismatching_types = set()

        for xmlobj in xml.find("objects").getchildren():
            # Remap the typeid. Should only be relevant when cloning between different games or
            # versions of hklib, but in those cases it might just make it work
            old_type_id = xmlobj.get("typeid")
            new_type_id = hierarchy.type_map[old_type_id].result[0]
            xmlobj.set("typeid", new_type_id)
            obj = tmp = None

            try:
                # If the record comes from a different game (or version), the xml element might
                # have extra fields or miss some we are expecting. By constructing a new object
                # we ensure that all required fields are present.
                obj = HkbRecord.new(behavior, new_type_id, None, xmlobj.get("id"))
                tmp = HkbRecord.from_object(behavior, xmlobj)

                # Fix up element type IDs. Search for arrays in obj, but modify them in tmp so
                # they can be resolved properly. Pointers don't need fixing since they don't
                # save their subtype in the xml.
                array: HkbArray
                for path, _ in obj.find_fields_by_type(HkbArray):
                    array = tmp.get_field(path, None)
                    if array:
                        array.element_type_id = hierarchy.type_map[
                            array.element_type_id
                        ].result[0]

                obj.set_value(tmp)

                # Verify object has the expected fields
                behavior.type_registry.verify_object(obj)
            except TypeMismatch as e:
                type_name = behavior.type_registry.get_name(new_type_id)
                if type_name not in mismatching_types:
                    if e.missing:
                        logger.warning(
                            f"Hierarchy type {old_type_id} ({type_name}) is missing expected fields, will use default initializers: {e.missing}"
                        )

                    if e.extra:
                        logger.warning(
                            f"Hierarchy type {old_type_id} ({type_name}) contains unexpected fields which will be ignored: {e.extra}"
                        )

                    mismatching_types.add(type_name)
            except Exception as e:
                raise ValueError(
                    f"Failed to reconstruct object {xmlobj.get('id')} from xml"
                ) from e

            # Pointers
            # Find pointers in the behavior referencing this object's ID. If more than one
            # other object is already referencing it, it is most likely a reused object like
            # e.g. DefaultTransition.
            existing_obj = behavior.objects.get(obj.object_id)
            if (
                existing_obj
                and existing_obj.type_name == obj.type_name
                and obj.type_name
                in ("CustomTransitionEffect", "hkbBlendingTransitionEffect")
            ):
                hierarchy.objects[obj.object_id] = Resolution(obj, MergeAction.REUSE, existing_obj)
            else:
                hierarchy.objects[obj.object_id] = Resolution(obj, MergeAction.NEW, obj)

    _find_index_attribute_conflicts(behavior, xml, hierarchy)
    _find_type_conflicts(behavior, xml, hierarchy)
    _find_object_conflicts(behavior, xml, hierarchy)

    return hierarchy


def resolve_conflicts(
    behavior: HavokBehavior,
    target_record: HkbRecord,
    hierarchy: MergeResult,
) -> None:
    # TODO this should be optional
    # TODO define various conflict resolution strategies, like skip on conflict, reuse
    # on conflict, and whether to continue following a path if the parent had a conflict
    def is_object_included(object_id: str) -> bool:
        # The root object will not have any parents to check
        if object_id == list(hierarchy.objects.keys())[0]:
            return True

        # Check parents: if all of them are skipped or reused,
        # this one should be skipped, too
        for other in hierarchy.objects.values():
            if not other.result or other.result.object_id == object_id:
                continue

            if other.action in (MergeAction.NEW, MergeAction.IGNORE):
                ptr: HkbPointer
                for _, ptr in other.result.find_fields_by_type(HkbPointer):
                    if ptr.get_value() == object_id:
                        return True

        return False

    # Create missing events, variables and animations. If the value is not MergeAction.NEW we can
    # expect that a mapping to another value has been applied
    for idx, resolution in hierarchy.events.items():
        name = resolution.original[1]
        if resolution.action == MergeAction.NEW:
            new_idx = behavior.create_event(name)
            resolution.result = (new_idx, name)
        elif resolution.action == MergeAction.REUSE:
            new_idx = behavior.find_event(name)
            resolution.result = (new_idx, name)
        elif resolution.action == MergeAction.IGNORE:
            resolution.result = resolution.original
        elif resolution.action == MergeAction.SKIP:
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for event {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.variables.items():
        var: HkbVariable = resolution.original[1]
        if resolution.action == MergeAction.NEW:
            new_idx = behavior.create_variable(*var.astuple())
            resolution.result = (new_idx, var)
        elif resolution.action == MergeAction.REUSE:
            new_idx = behavior.find_variable(var.name)
            resolution.result = (new_idx, var)
        elif resolution.action == MergeAction.IGNORE:
            resolution.result = resolution.original
        elif resolution.action == MergeAction.SKIP:
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for variable {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.animations.items():
        name = resolution.original[1]
        if resolution.action == MergeAction.NEW:
            new_idx = behavior.create_animation(name)
            resolution.result = (new_idx, name)
        elif resolution.action == MergeAction.REUSE:
            new_idx = behavior.find_animation(name)
            resolution.result = (new_idx, name)
        elif resolution.action == MergeAction.IGNORE:
            resolution.result = resolution.original
        elif resolution.action == MergeAction.SKIP:
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for animation {idx} ({resolution.original[1]})"
            )

    # Handle conflicting objects
    for object_id, resolution in hierarchy.objects.items():
        if resolution.action == MergeAction.NEW:
            resolution.result = resolution.original

            # If the object is set to <new>, but none of its parents are cloned,
            # the object will not be included after all
            if not is_object_included(object_id):
                resolution.action = MergeAction.SKIP
                logging.getLogger().info(
                    f"Skipping object {object_id} as none of its parents are cloned"
                )
                continue

            if object_id in behavior.objects:
                new_id = behavior.new_id()
                resolution.result.object_id = new_id

        elif resolution.action == MergeAction.REUSE:
            resolution.result = behavior.objects[object_id]
        elif resolution.action == MergeAction.IGNORE:
            # Will not be added, but giving it a new ID will be prevent other objects from 
            # accidently referring to existing objects from the behavior
            resolution.result = resolution.original
            resolution.result.object_id = behavior.new_id()
        elif resolution.action == MergeAction.SKIP:
            resolution.result = None
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for object {object_id}"
            )

    # Fix object references
    for object_id, resolution in hierarchy.objects.items():
        # Fix any pointers pointing to conflicting objects
        obj: HkbRecord = resolution.result
        # We still want to update the pointers of ignored objects so that they can be 
        # followed later if needed
        if not obj or resolution.action not in (MergeAction.NEW, MergeAction.IGNORE):
            continue

        ptr: HkbPointer
        for _, ptr in obj.find_fields_by_type(HkbPointer):
            target_id = ptr.get_value()
            if not target_id:
                continue

            if target_id in hierarchy.objects:
                new_target = hierarchy.objects[target_id].result
                ptr.set_value(new_target)
            else:
                logging.getLogger().warning(
                    f"Object {object_id} references ID {target_id}, which is not part of the cloned hierarchy"
                )

    # Attribute updates
    for object_id, resolution in hierarchy.objects.items():
        obj: HkbRecord = resolution.result

        if not obj or resolution.action in (MergeAction.REUSE, MergeAction.SKIP):
            # Skip if object is not cloned or an existing object is reused
            continue

        # Fix up events, variables and animations
        # Make sure to handle paths with * wildcards
        if obj.type_name in event_attributes:
            paths = event_attributes[obj.type_name]
            for path, evt_idx in obj.get_fields(paths, resolve=True).items():
                evt_res = hierarchy.events.get(evt_idx)
                if evt_res is not None:
                    obj.set_field(path, evt_res.result[0])

        if obj.type_name in variable_attributes:
            paths = variable_attributes[obj.type_name]
            for path, var_idx in obj.get_fields(paths, resolve=True).items():
                var_res = hierarchy.variables.get(var_idx)
                if var_res is not None:
                    obj.set_field(path, var_res.result[0])

        if obj.type_name in animation_attributes:
            paths = animation_attributes[obj.type_name]
            for path, anim_idx in obj.get_fields(paths, resolve=True).items():
                anim_res = hierarchy.animations.get(anim_idx)
                if anim_res is not None:
                    obj.set_field(path, anim_res.result[0])

    # Handle additional root metadata
    # root_res = hierarchy.objects[hierarchy.root_id]



def transfer_wildcard_transitions(behavior: HavokBehavior, results: MergeResult, source_sm: HkbRecord, target_sm: HkbRecord):
    # Collect all wildcard transitions for easy access
    transitions = {}

    # Transferred objects will refer to new IDs but may not have been added yet
    new_id_map = {}
    for res in results.objects.values():
        if res.result:
            new_id_map[res.result.object_id] = res.original

    # The source wildcards ID has probably been updated
    source_wildcards_id = source_sm["wildcardTransitions"].get_value()
    source_wildcards = new_id_map.get(source_wildcards_id)

    if source_wildcards:
        for trans in source_wildcards["transitions"]:
            transitions[trans["toStateId"].get_value()] = trans

    # Check if the target statemachine has a TransitionInfoArray object and create it
    # if neccessary
    target_wildcards = target_sm["wildcardTransitions"].get_target()
    if target_wildcards is None:
        target_wildcards = HkbRecord.new(
            behavior, target_sm.get_field_type("wildcardTransitions")
        )

        behavior.add_object(target_wildcards)
        undo_manager.on_create_object(behavior, target_wildcards)

        target_sm["wildcardTransitions"].set_value(target_wildcards)
        undo_manager.on_update_value(
            target_sm["wildcardTransitions"],
            None,
            target_wildcards.object_id,
        )

    # Transfer the transition infos
    target_wildcards_array: HkbArray = target_wildcards["transitions"]
    for ptr in source_sm["states"]:
        target_state = new_id_map.get(ptr.get_value())
        if target_state:
            state_id = target_state["stateId"].get_value()
            trans: HkbRecord = transitions.get(state_id)
            if trans:
                new_trans = HkbRecord(
                    behavior,
                    deepcopy(trans.element),
                    target_wildcards_array.element_type_id,
                )
                target_wildcards_array.append(new_trans)



def fix_state_ids(statemachine: HkbRecord):
    discovered = set()
    remapped_states = {}

    ptr: HkbPointer
    for ptr in statemachine["states"]:
        state = ptr.get_target()
        sid = state["stateId"].get_value()

        if sid in discovered:
            new_sid = max(discovered) + 1
            state["stateId"].set_value(new_sid)
            discovered.add(new_sid)
            remapped_states[sid] = new_sid
        else:
            discovered.add(sid)

    discovered.clear()
    transition_info_array = statemachine["wildcardTransitions"].get_target()
    if transition_info_array:
        for transition in transition_info_array["transitions"]:
            # No clue how fromNestedStateId and toNestedStateId work, but they start at 0
            state_id = transition["toStateId"].get_value()

            if state_id < 0:
                continue

            if state_id in discovered:
                new_id = remapped_states.get(state_id)
                if new_id is not None:
                    transition["toStateId"].set_value(new_id)
            else:
                discovered.add(state_id)


def open_merge_hierarchy_dialog(
    behavior: HavokBehavior,
    xml: ET.Element,
    hierarchy: MergeResult,
    target_record: HkbRecord,
    callback: Callable[[], None],
    *,
    tag: str = None,
) -> None:
    if tag in (0, None, ""):
        tag = f"merge_hierarchy_dialog_{dpg.generate_uuid()}"

    graph_data = xml.find("objects").get("graph")
    graph_preview = None

    def update_action(sender: str, action: str, resolution: Resolution):
        resolution.action = MergeAction[action]

    def resolve():
        loading = common_loading_indicator("Merging Hierarchy")
        try:
            with undo_manager.guard(behavior):
                resolve_conflicts(behavior, target_record, hierarchy)
                hierarchy.pin_objects = dpg.get_value(f"{tag}_pin_objects")
                callback()
        finally:
            dpg.delete_item(loading)
            close()

    def close():
        if graph_preview:
            graph_preview.deinit()

        dpg.delete_item(dialog)

    event_rows: dict[str, int] = {}
    variable_rows: dict[str, int] = {}
    animation_rows: dict[str, int] = {}
    type_rows: dict[str, int] = {}
    object_rows: dict[str, int] = {}

    # Window content
    with dpg.window(
        width=1100 if graph_data else 600,
        height=670,
        label="Merge Hierarchy",
        modal=False,
        on_close=close,
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        with dpg.group(horizontal=True):
            if graph_data:
                from hkb_editor.gui.graph_widget import GraphWidget

                graph = nx.from_edgelist(literal_eval(graph_data), nx.DiGraph)
                highlighted_rows: dict[str, list[int]] = {}
                highlight_color = list(style.yellow)

                if len(highlight_color) < 3:
                    highlight_color.append(100)
                else:
                    highlight_color[3] = 100

                def get_node_frontpage(node):
                    obj: HkbRecord = hierarchy.objects[node.id].original

                    try:
                        return [
                            (obj["name"].get_value(), style.yellow),
                            (obj.type_name, style.white),
                            (node.id, style.blue),
                        ]
                    except AttributeError:
                        return [
                            (obj.type_name, style.white),
                            (node.id, style.blue),
                        ]

                def highlight_row(table_type: str, key: str, row_map: dict[str, int]):
                    table = f"{tag}_{table_type}_table"
                    row = f"{tag}_{table_type}_row_{key}"
                    row_idx = row_map[row]

                    dpg.highlight_table_row(table, row_idx, highlight_color)
                    highlighted_rows.setdefault(table, []).append(row_idx)

                def on_node_selected(node):
                    for table, rows in highlighted_rows.items():
                        for row in rows:
                            dpg.unhighlight_table_row(table, row)
                        rows.clear()

                    if node:
                        obj: HkbRecord = hierarchy.objects[node.id].original

                        # Highlight events, variables and animations this object references
                        if obj.type_name in event_attributes:
                            for path in event_attributes[obj.type_name]:
                                for evt in obj.get_fields(path, resolve=True).values():
                                    if evt >= 0:
                                        highlight_row("event", evt, event_rows)

                        if obj.type_name in variable_attributes:
                            for path in variable_attributes[obj.type_name]:
                                for var in obj.get_fields(path, resolve=True).values():
                                    if var >= 0:
                                        highlight_row("variable", var, variable_rows)

                        if obj.type_name in animation_attributes:
                            for path in animation_attributes[obj.type_name]:
                                for anim in obj.get_fields(path, resolve=True).values():
                                    if anim >= 0:
                                        highlight_row("animation", anim, animation_rows)

                        for resolution in hierarchy.type_map.values():
                            if obj.type_id == resolution.result[0]:
                                # Old type ID is unique, new one may not be
                                old_type_id = resolution.original[0]
                                highlight_row("type", old_type_id, type_rows)
                                break

                        highlight_row("object", obj.object_id, object_rows)

                with dpg.child_window(
                    width=500,
                    height=500,
                    resizable_x=True,
                    no_scrollbar=True,
                    no_scroll_with_mouse=True,
                    horizontal_scrollbar=False,
                ):
                    graph_preview = GraphWidget(
                        graph,
                        on_node_selected=on_node_selected,
                        get_node_frontpage=get_node_frontpage,
                        hover_enabled=True,
                        width=500,
                        height=500,
                        tag=f"{tag}_graph_preview",
                    )

                    # Reveal everything when first showing
                    graph_preview.reveal_all_nodes()
                    dpg.split_frame()  # wait for dimensions to be known
                    graph_preview.zoom_show_all()

            # List of conflicts and resolutions
            with dpg.child_window(border=False, height=520):

                # Events
                with dpg.group():
                    with dpg.tree_node(label="Events", default_open=True):
                        with dpg.table(
                            header_row=False,
                            policy=dpg.mvTable_SizingFixedFit,
                            borders_innerH=True,
                            tag=f"{tag}_event_table",
                        ):
                            dpg.add_table_column(label="idx0", width_fixed=True)
                            dpg.add_table_column(label="name0", width_stretch=True)
                            dpg.add_table_column(label="to", width_fixed=True)
                            dpg.add_table_column(label="idx1", width_fixed=True)
                            dpg.add_table_column(label="name1", width_stretch=True)
                            dpg.add_table_column(
                                label="action", init_width_or_weight=100
                            )

                            for idx, (key, resolution) in enumerate(
                                hierarchy.events.items()
                            ):
                                row_tag = f"{tag}_event_row_{key}"
                                with dpg.table_row(tag=row_tag):
                                    dpg.add_text(str(resolution.original[0]))
                                    dpg.add_text(resolution.original[1])
                                    dpg.add_text("->")
                                    dpg.add_text(str(resolution.result[0]))
                                    dpg.add_text(resolution.result[1])

                                    actions = [a.name for a in MergeAction]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove(MergeAction.REUSE.name)
                                    else:
                                        # Can't add if the constant already exists
                                        actions.remove(MergeAction.NEW.name)

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action.name,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                event_rows[row_tag] = idx

                    dpg.add_spacer(height=10)

                    # Variables
                    with dpg.tree_node(label="Variables", default_open=True):
                        with dpg.table(
                            header_row=False,
                            policy=dpg.mvTable_SizingFixedFit,
                            borders_innerH=True,
                            tag=f"{tag}_variable_table",
                        ):
                            dpg.add_table_column(label="idx0", width_fixed=True)
                            dpg.add_table_column(label="name0", width_stretch=True)
                            dpg.add_table_column(label="to", width_fixed=True)
                            dpg.add_table_column(label="idx1", width_fixed=True)
                            dpg.add_table_column(label="name1", width_stretch=True)
                            dpg.add_table_column(
                                label="action", init_width_or_weight=100
                            )

                            for idx, (key, resolution) in enumerate(
                                hierarchy.variables.items()
                            ):
                                row_tag = f"{tag}_variable_row_{key}"
                                with dpg.table_row(tag=row_tag):
                                    dpg.add_text(str(resolution.original[0]))
                                    dpg.add_text(resolution.original[1].name)
                                    dpg.add_text("->")
                                    dpg.add_text(str(resolution.result[0]))
                                    dpg.add_text(resolution.result[1].name)

                                    actions = [a.name for a in MergeAction]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove(MergeAction.REUSE.name)
                                    else:
                                        # Can't add if the constant already exists
                                        actions.remove(MergeAction.NEW.name)

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action.name,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                variable_rows[row_tag] = idx

                    dpg.add_spacer(height=10)

                    # Animations
                    with dpg.tree_node(label="Animations", default_open=True):
                        with dpg.table(
                            header_row=False,
                            policy=dpg.mvTable_SizingFixedFit,
                            borders_innerH=True,
                            tag=f"{tag}_animation_table",
                        ):
                            dpg.add_table_column(label="idx0", width_fixed=True)
                            dpg.add_table_column(label="name0", width_stretch=True)
                            dpg.add_table_column(label="to", width_fixed=True)
                            dpg.add_table_column(label="idx1", width_fixed=True)
                            dpg.add_table_column(label="name1", width_stretch=True)
                            dpg.add_table_column(
                                label="action", init_width_or_weight=100
                            )

                            for idx, (key, resolution) in enumerate(
                                hierarchy.animations.items()
                            ):
                                row_tag = f"{tag}_animation_row_{key}"
                                with dpg.table_row(tag=row_tag):
                                    dpg.add_text(str(resolution.original[0]))
                                    dpg.add_text(resolution.original[1])
                                    dpg.add_text("->")
                                    dpg.add_text(str(resolution.result[0]))
                                    dpg.add_text(resolution.result[1])

                                    actions = [a.name for a in MergeAction]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove(MergeAction.REUSE.name)
                                    else:
                                        # Can't add if the constant already exists
                                        actions.remove(MergeAction.NEW.name)

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action.name,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                animation_rows[row_tag] = idx

                    dpg.add_spacer(height=10)

                    # Types
                    with dpg.tree_node(label="Types", default_open=True):
                        with dpg.table(
                            header_row=False,
                            policy=dpg.mvTable_SizingFixedFit,
                            borders_innerH=True,
                            tag=f"{tag}_type_table",
                        ):
                            dpg.add_table_column(label="id0", width_fixed=True)
                            dpg.add_table_column(label="to", width_fixed=True)
                            dpg.add_table_column(label="id1", width_fixed=True)
                            dpg.add_table_column(label="name", width_stretch=True)
                            dpg.add_table_column(
                                label="action", init_width_or_weight=100
                            )

                            for idx, (key, resolution) in enumerate(
                                hierarchy.type_map.items()
                            ):
                                row_tag = f"{tag}_type_row_{key}"

                                with dpg.table_row(tag=row_tag):
                                    dpg.add_text(str(resolution.original[0]))
                                    dpg.add_text("->")
                                    dpg.add_text(resolution.result[0])
                                    dpg.add_text(f"({resolution.result[1]})")
                                    dpg.add_combo(
                                        [MergeAction.REUSE.name],
                                        default_value=resolution.action.name,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                type_rows[row_tag] = idx

                    dpg.add_spacer(height=10)

                    # Objects
                    with dpg.tree_node(label="Objects", default_open=True):
                        with dpg.table(
                            header_row=False,
                            policy=dpg.mvTable_SizingFixedFit,
                            borders_innerH=True,
                            tag=f"{tag}_object_table",
                        ):
                            dpg.add_table_column(label="oid", width_fixed=True)
                            dpg.add_table_column(label="name", width_stretch=True)
                            dpg.add_table_column(
                                label="action", init_width_or_weight=100
                            )

                            for idx, (oid, resolution) in enumerate(
                                hierarchy.objects.items()
                            ):
                                row_tag = f"{tag}_object_row_{oid}"
                                with dpg.table_row(tag=row_tag):
                                    name = resolution.original.get_field("name", "")

                                    dpg.add_text(oid)
                                    dpg.add_text(name)

                                    actions = [a.name for a in MergeAction]
                                    if oid not in behavior.objects:
                                        # Can't reuse if there is no match
                                        actions.remove(MergeAction.REUSE.name)

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action.name,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                object_rows[row_tag] = idx

        dpg.add_separator()

        instructions = """\
The above hierarchy will be added to the behavior.

- NEW: add with a new ID/index
- REUSE: use already existing objects
- IGNORE: don't add, but include children (this can create gaps)
- SKIP: don't add and ignore all children (unless reachable otherwise)
"""
        add_paragraphs(instructions, 150, color=style.light_blue)

        dpg.add_separator()
        dpg.add_spacer(height=5)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Apply", callback=resolve, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=close,
                tag=f"{tag}_button_close",
            )

            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )
