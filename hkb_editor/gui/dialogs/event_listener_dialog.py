from typing import Any
import colorsys
from dearpygui import dearpygui as dpg

from hkb_editor.gui import style
from hkb_editor.gui.widgets import DpgItem, add_paragraphs
from hkb_editor.workflows.event_listener import EventListener, DEFAULT_PORT


_instructions = """\
https://ndahn.github.io/HkbEditor/howto/tools/event_listener/
"""


class event_listener_dialog(DpgItem):
    """Live scrolling plot of the behavior events received over UDP.

    Each event gets a lane and a colored label that fades out as it scrolls
    off the left edge. The socket itself lives in
    :class:`hkb_editor.workflows.event_listener.EventListener`.

    Parameters
    ----------
    title : str
        Window title bar label.
    port : int
        UDP port to listen on.
    time_range : int
        Seconds of history visible at once.
    max_events : int
        How many events to retain.
    num_rows : int
        How many lanes events are distributed over.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    """

    def __init__(
        self,
        *,
        title: str = "Event Listener",
        port: int = DEFAULT_PORT,
        time_range: int = 10,
        max_events: int = 100,
        num_rows: int = 10,
        tag: str = 0,
    ) -> None:
        super().__init__(tag)

        self._time_range = time_range
        self._max_events = max_events
        self._num_rows = num_rows
        self._plot_t = 0.0
        self._paused = False
        self._row_assignments: dict[str, int] = {}
        self._window: str = None

        self._listener = EventListener(
            lambda: self._plot_t,
            get_filter=lambda: dpg.get_value(self._t("filter")),
            strip_character=lambda: not dpg.get_value(self._t("show_chr")),
            port=port,
            max_events=max_events,
        )

        self._build(title)
        self._listener.start()

    def destroy(self) -> None:
        # Stops the background thread and closes the socket
        self._listener.stop()

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            min_size=(640, 480),
            label=title,
            no_saved_settings=True,
            on_close=self.close,
            tag=self._tag,
        ) as self._window:
            dpg.add_input_text(
                default_value="",
                hint="Filter (regex)...",
                tag=self._t("filter"),
                no_undo_redo=True,
                width=-1,
            )

            with dpg.plot(
                width=-1,
                height=-57,
                no_mouse_pos=True,
                no_menus=True,
                no_box_select=True,
                tag=self._t("plot"),
            ):
                dpg.add_plot_axis(
                    dpg.mvXAxis,
                    label="Time (s)",
                    no_highlight=True,
                    tag=self._t("x_axis"),
                )
                dpg.set_axis_limits(dpg.last_item(), -self._time_range, 0)

                with dpg.plot_axis(
                    dpg.mvYAxis,
                    tag=self._t("y_axis"),
                    no_highlight=True,
                    no_tick_labels=True,
                ):
                    dpg.set_axis_limits(
                        dpg.last_item(), 0, self._num_rows / 2 + 0.5
                    )
                    dpg.add_custom_series(
                        # Note: there is a bug in current dearpygui where
                        # updating the series data does not update how many
                        # items of transformed_x/y it will provide
                        [0] * self._max_events,
                        [0] * self._max_events,
                        2,
                        callback=self._render_events,
                        tag=self._t("series"),
                    )

            with dpg.group(horizontal=True):
                dpg.add_button(label="Pause", callback=self._on_toggle_playback)
                dpg.add_button(label="Clear", callback=self.clear)
                dpg.add_text("|")
                dpg.add_checkbox(
                    label="Show chr",
                    default_value=False,
                    tag=self._t("show_chr"),
                )
                dpg.add_spacer(width=0)
                dpg.add_input_int(
                    label="Range",
                    default_value=self._time_range,
                    min_value=2,
                    callback=self._on_range_changed,
                    width=100,
                )
                dpg.add_spacer(width=0)
                dpg.add_input_int(
                    label="Port",
                    default_value=self._listener.port,
                    max_value=65535,
                    callback=self._on_port_changed,
                    width=100,
                )

            add_paragraphs(_instructions, 90, color=style.light_blue)

    # === DPG callbacks ================================================

    def _on_toggle_playback(self, sender: str) -> None:
        self._paused = not self._paused
        dpg.configure_item(sender, label="Play " if self._paused else "Pause")

    def _on_range_changed(
        self, sender: str, new_range: int, user_data: Any
    ) -> None:
        self._time_range = max(2, new_range)

    def _on_port_changed(
        self, sender: str, new_port: int, user_data: Any
    ) -> None:
        self._listener.port = new_port

    # TODO there is an occasional annoying flicker that I couldn't track down so far
    def _render_events(self, sender: str, app_data: list) -> None:
        self._plot_t += dpg.get_delta_time()

        if self._paused:
            return

        # Scroll the plot
        dpg.set_axis_limits(
            self._t("x_axis"), self._plot_t - self._time_range, self._plot_t
        )

        visible = self._visible_events()

        # Update series data with visible events
        if visible:
            x_data = [t for _, t, _ in visible]
            y_data = [self._get_row(txt) * 0.5 + 0.5 for _, _, txt in visible]
            dpg.set_value(self._t("series"), [x_data, y_data])
        else:
            dpg.set_value(self._t("series"), [[0], [0]])

        transformed_x = app_data[1]
        transformed_y = app_data[2]

        # Draw visible events
        for visible_idx, (eid, evt_time, evt_text) in enumerate(visible):
            age = self._plot_t - evt_time

            if age > self._time_range * 2:
                self._delete_item(self._t(f"{eid}_rect"))
                self._delete_item(self._t(f"{eid}_text"))
                continue

            if visible_idx >= len(transformed_x):
                break

            x_pos = transformed_x[visible_idx]
            y_pos = transformed_y[visible_idx]

            # Calculate fade based on age
            alpha = max(
                0, min(255, int(255 * (1 - age / (self._time_range * 2))))
            )
            color = self._get_event_color(evt_text)
            faded_color = (color[0], color[1], color[2], alpha)

            # Draw event marker and text
            text_width, text_height = dpg.get_text_size(evt_text)
            pmin = (x_pos, y_pos - text_height / 2 - 4)
            pmax = (x_pos + text_width + 20, y_pos + text_height / 2 + 4)

            if dpg.does_item_exist(self._t(f"{eid}_rect")):
                dpg.configure_item(
                    self._t(f"{eid}_rect"),
                    pmin=pmin,
                    pmax=pmax,
                    fill=faded_color,
                )
                dpg.configure_item(
                    self._t(f"{eid}_text"), pos=(x_pos + 4, y_pos - 7)
                )
            else:
                dpg.push_container_stack(sender)
                dpg.draw_rectangle(
                    pmin,
                    pmax,
                    fill=faded_color,
                    color=faded_color,
                    tag=self._t(f"{eid}_rect"),
                )
                # text_color = (255, 255, 255, alpha)
                dpg.draw_text(
                    (x_pos + 4, y_pos - 7),
                    evt_text,
                    size=14,
                    color=(255, 255, 255, 255),
                    tag=self._t(f"{eid}_text"),
                )
                dpg.pop_container_stack()

    # === Helpers ======================================================

    def _visible_events(self) -> list[tuple[int, float, str]]:
        cutoff = self._plot_t - self._time_range * 2
        return [e for e in self._listener.events if e[1] >= cutoff]

    def _get_row(self, event: str) -> int:
        return self._row_assignments.setdefault(
            event, (len(self._row_assignments) + 1) % self._num_rows
        )

    @staticmethod
    def _get_event_color(evt: str) -> tuple[int, int, int, int]:
        h = hash(evt) % 360
        r, g, b = colorsys.hsv_to_rgb(h / 360, 0.8, 0.9)
        return (int(r * 255), int(g * 255), int(b * 255), 255)

    # === Public =======================================================

    def clear(self) -> None:
        """Drop all recorded events and reset the plot clock."""
        self._listener.clear()
        self._row_assignments.clear()
        self._plot_t = 0.0

        dpg.delete_item(self._t("series"), children_only=True, slot=2)

    def close(self) -> None:
        self.destroy()

        # Workaround for https://github.com/hoffstadt/DearPyGui/issues/2427
        dpg.hide_item(self._window)
        dpg.set_frame_callback(
            dpg.get_frame_count() + 1, lambda: dpg.delete_item(self._window)
        )


if __name__ == "__main__":
    dpg.create_context()
    dpg.create_viewport(title="Hkb Event Listener", width=600, height=600)

    dialog = event_listener_dialog()
    dpg.set_primary_window(dialog.tag, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
