from typing import Any, Type, Generator, Iterator, Mapping, Generic, TypeVar
import struct
from lxml import etree as ET

from .tagfile import Tagfile
from .type_registry import TypeRegistry
from .xml import HkbXmlElement
from .game_specific import separate_game_specific_attributes


_undefined = object()


class XmlValueHandler:
    @classmethod
    def new(
        cls, tagfile: Tagfile, type_id: str, value: Any = None
    ) -> "XmlValueHandler":
        raise NotImplementedError()

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
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

    def __repr__(self):
        return self.__str__()


T = TypeVar("T", bound=XmlValueHandler)


class HkbString(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: str = None) -> "HkbString":
        val = str(value) if value is not None else ""
        elem = HkbXmlElement.new("string", value=val)
        return HkbString(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
        if element.tag != "string":
            raise ValueError(f"Invalid element <{element.tag}>")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> str:
        return self.element.attrib.get("value", "")

    def set_value(self, value: "HkbString | str") -> None:
        if not isinstance(value, (HkbString, str)):
            raise ValueError(f"Value {value} ({type(value)}) is not a string")

        self.element.set("value", str(value))


class HkbInteger(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: int = None) -> "HkbInteger":
        val = int(value) if value is not None else 0
        elem = HkbXmlElement.new("integer", value=str(val))
        return HkbInteger(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
        if element.tag != "integer":
            raise ValueError(f"Invalid element <{element.tag}>")

        # No endianness since the int is stored as a string
        format = tagfile.type_registry.get_format(type_id)
        self.signed = format & 0x200 != 0
        self.byte_size = format >> 10

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> int:
        val = int(self.element.attrib.get("value", 0))
        if not self.signed:
            return abs(val)
        return val

    def set_value(self, value: "HkbInteger | int") -> None:
        val = int(value)
        if not self.signed:
            val = abs(val)
        self.element.set("value", str(val))

    def __int__(self) -> int:
        return self.get_value()


class HkbFloat(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: float = None) -> "HkbFloat":
        elem = HkbXmlElement.new("real", dec="", hex="")
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

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
        if element.tag != "real":
            raise ValueError(f"Invalid element <{element.tag}>")

        # Not needed/relevant for now
        # format = tagfile.type_registry.get_format(type_id)
        # Only matters when reading from the hex representation
        # self.bigendian = (format & 0x100 != 0)
        # Guessed, only have 1525253 to go off right now
        # See https://github.com/The12thAvenger/HKLib/blob/main/HKLib.Serialization/hk2018/Xml/FormatHandlers/FloatFormatHandler.cs#L39
        # self.size = (format >> 12) & 0xf
        # 23: float, 52: double
        # self.mantissa_bits = format >> 16

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> float:
        # TODO would be (slightly) better to use the hex representation
        # Behaviors use commas as decimal separators
        return float(self.element.attrib.get("dec", "0").replace(",", "."))

    def set_value(self, value: "HkbFloat | float") -> None:
        value = float(value)

        # Some older versions of HKLib seem to have decompiled floats with commas
        str_value = str(value)
        if self.tagfile.floats_use_commas:
            str_value = str_value.replace(".", ",")

        with self.element.try_transaction():
            self.element.set("dec", str_value)
            self.element.set("hex", self.float_to_ieee754(value))

    def __float__(self) -> float:
        return self.get_value()


class HkbBool(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: bool = None) -> "HkbBool":
        bval = bool(value) if value is not None else False
        rep = "true" if bval else "false"
        elem = HkbXmlElement.new("bool", value=rep)
        return HkbBool(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
        if element.tag != "bool":
            raise ValueError(f"Invalid element <{element.tag}>")

        super().__init__(tagfile, element, type_id)

    def get_value(self) -> bool:
        return self.element.attrib.get("value", "false").lower() == "true"

    def set_value(self, value: "HkbBool | bool") -> None:
        if not isinstance(value, (HkbBool, bool)):
            raise ValueError(f"Value {value} ({type(value)}) is not a bool")

        self.element.set("value", "true" if value else "false")

    def __bool__(self) -> bool:
        return self.get_value()


class HkbPointer(XmlValueHandler):
    @classmethod
    def new(cls, tagfile: Tagfile, type_id: str, value: str = None) -> "HkbPointer":
        val = str(value) if value else "object0"
        elem = HkbXmlElement.new("pointer", id=val)
        return HkbPointer(tagfile, elem, type_id)

    def __init__(self, tagfile: Tagfile, element: HkbXmlElement, type_id: str):
        if element.tag != "pointer":
            raise ValueError(f"Invalid element <{element.tag}>")

        super().__init__(tagfile, element, type_id)

        # This property is not saved on the pointer, so we don't need to guard it
        self.subtype_id = tagfile.type_registry.get_subtype(type_id)

    @property
    def subtype_name(self) -> str:
        return self.tagfile.type_registry.get_name(self.subtype_id)

    def get_compatible_types(self) -> list[str]:
        return self.tagfile.type_registry.get_compatible_types(self.subtype_id)

    def will_accept(
        self, type_id: "HkbRecord | HkbPointer | str", check_subtypes: bool = True
    ) -> bool:
        if isinstance(type_id, HkbRecord):
            type_id = type_id.type_id
        elif isinstance(type_id, HkbPointer):
            type_id = type_id.subtype_id

        if self.subtype_id == type_id:
            return True

        if (
            check_subtypes
            and type_id
            in self.tagfile.type_registry.get_compatible_types(self.subtype_id)
        ):
            return True

        return False

    def get_value(self) -> str:
        val = self.element.attrib.get("id", None)
        if val in ("object0", None, ""):
            return ""

        return val

    def set_value(
        self,
        value: "HkbPointer | HkbRecord | str",
        *,
        must_exist: bool = True,
        verify: bool = True,
    ) -> None:
        oid = None

        if isinstance(value, (HkbRecord, HkbPointer)) and not self.will_accept(value):
            raise ValueError(
                f"{self.type_name} does not accept value of type {value.type_name}"
            )

        if value is None:
            oid = None
        elif isinstance(value, HkbRecord):
            if not value.object_id:
                raise ValueError(f"Passed record {value} does not have an object ID")
            oid = value.object_id
        elif isinstance(value, HkbPointer):
            oid = value.get_value()
        elif isinstance(value, str):
            oid = value
        else:
            raise ValueError(f"Cannot apply '{value}' to a pointer")

        if not oid:
            oid = "object0"
        elif must_exist and oid not in self.tagfile.objects:
            raise ValueError("Target reference does not exist")

        self.element.set("id", str(oid))

    def get_target(self) -> "HkbRecord":
        oid = self.get_value()
        if oid:
            return self.tagfile.objects[oid]

        return None

    def is_set(self) -> bool:
        return bool(self.get_value())

    def __str__(self) -> str:
        return f"Pointer(id={self.get_value()}, subtype={self.subtype_name})"


class HkbArray(XmlValueHandler, Generic[T]):
    @classmethod
    def new(
        cls,
        tagfile: Tagfile,
        type_id: str,
        items: list[T] = None,
    ) -> "HkbArray":
        if items is None:
            items = []

        elem_type_id = None
        temp_type = type_id

        while elem_type_id is None:
            # Sometimes the subtype is inherited (e.g. type85/hkVector4 in Sekiro)
            elem_type_id = tagfile.type_registry.get_subtype(temp_type)
            temp_type = tagfile.type_registry.get_parent(temp_type)

        elem = HkbXmlElement.new(
            "array", count=str(len(items)), elementtypeid=elem_type_id
        )
        elem.extend(item.element for item in items)

        return HkbArray(tagfile, elem, type_id)

    def __init__(
        self,
        tagfile: Tagfile,
        element: HkbXmlElement,
        type_id: str,
    ):
        if element.tag != "array":
            raise ValueError(f"Invalid element {element}")

        # TODO make use of this!
        format = tagfile.type_registry.get_format(type_id)
        self.max_size = format >> 8

        super().__init__(tagfile, element, type_id)
        self.is_pointer_array = self.get_item_wrapper() == HkbPointer

    @property
    def element_type_id(self) -> str:
        return self.element.get("elementtypeid")

    @element_type_id.setter
    def element_type_id(self, new_element_typeid: str) -> None:
        self.element.set("elementtypeid", new_element_typeid)

    @property
    def element_type_name(self) -> str:
        return self.tagfile.type_registry.get_name(self.element_type_id)

    # NOTE not for public use, just use len(array)
    @property
    def _count(self) -> int:
        return int(self.element.get("count"))

    @_count.setter
    def _count(self, new_count: int) -> None:
        self.element.set("count", str(new_count))

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Generator[T, None, None]:
        for i in range(self._count):
            yield self[i]

    def __getitem__(self, key: int | slice) -> T | list[T]:
        if isinstance(key, int):
            if key < 0:
                key = len(self) + key

            try:
                item = next(e for i, e in enumerate(self.element) if i == key)
            except StopIteration:
                raise IndexError(f"Invalid index {key}")

            return wrap_element(self.tagfile, item, self.element_type_id)

        elif isinstance(key, slice):
            return [self[i] for i in range(*key.indices(len(self)))]

        else:
            raise KeyError(f"Invalid key {key}")

    def __setitem__(self, index: int, value: T | Any) -> None:
        if index < 0:
            index = len(self) + index

        if isinstance(value, T):
            self._verify_compatible(value)
            value = value.get_value()

        self[index].set_value(value)

    def __delitem__(self, index: int) -> None:
        if index < 0:
            index = len(self) + index

        child = self.element[index]

        with self.element.try_transaction():
            self.element.remove(child)
            self._count -= 1

    def _verify_compatible(self, value: T) -> None:
        if value.type_id == self.element_type_id:
            return True

        # Pointers allow being set from objects, so we should't be in the way
        if self.is_pointer_array and isinstance(value, HkbRecord):
            return True

        # Is this too soft?
        if isinstance(value, self.get_item_wrapper()):
            return True

        # NOTE could check for compatible types, but I have yet to see that in use

        val_type = self.tagfile.type_registry.get_name(value.type_id)
        exp_type = self.tagfile.type_registry.get_name(self.element_type_id)

        raise ValueError(
            f"Non-matching value type {value.type_id} ({val_type}), expected {self.element_type_id} ({exp_type})"
        )

    def _wrap_value(self, value: Any) -> T:
        if self.is_pointer_array and isinstance(value, HkbRecord):
            return HkbPointer.new(self.tagfile, self.element_type_id, value.object_id)

        if isinstance(value, XmlValueHandler):
            # Always make a copy to avoid moving the xml element away from its
            # original parent
            return value.new(self.tagfile, value.type_id, value.get_value())

        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return Handler.new(self.tagfile, self.element_type_id, value)

    def get_item_wrapper(self) -> Type[T]:
        return get_value_handler(self.tagfile.type_registry, self.element_type_id)

    def get_value(self) -> list[T]:
        Handler = get_value_handler(self.tagfile.type_registry, self.element_type_id)
        return [
            Handler(self.tagfile, elem, self.element_type_id) for elem in self.element
        ]

    def set_value(self, values: "HkbArray | list[T | Any]") -> None:
        values = [self._wrap_value(v) for v in values]

        for v in values:
            self._verify_compatible(v)

        with self.element.try_transaction():
            # Can't use clear as it would remove the attributes as well
            for child in list(self.element):
                self.element.remove(child)

            for v in values:
                self.element.append(v.element)

            self._count = len(values)

    def index(self, value: T | Any) -> int:
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)
            value = value.get_value()

        for idx, item in enumerate(self):
            if item.get_value() == value:
                return idx

        raise IndexError("Item not found")

    def append(self, value: T | Any) -> T:
        """Add a new item to this array.

        NOTE: this will ALWAYS create a new object inside the array, even if the passed
        value could be used as it is. This is to avoid unintentionally moving parts of the
        xml structure around.

        Parameters
        ----------
        value : T | Any
            The item to add.

        Returns
        -------
        T
            The new item that has been added to the array.
        """
        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)

        value = self._wrap_value(value)

        with self.element.try_transaction():
            self.element.append(value.element)
            self._count += 1

        return value

    def insert(self, index: int, value: T | Any) -> None:
        if index < 0:
            index = len(self) + index

        if isinstance(value, XmlValueHandler):
            self._verify_compatible(value)

        value = self._wrap_value(value)

        with self.element.try_transaction():
            self.element.insert(index, value.element)
            self._count += 1

    def pop(self, index: int) -> T:
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
        attributes: dict[str, Any] = None,
        *,
        object_id: str = None,
    ) -> "HkbRecord":
        record_elem = HkbXmlElement.new("record")
        record = HkbRecord(tagfile, record_elem, type_id, object_id)

        # Make sure the xml subtree contains all required fields
        for fname, ftype in tagfile.type_registry.get_field_types(type_id).items():
            field_elem = HkbXmlElement.new("field", name=fname)
            record_elem.append(field_elem)

            # Handler.new will create all expected fields for the subelement
            Handler = get_value_handler(tagfile.type_registry, ftype)
            field_val = Handler.new(tagfile, ftype)
            field_elem.append(field_val.element)

            # NOTE: userData is probably a void pointer and not useful to set
            # unless you are making a copy of another record

        if attributes:
            optional = separate_game_specific_attributes(record.type_name, attributes)

            for path, val in attributes.items():
                record.set_field(path, val)

            for path, val in optional.items():
                try:
                    record.set_field(path, val)
                except KeyError:
                    pass

        return record

    @classmethod
    def init_from_xml(
        self, tagfile: Tagfile, type_id: str, xml: HkbXmlElement, object_id: str = None
    ) -> "HkbRecord":
        obj = HkbRecord.new(tagfile, type_id, object_id=object_id)

        if xml.tag != "record":
            xml = xml.find("record")

        tmp = HkbRecord(tagfile, xml, type_id)
        obj.set_value(tmp)
        return obj

    @classmethod
    def from_object(self, tagfile: Tagfile, element: HkbXmlElement) -> "HkbRecord":
        record = element.find("record")
        type_id = element.get("typeid")
        object_id = element.get("id")
        return HkbRecord(tagfile, record, type_id, object_id)

    def __init__(
        self,
        tagfile: Tagfile,
        element: HkbXmlElement,
        type_id: str,
        object_id: str = None,
    ):
        assert element.tag == "record"
        assert type_id

        super().__init__(tagfile, element, type_id)
        self.object_id = object_id
        self._fields = tagfile.type_registry.get_field_types(type_id)

    def get_value(self) -> dict[str, XmlValueHandler]:
        return {
            f: self[f]
            for f in self._fields.keys()
            # Only return values that are actually in the underlying xml
            if self.element.xpath(f".//field[@name='{f}']")
        }

    def set_value(self, values: "HkbRecord | dict[str, XmlValueHandler]") -> None:
        if isinstance(values, HkbRecord):
            values = values.get_value()

        if not isinstance(values, Mapping):
            raise ValueError(f"Expected HkbRecord or Mapping, but got {values}")

        # values may have extra or missing values, so we go from our known fields
        with self.element.try_transaction():
            for field in self._fields.keys():
                if field in values:
                    self[field] = values[field]

    @property
    def fields(self) -> Iterator[str]:
        yield from self._fields.keys()

    def _get_field_element(self, name: str) -> HkbXmlElement:
        # Avoid infinite recursions from __getattr__
        for elem in self.element.findall("field"):
            if elem.get("name") == name:
                return elem

        return None

    def get_field_type(self, name: str) -> str:
        for fname, ftype in self._fields.items():
            if fname == name:
                return ftype

        return None

    def set_field(self, path: str, value: XmlValueHandler | Any) -> None:
        # Just delegate to the value handler
        handler = self.get_field(path, resolve=False)
        handler.set_value(value)

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
        except Exception as e:
            if default != _undefined:
                return default
            raise KeyError(f"No field with path '{path}'") from e

        if resolve:
            return obj.get_value()

        return obj

    def get_fields(
        self,
        paths: list[str] | str,
        *,
        resolve: bool = False,
        follow_pointers: bool = True,
    ) -> dict[str, list[XmlValueHandler | Any]]:
        """Special version of get_fields that can handle multiple paths and also handles * asterisk wildcards.

        Parameters
        ----------
        paths : list[str] | str
            Paths to resolve.
        resolve : bool, optional
            Whether to resolve XmlValueHelper values or return them as objects.
        follow_pointers : bool, optional
            Whether to follow pointers during recursion.

        Returns
        -------
        dict[str, list[XmlValueHandler | Any]]
            A mapping from paths to results.

        Raises
        ------
        KeyError
            If one of the paths could not be resolved.
        """

        def _get_fields_recursive(
            obj: HkbRecord, keys: list[str], key_index: int, current_path: str
        ):
            if key_index >= len(keys):
                value = obj.get_value() if resolve else obj
                return {current_path: value}

            results = {}
            k = keys[key_index]

            if follow_pointers and isinstance(obj, HkbPointer):
                obj = obj.get_target()

            if ":" in k:
                field, idx = k.split(":")
                array = obj[field]

                if idx == "*":
                    # Wildcard: recurse for all indices
                    for i in range(len(array)):
                        key = f"{field}:{i}"
                        path = f"{current_path}/{key}" if current_path else key
                        results.update(
                            _get_fields_recursive(array[i], keys, key_index + 1, path)
                        )
                else:
                    # Specific index
                    key = f"{field}:{idx}"
                    path = f"{current_path}/{key}" if current_path else key
                    results.update(
                        _get_fields_recursive(
                            array[int(idx)], keys, key_index + 1, path
                        )
                    )
            else:
                # Regular field access
                path = f"{current_path}/{k}" if current_path else k
                results.update(_get_fields_recursive(obj[k], keys, key_index + 1, path))

            return results

        if isinstance(paths, str):
            paths = [paths]

        ret = {}

        for path in paths:
            keys = path.split("/")
            try:
                ret.update(_get_fields_recursive(self, keys, 0, ""))
            except (AttributeError, KeyError, IndexError):
                raise KeyError(f"Failed to resolve path '{path}'")

        return ret

    def find_fields_by_class(
        self, field_class: T, *, recurse: bool = True
    ) -> Generator[tuple[str, T], None, None]:

        def delve_record(
            rec: HkbRecord, current_path: str
        ) -> Generator[tuple[str, T], None, None]:
            if not rec:
                # Arrays might contain null-pointers
                return

            for field_name in rec.fields:
                field = rec[field_name]
                field_path = (
                    f"{current_path}/{field_name}" if current_path else field_name
                )

                # Check the field itself first
                if isinstance(field, field_class):
                    yield (field_path, field)

                # Check children
                if isinstance(field, HkbRecord):
                    yield from delve_record(field, field_path)
                elif recurse and isinstance(field, HkbArray):
                    yield from delve_array(field, field_path)

        def delve_array(
            array: HkbArray, array_path: str
        ) -> Generator[tuple[str, T], None, None]:
            for i, item in enumerate(array):
                item_path = f"{array_path}:{i}"

                # Yield matching items
                if isinstance(item, field_class):
                    yield (item_path, item)

                # Recurse into records
                if isinstance(item, HkbRecord):
                    yield from delve_record(item, item_path)

                # Recurse into nested arrays
                elif isinstance(item, HkbArray):
                    yield from delve_array(item, item_path)

        yield from delve_record(self, "")

    def __getitem__(self, name: str) -> XmlValueHandler:
        ftype = self.get_field_type(name)
        if ftype is None:
            raise AttributeError(f"No field '{name}'")

        field_el = self._get_field_element(name)
        return wrap_element(self.tagfile, field_el, ftype)

    def __setitem__(self, key: str, value: XmlValueHandler | Any) -> None:
        self.set_field(key, value)

    def as_object(self, id: str = None) -> HkbXmlElement:
        if not id and not self.object_id:
            raise ValueError("Object does not have an ID and no ID was provided")

        parent = self.element.getparent()
        if parent is not None and parent.tag == "object":
            return parent

        if not id:
            id = self.object_id

        elem = HkbXmlElement.new("object", typeid=self.type_id, id=id)
        elem.append(self.element)

        return elem

    def __str__(self) -> str:
        name = self.get_field("name", None)
        name = f" '{name}'" if name else ""
        return f"{self.type_name}{name} (id={self.object_id})"

    def __repr__(self):
        return f"HkbRecord<{self.type_name}>({self.object_id})"


def get_value_handler(
    type_registry: TypeRegistry, type_id: str
) -> Type[XmlValueHandler]:
    format_map = {
        0: None,  # Void
        1: None,  # Opaque
        2: HkbBool,
        3: HkbString,
        4: HkbInteger,
        5: HkbFloat,
        6: HkbPointer,
        7: HkbRecord,
        8: HkbArray,
    }

    format = type_registry.get_format(type_id)
    tp = format_map[format & 0xF]

    if tp is None:
        raise TypeError(f"Don't know how to handle type_id {type_id} (format={format})")

    return tp


def wrap_element(
    tagfile: Tagfile, element: HkbXmlElement, type_id: str = None
) -> XmlValueHandler:
    if element.tag == "object":
        return HkbRecord.from_object(tagfile, element)

    if element.tag == "field":
        element = next(iter(element))

    Handler = get_value_handler(tagfile.type_registry, type_id)
    return Handler(tagfile, element, type_id)
