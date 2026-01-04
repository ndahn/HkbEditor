from typing import Any, Callable, Generator, Iterable
import re
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import Tagfile, HkbRecord
from hkb_editor.gui.workflows.aliases import AliasManager
from hkb_editor.gui.dialogs import find_dialog
from hkb_editor.gui.widgets import AttributesWidget
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui import style


def create_object_dialog(
    tagfile: Tagfile,
    alias_manager: AliasManager,
    callback: Callable[[str, HkbRecord, Any], None],
    *,
    allowed_types: Iterable[str] = None,
    include_derived_types: bool = False,
    selected_type_id: str = None,
    id_required: bool = False,
    title: str = "Create Hkb Object",
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, 0, ""):
        tag = f"create_object_dialog_{dpg.generate_uuid()}"

    type_registry = tagfile.type_registry
    record: HkbRecord = None

    if allowed_types:
        if isinstance(allowed_types, str):
            allowed_types = [allowed_types]
            
        record_types = []

        for tp in allowed_types:
            if re.match(r"type[0-9]+", tp):
                tid = tp
                name = type_registry.get_name(tp)
            else:
                tid = type_registry.find_first_type_by_name(tp)
                name = tp
            
            record_types.append((tid, name))

            if include_derived_types:
                for derived in type_registry.get_compatible_types(tid):
                    d_name = type_registry.get_name(derived)
                    record_types.append((derived, d_name))

        # Sort by names
        record_types.sort(key=lambda t: t[1])

        if selected_type_id is None:
            # We can assume the first item is a sensible choice
            selected_type_id = record_types[0][0]
    else:
        # There is no "hkbRecord" type to identify complex types that make sense for this dialog.
        # Instead we have to go by the type format, which may vary between games. Luckily, every
        # tagfile seems to contain a "hkRootLevelContainer" which we can use to identify the
        # record format.
        record_format = type_registry.get_format(tagfile.behavior_root.type_id)
        record_types = [
            (type_id, details["name"])
            for type_id, details in type_registry.types.items()
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

        type_name = type_registry.get_name(new_type_id)
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

        oid = record.object_id
        if not oid:
            if id_required:
                show_warning("Please enter a valid object ID")
                return
        elif oid in tagfile.objects:
            show_warning("Object ID already exists")
            return

        dpg.hide_item(f"{tag}_notification")

        type_id = dpg.get_value(f"{tag}_object_type")
        if not type_id:
            show_warning("No type selected")
            return

        with tagfile.transaction():
            tagfile.add_object(record)
            callback(window, record, user_data)
            
        dpg.delete_item(window)

    # UI content
    with dpg.window(
        label=title,
        width=500,
        height=600,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        if allowed_types:
            # If there's a limited number of available object types use a dropdown
            def on_type_selected(sender: str, type_name: str, user_data: Any):
                type_id = type_registry.find_first_type_by_name(type_name)
                change_object_type(type_id)

            dpg.add_combo(
                [t[1] for t in record_types],
                callback=on_type_selected,
                width=300,
                tag=f"{tag}_object_type",
            )
        else:
            # If all types are allowed use a find dialog
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
                label="+",
                small=True,
                callback=lambda: update_object_id(None, tagfile.new_id()),
            )
            dpg.add_text("Object ID")

        with dpg.child_window(auto_resize_y=True):
            attributes = AttributesWidget(alias_manager, hide_title=True)

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.red)

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

    if selected_type_id:
        change_object_type(selected_type_id)

    dpg.split_frame()
    center_window(window)
    return window
