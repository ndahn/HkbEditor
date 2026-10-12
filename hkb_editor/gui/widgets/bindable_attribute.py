from typing import Any, Generator, Callable
from contextlib import contextmanager
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui import style


@contextmanager
def bindable_attribute(
    filter_key: str = "",
    tag: str = 0,
    **kwargs,
) -> Generator[str, None, None]:
    """Wrap an attribute widget so it can be swapped for a variable binding.

    Yields the tag the binder is referred to by. Widgets created inside the
    context land in the "unbound" group, which is hidden and replaced by the
    variable name once the attribute is bound.
    """
    if tag in (0, "", None):
        tag = f"bindable_attribute_{dpg.generate_uuid()}"

    with dpg.group(filter_key=filter_key, tag=tag, **kwargs):
        dpg.add_input_text(
            readonly=True,
            default_value="",
            tag=f"{tag}_bound",
            show=False,
        )
        dpg.bind_item_theme(dpg.last_item(), style.themes.bound_attribute)

        with dpg.group(tag=f"{tag}_unbound"):
            # We yield the tag this binder can be referred to by, but elements
            # will still be added to the "unbound" group
            yield tag


def set_bindable_attribute_state(
    behavior: HavokBehavior, bindable_attribute: str, bound_var_idx: int = -1
) -> None:
    """Show either the bound variable name or the attribute's own widgets."""
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
) -> None:
    """Open the variable picker and bind the chosen variable to ``path``.

    Clearing the selection removes the binding instead. ``on_bind`` receives
    ``[variable_index, binding_set]``, or None when the binding was cleared.
    """
    # Imported here to break the widgets <-> dialogs cycle
    from hkb_editor.gui.dialogs.find_object_dialog import select_variable

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

    select_variable(behavior, on_variable_selected, user_data=user_data)
