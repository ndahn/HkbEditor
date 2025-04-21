from typing import NewType, Iterable
from dataclasses import dataclass, asdict


_hkb_class_registry = {}


HkbReference = NewType("HkbReference", str)


@dataclass
class HkbObject:
    id: str

    def __init_subclass__(cls, typeid: str):
        cls.typeid = typeid
        _hkb_class_registry[typeid] = cls

    @classmethod
    def get_hkb_class(cls, typeid: str):
        return _hkb_class_registry.get(typeid)
    
    def __init__(self, id: str, **kwargs):
        self.id = id
        # Will not be a dataclass field
        self.extra_fields = kwargs

    def get_name(self):
        return getattr(self, "name", None)
    
    def fields(self):
        return asdict(self)


@dataclass
class HkbType:
    id: str
    name: str
    fields: dict[str, HkbReference]

