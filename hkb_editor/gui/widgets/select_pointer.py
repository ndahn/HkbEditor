from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior


def select_pointer_dialog(
    behavior: HavokBehavior,
    callback: Callable[[str, str, Any], None],
    pointer: HkbPointer,
    user_data: Any = None,
) -> None:
    selected = pointer.get_value()
    tag = dpg.generate_uuid()

    def get_matching_objects(filt):
        return [
            obj
            for obj in behavior.objects.values()
            if pointer.subtype in (None, obj.type_id)
            and (
                filt in obj.object_id or filt in obj.type_id or filt in obj.get_field("name", "")
            )
        ]

    def on_filter_update(sender, app_data, user_data):
        dpg.delete_item(table, children_only=True, slot=1)

        # TODO come up with a filter syntax like "id=... & type=..."
        filt = dpg.get_value(sender)
        matches = get_matching_objects(filt)

        if len(matches) > 100:
            return

        for obj in sorted(matches, key=lambda o: o.object_id):
            name = obj["name"]
            type_name = behavior.type_registry.get_name(obj.type_id)
            with dpg.table_row(parent=table, user_data=obj.object_id):
                dpg.add_selectable(
                    label=obj.object_id,
                    span_columns=True,
                    default_value=obj.object_id == selected,
                    callback=on_select,
                    user_data=obj.object_id,
                    tag=f"{tag}_pointer_selectable_{obj.object_id}",
                )
                dpg.add_text(name)
                dpg.add_text(type_name)

    def on_select(sender, app_data, object_id: str):
        nonlocal selected
        if selected == object_id:
            return

        selected = object_id

        # Deselect all other selectables
        for row in dpg.get_item_children(table, slot=1):
            if dpg.get_item_user_data(row) != object_id:
                for cell in dpg.get_item_children(row, slot=1):
                    if dpg.get_item_type(cell) == "mvAppItemType::mvSelectable":
                        dpg.set_value(cell, False)

    def on_okay():
        callback(dialog, selected, user_data)
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
        # TODO use a clipper!
        # Way too many options, instead fill the table according to user input
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="Find Object...",
                callback=on_filter_update,
            )

            num_total = len(get_matching_objects(""))
            dpg.add_text(f"({num_total} candidates)")

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
