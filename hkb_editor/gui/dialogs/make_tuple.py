from typing import Any, Callable, Type
from enum import Enum
from dearpygui import dearpygui as dpg

from hkb_editor.gui.helpers import create_simple_value_widget


def new_tuple_dialog(
    columns: dict[str, Type],
    callback: Callable[[str, tuple, Any], None],
    *,
    choices: dict[int, list[str | tuple[str, Any]]] = None,
    title: str = "New Item",
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    new_val = [None] * len(columns)
    for idx, t in enumerate(columns.values()):
        if issubclass(t, Enum):
            new_val[idx] = list(t)[0]
        else:
            new_val[idx] = t()

    def assemble(sender: str, new_value: Any, val_idx: int):
        if choices and val_idx in choices:
            for item in choices[val_idx]:
                if item == new_value:
                    break
                if isinstance(item, tuple) and item[0] == new_value:
                    new_value = item[1]
                    break

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
        for idx, (col, col_type) in enumerate(columns.items()):
            create_simple_value_widget(
                col_type,
                col,
                assemble,
                choices=choices.get(idx) if choices else None,
                default=new_val[idx],
                tag=f"{tag}_widget_{idx}",
                user_data=idx,
            )

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=create_entry)
            dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(dialog))

    dpg.focus_item(f"{tag}_widget_0")
    return tag
