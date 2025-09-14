from typing import Any, Callable, Type
import logging
from dataclasses import dataclass, field
from copy import deepcopy
from ast import literal_eval
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb import HkbPointer, HkbRecord
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui import style
from hkb_editor.gui.graph_widget import GraphWidget
from hkb_editor.gui.workflows.undo import UndoManager


_event_attributes = {
    "hkbManualSelectorGenerator": [
        "endOfClipEventId",
    ],
    "hkbStateMachine" : ["eventToSendWhenStateOrTransitionChanges/id"],
    "hkbStateMachine::TransitionInfoArray": ["transitions:*/eventId"],
}

_variable_attributes = {
    "hkbVariableBindingSet": [
        "bindings:*/variableIndex",
    ]
}

_animation_attributes = {
    "hkbClipGenerator": [
        # While the index into the animations array may have changed, we can assume
        # that the animation name has not, so animationName and the clip's name don't
        # need to be changed. The same is true for the CMSG owning this clip.
        "animationInternalId",
    ]
}


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
    objects: dict[str, Resolution] = field(default_factory=dict)
    state_ids: dict[str, Resolution] = field(default_factory=dict)


@dataclass
class HierarchyConflicts:
    events: dict[tuple[int, str], str | int] = field(default_factory=dict)
    variables: dict[tuple[int, str], str | int] = field(default_factory=dict)
    animations: dict[tuple[int, str], str | int] = field(default_factory=dict)
    objects: dict[HkbRecord, str] = field(default_factory=dict)
    state_ids: dict[HkbRecord, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return (
            self.events
            or self.variables
            or self.animations
            or self.objects
            or self.state_ids
        )


@dataclass
class ConflictSolution:
    events: dict[int, int] = field(default_factory=dict)
    variables: dict[int, int] = field(default_factory=dict)
    animations: dict[int, int] = field(default_factory=dict)
    objects: dict[str, HkbRecord] = field(default_factory=dict)
    state_ids: dict[int, int] = field(default_factory=dict)


def copy_hierarchy(behavior: HavokBehavior, root_id: str) -> str:
    g = behavior.build_graph(root_id)

    events: dict[int, str] = {}
    variables: dict[int, HkbVariable] = {}
    animations: dict[int, str] = {}
    objects = []

    todo = [root_id]

    while todo:
        oid = todo.pop()

        obj = behavior.objects.get(oid)
        if not obj:
            continue

        # Make sure to handle paths with * wildcards
        if obj.type_name in _event_attributes:
            paths = _event_attributes[obj.type_name]
            for evt in obj.get_fields(paths, resolve=True).values():
                if evt >= 0:
                    event_name = behavior.get_event(evt)
                    events[evt] = event_name

        if obj.type_name in _variable_attributes:
            paths = _variable_attributes[obj.type_name]
            for var in obj.get_fields(paths, resolve=True).values():
                if var >= 0:
                    variable = behavior.get_variable(var)
                    variables[var] = variable

        if obj.type_name in _animation_attributes:
            paths = _animation_attributes[obj.type_name]
            for anim in obj.get_fields(paths, resolve=True).values():
                if anim >= 0:
                    animation_name = behavior.get_animation(anim)
                    animations[anim] = animation_name

        objects.append(obj)

        todo.extend(g.successors(oid))

    root = ET.Element("behavior_hierarchy")
    xml_events = ET.SubElement(root, "events")
    xml_variables = ET.SubElement(root, "variables")
    xml_animations = ET.SubElement(root, "animations")
    xml_objects = ET.SubElement(root, "objects", graph=str(nx.to_edgelist(g)))

    for idx, evt in events.items():
        ET.SubElement(xml_events, "event", idx=idx, name=evt)

    for idx, var in variables.items():
        # Need to include ALL variable attributes so we can reconsruct it if needed
        ET.SubElement(
            xml_variables,
            "variable",
            idx=idx,
            name=var.name,
            vtype=var.vtype.name,
            min=var.vmin,
            max=var.vmax,
            default=str(var.default),
        )

    for idx, anim in animations.items():
        ET.SubElement(xml_animations, "animation", idx=idx, name=anim)

    for obj in objects:
        xml_objects.append(deepcopy(obj))

    return ET.tostring(root, pretty_print=True, encoding="unicode")


def paste_hierarchy(
    behavior: HavokBehavior,
    target_pointer: HkbPointer,
    hierarchy: str,
    undo_manager: UndoManager,
) -> None:
    try:
        xml = ET.fromstring(hierarchy)
    except Exception as e:
        raise ValueError(f"Failed to parse hierarchy: {e}")

    if xml.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    root = xml.find("objects").getchildren()[0]
    root_type = root.attrib["typeid"]

    if not target_pointer.will_accept(root_type):
        raise ValueError("Hierarchy is not compatible with target pointer")

    hierarchy = find_conflicts(behavior, xml)

    with undo_manager.combine():
        resolve_merge_dialog(behavior, xml, target_pointer, hierarchy)

        # Events, variables, etc. have already been created as needed, 
        # just need to add the objects
        for res in hierarchy.objects.values():
            obj: HkbRecord = res.result
            if obj:
                behavior.add_object(obj)


def find_conflicts(behavior: HavokBehavior, xml: ET.Element) -> MergeHierarchy:
    hierarchy = MergeHierarchy()
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")

    # For events, variables and animations we check if there is already one with a matching name.
    # If there is no match it probably has to be created. If it exists but the index is different
    # we still treat it as a conflict, albeit one that has a likely solution.
    for evt in xml.findall(".//event"):
        idx = evt.get("idx")
        name = evt.get("name")
        
        match_idx = behavior.find_event(name, -1)
        action = "<new>" if match_idx < 0 else "<reuse>"
        hierarchy.events[idx] = Resolution(name, action, match_idx)

    for evt in xml.findall(".//variable"):
        idx = evt.get("idx")
        name = evt.get("name")
        vtype = VariableType[evt.get("vtype")]
        vmin = evt.get("min")
        vmax = evt.get("max")
        default = evt.get("default")
        
        try:
            default = literal_eval(default)
        except ValueError:
            # Assume it's a string
            pass

        var = HkbVariable(name, vtype, vmin, vmax, default)
        match_idx = behavior.find_variable(name, -1)
        
        if match_idx < 0:
            hierarchy.variables[idx] = Resolution(var, "<new>", -1)
        else:
            hierarchy.variables[idx] = Resolution(var, "<reuse>", match_idx)

    for evt in xml.findall(".//animation"):
        idx = evt.get("idx")
        name = evt.get("name")
        
        match_idx = behavior.find_animation(name, -1)
        action = "<new>" if match_idx < 0 else "<reuse>"
        hierarchy.animations[idx] = Resolution(name, action, match_idx)

    # Find objects with IDs that already exist
    for xmlobj in reversed(xml.find("objects").getchildren()):
        try:
            obj = HkbRecord.from_object(behavior, xmlobj)
            # TODO verify object has the expected fields
        except Exception as e:
            raise ValueError(f"Object {xmlobj.get("id")} with type_id {xmlobj.get("typeid")} does not match this behavior's type registry: {e}")

        # Find pointers in the behavior referencing this object's ID. If more than one
        # other object is already referencing it, it is most likely a reused object like
        # e.g. DefaultTransition.
        references = list(behavior.find_referees(obj.object_id))
        if len(references) > 1:
            hierarchy.objects[obj.object_id] = Resolution(
                obj, "<reuse>", behavior.objects[obj.object_id]
            )
        else:
            hierarchy.objects[obj.object_id] = Resolution(obj, "<new>", obj)

        # Type-specific conflicts

        # hkbStateMachine::StateInfo
        #   - stateId
        if obj.type_name == "hkbStateMachine::StateInfo":
            # Check if the hierarchy contains a statemachine which references the StateInfo.
            # StateInfo IDs can only be in conflict if they are pasted into a new statemachine.
            hsm = xml.xpath(
                f"/*/object[@type_id='{sm_type}' and .//pointer[@id='{obj.object_id}']]"
            )
            if next(hsm, None):
                continue

            obj_state_id = obj["stateId"].get_value()
            statemachine = behavior.find_hierarchy_parent_for(obj.object_id, sm_type)
            state_ptr: HkbPointer

            for state_ptr in statemachine["states"]:
                state = state_ptr.get_target()
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

    # TODO add undo actions
    # Create missing events, variables and animations. If the value is not "<new>" we can
    # expect that a mapping to another value has been applied
    for idx, resolution in hierarchy.events.items():
        if resolution.action == "<new>":
            resolution.result = behavior.create_event(resolution.original)
        elif resolution.action == "<reuse>":
            resolution.result = behavior.find_event(resolution.original)
        elif resolution.action == "<keep>":
            resolution.result = idx
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for event {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.variables.items():
        if resolution.action == "<new>":
            var: HkbVariable = resolution.original
            resolution.result = behavior.create_variable(*var.astuple())
        elif resolution.action == "<reuse>":
            resolution.result = behavior.find_variable(resolution.original)
        elif resolution.action == "<keep>":
            resolution.result = idx
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for variable {idx} ({resolution.original})"
            )

    for idx, resolution in hierarchy.animations.items():
        if resolution.action == "<new>":
            resolution.result = behavior.create_animation(resolution.original)
        elif resolution.action == "<reuse>":
            resolution.result = behavior.find_animation(resolution.original)
        elif resolution.action == "<keep>":
            resolution.result = idx
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for animation {idx} ({resolution.original})"
            )

    # Handle conflicting objects
    for object_id, resolution in hierarchy.objects.items():
        if resolution.action == "<new>":
            if object_id in behavior.objects:
                new_id = behavior.new_id()
                resolution.original.object_id = new_id
            resolution.result = resolution.original
        elif resolution.action == "<reuse>":
            resolution.result = behavior.objects[object_id]
        elif resolution.action == "<keep>":
            resolution.result = resolution.original
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
    target_sm = behavior.find_hierarchy_parent_for(target_record, sm_type)

    # Fix object references
    for object_id, resolution in hierarchy.objects.items():
        # Fix any pointers pointing to conflicting objects
        obj: HkbRecord = resolution.result
        if not obj or resolution.action == "<skip>":
            continue

        ptr: HkbPointer
        for ptr in obj.find_fields_by_type(HkbPointer):
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

    # Type-specific fixes

    # hkbStateMachine::StateInfo
    # - state IDs
    #
    # In theory it's not possible to paste more than one StateInfo without its statemachine,
    # but this certainly won't hurt. At the very least we can assume that there will only be
    # one statemachine with conflicts.
    state_id_offset = 0

    for object_id, resolution in hierarchy.state_ids.items():
        obj_res = hierarchy.objects[object_id]

        if obj_res.action == "<reuse>" or not obj_res.result:
            # Skip if the object is reused or not cloned
            continue

        old_state_id = obj_res.result["stateId"].get_value()
        new_state_id = common.get_next_state_id(target_sm) + state_id_offset

        obj_res.result["stateId"].set_value(new_state_id)
        resolution.result = new_state_id
        state_id_map[old_state_id] = new_state_id
        state_id_offset += 1

    for object_id, resolution in hierarchy.objects.items():
        obj = resolution.result

        if not obj or resolution.action == "<reuse>":
            # Skip if object is not cloned or an existing object is reused
            continue

        # Fix up events, variables and animations
        # Make sure to handle paths with * wildcards
        if obj.type_name in _event_attributes:
            paths = _event_attributes[obj.type_name]
            for path, evt in obj.get_fields(paths, resolve=True).items():
                new_id = hierarchy.events.get(evt)
                if new_id is not None:
                    obj.set_field(path, new_id.result)

        if obj.type_name in _variable_attributes:
            paths = _variable_attributes[obj.type_name]
            for path, var in obj.get_fields(paths, resolve=True).items():
                var = obj.get_field(path, resolve=True)
                new_id = hierarchy.variables.get(var)
                if new_id is not None:
                    obj.set_field(path, new_id.result)

        if obj.type_name in _animation_attributes:
            paths = _animation_attributes[obj.type_name]
            for path, anim in obj.get_fields(paths, resolve=True).items():
                anim = obj.get_field(path, resolve=True)
                new_id = hierarchy.animations.get(anim)
                if new_id is not None:
                    obj.set_field(path, new_id.result)

        # hkbStateMachine::TransitionInfoArray
        # - transitions:*/toStateId
        # - transitions:*/fromNestedStateId
        # - transitions:*/toNestedStateId
        if obj.type_name == "hkbStateMachine::TransitionInfoArray":
            # TODO should verify this object belongs to a StateInfo with state ID conflicts
            transition_ptr: HkbPointer

            for transition_ptr in obj["transitions"]:
                transition = transition_ptr.get_target()

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
                    

def resolve_merge_dialog(
    behavior: HavokBehavior,
    xml: ET.Element,
    target_pointer: HkbPointer,
    hierarchy: MergeHierarchy,
    *,
    tag: str = None,
) -> None:
    def resolve():
        resolve_conflicts(behavior, target_pointer, hierarchy)
        # TODO callback

    def close():
        dpg.delete_item(dialog)

    # Window content
    with dpg.window(
        width=600,
        height=400,
        label="Merge Hierarchy",
        modal=False,
        on_close=close,
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        with dpg.group(horizontal=True):
            graph_data = xml.find("objects").get("graph")
            if graph_data:
                graph = nx.from_edgelist(graph_data, nx.DiGraph)
                # TODO frontpage, highlight conflict on node select, color nodes if they have conflicts
                gw = GraphWidget(graph, on_node_selected=None, width=400, height=400)

            with dpg.group():
                if hierarchy.events:
                    with dpg.tree_node(label="Unresolved Events", default_open=True):
                        with dpg.table(header_row=False):
                            dpg.add_table_column(label="Event")
                            dpg.add_table_column(label="Remap")

                            for _, name in hierarchy.events.keys():
                                with dpg.table_row():
                                    dpg.add_checkbox(label=name, default_value=True)
                                    dpg.add_combo(
                                        ["Create", "Remap"], callback=None
                                    )  # TODO cb

                # TODO variables
                # TODO animations

                if hierarchy.objects:
                    with dpg.tree_node(label="Conflicting Objects", default_open=True):
                        with dpg.table(header_row=False):
                            dpg.add_table_column(label="Object")
                            dpg.add_table_column(label="Type")
                            dpg.add_table_column(label="Action")

                            for oid, xmlobj in hierarchy.objects:
                                with dpg.table_row():
                                    typeid = xmlobj.get("typeid")
                                    type_name = behavior.type_registry.get_name(typeid)

                                    dpg.add_text(oid)
                                    dpg.add_text(type_name)

                                    dpg.add_combo(["New ID", "Reuse Existing", "Skip"])

        dpg.add_separator()

        # TODO help text

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=resolve)
            dpg.add_button(label="Cancel", callback=close)
