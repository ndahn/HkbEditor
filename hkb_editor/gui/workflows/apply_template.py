from typing import Any, Callable, Literal, get_args as get_choices, get_origin
import os
import logging
import webbrowser
from dearpygui import dearpygui as dpg

from hkb_editor.templates import (
    TemplateContext,
    Variable,
    Event,
    Animation,
    HkbRecordSpec,
)
from hkb_editor.templates.glue import execute_template
from hkb_editor.hkb import Tagfile, HavokBehavior, HkbRecord
from hkb_editor.gui.dialogs import (
    select_variable,
    select_event,
    select_animation,
    select_object,
)
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.helpers import center_window, add_paragraphs, create_value_widget
from hkb_editor.gui import style


def apply_template_dialog(
    behavior: HavokBehavior,
    template_file: str,
    callback: Callable[[str, list[HkbRecord], Any], None] = None,
    *,
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    logger = logging.getLogger(f"{tag}_template_{os.path.basename(template_file)}")
    template = TemplateContext(behavior, template_file)
    args = {arg.name: arg for arg in template._args.values()}

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def open_template_source() -> None:
        webbrowser.open("file:///" + os.path.dirname(template_file))

    def set_arg(sender: str, value: Any, arg: TemplateContext._Arg) -> None:
        if get_origin(arg.type) == Literal:
            if value is None:
                return

            # Literal can hold types other than string, but the combo only supports strings
            for choice in get_choices(arg.type):
                if str(choice) == value:
                    value = choice
                    break

        else:
            # simple types and HkbRecord will just be passed through
            pass

        args[arg.name].value = value

    def create_widget(arg: TemplateContext._Arg) -> str:
        widget_tag = f"{tag}_attribute_{arg.name}"

        try:
            widget = create_value_widget(
                behavior,
                arg.type,
                arg.name,
                callback=set_arg,
                default=arg.value,
                tag=widget_tag,
                user_data=arg,
            )
        except ValueError:
            # Refuse to handle the template
            dpg.delete_item(window)
            raise ValueError(f"Template argument {arg.name} has unhandled type {arg.type.__name__}")

        if arg.doc:
            with dpg.tooltip(widget):
                add_paragraphs(arg.doc)

        return widget_tag

    def on_okay() -> None:
        dpg.hide_item(f"{tag}_notification")

        undo_top = undo_manager.top()
        last_obj_id = next(reversed(behavior.objects.keys()))

        try:
            with dpg.window(
                modal=True,
                no_title_bar=True,
                no_background=True,
                no_close=True,
                no_move=True,
                no_resize=True,
                no_collapse=True,
                no_saved_settings=True,
                no_scrollbar=True,
                autosize=True,
            ) as loading_indicator:
                dpg.add_loading_indicator(radius=5)

            dpg.split_frame()
            center_window(loading_indicator, window)

            logger.info(f"Executing template '{template._title}'")

            with undo_manager.combine():
                for arg in args.values():
                    if arg.value in (None, ""):
                        continue
                    
                    # Resolve to the types the template expects
                    if arg.type == Variable:
                        arg.value = template.variable(arg.value)
                    elif arg.type == Event:
                        arg.value = template.event(arg.value)
                    elif arg.type == Animation:
                        arg.value = template.animation(arg.value)

                arg_values = {key: arg.value for key, arg in args.items()}
                execute_template(template, **arg_values)
        except Exception as e:
            logger.error(f"Template failed: {str(e)}", exc_info=e)
            show_warning(f"Template failed: {str(e)}")

            # Undo any changes that might have already happened
            if undo_top != undo_manager.top():
                undo_manager.undo()

            logger.info("All recorded changes undone")
        else:
            logger.info(f"Template '{template._title}' finished successfully")

            # Dicts retain insertion order, so anything after the previous last key is new
            new_objects = []
            for oid in reversed(behavior.objects.keys()):
                if oid == last_obj_id:
                    break
                new_objects.append(behavior.objects[oid])
            new_objects.reverse()

            if callback:
                callback(window, new_objects, user_data)

            dpg.delete_item(window)
        finally:
            dpg.delete_item(loading_indicator)

    widget_zero = None

    with dpg.window(
        label=template._title,
        width=400,
        height=600,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        # Parameters required to run the template
        for arg in template._args.values():
            widget = create_widget(arg)
            if widget_zero is None:
                widget_zero = widget

        dpg.add_separator()

        # Description
        if template._description:
            add_paragraphs(template._description, color=style.light_blue)
        else:
            dpg.add_text("<no description>", color=style.orange)

        # Open the source file
        dpg.add_button(label="Source", callback=open_template_source)

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

    if widget_zero is not None:
        dpg.focus_item(widget_zero)
    
    return window
