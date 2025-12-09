from typing import Callable
import dearpygui.dearpygui as dpg
import numpy as np
import networkx as nx
from pykdtree.kdtree import KDTree

from hkb_editor.gui import style


class GraphMap:
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
        self.tag = tag

        self._nodes: list[str] = []
        self._node_radius = 10
        self._max_tooltip_lines = 6
        self._graph_extends: tuple[float, float] = None
        self._node_lookup: KDTree = None
        self._highlighted_node = None
        self._handler_tag = f"{self.tag}_handlers"

        self._setup_content()
        self.set_graph(graph)

    def __del__(self):
        if dpg.does_item_exist(self._handler_tag):
            dpg.delete_item(self._handler_tag)

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
        # TODO Performance seems to be okayish up until ~1000 nodes
        print("### nodes", len(self._nodes))

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

    def _render(self, sender: str, app_data: list) -> None:
        if not self.graph:
            return

        transformed_x = app_data[1]
        transformed_y = app_data[2]
        node_indices = {n: i for i, n in enumerate(self._nodes)}
        scale = 1 / max(*self.get_zoom())

        def get_pos(node: str):
            idx = node_indices[node]
            return transformed_x[idx], transformed_y[idx]

        dpg.push_container_stack(sender)

        # Edges first so they render below the nodes
        for node0, node1 in self.graph.edges:
            edge_tag = f"{self.tag}_edge_{node0}_TO_{node1}"
            if dpg.does_item_exist(edge_tag):
                dpg.configure_item(edge_tag, p1=get_pos(node0), p2=get_pos(node1))
            else:
                dpg.draw_line(
                    get_pos(node0),
                    get_pos(node1),
                    color=style.white,
                    tag=edge_tag,
                )

        for node in self._nodes:
            node_tag = f"{self.tag}_node_{node}"
            if dpg.does_item_exist(node_tag):
                # TODO scale
                dpg.configure_item(node_tag, center=get_pos(node), radius=self._node_radius * scale)
            else:
                dpg.draw_circle(
                    get_pos(node),
                    radius=self._node_radius * scale,
                    color=style.white,
                    fill=style.white,
                    tag=node_tag,
                )

        dpg.pop_container_stack()

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

        pos = dpg.get_plot_mouse_pos()
        node = self.get_node_at(pos)
        if node:
            self.on_click_callback(node)

    def set_highlighted_node(self, node: str) -> None:
        if self._highlighted_node and self._highlighted_node != node:
            dpg.configure_item(
                f"{self.tag}_node_{self._highlighted_node}", color=style.white
            )

            for node1 in nx.all_neighbors(self.graph, self._highlighted_node):
                if node1 != self._highlighted_node:
                    self._set_edge_highlight(self._highlighted_node, node1, False)

        if node and node != self._highlighted_node:
            dpg.configure_item(f"{self.tag}_node_{node}", color=style.orange)

            for node1 in nx.all_neighbors(self.graph, node):
                if node1 != node:
                    self._set_edge_highlight(node, node1, True)

        self._highlighted_node = node

    def _set_edge_highlight(self, node_a: str, node_b: str, highlighted: bool) -> None:
        tag = f"{self.tag}_edge_{node_a}_TO_{node_b}"
        if not dpg.does_item_exist(tag):
            tag = f"{self.tag}_edge_{node_b}_TO_{node_a}"

        if not dpg.does_item_exist(tag):
            return

        thickness = 2 if highlighted else 1
        color = style.orange if highlighted else style.white
        dpg.configure_item(tag, thickness=thickness, color=color)

    def _update_hover_text(self, node: str) -> None:
        if node:
            lines = self.get_node_data(node)
            if isinstance(lines, str):
                lines = [lines]
            elif isinstance(lines[0], tuple):
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
