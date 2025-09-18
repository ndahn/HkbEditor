from typing import Any, Callable
import logging
from dataclasses import dataclass, field
import re
from ast import literal_eval
from copy import deepcopy
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.xml import get_xml_parser
from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)
from hkb_editor.hkb import HkbPointer, HkbRecord, HkbArray
from hkb_editor.hkb.type_registry import TypeMismatch
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui import style
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.helpers import common_loading_indicator, add_paragraphs


@dataclass
class Resolution:
    original: Any = None
    action: str = "<new>"
    result: Any = None


@dataclass
class MergeHierarchy:
    events: dict[int, Resolution] = field(default_factory=dict)
    variables: dict[int, Resolution] = field(default_factory=dict)
    animations: dict[int, Resolution] = field(default_factory=dict)
    type_map: dict[str, Resolution] = field(default_factory=dict)
    objects: dict[str, Resolution] = field(default_factory=dict)
    state_ids: dict[str, Resolution] = field(default_factory=dict)
    pin_objects: bool = True


def copy_hierarchy(behavior: HavokBehavior, root_id: str) -> str:
    g = behavior.build_graph(root_id)

    events: dict[int, str] = {}
    variables: dict[int, HkbVariable] = {}
    animations: dict[int, str] = {}
    objects: list[HkbRecord] = []
    type_map: dict[str, str] = {}

    todo = [root_id]

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

        todo.extend(g.successors(oid))

    references = []

    for obj, path, _ in behavior.find_references_to(root_id):
        # If the path is into a pointer array we should ignore the item index
        path = re.sub(r"/:[0-9]+$", "/:-1", path)
        references.append((obj.object_id, path))

    # Create using the parser so we can use our guarded xml element class
    root = ET.fromstring(b"<behavior_hierarchy/>", get_xml_parser())
    root.set("references", str(references))

    xml_events = ET.SubElement(root, "events")
    xml_variables = ET.SubElement(root, "variables")
    xml_animations = ET.SubElement(root, "animations")
    xml_types = ET.SubElement(root, "types")
    xml_objects = ET.SubElement(root, "objects", graph=str(nx.to_edgelist(g)))

    for idx, evt in events.items():
        ET.SubElement(xml_events, "event", idx=str(idx), name=evt)

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

    for idx, anim in animations.items():
        ET.SubElement(xml_animations, "animation", idx=str(idx), name=anim)

    for type_id, type_name in type_map.items():
        ET.SubElement(xml_types, "type", id=type_id, name=type_name)

    for obj in objects:
        # Be careful not to remove the object elements from their original xml doc! 
        xml_objects.append(deepcopy(obj.as_object()))

    ret = ET.tostring(root, pretty_print=True, encoding="unicode")
    logging.getLogger().info(f"Serialized {len(objects)} objects")
    return ret


def import_hierarchy(
    behavior: HavokBehavior,
    xml: str,
    callback: Callable[[MergeHierarchy], None] = None,
    *,
    interactive: bool = True,
):
    try:
        xmldoc = ET.fromstring(xml, get_xml_parser())
    except Exception as e:
        raise ValueError(f"Failed to parse hierarchy: {e}")

    root = xmldoc.find("objects").getchildren()[0]
    root_id = root.get("id")

    try:
        references = literal_eval(xmldoc.get("references"))
    except Exception as e:
        raise ValueError(f"Could not parse references attribute: {e}")

    if not references:
        raise ValueError(
            "Could not determine import target - try manually cloning the hierarchy"
        )

    logger = logging.getLogger()

    def resolve_target(target_id: str, target_path: str) -> HkbPointer:
        target_obj = behavior.objects.get(target_id)
        if not target_obj:
            raise ValueError(f"Hierarchy target {target_id} not found")

        if target_path.endswith("/:-1"):
            target_array: HkbArray[HkbPointer] = target_obj.get_field(target_path[:-4])
            if not target_array.is_pointer_array:
                raise ValueError(f"Invalid target path {target_obj}/{target_path}")

            for ptr in target_array:
                if ptr.get_value() == root_id:
                    logger.info(
                        f"Hierarchy already present at {target_obj}/{target_path}"
                    )
                    return

            target_ptr = target_array.append(None)
            undo_manager.on_update_array_item(target_array, -1, None, target_ptr)

            return target_ptr
        else:
            target_ptr = target_obj.get_field(target_path, None)
            if not target_ptr or not isinstance(target_ptr, HkbPointer):
                raise ValueError(
                    f"Failed to resolve target path {target_obj}/{target_path}"
                )

            return target_ptr

    def update_target_pointers(hierarchy: MergeHierarchy):
        hierarchy_root = hierarchy.objects[root_id]
        if not hierarchy_root.result or hierarchy_root.action != "<new>":
            return

        new_root_id = hierarchy_root.result.object_id

        for ptr in target_pointers:
            try:
                ptr.set_value(new_root_id)
            except ValueError as e:
                logger.warning(f"Pointer update failed: {e}")

        if callback:
            callback(hierarchy)

    with undo_manager.combine():
        target_pointers = [resolve_target(oid, path) for oid, path in references]
        target_pointers = [p for p in target_pointers if p is not None]

        if not target_pointers:
            logger.warning("Reference analysis did not result in any targets")
            return

        paste_hierarchy(
            behavior,
            target_pointers[0],
            xmldoc,
            update_target_pointers,
            interactive=interactive,
        )


def paste_hierarchy(
    behavior: HavokBehavior,
    target_pointer: HkbPointer,
    xml: str | ET._Element,
    callback: Callable[[MergeHierarchy], None] = None,
    *,
    interactive: bool = True,
) -> MergeHierarchy:
    if isinstance(xml, str):
        try:
            xmldoc = ET.fromstring(xml, get_xml_parser())
        except Exception as e:
            raise ValueError(f"Failed to parse hierarchy: {e}")
    else:
        xmldoc = xml

    if xmldoc.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    root = xmldoc.find("objects").getchildren()[0]
    root_id = root.get("id")
    root_type = root.get("typeid")
    root_type_name = xmldoc.xpath(f".//type[@id='{root_type}']")[0].get("name")

    try:
        mapped_root_type = behavior.type_registry.find_first_type_by_name(
            root_type_name
        )
    except StopIteration:
        raise ValueError(
            f"Could not map object type {root_type} ({root_type_name}) to a known type ID"
        )

    if not target_pointer.will_accept(mapped_root_type):
        raise ValueError(
            f"Hierarchy is not compatible with target pointer: expected {target_pointer.subtype_name}, but got {mapped_root_type}"
        )

    loading = common_loading_indicator("Analyzing hierarchy")
    try:
        hierarchy = find_conflicts(behavior, xmldoc, target_pointer)
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
                if obj and res.action == "<new>":
                    behavior.add_object(obj)

            target_pointer.set_value(new_root)

        if callback:
            callback(hierarchy)

    if interactive:
        open_merge_hierarchy_dialog(
            behavior, xmldoc, target_pointer, hierarchy, add_objects
        )
    else:
        with undo_manager.guard(behavior):
            resolve_conflicts(behavior, target_pointer, hierarchy)
            hierarchy.pin_objects = True
            add_objects()


def find_conflicts(
    behavior: HavokBehavior, xml: ET.Element, target_ptr: HkbPointer
) -> MergeHierarchy:
    hierarchy = MergeHierarchy()
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")

    target_record = behavior.find_object_for(target_ptr)
    if target_record.type_id == sm_type:
        target_sm = target_record
    else:
        target_sm = next(behavior.find_hierarchy_parent_for(target_record, sm_type))

    logger = logging.getLogger()
    mismatching_types = set()

    # For events, variables and animations we check if there is already one with a matching name.
    # If there is no match it probably has to be created. If it exists but the index is different
    # we still treat it as a conflict, albeit one that has a likely solution.

    # Events
    for evt in xml.findall(".//event"):
        idx = evt.get("idx")
        name = evt.get("name")

        if name:
            match_idx = behavior.find_event(name, -1)
            action = "<new>" if match_idx < 0 else "<reuse>"
            hierarchy.events[idx] = Resolution((idx, name), action, (match_idx, name))
        else:
            hierarchy.events[idx] = Resolution((idx, name), "<skip>", (-1, None))

    # Variables
    for var in xml.findall(".//variable"):
        idx = var.get("idx")
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
                hierarchy.variables[idx] = Resolution((idx, var), "<new>", (-1, var))
            else:
                hierarchy.variables[idx] = Resolution(
                    (idx, var), "<reuse>", (match_idx, var)
                )
        else:
            hierarchy.variables[idx] = Resolution((idx, var), "<skip>", (-1, None))

    # Animations
    for anim in xml.findall(".//animation"):
        idx = anim.get("idx")
        name = anim.get("name")

        if name:
            match_idx = behavior.find_animation(name, -1)
            action = "<new>" if match_idx < 0 else "<reuse>"
            hierarchy.animations[idx] = Resolution(
                (idx, name), action, (match_idx, name)
            )
        else:
            hierarchy.animations[idx] = Resolution((idx, name), "<skip>", (-1, None))

    # Types
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

        hierarchy.type_map[tid] = Resolution((tid, name), "<remap>", (new_id, name))

    # Objects
    # Find objects with IDs that already exist
    for xmlobj in xml.find("objects").getchildren():
        # Remap the typeid. Should only be relevant when cloning between different games or
        # versions of hklib, but in those cases it might just make it work
        old_type_id = xmlobj.get("typeid")
        new_type_id = hierarchy.type_map[old_type_id].result[0]
        xmlobj.set("typeid", new_type_id)

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

        # Pointers
        # Find pointers in the behavior referencing this object's ID. If more than one
        # other object is already referencing it, it is most likely a reused object like
        # e.g. DefaultTransition.
        existing_obj = behavior.objects.get(obj.object_id)
        if (
            existing_obj
            and existing_obj.type_name == obj.type_name
            and obj.type_name in ("CustomTransitionEffect", "hkbBlendingTransitionEffect")
        ):
            hierarchy.objects[obj.object_id] = Resolution(obj, "<reuse>", existing_obj)
        else:
            hierarchy.objects[obj.object_id] = Resolution(obj, "<new>", obj)

        # State IDs
        if obj.type_name == "hkbStateMachine::StateInfo":
            # Check if the hierarchy contains a statemachine which references the StateInfo.
            # StateInfo IDs can only be in conflict if they are pasted into a new statemachine.
            hsm: list = xml.xpath(
                f"/*/object[@type_id='{sm_type}' and .//pointer[@id='{obj.object_id}']]"
            )
            if hsm:
                continue

            obj_state_id = obj["stateId"].get_value()
            state_ptr: HkbPointer

            for state_ptr in target_sm["states"]:
                state = state_ptr.get_target()

                if not state:
                    continue

                target_state_id = state["stateId"].get_value()
                if target_state_id == obj_state_id:
                    hierarchy.state_ids[obj.object_id] = Resolution(state, "<new>")
                else:
                    hierarchy.state_ids[obj.object_id] = Resolution(state, "<keep>")

        # These will need some corrections, but will not result in additional conflicts
        # - hkbStateMachine
        # - hkbStateMachine::TransitionInfoArray
        # - hkbClipGenerator

    return hierarchy


def resolve_conflicts(
    behavior: HavokBehavior,
    target_pointer: HkbPointer,
    hierarchy: MergeHierarchy,
) -> None:
    common = CommonActionsMixin(behavior)
    state_id_map: dict[int, int] = {}

    def is_object_included(object_id: str) -> bool:
        # The root object will not have any parents to check
        if object_id == list(hierarchy.objects.keys())[0]:
            return True

        # Check parents: if all of them are skipped or reused,
        # this one should be skipped, too
        for other in hierarchy.objects.values():
            if not other.result or other.result.object_id == object_id:
                continue

            if other.action == "<new>":
                # <new> is the only action type that will include descendents
                ptr: HkbPointer
                for _, ptr in other.result.find_fields_by_type(HkbPointer):
                    if ptr.get_value() == object_id:
                        return True

        return False

    # Create missing events, variables and animations. If the value is not "<new>" we can
    # expect that a mapping to another value has been applied
    for idx, resolution in hierarchy.events.items():
        name = resolution.original[1]
        if resolution.action == "<new>":
            new_idx = behavior.create_event(name)
            resolution.result = (new_idx, name)
        elif resolution.action == "<reuse>":
            new_idx = behavior.find_event(name)
            resolution.result = (new_idx, name)
        elif resolution.action == "<keep>":
            resolution.result = resolution.original
        elif resolution.action == "<skip>":
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for event {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.variables.items():
        var: HkbVariable = resolution.original[1]
        if resolution.action == "<new>":
            new_idx = behavior.create_variable(*var.astuple())
            resolution.result = (new_idx, var)
        elif resolution.action == "<reuse>":
            new_idx = behavior.find_variable(var.name)
            resolution.result = (new_idx, var)
        elif resolution.action == "<keep>":
            resolution.result = resolution.original
        elif resolution.action == "<skip>":
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for variable {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.animations.items():
        name = resolution.original[1]
        if resolution.action == "<new>":
            new_idx = behavior.create_animation(name)
            resolution.result = (new_idx, name)
        elif resolution.action == "<reuse>":
            new_idx = behavior.find_animation(name)
            resolution.result = (new_idx, name)
        elif resolution.action == "<keep>":
            resolution.result = resolution.original
        elif resolution.action == "<skip>":
            resolution.result = (-1, None)
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for animation {idx} ({resolution.original[1]})"
            )

    # Handle conflicting objects
    for object_id, resolution in hierarchy.objects.items():
        if resolution.action == "<new>":
            # If the object is set to <new>, but none of its parents are cloned,
            # the object will not be included after all
            if not is_object_included(object_id):
                resolution.action = "<skip>"
                logging.getLogger().info(
                    f"Skipping object {object_id} as none of its parents are cloned"
                )
                continue

            if object_id in behavior.objects:
                resolution.original.object_id = behavior.new_id()
            
            resolution.result = resolution.original
        elif resolution.action == "<reuse>":
            resolution.result = behavior.objects[object_id]
        elif resolution.action == "<skip>":
            resolution.result = None
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for object {object_id}"
            )

    # StateInfo IDs
    # All conflicts found must be from "naked" StateInfos, e.g. they are copied
    # into a new statemachine
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    target_record = behavior.find_object_for(target_pointer)
    target_sm = next(behavior.find_hierarchy_parent_for(target_record, sm_type))

    # Fix object references
    for object_id, resolution in hierarchy.objects.items():
        # Fix any pointers pointing to conflicting objects
        obj: HkbRecord = resolution.result
        if not obj or resolution.action in ("<reuse>", "<skip>"):
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

    # State IDs
    # In theory it's not possible to paste more than one StateInfo without its statemachine,
    # but this certainly won't hurt. At the very least we can assume that there will only be
    # one statemachine with conflicts.
    state_id_offset = 0

    for object_id, resolution in hierarchy.state_ids.items():
        obj_res = hierarchy.objects[object_id]

        if not obj_res.result or obj_res.action in ("<reuse>", "<skip>"):
            # Skip if the object is reused or not cloned
            continue

        old_state_id = obj_res.result["stateId"].get_value()
        new_state_id = common.get_next_state_id(target_sm) + state_id_offset

        obj_res.result["stateId"].set_value(new_state_id)
        resolution.result = new_state_id
        state_id_map[old_state_id] = new_state_id
        state_id_offset += 1

    # Attribute updates
    for object_id, resolution in hierarchy.objects.items():
        obj: HkbRecord = resolution.result

        if not obj or resolution.action in ("<reuse>", "<skip>"):
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

        # hkbStateMachine::TransitionInfoArray
        # - transitions:*/toStateId
        # - transitions:*/fromNestedStateId
        # - transitions:*/toNestedStateId
        if obj.type_name == "hkbStateMachine::TransitionInfoArray":
            # TODO should verify this object belongs to a StateInfo with state ID conflicts
            for transition in obj["transitions"]:
                for attr in ["toStateId", "fromNestedStateId", "toNestedStateId"]:
                    attr_id = transition[attr].get_value()

                    if attr_id < 0:
                        continue

                    new_id = state_id_map.get(attr_id)
                    if new_id is not None:
                        transition[attr].set_value(new_id)

        # - hkbStateMachine
        #   - eventToSendWhenStateOrTransitionChanges/id (?)
        #   - startStateId
        elif obj.type_name == "hkbStateMachine":
            start_state_id = obj["startStateId"].get_value()

            if start_state_id >= 0:
                new_id = state_id_map.get(start_state_id)
                if new_id is not None:
                    obj["startStateId"].set_value(new_id)


def open_merge_hierarchy_dialog(
    behavior: HavokBehavior,
    xml: ET.Element,
    target_pointer: HkbPointer,
    hierarchy: MergeHierarchy,
    callback: Callable[[], None],
    *,
    tag: str = None,
) -> None:
    if tag in (0, None, ""):
        tag = f"merge_hierarchy_dialog_{dpg.generate_uuid()}"

    graph_data = xml.find("objects").get("graph")
    graph_preview = None

    def update_action(sender: str, action: str, resolution: Resolution):
        resolution.action = action

    def resolve():
        loading = common_loading_indicator("Merging Hierarchy")
        try:
            with undo_manager.guard(behavior):
                resolve_conflicts(behavior, target_pointer, hierarchy)
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
        with dpg.child_window(border=False, height=520):
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

                    def highlight_row(
                        table_type: str, key: str, row_map: dict[str, int]
                    ):
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
                                    for evt in obj.get_fields(
                                        path, resolve=True
                                    ).values():
                                        if evt >= 0:
                                            highlight_row("event", evt, event_rows)

                            if obj.type_name in variable_attributes:
                                for path in variable_attributes[obj.type_name]:
                                    for var in obj.get_fields(
                                        path, resolve=True
                                    ).values():
                                        if var >= 0:
                                            highlight_row(
                                                "variable", var, variable_rows
                                            )

                            if obj.type_name in animation_attributes:
                                for path in animation_attributes[obj.type_name]:
                                    for anim in obj.get_fields(
                                        path, resolve=True
                                    ).values():
                                        if anim >= 0:
                                            highlight_row(
                                                "animation", anim, animation_rows
                                            )

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

                                    actions = ["<new>", "<reuse>", "<keep>"]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove("<reuse>")

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action,
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

                                    actions = ["<new>", "<reuse>", "<keep>"]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove("<reuse>")

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action,
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

                                    actions = ["<new>", "<reuse>", "<keep>"]
                                    if resolution.result[0] < 0:
                                        # Can't reuse if there's no match
                                        actions.remove("<reuse>")

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action,
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
                                        ["<remap>"],
                                        default_value=resolution.action,
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

                                    actions = ["<new>", "<reuse>", "<skip>"]
                                    if oid not in behavior.objects:
                                        # Can't reuse if there is no match
                                        actions.remove("<reuse>")

                                    dpg.add_combo(
                                        actions,
                                        default_value=resolution.action,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                object_rows[row_tag] = idx

        dpg.add_separator()

        instructions = """\
The above hierarchy will be added to the behavior. Items with the "<new>" action will be added
under a new ID/index, while items with the "<remap>" action will use already existing objects
from the behavior. 

Note that new events, variables and animations must still have unique names - you'll have to fix
these afterwards.
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
