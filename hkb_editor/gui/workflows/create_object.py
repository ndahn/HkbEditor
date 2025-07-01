from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import Tagfile, XmlValueHandler, HkbRecord
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.dialogs import find_dialog
from hkb_editor.gui.helpers import center_window


def open_create_object_dialog(
    tagfile: Tagfile,
    callback: Callable[[str, HkbRecord, Any], None],
    object_type_id: str = None,
    *,
    title: str = "Create Hkb Object",
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    record: HkbRecord = None

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def select_object_type() -> None:
        dialog = f"{tag}_select_mirror_bone"
        if dpg.does_item_exist(dialog):
            dpg.focus_item(dialog)
            return

        def get_object_types(filt: str) -> list[tuple[str, ...]]:
            return [
                (type_id, details["name"])
                for type_id, details in tagfile.type_registry.types.items()
                if (filt in type_id or filt in details["name"])
            ]

        find_dialog(
            get_object_types,
            ["Type ID", "Name"],
            lambda item: item,
            okay_callback=lambda s, a, u: change_object_type(a[0]),
            title="Select Object Type",
            tag=dialog,
        )

    def change_object_type(new_type_id: str) -> None:
        dpg.hide_item(f"{tag}_notification")

        dpg.delete_item(f"{tag}_attributes", children_only=True)

        type_name = tagfile.type_registry.get_name(new_type_id)
        dpg.set_value(f"{tag}_selected_type", type_name)

        nonlocal record
        # By having the record here all UI widgets can modify it directly and we don't 
        # need to collect their attributes later
        record = HkbRecord.new(tagfile, new_type_id)

        # TODO populate attributes, see beh_editor

    def on_okay() -> None:
        dpg.hide_item(f"{tag}_notification")

        type_id = dpg.get_value(f"{tag}_selected_type")
        if not type_id:
            show_warning("No type selected")
            return 

        undo_manager.on_create_object(tagfile, record)
        tagfile.add_object(record)
        callback(window, record, user_data)
        dpg.delete_item(window)

    # UI content
    with dpg.window(
        label=title,
        width=400,
        height=600,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        with dpg.group(horizontal=True, width=200):
            dpg.add_input_text(
                default_value="",
                readonly=True,
                tag=f"{tag}_selected_type",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=select_object_type,
            )

        dpg.add_separator()

        # Will be populated later
        dpg.add_group(tag=f"{tag}_attributes")

        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=(255, 0, 0))

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(window),
            )
            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )

    if object_type_id:
        change_object_type(object_type_id)

    dpg.split_frame()
    center_window(window)
    return window
