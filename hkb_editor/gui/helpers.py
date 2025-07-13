from typing import Any, Callable, Type, Literal
from enum import IntFlag
import logging
import textwrap
from dearpygui import dearpygui as dpg
import pyperclip
from natsort import natsorted

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
    label: str = "",
    tag: str = 0,
    **kwargs,
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if user_data is None:
        user_data = val_idx

    # TODO support for Literal, merge with function in apply_template
    if choices and val_idx in choices:
        items = choices[val_idx]
        dpg.add_combo(
            items,
            callback=callback,
            user_data=user_data,
            default_value=items[val if val is not None else 0],
            label=label,
            tag=tag,
            **kwargs,
        )
    elif val is None or isinstance(val, str):
        dpg.add_input_text(
            callback=callback,
            user_data=user_data,
            default_value=val or "",
            on_enter=on_enter,
            label=label,
            tag=tag,
            **kwargs,
        )
    elif isinstance(val, int):
        dpg.add_input_int(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            label=label,
            tag=tag,
            **kwargs,
        )
    elif isinstance(val, float):
        dpg.add_input_float(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            label=label,
            tag=tag,
            **kwargs,
        )
    elif isinstance(val, bool):
        dpg.add_checkbox(
            callback=callback,
            user_data=user_data,
            default_value=val,
            label=label,
            tag=tag,
            **kwargs,
        )
    else:
        logging.getLogger().warning(
            f"Cannot create widget for value {val} with unexpected type {type(val).__name__}"
        )
        return None

    return tag


def make_copy_menu(
    record_or_getter: HkbRecord | Callable[[], HkbRecord], *, tag: str = 0
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if isinstance(record_or_getter, HkbRecord):
        getter_func = lambda: record_or_getter
    else:
        getter_func = record_or_getter

    with dpg.menu(label="Copy", tag=tag):
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

    return tag


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

    zero_name = flag_type(0).name or "DISABLED"

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
                dpg.set_value(f"{base_tag}_{zero_name}", True)
                return

            active_flags &= ~flag

        # Flags are not required to have a 0 mapping
        if dpg.does_item_exist(f"{base_tag}_{zero_name}"):
            # 0 disables all other flags and enables 0
            if active_flags == 0:
                for flag in flag_type:
                    dpg.set_value(f"{base_tag}_{flag.name}", False)
                dpg.set_value(f"{base_tag}_{zero_name}", True)
            # 0 is disabled by any other flag
            else:
                dpg.set_value(f"{base_tag}_{zero_name}", False)

        if callback:
            callback(base_tag, active_flags, user_data)

    def set_from_int(sender: str, new_value: int, user_data: Any):
        new_flags = flag_type(new_value)
        for flag in flag_type:
            active = flag in new_flags
            if flag.value == 0 and new_flags > 0:
                active = False

            dpg.set_value(f"{base_tag}_{flag.name}", active)
            on_flag_changed(sender, active, flag)

    if not isinstance(active_flags, flag_type):
        try:
            active_flags = flag_type(active_flags)
        except ValueError:
            logger = logging.getLogger(__name__)
            logger.error(
                f"{active_flags} is not valid for flag type {flag_type.__name__}"
            )
            active_flags = 0

    with dpg.group():
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
                tag=f"{base_tag}_{flag.name}",
                user_data=flag,
            )

    with dpg.popup(dpg.last_container(), min_size=(50, 20)):
        dpg.add_input_int(
            label="from int",
            default_value=active_flags,
            on_enter=True,
            callback=set_from_int,
        )


def add_paragraphs(
    text: str,
    line_width: int = 70,
    *,
    margin: tuple[int, int] = (3, 3),
    line_gap: int = 5,
    paragraph_gap_factor: float = 0.8,
    **textargs,
) -> str:
    # Standard dpg font
    line_height = 13
    paragraph = ""
    y = margin[1]

    def place_line(line, **textargs):
        nonlocal y
        dpg.add_text(line, pos=(margin[0], y), **textargs)
        y += line_height + line_gap

    def place_paragraph(**textargs):
        nonlocal paragraph
        for frag in textwrap.wrap(paragraph, width=line_width):
            place_line(frag, **textargs)
        paragraph = ""

    with dpg.child_window(
        border=False, auto_resize_x=True, auto_resize_y=True
    ) as container:
        for line in text.splitlines():
            line = line.strip()

            if not line or line.startswith(("-", "*")):
                # Place all lines collected so far
                place_paragraph(**textargs)

                if not line:
                    # Paragraph gap
                    y += (line_height + line_gap) * paragraph_gap_factor

                elif line.startswith(("- ", "* ")):
                    # Bullet point
                    fragments = textwrap.wrap(
                        line,
                        # 2 bullet chars + 3 whitespaces
                        width=line_width - 5,
                        initial_indent="   ",
                        subsequent_indent="   ",
                    )
                    place_line(fragments[0][5:], bullet=True, **textargs)
                    for frag in fragments[1:]:
                        place_line(frag, **textargs)
            else:
                paragraph += line + " "

        # Place any remaining lines
        place_paragraph(**textargs)

    return container


def table_sort(sender: str, sort_specs: tuple[tuple[str, int]], user_data: Any):
    # See https://dearpygui.readthedocs.io/en/latest/documentation/tables.html#sorting
    # Sort_specs scenarios:
    #   1. no sorting -> sort_specs == None
    #   2. single sorting -> sort_specs == [[column_id, direction]]
    #   3. multi sorting -> sort_specs == [[column_id, direction], [column_id, direction], ...]
    #
    # Notes:
    #   1. direction is ascending if == 1
    #   2. direction is ascending if == -1

    if not sort_specs:
        return

    # column id -> index
    cols = dpg.get_item_children(sender, 0)
    col_idx = {cid: i for i, cid in enumerate(cols)}

    rows = list(dpg.get_item_children(sender, 1))
    row_values = {}

    for row in rows:
        row_items = dpg.get_item_children(row, 1)
        values = []
        for cell in row_items:
            if dpg.get_item_configuration(cell).get("span_columns") == True:
                # Selectables that span all columns should only be treated as text
                value = dpg.get_item_label(cell)
            else:
                value = dpg.get_value(cell)

            try:
                # Values like indices and other numbers should not be treated as strings
                value = float(value)
            except:
                pass

            values.append(value)

        row_values[row] = values

    # stable multi-column sort (last spec applied first)
    for col_id, direction in reversed(sort_specs):
        idx = col_idx[col_id]
        rows = natsorted(
            rows,
            key=lambda r: row_values[r][idx],
            reverse=direction < 0,
        )

    dpg.reorder_items(sender, 1, rows)
