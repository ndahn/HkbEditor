from typing import Any
import sys
from os import path
import shutil
from time import time
from logging import getLogger
from dearpygui import dearpygui as dpg
import networkx as nx

from .graph_widget import GraphWidget, GraphLayout, Node
from .dialogs import open_file_dialog, save_file_dialog
from .helpers import center_window
from . import style


def get_default_layout_path():
    return path.join(path.dirname(sys.argv[0]), "default_layout.ini")


def get_custom_layout_path():
    return path.join(path.dirname(sys.argv[0]), "user_layout.ini")


class GraphEditor:
    def __init__(self, tag: str = 0):
        super().__init__()

        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        self.logger = getLogger(self.__class__.__name__)
        self.tag: str = tag
        self.roots_table: str = None
        self.canvas: GraphWidget = None
        self.attributes_table: str = None
        self.loaded_file: str = None
        self.last_save: float = 0.0
        self.selected_roots: set[str] = set()
        self.selected_node: Node = None

        self._setup_content()

    # These should be implemented by subclasses
    def get_supported_file_extensions(self) -> dict[str, str]:
        return {"All files": "*.*"}

    def get_root_ids(self) -> list[str]:
        return []

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        return {}

    def set_node_attribute(self, node: Node, key: str, val: Any) -> None:
        pass

    def get_node_frontpage(
        self, node: Node
    ) -> list[str] | list[tuple[str, tuple[int, int, int, int]]]:
        return [f"<{node.id}>"]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return node_id

    def on_node_selected(self, node: Node) -> None:
        self.selected_node = node

        # Update the attributes panel
        self.clear_attributes()
        if node:
            self._update_attributes(node)

    def create_app_menu(self):
        self._create_file_menu()
        dpg.add_separator()
        self._create_dpg_menu()

    def _save_app_layout(self):
        dpg.save_init_file(get_custom_layout_path())
        self.logger.info("Saved custom layout")

    def _restore_default_app_layout(self):
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
                label="Save layout as default", callback=self._save_app_layout
            )
            dpg.add_menu_item(
                label="Restore factory layout",
                callback=self._restore_default_app_layout,
            )

            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self.exit_app)

    def _create_dpg_menu(self):
        with dpg.menu(label="Help"):
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

            dpg.add_separator()
            dpg.add_menu_item(
                label="HkbEditor",
                callback=self.open_about_dialog,
            )

    def open_node_menu(self, node: Node) -> None:
        pass

    def file_open(self):
        ret = open_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self.logger.debug("======================================")
            self.logger.info("Loading file %s", ret)
            self._do_load_from_file(ret)
            self.loaded_file = ret
            self.last_save = 0.0
            self.canvas.clear()
            self._update_roots()

    def _do_load_from_file(self, file_path: str) -> None:
        # Just some test data
        g = nx.DiGraph()

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

    def file_save_as(self) -> bool:
        ret = save_file_dialog(
            default_dir=path.dirname(self.loaded_file or ""),
            default_file=path.basename(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self._do_write_to_file(ret)
            self.loaded_file = ret
            self.last_save = time()
            return True

        return False

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
                callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                user_data=f"{self.tag}_roots_table",
                tag=f"{self.tag}_roots_filter",
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
            self.canvas = GraphWidget(
                None,
                GraphLayout(),
                on_node_selected=self.on_node_selected,
                node_menu_func=self.open_node_menu,
                get_node_frontpage=self.get_node_frontpage,
                single_branch_mode=True,
                tag=f"{self.tag}_canvas",
            )

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
            with dpg.child_window(border=False, tag=f"{self.tag}_attributes_table_container"):
                dpg.add_text("", tag=f"{self.tag}_attributes_title", color=style.blue)
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

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_frame_callback(2, self._on_resize)

    def _on_resize(self):
        cw, ch = dpg.get_item_rect_size(f"{self.tag}_canvas_window")
        dpg.set_item_width(self.canvas.tag, cw)
        dpg.set_item_height(self.canvas.tag, ch)

    def get_graph(self, root_id: str) -> nx.DiGraph:
        return nx.DiGraph()

    def _on_root_selected(self, sender: str, selected: bool, root_id: str):
        # NOTE for now we don't allow deselecting SMs
        selected = True
        dpg.set_value(f"{self.tag}_root_{root_id}_selectable", True)

        # Rebuild the graph even if the root_id is already selected
        self.canvas.clear()
        self.clear_attributes()
        self.selected_node = None

        # For now we only allow one root to be selected
        for other in self.get_root_ids():
            self.selected_roots.discard(other)
            tag = f"{self.tag}_root_{other}_selectable"
            if other != root_id and dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

        if selected:
            self.selected_roots.add(root_id)
            graph: nx.DiGraph = self.get_graph(root_id)
            self.canvas.set_graph(graph)
        else:
            if root_id in self.selected_roots:
                self.selected_roots.remove(root_id)
            self.canvas.set_graph(None)

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

    def clear_attributes(self) -> None:
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

    def open_about_dialog(self) -> None:
        tag = f"{self.tag}_about_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        rainbow = style.HighContrastColorGenerator()
        rainbow.hue = 0.6
        rainbow.hue_step = -0.05

        with dpg.window(
            width=300,
            height=150,
            label="About",
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(dialog),
            tag=tag,
        ) as dialog:
            from hkb_editor import __version__
            dpg.add_text(f"HkbEditor v{__version__}", color=rainbow())
            
            dpg.add_separator()
            
            dpg.add_text("Written by Nikolas Dahn", color=rainbow())
            dpg.add_button(label="https://github.com/ndahn/HkbEditor", small=True)
            dpg.bind_item_theme(dpg.last_item(), style.link_button_theme)
            
            dpg.add_separator()

            dpg.add_text("Bugs, questions, feature request?", color=rainbow())
            dpg.add_text("Find me on ?ServerName? @Managarm!", color=rainbow())

        dpg.split_frame()
        center_window(dialog)


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
