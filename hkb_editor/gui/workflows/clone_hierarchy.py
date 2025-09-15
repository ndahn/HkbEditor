from typing import Any, Callable
import logging
from dataclasses import dataclass, field
from ast import literal_eval
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb import HkbPointer, HkbRecord
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui import style
from hkb_editor.gui.workflows.undo import UndoManager
from hkb_editor.gui.helpers import common_loading_indicator


_event_attributes = {
    "hkbManualSelectorGenerator": [
        "endOfClipEventId",
    ],
    "hkbStateMachine": ["eventToSendWhenStateOrTransitionChanges/id"],
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
    type_map: dict[str, Resolution] = field(default_factory=dict)
    objects: dict[str, Resolution] = field(default_factory=dict)
    state_ids: dict[str, Resolution] = field(default_factory=dict)


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
        type_map[obj.type_id] = obj.type_name

        todo.extend(g.successors(oid))

    root = ET.Element("behavior_hierarchy")
    xml_events = ET.SubElement(root, "events")
    xml_variables = ET.SubElement(root, "variables")
    xml_animations = ET.SubElement(root, "animations")
    xml_types = ET.SubElement(root, "types")
    xml_objects = ET.SubElement(root, "objects", graph=str(nx.to_edgelist(g)))

    for idx, evt in events.items():
        ET.SubElement(xml_events, "event", idx=str(idx), name=evt)

    for idx, var in variables.items():
        # Need to include ALL variable attributes so we can reconsruct it if needed
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

    for idx, anim in animations.items():
        ET.SubElement(xml_animations, "animation", idx=str(idx), name=anim)

    for type_id, type_name in type_map.items():
        ET.SubElement(xml_types, "type", id=type_id, name=type_name)

    for obj in objects:
        xml_objects.append(obj.as_object())

    return ET.tostring(root, pretty_print=True, encoding="unicode")


def paste_hierarchy(
    behavior: HavokBehavior,
    target_pointer: HkbPointer,
    hierarchy: str,
    undo_manager: UndoManager,
    interactive: bool = True,
) -> MergeHierarchy:
    try:
        xml = ET.fromstring(hierarchy)
    except Exception as e:
        raise ValueError(f"Failed to parse hierarchy: {e}")

    if xml.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    root = xml.find("objects").getchildren()[0]
    root_id = root.get("id")
    root_type = root.get("typeid")

    if not target_pointer.will_accept(root_type):
        raise ValueError("Hierarchy is not compatible with target pointer")

    hierarchy = find_conflicts(behavior, xml)

    with undo_manager.combine():

        def add_objects():
            new_root: HkbRecord = hierarchy.objects[root_id].result

            if new_root:
                # Events, variables, etc. have already been created as needed,
                # just need to add the objects
                for res in hierarchy.objects.values():
                    obj: HkbRecord = res.result
                    if obj:
                        behavior.add_object(obj)

                target_pointer.set_value(new_root)

        if interactive:
            merge_hierarchy_dialog(
                behavior, xml, target_pointer, hierarchy, add_objects
            )
        else:
            resolve_conflicts(behavior, target_pointer, hierarchy)
            add_objects()

    return hierarchy


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
        hierarchy.events[idx] = Resolution((idx, name), action, (match_idx, name))

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
            hierarchy.variables[idx] = Resolution((idx, var), "<new>", (-1, var))
        else:
            hierarchy.variables[idx] = Resolution(
                (idx, var), "<reuse>", (match_idx, var)
            )

    for evt in xml.findall(".//animation"):
        idx = evt.get("idx")
        name = evt.get("name")

        match_idx = behavior.find_animation(name, -1)
        action = "<new>" if match_idx < 0 else "<reuse>"
        hierarchy.animations[idx] = Resolution((idx, name), action, (match_idx, name))

    # Even when the type IDs disagree, every type should have a corresponding match by name
    for type_info in xml.findall(".//type"):
        tid = type_info.get("id")
        name = type_info.get("name")

        try:
            new_id = behavior.type_registry.find_first_type_by_name(name)
        except StopIteration:
            raise ValueError(f"Could not resolve type {tid} ({name})")

        if new_id != tid:
            logging.getLogger().warning(
                f"Remapping object type {tid} ({name}) to {new_id}"
            )

        hierarchy.type_map[tid] = Resolution((tid, name), "<remap>", (new_id, name))

    # Find objects with IDs that already exist
    for xmlobj in reversed(xml.find("objects").getchildren()):
        # Remap the typeid. Should only be relevant when cloning between different games or
        # versions of hklib, but in those cases it might just make it work
        old_type_id = xmlobj.get("typeid")
        new_type_id = hierarchy.type_map[old_type_id].result[0]
        xmlobj.set("typeid", new_type_id)

        try:
            obj = HkbRecord.from_object(behavior, xmlobj)
            # Verify object has the expected fields
            behavior.type_registry.verify_object(obj)
        except ValueError as e:
            raise ValueError(
                f"Object {xmlobj.get('id')} with type_id {xmlobj.get('typeid')} does not match this behavior's type registry: {e}"
            )

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
            hsm: list = xml.xpath(
                f"/*/object[@type_id='{sm_type}' and .//pointer[@id='{obj.object_id}']]"
            )
            if hsm:
                continue

            obj_state_id = obj["stateId"].get_value()
            statemachine = next(
                behavior.find_hierarchy_parent_for(obj.object_id, sm_type)
            )
            state_ptr: HkbPointer

            for state_ptr in statemachine["states"]:
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

    # TODO add undo actions
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
        else:
            raise ValueError(
                f"Invalid action {resolution.action} for animation {idx} ({resolution.original[1]})"
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
            for path, evt_idx in obj.get_fields(paths, resolve=True).items():
                evt_res = hierarchy.events.get(evt_idx)
                if evt_res is not None:
                    obj.set_field(path, evt_res.result[0])

        if obj.type_name in _variable_attributes:
            paths = _variable_attributes[obj.type_name]
            for path, var_idx in obj.get_fields(paths, resolve=True).items():
                var_res = hierarchy.variables.get(var_idx)
                if var_res is not None:
                    obj.set_field(path, var_res.result[0])

        if obj.type_name in _animation_attributes:
            paths = _animation_attributes[obj.type_name]
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


def merge_hierarchy_dialog(
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
        try:
            loading = common_loading_indicator("Merging Hierarchy")
            resolve_conflicts(behavior, target_pointer, hierarchy)
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
        height=600 if graph_data else 500,
        label="Merge Hierarchy",
        modal=False,
        on_close=lambda: dpg.delete_item(dialog),
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
                            (node.id, style.blue),
                            (obj.type_name, style.white),
                        ]
                    except AttributeError:
                        return [
                            (node.id, style.blue),
                            (obj.type_name, style.white),
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
                        if obj.type_name in _event_attributes:
                            for path in _event_attributes[obj.type_name]:
                                for evt in obj.get_fields(path, resolve=True).values():
                                    highlight_row("event", evt, event_rows)

                        if obj.type_name in _variable_attributes:
                            for path in _variable_attributes[obj.type_name]:
                                for var in obj.get_fields(path, resolve=True).values():
                                    highlight_row("variable", var, variable_rows)

                        if obj.type_name in _animation_attributes:
                            for path in _animation_attributes[obj.type_name]:
                                for anim in obj.get_fields(path, resolve=True).values():
                                    highlight_row("animation", anim, animation_rows)

                        highlight_row("type", obj.type_id, type_rows)
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
                    #graph_preview.zoom_show_all() # TODO doesn't work

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
                        dpg.add_table_column(label="action", init_width_or_weight=100)

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
                                # TODO remove reuse if not reusable
                                dpg.add_combo(
                                    ["<new>", "<reuse>", "<keep>"],
                                    default_value=resolution.action,
                                    callback=update_action,
                                    user_data=resolution,
                                )

                            event_rows[row_tag] = idx

                dpg.add_spacer(height=10)

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
                        dpg.add_table_column(label="action", init_width_or_weight=100)

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
                                # TODO remove reuse if not reusable
                                dpg.add_combo(
                                    ["<new>", "<reuse>", "<keep>"],
                                    default_value=resolution.action,
                                    callback=update_action,
                                    user_data=resolution,
                                )

                            variable_rows[row_tag] = idx

                dpg.add_spacer(height=10)

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
                        dpg.add_table_column(label="action", init_width_or_weight=100)

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
                                # TODO remove reuse if not reusable
                                dpg.add_combo(
                                    ["<new>", "<reuse>", "<keep>"],
                                    default_value=resolution.action,
                                    callback=update_action,
                                    user_data=resolution,
                                )

                            animation_rows[row_tag] = idx

                dpg.add_spacer(height=10)

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
                        dpg.add_table_column(label="action", init_width_or_weight=100)

                        for idx, (key, resolution) in enumerate(
                            hierarchy.type_map.items()
                        ):
                            row_tag = f"{tag}_type_row_{key}"
                            with dpg.table_row(tag=row_tag):
                                dpg.add_text(str(resolution.original[0]))
                                dpg.add_text("->")
                                dpg.add_text(resolution.result[0])
                                dpg.add_text(f"({resolution.result[1]})")
                                # TODO remove reuse if not reusable
                                dpg.add_combo(
                                    ["<remap>"],
                                    default_value=resolution.action,
                                    callback=update_action,
                                    user_data=resolution,
                                )

                            type_rows[row_tag] = idx

                dpg.add_spacer(height=10)

                if hierarchy.objects:
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
                                reversed(hierarchy.objects.items())
                            ):
                                row_tag = f"{tag}_object_row_{oid}"
                                with dpg.table_row(tag=row_tag):
                                    name = resolution.original.get_field("name", "")

                                    dpg.add_text(oid)
                                    dpg.add_text(name)
                                    # TODO remove reuse if not reusable
                                    dpg.add_combo(
                                        ["<new>", "<reuse>", "<skip>"],
                                        default_value=resolution.action,
                                        callback=update_action,
                                        user_data=resolution,
                                    )

                                object_rows[row_tag] = idx

        dpg.add_separator()

        # TODO help text

        with dpg.group(horizontal=True):
            dpg.add_button(label="Apply", callback=resolve, tag=f"{tag}_button_okay")
            # Don't call close here, or it will be called again by the window's on_close!
            dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dialog), tag=f"{tag}_button_close")
