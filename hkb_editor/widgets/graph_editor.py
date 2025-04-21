from typing import Any
from dearpygui import dearpygui as dpg


class GraphEditor:
    def __init__(self, tag: str | int = 0):
        super().__init__()

        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        self.tag = tag
        self.active_node = None

        with dpg.menu_bar():
            self.create_menu()

        with dpg.group(horizontal=True):
            self._setup_content()

    def get_node_attributes(self, node_id: str | int):
        return {}
    
    def get_node_frontpage(self, node_id: str | int):
        return [f"<{node_id}>"]
    
    def get_node_children(self, node_id: str | int):
        return []

    def on_node_clicked(self, node_id: str | int):
        pass

    def on_node_created(self, node_id: str | int):
        pass

    def create_menu(self):
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open...", callback=self.open_file)
            dpg.add_menu_item(
                label="Save...", callback=self.save_file, enabled=False, tag="menu_file_save"
            )

    def open_file(self):
        pass

    def save_file(self):
        pass

    def _setup_content(self):
        # Roots
        with dpg.child_window():
            dpg.add_input_text(tag=f"{self.tag}_roots_filter")
            dpg.add_group(tag=f"{self.tag}_roots_pinned")
            dpg.add_listbox(
                [], tag=f"{self.tag}_roots_list", callback=self._on_root_selected, user_data=beh
            )

        # Canvas
        # TODO use set_item_height/width to resize dynamically
        dpg.add_drawlist(800, 800, tag=f"{self.tag}_canvas")

        # Attributes panel
        with dpg.child_window():
            dpg.add_input_text(hint="Filter", callback=update_attr_filter)
            with dpg.child_window():
                dpg.add_filter_set(tag=f"{self.tag}_attributes")

        # Callbacks
        def update_attr_filter(sender, filter_string):
            dpg.set_value(f"{self.tag}_attribute_filter", filter_string)

        def on_node_click():
            if dpg.is_item_hovered("canvas"):
                for node in dpg.get_item_children("canvas", slot=1):
                    if dpg.is_item_hovered(node):
                        node_id = dpg.get_item_alias(node)
                        self._activate_node(node_id)

        # TODO pan and zoom
        def on_mouse_drag():
            pass

        def on_mouse_wheel():
            pass

        with dpg.handler_registry():
            dpg.add_mouse_click_handler(callback=on_node_click)
            dpg.add_mouse_drag_handler(callback=on_mouse_drag)
            dpg.add_mouse_wheel_handler(callback=on_mouse_wheel)

    def _on_root_selected(self, sender: int | str, node_id: str):
        self._clear_canvas()
        self._add_node(node_id, (50, 50))  # TODO initial pos

    def _clear_canvas(self):
        dpg.delete_item(f"{self.tag}_canvas", children_only=True)

    def _activate_node(self, node_id: str):
        self.on_node_clicked(node_id)

        if self.active_node == node_id:
            return
        
        self._deactivate_node(self.active_node)
        
        # Update the attributes panel
        self._clear_attributes()
        for key, val in self.get_node_attributes():
            self._add_attribute(key, val, node_id)

        # Expand the node by showing its immediate children
        ppos = dpg.get_item_pos(node_id)
        prect = dpg.get_item_rect_size(node_id)
        gap_x = 50
        step_y = 35

        children = self.get_node_children(node_id)

        p_center_y = ppos[1] + prect [1] / 2
        child_x0 = ppos[0] + prect[0] + gap_x
        child_y0 = p_center_y - step_y * len(children) / 2

        for i, child in enumerate():
            cx = child_x0
            cy = child_y0 + step_y * i
            self._add_node(child, (cx, cy))
            
            parent_connect = (ppos[0] + prect[0], p_center_y)
            child_connect = (child_x0, cy - step_y / 2)
            self._add_relation(parent_connect, child_connect)

        self.active_node = node_id

    def _deactivate_node(self, node_id: str):
        if node_id in (0, None, ""):
            return
        
        children = self.get_node_children(node_id)
        for child in children:
            self._delete_node(child)

    def _add_node(self, node_id: str, pos: tuple[int, int]):
        px, py = pos
        margin = 5
        text_h = 10

        lines = self.get_node_frontpage(node_id)
        max_len = max(len(s) for s in lines)
        lines = [s.center(max_len) for s in lines]

        w = max_len * 1.5 + margin * 2
        h = text_h * len(lines) + margin * 2

        with dpg.draw_node(tag=node_id):
            # Background
            dpg.draw_rectangle(
                (px, py), (px + w, py + h), fill=(62, 62, 62, 255), tag=f"{node_id}_bg"
            )

            # Border
            dpg.draw_rectangle(
                (px, py),
                (px + w - 2, py + h - 2),
                color=(255, 255, 255, 255),
                thickness=2,
                tag=f"{node_id}_border",
            )

            # Text
            # TODO font and styling
            for i, text in enumerate(lines):
                dpg.draw_text((px + margin, py + margin + text_h * i), text)

        self.on_node_created(node_id)

        return (w, h)

    def _add_relation(self, p0: tuple[float, float], p1: tuple[float, float]):
        # Manhatten line
        mid_x = (p1[0] - p0[0]) / 2
        dpg.draw_polygon([
            p0,
            (mid_x, p0[1]),
            (mid_x, p1[1]),
            p1,
        ])

    def _delete_node(self, node_id: str | int):
        for child in self.get_node_children(node_id):
            self._delete_node(child)
        dpg.delete_item(node_id)

    def _clear_attributes(self):
        dpg.delete_item(f"{self.tag}_attributes", children_only=True)

    def _add_attribute(self, key: str, val: Any, node_id: str | int):
        # TODO
        tag = f"{node_id}_{key}"

        if isinstance(val, str):
            dpg.add_input_text(
                label=key,
                filter_key=key,
                tag=tag,
                callback=self._update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, int):
            dpg.add_input_int(
                label=key,
                filter_key=key,
                tag=tag,
                callback=self._update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, float):
            dpg.add_input_double(
                label=key,
                filter_key=key,
                tag=tag,
                callback=self._update_node_attribute,
                user_data=key,
                default_value=val,
            )
        elif isinstance(val, bool):
            dpg.add_checkbox(
                label=key,
                filter_key=key,
                tag=tag,
                callback=self._update_node_attribute,
                user_data=key,
                default_value=val,
            )
        else:
            dpg.add_button(
                label=key,
                filter_key=key,
                tag=tag,
                callback=lambda: show_attr_editor(key, val, node_id),
            )

    def _update_node_attribute(self, sender: str | int, new_val: Any, attribute: str):
        # TODO
        pass




def main():
    dpg.create_context()
    dpg.create_viewport(title="Behditor")

    with dpg.window() as main_window:
        setup_gui()

    dpg.set_primary_window(main_window, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
