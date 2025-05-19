from dearpygui import dearpygui as dpg


# https://coolors.co/palette/ffbe0b-fb5607-ff006e-8338ec-3a86ff
yellow = (255, 190, 11, 255)
orange = (251, 86, 7, 255)
red = (234, 11, 30, 255)
pink = (255, 0, 110, 255)
purple = (127, 50, 236, 255)
blue = (58, 134, 255, 255)
green = (138, 201, 38, 255)

white = (255, 255, 255, 255)
dark_grey = (62, 62, 62, 255)
black = (0, 0, 0, 255)


bound_attribute_theme = None
pointer_attribute_theme = None


def setup_styles():
    global bound_attribute_theme
    global pointer_attribute_theme

    with dpg.theme() as bound_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, pink)
    
    with dpg.theme() as pointer_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, blue)
    
