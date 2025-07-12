#!/usr/bin/env python3
import sys
import os
import shutil
import logging
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.gui import BehaviorEditor
from hkb_editor.gui.graph_editor import get_default_layout_path, get_custom_layout_path
from hkb_editor.gui.style import setup_styles


def main():
    # Logging setup
    logfile = os.path.join(os.path.dirname(sys.argv[0]), "log.txt")
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(logfile),
            logging.StreamHandler(),
        ]
    )
    _logger = logging.getLogger(__name__)

    # Check for clipboard support, will print instructions if it fails
    try:
        pyperclip.paste()
    except pyperclip.PyperclipException as e:
        _logger.error("Pyperclip failed: %s", e)

    dpg.create_context()

    # default layout should never be touched, it only serves as a template
    default_layout = get_default_layout_path()
    user_layout = get_custom_layout_path()

    if not os.path.isfile(default_layout):
        _logger.error("Layout not found")
    else:
         if not os.path.isfile(user_layout):
            shutil.copy(default_layout, user_layout)
            _logger.info("Copied default layout to user layout")

    dpg.configure_app(docking=True, docking_space=True, init_file=user_layout)
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
