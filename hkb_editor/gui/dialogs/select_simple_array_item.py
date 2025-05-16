from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb.hkb_types import HkbArray, XmlValueHandler
from hkb.behavior import HavokBehavior


def select_simple_array_item(
    array: HkbArray,
    callback: Callable[[str, int, XmlValueHandler], None],
    value_widget: str,
    selected: int = -1,
    user_data: Any = None,
) -> None:
    tag = dpg.generate_uuid()

    def on_select(sender, app_data, index: int):
        nonlocal selected
        if index == selected:
            return

        selected = index

        # Deselect all other selectables
        for row in dpg.get_item_children(table, slot=1):
            if dpg.get_item_user_data(row) != index:
                for cell in dpg.get_item_children(row, slot=1):
                    if dpg.get_item_type(cell) == "mvAppItemType::mvSelectable":
                        dpg.set_value(cell, False)

    def on_okay():
        if selected < 0:
            return

        callback(value_widget, selected, user_data)
        dpg.delete_item(dialog)

    def on_cancel():
        dpg.delete_item(dialog)

    with dpg.window(
        width=600,
        height=400,
        label="Select Item",
        modal=True,
        on_close=lambda: dpg.delete_item(dialog),
    ) as dialog:
        # Way too many options, instead fill the table according to user input
        dpg.add_input_text(
            hint="Find Object...",
            callback=lambda s, a, u: dpg.set_value(table, dpg.get_value(s)),
        )

        dpg.add_separator()

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            scrollY=True,
            # no_host_extendY=True,
            height=310,
        ) as table:
            dpg.add_table_column(label="Index")
            dpg.add_table_column(label="Name")

            for idx,item in enumerate(array):
                val = item.get_value()
                with dpg.table_row(filter_key=val, user_data=idx):
                    dpg.add_selectable(
                        label=idx,
                        span_columns=True,
                        default_value=idx == selected,
                        callback=on_select,
                        user_data=idx,
                        tag=f"{tag}_item_selectable_{idx}",
                    )
                    dpg.add_text(val)

        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Okay",
                callback=on_okay,
            )
            dpg.add_button(
                label="Cancel",
                callback=on_cancel,
            )
