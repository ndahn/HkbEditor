from typing import Any
import os
import logging
import traceback
from threading import Thread
import textwrap
import time
import pyperclip
from dearpygui import dearpygui as dpg
import networkx as nx

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import (
    XmlValueHandler,
    HkbRecord,
    HkbPointer,
)
from hkb_editor.hkb.skeleton import load_skeleton_bones
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.templates.glue import get_templates

from .graph_editor import GraphEditor, Node
from .attributes_widget import AttributesWidget
from .dialogs import (
    open_file_dialog,
    edit_simple_array_dialog,
    search_objects_dialog,
    open_state_graph_viewer,
)
from .workflows.undo import undo_manager
from .workflows.aliases import AliasManager, AliasMap
from .workflows.create_cmsg import create_cmsg_dialog
from .workflows.register_clip import register_clip_dialog
from .workflows.bone_mirror import bone_mirror_dialog
from .workflows.create_object import create_object_dialog
from .workflows.apply_template import apply_template_dialog
from .helpers import make_copy_menu
from . import style


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        # Setup the root logger first before calling super, which will instantiate
        # a new logger
        class LogHandler(logging.Handler):
            def emit(this, record):
                self.notification(record.getMessage(), record.levelno)

        logging.root.addHandler(LogHandler())

        self.beh: HavokBehavior = None
        self.alias_manager = AliasManager()
        self.attributes_widget: AttributesWidget = None
        self.pinned_objects_table: str = None
        self.min_notification_severity = logging.INFO
        self.loaded_skeleton_path: str = None

        super().__init__(tag)

    def notification(self, message: str, severity: int = logging.INFO) -> None:
        if severity < self.min_notification_severity:
            return

        lines = [
            subline for line in message.split("\n") for subline in textwrap.wrap(line)
        ]

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
        self.clear_attributes()
        self.remove_all_pinned_objects()
        self.close_all_dialogs()

        try:
            self.beh = HavokBehavior(file_path)
            filename = os.path.basename(file_path)
            dpg.configure_viewport(0, title=f"HkbEditor - {filename}")

            self._reload_templates()
            self._set_menus_enabled(True)
            
            dpg.focus_item(f"{self.tag}_roots_filter")
        except Exception as e:
            details = traceback.format_exception_only(e)
            self.logger.error(
                f"Loading behavior failed: {details[0]}\nSee log for details!"
            )
            raise e
        finally:
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

        # Edit
        with dpg.menu(label="Edit", enabled=False, tag=f"{self.tag}_menu_edit"):
            dpg.add_menu_item(
                label="Undo (ctrl-z)", callback=lambda: self.attributes_widget.undo()
            )
            dpg.add_menu_item(
                label="Redo (ctrl-y)", callback=lambda: self.attributes_widget.redo()
            )

            dpg.add_separator()

            with dpg.menu(label="Aliases"):
                dpg.add_menu_item(
                    label="Load Bone Names...", callback=self.load_bone_names
                )

            dpg.add_separator()

            dpg.add_menu_item(label="Variables...", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events...", callback=self.open_event_editor)
            dpg.add_menu_item(
                label="Animations...", callback=self.open_animation_names_editor
            )

            dpg.add_separator()

            dpg.add_menu_item(
                label="StateInfo Graph...",
                callback=lambda: self.open_stategraph_dialog(),
            )

            dpg.add_separator()

            dpg.add_menu_item(label="Pin Lost Objects", callback=self.pin_lost_objects)

            dpg.add_menu_item(label="Find Object...", callback=self.open_search_dialog)

        # Workflows
        with dpg.menu(
            label="Workflows", enabled=False, tag=f"{self.tag}_menu_workflows"
        ):
            dpg.add_menu_item(
                label="Create Object...",
                callback=self.open_create_object_dialog,
            )
            dpg.add_menu_item(
                label="Register Clip...", callback=self.open_register_clip_dialog
            )
            dpg.add_menu_item(
                label="Create CMSG...", callback=self.open_create_cmsg_dialog
            )

            dpg.add_separator()

            dpg.add_menu_item(
                label="Generate Bone Mirror Map...",
                callback=self.open_bone_mirror_map_dialog,
            )

        # Templates
        with dpg.menu(
            label="Templates", enabled=False, tag=f"{self.tag}_menu_templates"
        ):
            dpg.add_separator(tag=f"{self.tag}_menu_templates_bottom")
            dpg.add_menu_item(label="Reload Templates", callback=self._reload_templates)

        self._create_settings_menu()

        dpg.add_separator()
        self._create_dpg_menu()

    def _reload_templates(self) -> None:
        menu = f"{self.tag}_menu_templates"
        dpg.delete_item(menu, children_only=True)

        templates = get_templates()

        for template_file, (categories, template) in templates.items():
            parent = menu
            path = ""
            for cat in categories:
                path += cat + "/"
                if not dpg.does_item_exist(f"{self.tag}_menu_templates_cat_{path}"):
                    parent = dpg.add_menu(
                        label=cat,
                        tag=f"{self.tag}_menu_templates_cat_{path}",
                        parent=parent,
                    )

            if path:
                parent = f"{self.tag}_menu_templates_cat_{path}"

            dpg.add_menu_item(
                label=template,
                callback=lambda s, a, u: self.open_apply_template_dialog(u),
                user_data=template_file,
                parent=parent,
            )

        dpg.add_separator(tag=f"{self.tag}_menu_templates_bottom", parent=menu)
        dpg.add_menu_item(
            label="Reload Templates", parent=menu, callback=self._reload_templates
        )

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
        func(f"{self.tag}_menu_templates")

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_None, callback=self._on_key_press)

    def get_supported_file_extensions(self):
        return {"Behavior XML": "*.xml"}

    def _setup_content(self) -> None:
        super()._setup_content()

        # Replace the standard table with our more complex widget
        dpg.delete_item(f"{self.tag}_attributes_table_container")

        with dpg.child_window(border=False, parent=f"{self.tag}_attributes_window"):
            self.attributes_widget = AttributesWidget(
                self.alias_manager,
                jump_callback=self.jump_to_object,
                on_graph_changed=self.canvas.regenerate,
                on_value_changed=self._on_value_changed,
                tag=f"{self.tag}_attributes_widget",
            )

        # Update the input box for filtering the table
        self.attributes_table = self.attributes_widget.attributes_table
        dpg.set_item_user_data(f"{self.tag}_attribute_filter", self.attributes_table)

        # Pinned objects
        with dpg.window(
            label="Pinned Objects",
            autosize=True,
            no_close=True,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
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
                    dpg.add_table_column(label="ID", width_stretch=True)
                    dpg.add_table_column(label="Name", width_stretch=True)
                    dpg.add_table_column(label="Type", width_stretch=True)

        with dpg.item_handler_registry(tag=f"{self.tag}_pin_registry"):
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right, callback=self.open_pin_menu
            )

    def add_pinned_object(self, object_id: HkbRecord | str) -> None:
        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        if dpg.does_item_exist(f"{self.tag}_pin_{object_id}"):
            # Already pinned
            return

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

    def remove_all_pinned_objects(self) -> None:
        dpg.delete_item(f"{self.tag}_pinned_objects_table", children_only=True, slot=1)

    def pin_lost_objects(self) -> None:
        for oid in self.find_lost_objects():
            self.add_pinned_object(oid)

    def open_pin_menu(self, sender: str, app_data: str, user_data: Any) -> None:
        _, selectable = app_data
        object_id = dpg.get_item_user_data(selectable)
        pinned_obj: HkbRecord = self.beh.retrieve_object(object_id)

        def show_attributes():
            self.canvas.deselect()
            self.attributes_widget.set_record(pinned_obj)

        # Pin context menu
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_saved_settings=True,
            autosize=True,
        ) as popup:
            dpg.add_selectable(
                label="Unpin",
                callback=lambda s, a, u: self.remove_pinned_object(u),
                user_data=object_id,
            )
            dpg.add_selectable(
                label="Unpin All",
                callback=self.remove_all_pinned_objects,
            )
            dpg.add_selectable(
                label="Jump To",
                callback=lambda s, a, u: self.jump_to_object(u),
                user_data=object_id,
            )
            dpg.add_selectable(label="Show Attributes", callback=show_attributes)
            make_copy_menu(pinned_obj)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))

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

    def open_node_menu(self, node: Node):
        obj = self.beh.objects.get(node.id)
        if not obj:
            return []

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text(node.id, color=style.blue)
            dpg.add_separator()

            make_copy_menu(obj)

            dpg.add_selectable(
                label="Delete",
                callback=lambda s, a, u: self._delete_node(u),
                user_data=node,
            )

            dpg.add_separator()

            dpg.add_selectable(
                label="Pin Object",
                callback=lambda s, a, u: self.add_pinned_object(u),
                user_data=obj,
            )

    def _delete_node(self, node: Node) -> None:
        record = self.beh.objects.get(node.id)
        if record:
            # TODO remove all references to record
            self.beh.remove_object(record.object_id)
            undo_manager.on_delete_object(self.beh, record)

            parent = next(self.canvas.graph.predecessors(record.object_id), None)
            if parent:
                self.selected_node = self.canvas.nodes[parent]

            self.regenerate_all()
            self.logger.warning(f"{record} removed, but references may still exist")

    def _copy_to_clipboard(self, data: str):
        try:
            pyperclip.copy(data)
            self.logger.debug("Copied value:\n%s", data)
        except Exception as e:
            self.logger.warning(f"Copying value failed: {e}", exc_info=e)

    def _on_value_changed(
        self,
        sender,
        handler: XmlValueHandler,
        change: tuple[Any, Any],
    ) -> None:
        old_value, new_value = change

        if isinstance(handler, HkbPointer):
            if old_value:
                # Could be an entirely new pointer object with no previous value
                self.add_pinned_object(old_value)
                self.logger.info("Pinned previous object %s", old_value)

            if new_value not in self.canvas.nodes:
                # Edges have changed, previous node may not be connected anymore, new
                # node may not be part of the current statemachine graph yet, ...
                self.regenerate_all()
            else:
                # Changing a pointer will change the rendered graph
                self.canvas.regenerate()

    def _update_attributes(self, node):
        record = self.beh.objects[node.id]
        self.attributes_widget.set_record(record)

    def regenerate_all(self) -> None:
        root_id = self.get_active_statemachine().object_id
        selected = self.selected_node
        self._on_root_selected("", True, root_id)
        if selected:
            self.canvas.select(selected)

    def clear_attributes(self):
        self.attributes_widget.clear()

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

    def find_lost_objects(self) -> list[str]:
        # TODO open a dialog to select the object or SM to search from
        root_sm = next(self.beh.query("name:Root"), None)
        if not root_sm:
            self.logger.error("Could not locate Root SM")
            return []

        graph = self.beh.build_graph(root_sm.object_id)
        lost = [n for n in self.beh.objects.keys() if n not in graph]
        return lost

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
        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        # Open the associated state machine
        root = self.get_active_statemachine(object_id)

        if not root:
            self.logger.info("Object %s is not part of any StateMachine", object_id)
            return

        self._on_root_selected("", True, root.object_id)

        # Reveal the node in the state machine graph
        path = nx.shortest_path(self.canvas.graph, root.object_id, object_id)
        self.clear_attributes()
        self.canvas.show_node_path(path)

    def open_variable_editor(self):
        tag = f"{self.tag}_edit_variables_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str, int, int, int]):
            if self.beh.find_variable(new_value[0], None):
                self.logger.warning(
                    "A variable named '%s' already exists (%d)", new_value[0], idx
                )

            if idx not in (-1, len(self.beh._variables)):
                # TODO show warning dialog listing affected variables
                pass

            self.beh.create_variable(*new_value, idx)
            undo_manager.on_create_variable(self.beh, new_value, idx)

        def on_update(
            idx: int,
            old_value: tuple[str, int, int, int],
            new_value: tuple[str, int, int, int],
        ):
            self.beh.delete_variable(idx)
            self.beh.create_variable(*new_value, idx=idx)
            undo_manager.on_update_variable(self.beh, idx, old_value, new_value)

        def on_delete(idx: int):
            # TODO list variable bindings affected by this
            self.beh.delete_variable(idx)
            undo_manager.on_delete_variable(self.beh, idx)

        edit_simple_array_dialog(
            [
                (v.name, v.vtype.value, v.vmin, v.vmax)
                for v in self.beh.get_variables(full_info=True)
            ],
            ["Name", "Type", "Min", "Max"],
            title="Edit Variables",
            help=[
                ("Warning:", style.orange),
                (
                    "Variables are referenced by their index in VariableBindingSets.",
                    style.light_blue,
                ),
                (
                    "Deleting or inserting names may invalidate your behavior.",
                    style.light_blue,
                ),
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
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str]):
            new_value = new_value[0]
            if self.beh.find_event(new_value, None):
                self.logger.warning(
                    "An event named '%s' already exists (%d)", new_value, idx
                )

            if idx not in (-1, len(self.beh._variables)):
                # TODO show warning dialog listing affected variables
                pass

            self.beh.create_event(new_value, idx)
            undo_manager.on_create_event(self.beh, new_value, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: tuple[str]):
            old_value = old_value[0]
            new_value = new_value[0]

            self.beh.rename_event(idx, new_value)
            undo_manager.on_update_event(self.beh, idx, old_value, new_value)

        def on_delete(idx: int):
            # TODO list transition infos affected by this
            self.beh.delete_event(idx)
            undo_manager.on_delete_event(self.beh, idx)

        edit_simple_array_dialog(
            [(e,) for e in self.beh.get_events()],
            ["Name"],
            title="Edit Events",
            help=[
                ("Warning:", style.orange),
                (
                    "Events are referenced by their index in TransitionInfos.",
                    style.light_blue,
                ),
                (
                    "Deleting or inserting events may invalidate your behavior.",
                    style.light_blue,
                ),
            ],
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            tag=tag,
        )

    def open_animation_names_editor(self):
        tag = f"{self.tag}_edit_animation_names_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: tuple[str]):
            new_value = new_value[0]
            if self.beh.find_animation(new_value, None):
                self.logger.warning(
                    "An animation named '%s' already exists (%d)", new_value, idx
                )

            self.beh.create_animation(new_value, idx)
            undo_manager.on_create_animation(self.beh, new_value, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: tuple[str]):
            old_value = old_value[0]
            new_value = new_value[0]

            self.beh.rename_animation(idx, new_value)
            undo_manager.on_update_animation(self.beh, idx, old_value, new_value)

        def on_delete(idx: int):
            # TODO list generators affected by this
            self.beh.delete_animation(idx)
            undo_manager.on_delete_animation(self.beh, idx)

        edit_simple_array_dialog(
            [(a,) for a in self.beh.get_animations()],
            ["Name"],
            title="Edit Animation Names",
            help=[
                ("Warning:", style.orange),
                (
                    "Animation names are referenced by their index in ClipGenerators.",
                    style.light_blue,
                ),
                (
                    "Deleting or inserting names may invalidate your behavior.",
                    style.light_blue,
                ),
            ],
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            tag=tag,
        )

    def open_search_dialog(self):
        tag = f"{self.tag}_search_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        search_objects_dialog(
            self.beh,
            pin_callback=lambda s, a, u: self.add_pinned_object(a),
            jump_callback=lambda s, a, u: self.jump_to_object(a),
            tag=tag,
        )

    def open_stategraph_dialog(self):
        tag = f"{self.tag}_state_graph_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        active_sm = self.get_active_statemachine()
        open_state_graph_viewer(
            self.beh,
            active_sm.object_id if active_sm else None,
            jump_callback=lambda s, a, u: self.jump_to_object(a.object_id),
            tag=tag,
        )

    def open_create_object_dialog(self):
        tag = f"{self.tag}_create_object_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_object_created(sender: str, new_object: HkbRecord, user_data: Any):
            # This is a bit ugly, but so is adding more stuff to new_object
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(new_object.object_id)

        create_object_dialog(
            self.beh,
            self.alias_manager,
            on_object_created,
            tag=tag,
        )

    def open_register_clip_dialog(self):
        tag = f"{self.tag}_register_clip_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_clip_registered(sender: str, records: tuple[HkbRecord, HkbRecord], user_data: Any):
            cmsg, clip = records

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(cmsg)
                self.add_pinned_object(clip)
            
            self.jump_to_object(clip)

        register_clip_dialog(
            self.beh,
            on_clip_registered,
            tag=tag,
        )

    def open_create_cmsg_dialog(self):
        tag = f"{self.tag}_create_cmsg_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_cmsg_created(
            sender: str,
            records: tuple[HkbRecord, HkbRecord, HkbRecord],
            user_data: Any,
        ):
            stateinfo, cmsg, clip = records

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(stateinfo)
                self.add_pinned_object(cmsg)
                self.add_pinned_object(clip)

            self.jump_to_object(cmsg)

        active_sm = self.get_active_statemachine()
        create_cmsg_dialog(
            self.beh,
            on_cmsg_created,
            active_statemachine_id=active_sm.object_id if active_sm else None,
            tag=tag,
        )

    def load_bone_names(self) -> None:
        self.loaded_skeleton_path = None

        file_path = open_file_dialog(
            title="Select Skeleton", filetypes={"Skeleton files": "*.xml"}
        )

        if not file_path:
            return

        try:
            self.logger.info("Loading bone names from %s", file_path)

            bones = load_skeleton_bones(file_path)
            self.loaded_skeleton_path = file_path

            boneweights_type_id = self.beh.type_registry.find_first_type_by_name(
                "hkbBoneWeightArray"
            )
            basepath = "boneWeights"
            aliases = AliasMap()

            for idx, bone in enumerate(bones):
                aliases.add(bone, f"{basepath}:{idx}", boneweights_type_id, None)

            # Insert left so that these aliases take priority
            self.alias_manager.aliases.insert(0, aliases)
        except ValueError as e:
            self.logger.error("Loading bone names failed: %s", e, exc_info=True)

    def open_bone_mirror_map_dialog(self):
        tag = f"{self.tag}_bone_mirror_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        bone_mirror_dialog(self.loaded_skeleton_path, tag=tag)

    def open_apply_template_dialog(self, template_file: str):
        tag = f"{self.tag}_apply_template_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_template_finished(
            sender: str, new_objects: list[HkbRecord], user_data: Any
        ):
            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                for obj in new_objects:
                    self.add_pinned_object(obj.object_id)

        apply_template_dialog(
            self.beh,
            template_file,
            on_template_finished,
            tag=tag,
        )

    def close_all_dialogs(self) -> None:
        dialogs = [
            "_edit_variables_dialog",
            "_edit_events_dialog",
            "_edit_animation_names_dialog",
            "_search_dialog",
            "_state_graph_dialog",
            "_create_object_dialog",
            "_register_clip_dialog",
            "_create_cmsg_dialog",
            "_bone_mirror_dialog",
            "_apply_template_dialog",
        ]

        for dlg in dialogs:
            dpg.delete_item(f"{self.tag}{dlg}")
