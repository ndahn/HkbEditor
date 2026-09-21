import os
import random
import webbrowser
import numpy as np
from dearpygui import dearpygui as dpg

from hkb_editor.gui import style
from hkb_editor.gui.widgets.cats import draw_cat
from hkb_editor.gui.widgets import DpgItem


class about_dialog(DpgItem):
    """The about window, with rainbow text and a randomized cat arrangement.

    Parameters
    ----------
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    window_args : dict
        Forwarded to ``dpg.window``.
    """

    def __init__(self, *, tag: str = None, **window_args) -> None:
        super().__init__(tag)

        self._rainbow = style.HighContrastColorGenerator()
        self._rainbow.hue = random.random()
        self._rainbow.hue_step = 0.05
        self._window: str = None

        self._load_textures()
        self._build(**window_args)

    def destroy(self) -> None:
        # draw_cat binds a handler registry to the canvas to animate the cats.
        # Registries are root level items and outlive the window.
        self._delete_item(f"{self._t('icon_canvas')}_handler_registry")

    # === Build ========================================================

    def _load_textures(self) -> None:
        # Textures live in a global registry and are shared between dialogs
        if not dpg.does_item_exist("hkbeditor_icon_ufo"):
            with dpg.texture_registry():
                icon_ufo = os.path.abspath(
                    os.path.join(".", "docs/assets/images/ufo.png")
                )
                w, h, ch, data = dpg.load_image(icon_ufo)

                # 250ms? worth it!
                img_data = np.frombuffer(data, dtype=np.float32).reshape((w, h, ch))
                style.colorshift(
                    img_data,
                    hue_shift=self._rainbow.hue,
                    saturation_scale=random.random(),
                )

                dpg.add_static_texture(w, h, img_data, tag="hkbeditor_icon_ufo")

        if not dpg.does_item_exist("hkbeditor_icon_kofi"):
            with dpg.texture_registry():
                kofi = os.path.abspath(
                    os.path.join(".", "docs/assets/images/kofi_white.png")
                )
                w, h, _, data = dpg.load_image(kofi)
                dpg.add_static_texture(w, h, data, tag="hkbeditor_icon_kofi")

    def _add_cat(self, cat: int, pos: tuple[int, int], wf: float = 1.0) -> None:
        draw_cat(
            cat,
            pos=pos,
            rotation=random.randint(0, 359),
            spin_rate=random.random() * 0.5 + 0.5,
            spin_right=random.choice([True, False]),
            wobble=((random.random() * 5 + 2) * wf, (random.random() * 5 + 2) * wf),
            wobble_rate=(random.random() * 0.5 + 0.5) * 1,
            wobble_offset=random.random() * 3.1415,
        )

    def _make_cats(self) -> None:
        num_cats = random.randint(1, 3)

        if num_cats == 1:
            cat = random.choice(list(range(1, 4)))
            self._add_cat(cat, pos=(50, 100), wf=2)

        elif num_cats == 2:
            cats = random.sample(list(range(1, 4)), k=2)
            self._add_cat(cats[0], pos=(45, 80), wf=1.5)
            self._add_cat(cats[1], pos=(65, 125), wf=1.5)

        elif num_cats == 3:
            cats = random.sample(list(range(1, 4)), k=3)
            self._add_cat(cats[0], pos=(50, 70))
            self._add_cat(cats[1], pos=(35, 110))
            self._add_cat(cats[2], pos=(65, 125))

    def _build(self, **window_args) -> None:
        rainbow = self._rainbow

        with dpg.window(
            width=410,
            height=190,
            label="About",
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(self._window),
            no_resize=True,
            tag=self._tag,
            **window_args,
        ) as self._window:
            from hkb_editor import __version__

            with dpg.group(horizontal=True):
                with dpg.drawlist(100, 150, tag=self._t("icon_canvas")):
                    with dpg.draw_layer(perspective_divide=True):
                        dpg.draw_image("hkbeditor_icon_ufo", (0, 0), (100, 150))
                        self._make_cats()

                dpg.add_spacer(width=5)

                with dpg.group():
                    dpg.add_spacer(height=10)
                    dpg.add_text(f"HkbEditor v{__version__}", color=rainbow())

                    dpg.add_separator()

                    dpg.add_text("Written by Nikolas Dahn", color=rainbow())
                    dpg.add_button(
                        label="https://github.com/ndahn/HkbEditor",
                        small=True,
                        callback=lambda: webbrowser.open(
                            "https://github.com/ndahn/HkbEditor"
                        ),
                    )
                    dpg.bind_item_theme(dpg.last_item(), style.themes.link_button)

                    dpg.add_separator()

                    dpg.add_text("Bugs, questions, feature request?", color=rainbow())
                    dpg.add_text("Find me on ?ServerName? @Managarm!", color=rainbow())

                    # Tooltips don't work on buttons with absolute position
                    # See https://github.com/hoffstadt/DearPyGui/issues/2651
                    with dpg.group(pos=(365, 15)):
                        dpg.add_image_button(
                            "hkbeditor_icon_kofi",
                            width=24,
                            height=24,
                            tint_color=(255, 255, 255, 200),
                            callback=lambda: webbrowser.open(
                                "https://ko-fi.com/managarm"
                            ),
                        )
                        dpg.bind_item_theme(
                            dpg.last_item(), style.themes.button_transparent
                        )
                        with dpg.tooltip(dpg.last_item()):
                            dpg.add_text("Buy me a ko-fi?")
