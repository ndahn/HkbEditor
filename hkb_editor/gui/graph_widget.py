from typing import Any, Callable, Literal
from dearpygui import dearpygui as dpg
import networkx as nx
import math
from dataclasses import dataclass

from .graph_layout import GraphLayout, Node
from . import style
from .helpers import estimate_drawn_text_size


class GraphWidget:
    def __init__(
        self,
        graph: nx.DiGraph = None,
        layout: GraphLayout = None,
        *,
        on_node_selected: Callable[[Node], None] = None,
        node_menu_func: Callable[[Node], None] = None,
        get_node_frontpage: Callable[[str], str | list[str] | list[tuple[str, tuple[int, int, int, int]]]] = None,
        get_edge_label: Callable[[Node, Node], str] = None,
        draw_edges: bool = True,
        edge_style: Literal["manhattan", "straight"] = "manhattan",
        select_enabled: bool = True,
        single_branch_mode: bool = True,
        width: int = 800,
        height: int = 800,
        tag: str = None,
    ):
        if not layout:
            layout = GraphLayout()

        if not get_node_frontpage:
            get_node_frontpage = lambda s: s

        if tag in (None, 0, ""):
            tag = dpg.generate_uuid()

        self.layout = layout
        self.on_node_selected = on_node_selected
        self.node_menu_func = node_menu_func
        self.get_node_frontpage = get_node_frontpage
        self.get_edge_label = get_edge_label
        self.draw_edges = draw_edges
        self.edge_style = edge_style
        self.select_enabled = select_enabled
        self.single_branch_mode = single_branch_mode
        self.tag = tag

        self.graph = None
        self.root: str = None
        self.nodes: dict[str, Node] = {}
        self.hovered_node: Node = None
        self.selected_node: Node = None
        self.canvas: str = None
        self.transform: tuple[float, float] = (0.0, 0.0)
        self.dragging = False
        self.last_drag: tuple[float, float] = (0.0, 0.0)
        self.zoom_level = 0
        self.zoom_min = -3
        self.zoom_max = 3

        self._setup_content(width, height)
        self.set_graph(graph)

    @property
    def zoom_factor(self) -> float:
        return self.layout.zoom_factor**self.zoom_level

    def set_graph(self, graph: nx.DiGraph) -> None:
        self.clear()
        self.graph = graph

        if graph:
            self.root = next(n for n, in_deg in graph.in_degree() if in_deg == 0)
            
            for n in graph.nodes:
                if n not in self.nodes:
                    self.nodes[n] = Node(n)

            paths = nx.shortest_path(self.graph, self.root)

            for n in self.nodes.values():
                if n.id in paths:
                    n.layout_data = {"level": len(paths[n.id]) - 1}

            self._draw_node(self.nodes[self.root])

    def get_node_at_pos(self, x: float, y: float) -> Node:
        for node in self.nodes.values():
            # TODO Something like a b-tree might have better performance,
            # but so far this is not a bottleneck
            if node.visible:
                if node.contains(x, y):
                    return node

        return None

    def set_origin(self, new_x: float, new_y: float) -> None:
        self.transform = (new_x, new_y)
        self.look_at(*self.transform)

    def look_at(self, px: float, py: float) -> None:
        dpg.apply_transform(
            f"{self.tag}_root",
            dpg.create_translation_matrix((px, py)),
        )

    def set_zoom(
        self,
        zoom_level: int,
        zoom_point: tuple[float, float] = None,
        *,
        limits: bool = True,
    ) -> None:
        if zoom_level == self.zoom_level:
            return

        if limits:
            zoom_level = min(max(zoom_level, self.zoom_min), self.zoom_max)

        if zoom_point is not None:
            self.set_origin(*zoom_point)

        self.zoom_level = zoom_level
        self.regenerate()

    def get_canvas_content_bbox(
        self, margin: float = 50.0
    ) -> tuple[float, float, float, float]:
        x_min = 100000.0
        x_max = 0.0
        y_min = 100000.0
        y_max = 0.0

        for node in self.nodes.values():
            if node.visible:
                x_min = min(x_min, node.x)
                x_max = max(x_max, node.x + node.width)
                y_min = min(y_min, node.y)
                y_max = max(y_max, node.y + node.height)

        return (
            x_min - margin,
            y_min - margin,
            x_max - x_min + margin * 2,
            y_max - y_min + margin * 2,
        )

    def zoom_show_all(self, *, limits: bool = True) -> None:
        if not any(n.visible for n in self.nodes.values()):
            self.set_zoom(0, (0.0, 0.0))
            return

        bbox = self.get_canvas_content_bbox()
        center_x = bbox[0] + bbox[2] / 2
        center_y = bbox[1] + bbox[3] / 2
        canvas_w, canvas_h = dpg.get_item_rect_size(self.canvas)
        zw = math.log(canvas_w / bbox[2], self.layout.zoom_factor)
        zh = math.log(canvas_h / bbox[3], self.layout.zoom_factor)
        zoom_level = min(zw, zh)

        self.set_zoom(zoom_level, (center_x, center_y), limits=limits)

    # Content setup
    def _setup_content(self, width: int, height: int):
        with dpg.drawlist(width, height, tag=self.tag) as self.canvas:
            dpg.add_draw_node(tag=f"{self.tag}_root")

        with dpg.handler_registry():
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Left, callback=self._on_left_click
            )
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Right, callback=self._on_right_click
            )

            dpg.add_mouse_down_handler(
                dpg.mvMouseButton_Middle, callback=self._on_drag_start
            )
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Middle, callback=self._on_drag_release
            )
            dpg.add_mouse_drag_handler(
                dpg.mvMouseButton_Middle, callback=self._on_mouse_drag
            )

            dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)

            dpg.add_mouse_move_handler(callback=self._on_mouse_move)

    # Canvas interactions
    def _get_canvas_mouse_pos(self) -> tuple[float, float]:
        if not dpg.is_item_hovered(self.canvas):
            return (0.0, 0.0)

        mx, my = dpg.get_drawing_mouse_pos()
        ox, oy = self.transform
        return ((mx - ox), (my - oy))

    def _on_left_click(self) -> None:
        if not dpg.is_item_hovered(self.canvas):
            return

        mx, my = self._get_canvas_mouse_pos()
        node = self.get_node_at_pos(mx, my)

        if not node:
            self.deselect()
        else:
            self.select(node)

    def _on_right_click(self) -> None:
        if not dpg.is_item_hovered(self.canvas):
            return

        mx, my = self._get_canvas_mouse_pos()
        node = self.get_node_at_pos(mx, my)

        if node:
            if node != self.selected_node:
                self.select(node)

            if self.node_menu_func:
                self.node_menu_func(node)
        else:
            self._open_canvas_menu()

    def _open_canvas_menu(self) -> None:
        actions = [
            "Reset View",
            "Show All",
            "Zoom In",
            "Zoom Out",
        ]

        def on_item_select(sender, app_data, selected_item: str):
            dpg.set_value(sender, False)
            
            if selected_item == "Reset View":
                self.set_zoom(0, (0.0, 0.0))

            elif selected_item == "Show All":
                self.zoom_show_all(limits=False)

            elif selected_item == "Zoom In":
                self.set_zoom(self.zoom_level + 1)

            elif selected_item == "Zoom Out":
                self.set_zoom(self.zoom_level - 1)

        with dpg.window(
            popup=True, min_size=(100, 20), on_close=lambda: dpg.delete_item(wnd)
        ) as wnd:
            for item in actions:
                dpg.add_selectable(label=item, callback=on_item_select, user_data=item)

    def _on_drag_start(self) -> None:
        if dpg.is_item_hovered(self.canvas):
            self.dragging = True

    def _on_mouse_drag(self, sender, mouse_delta: list[float]) -> None:
        if not self.dragging:
            return

        _, delta_x, delta_y = mouse_delta
        self.last_drag = (delta_x, delta_y)
        self.look_at(
            self.transform[0] + delta_x, self.transform[1] + delta_y
        )

    def _on_drag_release(self, sender, mouse_button) -> None:
        if not self.dragging:
            return

        self.set_origin(
            self.transform[0] + self.last_drag[0],
            self.transform[1] + self.last_drag[1],
        )

        self.last_drag = (0.0, 0.0)
        self.dragging = False

    def _on_mouse_wheel(self, sender, wheel_delta: int):
        if not dpg.is_item_hovered(self.canvas):
            return

        if dpg.get_value(f"{self.tag}_settings_invert_zoom"):
            wheel_delta = -wheel_delta

        # +/-1 only
        wheel_delta /= abs(wheel_delta)

        # Scrolling too fast can cause problems
        with dpg.mutex():
            zoom_point = self._get_canvas_mouse_pos()
            self.set_zoom(self.zoom_level + wheel_delta, zoom_point)

    def _on_mouse_move(self) -> None:
        if dpg.is_item_hovered(self.canvas):
            mx, my = self._get_canvas_mouse_pos()
            node = self.get_node_at_pos(mx, my)
        else:
            node = None
        
        if self.hovered_node:
            self._set_node_hovered(self.hovered_node, False)
            for n in nx.all_neighbors(self.graph, self.hovered_node.id):
                neighbor = self.nodes[n]
                if neighbor.visible:
                    self._set_node_hovered(n, False)
                    # TODO edges

        if node:
            self._set_node_hovered(node, True)
            for n in nx.all_neighbors(self.graph, node.id):
                neighbor = self.nodes[n]
                if neighbor.visible:
                    self._set_node_hovered(n, True)
                    # TODO edges

        self.hovered_node = node

    # Canvas content management
    def clear(self):
        dpg.delete_item(f"{self.tag}_root", children_only=True)

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        self.selected_node = None
        self.set_origin(0.0, 0.0)

    def regenerate(self):
        dpg.delete_item(f"{self.tag}_root", children_only=True)

        want_visible = []
        selected = self.selected_node
        self.selected_node = None

        for node in self.nodes.values():
            if node.visible:
                want_visible.append(node)
                node.visible = False

        for node in want_visible:
            self._draw_node(node)

        for node in want_visible:
            for child_id in self.graph.successors(node.id):
                child_node = self.nodes[child_id]
                if child_node.visible and self.draw_edges:
                    self._draw_edge(node, child_node)

        if selected:
            self.select(selected)

    def show_node_path(self, path: list[Node | str]) -> None:
        self.clear()

        if not path:
            return
        
        for node in path:
            if isinstance(node, str):
                node = self.nodes[node]
            self._unfold_node(node)

        self.select(path[-1])

    def isolate_branch(self, node: Node | str) -> None:
        if isinstance(node, str):
            node = self.nodes[node]
        
        # Remove all nodes that don't need to be visible anymore. This is more complicated as it
        # seems, as we need to keep the branch unfolded by the user as it is
        branch = [node.id]

        while True:
            if branch[-1] == self.root:
                break

            # Find the visible parents and their children
            preds = self.graph.predecessors(branch[-1])
            for parent_id in preds:
                if self.nodes[parent_id].visible:
                    branch.extend(self.graph.successors(parent_id))
                    branch.append(parent_id)

        branch_nodes = set(branch)
        for n in self.nodes.values():
            if n.visible and n.id not in branch_nodes:
                self._remove_from_canvas(n)

    def select(self, node: Node | str):
        if not self.select_enabled:
            return

        if isinstance(node, str):
            node = self.nodes[node]

        if self.single_branch_mode:
            if node != self.selected_node:
                if self.selected_node:
                    self._set_node_highlight(self.selected_node, False)
                self.isolate_branch(node)
        else:
            if node == self.selected_node:
                self.deselect()
                return
            else:
                if self.selected_node:
                    self._set_node_highlight(self.selected_node, False)
                self._unfold_node(node)

        self.selected_node = node
        self._unfold_node(node)
        self._set_node_highlight(node, True)
        
        if self.on_node_selected:
            self.on_node_selected(node)

    def deselect(self):
        if self.selected_node is None:
            return

        self._set_node_highlight(self.selected_node, False)
        self._fold_node(self.selected_node)
        self.selected_node = None

        if self.on_node_selected:
            self.on_node_selected(None)

    def _set_node_highlight(self, node: Node | str, highlighted: bool) -> None:
        if isinstance(node, Node):
            node = node.id

        color = style.blue if highlighted else style.white
        dpg.configure_item(f"{self.tag}_node_{node}_box", color=color)

    def _set_edge_highlight(self, node_a: Node | str, node_b: Node | str, highlighted: bool) -> None:
        if isinstance(node_a, Node):
            node_a = node_a.id

        if isinstance(node_b, Node):
            node_b = node_b.id

        thickness = 2 if highlighted else 1
        dpg.configure_item(f"{self.tag}_edge_{node_a}_TO_{node_b}", thickness=thickness)

        # TODO highlight edge label if it exists, redraw it to place it on top

    def _set_node_hovered(self, node: Node | str, hovered: bool) -> None:
        if isinstance(node, Node):
            node = node.id

        thickness = 2 if hovered else 1
        dpg.configure_item(f"{self.tag}_node_{node}_box", thickness=thickness)

    def _unfold_node(self, node: Node) -> None:
        self._draw_node(node)

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes[child_id]
            self._draw_node(child_node)
            if self.draw_edges:
                self._draw_edge(node, child_node)

        node.unfolded = True

    def reveal_connected(self, node: Node | str = None) -> None:
        if not node:
            node = self.root
        
        if isinstance(node, str):
            node = self.nodes[node]

        for succ_id in nx.descendants(self.graph, node.id):
            succ = self.nodes[succ_id]
            succ.visible = True
            succ.unfolded = True

        self.regenerate()

    def reveal_all(self) -> None:
        for n in self.graph.nodes:
            node = self.nodes[n]
            node.visible = True
            node.unfolded = True

        self.regenerate()

    def _fold_node(self, node: Node) -> None:
        # Set visible status first, otherwise we make mistakes if nodes have multiple parents
        for child_id in self.graph.successors(self.selected_node.id):
            child_node = self.nodes[child_id]
            child_node.visible = False

        # Remove all children without still visible parents
        for child_id in nx.descendants(self.graph, self.selected_node.id):
            for parent_id in self.graph.predecessors(child_id):
                if parent_id != node.id and self.nodes[parent_id].visible:
                    break
            else:
                # Did not find any parents that should still be visible, delete the node
                self._remove_from_canvas(self.nodes[child_id])

        node.unfolded = False

    def _draw_node(self, node: Node) -> None:
        tag = f"{self.tag}_node_{node.id}"

        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            return

        scale = self.layout.zoom_factor**self.zoom_level
        margin = self.layout.text_margin
        text_h = 12
        text_offset_y = text_h * scale
        lines = self.get_node_frontpage(node)
        colors = None

        if isinstance(lines, str):
            lines = [lines]
        elif isinstance(lines[0], tuple):
            lines, colors = zip(*lines)
        
        if not colors:
            colors = [style.white] * len(lines)

        max_len = max(len(s) for s in lines)
        lines = [s.center(max_len) for s in lines]
        w, h = estimate_drawn_text_size(
            max_len, num_lines=len(lines), font_size=text_h, scale=scale, margin=margin
        )

        with dpg.draw_node(tag=tag, parent=f"{self.tag}_root"):
            # Background
            dpg.draw_rectangle(
                (0.0, 0.0),
                (w, h),
                fill=style.dark_grey,
                color=style.white,
                thickness=1,
                tag=f"{tag}_box",  # for highlighting
            )

            # Text
            for i, text in enumerate(lines):
                dpg.draw_text(
                    (margin, margin + text_offset_y * i),
                    text,
                    size=12 * scale,
                    color=colors[i],
                )

        node.size = (w, h)
        node.pos = self.layout.get_pos_for_node(self.graph, node, self.nodes)
        node.visible = True
        dpg.apply_transform(tag, dpg.create_translation_matrix([node.x, node.y]))

    def _draw_edge(self, node_a: Node, node_b: Node) -> None:
        tag = f"{self.tag}_edge_{node_a.id}_TO_{node_b.id}"
        if dpg.does_item_exist(tag):
            return

        ax = node_a.x + node_a.width
        ay = node_a.y + node_a.height / 2
        bx = node_b.x
        by = node_b.y + node_b.height / 2

        if self.edge_style == "manhattan":
            # The right side of node_a depends on its width, whereas the left side of all nodes
            # on the same level should be aligned, so this will give a more consistent look.
            mid_x = bx - self.layout.gap_x / 2

            dpg.draw_polygon(
                [
                    (ax, ay),
                    (mid_x, ay),
                    (mid_x, by),
                    (bx, by),
                ],
                tag=tag,
                parent=f"{self.tag}_root",
            )
        elif self.edge_style == "straight":
            dpg.draw_line(
                (ax, ay),
                (bx, by),
                tag=tag,
                parent=f"{self.tag}_root",
            )

        if self.get_edge_label:
            label = self.get_edge_label(node_a, node_b)
            if label:
                # TODO render text to buffer and rotate to match edge
                tw, th = estimate_drawn_text_size(len(label), font_size=11)
                tx = (ax + bx) * 2 / 5 - tw / 2
                ty = (ay + by) * 2 / 5 - th / 2
                dpg.draw_text((tx, ty), label, size=11, parent=f"{self.tag}_root")

    def _remove_from_canvas(self, node: Node) -> None:
        if not node:
            return

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes.get(child_id, None)
            self._remove_from_canvas(child_node)

        dpg.delete_item(f"{self.tag}_node_{node.id}")
        node.visible = False
        node.unfolded = False

        # Delete relations
        for parent_id in self.graph.predecessors(node.id):
            if dpg.does_item_exist(f"{self.tag}_edge_{parent_id}_TO_{node.id}"):
                dpg.delete_item(f"{self.tag}_edge_{parent_id}_TO_{node.id}")
