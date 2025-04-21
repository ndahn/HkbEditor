import dearpygui.dearpygui as dpg

dpg.create_context()
dpg.create_viewport(title='Custom Title', width=600, height=300)

def on_click():
    print("hello")

with dpg.window(label="Example Window") as window:
    dpg.add_text("hello")

with dpg.item_handler_registry() as handler:
    dpg.add_item_focus_handler(callback=on_click)

dpg.bind_item_handler_registry(window, handler)

dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()