from typing import Any, Callable, Literal, Annotated, get_origin, get_args
from enum import Enum, Flag
from functools import partial
import logging
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.templates.common import (
    CommonActionsMixin,
    Variable,
    Event,
    Animation,
)
from hkb_editor.gui import style
from .flags_widget import add_flag_checkboxes


def add_generic_widget(
    value_type: type,
    label: str,
    callback: Callable[[str, str | Any, Any], None],
    *,
    default: Any = None,
    choices: list[str | tuple[str | Any]] = None,
    readonly: bool = False,
    flags_as_int: bool = False,
    accept_on_enter: bool = False,
    not_supported_ok: bool = False,
    parent: str = 0,
    tag: str = 0,
    user_data: Any = None,
    **kwargs,
) -> str:
    """Create an input widget for any simple Python type.

    Handles ``int``, ``float``, ``bool``, ``str``, ``Literal``, ``Enum`` and
    ``Flag``. Anything else raises ``ValueError`` unless ``not_supported_ok``
    is set. See :func:`add_behavior_widget` for the behavior-aware types.

    Parameters
    ----------
    value_type : type
        The type to create a widget for.
    label : str
        Widget label.
    callback : callable
        Called as ``callback(sender, value, user_data)`` on change.
    default : any, optional
        Initial value.
    choices : list, optional
        Turns the widget into a combo. Items may be ``(label, value)`` tuples.
    readonly : bool
        Render the widget disabled.
    flags_as_int : bool
        Render ``Flag`` types as a plain int input instead of checkboxes.
    accept_on_enter : bool
        Only fire ``callback`` once Enter is pressed.
    not_supported_ok : bool
        Return None instead of raising for unsupported types.
    parent : int or str, optional
        Container to add the widget to.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    user_data : any, optional
        Passed through to ``callback``.
    """
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    if isinstance(value_type, type) and issubclass(value_type, Flag):
        if flags_as_int:
            value_type = int
        else:
            # We have specific support for flags already
            return add_flag_checkboxes(
                value_type,
                callback,
                readonly=readonly,
                base_tag=tag,
                parent=parent,
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
    type_origin = get_origin(value_type)
    if type_origin == Literal:
        choices = get_args(value_type)
        items = [str(c) for c in choices]

        if default in choices:
            default = items[choices.index(default)]

        dpg.add_combo(
            items,
            label=label,
            default_value=default if default is not None else "",
            enabled=not readonly,
            callback=callback,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif value_type is int:
        dpg.add_input_int(
            label=label,
            default_value=int(default) if default is not None else 0,
            readonly=readonly,
            enabled=not readonly,
            callback=callback,
            on_enter=accept_on_enter,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif value_type is float:
        dpg.add_input_float(
            label=label,
            default_value=float(default) if default is not None else 0.0,
            readonly=readonly,
            enabled=not readonly,
            callback=callback,
            on_enter=accept_on_enter,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif value_type is bool:
        dpg.add_checkbox(
            label=label,
            default_value=bool(default) if default is not None else False,
            enabled=not readonly,
            callback=callback,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif not type_origin and value_type in (type(None), str):
        dpg.add_input_text(
            label=label,
            default_value=str(default) if default is not None else "",
            readonly=readonly,
            enabled=not readonly,
            callback=callback,
            on_enter=accept_on_enter,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    else:
        if not_supported_ok:
            return None

        raise ValueError(f"Could not handle type {value_type} for {label}")

    return tag


def add_behavior_widget(
    behavior: HavokBehavior,
    value_type: type,
    label: str,
    callback: Callable[[str, str | Any, Any], None],
    *,
    default: Any = None,
    choices: list[str | tuple[str | Any]] = None,
    readonly: bool = False,
    accept_on_enter: bool = False,
    flags_as_int: bool = False,
    parent: str = 0,
    tag: str = 0,
    user_data: Any = None,
    **kwargs,
) -> str:
    """Create an input widget for any type appearing in a behavior.

    Falls back to :func:`add_generic_widget` for the simple types, and adds
    pickers for ``Variable``, ``Event``, ``Animation`` and ``HkbRecord`` plus
    item tables for ``list`` and ``dict``.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior the pickers query for variables, events and animations.
    value_type : type
        The type to create a widget for.
    label : str
        Widget label.
    callback : callable
        Called as ``callback(sender, value, user_data)`` on change.

    See :func:`add_generic_widget` for the remaining parameters.
    """
    # Imported here to break the widgets <-> dialogs cycle
    from hkb_editor.gui.dialogs.find_object_dialog import (
        select_variable,
        select_event,
        select_animation,
        select_object,
    )

    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    # See if a simple widget will suffice first
    widget = add_generic_widget(
        value_type,
        label,
        callback,
        default=default,
        choices=choices,
        readonly=readonly,
        accept_on_enter=accept_on_enter,
        flags_as_int=flags_as_int,
        not_supported_ok=True,
        parent=parent,
        tag=tag,
        user_data=user_data,
        **kwargs,
    )
    if widget is not None:
        return widget

    type_origin = get_origin(value_type)
    type_args = get_args(value_type)

    # Common helper types
    if value_type in (Variable, Event, Animation):
        util = CommonActionsMixin(behavior)
        if value_type == Variable:
            try:
                var_idx = util.variable(default, create=False)
                default = behavior.get_variable(var_idx)
            except Exception:
                pass

            def on_variable_selected(sender: str, var_idx: int, user_data: Any):
                if var_idx is not None:
                    # TODO get_variable returns a HkbVariable, not a Variable! :/
                    variable_name = behavior.get_variable(var_idx).name
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
            except Exception:
                pass

            def on_event_selected(sender: str, evt_idx: int, user_data: Any):
                if evt_idx is not None:
                    event_name = behavior.get_event(evt_idx)
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
            except Exception:
                pass

            def on_animation_selected(sender: str, anim_idx: int, user_data: Any):
                if anim_idx:
                    animation_name = behavior.get_animation(anim_idx)
                    dpg.set_value(f"{tag}_input_helper", animation_name)
                    callback(sender, animation_name, user_data)
                else:
                    dpg.set_value(f"{tag}_input_helper", "")
                    callback(sender, None, user_data)

            selector = partial(select_animation, behavior, on_animation_selected)

        with dpg.group(horizontal=True, parent=parent, tag=tag):
            dpg.add_input_text(
                readonly=readonly,
                default_value=default if default is not None else "",
                callback=callback,
                user_data=user_data,
                tag=f"{tag}_input_helper",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                enabled=not readonly,
                callback=lambda s, a, u: selector(user_data=u),
                user_data=user_data,
            )
            if label:
                dpg.add_text(label)

    # Item tables
    elif type_origin is list or value_type is list:
        from .editable_table import add_simple_items_table

        if type_args:
            item_type = type_args[0]
        elif default:
            item_type = type(default[0])
        else:
            item_type = str

        add_simple_items_table(
            behavior,
            {"value": item_type},
            lambda: (None,),
            callback,
            initial_values=default,
            label=label,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )
    elif type_origin is dict or value_type is dict:
        from .editable_table import add_simple_items_table

        if type_args:
            key_type, val_type = type_args
        elif default:
            key_type = type(next(iter(default.keys())))
            val_type = type(next(iter(default.values())))
        else:
            key_type = val_type = str

        add_simple_items_table(
            behavior,
            {"key": key_type, "value": val_type},
            lambda: (None, None),
            callback,
            initial_values=default,
            label=label,
            parent=parent,
            tag=tag,
            user_data=user_data,
            **kwargs,
        )

    # Select an object
    elif value_type == HkbRecord or (
        type_origin == Annotated and type_args[0] == HkbRecord
    ):
        record_type_id = None
        record_filter = None

        if type_args:
            if len(type_args) > 1:
                record_type_id = behavior.type_registry.find_first_type_by_name(
                    type_args[1]
                )

            if len(type_args) > 2:
                record_filter = type_args[2]

        def on_object_selected(sender: str, record: HkbRecord, cb_user_data: Any):
            oid = record.object_id if record else ""
            dpg.set_value(f"{tag}_input_helper", oid)
            callback(sender, record, user_data)

        def open_object_selector(sender: str, app_data: str, user_data: Any):
            select_object(
                behavior,
                record_type_id,
                on_object_selected,
                include_derived=True,
                initial_filter=record_filter,
                title=f"Select target for {label}",
            )

        if isinstance(default, str):
            default = next(behavior.query(default), None)

        if isinstance(default, HkbRecord):
            default = default.object_id

        with dpg.group(horizontal=True, parent=parent, tag=tag):
            dpg.add_input_text(
                readonly=readonly,
                default_value=str(default) if default is not None else "",
                tag=f"{tag}_input_helper",
            )
            dpg.bind_item_theme(dpg.last_item(), style.themes.pointer_attribute)
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                enabled=not readonly,
                callback=open_object_selector,
            )
            dpg.add_text(label)

    else:
        logging.getLogger(__name__).warning(
            f"Cannot create widget for value {default} with unexpected type "
            f"{type(default).__name__}"
        )
        return None

    return tag
