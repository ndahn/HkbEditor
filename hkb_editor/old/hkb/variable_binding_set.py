from enum import IntEnum

from .base import HkbObject


class HkbVariableBinding(HkbObject):
    class BindingType(IntEnum):
        VARIABLE = 0

    @classmethod
    def create(
        cls, 
        id: str,
        memberPath: str = "",
        variableIndex: int = -1,
        bitIndex: int = -1,
        bindingType: BindingType = BindingType.VARIABLE,
    ):
        return super().create(
            id, 
            "type91",
            memberPath,
            variableIndex,
            bitIndex,
            bindingType,
        )

    @property
    def memberPath(self):
        return self.get("memberPath")

    @property
    def variableIndex(self):
        return self.get("variableIndex")

    @property
    def bitIndex(self):
        return self.get("bitIndex")

    @property
    def bindingType(self):
        return self.get("bindingType")

    @memberPath.setter
    def memberPath(self, val):
        self.set("memberPath", val)

    @variableIndex.setter
    def variableIndex(self, val):
        self.set("variableIndex", val)

    @bitIndex.setter
    def bitIndex(self, val):
        self.set("bitIndex", val)

    @bindingType.setter
    def bindingType(self, val):
        self.set("bindingType", val)
