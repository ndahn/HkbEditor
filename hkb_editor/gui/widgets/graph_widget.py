from typing import Callable, Literal
from dearpygui import dearpygui as dpg
import networkx as nx
import math

from hkb_editor.external import get_config

from ..graph_layout import GraphLayout, Node
from .. import style
from ..helpers import estimate_drawn_text_size


class GraphWidget:
    def __init__(
        self,
        graph: nx.DiGraph = None,
        layout: GraphLayout = None,
        *,
        on_node_selected: Callable[[Node], None] = None,
        node_menu_func: Callable[[Node], None] = None,
        get_node_frontpage: Callable[
            [str], str | list[str] | list[tuple[str, tuple[int, int, int, int]]]
        ] = None,
        get_edge_label: Callable[[Node, Node], str] = None,
        draw_edges: bool = True,
        edge_style: Literal["manhattan", "straight"] = "manhattan",
        rainbow_edges: bool = False,
        select_enabled: bool = True,
        hover_enabled: bool = True,
        width: int = 800,
        height: int = 800,
        tag: str = None,
    ):
        if not layout:
            layout = GraphLayout()

        if not get_node_frontpage:
            get_node_frontpage = lambda n: n.id

        if tag in (None, 0, ""):
            tag = f"graph_widget_{dpg.generate_uuid()}"

        self.layout = layout
        self.on_node_selected = on_node_selected
        self.node_menu_func = node_menu_func
        self.get_node_frontpage = get_node_frontpage
        self.get_edge_label = get_edge_label
        self.draw_edges = draw_edges
        self.edge_style = edge_style
        self.rainbow_edges = rainbow_edges
        self.select_enabled = select_enabled
        self.hover_enabled = hover_enabled
        self.tag = tag

        self.color_generator = style.HighContrastColorGenerator()
        self.graph = None
        self.root: str = None
        self.nodes: dict[str, Node] = {}
        self.hovered_node: Node = None
        self.selected_node: Node = None
        self.transform: tuple[float, float] = (0.0, 0.0)
        self.dragging = False
        self.last_drag: tuple[float, float] = (0.0, 0.0)
        self.zoom_level = 0
        self.zoom_min = -3
        self.zoom_max = 3

        self._setup_content(width, height)
        self.set_graph(graph)

    def deinit(self):
        # Prevent double deinitialization
        if getattr(self, '_deinitialized', False):
            return
        
        self._deinitialized = True

        # Disable mouse callbacks in the brief window until the handlers are removed
        self.hover_enabled = False

        # Disable all handlers in case deletion fails (see below)
        registry_tag = f"{self.tag}_handler_registry"
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
        
    @property
    def zoom_factor(self) -> float:
        return self.layout.zoom_factor**self.zoom_level

    def set_graph(self, graph: nx.DiGraph) -> None:
        self.clear()
        self.graph = graph

        if graph:
            self.root = next(n for n, in_deg in graph.in_degree() if in_deg == 0)

            for n, data in graph.nodes.items():
                if n not in self.nodes:
                    self.nodes[n] = Node(n, user_data=data)

            paths = nx.shortest_path(self.graph, self.root)

            for n in self.nodes.values():
                if n.id in paths:
                    n.level = len(paths[n.id]) - 1

            self._draw_node(self.nodes[self.root])

    def get_node_at_pos(self, x: float, y: float) -> Node:
        for node in self.nodes.values():
            # Something like a b-tree might have better performance,
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

        # Temporarily set zoom to 0 to get the base layout without zoom scaling.
        # Expensive, but reliable
        self.zoom_level = 0
        self.regenerate()
        
        # Get content bounding box at base zoom level
        bbox = self.get_canvas_content_bbox()
        content_w = bbox[2]
        content_h = bbox[3]
        content_center_x = bbox[0] + content_w / 2
        content_center_y = bbox[1] + content_h / 2
        
        canvas_w, canvas_h = dpg.get_item_rect_size(self.tag)
        canvas_center_x = canvas_w / 2
        canvas_center_y = canvas_h / 2
        
        # Calculate zoom level to fit content
        zoom_w = math.log(canvas_w / content_w, self.layout.zoom_factor)
        zoom_h = math.log(canvas_h / content_h, self.layout.zoom_factor)
        zoom_level = min(zoom_w, zoom_h)
        
        if limits:
            zoom_level = min(max(zoom_level, self.zoom_min), self.zoom_max)
        
        # Calculate final zoom factor and centered origin
        final_zoom = self.layout.zoom_factor ** zoom_level
        
        # Calculate where to place origin so scaled content center aligns with canvas center
        new_origin_x = canvas_center_x - content_center_x * final_zoom
        new_origin_y = canvas_center_y - content_center_y * final_zoom
        
        # Apply zoom and centering together
        self.zoom_level = zoom_level
        self.set_origin(new_origin_x, new_origin_y)
        self.regenerate()

    # Content setup
    def _setup_content(self, width: int, height: int):
        with dpg.drawlist(width, height, tag=self.tag) as self.tag:
            with dpg.draw_node(tag=f"{self.tag}_root"):
                dpg.add_draw_node(tag=f"{self.tag}_edge_layer")
                dpg.add_draw_node(tag=f"{self.tag}_node_layer")

        with dpg.handler_registry(tag=f"{self.tag}_handler_registry"):
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

        with dpg.item_handler_registry():
            dpg.add_item_resize_handler(callback=self._on_resize)

        parent = dpg.get_item_parent(self.tag)
        dpg.bind_item_handler_registry(parent, dpg.last_container())

    def _on_resize(self, *args):
        pass

    # Canvas interactions
    def _get_graph_mouse_pos(self) -> tuple[float, float]:
        # x+: right, y+: down
        if not dpg.is_item_hovered(self.tag):
            return (0.0, 0.0)

        mx, my = dpg.get_drawing_mouse_pos()
        ox, oy = self.transform
        return ((mx - ox), (my - oy))

    def _on_left_click(self) -> None:
        if not dpg.is_item_hovered(self.tag):
            return

        mx, my = self._get_graph_mouse_pos()
        node = self.get_node_at_pos(mx, my)

        if not node:
            # Folding when clicking the canvas feels bad
            #self.deselect()
            pass
        else:
            self.select(node)

    def _on_right_click(self) -> None:
        if not dpg.is_item_hovered(self.tag):
            return

        mx, my = self._get_graph_mouse_pos()
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
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            for item in actions:
                dpg.add_selectable(label=item, callback=on_item_select, user_data=item)

    def _on_drag_start(self) -> None:
        if dpg.is_item_hovered(self.tag):
            self.dragging = True

    def _on_mouse_drag(self, sender, mouse_delta: list[float]) -> None:
        if not self.dragging:
            return

        _, delta_x, delta_y = mouse_delta
        self.last_drag = (delta_x, delta_y)
        self.look_at(self.transform[0] + delta_x, self.transform[1] + delta_y)

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
        if not dpg.is_item_hovered(self.tag):
            return

        if get_config().invert_zoom:
            wheel_delta = -wheel_delta

        # +/-1 only
        wheel_delta /= abs(wheel_delta)

        # Scrolling too fast can cause problems
        with dpg.mutex():
            # Don't set the zoom point, it will just mess things up
            self.set_zoom(self.zoom_level + wheel_delta)

    def _on_mouse_move(self) -> None:
        if not self.hover_enabled:
            return

        if dpg.is_item_hovered(self.tag):
            mx, my = self._get_graph_mouse_pos()
            node = self.get_node_at_pos(mx, my)
        else:
            node = None

        if self.hovered_node:
            self._set_node_hovered(self.hovered_node, False)
            for n in nx.all_neighbors(self.graph, self.hovered_node.id):
                neighbor = self.nodes[n]
                if neighbor.visible:
                    self._set_node_hovered(n, False)
                    self._set_edge_highlight(self.hovered_node, neighbor, False)

        if node:
            self._set_node_hovered(node, True)
            for n in nx.all_neighbors(self.graph, node.id):
                neighbor = self.nodes[n]
                if neighbor.visible:
                    self._set_node_hovered(n, True)
                    self._set_edge_highlight(node, neighbor, True)

        self.hovered_node = node

    # Canvas content management
    def clear(self, reset_origin: bool = True):
        dpg.delete_item(f"{self.tag}_edge_layer", children_only=True)
        dpg.delete_item(f"{self.tag}_node_layer", children_only=True)
        self.color_generator.reset()

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        self.selected_node = None
        if reset_origin:
            self.set_origin(0.0, 0.0)

    def regenerate(self):
        if not self.graph:
            return
        
        dpg.delete_item(f"{self.tag}_edge_layer", children_only=True)
        dpg.delete_item(f"{self.tag}_node_layer", children_only=True)
        self.color_generator.reset()

        want_visible = []
        selected = self.selected_node
        self.selected_node = None

        # By using a topological sort we ensure that nodes closer to the root are drawn first
        for n in nx.topological_sort(self.graph):
            node = self.nodes[n]
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
        self.clear(False)

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
            node = self.nodes.get(node)

        if not node or node not in self.nodes.values():
            return

        if get_config().single_branch_mode:
            if node != self.selected_node:
                if self.selected_node:
                    self._set_node_highlight(self.selected_node, False)
                self.reveal(node)
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

    def _set_edge_highlight(
        self, node_a: Node | str, node_b: Node | str, highlighted: bool
    ) -> None:
        if isinstance(node_a, Node):
            node_a = node_a.id

        if isinstance(node_b, Node):
            node_b = node_b.id

        tag = f"{self.tag}_edge_{node_a}_TO_{node_b}"
        if not dpg.does_item_exist(tag):
            tag = f"{self.tag}_edge_{node_b}_TO_{node_a}"

        if not dpg.does_item_exist(tag):
            # Seems to happen sometimes on quick mouse movements or jump-to-object
            return

        thickness = 2 if highlighted else 1
        dpg.configure_item(tag, thickness=thickness)

        # highlight edge label if it exists, redraw it to place it on top
        if self.get_edge_label:
            label = f"{tag}_label"
            if dpg.does_item_exist(label):
                if highlighted:
                    dpg.move_item(label, parent=f"{self.tag}_node_layer")
                    if not self.rainbow_edges:
                        dpg.configure_item(label, color=style.green)
                    dpg.configure_item(f"{label}_bg", show=True)
                else:
                    dpg.configure_item(f"{label}_bg", show=False)

    def _set_node_hovered(self, node: Node | str, hovered: bool) -> None:
        if isinstance(node, Node):
            node = node.id

        thickness = 2 if hovered else 1
        dpg.configure_item(f"{self.tag}_node_{node}_box", thickness=thickness)

    def _unfold_node(self, node: Node) -> None:
        self._draw_node(node)

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes.get(child_id)
            if child_node:
                self._draw_node(child_node)
                if self.draw_edges:
                    self._draw_edge(node, child_node)

        node.unfolded = True

    def reveal(self, node: Node | str) -> None:
        if isinstance(node, str):
            node = self.nodes[node]

        self.clear(False)

        path = nx.shortest_path(self.graph, self.root, node.id)
        for n in path:
            self._unfold_node(self.nodes[n])

    def reveal_descendant_nodes(self, node: Node | str = None) -> None:
        if not node:
            node = self.root

        if isinstance(node, str):
            node = self.nodes[node]

        for succ_id in nx.descendants(self.graph, node.id):
            succ = self.nodes[succ_id]
            succ.visible = True
            succ.unfolded = True

        self.regenerate()

    def reveal_all_nodes(self) -> None:
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

        scale = self.zoom_factor
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

        with dpg.draw_node(tag=tag, parent=f"{self.tag}_node_layer"):
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

        if self.rainbow_edges:
            color = self.color_generator()
        else:
            color = style.white

        if self.edge_style == "manhattan":
            ax = node_a.x + node_a.width
            ay = node_a.y + node_a.height / 2
            bx = node_b.x
            by = node_b.y + node_b.height / 2

            # The right side of node_a depends on its width, whereas the left side of all nodes
            # on the same level should be aligned, so this will give a more consistent look.
            mid_x = bx - self.layout.gap_x / 2
            #mid_x = ax + (bx - ax) / 2

            dpg.draw_polygon(
                [
                    (ax, ay),
                    (mid_x, ay),
                    (mid_x, by),
                    (bx, by),
                ],
                color=color,
                tag=tag,
                parent=f"{self.tag}_edge_layer",
            )
        elif self.edge_style == "straight":
            ax = node_a.x + node_a.width / 2
            ay = node_a.y + node_a.height / 2
            bx = node_b.x + node_b.width / 2
            by = node_b.y + node_b.height / 2

            dpg.draw_line(
                (ax, ay),
                (bx, by),
                color=color,
                tag=tag,
                parent=f"{self.tag}_edge_layer",
            )

        if self.get_edge_label:
            label = self.get_edge_label(node_a, node_b)
            if label:
                # TODO render text to buffer and rotate to match edge
                margin = self.layout.text_margin
                scale = self.zoom_factor

                tw, th = estimate_drawn_text_size(
                    len(label), font_size=11, scale=scale, margin=margin
                )
                tx = (ax + bx) / 2 - tw / 2
                ty = (ay + by) / 2 - th * 2 / 5

                # Drawn on the node layer so we can bring it to the front
                with dpg.draw_node(
                    tag=f"{tag}_label",
                    parent=f"{self.tag}_node_layer",
                ):
                    dpg.draw_rectangle(
                        (0.0, 0.0),
                        (tw, th),
                        fill=style.dark_grey,
                        color=None,
                        show=False,
                        tag=f"{tag}_label_bg",  # for highlighting
                    )
                    dpg.draw_text(
                        (margin, margin),
                        label,
                        size=11 * scale,
                        color=color,
                    )

                dpg.apply_transform(
                    f"{tag}_label", dpg.create_translation_matrix((tx, ty))
                )

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
