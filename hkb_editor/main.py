import os
from logging import getLogger
from dearpygui import dearpygui as dpg

from gui import BehaviorEditor
from gui.graph_editor import get_default_layout_path, get_custom_layout_path


_logger = getLogger("Main")


def main():
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
    dpg.create_viewport(title="Behditor")

    with dpg.window() as main_window:
        app = BehaviorEditor("graph_editor")

    dpg.set_primary_window(main_window, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
