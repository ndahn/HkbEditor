"""
hkpackfile (2014) <-> hktagfile v3 (2018) XML converter.

2014 -> 2018 inference rules (applied per token):
  null / #N          -> pointer
  true / false       -> bool
  integer pattern    -> integer
  float pattern      -> real
  (x y ... z)        -> <array> of reals; multiple groups -> nested <array> per group
  UPPER_SNAKE_CASE   -> <enum value="..." typeid="..."> with ad-hoc type stub
  anything else      -> string

Round-trip storage:
  signature -> stored once on <type hk_sig="...">; recovered via typeid lookup
  class     -> recovered from type_map[typeid]; no per-object attribute needed
  object id -> #N <-> objectN, stable with no remapping
"""

from __future__ import annotations

import re
import sys
from argparse import ArgumentParser
from pathlib import Path

from lxml import etree


# === regex helpers ===

_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d*([eE][+-]?\d+)?$|^-?\d*\.\d+([eE][+-]?\d+)?$")
_REF = re.compile(r"^#\d+$")
_ENUM = re.compile(r"^[A-Z][A-Z0-9_]+$")  # all-caps identifiers -> enum
_TUPLE = re.compile(r"\(([^)]*)\)")  # extract groups from (x y z) notation


# === id helpers ===

def _obj_to_ref(obj_id: str) -> str:
    """'object42' -> '#42'  |  'object0' -> 'null'"""
    n = obj_id.removeprefix("object")
    return "null" if n == "0" else f"#{n}"


def _ref_to_obj(ref: str) -> str:
    """'#42' -> 'object42'  |  'null' -> 'object0'"""
    s = ref.strip()
    return "object0" if s == "null" else "object" + s.lstrip("#")


def _real_val(el: etree._Element) -> str:
    """Read float value supporting both value= and dec= (native 2018 format)."""
    return el.get("value") or el.get("dec") or "0"


# === 2018 -> 2014 ===

def hk2018_to_2014(xml_2018: Path | str) -> str:
    """Convert hktagfile v3 (2018) to hkpackfile (2014)."""
    if isinstance(xml_2018, Path):
        xml_2018 = xml_2018.read_text("utf-8")

    root = etree.fromstring(xml_2018.encode())

    type_map: dict[str, str] = {}  # typeid -> class name
    sig_map: dict[str, str] = {}  # typeid -> signature

    for t in root.findall("type"):
        n = t.find("name")
        if n is not None:
            tid = t.get("id", "")
            type_map[tid] = n.get("value", "")
            sig_map[tid] = t.get("hk_sig", "0x0")

    out = etree.Element(
        "hkpackfile", classversion="11", contentsversion="hk_2014.1.0-r1"
    )
    section = etree.SubElement(out, "hksection", name="__data__")

    def _val_to_param(parent: etree._Element, name: str, val: etree._Element) -> None:
        """Append <hkparam name='...'> for a 2018 typed value element."""
        tag = val.tag
        p = etree.SubElement(parent, "hkparam", name=name)

        if tag == "integer":
            p.text = val.get("value", "0")

        elif tag == "bool":
            p.text = val.get("value", "false")

        elif tag == "real":
            p.text = _real_val(val)

        elif tag == "string":
            p.text = val.get("value", "")

        elif tag == "enum":
            p.text = val.get("value", "")

        elif tag == "pointer":
            p.text = _obj_to_ref(val.get("id", "object0"))

        elif tag == "array":
            p.set("numelements", val.get("count", "0"))
            items = [c for c in val if not isinstance(c, etree._Comment)]

            if not items:
                p.text = "\n"

            elif items[0].tag == "record":
                # class name from elementtypeid -> type_map
                elem_cls = type_map.get(val.get("elementtypeid", ""), "")
                for rec in items:
                    _rec_as_hkobj(p, rec, elem_cls)

            elif items[0].tag == "array":
                # nested arrays -> (x y z) per line
                parts = []
                for inner in items:
                    inner_vals = [
                        _real_val(c) for c in inner if not isinstance(c, etree._Comment)
                    ]
                    parts.append("(" + " ".join(inner_vals) + ")")
                p.text = "\n" + "\n".join(parts) + "\n"

            elif items[0].tag == "pointer":
                refs = [_obj_to_ref(c.get("id", "object0")) for c in items]
                p.text = "\n" + "\n".join(refs) + "\n"

            else:
                vals = [
                    _real_val(c) if c.tag == "real" else c.get("value", "0")
                    for c in items
                ]
                p.text = "\n" + "\n".join(vals) + "\n"

        elif tag == "record":
            _rec_as_hkobj(p, val)

    def _rec_as_hkobj(
        parent: etree._Element, rec: etree._Element, class_name: str = ""
    ) -> None:
        attrib: dict[str, str] = {}
        if class_name:
            attrib["class"] = class_name
        hkobj = etree.SubElement(parent, "hkobject", **attrib)
        for field in rec.findall("field"):
            children = [c for c in field if not isinstance(c, etree._Comment)]
            if children:
                _val_to_param(hkobj, field.get("name", ""), children[0])

    for elem in root:
        if elem.tag != "object":
            continue
        oid = elem.get("id", "")
        num = oid.removeprefix("object")
        typeid = elem.get("typeid", "")
        cls = type_map.get(typeid, typeid)
        sig = sig_map.get(typeid, "0x0")

        hkobj = etree.SubElement(
            section,
            "hkobject",
            attrib={"class": cls, "name": f"#{num}", "signature": sig},
        )
        record = elem.find("record")
        if record is None:
            continue
        for field in record.findall("field"):
            children = [c for c in field if not isinstance(c, etree._Comment)]
            if children:
                _val_to_param(hkobj, field.get("name", ""), children[0])

    return etree.tostring(out, encoding="unicode", pretty_print=True)


# === 2014 -> 2018 ===

def hk2014_to_2018(xml_2014: Path | str) -> str:
    """Convert hkpackfile (2014) to hktagfile v3 (2018)."""
    if isinstance(xml_2014, Path):
        xml_2014 = xml_2014.read_text("utf-8")

    root = etree.fromstring(xml_2014.encode())

    class_to_tid: dict[str, str] = {}  # class name -> typeid
    enum_to_tid: dict[str, str] = {}  # enum type name -> typeid
    array_elem_to_tid: dict[str, str] = {}  # array elem type name -> typeid
    out = etree.Element("hktagfile", version="3")
    _next = [1]

    def _next_tid() -> str:
        tid = f"type{_next[0]}"
        _next[0] += 1
        return tid

    def _get_class_tid(cls: str, sig: str = "0x0") -> str:
        if cls not in class_to_tid:
            tid = _next_tid()
            class_to_tid[cls] = tid
            t = etree.SubElement(out, "type", id=tid, hk_sig=sig)
            etree.SubElement(t, "name", value=cls)
            etree.SubElement(t, "format", value="7")
            etree.SubElement(t, "fields", count="0")
        return class_to_tid[cls]

    def _get_enum_tid(cls: str, field_name: str) -> str:
        enum_name = f"{cls}_{field_name}_Enum"
        if enum_name not in enum_to_tid:
            tid = _next_tid()
            enum_to_tid[enum_name] = tid
            t = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t, "name", value=enum_name)
            etree.SubElement(t, "format", value="33284")
        return enum_to_tid[enum_name]

    def _get_array_elem_tid(cls: str, field_name: str, suffix: str = "Type") -> str:
        type_name = f"{cls}_{field_name}_{suffix}"
        if type_name not in array_elem_to_tid:
            tid = _next_tid()
            array_elem_to_tid[type_name] = tid
            t = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t, "name", value=type_name)
            etree.SubElement(t, "format", value="7")
            etree.SubElement(t, "fields", count="0")
        return array_elem_to_tid[type_name]

    def _infer(
        parent: etree._Element, tok: str, cls: str = "", field_name: str = ""
    ) -> None:
        """Emit a single typed value element inferred from a text token."""
        t = tok.strip()
        if t == "null":
            etree.SubElement(parent, "pointer", id="object0")
        elif _REF.fullmatch(t):
            etree.SubElement(parent, "pointer", id=_ref_to_obj(t))
        elif t in ("true", "false"):
            etree.SubElement(parent, "bool", value=t)
        elif _INT.fullmatch(t):
            etree.SubElement(parent, "integer", value=t)
        elif _FLOAT.fullmatch(t):
            etree.SubElement(parent, "real", value=t)
        elif _ENUM.fullmatch(t):
            etree.SubElement(
                parent, "enum", value=t, typeid=_get_enum_tid(cls, field_name)
            )
        else:
            etree.SubElement(parent, "string", value=t)

    def _param_to_field(
        parent: etree._Element, param: etree._Element, cls: str = ""
    ) -> None:
        """Append a 2018 <field> for a 2014 <hkparam>."""
        fname = param.get("name", "")
        field = etree.SubElement(parent, "field", name=fname)
        hkobj_kids = param.findall("hkobject")
        numelems = param.get("numelements")
        raw = (param.text or "").strip()

        if numelems is not None:
            arr = etree.SubElement(
                field,
                "array",
                count=numelems,
                elementtypeid=_get_array_elem_tid(cls, fname),
            )

            if hkobj_kids:
                for child in hkobj_kids:
                    rec = etree.SubElement(arr, "record")
                    for p in child.findall("hkparam"):
                        _param_to_field(rec, p, cls)

            else:
                groups = _TUPLE.findall(raw)
                if groups:
                    # each () group is one element -> nested array per group
                    arr.set("count", str(len(groups)))
                    for group in groups:
                        tokens = group.split()
                        inner = etree.SubElement(
                            arr,
                            "array",
                            count=str(len(tokens)),
                            elementtypeid=_get_array_elem_tid(cls, fname, "ElemType"),
                        )
                        for tok in tokens:
                            etree.SubElement(inner, "real", value=tok)
                else:
                    for tok in raw.split():
                        _infer(arr, tok, cls, fname)

        elif hkobj_kids:
            rec = etree.SubElement(field, "record")
            for p in hkobj_kids[0].findall("hkparam"):
                _param_to_field(rec, p, cls)

        elif raw.startswith("("):
            # single tuple (x y z) without numelements -> plain flat array
            tokens = raw[1 : raw.rindex(")")].split()
            arr = etree.SubElement(
                field,
                "array",
                count=str(len(tokens)),
                elementtypeid=_get_array_elem_tid(cls, fname),
            )
            for tok in tokens:
                _infer(arr, tok, cls, fname)

        elif raw:
            _infer(field, raw, cls, fname)

        else:
            etree.SubElement(field, "string", value="")

    section = root.find("hksection")
    objects = (section if section is not None else root).findall("hkobject")

    for hkobj in objects:
        cls = hkobj.get("class", "")
        name_val = hkobj.get("name", "")
        num = name_val.lstrip("#")
        sig = hkobj.get("signature", "0x0")
        obj = etree.SubElement(
            out, "object", id=f"object{num}", typeid=_get_class_tid(cls, sig)
        )
        obj.append(etree.Comment(cls))
        rec = etree.SubElement(obj, "record")
        for param in hkobj.findall("hkparam"):
            _param_to_field(rec, param, cls)

    return etree.tostring(out, encoding="unicode", pretty_print=True)


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

    src = args.input.read_text("utf-8")
    to_2018 = (
        (args.direction == "2014to2018")
        if args.direction
        else (_root_tag(args.input) == "hkpackfile")
    )

    if to_2018:
        result = hk2014_to_2018(src)
        print(f"hkpackfile -> hktagfile  ->  {args.output}", file=sys.stderr)
    else:
        result = hk2018_to_2014(src)
        print(f"hktagfile -> hkpackfile  ->  {args.output}", file=sys.stderr)

    args.output.write_text(result, "utf-8")
