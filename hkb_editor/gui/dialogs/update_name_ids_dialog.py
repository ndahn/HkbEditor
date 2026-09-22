import logging
from pathlib import Path
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs
from hkb_editor.workflows.update_name_ids import (
    get_nameidfile_folder,
    find_missing_nameid_files,
    update_name_ids,
)
from .file_dialog import open_file_dialog


_instructions = """\
When adding new events, variables or StateInfo objects, they need to be recorded in a text file located in your mod's action folder. These are not character-specific and are required to correctly synchronize game state in online sessions.

Since these text files cover all behaviors in the entire game, they cannot be generated on the fly. This tool can only add new entries and will never remove any.

NOTE: If you don't have these files in your mod yet, copy them from the base game first!
"""


class update_name_ids_dialog(DpgItem):
    """Sync the mod's name ID files with the events, variables and states.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior whose names should be recorded.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        *,
        title: str = "Update Name ID Files",
        tag: str = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._action_path: Path = get_nameidfile_folder(behavior) or ""
        self._window: str = None
        self._logger = logging.getLogger()

        self._build(title)

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            label=title,
            width=700,
            height=400,
            autosize=True,
            no_saved_settings=True,
            tag=self._tag,
            on_close=lambda: dpg.delete_item(self._window),
        ) as self._window:
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    default_value=str(self._action_path),
                    readonly=True,
                    hint="mod/action",
                    tag=self._t("action_path"),
                )
                dpg.add_button(
                    label="Locate action folder...",
                    callback=self._on_select_action_folder,
                )

            dpg.add_spacer(height=3)
            add_paragraphs(_instructions, color=style.light_blue)

            dpg.add_separator()

            dpg.add_text(show=False, tag=self._t("notification"), color=style.orange)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=self._on_okay,
                    tag=self._t("button_okay"),
                )
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.delete_item(self._window),
                )

        center_window(self._window, split_frame=True)

    # === DPG callbacks ================================================

    def _on_select_action_folder(self) -> None:
        path = open_file_dialog(
            title="Locate mod/action folder",
            filetypes={"Name ID Files": "*.txt"},
        )

        if not path:
            return

        self._action_path = Path(path).parent
        dpg.set_value(self._t("action_path"), str(path))

        missing = find_missing_nameid_files(self._action_path)
        if missing:
            self.show_message(f"{tuple(missing)} not found")

    def _on_okay(self) -> None:
        if not self._action_path or not Path(self._action_path).is_dir():
            self.show_message("Please locate your mod/action folder first")
            return

        missing = update_name_ids(self._behavior, Path(self._action_path))

        if missing:
            self.show_message("At least one ID file was missing, check logs!")
        else:
            self._logger.info("All name ID files were updated")
            dpg.delete_item(self._window)

    # === Public =======================================================

    def show_message(self, msg: str = None, color: style.RGBA = style.orange) -> None:
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
