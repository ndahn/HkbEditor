from typing import Type
from enum import IntFlag
from functools import cache

from .type_registry import TypeRegistry


# TODO check HKLib to extract more flag definitions
# https://github.com/The12thAvenger/HKLib/tree/main/HKLib/hk2018/Autogen

# TODO add 0 mappings where missing, handle 0 in clipgen and cmsg dialogs


class hkbClipGenerator_Flags(IntFlag):
    CONTINUE_MOTION_AT_END = 1
    SYNC_HALF_CYCLE_IN_PING_PONG_MODE = 2
    MIRROR = 4
    FORCE_DENSE_POSE = 8
    DONT_CONVERT_ANNOTATIONS_TO_TRIGGERS = 16
    IGNORE_MOTION = 32


class hkbStateMachine_TransitionInfo_Flags(IntFlag):
    USE_TRIGGER_INTERVAL = 1
    USE_INITIATE_INTERVAL = 2
    UNINTERRUPTIBLE_WHILE_PLAYING = 4
    UNINTERRUPTIBLE_WHILE_DELAYED = 8
    DELAY_STATE_CHANGE = 16
    DISABLED = 32
    DISALLOW_RETURN_TO_PREVIOUS_STATE = 64
    DISALLOW_RANDOM_TRANSITION = 128
    DISABLE_CONDITION = 256
    ALLOW_SELF_TRANSITION_BY_TRANSITION_FROM_ANY_STATE = 512
    IS_GLOBAL_WILDCARD = 1024
    IS_LOCAL_WILDCARD = 2048
    FROM_NESTED_STATE_ID_IS_VALID = 4096
    TO_NESTED_STATE_ID_IS_VALID = 8192
    ABUT_AT_END_OF_FROM_GENERATOR = 16384


class hkbBlendingTransitionEffect_Flags(IntFlag):
    NONE = 0
    IGNORE_FROM_WORLD_FROM_MODEL = 1
    SYNC = 2
    IGNORE_TO_WORLD_FROM_MODEL = 4
    IGNORE_TO_WORLD_FROM_MODEL_ROTATION = 8
    DONT_BLEND_CONTROLS_DATA = 16


class CustomTransitionEffect_Flags(IntFlag):
    NONE = 0
    IGNORE_FROM_WORLD_FROM_MODEL = 1
    SYNC = 2


class hkbBlenderGenerator_Flags(IntFlag):
    SYNC = 1
    SMOOTH_GENERATOR_WEIGHTS = 4
    DONT_DEACTIVATE_CHILDREN_WITH_ZERO_WEIGHTS = 8
    PARAMETRIC_BLEND = 16
    IS_PARAMETRIC_BLEND_CYCLIC = 32
    FORCE_DENSE_POSE = 64
    BLEND_MOTION_OF_ADDITIVE_ANIMATIONS = 128
    USE_VELOCITY_SYNCHRONIZATION = 256


@cache
def get_hkb_flags(
    type_registry: TypeRegistry, record_type_id: str, field: str
) -> Type[IntFlag]:
    if field != "flags":
        # Seems consistent so far
        return None

    flags_name = type_registry.get_name(record_type_id).replace("::", "_") + "_Flags"
    return globals().get(flags_name, None)
