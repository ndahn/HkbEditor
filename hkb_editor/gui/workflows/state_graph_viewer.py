from typing import Any
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.gui.helpers import draw_graph_node, estimate_drawn_text_size
from hkb_editor.gui import style


def open_state_graph_viewer(
    behavior: HavokBehavior,
    statemachine_id: str,
    *,
    title: str = "State Graph Viewer",
    tag: str = 0,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    graph_layouts = {
        "Planar": nx.layout.planar_layout,
        "Circular": nx.layout.circular_layout,
    }

    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    statemachines = {sm.object_id: sm for sm in behavior.find_objects_by_type(sm_type)}
    sm_items = sorted(sm["name"].get_value() for sm in statemachines.values())

    # TODO should make a general "graph canvas" widget
    # TODO mouse interactions
    # TODO layout works fine, but node separation is bad with many nodes
    def refresh():
        dpg.delete_item(f"{tag}_canvas_root", children_only=True)

        statemachine_name = dpg.get_value(f"{tag}_statemachine")
        layout_name = dpg.get_value(f"{tag}_layout")

        selected_sm = next(
            sm
            for sm in statemachines.values()
            if sm["name"].get_value() == statemachine_name
        )

        state_pointers: HkbArray = selected_sm["states"]
        state_records = sorted(
            (behavior.objects[ptr.get_value()] for ptr in state_pointers),
            key=lambda s: s["stateId"].get_value(),
        )
        states_by_id = {s["stateId"].get_value(): s for s in state_records}
        states_by_name = {s["name"].get_value(): s for s in states_by_id.values()}

        transition_array_id = selected_sm["wildcardTransitions"].get_value()
        if transition_array_id:
            transitions_array: HkbRecord = behavior.objects[transition_array_id]
            transitions: HkbArray = transitions_array["transitions"]

        g = nx.DiGraph()

        for sname, state in states_by_name.items():
            g.add_node(sname)

        for idx, event in enumerate(behavior.get_events()):
            if "_to_" in event:
                src, dst = event.split("_to_")
                if src in states_by_name and dst in states_by_name:
                    g.add_edge(src, dst, event=event, idx=idx)
                else:
                    if src in states_by_name or dst in states_by_name:
                        # Can this even happen? Should we add an "external" node?
                        print(
                            f"Event {event} has only one edge connected in the current SM"
                        )

        # TODO adjust scaling and center to canvas size and origin
        pos = graph_layouts[layout_name](g)
        pos = nx.spring_layout(g, 1, pos=pos, scale=300, center=(350, 350))

        # Draw edges first so that nodes will be on top
        for src, dst, event in g.edges(data="event"):
            with dpg.draw_node(parent=f"{tag}_canvas_root"):
                p1 = pos[src]
                p2 = pos[dst]
                dpg.draw_line(p1, p2)

                # TODO render text to buffer and rotate to match edge
                tw, th = estimate_drawn_text_size(len(event), font_size=11)
                tx = (p1[0] + p2[0]) * 2 / 5 - tw / 2
                ty = (p1[1] + p2[1]) * 2 / 5 - th / 2
                dpg.draw_text((tx, ty), event, size=11)

        for sname in g.nodes:
            state_pos = pos[sname]
            state_id = states_by_name[sname]["stateId"].get_value()
            w, h = draw_graph_node(
                [f"{sname} ({state_id})"],
                tag=f"{tag}_state_{sname}",
                parent=f"{tag}_canvas_root",
            )
            # Nodes need to be centered on the position so the edges show up correctly
            dpg.apply_transform(
                f"{tag}_state_{sname}",
                dpg.create_translation_matrix(
                    [
                        state_pos[0] - w / 2,
                        state_pos[1] - h / 2,
                    ]
                ),
            )

    if statemachine_id:
        default_sm = statemachines[statemachine_id]["name"].get_value()
    else:
        default_sm = next(sm for sm in statemachines.values())["name"].get_value()

    with dpg.window(
        label=title,
        width=800,
        height=800,
        on_close=lambda: dpg.delete_item(window),
        tag=tag,
    ) as window:
        dpg.add_combo(
            sm_items,
            default_value=default_sm,
            callback=refresh,
            tag=f"{tag}_statemachine"
        )
        dpg.add_combo(
            list(graph_layouts.keys()),
            default_value=next(x for x in graph_layouts.keys()),
            callback=refresh,
            tag=f"{tag}_layout",
        )

        dpg.add_separator()
        with dpg.drawlist(800, 700, tag=f"{tag}_canvas"):
            dpg.add_draw_node(tag=f"{tag}_canvas_root")

    refresh()
