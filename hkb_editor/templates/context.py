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


_undefined = object()


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

        self._created_objects: list[HkbRecord] = []

        tree = ast.parse(open(template_file).read(), template_file, mode="exec")

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
        return list(self._tagfile.query(query))

    def find(self, query: str, default: Any = _undefined) -> HkbRecord:
        try:
            return next(self._tagfile.query(query))
        except StopIteration:
            if default != _undefined:
                return default

            raise ValueError(f"No object matching '{query}'")

    def create(
        self,
        object_type_name: str,
        *,
        object_id: str = None,
        generate_id: bool = True,
        **attributes: Any,
    ) -> HkbRecord:
        type_id = self._tagfile.type_registry.find_first_type_by_name(object_type_name)
        if generate_id:
            object_id = self._tagfile.new_id()

        record = HkbRecord.new(
            self._tagfile, type_id, path_values=attributes, object_id=object_id
        )
        if record.object_id:
            self._tagfile.add_object(record)
            undo_manager.on_create_object(self._tagfile, record)

        self._created_objects.append(record)

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
        self, record: HkbRecord | str, **attributes
    ) -> None:
        if isinstance(record, str):
            record = self._tagfile[record]

        with undo_manager.combine():
            for path, value in attributes.items():
                handler = record.get_path_value(path)
                handler.set_value(value)
                undo_manager.on_update_value(handler, handler.get_value(), value)

    def delete(self, record: HkbRecord | str) -> HkbRecord:
        if isinstance(record, str):
            record = self._tagfile[record]

        if record.object_id:
            self._tagfile.objects.pop(record.object_id)
            undo_manager.on_delete_object(record)
            return record

        return None

    def array_add(self, record: HkbRecord | str, path: str, item: Any) -> None:
        if isinstance(record, str):
            record = self._tagfile[record]

        array: HkbArray = record.get_path_value(path)
        array.append(item)
        undo_manager.on_update_array_item(array, -1, None, item)

    def array_pop(self, record: HkbRecord | str, path: str, index: int) -> Any:
        if isinstance(record, str):
            record = self._tagfile[record]

        array: HkbArray = record.get_path_value(path)
        ret = array.pop(index).get_value()
        undo_manager.on_update_array_item(array, index, ret, None)
        return ret
