from typing import TYPE_CHECKING, Any, Generator
from logging import getLogger
from functools import cache
from lxml import etree as ET

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

    def load_types(self, root: ET._Element) -> None:
        self.types.clear()

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
