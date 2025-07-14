from typing import Any, Type, Literal
from dataclasses import dataclass
import os
import ast
import logging
import re
from docstring_parser import parse as parse_docstring, DocstringParam

from .common import CommonActionsMixin, Variable, Event, Animation, HkbRecordSpec
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType


_undefined = object()


class TemplateContext(CommonActionsMixin):
    """Stores information and provides helper functions for temapltes.

    Templates are python scripts with a `run` function that takes a `TemplateContext` as their first argument. This object should be the main way of modifying the behavior from templates, primarily to give proper support for undo (or rollback in case of errors).

    Note that this class inherits from :py:class:`CommonActionsMixin` and thus provides many convenience functions for common tasks like creating CMSGs and the likes.

    Raises
    ------
    SyntaxError
        If the template does not contain valid python code.
    ValueError
        If the template is not a valid template file.
    """

    @dataclass
    class _Arg:
        name: str
        type: Type
        value: Any = None
        doc: str = None

    def __init__(self, behavior: HavokBehavior, template_file: str):
        super().__init__(behavior)
        
        self._template_file = template_file
        self._template_func: ast.FunctionDef = None

        self._title: str = None
        self._description: str = None
        self._args: dict[str, TemplateContext._Arg] = {}

        tree = ast.parse(open(template_file).read(), template_file, mode="exec")

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                self._template_func = node
                self._parse_template_func(node)
                break
        else:
            raise ValueError("Template does not contain a run() function")

        self.logger = logging.getLogger(os.path.basename(template_file))

    def _parse_template_func(self, func: ast.FunctionDef):
        doc = parse_docstring(ast.get_docstring(func))
        self._title = doc.short_description
        self._description = doc.long_description

        def type_from_str(type_str: str) -> type:
            if type_str.startswith("Literal["):
                choices = ast.literal_eval(type_str[7:])
                return Literal[tuple(choices)]

            valid = {
                c.__name__: c
                for c in (
                    int,
                    float,
                    bool,
                    str,
                    Variable,
                    Event,
                    Animation,
                    HkbRecord,
                    TemplateContext,
                )
            }
            return valid.get(type_str, type(None))

        def get_arg_type(arg: ast.arg, arg_doc: DocstringParam, default: Any):
            if arg.annotation:
                return type_from_str(ast.unparse(arg.annotation))
            elif arg_doc:
                return type_from_str(arg_doc.type_name)
            elif default is not None:
                return type(default)
            else:
                raise ValueError(f"Type of argument {name} could not be determined")

        def collect_args(args: list[ast.arg], defaults: list[Any]):
            # defaults are specified from the right
            pad = [None] * (len(args) - len(defaults))

            for arg, arg_default in zip(args, pad + defaults):
                name = arg.arg

                default = None
                if arg_default is not None:
                    try:
                        default = ast.literal_eval(arg_default)
                    except ValueError:
                        default = str(arg_default)

                arg_doc = next((p for p in doc.params if p.arg_name == name), None)
                arg_type = get_arg_type(arg, arg_doc, default)

                if arg_type == TemplateContext:
                    continue

                self._args[name] = TemplateContext._Arg(
                    name,
                    arg_type,
                    default,
                    arg_doc.description if arg_doc else "",
                )

        collect_args(func.args.args, func.args.defaults)
        collect_args(func.args.kwonlyargs, func.args.kw_defaults)

    def find_all(self, query: str) -> list[HkbRecord]:
        """Returns all objects matching the specified query.

        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.

        Returns
        -------
        list[HkbRecord]
            A list of matching :py:class:`HkbRecord` objects.
        """
        return list(self._behavior.query(query))

    def find(self, query: str, default: Any = _undefined) -> HkbRecord:
        """Returns the first object matching the specified query.

        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.
        default : Any
            The value to return if no match is found.

        Raises
        ------
        KeyError
            If no match was found and no default was provided.

        Returns
        -------
        HkbRecord
            A matching :py:class:`HkbRecord` object.
        """
        try:
            return next(self._behavior.query(query))
        except StopIteration:
            if default != _undefined:
                return default

            raise KeyError(f"No object matching '{query}'")

    # TODO remove?
    def get(
        self,
        record: HkbRecord | str,
        path: str,
        default: Any = None,
    ) -> Any:
        """Retrieve a value from the specified :py:class:`HkbRecord`.

        Parameters
        ----------
        record : HkbRecord | str
            The record to retrieve a value from.
        path : str
            Member path to the value of interest with deeper levels separated by /.
        default : Any, optional
            A default to return if the path doesn't exist.

        Raises
        ------
        KeyError
            If the specified path does not exist.

        Returns
        -------
        Any
            The value resolved to a regular type (non-recursive).
        """
        record = self._resolve_object(record)
        return record.get_path_value(path, default=default, resolve=True)

    def set(self, record: HkbRecord | str, **attributes) -> None:
        """Update a one or more fields of the specified :py:class:`HkbRecord`.

        Parameters
        ----------
        record : HkbRecord | str
            The record to update.
        attributes : dict[str, Any]
            Keyword arguments of fields and values to set.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        with undo_manager.combine():
            for path, value in attributes.items():
                handler = record.get_path_value(path)
                handler.set_value(value)
                undo_manager.on_update_value(handler, handler.get_value(), value)
                self.logger.debug(f"Updated {path}={value} of {record}")

    def delete(self, record: HkbRecord | str) -> HkbRecord:
        """Delete the specified :py:class:`HkbRecord` from the behavior.

        Parameters
        ----------
        record : HkbRecord | str
            The record to delete.

        Returns
        -------
        HkbRecord
            The record that was deleted.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        if record.object_id:
            self._behavior.objects.pop(record.object_id)
            undo_manager.on_delete_object(record)
            self.logger.debug(f"Deleted object {record}")
            return record

        return None

    def array_add(self, record: HkbRecord | str, path: str, item: Any) -> None:
        """Append a value to an array field of the specified record.

        Note that when appending to pointer arrays you need to pass an object ID, not an actual object.

        Parameters
        ----------
        record : HkbRecord | str
            The record holding the array.
        path : str
            Path to the array within the record, with deeper levels separated by /.
        item : Any
            The item to append to the array.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        array.append(item)
        undo_manager.on_update_array_item(array, -1, None, item)
        self.logger.debug(f"Appended {item} to {path} of {record}")

    def array_pop(self, record: HkbRecord | str, path: str, index: int = -1) -> Any:
        """Remove a value from an array inside a record.

        Parameters
        ----------
        record : HkbRecord | str
            The record holding the array.
        path : str
            Path to the array within the record, with deeper levels separated by /.
        index : int
            The index of the item to pop.

        Returns
        -------
        Any
            The value that was removed from the array.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        ret = array.pop(index).get_value()
        undo_manager.on_update_array_item(array, index, ret, None)
        self.logger.debug(f"Removed item {index} ({ret}) from {path} of {record}")
        return ret

    def variable(
        self,
        name: str,
        *,
        var_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
    ) -> Variable:
        """Get a variable by name, or create it if it doesn't exist yet.

        Variables are typically used to control behaviors from other subsystems like HKS and TAE. See :py:meth:`bind_attribute` for the most common use case.

        Parameters
        ----------
        name : str
            The name of the variable. Must not exist yet.
        var_type : VariableType, optional
            The type of data that will be stored in the variable.
        range_min : int, optional
            Minimum allowed value.
        range_max : int, optional
            Maximum allowed value.

        Returns
        -------
        Variable
            Description of the generated variable.
        """
        try:
            idx = self._behavior.find_variable(name)
        except ValueError:
            var_type = VariableType(var_type)
            idx = self._behavior.create_variable(name, var_type, range_min, range_max)
            undo_manager.on_create_variable(self._behavior, name)
            self.logger.debug(f"Created new variable {name} ({idx}) with type {var_type.name}")

        return Variable(idx, name)

    def event(self, event: str) -> Event:
        """Get the event with the specified name, or create it if it doesn't exist yet.

        Events are typically used to trigger transitions between statemachine states. See :py:meth:`new_statemachine_state` for details.
        TODO mention events.txt

        Parameters
        ----------
        event : str
            The name of the event to create. Typically starts with `W_`.

        Returns
        -------
        Event
            The generated event.
        """
        try:
            idx = self._behavior.find_event(event)
        except ValueError:
            idx = self._behavior.create_event(event)
            undo_manager.on_create_event(self._behavior, event)
            self.logger.debug(f"Created new event {event} ({idx})")

        return Event(idx, event)

    def animation(self, animation: str) -> Animation:
        """Get the animation with the specified name, or create a new one if it doesn't exist yet.

        Animation names must follow the pattern `aXXX_YYYYYY`. Animation names are typically associated with one or more CustomManualSelectorGenerators (CMSG). See :py:meth:`new_cmsg` for details.
        # TODO mention animations.txt

        Parameters
        ----------
        animation : str
            The name of the animation slot following the `aXXX_YYYYYY` pattern.

        Returns
        -------
        Animation
            The generated animation name. Note that the full name is almost never used.
        """
        try:
            idx = self._behavior.find_animation(animation)
        except ValueError:
            if not re.fullmatch(r"a[0-9]{3}_[0-9]{6}", animation):
                raise ValueError(f"Invalid animation name '{animation}'")

            idx = self._behavior.create_animation(animation)
            undo_manager.on_create_animation(self._behavior, animation)
            self.logger.debug(f"Created new animation {animation} ({idx})")

        full_name = self._behavior.get_animation(idx, full_name=True)
        return Animation(idx, animation, full_name)
