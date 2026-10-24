"""
hkpackfile (2014) <-> hktagfile v3 (2018) XML converter.

The editor works with the hk2018 format, which is typed: every value in an object
has a type, and the types (with their parent chains, enum parameters etc.) are listed
in the file. Many features of the editor rely on that information, e.g. looking up
objects by class name, offering compatible objects for pointers, or showing enums
as dropdowns.

hk2014 packfiles on the other hand are untyped. A value is just text, and the only
type information available is the class name of the objects. So when converting from
2014 to 2018, the converter has to find out what the types are:

1. The tagfile type definitions of the hkb classes found in the 2018 games (see
   hk2014_kb.py) are used for all classes and fields they recognize. This also takes
   care of the different class names, 2018 nests classes (hkbStateMachine::StateInfo)
   where 2014 concatenates names (hkbStateMachineStateInfo).
2. Everything else is inferred from the data. The values of all instances of a field
   are collected first, so that a field is typed by all of its values and not by
   the first one that happens to come along.

Fields that the knowledge base knows about must match what is in the file, otherwise
the data wins.

2018 -> 2014 is driven by the types stored in the tagfile and does not need any
additional knowledge, except for enum and flag constants (see hk2014_enums.py). A few
2014 specifics that cannot be derived from the 2018 representation are stored in
extra attributes, which the editor passes through:

    <hktagfile hk2014_classversion hk2014_contentsversion hk2014_toplevelobject>
    <type hk_sig="0x1234abcd">      signature of the class, required in hk2014 files

Can also be used as a script, the direction is detected from the input:

    python -m hkb_editor.hkb.tagfile_convert input.xml output.xml

Conventions of the 2014 xml that the converter relies on:
    null / #N       pointer
    true / false    bool
    (x y z w)       fixed size array (vectors, quaternions)
    CONSTANT        enum / flags, only for fields known to be enums
    <hkcstring>     string in an array
    <hkobject>      struct. Has class, name and signature when it is a field of
                    another struct, but has no attributes at all inside of arrays
"""

from __future__ import annotations

import logging
import math
import re
import struct
import sys
from argparse import ArgumentParser
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from lxml import etree

from .hk2014_kb import TYPES as KB
from .hk2014_enums import CONSTANTS, ConstantTable


_logger = logging.getLogger(__name__)


# === type formats ===

FMT_BOOL = 2
FMT_STRING = 3
FMT_INT = 4
FMT_REAL = 5
FMT_POINTER = 6
FMT_RECORD = 7
FMT_ARRAY = 8

# Format: bits 0-3 = kind, bit 9 = signed (ints), bits 10+ = size in bits (ints)
# or (bits 8+) fixed size (arrays)
_INT_SIGNED = 0x200

ROOT_OBJECT = "hkReferencedObject"

# Used when the converter has to come up with a base class
_CLASS_SUFFIXES = (
    ("TransitionEffect", "hkbTransitionEffect"),
    ("Modifier", "hkbModifier"),
    ("Generator", "hkbGenerator"),
    ("Condition", "hkbCondition"),
)

# Types the knowledge base lacks
_SYNTHETIC_TYPES: dict[str, dict] = {
    "hkInt64": {"format": 64 << 10 | _INT_SIGNED | FMT_INT},
}


# === text helpers ===

_INT = re.compile(r"[+-]?\d+")
_REAL = re.compile(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?|[+-]?(?:nan|inf)")
_REF = re.compile(r"#\d+")
_ENUM = re.compile(r"[A-Z_][A-Z0-9_]*(?:\s*\|\s*[A-Z_][A-Z0-9_]*)*")
# (x y z w) (x y z w) ...
_TUPLES = re.compile(r"\s*(?:\([-+0-9.eEnaif\s]*\)\s*)+")
_TUPLE = re.compile(r"\(([^)]*)\)")


def _classify(raw: str) -> str:
    """Guess the kind of value of a scalar from its text."""
    if raw == "":
        return "empty"

    token = raw.strip()
    if token == "":
        return "str"
    if token != raw:
        # Whitespace around other values is not something havok writes
        return "str"
    if token == "null":
        return "null"
    if _REF.fullmatch(token):
        return "ref"
    if token in ("true", "false"):
        return "bool"
    if _INT.fullmatch(token):
        # Leading zeros, plus signs etc. could not be restored
        return "int" if str(int(token)) == token else "str"
    if _REAL.fullmatch(token):
        return "real"
    if _ENUM.fullmatch(token):
        return "enum"
    return "str"


def _f32(value: float) -> float:
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return float("inf") if value > 0 else float("-inf")


# Values that are not written with the shortest possible number of digits
_LONG_FORM_REALS = (2.0**-24, 2.0**-44)


def _format_2014_real(value: float) -> str:
    """Floats in hk2014 xml are floats printed with the precision of doubles.

    The format matches Java's Double.toString: plain decimals from 0.001 to 10 million,
    otherwise scientific notation like 1.5E-7.
    """
    value = _f32(value)

    if not math.isfinite(value):
        return str(value)

    if value == 0:
        return "-0.0" if str(value).startswith("-") else "0.0"

    magnitude = abs(value)
    if magnitude in _LONG_FORM_REALS:
        text = f"{magnitude:.16e}"
    else:
        text = repr(magnitude)

    _, digit_tuple, exponent = Decimal(text).as_tuple()
    digits = "".join(map(str, digit_tuple))
    exp10 = len(digits) + exponent - 1
    digits = digits.rstrip("0") or "0"

    if -3 <= exp10 < 7:
        if exp10 >= 0:
            integral = digits[: exp10 + 1].ljust(exp10 + 1, "0")
            fraction = digits[exp10 + 1 :] or "0"
        else:
            integral = "0"
            fraction = "0" * (-exp10 - 1) + digits
        text = f"{integral}.{fraction}"
    else:
        text = f"{digits[0]}.{digits[1:] or '0'}E{exp10}"

    return f"-{text}" if value < 0 else text


def _format_2018_real(value: float) -> tuple[str, str]:
    """Shortest decimal representation of the float, and the hex of the double."""
    value = _f32(value)
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    hex_str = f"#{bits:x}"

    if not math.isfinite(value):
        return str(value), hex_str

    for precision in range(1, 10):
        text = f"{value:.{precision}g}"
        if _f32(float(text)) == value:
            break

    # Avoid exponents where they are not needed
    return repr(float(text)).removesuffix(".0"), hex_str


def _real_from_element(elem: etree._Element) -> float:
    dec = elem.get("dec")
    if dec:
        return float(dec.replace(",", "."))

    hex_str = elem.get("hex")
    if hex_str:
        return struct.unpack(">d", struct.pack(">Q", int(hex_str.lstrip("#") or "0", 16)))[0]

    return 0.0


def _wrap(tokens: list[str], width: int = 64) -> list[str]:
    """Distribute the values of an array on lines, like havok does."""
    # If the first value is too long, havok starts a new line before it anyway
    rows = [""] if tokens and len(tokens[0]) > width else []
    row = ""

    for token in tokens:
        if row and len(row) + 1 + len(token) > width:
            rows.append(row)
            row = token
        else:
            row = f"{row} {token}" if row else token

    if row:
        rows.append(row)

    return rows


def _parse_xml(data: bytes | str) -> etree._Element:
    if isinstance(data, str):
        parser = etree.XMLParser(encoding="utf-8", remove_comments=True)
        return etree.fromstring(data.encode("utf-8"), parser)

    try:
        return etree.fromstring(data, etree.XMLParser(remove_comments=True))
    except etree.XMLSyntaxError:
        # The declared encoding is not always honest
        return etree.fromstring(
            data, etree.XMLParser(encoding="utf-8", remove_comments=True)
        )


def _read_input(source: Path | str | etree._Element) -> etree._Element:
    if isinstance(source, Path):
        return _parse_xml(source.read_bytes())
    if isinstance(source, etree._Element):
        return source
    return _parse_xml(source)


# === type expressions and knowledge base ===
#
# Types are referred to by expressions, e.g. hkArray<hkRefPtr<hkbGenerator>>.
# See devel/gen_hk2014_kb.py.


def split_expr(expr: str) -> tuple[str, list[str]]:
    """'hkEnum<A,B>' -> ('hkEnum', ['A', 'B'])"""
    start = expr.find("<")
    if start < 0:
        return expr, []

    args = []
    depth = 0
    token_start = start + 1

    for i in range(start + 1, len(expr) - 1):
        ch = expr[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(expr[token_start:i])
            token_start = i + 1

    args.append(expr[token_start:-1])
    return expr[:start], args


def kb_format(name: str) -> int | None:
    """Format of a knowledge base type. Like in the tagfiles, the root parent wins."""
    fmt = None
    seen = set()

    while name in KB and name not in seen:
        seen.add(name)
        info = KB[name]
        if "format" in info:
            fmt = info["format"]
        name = info.get("parent")

    return fmt


def kb_subtype(name: str) -> str | None:
    """Subtype of a knowledge base type. Inherited, e.g. hkVector4 -> hkVector4f."""
    seen = set()

    while name in KB and name not in seen:
        seen.add(name)
        info = KB[name]
        if info.get("subtype"):
            return info["subtype"]
        name = info.get("parent")

    return None


# 2018 nests classes, 2014 concatenates their names
_NESTED_NAMES = {
    name.replace("::", ""): name
    for name in KB
    if "::" in name and kb_format(name) == FMT_RECORD
}


def to_2018_name(class_name: str) -> str:
    return _NESTED_NAMES.get(class_name, class_name)


def to_2014_name(type_name: str) -> str:
    return type_name.replace("::", "")


# === 2014 -> 2018: observing the data ===


def _unpack(param: etree._Element) -> tuple[str, Any]:
    """Split a <hkparam> into its form and content.

    Returns one of
        ("scalar", text)
        ("tuple", [[tokens], ...])                  inline (x y z w), maybe several
        ("struct", <hkobject>)
        ("empty", [])                               array without items
        ("empty_ptr", [])                           same, but havok wrote a line break
        ("structs", [<hkobject>, ...])              arrays
        ("cstrings", [str, ...])
        ("scalars", [token, ...])
        ("tuples", [[[tokens], ...], ...])          every item is a "tuple"
    """
    kids = [c for c in param if isinstance(c.tag, str)]
    numelements = param.get("numelements")
    text = param.text or ""

    if numelements is not None:
        if kids:
            first = kids[0].tag
            if first == "hkobject":
                return "structs", kids
            if first == "hkcstring":
                return "cstrings", [(c.text or "") for c in kids]
            raise ValueError(f"Unexpected <{first}> in array {param.get('name')}")

        if _TUPLES.fullmatch(text):
            groups = [g.split() for g in _TUPLE.findall(text)]

            # Items such as transforms consist of several groups
            count = int(numelements)
            per_item = len(groups) // count if count and len(groups) % count == 0 else 1
            return "tuples", [
                groups[i : i + per_item] for i in range(0, len(groups), per_item)
            ]

        tokens = text.split()
        if tokens:
            return "scalars", tokens

        # Empty pointer arrays are written differently from others. If there are
        # no items to look at, this is the only hint we get.
        return ("empty_ptr" if "\n" in text else "empty"), []

    if kids:
        if kids[0].tag != "hkobject":
            raise ValueError(f"Unexpected <{kids[0].tag}> in {param.get('name')}")
        return "struct", kids[0]

    if _TUPLES.fullmatch(text):
        return "tuple", [g.split() for g in _TUPLE.findall(text)]

    return "scalar", text


class StructInfo:
    """Everything known about a class or an anonymous struct."""

    def __init__(self, class_name: str | None):
        self.class_name = class_name
        self.fields: dict[str, Shape] = {}
        self.signature: str | None = None
        self.type_name: str | None = None
        self.is_object = False

    def observe(self, elem: etree._Element, conv: _To2018) -> None:
        if self.signature is None:
            self.signature = elem.get("signature")

        for param in elem.findall("hkparam"):
            name = param.get("name")
            shape = self.fields.get(name)
            if shape is None:
                shape = self.fields[name] = Shape()
            shape.observe(*_unpack(param), conv)


class Shape:
    """Merged observations of all values that occur at one place in the data.

    After the types have been decided, it also contains the decisions.
    """

    __slots__ = (
        # Observations
        "kinds",
        "tokens",
        "overflow",
        "ptr_hint",
        "refs",
        "int_min",
        "int_max",
        "is_array",
        "elem",
        "tuples",
        "struct",
        "named",
        # Decisions
        "kind",
        "expr",
        "table",
        "kb_source",
        "vec_elem",
        "vec_groups",
    )

    def __init__(self):
        self.kinds: set[str] = set()
        # Text values, to find out if they are enum constants
        self.tokens: set[str] = set()
        self.overflow = False
        # Empty arrays that look like they would contain pointers
        self.ptr_hint = False
        self.refs: set[str] = set()
        self.int_min: int | None = None
        self.int_max: int | None = None
        self.is_array = False
        self.elem: Shape | None = None
        self.tuples: set[tuple[int, ...]] = set()
        self.struct: StructInfo | None = None  # anonymous structs
        self.named: set[str] = set()  # class names of structs

        self.kind: str | None = None
        self.expr: str | None = None
        self.table: ConstantTable | None = None
        self.kb_source: str | None = None
        self.vec_elem: str | None = None
        self.vec_groups = 1

    def only_scalars(self) -> bool:
        return not (self.is_array or self.tuples or self.struct or self.named)

    def observe(self, form: str, data: Any, conv: _To2018) -> None:
        if form == "scalar":
            self._observe_scalar(data)
        elif form == "tuple":
            self.tuples.add(tuple(len(group) for group in data))
        elif form == "struct":
            self._observe_struct(data, conv)
        else:
            self.is_array = True
            if self.elem is None:
                self.elem = Shape()

            if form == "empty_ptr":
                self.elem.ptr_hint = True

            if form in ("empty", "empty_ptr"):
                return

            if form == "structs":
                for item in data:
                    self.elem._observe_struct(item, conv)
            elif form == "tuples":
                for item in data:
                    self.elem.tuples.add(tuple(len(group) for group in item))
            else:
                # Strings and scalars, the former are never interpreted
                for item in data:
                    if form == "cstrings":
                        self.elem.kinds.add("str")
                    else:
                        self.elem._observe_scalar(item)

    def _observe_scalar(self, raw: str) -> None:
        kind = _classify(raw)
        self.kinds.add(kind)

        if kind == "int":
            value = int(raw)
            self.int_min = value if self.int_min is None else min(self.int_min, value)
            self.int_max = value if self.int_max is None else max(self.int_max, value)
        elif kind == "ref":
            self.refs.add(raw)
        elif kind in ("enum", "str"):
            if len(self.tokens) < 64:
                self.tokens.add(raw)
            else:
                self.overflow = True

    def _observe_struct(self, elem: etree._Element, conv: _To2018) -> None:
        class_name = elem.get("class")

        if class_name:
            self.named.add(class_name)
            info = conv.struct_for_class(class_name)
        else:
            if self.struct is None:
                self.struct = StructInfo(None)
            info = self.struct

        info.observe(elem, conv)


# === 2014 -> 2018: type table ===


class TypeTable:
    """Collects the types of the tagfile, identified by type expressions."""

    def __init__(self, local: dict[str, dict]):
        # Types created by the converter, they take precedence over the knowledge base
        self.local = local
        self.ids: dict[str, str] = {}
        self.defs: dict[str, dict] = {}

    def ensure(self, expr: str) -> str:
        """Get the id of a type, creating it if needed."""
        tid = self.ids.get(expr)
        if tid is None:
            tid = f"type{len(self.ids) + 1}"
            self.ids[expr] = tid
            self.defs[tid] = self._define(expr)
        return tid

    def _define(self, expr: str) -> dict:
        name, args = split_expr(expr)

        if name == "hkArray":
            return {
                "name": name,
                "format": FMT_ARRAY,
                "subtype": args[0],
                "params": [args[0], "hkContainerHeapAllocator"],
                "fields": [
                    ("m_data", f"T*^<{args[0]}>", 34),
                    ("m_size", "int", 34),
                    ("m_capacityAndFlags", "int", 34),
                ],
            }

        if name in ("T*", "T*^"):
            # The second kind is used for the data pointer of arrays
            return {
                "name": "T*",
                "format": FMT_POINTER,
                "subtype": args[0],
                "params": [args[0]],
                "flags": 64 if name == "T*^" else 0,
            }

        if name == "hkRefPtr":
            return {
                "name": name,
                "format": FMT_POINTER,
                "subtype": args[0],
                "params": [args[0]],
                "fields": [("ptr", f"T*<{args[0]}>", 36)],
            }

        if name in ("hkEnum", "hkFlags"):
            return {
                "name": name,
                "format": kb_format(args[1]),
                "params": list(args),
                "fields": [("storage", args[1], 36 if name == "hkEnum" else 34)],
            }

        if name in self.local:
            return {"name": name, **self.local[name]}

        if name in KB:
            return {"name": name, **KB[name]}

        if name in _SYNTHETIC_TYPES:
            return {"name": name, **_SYNTHETIC_TYPES[name]}

        raise KeyError(f"Don't know how to define type {expr}")

    def to_xml(self) -> list[etree._Element]:
        elems = []
        done = 0

        # Defining a type may require others
        while done < len(self.defs):
            done += 1
            tid = f"type{done}"
            elems.append(self._type_element(tid, self.defs[tid]))

        return elems

    def _type_element(self, tid: str, info: dict) -> etree._Element:
        elem = etree.Element("type", id=tid)
        etree.SubElement(elem, "name", value=info["name"])

        if info.get("parent"):
            etree.SubElement(elem, "parent", id=self.ensure(info["parent"]))

        if info.get("format") is not None:
            etree.SubElement(elem, "format", value=str(info["format"]))

        if info.get("subtype"):
            etree.SubElement(elem, "subtype", id=self.ensure(info["subtype"]))

        if info.get("params"):
            params = etree.SubElement(
                elem, "parameters", count=str(len(info["params"]))
            )
            for param in info["params"]:
                etree.SubElement(params, "typeparam", id=self.ensure(param))

        if info.get("version") is not None:
            etree.SubElement(elem, "version", value=str(info["version"]))

        if info.get("flags") is not None:
            etree.SubElement(elem, "flags", value=str(info["flags"]))

        if info.get("fields") is not None:
            fields = etree.SubElement(elem, "fields", count=str(len(info["fields"])))
            for name, expr, flags in info["fields"]:
                etree.SubElement(
                    fields,
                    "field",
                    name=name,
                    typeid=self.ensure(expr),
                    flags=str(flags),
                )

        if info.get("sig"):
            elem.set("hk_sig", info["sig"])

        return elem


# === 2014 -> 2018: converter ===


class _To2018:
    def __init__(self, root: etree._Element):
        self.root = root
        self.section = root.find("hksection")
        self.objects = (self.section if self.section is not None else root).findall(
            "hkobject"
        )

        self.structs: dict[str, StructInfo] = {}
        self.anonymous: list[StructInfo] = []
        self.object_classes: dict[str, str] = {}  # #id -> 2018 class name
        self.inferred_parents: dict[str, str] = {}

        self.local: dict[str, dict] = {}
        self.types: TypeTable = None

    # --- hierarchy ---

    def parent_of(self, type_name: str) -> str | None:
        if type_name in KB:
            return KB[type_name].get("parent")
        return self.inferred_parents.get(type_name)

    def chain(self, type_name: str) -> list[str]:
        """The type and its parents."""
        ret = []
        while type_name and type_name not in ret:
            ret.append(type_name)
            type_name = self.parent_of(type_name)
        return ret

    def is_subclass(self, type_name: str, base: str) -> bool:
        return base == ROOT_OBJECT or base in self.chain(type_name)

    def common_class(self, type_names: set[str]) -> str:
        chains = [self.chain(t) for t in type_names]
        if not chains:
            return ROOT_OBJECT

        for candidate in chains[0]:
            if all(candidate in chain for chain in chains[1:]):
                return candidate

        return ROOT_OBJECT

    def pointee_classes(self, shape: Shape) -> set[str]:
        return {
            self.object_classes[ref]
            for ref in shape.refs
            if ref in self.object_classes
        }

    # --- pass 1: observation ---

    def struct_for_class(self, class_name: str) -> StructInfo:
        info = self.structs.get(class_name)
        if info is None:
            info = self.structs[class_name] = StructInfo(class_name)
        return info

    def observe(self) -> None:
        for elem in self.objects:
            class_name = elem.get("class")
            info = self.struct_for_class(class_name)
            info.is_object = True
            info.observe(elem, self)

            self.object_classes[elem.get("name")] = to_2018_name(class_name)

        # Unknown object classes have to derive from somewhere
        for info in self.structs.values():
            type_name = to_2018_name(info.class_name)
            if not info.is_object or type_name in KB:
                continue

            for suffix, base in _CLASS_SUFFIXES:
                if type_name.endswith(suffix) and base in KB:
                    self.inferred_parents[type_name] = base
                    break
            else:
                self.inferred_parents[type_name] = ROOT_OBJECT

    # --- pass 2: type decisions ---

    def describe(self, expr: str) -> dict | None:
        """Describe what kind of value a type expression stands for."""
        name, args = split_expr(expr)

        if name == "hkArray":
            return {"kind": "array", "elem": args[0]}
        if name in ("hkRefPtr", "T*"):
            return {"kind": "ptr", "target": args[0]}
        if name in ("hkEnum", "hkFlags"):
            return {"kind": "enum", "enum": args[0], "storage": args[1]}

        if name in self.local:
            return {"kind": "record"}

        fmt = kb_format(name)
        if fmt is None:
            fmt = _SYNTHETIC_TYPES.get(name, {}).get("format")
            if fmt is None:
                return None

        kind = fmt & 0xF
        if kind == FMT_BOOL:
            return {"kind": "bool"}
        if kind == FMT_STRING:
            return {"kind": "str"}
        if kind == FMT_INT:
            return {"kind": "int", "bits": fmt >> 10, "signed": bool(fmt & _INT_SIGNED)}
        if kind == FMT_REAL:
            return {"kind": "real"}
        if kind == FMT_POINTER:
            return {"kind": "ptr", "target": kb_subtype(name) or ROOT_OBJECT}
        if kind == FMT_RECORD:
            return {"kind": "record", "name": name}
        if kind == FMT_ARRAY:
            fixed = fmt >> 8
            if fixed:
                return {"kind": "vec", "elem": kb_subtype(name), "size": fixed}
            return {"kind": "array", "elem": kb_subtype(name)}

        return None

    def compatible(self, shape: Shape, expr: str) -> bool:
        """Check if the data fits a type from the knowledge base."""
        info = self.describe(expr)
        if info is None:
            return False

        kind = info["kind"]
        kinds = shape.kinds

        if kind == "array":
            if not shape.is_array or shape.tuples or shape.struct or shape.named:
                return False
            return shape.elem is None or self.compatible(shape.elem, info["elem"])

        if kind == "record":
            if shape.is_array or shape.tuples or shape.kinds:
                return False
            if not (shape.struct or shape.named):
                return False
            return all(
                to_2018_name(c) == info["name"] for c in shape.named
            ) if "name" in info else True

        if kind == "vec":
            return (
                not shape.is_array
                and not shape.kinds
                and not shape.struct
                and not shape.named
                and shape.tuples == {(info["size"],)}
            )

        if not shape.only_scalars():
            return False

        if kind == "str":
            return True

        if kind == "bool":
            return kinds <= {"bool"}

        if kind == "real":
            return kinds <= {"real", "int"}

        if kind == "int":
            return kinds <= {"int"} and self._int_fits(shape, info)

        if kind == "ptr":
            if not kinds <= {"null", "ref"}:
                return False
            return all(
                self.is_subclass(c, info["target"]) for c in self.pointee_classes(shape)
            )

        if kind == "enum":
            storage = self.describe(info["storage"])
            if storage is None or storage["kind"] != "int":
                return False

            if kinds <= {"int"}:
                # Written as plain numbers
                return self._int_fits(shape, storage)

            table = CONSTANTS.get(info["enum"])
            if table is None or shape.overflow or not kinds <= {"enum", "str", "int"}:
                return False

            if "int" in kinds and not table.is_flags:
                return False
            return all(table.parse(t) is not None for t in shape.tokens)

        return False

    @staticmethod
    def _int_fits(shape: Shape, info: dict) -> bool:
        if shape.int_min is None:
            return True

        bits = info["bits"]
        if info["signed"]:
            low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        else:
            low, high = 0, (1 << bits) - 1

        return low <= shape.int_min and shape.int_max <= high

    def adopt(self, shape: Shape, expr: str, owner: str, field: str) -> None:
        """Use a type from the knowledge base."""
        info = self.describe(expr)
        kind = info["kind"]

        shape.kind = kind
        shape.expr = expr

        if kind == "enum":
            if shape.kinds <= {"int"}:
                # Numeric representation, the enum is not important
                shape.kind = "int"
                shape.expr = info["storage"]
            else:
                shape.table = CONSTANTS[info["enum"]]

        elif kind == "array":
            if shape.elem is None:
                shape.elem = Shape()
            self.adopt(shape.elem, info["elem"], owner, field)

        elif kind == "record":
            self._bind_struct(shape, info.get("name", expr))
            shape.expr = info.get("name", expr)

        elif kind == "vec":
            shape.vec_elem = info["elem"]
            shape.vec_groups = 1

    def infer(self, shape: Shape, owner: str, field: str) -> None:
        """Come up with a type for the data."""
        if shape.is_array:
            if shape.elem is None:
                shape.elem = Shape()
            self.decide(shape.elem, None, None, owner, field)
            shape.kind = "array"
            shape.expr = f"hkArray<{shape.elem.expr}>"
            return

        if shape.struct or shape.named:
            shape.kind = "record"
            if shape.named:
                name = to_2018_name(min(shape.named))
            else:
                name = f"{owner}::{field[:1].upper()}{field[1:]}"
            self._bind_struct(shape, name)
            shape.expr = name
            return

        if shape.tuples:
            groups = min(shape.tuples)
            size = groups[0]
            shape.kind = "vec"
            shape.vec_groups = len(groups)
            shape.vec_elem = "float"

            if len(groups) == 1 and size == 4:
                shape.expr = "hkVector4"
            else:
                shape.expr = self._synthetic_vector(groups)
            return

        kinds = shape.kinds

        if (kinds and kinds <= {"null", "ref"}) or (not kinds and shape.ptr_hint):
            target = self.common_class(self.pointee_classes(shape))
            shape.kind, shape.expr = "ptr", f"hkRefPtr<{target}>"
        elif not kinds or "empty" in kinds:
            shape.kind, shape.expr = "str", "hkStringPtr"
        elif kinds == {"bool"}:
            shape.kind, shape.expr = "bool", "hkBool"
        elif kinds == {"int"}:
            shape.kind = "int"
            if -(1 << 31) <= shape.int_min and shape.int_max < (1 << 31):
                shape.expr = "hkInt32"
            elif shape.int_min >= 0 and shape.int_max < (1 << 32):
                shape.expr = "hkUint32"
            elif shape.int_min >= 0:
                shape.expr = "hkUlong"
            else:
                shape.expr = "hkInt64"
        elif kinds <= {"int", "real"}:
            shape.kind, shape.expr = "real", "hkReal"
        else:
            shape.kind, shape.expr = "str", "hkStringPtr"

    def _synthetic_vector(self, groups: tuple[int, ...]) -> str:
        """Fixed size arrays of floats that are not vectors."""
        inner_name = f"hkVector{groups[0]}f" if groups[0] != 4 else "hkVector4"
        if inner_name not in KB and inner_name not in self.local:
            self.local[inner_name] = {
                "format": groups[0] << 8 | 0x28,
                "subtype": "float",
            }

        if len(groups) == 1:
            return inner_name

        name = f"hkMatrix{len(groups)}x{groups[0]}f"
        self.local[name] = {"format": len(groups) << 8 | 0x28, "subtype": inner_name}
        return name

    def _bind_struct(self, shape: Shape, type_name: str) -> None:
        if shape.struct:
            self.decide_struct(shape.struct, type_name)
            self.anonymous.append(shape.struct)

    def decide(
        self,
        shape: Shape,
        kb_expr: str | None,
        kb_level: str | None,
        owner: str,
        field: str,
    ) -> None:
        if kb_expr and self.compatible(shape, kb_expr):
            self.adopt(shape, kb_expr, owner, field)
            shape.kb_source = kb_level
        else:
            if kb_expr:
                _logger.debug(
                    "Data of %s.%s does not match %s, inferring type",
                    owner,
                    field,
                    kb_expr,
                )
            self.infer(shape, owner, field)

    def kb_field(self, chain: list[str], field: str) -> tuple[str | None, str | None]:
        """Look up the type of a field in the knowledge base. Returns (expr, level)."""
        for level in chain:
            for name, expr, _ in KB.get(level, {}).get("fields", ()):
                if name == field:
                    return expr, level
        return None, None

    def decide_struct(self, info: StructInfo, type_name: str) -> None:
        if info.type_name is not None:
            return

        info.type_name = type_name
        chain = self.chain(type_name)

        for field, shape in info.fields.items():
            expr, level = self.kb_field(chain, field)
            self.decide(shape, expr, level, type_name, field)

    def decide_all(self) -> None:
        for info in list(self.structs.values()):
            self.decide_struct(info, to_2018_name(info.class_name))

    # --- pass 2b: record types ---

    def build_records(self) -> None:
        """Create the types of all structs, including their parents."""
        # Several structs can end up as the same type
        members: dict[str, dict[str, Shape]] = {}
        signatures: dict[str, str] = {}
        for info in [*self.structs.values(), *self.anonymous]:
            fields = members.setdefault(info.type_name, {})
            for name, shape in info.fields.items():
                fields.setdefault(name, shape)
            if info.signature:
                signatures.setdefault(info.type_name, info.signature)

        descendants: dict[str, list[dict[str, Shape]]] = defaultdict(list)
        for type_name, fields in members.items():
            for level in self.chain(type_name)[1:]:
                descendants[level].append(fields)

        names = set(members) | set(descendants)
        fields_of: dict[str, list[tuple[str, str, int]]] = {}

        # Parents first, since their fields are not repeated in the children
        for type_name in sorted(names, key=lambda n: len(self.chain(n))):
            inherited: dict[str, str] = {}
            for level in reversed(self.chain(type_name)[1:]):
                for name, expr, _ in fields_of[level]:
                    inherited[name] = expr

            fields = []

            if type_name in members:
                for name, shape in members[type_name].items():
                    if inherited.get(name) != shape.expr:
                        fields.append((name, shape.expr, self._field_flags(shape, name)))
            else:
                # Only keep what is true for every class that derives from it
                for name, expr, flags in KB.get(type_name, {}).get("fields", ()):
                    if name not in inherited and all(
                        name in d and d[name].kb_source == type_name
                        for d in descendants[type_name]
                    ):
                        fields.append((name, expr, flags))

            fields_of[type_name] = fields

        for type_name in names:
            kb = KB.get(type_name, {})
            record = {"format": FMT_RECORD, "fields": fields_of[type_name]}

            if self.parent_of(type_name):
                record["parent"] = self.parent_of(type_name)
            for key in ("version", "flags"):
                if key in kb:
                    record[key] = kb[key]
            if type_name in signatures:
                record["sig"] = signatures[type_name]

            self.local[type_name] = record

    @staticmethod
    def _field_flags(shape: Shape, name: str) -> int:
        if shape.kb_source:
            for fname, _, flags in KB[shape.kb_source].get("fields", ()):
                if fname == name:
                    return flags
        return 32

    # --- pass 3: conversion ---

    def convert_scalar(self, raw: str, shape: Shape) -> etree._Element:
        kind = shape.kind

        if kind == "bool":
            return etree.Element("bool", value=raw.strip().lower())

        if kind == "int":
            return etree.Element("integer", value=str(int(raw)))

        if kind == "enum":
            value = int(raw) if _INT.fullmatch(raw.strip()) else shape.table.parse(raw)
            if value is None:
                raise ValueError(f"Unknown constant '{raw}' ({shape.table.type_name})")
            return etree.Element("integer", value=str(value))

        if kind == "real":
            dec, hex_str = _format_2018_real(float(raw))
            return etree.Element("real", dec=dec, hex=hex_str)

        if kind == "str":
            return etree.Element("string", value=raw)

        if kind == "ptr":
            token = raw.strip()
            if token == "null":
                return etree.Element("pointer", id="object0")
            if not _REF.fullmatch(token):
                raise ValueError(f"'{raw}' is not a pointer")
            return etree.Element("pointer", id="object" + token[1:])

        raise ValueError(f"Cannot convert '{raw}' to {kind} ({shape.expr})")

    def convert_vector(self, groups: list[list[str]], shape: Shape) -> etree._Element:
        elem_type = self.types.ensure(shape.vec_elem)

        def make_array(tokens: list[str]) -> etree._Element:
            arr = etree.Element("array", count=str(len(tokens)), elementtypeid=elem_type)
            for token in tokens:
                dec, hex_str = _format_2018_real(float(token))
                etree.SubElement(arr, "real", dec=dec, hex=hex_str)
            return arr

        if len(groups) == 1:
            return make_array(groups[0])

        inner_type = self.types.ensure(
            self.local[shape.expr]["subtype"] if shape.expr in self.local else "hkVector4"
        )
        outer = etree.Element("array", count=str(len(groups)), elementtypeid=inner_type)
        for group in groups:
            outer.append(make_array(group))
        return outer

    def convert_value(self, form: str, data: Any, shape: Shape) -> etree._Element:
        kind = shape.kind

        if kind == "array":
            return self.convert_array(form, data, shape)

        if kind == "record":
            if form != "struct":
                raise ValueError(f"Expected a struct for {shape.expr}, but got {form}")
            return self.convert_record(data, shape)

        if kind == "vec":
            if form not in ("tuple", "tuples"):
                raise ValueError(f"Expected a tuple for {shape.expr}, but got {form}")
            return self.convert_vector(data, shape)

        if form != "scalar":
            raise ValueError(f"Expected a scalar for {shape.expr}, but got {form}")

        return self.convert_scalar(data, shape)

    def convert_array(self, form: str, data: Any, shape: Shape) -> etree._Element:
        elem_shape = shape.elem
        arr = etree.Element(
            "array",
            count=str(len(data)),
            elementtypeid=self.types.ensure(elem_shape.expr),
        )

        if form not in ("empty", "empty_ptr", "structs", "cstrings", "scalars", "tuples"):
            raise ValueError(f"Expected an array for {shape.expr}, but got {form}")

        item_form = {
            "structs": "struct",
            "cstrings": "scalar",
            "scalars": "scalar",
            "tuples": "tuple",
        }.get(form)

        for item in data:
            arr.append(self.convert_value(item_form, item, elem_shape))

        return arr

    def struct_info(self, elem: etree._Element, shape: Shape) -> StructInfo:
        class_name = elem.get("class")
        if class_name:
            return self.structs[class_name]
        return shape.struct

    def convert_record(self, elem: etree._Element, shape: Shape) -> etree._Element:
        return self._record(elem, self.struct_info(elem, shape))

    def _record(self, elem: etree._Element, info: StructInfo) -> etree._Element:
        record = etree.Element("record")

        for param in elem.findall("hkparam"):
            name = param.get("name")
            field = etree.SubElement(record, "field", name=name)
            form, data = _unpack(param)
            field.append(self.convert_value(form, data, info.fields[name]))

        return record

    def convert(self) -> etree._Element:
        self.observe()
        self.decide_all()
        self.build_records()
        self.types = TypeTable(self.local)

        out = etree.Element("hktagfile", version="3")
        for key in ("classversion", "contentsversion", "toplevelobject"):
            if self.root.get(key) is not None:
                out.set(f"hk2014_{key}", self.root.get(key))

        objects = []
        for elem in self.objects:
            info = self.structs[elem.get("class")]
            obj = etree.Element(
                "object",
                id="object" + elem.get("name").lstrip("#"),
                typeid=self.types.ensure(info.type_name),
            )
            obj.append(self._record(elem, info))
            objects.append(obj)

        # Make sure everything that the editor may need is defined
        for type_name in self.local:
            self.types.ensure(type_name)

        out.extend(self.types.to_xml())
        out.extend(objects)
        return out


def hk2014_to_2018(xml_2014: Path | str) -> str:
    """Convert hkpackfile (2014) to hktagfile v3 (2018).

    Parameters
    ----------
    xml_2014 : Path | str
        Path of the file to convert, or its content.
    """
    root = _read_input(xml_2014)
    if root.tag != "hkpackfile":
        raise ValueError(f"Not a hkpackfile (root is <{root.tag}>)")

    out = _To2018(root).convert()
    etree.indent(out, space="  ")
    return etree.tostring(out, encoding="unicode")


# === 2018 -> 2014 ===


class _Type:
    __slots__ = ("id", "name", "parent", "subtype", "params", "format", "fields", "sig")


class _To2014:
    def __init__(self, root: etree._Element):
        self.root = root
        self.types: dict[str, _Type] = {}
        self._warned: set[str] = set()

        for elem in root.findall("type"):
            t = _Type()
            t.id = elem.get("id")
            t.name = elem.find("name").get("value")
            t.parent = self._ref(elem, "parent")
            t.subtype = self._ref(elem, "subtype")
            t.sig = elem.get("hk_sig")

            fmt = elem.find("format")
            t.format = int(fmt.get("value")) if fmt is not None else None

            params = elem.find("parameters")
            t.params = (
                [p.get("id") for p in params.findall("typeparam")]
                if params is not None
                else []
            )

            fields = elem.find("fields")
            t.fields = (
                {f.get("name"): f.get("typeid") for f in fields.findall("field")}
                if fields is not None
                else {}
            )

            self.types[t.id] = t

    @staticmethod
    def _ref(elem: etree._Element, tag: str) -> str | None:
        child = elem.find(tag)
        return child.get("id") if child is not None else None

    # --- type queries ---

    def format_of(self, tid: str) -> int:
        """Like in the TypeRegistry, the root parent wins."""
        fmt = 0
        seen = set()
        while tid in self.types and tid not in seen:
            seen.add(tid)
            t = self.types[tid]
            if t.format is not None:
                fmt = t.format
            tid = t.parent
        return fmt

    def subtype_of(self, tid: str) -> str | None:
        seen = set()
        while tid in self.types and tid not in seen:
            seen.add(tid)
            t = self.types[tid]
            if t.subtype:
                return t.subtype
            tid = t.parent
        return None

    def constants_of(self, tid: str) -> ConstantTable | None:
        """Constant table of a hkEnum or hkFlags type, if there is one."""
        t = self.types.get(tid)
        if t is None or t.name not in ("hkEnum", "hkFlags") or not t.params:
            return None

        enum = self.types.get(t.params[0])
        return CONSTANTS.get(enum.name) if enum else None

    # --- values ---

    def scalar_text(self, elem: etree._Element, tid: str | None) -> str:
        tag = elem.tag

        if tag == "integer":
            value = int(elem.get("value", "0"))
            table = self.constants_of(tid) if tid else None
            if table is not None:
                text = table.format(value)
                if text is not None:
                    return text
                _logger.warning(
                    "No constant for %d in %s, writing the number", value, table.type_name
                )
            return str(value)

        if tag == "real":
            return _format_2014_real(_real_from_element(elem))

        if tag == "bool":
            return elem.get("value", "false")

        if tag == "string":
            return elem.get("value", "")

        if tag == "void":
            return "null"

        if tag == "pointer":
            target = elem.get("id", "object0")
            digits = target.removeprefix("object")
            return "null" if digits in ("", "0") else f"#{digits}"

        raise ValueError(f"Unsupported value <{tag}>")

    def vector_text(self, arr: etree._Element) -> str:
        """(x y z w), or (..)(..)(..) for vectors of vectors"""
        items = [c for c in arr if isinstance(c.tag, str)]
        if items and items[0].tag == "array":
            return "".join(self.vector_text(item) for item in items)

        return "(" + " ".join(self.scalar_text(i, None) for i in items) + ")"

    def is_numeric(self, arr: etree._Element) -> bool:
        """Check if an array contains only numbers, or arrays of numbers."""
        items = [c for c in arr if isinstance(c.tag, str)]
        return all(
            i.tag in ("real", "integer", "bool")
            or (i.tag == "array" and self.is_numeric(i))
            for i in items
        )

    def is_fixed_array(self, tid: str | None) -> bool:
        if not tid:
            return False
        fmt = self.format_of(tid)
        return fmt & 0xF == FMT_ARRAY and fmt >> 8 != 0

    def make_param(
        self, name: str, value: etree._Element, tid: str | None
    ) -> etree._Element:
        """Create <hkparam> for a field."""
        param = etree.Element("hkparam", name=name)
        tag = value.tag

        if tag == "record":
            param.append(self.make_struct(value, tid, name))

        elif tag == "array":
            if self.is_fixed_array(tid) and self.is_numeric(value):
                param.text = self.vector_text(value)
            else:
                self.fill_array(param, value, tid)

        else:
            text = self.scalar_text(value, tid)
            param.text = text if text != "" else None

        return param

    def struct_attributes(self, tid: str, name: str) -> dict[str, str]:
        """Attributes of a <hkobject> that is an object or a field of another struct."""
        t = self.types[tid]
        attrib = {"class": to_2014_name(t.name), "name": name}

        if t.sig:
            attrib["signature"] = t.sig
        elif tid not in self._warned:
            # The signature depends on the class version and can't be derived
            self._warned.add(tid)
            _logger.warning("Type %s has no signature, the file may be invalid", t.name)

        return attrib

    def make_struct(
        self, record: etree._Element, tid: str | None, field_name: str | None
    ) -> etree._Element:
        """Create <hkobject> for a record.

        Array items are anonymous, and so are objects whose type is unknown.
        """
        attrib = {}
        if field_name is not None and tid in self.types:
            attrib = self.struct_attributes(tid, field_name)

        struct_elem = etree.Element("hkobject", attrib)
        self.fill_struct(struct_elem, record, tid)
        return struct_elem

    def field_types(self, tid: str | None) -> dict[str, str]:
        """All fields of a type, including the ones of its parents."""
        fields: dict[str, str] = {}
        chain = []
        seen = set()
        while tid in self.types and tid not in seen:
            seen.add(tid)
            chain.append(self.types[tid])
            tid = self.types[tid].parent

        for t in reversed(chain):
            fields.update(t.fields)

        return fields

    def fill_struct(
        self, target: etree._Element, record: etree._Element, tid: str | None
    ) -> None:
        field_types = self.field_types(tid)

        for field in record.findall("field"):
            name = field.get("name")
            if name == "propertyBag":
                # Did not exist yet in 2014
                continue

            children = [c for c in field if isinstance(c.tag, str)]
            if not children:
                continue

            target.append(self.make_param(name, children[0], field_types.get(name)))

    def fill_array(
        self, param: etree._Element, arr: etree._Element, tid: str | None
    ) -> None:
        items = [c for c in arr if isinstance(c.tag, str)]
        param.set("numelements", str(len(items)))

        elem_tid = arr.get("elementtypeid") or (self.subtype_of(tid) if tid else None)

        if not items:
            # Only pointers always get a line break
            is_pointer = elem_tid and self.format_of(elem_tid) & 0xF == FMT_POINTER
            param.text = "\n" if is_pointer else None
            return

        first = items[0].tag

        if first == "record":
            for item in items:
                param.append(self.make_struct(item, elem_tid, None))

        elif first == "string":
            for item in items:
                child = etree.SubElement(param, "hkcstring")
                child.text = item.get("value") or None

        elif first == "pointer":
            lines = [self.scalar_text(item, elem_tid) for item in items]
            param.text = "\n" + "\n".join(lines) + "\n"

        else:
            if first == "array":
                tokens = [self.vector_text(item) for item in items]
            else:
                tokens = [self.scalar_text(item, elem_tid) for item in items]

            rows = _wrap(tokens)
            if len(rows) == 1:
                param.text = rows[0]
            else:
                param.text = "\n" + "\n".join(rows)

    def convert(self) -> etree._Element:
        out = etree.Element(
            "hkpackfile",
            classversion=self.root.get("hk2014_classversion", "11"),
            contentsversion=self.root.get("hk2014_contentsversion", "hk_2014.1.0-r1"),
        )
        if self.root.get("hk2014_toplevelobject"):
            out.set("toplevelobject", self.root.get("hk2014_toplevelobject"))

        section = etree.SubElement(out, "hksection", name="__data__")

        for obj in self.root.findall("object"):
            tid = obj.get("typeid")
            record = obj.find("record")

            attrib = self.struct_attributes(tid, "#" + obj.get("id").removeprefix("object"))
            elem = etree.SubElement(section, "hkobject", attrib)
            if record is not None:
                self.fill_struct(elem, record, tid)

        return out


def hk2018_to_2014(xml_2018: Path | str) -> str:
    """Convert hktagfile v3 (2018) to hkpackfile (2014).

    Parameters
    ----------
    xml_2018 : Path | str
        Path of the file to convert, or its content.
    """
    root = _read_input(xml_2018)
    if root.tag != "hktagfile":
        raise ValueError(f"Not a hktagfile (root is <{root.tag}>)")

    out = _To2014(root).convert()
    etree.indent(out, space="    ")

    body = etree.tostring(out, encoding="ascii").decode("ascii")
    return '<?xml version="1.0" encoding="ASCII" standalone="no"?>\n' + body + "\n"


# === CLI ===


def _root_tag(path: Path) -> str:
    for _, elem in etree.iterparse(str(path), events=("start",)):
        return elem.tag
    return ""


if __name__ == "__main__":
    ap = ArgumentParser(
        description="Convert between hkpackfile (2014) and hktagfile (2018)."
    )
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument(
        "--direction",
        choices=["2014to2018", "2018to2014"],
        help="Override auto-detection from root tag",
    )
    args = ap.parse_args()

    to_2018 = (
        (args.direction == "2014to2018")
        if args.direction
        else (_root_tag(args.input) == "hkpackfile")
    )

    if to_2018:
        result = hk2014_to_2018(args.input)
        print(f"hkpackfile -> hktagfile  ->  {args.output}", file=sys.stderr)
    else:
        result = hk2018_to_2014(args.input)
        print(f"hktagfile -> hkpackfile  ->  {args.output}", file=sys.stderr)

    args.output.write_text(result, "utf-8")
