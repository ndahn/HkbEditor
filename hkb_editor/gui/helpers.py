from typing import Any, Callable, Type, Literal, get_origin, get_args
from enum import IntFlag, Enum, Flag
from functools import partial
import re
import logging
import textwrap
import webbrowser
from dearpygui import dearpygui as dpg
import pyperclip
from natsort import natsorted

from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.templates.common import (
    CommonActionsMixin,
    Variable,
    Event,
    Animation,
)

from . import style


url_regex = r"https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)"


def center_window(window: str, parent: str = None) -> None:
    if parent:
        dpos = dpg.get_item_pos(parent)
        dsize = dpg.get_item_rect_size(parent)
    else:
        dpos = (0.0, 0.0)
        dsize = (dpg.get_viewport_width(), dpg.get_viewport_height())

    psize = dpg.get_item_rect_size(window)

    dpg.set_item_pos(
        window,
        (
            dpos[0] + (dsize[0] - psize[0]) / 2,
            dpos[1] + (dsize[1] - psize[1]) / 2,
        ),
    )


def create_simple_value_widget(
    value_type: type,
    label: str,
    callback: Callable[[str, str | Any, Any], None],
    *,
    default: Any = None,
    choices: list[str | tuple[str | Any]] = None,
    flags_as_int: bool = False,
    accept_on_enter: bool = False,
    tag: str = 0,
    user_data: Any = None,
    **kwargs,
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if isinstance(value_type, type) and issubclass(value_type, Flag):
        if flags_as_int:
            value_type = int
        else:
            # We have specific support for flags already
            return create_flag_checkboxes(
                value_type,
                callback,
                base_tag=tag,
                active_flags=default if default is not None else 0,
                user_data=user_data,
            )

    # Support enums by extracting their choices
    if isinstance(value_type, type) and issubclass(value_type, Enum):
        choices = [(v.name, v.value) for v in value_type]
        if default is not None and not isinstance(default, str):
            default = value_type(default).name

    # If choices is provided we treat this as a Literal
    if choices:
        orig_callback = callback
        items = [x[0] if isinstance(x, tuple) else x for x in choices]

        def new_callback(sender: str, data: str, cb_user_data: Any):
            # Find the selected item in the original choices list
            index = items.index(data)
            selected = choices[index]

            # If a tuple was provided the first element is only a label,
            # the actual value is in the second element
            if isinstance(selected, tuple):
                selected = selected[1]

            orig_callback(sender, selected, user_data)

        value_type = Literal[tuple(items)]
        callback = new_callback

    # The simple types
    if get_origin(value_type) == Literal:
        choices = get_args(value_type)
        items = [str(c) for c in choices]

        if default in choices:
            default = items[choices.index(default)]

        dpg.add_combo(
            items,
            label=label,
            default_value=default if default is not None else "",
            callback=callback,
            tag=tag,
            **kwargs,
            user_data=user_data,
        )
    elif value_type == int:
        dpg.add_input_int(
            label=label,
            default_value=default or 0,
            callback=callback,
            on_enter=accept_on_enter,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif value_type == float:
        dpg.add_input_float(
            label=label,
            default_value=default or 0.0,
            callback=callback,
            on_enter=accept_on_enter,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif value_type == bool:
        dpg.add_checkbox(
            label=label,
            default_value=default or False,
            callback=callback,
            tag=tag,
            **kwargs,
            user_data=user_data,
        )
    elif value_type in (type(None), str):
        dpg.add_input_text(
            label=label,
            default_value=default or "",
            callback=callback,
            on_enter=accept_on_enter,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    else:
        raise ValueError(f"Could not handle type {value_type} for {label}")

    return tag


def create_value_widget(
    behavior: HavokBehavior,
    value_type: type,
    label: str,
    callback: Callable[[str, str | Any, Any], None],
    *,
    default: Any = None,
    choices: list[str | tuple[str | Any]] = None,
    accept_on_enter: bool = False,
    flags_as_int: bool = False,
    tag: str = 0,
    user_data: Any = None,
    **kwargs,
) -> str:
    from hkb_editor.gui.dialogs import (
        select_variable,
        select_event,
        select_animation,
        select_object,
    )

    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    # See if a simple widget will suffice first
    try:
        return create_simple_value_widget(
            value_type,
            label,
            callback,
            default=default,
            choices=choices,
            accept_on_enter=accept_on_enter,
            flags_as_int=flags_as_int,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    except ValueError:
        pass

    # Common helper types
    if value_type in (Variable, Event, Animation):
        util = CommonActionsMixin(behavior)
        if value_type == Variable:
            try:
                var_idx = util.variable(default, create=False)
                default = behavior.get_variable(var_idx)
            except:
                pass

            def on_variable_selected(sender: str, variable: int, user_data: Any):
                if variable is not None:
                    variable_name = behavior.get_variable(variable)
                    dpg.set_value(f"{tag}_input_helper", variable_name)
                    callback(sender, variable_name, user_data)
                else:
                    dpg.set_value(f"{tag}_input_helper", "")
                    callback(sender, None, user_data)

            selector = partial(select_variable, behavior, on_variable_selected)

        elif value_type == Event:
            try:
                event_idx = util.event(default, create=False)
                default = behavior.get_event(event_idx)
            except:
                pass

            def on_event_selected(sender: str, event: int, user_data: Any):
                if event is not None:
                    event_name = behavior.get_event(event)
                    dpg.set_value(f"{tag}_input_helper", event_name)
                    callback(sender, event_name, user_data)
                else:
                    dpg.set_value(f"{tag}_input_helper", "")
                    callback(sender, None, user_data)

            selector = partial(select_event, behavior, on_event_selected)

        elif value_type == Animation:
            try:
                anim_idx = util.animation(default)
                default = behavior.get_animation(anim_idx)
            except:
                pass

            def on_animation_selected(sender: str, animation: int, user_data: Any):
                if animation:
                    animation_name = behavior.get_animation(animation)
                    dpg.set_value(f"{tag}_input_helper", animation_name)
                    callback(sender, animation_name, user_data)
                else:
                    dpg.set_value(f"{tag}_input_helper", "")
                    callback(sender, None, user_data)

            selector = partial(select_animation, behavior, on_animation_selected)

        with dpg.group(horizontal=True, tag=tag):
            dpg.add_input_text(
                # readonly=True,
                default_value=default if default is not None else "",
                callback=callback,
                user_data=user_data,
                tag=f"{tag}_input_helper",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda s, a, u: selector(user_data=u),
                user_data=user_data,
            )
            if label:
                dpg.add_text(label)

    # Select an object
    elif value_type == HkbRecord:

        def on_object_selected(sender: str, record: HkbRecord, cb_user_data: Any):
            oid = record.object_id if record else ""
            dpg.set_value(f"{tag}_input_helper", oid)
            callback(sender, record, user_data)

        def open_object_selector(sender: str, app_data: str, user_data: Any):
            select_object(
                behavior,
                None,
                on_object_selected,
                include_derived=True,
                initial_filter="",
                title=f"Select target for {label}",
            )

        with dpg.group(horizontal=True, tag=tag):
            dpg.add_input_text(
                # readonly=True,
                default_value=default if default is not None else "",
                tag=f"{tag}_input_helper",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=open_object_selector,
            )
            dpg.add_text(label)

    else:
        logging.getLogger().warning(
            f"Cannot create widget for value {default} with unexpected type {type(default).__name__}"
        )
        return None

    return tag


def make_copy_menu(
    record_or_getter: HkbRecord | Callable[[], HkbRecord], *, tag: str = 0
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if isinstance(record_or_getter, HkbRecord):
        getter_func = lambda: record_or_getter
    else:
        getter_func = record_or_getter

    with dpg.menu(label="Copy", tag=tag):
        dpg.add_selectable(
            label="ID",
            callback=lambda: pyperclip.copy(getter_func().object_id),
        )
        dpg.add_selectable(
            label="Name",
            callback=lambda: pyperclip.copy(
                getter_func().get_field("name", "", resolve=True)
            ),
        )
        dpg.add_selectable(
            label="Type Name",
            callback=lambda: pyperclip.copy(getter_func().type_name),
        )
        dpg.add_selectable(
            label="Type ID",
            callback=lambda: pyperclip.copy(getter_func().type_id),
        )
        dpg.add_selectable(
            label="XML",
            callback=lambda: pyperclip.copy(getter_func().xml()),
        )

    return tag


def estimate_drawn_text_size(
    textlen: int,
    num_lines: int = 1,
    font_size: int = 10,
    scale: float = 1.0,
    margin: int = 5,
) -> tuple[int, int]:
    # 6.5 for 12, around 5.3 for 10?
    len_est_factor = -0.7 + 0.6 * font_size
    len_est = len_est_factor * textlen

    w = (len_est + margin * 2) * scale
    h = (font_size * num_lines + margin * 2) * scale
    return w, h


def create_flag_checkboxes(
    flag_type: Type[IntFlag],
    callback: Callable[[str, int, Any], None],
    *,
    base_tag: str = None,
    active_flags: int = 0,
    user_data: Any = None,
) -> str:
    if base_tag in (None, 0, ""):
        base_tag = dpg.generate_uuid()

    zero_name = flag_type(0).name or "DISABLED"

    def on_flag_changed(sender: str, checked: bool, flag: IntFlag):
        nonlocal active_flags

        if checked:
            # Checking 0 will disable all other flags
            if flag == 0:
                active_flags = flag_type(0)
            else:
                active_flags |= flag
        else:
            # Prevent disabling 0
            if flag == 0:
                dpg.set_value(f"{base_tag}_{zero_name}", True)
                return

            active_flags &= ~flag

        # Flags are not required to have a 0 mapping
        if dpg.does_item_exist(f"{base_tag}_{zero_name}"):
            # 0 disables all other flags and enables 0
            if active_flags == 0:
                for flag in flag_type:
                    dpg.set_value(f"{base_tag}_{flag.name}", False)
                dpg.set_value(f"{base_tag}_{zero_name}", True)
            # 0 is disabled by any other flag
            else:
                dpg.set_value(f"{base_tag}_{zero_name}", False)

        if callback:
            callback(base_tag, active_flags, user_data)

    def set_from_int(sender: str, new_value: int, user_data: Any):
        new_flags = flag_type(new_value)
        for flag in flag_type:
            active = flag in new_flags
            if flag.value == 0 and new_flags > 0:
                active = False

            dpg.set_value(f"{base_tag}_{flag.name}", active)
            on_flag_changed(sender, active, flag)

    if not isinstance(active_flags, flag_type):
        try:
            active_flags = flag_type(active_flags)
        except ValueError:
            logger = logging.getLogger(__name__)
            logger.error(
                f"{active_flags} is not valid for flag type {flag_type.__name__}"
            )
            active_flags = 0

    with dpg.group():
        for flag in flag_type:
            if flag == 0:
                # 0 is in every flag
                active = active_flags == 0
            else:
                active = flag in active_flags

            dpg.add_checkbox(
                default_value=active,
                callback=on_flag_changed,
                label=flag.name,
                tag=f"{base_tag}_{flag.name}",
                user_data=flag,
            )

    with dpg.popup(dpg.last_container(), min_size=(50, 20)):
        dpg.add_input_int(
            label="from int",
            default_value=active_flags,
            on_enter=True,
            callback=set_from_int,
        )


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


def table_sort(sender: str, sort_specs: tuple[tuple[str, int]], user_data: Any):
    # See https://dearpygui.readthedocs.io/en/latest/documentation/tables.html#sorting
    # Sort_specs scenarios:
    #   1. no sorting -> sort_specs == None
    #   2. single sorting -> sort_specs == [[column_id, direction]]
    #   3. multi sorting -> sort_specs == [[column_id, direction], [column_id, direction], ...]
    #
    # Notes:
    #   1. direction is ascending if == 1
    #   2. direction is ascending if == -1

    if not sort_specs:
        return

    # column id -> index
    cols = dpg.get_item_children(sender, 0)
    col_idx = {cid: i for i, cid in enumerate(cols)}

    rows = list(dpg.get_item_children(sender, 1))
    row_values = {}

    for row in rows:
        row_items = dpg.get_item_children(row, 1)
        values = []
        for cell in row_items:
            if dpg.get_item_configuration(cell).get("span_columns") == True:
                # Selectables that span all columns should only be treated as text
                value = dpg.get_item_label(cell)
            else:
                value = dpg.get_value(cell)

            try:
                # Values like indices and other numbers should not be treated as strings
                value = float(value)
            except:
                pass

            values.append(value)

        row_values[row] = values

    # stable multi-column sort (last spec applied first)
    for col_id, direction in reversed(sort_specs):
        idx = col_idx[col_id]
        rows = natsorted(
            rows,
            key=lambda r: row_values[r][idx],
            reverse=direction < 0,
        )

    dpg.reorder_items(sender, 1, rows)


def common_loading_indicator(label: str, color: tuple[int, int, int, int] = style.red) -> str:
    with dpg.window(
        modal=True,
        min_size=(50, 20),
        no_close=True,
        no_move=True,
        no_collapse=True,
        no_title_bar=True,
        no_resize=True,
        no_scroll_with_mouse=True,
        no_scrollbar=True,
        no_saved_settings=True,
    ) as dialog:
        with dpg.group(horizontal=True):
            dpg.add_loading_indicator(color=color)
            with dpg.group():
                dpg.add_spacer(height=5)
                dpg.add_text(label)

    return dialog
