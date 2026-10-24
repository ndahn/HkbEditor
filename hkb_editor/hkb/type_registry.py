from typing import TYPE_CHECKING, Generator
from logging import getLogger
import re
from functools import cache
from copy import deepcopy
from lxml import etree as ET

from .xml import xml_from_str

if TYPE_CHECKING:
    from .hkb_types import HkbRecord


_logger = getLogger(__name__)


class TypeMismatch(Exception):
    def __init__(self, message: str, missing: list[str], extra: list[str]):
        super().__init__(message)
        self.missing = missing
        self.extra = extra


class TypeRegistry:
    def __init__(self):
        self.types: dict[str, dict] = {}
        # Types added after loading. They only exist in the registry until the owning
        # tagfile writes them out via write_new_types()
        self._new_type_elems: list[ET._Element] = []

    def load_types(self, root: ET._Element) -> None:
        self.types.clear()
        self._new_type_elems.clear()

        for type_el in root.findall(".//type"):
            type_id = type_el.attrib["id"]
            name = type_el.find("name").attrib["value"]

            # Seems to be inherited from the parent types
            fmt = self._collect_typeinfo(root, type_id, "format", "value")
            if not fmt:
                _logger.warning("Could not resolve format of type %s", type_id)
                fmt = 0
            else:
                fmt = int(fmt[0])

            fields = {
                f: ft
                for f, ft in self._collect_typeinfo(
                    root, type_id, "field", ("name", "typeid")
                )
            }

            typeparams = (
                [
                    tp.attrib["id"]
                    for tp in type_el.find("parameters").findall("typeparam")
                ]
                if type_el.find("parameters") is not None
                else []
            )

            subtype = self._get_attribute(type_el, "subtype", "id")
            parent = self._get_attribute(type_el, "parent", "id")

            # TODO field flags
            # https://github.com/The12thAvenger/HKLib/blob/main/HKLib.Reflection/HavokType.cs#L82

            self.types[type_id] = {
                "name": name,
                "format": fmt,
                "fields": fields,
                "subtype": subtype,
                "typeparams": typeparams,
                "parent": parent,
            }

        for type_id, info in self.types.items():
            subtype = info["subtype"]
            if subtype in self.types:
                subname = self.types[subtype]["name"]
                fullname = f"{info['name']}< {subname} >"
            else:
                fullname = info["name"]

            info["fullname"] = fullname

    def _get_attribute(self, elem: ET._Element, tag: str, key: str) -> str:
        attr_el = elem.find(tag)
        if attr_el is not None:
            return attr_el.attrib.get(key, None)

        return None

    def _collect_typeinfo(
        self,
        root: ET._Element,
        leaf_type_id: str,
        attr_tag: str,
        attributes: str | tuple[str],
    ) -> list[str | tuple[str]]:
        if not isinstance(attributes, tuple):
            attributes = (attributes,)

        ret = []

        while leaf_type_id:
            type_el = root.find(f".//type[@id='{leaf_type_id}']")
            level_vals = []

            for attr_el in type_el.findall(f".//{attr_tag}"):
                vals = tuple(attr_el.attrib[attr] for attr in attributes)
                if len(vals) == 1:
                    vals = vals[0]

                level_vals.append(vals)

            # Items found on a higher parent level should go in front
            ret = level_vals + ret
            leaf_type_id = self._get_attribute(type_el, "parent", "id")

        return ret

    def find_types_by_name(self, type_name: str) -> Generator[str, None, None]:
        for tid, t in self.types.items():
            if t["fullname"] == type_name:
                yield tid

    @cache
    def find_first_type_by_name(self, type_name: str) -> str:
        return next(self.find_types_by_name(type_name))

    @cache
    def get_name(self, type_id: str, with_template: bool = True) -> str:
        if with_template:
            return self.types[type_id]["fullname"]
        return self.types[type_id]["name"]

    def get_format(self, type_id: str) -> int:
        return self.types[type_id]["format"]

    def get_field_types(self, type_id: str) -> dict[str, str]:
        return self.types[type_id]["fields"]

    def get_subtype(self, type_id: str) -> str:
        return self.types[type_id].get("subtype", None)

    def get_typeparams(self, type_id: str) -> list[str]:
        return self.types[type_id].get("typeparams", [])

    def get_parent(self, type_id: str) -> str:
        return self.types[type_id].get("parent", None)

    @cache
    def get_compatible_types(self, type_id: str) -> list[str]:
        parents = [type_id]
        res = [type_id]

        while parents:
            p = parents.pop()
            for tid, t in self.types.items():
                if p == t["parent"]:
                    res.append(tid)
                    parents.append(tid)

        return res

    def verify_object(self, obj: "HkbRecord") -> None:
        elem = obj.element
        fields = self.get_field_types(obj.type_id).keys()

        # Only check immediate children
        missing = [f for f in fields if not elem.xpath(f"./field[@name='{f}']")]
        extra = [c.get("name") for c in elem.xpath("./field") if c.get("name") not in fields]
        # TODO check for fields with wrong type

        if missing or extra:
            raise TypeMismatch(f"""\
Failed to verify object {obj.object_id} ({obj.type_id} / {obj.type_name})
 - missing fields: {missing}
 - extra fields: {extra}""",
                missing,
                extra,
            )

    @staticmethod
    def _make_signature(name: str, subtype_signature: str | None) -> str:
        # Used to identify types across registries. Template arguments other than
        # the subtype are ignored, same as in the "fullname".
        if subtype_signature:
            return f"{name}< {subtype_signature} >"
        return name

    def _registry_signatures(self) -> dict[str, str]:
        """Map type signatures to type ids for all currently known types."""
        cache: dict[str, str] = {}

        def signature(type_id: str) -> str:
            if type_id not in cache:
                info = self.types[type_id]
                subtype = info["subtype"]
                sub_sig = signature(subtype) if subtype in self.types else None
                cache[type_id] = self._make_signature(info["name"], sub_sig)
            return cache[type_id]

        known: dict[str, str] = {}
        for type_id in self.types:
            known.setdefault(signature(type_id), type_id)

        return known

    def insert_types_from_hklib_xml(self, xml: str, types: list[str]) -> list[str]:
        """Add types from a HKLib type dump to the registry.

        The requested types are added together with all types they depend on (parents,
        subtypes, template parameters and member types) that the registry doesn't know
        yet. Types are matched by name and subtype, not by id, since ids differ between
        HKLib dumps and tagfiles.

        Parameters
        ----------
        xml : str
            Content of a HKLib type dump, i.e. a list of <HavokType> elements.
        types : list[str]
            Names of the types to insert, e.g. "hkbManualSelectorGenerator".

        Returns
        -------
        list[str]
            Ids of the newly added types. Empty if all types were already known.
            The tagfile that owns this registry will include them when saving, see
            write_new_types().
        """
        xml = xml.lstrip("﻿ \t\r\n")
        xml = re.sub(r"^<\?xml[^>]*\?>", "", xml)
        root = xml_from_str(f"<HavokTypes>{xml}</HavokTypes>")

        hk_types: dict[str, ET._Element] = {
            el.get("Id"): el for el in root.iter("HavokType")
        }

        def hk_type(hk_id: str) -> ET._Element:
            try:
                return hk_types[hk_id]
            except KeyError:
                raise KeyError(f"HKLib type id {hk_id} is not defined in the input")

        hk_sigs: dict[str, str] = {}

        def hk_signature(hk_id: str) -> str:
            if hk_id not in hk_sigs:
                el = hk_type(hk_id)
                subtype = el.get("SubType", "0")
                sub_sig = hk_signature(subtype) if subtype != "0" else None
                hk_sigs[hk_id] = self._make_signature(el.get("Name"), sub_sig)
            return hk_sigs[hk_id]

        def hk_template_params(el: ET._Element) -> list[str]:
            return [
                tp.get("Type")
                for tp in el.findall("./TemplateParams/*")
                if tp.get("Type", "0") != "0"
            ]

        def hk_references(el: ET._Element) -> list[str]:
            refs = [el.get("Parent", "0"), el.get("SubType", "0")]
            refs.extend(hk_template_params(el))
            refs.extend(m.get("Type", "0") for m in el.findall("./Members/Member"))
            return [r for r in refs if r != "0"]

        known = self._registry_signatures()
        next_id = 1 + max(
            (int(tid[4:]) for tid in self.types if tid[4:].isdigit()), default=0
        )

        hk_to_tid: dict[str, str] = {}
        new_hk_ids: list[str] = []

        def resolve(hk_id: str) -> str:
            nonlocal next_id

            if hk_id in hk_to_tid:
                return hk_to_tid[hk_id]

            sig = hk_signature(hk_id)
            if sig in known:
                hk_to_tid[hk_id] = known[sig]
                return known[sig]

            # Register before descending, member types may refer back to this one
            tid = f"type{next_id}"
            next_id += 1
            hk_to_tid[hk_id] = tid
            known[sig] = tid
            new_hk_ids.append(hk_id)

            for ref in hk_references(hk_type(hk_id)):
                resolve(ref)

            return tid

        for name in types:
            hk_id = next((i for i, el in hk_types.items() if el.get("Name") == name), None)
            if hk_id is None:
                hk_id = next((i for i in hk_types if hk_signature(i) == name), None)
            if hk_id is None:
                raise KeyError(f"Type {name} not found in the HKLib xml")

            resolve(hk_id)

        done: set[str] = set()

        def insert(hk_id: str) -> None:
            if hk_id in done:
                return
            done.add(hk_id)

            el = hk_type(hk_id)
            tid = hk_to_tid[hk_id]
            parent_hk = el.get("Parent", "0")
            subtype_hk = el.get("SubType", "0")

            # Inherited fields are collected from the parent, so it has to exist first
            if parent_hk in new_hk_ids:
                insert(parent_hk)

            parent = hk_to_tid[parent_hk] if parent_hk != "0" else None
            subtype = hk_to_tid[subtype_hk] if subtype_hk != "0" else None
            typeparams = [hk_to_tid[tp] for tp in hk_template_params(el)]
            if not typeparams and subtype:
                # The subtype is always the first template argument
                typeparams = [subtype]

            name = el.get("Name")
            fmt = int(el.get("Format", 0))
            version = int(el.get("Version", 0))
            flags = int(el.get("Flags", 0))
            members = [
                (m.get("Name"), hk_to_tid[m.get("Type")], m.get("Flags", "0"))
                for m in el.findall("./Members/Member")
            ]

            fields = dict(self.types[parent]["fields"]) if parent else {}
            fields.update({fname: ftype for fname, ftype, _ in members})

            fullname = name
            if subtype in self.types:
                fullname = f"{name}< {self.types[subtype]['name']} >"
            elif subtype:
                # Not inserted yet, but we know its name
                fullname = f"{name}< {hk_type(subtype_hk).get('Name')} >"

            self.types[tid] = {
                "name": name,
                "format": fmt,
                "fields": fields,
                "subtype": subtype,
                "typeparams": typeparams,
                "parent": parent,
                "fullname": fullname,
            }

            type_el = ET.Element("type", id=tid)
            ET.SubElement(type_el, "name", value=name)
            if parent:
                ET.SubElement(type_el, "parent", id=parent)
            ET.SubElement(type_el, "format", value=str(fmt))
            if subtype:
                ET.SubElement(type_el, "subtype", id=subtype)
            if typeparams:
                params_el = ET.SubElement(
                    type_el, "parameters", count=str(len(typeparams))
                )
                for tp in typeparams:
                    ET.SubElement(params_el, "typeparam", id=tp)
            if version:
                ET.SubElement(type_el, "version", value=str(version))
            if flags:
                ET.SubElement(type_el, "flags", value=str(flags))
            if el.find("Members") is not None:
                fields_el = ET.SubElement(type_el, "fields", count=str(len(members)))
                for fname, ftype, fflags in members:
                    ET.SubElement(
                        fields_el, "field", name=fname, typeid=ftype, flags=fflags
                    )

            self._new_type_elems.append(type_el)

        for hk_id in list(new_hk_ids):
            insert(hk_id)

        # Cached lookups may have missed the new types / subclasses
        self.find_first_type_by_name.cache_clear()
        self.get_compatible_types.cache_clear()

        return [hk_to_tid[hk_id] for hk_id in new_hk_ids]

    def write_new_types(self, root: ET._Element) -> None:
        """Add the types inserted after loading to a tagfile tree.

        Meant to be called on a copy of the tagfile tree right before it is saved.
        The new types are placed after the last existing type definition.
        """
        existing = {t.get("id") for t in root.findall(".//type")}
        last = root.xpath("(.//type)[last()]")
        anchor = last[0] if last else None

        for type_el in self._new_type_elems:
            if type_el.get("id") in existing:
                continue

            type_el = deepcopy(type_el)
            if anchor is not None:
                anchor.addnext(type_el)
            else:
                root.insert(0, type_el)
            anchor = type_el
