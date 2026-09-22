from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs
from hkb_editor.workflows.duplicate_clipcat import (
    validate_animation_names,
    duplicate_clip_category,
)
from .find_object_dialog import select_animation


_instructions = """\
For each selected animation, a new animation with new category (aXXX) will be created. All ClipGenerators using them will be duplicated within their respective parents.
"""


class duplicate_clipcat_dialog(DpgItem):
    """Copy a set of animation clips into a new animation category.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    callback : callable
        Called as ``callback(tag, copies, user_data)`` on confirm.
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
        callback: Callable[[str, list[HkbRecord], Any], None],
        *,
        title: str = "Duplicate Animation Clips",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._callback = callback
        self._user_data = user_data
        self._window: str = None
        self._select_dialog: select_animation = None

        self._build(title)

    def destroy(self) -> None:
        # The animation picker is a root level window and outlives us
        if self._select_dialog is not None:
            self._select_dialog.destroy()
            self._delete_item(self._select_dialog.tag)
            self._select_dialog = None

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            label=title,
            width=400,
            height=600,
            autosize=True,
            on_close=self._on_close,
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            dpg.add_input_text(
                label="Clips",
                hint="a123_456789",
                multiline=True,
                tag=self._t("anims"),
            )
            dpg.add_button(label="Add Clips...", callback=self._on_add_anims)
            dpg.add_input_int(
                label="Target Category",
                min_value=0,
                min_clamped=True,
                max_value=999,
                max_clamped=True,
                tag=self._t("target_category"),
            )
            dpg.add_checkbox(
                label="Replace existing",
                default_value=False,
                tag=self._t("replace_existing"),
            )

            dpg.add_spacer(height=3)
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
                dpg.add_button(label="Cancel", callback=self._on_close)
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

        center_window(self._window, split_frame=True)
        dpg.focus_item(self._tag)

    # === DPG callbacks ================================================

    def _on_add_anims(self) -> None:
        self.destroy()
        self._select_dialog = select_animation(
            self._behavior,
            self._on_anims_selected,
            title="Select Animations",
            multiple=True,
        )

    def _on_anims_selected(
        self, sender: str, anims: list[int], user_data: Any
    ) -> None:
        current = set(x for x in dpg.get_value(self._t("anims")).splitlines() if x)
        current.update(self._behavior.get_animation(aid) for aid in anims)
        dpg.set_value(self._t("anims"), "\n".join(sorted(current)))

    def _on_okay(self) -> None:
        try:
            animations = validate_animation_names(
                self._behavior,
                dpg.get_value(self._t("anims")).splitlines(),
            )
        except ValueError as e:
            self.show_message(str(e))
            return

        self.show_message()

        copies = duplicate_clip_category(
            self._behavior,
            animations,
            dpg.get_value(self._t("target_category")),
            replace_existing=dpg.get_value(self._t("replace_existing")),
            on_warning=self.show_message,
        )

        self._callback(self._tag, copies, self._user_data)
        self._on_close()

    def _on_close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)

    # === Public =======================================================

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the created clips."""
        return dpg.get_value(self._t("pin_objects"))

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
