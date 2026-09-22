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


# === type format constants ===

_PRIM_FORMATS: dict[str, int] = {
    "Void": 0,
    "Opaque": 1,
    "hkBool": 2,
    "hkStringPtr": 3,
    "hkInt32": 4,
    "hkReal": 5,
    "hkRefPtr": 6,
    "hkBaseObject": 7,
    "hkArray": 8,
}


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
            sig = t.get("hk_sig")  # only present on real classes
            if sig is not None:
                sig_map[tid] = sig

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
                elem_tid = val.get("elementtypeid", "")
                elem_cls = type_map.get(elem_tid, "") if elem_tid in sig_map else ""
                elem_sig = sig_map.get(elem_tid, "")
                for rec in items:
                    _rec_as_hkobj(p, rec, elem_cls, sig=elem_sig)

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

            elif items[0].tag == "string":
                for child in items:
                    hkc = etree.SubElement(p, "hkcstring")
                    hkc.text = child.get("value", "")

            else:
                tag = items[0].tag
                if tag not in ("real", "integer", "bool"):
                    print(
                        f"WARNING: unhandled array element <{tag}> in 2018->2014",
                        file=sys.stderr,
                    )
                vals = [
                    _real_val(c) if c.tag == "real" else c.get("value", "0")
                    for c in items
                ]
                p.text = "\n" + "\n".join(vals) + "\n"

        elif tag == "record":
            typeid = val.get("typeid", "")
            rec_cls = type_map.get(typeid, "") if typeid in sig_map else ""
            rec_sig = sig_map.get(typeid, "")
            rec_name = name if rec_cls else ""
            _rec_as_hkobj(p, val, rec_cls, rec_name, rec_sig)

    def _rec_as_hkobj(
        parent: etree._Element,
        rec: etree._Element,
        class_name: str = "",
        obj_name: str = "",
        sig: str = "",
    ) -> None:
        attrib: dict[str, str] = {}
        if class_name:
            attrib["class"] = class_name
        if obj_name:
            attrib["name"] = obj_name
        if sig:
            attrib["signature"] = sig
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
    class_type_els: dict[str, etree._Element] = {}  # class name -> <type> element
    class_fields_done: set[str] = set()  # classes whose fields are populated
    enum_to_tid: dict[str, str] = {}  # enum type name -> typeid
    array_elem_to_tid: dict[str, str] = {}  # array elem type name -> typeid
    array_elem_els: dict[str, etree._Element] = {}  # array elem type name -> <type> el
    prim_to_tid: dict[str, str] = {}  # primitive name -> typeid
    out = etree.Element("hktagfile", version="3")
    _next = [1]

    def _next_tid() -> str:
        tid = f"type{_next[0]}"
        _next[0] += 1
        return tid

    def _get_prim_tid(name: str) -> str:
        if name not in prim_to_tid:
            tid = _next_tid()
            prim_to_tid[name] = tid
            t = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t, "name", value=name)
            etree.SubElement(t, "format", value=str(_PRIM_FORMATS.get(name, 0)))
            etree.SubElement(t, "fields", count="0")
        return prim_to_tid[name]

    # map from value element tag -> typeid lookup
    def _val_typeid(val: etree._Element) -> str:
        tag = val.tag
        if tag == "real":
            return _get_prim_tid("hkReal")
        if tag == "bool":
            return _get_prim_tid("hkBool")
        if tag == "integer":
            return _get_prim_tid("hkInt32")
        if tag == "string":
            return _get_prim_tid("hkStringPtr")
        if tag == "pointer":
            return _get_prim_tid("hkRefPtr")
        if tag == "enum":
            return val.get("typeid", "")
        if tag == "array":
            return _get_prim_tid("hkArray")
        if tag == "record":
            return val.get("typeid", "")
        return ""

    def _get_class_tid(cls: str, sig: str = "0x0") -> str:
        if cls not in class_to_tid:
            tid = _next_tid()
            class_to_tid[cls] = tid
            t = etree.SubElement(out, "type", id=tid, hk_sig=sig)
            etree.SubElement(t, "name", value=cls)
            etree.SubElement(t, "format", value=str(_PRIM_FORMATS["hkBaseObject"]))
            etree.SubElement(t, "fields", count="0")  # populated on first object
            class_type_els[cls] = t
        return class_to_tid[cls]

    def _fill_fields(t_el: etree._Element, rec: etree._Element) -> None:
        """Populate <fields> on a type element from a processed record."""
        fields_el = t_el.find("fields")
        if fields_el is None or len(fields_el):
            return  # already populated
        field_els = rec.findall("field")
        fields_el.set("count", str(len(field_els)))
        for f in field_els:
            children = [c for c in f if not isinstance(c, etree._Comment)]
            tid = _val_typeid(children[0]) if children else ""
            etree.SubElement(
                fields_el, "field", name=f.get("name", ""), typeid=tid, flags="36"
            )

    def _populate_fields(cls: str, rec: etree._Element) -> None:
        """Back-fill <fields> on the class type stub from the first processed record."""
        if cls in class_fields_done:
            return
        class_fields_done.add(cls)
        t = class_type_els.get(cls)
        if t is not None:
            _fill_fields(t, rec)

    def _get_enum_tid(cls: str, field_name: str) -> str:
        enum_name = f"{cls}_{field_name}_Enum"
        if enum_name not in enum_to_tid:
            tid = _next_tid()
            enum_to_tid[enum_name] = tid
            t = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t, "name", value=enum_name)
            etree.SubElement(t, "format", value=str(_PRIM_FORMATS["hkStringPtr"]))
            etree.SubElement(t, "fields", count="0")
        return enum_to_tid[enum_name]

    def _peek_elem_fmt(raw: str, kids: list[etree._Element]) -> int:
        """Infer array element format from content; returns Void (0) if empty/unknown."""
        if kids:
            tag = kids[0].tag
            if tag == "hkobject":
                return _PRIM_FORMATS["hkBaseObject"]
            if tag == "hkcstring":
                return _PRIM_FORMATS["hkStringPtr"]
            return _PRIM_FORMATS["Void"]

        groups = _TUPLE.findall(raw)
        if groups:
            return _PRIM_FORMATS["hkArray"]  # outer elements are nested arrays

        tokens = raw.split()
        if not tokens:
            return _PRIM_FORMATS["Void"]  # empty array, format unknown

        t = tokens[0].strip()
        if t == "null" or _REF.fullmatch(t):
            return _PRIM_FORMATS["hkRefPtr"]
        if t in ("true", "false"):
            return _PRIM_FORMATS["hkBool"]
        if _INT.fullmatch(t):
            return _PRIM_FORMATS["hkInt32"]
        if _FLOAT.fullmatch(t):
            return _PRIM_FORMATS["hkReal"]
        if _ENUM.fullmatch(t):
            return _PRIM_FORMATS["hkInt32"]

        return _PRIM_FORMATS["hkStringPtr"]

    def _get_array_elem_tid(
        cls: str, field_name: str, fmt: int = 0, suffix: str = "Type"
    ) -> str:
        type_name = f"{cls}_{field_name}_{suffix}"
        if type_name not in array_elem_to_tid:
            tid = _next_tid()
            array_elem_to_tid[type_name] = tid
            t = etree.SubElement(out, "type", id=tid)
            etree.SubElement(t, "name", value=type_name)
            etree.SubElement(t, "format", value=str(fmt))
            etree.SubElement(t, "fields", count="0")
            array_elem_els[type_name] = t
        elif fmt != _PRIM_FORMATS["Void"]:
            # update format if stub was registered while array was empty
            fmt_el = array_elem_els[type_name].find("format")
            if fmt_el is not None and fmt_el.get("value") == str(_PRIM_FORMATS["Void"]):
                fmt_el.set("value", str(fmt))

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
                parent, "string", value=t, typeid=_get_enum_tid(cls, field_name)
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
            kids = [c for c in param if not isinstance(c, etree._Comment)]

            # determine elementtypeid before creating the array element
            if kids:
                first_tag = kids[0].tag
                if first_tag == "hkobject":
                    ek = kids[0]
                    ek_cls = ek.get("class", "")
                    ek_sig = ek.get("signature", "0x0")
                    elem_tid = (
                        _get_class_tid(ek_cls, ek_sig)
                        if ek_cls
                        else _get_array_elem_tid(
                            cls, fname, _PRIM_FORMATS["hkBaseObject"]
                        )
                    )
                elif first_tag == "hkcstring":
                    elem_tid = _get_prim_tid("hkStringPtr")
                else:
                    elem_tid = ""
                    print(
                        f"WARNING: unhandled array child <{first_tag}> in {cls}.{fname}",
                        file=sys.stderr,
                    )
            else:
                elem_tid = _get_array_elem_tid(cls, fname, _peek_elem_fmt(raw, kids))

            arr = etree.SubElement(
                field, "array", count=numelems, elementtypeid=elem_tid
            )

            if kids:
                if first_tag == "hkobject":
                    arr.set("count", str(len(kids)))
                    for i, child in enumerate(kids):
                        child_cls = child.get("class", "")
                        child_tid = (
                            _get_class_tid(child_cls, child.get("signature", "0x0"))
                            if child_cls
                            else elem_tid
                        )
                        rec = etree.SubElement(arr, "record", typeid=child_tid)
                        for p in child.findall("hkparam"):
                            _param_to_field(rec, p, cls)
                        if i == 0 and not child_cls:
                            # populate anonymous struct type from first element
                            t_el = array_elem_els.get(f"{cls}_{fname}_Type")
                            if t_el is not None:
                                _fill_fields(t_el, rec)
                elif first_tag == "hkcstring":
                    arr.set("count", str(len(kids)))
                    for child in kids:
                        etree.SubElement(arr, "string", value=(child.text or ""))
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
                            elementtypeid=_get_array_elem_tid(
                                cls, fname, _PRIM_FORMATS["hkReal"], "ElemType"
                            ),
                        )
                        for tok in tokens:
                            etree.SubElement(inner, "real", value=tok)
                else:
                    for tok in raw.split():
                        _infer(arr, tok, cls, fname)

        elif hkobj_kids:
            child = hkobj_kids[0]
            child_cls = child.get("class", "")
            child_tid = _get_class_tid(child_cls, child.get("signature", "0x0"))
            rec = etree.SubElement(field, "record", typeid=child_tid)

            for p in child.findall("hkparam"):
                _param_to_field(rec, p, cls)

            if child_cls:
                _populate_fields(child_cls, rec)

        elif raw.startswith("("):
            # single tuple (x y z) without numelements -> plain flat array
            tokens = raw[1 : raw.rindex(")")].split()
            arr = etree.SubElement(
                field,
                "array",
                count=str(len(tokens)),
                elementtypeid=_get_array_elem_tid(cls, fname, _PRIM_FORMATS["hkReal"]),
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
        _populate_fields(cls, rec)

    # Replace all void types with string
    # TODO present as uneditable items in gui instead
    _void = str(_PRIM_FORMATS["Void"])
    _str = str(_PRIM_FORMATS["hkStringPtr"])
    for t in out.findall("type"):
        fmt = t.find("format")
        if fmt is not None and fmt.get("value") == _void:
            fmt.set("value", _str)

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
