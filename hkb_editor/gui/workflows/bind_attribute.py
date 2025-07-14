from typing import Any, Generator, Callable
from logging import getLogger
from contextlib import contextmanager
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.templates.common import CommonActionsMixin
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
    on_bind: Callable[[str, tuple[int, str], Any], None] = None,
    user_data: Any = None,
):
    def on_variable_selected(sender, selected_idx: int, user_data: Any):
        util = CommonActionsMixin(behavior)

        if selected_idx is None:
            set_bindable_attribute_state(behavior, bindable_attribute, -1)
            util.clear_variable_binding(record, path)

            if on_bind:
                on_bind(sender, None, user_data)
        else:
            binding_set = util.bind_variable(record, path, selected_idx)
            set_bindable_attribute_state(behavior, bindable_attribute, selected_idx)

            if on_bind:
                on_bind(sender, [selected_idx, binding_set], user_data)

    select_variable(
        behavior, on_variable_selected, user_data=user_data
    )
