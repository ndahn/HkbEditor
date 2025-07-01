from typing import Any, Callable
import re
from logging import getLogger
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags,
)
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.dialogs import select_event, select_animation_name, select_object
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui import style


_logger = getLogger(__name__)


def open_new_cmsg_dialog(
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
        tag = dpg.generate_uuid()

    types = behavior.type_registry

    # CMSG generation
    def on_okay():
        # No need to verify, okay should be disabled when values are invalid
        statemachine_val: str = dpg.get_value(f"{tag}_statemachine")
        base_name: str = dpg.get_value(f"{tag}_base_name")
        animation_val: str = dpg.get_value(f"{tag}_animation")
        event_val: str = dpg.get_value(f"{tag}_event")
        transition_val: str = dpg.get_value(f"{tag}_transition")
        playback_mode_val: str = dpg.get_value(f"{tag}_playback_mode")
        animation_end_event_type_val: str = dpg.get_value(
            f"{tag}_animation_end_event_type"
        )
        stateinfo_transitions_val: str = dpg.get_value(f"{tag}_stateinfo_transitions")

        # TODO this could be nicer
        if not all([base_name, animation_val, event_val]):
            _logger.error("Cannot create CMSG as some values were missing")
            return

        # Look up the types we need
        _logger.debug("Resolving object types")
        cmsg_type = types.find_first_type_by_name("CustomManualSelectorGenerator")
        clipgen_type = types.find_first_type_by_name("hkbClipGenerator")
        stateinfo_type = types.find_first_type_by_name("hkbStateMachine::StateInfo")
        transitioninfo_type = types.find_first_type_by_name(
            "hkbStateMachine::TransitionInfo"
        )

        # Resolve values
        _logger.debug("Resolving user values")
        statemachine_type = types.find_first_type_by_name("hkbStateMachine")
        statemachine_id = next(
            behavior.query(f"type_id:{statemachine_type} AND name:{statemachine_val}")
        ).object_id
        statemachine = behavior.objects[statemachine_id]

        wildcard_transitions_ptr = statemachine.get_field("wildcardTransitions")
        if not wildcard_transitions_ptr.get_value():
            _logger.error("Statemachine does not have a wildcard transitions object")
            return

        # stateId in StateInfo directly correlates to toStateId in the transitionInfoArray.
        # It doesn't have to be unique, but it has to match and be unique within those
        # arrays (i.e. sm.wildcardTransitions and sm.states)
        new_state_id = 0
        for existing_state_ptr in statemachine["states"]:
            existing_state = behavior.objects[existing_state_ptr.get_value()]
            new_state_id = max(new_state_id, existing_state["stateId"].get_value() + 1)

        cmsg_name = base_name
        if base_name.endswith("_CMSG"):
            base_name = base_name[:-5]
        if not cmsg_name.endswith("_CMSG"):
            cmsg_name += "_CMSG"

        # Add entry to animations array. We also need the parts in some places
        _, anim_y = animation_val.split("_")
        try:
            anim_idx = behavior.find_animation(animation_val)
        except IndexError:
            _logger.debug("Creating new animation name %s", animation_val)
            # TODO undo action
            anim_idx = behavior.create_animation(animation_val)

        # Add event to the events array
        try:
            event_id = behavior.find_event(event_val)
        except IndexError:
            _logger.debug("Creating new event %s", event_val)
            # TODO undo action
            event_id = behavior.create_event(event_val)

        playback_mode = PlaybackMode[playback_mode_val].value
        animation_end_event_type = AnimeEndEventType[animation_end_event_type_val].value

        transition_type = types.find_first_type_by_name("hkbTransitionEffect")
        transitions = behavior.find_objects_by_type(
            transition_type, include_derived=True
        )
        transition_id = next(
            t.object_id for t in transitions if t["name"].get_value() == transition_val
        )

        transition_flags = 0
        for flag in TransitionInfoFlags:
            if dpg.get_value(f"{tag}_transitioninfo_flag_{flag.name}"):
                transition_flags |= flag

        # Generate the new objects
        cmsg_id = behavior.new_id()
        clipgen_id = behavior.new_id()
        stateinfo_id = behavior.new_id()

        cmsg = HkbRecord.new(
            behavior,
            cmsg_type,
            {
                "name": cmsg_name,
                "animId": anim_y,
                "animeEndEventType": animation_end_event_type,
                "enableScript": True,
                "enableTae": True,
                "generators": [clipgen_id],  # TODO probably won't work like this
            },
            cmsg_id,
        )
        clipgen = HkbRecord.new(
            behavior,
            clipgen_type,
            {
                "name": f"{animation_val}_{base_name}",
                "animationName": animation_val,
                "mode": playback_mode,
                "animationInternalId": anim_idx,
            },
            clipgen_id,
        )
        stateinfo = HkbRecord.new(
            behavior,
            stateinfo_type,
            {
                "name": base_name,
                "generator": cmsg_id,
                "transitions": stateinfo_transitions_val,
                "stateId": new_state_id,
            },
            stateinfo_id,
        )
        transitioninfo = HkbRecord.new(
            behavior,
            transitioninfo_type,
            {
                "transition": transition_id,
                "eventId": event_id,
                "toStateId": new_state_id,
                "flags": transition_flags,
            },
            # No object ID, this one lives inside an array
        )

        with undo_manager.combine():
            # Add objects with IDs to behavior
            undo_manager.on_create_object(behavior, cmsg)
            behavior.add_object(cmsg)

            undo_manager.on_create_object(behavior, clipgen)
            behavior.add_object(clipgen)

            undo_manager.on_create_object(behavior, stateinfo)
            behavior.add_object(stateinfo)

            # add stateinfo to statemachine/states array
            sm_states: HkbArray = statemachine.get_field("states")
            stateinfo_pointer = HkbPointer.new(
                behavior, sm_states.element_type_id, stateinfo_id
            )
            undo_manager.on_update_array_item(sm_states, -1, None, stateinfo_pointer)
            sm_states.append(stateinfo_pointer)

            # Add transition info to statemachine
            wildcard_transitions_obj = behavior.objects[
                wildcard_transitions_ptr.get_value()
            ]
            wildcard_transitions: HkbArray = wildcard_transitions_obj["transitions"]
            undo_manager.on_update_array_item(
                wildcard_transitions, -1, None, transitioninfo
            )
            wildcard_transitions.append(transitioninfo)

        # TODO tell user where to place generated event(s)

        callback(dialog, (cmsg_id, clipgen_id, stateinfo_id), user_data)
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
                readonly=True,
                tag=f"{tag}_event",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Used to trigger the transition to the CMSG from HKS")

            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda s, a, u: select_event(*u),
                user_data=(behavior, on_event_selected),
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
                readonly=True,
                tag=f"{tag}_animation",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Animation ID the ClipGenerator uses")

            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda s, a, u: select_animation_name(*u),
                user_data=(behavior, on_animation_selected),
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
            transition_type = types.find_first_type_by_name("hkbTransitionEffect")
            transitions = behavior.find_objects_by_type(
                transition_type, include_derived=True
            )
            transition_items = [t["name"].get_value() for t in transitions]
            default_transition = (
                "TaeBlend" if "TaeBlend" in transition_items else transition_items[0]
            )

            # TODO search dialog, option to create new -> general "new object" dialog
            dpg.add_combo(
                items=transition_items,
                default_value=default_transition,
                label="Transition",
                tag=f"{tag}_transition",
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text(
                    "Decides how animations are blended when transitioning to the CMSG"
                )

            # TransitionInfo flags
            with dpg.tree_node(label="Transition Flags"):
                for flag in TransitionInfoFlags:
                    dpg.add_checkbox(label=flag.name, tag=f"{tag}_transitioninfo_flag_{flag.name}")

            # AnimeEndEventType
            dpg.add_combo(
                [e.name for e in AnimeEndEventType],
                default_value=AnimeEndEventType.NONE.name,
                label="Animation End Event Type",
                tag=f"{tag}_animation_end_event_type",
            )

            # StateInfo transition pointer
            # TODO we probably need a table to get a clean layout
            with dpg.group(horizontal=True):

                def on_pointer_selected(sender: str, target: HkbRecord, user_data: Any):
                    dpg.set_value(f"{tag}_stateinfo_transitions", target.object_id)

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
                    user_data=(behavior, transition_type, on_pointer_selected),
                )
                dpg.add_text("StateInfo Transitions")

        dpg.add_spacer(height=3)

        # Main form done, now just some buttons and such
        dpg.add_separator()
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
