import argparse
from dearpygui import dearpygui as dpg

from HkbEditor.hkb_editor.old.parser import parse_behavior
from hkb_editor.widgets import BehaviorEditor


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
