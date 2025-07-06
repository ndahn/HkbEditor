from typing import Any, Callable, Type
from itertools import groupby
from enum import IntFlag
import logging
import textwrap
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.hkb_types import HkbRecord
from . import style


def center_window(window: str, parent: str = None) -> None:
    if parent:
        dpos = dpg.get_item_pos(parent)
        dsize = dpg.get_item_rect_size(parent)
    else:
        dpos = (0.0, 0.0)
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


def make_copy_menu(record_or_getter: HkbRecord | Callable[[], HkbRecord]) -> None:
    if isinstance(record_or_getter, HkbRecord):
        getter_func = lambda: record_or_getter
    else:
        getter_func = record_or_getter

    with dpg.menu(label="Copy"):
        dpg.add_selectable(
            label="ID",
            callback=lambda: pyperclip.copy(getter_func().object_id),
        )
        dpg.add_selectable(
            label="Name",
            callback=lambda: pyperclip.copy(
                getter_func().get_field("name", "", resolve=True)
            ),
        )
        dpg.add_selectable(
            label="Type Name",
            callback=lambda: pyperclip.copy(getter_func().type_name),
        )
        dpg.add_selectable(
            label="Type ID",
            callback=lambda: pyperclip.copy(getter_func().type_id),
        )
        dpg.add_selectable(
            label="XML",
            callback=lambda: pyperclip.copy(getter_func().xml()),
        )


def estimate_drawn_text_size(
    textlen: int,
    num_lines: int = 1,
    font_size: int = 10,
    scale: float = 1.0,
    margin: int = 5,
) -> tuple[int, int]:
    # 6.5 for 12, around 5.3 for 10?
    len_est_factor = -0.7 + 0.6 * font_size
    len_est = len_est_factor * textlen

    w = (len_est + margin * 2) * scale
    h = (font_size * num_lines + margin * 2) * scale
    return w, h


def create_flag_checkboxes(
    flag_type: Type[IntFlag],
    callback: Callable[[str, int, Any], None],
    *,
    base_tag: str = None,
    active_flags: int = 0,
    user_data: Any = None,
) -> str:
    if base_tag in (None, 0, ""):
        base_tag = dpg.generate_uuid()

    def on_flag_changed(sender: str, checked: bool, flag: IntFlag):
        nonlocal active_flags

        if checked:
            # Checking 0 will disable all other flags
            if flag == 0:
                active_flags = flag_type(0)
            else:
                active_flags |= flag
        else:
            # Prevent disabling 0
            if flag == 0:
                dpg.set_value(f"{base_tag}_0", True)
                return

            active_flags &= ~flag

        # Flags are not required to have a 0 mapping
        if dpg.does_item_exist(f"{base_tag}_0"):
            # 0 disables all other flags and enables 0
            if active_flags == 0:
                for flag in flag_type:
                    dpg.set_value(f"{base_tag}_{flag.value}", False)
                dpg.set_value(f"{base_tag}_0", True)
            # 0 is disabled by any other flag
            else:
                dpg.set_value(f"{base_tag}_0", False)

        if callback:
            callback(base_tag, active_flags, user_data)

    if not isinstance(active_flags, flag_type):
        try:
            active_flags = flag_type(active_flags)
        except ValueError:
            logger = logging.getLogger(__name__)
            logger.error(
                f"{active_flags} is not valid for flag type {flag_type.__name__}"
            )
            active_flags = 0

    for flag in flag_type:
        if flag == 0:
            # 0 is in every flag
            active = active_flags == 0
        else:
            active = flag in active_flags

        dpg.add_checkbox(
            default_value=active,
            callback=on_flag_changed,
            label=flag.name,
            tag=f"{base_tag}_{flag.value}",
            user_data=flag,
        )


def add_paragraphs(text: str, line_width: int = 70, paragraph_gap: int = 5, **textargs):
    with dpg.group():
        for has_chars, fragments in groupby(text.splitlines(), bool):
            if not has_chars:
                dpg.add_spacer(height=paragraph_gap)
                continue

            paragraph = " ".join(fragments)
            for line in textwrap.wrap(paragraph, width=line_width):
                dpg.add_text(line, **textargs)
