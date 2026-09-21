from typing import Any, Literal, get_args as get_choices, get_origin
from enum import Enum, Flag
import logging

from hkb_editor.templates import (
    TemplateContext,
    Variable,
    Event,
    Animation,
)
from hkb_editor.templates.glue import execute_template
from hkb_editor.hkb import HavokBehavior, HkbRecord


def coerce_template_arg(arg_type: type, value: Any) -> Any:
    """Turn a widget value back into what the template argument expects.

    Combos hand back strings, so Literal and Enum arguments have to be looked
    up again. Simple types and HkbRecord pass through unchanged.
    """
    origin = get_origin(arg_type) or arg_type

    if origin == Literal:
        if value is None:
            return None

        # Literal can hold types other than string, but the combo only
        # supports strings
        for choice in get_choices(origin):
            if str(choice) == value:
                return choice

        return value

    if isinstance(origin, type) and issubclass(origin, (Enum, Flag)):
        return origin[value].value

    return value


def apply_template(
    behavior: HavokBehavior,
    template: TemplateContext,
    args: dict[str, Any],
    logger: logging.Logger = None,
) -> list[HkbRecord]:
    """Run a template and return the objects it created.

    Argument values are resolved to the types the template expects first.
    On failure any changes already recorded are undone and the original
    exception is re-raised.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to modify.
    template : TemplateContext
        The loaded template.
    args : dict
        Maps argument name to its ``TemplateContext._Arg``.
    logger : logging.Logger, optional
        Where to report progress; defaults to the module logger.

    Returns
    -------
    list of HkbRecord
        Objects added to the behavior, in creation order.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    prev_undo = behavior.top_undo_id()
    last_obj_id = next(reversed(behavior.objects.keys()))

    logger.debug("======================================")
    logger.info(f"Executing template '{template._title}'")

    try:
        with behavior.transaction():
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
                elif arg.type == HkbRecord:
                    arg.value = template.resolve_object(arg.value)

            execute_template(template, **{k: a.value for k, a in args.items()})
    except Exception:
        # Undo any changes that might have already happened
        if prev_undo != behavior.top_undo_id():
            behavior.undo()
            logger.warning("All recorded changes undone")

        raise

    logger.info(f"Template '{template._title}' finished successfully")

    # Dicts retain insertion order, so anything after the previous last key is new
    new_objects = []
    for oid in reversed(behavior.objects.keys()):
        if oid == last_obj_id:
            break
        new_objects.append(behavior.objects[oid])
    new_objects.reverse()

    return new_objects
