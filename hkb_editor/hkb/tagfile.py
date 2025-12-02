from typing import Callable, Generator, TYPE_CHECKING, Any
import logging
from collections import deque
from copy import deepcopy
from functools import cache
import re

# lxml supports full xpath, which is beneficial for us
from lxml import etree as ET
import networkx as nx

from .xml import get_xml_parser, add_type_comments
from .type_registry import TypeRegistry
from .query import query_objects

if TYPE_CHECKING:
    from .hkb_types import HkbRecord, HkbPointer, XmlValueHandler


_undefined = object()


class Tagfile:
    def __init__(self, xml_file: str):
        from .hkb_types import HkbRecord

        self.file = xml_file

        self._tree: ET._ElementTree = ET.parse(xml_file, parser=get_xml_parser())
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

        self.behavior_root: HkbRecord = self.find_first_by_type_name(
            "hkRootLevelContainer"
        )

    def save_to_file(self, file_path: str) -> None:
        # Add comments on the copy. We don't want to keep these as they can mess up
        # parsing and object evaluation (e.g. locating fields)
        tmp = deepcopy(self._tree)
        add_type_comments(tmp, self)
        ET.indent(tmp)
        tmp.write(file_path)

        self.file = file_path

    def root_graph(self):
        # Caching this would be nice, but then we'd have to update it anytime there are 
        # changes to the graph
        return self.build_graph(self.behavior_root.object_id)

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

    def get_unique_object_paths(
        self, target_id: "str | HkbRecord"
    ) -> Generator[list[str], None, None]:
        """Find paths through the behavior graph that lead to the start object.

        To resolve a unique path to an object, use resolve_unique_object_path.

        Each element of a path is an attribute path, e.g. "transitions:2/transition".
        To resolve a path, start with the behavior's root object and get the field
        denoted by the first attribute path. This should return a pointer, which will
        lead you to the next object on which you resolve the second attribute path,
        and so on.

        As object IDs are not stable and may change between HkLib conversions, this is
        the only reliable way of locating an object. Due to the nature of the graph
        structure it is possible for an object to be referenced by more than one parent,
        thus yielding multiple unique paths. This method will find all shortest simple
        paths, as per the networkx definition.

        Parameters
        ----------
        target_id : str | HkbRecord
            The object you want to locate.

        Yields
        ------
        Generator[list[str], None, None]
            Unique paths to reach the target object from the behavior root.
        """
        from .hkb_types import HkbPointer

        root_paths = nx.all_shortest_paths(
            self.root_graph(), self.behavior_root.object_id, target_id
        )

        for path in root_paths:
            chain = []
            # Last element is the object itself
            for idx, node_id in enumerate(path[:-1]):
                obj: HkbRecord = self.objects[node_id]
                next_node = path[idx + 1]
                for attr_path, ptr in obj.find_fields_by_type(HkbPointer):
                    if ptr.get_value() == next_node:
                        chain.append(attr_path)
                        break

            yield chain

    def resolve_unique_object_path(
        self, object_path: list[str], default: Any = _undefined
    ) -> "HkbRecord":
        from .hkb_types import HkbPointer

        target_obj = self.behavior_root

        # Follow the chain
        for idx, path in enumerate(object_path):
            try:
                ptr: HkbPointer = target_obj.get_field(path)
            except KeyError:
                if default is not _undefined:
                    return default

                raise

            if not isinstance(ptr, HkbPointer):
                if default is not _undefined:
                    return default

                raise ValueError(
                    f"Failed to resolve root path ({idx}) {target_obj}/{path}: not a pointer (is {str(ptr)})"
                )

            new_target_obj = ptr.get_target()

            if new_target_obj is None:
                if default is not _undefined:
                    return default

                raise ValueError(
                    f"Failed to resolve root path ({idx}) {target_obj}/{path}: target is None"
                )

            target_obj = new_target_obj

        return target_obj

    @cache
    def get_most_common_object(self, type_id: str) -> "HkbRecord":
        max_ref = 0
        winner = None

        objects = self.query(f"type={type_id}")

        for candidate in objects:
            ref = len(list(self.find_references_to(candidate)))
            if ref > max_ref:
                winner = candidate
                max_ref = ref

        return winner

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

    def find_references_to(
        self, object_id: "str | HkbRecord"
    ) -> Generator["tuple[HkbRecord, str, HkbPointer]", None, None]:
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

            for path, ptr in record.find_fields_by_type(HkbPointer):
                if ptr.get_value() == object_id:
                    yield (record, path, ptr)

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

    def find_hierarchy_parents_for(
        self, object_id: "HkbRecord | str", parent_type: str
    ) -> Generator["HkbRecord", None, None]:
        from .hkb_types import HkbRecord

        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        candidates = [object_id]
        visited = set(candidates)

        while candidates:
            candidate_id = candidates.pop()
            visited.add(candidate_id)

            # Search upwards through the hierarchy to see if any ancestors match our criteria
            parents: list[ET._Element] = self._tree.xpath(
                f"/*/object[.//pointer[@id='{candidate_id}']]"
            )

            for parent_elem in parents:
                oid = parent_elem.get("id")

                if parent_elem.get("typeid") == parent_type:
                    yield self.objects[oid]

                # Parent didn't match, but might still have a matching parent
                if oid not in visited:
                    candidates.append(oid)

        return None

    def query(
        self,
        query_str: str,
        *,
        object_filter: Callable[["HkbRecord"], bool] = None,
        search_root: "HkbRecord | str" = None,
    ) -> Generator["HkbRecord", None, None]:
        # TODO would be nice to place this in the query module, but neither the query nor 
        # the HkbRecord objects have any knowledge about the graph structure
        parent_pattern = r"\bparent=(object[0-9]+)\b"
        parent_query = re.search(parent_pattern, query_str)
        if parent_query:
            search_root = parent_query.group(1)
            query_str = re.sub(parent_pattern, "", query_str).strip()

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
