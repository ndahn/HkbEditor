import math
import re
import textwrap
import webbrowser
from dearpygui import dearpygui as dpg

from hkb_editor.gui.helpers import estimate_drawn_text_size, url_regex


def add_paragraphs(
    text: str,
    line_width: int = 70,
    *,
    margin: tuple[int, int] = (3, 3),
    line_gap: int = 5,
    **textargs,
) -> str:
    # Standard dpg font
    line_height = 13
    paragraph = ""
    section_type = ""
    has_sections = False
    last_line_empty = False

    def place_paragraph():
        nonlocal paragraph
        y = margin[1]

        available_width = line_width
        if has_sections:
            available_width -= 5

        with dpg.child_window(border=False, auto_resize_x=True, auto_resize_y=True):
            # Bullet points
            if section_type == "-":
                for line in paragraph.splitlines():
                    fragments = textwrap.wrap(
                        line,
                        # 2 bullet chars + 3 whitespaces
                        width=available_width - 5,
                        initial_indent="   ",
                        subsequent_indent="   ",
                    )
                    dpg.add_text(
                        fragments[0][5:], pos=(margin[0], y), bullet=True, **textargs
                    )
                    y += line_height + line_gap

                    # Indent subsequent lines if bullet line is too long
                    for frag in fragments[1:]:
                        dpg.add_text(frag, pos=(margin[0], y), **textargs)
                        y += line_height + line_gap

            # Code block the user can copy from
            elif section_type == "```":
                block_width = int(
                    estimate_drawn_text_size(available_width, font_size=line_height)[0]
                    * 0.95
                )
                dpg.add_input_text(
                    default_value=paragraph,
                    readonly=True,
                    multiline=True,
                    width=block_width,
                )

            # Regular paragraph
            else:
                for frag in textwrap.wrap(paragraph, width=available_width):
                    dpg.add_text(frag, pos=(margin[0], y), **textargs)
                    y += line_height + line_gap

        paragraph = ""

    with dpg.child_window(
        border=False, auto_resize_x=True, auto_resize_y=True
    ) as container:
        for line in text.splitlines():
            line = line.strip()

            if section_type == "```":
                # If we are in a code block section, ignore all formatting cases
                # and simply add to the paragraph (or place the paragraph once we
                # reach the code block end)
                if line.startswith("```"):
                    place_paragraph()
                    section_type = ""
                else:
                    paragraph += line + "\n"

            elif line.startswith("```"):
                # Start a new code block
                place_paragraph()
                section_type = "```"

            elif line.startswith(("- ", "* ")):
                # Bullet point
                if section_type != "-":
                    place_paragraph()

                paragraph += line + "\n"
                section_type = "-"

            elif line.startswith("# "):
                # New section header
                if has_sections:
                    dpg.pop_container_stack()

                # Create a new section instead of adding to the paragraph
                section = dpg.add_tree_node(label=line[2:])
                dpg.push_container_stack(section)
                has_sections = True
                section_type = ""

            elif re.match(url_regex, line):
                # Web link
                place_paragraph()
                dpg.add_button(
                    label=line,
                    small=True,
                    callback=lambda s, a, u: webbrowser.open(u),
                    user_data=line,
                )

            elif not line:
                # Empty line
                if paragraph:
                    place_paragraph()
                elif last_line_empty and has_sections:
                    # If this is the second empty line end the section
                    dpg.pop_container_stack()
                    has_sections = False

                # End the previous section whatever it was
                section_type = ""

            else:
                # Need to preserve the newline for code blocks
                paragraph += line + "\n"

            last_line_empty = not bool(line)

        # Place any remaining lines
        place_paragraph()

    if has_sections:
        dpg.pop_container_stack()

    return container


def estimate_paragraph_height(
    text: str,
    line_width: int = 70,
    *,
    margin: tuple[int, int] = (3, 3),
    line_gap: int = 5,
):
    # Standard dpg font
    line_height = 13

    lines = text.split("\n")
    num_lines = 0

    for line in lines:
        num_lines += math.ceil(len(line) / line_width)

    return num_lines * (line_height + line_gap) + margin[1] * 2


def get_paragraph_height(tag: str) -> int:
    par_h = dpg.get_item_rect_size(tag)[1]

    for child in dpg.get_item_children(tag, slot=1):
        par_h += dpg.get_item_rect_size(child)[1]

    return par_h
