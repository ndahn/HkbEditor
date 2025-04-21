import re
import networkx as nx

from .hkb_types import HkbObject, HkbType


class Behavior:
    class ObjectCache:
        def __init__(self, objects: dict[str, HkbObject]):
            self.by_id = {}
            self.by_type = {}
            self.by_name = {}

            for id, obj in objects.items():
                self.by_id[id] = obj
                self.by_type.setdefault(obj.typeid, []).append(obj)
                
                name = getattr(obj, "name", None)
                if name:
                    if name in self.by_name:
                        print(f"WARNING: name {name} is not unique")
                    self.by_name.setdefault(name, []).append(obj)

        def __getitem__(self, key):
            return self.by_id[key]
        
        def ids(self):
            return self.by_id.keys()
        
        def values(self):
            return self.by_id.values()
        
        def items(self):
            return self.by_id.items()

    def __init__(
        self, 
        graph: nx.DiGraph,
        types: dict[str, HkbType],
        objects: dict[str, HkbObject],
    ):
        self.graph = graph
        # TODO types don't have typeid
        self.types = Behavior.ObjectCache(types)
        self.objects = Behavior.ObjectCache(objects)

        # IDs are typically named "object1234"
        highest_id = max(self.objects.ids())
        self._id_offset = int(re.findall(r"\d+", highest_id)[0])

    def new_id(self, base: str = "object"):
        ret = f"{base}{self._id_offset}"
        self._id_offset += 1
        return ret
