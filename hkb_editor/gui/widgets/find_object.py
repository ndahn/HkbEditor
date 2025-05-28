from typing import Any, Callable
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior


def find_object_dialog(
    behavior: HavokBehavior,
    jump_callback: Callable[[str, str, Any], None],
    *,
    user_data: Any = None,
    tag: str = 0,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()
    
    selected_id: HkbRecord = None

    # TODO come up with a filter syntax like "id=... & type=..."
    def get_matching_objects(filt):
        return [
            obj
            for obj in behavior.objects.values()
            if filt in obj.object_id
            or filt in obj.type_id
            or filt in obj.get_field("name", "", resolve=True)
        ]

    def on_filter_update(sender, app_data, user_data):
        dpg.delete_item(table, children_only=True, slot=1)

        filt = dpg.get_value(sender)
        matches = get_matching_objects(filt)

        if len(matches) > 100:
            return

        for obj in sorted(matches, key=lambda o: o.object_id):
            name = obj.get_field("name", "", resolve=True)
            type_name = behavior.type_registry.get_name(obj.type_id)
            with dpg.table_row(parent=table, user_data=obj.object_id):
                dpg.add_selectable(
                    label=obj.object_id,
                    span_columns=True,
                    callback=on_select,
                    user_data=obj.object_id,
                    tag=f"{tag}_pointer_selectable_{obj.object_id}",
                )

                dpg.add_text(name)
                dpg.add_text(type_name)

    def on_select(sender, is_selected: bool, object_id: str):
        nonlocal selected_id
        if selected_id == object_id:
            return

        selected_id = object_id

        # Deselect all other selectables
        if is_selected:
            for row in dpg.get_item_children(table, slot=1):
                is_selected_obj = (dpg.get_item_user_data(row) == object_id)
                for cell in dpg.get_item_children(row, slot=1):
                    if dpg.get_item_type(cell) == "mvAppItemType::mvSelectable":
                        dpg.set_value(cell, is_selected_obj)

    def on_mouse_click(sender, button: int):
        if dpg.does_item_exist(f"{tag}_popup") and dpg.is_item_focused(f"{tag}_popup"):
            return
        
        if button == dpg.mvMouseButton_Right:
            for row in dpg.get_item_children(f"{tag}_table", slot=1):
                for child in dpg.get_item_children(row, slot=1):
                    if dpg.is_item_hovered(child):
                        obj_id = dpg.get_item_user_data(row)
                        on_select(row, True, obj_id)
                        show_context_menu()
                        return
        
        dpg.delete_item(f"{tag}_popup")

    # Right click menu
    def show_context_menu():
        if not selected_id:
            return
        
        popup = f"{tag}_popup"

        if not dpg.does_item_exist(popup):
            with dpg.window(
                min_size=(100, 20),
                no_title_bar=True,
                no_resize=True,
                no_move=True,
                no_saved_settings=True,
                autosize=True,
                show=False,
                tag=popup,
            ):
                dpg.add_selectable(label="Copy ID", callback=copy_id)
                dpg.add_selectable(label="Copy Name", callback=copy_name)
                dpg.add_selectable(label="Copy XML", callback=copy_xml)
                dpg.add_separator()
                dpg.add_selectable(label="Jump To", callback=jump_to)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))
        dpg.show_item(popup)

    def copy_id():
        dpg.delete_item(f"{tag}_popup")
        pyperclip.copy(selected_id)

    def copy_name():
        dpg.delete_item(f"{tag}_popup")
        obj = behavior.objects[selected_id]
        pyperclip.copy(obj.get_field("name", "", resolve=True))

    def copy_xml():
        dpg.delete_item(f"{tag}_popup")
        obj = behavior.objects[selected_id]
        pyperclip.copy(obj.xml())

    def jump_to():
        # We keep the window itself open
        dpg.delete_item(f"{tag}_popup")
        
        if selected_id:
            jump_callback(dialog, selected_id, user_data)

    def on_window_close():
        dpg.delete_item(dialog)
        dpg.delete_item(mouse_handler)

    with dpg.handler_registry() as mouse_handler:
        dpg.add_mouse_click_handler(callback=on_mouse_click)

    # Window content
    with dpg.window(
        width=600,
        height=400,
        label="Find Object",
        on_close=on_window_close,
        tag=tag,
    ) as dialog:
        # Way too many options, instead fill the table according to user input
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="Filter...",
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
            height=310,
            tag=f"{tag}_table"
        ) as table:
            dpg.add_table_column(label="ID")
            dpg.add_table_column(label="Name")
            dpg.add_table_column(label="Type")

    return tag
