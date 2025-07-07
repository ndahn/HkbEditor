from typing import Any
import sys
import os
import logging
import ast
import importlib.util
from docstring_parser import parse as parse_doc

from .context import TemplateContext


def templates_dir() -> str:
    return os.path.join(os.path.dirname(sys.argv[0]), "templates/")


def get_templates() -> dict[str, str]:
    tdir = templates_dir()
    templates = sorted(os.listdir(tdir))
    ret = {}

    for file in templates:
        if file == "example.py":
            continue

        path = os.path.join(tdir, file)
        if not file.endswith(".py") or not os.path.isfile(path):
            continue

        try:
            with open(path) as f:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == "run":
                        docstring = ast.get_docstring(node) or ""
                        doc = parse_doc(docstring)
                        
                        if doc and doc.short_description:
                            ret[path] = doc.short_description
                        else:
                            ret[path] = os.path.splitext(file)[0]

                        break
                else:
                    # TODO logging.getLogger().warning, see below
                    print(f"{file} is not a valid template")
        except Exception as e:
            # TODO logging.getLogger().error needs logging with a QueueHandler
            print(f"Loading template {file} failed: {e}")
            continue

    return ret


def execute_template(context: TemplateContext, **args) -> Any:
    # Load the template so we can execute its main function
    spec = importlib.util.spec_from_file_location("mod", context._template_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_func = getattr(mod, "run")

    return run_func(context, **args)
