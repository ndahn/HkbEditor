from collections import deque
from enum import IntEnum
from lxml import etree as ET
import networkx as nx

from .tagfile import Tagfile
from .hkb_types import HkbRecord, HkbArray, HkbString


class HavokBehavior(Tagfile):
    class VariableType(IntEnum):
        BOOL = 0
        INT8 = 1
        INT16 = 2
        INT32 = 3
        REAL = 4
        POINTER = 5
        STRING = 6  # NOTE just an assumption, no examples for this
        VECTOR4 = 7
        QUATERNION = 8

    def __init__(self, xml_file: str):
        super().__init__(xml_file)

        # There's some special objects storing the string values referenced from HKS
        # TODO hide all of these behind properties or getters
        strings_type_id = self.type_registry.find_type_by_name(
            "hkbBehaviorGraphStringData"
        )
        strings_obj = next(self.find_objects_by_type(strings_type_id))

        self.events: HkbArray = strings_obj["eventNames"]
        self.variables: HkbArray = strings_obj["variableNames"]
        self.animations: HkbArray = strings_obj["animationNames"]

        # TODO hide all of these behind properties or getters
        graphdata_type_id = self.type_registry.find_type_by_name("hkbBehaviorGraphData")
        graphdata_obj = next(self.find_objects_by_type(graphdata_type_id))

        self.event_infos: HkbArray = graphdata_obj["eventInfos"]
        self.variable_infos: HkbArray = graphdata_obj["variableInfos"]
        self.variable_bounds: HkbArray = graphdata_obj["variableBounds"]

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
        self.event_infos.append(HkbRecord.new(self, self.event_infos.element_type_id))
        return len(self.events) - 1

    # TODO not so simple after all, add type and bounds to dialog
    def create_variable(
        self, variable_name: str, type_: VariableType = VariableType.INT32, min_: int = 0, max_: int = 0
    ) -> int:
        self.variables.append(
            HkbString.new(self, self.variables.element_type_id, variable_name)
        )
        self.variable_infos.append(
            HkbRecord.new(
                self,
                self.variable_infos.element_type_id,
                {
                    "type": type_,
                },
            )
        )
        self.variable_bounds.append(
            HkbRecord.new(
                self,
                self.variable_bounds.element_type_id,
                {
                    "min/value": min_,
                    "max/value": max_,
                },
            )
        )

        return len(self.variables) - 1

    def get_full_animation_name(self, animation_name: str, char_id: str = None) -> str:
        if not char_id:
            hkb_graph_type = self.type_registry.find_type_by_name("hkbBehaviorGraph")
            hkb_graph_obj = next(self.find_objects_by_type(hkb_graph_type))
            # TODO is this reliable?
            char_id = hkb_graph_obj["name"].split(".")[0]

        anim_anum = animation_name.split("_")[0]
        return f"..\..\..\..\..\Model\chr\{char_id}\hkx\{anim_anum}\{animation_name}.hkx"

    def get_animation_index(self, animation_name: str, char_id: str = None) -> int:
        full_anim_name = self.get_full_animation_name(animation_name, char_id)
        return self.animations.index(full_anim_name)

    def create_animation(self, animation_name: str, char_id: str = None) -> int:
        full_anim_name = self.get_full_animation_name(animation_name, char_id)
        self.animations.append(
            HkbString.new(self, self.animations.element_type_id, full_anim_name)
        )
        return len(self.animations) - 1
