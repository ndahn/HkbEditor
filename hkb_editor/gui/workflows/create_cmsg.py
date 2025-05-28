from typing import Any, Callable
import re
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer, HkbString
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.gui import style


def open_new_cmsg_dialog(
    behavior: HavokBehavior,
    active_statemachine: str = None,
    tag: str = 0,
    callback: Callable[
        [str, tuple[HkbRecord, HkbRecord, HkbRecord, HkbRecord], Any], None
    ] = None,
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
    animation_regex = re.compile(r"a\d{3}_\d{6}")
    event_regex = re.compile(r"\w+")

    # CMSG generation
    def on_okay():
        # No need to verify, okay should be disabled when values are invalid
        base_name: str = dpg.get_value(f"{tag}_base_name")
        statemachine_val: str = dpg.get_value(f"{tag}_statemachine")
        transition_val: str = dpg.get_value(f"{tag}_transition")
        animation_val: str = dpg.get_value(f"{tag}_animation")
        event_val: str = dpg.get_value(f"{tag}_event")

        # Look up the types we need
        cmsg_type = types.find_type_by_name("CustomGeneratorManualSelector")
        clipgen_type = types.find_type_by_name("hkbClipGenerator")
        stateinfo_type = types.find_type_by_name("hkbStateMachine::StateInfo")
        transitioninfo_type = types.find_type_by_name("hkbStateMachine::TransitionInfo")

        # Resolve values
        cmsg_name = base_name
        if not base_name.endswith("_CMSG"):
            base_name -= "_CMSG"
        
        statemachine_type = types.find_type_by_name("hkbStateMachine")
        statemachine_id = next(
            behavior.query(f"type_id:{statemachine_type} AND name:{statemachine_val}")
        ).object_id

        # TODO include derived types
        transition_type = types.find_type_by_name("hkbTransitionEffect")
        transitions = behavior.find_objects_by_type(transition_type)
        transition_id = next(t.object_id for t in transitions if t["name"] == transition_val)

        # Add entry to animations array
        anim_anum, anim_id = animation_val.split("_")
        
        hkb_graph_type = types.find_type_by_name("hkbBehaviorGraph")
        hkb_graph_obj = next(behavior.find_objects_by_type(hkb_graph_type))
        # TODO is this reliable?
        char_id = hkb_graph_obj["name"].split(".")[0]

        full_anim_name = f"..\..\..\..\..\Model\chr\{char_id}\hkx\{anim_anum}\{animation_val}.hkx"
        try:
            anim_id = behavior.animations.index(full_anim_name)
        except ValueError:
            anim_id = behavior.create_animation(full_anim_name)

        # Fix event name and add it to the events array
        if not event_val.startswith("W_"):
            event_val = "W_" + event_val
        
        try:
            event_id = behavior.events.index(event_val)
        except ValueError:
            event_id = behavior.create_event(event_val)

        # behavior.new_id will not advance until the object has been added, so we generate it later
        cmsg_id = behavior.reserve_id()
        clipgen_id = behavior.reserve_id()
        stateinfo_id = behavior.reserve_id()
        transitioninfo_id = behavior.reserve_id()

        cmsg = HkbRecord.new(
            behavior,
            cmsg_type,
            {
                "name": cmsg_name,
                "animId": anim_anum,
                "animeEndEventType": animend_mode,  # TODO fire idle event, etc
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
                "mode": clipgen_mode,  # TODO single play, loop, etc
                "animationInternalId": anim_id,
            },
            clipgen_id,
        )
        stateinfo = HkbRecord.new(
            behavior,
            stateinfo_type,
            {
                "name": base_name,
                "generator": cmsg_id,
                "transitions": transitioninfoarray_id,  # TODO create new
                # stateId in StateInfo directly correlates to toStateId in the transitionInfoArray.
                # It doesn't have to be unique, but it has to be unique within that array
                "stateId": stateid_val,  # TODO do we need this?
            },
            stateinfo_id,
        )
        # TODO needs to live inside a TransitionInfoArray
        transitioninfo = HkbRecord.new(
            behavior,
            transitioninfo_type,
            {
                "transition": transition_id,
                "eventId": event_id,
                # See stateId above
                # TODO has to match stateId above and must be unique within transition array
                "toStateId": tostate_id,
                "flags": 3584,  # TODO Who knows what this does, but it's always set
            },
            transitioninfo_id,
        )

        # add stateinfo to statemachine/states array
        statemachine = behavior.objects[statemachine_id]
        sm_states: HkbArray = statemachine.get_field("states")
        sm_states.append(HkbPointer.new(behavior, sm_states.element_type_id, stateinfo_id))
        
        # TODO set/update wildcard transition?

        # TODO tell user where to place generated event(s)

        callback(dialog, selected, user_data)
        dpg.delete_item(dialog)

    def on_cancel():
        dpg.delete_item(dialog)

    # Input verification
    def check_animation_name(anim: str) -> bool:
        return re.fullmatch(animation_regex, anim)

    def check_event_name(event: str) -> bool:
        return re.fullmatch(event_regex, event)

    def verify_animation(sender: str, value: str):
        if check_animation_name(value):
            dpg.bind_item_theme(sender, style.input_field_okay_theme)
            dpg.enable_item(f"{tag}_button_okay")
        else:
            dpg.bind_item_theme(sender, style.input_field_error_theme)
            dpg.disable_item(f"{tag}_button_okay")

    def verify_event(sender: str, value: str):
        if check_event_name(value):
            dpg.bind_item_theme(sender, style.input_field_okay_theme)
            dpg.enable_item(f"{tag}_button_okay")
        else:
            dpg.bind_item_theme(sender, style.input_field_error_theme)
            dpg.disable_item(f"{tag}_button_okay")

    # Dialog content
    with dpg.window(
        label="Create CMSG",
        width=400,
        height=600,
        on_close=on_cancel,
        tag=tag,
    ) as dialog:
        dpg.add_input_text(
            default_value="",
            label="CMSG Name",
            tag=f"{tag}_base_name",
        )

        sm_type = types.find_type_by_name("hkbStateMachine")
        statemachines = behavior.find_objects_by_type(sm_type)
        sm_items = [sm["name"] for sm in statemachines]
        dpg.add_combo(
            items=sm_items,
            default_value=(
                active_statemachine["name"] if active_statemachine else sm_items[0]
            ),
            label="Statemachine",
            tag=f"{tag}_statemachine",
        )

        transition_type = types.find_type_by_name("hkbTransitionEffect")
        transitions = behavior.find_objects_by_type(transition_type)
        transition_items = [t["name"] for t in transitions]
        dpg.add_combo(
            items=transition_items,
            default_value="TaeBlend",  # TODO verify it exists
            label="Transition",
            tag=f"{tag}_transition",
        )

        dpg.add_input_text(
            default_value="a000_000000",
            no_spaces=True,
            callback=verify_animation,
            label="Animation",
            tag=f"{tag}_animation",
        )

        # Must not exist yet
        dpg.add_input_text(
            default_value="W_",
            no_spaces=True,
            callback=verify_event,
            label="Event",
            tag=f"{tag}_event",
        )

        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=on_cancel,
            )
