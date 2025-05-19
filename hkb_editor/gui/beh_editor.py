from typing import Any
from xml.etree import ElementTree as ET
from dearpygui import dearpygui as dpg
import pyperclip

from .graph_editor import GraphEditor, Node
from .dialogs import (
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
from hkb.behavior import HavokBehavior
from hkb.hkb_types import (
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


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        super().__init__(tag)

        self.beh: HavokBehavior = None

    def _do_load_from_file(self, file_path: str):
        self.beh = HavokBehavior(file_path)
        self._set_menus_enabled(True)

    def _do_write_to_file(self, file_path):
        self.beh.tree.write(file_path)

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

    def create_menu(self):
        self._create_file_menu()

        dpg.add_separator()
        with dpg.menu(label="Edit", enabled=False, tag=f"{self.tag}_menu_edit"):
            dpg.add_menu_item(label="Undo (ctrl-z)", callback=self.undo)
            dpg.add_menu_item(label="Redo (ctrl-y)", callback=self.redo)
            dpg.add_separator()
            dpg.add_menu_item(label="Variables...", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events...", callback=self.open_event_editor)
            dpg.add_menu_item(
                label="Animations...", callback=self.open_animation_editor
            )

        dpg.add_separator()
        self._create_dpg_menu()

    def _set_menus_enabled(self, enabled: bool) -> None:
        func = dpg.enable_item if enabled else dpg.disable_item
        func(f"{self.tag}_menu_edit")

    def get_supported_file_extensions(self):
        return [("Behavior XML", ".xml")]

    def get_roots(self) -> list[str]:
        sm_type = self.beh.type_registry.find_type_by_name("hkbStateMachine")
        return [obj.object_id for obj in self.beh.find_objects_by_type(sm_type)]

    def _on_root_selected(self, sender: str, app_data: str, node_id: str) -> None:
        self.logger.info("Building graph for node %s", node_id)
        self.graph = self.beh.build_graph(node_id)
        super()._on_root_selected(sender, app_data, node_id)

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        obj: HkbRecord = self.beh.objects[node.id]
        # TODO return v instead of v.get_value()
        return {k: v for k, v in obj.get_value().items()}

    def set_node_attribute(self, node: Node, key: str, val: Any) -> None:
        obj: HkbRecord = self.beh.objects[node.id]
        # TODO implement setitem
        setattr(obj, key, val)

    def get_node_frontpage(self, node_id: str) -> list[str]:
        obj = self.beh.objects[node_id]
        try:
            return [
                obj.name.get_value(),
                node_id,
                self.beh.type_registry.get_name(obj.type_id),
            ]
        except AttributeError:
            return [
                node_id,
                self.beh.type_registry.get_name(obj.type_id),
            ]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return self.beh.objects[node_id].name.get_value()

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

    def on_node_selected(self, node: Node) -> None:
        pass

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
        attribute = path.split("/")[-1]
        widget = tag

        if isinstance(value, HkbRecord):
            with table_tree_node(
                attribute, table=f"{self.tag}_attributes_table", folded=True, tag=tag
            ):
                widget = get_row_node_item(tag)
                for subkey, subval in value.get_value().items():
                    self._create_attribute_widget(
                        source_record, subval, f"{path}/{subkey}"
                    )

        elif isinstance(value, HkbArray):
            with table_tree_node(
                attribute, table=f"{self.tag}_attributes_table", folded=True, tag=tag
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
                dpg.add_text(attribute)

        else:
            with table_tree_leaf(
                table=f"{self.tag}_attributes_table",
            ):
                self._create_attribute_widget_simple(source_record, value, path, tag)
                dpg.add_text(attribute)

        
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
            # Update the graph
            pointer.set_value(new_value)

            try:
                self.graph.add_edge(source_record.object_id, new_value)
                self.graph.remove_edge(source_record.object_id, pointer.get_value())
            except:
                pass

            self.on_attribute_update(ptr_widget, new_value, pointer)

            # Changing a pointer will change the rendered graph
            self._regenerate_canvas()

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
        attribute = path.split("/")[-1]

        def delete_last_item(sender, app_data, user_data) -> None:
            # TODO this may invalidate variable bindings!
            del array[len(array) - 1]

            # Records potentially contain pointers which will affect the graph
            Handler = get_value_handler(array.element_type_id)
            if Handler in (HkbRecord, HkbPointer):
                self._regenerate_canvas()

            # TODO this is a bit expensive, but managing index updates is just so tedious
            self._clear_attributes()
            self._update_attributes(self.selected_node)

        def append_item() -> None:
            subtype = array.element_type_id
            Handler = get_value_handler(subtype)
            new_item = Handler.new(subtype)

            self.logger.info(
                "Added new element of type %s to array %s->%s",
                subtype,
                source_record.object_id,
                path,
            )

            idx = len(array)
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
                self.logger.debug(
                    "The offending record is \n%s" ,source_record.xml()
                )
                return None

        return bindable

    def on_attribute_update(
        self, sender, new_value: Any, handler: XmlValueHandler
    ) -> None:
        # TODO create and manage undo history
        handler.set_value(new_value)
        dpg.set_value(sender, new_value)

    def undo(self) -> None:
        # TODO undo change, show notification
        pass

    def redo(self) -> None:
        # TODO
        pass

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
                path
            )
            return

        is_simple = isinstance(value, (HkbString, HkbFloat, HkbInteger, HkbBool))

        # Create a context menu for the widget
        with dpg.popup(widget):
            dpg.add_text(path.split("/")[-1])
            dpg.add_text(f"<{value.type_id}>")
            dpg.add_separator()

            # TODO
            if is_simple:
                dpg.add_selectable(label="Cut", callback=None)
                dpg.add_selectable(label="Copy", callback=None)
            
            dpg.add_selectable(label="Copy as XML", callback=None)

            if is_simple:
                dpg.add_selectable(label="Paste", callback=None)

            if is_simple:
                # TODO add to common menu with copy/cut/paste
                bound_attributes = get_bound_attributes(self.beh, source_record)
                bound_var_idx = bound_attributes.get(path, -1)
                set_bindable_attribute_state(self.beh, widget, bound_var_idx)

                def on_binding_established(sender, selected_idx: int, user_data: Any):
                    # If a new binding set was created the graph will change

                    # TODO if a binding set was created we need to add it to the graph!

                    self._regenerate_canvas()
                    self._clear_attributes()
                    self._update_attributes(self.selected_node)

                dpg.add_separator()
                dpg.add_selectable(
                    label="Bind Variable",
                    callback=lambda s, a, u: select_variable_to_bind(*u),
                    user_data=(
                        self.beh,
                        source_record,
                        widget,
                        path,
                        bound_var_idx,
                        on_binding_established,
                    ),
                )

                dpg.add_selectable(
                    label="Clear binding",
                    callback=lambda s, a, u: unbind_attribute(*u),
                    user_data=(self.beh, source_record, widget, path),
                )

    def _cut_value(self, sender, app_data, user_data: tuple[str, XmlValueHandler]) -> None:
        widget, _ = user_data
        val = dpg.get_value(widget)
        pyperclip.copy(str(val))
        dpg.set_value(type(val)())

    def _copy_value(self, sender, app_data, user_data: tuple[str, XmlValueHandler]) -> None:
        widget, _ = user_data
        pyperclip.copy(str(dpg.get_value(widget)))

    def _copy_value_xml(self, sender, app_data, user_data: tuple[str, XmlValueHandler]) -> None:
        _, value = user_data
        pyperclip.copy(value.xml())

    def _paste_value(self, sender, app_data, user_data: tuple[str, XmlValueHandler]) -> None:
        widget, value = user_data
        data = pyperclip.paste()
        
        try:
            xml = ET.fromstring(data)
            new_value = type(value)(xml, value.type_id)
        except:
            new_value = data
        
        try:
            value.set_value(new_value)
            dpg.set_value(widget, value.get_value())
        except Exception as e:
            self.logger.error("Paste value to %s failed: %s", widget, e)
            return

    # Fleshing out common use cases here
    def open_variable_editor(self):
        edit_simple_array_dialog(
            self.beh.variables,
            "Edit Variables",
        )

    def open_event_editor(self):
        edit_simple_array_dialog(
            self.beh.events,
            "Edit Events",
        )

    def open_animation_editor(self):
        edit_simple_array_dialog(self.beh.animations, "Edit Animations")

    def wizard_create_generator(self, parent_id: str):
        # TODO a wizard that lets the user create a new generator and attach it to another node
        pass
