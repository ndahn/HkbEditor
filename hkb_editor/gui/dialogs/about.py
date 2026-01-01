import os
import random
import numpy as np
from dearpygui import dearpygui as dpg
import webbrowser

from hkb_editor.gui import style
from hkb_editor.gui.cats import draw_cat


def about_dialog(*, tag: str = None, **window_args) -> str:
    if not tag:
        tag = f"about_dialog_{dpg.generate_uuid()}"

    rainbow = style.HighContrastColorGenerator()
    rainbow.hue = random.random()
    rainbow.hue_step = 0.05

    if not dpg.does_item_exist("hkbeditor_icon_ufo"):
        with dpg.texture_registry():
            icon_ufo = os.path.abspath(os.path.join(".", "docs/assets/images/ufo.png"))
            w, h, ch, data = dpg.load_image(icon_ufo)
            
            # 250ms? worth it!
            img_data = np.frombuffer(data, dtype=np.float32).reshape((w, h, ch))
            style.colorshift(
                img_data, 
                hue_shift=rainbow.hue,
                saturation_scale=random.random(),
            )
            
            dpg.add_static_texture(w, h, img_data, tag="hkbeditor_icon_ufo")

    def add_cat(cat: int, pos: tuple[int, int], wf: float = 1.0) -> None:
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

    def make_cats():
        num_cats = random.randint(1, 3)

        if num_cats == 1:
            cat = random.choice(list(range(1, 4)))
            add_cat(cat, pos=(50, 100), wf=2)

        elif num_cats == 2:
            cats = random.sample(list(range(1, 4)), k=2)
            add_cat(cats[0], pos=(45, 80), wf=1.5)
            add_cat(cats[1], pos=(65, 125), wf=1.5)

        elif num_cats == 3:
            cats = random.sample(list(range(1, 4)), k=3)
            add_cat(cats[0], pos=(50, 70))
            add_cat(cats[1], pos=(35, 110))
            add_cat(cats[2], pos=(65, 125))

    with dpg.window(
        width=410,
        height=190,
        label="About",
        no_saved_settings=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_resize=True,
        tag=tag,
        **window_args,
    ) as dialog:
        from hkb_editor import __version__

        with dpg.group(horizontal=True):
            with dpg.drawlist(100, 150, tag=f"{tag}_icon_canvas"):
                with dpg.draw_layer(perspective_divide=True):
                    dpg.draw_image("hkbeditor_icon_ufo", (0, 0), (100, 150))
                    make_cats()

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
                dpg.bind_item_theme(dpg.last_item(), style.link_button_theme)

                dpg.add_separator()

                dpg.add_text("Bugs, questions, feature request?", color=rainbow())
                dpg.add_text("Find me on ?ServerName? @Managarm!", color=rainbow())

    return tag
