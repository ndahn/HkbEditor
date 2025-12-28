from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
)
from hkb_editor.templates.common import CommonActionsMixin
from hkb_editor.gui.dialogs import select_event, select_animation, select_object
from hkb_editor.gui.helpers import center_window, create_flag_checkboxes, add_paragraphs
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
    selected_transitioninfo_effect: HkbRecord = None
    selected_stateinfo_effect: HkbRecord = None

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

        wildcard_transitions_ptr = statemachine.get_field("wildcardTransitions")
        if not wildcard_transitions_ptr.get_value():
            show_warning("Statemachine does not have a wildcard transitions object")
            return

        # Must be unique within the statemachine
        new_state_id = util.get_next_state_id(statemachine)

        cmsg_name = base_name
        if base_name.endswith("_CMSG"):
            base_name = base_name[:-5]
        if not cmsg_name.endswith("_CMSG"):
            cmsg_name += "_CMSG"

        with behavior.transaction():
            # Get or create the animation slot
            animation = util.animation(animation_val)

            # Get or create the event
            event = util.event(event_val)

            playback_mode = PlaybackMode[playback_mode_val].value
            animation_end_event_type = AnimeEndEventType[animation_end_event_type_val].value

            transitioninfo_effect_id = (
                selected_transitioninfo_effect.object_id
                if selected_transitioninfo_effect
                else None
            )

            stateinfo_transition_effect_id = (
                selected_stateinfo_effect.object_id if selected_stateinfo_effect else None
            )

            transition_flags = 0
            for flag in TransitionInfoFlags:
                if dpg.get_value(f"{tag}_transition_flags_{flag.name}"):
                    transition_flags |= flag

            # Do the deed
            clip = util.new_clip(
                animation,
                mode=playback_mode,
            )
            cmsg = util.new_cmsg(
                animation.anim_id,
                name=cmsg_name,
                generators=[clip],
                animeEndEventType=animation_end_event_type,
                enableScript=True,
                enableTae=True,
                checkAnimEndSlotNo=-1,
            )
            stateinfo = util.new_stateinfo(
                name=base_name,
                generator=cmsg,
                transitions=stateinfo_transition_effect_id,
                stateId=new_state_id,
            )
            transitioninfo = util.new_transition_info(
                new_state_id,
                event,
                transition=transitioninfo_effect_id,
                flags=transition_flags,
            )

            # add stateinfo to statemachine/states array
            sm_states = statemachine["states"]
            sm_states.append(stateinfo.object_id)

            # Add transition info to statemachine
            # TODO doesn't mesh well with undo yet
            #util.register_wildcard_transition(statemachine, new_state_id, event)
            wildcard_transitions = wildcard_transitions_ptr.get_target()["transitions"]
            wildcard_transitions.append(transitioninfo)
            
        callback(dialog, (stateinfo, cmsg, clip), user_data)
        dpg.delete_item(dialog)

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
        statemachines = behavior.find_objects_by_type(sm_type)
        sm_items = [sm["name"] for sm in statemachines]

        default_sm = sm_items[0]
        if active_statemachine_id:
            default_sm = behavior.objects[active_statemachine_id]["name"].get_value()

        dpg.add_combo(
            items=sm_items,
            default_value=default_sm,
            label="Statemachine",
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
                dpg.add_text("Used to trigger the transition to the CMSG from HKS")

            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda: select_event(
                    behavior, on_event_selected, allow_clear=False
                ),
            )

            dpg.add_text("CMSG Event")

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
            # TransitionInfo
            with dpg.group(horizontal=True):

                def on_transition_selected(
                    sender: str, transition: HkbRecord, user_data: Any
                ):
                    nonlocal selected_transitioninfo_effect
                    selected_transitioninfo_effect = transition
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
                dpg.add_text("Wildcard Transition")

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text(
                    "Decides how animations are blended when transitioning to the CMSG"
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

            # AnimeEndEventType
            dpg.add_combo(
                [e.name for e in AnimeEndEventType],
                default_value=AnimeEndEventType.NONE.name,
                label="Animation End Event Type",
                tag=f"{tag}_animation_end_event_type",
            )

            # StateInfo transition pointer
            with dpg.group(horizontal=True):

                def on_pointer_selected(sender: str, target: HkbRecord, user_data: Any):
                    nonlocal selected_stateinfo_effect
                    selected_stateinfo_effect = target
                    oid = target.object_id if target else ""
                    dpg.set_value(f"{tag}_stateinfo_transitions", oid)

                dpg.add_input_text(
                    default_value="",
                    readonly=True,
                    tag=f"{tag}_stateinfo_transitions",
                )
                dpg.bind_item_theme(dpg.last_item(), style.pointer_attribute_theme)
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: select_object(*u),
                    user_data=(
                        behavior,
                        transition_effect_type_id,
                        on_pointer_selected,
                    ),
                )
                dpg.add_text("State Transitions")

            with dpg.tooltip(dpg.last_container()):
                dpg.add_text("Will be used by the new StateInfo")

        dpg.add_spacer(height=3)

        instructions = """\
Adds a new StateInfo, CMSG and Clip and adds them to a statemachine.
This essentially allows you to create entirely new animation slots.

Note that for a StateInfo to work correctly you need to do two things:
- add a '<statename>_onUpdate' function in your HKS
- add an entry to 'action/statenameid.txt' (see File/Update name ID files)
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
