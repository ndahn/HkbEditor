from typing import Any, Callable, Annotated
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as OffsetType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui.dialogs import select_event, select_animation, select_object
from hkb_editor.gui.helpers import (
    center_window,
    create_flag_checkboxes,
    add_paragraphs,
    create_value_widget,
)
from hkb_editor.gui import style


def create_cmsg_dialog(
    behavior: HavokBehavior,
    callback: Callable[
        [str, tuple[HkbRecord, HkbRecord, HkbRecord, HkbRecord], Any], None
    ],
    active_statemachine_id: str = None,
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
    types = behavior.type_registry
    transition_effect: HkbRecord = None

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    # CMSG generation
    def on_okay():
        dpg.hide_item(f"{tag}_notification")

        # No need to verify, okay should be disabled when values are invalid
        statemachine_val: str = dpg.get_value(f"{tag}_statemachine")
        base_name: str = dpg.get_value(f"{tag}_base_name")
        animation_val: str = dpg.get_value(f"{tag}_animation")
        event_val: str = dpg.get_value(f"{tag}_event")
        playback_mode_val: str = dpg.get_value(f"{tag}_playback_mode")
        animation_end_event_type_val: str = dpg.get_value(
            f"{tag}_animation_end_event_type"
        )
        offset_type_val: str = dpg.get_value(f"{tag}_offset_type")
        enable_tae: bool = dpg.get_value(f"{tag}_enable_tae")
        enable_script: bool = dpg.get_value(f"{tag}_enable_script")

        if not base_name:
            show_warning("Base name not set")
            return

        if not animation_val:
            show_warning("Animation not set")
            return

        if not event_val:
            show_warning("Event not set")
            return

        # Resolve values
        statemachine_type = types.find_first_type_by_name("hkbStateMachine")
        statemachine_id = next(
            behavior.query(f"type_id={statemachine_type} name={statemachine_val}")
        ).object_id
        statemachine = behavior.objects[statemachine_id]

        # Must be unique within the statemachine
        new_state_id = util.get_next_state_id(statemachine)

        cmsg_name = base_name
        if base_name.endswith("_CMSG"):
            base_name = base_name[:-5]
        if not cmsg_name.endswith("_CMSG"):
            cmsg_name += "_CMSG"

        with behavior.transaction():
            playback_mode = PlaybackMode[playback_mode_val].value
            animation_end_event_type = AnimeEndEventType[
                animation_end_event_type_val
            ].value
            offset_type = OffsetType[offset_type_val].value

            state, cmsg, clip = util.create_state_chain(
                new_state_id,
                animation_val,
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
                event_val,
                transition_effect=transition_effect,
            )

        callback(dialog, (state, cmsg, clip), user_data)
        dpg.delete_item(dialog)

    dialog_values = {}

    # Dialog content
    with dpg.window(
        label="Create CMSG",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        # Statemachine
        sm_type = types.find_first_type_by_name("hkbStateMachine")
        statemachines = list(behavior.find_objects_by_type(sm_type))

        if active_statemachine_id:
            default_sm = behavior.objects[active_statemachine_id]
        else:
            default_sm = statemachines[0]

        def on_value_change(sender: str, value: Any, user_data: Any):
            dialog_values[sender] = value

        create_value_widget(
            behavior,
            Annotated[HkbRecord, "hkbStateMachine"],
            "Statemachine",
            on_value_change,
            default=default_sm.object_id,
            tag=f"{tag}_statemachine",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("The StateMachine the CMSG will be linked to")

        # Base name
        dpg.add_input_text(
            default_value="",
            label="Base Name",
            tag=f"{tag}_base_name",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("Used for the CMSG, ClipGenerator and TransitionInfo")

        # CMSG event
        with dpg.group(horizontal=True):

            def on_event_selected(sender: str, event_id: int, user_data: Any):
                event_name = behavior.get_event(event_id)
                dpg.set_value(f"{tag}_event", event_name)

            dpg.add_input_text(
                default_value="",
                tag=f"{tag}_event",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Used to activate the new state from HKS")

            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda: select_event(
                    behavior, on_event_selected, allow_clear=False
                ),
            )

            dpg.add_text("CMSG Event")

        # CMSG offset type
        dpg.add_combo(
            [e.name for e in OffsetType],
            default_value=OffsetType.IDLE_CATEGORY.name,
            label="Offset Type",
            tag=f"{tag}_offset_type",
        )

        with dpg.tooltip(dpg.last_container()):
            dpg.add_text("How the CMSG picks the clip to activate")

        # ClipGenerator animation
        with dpg.group(horizontal=True):

            def on_animation_selected(sender: str, animation_id: int, user_data: Any):
                animation_name = behavior.get_animation(animation_id)
                dpg.set_value(f"{tag}_animation", animation_name)

            dpg.add_input_text(
                default_value="",
                hint="aXXX_YYYYYY",
                tag=f"{tag}_animation",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Animation ID the ClipGenerator uses")

            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda: select_animation(
                    behavior, on_animation_selected, allow_clear=False
                ),
            )

            dpg.add_text("Clip Animation")

        # Clip playback mode
        dpg.add_combo(
            [e.name for e in PlaybackMode],
            default_value=PlaybackMode.SINGLE_PLAY.name,
            label="Playback Mode",
            tag=f"{tag}_playback_mode",
        )

        dpg.add_spacer(height=1)

        with dpg.tree_node(label="Advanced"):
            # AnimeEndEventType
            dpg.add_combo(
                [e.name for e in AnimeEndEventType],
                default_value=AnimeEndEventType.NONE.name,
                label="Animation End Event Type",
                tag=f"{tag}_animation_end_event_type",
            )

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text("What to do when the animation ends")

            # CMSG enable TAE
            dpg.add_checkbox(
                label="Enable TAE", default_value=True, tag=f"{tag}_enable_tae"
            )

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text("Whether the CMSG should use the TAE")

            # CMSG enable script
            dpg.add_checkbox(
                label="Enable Script", default_value=True, tag=f"{tag}_enable_script"
            )

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text(
                    "Whether the CMSG should call HKS functions (onUpdate and co.)"
                )

            # Transition effect
            with dpg.group(horizontal=True):

                def on_transition_selected(
                    sender: str, transition: HkbRecord, user_data: Any
                ):
                    nonlocal transition_effect
                    transition_effect = transition
                    name = transition["name"].get_value() if transition else ""
                    dpg.set_value(f"{tag}_transition_effect", name)

                transition_effect_type_id = (
                    behavior.type_registry.find_first_type_by_name(
                        "hkbTransitionEffect"
                    )
                )

                default_transition = util.get_default_transition_effect()

                dpg.add_input_text(
                    readonly=True,
                    default_value=(
                        default_transition["name"].get_value()
                        if default_transition
                        else ""
                    ),
                    tag=f"{tag}_transition_effect",
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: select_object(
                        behavior,
                        transition_effect_type_id,
                        on_transition_selected,
                    ),
                )
                dpg.add_text("Transition Effect")

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text(
                    "Decides how animations are blended when transitioning to the new state"
                )

            # TransitionInfo flags
            with dpg.tree_node(label="Transition Flags"):
                with dpg.tooltip(dpg.last_container()):
                    dpg.add_text("Flags of the new wildcard transition")

                create_flag_checkboxes(
                    TransitionInfoFlags,
                    None,
                    base_tag=f"{tag}_transition_flags",
                    active_flags=3584,
                )

        dpg.add_spacer(height=3)

        instructions = """\
Adds a new StateInfo, CMSG and Clip and adds them to a statemachine.
This essentially allows you to create entirely new animation slots.

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
