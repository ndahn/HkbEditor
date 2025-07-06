from typing import Any, Type, Literal, NewType
from dataclasses import dataclass
import ast
from docstring_parser import parse as parse_docstring, DocstringParam

from hkb_editor.hkb import Tagfile, HkbRecord, HkbArray
from hkb_editor.gui.workflows.undo import undo_manager


@dataclass
class Variable:
    index: int
    name: str


@dataclass
class Event:
    index: int
    name: str


@dataclass
class Animation:
    index: int
    name: str
    full_name: str


class TemplateContext:
    @dataclass
    class _Arg:
        name: str
        type: Type
        value: Any = None
        doc: str = None

    def __init__(self, tagfile: Tagfile, template_file: str):
        self._tagfile = tagfile
        self._template_file = template_file
        self._template_func: ast.FunctionDef = None

        self._title: str = None
        self._description: str = None
        self._args: dict[str, TemplateContext._Arg] = {}

        with open(template_file) as f:
            tree = ast.parse(f, template_file, mode="exec")

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "run":
                    self._template_func = node
                    self._parse_template_func(node)
                    break
            else:
                raise ValueError("Template does not contain a run() function")

    def _parse_template_func(self, func: ast.FunctionDef):
        doc = parse_docstring(ast.get_docstring(func))
        self._title = doc.short_description
        self._description = doc.long_description

        def type_from_str(type_str: str) -> type:
            if type_str.startswith("Literal["):
                # Python 3.9+
                choices = ast.literal_eval(type_str[7:])
                return Literal[tuple(choices)]

            valid = [
                int,
                float,
                bool,
                str,
                Variable,
                Event,
                Animation,
                HkbRecord,
            ]
            return valid[type_str]

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

                try:
                    default = ast.literal_eval(arg_default)
                except ValueError:
                    default = str(arg_default)

                arg_doc = next((p for p in doc.params if p.arg_name == name), None)
                arg_type = get_arg_type(arg, arg_doc, default)

                self._args[name] = TemplateContext._Arg(
                    name,
                    arg_type,
                    default,
                    arg_doc.description if arg_doc else "",
                )

        collect_args(func.args.args, func.args.defaults)
        collect_args(func.args.kwonlyargs, func.args.kw_defaults)

    def find_all(self, query: str) -> list[HkbRecord]:
        return list(self._tagfile.query(query))

    def find(self, query: str, default: Any = None) -> HkbRecord:
        return next(self._tagfile.query(query), default)

    def create(
        self,
        *path_values: tuple[str, Any],
        object_type_name: str,
        object_id: str = None,
        generate_id: bool = True,
        **attributes: Any,
    ) -> HkbRecord:
        type_id = self._tagfile.type_registry.find_first_type_by_name(object_type_name)
        if generate_id:
            object_id = self._tagfile.new_id()

        for path, val in path_values:
            attributes[path] = val

        for key, val in attributes:
            attributes[key] = val

        record = HkbRecord.new(
            self._tagfile, type_id, object_id=object_id, **attributes
        )
        if record.object_id:
            undo_manager.on_create_object(self._tagfile, record)
            self._tagfile.add_object(record)

        return record

    def get(
        self,
        record: HkbRecord | str,
        path: str,
        default: Any = None,
    ) -> Any:
        if isinstance(record, str):
            record = self._tagfile[record]

        return record.get_path_value(path, default=default, resolve=True)

    def set(
        self, record: HkbRecord | str, *path_values: tuple[str, Any], **attributes
    ) -> None:
        if isinstance(record, str):
            record = self._tagfile[record]

        for path, val in path_values:
            attributes[path] = val

        with undo_manager.combine():
            for path, value in attributes:
                handler = record.get_path_value(path)
                undo_manager.on_update_value(handler, handler.get_value(), value)
                handler.set_value(value)

    def delete(self, record: HkbRecord | str) -> HkbRecord:
        if isinstance(record, str):
            record = self._tagfile[record]

        if record.object_id:
            undo_manager.on_delete_object(record)
            return self._tagfile.objects.pop(record.object_id)

        return None

    def array_add(self, record: HkbRecord | str, path: str, item: Any) -> None:
        if isinstance(record, str):
            record = self._tagfile[record]

        array: HkbArray = record.get_path_value(path)
        undo_manager.on_update_array_item(array, -1, None, item)
        array.append(item)

    def array_pop(self, record: HkbRecord | str, path: str, index: int) -> Any:
        if isinstance(record, str):
            record = self._tagfile[record]

        array: HkbArray = record.get_path_value(path)
        undo_manager.on_update_array_item(array, index, array[index], None)
        return array.pop(index).get_value()
