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
notification_info_theme = None
notification_warning_theme = None
notification_error_theme = None


def pastel(color: tuple[int, int, int, int]):
    return tuple((c + 255) // 2 for c in color[:3]) + (color[3],)


def setup_styles():
    global bound_attribute_theme
    global pointer_attribute_theme
    global notification_info_theme
    global notification_warning_theme
    global notification_error_theme

    with dpg.theme() as bound_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, pink)

    with dpg.theme() as pointer_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, blue)

    with dpg.theme() as notification_info_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, pastel(blue))
            dpg.add_theme_color(dpg.mvThemeCol_Border, white)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 5)

    with dpg.theme() as notification_warning_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, pastel(yellow))
            dpg.add_theme_color(dpg.mvThemeCol_Border, white)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 5)

    with dpg.theme() as notification_error_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, pastel(red))
            dpg.add_theme_color(dpg.mvThemeCol_Border, white)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 5)
