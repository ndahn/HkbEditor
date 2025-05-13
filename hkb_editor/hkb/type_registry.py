import xml.etree.ElementTree as ET


class TypeRegistry:
    def __init__(self):
        self.types: dict[str, dict] = {}

    def load_types(self, root: ET.Element) -> None:
        self.types.clear()

        for t in root.findall(".//type"):
            type_id = t.attrib["id"]
            name = t.find("name").attrib["value"]
            fmt = int(t.find("format").attrib["value"])

            fields = (
                [
                    (f.attrib["name"], f.attrib["typeid"])
                    for f in t.find("fields").findall("field")
                ]
                if t.find("fields") is not None
                else []
            )

            subtype_el = t.find("subtype")
            subtype = subtype_el.attrib["id"] if subtype_el is not None else None

            self.types[type_id] = {
                "name": name,
                "format": fmt,
                "fields": fields,
                "subtype": subtype,
            }

    def find_type_by_name(self, type_name: str) -> tuple[str, dict]:
        for tid, t in self.types.items():
            if t["name"] == type_name:
                return tid, t

        return None, None

    def get_format(self, type_id: str) -> int:
        return self.types.get(type_id, {}).get("format", 0)

    def get_fields(self, type_id: str) -> list[tuple]:
        return self.types.get(type_id, {}).get("fields", [])

    def get_subtype(self, type_id: str) -> str:
        return self.types.get(type_id, {}).get("subtype")


# Global registry
type_registry = TypeRegistry()
