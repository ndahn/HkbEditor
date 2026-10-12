from __future__ import annotations
from typing import Callable, Generic, TypeVar
import logging
from dataclasses import dataclass, field
import re
from ast import literal_eval
from copy import deepcopy
from enum import Enum
from lxml import etree as ET
import networkx as nx

from hkb_editor.hkb.xml import (
    xml_from_str,
    add_type_comments,
    make_subelement,
)
from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)
from hkb_editor.hkb import HkbPointer, HkbRecord, HkbArray, XmlValueHandler
from hkb_editor.hkb.type_registry import TypeMismatch


T = TypeVar("T")

# Called as resolver(behavior, xml, results, target_record, on_complete) to let
# the user pick a MergeAction per conflict. It owns the call to
# resolve_conflicts and must invoke on_complete afterwards. Passing None
# resolves everything automatically, which is what headless callers want.
ConflictResolver = Callable[
    ["HavokBehavior", ET._Element, "MergeResult", "HkbRecord", Callable[[], None]],
    None,
]


class MergeAction(Enum):
    NEW = 0
    REUSE = 1
    IGNORE = 2
    SKIP = 3


@dataclass
class Resolution(Generic[T]):
    original: T = None
    action: MergeAction = MergeAction.NEW
    result: T = None


@dataclass
class MergeResult:
    root_id: str = None
    root_meta: ET._Element = None
    events: dict[int, Resolution[tuple[int, str]]] = field(default_factory=dict)
    variables: dict[int, Resolution[tuple[int, str]]] = field(default_factory=dict)
    animations: dict[int, Resolution[tuple[int, str]]] = field(default_factory=dict)
    type_map: dict[str, Resolution[tuple[str, str]]] = field(default_factory=dict)
    objects: dict[str, Resolution[HkbRecord]] = field(default_factory=dict)
    pin_objects: bool = True


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


def _collect_referenced_indices(
    obj: HkbRecord,
    attr_map: dict[str, list[str]],
    lookup: Callable[[int, str], object],
    sink: dict[int, object],
) -> None:
    if obj.type_name not in attr_map:
        return

    # paths may contain * wildcards, get_fields already resolves those
    for idx in obj.get_fields(attr_map[obj.type_name], resolve=True).values():
        if idx >= 0:
            sink[idx] = lookup(idx, None) or ""


def copy_hierarchy(start_obj: HkbRecord) -> str:
    behavior = start_obj.tagfile
    start_id = start_obj.object_id

    hierarchy_graph = behavior.build_graph(start_id)

    root_meta: dict[str, list] = {}
    events: dict[int, str] = {}
    variables: dict[int, HkbVariable] = {}
    animations: dict[int, str] = {}
    objects: list[HkbRecord] = []
    type_map: dict[str, str] = {}

    for oid in nx.topological_sort(hierarchy_graph):
        obj = behavior.objects.get(oid)
        if not obj:
            continue

        _collect_referenced_indices(obj, event_attributes, behavior.get_event, events)
        _collect_referenced_indices(obj, variable_attributes, behavior.get_variable, variables)
        _collect_referenced_indices(obj, animation_attributes, behavior.get_animation, animations)

        objects.append(obj)
        type_map[obj.type_id] = obj.type_name

        # element types of arrays need remapping too; pointers don't store their
        # subtype in the xml so they're fine as-is
        array: HkbArray
        for _, array in obj.find_fields_by_class(HkbArray):
            type_map[array.element_type_id] = array.element_type_name

    # the root object might need additional data to be merged correctly
    if start_obj.type_name == "hkbStateMachine::StateInfo":
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
                        type_map[transition_effect.type_id] = transition_effect.type_name

                trans_event_idx = transition["eventId"].get_value()
                events[trans_event_idx] = behavior.get_event(trans_event_idx, None)

                # no break: a state could in theory have more than one wildcard transition

    xml_root = xml_from_str(b"<behavior_hierarchy/>")
    xml_root_meta = make_subelement(xml_root, "root_meta", root_id=start_id)
    xml_events = make_subelement(xml_root, "events")
    xml_variables = make_subelement(xml_root, "variables")
    xml_animations = make_subelement(xml_root, "animations")
    xml_types = make_subelement(xml_root, "types")
    xml_objects = make_subelement(xml_root, "objects", graph=str(nx.to_edgelist(hierarchy_graph)))

    # unique paths to reach the object, needed when importing a subtree
    for root_path in behavior.get_unique_object_paths(start_id):
        make_subelement(xml_root_meta, "path").text = str(root_path)

    for key, items in root_meta.items():
        meta_group = make_subelement(xml_root_meta, key)
        for item in items:
            if isinstance(item, XmlValueHandler):
                meta_group.append(deepcopy(item.element))
            else:
                make_subelement(meta_group, "item", value=str(item))

    for idx, evt in events.items():
        make_subelement(xml_events, "event", idx=str(idx), name=evt)

    for idx, var in variables.items():
        if var:
            make_subelement(
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
            make_subelement(xml_variables, "variable", idx=str(idx), name="")

    for idx, anim in animations.items():
        make_subelement(xml_animations, "animation", idx=str(idx), name=anim)

    for type_id, type_name in type_map.items():
        make_subelement(xml_types, "type", id=type_id, name=type_name)

    for obj in objects:
        # be careful not to remove the object elements from their original xml doc
        xml_objects.append(deepcopy(obj.as_object()))

    add_type_comments(xml_root, behavior)
    ET.indent(xml_root)
    ret = ET.tostring(xml_root, pretty_print=True, encoding="unicode")
    logging.getLogger().info(f"Serialized {len(objects)} objects")

    return ret


# ---------------------------------------------------------------------------
# import / paste entry points
# ---------------------------------------------------------------------------


def _parse_hierarchy_xml(
    xml: str | ET._Element, error_prefix: str = "Failed to parse hierarchy"
) -> ET._Element:
    if isinstance(xml, str):
        try:
            xmldoc = xml_from_str(xml)
        except Exception as e:
            raise ValueError(f"{error_prefix}: {e}") from e
    else:
        xmldoc = xml

    if xmldoc.tag != "behavior_hierarchy":
        raise ValueError("Not a valid behavior hierarchy")

    return xmldoc


def _apply_merge(
    behavior: HavokBehavior,
    xmldoc: ET._Element,
    results: MergeResult,
    target_record: HkbRecord,
    on_complete: Callable[[], None],
    conflict_resolver: ConflictResolver,
) -> None:
    if conflict_resolver:
        # Hands over to e.g. merge_hierarchy_dialog, which calls
        # resolve_conflicts itself once the user has picked the actions
        conflict_resolver(behavior, xmldoc, results, target_record, on_complete)
    else:
        with behavior.transaction():
            resolve_conflicts(behavior, target_record, results)
            results.pin_objects = True
            on_complete()


def import_hierarchy(
    behavior: HavokBehavior,
    xml: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    conflict_resolver: ConflictResolver = None,
):
    try:
        xmldoc = xml_from_str(xml)
    except Exception as e:
        raise ValueError(f"Failed to parse hierarchy: {e}") from e

    logger = logging.getLogger()

    def resolve_root_path(root_path: list[str]):
        try:
            target_obj = behavior.resolve_unique_object_path(root_path[:-1])
        except Exception as e:
            logger.error(f"Failed to resolve root path {root_path}", exc_info=e)
            return None

        # if the path ends inside a pointer array, append a new slot instead
        target_path = root_path[-1]
        if re.match(r"^.*:[0-9]+$", target_path):
            target_path = target_path.rsplit(":", maxsplit=1)[0] + ":-1"

        return target_obj, target_path

    def update_target_pointers(results: MergeResult):
        hierarchy_root = results.objects[results.root_id]
        if not hierarchy_root.result or hierarchy_root.action != MergeAction.NEW:
            return

        target_id = hierarchy_root.result.object_id

        # the first target is already set by paste_hierarchy
        for target_obj, target_path in targets[1:]:
            try:
                if target_path.endswith(":-1"):
                    array: HkbArray = target_obj.get_field(target_path[:-3])
                    ptr = array.append(None)
                else:
                    ptr = target_obj.get_field(target_path)

                if not isinstance(ptr, HkbPointer):
                    logger.error(
                        f"Target path {target_obj.object_id}/{target_path} did not yield a pointer (is {str(ptr)})"
                    )
                    continue

                ptr.set_value(target_id)
            except ValueError as e:
                logger.warning(f"Pointer update failed: {e}")

        if callback:
            callback(results)

    with behavior.transaction():
        # the target object may be attached in more than one place
        targets: list[tuple[HkbRecord, str]] = []

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
            conflict_resolver=conflict_resolver,
        )


def paste_hierarchy(
    behavior: HavokBehavior,
    xml: str | ET._Element,
    target_record: HkbRecord,
    target_path: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    conflict_resolver: ConflictResolver = None,
) -> MergeResult:
    xmldoc = _parse_hierarchy_xml(xml)

    root_id = xmldoc.find("root_meta").get("root_id")
    root_type = xmldoc.xpath(f".//object[@id='{root_id}']")[0].get("typeid")
    root_type_name = xmldoc.xpath(f".//type[@id='{root_type}']")[0].get("name")

    # the target pointer must accept the hierarchy root's type
    if target_path.endswith(":-1"):
        target_path = target_path[:-3]

    target_field = target_record.get_field(target_path)
    if isinstance(target_field, HkbArray):
        target_pointer = target_field.append(None)
        target_path += f":{len(target_field) - 1}"
    else:
        target_pointer = target_field

    if not isinstance(target_pointer, HkbPointer):
        raise ValueError(
            f"Target {target_record.object_id}/{target_path} is not a pointer (is {target_pointer})"
        )

    try:
        mapped_root_type = behavior.type_registry.find_first_type_by_name(root_type_name)
        if not target_pointer.will_accept(mapped_root_type):
            raise ValueError(
                f"Hierarchy is not compatible with target pointer: expected {target_pointer.subtype_name}, but got {mapped_root_type} ({root_type_name})"
            )
    except StopIteration:
        raise ValueError(f"Could not map object type {root_type} ({root_type_name}) to a known type ID")

    results = find_conflicts(behavior, xmldoc, target_record)

    def add_objects():
        new_root: HkbRecord = results.objects[results.root_id].result
        if new_root:
            # events, variables etc. are already created, just add the objects
            for res in results.objects.values():
                obj: HkbRecord = res.result
                if obj and res.action == MergeAction.NEW:
                    behavior.add_object(obj)

            target_record.get_field(target_path).set_value(new_root)

        if target_record.type_name == "hkbStateMachine":
            fix_state_ids(target_record)

        if callback:
            callback(results)

    _apply_merge(behavior, xmldoc, results, target_record, add_objects, conflict_resolver)


def paste_children(
    behavior: HavokBehavior,
    xml: str | ET._Element,
    target_record: HkbRecord,
    target_path: str,
    callback: Callable[[MergeResult], None] = None,
    *,
    conflict_resolver: ConflictResolver = None,
) -> MergeResult:
    logger = logging.getLogger()
    xmldoc = _parse_hierarchy_xml(xml, "Clipboard data is not a valid hierarchy")

    results = find_conflicts(behavior, xmldoc, target_record)
    results.objects[results.root_id].action = MergeAction.IGNORE

    def add_children():
        nonlocal target_path

        root_id = results.root_id
        results.objects[root_id].action = MergeAction.SKIP

        source_obj: HkbRecord = results.objects[root_id].original
        root_children = {
            ptr.get_value()
            for _, ptr in source_obj.find_fields_by_class(HkbPointer)
            if ptr.is_set()
        }

        target_array = target_record.get_field(target_path)
        if isinstance(target_array, HkbPointer):
            target_path = target_path.rsplit(":", maxsplit=1)[0]
            target_array = target_record.get_field(target_path)

        if not isinstance(target_array, HkbArray):
            raise ValueError(
                f"Cloning children failed because the target is not a HkbArray (is {target_array})"
            )

        refptr = HkbPointer.new(behavior, target_array.element_type_id)

        for res in results.objects.values():
            obj: HkbRecord = res.result
            if not obj or res.action != MergeAction.NEW:
                continue

            if obj.object_id not in root_children:
                behavior.add_object(obj)
                continue

            if refptr.will_accept(obj):
                behavior.add_object(obj)
                target_array.append(obj.object_id)
            else:
                res.action = MergeAction.SKIP
                logger.warning(f"Skipping incompatible hierarchy child {obj}")

        # only copying the root's children means we also need its wildcard transitions
        if source_obj.type_name == "hkbStateMachine":
            logger.info("Fixing state IDs and wildcard transitions")
            transfer_wildcard_transitions(behavior, results, source_obj, target_record)
            fix_state_ids(target_record)

        if callback:
            callback(results)

    _apply_merge(behavior, xmldoc, results, target_record, add_children, conflict_resolver)


# ---------------------------------------------------------------------------
# conflict detection
# ---------------------------------------------------------------------------


def _parse_variable(elem: ET._Element, name: str) -> HkbVariable:
    default = elem.get("default")
    try:
        default = literal_eval(default)
    except ValueError:
        pass  # plain string default

    return HkbVariable(name, VariableType[elem.get("vtype")], elem.get("min"), elem.get("max"), default)


def _resolve_named_index(
    elem: ET._Element,
    find_fn: Callable[[str, int], int],
    make_value: Callable[[ET._Element, str], object],
) -> tuple[int, Resolution]:
    idx = int(elem.get("idx"))
    name = elem.get("name")

    if not name:
        return idx, Resolution((idx, name), MergeAction.SKIP, (-1, None))

    value = make_value(elem, name)
    match_idx = find_fn(name, -1)
    action = MergeAction.NEW if match_idx < 0 else MergeAction.REUSE

    return idx, Resolution((idx, value), action, (match_idx, value))


def _find_index_attribute_conflicts(behavior: HavokBehavior, xml: ET._Element, results: MergeResult) -> None:
    # for events, variables and animations we look for an existing match by name;
    # no match means it likely has to be created, a name/index mismatch still
    # counts as a conflict, albeit one with an obvious resolution
    for evt in xml.findall(".//event"):
        idx, res = _resolve_named_index(evt, behavior.find_event, lambda _, name: name)
        results.events[idx] = res

    for var in xml.findall(".//variable"):
        idx, res = _resolve_named_index(var, behavior.find_variable, _parse_variable)
        results.variables[idx] = res

    for anim in xml.findall(".//animation"):
        idx, res = _resolve_named_index(anim, behavior.find_animation, lambda _, name: name)
        results.animations[idx] = res


def _find_type_conflicts(behavior: HavokBehavior, xml: ET._Element, results: MergeResult) -> None:
    logger = logging.getLogger()

    # every type should have a matching type by name, even if the type ids disagree
    for type_info in xml.findall(".//type"):
        tid = type_info.get("id")
        name = type_info.get("name")

        try:
            new_id = behavior.type_registry.find_first_type_by_name(name)
        except StopIteration:
            raise ValueError(f"Could not resolve type {tid} ({name})")

        if new_id != tid:
            logger.debug(f"Remapping object type {tid} ({name}) to {new_id}")

        results.type_map[tid] = Resolution((tid, name), MergeAction.REUSE, (new_id, name))


def _find_object_conflicts(behavior: HavokBehavior, xml: ET._Element, results: MergeResult) -> None:
    logger = logging.getLogger()
    mismatching_types = set()

    for xmlobj in xml.find("objects").getchildren():
        # remap the typeid, relevant when cloning between games/hklib versions
        old_type_id = xmlobj.get("typeid")
        new_type_id = results.type_map[old_type_id].result[0]
        xmlobj.set("typeid", new_type_id)
        obj = tmp = None

        try:
            # construct via HkbRecord.new so any fields missing from the xml
            # still get their default initializers
            obj = HkbRecord.new(behavior, new_type_id, object_id=xmlobj.get("id"))
            tmp = HkbRecord.from_object(behavior, xmlobj)

            # fix up array element type ids; pointers don't need this since they
            # don't store their subtype in the xml
            array: HkbArray
            for path, _ in obj.find_fields_by_class(HkbArray):
                array = tmp.get_field(path, None)
                if array:
                    array.element_type_id = results.type_map[array.element_type_id].result[0]

            obj.set_value(tmp)
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
            raise ValueError(f"Failed to reconstruct object {xmlobj.get('id')} from xml") from e

        # if multiple objects already reference this id, it's likely a reused
        # object such as DefaultTransition
        existing_obj = behavior.objects.get(obj.object_id)
        if (
            existing_obj
            and existing_obj.type_name == obj.type_name
            and obj.type_name in ("CustomTransitionEffect", "hkbBlendingTransitionEffect")
        ):
            results.objects[obj.object_id] = Resolution(obj, MergeAction.REUSE, existing_obj)
        else:
            results.objects[obj.object_id] = Resolution(obj, MergeAction.NEW, obj)


def find_conflicts(behavior: HavokBehavior, xml: ET._Element, target_record: HkbRecord) -> MergeResult:
    results = MergeResult()
    results.root_meta = xml.find("root_meta")
    results.root_id = results.root_meta.get("root_id")

    _find_index_attribute_conflicts(behavior, xml, results)
    _find_type_conflicts(behavior, xml, results)
    _find_object_conflicts(behavior, xml, results)

    return results


# ---------------------------------------------------------------------------
# conflict resolution
# ---------------------------------------------------------------------------


def _resolve_index_resolutions(
    resolutions: dict[int, Resolution],
    create_fn: Callable[[object], int],
    find_fn: Callable[[object], int],
    label: str,
) -> None:
    for idx, resolution in resolutions.items():
        value = resolution.original[1]

        if resolution.action == MergeAction.NEW:
            resolution.result = (create_fn(value), value)
        elif resolution.action == MergeAction.REUSE:
            resolution.result = (find_fn(value), value)
        elif resolution.action == MergeAction.IGNORE:
            resolution.result = resolution.original
        elif resolution.action == MergeAction.SKIP:
            resolution.result = (-1, None)
        else:
            raise ValueError(f"Invalid action {resolution.action} for {label} {idx} ({resolution.original})")


def _is_object_included(results: MergeResult, object_id: str) -> bool:
    if object_id == results.root_id:
        return True

    # included if any non-skipped parent still points at it
    for other in results.objects.values():
        if not other.result or other.result.object_id == object_id:
            continue

        if other.action in (MergeAction.NEW, MergeAction.IGNORE):
            ptr: HkbPointer
            for _, ptr in other.result.find_fields_by_class(HkbPointer):
                if ptr.get_value() == object_id:
                    return True

    return False


def _remap_object_indices(obj: HkbRecord, attr_map: dict[str, list[str]], resolutions: dict[int, Resolution]) -> None:
    if obj.type_name not in attr_map:
        return

    for path, idx in obj.get_fields(attr_map[obj.type_name], resolve=True).items():
        res = resolutions.get(idx)
        if res is not None:
            obj.set_field(path, res.result[0])


def resolve_conflicts(behavior: HavokBehavior, target_record: HkbRecord, results: MergeResult) -> None:
    # TODO this should be optional
    # TODO define various conflict resolution strategies, like skip on conflict, reuse
    # on conflict, and whether to continue following a path if the parent had a conflict

    _resolve_index_resolutions(results.events, behavior.create_event, behavior.find_event, "event")
    _resolve_index_resolutions(
        results.variables,
        lambda var: behavior.create_variable(*var.astuple()),
        lambda var: behavior.find_variable(var.name),
        "variable",
    )
    _resolve_index_resolutions(results.animations, behavior.create_animation, behavior.find_animation, "animation")

    # decide the final id / fate of every object
    for object_id, resolution in results.objects.items():
        if resolution.action == MergeAction.NEW:
            resolution.result = resolution.original

            # if none of its parents are cloned either, drop it after all
            if not _is_object_included(results, object_id):
                resolution.action = MergeAction.SKIP
                logging.getLogger().info(f"Skipping object {object_id} as none of its parents are cloned")
                continue

            if object_id in behavior.objects:
                resolution.result.object_id = behavior.new_id()

        elif resolution.action == MergeAction.REUSE:
            resolution.result = behavior.objects[object_id]
        elif resolution.action == MergeAction.IGNORE:
            # give it a new id so nothing accidentally refers to the existing object
            resolution.result = resolution.original
            resolution.result.object_id = behavior.new_id()
        elif resolution.action == MergeAction.SKIP:
            resolution.result = None
        else:
            raise ValueError(f"Invalid action {resolution.action} for object {object_id}")

    # fix pointers referencing objects that got remapped or dropped
    for object_id, resolution in results.objects.items():
        obj: HkbRecord = resolution.result
        if not obj or resolution.action not in (MergeAction.NEW, MergeAction.IGNORE):
            continue

        ptr: HkbPointer
        for _, ptr in obj.find_fields_by_class(HkbPointer):
            target_id = ptr.get_value()
            if not target_id:
                continue

            if target_id not in results.objects:
                logging.getLogger().warning(
                    f"Object {object_id} references ID {target_id}, which is not part of the cloned hierarchy"
                )
                continue

            target_res = results.objects[target_id]
            if target_res.action in (MergeAction.NEW, MergeAction.REUSE):
                # skip verification here, the referenced id might already exist
                # but point at something else; objects are added later
                ptr.set_value(target_res.result.object_id, must_exist=False)
            else:
                ptr.set_value(None)

    # remap event/variable/animation indices inside the cloned objects themselves
    for resolution in results.objects.values():
        obj: HkbRecord = resolution.result
        if not obj or resolution.action in (MergeAction.REUSE, MergeAction.SKIP):
            continue

        _remap_object_indices(obj, event_attributes, results.events)
        _remap_object_indices(obj, variable_attributes, results.variables)
        _remap_object_indices(obj, animation_attributes, results.animations)

    restore_root_meta(behavior, target_record, results)


def restore_root_meta(behavior: HavokBehavior, target_record: HkbRecord, results: MergeResult) -> None:
    root_res = results.objects[results.root_id]

    # StateInfos may come with wildcard transitions that need to be transferred
    if root_res.action == MergeAction.NEW and root_res.result.type_name == "hkbStateMachine::StateInfo":
        if not target_record.type_name == "hkbStateMachine":
            raise ValueError(
                f"Expected target record to be of type hkbStateMachine, but got {target_record.type_name}"
            )

        wildcards: HkbArray[HkbRecord] = ensure_statemachine_wildcards(target_record)["transitions"]

        old_state_id = root_res.original["stateId"].get_value()
        new_state_id = root_res.result["stateId"].get_value()

        transition_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine::TransitionInfo")

        for transition_xml in results.root_meta.xpath(".//wildcard_transitions/record"):
            transition = HkbRecord.init_from_xml(behavior, transition_type, transition_xml)

            event = transition["eventId"].get_value()
            event_res = results.events.get(event)
            if event_res:
                if event_res.action in (MergeAction.IGNORE, MergeAction.SKIP):
                    continue  # event was not transferred, skip this transition
                transition["eventId"].set_value(event_res.result[0])

            state_id = transition["toStateId"].get_value()
            if state_id != old_state_id:
                continue  # transition is not for our root state info
            transition["toStateId"].set_value(new_state_id)

            effect = transition["transition"].get_value()
            if effect:
                effect_res = results.objects.get(effect)
                if effect_res:
                    if effect_res.action in (MergeAction.NEW, MergeAction.REUSE):
                        transition["transition"].set_value(effect_res.result.object_id)
                    elif effect_res.action in (MergeAction.IGNORE, MergeAction.SKIP):
                        transition["transition"].set_value(None)

            condition = transition["condition"].get_value()
            if condition:
                condition_res = results.objects.get(condition)
                if condition_res:
                    if condition_res.action in (MergeAction.NEW, MergeAction.REUSE):
                        transition["condition"].set_value(condition_res.result.object_id)
                    elif condition_res.action in (MergeAction.IGNORE, MergeAction.SKIP):
                        transition["transition"].set_value(None)

            wildcards.append(transition)


def ensure_statemachine_wildcards(statemachine: HkbRecord) -> HkbRecord:
    wildcards = statemachine["wildcardTransitions"].get_target()
    if wildcards is None:
        wildcards = HkbRecord.new(statemachine.tagfile, statemachine.get_field_type("wildcardTransitions"))
        statemachine.tagfile.add_object(wildcards)
        statemachine["wildcardTransitions"].set_value(wildcards)

    return wildcards


def transfer_wildcard_transitions(
    behavior: HavokBehavior,
    results: MergeResult,
    source_sm: HkbRecord,
    target_sm: HkbRecord,
):
    # transferred objects refer to new ids but may not have been added yet
    new_id_map = {res.result.object_id: res.original for res in results.objects.values() if res.result}

    transitions = {}
    source_wildcards_id = source_sm["wildcardTransitions"].get_value()
    source_wildcards = new_id_map.get(source_wildcards_id)
    if source_wildcards:
        for trans in source_wildcards["transitions"]:
            transitions[trans["toStateId"].get_value()] = trans

    target_wildcards = ensure_statemachine_wildcards(target_sm)
    target_wildcards_array: HkbArray = target_wildcards["transitions"]

    for ptr in source_sm["states"]:
        target_state = new_id_map.get(ptr.get_value())
        if not target_state:
            continue

        trans: HkbRecord = transitions.get(target_state["stateId"].get_value())
        if trans:
            new_trans = HkbRecord(behavior, deepcopy(trans.element), target_wildcards_array.element_type_id)
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
            # no clue how fromNestedStateId/toNestedStateId work, but they start at 0
            state_id = transition["toStateId"].get_value()
            if state_id < 0:
                continue

            if state_id in discovered:
                new_id = remapped_states.get(state_id)
                if new_id is not None:
                    transition["toStateId"].set_value(new_id)
            else:
                discovered.add(state_id)