from typing import Any, Callable
from dearpygui import dearpygui as dpg
import re
import networkx as nx

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.gui.helpers import add_paragraphs, center_window
from hkb_editor.gui import style


def mass_rename_dialog(
    root: HkbRecord,
    callback: Callable[[str, list[HkbRecord], Any], None] = None,
    *,
    initial_search: str = None,
    initial_replace: str = None,
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    def update_preview() -> None:
        search_str = dpg.get_value(f"{tag}_search")
        replace_str = dpg.get_value(f"{tag}_replace")

        try:
            search_pat = re.compile(search_str)
        except re.PatternError:
            dpg.set_value(f"{tag}_preview_output", "<error>")
            return

        txt_in = dpg.get_value(f"{tag}_preview_input")
        preview = re.sub(search_pat, replace_str, txt_in)
        dpg.set_value(f"{tag}_preview_output", preview)

    def show_message(
        msg: str = None, color: tuple[int, int, int, int] = style.red
    ) -> None:
        if msg:
            # TODO log
            dpg.configure_item(
                f"{tag}_notification",
                default_value=msg,
                color=color,
                show=True,
            )
        else:
            dpg.hide_item(f"{tag}_notification")

    def on_okay():
        search_str = dpg.get_value(f"{tag}_search")
        replace_str = dpg.get_value(f"{tag}_replace")

        try:
            search_pat = re.compile(search_str)
        except re.PatternError as e:
            show_message(e.msg)
            return

        show_message()

        tagfile = root.tagfile
        altered = []

        with tagfile.transaction():
            g = tagfile.build_graph(root.object_id)
            for layer in nx.topological_generations(g):
                for nid in layer:
                    node = tagfile.objects[nid]
                    name_field = node.get_field("name", None)
                    if name_field:
                        new_name = re.sub(
                            search_pat, replace_str, name_field.get_value()
                        )
                        name_field.set_value(new_name)
                        altered.append(node)

        if callback:
            callback(tag, altered, user_data)

    def add_tooltip_table(items: list[tuple[str, str]]) -> None:
        with dpg.table(
            header_row=False,
            no_host_extendX=True,
            no_host_extendY=True,
        ):
            dpg.add_table_column()
            dpg.add_table_column()

            for row in items:
                with dpg.table_row():
                    dpg.add_text(row[0])
                    dpg.add_text(row[1])

    # Dialog content
    with dpg.window(
        label="Mass Rename",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        dpg.add_input_text(
            label="Search",
            default_value=initial_search or "",
            callback=update_preview,
            tag=f"{tag}_search",
        )
        with dpg.tooltip(dpg.last_item()):
            add_tooltip_table(
                [
                    ("(abc)", "capture group"),
                    ("(?:abc)", "non-capturing group"),
                    (".", "any character"),
                    ("[abc]", "any of abc")
                    ("\d  \w  \s", "digit, word, space"),
                    ("*  +  ?", "0+, 1+, optional"),
                ]
            )

        dpg.add_input_text(
            label="Replace",
            default_value=initial_replace or "",
            callback=update_preview,
            tag=f"{tag}_replace",
        )
        with dpg.tooltip(dpg.last_item()):
            add_tooltip_table([
                ("\\1 \\2", "insert capture group"),
                ("\\g<0>", "entire match"),
            ])

        dpg.add_text("Try it out!")
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="Test",
                default_value=root["name"].get_value(),
                callback=update_preview,
                tag=f"{tag}_preview_input",
            )
            dpg.add_text("->")
            dpg.add_input_text(
                hint="Preview",
                default_value="",
                enabled=False,
                readonly=True,
                tag=f"{tag}_preview_output",
            )

        dpg.add_spacer(height=3)

        instructions = """\
Use regular expressions to replace parts of record names. Supports capture groups to keep parts of the matched string. Be aware that the names of StateInfos are relevant for HKS!
"""
        add_paragraphs(instructions, 50, color=style.light_blue)

        # Main form done, now just some buttons and such
        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.red)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(dialog),
            )
            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )

    dpg.split_frame()
    center_window(dialog)

    dpg.focus_item(f"{tag}_base_name")
    return dialog
