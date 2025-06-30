from typing import Any, Callable
import os
import logging
from threading import Thread
import textwrap
import time
from lxml import etree as ET
from dearpygui import dearpygui as dpg
import networkx as nx
import pyperclip

from hkb_editor.hkb.behavior import HavokBehavior, VariableType
from hkb_editor.hkb.hkb_types import (
    XmlValueHandler,
    HkbRecord,
    HkbPointer,
    HkbArray,
    HkbString,
    HkbInteger,
    HkbFloat,
    HkbBool,
    get_value_handler,
)
from hkb_editor.hkb.hkb_enums import get_hkb_enum

from .graph_editor import GraphEditor, Node
from .dialogs import (
    edit_simple_array_dialog,
    select_object,
    search_objects_dialog,
)
from .table_tree import (
    table_tree_leaf,
    add_lazy_table_tree_node,
    get_row_node_item,
    set_foldable_row_status,
)
from .workflows.bind_attribute import (
    bindable_attribute,
    select_variable_to_bind,
    get_bound_attributes,
    set_bindable_attribute_state,
    unbind_attribute,
)
from .workflows.file_dialog import open_file_dialog
from .workflows.undo import undo_manager
from .workflows.aliases import AliasManager
from .workflows.create_cmsg import open_new_cmsg_dialog
from .workflows.register_clip import open_register_clip_dialog
from .workflows.state_graph_viewer import open_state_graph_viewer
from .helpers import make_copy_menu, center_window
from . import style


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        # Setup the root logger first before calling super, which will instantiate
        # a new logger
        class LogHandler(logging.Handler):
            def emit(this, record):
                self.notification(record.getMessage(), record.levelno)

        logging.root.addHandler(LogHandler())

        super().__init__(tag)
        self.beh: HavokBehavior = None
        self.alias_manager = AliasManager()
        self.pinned_objects_table: str = None
        self.min_notification_severity = logging.INFO

    def notification(self, message: str, severity: int = logging.INFO) -> None:
        if severity < self.min_notification_severity:
            return

        lines = textwrap.wrap(message)

        with dpg.mutex():
            with dpg.window(
                min_size=(20, 20),
                no_title_bar=True,
                no_focus_on_appearing=True,
                no_saved_settings=True,
                no_close=True,
                no_collapse=True,
                no_move=True,
                autosize=True,
            ) as note:
                for line in lines:
                    dpg.add_text(line, color=(0, 0, 0, 255))

            if severity >= logging.ERROR:
                theme = style.notification_error_theme
            elif severity >= logging.WARNING:
                theme = style.notification_warning_theme
            else:
                theme = style.notification_info_theme

            dpg.bind_item_theme(note, theme)

        dpg.split_frame(delay=64)

        w = dpg.get_item_width(note)
        h = dpg.get_item_height(note)
        pos = (
            dpg.get_viewport_width() - w - 50,
            dpg.get_viewport_height() - h - 50,
        )
        dpg.configure_item(note, pos=pos)

        def remove_notification():
            time.sleep(3.0)
            dpg.delete_item(note)

        Thread(target=remove_notification, daemon=True).start()

    def _do_load_from_file(self, file_path: str):
        with dpg.window(
            modal=True,
            no_close=True,
            no_move=True,
            no_collapse=True,
            no_title_bar=True,
            no_resize=True,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
            no_saved_settings=True,
        ) as loading_screen:
            dpg.add_loading_indicator()
            dpg.add_text(f"Loading {os.path.basename(file_path)}...")
            dpg.add_separator()
            dpg.add_text("Relax, get a coffee, breathe, maybe")
            dpg.add_text("contemplate your life choices...")

        # Already centered, this will make it worse somehow
        # dpg.split_frame(delay=64)
        # center_window(loading_screen)

        undo_manager.clear()
        self.alias_manager.clear()
        filename = os.path.basename(file_path)
        dpg.configure_viewport(0, title=f"HkbEditor - {filename}")
        self.beh = HavokBehavior(file_path)
        self._set_menus_enabled(True)

        dpg.delete_item(loading_screen)

    def _do_write_to_file(self, file_path):
        self.beh.save_to_file(file_path)

    def exit_app(self):
        with dpg.window(
            label="Exit?",
            modal=True,
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            if self.last_save == 0.0:
                dpg.add_text(f"You have not saved yet. Exit anyways?")
            else:
                dpg.add_text(
                    f"It has been {self.last_save:.0f}s since your last save. Exit?"
                )

            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Exit", callback=dpg.stop_dearpygui)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(wnd))

    def create_app_menu(self):
        self._create_file_menu()
        dpg.add_separator()

        with dpg.menu(label="Edit", enabled=False, tag=f"{self.tag}_menu_edit"):
            dpg.add_menu_item(label="Undo (ctrl-z)", callback=self.undo)
            dpg.add_menu_item(label="Redo (ctrl-y)", callback=self.redo)
            dpg.add_separator()
            dpg.add_menu_item(label="Load Skeleton...", callback=self.load_bone_names)
            # TODO enable
            dpg.add_menu_item(label="Attribute Aliases...", enabled=False)
            dpg.add_separator()
            dpg.add_menu_item(label="Variables...", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events...", callback=self.open_event_editor)
            dpg.add_menu_item(
                label="Animations...", callback=self.open_animation_names_editor
            )

        with dpg.menu(
            label="Workflows", enabled=False, tag=f"{self.tag}_menu_workflows"
        ):
            dpg.add_menu_item(
                label="Find Object...", callback=lambda: self.open_search_dialog()
            )
            dpg.add_separator()
            # TODO not mature enough yet
            dpg.add_menu_item(
                label="StateInfo Graph...",
                enabled=True,
                callback=lambda: self.open_stategraph_dialog(),
            )
            dpg.add_separator()
            dpg.add_menu_item(
                label="Create Object...",
                enabled=False,
                callback=self.create_object_dialog,
            )
            dpg.add_menu_item(
                label="Register Clip...", callback=self.open_register_clip_dialog
            )
            dpg.add_menu_item(
                label="Create CMSG...", callback=self.open_create_cmsg_dialog
            )

        self._create_settings_menu()

        dpg.add_separator()
        self._create_dpg_menu()

    def _on_key_press(self, sender, key: int) -> None:
        if dpg.is_key_down(dpg.mvKey_ModCtrl):
            if key == dpg.mvKey_Z:
                self.undo()
            elif key == dpg.mvKey_Y:
                self.redo()

    def _set_menus_enabled(self, enabled: bool) -> None:
        func = dpg.enable_item if enabled else dpg.disable_item
        func(f"{self.tag}_menu_file_save")
        func(f"{self.tag}_menu_file_save_as")
        func(f"{self.tag}_menu_edit")
        func(f"{self.tag}_menu_workflows")

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_None, callback=self._on_key_press)

    def get_supported_file_extensions(self):
        return {"Behavior XML": "*.xml"}

    def _setup_content(self) -> None:
        super()._setup_content()

        with dpg.window(
            label="Pinned Objects",
            autosize=True,
            no_close=True,
            tag=f"{self.tag}_pinned_objects",
        ):
            # Child window to fix table sizing
            with dpg.child_window(border=False):
                with dpg.table(
                    no_host_extendX=True,
                    resizable=True,
                    borders_innerV=True,
                    policy=dpg.mvTable_SizingFixedFit,
                    scrollY=True,
                    tag=f"{self.tag}_pinned_objects_table",
                ) as self.pinned_objects_table:
                    dpg.add_table_column(label="ID")
                    dpg.add_table_column(label="Name", width_stretch=True)
                    dpg.add_table_column(label="Type", width_stretch=True)

        with dpg.item_handler_registry(tag=f"{self.tag}_pin_registry"):
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right, callback=self.open_pin_menu
            )

    def add_pinned_object(self, object_id: str) -> None:
        obj = self.beh.objects[object_id]

        def on_select(sender: str):
            # No selection
            dpg.set_value(sender, False)

        with dpg.table_row(
            # For some reason self.pinned_objects_table doesn't work?
            parent=f"{self.tag}_pinned_objects_table",
            tag=f"{self.tag}_pin_{object_id}",
            user_data=object_id,
        ) as row:
            dpg.add_selectable(
                label=object_id,
                span_columns=True,
                callback=on_select,
                user_data=object_id,
            )
            dpg.bind_item_handler_registry(dpg.last_item(), f"{self.tag}_pin_registry")
            dpg.add_text(
                obj.get_field("name", None, resolve=True),
            )
            dpg.add_text(obj.type_name)

    def remove_pinned_object(self, object_id: str) -> None:
        for row in dpg.get_item_children(f"{self.tag}_pinned_objects_table", slot=1):
            if dpg.get_item_user_data(row) == object_id:
                dpg.delete_item(row)
                break

    def open_pin_menu(self, sender: str, app_data: str, user_data: Any) -> None:
        _, selectable = app_data
        object_id = dpg.get_item_user_data(selectable)
        pinned_obj: HkbRecord = self.beh.retrieve_object(object_id)

        def show_attributes():
            self.canvas.deselect()
            self._clear_attributes()

            # update_attributes wants a Node, not a record, so we do it ourselves
            dpg.set_value(f"{self.tag}_attributes_title", object_id)

            for key, val in pinned_obj.get_value().items():
                with dpg.table_row(
                    filter_key=key,
                    parent=self.attributes_table,
                ):
                    self._create_attribute_widget(pinned_obj, val, key)

        popup = f"{self.tag}_pin_menu"

        if dpg.does_item_exist(popup):
            dpg.delete_item(popup)

        # Pin context menu
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_saved_settings=True,
            autosize=True,
            show=False,
            tag=popup,
        ):
            dpg.add_selectable(
                label="Unpin", callback=lambda: self.remove_pinned_object(object_id)
            )
            dpg.add_selectable(
                label="Jump To", callback=lambda: self.jump_to_object(object_id)
            )
            dpg.add_selectable(label="Show Attributes", callback=show_attributes)
            make_copy_menu(pinned_obj)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))
        dpg.show_item(popup)

    def get_root_ids(self) -> list[str]:
        sm_type = self.beh.type_registry.find_first_type_by_name("hkbStateMachine")
        roots = [
            (obj["name"].get_value(), obj.object_id)
            for obj in self.beh.find_objects_by_type(sm_type)
        ]
        # Names for sorting, but return root IDs. They'll be resolved to names via
        # get_node_frontpage_short
        return [r[1] for r in sorted(roots)]

    def get_graph(self, root_id: str) -> nx.DiGraph:
        self.logger.info("Building graph for node %s", root_id)
        return self.beh.build_graph(root_id)

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        obj: HkbRecord = self.beh.objects[node.id]
        return {k: v for k, v in obj.get_value().items()}

    def get_node_frontpage(self, node: Node) -> list[str]:
        obj = self.beh.objects[node.id]
        try:
            return [
                (obj["name"].get_value(), style.yellow),
                (node.id, style.blue),
                (self.beh.type_registry.get_name(obj.type_id), style.white),
            ]
        except AttributeError:
            return [
                (node.id, style.blue),
                (self.beh.type_registry.get_name(obj.type_id), style.white),
            ]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return self.beh.objects[node_id]["name"].get_value()

    def open_node_menu(self, node):
        obj = self.beh.objects.get(node.id)
        if not obj:
            return []

        # TODO more actions
        # type_name = self.beh.type_registry.get_name(obj.type_id)
        actions = [
            "Copy ID",
            # "Copy Node",
            # "-",
            # "Hide",
        ]

        if obj.get_field("name", None) is not None:
            actions.append("Copy Name")

        actions.extend(["Copy XML", "-", "Pin Object"])

        def on_item_selected(sender, app_data, selected_item: str):
            dpg.set_value(sender, False)
            dpg.delete_item(f"{self.tag}_{node.id}_menu")

            if selected_item == "Copy ID":
                self._copy_to_clipboard(node.id)
            elif selected_item == "Copy Name":
                obj = self.beh.objects[node.id]
                self._copy_to_clipboard(obj["name"])
            elif selected_item == "Copy XML":
                obj = self.beh.objects[node.id]
                self._copy_to_clipboard(obj.xml())
            elif selected_item == "Pin Object":
                self.add_pinned_object(node.id)
            else:
                self.logger.warning("Not implemented yet")

        # Node menu
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text(node.id, color=style.blue)
            dpg.add_separator()

            for item in actions:
                if item == "-":
                    dpg.add_separator()
                else:
                    dpg.add_selectable(
                        label=item, callback=on_item_selected, user_data=item
                    )

    def on_update_pointer(
        self,
        sender: str,
        record: HkbRecord,
        pointer: HkbPointer,
        old_value: str,
        new_value: str,
    ) -> None:
        if old_value:
            # Could be an entirely new pointer object with no previous value
            self.add_pinned_object(old_value)
            self.logger.info("Pinned previous object %s", old_value)

        self.on_attribute_update(sender, new_value, pointer)

        if new_value not in self.canvas.nodes:
            # Edges have changed, previous node may not be connected anymore, new
            # node may not be part of the current statemachine graph yet, ...
            root_id = self.get_active_statemachine().object_id
            selected = self.selected_node
            self._on_root_selected(sender, True, root_id)
            if selected:
                self.canvas.select(selected)
        else:
            # Changing a pointer will change the rendered graph
            self.canvas.regenerate()

    def reveal_attribute(self, path: str) -> None:
        if not self.selected_node:
            return

        subpath = ""

        def reveal(part: str):
            nonlocal subpath
            subpath += part
            row = f"{self.tag}_attribute_{subpath}"
            set_foldable_row_status(row, True)

        for part in path.split("/"):
            if subpath:
                subpath += "/"

            subparts = part.split(":")
            reveal(subparts[0])

            if len(subparts) > 1:
                for idx in subparts[1:]:
                    reveal(f":{idx}")

    def _add_attribute_row_contents(self, attribute: str, val: Any, node: Node) -> None:
        obj = self.beh.objects.get(node.id)
        self._create_attribute_widget(obj, val, attribute)

    def _create_attribute_widget(
        self,
        source_record: HkbRecord,
        value: XmlValueHandler,
        path: str,
        *,
        before: str = 0,
    ):
        self.logger.debug("Creating new attribute widget: %s", path)

        tag = f"{self.tag}_attribute_{path}"
        widget = tag

        label = self.alias_manager.get_attribute_alias(source_record, path)
        if label is None:
            label = path.split("/")[-1]
            label_color = style.white
        else:
            label_color = style.green

        if isinstance(value, HkbRecord):
            # create items on demand, dpg performance tanks with too many widgets
            def lazy_create_record_attributes(anchor: str):
                for subkey, subval in value.get_value().items():
                    self._create_attribute_widget(
                        source_record, subval, f"{path}/{subkey}", before=anchor
                    )

            add_lazy_table_tree_node(
                label,
                lazy_create_record_attributes,
                table=self.attributes_table,
                tag=tag,
                before=before,
            )
            widget = get_row_node_item(tag)

        elif isinstance(value, HkbArray):
            type_name = self.beh.type_registry.get_name(value.type_id)
            if type_name in (
                "hkVector4",
                "hkVector4f",
                "hkQuaternion",
                "hkQuaternionf",
            ):
                self._create_attribute_widget_vector4(
                    source_record,
                    value,
                    path,
                    tag,
                )

            else:
                # create items on demand, dpg performance tanks with too many widgets
                def lazy_create_array_items(anchor: str):
                    for idx, subval in enumerate(value):
                        self._create_attribute_widget(
                            source_record, subval, f"{path}:{idx}", before=anchor
                        )

                    with table_tree_leaf(
                        table=self.attributes_table,
                        tag=f"{tag}_arraybuttons",
                        before=anchor,
                    ):
                        self._create_attribute_widget_array_buttons(
                            source_record,
                            value,
                            path,
                        )

                add_lazy_table_tree_node(
                    label,
                    lazy_create_array_items,
                    table=self.attributes_table,
                    tag=tag,
                    before=before,
                )
                widget = get_row_node_item(tag)

        elif isinstance(value, HkbPointer):
            with table_tree_leaf(
                table=self.attributes_table,
                before=before,
            ):
                self._create_attribute_widget_pointer(source_record, value, path, tag)
                dpg.add_text(label, color=label_color)

        else:
            with table_tree_leaf(
                table=self.attributes_table,
                before=before,
            ):
                self._create_attribute_widget_simple(source_record, value, path, tag)
                dpg.add_text(label, color=label_color)

        self._create_attribute_menu(widget, source_record, value, path)

    def _create_attribute_widget_pointer(
        self,
        source_record: HkbRecord,
        pointer: HkbPointer,
        path: str,
        tag: str = 0,
        before: dict[str, Any] = None,
    ) -> str:
        attribute = path.split("/")[-1]

        def on_pointer_selected(sender, target: HkbRecord, user_data: Any):
            self.on_update_pointer(
                sender, source_record, pointer, pointer.get_value(), target.object_id
            )

            # If the binding set pointer changed we should regenerate all attribute widgets
            vbs_type_id = self.beh.type_registry.find_first_type_by_name(
                "hkbVariableBindingSet"
            )
            if pointer.type_id == vbs_type_id:
                self._clear_attributes()
                self._update_attributes(self.selected_node)
                self.reveal_attribute(path)

        def open_pointer_dialog():
            select_object(
                self.beh, pointer.subtype, on_pointer_selected, include_derived=True
            )

        with dpg.group(horizontal=True, filter_key=attribute, tag=tag) as group:
            ptr_input = dpg.add_input_text(
                default_value=pointer.get_value(),
                readonly=True,
                width=-30,  # TODO is there no better solution?
            )
            dpg.bind_item_theme(ptr_input, style.pointer_attribute_theme)
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=open_pointer_dialog,
            )

        return group

    def _create_attribute_widget_vector4(
        self,
        source_record: HkbRecord,
        array: HkbArray,
        path: str,
        tag: str = 0,
    ) -> str:
        attribute = path.split("/")[-1]

        with dpg.group(filter_key=attribute, tag=tag) as group:
            for i, comp in zip(range(4), "xyzw"):
                value = array[i].get_value()
                dpg.add_input_double(
                    label=comp,
                    default_value=value,
                    callback=self.on_attribute_update,
                    user_data=array[i],
                )

        return group

    def _create_attribute_widget_array_buttons(
        self,
        source_record: HkbRecord,
        array: HkbArray,
        path: str,
        tag: str = 0,
    ) -> str:
        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        def delete_last_item(sender, app_data, user_data) -> None:
            # TODO deleting an item may invalidate variable bindings!
            idx = len(array) - 1
            undo_manager.on_update_array_item(array, idx, array[idx], None)
            del array[idx]

            # Records potentially contain pointers which will affect the graph
            Handler = get_value_handler(self.beh.type_registry, array.element_type_id)
            if Handler in (HkbRecord, HkbPointer):
                self.canvas.regenerate()

            dpg.delete_item(f"{self.tag}_attribute_{path}:{idx}")

        def append_item() -> None:
            subtype = array.element_type_id
            Handler = get_value_handler(self.beh.type_registry, subtype)
            new_item = Handler.new(self.beh, subtype)

            self.logger.info(
                "Added new element of type %s to array %s->%s",
                subtype,
                source_record.object_id,
                path,
            )

            idx = len(array)
            undo_manager.on_update_array_item(array, idx, None, new_item)
            array.append(new_item)

            # TODO doesn't work for some reason
            # self._create_attribute_widget(
            #     source_record,
            #     new_item,
            #     f"{path}:{idx}",
            #     before=tag,  # insert before the buttons
            # )

            # TODO this will close the unfolded rows, we should have a "reveal_attribute" function
            self._clear_attributes()
            self._update_attributes(self.selected_node)
            self.reveal_attribute(f"{path}:{idx}")

        with dpg.group(horizontal=True, tag=tag) as button_group:
            # Deleting from the end doesn't require index updates,
            # especially for potential bindings
            dpg.add_button(
                label="(-)",
                small=True,
                callback=delete_last_item,
            )
            dpg.add_button(
                label="(+)",
                small=True,
                callback=append_item,
            )

        return button_group

    def _create_attribute_widget_simple(
        self,
        source_record: HkbRecord,
        value: XmlValueHandler,
        path: str,
        tag: str = 0,
    ) -> str:
        attribute = path.split("/")[-1]

        with bindable_attribute(filter_key=attribute, tag=tag, width=-1) as bindable:
            if isinstance(value, HkbString):
                dpg.add_input_text(
                    filter_key=attribute,
                    callback=self.on_attribute_update,
                    user_data=value,
                    default_value=value.get_value(),
                )

            elif isinstance(value, HkbInteger):
                current_record = source_record
                if "/" in path:
                    # The path will become deeper if and only if we descended into
                    # record fields, so the parent object will always be a record
                    parent_path = "/".join(path.split("/")[:-1])
                    current_record = source_record.get_path_value(parent_path)

                enum = get_hkb_enum(
                    self.beh.type_registry, current_record.type_id, path
                )

                if enum:

                    def on_enum_change(sender: str, new_value: str, val: HkbInteger):
                        int_value = enum[new_value].value
                        self.on_attribute_update(sender, int_value, val)

                    dpg.add_combo(
                        [e.name for e in enum],
                        filter_key=attribute,
                        callback=on_enum_change,
                        user_data=value,
                        default_value=enum(value.get_value()).name,
                    )
                else:
                    dpg.add_input_int(
                        filter_key=attribute,
                        callback=self.on_attribute_update,
                        user_data=value,
                        default_value=value.get_value(),
                    )

            elif isinstance(value, HkbFloat):
                dpg.add_input_double(
                    filter_key=attribute,
                    callback=self.on_attribute_update,
                    user_data=value,
                    default_value=value.get_value(),
                )

            elif isinstance(value, HkbBool):
                dpg.add_checkbox(
                    filter_key=attribute,
                    callback=self.on_attribute_update,
                    user_data=value,
                    default_value=value.get_value(),
                )

            else:
                self.logger.error(
                    "Cannot handle attribute %s (%s) of object %s",
                    path,
                    value,
                    source_record.object_id,
                )
                self.logger.debug("The offending record is \n%s", source_record.xml())
                return None

        return bindable

    def on_attribute_update(
        self, sender, new_value: Any, handler: XmlValueHandler
    ) -> None:
        # The handler may throw if the new value is not appropriate
        undo_manager.on_update_value(handler, handler.get_value(), new_value)
        handler.set_value(new_value)
        dpg.set_value(sender, new_value)

    def undo(self) -> None:
        if not undo_manager.can_undo():
            return

        self.notification(f"Undo: {undo_manager.top()}")
        undo_manager.undo()

        # TODO so expensive....
        self.canvas.regenerate()
        self._clear_attributes()
        self._update_attributes(self.selected_node)
        # TODO reveal currently revealed attribute

    def redo(self) -> None:
        if not undo_manager.can_redo():
            return

        self.notification(f"Redo: {undo_manager.top()}")
        undo_manager.redo()

        # TODO so expensive....
        self.canvas.regenerate()
        self._clear_attributes()
        self._update_attributes(self.selected_node)
        # TODO reveal currently revealed attribute

    def _create_attribute_menu(
        self,
        widget: str,
        source_record: HkbRecord,
        value: XmlValueHandler,
        path: str,
    ):
        # Should never happen, but development is funny ~
        if value is None:
            self.logger.error(
                "%s->%s is None, this should never happen",
                source_record.object_id,
                path,
            )
            return

        is_simple = isinstance(value, (HkbString, HkbFloat, HkbInteger, HkbBool))

        if is_simple:
            bound_attributes = get_bound_attributes(self.beh, source_record)
            bound_var_idx = bound_attributes.get(path, -1)

        # Create a context menu for the widget
        with dpg.popup(widget):
            dpg.add_text(path.split("/")[-1])
            type_name = self.beh.type_registry.get_name(value.type_id)
            dpg.add_text(f"<{type_name}>")

            if is_simple and bound_var_idx >= 0:
                bound_var_name = self.beh.get_variable_name(bound_var_idx)
                dpg.add_text(
                    f"bound: {bound_var_name}",
                    color=style.pink,
                )

            # Copy & paste
            dpg.add_separator()
            if is_simple:
                # Not clear how cut should work on records and lists
                dpg.add_selectable(
                    label="Cut",
                    callback=self._cut_value,
                    user_data=(widget, path, value),
                )

            dpg.add_selectable(
                label="Copy",
                callback=self._copy_value,
                user_data=(widget, path, value),
            )
            dpg.add_selectable(
                label="Copy Path",
                callback=self._copy_value_path,
                user_data=(widget, path, value),
            )
            dpg.add_selectable(
                label="Copy XML",
                callback=self._copy_value_xml,
                user_data=(widget, path, value),
            )
            dpg.add_selectable(
                label="Paste",
                callback=self._paste_value,
                user_data=(widget, path, value),
            )

            if isinstance(value, HkbPointer):

                def create_object_for_pointer():
                    obj = HkbRecord.new(
                        self.beh, value.subtype, object_id=self.beh.new_id()
                    )
                    with undo_manager.combine():
                        undo_manager.on_create_object(self.beh, obj)
                        self.beh.add_object(obj)
                        self.on_update_pointer(
                            widget,
                            source_record,
                            value,
                            value.get_value(),
                            obj.object_id,
                        )

                def go_to_pointer():
                    oid = value.get_value()
                    if not oid or oid == "object0":
                        return

                    node = self.canvas.nodes[oid]
                    self.canvas.select(node)
                    # TODO not quite right yet, not sure why
                    self.look_at(node.x + node.width / 2, node.y + node.width / 2)

                dpg.add_separator()

                dpg.add_selectable(
                    label="New object",
                    callback=create_object_for_pointer,
                )
                dpg.add_selectable(label="Go to", callback=go_to_pointer)

            if is_simple:
                set_bindable_attribute_state(self.beh, widget, bound_var_idx)

                def _bind_variable(sender, app_data, user_data):
                    # deselect the selectable
                    dpg.set_value(sender, False)
                    select_variable_to_bind(*user_data)

                def _unbind_variable(sender, app_data, user_data):
                    # deselect the selectable
                    dpg.set_value(sender, False)
                    unbind_attribute(*user_data)

                def _on_binding_established(
                    sender, data: tuple[int, str], user_data: Any
                ):
                    # If a new binding set was created the graph will change
                    # binding_var, binding_set_id = data
                    # TODO graph needs to be rebuilt
                    self.canvas.regenerate()
                    self._clear_attributes()
                    self._update_attributes(self.selected_node)
                    self.reveal_attribute(path)

                dpg.add_separator()
                dpg.add_selectable(
                    label="Bind Variable",
                    callback=lambda s, a, u: _bind_variable(s, a, u),
                    user_data=(
                        self.beh,
                        source_record,
                        widget,
                        path,
                        bound_var_idx,
                        _on_binding_established,
                    ),
                )

                dpg.add_selectable(
                    label="Clear binding",
                    callback=lambda s, a, u: _unbind_variable(s, a, u),
                    user_data=(self.beh, source_record, widget, path),
                )

    def _cut_value(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        val = dpg.get_value(widget)

        try:
            pyperclip.copy(str(val))
        except pyperclip.PyperclipException as e:
            self.logger.error("Cut value failed: %s", e)
            # Not nice, but clearing the value without having copied it is worse
            return

        default_val = type(val)()
        self.on_attribute_update(widget, default_val, value)

        self.logger.info("Cut value:\n%s", val)

    def _copy_value(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        val = dpg.get_value(widget)
        self._copy_to_clipboard(val)

    def _copy_value_xml(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        val = value.xml().strip().strip("\n")
        self._copy_to_clipboard(val)

    def _copy_value_path(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        self._copy_to_clipboard(path)

    def _paste_value(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        data = pyperclip.paste()

        try:
            xml = ET.fromstring(data)
            new_value = type(value)(xml, value.type_id)
        except:
            new_value = data

        try:
            self.on_attribute_update(widget, new_value, value)
        except Exception as e:
            self.logger.error("Paste value to %s failed: %s", widget, e)
            return

    def _copy_to_clipboard(self, data: str):
        try:
            pyperclip.copy(data)
        except:
            pass

        self.logger.debug("Copied value:\n%s", data)

    # Common use cases
    def get_active_statemachine(self, for_object_id: str = None) -> HkbRecord:
        if not for_object_id:
            if self.canvas.graph:
                for_object_id = self.canvas.root
            elif self.selected_node:
                for_object_id = self.selected_node.id

        if not for_object_id:
            return None

        sm_type = self.beh.type_registry.find_first_type_by_name("hkbStateMachine")
        obj = self.beh.objects[for_object_id]
        if obj.type_id == sm_type:
            return obj

        return next(
            (sm for sm in self.beh.find_parents_by_type(for_object_id, sm_type)), None
        )

    # Not used right now, but might be useful at some point
    def get_active_cmsg(self) -> HkbRecord:
        if self.selected_node:
            candidates = [self.selected_node.id]
            cmsg_type = self.beh.type_registry.find_first_type_by_name(
                "CustomManualSelectorGenerator"
            )

            while candidates:
                oid = candidates.pop()
                obj = self.beh.objects[oid]
                if obj.type_id == cmsg_type:
                    return obj

                candidates.extend(self.canvas.graph.predecessors(oid))

        return None

    def jump_to_object(self, object_id: str):
        # Open the associated state machine
        root = self.get_active_statemachine(object_id)

        if not root:
            self.logger.info("Object %s is not part of any StateMachine", object_id)
            return

        self._on_root_selected("", True, root.object_id)

        # Reveal the node in the state machine graph
        path = nx.shortest_path(self.canvas.graph, root.object_id, object_id)
        self._clear_attributes()
        self.canvas.show_node_path(path)

    def open_variable_editor(self):
        tag = f"{self.tag}_edit_variables_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str, int, int, int]):
            if self.beh.find_variable(new_value[0], None):
                self.logger.warning(
                    "A variable named '%s' already exists (%d)", new_value[0], idx
                )

            undo_manager.on_create_variable(self.beh, new_value, idx)
            self.beh.create_variable(*new_value, idx)

        def on_update(
            idx: int,
            old_value: tuple[str, int, int, int],
            new_value: tuple[str, int, int, int],
        ):
            undo_manager.on_update_variable(self.beh, idx, old_value, new_value)
            self.beh.delete_variable(idx)
            self.beh.create_variable(*new_value, idx=idx)

        def on_delete(idx: int):
            # TODO list variable bindings affected by this
            undo_manager.on_delete_variable(self.beh, idx)
            self.beh.delete_variable(idx)

        edit_simple_array_dialog(
            [
                (v.name, v.vtype.value, v.vmin, v.vmax)
                for v in self.beh.get_variables(full_info=True)
            ],
            ["Name", "Type", "Min", "Max"],
            title="Edit Variables",
            help=[
                "Warning:",
                "Variables are referenced by their index in VariableBindingSets.",
                "Deleting or inserting names may invalidate your behavior.",
            ],
            choices={
                1: [v.name for v in VariableType],
            },
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            tag=tag,
        )

    def open_event_editor(self):
        tag = f"{self.tag}_edit_events_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str]):
            new_value = new_value[0]
            if self.beh.find_event(new_value, None):
                self.logger.warning(
                    "An event named '%s' already exists (%d)", new_value, idx
                )

            undo_manager.on_create_event(self.beh, new_value, idx)
            self.beh.create_event(new_value, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: tuple[str]):
            old_value = old_value[0]
            new_value = new_value[0]

            undo_manager.on_update_event(self.beh, idx, old_value, new_value)
            self.beh.rename_event(idx, new_value)

        def on_delete(idx: int):
            # TODO list transition infos affected by this
            undo_manager.on_delete_event(self.beh, idx)
            self.beh.delete_event(idx)

        edit_simple_array_dialog(
            [(e,) for e in self.beh.get_events()],
            ["Name"],
            title="Edit Events",
            help=[
                "Warning:",
                "Events are referenced by their index in TransitionInfos.",
                "Deleting or inserting events may invalidate your behavior.",
            ],
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            tag=tag,
        )

    def open_animation_names_editor(self):
        tag = f"{self.tag}_edit_animation_names_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str]):
            new_value = new_value[0]
            if self.beh.find_animation(new_value, None):
                self.logger.warning(
                    "An animation named '%s' already exists (%d)", new_value, idx
                )

            undo_manager.on_create_animation(self.beh, new_value, idx)
            self.beh.create_animation(new_value, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: tuple[str]):
            old_value = old_value[0]
            new_value = new_value[0]

            undo_manager.on_update_animation(self.beh, idx, old_value, new_value)
            self.beh.rename_animation(idx, new_value)

        def on_delete(idx: int):
            # TODO list generators affected by this
            undo_manager.on_delete_animation(self.beh, idx)
            self.beh.delete_animation(idx)

        edit_simple_array_dialog(
            [(a,) for a in self.beh.get_animations()],
            ["Name"],
            title="Edit Animation Names",
            help=[
                "Warning:",
                "Animation names are referenced by their index in ClipGenerators.",
                "Deleting or inserting names may invalidate your behavior.",
            ],
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            tag=tag,
        )

    def open_array_aliases_editor(self):
        # TODO open dialog, update alias manager
        pass

    def load_bone_names(self) -> None:
        file_path = open_file_dialog(
            title="Select Skeleton", filetypes={"Skeleton files": "*.xml"}
        )

        if file_path:
            try:
                self.logger.info("Loading bone names from %s", file_path)
                self.alias_manager.load_bone_names(self.beh, file_path)
            except ValueError as e:
                self.logger.error("Loading bone names failed: %s", e, exc_info=True)

    def open_search_dialog(self, close_after_select: bool = False):
        tag = f"{self.tag}_search_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def jump(sender: str, object_id: str, user_data: Any):
            self.jump_to_object(object_id)

            if close_after_select:
                dpg.delete_item(dialog)

        dialog = search_objects_dialog(self.beh, jump, tag=tag)

    def open_stategraph_dialog(self):
        tag = f"{self.tag}_state_graph_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        active_sm = self.get_active_statemachine()
        open_state_graph_viewer(
            self.beh,
            active_sm.object_id if active_sm else None,
            jump_callback=lambda s, a, u: self.jump_to_object(a.object_id),
            tag=tag,
        )

    def open_register_clip_dialog(self):
        tag = f"{self.tag}_register_clip_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def on_clip_registered(sender: str, ids: tuple[str, str], user_data: Any):
            clip_id, cmsg_id = ids
            self.jump_to_object(clip_id)

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(clip_id)
                self.add_pinned_object(cmsg_id)

        open_register_clip_dialog(
            self.beh,
            on_clip_registered,
            tag=tag,
        )

    def open_create_cmsg_dialog(self):
        tag = f"{self.tag}_create_cmsg_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        def on_cmsg_created(sender: str, ids: tuple[str, str, str], user_data: Any):
            cmsg_id, clipgen_id, stateinfo_id = ids
            self.jump_to_object(cmsg_id)

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(cmsg_id)
                self.add_pinned_object(clipgen_id)
                self.add_pinned_object(stateinfo_id)

        active_sm = self.get_active_statemachine()
        open_new_cmsg_dialog(
            self.beh,
            on_cmsg_created,
            active_statemachine_id=active_sm.object_id if active_sm else None,
            tag=tag,
        )

    def create_object_dialog(self):
        tag = f"{self.tag}_create_object_dialog"
        if dpg.does_item_exist(tag):
            dpg.focus_item(tag)
            return

        # TODO
