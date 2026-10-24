"""Generates hkb_editor/hkb/hk2014_kb.py, the type knowledge base used by tagfile_convert.

2014 packfiles do not contain any type information, so the converter uses the type
definitions found in hk2018 tagfiles (Nightreign, Elden Ring, Sekiro, ...) to type
everything it can recognize. Only the type definitions go into the knowledge base,
no object data.

Usage (from the repository root):
    python devel/gen_hk2014_kb.py test/c0000_nightreign.xml test/c0000_er.xml test/c0000_sekiro.xml

Earlier files take precedence over later ones if they define the same type.

Type expressions
----------------
Template types are written as expressions, since the same template (e.g. hkArray) is
instantiated many times with different parameters:

    hkArray<X>           array of X (the allocator parameter is implied)
    hkRefPtr<X>, T*<X>   pointers to X
    hkEnum<E,S>          enum E with storage type S
    hkFlags<E,S>         flags E with storage type S

Everything else is referred to by its plain name. Names are unique among the
non-template types.
"""

import sys
import pprint
from pathlib import Path

from lxml import etree


TEMPLATES = ("hkArray", "hkRefPtr", "T*", "hkEnum", "hkFlags")
# Not supported by the converter, and not useful for 2014 behaviors anyway
SKIP_TYPES = ("T[N]", "hkReflect::Type", "hkReflect::QualifiedType", "hkReflect::Any")
# Fields that exist in 2018 only
SKIP_FIELDS = (("hkReferencedObject", "propertyBag"),)


class Source:
    """Wrapper around the type section of a tagfile."""

    def __init__(self, path: str):
        root = etree.parse(path).getroot()
        self.types = {t.get("id"): t for t in root.findall("type")}

    def name(self, tid: str) -> str:
        return self.types[tid].find("name").get("value")

    def attr(self, tid: str, tag: str, key: str = "value"):
        el = self.types[tid].find(tag)
        return el.get(key) if el is not None else None

    def params(self, tid: str) -> list[str]:
        el = self.types[tid].find("parameters")
        if el is None:
            return []
        return [p.get("id") for p in el.findall("typeparam")]

    def expr(self, tid: str | None) -> str | None:
        if tid is None:
            return None

        name = self.name(tid)
        if name not in TEMPLATES:
            return name

        params = self.params(tid)
        if not params and self.attr(tid, "subtype", "id"):
            params = [self.attr(tid, "subtype", "id")]

        if name == "hkArray":
            params = params[:1]
        elif name in ("hkRefPtr", "T*"):
            params = params[:1]

        if not params or any(p is None for p in params):
            raise ValueError(f"Cannot build expression for {name} ({tid})")

        return f"{name}<{','.join(self.expr(p) for p in params)}>"


def collect(src: Source, kb: dict[str, dict]) -> None:
    done = set()
    todo = list(src.types.keys())

    while todo:
        tid = todo.pop()
        if tid in done:
            continue
        done.add(tid)

        name = src.name(tid)
        if name in TEMPLATES or name in SKIP_TYPES:
            continue

        # Expressions in fields mention templates, but not their parameters' types,
        # so everything is visited anyway
        if name in kb:
            continue

        info = {}

        parent = src.attr(tid, "parent", "id")
        if parent:
            info["parent"] = src.expr(parent)

        fmt = src.attr(tid, "format")
        if fmt is not None:
            info["format"] = int(fmt)

        subtype = src.attr(tid, "subtype", "id")
        if subtype:
            info["subtype"] = src.expr(subtype)

        params = src.params(tid)
        if params:
            if any(p is None for p in params):
                continue
            info["params"] = [src.expr(p) for p in params]

        version = src.attr(tid, "version")
        if version is not None:
            info["version"] = int(version)

        flags = src.attr(tid, "flags")
        if flags is not None:
            info["flags"] = int(flags)

        fields_el = src.types[tid].find("fields")
        if fields_el is not None:
            fields = []
            for f in fields_el.findall("field"):
                if (name, f.get("name")) in SKIP_FIELDS:
                    continue
                if src.name(f.get("typeid")) in SKIP_TYPES:
                    continue
                fields.append((f.get("name"), src.expr(f.get("typeid")), int(f.get("flags"))))
            info["fields"] = fields

        kb[name] = info


def prune(
    kb: dict[str, dict], keep_prefixes: tuple[str, ...], keep_names: tuple[str, ...]
) -> dict[str, dict]:
    """Drop everything that is not reachable from the types we care about."""

    def refs(info: dict) -> set[str]:
        found = set()

        def scan(expr: str | None) -> None:
            if not expr:
                return
            # Split the expression into names
            token = ""
            for ch in expr + "<":
                if ch in "<>,":
                    if token:
                        found.add(token)
                    token = ""
                else:
                    token += ch

        scan(info.get("parent"))
        scan(info.get("subtype"))
        for p in info.get("params", []):
            scan(p)
        for _, expr, _ in info.get("fields", []):
            scan(expr)
        return found

    todo = [n for n in kb if n.startswith(keep_prefixes) or n in keep_names]
    reachable = set()

    while todo:
        name = todo.pop()
        if name in reachable or name not in kb:
            continue
        reachable.add(name)
        todo.extend(refs(kb[name]))

    return {n: kb[n] for n in kb if n in reachable}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    kb: dict[str, dict] = {}
    for path in sys.argv[1:]:
        collect(Source(path), kb)

    # The names are required to instantiate the templates
    kb = prune(
        kb,
        ("hkb", "Custom", "hka", "hkRootLevelContainer"),
        ("int", "char", "hkContainerHeapAllocator", "hkStringPtr", "hkRefVariant"),
    )
    kb = dict(sorted(kb.items()))

    out = Path(__file__).parent.parent / "hkb_editor" / "hkb" / "hk2014_kb.py"
    with out.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write(
            '"""Type knowledge base for tagfile_convert.\n\n'
            "AUTO-GENERATED by devel/gen_hk2014_kb.py, do not edit by hand.\n"
            "See that script for details on the format.\n"
            '"""\n\n'
        )
        fp.write("TEMPLATES = %r\n\n" % (TEMPLATES,))
        fp.write("TYPES = ")
        fp.write(pprint.pformat(kb, width=100, sort_dicts=False, compact=True))
        fp.write("\n")

    print(f"Wrote {len(kb)} types to {out}")


if __name__ == "__main__":
    main()
