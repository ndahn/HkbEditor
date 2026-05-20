from typing import Generator
from contextlib import contextmanager
from dearpygui import dearpygui as dpg

from hkb_editor.gui import style


@contextmanager
def loading_indicator(
    label: str, color: style.RGBA = style.red
) -> Generator[str, None, None]:
    try:
        dpg.split_frame()

        with dpg.window(
            modal=True,
            min_size=(50, 20),
            no_close=True,
            no_move=True,
            no_collapse=True,
            no_title_bar=True,
            no_resize=True,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
            no_saved_settings=True,
        ) as dialog:
            with dpg.group(horizontal=True):
                dpg.add_loading_indicator(color=color)
                with dpg.group():
                    dpg.add_spacer(height=5)
                    dpg.add_text(label, tag=f"{dialog}_label")

        yield dialog
    finally:
        if dpg.does_item_exist(dialog):
            dpg.delete_item(dialog)
