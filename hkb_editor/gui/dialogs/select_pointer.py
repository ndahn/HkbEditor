from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb.hkb_types import HkbPointer, XmlValueHandler
from hkb.behavior import HavokBehavior


def select_pointer(
    value_widget: str,
    beh: HavokBehavior,
    ptr: HkbPointer,
    callback: Callable[[str, Any, XmlValueHandler], None],
    target_type_id: str = None,
) -> None:
    selected = ptr.get_value()
    tag = dpg.generate_uuid()

    def on_filter_update(sender, app_data, user_data):
        dpg.delete_item(table, children_only=True, slot=1)

        # TODO come up with a filter syntax like "id=... & type=..."
        filt: str = dpg.get_value(sender)
        matches = [
            obj
            for obj in beh.objects.values()
            if target_type_id in (None, obj.type_id)
            and (
                filt in obj.id or filt in obj.type_id or filt in obj.get("name", "")
            )
        ]

        if len(matches) > 100:
            return

        for obj in sorted(matches, key=lambda o: o.id):
            name = obj.get("name")
            type_name = beh.type_registry.get_name(obj.type_id)
            with dpg.table_row(parent=table, user_data=obj.id):
                dpg.add_selectable(
                    label=obj.id,
                    span_columns=True,
                    default_value=obj.id == selected,
                    callback=on_select,
                    user_data=obj.id,
                    tag=f"{tag}_pointer_selectable_{obj.id}",
                )
                dpg.add_text(name)
                dpg.add_text(type_name)

    def on_select(sender, app_data, object_id: str):
        nonlocal selected
        selected = object_id

        # Deselect all other selectables
        for row in dpg.get_item_children(table, slot=1):
            if dpg.get_item_user_data(row) != object_id:
                for cell in dpg.get_item_children(row, slot=1):
                    if dpg.get_item_type(cell) == "mvAppItemType::mvSelectable":
                        dpg.set_value(cell, False)

    def on_okay():
        callback(value_widget, selected, ptr)
        dpg.delete_item(dialog)

    def on_cancel():
        dpg.delete_item(dialog)

    with dpg.window(
        width=600,
        height=400,
        label="Select Pointer",
        modal=True,
        on_close=lambda: dpg.delete_item(dialog),
    ) as dialog:
        # Way too many options, instead fill the table according to user input
        dpg.add_input_text(
            hint="Find Object...",
            callback=on_filter_update,
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
            dpg.add_table_column(label="ID")
            dpg.add_table_column(label="Name")
            dpg.add_table_column(label="Type")

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
