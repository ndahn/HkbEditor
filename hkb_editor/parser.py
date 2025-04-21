from typing import Any
from xml.etree import ElementTree
import networkx as nx

from behavior import Behavior
from hkb_types.hkb_base import HkbObject, HkbType, HkbReference, HkbArray


def parse_behavior(beh_xml: str) -> Behavior:
    tree = ElementTree.parse(beh_xml)
    root = tree.getroot()

    types: dict[str, HkbType] = {}
    objects: dict[str, HkbObject] = {}
    g = nx.DiGraph()

    def delve_object(elem: ElementTree.Element, root_id: str, path: list = None):
        if path is None:
            path = []

        if elem.tag == "record":
            data = {}
            for field in elem:
                name = field.attrib["name"]
                path.append(name)
                data[name] = delve_object(field, root_id, path)
                path.pop()
            return data
        
        elif elem.tag == "field":
            return delve_object(elem[0], root_id, path)

        elif elem.tag == "array":
            element_typeid = elem.attrib["elementtypeid"]
            arr = HkbArray(element_typeid)
            for idx, child in enumerate(elem):
                path.append(f"[{idx}]")
                arr.append(delve_object(child, root_id, path))
                path.pop()
            return arr

        elif elem.tag == "pointer":
            target = elem.attrib["id"]
            g.add_edge(root_id, target, path="/".join(path))
            return HkbReference(target)

        elif elem.tag == "string":
            return elem.attrib["value"]

        elif elem.tag == "integer":
            return int(elem.attrib["value"])

        elif elem.tag == "real":
            return float(elem.attrib["dec"].replace(",", "."))

        elif elem.tag == "bool":
            return elem.attrib["value"].lower() == "true"

        else:
            p = root_id + "/" + "/".join(path)
            print(f"WARNING: Did not recognize node {p} ({elem.tag} {elem.attrib})")
            return {
                "hkb_type": elem.tag,
                "attr": dict(elem.attrib),
                "children": [delve_object(child, root_id, path) for child in elem],
            }

    reported = set()

    for elem in root:
        id = elem.attrib["id"]
        elem_type = elem.tag

        if elem_type == "type":
            name = elem.find("name").attrib["value"]
            fields = {}

            fields_node = elem.find("fields")
            if fields_node is not None:
                for field in fields_node:
                    fields[field.attrib["name"]] = field.attrib["typeid"]

            types[id] = HkbType(id, name, fields)

        elif elem_type == "object":
            typeid = elem.attrib["typeid"]
            record = elem.find("record")

            if record is None:
                print(f"WARNING: object {id} ({typeid}) does not have a record child")

            fields = delve_object(record, id)
            obj_cls = HkbObject.get_hkb_class(typeid)

            if obj_cls:
                obj = obj_cls(id=id, **fields)
            else:
                obj = HkbObject(id=id, **fields)
            
            objects[id] = obj

        else:
            if elem_type not in reported:
                print(f"WARNING: unknown top-level node type {elem_type}")
                reported.add(elem_type)

    return Behavior(g, types, objects)


if __name__ == "__main__":
    from os import path

    cwd = path.dirname(__file__)
    beh = parse_behavior(path.join(cwd, "..", "c0000_out.xml"))
    print(beh)
