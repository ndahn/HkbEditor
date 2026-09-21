from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.hkb.hkb_enums import hkbClipGenerator_PlaybackMode as PlaybackMode
from hkb_editor.hkb.hkb_flags import hkbClipGenerator_Flags as ClipFlags
from hkb_editor.templates.common import CommonActionsMixin, Animation, Variable
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs, add_behavior_widget
from hkb_editor.workflows.register_clips import (
    validate_clip_animations,
    register_clips,
)
from .find_object_dialog import select_animation


_instructions = """\
Registers one or more animations in an existing CMSG. All animations should have the same ID (the Y part of aXXX_YYYYYY), and the ID should be compatible with the CMSG's animId.

See "Create Slot" instead if you want to setup an animation ID for which no CMSG exists yet.
"""


class register_clips_dialog(DpgItem):
    """Create ClipGenerators for a list of animations and wire them into CMSGs.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    callback : callable
        Called as ``callback(tag, clips, user_data)`` on confirm.
    reuse_clips : bool
        Initial value of the "Reuse clips" option.
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
        reuse_clips: bool = False,
        title: str = "Register Clip",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._callback = callback
        self._user_data = user_data
        self._util = CommonActionsMixin(behavior)
        self._window: str = None
        self._select_dialog: select_animation = None

        self._values = {
            "animations": [],
            "reuse_clips": reuse_clips,
            "starttime_variable": None,
            "playback_mode": PlaybackMode.SINGLE_PLAY.name,
            "flags": ClipFlags.NONE,
        }

        self._build(title)

    def destroy(self) -> None:
        # The animation picker is a root level window and outlives us
        if self._select_dialog is not None:
            self._select_dialog.destroy()
            self._delete_item(self._select_dialog.tag)
            self._select_dialog = None

    # === Build ========================================================

    def _build(self, title: str) -> None:
        values = self._values

        with dpg.window(
            label=title,
            width=400,
            height=600,
            autosize=True,
            on_close=self._on_close,
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            # Animation name
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    hint="aXXX_YYYYYY",
                    multiline=True,
                    callback=self._on_value_change,
                    default_value="\n".join(str(v) for v in values["animations"]),
                    tag=self._t("animations"),
                    user_data="animations",
                )
                dpg.add_button(label="+", callback=self._on_add_animation)
                dpg.add_text("Animations")
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text("Animations to register, one animation per line")

            # Clip playback mode
            add_behavior_widget(
                self._behavior,
                PlaybackMode,
                "Playback Mode",
                self._on_value_change,
                default=values["playback_mode"],
                tag=self._t("playback_mode"),
                user_data="playback_mode",
            )

            with dpg.tree_node(label="Advanced"):
                # Bind startTime to a variable
                add_behavior_widget(
                    self._behavior,
                    Variable,
                    "Bind startTime",
                    self._on_value_change,
                    default=values["starttime_variable"],
                    tag=self._t("starttime_variable"),
                    user_data="starttime_variable",
                )

                # Reuse clips, although it's rarely useful
                add_behavior_widget(
                    self._behavior,
                    bool,
                    "Reuse clips",
                    self._on_value_change,
                    default=values["reuse_clips"],
                    tag=self._t("reuse_clips"),
                    user_data="reuse_clips",
                )
                with dpg.tooltip(dpg.last_item()):
                    dpg.add_text(
                        "Reuse clip insances in multiple CMSGs. Can cause problems\n"
                        "with self transitions (e.g. dodge stutter)."
                    )

                # Flags
                with dpg.tree_node(label="Flags"):
                    add_behavior_widget(
                        self._behavior,
                        ClipFlags,
                        "Flags",
                        self._on_value_change,
                        default=values["flags"],
                        tag=self._t("flags"),
                        user_data="flags",
                    )

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
        dpg.focus_item(self._t("animations"))

    # === DPG callbacks ================================================

    def _on_value_change(self, sender: str, value: Any, key: str) -> None:
        if key == "animations" and isinstance(value, str):
            value = value.splitlines()

        self._values[key] = value

    def _on_add_animation(self) -> None:
        self.destroy()
        self._select_dialog = select_animation(
            self._behavior,
            self._on_animation_selected,
            allow_clear=False,
        )

    def _on_animation_selected(
        self, sender: str, animation_id: int, user_data: Any
    ) -> None:
        new_anim = self._util.animation(animation_id)
        animations: list[Animation] = self._values["animations"]

        for anim in animations:
            if anim == new_anim:
                return

        animations.append(new_anim.name)
        dpg.set_value(
            self._t("animations"), "\n".join(str(v) for v in animations)
        )
        self._on_value_change(sender, animations, "animations")

    def _on_okay(self) -> None:
        values = self._values

        try:
            animations = validate_clip_animations(values["animations"])
        except ValueError as e:
            self.show_message(str(e))
            return

        self.show_message()

        clips = register_clips(
            self._behavior,
            animations,
            playback_mode=PlaybackMode[values["playback_mode"]],
            flags=ClipFlags(values["flags"]),
            starttime_variable=values.get("starttime_variable"),
            reuse_clips=values["reuse_clips"],
        )

        self._callback(self._tag, clips, self._user_data)
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
