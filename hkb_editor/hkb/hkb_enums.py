from typing import Type
from enum import IntEnum
from functools import cache

from .type_registry import TypeRegistry


# TODO check HKLib to extract more flag definitions
# https://github.com/The12thAvenger/HKLib/tree/main/HKLib/hk2018/Autogen


# Enum values are not documented within the behavior files, but we can discover
# many values from when they are used and the comments going with them
# hkbBehaviorGraph_VariableMode(IntEnum): pass
# hkbVariableInfo_VariableType(IntEnum): pass
# hkbRoleAttribute_Role(IntEnum): pass
class hkbVariableBindingSet_Binding_BindingType(IntEnum):
    VARIABLE = 0


# hkbStateMachine_StartStateMode(IntEnum): pass
class hkbStateMachine_StateMachineSelfTransitionMode(IntEnum):
    NO_TRANSITION = 0
    TRANSITION_TO_START_STATE = 1


class hkbTransitionEffect_SelfTransitionMode(IntEnum):
    CONTINUE_IF_CYCLIC_BLEND_IF_ACYCLIC = 0
    CONTINUE = 1
    RESET = 2


# hkbTransitionEffect_EventMode(IntEnum): pass
# hkbHandIkControlData_HandleChangeMode(IntEnum): pass
# hkbTransitionEffect_EventMode(IntEnum): pass
# hkaSkeletonMapperData_MappingType(IntEnum): pass
# hkbRigidBodySetup_Type(IntEnum): pass
# hkbShapeSetup_Type(IntEnum): pass
# hkbBlendCurveUtils_BlendCurve(IntEnum): pass
# CustomLookAtTwistModifier_MultiRotationAxisType(IntEnum): pass
# CustomLookAtTwistModifier_SetAngleMethod(IntEnum): pass
# hkbTwistModifier_SetAngleMethod(IntEnum): pass
# hkbTwistModifier_RotationAxisCoordinates(IntEnum): pass
# hkbEvaluateHandleModifier_HandleChangeMode(IntEnum): pass
class CustomManualSelectorGenerator_OffsetType(IntEnum):
    NONE = 0
    IDLE_CATEGORY = 11
    WEAPON_CATEGORY_RIGHT = 13
    WEAPON_CATEGORY_LEFT = 14
    WEAPON_CATEGORY_HAND_STYLE = 16
    MAGIC_CATEGORY = 17
    SWORD_ARTS_CATEGORY = 18


class CustomManualSelectorGenerator_AnimeEndEventType(IntEnum):
    FIRE_NEXT_STATE_EVENT = 0
    FIRE_STATE_END_EVENT = 1
    FIRE_IDLE_EVENT = 2
    NONE = 3


class CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate(IntEnum):
    NONE = 0
    SELF_TRANSITION = 1
    UPDATE = 2


class CustomManualSelectorGenerator_ReplanningAI(IntEnum):
    ENABLE = 0
    DISABLE = 1


class CustomManualSelectorGenerator_RideSync(IntEnum):
    DISABLE = 0
    ENABLE = 1


# hkbBlendingTransitionEffect_EndMode(IntEnum): pass
# hkbBlendCurveUtils_BlendCurve(IntEnum): pass
class hkbClipGenerator_PlaybackMode(IntEnum):
    SINGLE_PLAY = 0
    LOOPING = 1


# CustomDockingGenerator_DockingType(IntEnum): pass
# hkbDockingGenerator_BlendType(IntEnum): pass


@cache
def get_hkb_enum(
    type_registry: TypeRegistry, record_type_id: str, field: str
) -> Type[IntEnum]:
    # Not all records are objects or have IDs, so going from the record type is better
    field_type = type_registry.get_field_types(record_type_id).get(field, None)

    if not field_type or type_registry.get_name(field_type) != "hkEnum":
        # Not robust, but seems consistent so far
        return None

    try:
        enum_type = type_registry.get_typeparams(field_type)[0]
    except IndexError:
        return None

    enum_name = type_registry.get_name(enum_type).replace("::", "_")
    return globals().get(enum_name, None)
