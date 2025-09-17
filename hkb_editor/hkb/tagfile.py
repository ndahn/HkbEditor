from typing import Callable, Generator, TYPE_CHECKING, Any
import logging
from collections import deque

# lxml supports full xpath, which is beneficial for us
from lxml import etree as ET
import networkx as nx

from .type_registry import TypeRegistry
from .query import query_objects

if TYPE_CHECKING:
    from .hkb_types import HkbRecord, HkbPointer, XmlValueHandler


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
        self.objects: dict[str, HkbRecord] = {
            obj.get("id"): HkbRecord.from_object(self, obj)
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
        self.file = file_path

    def build_graph(self, root_id: str):
        g = nx.DiGraph()

        visited = set()
        todo: deque[tuple[str, ET.Element]] = deque()

        def expand(elem: ET.Element, parent_id: str) -> None:
            if parent_id in visited:
                return

            todo.extend(
                (parent_id, ptr)
                for ptr in elem.findall(".//pointer")
                if ptr.attrib["id"] != "object0"
            )
            visited.add(parent_id)

        root = self.objects[root_id]
        expand(root.element, root_id)
        g.add_node(root_id)

        logger = logging.getLogger()

        while todo:
            # popleft: breadth first, pop(right): depth first
            parent_id, pointer_elem = todo.pop()
            pointer_id = pointer_elem.attrib["id"]

            obj = self.objects.get(pointer_id)
            if obj:
                g.add_edge(parent_id, pointer_id)
                expand(obj.element, obj.object_id)
            else:
                logger.warning(
                    f"Object {parent_id} is referencing non-existing object {pointer_id}"
                )

        return g

    def retrieve_object(self, object_id: str) -> "HkbRecord":
        from .hkb_types import HkbRecord

        try:
            return self.objects[object_id]
        except KeyError:
            # Not cached, directly construct it from the xml
            elem = self._tree.xpath(f".//object[@id='{object_id}']")[0]
            if elem:
                return HkbRecord.from_object(self, elem)

        return None

    def find_object_for(self, item: "XmlValueHandler | ET._Element") -> "HkbRecord":
        from .hkb_types import XmlValueHandler
        
        if isinstance(item, XmlValueHandler):
            item = item.element

        parent: ET._Element = item

        while parent is not None and not parent.tag == "object":
            parent = parent.getparent()

        if parent is not None:
            oid = parent.get("id")
            return self.objects.get(oid)

        return None

    def find_referees(
        self, object_id: "str | HkbRecord"
    ) -> Generator["HkbPointer", None, None]:
        from .hkb_types import HkbRecord, HkbPointer

        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        if not object_id:
            return

        # We could search for the pointer itself, but to return it properly we need at
        # the very least the pointer's specific type, for which we need the parent record
        for xmlrecord in self._tree.xpath(f"/*/object[.//pointer[@id='{object_id}']]"):
            record = self.objects[xmlrecord.get("id")]
            ptr: HkbPointer

            for _, ptr in record.find_fields_by_type(HkbPointer):
                if ptr.get_value == object_id:
                    yield ptr

    def find_first_by_type_name(
        self, type_name: str, default: Any = None
    ) -> "HkbRecord":
        # Used often enough to create a helper
        type_id = self.type_registry.find_first_type_by_name(type_name)
        return next(self.find_objects_by_type(type_id), default)

    def find_objects_by_type(
        self, type_id: str, include_derived: bool = False
    ) -> Generator["HkbRecord", None, None]:
        compatible = set([type_id])

        if include_derived:
            compatible.update(self.type_registry.get_compatible_types(type_id))

        for obj in self.objects.values():
            if obj.type_id in compatible:
                yield obj

    def find_hierarchy_parent_for(
        self, object_id: "HkbRecord | str", parent_type: str
    ) -> Generator["HkbRecord", None, None]:
        from .hkb_types import HkbRecord

        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        candidates = [object_id]
        visited = set(candidates)

        while candidates:
            candidate = candidates.pop()

            # Search upwards through the hierarchy to see if any ancestors match our criteria
            parents: list[ET._Element] = self._tree.xpath(
                f"/*/object[.//pointer[@id='{candidate}']]"
            )

            for parent_elem in parents:
                oid = parent_elem.get("id")

                if parent_elem.get("typeid") == parent_type:
                    yield self.objects[oid]

                # Parent didn't match, but might still have a matching parent
                if oid not in visited:
                    candidates.append(oid)
                    visited.add(oid)

        return None

    def query(
        self,
        query_str: str,
        *,
        object_filter: Callable[["HkbRecord"], bool] = None,
        search_root: "HkbRecord | str" = None,
    ) -> Generator["HkbRecord", None, None]:
        if search_root:
            from .hkb_types import HkbRecord

            if isinstance(search_root, HkbRecord):
                search_root = search_root.object_id

            g = self.build_graph(search_root)
            objects = [self.objects[node] for node in g.nodes()]
        else:
            objects = self.objects.values()

        yield from query_objects(objects, query_str, object_filter)

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

        if id in self.objects:
            raise ValueError(f"An object with ID {id} already exists")
            
        record.object_id = id
        self._tree.getroot().append(record.as_object())
        self.objects[id] = record

        return id

    def delete_object(self, object_id: "HkbRecord | str") -> "HkbRecord":
        """Delete the specified object from the behavior. 
        
        Note that this will not update any pointers referring to the object.

        Parameters
        ----------
        object_id : str
            The HkbRecord object or object ID to remove.

        Returns
        -------
        HkbRecord
            The removed object.
        """
        from .hkb_types import HkbRecord

        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        obj = self.objects.pop(object_id)

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
