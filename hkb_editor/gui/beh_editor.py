from typing import Any, Callable
from dearpygui import dearpygui as dpg

from .graph_editor import GraphEditor, Node
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

    def _do_write_to_file(self, file_path):
        # TODO
        pass

    def exit_app(self):
        # TODO ask for confirmation
        super().exit_app()

    def create_menu(self):
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open...", callback=self.open_file)
            dpg.add_menu_item(
                label="Save...",
                callback=self.save_file,
                enabled=False,
                tag="menu_file_save",
            )
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self.exit_app)

        with dpg.menu(label="Edit"):
            dpg.add_menu_item(label="Variables", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events", callback=self.open_event_editor)
            dpg.add_menu_item(label="Animations", callback=self.open_animation_editor)

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
        return []

    def on_node_menu_item_selected(node: Node, selected_item: str) -> None:
        pass

    def on_node_selected(self, node: Node) -> None:
        pass

    def _get_bound_attributes(self, record: HkbRecord) -> dict[str, int]:
        if not isinstance(record, HkbRecord):
            return {}

        try:
            binding_ptr: HkbPointer = record.variableBindingSet
            bindings: HkbArray = self.beh.objects[binding_ptr.get].bindings
        except (AttributeError, KeyError):
            return {}

        ret = {}
        bnd: HkbRecord
        for bnd in bindings.get_value():
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
        self._create_attribute_widget(key, val, bound, key)

    def _create_attribute_widget(
        self,
        key: str,
        val: XmlValueHandler,
        bound_attributes: dict[str, int],
        path: str = "",
    ):
        def _update_node_attribute(
            sender, new_value: Any, handler: XmlValueHandler
        ) -> None:
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
            # TODO passing None is not supported yet
            new_item = Handler.new(None)

            idx = len(array)
            array.append(new_item)

            self._create_attribute_widget(
                f"{key}:{idx}",
                new_item,
                bound_attributes,
                f"{path}:{idx}",
            )

        def _bind_attribute(sender, app_data, path: str) -> None:
            # TODO open dialog with variables, replace sender widget with bound item widget
            pass

        def _unbind_attribute(sender, app_data, path: str) -> None:
            # TODO remove from bound_attributes, replace sender widget with regular one
            pass

        if isinstance(val, HkbPointer):
            # NOTE probably bindable, but let's maybe not :)
            with dpg.group(horizontal=True, filter_key=key):
                ptr_input = dpg.add_input_text(
                    default_value=val.get_value(),
                    enabled=False,
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: self._select_pointer(*u),
                    user_data=(ptr_input, val, _update_node_attribute, val.subtype),
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
                            f"{key}:{idx}", subval, bound_attributes, f"{path}:{idx}"
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
                        subkey, subval, bound_attributes, f"{path}/{subkey}"
                    )

        else:
            widget = None

            # All bindable objects
            if path in bound_attributes:
                var_idx = bound_attributes[path]
                var_name = self.beh.events[var_idx]

                # TODO set theme
                widget = dpg.add_input_text(
                    filter_key=key,
                    enabled=False,
                    default_value=f"<{var_name}>",
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
                    dpg.add_button(
                        label="Bind",
                        callback=_bind_attribute,
                        user_data=path,
                    )
                    dpg.add_button(
                        label="Clear binding",
                        callback=_unbind_attribute,
                        user_data=path,
                    )

    def _select_pointer(
        self,
        value_widget: str,
        ptr: HkbPointer,
        callback: Callable[[str, Any, XmlValueHandler], None],
        target_type_id: str = None,
    ) -> None:
        selected = ptr.get_value()

        def on_filter_update(sender, app_data, user_data):
            dpg.delete_item(table, children_only=True, slot=1)

            # TODO come up with a filter syntax like "id=... & type=..."
            filt: str = dpg.get_value(sender)
            matches = [
                obj
                for obj in self.beh.objects.values()
                if target_type_id in (None, obj.type_id)
                and (
                    filt in obj.id or filt in obj.type_id or filt in obj.get("name", "")
                )
            ]

            if len(matches) > 100:
                return

            for obj in sorted(matches, key=lambda o: o.id):
                name = obj.get("name")
                type_name = self.beh.type_registry.get_name(obj.type_id)
                with dpg.table_row(parent=table, user_data=obj.id):
                    dpg.add_selectable(
                        label=obj.id,
                        span_columns=True,
                        default_value=obj.id == selected,
                        callback=on_select,
                        user_data=obj.id,
                        tag=f"{self.tag}_pointer_selectable_{obj.id}",
                    )
                    dpg.add_text(name)
                    dpg.add_text(type_name)

        def on_select(sender, app_data, object_id: str):
            nonlocal selected
            selected = object_id

            # Deselect all other selectables
            for row in dpg.get_item_children(table, slot=1):
                if dpg.get_item_user_data(row) != object_id:
                    for cell in dpg.get_item_children(row, slot=1):
                        if dpg.get_item_type(cell) == "mvAppItemType::mvSelectable":
                            dpg.set_value(cell, False)

        def on_okay():
            callback(value_widget, selected, ptr)
            dpg.delete_item(dialog)

        def on_cancel():
            dpg.delete_item(dialog)

        with dpg.window(
            width=600,
            height=400,
            label="Select Pointer",
            modal=True,
            on_close=lambda: dpg.delete_item(dialog),
        ) as dialog:
            # Way too many options, instead fill the table according to user input
            dpg.add_input_text(
                hint="Find Object...",
                callback=on_filter_update,
            )

            with dpg.table(
                delay_search=True,
                # no_host_extendX=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                # no_host_extendY=True,
                height=320,
            ) as table:
                dpg.add_table_column(label="ID")
                dpg.add_table_column(label="Name")
                dpg.add_table_column(label="Type")

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=on_okay,
                )
                dpg.add_button(
                    label="Cancel",
                    callback=on_cancel,
                )

    # Fleshing out common use cases here
    def open_variable_editor(self):
        # TODO append to variableNames array
        pass

    def open_event_editor(self):
        pass

    def open_animation_editor(self):
        pass

    def wizard_create_generator(self, parent_id: str):
        # TODO a wizard that lets the user create a new generator and attach it to another node
        pass
