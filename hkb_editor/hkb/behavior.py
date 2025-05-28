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
        strings_type_id = self.type_registry.find_type_by_name(
            "hkbBehaviorGraphStringData"
        )
        strings_obj = next(self.find_objects_by_type(strings_type_id))

        self._events: HkbArray = strings_obj["eventNames"]
        self._variables: HkbArray = strings_obj["variableNames"]
        self._animations: HkbArray = strings_obj["animationNames"]

        graphdata_type_id = self.type_registry.find_type_by_name("hkbBehaviorGraphData")
        graphdata_obj = next(self.find_objects_by_type(graphdata_type_id))

        self._event_infos: HkbArray = graphdata_obj["eventInfos"]
        self._variable_infos: HkbArray = graphdata_obj["variableInfos"]
        self._variable_bounds: HkbArray = graphdata_obj["variableBounds"]

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
        self._events.append(HkbString.new(self, self._events.element_type_id, event_name))
        # This one never has any meaningful data, but must still have an entry 
        self._event_infos.append(HkbRecord.new(self, self._event_infos.element_type_id))
        return len(self._events) - 1

    def get_event(self, idx: int) -> str:
        return self._events[idx].get_value()

    def find_event(self, event: str) -> int:
        return self._events.index(event)

    def delete_event(self, idx: int = -1) -> None:
        del self._event_infos[idx]
        del self._events[idx]

    # HKS variables
    # TODO not so simple after all, add type and bounds to dialog
    def create_variable(
        self, variable_name: str, type_: VariableType = VariableType.INT32, min_: int = 0, max_: int = 0
    ) -> int:
        self._variables.append(
            HkbString.new(self, self._variables.element_type_id, variable_name)
        )

        # TODO these must have matching entries as well
        self._variable_infos.append(
            HkbRecord.new(
                self,
                self._variable_infos.element_type_id,
                {
                    "type": type_,
                },
            )
        )
        self._variable_bounds.append(
            HkbRecord.new(
                self,
                self._variable_bounds.element_type_id,
                {
                    "min/value": min_,
                    "max/value": max_,
                },
            )
        )

        return len(self._variables) - 1

    def get_variable(self, idx: int) -> str:
        return self._variables[idx].get_value()

    def find_variable(self, variable: str) -> int:
        return self._variables.index(variable)

    def get_variable_bounds(self, idx: int) -> tuple[int, int]:
        bounds: HkbRecord = self._variable_bounds[idx]
        lo = bounds.get_path_value("min/value", resolve=True)
        hi = bounds.get_path_value("max/value", resolve=True)
        return [lo, hi]

    def get_variable_type(self, idx: int) -> VariableType:
        info: HkbRecord = self._variable_infos[idx]
        return info.get_field("type", resolve=True)

    def delete_variable(self, idx: int = -1) -> None:
        del self._variable_bounds[idx]
        del self._variable_infos[idx]
        del self._variables[idx]

    # animationNames array
    def get_full_animation_name(self, animation_name: str, char_id: str = None) -> str:
        if not char_id:
            hkb_graph_type = self.type_registry.find_type_by_name("hkbBehaviorGraph")
            hkb_graph_obj = next(self.find_objects_by_type(hkb_graph_type))
            # TODO is this reliable?
            char_id = hkb_graph_obj["name"].split(".")[0]

        anim_anum = animation_name.split("_")[0]
        return f"..\..\..\..\..\Model\chr\{char_id}\hkx\{anim_anum}\{animation_name}.hkx"

    def create_animation(self, animation_name: str, char_id: str = None) -> int:
        full_anim_name = self.get_full_animation_name(animation_name, char_id)
        self._animations.append(
            HkbString.new(self, self._animations.element_type_id, full_anim_name)
        )
        return len(self._animations) - 1

    def get_animation(self, idx: int, full_name: bool = False) -> str:
        anim: str = self._animations[idx].get_value()
        if full_name:
            return anim

        # Extract the aXXX_YYYYYY part (see get_full_animation_name)
        return anim.rsplit("\\", maxsplit=1)[-1].rsplit(".", maxsplit=1)[0]

    def find_animation(self, animation_name: str, char_id: str = None) -> int:
        full_anim_name = self.get_full_animation_name(animation_name, char_id)
        return self._animations.index(full_anim_name)

    def delete_animation(self, idx: int = -1) -> None:
        del self._animations[idx]