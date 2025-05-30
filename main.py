#!/usr/bin/env python3
import os
import logging
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.gui import BehaviorEditor
from hkb_editor.gui.graph_editor import get_default_layout_path, get_custom_layout_path
from hkb_editor.gui.style import setup_styles


def main():
    # Logging setup
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)

    # Check for clipboard support, will print instructions if it fails
    try:
        pyperclip.paste()
    except pyperclip.PyperclipException as e:
        _logger.error("Pyperclip failed: %s", e)

    dpg.create_context()

    layout = get_custom_layout_path()
    if not os.path.isfile(layout):
        layout = get_default_layout_path()

    if not os.path.isfile(layout):
        layout = None
        _logger.error("Layout not found")
    else:
        _logger.info("Loading layout %s", layout)

    dpg.configure_app(docking=True, docking_space=True, init_file=layout)
    dpg.create_viewport(title="HkbEditor")

    setup_styles()
    with dpg.window() as main_window:
        app = BehaviorEditor("hkbeditor")

    dpg.set_primary_window(main_window, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
