from typing import Any, Callable
from dearpygui import dearpygui as dpg
import pyperclip

from hkb_editor.hkb.hkb_types import HkbRecord
from . import style


def center_window(window: str, parent: str = None) -> None:
    if parent:
        dpos = dpg.get_item_pos(parent)
        dsize = dpg.get_item_rect_size(parent)
    else:
        dpos = dpg.get_viewport_pos()
        dsize = (dpg.get_viewport_width(), dpg.get_viewport_height())

    psize = dpg.get_item_rect_size(window)

    dpg.set_item_pos(
        window,
        (
            dpos[0] + (dsize[0] - psize[0]) / 2,
            dpos[1] + (dsize[1] - psize[1]) / 2,
        ),
    )


def create_value_widget(
    val_idx: int,
    val: Any,
    *,
    choices: dict[int, str] = None,
    callback: Callable[[str, Any, Any], None] = None,
    user_data: Any = None,
    on_enter: bool = False,
    **kwargs,
):
    if user_data is None:
        user_data = val_idx

    if choices and val_idx in choices:
        items = choices[val_idx]
        dpg.add_combo(
            items,
            callback=callback,
            user_data=user_data,
            default_value=items[val if val is not None else 0],
            **kwargs,
        )
    elif val is None or isinstance(val, str):
        dpg.add_input_text(
            callback=callback,
            user_data=user_data,
            default_value=val or "",
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, int):
        dpg.add_input_int(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, float):
        dpg.add_input_float(
            callback=callback,
            user_data=user_data,
            default_value=val,
            on_enter=on_enter,
            **kwargs,
        )
    elif isinstance(val, bool):
        dpg.add_checkbox(
            callback=callback,
            user_data=user_data,
            default_value=val,
            **kwargs,
        )
    else:
        print(f"WARNING cannot handle value {val} with unknown type")


def make_copy_menu(getter: HkbRecord | Callable[[], HkbRecord]) -> None:
    if isinstance(getter, HkbRecord):
        getter = lambda: getter()

    with dpg.menu(label="Copy"):
        dpg.add_selectable(
            label="ID",
            callback=lambda: pyperclip.copy(getter().object_id),
        )
        dpg.add_selectable(
            label="Name",
            callback=lambda: pyperclip.copy(
                getter().get_field("name", "", resolve=True)
            ),
        )
        dpg.add_selectable(
            label="Type Name",
            callback=lambda: pyperclip.copy(getter().type_name),
        )
        dpg.add_selectable(
            label="Type ID",
            callback=lambda: pyperclip.copy(getter().type_id),
        )
        dpg.add_selectable(
            label="XML",
            callback=lambda: pyperclip.copy(getter().xml()),
        )


def estimate_drawn_text_size(
    textlen: int,
    num_lines: int = 1,
    font_size: int = 10,
    scale: float = 1.0,
    margin: int = 5,
) -> tuple[int, int]:
    # TODO 6.5 for 12, around 5.3 for 10?
    w = (textlen * 6.5 + margin * 2) * scale
    h = (font_size * num_lines + margin * 2) * scale
    return w, h


def draw_graph_node(
    lines: list[str],
    *,
    margin: int = 5,
    scale: float = 1.0,
    tag: str = 0,
    parent: str = 0,
) -> tuple[float, float]:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    if isinstance(lines[0], tuple):
        lines, colors = zip(*lines)
    else:
        colors = [style.white] * len(lines)

    max_len = max(len(s) for s in lines)
    lines = [s.center(max_len) for s in lines]

    text_h = 12
    w, h = estimate_drawn_text_size(
        max_len, num_lines=len(lines), font_size=text_h, scale=scale, margin=margin
    )
    text_offset_y = text_h * scale

    with dpg.draw_node(tag=tag, parent=parent):
        # Background
        dpg.draw_rectangle(
            (0.0, 0.0),
            (w, h),
            fill=style.dark_grey,
            color=style.white,
            thickness=1,
            tag=f"{tag}_box",  # for highlighting
        )

        # Text
        for i, text in enumerate(lines):
            dpg.draw_text(
                (margin, margin + text_offset_y * i),
                text,
                size=12 * scale,
                color=colors[i],
            )

    return (w, h)
