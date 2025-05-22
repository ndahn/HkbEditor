from typing import Generator, TYPE_CHECKING
import xml.etree.ElementTree as ET

from .type_registry import TypeRegistry
if TYPE_CHECKING:
    from .hkb_types import HkbRecord


class Tagfile:
    def __init__(self, xml_file: str):
        from .hkb_types import HkbRecord

        self._tree = ET.parse(xml_file)
        root = self._tree.getroot()

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

    def new_id(self, base: str = "object", offset: int = 1) -> str:
        last_key = max(
            int(k[len(base) :]) for k in self.objects.keys() if k.startswith(base)
        )

        return f"base{last_key + offset}"

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
