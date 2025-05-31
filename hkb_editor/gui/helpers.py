from typing import Any, Callable
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.hkb_types import HkbRecord


def center_window(window: str, parent: str = None) -> None:
    if parent:
        dpos = dpg.get_item_pos(parent)
        dsize = dpg.get_item_rect_size(parent)
    else:
        dpos = dpg.get_viewport_pos()
        dsize = (dpg.get_viewport_width(), dpg.get_viewport_height())
    
    psize = dpg.get_item_rect_size(window)

    dpg.set_item_pos(
        window,
        (
            dpos[0] + (dsize[0] - psize[0]) / 2,
            dpos[1] + (dsize[1] - psize[1]) / 2,
        ),
    )


def create_value_widget(
    val_idx: int,
    val: Any,
    *,
    choices: dict[int, str] = None,
    callback: Callable[[str, Any, Any], None] = None,
    user_data: Any = None,
    on_enter: bool = False,
    **kwargs,
):
    if user_data is None:
        user_data = val_idx

    if choices and val_idx in choices:
        items = choices[val_idx]
        dpg.add_combo(
            items,
            callback=callback,
            user_data=user_data,
            default_value=items[val if val is not None else 0],
            **kwargs,
        )
    elif val is None or isinstance(val, str):
        dpg.add_input_text(
            callback=callback,
            user_data=user_data,
            default_value=val or "",
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, int):
        dpg.add_input_int(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, float):
        dpg.add_input_float(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, bool):
        dpg.add_checkbox(
            callback=callback,
            user_data=user_data,
            default_value=val,
            **kwargs,
        )
    else:
        print(f"WARNING cannot handle value {val} with unknown type")


def make_copy_menu(getter: HkbRecord | Callable[[], HkbRecord]) -> None:
    if isinstance(getter, HkbRecord):
        getter = lambda: getter()

    with dpg.menu(label="Copy"):
        dpg.add_selectable(
            label="ID",
            callback=lambda: pyperclip.copy(getter().object_id),
        )
        dpg.add_selectable(
            label="Name",
            callback=lambda: pyperclip.copy(
                getter().get_field("name", "", resolve=True)
            ),
        )
        dpg.add_selectable(
            label="Type Name",
            callback=lambda: pyperclip.copy(getter().type_name),
        )
        dpg.add_selectable(
            label="Type ID",
            callback=lambda: pyperclip.copy(getter().type_id),
        )
        dpg.add_selectable(
            label="XML",
            callback=lambda: pyperclip.copy(getter().xml()),
        )
