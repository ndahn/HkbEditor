from typing import Any, Callable, Generator
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import Tagfile, HkbRecord
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.workflows.aliases import AliasManager
from hkb_editor.gui.dialogs import find_dialog
from hkb_editor.gui.attributes_widget import AttributesWidget
from hkb_editor.gui.helpers import center_window


def create_object_dialog(
    tagfile: Tagfile,
    alias_manager: AliasManager,
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

    # There is no "hkbRecord" type to identify complex types that make sense for this dialog.
    # Instead we have to go by the type format, which may vary between games. Luckily, every
    # tagfile seems to contain a "hkRootLevelContainer" which we can use to identify the
    # record format.
    root_type_id = tagfile.type_registry.find_first_type_by_name("hkRootLevelContainer")
    record_format = tagfile.type_registry.get_format(root_type_id)
    record_types = [
        (type_id, details["name"])
        for type_id, details in tagfile.type_registry.types.items()
        if details["format"] == record_format
    ]

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def select_object_type() -> None:
        dialog = f"{tag}_select_mirror_bone"
        if dpg.does_item_exist(dialog):
            dpg.focus_item(dialog)
            return

        def get_object_types(filt: str) -> Generator[tuple[str, ...], None, None]:
            filt = filt.lower()
            for type_id, type_name in record_types:
                if filt in type_id or filt in type_name.lower():
                    yield (type_id, type_name)

        find_dialog(
            get_object_types,
            ["Type ID", "Name"],
            lambda item: item,
            okay_callback=lambda s, a, u: change_object_type(a[0]),
            title="Select Object Type",
            tag=dialog,
        )

    def change_object_type(new_type_id: str) -> None:
        nonlocal record

        dpg.hide_item(f"{tag}_notification")
        dpg.delete_item(f"{tag}_attributes", children_only=True)

        type_name = tagfile.type_registry.get_name(new_type_id)
        dpg.set_value(f"{tag}_object_type", type_name)

        # By creating the record here all UI widgets can modify it directly and we don't
        # need to collect their attributes later
        oid = dpg.get_value(f"{tag}_object_id")
        record = HkbRecord.new(tagfile, new_type_id, object_id=oid)
        attributes.set_record(record)
        attributes.set_title(None)

    def update_object_id(sender: str, new_id: str, user_data: Any = None) -> None:
        dpg.set_value(f"{tag}_object_id", new_id)
        if record:
            record.object_id = new_id
            attributes.set_title(None)

    def on_okay() -> None:
        if not record:
            show_warning("Select an object type first")
            return

        oid = dpg.get_value(f"{tag}_object_id")
        if not oid:
            show_warning("Please enter a valid object ID")
            return

        if oid in tagfile.objects:
            show_warning("Object ID already exists")
            return

        dpg.hide_item(f"{tag}_notification")

        type_id = dpg.get_value(f"{tag}_object_type")
        if not type_id:
            show_warning("No type selected")
            return

        tagfile.add_object(record)
        undo_manager.on_create_object(tagfile, record)
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
        with dpg.group(horizontal=True, width=300):
            dpg.add_input_text(
                default_value="",
                readonly=True,
                hint="Object type",
                tag=f"{tag}_object_type",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=select_object_type,
            )
            dpg.add_text("Object type")

        with dpg.group(horizontal=True, width=300):
            dpg.add_input_text(
                default_value=tagfile.new_id(),
                no_spaces=True,
                callback=update_object_id,
                tag=f"{tag}_object_id",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda: update_object_id(None, tagfile.new_id()),
            )
            dpg.add_text("Object ID")

        with dpg.child_window(auto_resize_y=True):
            attributes = AttributesWidget(alias_manager)

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
