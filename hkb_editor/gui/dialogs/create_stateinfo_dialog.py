from typing import Any, Callable, Annotated
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as OffsetType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)
from hkb_editor.templates.common import CommonActionsMixin, Event, Animation
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs, add_behavior_widget
from hkb_editor.workflows.create_stateinfo import (
    get_statemachines,
    create_stateinfo,
)


_instructions = """\
Creates a new StateInfo, CMSG and Clip and adds them to a statemachine. This essentially allows you to create entirely new animation slots.

Note that for a StateInfo to work correctly you need to do two things:
- add a '<statename>_onUpdate' function in your HKS (if 'enableScript' is true)
- run 'File -> Update Name ID files' to register the new states/events
"""

# Fields that must be filled in before the slot can be created
_required = {
    "statemachine": "Statemachine not set",
    "base_name": "Base name not set",
    "animation": "Animation not set",
    "event": "Event not set",
}


class create_stateinfo_dialog(DpgItem):
    """Create a new animation slot (StateInfo + CMSG + ClipGenerator).

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    callback : callable
        Called as ``callback(tag, (state, cmsg, clip), user_data)`` on confirm.
    active_statemachine : HkbRecord or str, optional
        Pre-selected state machine; falls back to the first one found.
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
        callback: Callable[
            [str, tuple[HkbRecord, HkbRecord, HkbRecord], Any], None
        ],
        active_statemachine: HkbRecord | str = None,
        *,
        title: str = "Create Slot",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._callback = callback
        self._user_data = user_data
        self._window: str = None

        util = CommonActionsMixin(behavior)
        self._statemachines = get_statemachines(behavior)
        default_sm = util.resolve_object(
            active_statemachine, self._statemachines[0]
        )

        self._values = {
            "statemachine": default_sm["name"].get_value() if default_sm else None,
            "base_name": "",
            "animation": "",
            "event": "",
            "playback_mode": PlaybackMode.SINGLE_PLAY.name,
            "animation_end_event_type": AnimeEndEventType.FIRE_IDLE_EVENT.name,
            "offset_type": OffsetType.IDLE_CATEGORY.name,
            "enable_tae": True,
            "enable_script": True,
            "transition_effect": None,
            "copy_transition_effect": True,
            "transition_flags": 3584,
        }

        self._build(title)

    # === Build ========================================================

    def _add_field(
        self,
        value_type: type,
        label: str,
        key: str,
        tooltip: str = None,
        **kwargs,
    ) -> None:
        add_behavior_widget(
            self._behavior,
            value_type,
            label,
            self._on_value_change,
            default=self._values[key],
            tag=self._t(key),
            user_data=key,
            **kwargs,
        )
        if tooltip:
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text(tooltip)

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
            self._add_field(
                str,
                "Statemachine",
                "statemachine",
                "The StateMachine the CMSG will be linked to",
                choices=sorted(
                    sm["name"].get_value() for sm in self._statemachines
                ),
            )
            self._add_field(
                str,
                "Base Name",
                "base_name",
                "Used for the CMSG, ClipGenerator and TransitionInfo",
            )
            self._add_field(
                Event,
                "Event",
                "event",
                "Used to activate the new state from HKS",
            )
            self._add_field(
                OffsetType,
                "Offset Type",
                "offset_type",
                "How the CMSG picks the clip to activate",
            )
            self._add_field(
                AnimeEndEventType,
                "Animation End Action",
                "animation_end_event_type",
                "What to do when the animation ends, usually IDLE or NONE",
            )
            self._add_field(
                Animation,
                "Animation",
                "animation",
                "Animation ID the ClipGenerator uses",
            )
            self._add_field(PlaybackMode, "Playback Mode", "playback_mode")

            dpg.add_spacer(height=1)

            with dpg.tree_node(label="Advanced"):
                self._add_field(
                    bool,
                    "Enable TAE",
                    "enable_tae",
                    "Whether the CMSG should use the TAE",
                )
                self._add_field(
                    bool,
                    "Enable Script",
                    "enable_script",
                    "Whether the CMSG should call HKS functions (onUpdate and co.)",
                )
                self._add_field(
                    Annotated[HkbRecord, "hkbTransitionEffect"],
                    "Transition Effect",
                    "transition_effect",
                    "Decides how animations are blended when transitioning to "
                    "the new state",
                )
                self._add_field(
                    bool,
                    "Copy Transition Effect",
                    "copy_transition_effect",
                    "Make a copy of the transition effect instead of reusing it",
                )

                with dpg.tree_node(label="Transition Flags"):
                    self._add_field(
                        TransitionInfoFlags,
                        "Transition Flags",
                        "transition_flags",
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
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.delete_item(self._window),
                )
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

        center_window(self._window, split_frame=True)
        dpg.focus_item(self._t("base_name"))

    # === DPG callbacks ================================================

    def _on_value_change(self, sender: str, value: Any, key: str) -> None:
        self._values[key] = value

    def _on_okay(self) -> None:
        values = self._values

        for key, msg in _required.items():
            if not values[key]:
                self.show_message(msg)
                return

        self.show_message()

        created = create_stateinfo(
            self._behavior,
            values["statemachine"],
            values["base_name"],
            values["animation"],
            values["event"],
            playback_mode=PlaybackMode[values["playback_mode"]],
            animation_end_event_type=AnimeEndEventType[
                values["animation_end_event_type"]
            ],
            offset_type=OffsetType[values["offset_type"]],
            enable_tae=values["enable_tae"],
            enable_script=values["enable_script"],
            transition_effect=values["transition_effect"],
            copy_transition_effect=values["copy_transition_effect"],
            transition_flags=TransitionInfoFlags(values["transition_flags"]),
        )

        self._callback(self._tag, created, self._user_data)
        dpg.delete_item(self._window)

    # === Public =======================================================

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the created objects."""
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
