from typing import Any
from dearpygui import dearpygui as dpg

from .graph_editor import GraphEditor, Node
from .dialogs import (
    select_pointer_dialog,
    edit_simple_array_dialog,
)
from .workflows.bind_attribute import (
    bindable_attribute,
    select_variable_to_bind,
    get_bound_attributes,
    set_bindable_attribute_state,
    unbind_attribute
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
        self.roots: list[HkbRecord] = None

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
                dpg.add_text(f"It has been {self.last_save:.0f}s since your last save. Exit?")
            
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
        self.roots = list(self.beh.find_objects_by_type(sm_type))
        return self.roots

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

    def _add_attribute(self, key: str, val: Any, node: Node) -> None:
        obj = self.beh.objects.get(node.id)
        bound = get_bound_attributes(self.beh, obj)
        self._create_attribute_widget(obj, key, val, bound, key)

    def _create_attribute_widget(
        self,
        source_record: HkbRecord,
        key: str,
        val: XmlValueHandler,
        bound_attributes: dict[str, int],
        path: str = "",
    ):
        def update_node_attribute(
            sender, new_value: Any, handler: XmlValueHandler
        ) -> None:
            self.on_attribute_changed(path, handler, new_value, handler.get_value())
            handler.set_value(new_value)
            dpg.set_value(sender, new_value)

        def _delete_array_elem(
            sender, app_data, user_data: tuple[HkbArray, int]
        ) -> None:
            array, idx = user_data
            
            # TODO this may screw up variable binding sets!
            del array[idx]

            # Records potentially contain pointers which will affect the graph
            Handler = get_value_handler(array.element_type_id)
            if Handler in (HkbRecord, HkbPointer):
                self._regenerate_canvas()

            # TODO this is a bit expensive, managing index updates is just so tedious
            self._clear_attributes()
            self._update_attributes(self.selected_node)

        def _add_array_elem(array_group: str, app_data, array: HkbArray) -> None:
            subtype = array.element_type_id
            Handler = get_value_handler(subtype)
            new_item = Handler.new(subtype)

            idx = len(array)
            array.append(new_item)

            self._create_attribute_widget(
                source_record,
                f"{key}:{idx}",
                new_item,
                bound_attributes,
                f"{path}:{idx}",
            )
            
            # Records potentially contain pointers which will affect the graph
            if isinstance(new_item, (HkbRecord, HkbPointer)):
                self._regenerate_canvas()

            # TODO appending to the end is easy, inserting in between requires index updates
            self._clear_attributes()
            self._update_attributes(self.selected_node)

        # NOTE pointers are probably bindable, but let's maybe not :)
        if isinstance(val, HkbPointer):
            def on_pointer_select(sender, new_value: str, ptr_widget: str):
                # Update the graph
                try:
                    self.graph.add_edge(source_record.id, new_value)
                    self.graph.remove_edge(source_record.id, val.get_value())
                except:
                    pass

                update_node_attribute(ptr_widget, new_value, val)

                # Changing a pointer will change the rendered graph
                self._regenerate_canvas()

                # If the binding set pointer changed we should regenerate all attribute widgets
                vbs_type_id = self.beh.type_registry.find_type_by_name("hkbVariableBindingSet")
                if val.type_id == vbs_type_id:
                    self._clear_attributes()
                    self._update_attributes(self.selected_node)
            
            with dpg.group(horizontal=True, filter_key=key):
                ptr_input = dpg.add_input_text(
                    default_value=val.get_value(),
                    readonly=True,
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: select_pointer_dialog(*u),
                    user_data=(self.beh, on_pointer_select, val, ptr_input)
                )

        elif isinstance(val, HkbArray):
            # Organize members in a foldable section
            # NOTE these will all live inside the same table row
            with dpg.tree_node(label=key, filter_key=key) as array_group:
                for idx, subval in enumerate(val.get_value()):
                    with dpg.group(horizontal=True):
                        # Allow deleting elements
                        dpg.add_button(
                            label="(-)",
                            small=True,
                            callback=_delete_array_elem,
                            user_data=(val, idx),
                        )
                        # Descend into the array
                        # Note that array elements can be bound, too, e.g.
                        # "hands:0/controlData/targetPosition"
                        self._create_attribute_widget(
                            source_record,
                            f"{key}:{idx}",
                            subval,
                            bound_attributes,
                            f"{path}:{idx}",
                        )

                    dpg.add_separator()

                # Allow adding elements
                dpg.add_button(
                    label="(+)",
                    small=True,
                    callback=lambda s, a, u: _add_array_elem(*u),
                    user_data=(array_group, key, val),
                )

        elif isinstance(val, HkbRecord):
            # NOTE these will all live inside the same table row
            with dpg.tree_node(label=key, filter_key=key):
                for subkey, subval in val.get_value().items():
                    self._create_attribute_widget(
                        source_record,
                        subkey,
                        subval,
                        bound_attributes,
                        f"{path}/{subkey}",
                    )

        else:
            with bindable_attribute(filter_key=key, tag=f"{self.tag}_{path}") as bindable:
                if isinstance(val, HkbString):
                    dpg.add_input_text(
                        filter_key=key,
                        callback=update_node_attribute,
                        user_data=val,
                        default_value=val.get_value(),
                    )

                elif isinstance(val, HkbInteger):
                    dpg.add_input_int(
                        filter_key=key,
                        callback=update_node_attribute,
                        user_data=val,
                        default_value=val.get_value(),
                    )

                elif isinstance(val, HkbFloat):
                    dpg.add_input_double(
                        filter_key=key,
                        callback=update_node_attribute,
                        user_data=val,
                        default_value=val.get_value(),
                    )

                elif isinstance(val, HkbBool):
                    dpg.add_checkbox(
                        filter_key=key,
                        callback=update_node_attribute,
                        user_data=val,
                        default_value=val.get_value(),
                    )

                else:
                    self.logger.error("Cannot handle attribute %s (%s)", key, val)
                    bindable = None

            # Add menu to bind attribute to variable
            if bindable:
                # TODO add to common menu with copy/cut/paste
                bound_var_idx = bound_attributes.get(path, -1)
                set_bindable_attribute_state(self.beh, bindable, bound_var_idx)

                def on_binding_established(sender, selected_idx: int, user_data: Any):
                    # If a new binding set was created the graph will change

                    # TODO if a binding set was created we need to add it to the graph!

                    self._regenerate_canvas()
                    self._clear_attributes()
                    self._update_attributes(self.selected_node)

                with dpg.popup(bindable):
                    dpg.add_text(key)
                    dpg.add_separator()

                    dpg.add_selectable(
                        label="Bind",
                        callback=lambda s, a, u: select_variable_to_bind(*u),
                        user_data=(
                            self.beh,
                            source_record,
                            bindable,
                            path,
                            bound_var_idx,
                            on_binding_established,
                        ),
                    )

                    dpg.add_selectable(
                        label="Clear binding",
                        callback=lambda s, a, u: unbind_attribute(*u),
                        user_data=(self.beh, source_record, bindable, path),
                    )

    def on_attribute_changed(
        self, path: str, handler: XmlValueHandler, new_value: Any, prev_value: Any
    ) -> None:
        # TODO add to undo history
        pass

    def undo(self) -> None:
        # TODO undo change, show notification
        pass

    def redo(self) -> None:
        # TODO
        pass

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
