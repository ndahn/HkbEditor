from typing import Any, Callable, Type
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior
from hkb_editor.gui.helpers import center_window, create_simple_value_widget, table_sort, add_paragraphs
from hkb_editor.gui import style
from .make_tuple import new_tuple_dialog


def edit_simple_array_dialog(
    items: list[tuple],
    columns: dict[str, Type],
    *,
    title: str = "Edit Array",
    help: str = None,
    choices: dict[int, list[str | tuple[str, Any]]] = None,
    on_add: Callable[[int, str], bool] = None,
    on_update: Callable[[int, str, str], bool] = None,
    on_delete: Callable[[int], bool] = None,
    on_close: Callable[[str, list[str], Any], None] = None,
    get_item_hint: Callable[[int], list[str]] = None,
    item_limit: int = None,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    if item_limit is None:
        item_limit = 2000 / len(columns)
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
        # May return True as a veto
        if on_add and on_add(index, new_value):
            return

        items.insert(index, new_value)
        fill_table()

        # row = dpg.get_item_children(f"{tag}_table", slot=1)[index]
        # input_box = dpg.get_item_children(row, slot=1)[1]
        # dpg.focus_item(input_box)

    def update_entry(sender, new_value: Any, user_data: tuple[int, int]):
        item_idx, val_idx = user_data

        if choices and val_idx in choices:
            for item in choices[val_idx]:
                if item == new_value:
                    break
                if isinstance(item, tuple) and item[0] == new_value:
                    new_value = item[1]
                    break

        old_value_tuple = items[item_idx]
        new_value_tuple = list(old_value_tuple)
        new_value_tuple[val_idx] = new_value
        new_value_tuple = tuple(new_value_tuple)

        # May return True as a veto
        if on_update and on_update(item_idx, old_value_tuple, new_value_tuple):
            return

        items[item_idx] = new_value_tuple
        fill_table()

    def delete_entry(sender: str, app_data: Any, index: int):
        # May return True as a veto
        if on_delete and on_delete(index):
            return

        del items[index]
        fill_table()

    def show_item_hint(sender: str, app_data: Any, index: int):
        # TODO can use this to show where items are referenced
        print("TODO not implemented yet")

    def fill_table():
        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)

        filt = dpg.get_value(f"{tag}_filter")
        if filt:
            matches = [
                (idx, item)
                for idx, item in enumerate(items)
                if filt in str(idx) or filt in str(item)
            ]
        else:
            matches = [(idx, item) for idx, item in enumerate(items)]

        if len(matches) > item_limit:
            dpg.set_value(f"{tag}_total", f"(showing {item_limit}/{len(matches)})")
            matches = matches[:item_limit]
        else:
            dpg.set_value(f"{tag}_total", f"({len(matches)} matches)")

        for item_idx, item in matches:
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
                        label="(-)",
                        small=True,
                        callback=delete_entry,
                        user_data=item_idx,
                    )
                    dpg.add_button(
                        label="(+)",
                        callback=new_entry_dialog,
                        user_data=item_idx + 1,
                    )
                    if get_item_hint:
                        dpg.add_button(
                            label="(?)",
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
        height=400,
        label=title,
        on_close=close_dialog,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="Filter Entries",
                callback=fill_table,
                tag=f"{tag}_filter",
            )
            dpg.add_text(f"", tag=f"{tag}_total")

        dpg.add_separator()

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchSame,
            scrollY=True,
            width=600,
            height=250,
            sortable=True,
            # sort_tristate=True,
            sort_multi=True,
            callback=table_sort,
            tag=f"{tag}_table",
        ) as table:
            dpg.add_table_column(label="Index")
            for col in columns.keys():
                dpg.add_table_column(label=col, width_stretch=True)
            dpg.add_table_column()

        if help:
            dpg.add_separator()
            add_paragraphs(help, 90, color=style.light_blue)
            
    dpg.focus_item(f"{tag}_filter")
    fill_table()
