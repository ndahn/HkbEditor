from typing import Any, Callable
import webbrowser
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.query import lucene_help_text, lucene_url
from hkb_editor.gui.helpers import make_copy_menu
from hkb_editor.gui import style


def find_object_dialog(
    behavior: HavokBehavior,
    jump_callback: Callable[[str, str, Any], None] = None,
    *,
    context_menu: bool = True,
    user_data: Any = None,
    tag: str = 0,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()
    
    selected_id: HkbRecord = None

    def get_matching_objects(filt: str):
        try:
            return list(behavior.query(filt))
        except ValueError:
            return []

    def on_filter_update(sender, app_data, user_data):
        dpg.delete_item(table, children_only=True, slot=1)

        filt = dpg.get_value(sender)
        matches = get_matching_objects(filt)
        dpg.set_value(f"{tag}_total", f"({len(matches)} candidates)")

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
                if context_menu:
                    dpg.bind_item_handler_registry(dpg.last_item(), right_click_handler)

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
                if dpg.get_item_user_data(row) != object_id:
                    dpg.set_value(dpg.get_item_children(row, slot=1)[0], False)

    # Right click menu
    def show_context_menu():
        if not selected_id:
            return
        
        popup = f"{tag}_popup"

        if not dpg.does_item_exist(popup):
            with dpg.window(
                popup=True,
                min_size=(100, 20),
                no_saved_settings=True,
                autosize=True,
                tag=popup,
            ):
                make_copy_menu(lambda: behavior.objects[selected_id])
                if jump_callback:
                    dpg.add_separator()
                    dpg.add_selectable(label="Jump To", callback=jump_to)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))
        dpg.show_item(popup)

    def jump_to():
        if selected_id:
            jump_callback(dialog, selected_id, user_data)

    with dpg.item_handler_registry() as right_click_handler:
        dpg.add_item_clicked_handler(
            button=dpg.mvMouseButton_Right, callback=show_context_menu
        )

    def on_window_close():
        dpg.delete_item(dialog)
        dpg.delete_item(right_click_handler)

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

            # A helpful tooltip full of help
            dpg.add_button(
                label="?", 
                callback=lambda: webbrowser.open(lucene_url)
            )
            with dpg.tooltip(dpg.last_item()):
                for line in lucene_help_text.split("\n"):
                    bullet = False
                    if line.startswith("- "):
                        line = line[2:]
                        bullet = True

                    dpg.add_text(line, bullet=bullet)

                dpg.add_text(
                    "(Click the '?' to open the official documentation)", 
                    color=style.blue
                )

            num_total = len(get_matching_objects("*"))
            dpg.add_text(f"({num_total} total)", tag=f"{tag}_total")

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
