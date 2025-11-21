#!/usr/bin/env python3
from typing import Any
import socket
import threading
import colorsys
import re
from dearpygui import dearpygui as dpg
from collections import deque


def eventlistener_dialog(*, tag: str = 0) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    plot_t = 0.0
    port = 27072
    time_range = 10
    max_events = 100
    num_rows = 10
    event_idx = 0
    row_assignments = {}
    events = deque(maxlen=max_events)
    sock = None
    listener_thread = None
    running = True
    paused = False

    def socket_listener():
        nonlocal sock, event_idx
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.1)
        sock.bind(("localhost", port))

        while running:
            try:
                data, _ = sock.recvfrom(1024)
                event = data.decode("utf-8").strip()
                filter_value = dpg.get_value(f"{tag}_filter").strip()

                if not filter_value or (
                    filter_value in event
                    or re.match(filter_value, event, flags=re.IGNORECASE)
                ):
                    print(f" ✦ {event}")

                    if not dpg.get_value(f"{tag}_show_chr"):
                        event = event.split(":", maxsplit=1)[-1]

                    row = row_assignments.setdefault(
                        event, (len(row_assignments) + 1) % num_rows
                    )

                    eid = event_idx
                    event_idx += 1
                    events.append((eid, plot_t, row, event))
            except socket.timeout:
                continue
            except Exception:
                break

    def toggle_playback(sender: str):
        nonlocal paused
        paused = not paused
        label = "Play " if paused else "Pause"
        dpg.configure_item(sender, label=label)

    def clear_events():
        nonlocal plot_t
        events.clear()
        row_assignments.clear()
        plot_t = 0.0

    def update_port(sender: str, new_port: int, user_data: Any):
        nonlocal port, listener_thread, running
        if new_port == port:
            return

        running = False
        if listener_thread:
            listener_thread.join()
        if sock:
            sock.close()

        port = new_port
        running = True
        listener_thread = threading.Thread(target=socket_listener, daemon=True)
        listener_thread.start()

    def update_range(sender: str, new_range: int, user_data: Any):
        nonlocal time_range
        time_range = max(2, new_range)

    def get_event_color(evt: str) -> tuple[int, int, int, int]:
        h = hash(evt) % 360
        r, g, b = colorsys.hsv_to_rgb(h / 360, 0.8, 0.9)
        return (int(r * 255), int(g * 255), int(b * 255), 255)

    # TODO there is an occasional annoying flicker that I couldn't track down so far
    def render_events(sender: str, app_data: list):
        if paused:
            return

        transformed_x = app_data[1]
        transformed_y = app_data[2]

        # Draw visible events
        visible = [
            (eid, t, row, txt)
            for eid, t, row, txt in events
            if t >= plot_t - time_range * 2
        ]

        for visible_idx, (eid, evt_time, _, evt_text) in enumerate(visible):
            age = plot_t - evt_time

            if age > time_range * 2:
                if dpg.does_item_exist(f"{tag}_{eid}_rect"):
                    dpg.delete_item(f"{tag}_{eid}_rect")
                    dpg.delete_item(f"{tag}_{eid}_text")
                continue

            if visible_idx >= len(transformed_x):
                break

            x_pos = transformed_x[visible_idx]
            y_pos = transformed_y[visible_idx]

            # Calculate fade based on age
            alpha = max(0, min(255, int(255 * (1 - age / (time_range * 2)))))

            color = get_event_color(evt_text)
            faded_color = (color[0], color[1], color[2], alpha)

            # Draw event marker and text
            # Draw rectangle
            text_width, text_height = dpg.get_text_size(evt_text)

            if dpg.does_item_exist(f"{tag}_{eid}_rect"):
                dpg.configure_item(
                    f"{tag}_{eid}_rect",
                    pmin=(x_pos, y_pos - text_height / 2 - 4),
                    pmax=(x_pos + text_width + 20, y_pos + text_height / 2 + 4),
                    fill=faded_color,
                )
                dpg.configure_item(
                    f"{tag}_{eid}_text",
                    pos=(x_pos + 4, y_pos - 7),
                )
            else:
                dpg.push_container_stack(sender)
                dpg.draw_rectangle(
                    (x_pos, y_pos - text_height / 2 - 4),
                    (x_pos + text_width + 20, y_pos + text_height / 2 + 4),
                    fill=faded_color,
                    color=faded_color,
                    tag=f"{tag}_{eid}_rect",
                )
                text_color = (255, 255, 255, 255)
                # text_color = (255, 255, 255, alpha)
                dpg.draw_text(
                    (x_pos + 4, y_pos - 7),
                    evt_text,
                    size=14,
                    color=text_color,
                    tag=f"{tag}_{eid}_text",
                )
                dpg.pop_container_stack()

    def update_plot():
        nonlocal plot_t
        plot_t += dpg.get_delta_time()

        if paused:
            return

        dpg.set_axis_limits(f"{tag}_x_axis", plot_t - time_range, plot_t)

        # Update series data with visible events
        visible = [
            (eid, t, row, txt)
            for eid, t, row, txt in events
            if t >= plot_t - time_range * 2
        ]

        if visible:
            x_data = [t for _, t, _, _ in visible]
            y_data = [r * 0.5 + 0.5 for _, _, r, _ in visible]
            dpg.set_value(f"{tag}_series", [x_data, y_data])
        else:
            dpg.set_value(f"{tag}_series", [[0], [0]])

    def close():
        nonlocal running
        running = False

        if listener_thread:
            listener_thread.join(timeout=0.5)
        if sock:
            sock.close()

        # Workaround for https://github.com/hoffstadt/DearPyGui/issues/2427
        dpg.hide_item(dialog)
        dpg.set_frame_callback(
            dpg.get_frame_count() + 1, lambda: dpg.delete_item(dialog)
        )

    with dpg.window(
        min_size=(600, 400),
        label="Event Listener",
        no_saved_settings=True,
        on_close=close,
        tag=tag,
    ) as dialog:
        dpg.add_input_text(
            default_value="",
            hint="Filter (regex)...",
            tag=f"{tag}_filter",
            no_undo_redo=True,
            width=-1,
        )

        with dpg.plot(
            width=-1,
            height=-25,
            no_mouse_pos=True,
            no_menus=True,
            no_box_select=True,
            tag=f"{tag}_plot",
        ):
            dpg.add_plot_axis(
                dpg.mvXAxis, label="Time (s)", no_highlight=True, tag=f"{tag}_x_axis"
            )
            dpg.set_axis_limits(dpg.last_item(), -time_range, 0)

            with dpg.plot_axis(
                dpg.mvYAxis, tag=f"{tag}_y_axis", no_highlight=True, no_tick_labels=True
            ):
                dpg.set_axis_limits(dpg.last_item(), 0, num_rows / 2 + 0.5)
                dpg.add_custom_series(
                    # Note: there is a bug in current dearpygui where updating the series data
                    # does not update how many items of transformed_x/y it will provide
                    [0] * max_events,
                    [0] * max_events,
                    2,
                    callback=render_events,
                    tag=f"{tag}_series",
                )

        with dpg.group(horizontal=True):
            dpg.add_button(label="Pause", callback=toggle_playback)
            dpg.add_button(label="Clear", callback=clear_events)
            dpg.add_text("|")
            dpg.add_checkbox(
                label="Show chr",
                default_value=False,
                tag=f"{tag}_show_chr",
            )
            dpg.add_spacer(width=0)
            dpg.add_input_int(
                label="Range",
                default_value=10,
                min_value=2,
                callback=update_range,
                width=100,
            )
            dpg.add_spacer(width=0)
            dpg.add_input_int(
                label="Port",
                default_value=27072,
                max_value=65535,
                callback=update_port,
                width=100,
            )

    # Plot updates
    if not dpg.does_item_exist(f"{tag}_handler"):
        with dpg.item_handler_registry(tag=f"{tag}_handler"):
            dpg.add_item_visible_handler(
                callback=update_plot, tag=f"{tag}_visible_handler"
            )
    dpg.bind_item_handler_registry(f"{tag}_plot", f"{tag}_handler")

    # Start listener
    listener_thread = threading.Thread(target=socket_listener, daemon=True)
    listener_thread.start()

    return tag


if __name__ == "__main__":
    dpg.create_context()
    dpg.create_viewport(title="Hkb Event Listener", width=600, height=600)

    dialog = eventlistener_dialog()
    dpg.set_primary_window(dialog, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
