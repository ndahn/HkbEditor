from typing import Callable
import colorsys
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


class HighContrastColorGenerator:
    """Generates RGB colors with a certain distance apart so that subsequent colors are visually distinct."""
    
    def __init__(self):
        # Golden ratio conjugate, ensures well-spaced hues
        self.hue_step = 0.61803398875
        self.hue = 0

    def __iter__(self):
        """Allows the class to be used as an iterable."""
        return self

    def reset(self) -> None:
        self.hue = 0

    def __next__(self):
        """Generates the next high-contrast color."""
        self.hue = (self.hue + self.hue_step) % 1
        r, g, b = colorsys.hsv_to_rgb(self.hue, 1, 1)
        return (int(r * 255), int(g * 255), int(b * 255))

    def __call__(self):
        """Allows calling the instance directly to get the next color."""
        return next(self)


get_contrast_color: Callable[[], tuple[int, int, int]] = HighContrastColorGenerator()
"""A global instance to generate sequences of visually distinct colors.
"""

bound_attribute_theme = None
pointer_attribute_theme = None

notification_info_theme = None
notification_warning_theme = None
notification_error_theme = None

input_field_error_theme = None
input_field_okay_theme = None


def pastel(color: tuple[int, int, int, int]):
    return tuple((c + 255) // 2 for c in color[:3]) + (color[3],)


def setup_styles():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (46, 46, 69), category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 1, category=dpg.mvThemeCat_Core)

    dpg.bind_theme(global_theme)

    global bound_attribute_theme
    global pointer_attribute_theme
    global notification_info_theme
    global notification_warning_theme
    global notification_error_theme
    global input_field_okay_theme
    global input_field_error_theme

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

    with dpg.theme() as input_field_okay_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Border, white)

    with dpg.theme() as input_field_error_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Border, red)
