from typing import Callable, Generator, TYPE_CHECKING, Any
from itertools import chain
# lxml supports full xpath, which is beneficial for us
from lxml import etree as ET

from .type_registry import TypeRegistry
from .query import query_objects

if TYPE_CHECKING:
    from .hkb_types import HkbRecord


class Tagfile:
    def __init__(self, xml_file: str):
        from .hkb_types import HkbRecord

        self.file = xml_file
        self._tree: ET._ElementTree = ET.parse(
            # lxml keeps comments, which affect subelement counts and iterations.
            # TODO we should handle comments properly at some point so they are kept,
            # but for now this is easier
            xml_file,
            parser=ET.XMLParser(remove_comments=True),
        )
        root: ET._Element = self._tree.getroot()

        # Some versions of HKLib seem to decompile floats with commas
        self.floats_use_commas = bool(root.xpath("(//real[contains(@dec, ',')])[1]"))
        
        self.type_registry = TypeRegistry()
        self.type_registry.load_types(root)

        # TODO hide behind a property, changing this dict should also affect the xml
        self.objects = {
            obj.attrib["id"]: HkbRecord.from_object(self, obj)
            for obj in root.findall(".//object")
        }

        # TODO cache objects by name and type_name for quick access

        objectid_values = [
            int(k[len("object") :])
            for k in self.objects.keys()
            if k.startswith("object")
        ]
        self._next_object_id = max(objectid_values, default=0) + 1

    def save_to_file(self, file_path: str) -> None:
        ET.indent(self._tree)
        self._tree.write(file_path)

    def retrieve_object(self, object_id: str) -> "HkbRecord":
        from .hkb_types import HkbRecord

        try:
            return self.objects[object_id]
        except KeyError:
            # Not cached, directly construct it from the xml
            elem = next(self._tree.xpath(f".//object[@id='{object_id}']"), None)
            if elem:
                return HkbRecord.from_object(self, elem)

        return None

    # TODO include subtypes
    def find_objects_by_type(
        self, type_id: str, include_derived: bool = False
    ) -> Generator["HkbRecord", None, None]:
        compatible = set([type_id])

        if include_derived:
            compatible.update(self.type_registry.get_compatible_types(type_id))

        for obj in self.objects.values():
            if obj.type_id in compatible:
                yield obj

    def find_first_by_type_name(
        self, type_name: str, default: Any = None
    ) -> "HkbRecord":
        # Used often enough to create a helper
        type_id = self.type_registry.find_first_type_by_name(type_name)
        return next(self.find_objects_by_type(type_id), default)

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

    def query(
        self,
        query_str: str,
        *,
        object_filter: Callable[["HkbRecord"], bool] = None,
    ) -> Generator["HkbRecord", None, None]:
        yield from query_objects(self.objects.values(), query_str, object_filter)

    def new_id(self, offset: int = 0) -> str:
        new_id = self._next_object_id + offset

        while new_id in self.objects:
            new_id += 1

        self._next_object_id = new_id + 1
        return f"object{new_id}"

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

        # Proper objects will have their <record> inside an <object> tag
        parent: ET._Element = obj.element.getparent()

        if parent is None:
            parent = self._tree.getroot()
        
        # Make sure to not leave an empty <object> tag behind!
        if parent.tag == "object":
            object_elem = parent
            parent.getparent().remove(object_elem)
        else:
            parent.remove(obj.element)
        
        return obj
