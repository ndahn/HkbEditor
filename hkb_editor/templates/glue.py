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


def get_templates() -> dict[str, tuple[tuple[str, ...], str]]:
    tdir = templates_dir()
    ret = []

    for dirpath, subdirs, files in os.walk(tdir, topdown=True):
        subpath = dirpath[len(tdir) :]
        if subpath:
            categories = subpath.split(os.path.sep)
        else:
            categories = ()

        for file in files:
            if file == "example.py":
                continue

            path = os.path.join(dirpath, file)
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
                                ret.append((categories, doc.short_description, path))
                            else:
                                ret.append(
                                    (categories, os.path.splitext(file)[0], path)
                                )

                            break
                    else:
                        # TODO logging.getLogger().warning, see below
                        print(f"{file} is not a valid template")
            except Exception as e:
                # TODO logging.getLogger().error needs logging with a QueueHandler
                print(f"Loading template {file} failed: {e}")
                continue

    if ret:
        # Remove cateogires if they are all the same
        # cat0 = ret[0][0]
        # if all(t[0] == cat0 for t in ret):
        #     ret = [((), t[1], t[2]) for t in ret]
        # else:

        # Sort items with categories first
        ret.sort(key=lambda x: (x[0] == (), x[0], x[1:]))

    return {path: (categories, template) for categories, template, path in ret}


def execute_template(context: TemplateContext, **args) -> Any:
    # Load the template so we can execute its main function
    spec = importlib.util.spec_from_file_location("mod", context._template_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_func = getattr(mod, "run")

    return run_func(context, **args)
