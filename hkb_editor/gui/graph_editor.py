from typing import Any
from os import path
from logging import getLogger
from dataclasses import dataclass
from dearpygui import dearpygui as dpg
import networkx as nx
import tkinter as tk
from tkinter import filedialog


def open_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: list[tuple[str, str]] = None,
) -> str:
    if not title:
        title = "Select file to load"

    # dpg file dialog sucks, so we use the tk one instead
    root = tk.Tk()
    root.withdraw()

    ret = filedialog.askopenfilename(
        title=title,
        filetypes=filetypes,
        initialdir=default_dir,
        initialfile=default_file,
    )

    root.destroy()
    return ret


def save_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: list[tuple[str, str]] = None,
) -> str:
    if not title:
        title = "Select file to load"

    # dpg file dialog sucks, so we use the tk one instead
    root = tk.Tk()
    root.withdraw()

    ret = filedialog.asksaveasfilename(
        title=title,
        filetypes=filetypes,
        initialdir=default_dir,
        initialfile=default_file,
    )

    root.destroy()
    return ret


@dataclass
class Layout:
    gap_x: int = 20
    step_y: int = 20
    node0_margin: tuple[int, int] = (50, 50)
    text_margin: int = 5
    zoom_factor: float = 2.0


@dataclass
class Node:
    id: str
    parent: str
    level: int
    pos: tuple[float, float]
    size: tuple[float, float]
    folded: bool = True

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
        self.loaded_file: str = None
        self.graph: nx.DiGraph = None
        self.layout = Layout()
        self.visible_nodes: dict[int, Node] = {}
        self.root: Node = None
        self.selected_node: Node = None
        self.origin: tuple[float, float] = (0.0, 0.0)
        self.dragging = False
        self.last_drag: tuple[float, float] = (0.0, 0.0)
        self.zoom = 0
        self.zoom_min = -3
        self.zoom_max = 3

        self._setup_content()

    # These should be implemented by subclasses
    def get_supported_file_extensions(self) -> list[tuple[str, str]]:
        return []

    def get_roots(self) -> list[Node]:
        return []

    def make_node(self, node_id) -> None:
        pass

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        return {}

    def set_node_attribute(self, node: Node, key: str, val: Any) -> None:
        pass

    def get_node_frontpage(self, node_id: str) -> list[str]:
        return [f"<{node_id}>"]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return node_id

    def get_node_menu_items(self, node: Node) -> list[str]:
        return []

    def on_node_menu_item_selected(node: Node, selected_item: str) -> None:
        pass

    def on_node_selected(self, node: Node) -> None:
        pass

    def create_menu(self):
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open...", callback=self.open_file)
            dpg.add_menu_item(
                label="Save...",
                callback=self.save_file,
                enabled=False,
                tag="menu_file_save",
            )
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self.exit_app)

    def open_file(self):
        ret = open_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self.logger.info("Loading file %s", ret)
            self._do_load_from_file(ret)
            self.loaded_file = ret
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

        self._on_root_selected("", "", "A")

    def save_file(self):
        ret = save_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            default_file=path.basename(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self._do_write_to_file(ret)
            self.loaded_file = ret

    def _do_write_to_file(self, file_path: str) -> None:
        pass

    def exit_app(self):
        dpg.stop_dearpygui()

    def _setup_content(self):
        with dpg.menu_bar():
            self.create_menu()

        with dpg.group(horizontal=True):
            # Roots
            with dpg.child_window(
                resizable_x=True,
                auto_resize_x=True,
                tag=f"{self.tag}_roots_window",
            ):
                dpg.add_input_text(
                    hint="Filter Roots",
                    tag=f"{self.tag}_roots_filter",
                    callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                    user_data=f"{self.tag}_roots_table",
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
                ):
                    dpg.add_table_column(label="Name")

            # Canvas
            with dpg.child_window(
                auto_resize_x=True,
                auto_resize_y=True,
                no_scrollbar=True,
                tag=f"{self.tag}_canvas_window",
            ):
                with dpg.drawlist(800, 800, tag=f"{self.tag}_canvas"):
                    dpg.add_draw_node(tag=f"{self.tag}_canvas_root")

            # Attributes panel
            with dpg.child_window(
                resizable_x=True,
                auto_resize_x=True,
                tag=f"{self.tag}_attributes_window",
            ):
                dpg.add_input_text(
                    hint="Filter Attributes",
                    tag=f"{self.tag}_attribute_filter",
                    callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                    user_data=f"{self.tag}_attributes_table",
                )
                dpg.add_separator()

                dpg.add_text("", tag=f"{self.tag}_attributes_title")
                with dpg.table(
                    delay_search=True,
                    #no_host_extendX=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    header_row=False,
                    scrollY=True,
                    tag=f"{self.tag}_attributes_table",
                ):
                    dpg.add_table_column(label="Value", width_stretch=True)
                    dpg.add_table_column(label="Key")

            with dpg.handler_registry():
                dpg.add_mouse_click_handler(callback=self._on_mouse_click)
                dpg.add_mouse_down_handler(
                    dpg.mvMouseButton_Left, callback=self._on_mouse_down
                )
                dpg.add_mouse_release_handler(
                    dpg.mvMouseButton_Left, callback=self._on_mouse_release
                )
                dpg.add_mouse_drag_handler(callback=self._on_mouse_drag)
                dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)

            dpg.set_viewport_resize_callback(self._on_resize)
            self._on_resize()

    # Callbacks
    def _on_mouse_click(self, sender, button: int) -> None:
        # TODO move into mouse_up
        if self.dragging:
            return

        if not dpg.is_item_hovered(f"{self.tag}_canvas"):
            return

        mx, my = dpg.get_drawing_mouse_pos()
        ox, oy = self.origin

        for node in self.visible_nodes.values():
            if node.contains(mx - ox, my - oy):
                if button == dpg.mvMouseButton_Left:
                    if self.selected_node != node:
                        self._select_node(node)

                elif button == dpg.mvMouseButton_Right:
                    self._open_node_menu(node)

                break
        else:
            if button == dpg.mvMouseButton_Left:
                self._deselect_active_node()
            elif button == dpg.mvMouseButton_Right:
                self._open_canvas_menu()
            elif button == dpg.mvMouseButton_Middle:
                self.set_origin(0.0, 0.0)

    def _on_mouse_down(self) -> None:
        if dpg.is_item_hovered(f"{self.tag}_canvas"):
            self.dragging = True

    def _on_mouse_drag(self, sender, mouse_delta: list[float]) -> None:
        if not self.dragging:
            return

        _, delta_x, delta_y = mouse_delta
        self.last_drag = (delta_x, delta_y)
        self.look_at(self.origin[0] + delta_x, self.origin[1] + delta_y)

    def _on_mouse_release(self) -> None:
        if self.dragging:
            self.set_origin(
                self.origin[0] + self.last_drag[0], self.origin[1] + self.last_drag[1]
            )
            self.last_drag = (0.0, 0.0)
            self.dragging = False

    def _on_mouse_wheel(self, sender, wheel_delta: int):
        if not dpg.is_item_hovered(f"{self.tag}_canvas"):
            return

        zoom_point = dpg.get_drawing_mouse_pos()
        self.origin = (self.origin[0] + zoom_point[0], self.origin[1] + zoom_point[1])
        self.zoom = min(max(self.zoom - wheel_delta, self.zoom_min), self.zoom_max)

        visible = list(self.visible_nodes.values())
        self._clear_canvas()

        for node in visible:
            self._create_node(node.id, node.parent, node.level)

    def _on_resize(self):
        dpg.set_item_height(f"{self.tag}_canvas", dpg.get_viewport_height() - 50)

        w = dpg.get_viewport_width() - 270
        dpg.set_item_width(f"{self.tag}_roots_window", 200)
        dpg.set_item_width(f"{self.tag}_canvas", int(w * 0.8))
        dpg.set_item_width(f"{self.tag}_attributes_table", int(w * 0.2))

    def set_origin(self, new_x: float, new_y: float) -> None:
        self.origin = (new_x, new_y)
        self.look_at(*self.origin)

    def look_at(self, px: float, py: float) -> None:
        dpg.apply_transform(
            f"{self.tag}_canvas_root",
            dpg.create_translation_matrix((px, py)),
        )

    def _on_root_selected(self, sender: str, app_data: str, node_id: str):
        if self.root and node_id == self.root.id:
            # Prevent deselecting a root
            dpg.set_value(f"{self.tag}_{node_id}_selectable", True)
            return

        for root in self.get_roots():
            tag = f"{self.tag}_{root.id}_selectable"
            if root.id != node_id and dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

        self._clear_canvas()
        self.root = self._create_node(node_id, None, 0)

    def _clear_canvas(self):
        dpg.delete_item(f"{self.tag}_canvas_root", children_only=True)
        self.visible_nodes.clear()
        self.selected_node = None
        self.root = None
        self.set_origin(0.0, 0.0)

    def _isolate(self, node: Node):
        dpg.delete_item(f"{self.tag}_canvas_root", children_only=True)
        self.visible_nodes.clear()

        required_visible = nx.shortest_path(self.graph, self.root.id, node.id)
        parent_id = None
        for level, node_id in enumerate(required_visible):
            node = self._create_node(node_id, parent_id, level)
            self._unfold_node(node)
            parent_id = node.id

    def _select_node(self, node: Node):
        self._deselect_active_node()
        self._isolate(node)

        # Update the attributes panel
        self._clear_attributes()
        self._update_attributes(node)

        self.set_highlight(node, True)
        self.selected_node = node
        self.on_node_selected(node)

    def _deselect_active_node(self):
        if self.selected_node is None:
            return

        self.set_highlight(self.selected_node, False)
        # self._fold_node(self.selected_node)
        self._clear_attributes()

        self.selected_node = None

    def set_highlight(self, node: Node, highlighted: bool) -> None:
        color = (255, 0, 0, 255) if highlighted else (255, 255, 255, 255)
        dpg.configure_item(f"{node.id}_box", color=color)

    def _open_node_menu(self, node: Node) -> None:
        def on_item_select(sender, app_data, selected_item: str):
            dpg.delete_item(f"{node.id}_menu")
            self.on_node_menu_item_selected(node, selected_item)

        with dpg.window(
            popup=True,
            tag=f"{node.id}_menu",
            on_close=lambda: dpg.delete_item(f"{node.id}_menu"),
        ):
            dpg.add_text(node.id)
            dpg.add_separator()

            for item in self.get_node_menu_items(node):
                dpg.add_selectable(label=item, callback=on_item_select, user_data=item)

    def _unfold_node(self, node: Node) -> None:
        if not dpg.does_item_exist(node.id):
            raise KeyError(f"Tried to unfold non-existing node {node.id}")

        for child_id in self.graph.successors(node.id):
            child_node = self._create_node(child_id, node.id, node.level + 1)
            self._create_relation(node, child_node)

        node.folded = False

    def _fold_node(self, node: Node) -> None:
        for child_id in self.graph.successors(node.id):
            child_node = self.visible_nodes.get(child_id, None)
            # TODO can there be multiple parents? If so, check if there's another parent visible
            self._delete_node(child_node)

        node.folded = True

    def _create_node(self, node_id: str, parent_id: str, level: int) -> Node:
        if node_id in self.visible_nodes:
            return self.visible_nodes[node_id]

        if level == 0:
            px = self.layout.node0_margin[0]
        else:
            px = (
                max(
                    n.x + n.width
                    for n in self.visible_nodes.values()
                    if n.level == level - 1
                )
                + self.layout.gap_x
            )

        try:
            py = (
                max(
                    n.y + n.height
                    for n in self.visible_nodes.values()
                    if n.level == level
                )
                + self.layout.step_y
            )
        except ValueError:
            if parent_id:
                py = self.visible_nodes[parent_id].y
            else:
                py = self.layout.node0_margin[1]

        margin = self.layout.text_margin
        lines = self.get_node_frontpage(node_id)
        max_len = max(len(s) for s in lines)
        lines = [s.center(max_len) for s in lines]

        text_h = 12
        w = max_len * 6.5 + margin * 2
        h = text_h * len(lines) + margin * 2

        zoom_factor = self.layout.zoom_factor**self.zoom
        # px *= zoom_factor
        # py *= zoom_factor
        w *= zoom_factor
        h *= zoom_factor
        text_offset_y = text_h * zoom_factor

        with dpg.draw_node(tag=node_id, parent=f"{self.tag}_canvas_root"):
            # Background
            dpg.draw_rectangle(
                (px, py),
                (px + w, py + h),
                fill=(62, 62, 62, 255),
                color=(255, 255, 255, 255),
                thickness=1,
                tag=f"{node_id}_box",
            )

            # Text
            # TODO font and styling
            for i, text in enumerate(lines):
                dpg.draw_text(
                    (px + margin, py + margin + text_offset_y * i),
                    text,
                    size=12 * zoom_factor,
                )

        node = Node(node_id, parent_id, level, (px, py), (w, h))
        self.visible_nodes[node_id] = node
        return node

    def _create_relation(self, node_a: Node, node_b: Node) -> None:
        tag = f"{node_a.id}_TO_{node_b.id}"
        if dpg.does_item_exist(tag):
            return

        ax = node_a.x + node_a.width
        ay = node_a.y + node_a.height / 2
        bx = node_b.x
        by = node_b.y + node_b.height / 2

        # Manhatten line
        mid_x = ax + (bx - ax) / 2
        dpg.draw_polygon(
            [
                (ax, ay),
                (mid_x, ay),
                (mid_x, by),
                (bx, by),
            ],
            tag=tag,
            parent=node_a.id,
        )

    def _delete_node(self, node: Node) -> None:
        if not node:
            return

        for child_id in self.graph.successors(node.id):
            child_node = self.visible_nodes.get(child_id, None)
            self._delete_node(child_node)

        dpg.delete_item(node.id)
        del self.visible_nodes[node.id]

        # Delete relations
        for parent_id in self.graph.predecessors(node.id):
            if dpg.does_item_exist(f"{parent_id}_TO_{node.id}"):
                dpg.delete_item(f"{parent_id}_TO_{node.id}")

    def _update_roots(self) -> None:
        dpg.delete_item(f"{self.tag}_roots_table", children_only=True, slot=1)

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(f"{self.tag}_roots_table", slot=0):
            dpg.show_item(col)

        roots = self.get_roots()
        for root in roots:
            label = self.get_node_frontpage_short(root.id)
            with dpg.table_row(filter_key=label, parent=f"{self.tag}_roots_table"):
                dpg.add_selectable(
                    label=label,
                    user_data=root.id,
                    callback=self._on_root_selected,
                    tag=f"{self.tag}_{root.id}_selectable",
                )

    def _clear_attributes(self) -> None:
        dpg.set_value(f"{self.tag}_attributes_title", "Attributes")
        dpg.delete_item(f"{self.tag}_attributes_table", children_only=True, slot=1)

    def _update_attributes(self, node: Node) -> None:
        dpg.set_value(f"{self.tag}_attributes_title", node.id)

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(f"{self.tag}_attributes_table", slot=0):
            dpg.show_item(col)

        for key, val in self.get_node_attributes(node).items():
            with dpg.table_row(
                filter_key=key,
                parent=f"{self.tag}_attributes_table",
            ):
                self._add_attribute(key, val, node)
                # Could show the value type, too
                dpg.add_text(key)

    def _add_attribute(self, key: str, val: Any, node: Node) -> None:
        tag = f"{node.id}_{key}"

        def update_node_attribute(sender: str, new_val: Any, attribute: str):
            self.set_node_attribute(node, attribute, new_val)

        if isinstance(val, str):
            dpg.add_input_text(
                label=key,
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
            # TODO
            dpg.add_button(
                label=key,
                filter_key=key,
                tag=tag,
                callback=lambda: print("TODO not supported yet"),
            )


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
