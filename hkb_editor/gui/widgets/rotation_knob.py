from typing import Callable, Any
import math
import dearpygui.dearpygui as dpg


def add_rotation_knob(
    *,
    size: int = 60,
    default_value: float = 0.0,  # degrees, 0–360
    tag: str = None,
    parent: str = None,
    source: str = None,
    show_value: bool = False,
    ring_color: list = (200, 200, 200, 255),
    ring_thickness: int = 2,
    indicator_color: list = (255, 0, 0, 255),
    indicator_thickness: int = 3,
    on_change: Callable[[str, float, Any], None] = None,
    window_on_close_cleanup: bool = True,
) -> str:
    """Adds a full-circle rotation knob into an existing window/container.
    Returns the knob's group tag. The value will be stored in {tag}_rotation.
    """
    if not tag:
        tag = f"rotation_knob_{dpg.generate_uuid()}"

    if not parent:
        parent = dpg.last_container()

    W = H = float(size)
    cx, cy = W * 0.5, H * 0.5
    radius = W * 0.40
    indicator_len = radius * 0.84

    # state
    default_value = float(default_value % 360)
    if not source:
        source = f"{tag}_rotation"
        with dpg.value_registry():
            dpg.add_float_value(tag=source, default_value=default_value)

    def angle_from_mouse() -> float:
        x, y = dpg.get_drawing_mouse_pos()
        dx = x - cx
        dy = y - cy
        return math.degrees(math.atan2(dy, dx)) % 360.0

    def update_needle() -> None:
        dpg.delete_item(f"{tag}_needle")
        rotation = dpg.get_value(source)
        px = cx + indicator_len * math.cos(math.radians(rotation))
        py = cy + indicator_len * math.sin(math.radians(rotation))
        dpg.draw_line(
            (cx, cy),
            (px, py),
            color=indicator_color,
            thickness=indicator_thickness,
            parent=f"{tag}_knob",
            tag=f"{tag}_needle",
        )
        if show_value:
            dpg.configure_item(f"{tag}_text", default_value=f"{int(rotation)%360}°")

    def drag_cb(sender: int, app_data: Any, user_data: Any) -> None:
        if not dpg.is_item_hovered(f"{tag}_knob"):
            return

        rotation = dpg.get_value(source)
        new_angle = angle_from_mouse()
        if new_angle != rotation:
            dpg.set_value(source, new_angle)
            update_needle()

            if on_change:
                on_change(rotation)

    def click_cb(sender: int, app_data: Any, user_data: Any) -> None:
        if dpg.is_item_hovered(f"{tag}_knob"):
            rotation = angle_from_mouse()
            dpg.set_value(source, rotation)
            update_needle()

            if on_change:
                on_change(rotation)

    with dpg.group(tag=tag, parent=parent):
        if show_value:
            dpg.add_text(f"{int(default_value)%360}°", tag=f"{tag}_text")

        with dpg.drawlist(width=int(W), height=int(H), tag=f"{tag}_knob"):
            dpg.draw_circle(
                (cx, cy), radius, color=ring_color, thickness=ring_thickness
            )
            px = cx + indicator_len * math.cos(math.radians(default_value))
            py = cy + indicator_len * math.sin(math.radians(default_value))
            dpg.draw_line(
                (cx, cy),
                (px, py),
                color=indicator_color,
                thickness=indicator_thickness,
                tag=f"{tag}_needle",
            )

    handler_tag = f"{tag}_handlers"
    with dpg.handler_registry(tag=handler_tag):
        dpg.add_mouse_drag_handler(callback=drag_cb)
        dpg.add_mouse_click_handler(callback=click_cb)

    if window_on_close_cleanup:

        def _on_close() -> None:
            if dpg.does_item_exist(handler_tag):
                dpg.delete_item(handler_tag)

        win = parent
        while win and dpg.get_item_type(win) != "mvAppItemType::Window":
            win = dpg.get_item_parent(win)

        if win:
            dpg.configure_item(win, on_close=_on_close)

    return tag
