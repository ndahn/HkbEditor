from typing import Any, Generator, Callable
from logging import getLogger
from contextlib import contextmanager
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.gui.dialogs import select_variable
from hkb_editor.gui import style
from hkb_editor.gui.workflows.undo import undo_manager


_logger = getLogger(__name__)


@contextmanager
def bindable_attribute(
    filter_key: str = "",
    tag: str = 0,
    **kwargs,
) -> Generator[str, None, None]:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    try:
        with dpg.group(filter_key=filter_key, tag=tag, **kwargs):
            dpg.add_input_text(
                readonly=True,
                default_value="",
                tag=f"{tag}_bound",
                show=False,
            )
            dpg.bind_item_theme(dpg.last_item(), style.bound_attribute_theme)

            with dpg.group(tag=f"{tag}_unbound") as g:
                # We yield the tag this binder can be referred to by, but elements will still be
                # added to the "unbound" group
                yield tag
    finally:
        pass


def set_bindable_attribute_state(
    behavior: HavokBehavior, bindable_attribute: str, bound_var_idx: int = -1
):
    if bound_var_idx >= 0:
        variable_name = behavior.get_variable_name(bound_var_idx)
        dpg.set_value(f"{bindable_attribute}_bound", f"@{variable_name}")
        dpg.show_item(f"{bindable_attribute}_bound")
        dpg.hide_item(f"{bindable_attribute}_unbound")
    else:
        dpg.hide_item(f"{bindable_attribute}_bound")
        dpg.show_item(f"{bindable_attribute}_unbound")


def select_variable_to_bind(
    behavior: HavokBehavior,
    record: HkbRecord,
    bindable_attribute: str,
    path: str,
    bound_var_idx: int = -1,
    on_bind: Callable[[str, tuple[int, str], Any], None] = None,
    user_data: Any = None,
):
    def on_variable_selected(sender, selected_idx: int, user_data: Any):
        with undo_manager.combine():
            binding_id = bind_attribute(
                behavior,
                record,
                bindable_attribute,
                path,
                selected_idx,
            )

            if on_bind:
                on_bind(sender, [selected_idx, binding_id], user_data)

    select_variable(
        behavior, on_variable_selected, user_data=user_data
    )


def get_variable_binding_set(behavior: HavokBehavior, record: HkbRecord) -> HkbRecord:
    if not isinstance(record, HkbRecord):
        return None

    try:
        # TODO we could create a specialized VariableBindingSet subclass
        binding_ptr: HkbPointer = record["variableBindingSet"]
        return behavior.objects[binding_ptr.get_value()]
    except (AttributeError, KeyError) as e:
        return None


def get_bound_attributes(behavior: HavokBehavior, record: HkbRecord) -> dict[str, int]:
    binding_set = get_variable_binding_set(behavior, record)
    if not binding_set:
        return {}

    ret = {}
    bnd: HkbRecord
    for bnd in binding_set["bindings"]:
        var_path = bnd["memberPath"].get_value()
        var_idx = bnd["variableIndex"].get_value()
        binding_type = bnd["bindingType"].get_value()
        if binding_type != 0:
            _logger.warning(
                "Unknown binding type %i (%s:%i)", binding_type, var_path, var_idx
            )
        else:
            ret[var_path] = var_idx

    return ret


def create_variable_binding_set(behavior: HavokBehavior, record: HkbRecord) -> str:
    ptr_type_id = record.get_field_type("variableBindingSet")
    bindings_type_id = behavior.type_registry.get_subtype(ptr_type_id)
    binding_id = behavior.new_id()
    binding_set = HkbRecord.new(behavior, bindings_type_id, None, binding_id)

    # Add the new binding set
    undo_manager.on_create_object(behavior, binding_set)
    behavior.add_object(binding_set)

    # Assign pointer to source record
    vbs = record["variableBindingSet"]
    undo_manager.on_update_value(vbs, vbs.get_value(), binding_id)
    vbs.set_value(binding_id)

    return binding_id


def bind_attribute(
    behavior: HavokBehavior,
    record: HkbRecord,
    bindable_attribute: str,
    path: str,
    variable_idx: int,
) -> str:
    binding_set = get_variable_binding_set(behavior, record)

    if binding_set is None:
        binding_id = create_variable_binding_set(behavior, record)
        binding_set = behavior.objects[binding_id]

    bindings: HkbArray = binding_set["bindings"]
    bnd: HkbRecord

    for bnd in bindings:
        if bnd["memberPath"] == path:
            val = bnd["variableIndex"]
            undo_manager.on_update_value(val, val.get_value(), variable_idx)
            val.set_value(variable_idx)
            break
    else:
        new_binding = HkbRecord.new(
            behavior,
            bindings.element_type_id,
            {
                "memberPath": path,
                "variableIndex": variable_idx,
                "bitIndex": -1,
                "bindingType": 0,
            },
        )
        undo_manager.on_update_array_item(bindings, -1, None, new_binding)
        bindings.append(new_binding)

    set_bindable_attribute_state(behavior, bindable_attribute, variable_idx)

    return binding_id


def unbind_attribute(
    behavior: HavokBehavior,
    record: HkbRecord,
    bindable_attribute: str,
    path: str,
) -> None:
    set_bindable_attribute_state(behavior, bindable_attribute, -1)

    binding_set = get_variable_binding_set(behavior, record)
    if binding_set is None:
        return

    bindings: HkbArray = binding_set["bindings"]
    bnd: HkbRecord

    for idx, bnd in enumerate(bindings):
        if bnd["memberPath"] == path:
            undo_manager.on_update_array_item(bindings, idx, bindings[idx], None)
            del bindings[idx]
            break
