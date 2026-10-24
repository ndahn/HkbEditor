"""Enum and flag constants as they appear in hk2014 packfile xml.

hk2018 tagfiles store enums and flags as plain integers, but hk2014 packfiles write
them as symbolic constants. The converter needs to be able to map between the two,
which requires the names of the constants.

The values are taken from hkb_enums and hkb_flags, this module only adds the naming
scheme that hk2014 uses for the members. Usually this is a prefix in front of the
member name (e.g. START_STATE_MODE_DEFAULT for hkbStateMachine::StartStateMode.DEFAULT),
but the custom (FromSoftware) enums are written in CamelCase (IdleCategory). Enums that
aren't listed here are not converted, the converter will fall back to keeping their
values as strings.
"""

from enum import IntEnum, IntFlag
from typing import Callable

from . import hkb_enums as E
from . import hkb_flags as F


class ConstantTable:
    """Bidirectional mapping between hk2014 constants and their integer values."""

    def __init__(
        self,
        type_name: str,
        py_enum: type[IntEnum] | type[IntFlag],
        naming: Callable[[str], str],
    ):
        self.type_name = type_name
        self.is_flags = issubclass(py_enum, IntFlag)

        # __members__ includes aliases and zero values, which iterating a Flag skips
        self.by_name: dict[str, int] = {
            naming(name): int(member.value)
            for name, member in py_enum.__members__.items()
        }

        self.by_value: dict[int, str] = {}
        for name, value in self.by_name.items():
            self.by_value.setdefault(value, name)

    def parse(self, text: str) -> int | None:
        """Convert the symbolic representation to an integer. None if it fails."""
        text = text.strip()

        if text in self.by_name:
            return self.by_name[text]

        if not self.is_flags:
            return None

        # Flags can be combined, usually with "|"
        value = 0
        for part in text.split("|"):
            part = part.strip()
            if part in self.by_name:
                value |= self.by_name[part]
            else:
                return None

        return value

    def format(self, value: int) -> str | None:
        """Convert an integer to its symbolic representation. None if it fails."""
        if value in self.by_value:
            return self.by_value[value]

        if not self.is_flags:
            return None

        names = []
        remaining = value

        for const_value, name in sorted(self.by_value.items()):
            if const_value and const_value & remaining == const_value:
                if const_value & (const_value - 1):
                    # Not a single bit, skip combinations
                    continue
                names.append(name)
                remaining &= ~const_value

        if remaining or not names:
            return None

        return "|".join(names)


def _camel_case(name: str) -> str:
    """IDLE_CATEGORY -> IdleCategory"""
    return "".join(part.capitalize() for part in name.split("_"))


def _offset_type_name(name: str) -> str:
    return {"NONE": "OffsetNone", "ANIM_ID": "AnimIdOffset"}.get(name) or _camel_case(name)


def _enum(type_name: str, py_enum: type[IntEnum], naming: str | Callable = ""):
    """naming is either a prefix, or a function that creates the constant."""
    if isinstance(naming, str):
        prefix = naming
        naming = lambda name: prefix + name  # noqa: E731
    return type_name, ConstantTable(type_name, py_enum, naming)


def _flags(type_name: str, py_flags: type[IntFlag]):
    return type_name, ConstantTable(type_name, py_flags, lambda name: "FLAG_" + name)


CONSTANTS: dict[str, ConstantTable] = dict(
    [
        _enum("hkbBehaviorGraph::VariableMode", E.hkbBehaviorGraph_VariableMode, "VARIABLE_MODE_"),
        _enum("hkbVariableBindingSet::Binding::BindingType", E.hkbVariableBindingSet_Binding_BindingType, "BINDING_TYPE_"),
        _enum("hkbVariableInfo::VariableType", E.hkbVariableInfo_VariableType, "VARIABLE_TYPE_"),
        _enum("hkbRoleAttribute::Role", E.hkbRoleAttribute_Role, "ROLE_"),
        _enum("hkbStateMachine::StartStateMode", E.hkbStateMachine_StartStateMode, "START_STATE_MODE_"),
        _enum("hkbStateMachine::StateMachineSelfTransitionMode", E.hkbStateMachine_StateMachineSelfTransitionMode, "SELF_TRANSITION_MODE_"),
        _enum("hkbTransitionEffect::SelfTransitionMode", E.hkbTransitionEffect_SelfTransitionMode, "SELF_TRANSITION_MODE_"),
        _enum("hkbTransitionEffect::EventMode", E.hkbTransitionEffect_EventMode, "EVENT_MODE_"),
        _enum("hkbBlendingTransitionEffect::EndMode", E.hkbBlendingTransitionEffect_EndMode, "END_MODE_"),
        _enum("hkbClipGenerator::PlaybackMode", E.hkbClipGenerator_PlaybackMode, "MODE_"),
        _enum("hkbHandIkControlData::HandleChangeMode", E.hkbHandIkControlData_HandleChangeMode, "HANDLE_CHANGE_MODE_"),
        _enum("hkbEvaluateHandleModifier::HandleChangeMode", E.hkbEvaluateHandleModifier_HandleChangeMode, "HANDLE_CHANGE_MODE_"),
        _enum("hkbTwistModifier::RotationAxisCoordinates", E.hkbTwistModifier_RotationAxisCoordinates, "ROTATION_AXIS_"),
        _enum("hkbTwistModifier::SetAngleMethod", E.hkbTwistModifier_SetAngleMethod, ""),
        _enum("hkbBlendCurveUtils::BlendCurve", E.hkbBlendCurveUtils_BlendCurve, "BLEND_CURVE_"),
        _enum("hkaSkeletonMapperData::MappingType", E.hkaSkeletonMapperData_MappingType, ""),
        _enum("hkbDockingGenerator::BlendType", E.hkbDockingGenerator_BlendType, ""),
        # Custom (FromSoftware) types, inconsistent naming
        _enum("CustomLookAtTwistModifier::MultiRotationAxisType", E.CustomLookAtTwistModifier_MultiRotationAxisType, lambda name: "Axis" + name),
        _enum("CustomLookAtTwistModifier::SetAngleMethod", E.CustomLookAtTwistModifier_SetAngleMethod, ""),
        _enum("CustomManualSelectorGenerator::OffsetType", E.CustomManualSelectorGenerator_OffsetType, _offset_type_name),
        _enum("CustomManualSelectorGenerator::AnimeEndEventType", E.CustomManualSelectorGenerator_AnimeEndEventType, _camel_case),
        _enum("CustomManualSelectorGenerator::ChangeTypeOfSelectedIndexAfterActivate", E.CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate, ""),
        _enum("CustomManualSelectorGenerator::ReplanningAI", E.CustomManualSelectorGenerator_ReplanningAI, _camel_case),
        _enum("CustomManualSelectorGenerator::RideSync", E.CustomManualSelectorGenerator_RideSync, _camel_case),
        _flags("hkbBlendingTransitionEffect::FlagBits", F.hkbBlendingTransitionEffect_Flags),
        _flags("hkbRoleAttribute::RoleFlags", F.hkbRoleAttribute_Flags),
        _flags("hkbLayerGenerator::LayerFlagBits", F.hkbLayerGenerator_Flags),
        _flags("hkbDockingGenerator::DockingFlagBits", F.hkbDockingGenerator_Flags),
        _flags("hkbStateMachine::TransitionInfo::TransitionFlags", F.hkbStateMachine_TransitionInfoArray_Flags),
    ]
)
