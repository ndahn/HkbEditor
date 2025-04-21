from dataclasses import dataclass, field

from .hkb_base import HkbObject, HkbReference
from .variable_binding_set import VariableBindingSet


@dataclass
class ManualSelectorGenerator(HkbObject):
    name: str = "Jump_F HandCondition Selector"
    variableBindingSet: VariableBindingSet = None
    generators: list[HkbReference] = field(default_factory=list)

    # These are sometimes used
    selectedIndexCanChangeAfterActivate: bool = True
    generatorChangedTransitionEffect: HkbReference = "object0"
    userData: int = 0

    # These never seem to be used
    propertyBag: list = field(default_factory=list)
    selectedGeneratorIndex: int = 0
    indexSelector: HkbReference = "object0"
    sentOnClipEnd: dict = field(default_factory=dict)
    generatorPreDeleteIndex: list = field(default_factory=list)
    endOfClipEventId: int = -1
