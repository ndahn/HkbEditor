from dearpygui import dearpygui as dpg


# TODO Setup properly and use
def setup_styles():
    # We need to adjust padding so that widgets of different types are positioned properly
    with dpg.theme() as foldable_table_theme:
        with dpg.theme_component(dpg.mvAll):
            # Frame padding affects vertical positioning of add_text items within the table
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 4, 0)
