from typing import Generator
from collections import deque
import xml.etree.ElementTree as ET
import networkx as nx

from .type_registry import type_registry
from .hkb_types import HkbRecord, HkbArray, HkbString, wrap_element, get_value_handler


class HavokBehavior:
    def __init__(self, xml_file: str):
        self.tree = ET.parse(xml_file)
        root = self.tree.getroot()

        self.type_registry = type_registry
        type_registry.load_types(root)

        self.objects = {
            obj.attrib["id"]: HkbRecord.from_object(obj)
            for obj in root.findall(".//object")
        }

        # object0 is used for null pointers, but it's better to catch those when
        # resolving the pointer
        # if "object0" not in self.objects:
        #    # Treated as None
        #    t_void = self.type_registry.find_type_by_name("void")
        #    self.objects["object0"] = HkbRecord.new({}, t_void, "object0")

        # There's a special object storing the string values referenced from HKS
        strings_type_id = type_registry.find_type_by_name("hkbBehaviorGraphStringData")
        strings_id = root.find(f".//object[@typeid='{strings_type_id}']").attrib["id"]
        strings_obj = self.objects[strings_id]

        self.events: HkbArray = strings_obj.eventNames
        self.variables: HkbArray = strings_obj.variableNames
        self.animations: HkbArray = strings_obj.animationNames

    def find_objects_by_type(self, type_id: str) -> Generator[HkbRecord, None, None]:
        for obj in self.objects.values():
            if obj.type_id == type_id:
                yield obj

    def build_graph(self, root_id: str):
        g = nx.DiGraph()

        todo: deque[tuple[str, ET.Element]] = deque()

        def expand(elem: ET.Element, parent_id: str) -> None:
            todo.extend(
                (parent_id, ptr)
                for ptr in elem.findall(".//pointer")
                if ptr.attrib["id"] != "object0"
            )

        root = self.objects[root_id]
        expand(root.element, root_id)
        g.add_node(root_id)

        while todo:
            # popleft: breadth first, pop(right): depth first
            parent_id, pointer_elem = todo.pop()
            pointer_id = pointer_elem.attrib["id"]
            g.add_edge(parent_id, pointer_id)

            obj = self.objects[pointer_id]
            expand(obj.element, obj.id)

        return g

    def add_object(self, record: HkbRecord, id: str = None) -> str:
        if id is None:
            if record.id:
                id = record.id
            else:
                id = self.new_object_id()

        record.id = id
        self.tree.getroot().append(record.as_object())
        self.objects[id] = record

        return id

    def add_event(self, event_name: str) -> int:
        self.events.append(HkbString.new(self.events.element_type_id, event_name))
        return len(self.events) - 1

    def add_variable(self, variable_name: str) -> int:
        self.variables.append(
            HkbString.new(self.variables.element_type_id, variable_name)
        )
        return len(self.variables) - 1

    def add_animation(self, animation_name: str) -> int:
        self.animations.append(
            HkbString.new(self.animations.element_type_id, animation_name)
        )
        return len(self.animations) - 1

    def new_object_id(self) -> str:
        last_key = max(
            int(k[len("object") :]) 
            for k in self.objects.keys() if k.startswith("object")
        )

        return f"object{last_key + 1}"
