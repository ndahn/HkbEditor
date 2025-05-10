from .base import HkbObject, HkbArray, HkbReference


class HkbManualSelectorGenerator(HkbObject):
    @classmethod
    def create(
        self,
        id: str,
        generators: HkbArray = None,
        selectedGeneratorIndex: int = -1,
        indexSelector: HkbReference = "object0",
        selectedIndexCanChangeAfterActivate: bool = False,
        generatorChangedTransitionEffect: str = "",  # TODO hkbTransitionEffect
        sentOnClipEnd: str = "",  # TODO hkbEventProperty
        generatorPreDeleteIndex: HkbArray = None,
        endOfClipEventId: int = -1,
    ):
        super().create(
            id,
            "type318",
            generators or HkbArray(),
            selectedGeneratorIndex,
            indexSelector,
            selectedIndexCanChangeAfterActivate,
            generatorChangedTransitionEffect,
            sentOnClipEnd,
            generatorPreDeleteIndex or HkbArray(),
            endOfClipEventId,
        )

    @property
    def generators(self):
        return self.get("generators")

    @property
    def selectedGeneratorIndex(self):
        return self.get("selectedGeneratorIndex")

    @property
    def indexSelector(self):
        return self.get("indexSelector")

    @property
    def selectedIndexCanChangeAfterActivate(self):
        return self.get("selectedIndexCanChangeAfterActivate")

    @property
    def generatorChangedTransitionEffect(self):
        return self.get("generatorChangedTransitionEffect")

    @property
    def sentOnClipEnd(self):
        return self.get("sentOnClipEnd")

    @property
    def generatorPreDeleteIndex(self):
        return self.get("generatorPreDeleteIndex")

    @property
    def endOfClipEventId(self):
        return self.get("endOfClipEventId")

    @generators.setter
    def generators(self, val):
        self.set("generators", val)
    
    @selectedGeneratorIndex.setter
    def selectedGeneratorIndex(self, val):
        self.set("selectedGeneratorIndex", val)
    
    @indexSelector.setter
    def indexSelector(self, val):
        self.set("indexSelector", val)
    
    @selectedIndexCanChangeAfterActivate.setter
    def selectedIndexCanChangeAfterActivate(self, val):
        self.set("selectedIndexCanChangeAfterActivate", val)
    
    @generatorChangedTransitionEffect.setter
    def generatorChangedTransitionEffect(self, val):
        self.set("generatorChangedTransitionEffect", val)
    
    @sentOnClipEnd.setter
    def sentOnClipEnd(self, val):
        self.set("sentOnClipEnd", val)
    
    @generatorPreDeleteIndex.setter
    def generatorPreDeleteIndex(self, val):
        self.set("generatorPreDeleteIndex", val)
    
    @endOfClipEventId.setter
    def endOfClipEventId(self, val):
        self.set("endOfClipEventId", val)
    