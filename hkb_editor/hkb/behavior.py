from typing import Any, Iterable
from dataclasses import dataclass
import re
import logging
import struct
import ctypes
import networkx as nx

from .tagfile import Tagfile
from .hkb_types import HkbRecord, HkbArray, HkbPointer, HkbFloat
from .hkb_enums import hkbVariableInfo_VariableType as VariableType
from .cached_array import CachedArray


_undefined = object()


@dataclass
class HkbVariable:
    name: str
    vtype: VariableType
    vmin: int
    vmax: int
    default: Any = 0  # Can be int, float, str, pointer, tuple, ...

    def astuple(self) -> tuple[str, int, int, int, Any]:
        return (self.name, self.vtype, self.vmin, self.vmax, self.default)


class HavokBehavior(Tagfile):
    def __init__(self, xml_file: str):
        super().__init__(xml_file)

        # Locate the root statemachine
        self.root_sm = None
        for node, _ in nx.bfs_successors(self.root_graph(), self.behavior_root.object_id):
            obj = self.objects[node]
            if obj.type_name == "hkbStateMachine":
                self.root_sm = obj
                break
        else:
            logging.getLogger().warning("Could not locate root statemachine")

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
        self._variable_defaults: HkbRecord = self.find_first_by_type_name(
            "hkbVariableValueSet"
        )

    def get_character_id(self) -> str:
        """Returns the character ID of this behavior, e.g. c0000."""
        # 1st try: hkbBehaviorGraph's name
        beh_graph = self.find_first_by_type_name("hkbBehaviorGraph")
        if beh_graph:
            name: str = beh_graph["name"].get_value()
            m = re.match(r"(c[0-9]{4}).hkb", name)
            if m:
                return m.group(1)

        # 2nd try: component of full animation names
        anim_name = self.get_animation(0, full_name=True)
        m = re.match(r".*\\chr\\(c[0-9]{4})\\hkx", anim_name)
        if m:
            return m.group(1)

        # TODO 3rd attempt: folder name

        return None

    def create_event(self, event_name: str, idx: int = None) -> int:
        if idx is None or idx < 0:
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

    def get_event(self, idx: int, default: Any = _undefined) -> str:
        if idx < 0:
            return None

        try:
            return self._events[idx]
        except IndexError:
            if default != _undefined:
                return default
            raise

    def find_event(self, event: str, default: Any = _undefined) -> int:
        try:
            return self._events.index(event)
        except ValueError:
            if default != _undefined:
                return default
            raise

    def rename_event(self, idx: int, new_name: str) -> None:
        self._events[idx] = new_name

    def delete_event(self, idx: int) -> None:
        del self._event_infos[idx]
        del self._events[idx]

    # HKS variables
    def create_variable(
        self,
        variable_name: str,
        var_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
        default: Any = 0,
        idx: int = None,
    ) -> int:
        if idx is None or idx < 0:
            idx = len(self._variables)

        if isinstance(var_type, str):
            var_type = VariableType[var_type]

        var_type = VariableType(var_type)

        # Update the defaults array first to verify the default value is valid
        self.set_variable_default(idx, default, vtype=var_type)

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

    def get_variable_name(self, idx: int, default: Any = _undefined) -> str:
        try:
            return self._variables[idx]
        except IndexError:
            if default != _undefined:
                return default
            raise

    def get_variable(self, idx: int, default: Any = _undefined) -> HkbVariable:
        if idx < 0:
            return None

        try:
            return HkbVariable(
                self.get_variable_name(idx),
                self.get_variable_type(idx),
                *self.get_variable_bounds(idx),
                self.get_variable_default(idx),
            )
        except IndexError:
            if default != _undefined:
                return default
            raise

    def find_variable(self, variable: str, default: Any = _undefined) -> int:
        try:
            return self._variables.index(variable)
        except ValueError:
            if default != _undefined:
                return default
            raise

    def get_variable_type(self, idx: int, default: Any = _undefined) -> VariableType:
        try:
            info: HkbRecord = self._variable_infos[idx]
            type_idx = info.get_field("type", resolve=True)
            return VariableType(type_idx)
        except IndexError:
            if default != _undefined:
                return default
            raise

    def get_variable_bounds(self, idx: int, default: Any = _undefined) -> tuple[int, int]:
        try:
            bounds: HkbRecord = self._variable_bounds[idx]
            lo = bounds.get_field("min/value", resolve=True)
            hi = bounds.get_field("max/value", resolve=True)
            return [lo, hi]
        except IndexError:
            if default != _undefined:
                return default
            raise

    def get_variable_default(self, idx: int, default: Any = _undefined) -> Any:
        try:
            vtype = self.get_variable_type(idx)
        except IndexError:
            if default != _undefined:
                return default
            raise

        # The words array will hold the byte values of all variables that can be represented with
        # at most 32 bit. Where this is not possible (Pointer, Vector3, Vector4, Quaternion), the
        # value will instead be an index into either variantVariableValues (for pointers) or
        # quadVariableValues.
        # Note that words is an array of HkbRecords
        word: int = self._variable_defaults.get_field(
            f"wordVariableValues:{idx}/value", resolve=True
        )

        if vtype == VariableType.BOOL:
            return bool(word)
        elif vtype == VariableType.INT8:
            return word
        elif vtype == VariableType.INT16:
            return word
        elif vtype == VariableType.INT32:
            return word
        elif vtype == VariableType.REAL:
            # IEEE 754 representation
            raw = struct.pack("<i", word)
            return struct.unpack("<f", raw)[0]
        elif vtype == VariableType.POINTER:
            # "word" is an index into another defaults array
            return self._variable_defaults.get_field(f"variantVariableValues:{word}", resolve=True)
        elif vtype == VariableType.VECTOR3:
            quad = self._variable_defaults.get_field(f"quadVariableValues:{word}")
            return [q.get_value() for q in quad[:3]]
        elif vtype == VariableType.VECTOR4:
            quad = self._variable_defaults.get_field(f"quadVariableValues:{word}")
            return [q.get_value() for q in quad[:4]]
        elif vtype == VariableType.QUATERNION:
            # Should be XYZW
            quad = self._variable_defaults.get_field(f"quadVariableValues:{word}")
            return [q.get_value() for q in quad[:4]]
        else:
            raise ValueError(f"Unknown variable type {vtype}")

    def set_variable_default(self, idx: int, default: Any, vtype: VariableType = None) -> Any:
        # The words array will hold the byte values of all variables that can be represented with
        # at most 32 bit. Where this is not possible (Pointer, Vector3, Vector4, Quaternion), the
        # value will instead be an index into either variantVariableValues (for pointers) or
        # quadVariableValues.
        # Note that words is an array of HkbRecords
        words: HkbArray[HkbRecord] = self._variable_defaults["wordVariableValues"]

        if not vtype:
            vtype = self.get_variable_type(idx)

        if vtype == VariableType.BOOL:
            if default in (None, ""):
                default = False

            elif not isinstance(default, bool):
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            # Repack as int32, value will be stored in words
            word_value = 1 if default else 0
            default = word_value
        elif vtype == VariableType.INT8:
            if default in (None, ""):
                default = 0

            elif not isinstance(default, int) or default.bit_length() > 8:
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            word_value = ctypes.c_int8(default).value
            default = word_value
        elif vtype == VariableType.INT16:
            if default in (None, ""):
                default = 0

            elif not isinstance(default, int) or default.bit_length() > 16:
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            word_value = ctypes.c_int16(default).value
            default = word_value
        elif vtype == VariableType.INT32:
            if default in (None, ""):
                default = 0

            elif not isinstance(default, int) or default.bit_length() > 32:
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            word_value = ctypes.c_int32(default).value
            default = word_value
        elif vtype == VariableType.REAL:
            if default in (None, ""):
                default = 0.0

            elif not isinstance(default, float):
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            # IEEE 754 representation
            raw = struct.pack("<f", default)
            word_value = struct.unpack("<i", raw)[0]
            default = word_value
        elif vtype == VariableType.POINTER:
            # the default will be stored in another defaults array
            if default is not None and not isinstance(default, str):
                raise ValueError(
                    f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                )

            if default and default not in self.objects:
                logging.getLogger().warning(
                    "Default target {default} for pointer variable {idx} does not exist"
                )

            # Add a new pointer to variants, words will store the variant index.
            # As opposed to words, this contains the plain pointers without another record around.
            pointers: HkbArray[HkbPointer] = self._variable_defaults["variantVariableValues"]

            if idx < len(words):
                # When creating a new variable default we append, otherwise we update
                pidx: int = words[idx].get_field("value", resolve=True)
                pointers[pidx].set_value(default)
                word_value = pidx
            else:
                # We are creating a new default value, append a new entry
                ptr = HkbPointer.new(self, pointers.element_type_id, default)
                pointers.append(ptr)
                word_value = len(pointers) - 1
        elif vtype in (
            VariableType.VECTOR3,
            VariableType.VECTOR4,
            VariableType.QUATERNION,
        ):
            if vtype == VariableType.VECTOR3:
                if default in (None, ""):
                    default = [0.0, 0.0, 0.0]

                elif not isinstance(default, Iterable) or len(default) != 3:
                    raise ValueError(
                        f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                    )
            elif vtype == VariableType.VECTOR4:
                if default in (None, ""):
                    default = [0.0, 0.0, 0.0, 0.0]
                
                elif not isinstance(default, Iterable) or len(default) != 4:
                    raise ValueError(
                        f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                    )
            elif vtype == VariableType.QUATERNION:
                # Should be XYZW
                if default in (None, ""):
                    default = [0.0, 0.0, 0.0, 1.0]

                elif not isinstance(default, Iterable) or len(default) != 4:
                    raise ValueError(
                        f'Invalid default "{default}" for variable {idx} ({vtype.name})'
                    )

                # TODO must the quaternion be normalized?

            # Add a new 4-tuple to quads, words will store the quad index.
            # As opposed to words, this contains the array values without another record around.
            quads: HkbArray[HkbArray[HkbFloat]] = self._variable_defaults["quadVariableValues"]

            if idx < len(words):
                # When creating a new variable default we append, otherwise we update
                qidx = words[idx].get_field("value", resolve=True)
                default = quads[qidx]
                for i in range(len(default)):
                    default[i].set_value(default[i])
                word_value = qidx
            else:
                # We are creating a new default value, append a new entry
                float_type = self.type_registry.get_subtype(quads.element_type_id)
                values = [HkbFloat.new(self, float_type, v) for v in default]
                default = HkbArray.new(self, quads.element_type_id, values)
                quads.append(default)
                word_value = len(quads) - 1
        else:
            raise ValueError(f"Unknown variable type {vtype}")

        if idx < len(words):
            # Update an existing variable's default
            words[idx].set_field("value", word_value)
        elif idx == len(words):
            # We're creating an entry for a new variable
            record = HkbRecord.new(self, words.element_type_id, {"value": default})
            words.append(record)
        else:
            raise ValueError(f"Index {idx} is not a valid variable index")

        return default

    def delete_variable(self, idx: int) -> None:
        del self._variables[idx]
        del self._variable_bounds[idx]
        del self._variable_infos[idx]
        del self._variable_defaults["wordVariableValues"][idx]

        self._cleanup_variable_defaults()

    def _cleanup_variable_defaults(self) -> None:
        words: HkbArray[HkbRecord] = self._variable_defaults["wordVariableValues"]

        def cleanup(defaults: HkbArray, vartypes: list[VariableType]):
            used_indices = []
            variables = []

            for idx, var in enumerate(self.get_variables(full_info=True)):
                if var.vtype in vartypes:
                    variables.append(idx)
                    target_idx = words[idx].get_field("value", resolve=True)
                    used_indices.append(target_idx)

            if len(used_indices) == len(defaults):
                return

            used_indices.sort()

            # Remove any items that are no longer referenced
            for idx in reversed(used_indices):
                del defaults[idx]

            # Update the references to the new indices
            old_to_new = {old: new for new, old in enumerate(used_indices)}

            for var in variables:
                old = words[var].get_field("value", resolve=True)
                words[var].set_field("value", old_to_new[old])

        # Quads and pointers are referenced from the words array, so when a variable is removed
        # it can leave behind abandoned items in those arrays
        quads: HkbArray = self._variable_defaults["quadVariableValues"]
        pointers: HkbArray = self._variable_defaults["variantVariableValues"]

        cleanup(
            quads, [VariableType.VECTOR3, VariableType.VECTOR4, VariableType.QUATERNION]
        )
        cleanup(pointers, [VariableType.POINTER])

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
        if idx is None or idx < 0:
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

    def get_animation(self, idx: int, default: Any = _undefined, *, full_name: bool = False) -> str:
        if idx < 0:
            return None

        try:
            anim: str = self._animations[idx]
        except IndexError:
            if default != _undefined:
                return default
            raise

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

    def delete_animation(self, idx: int) -> None:
        del self._animations[idx]
