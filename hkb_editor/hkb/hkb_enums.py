from typing import Type
from enum import IntEnum
from functools import cache

from .type_registry import TypeRegistry


# TODO check HKLib to extract more flag definitions
# https://github.com/The12thAvenger/HKLib/tree/main/HKLib/hk2018/Autogen


class hkbVariableBindingSet_Binding_BindingType(IntEnum):
    VARIABLE = 0
    CHARACTER_PROPERTY = 1


class hkbBehaviorGraph_NodeIdRanges(IntEnum):
    FIRST_TRANSITION_EFFECT_ID = 64512
    FIRST_DYNAMIC_NODE_ID = 64511
    LAST_DYNAMIC_NODE_ID = 32255
    LAST_STANDARD_NODE_ID = 32254


class hkbBehaviorGraph_VariableMode(IntEnum):
    DISCARD_WHEN_INACTIVE = 0
    MAINTAIN_VALUES_WHEN_INACTIVE = 1


class hkbVariableInfo_VariableType(IntEnum):
    INVALID = -1
    BOOL = 0
    INT8 = 1
    INT16 = 2
    INT32 = 3
    REAL = 4
    POINTER = 5
    VECTOR3 = 6
    VECTOR4 = 7
    QUATERNION = 8


class hkbRoleAttribute_Role(IntEnum):
    DEFAULT = 0
    FILE_NAME = 1
    BONE_INDEX = 2
    EVENT_ID = 3
    VARIABLE_INDEX = 4
    ATTRIBUTE_INDEX = 5
    TIME = 6
    SCRIPT = 7
    LOCAL_FRAME = 8
    BONE_ATTACHMENT = 9
    CHARACTER_PROPERTY_SHEET = 10


class hkbStateMachine_StartStateMode(IntEnum):
    DEFAULT = 0
    SYNC = 1
    RANDOM = 2
    CHOOSER = 3


class hkbStateMachine_StateMachineSelfTransitionMode(IntEnum):
    NO_TRANSITION = 0
    TRANSITION_TO_START_STATE = 1
    FORCE_TRANSITION_TO_START_STATE = 2


class hkbTransitionEffect_SelfTransitionMode(IntEnum):
    CONTINUE_IF_CYCLIC_BLEND_IF_ACYCLIC = 0
    CONTINUE = 1
    RESET = 2
    BLEND = 3


class hkbTransitionEffect_EventMode(IntEnum):
    DEFAULT = 0
    PROCESS_ALL = 1
    IGNORE_FROM_GENERATOR = 2
    IGNORE_TO_GENERATOR = 3


class hkbHandIkControlData_HandleChangeMode(IntEnum):
    ABRUPT = 0
    CONSTANT_VELOCITY = 1


class hkbTransitionEffect_EventMode(IntEnum):
    DEFAULT = 0
    PROCESS_ALL = 1
    IGNORE_FROM_GENERATOR = 2
    IGNORE_TO_GENERATOR = 3


class hkbTransitionEffect_SelfTransitionMode(IntEnum):
    CONTINUE_IF_CYCLIC_BLEND_IF_ACYCLIC = 0
    CONTINUE = 1
    RESET = 2
    BLEND = 3


class hkaSkeletonMapperData_MappingType(IntEnum):
    HK_RAGDOLL_MAPPING = 0
    HK_RETARGETING_MAPPING = 1


class hkbRigidBodySetup_Type(IntEnum):
    INVALID = -1
    KEYFRAMED = 0
    DYNAMIC = 1
    FIXED = 2


class hkbShapeSetup_Type(IntEnum):
    CAPSULE = 0
    FILE = 1


class hkbBlendCurveUtils_BlendCurve(IntEnum):
    SMOOTH = 0
    LINEAR = 1
    LINEAR_TO_SMOOTH = 2
    SMOOTH_TO_LINEAR = 3


hkbLayer_BlendCurve = hkbBlendCurveUtils_BlendCurve


class CustomLookAtTwistModifier_GainState(IntEnum):
    TARGET_GAIN = 0
    ON = 1
    OFF = 2


class CustomLookAtTwistModifier_SetAngleMethod(IntEnum):
    LINEAR = 0
    RAMPED = 1


class CustomLookAtTwistModifier_MultiRotationAxisType(IntEnum):
    XY = 0
    YX = 1


class hkbTwistModifier_RotationAxisCoordinates(IntEnum):
    IN_MODEL_COORDINATES = 0
    IN_PARENT_COORDINATES = 1
    IN_LOCAL_COORDINATES = 2


class hkbTwistModifier_SetAngleMethod(IntEnum):
    LINEAR = 0
    RAMPED = 1


class hkbEvaluateHandleModifier_HandleChangeMode(IntEnum):
    ABRUPT = 0
    CONSTANT_VELOCITY = 1


class CustomManualSelectorGenerator_OffsetType(IntEnum):
    NONE = 0
    IDLE_CATEGORY = 11
    WEAPON_CATEGORY_RIGHT = 13
    WEAPON_CATEGORY_LEFT = 14
    ANIM_ID = 15
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


class hkbBlendingTransitionEffect_EndMode(IntEnum):
    NONE = 0
    TRANSITION_UNTIL_END_OF_FROM_GENERATOR = 1
    CAP_DURATION_AT_END_OF_FROM_GENERATOR = 2


class hkbClipGenerator_PlaybackMode(IntEnum):
    SINGLE_PLAY = 0
    LOOPING = 1
    USER_CONTROLLED = 2
    PING_PONG = 3
    COUNT = 4


# TODO sekiro only?
# CustomDockingGenerator_DockingType(IntEnum): pass


class hkbDockingGenerator_BlendType(IntEnum):
    BLEND_IN = 0
    FULL_ON = 1


@cache
def get_hkb_enum(
    type_registry: TypeRegistry, record_type_id: str, path: str
) -> Type[IntEnum]:
    # Not all records are objects or have IDs, so going from the record type is better
    field = path.rsplit("/", maxsplit=1)[-1].split(":", maxsplit=1)[0]
    record_fields = type_registry.get_field_types(record_type_id)
    field_type = record_fields.get(field, None)

    if not field_type:
        return None

    # Not robust, but seems consistent between games so far
    if type_registry.get_name(field_type) != "hkEnum":
        return None

    try:
        enum_type = type_registry.get_typeparams(field_type)[0]
    except IndexError:
        return None

    enum_name = type_registry.get_name(enum_type).replace("::", "_")
    return globals().get(enum_name, None)
