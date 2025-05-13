from typing import NewType, Iterable, Any
from xml.etree import ElementTree as ET


HkbReference = NewType("HkbReference", str)


class HkbArray(list):
    def __init__(self, element_type_id: str, elements: Iterable = None):
        self.element_type_id = element_type_id
        if elements is None:
            elements = []
        super().__init__(elements)


class XmlObject:
    @classmethod
    def create(cls, id: str, typeid: str, **fields):
        obj = ET.Element("object", {"id": id, "typeid": typeid})
        record = ET.SubElement(obj, "record")

        for name, val in fields.items():
            field = ET.SubElement(record, "field", {"name": name})
            _append_value(field, name, val)

        return cls(obj)

    def __init__(self, xml_node: ET.Element):
        # TODO userdata name variableBindingSet, propertyBag
        self._node = xml_node
        self._id = xml_node.attrib["id"]
        self._fields = {}

        for field in xml_node.iterfind("field"):
            name = field.attrib["name"]
            val = self._get_field_value(field)
            self._fields[name] = val

    @property
    def id(self):
        return self._id
    
    def get(self, field: str):
        return self._fields[field]
    
    def set(self, field: str, val: Any):
        if field not in self._fields:
            raise ValueError(f"Node {self} does not have a field named {field}")
        
        field_type = type(self._fields[field])
        if field_type != type(val):
            try:
                val = field_type(val)
            except:
                raise ValueError(f"Value {val} is incompatible with field {field} of type {field_type}")
            
        self._fields[field] = val
        self._set_field_value(self._node, field, val)


def _get_field_value(elem: ET.Element):
    if elem.tag == "field":
        return _get_field_value(elem[0])

    elif elem.tag == "pointer":
        target = elem.attrib["id"]
        return HkbReference(target)

    elif elem.tag == "string":
        return elem.attrib["value"]

    elif elem.tag == "integer":
        return int(elem.attrib["value"])

    elif elem.tag == "real":
        return float(elem.attrib["dec"].replace(",", "."))

    elif elem.tag == "bool":
        return elem.attrib["value"].lower() == "true"

    elif elem.tag == "array":
        element_typeid = elem.attrib["elementtypeid"]
        arr = HkbArray(element_typeid)
        for child in elem:
            arr.append(_get_field_value(child))
        return arr
    
    elif elem.tag == "record":
        data = {}
        for field in elem:
            name = field.attrib["name"]
            data[name] = _get_field_value(field)
        return data
    
    else:
        print(f"WARNING: Did not recognize node {p} ({elem.tag} {elem.attrib})")
        return {
            "hkb_type": elem.tag,
            "attr": dict(elem.attrib),
            "children": [_get_field_value(child) for child in elem],
        }


def _set_field_value(elem: ET.Element, name: str, val: Any):
    for child in elem.iterfind("field"):
        if child.attrib["name"] == name:
            field = child[0]
            break
    else:
        raise ValueError(f"Unknown field {name}")
    
    if field.tag == "string":
        field.attrib["value"] = val

    elif field.tag == "integer":
        field.attrib["value"] = str(int(val))

    elif field.tag == "real":
        field.attrib["dec"] = str(float(val)).replace(".", ",")

    elif field.tag == "bool":
        field.attrib["value"] = "true" if val else "false"

    elif field.tag == "pointer":
        # NOTE could verify that the ID exists
        field.attrib["id"] = val

    elif field.tag == "array":
        _append_value(field, val)

    elif field.tag == "record":
        assert isinstance(val, dict)
        for subfield in field:
            subname = subfield.attrib["name"]
            if subname in val:
                _set_field_value(subfield, subname, val[subname])


class HkbObject(XmlObject):
    @classmethod
    def create(
        cls,
        id: str,
        typeid: str,
        name: str = "",
        userData: int = 0,
        variableBindingSet: str = "",  # TODO VariableBindingSet
        propertyBag: HkbArray = "",  # TODO DefaultPropertyBack
        **fields
    ):
        super().create(
            id,
            typeid,
            name=name,
            userData=userData,
            variableBindingSet=variableBindingSet,
            propertyBag=propertyBag,
            **fields
        )

    @property
    def name(self):
        return self.get("name")
        
    @property
    def userData(self):
        return self.get("userData")
        
    @property
    def variableBindingSet(self):
        return self.get("variableBindingSet")
        
    @property
    def propertyBag(self):
        return self.get("propertyBag")
        
    @name.setter
    def name(self, val):
        self.set("name", val)

    @userData.setter
    def userData(self, val):
        self.set("userData", val)

    @variableBindingSet.setter
    def variableBindingSet(self, val):
        self.set("variableBindingSet", val)

    @propertyBag.setter
    def propertyBag(self, val):
        self.set("propertyBag", val)


def _append_value(parent: ET.Element, val: Any):
    if isinstance(val, str):
        ET.SubElement(parent, "string", {"value": val})

    elif isinstance(val, int):
        ET.SubElement(parent, "integer", {"value": str(val)})

    elif isinstance(val, float):
        ET.SubElement(parent, "real", {"dec": str(val).replace(".", ",")})

    elif isinstance(val, bool):
        ET.SubElement(parent, "bool", {"value": "true" if val else "false"})

    elif isinstance(val, dict) and val.get("pointer_id"):
        ET.SubElement(parent, "pointer", {"id": val["pointer_id"]})

    elif isinstance(val, list):
        if isinstance(val, HkbArray):
            element_typeid = val.element_type_id
        elif val:
            element_typeid = val[0].get("elementtypeid", "type0")
        else:
            element_typeid = "type0"
        
        array = ET.SubElement(parent, "array", {
            "count": str(len(val)),
            "elementtypeid": element_typeid
        })

        for v in val:
            _append_value(array, v)

    elif isinstance(val, dict):
        record = ET.SubElement(parent, "record")
        for key, subval in val.items():
            field = ET.SubElement(record, "field", {"name": key})
            _append_value(field, subval)
