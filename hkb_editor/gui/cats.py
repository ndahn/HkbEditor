import os
import math
import time
from dearpygui import dearpygui as dpg


variant = "x"


def _load_cats() -> None:
    if not dpg.does_item_exist("hkbeditor_icon_cat1"):
        with dpg.texture_registry():
            for i in range(1, 4):
                cat = os.path.abspath(os.path.join(".", f"doc/cat{i}{variant}.png"))
                w, h, _, data = dpg.load_image(cat)
                dpg.add_static_texture(w, h, data, tag=f"hkbeditor_icon_cat{i}")


def draw_cat(
    cat: int = 1,
    spin: bool = True,
    *,
    pos: tuple[int, int] = (50, 100),
    scale: float = 20,
    rotation: float = 0.0,
    spin_right: bool = True,
    spin_rate: float = 1.0,
    wobble: tuple[float, float] = (5, 3),
    wobble_rate: float = 1.0,
    wobble_offset: float = 0.0,
    tag: str = None,
    parent: str = None,
) -> str:
    if not tag:
        tag = f"{dpg.generate_uuid()}_icon_cat"

    if not parent:
        parent = dpg.top_container_stack()
        while parent and dpg.get_item_type(parent) != "mvAppItemType::mvDrawlist":
            parent = dpg.get_item_parent(parent)

        if not parent:
            raise RuntimeError("Could not locate canvas to draw to")

    _load_cats()

    with dpg.draw_node(tag=tag, user_data=rotation):
        dpg.draw_image_quad(
            f"hkbeditor_icon_cat{cat}",
            (-scale, -scale),
            (scale, -scale),
            (scale, scale),
            (-scale, scale),
        )

    if spin:

        def spin_cat() -> None:
            if not dpg.does_item_exist(tag):
                return

            sig = 1 if spin_right else -1
            rot = dpg.get_item_user_data(tag) + spin_rate * sig
            phase = time.time() * wobble_rate + wobble_offset
            off = math.sin(phase % (math.pi * 2))

            dpg.apply_transform(
                tag,
                dpg.create_translation_matrix(
                    [pos[0] + off * wobble[0], pos[1] + off * wobble[1]]
                )
                * dpg.create_rotation_matrix(math.radians(rot), [0, 0, 1]),
            )

            dpg.set_item_user_data(tag, rot)

        # Can only have one registry per parent
        registry = f"{parent}_handler_registry"
        if not dpg.does_item_exist(registry):
            dpg.add_item_handler_registry(tag=registry)
            dpg.bind_item_handler_registry(parent, registry)
            
        dpg.add_item_visible_handler(callback=spin_cat, user_data=tag, parent=registry)

    else:
        dpg.apply_transform(
            tag,
            dpg.create_translation_matrix([pos[0], pos[1]])
            * dpg.create_rotation_matrix(math.radians(rotation), [0, 0, 1]),
        )
