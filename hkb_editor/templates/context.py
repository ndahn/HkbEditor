from typing import Any, Type, Literal
from dataclasses import dataclass
import os
import ast
import logging
from enum import Enum, Flag
from docstring_parser import parse as parse_docstring, DocstringParam

from .common import CommonActionsMixin, Variable, Event, Animation
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray


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

        self._title: str = os.path.basename(template_file)
        self._description: str = None
        self._args: dict[str, TemplateContext._Arg] = {}

        tree = ast.parse(open(template_file).read(), template_file, mode="exec")

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                self._template_func = node
                self._parse_template_func(node, tree)
                break
        else:
            raise ValueError("Template does not contain a run() function")

        self.logger = logging.getLogger(os.path.basename(template_file))
        
    def _parse_template_func(self, func: ast.FunctionDef, module_ast: ast.Module = None):
        doc = parse_docstring(ast.get_docstring(func))
        self._title = doc.short_description
        self._description = doc.long_description
        
        # For cases where a class has been imported under an alias (import X as Y)
        import_map = {}
        if module_ast:
            for node in ast.walk(module_ast):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name
                        import_map[name] = (alias.name, alias.name.split('.')[-1])
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        local_name = alias.asname or alias.name
                        import_map[local_name] = (module, alias.name)
        
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
            
            if type_str in valid:
                return valid[type_str]
            
            # Try to resolve enum/flag from imports
            if type_str in import_map:
                module_path, original_name = import_map[type_str]
                try:
                    module = __import__(module_path, fromlist=[original_name])
                    resolved = getattr(module, original_name)
                    if isinstance(resolved, type) and issubclass(resolved, (Enum, Flag)):
                        return resolved
                except (ImportError, AttributeError):
                    pass
            
            return type(None)
        
        def get_arg_type(arg: ast.arg, arg_doc: DocstringParam, default: Any):
            if arg.annotation:
                return type_from_str(ast.unparse(arg.annotation))
            elif arg_doc:
                return type_from_str(arg_doc.type_name)
            elif default is not None:
                return type(default)
            else:
                raise ValueError(f"Type of argument {arg.arg} could not be determined")
        
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
                        default_str = ast.unparse(arg_default)

                        # Might be an Enum or Flag member
                        if "." in default_str:
                            type_name, member_name = default_str.rsplit(".", 1)
                            if type_name in import_map:
                                module_path, original_name = import_map[type_name]
                                try:
                                    module = __import__(module_path, fromlist=[original_name])
                                    enum_class = getattr(module, original_name)
                                    default = getattr(enum_class, member_name)
                                except (ImportError, AttributeError):
                                    default = default_str
                            else:
                                default = default_str
                        else:
                            default = default_str

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

    def find_all(self, *query: str, start_from: HkbRecord | str = None) -> list[HkbRecord]:
        """Returns all objects matching the specified query.

        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.
        start_from : HkbRecord | str
            Only search part of the hierarchy starting at this node.

        Returns
        -------
        list[HkbRecord]
            A list of matching :py:class:`HkbRecord` objects.
        """
        return list(self._behavior.query(" ".join(query), search_root=start_from))

    def find(self, *query: str, default: Any = _undefined, start_from: HkbRecord | str = None) -> HkbRecord:
        """Returns the first object matching the specified query.

        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.
        default : Any
            The value to return if no match is found.
        start_from : HkbRecord | str
            Only search part of the hierarchy starting at this node.

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
            return next(self._behavior.query(" ".join(query), search_root=start_from))
        except StopIteration:
            if default != _undefined:
                return default

            raise KeyError(f"No object matching '{query}'")

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
        record = self.resolve_object(record)
        return record.get_field(path, default=default, resolve=True)

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
                handler = record.get_field(path)
                
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
        record = self.resolve_object(record)

        if record.object_id:
            self._behavior.delete_object(record)
            undo_manager.on_delete_object(self._behavior, record)
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
        record = self.resolve_object(record)
        array: HkbArray = record.get_field(path)

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
        record = self.resolve_object(record)
        array: HkbArray = record.get_field(path)

        ret = array.pop(index).get_value()
        undo_manager.on_update_array_item(array, index, ret, None)
        self.logger.debug(f"Removed item {index} ({ret}) from {path} of {record}")
        
        return ret
