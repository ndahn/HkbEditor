from typing import Any, Callable
from xml.etree import ElementTree as ET
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.behavior import HavokBehavior
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

from .graph_editor import GraphEditor, Node
from .widgets import (
    select_pointer_dialog,
    edit_simple_array_dialog,
)
from .table_tree import table_tree_node, table_tree_leaf, get_row_node_item
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
from . import style


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        super().__init__(tag)

        self.beh: HavokBehavior = None
        self.alias_manager = AliasManager()

    def _do_load_from_file(self, file_path: str):
        self.beh = HavokBehavior(file_path)
        self._set_menus_enabled(True)

    def _do_write_to_file(self, file_path):
        self.beh.save_to_file(file_path)

    def exit_app(self):
        with dpg.window(
            label="Exit?",
            modal=True,
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
            dpg.add_menu_item(label="Undo (ctrl-z)", enabled=False, callback=self.undo)
            dpg.add_menu_item(label="Redo (ctrl-y)", enabled=False, callback=self.redo)
            dpg.add_separator()
            dpg.add_menu_item(label="Load bone names...", callback=self.load_bone_names)
            dpg.add_separator()
            dpg.add_menu_item(label="Variables...", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events...", callback=self.open_event_editor)
            dpg.add_menu_item(
                label="Animations...", callback=self.open_animation_editor
            )

        with dpg.menu(
            label="Workflows", enabled=False, tag=f"{self.tag}_menu_workflows"
        ):
            dpg.add_menu_item(label="Load skeleton...", callback=self.load_bone_names)
            # TODO enable
            dpg.add_menu_item(label="Attribute aliases...", enabled=False)
            dpg.add_menu_item(
                label="Create CMSG...", enabled=False, callback=self.create_cmsg
            )

        dpg.add_separator()
        self._create_dpg_menu()

    def _set_menus_enabled(self, enabled: bool) -> None:
        func = dpg.enable_item if enabled else dpg.disable_item
        func(f"{self.tag}_menu_file_save")
        func(f"{self.tag}_menu_file_save_as")
        func(f"{self.tag}_menu_edit")
        func(f"{self.tag}_menu_workflows")

    def get_supported_file_extensions(self):
        return {"Behavior XML": "*.xml"}

    def get_roots(self) -> list[str]:
        sm_type = self.beh.type_registry.find_type_by_name("hkbStateMachine")
        roots = [
            (obj["name"].get_value(), obj.object_id)
            for obj in self.beh.find_objects_by_type(sm_type)
        ]
        return [r[1] for r in sorted(roots)]

    def _on_root_selected(self, sender: str, app_data: str, node_id: str) -> None:
        self.logger.info("Building graph for node %s", node_id)
        self.graph = self.beh.build_graph(node_id)
        super()._on_root_selected(sender, app_data, node_id)

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        obj: HkbRecord = self.beh.objects[node.id]
        # TODO return v instead of v.get_value()
        return {k: v for k, v in obj.get_value().items()}

    def get_node_frontpage(self, node_id: str) -> list[str]:
        obj = self.beh.objects[node_id]
        try:
            return [
                (obj["name"].get_value(), style.yellow),
                (node_id, style.blue),
                (self.beh.type_registry.get_name(obj.type_id), style.white),
            ]
        except AttributeError:
            return [
                (node_id, style.blue),
                (self.beh.type_registry.get_name(obj.type_id), style.white),
            ]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return self.beh.objects[node_id]["name"].get_value()

    def get_node_menu_items(self, node: Node) -> list[str]:
        obj = self.beh.objects.get(node.id)
        if not obj:
            return []

        type_name = self.beh.type_registry.get_name(obj.type_id)

        # TODO show useful node actions
        # "hkbStateMachine"
        # "hkbVariableBindingSet"
        # "hkbLayerGenerator"
        # "CustomManualSelectorGenerator":
        # "hkbClipGenerator"
        # "hkbScriptGenerator"

        return []

    def on_node_menu_item_selected(node: Node, selected_item: str) -> None:
        # TODO implement useful node actions
        pass

    def get_canvas_menu_items(self):
        # TODO
        return super().get_canvas_menu_items()

    def on_canvas_menu_item_selected(self, selected_item):
        # TODO
        return super().on_canvas_menu_item_selected(selected_item)

    def on_node_selected(self, node: Node) -> None:
        pass

    def on_update_pointer(self, widget: str, record: HkbRecord, pointer: HkbPointer, old_value: str, new_value: str) -> None:
        # Update the graph first
        try:
            self.graph.add_edge(record.object_id, new_value)
            self.graph.remove_edge(record.object_id, old_value)
        except:
            pass

        self.on_attribute_update(widget, new_value, pointer)

        # Changing a pointer will change the rendered graph
        self._regenerate_canvas()

    def _add_attribute_row_contents(self, attribute: str, val: Any, node: Node) -> None:
        obj = self.beh.objects.get(node.id)
        self._create_attribute_widget(obj, val, attribute)

    def _create_attribute_widget(
        self,
        source_record: HkbRecord,
        value: XmlValueHandler,
        path: str,
    ):
        tag = f"{self.tag}_attribute_{path}"
        widget = tag

        label = self.alias_manager.get_attribute_alias(source_record, path)
        if label is None:
            label = path.split("/")[-1]
            label_color = style.white
        else:
            label_color = style.green

        if isinstance(value, HkbRecord):
            # TODO label_color
            with table_tree_node(
                label, table=f"{self.tag}_attributes_table", folded=True, tag=tag
            ):
                widget = get_row_node_item(tag)
                for subkey, subval in value.get_value().items():
                    self._create_attribute_widget(
                        source_record, subval, f"{path}/{subkey}"
                    )

        elif isinstance(value, HkbArray):
            # TODO label_color
            # TODO special handlers for e.g. hkVector4, HkQuaternion, etc.
            with table_tree_node(
                label, table=f"{self.tag}_attributes_table", folded=True, tag=tag
            ):
                widget = get_row_node_item(tag)
                for idx, subval in enumerate(value):
                    self._create_attribute_widget(
                        source_record, subval, f"{path}:{idx}"
                    )
                    # self._create_attribute_widget_array_item(
                    #    source_record, subval, f"{path}:{idx}"
                    # )
                with table_tree_leaf(
                    table=f"{self.tag}_attributes_table",
                    tag=f"{self.tag}_attribute_{path}_arraybuttons",
                ):
                    self._create_attribute_widget_array_buttons(
                        source_record, value, path
                    )

        elif isinstance(value, HkbPointer):
            with table_tree_leaf(
                table=f"{self.tag}_attributes_table",
            ):
                self._create_attribute_widget_pointer(source_record, value, path, tag)
                dpg.add_text(label, color=label_color)

        else:
            with table_tree_leaf(
                table=f"{self.tag}_attributes_table",
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
    ) -> str:
        attribute = path.split("/")[-1]

        def on_pointer_select(sender, new_value: str, ptr_widget: str):
            self.on_update_pointer(
                ptr_widget, 
                source_record, 
                pointer, 
                pointer.get_value(), 
                new_value
            )

            # If the binding set pointer changed we should regenerate all attribute widgets
            vbs_type_id = self.beh.type_registry.find_type_by_name(
                "hkbVariableBindingSet"
            )
            if pointer.type_id == vbs_type_id:
                self._clear_attributes()
                self._update_attributes(self.selected_node)

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
                callback=lambda s, a, u: select_pointer_dialog(*u),
                user_data=(self.beh, on_pointer_select, pointer, ptr_input),
            )

        return group

    def _create_attribute_widget_array_buttons(
        self,
        source_record: HkbRecord,
        array: HkbArray,
        path: str,
        tag: str = 0,
    ) -> str:
        def delete_last_item(sender, app_data, user_data) -> None:
            # TODO this may invalidate variable bindings!
            undo_manager.on_update_array_item(array, -1, array[-1], None)
            del array[-1]

            # Records potentially contain pointers which will affect the graph
            Handler = get_value_handler(self.beh.type_registry, array.element_type_id)
            if Handler in (HkbRecord, HkbPointer):
                self._regenerate_canvas()

            # TODO this is a bit expensive, but managing index updates is just so tedious
            self._clear_attributes()
            self._update_attributes(self.selected_node)

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

            self._create_attribute_widget(
                source_record,
                new_item,
                f"{path}:{idx}",
            )

            # Records potentially contain pointers which will affect the graph
            if isinstance(new_item, (HkbRecord, HkbPointer)):
                self._regenerate_canvas()

            # TODO appending to the end is easy, inserting in between requires index updates
            self._clear_attributes()
            self._update_attributes(self.selected_node)

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
        # TODO show notification
        undo_manager.undo()

    def redo(self) -> None:
        # TODO show notification
        undo_manager.redo()

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
            # TODO add to common menu with copy/cut/paste
            bound_attributes = get_bound_attributes(self.beh, source_record)
            bound_var_idx = bound_attributes.get(path, -1)

        # Create a context menu for the widget
        with dpg.popup(widget):
            dpg.add_text(path.split("/")[-1])
            type_name = self.beh.type_registry.get_name(value.type_id)
            dpg.add_text(f"<{type_name}>")

            if is_simple and bound_var_idx >= 0:
                bound_var_name = self.beh.variables[bound_var_idx]
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
                    user_data=(widget, value),
                )

            dpg.add_selectable(
                label="Copy",
                callback=self._copy_value,
                user_data=(widget, value),
            )
            dpg.add_selectable(
                label="Copy as XML",
                callback=self._copy_value_xml,
                user_data=(widget, value),
            )
            dpg.add_selectable(
                label="Paste",
                callback=self._paste_value,
                user_data=(widget, value),
            )

            if isinstance(value, HkbPointer):
                def on_new_object(sender, object: HkbRecord, user_data):
                    with undo_manager.combine():
                        self.beh.add_object(object)
                        self.on_update_pointer(
                            widget, 
                            source_record, 
                            value, 
                            value.get_value(), 
                            object.object_id,
                        )

                dpg.add_separator()
                dpg.add_selectable(
                    label="New object",
                    callback=lambda s, a, u: self.open_create_object_dialog(*u),
                    user_data=(value.subtype, on_new_object, None),
                )

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
                    self._regenerate_canvas()
                    self._clear_attributes()
                    self._update_attributes(self.selected_node)

                dpg.add_separator()
                dpg.add_selectable(
                    label="Bind Variable",
                    callback=lambda s, a, u: _bind_variable,
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
                    callback=lambda s, a, u: _unbind_variable,
                    user_data=(self.beh, source_record, widget, path),
                )

    def _cut_value(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, value = user_data
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

        widget, _ = user_data
        val = dpg.get_value(widget)

        try:
            pyperclip.copy(str(val))
        except:
            pass

        # Pyperclip (or rather copy/paste) can be a bit finnicky, so
        self.logger.info("Copied value:\n%s", val)

    def _copy_value_xml(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        _, value = user_data
        val = value.xml().strip().strip("\n")

        try:
            pyperclip.copy(val)
        except:
            pass

        self.logger.info("Copied value:\n%s", val)

    def _paste_value(
        self, sender, app_data, user_data: tuple[str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, value = user_data
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

    # Fleshing out common use cases here
    def open_variable_editor(self):
        edit_simple_array_dialog(
            self.beh,
            self.beh.variables,
            "Edit Variables",
        )

    def open_event_editor(self):
        edit_simple_array_dialog(
            self.beh,
            self.beh.events,
            "Edit Events",
        )

    def open_animation_editor(self):
        edit_simple_array_dialog(
            self.beh, 
            self.beh.animations, 
            "Edit Animations"
        )

    def open_array_aliases_editor(self):
        # TODO open dialog, update alias manager
        pass

    def load_bone_names(self) -> None:
        file_path = open_file_dialog(
            title="Select Skeleton", filetypes=[("Skeleton files", "*.xml")]
        )

        if file_path:
            try:
                self.logger.info("Loading bone names from %s", file_path)
                self.alias_manager.load_bone_names(self.beh, file_path)
            except ValueError as e:
                self.logger.error("Loading bone names failed: %s", e, exc_info=True)

    def open_create_object_dialog(self, type_id: str, callback: Callable[[str, int, Any], None], user_data: Any = None) -> None:
        # TODO create a proper dialog here
        obj = HkbRecord.new(self.beh, type_id, object_id=self.beh.new_id())
        
        if "name" in obj.fields:
            obj["name"] = "<new object>"

        if callback:
            callback(None, obj, user_data)

    def create_cmsg(self):
        # TODO a wizard that lets the user create a new generator and attach it to another node
        pass
