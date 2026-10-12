from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs, loading_indicator
from hkb_editor.workflows.fix_common_problems import (
    COMMON_PROBLEMS,
    fix_common_problems,
)


_instructions = """\
Note that most severe issues cannot be fixed automatically. Use "Workflows -> Verify Behavior" and watch the terminal output carefully!
"""


class fix_common_problems_dialog(DpgItem):
    """Pick and run the automated behavior repairs.

    The available fixes come from
    :data:`hkb_editor.workflows.fix_common_problems.COMMON_PROBLEMS`;
    the dialog just renders a checkbox per entry.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to repair.
    callback : callable, optional
        Called as ``callback(tag, num_fixes, user_data)`` after a run.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    user_data : any, optional
        Passed through to ``callback``.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        callback: Callable[[str, int, Any], None] = None,
        *,
        title: str = "Fix Common Problems",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._callback = callback
        self._user_data = user_data
        self._window: str = None

        self._build(title)

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            label=title,
            width=400,
            height=600,
            autosize=True,
            on_close=lambda: dpg.delete_item(self._window),
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            for key, (label, tooltip, default, _) in COMMON_PROBLEMS.items():
                dpg.add_checkbox(
                    label=label,
                    default_value=default,
                    tag=self._t(key),
                )
                with dpg.tooltip(dpg.last_item()):
                    add_paragraphs(tooltip)

            add_paragraphs(_instructions, 50, color=style.light_blue)

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
                    label="Cancel",
                    callback=lambda: dpg.delete_item(self._window),
                )

        center_window(self._window, split_frame=True)

    # === DPG callbacks ================================================

    def _on_okay(self) -> None:
        self.show_message()

        with loading_indicator("Fixing"):
            fixes = fix_common_problems(self._behavior, self.selected_fixes)

            self.show_message(f"Fixed {fixes} issues", color=style.blue)
            dpg.set_item_label(self._t("button_okay"), "Again?")

            if self._callback:
                self._callback(self._tag, fixes, self._user_data)

    # === Public =======================================================

    @property
    def selected_fixes(self) -> list[str]:
        return [key for key in COMMON_PROBLEMS if dpg.get_value(self._t(key))]

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
