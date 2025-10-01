import os
from dearpygui import dearpygui as dpg
import webbrowser

from hkb_editor.gui import style


def about_dialog(*, tag: str = None, **window_args) -> str:
    if not tag:
        tag = f"about_dialog_{dpg.generate_uuid()}"

    rainbow = style.HighContrastColorGenerator()
    rainbow.hue = 0.0
    rainbow.hue_step = 0.15

    with dpg.window(
        width=410,
        height=165,
        label="About",
        no_saved_settings=True,
        on_close=lambda: dpg.delete_item(dialog),
        tag=tag,
        **window_args,
    ) as dialog:
        from hkb_editor import __version__

        with dpg.group(horizontal=True):
            if not dpg.does_item_exist("hkbeditor_icon_large"):
                icon_path = os.path.abspath(os.path.join(".", "icon_large.png"))
                w, h, _, data = dpg.load_image(icon_path)
                with dpg.texture_registry():
                    dpg.add_static_texture(w, h, data, tag="hkbeditor_icon_large")

            dpg.add_image("hkbeditor_icon_large")

            with dpg.group():
                dpg.add_text(f"HkbEditor v{__version__}", color=rainbow())

                dpg.add_separator()

                dpg.add_text("Written by Nikolas Dahn", color=rainbow())
                dpg.add_button(
                    label="https://github.com/ndahn/HkbEditor",
                    small=True,
                    callback=lambda: webbrowser.open(
                        "https://github.com/ndahn/HkbEditor"
                    ),
                )
                dpg.bind_item_theme(dpg.last_item(), style.link_button_theme)

                dpg.add_separator()

                dpg.add_text("Bugs, questions, feature request?", color=rainbow())
                dpg.add_text("Find me on ?ServerName? @Managarm!", color=rainbow())

    return tag
