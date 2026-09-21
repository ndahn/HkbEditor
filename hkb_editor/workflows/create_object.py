from typing import Iterable
import re

from hkb_editor.hkb import Tagfile


def get_record_types(
    tagfile: Tagfile,
    allowed_types: Iterable[str] = None,
    *,
    include_derived_types: bool = False,
) -> list[tuple[str, str]]:
    """List the ``(type_id, type_name)`` pairs a new object may use.

    ``allowed_types`` may name types either by ID (``typeNNN``) or by name.
    Without it every record type in the tagfile is returned.
    """
    type_registry = tagfile.type_registry

    if not allowed_types:
        # There is no "hkbRecord" type to identify complex types that make sense
        # for this dialog. Instead we have to go by the type format, which may
        # vary between games. Luckily, every tagfile seems to contain a
        # "hkRootLevelContainer" which we can use to identify the record format.
        record_format = type_registry.get_format(tagfile.behavior_root.type_id)
        return [
            (type_id, details["name"])
            for type_id, details in type_registry.types.items()
            if details["format"] == record_format
        ]

    if isinstance(allowed_types, str):
        allowed_types = [allowed_types]

    record_types = []

    for tp in allowed_types:
        if re.match(r"type[0-9]+", tp):
            tid = tp
            name = type_registry.get_name(tp)
        else:
            tid = type_registry.find_first_type_by_name(tp)
            name = tp

        record_types.append((tid, name))

        if include_derived_types:
            for derived in type_registry.get_compatible_types(tid):
                record_types.append((derived, type_registry.get_name(derived)))

    # Sort by names
    record_types.sort(key=lambda t: t[1])
    return record_types
