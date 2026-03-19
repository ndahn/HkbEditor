from typing import Any, Callable, Literal
from dearpygui import dearpygui as dpg
import networkx as nx

from hkb_editor.external import get_config

from .graph_layout import GraphLayout, HorizontalGraphLayout, Node
from hkb_editor.gui import style
from hkb_editor.gui.helpers import estimate_drawn_text_size


class GraphWidget:
    def __init__(
        self,
        graph: nx.DiGraph = None,
        layout: GraphLayout = None,
        *,
        on_node_selected: Callable[[Node], None] = None,
        node_menu_func: Callable[[Node], None] = None,
        get_node_frontpage: Callable[
            [Node], str | list[str] | list[tuple[str, tuple[int, int, int, int]]]
        ] = None,
        get_edge_label: Callable[[Node, Node], str] = None,
        draw_edges: bool = True,
        edge_style: Literal["manhattan", "straight"] = "manhattan",
        rainbow_edges: bool = False,
        select_enabled: bool = True,
        hover_enabled: bool = True,
        tag: str = None,
    ):
        if not layout:
            layout = HorizontalGraphLayout()

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

        self.color_generator = style.HighContrastColorGenerator(0.0, 0.18)
        self.graph = None
        self.root: str = None
        self.nodes: dict[str, Node] = {}
        self.hovered_node: Node = None
        self.selected_node: Node = None
        self.zoom_factor: float = 1.0

        self._setup_content()
        self.set_graph(graph)

    def deinit(self):
        # Prevent double deinitialization
        if getattr(self, "_deinitialized", False):
            return

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

            self.nodes[self.root].visible = True
            self.regenerate()

    def get_node_at_pos(self, x: float, y: float) -> Node:
        for node in self.nodes.values():
            # Something like a b-tree might have better performance,
            # but so far this is not a bottleneck
            if node.visible:
                if node.contains(x, y):
                    return node

        return None

    def look_at(self, px: float, py: float) -> None:
        xmin, xmax = dpg.get_axis_limits(f"{self.tag}_plot_xaxis")
        ymin, ymax = dpg.get_axis_limits(f"{self.tag}_plot_yaxis")
        xrange = (xmax - xmin) / 2
        yrange = (ymax - ymin) / 2
        dpg.set_axis_limits(f"{self.tag}_plot_xaxis", px - xrange, px + xrange)
        dpg.set_axis_limits(f"{self.tag}_plot_yaxis", py - yrange, py + yrange)

    def look_at_node(self, node: str) -> None:
        n = self.nodes[node]
        cw, ch = dpg.get_item_rect_size(self.tag)
        # Not sure why it's -n.pos, but it works
        px = -n.pos[0] + cw / 2 - n.width / 2
        py = -n.pos[1] + ch / 2 - n.height / 2
        self.look_at(px, py)

    def zoom_show_all(self) -> None:
        dpg.fit_axis_data(f"{self.tag}_plot_xaxis")
        dpg.fit_axis_data(f"{self.tag}_plot_yaxis")

    # Content setup
    def _setup_content(self):
        with dpg.plot(
            width=-1,
            height=-1,
            no_menus=True,
            no_mouse_pos=True,
            equal_aspects=True,
            tag=self.tag,
        ) as self.tag:
            dpg.add_plot_axis(
                dpg.mvXAxis,
                no_label=True,
                no_menus=True,
                no_highlight=True,
                no_tick_labels=True,
                no_tick_marks=True,
                tag=f"{self.tag}_plot_xaxis",
            )
            dpg.add_plot_axis(
                dpg.mvYAxis,
                no_label=True,
                no_menus=True,
                no_highlight=True,
                no_tick_labels=True,
                no_tick_marks=True,
                tag=f"{self.tag}_plot_yaxis",
            )

        with dpg.handler_registry(tag=f"{self.tag}_handler_registry"):
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Left, callback=self._on_left_click
            )
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Right, callback=self._on_right_click
            )

    # Canvas interactions
    def _on_left_click(self) -> None:
        if not dpg.is_item_hovered(self.tag):
            return

        if self.hovered_node:
            self.select(self.hovered_node)

    def _on_right_click(self) -> None:
        if not dpg.is_item_hovered(self.tag):
            return

        if self.hovered_node:
            if self.hovered_node != self.selected_node:
                self.select(self.hovered_node)

            if self.node_menu_func:
                self.node_menu_func(self.hovered_node)
        else:
            self._open_canvas_menu()

    def _open_canvas_menu(self) -> None:
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_menu_item(
                label="Show All",
                callback=self.zoom_show_all,
            )

    # Canvas content management
    def clear(self, reset_origin: bool = True):
        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True, slot=1)
        self.color_generator.reset()

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        self.selected_node = None
        if reset_origin:
            self.look_at(0.0, 0.0)

    def regenerate(self):
        if not self.graph:
            return

        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True)
        self.color_generator.reset()

        # Insert a reference point to calculate the zoom level from
        for node in self.nodes.values():
            # TODO must also estimate the size beforehand
            node.pos = self.layout.get_pos_for_node(self.graph, node, self.nodes)

        px = [1.0] + [n.x for n in self.nodes.values()]
        py = [1.0] + [n.y for n in self.nodes.values()]

        dpg.add_custom_series(
            px,
            py,
            2,
            callback=self._render_graph,
            tooltip=False,
            parent=self.tag,
            tag=f"{self.tag}_plot_series",
        )

        if self.selected_node:
            selected = self.selected_node
            self.selected_node = None
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
            on_branch = n.id in branch_nodes
            n.visible = on_branch
            n.unfolded = on_branch

    def select(self, node: Node | str):
        if not self.select_enabled:
            return

        if isinstance(node, str):
            node = self.nodes.get(node)

        if not node or node not in self.nodes.values():
            return

        if get_config().single_branch_mode:
            if node != self.selected_node:
                self.reveal(node)
        else:
            if node == self.selected_node:
                self.deselect()
                return
            else:
                self._unfold_node(node)

        self.selected_node = node
        self._unfold_node(node)

        if self.on_node_selected:
            self.on_node_selected(node)

    def deselect(self):
        if self.selected_node is None:
            return

        self._fold_node(self.selected_node)
        self.selected_node = None

        if self.on_node_selected:
            self.on_node_selected(None)

    def _unfold_node(self, node: Node) -> None:
        node.visible = True
        node.unfolded = True

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes.get(child_id)
            if child_node:
                child_node.visible = True

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

    def reveal_all_nodes(self, max_depth: int = -1) -> None:
        if max_depth == 0:
            return

        for n in self.graph.nodes:
            node = self.nodes[n]
            if max_depth < 0 or node.level < max_depth:
                node.visible = True
                node.unfolded = True

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
                node.visible = False
                node.unfolded = False

        node.unfolded = False

    def _render_graph(self, sender: str, app_data: list, user_data: Any) -> None:
        # Save some cpu cycles when no updates are needed
        if not (
            dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
            or dpg.is_item_hovered(self.tag)
        ):
            return

        helper_data = app_data[0]
        transformed_x = app_data[1][1:]
        transformed_y = app_data[2][1:]
        idx_map = {n: i for i, n in enumerate(self.nodes.keys())}
        mouse_x = helper_data["MouseX_PixelSpace"]
        mouse_y = helper_data["MouseY_PixelSpace"]

        self.hovered_node = None
        self.zoom_factor = app_data[1][0]
        print("### zoom:", self.zoom_factor)  # TODO confirm this is not position dependent

        dpg.delete_item(sender, children_only=True, slot=2)
        dpg.push_container_stack(sender)
        dpg.configure_item(sender, tooltip=False)

        # By using a topological sort we ensure that nodes closer to the root are drawn first
        for n in nx.topological_sort(self.graph):
            px = transformed_x[idx_map[n]]
            py = transformed_y[idx_map[n]]

            node = self.nodes[n]
            if node.visible:
                for child_id in self.graph.successors(node.id):
                    child_node = self.nodes[child_id]
                    if child_node.visible and self.draw_edges:
                        cx = transformed_x[idx_map[child_id]]
                        cy = transformed_y[idx_map[child_id]]
                        self._draw_edge(node, px, py, child_node, cx, cy)

            self._draw_node(node, px, py)

            if not self.hovered_node and node.contains(mouse_x, mouse_y):
                self.hovered_node = node

        dpg.pop_container_stack()

    def _draw_node(self, node: Node, plot_x: float, plot_y: float) -> None:
        tag = f"{self.tag}_node_{node.id}"

        if dpg.does_item_exist(tag):
            if not node.visible:
                node.pos = (plot_x, plot_y)
                node.visible = True
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

        with dpg.draw_node(tag=tag):
            if self.select_enabled and node == self.selected_node:
                edge_color = style.blue
                thickness = 2
            elif self.hover_enabled and node == self.hovered_node:
                edge_color = style.white
                thickness = 2
            else:
                edge_color = style.white
                thickness = 1

            # Background
            dpg.draw_rectangle(
                (plot_x, plot_y),
                (w, h),
                fill=style.dark_grey,
                color=edge_color,
                thickness=thickness,
                tag=f"{tag}_box",  # for highlighting
            )

            # Text
            for i, text in enumerate(lines):
                dpg.draw_text(
                    (plot_x + margin, plot_y + margin + text_offset_y * i),
                    text,
                    size=12 * scale,
                    color=colors[i],
                )

        node.pos = (plot_x, plot_y)
        node.size = (w, h)
        node.visible = True

    def _draw_edge(
        self, node_a: Node, ax: float, ay: float, node_b: Node, bx: float, by: float
    ) -> None:
        tag = f"{self.tag}_edge_{node_a.id}_TO_{node_b.id}"
        if dpg.does_item_exist(tag):
            return

        if (self.hover_enabled or self.select_enabled) and (
            node_a in (self.hovered_node, self.selected_node)
            or node_b in (self.hovered_node, self.selected_node)
        ):
            color = style.orange
            thickness = 2
        elif self.rainbow_edges:
            color = self.color_generator(node_a.id)
            color = tuple((c + 255) // 2 for c in color)
            thickness = 1
        else:
            color = style.white
            thickness = 1

        if self.edge_style == "manhattan":
            p0x = ax + node_a.width
            p0y = ay + node_a.height / 2
            p1x = bx
            p1y = by + node_b.height / 2

            # The right side of node_a depends on its width, whereas the left side of all nodes
            # on the same level should be aligned, so this will give a more consistent look.
            mid_x = p1x - self.layout.gap_x / 2
            # mid_x = ax + (bx - ax) / 2

            dpg.draw_polygon(
                [
                    (p0x, p0y),
                    (mid_x, p0y),
                    (mid_x, p1y),
                    (p1x, p1y),
                ],
                color=color,
                thickness=thickness,
                tag=tag,
                parent=f"{self.tag}_edge_layer",
            )
        elif self.edge_style == "straight":
            p0x = ax + node_a.width / 2
            p0y = ay + node_a.height / 2
            p1x = bx + node_b.width / 2
            p1y = by + node_b.height / 2

            dpg.draw_line(
                (p0x, p0y),
                (p1x, p1y),
                color=color,
                tag=tag,
                parent=f"{self.tag}_edge_layer",
            )

        if self.get_edge_label:
            label = self.get_edge_label(node_a, node_b)
            if label:
                # TODO find an efficient way to rotate the text
                margin = self.layout.text_margin
                scale = self.zoom_factor

                tw, th = estimate_drawn_text_size(
                    len(label), font_size=11, scale=scale, margin=margin
                )
                tx = (p0x + p1x) / 2 - tw / 2
                ty = (p0y + p1y) / 2 - th * 2 / 5

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
