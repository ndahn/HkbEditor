from typing import Any, Callable, Literal, get_args as get_choices, get_origin, cast
import os
import logging
import webbrowser
from dearpygui import dearpygui as dpg

from hkb_editor.templates import (
    TemplateContext,
    Variable,
    Event,
    Animation,
)
from hkb_editor.templates.glue import execute_template
from hkb_editor.hkb import Tagfile, HavokBehavior, HkbRecord
from hkb_editor.gui.dialogs import (
    select_variable,
    select_event,
    select_animation_name,
    select_object,
)
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.helpers import center_window, add_paragraphs
from hkb_editor.gui import style


def apply_template_dialog(
    tagfile: Tagfile,
    template_file: str,
    callback: Callable[[str, list[HkbRecord], Any], None] = None,
    *,
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    logger = logging.getLogger(f"{tag}_template_{os.path.basename(template_file)}")
    template = TemplateContext(tagfile, template_file)
    args = {arg.name: arg.value for arg in template._args.values()}

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def open_template_source() -> None:
        webbrowser.open("file:///" + os.path.dirname(template_file))

    def set_arg(sender: str, value: Any, arg: TemplateContext._Arg) -> None:
        if get_origin(arg.type) == Literal:
            # Literal can hold types other than string, but the combo only supports strings
            for choice in get_choices(arg.type):
                if str(choice) == value:
                    value = choice
                    break

        elif arg.type == Variable:
            var_name = cast(HavokBehavior, tagfile).get_variable_name(value)
            value = Variable(value, var_name)
            dpg.set_value(f"{tag}_attribute_{arg.name}", var_name)

        elif arg.type == Event:
            event = cast(HavokBehavior, tagfile).get_event(value)
            value = Event(value, event)
            dpg.set_value(f"{tag}_attribute_{arg.name}", event)

        elif arg.type == Animation:
            anim_short = cast(HavokBehavior, tagfile).get_animation(value, full_name=False)
            anim_long = cast(HavokBehavior, tagfile).get_animation(value, full_name=True)
            value = Animation(value, anim_short, anim_long)
            dpg.set_value(f"{tag}_attribute_{arg.name}", anim_short)

        else:
            # simple types and HkbRecord will just be passed through
            pass

        args[arg.name] = value

    def create_widget(arg: TemplateContext._Arg) -> None:
        # TODO make some of the AttributeWidget functions reusable for this

        # Simple types
        if arg.type == int:
            default = arg.value if isinstance(arg.value, int) else 0
            widget = dpg.add_input_int(
                label=arg.name,
                default_value=default,
                tag=f"{tag}_attribute_{arg.name}",
                callback=set_arg,
                user_data=arg,
            )
        elif arg.type == float:
            default = arg.value if isinstance(arg.value, float) else 0.0
            widget = dpg.add_input_float(
                label=arg.name,
                default_value=default,
                tag=f"{tag}_attribute_{arg.name}",
                callback=set_arg,
                user_data=arg,
            )
        elif arg.type == bool:
            default = arg.value if isinstance(arg.value, bool) else False
            widget = dpg.add_checkbox(
                label=arg.name,
                default_value=default,
                tag=f"{tag}_attribute_{arg.name}",
                callback=set_arg,
                user_data=arg,
            )
        elif arg.type == str:
            default = arg.value if isinstance(arg.value, str) else ""
            widget = dpg.add_input_text(
                label=arg.name,
                default_value=default,
                tag=f"{tag}_attribute_{arg.name}",
                callback=set_arg,
                user_data=arg,
            )

        # Literal
        elif get_origin(arg.type) == Literal:
            choices = [str(c) for c in get_choices(arg.type)]
            default = str(arg.value) if arg.value is not None else ""
            widget = dpg.add_combo(
                choices,
                label=arg.name,
                default_value=default,
                tag=f"{tag}_attribute_{arg.name}",
                callback=set_arg,
                user_data=arg,
            )

        # Common constants
        elif arg.type in (Variable, Event, Animation):
            if not isinstance(tagfile, HavokBehavior):
                raise ValueError("Cannot use this template on a non-behavior tagfile")

            default = ""
            if arg.value is not None:
                if isinstance(arg.value, str):
                    default = arg.value
                elif isinstance(arg.value, int):
                    if arg.type == Variable:
                        default = tagfile.get_variable_name(arg.value)
                    elif arg.type == Event:
                        default = tagfile.get_event(arg.value)
                    elif arg.type == Animation:
                        default = tagfile.get_short_animation_name(arg.value)
                elif isinstance(arg.value, (Animation, Event, Animation)):
                    if tagfile.find_variable(arg.value, None):
                        default = arg.value.name

            if arg.type == Variable:
                selector = select_variable
            elif arg.type == Event:
                selector = select_event
            elif arg.type == Animation:
                selector = select_animation_name

            with dpg.group(horizontal=True) as widget:
                dpg.add_input_text(
                    readonly=True,
                    default_value=default,
                    tag=f"{tag}_attribute_{arg.name}",
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: selector(tagfile, set_arg, user_data=u),
                    user_data=arg,
                )
                dpg.add_text(arg.name)

        elif arg.type == HavokBehavior:
            default = str(arg.value) if arg.value is not None else ""

            with dpg.group(horizontal=True) as widget:
                dpg.add_input_text(
                    readonly=True,
                    default_value=default,
                    tag=f"{tag}_attribute_{arg.name}",
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Right,
                    callback=lambda s, a, u: select_object(
                        tagfile, None, set_arg, user_data=u
                    ),
                    user_data=arg,
                )
                dpg.add_text(arg.name)

        else:
            show_warning(f"Argument {arg.name} has unhandled type {arg.type.__name__}")
            return

        if arg.doc:
            with dpg.tooltip(widget):
                dpg.add_text(arg.doc)

    def on_okay() -> None:
        dpg.hide_item(f"{tag}_notification")

        undo_top = undo_manager.top()

        try:
            with undo_manager.combine():
                execute_template(template, **args)
        except Exception as e:
            # Undo any changes that might have already happened
            if undo_top != undo_manager.top():
                undo_manager.undo()

            logger.error(f"Template failed: {str(e)}", exc_info=e)
            show_warning(f"Template failed: {str(e)}")
        else:
            if callback:
                callback(window, template._created_objects, user_data)

            dpg.delete_item(window)

    with dpg.window(
        label=template._title,
        width=400,
        height=600,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        # Description first
        add_paragraphs(template._description, color=style.light_blue)

        # Open the source file
        dpg.add_button(label="Source", callback=open_template_source)

        dpg.add_separator()

        # Parameters required to run the template
        for arg in template._args.values():
            create_widget(arg)

        dpg.add_separator()

        # Notification
        dpg.add_text(show=False, tag=f"{tag}_notification", color=(255, 0, 0))

        # Buttons
        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(window),
            )
            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )

    dpg.split_frame()
    center_window(window)
    return window
