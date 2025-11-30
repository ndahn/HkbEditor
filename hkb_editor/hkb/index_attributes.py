import re

from hkb_editor.hkb import HavokBehavior, HkbRecord


event_attributes = {
    "hkbManualSelectorGenerator": [
        "endOfClipEventId",  # NOTE guessed
    ],
    "hkbStateMachine": [
        "eventToSendWhenStateOrTransitionChanges/id",  # NOTE guessed
    ],
    "hkbStateMachine::TransitionInfoArray": [
        "transitions:*/eventId",
    ],
    "hkbLayer": [
        "blendingControlData/onEventId",
        "blendingControlData/offEventId",
    ],
}


variable_attributes = {
    "hkbVariableBindingSet": [
        "bindings:*/variableIndex",
    ],
    "hkbStateMachine": [
        "syncVariableIndex",
    ],
}


animation_attributes = {
    "hkbClipGenerator": [
        # While the index into the animations array may have changed, we can assume
        # that the animation name has not, so animationName and the clip's name don't
        # need to be changed. The same is true for the CMSG owning this clip.
        "animationInternalId",
    ]
}


def is_event_attribute(obj: HkbRecord, attribute_path: str) -> bool:
    attribute_path = re.sub(r":[0-9]+", ":*", attribute_path)

    if obj.type_name in event_attributes:
        for path in event_attributes[obj.type_name]:
            if path == attribute_path:
                return True

    return False


def is_variable_attribute(obj: HkbRecord, attribute_path: str) -> bool:
    attribute_path = re.sub(r":[0-9]+", ":*", attribute_path)

    if obj.type_name in variable_attributes:
        for path in variable_attributes[obj.type_name]:
            if path == attribute_path:
                return True

    return False


def is_animation_attribute(obj: HkbRecord, attribute_path: str) -> bool:
    attribute_path = re.sub(r":[0-9]+", ":*", attribute_path)

    if obj.type_name in animation_attributes:
        for path in animation_attributes[obj.type_name]:
            if path == attribute_path:
                return True

    return False


def fix_index_references(
    behavior: HavokBehavior,
    attributes: dict[str, list[str]],
    prev_idx: int,
    new_idx: int,
):
    """Fix attributes that refer to values by index.

    Events, variables and animations are referred to by index, so when a value is inserted, removed, or deleted, these indices would suddenly point to different entries. This function adjusts these attributes based on how the value array was modified.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to fix attributes in.
    attributes : dict[str, list[str]]
        A dict from record type names to attribute paths to fix.
    prev_idx : int
        The previous index of the modified array value. Set to None if a new item was inserted at new_idx.
    new_idx : int
        The new index of the modified array value. Set to None if an item at prev_idx was deleted.
    """
    def get_adjusted_index(idx):
        if idx < 0:
            return idx

        # Item inserted
        if prev_idx is None:
            return idx + 1 if idx >= new_idx else idx

        # Item deleted
        elif new_idx is None:
            if idx == prev_idx:
                # Reference to deleted item
                return -1
            return idx - 1 if idx > prev_idx else idx

        # Item moved
        else:
            if idx == prev_idx:
                return new_idx
            elif prev_idx < new_idx:
                # Item moved forward
                return idx - 1 if prev_idx < idx <= new_idx else idx
            else:
                # Item moved backward
                return idx + 1 if new_idx <= idx < prev_idx else idx

    # Process all records
    for record in behavior.objects.values():
        if record.type_name in attributes:
            paths = attributes[record.type_name]
            for attr in record.get_fields(paths).values():
                val = attr.get_value()
                new_val = get_adjusted_index(val)
                if val != new_val:
                    attr.set_value(new_val)
