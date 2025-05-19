from typing import Any, Type, Generator
import struct
import xml.etree.ElementTree as ET

from .type_registry import type_registry


class XmlValueHandler:
    @classmethod
    def new(cls, type_id: str, value: Any = None) -> "XmlValueHandler":
        raise NotImplementedError()

    def __init__(self, element: ET.Element, type_id: str):
        self.element = element
        self.type_id = type_id

    def get_value(self) -> Any:
        raise NotImplementedError()

    def set_value(self, value: Any) -> None:
        raise NotImplementedError()

    def xml(self) -> str:
        ET.indent(self.element)
        return ET.tostring(self.element, encoding="unicode")

    def __str__(self) -> str:
        return str(self.get_value())


class HkbString(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, value: str = None) -> "HkbString":
        val = str(value) if value is not None else ""
        elem = ET.Element("string", value=val)
        return HkbString(elem, type_id)

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "string":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)

    def get_value(self) -> str:
        return self.element.attrib["value"]

    def set_value(self, value: str) -> None:
        self.element.attrib["value"] = value


class HkbInteger(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, value: int = None) -> "HkbInteger":
        val = int(value) if value is not None else 0
        elem = ET.Element("integer", value=str(val))
        return HkbInteger(elem, type_id)

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "integer":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)

    def get_value(self) -> int:
        return int(self.element.attrib["value"])

    def set_value(self, value: int) -> None:
        self.element.attrib["value"] = value


class HkbFloat(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, value: float = None) -> "HkbFloat":
        val = float(value) if value is not None else 0.0
        ieee = cls.float_to_ieee754(val)
        elem = ET.Element("real", dec=str(val), hex=ieee)
        return HkbFloat(elem, type_id)

    @classmethod
    def float_to_ieee754(cls, value: float) -> str:
        # IEEE 754 representation for 64bit floats
        h = struct.unpack(">Q", struct.pack(">d", value))[0]
        return f"#{h}:016x"

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "real":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)

    def get_value(self) -> float:
        # Behaviors use commas as decimal separators
        return float(self.element.attrib["dec"].replace(",", "."))

    def set_value(self, value: float) -> None:
        # Behaviors use commas as decimal separators
        self.element.attrib["dec"] = str(value).replace(".", ",")
        self.element.attrib["hex"] = self.float_to_ieee754(value)


class HkbBool(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, value: bool = None) -> "HkbBool":
        val = bool(value) if value is not None else False
        rep = "true" if value else "false"
        elem = ET.Element("bool", value=rep)
        return HkbBool(elem, type_id)

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "bool":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)

    def get_value(self) -> bool:
        return self.element.attrib["value"].lower() == "true"

    def set_value(self, value: bool) -> None:
        self.element.attrib["value"] = "true" if value else "false"


class HkbPointer(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, value: str = None) -> "HkbInteger":
        val = str(value) if value is not None else "object0"
        elem = ET.Element("pointer", id=val)
        return HkbPointer(elem, type_id)

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "pointer":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)
        self.subtype = type_registry.get_subtype(type_id)

    def get_value(self) -> str:
        val = self.element.attrib["id"]
        if val == "object0":
            return ""

        return val

    def set_value(self, value: str) -> None:
        if value in ("", None):
            value = "object0"

        self.element.attrib["id"] = value


class HkbArray(XmlValueHandler):
    @classmethod
    def new(cls, type_id: str, values: list[XmlValueHandler] = None) -> "HkbArray":
        if values is None:
            values = []

        elem_type_id = type_registry.get_subtype(type_id)
        elem = ET.Element("array", count=len(values), elementtypeid=elem_type_id)
        elem.extend(item.element for item in values)

        return HkbArray(elem, type_id)

    def __init__(self, element: ET.Element, type_id: str):
        if element.tag != "array":
            raise ValueError(f"Invalid element {element}")

        super().__init__(element, type_id)
        self.element_type_id = element.attrib["elementtypeid"]

    @property
    def _count(self) -> int:
        return int(self.element.attrib["count"])

    @_count.setter
    def _count(self, new_count: int) -> None:
        self.element.attrib["count"] = new_count

    def get_value(self) -> list[XmlValueHandler]:
        return [wrap_element(e, self.element_type_id) for e in self.element]

    def set_value(self, values: list[XmlValueHandler]) -> None:
        for idx, item in enumerate(values):
            if item.type_id != self.element_type_id:
                raise ValueError(
                    f"Non-matching value type {item.type_id} (should be {self.element_type_id})"
                )

        self.element[:] = [v.element for v in values]
        self._count = len(values)

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Generator[XmlValueHandler, None, None]:
        for i in range(self._count):
            yield self[i]

    def __getitem__(self, index: int) -> XmlValueHandler:
        item = next(e for i, e in enumerate(self.element) if i == index)
        return wrap_element(item, self.element_type_id)

    def __setitem__(self, index: int, value: Any) -> None:
        if isinstance(value, XmlValueHandler):
            if value.type_id != self.element_type_id:
                raise ValueError(
                    f"Non-matching value type {value.type_id} (should be {self.element_type_id})"
                )

            value = value.get_value()

        self[index].set_value(value)

    def __delitem__(self, index: int) -> None:
        self.element[:] = [
            e.element for i, e in enumerate(self.get_value()) if e != index
        ]
        self._count -= 1

    def index(self, value: XmlValueHandler) -> int:
        if isinstance(value, XmlValueHandler):
            if value.type_id != self.element_type_id:
                raise ValueError(
                    f"Non-matching value type {value.type_id} (should be {self.element_type_id})"
                )

            value = value.get_value()

        for idx, item in enumerate(self):
            if item.get_value() == value:
                return idx

        raise ValueError("Item not found")

    def append(self, value: XmlValueHandler):
        if value.type_id != self.element_type_id:
            raise ValueError(
                f"Non-matching value type {value.type_id} (should be {self.element_type_id})"
            )

        self.element.append(value.element)
        self._count += 1

    def insert(self, index: int, value: XmlValueHandler) -> None:
        if value.type_id != self.element_type_id:
            raise ValueError(
                f"Non-matching value type {value.type_id} (should be {self.element_type_id})"
            )

        self.element.insert(index, value.element)
        self._count += 1


class HkbRecord(XmlValueHandler):
    @classmethod
    def new(
        cls, type_id: str, values: dict[str, Any] = None, object_id: str = None
    ) -> "HkbRecord":
        elem = ET.Element("record")
        record = HkbRecord(elem, type_id, object_id)

        # Make sure the xml subtree contains all required fields
        def create_fields(parent_elem: ET.Element, record_type_id: str):
            for fname, ftype in type_registry.get_fields(record_type_id):
                field_elem = ET.SubElement(parent_elem, "field", name=fname)
                field_val = get_value_handler(ftype).new(ftype)

                if isinstance(field_val, HkbRecord):
                    create_fields(field_val.element, ftype)
                
                field_elem.append(field_val.element)

        create_fields(elem, type_id)

        if values:
            for key, val in values.items():
                # TODO implement setitem
                setattr(record, key, val)

        return record

    @classmethod
    def from_object(self, element: ET.Element) -> "HkbRecord":
        record = element.find("record")
        type_id = element.attrib["typeid"]
        object_id = element.attrib["id"]
        return HkbRecord(record, type_id, object_id)

    def __init__(self, element: ET.Element, type_id: str, object_id: str = None):
        assert element.tag == "record"
        assert type_id

        super().__init__(element, type_id)
        self.object_id = object_id

    def get_value(self) -> dict[str, XmlValueHandler]:
        ret = {}
        for fname, _ in self.fields():
            ret[fname] = getattr(self, fname)

        return ret

    def set_value(self, values: dict[str, XmlValueHandler]) -> None:
        for key, val in values.items():
            setattr(self, key, val)

    def fields(self) -> Generator[tuple[str, ET.Element], None, None]:
        for f in self.element.findall("field"):
            yield f.attrib["name"], f

    def get_field_element(self, name: str) -> ET.Element:
        return next((f for fname, f in self.fields() if fname == name), None)

    def get_field_type(self, name: str) -> str:
        for fname, ftype in type_registry.get_fields(self.type_id):
            if fname == name:
                return ftype

        return None

    def get(
        self, name: str, default: Any = None, resolve: bool = True
    ) -> XmlValueHandler:
        ret = getattr(self, name, default)
        if resolve and isinstance(ret, XmlValueHandler):
            return ret.get_value()
        return ret

    def __getattr__(self, name: str) -> XmlValueHandler:
        field_el = self.get_field_element(name)
        if field_el is None:
            raise AttributeError(f"No field '{name}'")

        type_id = self.get_field_type(name)
        return wrap_element(field_el, type_id)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"element", "type_id", "object_id"}:
            super().__setattr__(name, value)
            return

        field_el = self.get_field_element(name)
        if field_el is None:
            raise AttributeError(f"No field named '{name}'")

        ftype = self.get_field_type(name)
        if isinstance(value, XmlValueHandler):
            if value.type_id != ftype:
                raise ValueError(
                    f"Tried to assign value with non-matching type {value.type_id} to field {name} ({ftype})"
                )

            value = value.get_value()

        wrapped = wrap_element(field_el, ftype)
        wrapped.set_value(value)

    def as_object(self, id: str = None) -> ET.Element:
        if not id and not self.object_id:
            raise ValueError(f"Object does not have an ID and no ID was provided")

        if not id:
            id = self.object_id

        obj = ET.Element("object", type_id=self.type_id, id=id)
        obj.append(self.element)

        return obj


def get_value_handler(type_id: str) -> Type[XmlValueHandler]:
    format_map = {
        0: None,  # TODO void
        1: object,  # TODO opaque
        3: HkbString,
        131: HkbString,
        6: HkbPointer,
        7: HkbRecord,
        8: HkbArray,
        1064: HkbArray,
        4136: HkbArray,
        8232: HkbArray,
        8194: HkbBool,
        8196: HkbInteger,
        8708: HkbInteger,
        16900: HkbInteger,
        16388: HkbInteger,
        33284: HkbInteger,
        32772: HkbInteger,
        65540: HkbInteger,
        1525253: HkbFloat,
    }

    type_format = type_registry.get_format(type_id)
    return format_map[type_format]


def wrap_element(element: ET.Element, type_id: str = None) -> XmlValueHandler:
    if element.tag == "object":
        return HkbRecord.from_object(element)

    if element.tag == "field":
        element = next(iter(element))

    Handler = get_value_handler(type_id)
    return Handler(element, type_id)
