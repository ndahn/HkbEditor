import re

from hkb_editor.hkb import HkbRecord


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
