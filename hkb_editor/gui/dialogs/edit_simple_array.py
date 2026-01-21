from typing import Any, Callable, Type
import logging
import re
from dearpygui import dearpygui as dpg

from hkb_editor.gui.helpers import (
    center_window,
    create_simple_value_widget,
    table_sort,
    add_paragraphs,
    get_paragraph_height,
)
from hkb_editor.gui import style
from .make_tuple import new_tuple_dialog


search_help_text = """\
By default this will filter the items by simple string match.

For more advanced searches you may combine several filters separated by commas (,). These filters will be applied in the order they are specified.

To only search specific index ranges you may use the ">X" or "<X" filters, where X is a number.
"""


def edit_simple_array_dialog(
    items: list[tuple],
    columns: dict[str, Type],
    *,
    title: str = "Edit Array",
    help: str = None,
    choices: dict[int, list[str | tuple[str, Any]]] = None,
    on_add: Callable[[int, list], bool] = None,
    on_update: Callable[[int, tuple, list], None] = None,
    on_delete: Callable[[int], None] = None,
    on_move: Callable[[int, int], None] = None,
    on_close: Callable[[str, list[str], Any], None] = None,
    get_item_hint: Callable[[int], list[str]] = None,
    item_limit: int = None,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    if item_limit is None:
        item_limit = 1000 / len(columns)
        # round to nearest hundred
        item_limit = max(100, int(round(item_limit / 100)) * 100)

    def new_entry_dialog(sender, app_data, item_idx: int):
        popup = new_tuple_dialog(
            columns,
            add_entry,
            choices=choices,
            user_data=item_idx,
        )

        dpg.split_frame()
        center_window(popup, dialog)

    def add_entry(sender, new_value: tuple, index: int):
        # In case on_add wants to edit the values
        new_value = list(new_value)

        if index is None:
            index = len(items)

        # May raise as a veto
        if on_add:
            on_add(index, new_value)

        items.insert(index, tuple(new_value))
        fill_table()

        # row = dpg.get_item_children(f"{tag}_table", slot=1)[index]
        # input_box = dpg.get_item_children(row, slot=1)[1]
        # dpg.focus_item(input_box)

    def move_entry(sender: str, app_data: Any, move: tuple[int, int]):
        idx, offset = move
        new_idx = idx + offset

        if not 0 <= new_idx < len(items):
            return

        # May raise as a veto
        if on_move:
            on_move(idx, new_idx)

        items[new_idx], items[idx] = items[idx], items[new_idx]
        fill_table()

    def delete_entry(sender: str, app_data: Any, index: int):
        if index is None:
            index = len(items) - 1

        # May raise as a veto
        if on_delete:
            on_delete(index)

        del items[index]
        fill_table()

    def update_entry(sender, new_value: Any, user_data: tuple[int, int]):
        item_idx, val_idx = user_data

        if choices and val_idx in choices:
            for item in choices[val_idx]:
                if item == new_value:
                    break
                if isinstance(item, tuple) and item[0] == new_value:
                    new_value = item[1]
                    break

        old_item = items[item_idx]
        new_item = list(old_item)
        new_item[val_idx] = new_value

        # May raise as a veto
        if on_update:
            try:
                on_update(item_idx, old_item, new_item)
            except Exception:
                # Rejected, regenerate the table before chickening out
                fill_table()
                raise

        items[item_idx] = tuple(new_item)

    def toggle_advanced(sender: str, enabled: bool, user_data: Any):
        if enabled:
            dpg.enable_item(f"{tag}_column_advanced")
        else:
            dpg.disable_item(f"{tag}_column_advanced")

    def show_item_hint(sender: str, app_data: Any, index: int):
        # TODO can use this to show where items are referenced
        print("TODO not implemented yet")

    def is_match(filt: str, idx: int, item: Any):
        filt = filt.strip().lower()
        if re.match(r"[<>][0-9]+", filt):
            num = int(filt[1:])
            if filt[0] == "<" and idx < num:
                return True
            elif filt[0] == ">" and idx > num:
                return True
        else:
            return filt in str(idx) or filt in str(item).lower()

    def get_matching_items(filt: str):
        if not filt:
            return [(idx, item) for idx, item in enumerate(items)]

        filt_parts = filt.lower().split(",")
        matches = list(enumerate(items))
        for part in filt_parts:
            matches = [
                (idx, item) for idx, item in matches if is_match(part, idx, item)
            ]

        return matches

    def fill_table(sender: str = None, filt: str = None, user_data: Any = None):
        if sender is None:
            sender = f"{tag}_filter"

        if filt is None:
            filt = dpg.get_value(f"{tag}_filter")

        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)

        matches = get_matching_items(filt)
        if len(matches) > item_limit:
            dpg.set_value(f"{tag}_total", f"(showing {item_limit}/{len(matches)})")
            matches = matches[:item_limit]
        else:
            dpg.set_value(f"{tag}_total", f"({len(matches)} matches)")

        for item_idx, item in matches:
            if filt != dpg.get_value(sender):
                # Crude attempt to return early
                break

            with dpg.table_row(filter_key=f"{item_idx}:{item}", parent=table) as row:
                dpg.add_text(str(item_idx))

                for val_idx, (val_type, val) in enumerate(zip(columns.values(), item)):
                    create_simple_value_widget(
                        val_type,
                        "",
                        callback=update_entry,
                        default=val,
                        choices=choices.get(val_idx) if choices else None,
                        user_data=(item_idx, val_idx),
                        width=-1,
                    )

                with dpg.group(horizontal=True, horizontal_spacing=2):
                    dpg.add_button(
                        label="+",
                        callback=new_entry_dialog,
                        user_data=item_idx + 1,
                    )
                    dpg.add_button(
                        arrow=True,
                        direction=dpg.mvDir_Down,
                        callback=move_entry,
                        user_data=(item_idx, 1),
                    )
                    dpg.add_button(
                        arrow=True,
                        direction=dpg.mvDir_Up,
                        callback=move_entry,
                        user_data=(item_idx, -1),
                    )
                    dpg.add_button(
                        label="-",
                        callback=delete_entry,
                        user_data=item_idx,
                    )

                    if get_item_hint:
                        dpg.add_button(
                            label="(?)",
                            small=True,
                            callback=show_item_hint,
                            user_data=item_idx,
                        )

    def close_dialog():
        if on_close:
            on_close(dialog, items, user_data)

        dpg.delete_item(dialog)
        if dpg.does_item_exist(f"{tag}_create_entry_popup"):
            dpg.delete_item(f"{tag}_create_entry_popup")

    with dpg.window(
        width=600,
        height=460,
        label=title,
        on_close=close_dialog,
        # autosize=True,
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="Filter Entries",
                callback=fill_table,
                tag=f"{tag}_filter",
            )

            dpg.add_button(label="?")
            with dpg.tooltip(dpg.last_item()):
                add_paragraphs(search_help_text, 70, color=style.yellow)
            
            dpg.add_text("", tag=f"{tag}_total")

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            scrollY=True,
            width=-1,
            # height=-help_text_height,  # set later
            borders_outerH=True,
            sortable=True,
            # sort_tristate=True,
            sort_multi=True,
            callback=table_sort,
            tag=f"{tag}_table",
        ) as table:
            dpg.add_table_column(label="Index")
            for col in columns.keys():
                dpg.add_table_column(label=col, width_stretch=True)
            dpg.add_table_column(tag=f"{tag}_column_advanced", enabled=False)

        with dpg.group(horizontal=True, show=True):
            dpg.add_button(
                label="Add New",
                callback=new_entry_dialog,
            )
            dpg.add_button(
                label="Delete Last",
                callback=delete_entry,
            )
            # Vertical separator :)
            dpg.add_text("|")
            dpg.add_checkbox(
                label="Advanced",
                default_value=False,
                callback=toggle_advanced,
            )

        if help:
            dpg.add_separator()
            par = add_paragraphs(help, 90, color=style.light_blue)

    dpg.focus_item(f"{tag}_filter")
    fill_table(f"{tag}_filter", "", None)

    # Adjust table height to content below it
    dpg.split_frame()
    table_h = 25
    if help:
        table_h += get_paragraph_height(par)

    # Round to nearest 10
    table_h = max(10, int(round(table_h / 10)) * 10)
    dpg.configure_item(f"{tag}_table", height=-table_h)
