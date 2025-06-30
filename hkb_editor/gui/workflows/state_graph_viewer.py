from dataclasses import dataclass, InitVar
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.gui.graph_widget import GraphWidget
from hkb_editor.gui.graph_layout import GraphLayout, Node
from hkb_editor.gui import style


@dataclass
class CachedLayout(GraphLayout):
    cache: dict[str, tuple[float, float]] = None

    def get_pos_for_node(
        self, graph: nx.DiGraph, node: Node, nodemap: dict[str, Node]
    ) -> tuple[float, float]:
        return self.cache[node.id]


def open_state_graph_viewer(
    behavior: HavokBehavior,
    statemachine_id: str,
    *,
    title: str = "State Graph Viewer",
    tag: str = 0,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    layout_functions = {
        "Planar": nx.layout.planar_layout,
        "Circular": nx.layout.circular_layout,
    }
    graph_layout = CachedLayout()

    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    statemachines = {sm.object_id: sm for sm in behavior.find_objects_by_type(sm_type)}
    sm_items = sorted(sm["name"].get_value() for sm in statemachines.values())

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

        # TODO useful?
        transition_array_id = selected_sm["wildcardTransitions"].get_value()
        if transition_array_id:
            transitions_array: HkbRecord = behavior.objects[transition_array_id]
            transitions: HkbArray = transitions_array["transitions"]

        g = nx.DiGraph()
        
        for sname, state in states_by_name.items():
            state_id = states_by_name[sname]["stateId"].get_value()
            g.add_node(sname, state_id=state_id)

        for idx, event in enumerate(behavior.get_events()):
            if "_to_" in event:
                src, dst = event.split("_to_", maxsplit=1)
                if src in states_by_name and dst in states_by_name:
                    g.add_edge(src, dst, event=event, idx=idx)
                else:
                    if src in states_by_name or dst in states_by_name:
                        # Can this even happen? Should we add an "external" node?
                        print(
                            f"Event {event} has only one edge connected in the current SM"
                        )
        
        # TODO adjust scaling and center to canvas size and origin
        pos = layout_functions[layout_name](g)
        pos = nx.spring_layout(g, 1, pos=pos, scale=300, center=(350, 350))
        graph_layout.cache = pos

        canvas.set_graph(g)
        canvas.reveal_all()

    def get_node_frontpage(node: Node) -> str:
        state_id = canvas.graph.nodes(data=True)[node.id]["state_id"]
        return f"{node.id} ({state_id})"

    def get_edge_label(node_a: Node, node_b: Node) -> str:
        edge = canvas.graph.edges[node_a.id, node_b.id]
        if edge:
            event = edge.get("event")
            if event:
                return event
        return None

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
            tag=f"{tag}_statemachine",
        )
        dpg.add_combo(
            list(layout_functions.keys()),
            default_value=next(x for x in layout_functions.keys()),
            callback=refresh,
            tag=f"{tag}_layout",
        )

        dpg.add_separator()
        canvas = GraphWidget(
            None,
            graph_layout,
            on_node_selected=None,
            node_menu_func=None,
            get_node_frontpage=get_node_frontpage,
            get_edge_label=get_edge_label,
            select_enabled=False,
            edge_style="straight",
        )

    refresh()
