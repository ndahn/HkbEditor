from typing import Any, Callable
from dearpygui import dearpygui as dpg

from .graph_editor import GraphEditor, Node
from .dialogs.select_pointer import select_pointer
from .dialogs.edit_simple_array import edit_simple_array
from .dialogs.select_simple_array_item import select_simple_array_item
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
        # TODO
        pass

    def exit_app(self):
        # TODO ask for confirmation
        super().exit_app()

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

    def _get_variable_binding_set(self, record: HkbRecord) -> HkbRecord:
        if not isinstance(record, HkbRecord):
            return None

        try:
            # TODO we could create a specialized VariableBindingSet subclass
            binding_ptr: HkbPointer = record.variableBindingSet
            return self.beh.objects[binding_ptr.get]
        except (AttributeError, KeyError):
            return None

    def _get_bound_attributes(self, record: HkbRecord) -> dict[str, int]:
        binding_set = self._get_variable_binding_set(record)
        if not binding_set:
            return {}

        ret = {}
        bnd: HkbRecord
        for bnd in binding_set.bindings:
            var_path = bnd.memberPath.get()
            var_idx = bnd.variableIndex.get()
            binding_type = bnd.bindingType.get()
            if binding_type != 0:
                self.logger.error(
                    "Unknown binding type %i (%s:%i)", binding_type, var_path, var_idx
                )
            else:
                ret[var_path] = var_idx

        return ret

    def _add_attribute(self, key: str, val: Any, node: Node) -> None:
        obj = self.beh.objects.get(node.id)
        bound = self._get_bound_attributes(obj)
        self._create_attribute_widget(obj, key, val, bound, key)

    def _create_attribute_widget(
        self,
        source_record: HkbRecord,
        key: str,
        val: XmlValueHandler,
        bound_attributes: dict[str, int],
        path: str = "",
    ):
        def _update_node_attribute(
            sender, new_value: Any, handler: XmlValueHandler
        ) -> None:
            self.on_attribute_changed(path, handler, new_value, handler.get_value())
            handler.set_value(new_value)
            dpg.set_value(sender, new_value)

        def _delete_array_elem(
            sender, app_data, user_data: tuple[HkbArray, int]
        ) -> None:
            # TODO note that this may screw up variable binding sets!
            array, idx = user_data
            pass

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

        def _bind_attribute(sender, bound_var_idx: int, user_data: tuple[HkbRecord, str]) -> None:
            record, path = user_data
            binding_set = self._get_variable_binding_set(source_record)

            if binding_set is None:
                ptr_type_id = source_record.get_field_type("variableBindingSet")
                bindings_type_id = self.beh.type_registry.get_subtype(ptr_type_id)
                binding_id = self.beh.new_object_id()
                binding_set = HkbRecord.new(bindings_type_id, None, binding_id)

                # Assign pointer to source record
                record.variableBindingSet.set_value(binding_id)
                # TODO update pointer attribute widget
                # TODO redraw graph

                self.beh.objects[binding_id] = binding_set
                # TODO append to xml, too!

            bindings: HkbArray = binding_set.bindings
            bnd: HkbRecord

            for bnd in bindings:
                if bnd.memberPath == path:
                    bnd.variableIndex = bound_var_idx
                    break
            else:
                bindings.append(
                    HkbRecord.new(
                        bindings.element_type_id,
                        {
                            "memberPath": path,
                            "variableIndex": bound_var_idx,
                            "bitIndex": -1,
                            "bindingType": 0,
                        },
                    )
                )

            # TODO replace sender with a bound-attribute widget

        def _unbind_attribute(sender, app_data, path: str) -> None:
            # TODO remove from bound_attributes, replace sender widget with regular one
            binding_set = self._get_variable_binding_set(source_record)

            if binding_set is None:
                bindings_type_id = source_record.get_field_type("bindings")
                binding_id = self.beh.new_object_id()
                binding_set = HkbRecord.new(bindings_type_id, {}, binding_id)

                self.beh.objects[binding_id] = binding_set
                # TODO append to xml, too!

            bindings: HkbArray = binding_set.bindings
            bnd: HkbRecord

            for idx, bnd in enumerate(bindings):
                if bnd.memberPath == path:
                    del bindings[idx]
                    break
            else:
                return

            # TODO replace sender with a regular widget

        if isinstance(val, HkbPointer):
            # NOTE probably bindable, but let's maybe not :)
            with dpg.group(horizontal=True, filter_key=key):
                ptr_input = dpg.add_input_text(
                    default_value=val.get_value(),
                    readonly=True,
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: select_pointer(*u),
                    user_data=(
                        self.beh,
                        _update_node_attribute,
                        ptr_input,
                        val,
                    ),
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
            widget = None

            # All bindable objects
            bound_var_idx = bound_attributes.get(path, -1)
            if bound_var_idx >= 0:
                bound_var_name = self.beh.events[bound_var_idx]

                # TODO set theme
                widget = dpg.add_input_text(
                    filter_key=key,
                    enabled=False,
                    default_value=f"<{bound_var_name}>",
                )

            elif isinstance(val, HkbString):
                widget = dpg.add_input_text(
                    filter_key=key,
                    callback=lambda s, a, u: self._select_pointer(*u),
                    user_data=(widget, val, _update_node_attribute),
                    default_value=val.get_value(),
                )

            elif isinstance(val, HkbInteger):
                widget = dpg.add_input_int(
                    filter_key=key,
                    callback=lambda s, a, u: self._select_pointer(*u),
                    user_data=(widget, val, _update_node_attribute),
                    default_value=val.get_value(),
                )

            elif isinstance(val, HkbFloat):
                widget = dpg.add_input_double(
                    filter_key=key,
                    callback=lambda s, a, u: self._select_pointer(*u),
                    user_data=(widget, val, _update_node_attribute),
                    default_value=val.get_value(),
                )

            elif isinstance(val, HkbBool):
                dpg.add_checkbox(
                    filter_key=key,
                    callback=lambda s, a, u: self._select_pointer(*u),
                    user_data=(widget, val, _update_node_attribute),
                    default_value=val.get_value(),
                )

            else:
                self.logger.error("Cannot handle attribute %s (%s)", key, val)

            # Add menu to bind to variable
            if widget:
                with dpg.popup(dpg.last_item()):
                    dpg.add_selectable(
                        label="Bind",
                        callback=lambda s, a, u: select_simple_array_item(*u),
                        user_data=(
                            self.beh.variables,
                            _bind_attribute,
                            widget,
                            bound_var_idx,
                            (source_record, path),
                        ),
                    )

                    if bound_var_idx >= 0:
                        dpg.add_selectable(
                            label="Clear binding",
                            callback=_unbind_attribute,
                            user_data=(widget, None, path),
                        )

    def on_attribute_changed(
        self, path: str, handler: XmlValueHandler, new_value: Any, prev_value: Any
    ) -> None:
        # TODO add to undo history, show notification
        pass

    def undo(self) -> None:
        # TODO
        pass

    def redo(self) -> None:
        # TODO
        pass

    # Fleshing out common use cases here
    def open_variable_editor(self):
        edit_simple_array(
            self.beh.variables,
            "Edit Variables",
        )

    def open_event_editor(self):
        edit_simple_array(
            self.beh.events,
            "Edit Events",
        )

    def open_animation_editor(self):
        edit_simple_array(self.beh.animations, "Edit Animations")

    def wizard_create_generator(self, parent_id: str):
        # TODO a wizard that lets the user create a new generator and attach it to another node
        pass
