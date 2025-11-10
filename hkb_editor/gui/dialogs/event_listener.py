from typing import Any
import socket
import threading
import colorsys
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
    events = deque(maxlen=max_events)
    sock = None
    listener_thread = None
    running = True
    paused = False

    def socket_listener():
        nonlocal sock
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.1)
        sock.bind(("localhost", port))

        while running:
            try:
                data, _ = sock.recvfrom(1024)
                evt = data.decode("utf-8").strip()
                print(f" (evt) {evt}")
                events.append((plot_t, evt))
            except socket.timeout:
                continue
            except Exception:
                break

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

    def toggle_playback(sender: str):
        nonlocal paused
        paused = not paused
        label = "Play" if paused else "Pause"
        dpg.configure_item(sender, label=label)

    def get_event_color(evt: str) -> tuple[int, int, int, int]:
        h = hash(evt) % 360
        r, g, b = colorsys.hsv_to_rgb(h / 360, 0.8, 0.9)
        return (int(r * 255), int(g * 255), int(b * 255), 255)

    def render_events(sender: str, app_data: list):
        if paused:
            return

        transformed_x = app_data[1]
        transformed_y = app_data[2]

        # Clear previous drawings
        dpg.delete_item(sender, children_only=True, slot=2)
        dpg.push_container_stack(sender)

        # Get visible events
        visible = [(t, txt) for t, txt in events if t >= plot_t - time_range]
        if not visible:
            dpg.pop_container_stack()
            return

        visible.sort()

        # Draw events
        for i, (evt_time, evt_text) in enumerate(visible):
            if i >= len(transformed_x):
                break

            x_pos = transformed_x[i]
            y_pos = transformed_y[i]

            # Calculate fade based on age
            age = plot_t - evt_time
            alpha = max(0, min(255, int(255 * (1 - age / time_range))))

            color = get_event_color(evt_text)
            faded_color = (color[0], color[1], color[2], alpha)

            # Draw event marker and text
            # Draw rectangle
            text_width, text_height = dpg.get_text_size(evt_text)
            dpg.draw_rectangle(
                (x_pos, y_pos - text_height / 2),
                (x_pos + text_width + 12, y_pos + text_height / 2),
                fill=faded_color,
                color=faded_color,
            )
            text_color = (255, 255, 255, 255)
            # text_color = (255, 255, 255, alpha)
            dpg.draw_text((x_pos + 4, y_pos - 7), evt_text, size=14, color=text_color)

        dpg.pop_container_stack()

    def update_plot():
        nonlocal plot_t
        plot_t += dpg.get_delta_time()

        if paused:
            return

        dpg.set_axis_limits(f"{tag}_x_axis", plot_t - time_range, plot_t)

        # Update series data with visible events
        visible = [(t, txt) for t, txt in events if t >= plot_t - time_range]
        visible.sort()

        row_assignments = []

        for i, (evt_time, evt_text) in enumerate(visible):
            row_assignments.append((evt_time, evt_text, i % num_rows))

        if row_assignments:
            x_data = [t for t, _, _ in row_assignments]
            y_data = [r * 0.5 + 0.5 for _, _, r in row_assignments]
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
        dpg.set_frame_callback(dpg.get_frame_count() + 1, lambda: dpg.delete_item(dialog))

    with dpg.window(
        min_size=(600, 400),
        label="Event Listener",
        no_saved_settings=True,
        on_close=close,
        tag=tag,
    ) as dialog:
        with dpg.group(horizontal=True):
            dpg.add_button(label="Pause", callback=toggle_playback)
            dpg.add_input_int(
                label="Range (s)",
                default_value=10,
                min_value=2,
                callback=update_range,
                width=150,
            )
            dpg.add_input_int(
                label="Port",
                default_value=27072,
                max_value=65535,
                callback=update_port,
                width=150,
            )

        dpg.add_separator()

        with dpg.plot(
            tag=f"{tag}_plot",
            height=-1,
            width=-1,
            no_mouse_pos=True,
            no_menus=True,
            no_box_select=True,
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

    # Plot updates
    with dpg.item_handler_registry():
        dpg.add_item_visible_handler(callback=update_plot, tag=f"{tag}_visible_handler")
    dpg.bind_item_handler_registry(f"{tag}_plot", dpg.last_container())

    # Start listener
    listener_thread = threading.Thread(target=socket_listener, daemon=True)
    listener_thread.start()

    return tag


# Just for testing
if __name__ == "__main__":
    import random
    import time

    dpg.create_context()
    dpg.create_viewport(title="Test Event Listener", width=600, height=600)

    def generate_events():
        event_types = [
            "sensor.temperature",
            "sensor.pressure",
            "alarm.high_temp",
            "alarm.low_pressure",
            "system.startup",
            "system.shutdown",
            "data.received",
            "data.error",
            "network.connected",
            "network.timeout",
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"Sending test events to localhost:{27072}")

        try:
            while True:
                event = random.choice(event_types)
                sock.sendto(event.encode("utf-8"), ("localhost", 27072))
                time.sleep(random.uniform(0.5, 3.0))
        except KeyboardInterrupt:
            print("\nStopped")
        finally:
            sock.close()

    test_thread = threading.Thread(target=generate_events, daemon=True)
    test_thread.start()

    eventlistener_dialog()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
