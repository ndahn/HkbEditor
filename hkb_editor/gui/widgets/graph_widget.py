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
        edge_style: Literal["manhattan", "bezier", "straight"] = "manhattan",
        rainbow_edges: bool = False,
        select_enabled: bool = True,
        hover_enabled: bool = True,
        default_axis_range: int = 600,
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
        self.prev_hover: Node = None
        self.hovered_node: Node = None
        self.selected_node: Node = None
        self.default_axis_range = default_axis_range

        self._manual_highlights: dict[str, style.RGBA] = {}

        self._x_scale = 1.0
        self._x_offset = 0.0
        self._y_scale = 1.0
        self._y_offset = 0.0
        # Previous-frame transform; used to detect pan/zoom changes
        self._prev_x_scale = 0.0
        self._prev_y_scale = 0.0
        self._prev_x_offset = 0.0
        self._prev_y_offset = 0.0
        # Plot-space positions from the last layout pass; used to transform to pixels
        self._plot_positions: dict[str, tuple[float, float]] = {}
        self._graph_layers: list[str] = None
        # Persistent draw-item bookkeeping for diff-based updates
        self._rendered_nodes: set[str] = set()
        self._rendered_edges: set[tuple[str, str]] = set()
        # Tracks which rendered items currently have show=True so we don't re-set it each frame
        self._visible_nodes: set[str] = set()
        self._visible_edges: set[tuple[str, str]] = set()
        self._node_line_counts: dict[str, int] = {}
        self._edge_base_colors: dict[tuple[str, str], tuple] = {}
        # Cached label length (chars) per edge so we don't have to read it back from DPG
        self._edge_label_lens: dict[tuple[str, str], int] = {}
        # Track previous hover/selection so style transitions can be applied incrementally
        self._prev_selected: Node = None

        # Set when visibility changes; cleared after layout is recomputed
        self._layout_dirty: bool = False
        self._render_required: bool = False

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
            dpg.configure_item(self.tag, pan_button=cfg.pan_button_id)

        @cfg.events.invert_zoom.connect
        def on_invertzoom_changed(new: bool, old: bool) -> None:
            rate = -0.1 if cfg.invert_zoom else 0.1
            dpg.configure_item(self.tag, zoom_rate=rate)

        with dpg.plot(
            no_menus=True,
            no_mouse_pos=True,
            no_box_select=True,
            no_frame=True,
            no_title=True,
            pan_button=cfg.pan_button_id,
            equal_aspects=True,
            zoom_rate=-0.1 if cfg.invert_zoom else 0.1,
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
        self.nodes.clear()
        self.graph = graph

        if graph:
            # Topological order ensures parents are drawn (and positioned) before children
            self._graph_layers = list(nx.topological_sort(graph))
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

    def clear_highlights(self) -> None:
        affected = list(self._manual_highlights.keys())
        self._manual_highlights.clear()
        # Restyle each previously-highlighted node so the highlight visually clears
        for nid in affected:
            node = self.nodes.get(nid)
            if node:
                self._apply_node_style(node)

    def highlight_node(self, node: Node | str, color: style.RGBA = style.green) -> None:
        if isinstance(node, Node):
            node = node.id

        self._manual_highlights[node] = color
        target = self.nodes.get(node)
        if target:
            self._apply_node_style(target)

    def unhighlight_node(self, node: Node | str) -> None:
        if isinstance(node, Node):
            node = node.id

        self._manual_highlights.pop(node, None)
        target = self.nodes.get(node)
        if target:
            self._apply_node_style(target)

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

    def _unlock_axes(self) -> None:
        def release():
            dpg.set_axis_limits_auto(f"{self.tag}_plot_xaxis")
            dpg.set_axis_limits_auto(f"{self.tag}_plot_yaxis")
            dpg.split_frame()
            self._layout_dirty = True

        dpg.set_frame_callback(dpg.get_frame_count() + 1, release)

    def goto_node(self, node: str | Node) -> None:
        if not node:
            return

        if isinstance(node, str):
            node = self.nodes[node]

        ar = self.default_axis_range
        dpg.set_axis_limits(
            f"{self.tag}_plot_xaxis", node.x - ar * 0.1, node.x + ar * 0.9
        )
        dpg.set_axis_limits(
            f"{self.tag}_plot_yaxis", node.y + ar * 0.1, node.y - ar * 0.9
        )
        self._unlock_axes()

    def look_at_node(self, node: str | Node) -> None:
        if not node:
            return

        if isinstance(node, str):
            node = self.nodes[node]

        # n.pos and n.size are plot-space; compute the node centre directly
        self.look_at(node.x + node.width / 2, node.y + node.height / 2)

    def look_at(self, px: float, py: float) -> None:
        xmin, xmax = dpg.get_axis_limits(f"{self.tag}_plot_xaxis")
        ymin, ymax = dpg.get_axis_limits(f"{self.tag}_plot_yaxis")
        axis_range = max(xmax - xmin, ymax - ymin, self.default_axis_range)

        dpg.set_axis_limits(
            f"{self.tag}_plot_xaxis", px - axis_range * 0.1, px + axis_range * 0.9
        )
        dpg.set_axis_limits(
            f"{self.tag}_plot_yaxis", py + axis_range * 0.1, py - axis_range * 0.9
        )
        self._unlock_axes()

    def show_all(self) -> None:
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
        max_range = max(xrange, yrange, self.default_axis_range)
        margin = max_range * 0.1

        pxmin = xmin - margin
        pxmax = pxmin + max_range + margin
        pymin = ymin + margin
        pymax = pymin - max_range - margin

        dpg.set_axis_limits(f"{self.tag}_plot_xaxis", pxmin, pxmax)
        dpg.set_axis_limits(f"{self.tag}_plot_yaxis", pymin, pymax)
        self._unlock_axes()

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
                label="Show Selection",
                callback=lambda s, a, u: self.goto_node(self.selected_node),
            )
            dpg.add_menu_item(
                label="Show All",
                callback=self.show_all,
            )

    # === Canvas content management ========================

    def clear(self):
        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True, slot=1)
        self.color_generator.reset()

        # The series and all its children are gone; reset diff tracking
        self._rendered_nodes.clear()
        self._rendered_edges.clear()
        self._visible_nodes.clear()
        self._visible_edges.clear()
        self._node_line_counts.clear()
        self._edge_base_colors.clear()
        self._edge_label_lens.clear()
        self._prev_selected = None
        self.prev_hover = None
        self.hovered_node = None

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        if self.graph:
            root = next(n for n, in_deg in self.graph.in_degree() if in_deg == 0)
            self.nodes[root].visible = True

        self.selected_node = None
        self._layout_dirty = True

        # self.look_at(0.0, 0.0)

    def regenerate(self):
        if not self.graph:
            return

        dpg.delete_item(f"{self.tag}_plot_yaxis", children_only=True, slot=1)
        self.color_generator.reset()

        # Series children are gone; reset diff tracking before the new series is created
        self._rendered_nodes.clear()
        self._rendered_edges.clear()
        self._visible_nodes.clear()
        self._visible_edges.clear()
        self._node_line_counts.clear()
        self._edge_base_colors.clear()
        self._edge_label_lens.clear()

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

        self.show_all()

    def show_node_path(self, path: list[Node | str]) -> None:
        if not path:
            return

        self.reveal()

        self.clear()
        for node in path:
            if isinstance(node, str):
                node = self.nodes[node]
            self.unfold_node(node)

        self.regenerate()
        self.look_at_node(path[-1])
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

        if not node or node.id not in self.nodes:
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
        if not node:
            return

        if isinstance(node, str):
            node = self.nodes[node]

        self.clear()

        path = nx.shortest_path(self.graph, self.root, node.id)
        for n in path:
            self.unfold_node(self.nodes[n])

        self.regenerate()
        self.look_at_node(node)

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
            or self._render_required
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
        self.prev_hover = self.hovered_node
        self.hovered_node = None

        # One series anchor gives us offset once we know scale.
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

        # Detect transform changes so we only update positions when needed
        transform_changed = (
            self._x_scale != self._prev_x_scale
            or self._y_scale != self._prev_y_scale
            or self._x_offset != self._prev_x_offset
            or self._y_offset != self._prev_y_offset
        )
        zoom_changed = (
            self._x_scale != self._prev_x_scale or self._y_scale != self._prev_y_scale
        )

        if self._layout_dirty:
            for node in self.nodes.values():
                if node.visible and node.size is None:
                    # Estimate size in plot space; layout uses plot-space units
                    node.size = self._estimate_node_size(node)

            self._plot_positions = self.layout.compute_layout(self.graph, self.nodes)
            self._layout_dirty = False
            # Layout move requires position update even if transform didn't change
            transform_changed = True

        geometry_update = transform_changed
        self._render_required = False

        dpg.push_container_stack(sender)
        dpg.configure_item(sender, tooltip=False)

        # Pixel positions used by both node and edge passes; built during node pass
        node_pixels: dict[str, tuple[float, float, float, float]] = {}

        # Topological order ensures parents are created before children, which means
        # edges (created with the parent) have valid child positions on the same frame
        for n in self._graph_layers:
            node = self.nodes[n]
            plot_pos = self._plot_positions.get(n)

            if not node.visible or plot_pos is None:
                if n in self._rendered_nodes:
                    self._hide_node_items(n)
                continue

            px, py = self._to_pixel(*plot_pos)
            pw, ph = self._size_to_pixel(*node.size) if node.size else (0.0, 0.0)
            node_pixels[n] = (px, py, pw, ph)

            # Hit-test in pixel space; first match wins
            if not self.hovered_node:
                if px <= mouse_x < px + pw and py <= mouse_y < py + ph:
                    self.hovered_node = node

            if n not in self._rendered_nodes:
                self._draw_node(node, px, py, pw, ph)
                self._rendered_nodes.add(n)
            else:
                # Re-show in case it was hidden previously
                self._show_node_items(n)
                if geometry_update:
                    self._update_node_geometry(node, px, py, pw, ph, zoom_changed)

        # Edge pass — separate from nodes so both endpoints have known pixel positions
        if self.draw_edges:
            for a_id, b_id in self.graph.edges:
                key = (a_id, b_id)
                a_geom = node_pixels.get(a_id)
                b_geom = node_pixels.get(b_id)

                if a_geom is None or b_geom is None:
                    if key in self._rendered_edges:
                        self._hide_edge_items(key)
                    continue

                ax, ay, aw, ah = a_geom
                bx, by, bw, bh = b_geom

                if key not in self._rendered_edges:
                    self._draw_edge(
                        self.nodes[a_id],
                        ax,
                        ay,
                        aw,
                        ah,
                        self.nodes[b_id],
                        bx,
                        by,
                        bw,
                        bh,
                    )
                    self._rendered_edges.add(key)
                else:
                    self._show_edge_items(key)
                    if geometry_update:
                        self._update_edge_geometry(
                            a_id, b_id, ax, ay, aw, ah, bx, by, bw, bh, zoom_changed
                        )

        # Apply style transitions for hover and selection changes
        if self.prev_hover != self.hovered_node:
            self._apply_node_style(self.prev_hover)
            self._apply_node_style(self.hovered_node)
            self._apply_adjacent_edge_styles(self.prev_hover)
            self._apply_adjacent_edge_styles(self.hovered_node)

        if self._prev_selected != self.selected_node:
            self._apply_node_style(self._prev_selected)
            self._apply_node_style(self.selected_node)
            self._apply_adjacent_edge_styles(self._prev_selected)
            self._apply_adjacent_edge_styles(self.selected_node)
            self._prev_selected = self.selected_node

        # Cache transform for next-frame change detection
        self._prev_x_scale = self._x_scale
        self._prev_y_scale = self._y_scale
        self._prev_x_offset = self._x_offset
        self._prev_y_offset = self._y_offset

        dpg.pop_container_stack()

    # === Draw-item helpers ================================

    def _node_tag(self, node: Node | str, suffix: str = None) -> str:
        nid = node.id if isinstance(node, Node) else node
        t = f"{self.tag}_node_{nid}"
        if suffix:
            t += "_" + suffix
        return t

    def _edge_tag(self, a_id: str, b_id: str, suffix: str = None) -> str:
        t = f"{self.tag}_edge_{a_id}_TO_{b_id}"
        if suffix:
            t += "_" + suffix
        return t

    def _hide_node_items(self, node_id: str) -> None:
        if node_id not in self._visible_nodes:
            return
        box_tag = self._node_tag(node_id, "box")
        if dpg.does_item_exist(box_tag):
            dpg.configure_item(box_tag, show=False)
        for i in range(self._node_line_counts.get(node_id, 0)):
            line_tag = self._node_tag(node_id, f"text_{i}")
            if dpg.does_item_exist(line_tag):
                dpg.configure_item(line_tag, show=False)
        self._visible_nodes.discard(node_id)

    def _show_node_items(self, node_id: str) -> None:
        if node_id in self._visible_nodes:
            return
        box_tag = self._node_tag(node_id, "box")
        if dpg.does_item_exist(box_tag):
            dpg.configure_item(box_tag, show=True)
        for i in range(self._node_line_counts.get(node_id, 0)):
            line_tag = self._node_tag(node_id, f"text_{i}")
            if dpg.does_item_exist(line_tag):
                dpg.configure_item(line_tag, show=True)
        self._visible_nodes.add(node_id)

    def _hide_edge_items(self, key: tuple[str, str]) -> None:
        if key not in self._visible_edges:
            return
        a_id, b_id = key
        edge_tag = self._edge_tag(a_id, b_id)
        if dpg.does_item_exist(edge_tag):
            dpg.configure_item(edge_tag, show=False)
        for suffix in ("label", "label_bg"):
            t = self._edge_tag(a_id, b_id, suffix)
            if dpg.does_item_exist(t):
                dpg.configure_item(t, show=False)
        self._visible_edges.discard(key)

    def _show_edge_items(self, key: tuple[str, str]) -> None:
        if key in self._visible_edges:
            return
        a_id, b_id = key
        edge_tag = self._edge_tag(a_id, b_id)
        if dpg.does_item_exist(edge_tag):
            dpg.configure_item(edge_tag, show=True)
        for suffix in ("label", "label_bg"):
            t = self._edge_tag(a_id, b_id, suffix)
            if dpg.does_item_exist(t):
                dpg.configure_item(t, show=True)
        self._visible_edges.add(key)

    # === Style application ================================

    def _apply_node_style(self, node: Node) -> None:
        # Compute the box color and thickness from current select/hover/highlight state
        if not node:
            return

        box_tag = self._node_tag(node, "box")
        if not dpg.does_item_exist(box_tag):
            return

        color = style.white
        thickness = 1

        if self.select_enabled and node == self.selected_node:
            color = style.blue
            thickness = 2
        else:
            if node.id in self._manual_highlights:
                color = self._manual_highlights[node.id]
            if self.hover_enabled and node == self.hovered_node:
                thickness = 2

        dpg.configure_item(box_tag, color=color, thickness=thickness)

    def _apply_edge_style(self, a_id: str, b_id: str) -> None:
        # Edge color follows hover (yellow) > selection (orange) > base color
        edge_tag = self._edge_tag(a_id, b_id)
        if not dpg.does_item_exist(edge_tag):
            return

        node_a = self.nodes.get(a_id)
        node_b = self.nodes.get(b_id)
        base_color = self._edge_base_colors.get((a_id, b_id), style.white)

        if self.hover_enabled and (
            node_a is self.hovered_node or node_b is self.hovered_node
        ):
            color = style.yellow
            thickness = 2
        elif self.select_enabled and (
            node_a is self.selected_node or node_b is self.selected_node
        ):
            color = style.orange
            thickness = 2
        else:
            color = base_color
            thickness = 1

        dpg.configure_item(edge_tag, color=color, thickness=thickness)

        # Edge label colour matches the edge
        label_tag = self._edge_tag(a_id, b_id, "label")
        if dpg.does_item_exist(label_tag):
            dpg.configure_item(label_tag, color=color)

    def _apply_adjacent_edge_styles(self, node: Node) -> None:
        # Restyle every edge touching this node so hover/select highlights propagate
        if not node or not self.graph:
            return
        for child_id in self.graph.successors(node.id):
            self._apply_edge_style(node.id, child_id)
        for parent_id in self.graph.predecessors(node.id):
            self._apply_edge_style(parent_id, node.id)

    # === Node and edge creation / geometry updates =======

    def _draw_node(
        self, node: Node, px: float, py: float, pw: float, ph: float
    ) -> None:
        # Create persistent box and text-line items for the node
        scale = self.zoom_factor
        margin = self.layout.text_margin
        text_offset_y = 12 * scale
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

        dpg.draw_rectangle(
            (px, py),
            (px + pw, py + ph),
            fill=style.dark_grey,
            color=style.white,
            thickness=1,
            tag=self._node_tag(node, "box"),
        )

        for i, text in enumerate(lines):
            dpg.draw_text(
                (px + margin, py + margin + text_offset_y * i),
                text,
                size=12 * scale,
                color=colors[i],
                tag=self._node_tag(node, f"text_{i}"),
            )

        self._node_line_counts[node.id] = len(lines)
        self._visible_nodes.add(node.id)

        # Apply current select/hover/highlight state to the freshly drawn box
        self._apply_node_style(node)

    def _update_node_geometry(
        self,
        node: Node,
        px: float,
        py: float,
        pw: float,
        ph: float,
        zoom_changed: bool,
    ) -> None:
        # Move and resize the persistent box and text lines for a layout/pan/zoom change
        dpg.configure_item(
            self._node_tag(node, "box"), pmin=(px, py), pmax=(px + pw, py + ph)
        )

        scale = self.zoom_factor
        margin = self.layout.text_margin
        text_offset_y = 12 * scale

        for i in range(self._node_line_counts.get(node.id, 0)):
            line_tag = self._node_tag(node, f"text_{i}")
            if not dpg.does_item_exist(line_tag):
                continue
            pos = (px + margin, py + margin + text_offset_y * i)
            if zoom_changed:
                dpg.configure_item(line_tag, pos=pos, size=12 * scale)
            else:
                dpg.configure_item(line_tag, pos=pos)

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
        bw: float,
        bh: float,
    ) -> None:
        # Create the persistent edge geometry plus optional label
        tag = self._edge_tag(node_a.id, node_b.id)

        # Resolve and remember a base color so style transitions can revert correctly
        if self.rainbow_edges:
            base = self.color_generator(node_a.id)
            base = tuple((c + 255) // 2 for c in base)
        else:
            base = style.white
        self._edge_base_colors[(node_a.id, node_b.id)] = base

        scale = self.zoom_factor

        if self.edge_style == "manhattan":
            p0x = ax + aw
            p0y = ay + ah / 2
            p1x = bx
            p1y = by + bh / 2
            mid_x = p1x - self.layout.gap_x * scale / 2

            dpg.draw_polygon(
                [(p0x, p0y), (mid_x, p0y), (mid_x, p1y), (p1x, p1y)],
                color=base,
                thickness=1,
                tag=tag,
            )
        elif self.edge_style == "bezier":
            p0x = ax + aw / 2
            p0y = ay + ah / 2
            p1x = bx + bw / 2
            p1y = by + bh / 2
            dpg.draw_bezier_cubic(
                (p0x, p0y),
                (p1x, p0y),
                (p0x, p1y),
                (p1x, p1y),
                color=base,
                thickness=1,
                tag=tag,
            )
        else:  # "straight"
            p0x = ax + aw / 2
            p0y = ay + ah / 2
            p1x = bx + bw / 2
            p1y = by + bh / 2

            dpg.draw_line((p0x, p0y), (p1x, p1y), color=base, thickness=1, tag=tag)

        if self.get_edge_label:
            label = self.get_edge_label(node_a, node_b)
            if label:
                margin = self.layout.text_margin
                tw, th = estimate_drawn_text_size(
                    len(label), font_size=11, scale=scale, margin=margin
                )
                lx = (p0x + p1x) / 2 - tw / 2
                ly = (p0y + p1y) / 2 - th * 2 / 5

                # Stored as siblings of the edge so configure_item works on them directly
                dpg.draw_rectangle(
                    (lx, ly),
                    (lx + tw, ly + th),
                    fill=style.dark_grey,
                    color=None,
                    show=False,
                    tag=self._edge_tag(node_a.id, node_b.id, "label_bg"),
                )
                dpg.draw_text(
                    (lx + margin, ly + margin),
                    label,
                    size=11 * scale,
                    color=base,
                    tag=self._edge_tag(node_a.id, node_b.id, "label"),
                )
                self._edge_label_lens[(node_a.id, node_b.id)] = len(label)

        self._visible_edges.add((node_a.id, node_b.id))

        # Apply current hover/select state in case this edge is adjacent to either
        self._apply_edge_style(node_a.id, node_b.id)

    def _update_edge_geometry(
        self,
        a_id: str,
        b_id: str,
        ax: float,
        ay: float,
        aw: float,
        ah: float,
        bx: float,
        by: float,
        bw: float,
        bh: float,
        zoom_changed: bool,
    ) -> None:
        # Reposition the polygon/line points; update label position and size on zoom
        tag = self._edge_tag(a_id, b_id)
        scale = self.zoom_factor

        if self.edge_style == "manhattan":
            p0x = ax + aw
            p0y = ay + ah / 2
            p1x = bx
            p1y = by + bh / 2
            mid_x = p1x - self.layout.gap_x * scale / 2
            dpg.configure_item(
                tag,
                points=[(p0x, p0y), (mid_x, p0y), (mid_x, p1y), (p1x, p1y)],
            )
        elif self.edge_style == "bezier":
            p0x = ax + aw / 2
            p0y = ay + ah / 2
            p1x = bx + bw / 2
            p1y = by + bh / 2
            dpg.draw_bezier_cubic(
                tag,
                p0=(p0x, p0y),
                p1=(p1x, p0y),
                p2=(p0x, p1y),
                p3=(p1x, p1y),
            )
        else:  # "straight"
            p0x = ax + aw / 2
            p0y = ay + ah / 2
            p1x = bx + bw / 2
            p1y = by + bh / 2
            dpg.configure_item(tag, p1=(p0x, p0y), p2=(p1x, p1y))

        label_tag = self._edge_tag(a_id, b_id, "label")
        if dpg.does_item_exist(label_tag):
            # Use cached label length to recompute the bounding box
            label_len = self._edge_label_lens.get((a_id, b_id), 0)
            margin = self.layout.text_margin
            tw, th = estimate_drawn_text_size(
                label_len, font_size=11, scale=scale, margin=margin
            )
            lx = (p0x + p1x) / 2 - tw / 2
            ly = (p0y + p1y) / 2 - th * 2 / 5

            if zoom_changed:
                dpg.configure_item(
                    label_tag, pos=(lx + margin, ly + margin), size=11 * scale
                )
            else:
                dpg.configure_item(label_tag, pos=(lx + margin, ly + margin))

            bg_tag = self._edge_tag(a_id, b_id, "label_bg")
            if dpg.does_item_exist(bg_tag):
                dpg.configure_item(bg_tag, pmin=(lx, ly), pmax=(lx + tw, ly + th))
