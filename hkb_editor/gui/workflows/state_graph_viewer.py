from typing import Any, Callable
from dataclasses import dataclass
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.gui.graph_widget import GraphWidget
from hkb_editor.gui.graph_layout import GraphLayout, Node
from hkb_editor.gui.helpers import make_copy_menu


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
    jump_callback: Callable[[str, str, Any], None] = None,
    title: str = "State Graph Viewer",
    tag: str = None,
    user_data: Any = None,
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
            g.add_node(sname, record=state, state_id=state_id)

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

        # Adjust scaling and center to canvas size and origin
        # TODO once resizing the canvas with its container works we can do this properly
        #canvas_size = dpg.get_item_rect_size(canvas.canvas)
        #center = (canvas_size[0] / 2, canvas_size[1] / 2)
        center = (300, 300)
        separation = dpg.get_value(f"{tag}_node_separation")

        pos = layout_functions[layout_name](g)
        pos = nx.spring_layout(g, 1, pos=pos, scale=separation, center=center)
        graph_layout.cache = pos

        canvas.set_graph(g)
        canvas.reveal_all_nodes()
        canvas.set_origin(0, 0)

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

    def open_context_menu(item: Node) -> None:
        popup = f"{tag}_popup"

        if dpg.does_item_exist(popup):
            dpg.delete_item(popup)

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            autosize=True,
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(popup),
            tag=popup,
        ):
            make_copy_menu(item)
            if jump_callback:
                dpg.add_separator()
                dpg.add_selectable(
                    label="Jump To",
                    callback=lambda: jump_callback(
                        window, item.user_data["record"], user_data
                    ),
                )

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))
        dpg.show_item(popup)

    def on_close():
        # Make sure the canvas can clean up its handlers and so on
        canvas.deinit()
        dpg.delete_item(window)

    if statemachine_id:
        default_sm = statemachines[statemachine_id]["name"].get_value()
    else:
        default_sm = next(sm for sm in statemachines.values())["name"].get_value()

    with dpg.window(
        label=title,
        width=800,
        height=600,
        no_scroll_with_mouse=True,
        no_scrollbar=True,
        no_saved_settings=True,
        horizontal_scrollbar=False,
        tag=tag,
        on_close=on_close,
    ) as window:
        with dpg.group(horizontal=True):
            # TODO Child window does not work with item_resize_handler
            # so adjusting the canvas size is difficult
            with dpg.child_window(
                width=600,
                resizable_x=True,
                autosize_y=True,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
                horizontal_scrollbar=False,
            ):
                canvas = GraphWidget(
                    None,
                    graph_layout,
                    on_node_selected=None,
                    node_menu_func=open_context_menu,
                    get_node_frontpage=get_node_frontpage,
                    get_edge_label=get_edge_label,
                    rainbow_edges=True,
                    select_enabled=False,
                    edge_style="straight",
                    width=1000,  # larger canvas to compensate it not resizing
                    height=1000,
                )

            with dpg.group(width=200):
                dpg.add_combo(
                    sm_items,
                    default_value=default_sm,
                    callback=refresh,
                    width=100,
                    label="Statemachine",
                    tag=f"{tag}_statemachine",
                )
                dpg.add_combo(
                    list(layout_functions.keys()),
                    default_value=next(x for x in layout_functions.keys()),
                    callback=refresh,
                    width=100,
                    label="Layout",
                    tag=f"{tag}_layout",
                )
                dpg.add_slider_int(
                    default_value=500,
                    min_value=50,
                    max_value=1000,
                    clamped=True,
                    callback=refresh,
                    width=100,
                    label="Node separation",
                    tag=f"{tag}_node_separation",
                )

    dpg.split_frame()
    refresh()
