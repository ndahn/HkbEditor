from collections import deque
from lxml import etree as ET
import networkx as nx

from .tagfile import Tagfile
from .hkb_types import HkbArray, HkbString


class HavokBehavior(Tagfile):
    def __init__(self, xml_file: str):
        super().__init__(xml_file)

        # There's a special object storing the string values referenced from HKS
        strings_type_id = self.type_registry.find_type_by_name(
            "hkbBehaviorGraphStringData"
        )
        strings_id = (
            self._tree.getroot()
            .find(f".//object[@typeid='{strings_type_id}']")
            .attrib["id"]
        )
        strings_obj = self.objects[strings_id]

        self.events: HkbArray = strings_obj["eventNames"]
        self.variables: HkbArray = strings_obj["variableNames"]
        self.animations: HkbArray = strings_obj["animationNames"]

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
            expand(obj.element, obj.object_id)

        return g

    def create_event(self, event_name: str) -> int:
        self.events.append(HkbString.new(self, self.events.element_type_id, event_name))
        return len(self.events) - 1

    def create_variable(self, variable_name: str) -> int:
        self.variables.append(
            HkbString.new(self, self.variables.element_type_id, variable_name)
        )
        return len(self.variables) - 1

    def create_animation(self, animation_name: str) -> int:
        self.animations.append(
            HkbString.new(self, self.animations.element_type_id, animation_name)
        )
        return len(self.animations) - 1
