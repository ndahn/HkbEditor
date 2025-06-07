from typing import Any
import sys
from os import path
import shutil
from time import time
import math
from logging import getLogger
from dataclasses import dataclass
from dearpygui import dearpygui as dpg
import networkx as nx

from .workflows.file_dialog import open_file_dialog, save_file_dialog
from . import style
from .helpers import draw_graph_node


def get_default_layout_path():
    return path.join(path.dirname(sys.argv[0]), "default_layout.ini")


def get_custom_layout_path():
    return path.join(path.dirname(sys.argv[0]), "user_layout.ini")


@dataclass
class Layout:
    gap_x: int = 30
    step_y: int = 20
    node0_margin: tuple[int, int] = (50, 50)
    text_margin: int = 5
    zoom_factor: float = 1.5


@dataclass
class Node:
    id: str
    pos: tuple[float, float] = None
    size: tuple[float, float] = None
    visible: bool = False
    unfolded: bool = False
    layout_data: dict[str, Any] = None

    @property
    def x(self) -> float:
        return self.pos[0]

    @property
    def y(self) -> float:
        return self.pos[1]

    @property
    def width(self) -> float:
        return self.size[0]

    @property
    def height(self) -> float:
        return self.size[1]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            self.pos[0],
            self.pos[1],
            self.pos[0] + self.size[0],
            self.pos[1] + self.size[1],
        )

    def contains(self, px: float, py: float) -> bool:
        bbox = self.bbox
        return bbox[0] <= px < bbox[2] and bbox[1] <= py < bbox[3]

    def __str__(self):
        return self.id

    def __hash__(self):
        return hash(self.id)


class GraphEditor:
    def __init__(self, tag: str = 0):
        super().__init__()

        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        self.logger = getLogger(self.__class__.__name__)
        self.tag: str = tag
        self.roots_table: str = None
        self.canvas: str = None
        self.attributes_table: str = None
        self.loaded_file: str = None
        self.last_save: float = 0.0
        self.graph: nx.DiGraph = nx.DiGraph()
        self.layout = Layout()
        self.nodes: dict[str, Node] = {}
        self.selected_roots: set[str] = set()
        self.selected_node: Node = None
        self.canvas_transform: tuple[float, float] = (0.0, 0.0)
        self.dragging = False
        self.last_drag: tuple[float, float] = (0.0, 0.0)
        self.zoom_level = 0
        self.zoom_min = -3
        self.zoom_max = 3

        self._setup_content()

    @property
    def zoom(self) -> float:
        return self.layout.zoom_factor**self.zoom_level

    # These should be implemented by subclasses
    def get_supported_file_extensions(self) -> dict[str, str]:
        return {"All files": "*.*"}

    def get_root_ids(self) -> list[str]:
        return []

    def make_node(self, node_id: str) -> None:
        pass

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        return {}

    def set_node_attribute(self, node: Node, key: str, val: Any) -> None:
        pass

    def get_node_frontpage(
        self, node_id: str
    ) -> list[str] | list[tuple[str, tuple[int, int, int, int]]]:
        return [f"<{node_id}>"]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return node_id

    def get_node_menu_items(self, node: Node) -> list[str]:
        return []

    def get_canvas_menu_items(self) -> list[str]:
        return []

    def on_node_menu_item_selected(node: Node, selected_item: str) -> None:
        pass

    def on_canvas_menu_item_selected(self, selected_item: str) -> None:
        pass

    def on_node_selected(self, node: Node) -> None:
        pass

    def create_app_menu(self):
        self._create_file_menu()
        self._create_settings_menu()
        dpg.add_separator()
        self._create_dpg_menu()

    def _save_layout(self):
        dpg.save_init_file(get_custom_layout_path())
        self.logger.info("Saved custom layout")

    def _restore_default_layout(self):
        default_layout = get_default_layout_path()
        user_layout = get_custom_layout_path()

        if path.isfile(user_layout):
            shutil.move(get_custom_layout_path(), get_custom_layout_path() + ".old")
        
        # Replace the user layout with the default
        shutil.move(default_layout, user_layout)

        with dpg.window(
            label="Layout Restored",
            modal=True,
            autosize=True,
            min_size=(100, 50),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text("Layout restored - restart to apply!")
            dpg.add_separator()
            dpg.add_button(label="Okay", callback=lambda: dpg.delete_item(wnd))

    def _create_file_menu(self):
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open...", callback=self.file_open)
            dpg.add_separator()

            dpg.add_menu_item(
                label="Save",
                callback=self.file_save,
                enabled=False,
                tag=f"{self.tag}_menu_file_save",
            )
            dpg.add_menu_item(
                label="Save as...",
                callback=self.file_save_as,
                enabled=False,
                tag=f"{self.tag}_menu_file_save_as",
            )
            dpg.add_separator()

            dpg.add_menu_item(
                label="Save layout as default", callback=self._save_layout
            )
            dpg.add_menu_item(
                label="Restore factory layout", callback=self._restore_default_layout
            )

            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self.exit_app)

    def _create_settings_menu(self):
        with dpg.menu(label="Settings", tag=f"{self.tag}_menu_settings"):
            dpg.add_menu_item(
                label="Invert Zoom", check=True, tag=f"{self.tag}_settings_invert_zoom"
            )
            dpg.add_menu_item(
                label="Single Branch Mode",
                check=True,
                default_value=True,
                tag=f"{self.tag}_settings_single_branch_mode",
            )

    def _create_dpg_menu(self):
        with dpg.menu(label="dearpygui"):
            dpg.add_menu_item(
                label="Show About", callback=lambda: dpg.show_tool(dpg.mvTool_About)
            )
            dpg.add_menu_item(
                label="Show Metrics", callback=lambda: dpg.show_tool(dpg.mvTool_Metrics)
            )
            dpg.add_menu_item(
                label="Show Documentation",
                callback=lambda: dpg.show_tool(dpg.mvTool_Doc),
            )
            dpg.add_menu_item(
                label="Show Debug", callback=lambda: dpg.show_tool(dpg.mvTool_Debug)
            )
            dpg.add_menu_item(
                label="Show Style Editor",
                callback=lambda: dpg.show_tool(dpg.mvTool_Style),
            )
            dpg.add_menu_item(
                label="Show Font Manager",
                callback=lambda: dpg.show_tool(dpg.mvTool_Font),
            )
            dpg.add_menu_item(
                label="Show Item Registry",
                callback=lambda: dpg.show_tool(dpg.mvTool_ItemRegistry),
            )
            dpg.add_menu_item(
                label="Show Stack Tool",
                callback=lambda: dpg.show_tool(dpg.mvTool_Stack),
            )

    def file_open(self):
        ret = open_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self.logger.info("Loading file %s", ret)
            self._do_load_from_file(ret)
            self.loaded_file = ret
            self.last_save = 0.0
            self._clear_canvas()
            self._update_roots()

    def _do_load_from_file(self, file_path: str) -> None:
        # Just some test data
        g = self.graph = nx.DiGraph()

        g.add_node("A")
        g.add_node("AB1")
        g.add_node("AB2")
        g.add_node("AB3")
        g.add_node("AB1C1")
        g.add_node("AB1C2")
        g.add_node("AB2C1")
        g.add_node("AB3C1")
        g.add_node("AB3C2")
        g.add_node("AB3C3")
        g.add_node("AB3C4")
        g.add_node("AB2C1D1")
        g.add_node("AB2C1D2")

        # Add edges
        g.add_edge("A", "AB1")
        g.add_edge("A", "AB2")
        g.add_edge("A", "AB3")
        g.add_edge("AB1", "AB1C1")
        g.add_edge("AB1", "AB1C2")
        g.add_edge("AB2", "AB2C1")
        g.add_edge("AB3", "AB3C1")
        g.add_edge("AB3", "AB3C2")
        g.add_edge("AB3", "AB3C3")
        g.add_edge("AB3", "AB3C4")
        g.add_edge("AB2C1", "AB2C1D1")
        g.add_edge("AB2C1", "AB2C1D2")

        self._on_root_selected("", True, "A")

    def file_save(self):
        self._do_write_to_file(self.loaded_file)
        self.last_save = time()

    def file_save_as(self):
        ret = save_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            default_file=path.basename(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self._do_write_to_file(ret)
            self.loaded_file = ret
            self.last_save = time()

    def _do_write_to_file(self, file_path: str) -> None:
        pass

    def exit_app(self):
        dpg.stop_dearpygui()

    def _setup_content(self):
        with dpg.viewport_menu_bar():
            self.create_app_menu()

        # Roots
        with dpg.window(
            label="Root Nodes",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_roots_window",
        ):
            dpg.add_input_text(
                hint="Filter",
                tag=f"{self.tag}_roots_filter",
                callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                user_data=f"{self.tag}_roots_table",
                width=-1,
            )
            dpg.add_separator()
            # Tables are more flexible with item design and support filtering
            with dpg.table(
                delay_search=True,
                no_host_extendX=True,
                header_row=False,
                # policy=dpg.mvTable_SizingFixedFit,
                scrollY=True,
                tag=f"{self.tag}_roots_table",
            ) as self.roots_table:
                dpg.add_table_column(label="Name")

        # Canvas
        with dpg.window(
            label="Graph",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_canvas_window",
        ):
            with dpg.drawlist(800, 800, tag=f"{self.tag}_canvas") as self.canvas:
                dpg.add_draw_node(tag=f"{self.tag}_canvas_root")

        # Attributes panel
        with dpg.window(
            label="Attributes",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_attributes_window",
        ):
            dpg.add_input_text(
                hint="Filter",
                tag=f"{self.tag}_attribute_filter",
                callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                user_data=f"{self.tag}_attributes_table",
                width=-1,
            )
            dpg.add_separator()

            # Child window is needed to fix table sizing
            with dpg.child_window(border=False):
                dpg.add_text(
                    "", tag=f"{self.tag}_attributes_title", color=style.blue
                )
                with dpg.table(
                    delay_search=True,
                    no_host_extendX=True,
                    resizable=True,
                    borders_innerV=True,
                    policy=dpg.mvTable_SizingFixedFit,
                    header_row=False,
                    tag=f"{self.tag}_attributes_table",
                ) as self.attributes_table:
                    dpg.add_table_column(label="Value", width_stretch=True)
                    dpg.add_table_column(label="Key", width_fixed=True)

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

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_frame_callback(2, self._on_resize)

    # Callbacks
    def get_canvas_mouse_pos(self) -> tuple[float, float]:
        if not dpg.is_item_hovered(self.canvas):
            return (0.0, 0.0)

        mx, my = dpg.get_drawing_mouse_pos()
        ox, oy = self.canvas_transform
        return ((mx - ox), (my - oy))

    def get_node_at_pos(self, x: float, y: float) -> Node:
        for node in self.nodes.values():
            # TODO Something like a b-tree might have better performance,
            # but so far this is not a bottleneck
            if node.visible:
                if node.contains(x, y):
                    return node

        return None

    def _on_left_click(self, sender, button: int) -> None:
        if not dpg.is_item_hovered(self.canvas):
            return

        mx, my = self.get_canvas_mouse_pos()
        node = self.get_node_at_pos(mx, my)

        if not node:
            self._deselect_active_node()
        else:
            self._select_node(node)

    def _on_right_click(self, sender, button: int) -> None:
        if not dpg.is_item_hovered(self.canvas):
            return

        mx, my = self.get_canvas_mouse_pos()
        node = self.get_node_at_pos(mx, my)

        if node:
            if node != self.selected_node:
                self._select_node(node)

            self._open_node_menu(node)
        else:
            self._open_canvas_menu()

    def _on_drag_start(self) -> None:
        if dpg.is_item_hovered(self.canvas):
            self.dragging = True

    def _on_mouse_drag(self, sender, mouse_delta: list[float]) -> None:
        if not self.dragging:
            return

        _, delta_x, delta_y = mouse_delta
        self.last_drag = (delta_x, delta_y)
        self.look_at(
            self.canvas_transform[0] + delta_x, self.canvas_transform[1] + delta_y
        )

    def _on_drag_release(self, sender, mouse_button) -> None:
        if not self.dragging:
            return

        self.set_origin(
            self.canvas_transform[0] + self.last_drag[0],
            self.canvas_transform[1] + self.last_drag[1],
        )

        self.last_drag = (0.0, 0.0)
        self.dragging = False

    def _on_mouse_wheel(self, sender, wheel_delta: int):
        if not dpg.is_item_hovered(self.canvas):
            return

        if dpg.get_value(f"{self.tag}_settings_invert_zoom"):
            wheel_delta = -wheel_delta

        # Scrolling too fast can cause problems
        with dpg.mutex():
            zoom_point = self.get_canvas_mouse_pos()
            self.set_zoom(self.zoom_level + wheel_delta, zoom_point)

    def _on_resize(self):
        cw, ch = dpg.get_item_rect_size(f"{self.tag}_canvas_window")
        dpg.set_item_width(self.canvas, cw)
        dpg.set_item_height(self.canvas, ch)

    def set_origin(self, new_x: float, new_y: float) -> None:
        self.canvas_transform = (new_x, new_y)
        self.look_at(*self.canvas_transform)

    def look_at(self, px: float, py: float) -> None:
        dpg.apply_transform(
            f"{self.tag}_canvas_root",
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
        self._regenerate_canvas()

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

    def get_graph(self, root_id: str) -> nx.DiGraph:
        return nx.DiGraph()

    def prepate_nodes(self, root_id: str) -> None:
        paths = nx.shortest_path(self.graph, root_id)

        for n in self.nodes.values():
            if n.id in paths:
                n.layout_data = {"level": len(paths[n.id]) - 1}

    def _on_root_selected(self, sender: str, selected: bool, root_id: str):
        self.graph.clear()

        # For now we only allow one root to be selected
        for other in self.get_root_ids():
            self.selected_roots.discard(other)
            tag = f"{self.tag}_root_{other}_selectable"
            if other != root_id and dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

        # Build the new graph and combine it with the existing one
        root_graph: nx.DiGraph = self.get_graph(root_id)

        if selected:
            self.selected_roots.add(root_id)
            self.graph = nx.compose(self.graph, root_graph)

            for n in root_graph.nodes:
                if n not in self.nodes:
                    self.nodes[n] = Node(n)

            self.prepate_nodes(root_id)

            self._clear_canvas()
            self._clear_attributes()
            root_node = self.nodes[root_id]
            self._draw_node(root_node)

        else:
            self.selected_roots.pop(root_id)
            for n in root_graph.nodes:
                del self.nodes[n]

            self.graph.remove_nodes_from(root_graph.nodes)

            if self.selected_node and self.selected_node not in self.nodes:
                self.selected_node = None

            self._regenerate_canvas()

    def _clear_canvas(self):
        dpg.delete_item(f"{self.tag}_canvas_root", children_only=True)

        for node in self.nodes.values():
            node.visible = False
            node.unfolded = False

        self.selected_node = None
        self.set_origin(0.0, 0.0)

    def _regenerate_canvas(self):
        dpg.delete_item(f"{self.tag}_canvas_root", children_only=True)

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
                if child_node.visible:
                    self._draw_edge(node, child_node)

        if selected:
            self._select_node(selected)

    def _show_node_path(self, path: list[Node]) -> None:
        self._clear_canvas()
        self._clear_attributes()

        if not path:
            return
        
        for node in path:
            self._unfold_node(node)

        self._select_node(path[-1])

    def _isolate_branch(self, node: Node) -> None:
        # Remove all nodes that don't need to be visible anymore. This is more complicated as it
        # seems, as we need to keep the branch unfolded by the user as it is
        root = next(
            r for r in self.selected_roots if nx.has_path(self.graph, r, node.id)
        )
        branch = [node.id]

        while True:
            if branch[-1] == root:
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

    def _select_node(self, node: Node):
        single_branch_mode = dpg.get_value(f"{self.tag}_settings_single_branch_mode")

        if single_branch_mode:
            if self.selected_node and node != self.selected_node:
                self.set_highlight(self.selected_node, False)
                self._isolate_branch(node)
        else:
            if node == self.selected_node:
                self._deselect_active_node()
                return
            else:
                if self.selected_node:
                    self.set_highlight(self.selected_node, False)
                self._unfold_node(node)

        # Update the attributes panel
        self._clear_attributes()
        self._update_attributes(node)

        self.selected_node = node
        self._unfold_node(node)
        self.set_highlight(node, True)
        self.on_node_selected(node)

    def _deselect_active_node(self):
        if self.selected_node is None:
            return

        self.set_highlight(self.selected_node, False)
        self._clear_attributes()
        self._fold_node(self.selected_node)
        self.selected_node = None

    def set_highlight(self, node: Node, highlighted: bool) -> None:
        color = style.blue if highlighted else style.white
        dpg.configure_item(f"{self.tag}_node_{node.id}_box", color=color)

    def _open_node_menu(self, node: Node) -> None:
        def on_item_selected(sender, app_data, selected_item: str):
            dpg.set_value(sender, False)
            dpg.delete_item(f"{self.tag}_{node.id}_menu")
            self.on_node_menu_item_selected(node, selected_item)

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text(node.id, color=style.blue)
            dpg.add_separator()

            for item in self.get_node_menu_items(node):
                if item == "-":
                    dpg.add_separator()
                else:
                    dpg.add_selectable(
                        label=item, callback=on_item_selected, user_data=item
                    )

    def _open_canvas_menu(self) -> None:
        def on_item_select(sender, app_data, selected_item: str):
            dpg.set_value(sender, False)
            self.on_canvas_menu_item_selected(selected_item)

        with dpg.window(
            popup=True, min_size=(100, 20), on_close=lambda: dpg.delete_item(wnd)
        ) as wnd:
            for item in self.get_canvas_menu_items():
                dpg.add_selectable(label=item, callback=on_item_select, user_data=item)

    def _unfold_node(self, node: Node) -> None:
        self._draw_node(node)

        for child_id in self.graph.successors(node.id):
            child_node = self.nodes[child_id]
            self._draw_node(child_node)
            self._draw_edge(node, child_node)

        node.unfolded = True

    # TODO not used at the moment, layout is not clean
    def _unfold_all(self, node: Node) -> None:
        for succ_id in nx.descendants(self.graph, node.id):
            succ = self.nodes[succ_id]
            succ.visible = True
            succ.unfolded = True

        self._regenerate_canvas()

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

    def _get_pos_for_node(self, node: Node) -> tuple[float, float]:
        level = node.layout_data["level"]

        if level == 0:
            px, py = self.layout.node0_margin
        else:
            px = py = 0.0

            for n in self.nodes.values():
                if n.visible:
                    nl = n.layout_data["level"]

                    if nl == level:
                        # Move down
                        py = max(py, n.y + n.height)

                    elif nl == (level - 1):
                        # Move to the right
                        px = max(px, n.x + n.width)

            px += self.layout.gap_x * self.zoom

            if py > 0.0:
                py += self.layout.step_y * self.zoom
            else:
                parent_id = next(
                    n for n in self.graph.predecessors(node.id) if self.nodes[n].visible
                )
                py = self.nodes[parent_id].y

        return px, py

    def _draw_node(self, node: Node) -> None:
        tag = f"{self.tag}_node_{node.id}"

        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            return

        zoom_factor = self.layout.zoom_factor**self.zoom_level
        w, h = draw_graph_node(
            self.get_node_frontpage(node.id),
            margin=self.layout.text_margin,
            scale=zoom_factor,
            tag=tag,
            parent=f"{self.tag}_canvas_root",
        )

        node.size = (w, h)
        node.pos = self._get_pos_for_node(node)
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

        # Manhatten line
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
            parent=f"{self.tag}_canvas_root",
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

    def _update_roots(self) -> None:
        dpg.delete_item(self.roots_table, children_only=True, slot=1)

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(self.roots_table, slot=0):
            dpg.show_item(col)

        root_ids = self.get_root_ids()
        for root_id in root_ids:
            label = self.get_node_frontpage_short(root_id)
            with dpg.table_row(filter_key=label, parent=self.roots_table):
                dpg.add_selectable(
                    label=label,
                    user_data=root_id,
                    callback=self._on_root_selected,
                    tag=f"{self.tag}_root_{root_id}_selectable",
                )

    def _clear_attributes(self) -> None:
        dpg.set_value(f"{self.tag}_attributes_title", "Attributes")
        dpg.delete_item(self.attributes_table, children_only=True, slot=1)

    def _update_attributes(self, node: Node) -> None:
        if node is None:
            return

        dpg.set_value(f"{self.tag}_attributes_title", node.id)

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(self.attributes_table, slot=0):
            dpg.show_item(col)

        for key, val in self.get_node_attributes(node).items():
            with dpg.table_row(
                filter_key=key,
                parent=self.attributes_table,
            ):
                self._add_attribute_row_contents(key, val, node)

    def _add_attribute_row_contents(self, key: str, val: Any, node: Node) -> None:
        tag = f"{self.tag}_node_{node.id}_{key}"

        def update_node_attribute(sender: str, new_val: Any, attribute: str):
            self.set_node_attribute(node, attribute, new_val)

        if isinstance(val, str):
            dpg.add_input_text(
                label=key,
                width=-1,
                filter_key=key,
                tag=tag,
                callback=update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, int):
            dpg.add_input_int(
                label=key,
                filter_key=key,
                tag=tag,
                callback=update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, float):
            dpg.add_input_double(
                label=key,
                filter_key=key,
                tag=tag,
                callback=update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, bool):
            dpg.add_checkbox(
                label=key,
                filter_key=key,
                tag=tag,
                callback=update_node_attribute,
                user_data=key,
                default_value=val,
            )
        else:
            dpg.add_button(
                label=key,
                filter_key=key,
                tag=tag,
                callback=lambda: self.logger.error("TODO not supported yet"),
            )

        dpg.add_text(key)


def main():
    dpg.create_context()
    dpg.create_viewport(title="Behditor")

    with dpg.window() as main_window:
        app = GraphEditor("graph_editor")

    dpg.set_primary_window(main_window, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
