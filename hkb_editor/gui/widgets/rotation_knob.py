from typing import Callable, Any
import math
import dearpygui.dearpygui as dpg


class RotationKnob:
    def __init__(
        self,
        *,
        default_value: float = 0.0,  # degrees, 0–360
        label: str | None = None,
        size: int = 60,
        show_value: bool = True,
        ring_color: list = (200, 200, 200, 255),
        ring_thickness: int = 2,
        indicator_color: list = (255, 0, 0, 255),
        indicator_thickness: int = 3,
        callback: Callable[[str, float, Any], None] | None = None,
        tag: str | None = None,
        parent: str | int = 0,
        user_data: Any = None,
    ) -> None:
        """Create a full-circle rotation knob. Builds immediately."""
        self.tag = tag or f"rotation_knob_{dpg.generate_uuid()}"
        self.size = size
        self.label = label
        self.ring_color = ring_color
        self.indicator_color = indicator_color
        self.indicator_thickness = indicator_thickness
        self.callback = callback
        self.user_data = user_data

        self._drag_active: bool = False
        self._value_deg = float(default_value % 360.0)

        # build UI
        W = H = float(self.size)
        cx, cy = W * 0.5, H * 0.5
        radius = W * 0.40
        indicator_len = radius * 0.84

        with dpg.group(tag=self.tag, parent=parent):
            if show_value:
                with dpg.tooltip(dpg.last_container()):
                    dpg.add_text(tag=f"{self.tag}_text")

            with dpg.drawlist(width=int(W), height=int(H), tag=f"{self.tag}_knob"):
                dpg.draw_circle(
                    (cx, cy), radius, color=self.ring_color, thickness=ring_thickness
                )

                px = cx + indicator_len * math.cos(math.radians(self._value_deg))
                py = cy + indicator_len * math.sin(math.radians(self._value_deg))
                with dpg.draw_layer(tag=f"{self.tag}_needle_layer"):
                    dpg.draw_line(
                        (cx, cy),
                        (px, py),
                        color=self.indicator_color,
                        thickness=self.indicator_thickness,
                        tag=f"{self.tag}_needle",
                    )

        self._update_label()

        # handlers
        self.handler_tag = f"{self.tag}_handlers"

        if not dpg.does_item_exist(self.handler_tag):
            dpg.add_handler_registry(tag=self.handler_tag)

        dpg.add_mouse_drag_handler(
            callback=self._on_mouse_drag, parent=self.handler_tag
        )
        dpg.add_mouse_down_handler(
            button=dpg.mvMouseButton_Left,
            callback=self._on_mouse_down,
            parent=self.handler_tag,
        )
        dpg.add_mouse_release_handler(
            button=dpg.mvMouseButton_Left,
            callback=self._on_mouse_release,
            parent=self.handler_tag,
        )

    @property
    def degrees(self) -> float:
        return self._value_deg

    @property
    def radians(self) -> float:
        return math.radians(self.degrees)

    def __del__(self):
        if dpg.does_item_exist(self.handler_tag):
            dpg.delete_item(self.handler_tag)

    def set_value_deg(self, new_val: float) -> None:
        self._value_deg = new_val
        self._update_label()
        self._update_needle()

    def set_value_rad(self, new_val: float) -> None:
        self.set_value_deg(math.degrees(new_val))

    def _angle_from_mouse(self) -> float:
        W = H = float(self.size)
        cx, cy = W * 0.5, H * 0.5
        x, y = dpg.get_drawing_mouse_pos()
        return math.degrees(math.atan2(y - cy, x - cx)) % 360.0

    def _update_label(self) -> None:
        tid = f"{self.tag}_text"
        if dpg.does_item_exist(tid):
            txt = f"{self.degrees:.1f}°"
            if self.label:
                txt = f"{self.label}: {txt}"
            dpg.set_value(tid, txt)

    def _update_needle(self) -> None:
        W = H = float(self.size)
        cx, cy = W * 0.5, H * 0.5
        radius = W * 0.40
        indicator_len = radius * 0.84

        dpg.delete_item(f"{self.tag}_needle")
        ang = self.degrees
        px = cx + indicator_len * math.cos(math.radians(ang))
        py = cy + indicator_len * math.sin(math.radians(ang))
        dpg.draw_line(
            (cx, cy),
            (px, py),
            color=self.indicator_color,
            thickness=self.indicator_thickness,
            parent=f"{self.tag}_needle_layer",
            tag=f"{self.tag}_needle",
        )

    def _on_mouse_drag(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not self._drag_active:
            return

        cur = float(self.degrees)
        new_angle = self._angle_from_mouse()

        if new_angle != cur:
            self._value_deg = new_angle
            self._update_label()
            self._update_needle()

            if self.callback:
                self.callback(self.tag, new_angle, self.user_data)

    def _on_mouse_down(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not dpg.does_item_exist(f"{self.tag}_knob"):
            dpg.hide_item(self.handler_tag)
            return

        if dpg.is_item_hovered(f"{self.tag}_knob"):
            self._drag_active = True
            self._on_mouse_drag(sender, app_data, user_data)

    def _on_mouse_release(self, sender: int, app_data: Any, user_data: Any) -> None:
        self._drag_active = False
