from .base import HkbObject, HkbReference


class HkbLayer(HkbObject):
    @classmethod
    def create(
        self,
        id: str,
        generator: HkbReference = "object0",
        boneWeights: HkbReference = "object0",
        useMotion: bool = False,
        blendingControlData: str = "",  # TODO hkbEventDrivenBlendingObject
    ):
        super().create(
            id,
            "type294",
            generator,
            boneWeights,
            useMotion,
            blendingControlData,
        )

    @property
    def generator(self):
        return self.get("generator")
    
    @property
    def boneWeights(self):
        return self.get("boneWeights")
    
    @property
    def useMotion(self):
        return self.get("useMotion")
    
    @property
    def blendingControlData(self):
        return self.get("blendingControlData")

    @generator.setter
    def generator(self, val):
        self.set("generator", val)
    
    @boneWeights.setter
    def boneWeights(self, val):
        self.set("boneWeights", val)
    
    @useMotion.setter
    def useMotion(self, val):
        self.set("useMotion", val)
    
    @blendingControlData.setter
    def blendingControlData(self, val):
        self.set("blendingControlData", val)
    