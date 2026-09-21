from typing import Any, Callable
from dataclasses import dataclass
import logging
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray
from hkb_editor.gui.helpers import make_copy_menu
from hkb_editor.gui.widgets import DpgItem, GraphWidget
from hkb_editor.gui.widgets.graph_layout import HorizontalGraphLayout, Node


_logger = logging.getLogger(__name__)

_layout_functions = {
    "Planar": nx.layout.planar_layout,
    "Circular": nx.layout.circular_layout,
}


@dataclass
class CachedLayout(HorizontalGraphLayout):
    """A layout that simply replays pre-computed node positions."""

    cache: dict[str, tuple[float, float]] = None

    def get_pos_for_node(
        self, graph: nx.DiGraph, node: Node, nodemap: dict[str, Node]
    ) -> tuple[float, float]:
        return self.cache[node.id]


def get_statemachines(behavior: HavokBehavior) -> dict[str, HkbRecord]:
    """All hkbStateMachine records, keyed by object ID."""
    sm_type = behavior.type_registry.find_first_type_by_name("hkbStateMachine")
    return {sm.object_id: sm for sm in behavior.find_objects_by_type(sm_type)}


def build_state_graph(
    behavior: HavokBehavior, statemachine: HkbRecord
) -> nx.DiGraph:
    """Build the state transition graph of a state machine.

    Nodes are state names carrying ``record`` and ``state_id``; edges come
    from events named ``<source>_to_<target>`` and carry ``event`` and the
    event's ``idx``.
    """
    state_pointers: HkbArray = statemachine["states"]
    state_records = sorted(
        (behavior.objects[ptr.get_value()] for ptr in state_pointers),
        key=lambda s: s["stateId"].get_value(),
    )
    states_by_id = {s["stateId"].get_value(): s for s in state_records}
    states_by_name = {s["name"].get_value(): s for s in states_by_id.values()}

    g = nx.DiGraph()

    for sname, state in states_by_name.items():
        g.add_node(sname, record=state, state_id=state["stateId"].get_value())

    for idx, event in enumerate(behavior.get_events()):
        if "_to_" not in event:
            continue

        src, dst = event.split("_to_", maxsplit=1)
        if src in states_by_name and dst in states_by_name:
            g.add_edge(src, dst, event=event, idx=idx)
        elif src in states_by_name or dst in states_by_name:
            # Can this even happen? Should we add an "external" node?
            _logger.debug(
                f"Event {event} has only one edge connected in the current SM"
            )

    return g


class state_graph_viewer_dialog(DpgItem):
    """Draw a state machine's transitions as a graph.

    Transitions are derived from event names of the form
    ``<source>_to_<target>``. The node layout is computed with networkx and
    then handed to the graph widget through a :class:`CachedLayout`.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to read state machines from.
    statemachine_id : str or None
        Object ID of the state machine to show first; falls back to any.
    jump_callback : callable, optional
        Called as ``callback(tag, record, user_data)`` from the context menu.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    user_data : any, optional
        Passed through to ``jump_callback``.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        statemachine_id: str,
        *,
        jump_callback: Callable[[str, str, Any], None] = None,
        title: str = "State Graph Viewer",
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._jump_callback = jump_callback
        self._user_data = user_data

        self._window: str = None
        self._canvas: GraphWidget = None
        self._graph_layout = CachedLayout()
        self._statemachines = get_statemachines(behavior)

        if statemachine_id:
            default_sm = self._statemachines[statemachine_id]["name"].get_value()
        else:
            default_sm = next(iter(self._statemachines.values()))["name"].get_value()

        self._build(title, default_sm)

        dpg.split_frame()
        self.refresh()

    def destroy(self) -> None:
        # Make sure the canvas can clean up its handlers and so on
        if self._canvas is not None:
            self._canvas.destroy()
            self._canvas = None

        # Popups are root level items and outlive the window
        self._delete_item(self._t("context_popup"))

    # === Build ========================================================

    def _build(self, title: str, default_sm: str) -> None:
        sm_items = sorted(
            sm["name"].get_value() for sm in self._statemachines.values()
        )

        with dpg.window(
            label=title,
            width=850,
            height=600,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
            no_saved_settings=True,
            horizontal_scrollbar=False,
            tag=self._tag,
            on_close=self.close,
        ) as self._window:
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
                    self._canvas = GraphWidget(
                        None,
                        self._graph_layout,
                        on_node_selected=None,
                        node_menu_func=self._on_context_menu,
                        get_node_frontpage=self._get_node_frontpage,
                        get_edge_label=self._get_edge_label,
                        rainbow_edges=True,
                        select_enabled=False,
                        edge_style="straight",
                        # larger canvas to compensate it not resizing
                        width=1000,
                        height=1000,
                        tag=self._t("graph_widget"),
                    )

                with dpg.group(width=150):
                    dpg.add_combo(
                        sm_items,
                        default_value=default_sm,
                        callback=self.refresh,
                        width=100,
                        label="Statemachine",
                        tag=self._t("statemachine"),
                    )
                    dpg.add_combo(
                        list(_layout_functions.keys()),
                        default_value=next(iter(_layout_functions)),
                        callback=self.refresh,
                        width=100,
                        label="Layout",
                        tag=self._t("layout"),
                    )
                    dpg.add_slider_int(
                        default_value=500,
                        min_value=50,
                        max_value=1000,
                        clamped=True,
                        callback=self.refresh,
                        width=100,
                        label="Node separation",
                        tag=self._t("node_separation"),
                    )

    # === DPG callbacks ================================================

    def _get_node_frontpage(self, node: Node) -> str:
        state_id = self._canvas.graph.nodes(data=True)[node.id]["state_id"]
        return f"{node.id} ({state_id})"

    def _get_edge_label(self, node_a: Node, node_b: Node) -> str:
        edge = self._canvas.graph.edges[node_a.id, node_b.id]
        if edge:
            return edge.get("event")
        return None

    def _on_context_menu(self, item: Node) -> None:
        # Only one context menu can be open at a time
        self._delete_item(self._t("context_popup"))

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            autosize=True,
            no_saved_settings=True,
            tag=self._t("context_popup"),
            on_close=lambda: self._delete_item(self._t("context_popup")),
        ) as popup:
            make_copy_menu(item.user_data)
            if self._jump_callback:
                dpg.add_separator()
                dpg.add_selectable(
                    label="Jump To",
                    callback=lambda: self._jump_callback(
                        self._tag, item.user_data["record"], self._user_data
                    ),
                )

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))
        dpg.show_item(popup)

    # === Public =======================================================

    @property
    def statemachine(self):
        """The state machine currently on display."""
        name = dpg.get_value(self._t("statemachine"))
        return next(
            sm
            for sm in self._statemachines.values()
            if sm["name"].get_value() == name
        )

    # TODO layout works fine, but node separation is bad with many nodes
    def refresh(self) -> None:
        """Rebuild and re-layout the graph from the current selection."""
        dpg.delete_item(self._t("canvas_root"), children_only=True)

        g = build_state_graph(self._behavior, self.statemachine)

        # Adjust scaling and center to canvas size and origin
        # TODO once resizing the canvas with its container works we can do this properly
        # canvas_size = dpg.get_item_rect_size(self._canvas.canvas)
        # center = (canvas_size[0] / 2, canvas_size[1] / 2)
        center = (300, 300)
        separation = dpg.get_value(self._t("node_separation"))
        layout_name = dpg.get_value(self._t("layout"))

        pos = _layout_functions[layout_name](g)
        pos = nx.spring_layout(g, 1, pos=pos, scale=separation, center=center)
        self._graph_layout.cache = pos

        self._canvas.set_graph(g)
        self._canvas.reveal_all_nodes()
        self._canvas.set_origin(0, 0)

    def close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)
