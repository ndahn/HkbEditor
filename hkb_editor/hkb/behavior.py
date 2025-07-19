from typing import Any
from collections import deque
from dataclasses import dataclass
import logging
from lxml import etree as ET
import networkx as nx

from .tagfile import Tagfile
from .hkb_types import HkbRecord, HkbArray
from .hkb_enums import hkbVariableInfo_VariableType as VariableType
from .cached_array import CachedArray


_undefined = object()


@dataclass
class HkbVariable:
    name: str
    vtype: VariableType
    vmin: int
    vmax: int

    def astuple(self) -> tuple[str, int, int, int]:
        return (self.name, self.vtype, self.vmin, self.vmax)


class HavokBehavior(Tagfile):
    def __init__(self, xml_file: str):
        super().__init__(xml_file)

        # There's some special objects storing the string values referenced from HKS
        strings_type_id = self.type_registry.find_first_type_by_name(
            "hkbBehaviorGraphStringData"
        )
        strings_obj = next(self.find_objects_by_type(strings_type_id))

        # Querying the actual values of a full array can be very slow, especially for
        # arrays with 10s of thousands of items. Caching these here will increase the
        # initial file opening time by a few seconds, but in return the user won't have
        # to sit idle every time they open a select dialog or similar
        self._events = CachedArray[str](strings_obj["eventNames"])
        self._variables = CachedArray[str](strings_obj["variableNames"])
        self._animations = CachedArray[str](strings_obj["animationNames"])

        graphdata_type_id = self.type_registry.find_first_type_by_name(
            "hkbBehaviorGraphData"
        )
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

    def create_event(self, event_name: str, idx: int = None) -> int:
        if idx is None:
            idx = len(self._events)

        self._events.insert(idx, event_name)

        # This one never has any meaningful data, but must still have an entry
        self._event_infos.insert(
            idx, HkbRecord.new(self, self._event_infos.element_type_id)
        )

        if idx < 0:
            return len(self._events) - idx

        return idx

    def get_events(self) -> list[str]:
        return self._events.get_value()

    def get_event(self, idx: int) -> str:
        return self._events[idx]

    def find_event(self, event: str, default: Any = _undefined) -> int:
        try:
            return self._events.index(event)
        except ValueError:
            if default != _undefined:
                return default
            raise

    def rename_event(self, idx: int, new_name: str) -> None:
        self._events[idx] = new_name

    def delete_event(self, idx: int = -1) -> None:
        del self._event_infos[idx]
        del self._events[idx]

    # HKS variables
    def create_variable(
        self,
        variable_name: str,
        var_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
        idx: int = None,
    ) -> int:
        if idx is None:
            idx = len(self._variables)

        if isinstance(var_type, str):
            var_type = VariableType[var_type]

        var_type = VariableType(var_type)
        
        self._variables.insert(idx, variable_name)

        # These must have matching entries as well
        self._variable_infos.insert(
            idx,
            HkbRecord.new(
                self,
                self._variable_infos.element_type_id,
                {
                    "type": var_type.value,
                },
            ),
        )
        self._variable_bounds.insert(
            idx,
            HkbRecord.new(
                self,
                self._variable_bounds.element_type_id,
                {
                    "min/value": range_min,
                    "max/value": range_max,
                },
            ),
        )

        if idx < 0:
            return len(self._variables) - idx

        return idx

    def get_variables(self, full_info: bool = False) -> list[str] | list[HkbVariable]:
        if full_info:
            return [self.get_variable(i) for i in range(len(self._variables))]

        return self._variables.get_value()

    def get_variable_name(self, idx: int) -> str:
        return self._variables[idx]

    def get_variable(self, idx: int) -> HkbVariable:
        return HkbVariable(
            self.get_variable_name(idx),
            self.get_variable_type(idx),
            *self.get_variable_bounds(idx),
        )

    def find_variable(self, variable: str, default: Any = _undefined) -> int:
        try:
            return self._variables.index(variable)
        except ValueError:
            if default != _undefined:
                return default
            raise

    def get_variable_type(self, idx: int) -> VariableType:
        info: HkbRecord = self._variable_infos[idx]
        type_idx = info.get_field("type", resolve=True)
        return VariableType(type_idx)

    def get_variable_bounds(self, idx: int) -> tuple[int, int]:
        bounds: HkbRecord = self._variable_bounds[idx]
        lo = bounds.get_field("min/value", resolve=True)
        hi = bounds.get_field("max/value", resolve=True)
        return [lo, hi]

    def delete_variable(self, idx: int = -1) -> None:
        del self._variable_bounds[idx]
        del self._variable_infos[idx]
        del self._variables[idx]

    # animationNames array
    def get_full_animation_name(self, animation_name: str) -> str:
        ref = self._animations[-1]
        parts = ref.split("\\")

        # Assume it's already a full name
        if animation_name.startswith(parts[0]):
            return animation_name

        # Usually of the form
        # ..\..\..\..\..\Model\chr\c0000\hkx\a123\a123_123456.hkx
        parts[-2] = animation_name.split("_")[0]
        parts[-1] = animation_name + ".hkx"

        return "\\".join(parts)

    def get_short_animation_name(self, full_anim_name: str) -> str:
        return full_anim_name.rsplit("\\", maxsplit=1)[-1].rsplit(".", maxsplit=1)[0]

    def create_animation(self, animation_name: str, idx: int = None) -> int:
        if idx is None:
            idx = len(self._animations)

        full_anim_name = self.get_full_animation_name(animation_name)
        self._animations.insert(idx, full_anim_name)

        if idx < 0:
            return len(self._animations) - idx

        return idx

    def get_animations(self, full_names: bool = False) -> list[str]:
        if full_names:
            return self._animations.get_value()

        return [self.get_short_animation_name(a) for a in self._animations]

    def get_animation(self, idx: int, full_name: bool = False) -> str:
        anim: str = self._animations[idx]
        if full_name:
            return anim

        # Extract the aXXX_YYYYYY part (see get_full_animation_name)
        return self.get_short_animation_name(anim)

    def find_animation(self, animation_name: str, default: Any = _undefined) -> int:
        try:
            full_anim_name = self.get_full_animation_name(animation_name)
            return self._animations.index(full_anim_name)
        except ValueError:
            if default != _undefined:
                return default
            raise

    def rename_animation(self, idx: int, new_name: str) -> None:
        full_anim_name = self.get_full_animation_name(new_name)
        self._animations[idx] = full_anim_name

    def delete_animation(self, idx: int = -1) -> None:
        del self._animations[idx]
