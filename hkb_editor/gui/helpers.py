from __future__ import annotations
from typing import Any, Callable
from pathlib import Path
from dearpygui import dearpygui as dpg
import pyperclip
from natsort import natsorted

from hkb_editor.hkb import HkbRecord
from hkb_editor.hkb.xml import xml_to_str


url_regex = r"https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)"


def center_window(
    window: str,
    xratio: float = 0.5,
    yratio: float = 0.5,
    *,
    parent: str = None,
    split_frame: bool = False,
) -> None:
    if split_frame:
        dpg.split_frame()

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
            dpos[0] + (dsize[0] - psize[0]) * xratio,
            dpos[1] + (dsize[1] - psize[1]) * yratio,
        ),
    )


def make_copy_menu(
    record_or_getter: HkbRecord | Callable[[], HkbRecord], *, tag: str = 0
) -> str:
    from hkb_editor.workflows.clone_hierarchy import copy_hierarchy

    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if isinstance(record_or_getter, HkbRecord):
        getter_func = lambda: record_or_getter
    else:
        getter_func = record_or_getter

    with dpg.menu(label="Copy", tag=tag):
        dpg.add_selectable(
            label="XML",
            callback=lambda: pyperclip.copy(xml_to_str(getter_func().as_object())),
        )
        dpg.add_selectable(
            label="Hierarchy",
            callback=lambda: pyperclip.copy(copy_hierarchy(getter_func())),
        )

        dpg.add_separator()

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
            if dpg.get_item_configuration(cell).get("span_columns") is True:
                # Selectables that span all columns should only be treated as text
                value = dpg.get_item_label(cell)
            else:
                value = dpg.get_value(cell)

            try:
                # Values like indices and other numbers should not be treated as strings
                value = float(value)
            except Exception:
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


def shorten_path(path: str | Path, maxlen: int = 30) -> str:
    if not path:
        return ""

    parts = Path(path).parts
    short = parts[-1]

    for p in reversed(parts[:-1]):
        short = Path(p, short)
        if len(str(short)) > maxlen:
            short = Path("...", short)
            break

    return str(short)


def dpg_section(
    label: str,
    color: tuple,
    *,
    spacer: int = 10,
    parent: str = 0,
    tag: str = 0,
) -> None:
    if spacer > 0:
        dpg.add_spacer(height=spacer)

    dpg.add_text(label, color=color, parent=parent, tag=tag)
    dpg.add_separator()


