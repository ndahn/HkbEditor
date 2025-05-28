from typing import Generator, TYPE_CHECKING

# lxml supports full xpath, which is beneficial for us
from lxml import etree as ET

from .type_registry import TypeRegistry
from .query import query_objects

if TYPE_CHECKING:
    from .hkb_types import HkbRecord


class Tagfile:
    def __init__(self, xml_file: str):
        from .hkb_types import HkbRecord

        self._tree: ET._ElementTree = ET.parse(xml_file)
        root: ET._Element = self._tree.getroot()

        self.type_registry = TypeRegistry()
        self.type_registry.load_types(root)

        # TODO hide behind a property, changing this dict should also affect the xml
        self.objects = {
            obj.attrib["id"]: HkbRecord.from_object(self, obj)
            for obj in root.findall(".//object")
        }

    def save_to_file(self, file_path: str) -> None:
        self._tree.write(file_path)

    def find_objects_by_type(self, type_id: str) -> Generator["HkbRecord", None, None]:
        for obj in self.objects.values():
            if obj.type_id == type_id:
                yield obj

    def find_parents_by_type(
        self, object_id: str, parent_type: str
    ) -> Generator["HkbRecord", None, None]:
        candidates = [object_id]
        visited = set(candidates)

        while candidates:
            candidate = candidates.pop()

            # Search upwards through the hierarchy to see if any ancestors match our criteria
            parents: list[ET._Element] = self._tree.xpath(
                f"/*/object[.//pointer[@id='{candidate}']]"
            )

            for parent_elem in parents:
                pid = parent_elem.attrib["id"]

                if parent_elem.attrib["typeid"] == parent_type:
                    yield self.objects[pid]

                # Parent didn't match, but might still have a matching parent
                if pid not in visited:
                    candidates.append(pid)
                    visited.add(pid)

        return None

    def query(self, query_str: str) -> Generator["HkbRecord", None, None]:
        yield from query_objects(self, query_str)

    def new_id(self, base: str = "object", offset: int = 1) -> str:
        last_key = max(
            int(k[len(base) :]) for k in self.objects.keys() if k.startswith(base)
        )

        return f"{base}{last_key + offset}"

    def add_object(self, record: "HkbRecord", id: str = None) -> str:
        if id is None:
            if record.object_id:
                id = record.object_id
            else:
                id = self.new_id()

        record.object_id = id
        self._tree.getroot().append(record.as_object())
        self.objects[id] = record

        return id

    def remove_object(self, id: str) -> "HkbRecord":
        obj = self.objects.pop(id)
        self._tree.getroot().remove(obj.element)
        return obj
