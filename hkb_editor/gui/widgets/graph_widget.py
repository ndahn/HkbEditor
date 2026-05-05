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

        self.color_generator = style.HighContrastColorGenerator(0.0, 0.02)  # before: 0.18
        self.graph = None
        self.root: str = None
        self.nodes: dict[str, Node] = {}
        self.hovered_node: Node = None
        self.selected_node: Node = None
        self._x_scale = 1.0
        self._x_offset = 0.0
        self._y_scale = 1.0
        self._y_offset = 0.0
        # Plot-space positions from the last layout pass; used to transform to pixels.
        self._plot_positions: dict[str, tuple[float, float]] = {}

        # Set when visibility changes; cleared after layout is recomputed.
        self._layout_dirty: bool = False

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

        # TODO still needed? issue is fixed, test with graph map
        with dpg.mutex():
            # Calling delayed_cleanup directly sometimes leads to a silent crash.
            # Unfortunately, this is not guaranteed to run due to a bug in dearpygui, see
            # https://github.com/hoffstadt/DearPyGui/issues/2269
            dpg.set_frame_callback(dpg.get_frame_count() + 5, delayed_cleanup)

    # Content setup
    def _setup_content(self):
        cfg = get_config()
        
        @cfg.events.pan_button.connect
        def on_panbutton_changed(new: str, old: str) -> None:
            dpg.configure_item(self.tag, pan_button=cfg.get_pan_button_id())

        with dpg.plot(
            width=-1,
            height=-1,
            no_menus=True,
            no_mouse_pos=True,
            no_box_select=True,
            no_frame=True,
            no_title=True,
            pan_button=cfg.get_pan_button_id(),
            equal_aspects=True,
            tag=self.tag,
        ):
            dpg.add_plot_axis(
                dpg.mvXAxis,
                no_label=True,
                no_menus=True,
                no_highlight=True,
                no_tick_labels=True,
                no_tick_marks=True,
                no_initial_fit=True,
                tag=f"{self.tag}_plot_xaxis",
            )
            dpg.add_plot_axis(
                dpg.mvYAxis,
                no_label=True,
                no_menus=True,
                no_highlight=True,
                no_tick_labels=True,
                no_tick_marks=True,
                no_initial_fit=True,
                tag=f"{self.tag}_plot_yaxis",
            )

        dpg.bind_item_theme(self.tag, style.plot_no_borders_theme)

        with dpg.handler_registry(tag=f"{self.tag}_handler_registry"):
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Left, callback=self._on_left_click
            )
            dpg.add_mouse_release_handler(
                dpg.mvMouseButton_Right, callback=self._on_right_click
            )

    def set_graph(self, graph: nx.DiGraph) -> None:
        self.clear()
        self.graph = graph

        if graph:
            self.root = next(n for n, in_deg in graph.in_degree() if in_deg == 0)

            for n, data in graph.nodes.items():
                if n not in self.nodes:
                    self.nodes[n] = Node(n, user_data=data)

            # How early can the node be reached?
            paths = nx.shortest_path(self.graph, self.root)
            for n in self.nodes.values():
                if n.id in paths:
                    n.level = len(paths[n.id]) - 1

            self.nodes[self.root].visible = True
            self.regenerate()

    @property
    def zoom_factor(self) -> float:
        return self._x_scale

    def _to_pixel(self, x: float, y: float) -> tuple[float, float]:
        return (
            x * self._x_scale + self._x_offset,
            y * self._y_scale + self._y_offset,
        )

    def _size_to_pixel(self, w: float, h: float) -> tuple[float, float]:
        """Scale a plot-space size delta to pixels (no offset)."""
        return (
            w * self._x_scale,
            h * self._y_scale,
        )

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
        half_range = max(xmax - xmin, ymax - ymin) / 2

        if half_range == 0:
            half_range = 10

        dpg.set_axis_limits(f"{self.tag}_plot_xaxis", px - half_range, px + half_range)
        dpg.set_axis_limits(f"{self.tag}_plot_yaxis", py - half_range, py + half_range)

        def release():
            dpg.set_axis_limits_auto(f"{self.tag}_plot_xaxis")
            dpg.set_axis_limits_auto(f"{self.tag}_plot_yaxis")
            dpg.split_frame()
            self._layout_dirty = True
 
        dpg.set_frame_callback(dpg.get_frame_count() + 1, release)

    def look_at_node(self, node: str) -> None:
        n = self.nodes[node]
        # n.pos and n.size are plot-space; compute the node centre directly
        self.look_at(n.x + n.width / 2, n.y + n.height / 2)

    def zoom_show_all(self) -> None:
        xmin = 0
        xmax = 0
        ymin = 0
        ymax = 0

        for n in self.nodes.values():
            if not n.visible or n.size is None:
                continue

            xmin = min(n.x, xmin)
            xmax = max(n.x + n.width, xmax)
            ymin = min(n.y, ymin)
            ymax = max(n.y + n.height, ymax)

        xrange = xmax - xmin + self.layout.node0_margin[0]
        yrange = ymax - ymin + self.layout.node0_margin[1]
        half_range = max(xrange, yrange) / 2
        cx = xmin + (xmax - xmin) / 2
        cy = ymin + (ymax - ymin) / 2
        
        dpg.set_axis_limits(f"{self.tag}_plot_xaxis", cx - half_range, cx + half_range)
        dpg.set_axis_limits(f"{self.tag}_plot_yaxis", cy - half_range, cy + half_range)

        def release():
            dpg.set_axis_limits_auto(f"{self.tag}_plot_xaxis")
            dpg.set_axis_limits_auto(f"{self.tag}_plot_yaxis")
            dpg.split_frame()
            self._layout_dirty = True
 
        dpg.set_frame_callback(dpg.get_frame_count() + 1, release)

    # === Canvas interactions ==============================

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

    # === Canvas content management ========================

    def clear(self):
        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True, slot=1)
        self.color_generator.reset()

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        self.selected_node = None
        self._layout_dirty = True

        #self.look_at(0.0, 0.0)

    def regenerate(self):
        if not self.graph:
            return

        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True, slot=1)
        self.color_generator.reset()

        # Pre-compute a layout at the current zoom so the series has real
        # plot-space positions for DPG to auto-fit and transform. _layout_dirty
        # triggers a recompute on the first callback with the actual zoom factor.
        for node in self.nodes.values():
            if node.visible and node.size is None:
                node.size = self._estimate_node_size(node)

        self.layout.compute_layout(self.graph, self.nodes)

        visible = [n for n in self.nodes.values() if n.visible and n.pos is not None]
        px = [n.x for n in visible] or [0.0]
        py = [n.y for n in visible] or [0.0]

        dpg.add_custom_series(
            px,
            py,
            2,
            callback=self._render_graph,
            tooltip=False,
            parent=f"{self.tag}_plot_yaxis",
            tag=f"{self.tag}_plot_series",
        )

        self._layout_dirty = True

        if self.selected_node:
            selected = self.selected_node
            self.selected_node = None
            self.select(selected)

        self.zoom_show_all()

    def show_node_path(self, path: list[Node | str]) -> None:
        self.clear(False)

        if not path:
            return

        for node in path:
            if isinstance(node, str):
                node = self.nodes[node]
            self.unfold_node(node)

        self.select(path[-1])

    def isolate_branch(self, node: Node | str) -> None:
        if isinstance(node, str):
            node = self.nodes[node]

        # Remove all nodes that don't need to be visible anymore. This is
        # more complicated than it seems, as we need to keep the branch
        # unfolded by the user as it is
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

        self._layout_dirty = True

    def select(self, node: Node | str):
        if not self.select_enabled:
            return

        if isinstance(node, str):
            node = self.nodes.get(node)

        if not node or node not in self.nodes.values():
            return

        if get_config().single_branch_mode:
            if node != self.selected_node:
                # For programmatic reveal
                if not node.visible:
                    self.reveal(node)

                else:
                    # Fold all other nodes on the same level
                    for n in self.nodes.values():
                        if n.visible and n.level == node.level:
                            self.fold_node(n)
        else:
            if node == self.selected_node:
                self.deselect()
                return

        self.selected_node = node
        self.unfold_node(node)
        self._layout_dirty = True

        if self.on_node_selected:
            self.on_node_selected(node)

    def deselect(self):
        if self.selected_node is None:
            return

        self.fold_node(self.selected_node)
        self.selected_node = None
        self._layout_dirty = True

        if self.on_node_selected:
            self.on_node_selected(None)

    def unfold_node(self, node: Node) -> None:
        node.visible = True
        node.unfolded = True

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes.get(child_id)
            if child_node:
                child_node.visible = True

        self._layout_dirty = True

    def fold_node(self, node: Node) -> None:
        subtree = nx.descendants(self.graph, node.id) | {node.id}
 
        # Topological order: a parent's visibility is settled before its children
        for desc_id in nx.descendants(self.graph, node.id):
            desc = self.nodes[desc_id]
            # A descendant is hidden unless it has a visible parent outside the subtree
            has_outside_parent = any(
                self.nodes[p].visible
                for p in self.graph.predecessors(desc_id)
                if p not in subtree
            )
            if not has_outside_parent:
                desc.visible = False
                desc.unfolded = False
 
        node.unfolded = False
        self._layout_dirty = True

    def reveal(self, node: Node | str) -> None:
        if isinstance(node, str):
            node = self.nodes[node]

        self.clear(False)

        path = nx.shortest_path(self.graph, self.root, node.id)
        for n in path:
            self.unfold_node(self.nodes[n])

    def reveal_descendant_nodes(self, node: Node | str = None) -> None:
        if not node:
            node = self.root

        if isinstance(node, str):
            node = self.nodes[node]

        for succ_id in nx.descendants(self.graph, node.id):
            succ = self.nodes[succ_id]
            succ.visible = True
            succ.unfolded = True

        self._layout_dirty = True

    def reveal_all_nodes(self, max_depth: int = -1) -> None:
        if max_depth == 0:
            return

        for n in self.graph.nodes:
            node = self.nodes[n]
            if max_depth < 0 or node.level < max_depth:
                node.visible = True
                node.unfolded = True

        self._layout_dirty = True

    def _estimate_node_size(self, node: Node) -> tuple[float, float]:
        # Size in plot-space units, zoom-independent
        margin = self.layout.text_margin
        lines = self.get_node_frontpage(node)

        if isinstance(lines, str):
            lines = [lines]
        elif isinstance(lines[0], tuple):
            lines = [t for t, _ in lines]

        max_len = max(len(s) for s in lines)
        return estimate_drawn_text_size(
            max_len, num_lines=len(lines), font_size=12, scale=1, margin=margin
        )
        
    def _render_graph(self, sender: str, app_data: list, user_data: Any) -> None:
        # Save some cpu cycles when no updates are needed
        if not (
            self._layout_dirty
            or dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
            or dpg.is_item_hovered(self.tag)
        ):
            return

        widget_w, widget_h = dpg.get_item_rect_size(self.tag)
        if widget_w == 0 or widget_h == 0:
            return

        # Derive the plot -> pixel linear transform from axis limits and widget size.
        #   pixel(p) = p * scale + offset
        xmin, xmax = dpg.get_axis_limits(f"{self.tag}_plot_xaxis")
        ymin, ymax = dpg.get_axis_limits(f"{self.tag}_plot_yaxis")

        x_range = xmax - xmin
        y_range = ymax - ymin
        if x_range == 0 or y_range == 0:
            return

        helper_data = app_data[0]
        mouse_x = helper_data["MouseX_PixelSpace"]
        mouse_y = helper_data["MouseY_PixelSpace"]
        self.hovered_node = None

        # One series anchor gives us offset once we know scale.
        # scale ~ widget_pixels / axis_range (the border eats a few px, but the
        # anchor corrects for that via offset).
        tx0, ty0 = app_data[1][0], app_data[2][0]
        plot_vals = dpg.get_value(f"{self.tag}_plot_series")
        px0, py0 = plot_vals[0][0], plot_vals[1][0]

        # pixel(p) = p * scale + offset
        # scale = widget_pixels / axis_range  (approximation; corrected by offset below)
        # offset = anchor_pixel - anchor_plot * scale  (pins the transform to one known point)
        self._x_scale = widget_w / x_range
        self._y_scale = widget_h / y_range
        self._x_offset = tx0 - px0 * self._x_scale
        self._y_offset = ty0 - py0 * self._y_scale

        if self._layout_dirty:
            for node in self.nodes.values():
                if node.visible and node.size is None:
                    # Estimate size in plot space; layout uses plot-space units
                    node.size = self._estimate_node_size(node)

            self._plot_positions = self.layout.compute_layout(self.graph, self.nodes)
            self._layout_dirty = False

        dpg.delete_item(sender, children_only=True, slot=2)
        dpg.push_container_stack(sender)
        dpg.configure_item(sender, tooltip=False)

        # Topological order ensures parents are drawn (and positioned) before children
        for n in nx.topological_sort(self.graph):
            node = self.nodes[n]
            plot_pos = self._plot_positions.get(n)
            if not node.visible or plot_pos is None:
                continue

            px, py = self._to_pixel(*plot_pos)
            pw_node, ph_node = self._size_to_pixel(*node.size) if node.size else (0.0, 0.0)

            if self.draw_edges:
                for child_id in self.graph.successors(node.id):
                    child_node = self.nodes[child_id]
                    child_pos = self._plot_positions.get(child_id)
                    if child_node.visible and child_pos is not None:
                        cx, cy = self._to_pixel(*child_pos)
                        self._draw_edge(
                            node, px, py, pw_node, ph_node, child_node, cx, cy
                        )

            # Hit-test with pixel-space mouse coords and pixel-space box
            if not self.hovered_node:
                x1, y1 = px, py
                x2, y2 = px + pw_node, py + ph_node
                if x1 <= mouse_x < x2 and y1 <= mouse_y < y2:
                    self.hovered_node = node

            self._draw_node(node, px, py, pw_node, ph_node)

        dpg.pop_container_stack()

    def _draw_node(
        self, node: Node, px: float, py: float, pixel_w: float, pixel_h: float
    ) -> None:
        tag = f"{self.tag}_node_{node.id}"

        if dpg.does_item_exist(tag):
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

        if self.select_enabled and node == self.selected_node:
            edge_color = style.blue
            thickness = 2
        elif self.hover_enabled and node == self.hovered_node:
            edge_color = style.white
            thickness = 2
        else:
            edge_color = style.white
            thickness = 1

        dpg.draw_rectangle(
            (px, py),
            (px + pixel_w, py + pixel_h),
            fill=style.dark_grey,
            color=edge_color,
            thickness=thickness,
            tag=f"{tag}_box",
        )

        for i, text in enumerate(lines):
            dpg.draw_text(
                (px + margin, py + margin + text_offset_y * i),
                text,
                size=12 * scale,
                color=colors[i],
            )

    def _draw_edge(
        self,
        node_a: Node,
        ax: float,
        ay: float,
        aw: float,
        ah: float,
        node_b: Node,
        bx: float,
        by: float,
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

        # Pixel size of node_b; needed for mid-point calculations.
        # node_b.size is plot-space, so scale it.
        scale = self.zoom_factor
        bw = node_b.width * scale if node_b.size else 0.0
        bh = node_b.height * scale if node_b.size else 0.0

        if self.edge_style == "manhattan":
            p0x = ax + aw  # right edge of node_a (pixels)
            p0y = ay + ah / 2  # vertical centre of node_a (pixels)
            p1x = bx  # left edge of node_b (pixels)
            p1y = by + bh / 2  # vertical centre of node_b (pixels)

            mid_x = p1x - self.layout.gap_x * scale / 2

            dpg.draw_polygon(
                [(p0x, p0y), (mid_x, p0y), (mid_x, p1y), (p1x, p1y)],
                color=color,
                thickness=thickness,
                tag=tag,
            )
        elif self.edge_style == "straight":
            p0x = ax + aw / 2
            p0y = ay + ah / 2
            p1x = bx + bw / 2
            p1y = by + bh / 2

            dpg.draw_line((p0x, p0y), (p1x, p1y), color=color, tag=tag)

        if self.get_edge_label:
            label = self.get_edge_label(node_a, node_b)
            if label:
                margin = self.layout.text_margin
                tw, th = estimate_drawn_text_size(
                    len(label), font_size=11, scale=scale, margin=margin
                )
                lx = (p0x + p1x) / 2 - tw / 2
                ly = (p0y + p1y) / 2 - th * 2 / 5

                with dpg.draw_node(
                    tag=f"{tag}_label",
                    parent=f"{self.tag}_node_layer",
                ):
                    dpg.draw_rectangle(
                        (lx, ly),
                        (lx + tw, ly + th),  # absolute pmax, not size
                        fill=style.dark_grey,
                        color=None,
                        show=False,
                        tag=f"{tag}_label_bg",
                    )
                    dpg.draw_text(
                        (lx + margin, ly + margin),
                        label,
                        size=11 * scale,
                        color=color,
                    )
