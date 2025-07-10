from typing import Any
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import Tagfile, HavokBehavior, HkbRecord, HkbPointer, HkbArray


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


def get_next_state_id(statemachine: HkbRecord) -> int:
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
) -> HkbRecord:
    binding_set_ptr: HkbPointer = hkb_object["variableBindingSet"]

    with undo_manager.combine():
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
            undo_manager.on_create_object(binding_set)
            
            binding_set_ptr.set_value(binding_set.object_id)
            undo_manager.on_update_value(binding_set_ptr, None, binding_set.object_id)
        else:
            binding_set = binding_set_ptr.get_target()

        if isinstance(variable, str):
            variable = behavior.find_variable(variable)

        bindings: HkbArray = binding_set["bindings"]
        for bind in bindings:
            if bind["memberPath"] == path:
                # Binding for this path already exists, update it
                bound_var_idx = bind["variableIndex"]
                old_value = bound_var_idx.get_value()
                bound_var_idx.set_value(variable)
                undo_manager.on_update_value(bound_var_idx, old_value, variable)
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
            undo_manager.on_update_array_item(bindings, -1, None, bind)

    return binding_set
