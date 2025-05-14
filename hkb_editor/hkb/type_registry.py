from typing import Any
from logging import getLogger
import xml.etree.ElementTree as ET


_logger = getLogger("TypeRegistry")


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

            subtype = self._get_attribute(type_el, "subtype", "id")
            parent = self._get_attribute(type_el, "parent", "id")

            self.types[type_id] = {
                "name": name,
                "format": fmt,
                "fields": fields,
                "subtype": subtype,
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

    def find_type_by_name(self, type_name: str) -> str:
        for tid, t in self.types.items():
            if t["name"] == type_name:
                return tid

        return None

    def get_name(self, type_id: str) -> str:
        return self.types[type_id]["name"]

    def get_format(self, type_id: str) -> int:
        return self.types[type_id]["format"]

    def get_fields(self, type_id: str) -> list[tuple]:
        t = self.types[type_id]
        fields: list[tuple[str, str]] = []

        while t:
            fields.extend(t["fields"])
            parent = t.get("parent", None)
            t = self.types.get(parent, None)
        
        return fields

    def get_subtype(self, type_id: str) -> str:
        return self.types[type_id].get("subtype", None)

    def get_parent(self, type_id: str) -> str:
        return self.types[type_id].get("parent", None)


# Global registry
type_registry = TypeRegistry()
