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
from hkb_editor.gui.helpers import (
    center_window,
    add_paragraphs,
    create_value_widget,
)
from hkb_editor.gui import style


def create_slot_dialog(
    behavior: HavokBehavior,
    callback: Callable[
        [str, tuple[HkbRecord, HkbRecord, HkbRecord, HkbRecord], Any], None
    ],
    active_statemachine: HkbRecord | str = None,
    *,
    tag: str = 0,
    user_data: Any = None,
) -> str:
    # To create a new CMSG we need at least the following:
    # - CMSG
    # - ClipGenerator
    # - StateInfo
    # - TransitionInfo
    #
    # We also need to:
    # - add a new event name
    # - add a new (?) animation ID
    # - select an appropriate transition object (e.g. TaeBlend)

    if tag in (0, "", None):
        tag = f"create_cmsg_dialog_{dpg.generate_uuid()}"

    util = CommonActionsMixin(behavior)
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    statemachines = list(behavior.find_objects_by_type(sm_type))
    default_sm = util.resolve_object(active_statemachine, statemachines[0])

    values = {
        "statemachine": default_sm["name"].get_value() if default_sm else None,
        "base_name": "",
        "animation": "",
        "event": "",
        "playback_mode": PlaybackMode.SINGLE_PLAY.name,
        "animation_end_event_type": AnimeEndEventType.NONE.name,
        "offset_type": OffsetType.IDLE_CATEGORY.name,
        "enable_tae": True,
        "enable_script": True,
        "transition_effect": None,
        "copy_transition_effect": True,
        "transition_flags": 3584,
    }

    def on_value_change(sender: str, value: Any, key: Any):
        values[key] = value

    def show_warning(msg: str) -> None:
        if msg:
            dpg.set_value(f"{tag}_notification", msg)
            dpg.show_item(f"{tag}_notification")
        else:
            dpg.hide_item(f"{tag}_notification")

    # CMSG generation
    def on_okay():
        # No need to verify, okay should be disabled when values are invalid
        statemachine_val: HkbRecord = values["statemachine"]
        base_name: str = values["base_name"]
        animation: Animation = values["animation"]
        event: Event = values["event"]
        playback_mode_val: str = values["playback_mode"]
        animation_end_event_type_val: str = values["animation_end_event_type"]
        offset_type_val: str = values["offset_type"]
        enable_tae: bool = values["enable_tae"]
        enable_script: bool = values["enable_script"]
        transition_effect: HkbRecord = values["transition_effect"]
        copy_transition_effect: bool = values["copy_transition_effect"]
        transition_flags = TransitionInfoFlags(values["transition_flags"])

        playback_mode = PlaybackMode[playback_mode_val]
        animation_end_event_type = AnimeEndEventType[animation_end_event_type_val]
        offset_type = OffsetType[offset_type_val]

        if not statemachine_val:
            show_warning("Statemachine not set")
            return

        if not base_name:
            show_warning("Base name not set")
            return

        if not animation:
            show_warning("Animation not set")
            return

        if not event:
            show_warning("Event not set")
            return

        show_warning("")
        
        statemachine = next(behavior.query(f"name='{statemachine_val}' type_name=hkbStateMachine"))
        new_state_id = util.get_next_state_id(statemachine)

        with behavior.transaction():
            state, cmsg, clip = util.create_state_chain(
                new_state_id,
                animation,
                base_name,
                cmsg_kwargs={
                    "animeEndEventType": animation_end_event_type,
                    "offsetType": offset_type,
                    "enableTae": enable_tae,
                    "enableScript": enable_script,
                },
                clip_kwargs={"mode": playback_mode},
            )

            util.add_wildcard_state(
                statemachine,
                state,
                event,
                transition_effect=transition_effect,
                copy_transition_effect=copy_transition_effect,
                flags=transition_flags,
            )

        callback(dialog, (state, cmsg, clip), user_data)
        dpg.delete_item(dialog)

    # Dialog content
    with dpg.window(
        label="Create Slot",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        # Statemachine
        create_value_widget(
            behavior,
            str,
            "Statemachine",
            on_value_change,
            default=values["statemachine"],
            choices=[sm["name"].get_value() for sm in statemachines],
            tag=f"{tag}_statemachine",
            user_data="statemachine",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("The StateMachine the CMSG will be linked to")

        # Base name
        create_value_widget(
            behavior, 
            str,
            "Base Name",
            on_value_change,
            default=values["base_name"],
            tag=f"{tag}_base_name",
            user_data="base_name",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("Used for the CMSG, ClipGenerator and TransitionInfo")

        # CMSG event
        create_value_widget(
            behavior,
            Event,
            "Event",
            on_value_change,
            default=values["event"],
            tag=f"{tag}_event",
            user_data="event",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("Used to activate the new state from HKS")

        # CMSG offset type
        create_value_widget(
            behavior,
            OffsetType,
            "Offset Type",
            on_value_change,
            default=values["offset_type"],
            tag=f"{tag}_offset_type",
            user_data="offset_type",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("How the CMSG picks the clip to activate")

        # ClipGenerator animation
        create_value_widget(
            behavior,
            Animation,
            "Animation",
            on_value_change,
            default=values["animation"],
            tag=f"{tag}_animation",
            user_data="animation",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("Animation ID the ClipGenerator uses")

        # Clip playback mode
        create_value_widget(
            behavior,
            PlaybackMode,
            "Playback Mode",
            on_value_change,
            default=values["playback_mode"],
            tag=f"{tag}_playback_mode",
            user_data="playback_mode",
        )

        dpg.add_spacer(height=1)

        with dpg.tree_node(label="Advanced"):
            # AnimeEndEventType
            create_value_widget(
                behavior,
                AnimeEndEventType,
                "Animation End Action",
                on_value_change,
                default=values["animation_end_event_type"],
                tag=f"{tag}_animation_end_event_type",
                user_data="animation_end_event_type",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("What to do when the animation ends")

            # CMSG enable TAE
            create_value_widget(
                behavior,
                bool,
                "Enable TAE",
                on_value_change,
                default=values["enable_tae"],
                tag=f"{tag}_enable_tae",
                user_data="enable_tae",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Whether the CMSG should use the TAE")

            # CMSG enable script
            create_value_widget(
                behavior,
                bool,
                "Enable Script",
                on_value_change,
                default=values["enable_script"],
                tag=f"{tag}_enable_script",
                user_data="enable_script",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text(
                    "Whether the CMSG should call HKS functions (onUpdate and co.)"
                )

            # Transition effect
            create_value_widget(
                behavior,
                Annotated[HkbRecord, "hkbTransitionEffect"],
                "Transition Effect",
                on_value_change,
                default=values["transition_effect"],
                tag=f"{tag}_transition_effect",
                user_data="transition_effect",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text(
                    "Decides how animations are blended when transitioning to the new state"
                )

            # Make copy of transition effect
            create_value_widget(
                behavior,
                bool,
                "Copy Transition Effect",
                on_value_change,
                default=values["copy_transition_effect"],
                tag=f"{tag}_copy_transition_effect",
                user_data="copy_transition_effect",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text(
                    "Make a copy of the transition effect instead of reusing it"
                )

            # TransitionInfo flags
            with dpg.tree_node(label="Transition Flags"):
                create_value_widget(
                    behavior,
                    TransitionInfoFlags,
                    "Transition Flags",
                    on_value_change,
                    default=values["transition_flags"],
                    tag=f"{tag}_transition_flags",
                    user_data="transition_flags",
                )

        dpg.add_spacer(height=3)

        instructions = """\
Creates a new StateInfo, CMSG and Clip and adds them to a statemachine. This essentially allows you to create entirely new animation slots.

Note that for a StateInfo to work correctly you need to do two things:
- add a '<statename>_onUpdate' function in your HKS (if 'enableScript' is true)
- run 'File -> Update Name ID files' to register the new states/events
"""
        add_paragraphs(instructions, 50, color=style.light_blue)

        # Main form done, now just some buttons and such
        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.red)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(dialog),
            )
            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )

    dpg.split_frame()
    center_window(dialog)

    dpg.focus_item(f"{tag}_base_name")
    return dialog
