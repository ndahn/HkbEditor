from typing import Any, Type, Generator, Iterator
import struct
from lxml import etree as ET

from .tagfile import Tagfile
from .type_registry import TypeRegistry


_undefined = object()


class XmlValueHandler:
    @classmethod
    def new(
        cls, tagfile: Tagfile, type_id: str, value: Any = None
    ) -> "XmlValueHandler":
        raise NotImplementedError()

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        self.tagfile = tagfile
        self.element = element
        self.type_id = type_id

    @property
    def type_name(self) -> str:
        return self.tagfile.type_registry.get_name(self.type_id)

    def get_value(self) -> Any:
        raise NotImplementedError()

    def set_value(self, value: Any) -> None:
        raise NotImplementedError()

    def xml(self) -> str:
        ET.indent(self.element)
        return ET.tostring(self.element, pretty_print=True, encoding="unicode")

    def __str__(self) -> str:
        return str(self.get_value())


class HkbString(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: str = None) -> "HkbString":
        val = str(value) if value is not None else ""
        elem = ET.Element("string", value=val)
        return HkbString(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        if element.tag != "string":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> str:
        return self.element.attrib.get("value", "")

    def set_value(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValueError(f"Value {value} ({type(value)}) is not a string")
        self.element.attrib["value"] = str(value)


class HkbInteger(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: int = None) -> "HkbInteger":
        val = int(value) if value is not None else 0
        elem = ET.Element("integer", value=str(val))
        return HkbInteger(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        if element.tag != "integer":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> int:
        return int(self.element.attrib.get("value", 0))

    def set_value(self, value: int) -> None:
        self.element.attrib["value"] = str(int(value))


class HkbFloat(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: float = None) -> "HkbFloat":
        val = float(value) if value is not None else 0.0
        ieee = cls.float_to_ieee754(val)
        elem = ET.Element("real", dec=str(val), hex=ieee)
        return HkbFloat(tagfile, elem, type_id)

    @classmethod
    def float_to_ieee754(cls, value: float) -> str:
        # IEEE 754 representation for 64bit floats
        h = struct.unpack(">Q", struct.pack(">d", value))[0]
        return f"#{h:016x}"

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        if element.tag != "real":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> float:
        # Behaviors use commas as decimal separators
        return float(self.element.attrib.get("dec", "0").replace(",", "."))

    def set_value(self, value: float) -> None:
        # Behaviors use commas as decimal separators
        value = float(value)
        self.element.attrib["dec"] = str(value).replace(".", ",")
        self.element.attrib["hex"] = self.float_to_ieee754(value)


class HkbBool(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: bool = None) -> "HkbBool":
        bval = bool(value) if value is not None else False
        rep = "true" if bval else "false"
        elem = ET.Element("bool", value=rep)
        return HkbBool(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        if element.tag != "bool":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> bool:
        return self.element.attrib.get("value", "false").lower() == "true"

    def set_value(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError(f"Value {value} ({type(value)}) is not a bool")
        self.element.attrib["value"] = "true" if value else "false"


class HkbPointer(XmlValueHandler):
    @classmethod
    def new(
        cls, tagfile: Tagfile, type_id: str, value: str = None
    ) -> "HkbPointer":
        val = str(value) if value else "object0"
        elem = ET.Element("pointer", id=val)
        return HkbPointer(tagfile, elem, type_id)

    def __init__(
        self, tagfile: Tagfile, element: ET._Element, type_id: str
    ):
        if element.tag != "pointer":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)
        self.subtype = tagfile.type_registry.get_subtype(type_id)

    def get_value(self) -> str:
        val = self.element.attrib.get("id", None)
        if val in ("object0", None, ""):
            return ""

        return val

    def set_value(self, value: str) -> None:
        if isinstance(value, HkbRecord):
            value = value.object_id

        if value in ("", None):
            value = "object0"

        if not isinstance(value, str):
            raise ValueError(f"Value {value} ({type(value)}) is not a pointer")

        self.element.attrib["id"] = str(value)

    def get_target(self) -> "HkbRecord":
        oid = self.get_value()
        if not oid:
            return None

        return self.tagfile.objects[oid]


class HkbArray(XmlValueHandler):
    @classmethod
    def new(
        cls,
        tagfile: Tagfile,
        type_id: str,
        items: list[XmlValueHandler] = None,
    ) -> "HkbArray":
        if items is None:
            items = []

        elem_type_id = tagfile.type_registry.get_subtype(type_id)
        elem = ET.Element("array", count=str(len(items)), elementtypeid=elem_type_id)
        elem.extend(item.element for item in items)

        return HkbArray(tagfile, elem, type_id)

    def __init__(
        self,
        tagfile: Tagfile,
        element: ET._Element,
        type_id: str,
    ):
        if element.tag != "array":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)
        self.element_type_id = element.attrib["elementtypeid"]

    # NOTE not for public use, just use len(array)
    @property
    def _count(self) -> int:
        return int(self.element.attrib["count"])

    @_count.setter
    def _count(self, new_count: int) -> None:
        self.element.attrib["count"] = str(new_count)

    def clear(self) -> None:
        for child in self.element:
            self.element.remove(child)

    def get_value(self) -> list[XmlValueHandler]:
        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return [
            Handler(self.tagfile, elem, self.element_type_id)
            for elem in self.element
        ]

    def set_value(self, values: list[XmlValueHandler | Any], autowrap: bool = True) -> None:
        if autowrap:
            wrapped = []
            ElemHandler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
            for v in values:
                if not isinstance(v, XmlValueHandler):
                    # Could use self._wrap_value, but this way we safe some lookups
                    v = ElemHandler.new(self.tagfile, self.element_type_id, v)
                wrapped.append(v)

            values = wrapped

        for item in values:
            if isinstance(item, XmlValueHandler):
                self._verify_compatible(item)

        for child in list(self.element):
            self.element.remove(child)

        for v in values:
            self.element.append(v.element)
        self._count = len(values)

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Generator[XmlValueHandler, None, None]:
        for i in range(self._count):
            yield self[i]

    def __getitem__(self, index: int) -> XmlValueHandler:
        if index < 0:
            index = len(self) + index

        item = next(e for i, e in enumerate(self.element) if i == index)
        return wrap_element(self.tagfile, item, self.element_type_id)

    def __setitem__(self, index: int, value: XmlValueHandler | Any) -> None:
        if index < 0:
            index = len(self) + index
        
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)
            value = value.get_value()

        self[index].set_value(value)

    def __delitem__(self, index: int) -> None:
        if index < 0:
            index = len(self) + index
        
        self.element[:] = [
            elem
            for i, elem in enumerate(self.element)
            if i != index
        ]

        self._count -= 1

    def _wrap_value(self, value: Any) -> XmlValueHandler:
        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return Handler.new(self.tagfile, self.element_type_id, value)

    def _verify_compatible(self, value: XmlValueHandler) -> None:
        if value.type_id == self.element_type_id:
            return True
        
        # NOTE could check for compatible types, but I have yet to see that in use
        
        val_type = self.tagfile.type_registry.get_name(value.type_id)
        exp_type = self.tagfile.type_registry.get_name(self.element_type_id)
        
        # We might be an array of pointers, but even if the underlying type matches
        # we still only can accept its object_id, not the object itself
        # TODO check format once we have a complete format map
        #fmt = self.tagfile.type_registry.get_format(self.element_type_id)
        #if fmt == TypeFormats.POINTER
        
        raise ValueError(
            f"Non-matching value type {value.type_id} ({val_type}), expected {self.element_type_id} ({exp_type})"
        )

    def index(self, value: XmlValueHandler | Any) -> int:
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)
            value = value.get_value()

        for idx, item in enumerate(self):
            if item.get_value() == value:
                return idx

        raise IndexError("Item not found")

    def append(self, value: XmlValueHandler | Any) -> None:
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)
        else:
            value = self._wrap_value(value)

        self.element.append(value.element)
        self._count += 1

    def insert(self, index: int, value: XmlValueHandler | Any) -> None:
        if index < 0:
            index = len(self) + index
        
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)
        else:
            value = self._wrap_value(value)

        self.element.insert(index, value.element)
        self._count += 1

    def pop(self, index: int) -> XmlValueHandler:
        ret = self[index]
        del self[index]
        return ret


class HkbRecord(XmlValueHandler):
    @classmethod
    def new(
        cls,
        tagfile: Tagfile,
        type_id: str,
        path_values: dict[str, Any] = None,
        object_id: str = None,
    ) -> "HkbRecord":
        elem = ET.Element("record")
        record = HkbRecord(tagfile, elem, type_id, object_id)

        # Make sure the xml subtree contains all required fields
        for fname, ftype in tagfile.type_registry.get_field_types(type_id).items():
            field_elem = ET.SubElement(elem, "field", name=fname)

            # Handler.new will create all expected fields for the subelement
            Handler = get_value_handler(tagfile.type_registry, ftype)
            field_val = Handler.new(tagfile, ftype)

            if fname == "userData":
                # Needs to be unique?
                field_val.set_value(tagfile.new_userdata_value())
            
            field_elem.append(field_val.element)

        if path_values:
            for path, val in path_values.items():
                record.set_path_value(path, val)

        return record

    @classmethod
    def from_object(self, tagfile: Tagfile, element: ET._Element) -> "HkbRecord":
        record = element.find("record")
        type_id = element.attrib["typeid"]
        object_id = element.attrib["id"]
        return HkbRecord(tagfile, record, type_id, object_id)

    def __init__(
        self,
        tagfile: Tagfile,
        element: ET._Element,
        type_id: str,
        object_id: str = None,
    ):
        assert element.tag == "record"
        assert type_id

        super().__init__(tagfile, element, type_id)
        self.object_id = object_id
        self._fields = tagfile.type_registry.get_field_types(type_id)

    def get_value(self) -> dict[str, XmlValueHandler]:
        return {f: self[f] for f in self._fields.keys()}

    def set_value(self, values: dict[str, XmlValueHandler]) -> None:
        for key, val in values.items():
            self[key] = val

    @property
    def fields(self) -> Iterator[str]:
        yield from self._fields.keys()

    def _get_field_element(self, name: str) -> ET._Element:
        # Avoid infinite recursions from __getattr__
        for elem in self.element.findall("field"):
            if elem.attrib["name"] == name:
                return elem

        return None

    def get_field_type(self, name: str) -> str:
        for fname, ftype in self._fields.items():
            if fname == name:
                return ftype

        return None

    def get_path_value(
        self, path: str, default: Any = _undefined, *, resolve: bool = False
    ) -> XmlValueHandler:
        keys = path.split("/")
        obj = self

        try:
            for k in keys:
                if ":" in k:
                    k, idx = k.split(":")
                    obj = obj[k][int(idx)]
                else:
                    obj = obj[k]
        except (AttributeError, KeyError) as e:
            if default != _undefined:
                return default
            raise KeyError(f"No field with path '{path}'") from e

        if resolve:
            return obj.get_value()

        return obj

    def set_path_value(self, path: str, value: Any) -> None:
        handler = self.get_path_value(path, resolve=False)
        handler.set_value(value)

    def get_field(
        self, name: str, default: Any = _undefined, resolve: bool = False
    ) -> XmlValueHandler | Any:
        ftype = self.get_field_type(name)
        if ftype is None:
            if default is not _undefined:
                return default
            raise AttributeError(f"No field '{name}'")

        field_el = self._get_field_element(name)
        wrap = wrap_element(self.tagfile, field_el, ftype)

        if resolve:
            return wrap.get_value()

        return wrap

    def set_field(self, name: str, value: XmlValueHandler | Any) -> None:
        ftype = self.get_field_type(name)
        if ftype is None:
            raise AttributeError(f"No field named '{name}'")

        field_el = self._get_field_element(name)
        if isinstance(value, XmlValueHandler):
            if value.type_id != ftype:
                raise ValueError(
                    f"Tried to assign value with non-matching type {value.type_id} to field {name} ({ftype})"
                )

            # We fully replace the inner field element. This will invalidate any previous 
            # references to values of this field, but I suspect that will be less surprising
            # than modifying a previously applied value and seeing no effect.
            # TODO by doing this we might remove the value XML from another record
            field_el.remove(next(field_el))
            field_el.append(value.element)
            #value = value.get_value()
        else:
            wrapped = wrap_element(self.tagfile, field_el, ftype)
            wrapped.set_value(value)

    def __getitem__(self, key: str) -> XmlValueHandler:
        return self.get_field(key)

    def __setitem__(self, key: str, value: XmlValueHandler | Any) -> None:
        self.set_field(key, value)

    def as_object(self, id: str = None) -> ET._Element:
        if not id and not self.object_id:
            raise ValueError(f"Object does not have an ID and no ID was provided")

        if not id:
            id = self.object_id

        elem = ET.Element("object", typeid=self.type_id, id=id)
        elem.append(self.element)

        return elem


def get_value_handler(type_registry: TypeRegistry, type_id: str) -> Type[XmlValueHandler]:
    # TODO don't hardcode these, should be derived from the behavior somehow
    # From a different file:
    # 0          void
    # 1          incomplete
    # 3          string (ptr)
    # 6          pointer
    # 7          record
    # 8          array
    # 552        array(2)
    # 1064       array(4)
    # 3112       array(12)
    # 4136       array(16)
    # 8194       bool8 (unsigned, LE)
    # 8196       uint8 (LE)
    # 8708       int8 (LE)
    # 16388      uint16 (LE)
    # 16900      int16 (LE)
    # 32772      uint32 (LE)
    # 33284      int32 (LE)
    # 65540      uint64 (LE)
    # 1525253    float
    format_map = {
        0: None,  # TODO void
        1: object,  # TODO opaque
        3: HkbString,
        6: HkbPointer,
        7: HkbRecord,
        8: HkbArray,
        131: HkbString,
        1064: HkbArray,
        4136: HkbArray,
        8194: HkbBool,
        8196: HkbInteger,
        8232: HkbArray,
        8708: HkbInteger,
        16388: HkbInteger,
        16900: HkbInteger,
        32772: HkbInteger,
        33284: HkbInteger,
        65540: HkbInteger,
        1525253: HkbFloat,
    }

    type_format = type_registry.get_format(type_id)
    return format_map[type_format]


def wrap_element(
    tagfile: Tagfile, element: ET._Element, type_id: str = None
) -> XmlValueHandler:
    if element.tag == "object":
        return HkbRecord.from_object(tagfile, element)

    if element.tag == "field":
        element = next(iter(element))

    Handler = get_value_handler(tagfile.type_registry, type_id)
    return Handler(tagfile, element, type_id)
