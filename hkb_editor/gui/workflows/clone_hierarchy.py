from typing import Any, Callable, Type
import logging
from dataclasses import dataclass, field
from copy import deepcopy
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb import HkbPointer, HkbRecord
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui import style
from hkb_editor.gui.graph_widget import GraphWidget
from hkb_editor.gui.workflows.undo import UndoManager


_event_attributes = {
    "hkbManualSelectorGenerator": [
        "endOfClipEventId",
    ],
    "hkbStateMachine::TransitionInfoArray": ["transitions:*/eventId"],
}

_variable_attributes = {
    "hkbVariableBindingSet": [
        "bindings:*/variableIndex",
    ]
}

_animation_attributes = {
    "hkbClipGenerator": [
        "animationInternalId",
    ]
}


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

        # TODO handle paths with * placeholders
        if obj.type_name in _event_attributes:
            for path in _event_attributes[obj.type_name]:
                event_idx = obj.get_field(path, resolve=True)
                if event_idx >= 0:
                    event_name = behavior.get_event(event_idx)
                    events[event_idx] = event_name

        if obj.type_name in _variable_attributes:
            for path in _variable_attributes[obj.type_name]:
                variable_idx = obj.get_field(path, resolve=True)
                if variable_idx >= 0:
                    variable = behavior.get_variable(variable_idx)
                    variables[variable_idx] = variable

        if obj.type_name in _animation_attributes:
            for path in _animation_attributes[obj.type_name]:
                animation_idx = obj.get_field(path, resolve=True)
                if animation_idx >= 0:
                    animation_name = behavior.get_animation(animation_idx)
                    animations[animation_idx] = animation_name

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
        # TODO need to include ALL variable attributes
        ET.SubElement(xml_variables, "variable", idx=idx, name=var.name)

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

    conflicts = find_conflicts(behavior, xml)
    solution = resolve_merge_dialog(behavior, xml, target_pointer, conflicts, undo_manager)

    # TODO add objects


def find_conflicts(
    behavior: HavokBehavior, hierarchy: ET.Element
) -> HierarchyConflicts:
    conflicts = HierarchyConflicts()

    # For events, variables and animations we check if there is already one with a matching name.
    # If there is no match it probably has to be created. If it exists but the index is different
    # we still treat it as a conflict, albeit one that has a likely solution.
    for evt in hierarchy.findall(".//event"):
        idx = evt.get("idx")
        name = evt.get("name")
        match_idx = behavior.find_event(name, "<new>")
        if match_idx != idx:
            conflicts.events[(idx, name)] = match_idx

    for evt in hierarchy.findall(".//variable"):
        idx = evt.get("idx")
        name = evt.get("name")
        match_idx = behavior.find_variable(name, "<new>")
        if match_idx != idx:
            conflicts.variables[(idx, name)] = match_idx

    for evt in hierarchy.findall(".//animation"):
        idx = evt.get("idx")
        name = evt.get("name")
        match_idx = behavior.find_animation(name, "<new>")
        if match_idx != idx:
            conflicts.animations[(idx, name)] = match_idx

    # Find objects with IDs that already exist
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")

    for xmlobj in reversed(hierarchy.find("objects").getchildren()):
        obj = HkbRecord.from_object(behavior, xmlobj)

        # Find pointers in the behavior referencing this object's ID. If more than one
        # other object is already referencing it, it is most likely a reused object like
        # e.g. DefaultTransition.
        # FIXME since we're editing conflicting objects we need to add ALL objects here
        if obj.object_id in behavior.objects:
            references = list(behavior.find_referees(obj))
            default = "<reuse>" if len(references) > 1 else "<new>"
            conflicts.objects[obj] = default

        # Type-specific conflicts

        # hkbStateMachine::StateInfo
        #   - stateId
        if obj.type_name == "hkbStateMachine::StateInfo":
            # Check if the hierarchy contains a statemachine which references the StateInfo.
            # StateInfo IDs can only be in conflict if they are pasted into a new statemachine.
            hsm = hierarchy.xpath(
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
                    conflicts.state_ids[obj] = "<new>"
                    break

        # These will need some corrections, but will not result in additional conflicts
        # - hkbStateMachine
        # - hkbStateMachine::TransitionInfoArray
        # - hkbClipGenerator

    return conflicts


def resolve_conflicts(
    behavior: HavokBehavior,
    target_pointer: HkbPointer,
    conflicts: HierarchyConflicts,
    undo_manager: UndoManager,
):
    solution = ConflictSolution()
    common = CommonActionsMixin(behavior)

    with undo_manager.combine():
        # TODO add undo actions
        # Create missing events, variables and animations. If the value is not "<new>" we can
        # expect that a mapping to another value has been applied
        for (idx, evt), new_idx in conflicts.events.items():
            if new_idx == "<new>":
                new_idx = behavior.create_event(evt)
                solution.events[idx] = new_idx
            elif not isinstance(new_idx, int):
                raise ValueError(f"Invalid mapping for event {idx} ({evt}): {new_idx}")

        for (idx, var), new_idx in conflicts.variables.items():
            if new_idx == "<new>":
                new_idx = behavior.create_variable(var)
                solution.variables[idx] = new_idx
            elif not isinstance(new_idx, int):
                raise ValueError(
                    f"Invalid mapping for variable {idx} ({var}): {new_idx}"
                )

        for (idx, anim), new_idx in conflicts.animations.items():
            if new_idx == "<new>":
                new_idx = behavior.create_animation(anim)
                solution.animations[idx] = new_idx
            elif not isinstance(new_idx, int):
                raise ValueError(
                    f"Invalid mapping for animation {idx} ({anim}): {new_idx}"
                )

        # Handle conflicting objects
        for obj, action in conflicts.objects.items():
            if action == "<new>":
                solution.objects[obj.object_id] = obj
                obj.object_id = behavior.new_id()
            elif action == "<reuse>":
                shared_obj = behavior.objects[obj.object_id]
                solution.objects[obj.object_id] = shared_obj
            elif action == "<skip>":
                solution.objects[obj.object_id] = None
            else:
                raise ValueError(f"Invalid action for object {obj}: {action}")

        # StateInfo IDs
        # All conflicts found must be from "naked" StateInfos, e.g. they are copied
        # into a new statemachine
        sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
        target_record = behavior.find_object_for(target_pointer)
        target_sm = behavior.find_hierarchy_parent_for(target_record, sm_type)

        # In theory it's not possible to paste more than one StateInfo without its statemachine, 
        # but this certainly won't hurt. At the very least we can assume that there will only be 
        # one statemachine with conflicts.
        state_id_offset = 0

        for obj, action in conflicts.state_ids.items():
            old_state_id = obj["stateId"].get_value()
            new_state_id = common.get_next_state_id(target_sm)
            solution.state_ids[old_state_id] = new_state_id + state_id_offset
            state_id_offset += 1

        # Fix object attributes
        # TODO iterate over all objects as they may reference some of the conflicting ones
        for obj in conflicts.objects.keys():
            # Fix any pointers pointing to conflicting objects
            ptr: HkbPointer
            for ptr in obj.find_fields_by_type(HkbPointer):
                target_id = ptr.get_value()
                if target_id in solution.objects:
                    new_target = solution.objects[target_id]
                    ptr.set_value(new_target)

            # Type-specific fixes

            # hkbStateMachine::StateInfo
            #   - stateId
            if obj in conflicts.state_ids and obj.type_name == "hkbStateMachine::StateInfo":
                state_id = obj["stateId"].get_value()
                if state_id in solution.state_ids:
                    new_id = solution.state_ids[obj]
                    obj["stateId"].set_value(new_id)

            # hkbStateMachine::TransitionInfoArray
            #   - transitions:*/toStateId
            #   - transitions:*/fromNestedStateId
            #   - transitions:*/toNestedStateId
            elif obj.type_name == "hkbStateMachine::TransitionInfoArray":
                # TODO need to verify this object belongs to a StateInfo with state ID conflicts
                transition_ptr: HkbPointer

                for transition_ptr in obj["transitions"]:
                    transition = transition_ptr.get_target()

                    for attr in ["toStateId", "fromNestedStateId", "toNestedStateId"]:
                        attr_id = transition[attr].get_value()
                        new_id = conflicts.state_ids.get(attr_id)
                        if new_id is not None:
                            transition[attr].set_value(new_id)

            # - hkbStateMachine
            #   - eventToSendWhenStateOrTransitionChanges/id (?)
            #   - startStateId
            elif obj.type_name == "hkbStateMachine":
                transition_change_event = obj.get_field(
                    "eventToSendWhenStateOrTransitionChanges/id", resolve=True
                )
                start_state_id = obj["startStateId"].get_value()

                if transition_change_event >= 0:
                    new_event = conflicts.events.get(transition_change_event)
                    if new_event is not None:
                        obj.set_field(
                            "eventToSendWhenStateOrTransitionChanges/id", new_event
                        )

                if start_state_id >= 0:
                    new_id = conflicts.state_ids.get(start_state_id)
                    if new_id is not None:
                        obj["startStateId"].set_value(new_id)

            # - hkbClipGenerator
            #   - animationInternalId
            elif obj.type_name == "hkbClipGenerator":
                anim_idx = obj["animationInternalId"].get_value()
                new_idx = conflicts.animations.get(anim_idx)

                if new_idx is not None:
                    obj["animationInternalId"].set_value(new_idx)
                    # While the index into the animations array may have changed, we can assume
                    # that the animation name has not, so animationName and the clip's name don't
                    # need to be changed. The same is true for the CMSG owning this clip.


def resolve_merge_dialog(
    behavior: HavokBehavior,
    xml: ET.Element,
    target_pointer: HkbPointer,
    conflicts: HierarchyConflicts,
    undo_manager: UndoManager,
    *,
    tag: str = None,
) -> None:
    def resolve():
        resolve_conflicts(behavior, target_pointer, conflicts, undo_manager)
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
                if conflicts.events:
                    with dpg.tree_node(label="Unresolved Events", default_open=True):
                        with dpg.table(header_row=False):
                            dpg.add_table_column(label="Event")
                            dpg.add_table_column(label="Remap")

                            for _, name in conflicts.events.keys():
                                with dpg.table_row():
                                    dpg.add_checkbox(label=name, default_value=True)
                                    dpg.add_combo(
                                        ["Create", "Remap"], callback=None
                                    )  # TODO cb

                # TODO variables
                # TODO animations

                if conflicts.objects:
                    with dpg.tree_node(label="Conflicting Objects", default_open=True):
                        with dpg.table(header_row=False):
                            dpg.add_table_column(label="Object")
                            dpg.add_table_column(label="Type")
                            dpg.add_table_column(label="Action")

                            for oid, xmlobj in conflicts.objects:
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
