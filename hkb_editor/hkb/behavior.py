import xml.etree.ElementTree as ET

from .type_registry import type_registry
from .hkb_types import HkbRecord, HkbArray, HkbString


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

        # There's a special object storing the string values referenced from HKS
        strings_type, _ = type_registry.find_type_by_name("hkbBehaviorGraphStringData")
        strings_id = root.find(f".//object[@typeid={strings_type}]").attrib["id"]
        strings_obj = self.objects[strings_id]

        self.events: HkbArray = strings_obj.eventNames
        self.variables: HkbArray = strings_obj.variableNames
        self.animations: HkbArray = strings_obj.animationNames

    def add_event(self, event_name: str) -> int:
        self.events.append(HkbString.new(event_name))
        return len(self.events) - 1

    def add_variable(self, variable_name: str) -> int:
        self.variables.append(HkbString.new(variable_name))
        return len(self.variables) - 1

    def add_animation(self, animation_name: str) -> int:
        self.animations.append(HkbString.new(animation_name))
        return len(self.animations) - 1
