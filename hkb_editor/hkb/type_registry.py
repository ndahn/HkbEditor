from typing import Any, Generator
from logging import getLogger
from lxml import etree as ET


_logger = getLogger(__name__)


class TypeRegistry:
    def __init__(self):
        self.types: dict[str, dict] = {}

    def load_types(self, root: ET.Element) -> None:
        self.types.clear()

        for type_el in root.findall(".//type"):
            type_id = type_el.attrib["id"]
            name = type_el.find("name").attrib["value"]
            
            # Seems to be inherited from the parent types
            fmt = self._resolve_attribute(root, type_id, "format", "value")
            if fmt is None:
                _logger.warning("Could not resolve format of type %s", type_id)
            else:
                fmt = int(fmt)

            fields = (
                [
                    (f.attrib["name"], f.attrib["typeid"])
                    for f in type_el.find("fields").findall("field")
                ]
                if type_el.find("fields") is not None
                else []
            )

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

            self.types[type_id] = {
                "name": name,
                "format": fmt,
                "fields": fields,
                "subtype": subtype,
                "typeparams": typeparams,
                "parent": parent,
            }

    def _get_attribute(self, elem: ET.Element, tag: str, key: str) -> str:
        attr_el = elem.find(tag)
        if attr_el is not None:
            return attr_el.attrib.get(key, None)

        return None

    def _resolve_attribute(self, root: ET.Element, type_id: str, attr_tag: str, attr: str) -> Any:
        val = None

        while type_id and val is None:
            elem = root.find(f".//type[@id='{type_id}']")
            val = self._get_attribute(elem, attr_tag, attr)
            type_id = self._get_attribute(elem, "parent", "id")
            
        return val

    def find_types_by_name(self, type_name: str) -> Generator[str, None, None]:
        for tid, t in self.types.items():
            if t["name"] == type_name:
                yield tid

    def find_first_type_by_name(self, type_name: str) -> str:
        return next(self.find_types_by_name(type_name))

    def get_name(self, type_id: str) -> str:
        return self.types[type_id]["name"]

    def get_format(self, type_id: str) -> int:
        return self.types[type_id]["format"]

    def get_fields(self, type_id: str) -> dict[str, str]:
        t = self.types[type_id]
        fields = {}

        while t:
            fields.update({f:ft for f,ft in t["fields"]})
            parent = t.get("parent", None)
            t = self.types.get(parent, None)
        
        return fields

    def get_subtype(self, type_id: str) -> str:
        return self.types[type_id].get("subtype", None)

    def get_typeparams(self, type_id: str) -> list[str]:
        return self.types[type_id].get("typeparams", [])

    def get_parent(self, type_id: str) -> str:
        return self.types[type_id].get("parent", None)

    def get_compatible_types(self, type_id: str) -> list[str]:
        parents = [type_id]
        res = []

        while parents:
            p = parents.pop()
            for tid, t in self.types.items():
                if p == t["parent"]:
                    res.append(tid)
                    parents.append(tid)

        return res
