from typing import Any, Callable
import os
import logging
import webbrowser
from dearpygui import dearpygui as dpg

from hkb_editor.templates import TemplateContext
from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import (
    DpgItem,
    add_paragraphs,
    add_behavior_widget,
    loading_indicator,
)
from hkb_editor.workflows.apply_template import (
    coerce_template_arg,
    apply_template,
)


class apply_template_dialog(DpgItem):
    """Render a template's arguments as a form and run it.

    One input widget is created per template argument; the widget type comes
    from the argument's annotation. The dialog stays open after a successful
    run so the template can be applied again.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    template_file : str
        Path to the template module.
    callback : callable, optional
        Called as ``callback(tag, new_objects, user_data)`` after a run.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    user_data : any, optional
        Passed through to ``callback``.

    Raises
    ------
    ValueError
        If a template argument has a type no widget can handle.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        template_file: str,
        callback: Callable[[str, list[HkbRecord], Any], None] = None,
        *,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._template_file = template_file
        self._callback = callback
        self._user_data = user_data
        self._window: str = None

        self._logger = logging.getLogger(
            os.path.splitext(os.path.basename(template_file))[0]
        )
        self._template = TemplateContext(behavior, template_file)
        self._args = {arg.name: arg for arg in self._template._args.values()}

        self._build()

    # === Build ========================================================

    def _create_widget(self, arg: TemplateContext._Arg) -> str:
        widget_tag = self._t(f"attribute_{arg.name}")

        try:
            widget = add_behavior_widget(
                self._behavior,
                arg.type,
                arg.name,
                callback=self._on_arg_changed,
                default=arg.value,
                tag=widget_tag,
                user_data=arg,
            )
        except ValueError:
            # Refuse to handle the template
            dpg.delete_item(self._window)
            raise ValueError(
                f"Template argument {arg.name} has unhandled type "
                f"{arg.type.__name__}"
            )

        if arg.doc:
            with dpg.tooltip(widget):
                add_paragraphs(arg.doc)

        return widget_tag

    def _build(self) -> None:
        template = self._template
        widget_zero = None

        with dpg.window(
            label=template._title,
            width=400,
            height=600,
            autosize=True,
            no_saved_settings=True,
            tag=self._tag,
            on_close=lambda: dpg.delete_item(self._window),
        ) as self._window:
            # Parameters required to run the template
            for arg in template._args.values():
                widget = self._create_widget(arg)
                if widget_zero is None:
                    widget_zero = widget

            dpg.add_separator()

            # Description
            if template._description:
                add_paragraphs(template._description, color=style.light_blue)
            else:
                dpg.add_text("<no description>", color=style.orange)

            # Open the source file
            dpg.add_button(label="Source", callback=self._on_open_source)

            dpg.add_separator()

            # Notification
            dpg.add_text(show=False, tag=self._t("notification"), color=style.red)

            # Buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Run Template",
                    callback=self._on_okay,
                    tag=self._t("button_okay"),
                )
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

        center_window(self._window, split_frame=True)

        if widget_zero is not None:
            dpg.focus_item(widget_zero)

    # === DPG callbacks ================================================

    def _on_open_source(self) -> None:
        webbrowser.open("file:///" + os.path.dirname(self._template_file))

    def _on_arg_changed(
        self, sender: str, value: Any, arg: TemplateContext._Arg
    ) -> None:
        self._args[arg.name].value = coerce_template_arg(arg.type, value)

    def _on_okay(self) -> None:
        self.show_message()

        with loading_indicator("Running template...", style.yellow):
            try:
                new_objects = apply_template(
                    self._behavior, self._template, self._args, self._logger
                )
            except Exception as e:
                self._logger.error(
                    f"Template '{self._template._title}' failed: {str(e)}",
                    exc_info=e,
                )
                self.show_message(f"Error: {str(e)}")
                return

        if self._callback:
            self._callback(self._tag, new_objects, self._user_data)

        self.show_message("Success!", style.light_green)
        dpg.configure_item(self._t("button_okay"), label="Again?")

    # === Public =======================================================

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the created objects."""
        return dpg.get_value(self._t("pin_objects"))

    def show_message(self, msg: str = None, color: style.RGBA = style.red) -> None:
        """Show or hide the notification label. Pass ``msg=None`` to hide."""
        if not msg:
            dpg.hide_item(self._t("notification"))
            return

        dpg.configure_item(
            self._t("notification"),
            default_value=msg,
            color=color,
            show=True,
        )
