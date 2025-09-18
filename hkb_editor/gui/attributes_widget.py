from typing import Any, Type, Callable
import sys
import os
import yaml
import logging
from enum import IntFlag
from lxml import etree as ET
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb import (
    Tagfile,
    HavokBehavior,
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
from hkb_editor.hkb import get_hkb_enum, get_hkb_flags
from hkb_editor.hkb.index_attributes import (
    is_event_attribute,
    is_variable_attribute,
    is_animation_attribute,
)
from hkb_editor.hkb.xml import get_xml_parser
from hkb_editor.templates.common import CommonActionsMixin

from .dialogs import select_object, select_event, select_variable, select_animation
from .table_tree import (
    table_tree_leaf,
    add_lazy_table_tree_node,
    get_row_node_item,
    set_foldable_row_status,
    is_row_visible,
)
from .workflows.bind_attribute import (
    bindable_attribute,
    select_variable_to_bind,
    get_bound_attributes,
    set_bindable_attribute_state,
)
from .workflows.aliases import AliasManager
from .workflows.undo import undo_manager
from .workflows.clone_hierarchy import paste_hierarchy
from .helpers import create_flag_checkboxes, add_paragraphs
from . import style


class AttributesWidget:
    def __init__(
        self,
        alias_manager: AliasManager,
        *,
        jump_callback: Callable[[str], None] = None,
        on_graph_changed: Callable[[], None] = None,
        on_value_changed: Callable[
            [str, XmlValueHandler, tuple[Any, Any]], None
        ] = None,
        pin_object_callback: Callable[[HkbRecord | str], None] = None,
        hide_title: bool = False,
        tag: str = None,
    ):
        if tag in (None, 0, ""):
            tag = dpg.generate_uuid()

        self.alias_manager = alias_manager
        self.tagfile: Tagfile = None
        self.record: HkbRecord = None
        self.jump_callback = jump_callback
        self.on_graph_changed = on_graph_changed
        self.on_value_changed = on_value_changed
        self.pin_object_callback = pin_object_callback
        self.hide_title = hide_title
        self.tag = tag

        self.logger = logging.getLogger()
        self.attributes_table = None

        # Hover explanations for attributes
        expl_file = os.path.join(os.path.dirname(sys.argv[0]), "attributes.yaml")
        if os.path.isfile(expl_file):
            with open(expl_file) as f:
                self.explanations = yaml.safe_load(f)
        else:
            self.explanations = {}

        self._setup_content()

    def set_record(self, record: HkbRecord) -> None:
        self.clear()
        self.tagfile = record.tagfile
        self.record = record

        if record:
            self._update_attributes()

    def set_title(self, title: str) -> None:
        if not title or self.hide_title:
            dpg.hide_item(f"{self.tag}_attributes_title")
        else:
            dpg.set_value(f"{self.tag}_attributes_title", title)
            dpg.show_item(f"{self.tag}_attributes_title")

    def clear(self) -> None:
        self.set_title("Attributes")
        dpg.delete_item(self.attributes_table, children_only=True, slot=1)

    def reveal_attribute(self, path: str) -> None:
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

    def get_explanation(self, path: str) -> str:
        type_expl = self.explanations.get(self.record.type_name)
        if not type_expl:
            type_expl = self.explanations.get("common", {})

        return type_expl.get(path)

    # UI content
    def _setup_content(self) -> None:
        with dpg.group(tag=self.tag):
            dpg.add_text("", tag=f"{self.tag}_attributes_title", color=style.blue)
            with dpg.table(
                delay_search=True,
                no_host_extendX=True,
                resizable=True,
                borders_innerV=True,
                policy=dpg.mvTable_SizingFixedFit,
                header_row=False,
                tag=f"{self.tag}_attributes_table",
            ) as self.attributes_table:
                dpg.add_table_column(label="Value", width_stretch=True)
                dpg.add_table_column(label="Key", width_fixed=True)

    def _update_attributes(self) -> None:
        self.set_title(f"{self.record.object_id} ({self.record.type_name})")

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(self.attributes_table, slot=0):
            dpg.show_item(col)

        for key, val in self.record.get_value().items():
            with dpg.table_row(
                filter_key=key,
                parent=self.attributes_table,
            ):
                self._create_attribute_widget(val, key)

    def regenerate(self):
        # TODO we need to collect the paths that are currently revealed somehow
        revealed = []

        self.clear()
        self._update_attributes()

        for path in revealed:
            self.reveal_attribute(path)

    def _create_attribute_widget(
        self,
        attribute: XmlValueHandler,
        path: str,
        *,
        before: str = 0,
    ):
        tag = f"{self.tag}_attribute_{path}"
        widget = tag
        is_simple = isinstance(attribute, (HkbString, HkbFloat, HkbInteger, HkbBool))

        label = self.alias_manager.get_attribute_alias(self.record, path)
        if label is None:
            label = path.split("/")[-1]
            label_color = style.white
        else:
            label_color = style.green

        def create_label():
            dpg.add_text(label, color=label_color)

            expl = self.get_explanation(path)
            if expl:
                with dpg.tooltip(dpg.last_item()):
                    add_paragraphs(expl, 50)

        if isinstance(attribute, HkbRecord):
            # create items on demand, dpg performance tanks with too many widgets
            def lazy_create_record_attributes(anchor: str):
                for subkey, subval in attribute.get_value().items():
                    self._create_attribute_widget(
                        subval, f"{path}/{subkey}", before=anchor
                    )

            add_lazy_table_tree_node(
                label,
                lazy_create_record_attributes,
                table=self.attributes_table,
                tag=tag,
                before=before,
            )
            widget = get_row_node_item(tag)

        elif isinstance(attribute, HkbArray):
            type_name = self.tagfile.type_registry.get_name(attribute.type_id)
            if type_name in (
                "hkVector4",
                "hkVector4f",
                "hkQuaternion",
                "hkQuaternionf",
            ):
                with table_tree_leaf(
                    table=self.attributes_table,
                    tag=tag,
                    before=before,
                ):
                    widget = self._create_attribute_widget_vector4(attribute, path)

            else:
                # create items on demand, dpg performance tanks with too many widgets
                def lazy_create_array_items(anchor: str):
                    for idx, subval in enumerate(attribute):
                        self._create_attribute_widget(
                            subval, f"{path}:{idx}", before=anchor
                        )

                    with table_tree_leaf(
                        table=self.attributes_table,
                        tag=f"{tag}_arraybuttons",
                        before=anchor,
                    ):
                        self._create_attribute_widget_array_buttons(attribute, path)

                add_lazy_table_tree_node(
                    label,
                    lazy_create_array_items,
                    table=self.attributes_table,
                    tag=tag,
                    before=before,
                )
                widget = get_row_node_item(tag)

        elif isinstance(attribute, HkbPointer):
            with table_tree_leaf(
                table=self.attributes_table,
                tag=tag,
                before=before,
            ):
                widget = self._create_attribute_widget_pointer(attribute, path)
                create_label()

        else:
            FieldFlags = get_hkb_flags(
                self.tagfile.type_registry,
                self.record.type_id,
                path.split("/")[-1],
            )

            if FieldFlags:
                with table_tree_leaf(
                    table=self.attributes_table,
                    before=before,
                ):
                    self._create_attribute_widget_flags(
                        attribute, FieldFlags, path, tag
                    )
                    create_label()
                    is_simple = False
            else:
                with table_tree_leaf(
                    table=self.attributes_table,
                    before=before,
                ):
                    self._create_attribute_widget_simple(attribute, path, tag)
                    create_label()

        self._create_attribute_menu(widget, attribute, path, is_simple)

    def _add_reference_attribute_text(
        self,
        label: str,
        value: str,
        callback: Callable,
        theme: int | str,
        *,
        tag: str = None,
    ) -> str:
        if tag in (0, None, ""):
            tag = f"reference_attribute_{dpg.generate_uuid()}"

        # Embed in another child_window, otherwise the horizontal group will expand too much
        # when placed inside another group
        with dpg.child_window(border=False, auto_resize_y=True):
            with dpg.group(horizontal=True, filter_key=label, tag=tag) as group:
                dpg.add_input_text(
                    default_value=value,
                    readonly=True,
                    width=-30,
                    tag=f"{tag}_input",
                )
                dpg.bind_item_theme(dpg.last_item(), theme)
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=callback,
                )

        return group

    def _add_reference_attribute_int(
        self,
        label: str,
        value: str,
        change_callback: Callable[[str, int, Any], None],
        button_callback: Callable[[str, str, Any], None],
        theme: int | str,
        *,
        tag: str = None,
    ) -> str:
        if tag in (0, None, ""):
            tag = f"reference_attribute_{dpg.generate_uuid()}"

        # Embed in another child_window, otherwise the horizontal group will expand too much
        # when placed inside another group
        with dpg.child_window(border=False, auto_resize_y=True):
            with dpg.group(horizontal=True):
                dpg.add_input_int(
                    filter_key=label,
                    width=-30,
                    callback=change_callback,
                    default_value=value,
                )
                dpg.bind_item_theme(dpg.last_item(), theme)
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=button_callback,
                )

    def _create_attribute_widget_pointer(
        self,
        pointer: HkbPointer,
        path: str,
    ) -> str:
        label = path.split("/")[-1]

        def on_pointer_selected(sender, target: HkbRecord, user_data: Any):
            self._on_value_changed(
                sender, target.object_id if target else None, pointer
            )

            # If the binding set pointer changed we should regenerate all attribute widgets
            vbs_type_id = self.tagfile.type_registry.find_first_type_by_name(
                "hkbVariableBindingSet"
            )
            if pointer.type_id == vbs_type_id:
                self.regenerate()
                self.reveal_attribute(path)

        def open_pointer_dialog():
            select_object(
                self.tagfile,
                pointer.subtype_id,
                on_pointer_selected,
                include_derived=True,
            )

        widget = self._add_reference_attribute_text(
            label,
            pointer.get_value(),
            open_pointer_dialog,
            style.pointer_attribute_theme,
        )
        return widget

    def _create_attribute_widget_vector4(
        self,
        array: HkbArray,
        path: str,
    ) -> str:
        label = path.split("/")[-1]

        with dpg.tree_node(
            label=label,
            filter_key=label,
            default_open=False,
        ) as tree_node:
            # In some cases the array might could be still empty
            for i in range(0, 4 - len(array)):
                if i == 3:
                    array.append(1.0)
                else:
                    array.append(0.0)

            for i, comp in zip(range(4), "xyzw"):
                value = array[i].get_value()
                dpg.add_input_double(
                    label=comp,
                    default_value=value,
                    callback=self._on_value_changed,
                    user_data=array[i],
                )

        return tree_node

    def _create_attribute_widget_array_buttons(
        self,
        array: HkbArray,
        path: str,
        tag: str = 0,
    ) -> str:
        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        def delete_last_item(sender, app_data, user_data) -> None:
            # TODO deleting an item may invalidate variable bindings!
            idx = len(array) - 1
            if idx < 0:
                return

            old_value = array.pop(idx)
            undo_manager.on_update_array_item(array, idx, old_value, None)

            # Records potentially contain pointers which will affect the graph
            Handler = get_value_handler(
                self.tagfile.type_registry, array.element_type_id
            )
            if Handler in (HkbRecord, HkbPointer):
                if self.on_graph_changed:
                    self.on_graph_changed()

            dpg.delete_item(f"{self.tag}_attribute_{path}:{idx}")

        def append_item() -> None:
            subtype = array.element_type_id
            Handler = get_value_handler(self.tagfile.type_registry, subtype)
            new_item = Handler.new(self.tagfile, subtype)

            self.logger.info(
                "Added new element of type %s to array %s->%s",
                subtype,
                self.record.object_id,
                path,
            )

            idx = len(array)
            array.append(new_item)
            undo_manager.on_update_array_item(array, idx, None, new_item)

            # TODO doesn't work for some reason
            # self._create_attribute_widget(
            #     self.record,
            #     new_item,
            #     f"{path}:{idx}",
            #     before=tag,  # insert before the buttons
            # )

            self.regenerate()
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

    def _create_attribute_widget_flags(
        self,
        attribute: XmlValueHandler,
        flag_type: Type[IntFlag],
        path: str,
        tag: str = 0,
    ) -> str:
        label = path.split("/")[-1]

        def on_flag_changed(sender: str, active_flags: int, user_data):
            self._on_value_changed(None, int(active_flags), attribute)

        flags = flag_type(attribute.get_value())
        with dpg.tree_node(label=label, default_open=True, tag=tag):
            create_flag_checkboxes(
                flag_type,
                on_flag_changed,
                base_tag=tag,
                active_flags=flags,
            )

    def _create_attribute_widget_simple(
        self,
        attribute: XmlValueHandler,
        path: str,
        tag: str = 0,
    ) -> str:
        label = path.split("/")[-1]

        with bindable_attribute(filter_key=label, tag=tag, width=-1) as bindable:
            if isinstance(attribute, HkbString):
                dpg.add_input_text(
                    filter_key=label,
                    callback=self._on_value_changed,
                    user_data=attribute,
                    default_value=attribute.get_value(),
                )

            elif isinstance(attribute, HkbInteger):
                current_record = self.record
                if "/" in path:
                    # The path will become deeper if and only if we descended into
                    # record fields, so the parent object will always be a record
                    parent_path = "/".join(path.split("/")[:-1])
                    current_record = self.record.get_field(parent_path)

                enum = get_hkb_enum(
                    self.tagfile.type_registry, current_record.type_id, path
                )

                if enum:

                    def on_enum_change(sender: str, new_value: str, val: HkbInteger):
                        int_value = enum[new_value].value
                        ui_repr = enum[new_value].name
                        self._on_value_changed(sender, (int_value, ui_repr), val)

                    dpg.add_combo(
                        [e.name for e in enum],
                        filter_key=label,
                        callback=on_enum_change,
                        user_data=attribute,
                        default_value=enum(attribute.get_value()).name,
                    )
                else:
                    if isinstance(self.tagfile, HavokBehavior):

                        # Event index
                        if is_event_attribute(self.record, path):

                            def on_event_selected(
                                sender: str, new_idx: int, user_data: Any
                            ):
                                if new_idx is None:
                                    self._on_value_changed(sender, -1, attribute)
                                else:
                                    self._on_value_changed(sender, new_idx, attribute)

                                self.regenerate()

                            self._add_reference_attribute_int(
                                label,
                                attribute.get_value(),
                                on_event_selected,
                                lambda s, a, u: select_event(
                                    self.tagfile, on_event_selected
                                ),
                                style.index_attribute_theme,
                            )

                        # Variable index
                        elif is_variable_attribute(self.record, path):

                            def on_variable_selected(
                                sender: str, new_idx: int, user_data: Any
                            ):
                                if new_idx is None:
                                    self._on_value_changed(sender, -1, attribute)
                                else:
                                    self._on_value_changed(sender, new_idx, attribute)

                                self.regenerate()

                            self._add_reference_attribute_int(
                                label,
                                attribute.get_value(),
                                on_variable_selected,
                                lambda s, a, u: select_variable(
                                    self.tagfile, on_variable_selected
                                ),
                                style.index_attribute_theme,
                            )

                        # Animation index
                        elif is_animation_attribute(self.record, path):

                            def on_animation_selected(
                                sender: str, new_idx: int, user_data: Any
                            ):
                                if new_idx is None:
                                    self._on_value_changed(sender, -1, attribute)
                                else:
                                    self._on_value_changed(sender, new_idx, attribute)

                                self.regenerate()

                            self._add_reference_attribute_int(
                                label,
                                attribute.get_value(),
                                on_animation_selected,
                                lambda s, a, u: select_animation(
                                    self.tagfile, on_animation_selected
                                ),
                                style.index_attribute_theme,
                            )
                        else:
                            dpg.add_input_int(
                                filter_key=label,
                                callback=self._on_value_changed,
                                user_data=attribute,
                                default_value=attribute.get_value(),
                            )
                    else:
                        dpg.add_input_int(
                            filter_key=label,
                            callback=self._on_value_changed,
                            user_data=attribute,
                            default_value=attribute.get_value(),
                        )

            elif isinstance(attribute, HkbFloat):
                dpg.add_input_double(
                    filter_key=label,
                    callback=self._on_value_changed,
                    user_data=attribute,
                    default_value=attribute.get_value(),
                )

            elif isinstance(attribute, HkbBool):
                dpg.add_checkbox(
                    filter_key=label,
                    callback=self._on_value_changed,
                    user_data=attribute,
                    default_value=attribute.get_value(),
                )

            else:
                self.logger.error(
                    "Cannot handle attribute %s (%s) of object %s",
                    path,
                    attribute,
                    self.record.object_id,
                )
                self.logger.debug("The offending record is \n%s", self.record.xml())
                return None

        return bindable

    def _create_attribute_menu(
        self,
        widget: str,
        attribute: XmlValueHandler,
        path: str,
        is_simple: bool,
    ):
        if not widget:
            self.logger.error(
                "Can't create attribute menu for %s (%s) as no widget was passed",
                path,
                type(attribute).__name__,
            )
            return

        # Should never happen, but development is funny ~
        if attribute is None:
            self.logger.error(
                "%s->%s is None, this should never happen",
                self.record.object_id,
                path,
            )
            return

        if is_simple:
            bound_attributes = get_bound_attributes(self.tagfile, self.record)
            bound_var_idx = bound_attributes.get(path, -1)

        # Create a context menu for the widget
        with dpg.popup(widget):
            dpg.add_text(path.split("/")[-1])
            type_name = self.tagfile.type_registry.get_name(attribute.type_id)
            dpg.add_text(f"<{type_name}>")

            if is_simple:
                if bound_var_idx >= 0:
                    bound_var_name = self.tagfile.get_variable_name(bound_var_idx)
                    dpg.add_text(f"bound: {bound_var_name}", color=style.pink)

                elif isinstance(self.tagfile, HavokBehavior):
                    if is_event_attribute(self.record, path):
                        idx = attribute.get_value()
                        name = (
                            self.tagfile.get_event(idx, "<invalid>")
                            if idx >= 0
                            else "<none>"
                        )
                        dpg.add_text(f"event: {name}", color=style.green)

                    elif is_variable_attribute(self.record, path):
                        idx = attribute.get_value()
                        name = (
                            self.tagfile.get_variable_name(idx, "<invalid>")
                            if idx >= 0
                            else "<none>"
                        )
                        dpg.add_text(f"variable: {name}", color=style.green)

                    elif is_animation_attribute(self.record, path):
                        idx = attribute.get_value()
                        name = (
                            self.tagfile.get_animation(idx, "<invalid>")
                            if idx >= 0
                            else "<none>"
                        )
                        dpg.add_text(f"animation: {name}", color=style.green)

            # Copy & paste
            dpg.add_separator()
            if is_simple:
                # Not clear how cut should work on records and lists
                dpg.add_selectable(
                    label="Cut",
                    callback=self._cut_value,
                    user_data=(widget, path, attribute),
                )

            dpg.add_selectable(
                label="Copy",
                callback=self._copy_value,
                user_data=(widget, path, attribute),
            )
            dpg.add_selectable(
                label="Copy Path",
                callback=self._copy_value_path,
                user_data=(widget, path, attribute),
            )
            dpg.add_selectable(
                label="Copy XML",
                callback=self._copy_value_xml,
                user_data=(widget, path, attribute),
            )
            dpg.add_selectable(
                label="Paste",
                callback=self._paste_value,
                user_data=(widget, path, attribute),
            )

            if isinstance(attribute, HkbPointer):

                def on_object_created(
                    sender: str, new_object: HkbRecord, user_data: Any
                ):
                    self._on_value_changed(widget, new_object.object_id, attribute)

                    if self.on_graph_changed:
                        self.on_graph_changed()

                def create_object_for_pointer():
                    # Late import to avoid cyclic import
                    from .workflows.create_object import create_object_dialog

                    current = attribute.get_target()
                    selected_type = None
                    if current:
                        selected_type = current.type_id

                    create_object_dialog(
                        self.tagfile,
                        self.alias_manager,
                        on_object_created,
                        allowed_types=[attribute.subtype_id],
                        include_derived_types=True,
                        id_required=True,
                        selected_type_id=selected_type,
                        title=f"Create object for '{path}'",
                        tag=f"{self.tag}_{path}_create_object_dialog",
                    )

                def jump():
                    oid = attribute.get_value()
                    if not oid or oid == "object0":
                        return

                    self.jump_callback(oid)

                dpg.add_separator()

                dpg.add_selectable(
                    label="New object",
                    callback=create_object_for_pointer,
                )

                # TODO we could provide a menu listing pinned items here

                dpg.add_selectable(
                    label="Clone Hierarchy",
                    callback=self._paste_hierarchy,
                    user_data=attribute,
                )

                if self.jump_callback:
                    dpg.add_selectable(label="Jump to", callback=jump)

            if is_simple:
                set_bindable_attribute_state(self.tagfile, widget, bound_var_idx)

                def _bind_variable(sender, app_data, user_data):
                    # deselect the selectable
                    dpg.set_value(sender, False)
                    select_variable_to_bind(*user_data)

                def _unbind_variable(
                    sender, app_data, data: tuple[HkbRecord, str, str]
                ):
                    # deselect the selectable
                    dpg.set_value(sender, False)

                    record, path, bindable_attribute = data
                    util = CommonActionsMixin(self.tagfile)
                    util.clear_variable_binding(record, path)

                    set_bindable_attribute_state(self.tagfile, bindable_attribute, -1)

                def _on_binding_established(
                    sender, data: tuple[int, HkbRecord], user_data: Any
                ):
                    if data is None:
                        return

                    # No need to call set_bindable_attribute_state since we'll rebuild the
                    # attribute widgets anyways

                    # If a new binding set was created the graph will change
                    if self.on_graph_changed:
                        self.on_graph_changed()

                    self.clear()
                    self._update_attributes()
                    self.reveal_attribute(path)

                dpg.add_separator()
                dpg.add_selectable(
                    label="Bind Variable",
                    callback=lambda s, a, u: _bind_variable(s, a, u),
                    user_data=(
                        self.tagfile,
                        self.record,
                        widget,
                        path,
                        _on_binding_established,
                    ),
                )

                dpg.add_selectable(
                    label="Clear binding",
                    callback=lambda s, a, u: _unbind_variable(s, a, u),
                    user_data=(self.record, path, widget),
                )

    # Internal callbacks
    def _on_value_changed(
        self, sender, new_value: Any | tuple[Any, Any], handler: XmlValueHandler
    ) -> None:
        if isinstance(new_value, tuple):
            new_value, ui_repr = new_value
        else:
            ui_repr = new_value

        old_value = handler.get_value()
        handler.set_value(new_value)
        undo_manager.on_update_value(handler, old_value, new_value)

        if self.on_value_changed:
            old_value = handler.get_value()
            self.on_value_changed(sender, handler, (old_value, new_value))

        if sender and dpg.does_item_exist(sender):
            dpg.set_value(sender, ui_repr)

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
        self._on_value_changed(widget, default_val, value)

        self.logger.info("Cut value:\n%s", val)

    def _copy_value(
        self, sender, app_data, user_data: tuple[str, str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        val = dpg.get_value(widget)
        self._copy_to_clipboard(val)

    def _copy_value_xml(
        self, sender, app_data, user_data: tuple[str, str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        val = value.xml().strip().strip("\n")
        self._copy_to_clipboard(val)

    def _copy_value_path(
        self, sender, app_data, user_data: tuple[str, str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        self._copy_to_clipboard(path)

    def _paste_value(
        self, sender, app_data, user_data: tuple[str, str, XmlValueHandler]
    ) -> None:
        # deselect the selectable
        dpg.set_value(sender, False)

        widget, path, value = user_data
        data = pyperclip.paste()

        if isinstance(value, HkbPointer):
            target = self.tagfile.retrieve_object(data)
            if target is None:
                self.logger.error(f"'{data}' is not a valid pointer ID")
                return

            if target == self.record:
                self.logger.error(
                    "A record should not reference itself. If this is intended, use the select object dialog."
                )
                return

            if not value.will_accept(target):
                self.logger.error(
                    f"'{data}' is of type {target.type_name}, which is incompatible with {value.subtype_name}"
                )
                return

        try:
            xml = ET.fromstring(data, get_xml_parser())
            new_value = type(value)(xml, value.type_id)
        except Exception:
            new_value = data

        try:
            self._on_value_changed(widget, new_value, value)

            if isinstance(value, HkbPointer) and self.on_graph_changed:
                self.on_graph_changed()
        except Exception as e:
            self.logger.error("Paste value to %s failed: %s", widget, e)
            return

    def _paste_hierarchy(self, sender, app_data, pointer: HkbPointer) -> None:
        data = pyperclip.paste()

        if not data.startswith("<behavior_hierarchy"):
            self.logger.error("Clipboard data is not a node hierarchy")
            return

        def on_hierarchy_merged(hierarchy):
            new_objects = [
                r.result for r in hierarchy.objects.values() if r.action == "<new>"
            ]
            self.logger.info(f"Cloned hierarchy of {len(new_objects)} elements")

            if hierarchy.pin_objects and self.pin_object_callback:
                for obj in new_objects:
                    self.pin_object_callback(obj)

            if self.on_graph_changed:
                self.on_graph_changed()

        paste_hierarchy(self.tagfile, pointer, data, on_hierarchy_merged)

    def _copy_to_clipboard(self, data: str):
        try:
            pyperclip.copy(data)
            self.logger.info("Copied to clipboard")
        except Exception as e:
            self.logger.warning(f"Copying value failed: {e}", exc_info=e)
