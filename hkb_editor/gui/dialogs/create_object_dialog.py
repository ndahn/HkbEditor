from typing import Any, Callable, Generator, Iterable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import Tagfile, HkbRecord
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, AttributesWidget
from hkb_editor.workflows.aliases import AliasManager
from hkb_editor.workflows.create_object import get_record_types
from .find_object_dialog import find_dialog


class create_object_dialog(DpgItem):
    """Create a new record of a chosen type and fill in its attributes.

    The record is created as soon as a type is picked so the attribute
    widgets can edit it directly; it is only added to the tagfile on confirm.

    Parameters
    ----------
    tagfile : Tagfile
        Tagfile the object will be added to.
    alias_manager : AliasManager
        Passed on to the embedded attributes widget.
    callback : callable
        Called as ``callback(tag, record, user_data)`` on confirm.
    allowed_types : iterable of str, optional
        Restrict the type choice; names or ``typeNNN`` IDs. Renders a combo
        instead of the type search dialog.
    include_derived_types : bool
        Also offer subtypes of ``allowed_types``.
    selected_type_id : str, optional
        Pre-select this type.
    id_required : bool
        Refuse to create the object without an explicit object ID.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    user_data : any, optional
        Passed through to ``callback``.
    """

    def __init__(
        self,
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
    ) -> None:
        super().__init__(tag)

        self._tagfile = tagfile
        self._alias_manager = alias_manager
        self._callback = callback
        self._id_required = id_required
        self._user_data = user_data

        self._type_registry = tagfile.type_registry
        self._record: HkbRecord = None
        self._window: str = None
        self._attributes: AttributesWidget = None
        self._type_dialog: find_dialog = None

        self._record_types = get_record_types(
            tagfile,
            allowed_types,
            include_derived_types=include_derived_types,
        )

        if allowed_types and selected_type_id is None:
            # We can assume the first item is a sensible choice
            selected_type_id = self._record_types[0][0]

        self._build(title, bool(allowed_types))

        if selected_type_id:
            self.set_object_type(selected_type_id)

    def destroy(self) -> None:
        # Both are root level items and outlive our window
        if self._type_dialog is not None:
            self._type_dialog.destroy()
            self._delete_item(self._type_dialog.tag)
            self._type_dialog = None

        if self._attributes is not None:
            self._attributes.destroy()
            self._attributes = None

    # === Build ========================================================

    def _build(self, title: str, use_combo: bool) -> None:
        tagfile = self._tagfile

        with dpg.window(
            label=title,
            width=500,
            height=600,
            autosize=True,
            no_saved_settings=True,
            tag=self._tag,
            on_close=self._on_close,
        ) as self._window:
            if use_combo:
                # If there's a limited number of available object types use a dropdown
                dpg.add_combo(
                    [t[1] for t in self._record_types],
                    callback=self._on_type_selected,
                    width=300,
                    tag=self._t("object_type"),
                )
            else:
                # If all types are allowed use a find dialog
                with dpg.group(horizontal=True, width=300):
                    dpg.add_input_text(
                        default_value="",
                        readonly=True,
                        hint="Object type",
                        tag=self._t("object_type"),
                    )
                    dpg.add_button(
                        arrow=True,
                        direction=dpg.mvDir_Right,
                        callback=self._on_search_type,
                    )
                    dpg.add_text("Object type")

            with dpg.group(horizontal=True, width=300):
                dpg.add_input_text(
                    default_value=tagfile.new_id(),
                    no_spaces=True,
                    callback=self._on_object_id_changed,
                    tag=self._t("object_id"),
                )
                dpg.add_button(
                    label="+",
                    small=True,
                    callback=lambda: self._on_object_id_changed(
                        None, tagfile.new_id()
                    ),
                )
                dpg.add_text("Object ID")

            with dpg.child_window(auto_resize_y=True):
                self._attributes = AttributesWidget(
                    self._alias_manager, hide_title=True
                )

            dpg.add_text(show=False, tag=self._t("notification"), color=style.red)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=self._on_okay,
                    tag=self._t("button_okay"),
                )
                dpg.add_button(label="Cancel", callback=self._on_close)
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

        center_window(self._window, split_frame=True)

    # === DPG callbacks ================================================

    def _on_type_selected(
        self, sender: str, type_name: str, user_data: Any
    ) -> None:
        self.set_object_type(
            self._type_registry.find_first_type_by_name(type_name)
        )

    def _on_search_type(self) -> None:
        if self._type_dialog is not None and dpg.does_item_exist(
            self._type_dialog.tag
        ):
            dpg.focus_item(self._type_dialog.tag)
            return

        def get_object_types(filt: str) -> Generator[tuple[str, ...], None, None]:
            filt = filt.lower()
            for type_id, type_name in self._record_types:
                if filt in type_id or filt in type_name.lower():
                    yield (type_id, type_name)

        self._type_dialog = find_dialog(
            get_object_types,
            ["Type ID", "Name"],
            lambda item: item,
            okay_callback=lambda s, a, u: self.set_object_type(a[0]),
            title="Select Object Type",
            tag=self._t("select_object_type"),
        )

    def _on_object_id_changed(
        self, sender: str, new_id: str, user_data: Any = None
    ) -> None:
        dpg.set_value(self._t("object_id"), new_id)
        if self._record:
            self._record.object_id = new_id
            self._attributes.set_title(None)

    def _on_okay(self) -> None:
        if not self._record:
            self.show_message("Select an object type first")
            return

        oid = self._record.object_id
        if not oid:
            if self._id_required:
                self.show_message("Please enter a valid object ID")
                return
        elif oid in self._tagfile.objects:
            self.show_message("Object ID already exists")
            return

        self.show_message()

        if not dpg.get_value(self._t("object_type")):
            self.show_message("No type selected")
            return

        with self._tagfile.transaction():
            self._tagfile.add_object(self._record)
            self._callback(self._tag, self._record, self._user_data)

        self._on_close()

    def _on_close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)

    # === Public =======================================================

    @property
    def record(self) -> HkbRecord:
        """The record being edited, or None while no type is selected."""
        return self._record

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the created object."""
        return dpg.get_value(self._t("pin_objects"))

    def set_object_type(self, new_type_id: str) -> None:
        """Switch to a new record type, discarding the current attributes."""
        self.show_message()

        type_name = self._type_registry.get_name(new_type_id)
        dpg.set_value(self._t("object_type"), type_name)

        # By creating the record here all UI widgets can modify it directly and
        # we don't need to collect their attributes later
        oid = dpg.get_value(self._t("object_id"))
        self._record = HkbRecord.new(self._tagfile, new_type_id, object_id=oid)
        self._attributes.set_record(self._record)
        self._attributes.set_title(None)

    def show_message(self, msg: str = None, color: style.RGBA = style.red) -> None:
        """Show or hide the notification label. Pass ``msg=None`` to hide."""
        if not msg:
            dpg.hide_item(self._t("notification"))
            return

        dpg.configure_item(
            self._t("notification"),
            default_value=msg,
            color=color,
            show=True,
        )
