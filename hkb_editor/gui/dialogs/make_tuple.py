from typing import Any, Callable, Type
from dearpygui import dearpygui as dpg

from hkb_editor.gui.helpers import create_value_widget


def new_tuple_dialog(
    columns: dict[str, Type],
    callback: Callable[[str, tuple, Any], None],
    *,
    choices: dict[int, list[str]] = None,
    title: str = "New Item",
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    new_val = [t() for t in columns.values()]

    def assemble(sender: str, new_value: Any, val_idx: int):
        if choices and val_idx in choices:
            choice_values = choices[val_idx]
            new_value = choice_values.index(new_value)

        new_val[val_idx] = new_value

    def create_entry():
        callback(dialog, new_val, user_data)
        dpg.delete_item(dialog)

    with dpg.window(
        modal=True,
        min_size=(100, 30),
        autosize=True,
        label=title,
        no_saved_settings=True,
        on_close=lambda: dpg.delete_item(dialog),
        tag=tag,
    ) as dialog:
        for idx, (col, subval) in enumerate(zip(columns.keys(), new_val)):
            create_value_widget(
                idx,
                subval,
                callback=assemble,
                label=col,
                choices=choices,
                tag=f"{tag}_widget_{idx}",
            )

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=create_entry)
            dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dialog))

    dpg.focus_item(f"{tag}_widget_0")
    return tag
