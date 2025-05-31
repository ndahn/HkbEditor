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
        state_records = [behavior.objects[ptr.get_value()] for ptr in state_pointers]
        states = {s["name"].get_value():s for s in state_records}

        transitions_array: HkbRecord = behavior.objects[sm["wildcardTransitions"].get_value()]
        transitions: HkbArray = transitions_array["transitions"]
        
        g = nx.DiGraph()

        for sname, s in states.items():
            g.add_node(s["stateId"].get_value(), name=sname)

        for idx, event in enumerate(behavior.get_events()):
            if "_to_" in event:
                src, dst = event.split("_to_")
                if src in states and dst in states:
                    g.add_edge(src, dst, event=event, idx=idx)
                else:
                    if src in states or dst in states:
                        # Can this even happen? Should we add an "external" node?
                        print(f"Event {event} has only one edge connected in the current SM")

        # TODO Planar or circular are probably best?
        pos = nx.layout.planar_layout(g, scale=400, center=(0, 0))

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
