from typing import Callable
import dearpygui.dearpygui as dpg
import numpy as np
import networkx as nx
from pykdtree.kdtree import KDTree

from hkb_editor.gui import style
from .dpg_item import DpgItem


class GraphMap(DpgItem):
    def __init__(
        self,
        graph: nx.DiGraph,
        get_node_data: Callable[[str], list[str | tuple[str]]],
        on_click_callback: Callable[[str], None],
        tag: str,
    ):
        self.graph: nx.DiGraph = None
        self.get_node_data = get_node_data
        self.on_click_callback = on_click_callback
        self.callback_triggered = False

        # self.tag comes from DpgItem
        super().__init__(tag)

        self._nodes: list[str] = []
        self._node_radius = 10
        self._max_tooltip_lines = 6
        self._graph_extends: tuple[float, float] = None
        self._node_lookup: KDTree = None
        self._highlighted_node = None
        self._handler_tag = f"{self.tag}_handlers"

        # Draw items are addressed by integer id rather than looked up by string
        # tag every frame. Index i of _node_items belongs to _nodes[i], and
        # index j of _edge_items to _edges[j].
        self._edges: list[tuple[str, str]] = []
        self._node_items: list[int] = []
        self._edge_items: list[int] = []
        self._node_index: dict[str, int] = {}
        self._edge_index: dict[tuple[str, str], int] = {}
        self._items_built = False
        # Which items currently have show=True, so we only toggle on change
        self._shown_nodes: set[int] = set()
        self._shown_edges: set[int] = set()
        # Last transform seen by _render; used to skip frames where nothing moved
        self._prev_anchor: tuple[float, float] = None
        self._prev_scale: float = None

        self._setup_content()
        self.set_graph(graph)

    def destroy(self):
        # Prevent double deinitialization
        if getattr(self, "_deinitialized", False):
            return

        # Disable mouse callbacks in the brief window until the handlers are removed
        self._node_lookup = None

        # Disable all handlers in case deletion fails (see below)
        registry_tag = self._handler_tag
        if dpg.does_item_exist(registry_tag):
            dpg.configure_item(registry_tag, show=False)

        # Delete the drawable content
        if dpg.does_item_exist(self.tag):
            dpg.delete_item(self.tag)

        # Schedule handler registry deletion for later, otherwise this can sometimes lead
        # to silent program crashes. This is the only solution I have found to this.
        def delayed_cleanup():
            if dpg.does_item_exist(registry_tag):
                for listener in dpg.get_item_children(registry_tag, 1):
                    dpg.delete_item(listener)
                dpg.delete_item(registry_tag)

        with dpg.mutex():
            # Calling delayed_cleanup directly sometimes leads to a silent crash.
            # Unfortunately, this is not guaranteed to run due to a bug in dearpygui, see
            # https://github.com/hoffstadt/DearPyGui/issues/2269
            dpg.set_frame_callback(dpg.get_frame_count() + 5, delayed_cleanup)

    # Kept for callers that predate the DpgItem convention
    deinit = destroy

    def __del__(self) -> None:
        self._delete_item(self._handler_tag)
        super().__del__()

    def _setup_content(self) -> None:
        with dpg.group(tag=self.tag):
            with dpg.plot(
                width=-1,
                height=-25,
                no_mouse_pos=True,
                no_menus=True,
                no_box_select=True,
                pan_button=dpg.mvMouseButton_Middle,
                tag=f"{self.tag}_plot",
            ):
                dpg.add_plot_axis(
                    dpg.mvXAxis,
                    show=True,
                    #no_highlight=True,
                    no_tick_marks=True,
                    no_tick_labels=True,
                    no_menus=True,
                    tag=f"{self.tag}_x_axis",
                )
                dpg.add_plot_axis(
                    dpg.mvYAxis,
                    show=True,
                    #no_highlight=True,
                    no_tick_marks=True,
                    no_tick_labels=True,
                    no_menus=True,
                    tag=f"{self.tag}_y_axis",
                )
                    
        # handlers
        if not dpg.does_item_exist(self._handler_tag):
            dpg.add_handler_registry(tag=self._handler_tag)

        dpg.add_mouse_move_handler(
            callback=self._on_mouse_move, parent=self._handler_tag
        )
        dpg.add_mouse_click_handler(
            button=dpg.mvMouseButton_Left,
            callback=self._on_mouse_click, parent=self._handler_tag,
        )

    def get_node_at(self, pos: tuple[float, float]) -> str:
        if self._node_lookup:
            dist, idx = self._node_lookup.query(
                np.array([pos]),
                k=1,
                distance_upper_bound=self._node_radius / 2,
            )
            if dist < np.inf:
                return self._nodes[int(idx[0])]

        return None

    def get_zoom(self) -> tuple[float, float]:
        if not self._graph_extends or any(x == 0 for x in self._graph_extends):
            return (1, 1)

        x_limits = dpg.get_axis_limits(f"{self.tag}_x_axis")
        y_limits = dpg.get_axis_limits(f"{self.tag}_y_axis")
        extends = (
            x_limits[1] - x_limits[0],
            y_limits[1] - y_limits[0],
        )

        return (
            extends[0] / self._graph_extends[0],
            extends[1] / self._graph_extends[1],
        )

    def set_graph(self, graph: nx.DiGraph) -> None:
        self.graph = graph
        self._nodes: list[str] = sorted(graph.nodes)
        self._edges = list(graph.edges)

        # Built once here instead of being rebuilt on every render callback
        self._node_index = {n: i for i, n in enumerate(self._nodes)}
        self._edge_index = {e: j for j, e in enumerate(self._edges)}

        # The series and all the draw items parented to it are about to go away
        self._items_built = False
        self._node_items = []
        self._edge_items = []
        self._shown_nodes.clear()
        self._shown_edges.clear()
        self._prev_anchor = None
        self._prev_scale = None
        self._highlighted_node = None

        # Need to create a new series due to the bug mentioned below
        dpg.delete_item(f"{self.tag}_x_axis", children_only=True)
        dpg.split_frame()

        num_nodes = len(self._nodes)
        with dpg.custom_series(
            # Note: there is a bug in current dearpygui where updating the series data
            # does not update how many items of transformed_x/y it will provide
            [0] * num_nodes,
            [0] * num_nodes,
            2,
            callback=self._render,
            tag=f"{self.tag}_series",
            parent=f"{self.tag}_x_axis",
        ):
            # Tooltip
            # NOTE creating a group/child window and adding children later doesn't work
            # NOTE placing widgets inside groups/child windows here will make them 
            # impossible to change
            for i in range(self._max_tooltip_lines):
                dpg.add_text("hello", tag=f"{self.tag}_plot_tooltip_line{i}")


        self.regenerate()
        dpg.fit_axis_data(f"{self.tag}_x_axis")
        dpg.fit_axis_data(f"{self.tag}_y_axis")

    def regenerate(self) -> None:
        if not self.graph:
            return
        
        dpg.delete_item(f"{self.tag}_plot", children_only=True, slot=2)

        # Use a map so that we can control the order of nodes in each layer
        layers = {}
        max_layer_nodes = 0
        for layer, nodes in enumerate(nx.topological_generations(self.graph)):
            max_layer_nodes = max(len(nodes), max_layer_nodes)
            layers[layer] = sorted(nodes)

        # TODO use this for our main layout, too
        pos = nx.multipartite_layout(self.graph, subset_key=layers, scale=100)
        # Be sure to use a consistent order of nodes
        points = np.vstack(list(pos[n] for n in self._nodes))
        self._node_lookup = KDTree(points)

        x_data, y_data = list(zip(*[pos[n] for n in self._nodes]))
        dpg.set_value(f"{self.tag}_series", [x_data, y_data])

        x_min = min(x_data)
        x_max = max(x_data)
        y_min = min(y_data)
        y_max = max(y_data)
        self._graph_extends = (x_max - x_min, y_max - y_min)

        # Positions moved, so the next render must not take the unchanged-transform
        # shortcut even if the view itself did not move
        self._prev_anchor = None
        self._prev_scale = None

    def _build_items(self, sender: str) -> None:
        """Create every draw item once, hidden, in back-to-front order.

        Creating them up front (rather than on first sighting) is what keeps
        edges behind nodes: draw order follows creation order, and a lazily
        created edge would end up painted over the nodes it connects.
        """
        dpg.push_container_stack(sender)

        # Edges first so they render below the nodes
        self._edge_items = [
            dpg.draw_line((0, 0), (0, 0), color=style.white, show=False)
            for _ in self._edges
        ]
        self._node_items = [
            dpg.draw_circle(
                (0, 0),
                radius=self._node_radius,
                color=style.white,
                fill=style.white,
                show=False,
            )
            for _ in self._nodes
        ]

        dpg.pop_container_stack()
        self._items_built = True

    def _render(self, sender: str, app_data: list) -> None:
        if not self.graph or not self._nodes:
            return

        transformed_x = app_data[1]
        transformed_y = app_data[2]
        if not transformed_x:
            return

        zoom = max(self.get_zoom())
        scale = 1 / zoom if zoom > 0 else 1.0

        # The transform is a uniform scale plus translation, so one anchor point
        # and the zoom fully describe it. Comparing those is O(1) and lets us
        # skip the whole pass on frames where nothing actually moved.
        anchor = (transformed_x[0], transformed_y[0])
        transform_changed = anchor != self._prev_anchor or scale != self._prev_scale

        if self._items_built and not transform_changed:
            return

        if not self._items_built:
            self._build_items(sender)

        self._prev_anchor = anchor
        self._prev_scale = scale

        # Cull against the plot rect, in the same pixel space the series reports
        rx, ry = dpg.get_item_rect_min(f"{self.tag}_plot")
        rw, rh = dpg.get_item_rect_size(f"{self.tag}_plot")
        margin = 32.0
        x0 = rx - margin
        y0 = ry - margin
        x1 = rx + rw + margin
        y1 = ry + rh + margin

        shown_nodes = self._shown_nodes
        shown_edges = self._shown_edges

        # Edges reference node positions, so both passes read transformed_x/y directly
        node_idx = self._node_index
        for j, (node0, node1) in enumerate(self._edges):
            ia = node_idx[node0]
            ib = node_idx[node1]
            ax = transformed_x[ia]
            ay = transformed_y[ia]
            bx = transformed_x[ib]
            by = transformed_y[ib]

            if (
                max(ax, bx) < x0
                or min(ax, bx) > x1
                or max(ay, by) < y0
                or min(ay, by) > y1
            ):
                if j in shown_edges:
                    dpg.configure_item(self._edge_items[j], show=False)
                    shown_edges.discard(j)
                continue

            if j in shown_edges:
                dpg.configure_item(self._edge_items[j], p1=(ax, ay), p2=(bx, by))
            else:
                dpg.configure_item(
                    self._edge_items[j], p1=(ax, ay), p2=(bx, by), show=True
                )
                shown_edges.add(j)

        for i in range(len(self._nodes)):
            px = transformed_x[i]
            py = transformed_y[i]

            if px < x0 or px > x1 or py < y0 or py > y1:
                if i in shown_nodes:
                    dpg.configure_item(self._node_items[i], show=False)
                    shown_nodes.discard(i)
                continue

            if i in shown_nodes:
                dpg.configure_item(self._node_items[i], center=(px, py))
            else:
                dpg.configure_item(
                    self._node_items[i], center=(px, py), show=True
                )
                shown_nodes.add(i)

    def _on_mouse_move(self) -> None:
        if not self._node_lookup:
            return

        if not dpg.is_item_hovered(f"{self.tag}_plot"):
            return

        pos = dpg.get_plot_mouse_pos()
        node = self.get_node_at(pos)
        self.set_highlighted_node(node)
        self._update_hover_text(node)

    def _on_mouse_click(self) -> None:
        if not self._node_lookup or not self.on_click_callback:
            return

        if not dpg.is_item_hovered(f"{self.tag}_plot"):
            return

        if self.callback_triggered:
            return

        # The callback can take a while to resolve, make sure we handle the user's impatience :)
        self.callback_triggered = True
        
        pos = dpg.get_plot_mouse_pos()
        node = self.get_node_at(pos)
        if node:
            self.on_click_callback(node)

        self.callback_triggered = False

    def _set_node_color(self, node: str, color: tuple) -> None:
        idx = self._node_index.get(node)
        if idx is None or not self._items_built:
            return

        dpg.configure_item(self._node_items[idx], color=color)

    def set_highlighted_node(self, node: str) -> None:
        if self._highlighted_node and self._highlighted_node != node:
            self._set_node_color(self._highlighted_node, style.white)

            for node1 in nx.all_neighbors(self.graph, self._highlighted_node):
                if node1 != self._highlighted_node:
                    self._set_edge_highlight(self._highlighted_node, node1, False)

        if node and node != self._highlighted_node:
            self._set_node_color(node, style.orange)

            for node1 in nx.all_neighbors(self.graph, node):
                if node1 != node:
                    self._set_edge_highlight(node, node1, True)

        self._highlighted_node = node

    def _set_edge_highlight(self, node_a: str, node_b: str, highlighted: bool) -> None:
        if not self._items_built:
            return

        # The edge may be stored in either direction
        idx = self._edge_index.get((node_a, node_b))
        if idx is None:
            idx = self._edge_index.get((node_b, node_a))

        if idx is None:
            return

        thickness = 2 if highlighted else 1
        color = style.orange if highlighted else style.white
        dpg.configure_item(self._edge_items[idx], thickness=thickness, color=color)

    def _update_hover_text(self, node: str) -> None:
        if node:
            lines = self.get_node_data(node)
            colors = None

            if isinstance(lines, str):
                lines = [lines]
            elif lines and isinstance(lines[0], tuple):
                lines, colors = zip(*lines)

            if not colors:
                colors = [style.white] * len(lines)

            for i in range(self._max_tooltip_lines):
                if i < len(lines):
                    dpg.configure_item(
                        f"{self.tag}_plot_tooltip_line{i}",
                        default_value=lines[i],
                        color=colors[i],
                    )
                    # configure(show=True) doesn't work
                    dpg.show_item(f"{self.tag}_plot_tooltip_line{i}")
                else:
                    dpg.hide_item(f"{self.tag}_plot_tooltip_line{i}")
            
            dpg.configure_item(f"{self.tag}_series", tooltip=True)
        else:
            dpg.configure_item(f"{self.tag}_series", tooltip=False)
