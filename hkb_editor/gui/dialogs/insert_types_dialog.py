import logging
from pathlib import Path
from typing import Any, Callable
from dearpygui import dearpygui as dpg
from lxml import etree as ET

from hkb_editor.hkb import Tagfile
from hkb_editor.hkb.type_registry import parse_hklib_xml
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs, loading_indicator
from .file_dialog import open_file_dialog


_instructions = """\
Select a type dump created by HKLib to add types this behavior doesn't have yet. Any types they depend on will be added as well.

The new types are saved together with the behavior. This cannot be undone!
"""


class insert_types_dialog(DpgItem):
    """Add types from a HKLib type dump to a tagfile.

    Lists every record type of the dump that is not part of the tagfile yet
    and inserts the selected ones via
    :meth:`hkb_editor.hkb.type_registry.TypeRegistry.insert_types_from_hklib_xml`.

    Parameters
    ----------
    tagfile : Tagfile
        Tagfile to add the types to.
    file_path : str, optional
        HKLib type dump to load right away.
    callback : callable, optional
        Called as ``callback(tag, new_type_ids, user_data)`` after types were added.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    user_data : any, optional
        Passed through to ``callback``.
    """

    def __init__(
        self,
        tagfile: Tagfile,
        file_path: str = None,
        callback: Callable[[str, list[str], Any], None] = None,
        *,
        title: str = "Insert Types",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._tagfile = tagfile
        self._callback = callback
        self._user_data = user_data
        self._window: str = None
        self._logger = logging.getLogger()

        self._hklib_root: ET._Element = None
        # (type name, checkbox tag)
        self._checkboxes: list[tuple[str, str]] = []

        self._build(title)

        if file_path:
            self.load_types(file_path)

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            label=title,
            width=500,
            height=600,
            autosize=True,
            on_close=lambda: dpg.delete_item(self._window),
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    readonly=True,
                    hint="HKLib types .xml",
                    tag=self._t("file_path"),
                )
                dpg.add_button(label="Load...", callback=self._on_select_file)

            dpg.add_spacer(height=3)
            add_paragraphs(_instructions, color=style.light_blue)
            dpg.add_separator()

            dpg.add_input_text(
                hint="Filter",
                callback=lambda s, a, u: self._apply_filter(a),
                tag=self._t("filter"),
            )

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Select all",
                    small=True,
                    callback=lambda: self._select_visible(True),
                )
                dpg.add_button(
                    label="Select none",
                    small=True,
                    callback=lambda: self._select_visible(False),
                )
                dpg.add_text("", tag=self._t("type_count"))

            with dpg.child_window(height=350, tag=self._t("type_list")):
                dpg.add_text("No types loaded", color=style.light_blue)

            # Main form done, now just some buttons and such
            dpg.add_separator()

            dpg.add_text(show=False, tag=self._t("notification"), color=style.red)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=self._on_okay,
                    tag=self._t("button_okay"),
                )
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.delete_item(self._window),
                )

        center_window(self._window, split_frame=True)

    def _fill_type_list(self, type_names: list[str]) -> None:
        dpg.delete_item(self._t("type_list"), children_only=True)
        self._checkboxes.clear()

        if not type_names:
            dpg.add_text(
                "All types are already known",
                color=style.light_blue,
                parent=self._t("type_list"),
            )

        for name in type_names:
            # No tags, the list is rebuilt whenever types are added
            checkbox = dpg.add_checkbox(label=name, parent=self._t("type_list"))
            self._checkboxes.append((name, checkbox))

        self._apply_filter(dpg.get_value(self._t("filter")))

    # === DPG callbacks ================================================

    def _on_select_file(self) -> None:
        path = open_file_dialog(
            title="Select HKLib types",
            filetypes={"HKLib types": "*.xml"},
        )

        if path:
            self.load_types(path)

    def _on_okay(self) -> None:
        self.show_message()

        if self._hklib_root is None:
            self.show_message("Load a HKLib types file first")
            return

        selected = self.selected_types
        if not selected:
            self.show_message("No types selected")
            return

        try:
            with loading_indicator("Inserting types"):
                new_type_ids = self._tagfile.type_registry.insert_types_from_hklib_xml(
                    self._hklib_root, selected
                )
        except KeyError as e:
            self._logger.error("Inserting types failed: %s", e)
            self.show_message(f"Failed: {e}")
            return

        self._logger.info(
            "Added %d types (%s)", len(new_type_ids), ", ".join(selected)
        )
        self.show_message(f"Added {len(new_type_ids)} types", color=style.blue)

        # The new types and their dependencies are no longer missing
        self._refresh()

        if self._callback:
            self._callback(self._tag, new_type_ids, self._user_data)

    # === Public =======================================================

    def load_types(self, file_path: str) -> None:
        """Load a HKLib type dump and list the types the tagfile is missing."""
        self.show_message()
        dpg.set_value(self._t("file_path"), str(file_path))

        try:
            with loading_indicator("Loading types"):
                xml = Path(file_path).read_text(encoding="utf-8-sig")
                self._hklib_root = parse_hklib_xml(xml)
        except (OSError, UnicodeDecodeError, ET.XMLSyntaxError) as e:
            self._logger.error("Failed to load %s: %s", file_path, e)
            self._hklib_root = None
            self._fill_type_list([])
            self.show_message(f"Failed to load file: {e}")
            return

        self._refresh()

    @property
    def selected_types(self) -> list[str]:
        return [name for name, checkbox in self._checkboxes if dpg.get_value(checkbox)]

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

    # === Helpers ======================================================

    def _refresh(self) -> None:
        missing = self._tagfile.type_registry.find_missing_hklib_types(
            self._hklib_root
        )
        self._fill_type_list(missing)

    def _apply_filter(self, filt: str) -> None:
        filt = (filt or "").lower()
        visible = 0

        for name, checkbox in self._checkboxes:
            show = filt in name.lower()
            dpg.configure_item(checkbox, show=show)
            visible += show

        dpg.set_value(
            self._t("type_count"), f"{visible} of {len(self._checkboxes)} shown"
        )

    def _select_visible(self, selected: bool) -> None:
        for _, checkbox in self._checkboxes:
            if dpg.is_item_shown(checkbox):
                dpg.set_value(checkbox, selected)
