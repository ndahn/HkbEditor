from typing import Any
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray


def open_state_graph_viewer(
    behavior: HavokBehavior,
    statemachine_id: str,
    *,
    title: str = "State Graph Viewer",
    tag: str = 0,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    statemachines = {sm.object_id: sm for sm in behavior.find_objects_by_type(sm_type)}
    smids = sorted(smid for smid in statemachines.keys())
    sm_items = [statemachines[smid]["name"] for smid in smids]

    def on_statemachine_selected(sender: str, statemachine_name: str, user_data: Any):
        sm = next(sm for sm in statemachines.values() if sm["name"] == statemachine_name)
        
        state_pointers: HkbArray = sm["states"]
        states = [behavior.objects[ptr.get_value()] for ptr in state_pointers]
        #states = {s["stateId"]:s for s in state_records}

        transitions_array: HkbRecord = behavior.objects[sm["wildcardTransitions"].get_value()]
        transitions: HkbArray = transitions_array["transitions"]
        
        g = nx.DiGraph()

        for s in states:
            g.add_node(s["stateId"].get_value(), name=s["state"])

        prev_state = sm["startStateId"].get_value()

        for t in transitions:
            # toStateID is the state this refers to, NOT where the transition goes to!
            to_state = t["toStateId"].get_value()
            event_idx = t["eventId"].get_value()
            event_name = behavior.get_event(event_idx)
            g.add_edge(prev_state, to_state, event_name=event_name)


    with dpg.window(
        label=title,
        size=(400, 400),
        on_close=lambda: dpg.delete_item(window),
        tag=tag,
    ) as window:
        dpg.add_combo(
            sm_items, 
            default_value=statemachines[statemachine_id]["name"],
            callback=on_statemachine_selected,
        )

        dpg.add_separator()

        with dpg.drawlist(400, 400, tag=f"{tag}_canvas"):
            pass
