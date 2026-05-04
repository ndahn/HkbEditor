from __future__ import annotations
from typing import Any, Iterable, Callable
import numpy as np
import colorsys
from dearpygui import dearpygui as dpg


class RGBA(tuple):
    def __new__(
        cls, color_or_r: int | Iterable[int], g: int = None, b: int = None, a: int = 255
    ):
        if isinstance(color_or_r, Iterable):
            if len(color_or_r) == 3:
                r, g, b = color_or_r
                a = 255
            else:
                r, g, b, a = color_or_r[:4]
            return super().__new__(cls, (r, g, b, a))

        return super().__new__(cls, (color_or_r, g, b, a))

    @classmethod
    def from_floats(cls, r: float, g: float, b: float, a: float = 1.0) -> RGBA:
        return RGBA(int(r * 255), int(g * 255), int(b * 255), int(a * 255))

    def as_floats(self) -> tuple[float, float, float, float]:
        return (self.r / 255, self.g / 255, self.b / 255, self.a / 255)

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self[:2]

    @property
    def hsv(self) -> tuple[int, int, int]:
        h, s, v = colorsys.rgb_to_hsv(self.r, self.g, self.b)
        return (int(h * 255), int(s * 255), int(v * 255))

    @property
    def r(self) -> int:
        return self[0]

    @property
    def g(self) -> int:
        return self[1]

    @property
    def b(self) -> int:
        return self[2]

    @property
    def a(self) -> int:
        return self[3]

    def but(
        self, *, r: int = None, g: int = None, b: int = None, a: int = None
    ) -> RGBA:
        if r is None:
            r = self.r

        if g is None:
            g = self.g

        if b is None:
            b = self.b

        if a is None:
            a = self.a

        return RGBA(r, g, b, a)

    def mix(self, other: "tuple | RGBA", ratio: float = 0.5) -> RGBA:
        r = ratio * self.r + (1 - ratio) * other[0]
        g = ratio * self.g + (1 - ratio) * other[1]
        b = ratio * self.b + (1 - ratio) * other[2]
        a = ratio * self.a + (1 - ratio) * other[3]
        return RGBA(r, g, b, a)

    def shift(self, amount: int) -> RGBA:
        h, s, v = colorsys.rgb_to_hsv(*self.as_floats()[:3])
        r, g, b = colorsys.hsv_to_rgb(h, (s + amount) % 1.0, v)
        return RGBA.from_floats(r, g, b, self.a / 255)

    def brightness(self, brightness: float) -> RGBA:
        h, s, _ = colorsys.rgb_to_hsv(*self.as_floats()[:3])
        r, g, b = colorsys.hsv_to_rgb(h, s, brightness)
        return RGBA.from_floats(r, g, b, self.a / 255)

    def __or__(self, other: "tuple | RGBA") -> RGBA:
        return self.mix(other)

    def __str__(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return f"Color {self}"


# https://coolors.co/palette/ffbe0b-fb5607-ff006e-8338ec-3a86ff
yellow = RGBA(255, 190, 11, 255)
orange = RGBA(251, 86, 7, 255)
red = RGBA(234, 11, 30, 255)
pink = RGBA(255, 0, 110, 255)
purple = RGBA(127, 50, 236, 255)
blue = RGBA(58, 134, 255, 255)
green = RGBA(138, 201, 38, 255)

white = RGBA(255, 255, 255, 255)
light_grey = RGBA(151, 151, 151, 255)
dark_grey = RGBA(62, 62, 62, 255)
black = RGBA(0, 0, 0, 255)

light_blue = RGBA(112, 214, 255, 255)
light_green = RGBA(112, 255, 162, 255)
light_red = RGBA(255, 112, 119)


# Section colors
muted_orange = RGBA(200, 120, 80, 255)
muted_blue = RGBA(80, 120, 200, 255)
muted_green = RGBA(80, 180, 120, 255)
muted_purple = RGBA(140, 90, 180, 255)
muted_yellow = RGBA(200, 180, 60, 255)
muted_teal = RGBA(60, 180, 180, 255)
muted_rose = RGBA(200, 80, 120, 255)


class HighContrastColorGenerator:
    """Generates RGB colors with a certain distance apart so that subsequent colors are visually distinct."""

    def __init__(
        self,
        initial_hue: float = 0.0,
        hue_step: float = 0.61803398875,
        saturation: float = 1.0,
        value: float = 1.0,
        alpha: float = 1.0,
    ):
        # 0.61803398875: golden ratio conjugate, ensures well-spaced hues
        self.hue_step = hue_step
        self.hue = initial_hue
        self.saturation = saturation
        self.value = value
        self.alpha = alpha
        self.initial_hue = initial_hue
        self.cache = {}

    def __iter__(self):
        """Allows the class to be used as an iterable."""
        return self

    def reset(self) -> None:
        self.hue = self.initial_hue
        self.cache.clear()

    def __next__(self) -> tuple[int, int, int]:
        """Generates the next high-contrast color."""
        self.hue = (self.hue + self.hue_step) % 1
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        return (int(r * 255), int(g * 255), int(b * 255), int(self.alpha * 255))

    def __call__(self, key: Any = None) -> tuple[int, int, int]:
        """Allows calling the instance directly to get the next color."""
        if key is not None:
            if key not in self.cache:
                self.cache[key] = next(self)
            return self.cache[key]

        return next(self)


get_contrast_color: Callable[[], tuple[int, int, int]] = HighContrastColorGenerator()
"""A global instance to generate sequences of visually distinct colors.
"""

bound_attribute_theme = None
pointer_attribute_theme = None
index_attribute_theme = None

notification_info_theme = None
notification_warning_theme = None
notification_error_theme = None

input_field_error_theme = None
input_field_okay_theme = None

link_button_theme = None

plot_no_borders_theme = None
window_no_padding_theme = None


def pastel(color: tuple[int, int, int, int]):
    return tuple((c + 255) // 2 for c in color[:3]) + (color[3],)


def colorshift(
    image: np.ndarray,
    hue_shift: float = 0.0,
    saturation_scale: float = 1.0,
    value_scale: float = 1.0,
):
    """
    Colorshift an RGBA image in place by adjusting hue, saturation, and value.

    Parameters:
    -----------
    image : np.ndarray
        RGBA image as float32 array with shape (H, W, 4) and values in [0, 1]
    hue_shift : float
        Hue rotation in range [0, 1] (e.g., 0.5 shifts by 180 degrees)
    saturation_scale : float
        Saturation multiplier (e.g., 1.5 increases saturation by 50%)
    value_scale : float
        Value/brightness multiplier

    Returns:
    --------
    np.ndarray
        Colorshifted RGBA image
    """
    h, w = image.shape[:2]

    for i in range(h):
        for j in range(w):
            r, g, b = image[i, j, :3]
            h_val, s_val, v_val = colorsys.rgb_to_hsv(r, g, b)

            h_val = (h_val + hue_shift) % 1.0
            s_val = np.clip(s_val * saturation_scale, 0, 1)
            v_val = np.clip(v_val * value_scale, 0, 1)

            r, g, b = colorsys.hsv_to_rgb(h_val, s_val, v_val)
            image[i, j, :3] = [r, g, b]

    return image


def setup_styles():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBg, (46, 46, 69), category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_FrameRounding, 1, category=dpg.mvThemeCat_Core
            )

    dpg.bind_theme(global_theme)

    global bound_attribute_theme
    global pointer_attribute_theme
    global index_attribute_theme
    global notification_info_theme
    global notification_warning_theme
    global notification_error_theme
    global input_field_okay_theme
    global input_field_error_theme
    global link_button_theme
    global plot_no_borders_theme
    global window_no_padding_theme

    with dpg.theme() as bound_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, pink)

    with dpg.theme() as pointer_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, blue)

    with dpg.theme() as index_attribute_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, green)

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

    with dpg.theme() as link_button_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, blue, category=dpg.mvThemeCat_Core)

    with dpg.theme() as plot_no_borders_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvPlotStyleVar_PlotBorderSize, 0, category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_PlotPadding, 0, 0, category=dpg.mvThemeCat_Plots)

    with dpg.theme() as window_no_padding_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
