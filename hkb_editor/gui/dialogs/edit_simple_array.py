from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.gui.helpers import center_window, create_value_widget
from .make_tuple import new_tuple_dialog


def edit_simple_array_dialog(
    items: list[tuple],
    columns: list[str],
    *,
    title: str = "Edit Array",
    help: list[str] = None,
    choices: dict[int, list[str]] = None,
    on_add: Callable[[int, str], bool] = None,
    on_update: Callable[[int, str, str], bool] = None,
    on_delete: Callable[[int], bool] = None,
    on_close: Callable[[str, list[str], Any], None] = None,
    get_item_hint: Callable[[int], list[str]] = None,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    def new_entry_dialog(sender, app_data, item_idx: int):
        popup = new_tuple_dialog(
            {col:type(v) for col, v in zip(columns, items[0])},
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

    # TODO move

    def show_item_hint(sender: str, app_data: Any, index: int):
        # TODO can use this to show where items are referenced
        print("TODO not implemented yet")

    def fill_table():
        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)

        for item_idx, item in enumerate(items):
            with dpg.table_row(filter_key=f"{item_idx}:{item}", parent=table) as row:
                dpg.add_text(str(item_idx))

                for val_idx, val in enumerate(item):
                    create_value_widget(
                        val_idx,
                        val,
                        callback=update_entry,
                        user_data=(item_idx, val_idx),
                        choices=choices,
                        on_enter=True,
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

    def cloe_dialog():
        if on_close:
            on_close(dialog, items, user_data)

        dpg.delete_item(dialog)
        if dpg.does_item_exist(f"{tag}_create_entry_popup"):
            dpg.delete_item(f"{tag}_create_entry_popup")

    with dpg.window(
        width=600,
        height=400,
        label=title,
        on_close=cloe_dialog,
        # autosize=True,
        tag=tag,
    ) as dialog:
        dpg.add_input_text(
            hint="Filter Entries",
            callback=lambda s, a, u: dpg.set_value(table, dpg.get_value(s)),
        )

        dpg.add_separator()

        spare_height = 30
        if help:
            spare_height += 15 * len(help)

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchSame,
            scrollY=True,
            height=-spare_height,
            tag=f"{tag}_table",
        ) as table:
            dpg.add_table_column(label="Index")
            for col in columns:
                dpg.add_table_column(label=col, width_stretch=True)
            dpg.add_table_column()

        if help:
            dpg.add_separator()
            for line in help:
                dpg.add_text(line)

    fill_table()
