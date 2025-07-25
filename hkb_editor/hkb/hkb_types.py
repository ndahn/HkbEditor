from typing import Any, Type, Generator, Iterator, Mapping
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

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, type(self)):
            return False

        return self.get_value() == other.get_value()

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

    def set_value(self, value: "HkbString | str") -> None:
        if not isinstance(value, (HkbString, str)):
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

    def set_value(self, value: "HkbInteger | int") -> None:
        self.element.attrib["value"] = str(int(value))

    def __int__(self) -> int:
        return self.get_value()


class HkbFloat(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: float = None) -> "HkbFloat":
        elem = ET.Element("real", dec="", hex="")
        ret = HkbFloat(tagfile, elem, type_id)

        # Slightly roundabout, but this way we get proper comma handling etc.
        val = float(value) if value is not None else 0.0
        ret.set_value(val)
        return ret

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

    def set_value(self, value: "HkbFloat | float") -> None:
        value = float(value)

        # Some older versions of HKLib seem to have decompiled floats with commas
        str_value = str(value)
        if self.tagfile.floats_use_commas:
            str_value = str_value.replace(".", ",")

        self.element.attrib["dec"] = str_value
        self.element.attrib["hex"] = self.float_to_ieee754(value)

    def __float__(self) -> float:
        return self.get_value()


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

    def set_value(self, value: "HkbBool | bool") -> None:
        if not isinstance(value, (HkbBool, bool)):
            raise ValueError(f"Value {value} ({type(value)}) is not a bool")

        self.element.attrib["value"] = "true" if value else "false"

    def __bool__(self) -> bool:
        return self.get_value()


class HkbPointer(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: str = None) -> "HkbPointer":
        val = str(value) if value else "object0"
        elem = ET.Element("pointer", id=val)
        return HkbPointer(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        if element.tag != "pointer":
            raise ValueError(f"Invalid element {element}")

        super().__init__(tagfile, element, type_id)
        self.subtype = tagfile.type_registry.get_subtype(type_id)

    @property
    def subtype_name(self) -> str:
        return self.tagfile.type_registry.get_name(self.subtype)

    def will_accept(self, record: "HkbRecord", check_subtypes: bool = True) -> bool:
        if self.subtype == record.type_id:
            return True

        if (
            check_subtypes
            and record.type_id
            in self.tagfile.type_registry.get_compatible_types(self.subtype)
        ):
            return True

        return False

    def get_value(self) -> str:
        val = self.element.attrib.get("id", None)
        if val in ("object0", None, ""):
            return ""

        return val

    def set_value(self, value: "HkbPointer | HkbRecord | str") -> None:
        if isinstance(value, HkbRecord) and value.object_id:
            # verify the record is compatible
            if not self.will_accept(value):
                raise ValueError(f"Incompatible record type {value.type_name}, expected {self.subtype_name}")
            value = value.object_id
        elif isinstance(value, HkbPointer):
            value = value.get_value()

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

    def __str__(self) -> str:
        return f"Pointer -> {self.get_value()} ({self.subtype_name})"


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
        # TODO format of element_type_id will be easier to check
        self.is_pointer_array = (
            get_value_handler(tagfile.type_registry, self.element_type_id) == HkbPointer
        )

    @property
    def element_type_name(self) -> str:
        return self.tagfile.type_registry.get_name(self.element_type_id)

    # NOTE not for public use, just use len(array)
    @property
    def _count(self) -> int:
        return int(self.element.attrib["count"])

    @_count.setter
    def _count(self, new_count: int) -> None:
        self.element.attrib["count"] = str(new_count)

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Generator[XmlValueHandler, None, None]:
        for i in range(self._count):
            yield self[i]

    def __getitem__(self, index: int) -> XmlValueHandler:
        if index < 0:
            index = len(self) + index

        try:
            item = next(e for i, e in enumerate(self.element) if i == index)
        except StopIteration:
            raise IndexError(f"Invalid index {index}")

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

        self.element[:] = [elem for i, elem in enumerate(self.element) if i != index]

        self._count -= 1

    def _verify_compatible(self, value: XmlValueHandler) -> None:
        if value.type_id == self.element_type_id:
            return True

        # Pointers allow being set from objects, so we should't be in the way
        if self.is_pointer_array and isinstance(value, HkbRecord):
            return True

        # NOTE could check for compatible types, but I have yet to see that in use

        val_type = self.tagfile.type_registry.get_name(value.type_id)
        exp_type = self.tagfile.type_registry.get_name(self.element_type_id)

        raise ValueError(
            f"Non-matching value type {value.type_id} ({val_type}), expected {self.element_type_id} ({exp_type})"
        )

    def _wrap_value(self, value: Any) -> XmlValueHandler:
        if self.is_pointer_array and isinstance(value, HkbRecord):
            return HkbPointer.new(self.tagfile, self.element_type_id, value.object_id)

        if isinstance(value, XmlValueHandler):
            # Always make a copy to avoid moving the xml element away from its 
            # original parent
            return value.new(self.tagfile, value.type_id, value.get_value())

        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return Handler.new(self.tagfile, self.element_type_id, value)

    def get_value(self) -> list[XmlValueHandler]:
        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return [
            Handler(self.tagfile, elem, self.element_type_id) for elem in self.element
        ]

    def set_value(self, values: "HkbArray | list[XmlValueHandler | Any]") -> None:
        values = [self._wrap_value(v) for v in values]

        for v in values:
            self._verify_compatible(v)

        # Can't use clear as it would remove the attributes as well
        for child in list(self.element):
            self.element.remove(child)

        for v in values:
            self.element.append(v.element)

        self._count = len(values)

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

        value = self._wrap_value(value)
        self.element.append(value.element)
        self._count += 1

    def insert(self, index: int, value: XmlValueHandler | Any) -> None:
        if index < 0:
            index = len(self) + index

        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)

        value = self._wrap_value(value)
        self.element.insert(index, value.element)
        self._count += 1

    def pop(self, index: int) -> XmlValueHandler:
        ret = self[index]
        del self[index]
        return ret

    def clear(self) -> None:
        for child in self.element:
            self.element.remove(child)

    def __str__(self):
        return f"HkbArray[{self.element_type_name}] (len={self._count})"


class HkbRecord(XmlValueHandler):
    @classmethod
    def new(
        cls,
        tagfile: Tagfile,
        type_id: str,
        path_values: dict[str, Any] = None,
        object_id: str = None,
    ) -> "HkbRecord":
        if path_values and not isinstance(path_values, Mapping):
            raise ValueError(
                f"path_values must be a dict-like object, but got {path_values} ({type(path_values).__name__}) instead"
            )

        elem = ET.Element("record")
        record = HkbRecord(tagfile, elem, type_id, object_id)

        # Make sure the xml subtree contains all required fields
        for fname, ftype in tagfile.type_registry.get_field_types(type_id).items():
            field_elem = ET.SubElement(elem, "field", name=fname)

            # Handler.new will create all expected fields for the subelement
            Handler = get_value_handler(tagfile.type_registry, ftype)
            field_val = Handler.new(tagfile, ftype)
            field_elem.append(field_val.element)

            # Note: userData is probably a void pointer and not useful to set
            # unless you are making a copy of another record

        if path_values:
            for path, val in path_values.items():
                record.set_field(path, val)

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

    def set_value(self, values: "HkbRecord | dict[str, XmlValueHandler]") -> None:
        if isinstance(values, HkbRecord):
            values = values.get_value()
        
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

    def get_field(
        self,
        path: str,
        default: Any = _undefined,
        *,
        resolve: bool = False,
        follow_pointers: bool = True,
    ) -> XmlValueHandler | Any:
        keys = path.split("/")
        obj = self

        try:
            for k in keys:
                if follow_pointers and isinstance(obj, HkbPointer):
                    obj = obj.get_target()

                if ":" in k:
                    k, idx = k.split(":")
                    obj = obj[k][int(idx)]
                else:
                    obj = obj[k]
        except (AttributeError, KeyError, IndexError) as e:
            if default != _undefined:
                return default
            raise KeyError(f"No field with path '{path}'") from e

        if resolve:
            return obj.get_value()

        return obj

    def set_field(self, path: str, value: XmlValueHandler | Any) -> None:
        # Just delegate to the value handler
        handler = self.get_field(path, resolve=False)
        handler.set_value(value)

    def __getitem__(self, name: str) -> XmlValueHandler:
        ftype = self.get_field_type(name)
        if ftype is None:
            raise AttributeError(f"No field '{name}'")

        field_el = self._get_field_element(name)
        return wrap_element(self.tagfile, field_el, ftype)

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

    def __str__(self) -> str:
        name = self.get_field("name", None)
        name = f" '{name}'" if name else ""
        return f"{self.type_name}{name} (id={self.object_id})"


def get_value_handler(
    type_registry: TypeRegistry, type_id: str
) -> Type[XmlValueHandler]:
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
