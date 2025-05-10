from enum import IntEnum

from .base import HkbObject, HkbArray, HkbReference


class HkbCustomManualSelectorGenerator(HkbObject):
    class OffsetType(IntEnum):
        NONE = 0
        IDLE_CATEGORY = 11
        WEAPON_CATEGORY_RIGHT = 13
        WEAPON_CATEGORY_LEFT = 14
        WEAPON_CATEGORY_HAND_STYLE = 16
        MAGIC_CATEGORY = 17
        SWORD_ARTS_CATEGORY = 18

    class AnimeEndEventType(IntEnum):
        FIRE_NEXT_STATE_EVENT = 0
        FIRE_STATE_END_EVENT = 1
        FIRE_IDLE_EVENT = 2
        NONE = 3

    class ChangeTypeOfSelectedIndexAfterActivate(IntEnum):
        NONE = 0
        SELF_TRANSITION = 1
        UPDATE = 2

    class ReplanningAI(IntEnum):
        ENABLE = 0
        DISABLE = 1

    class RideSync(IntEnum):
        DISABLE = 0
        ENABLE = 1


    @classmethod
    def create(
        cls,
        id: str,
        generators: HkbArray = None,
        offsetType: OffsetType = OffsetType.NONE,
        animId: int = -1,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        enableScript: bool = False,
        enableTae: bool = False,
        changeTypeOfSelectedIndexAfterActivate: ChangeTypeOfSelectedIndexAfterActivate = ChangeTypeOfSelectedIndexAfterActivate.NONE,
        generatorChangedTransitionEffect: HkbReference = "",
        checkAnimEndSlotNo: int = -1,
        replanningAI: ReplanningAI = ReplanningAI.ENABLE,
        rideSync: RideSync = RideSync.DISABLE,
    ):
        super().create(
            id,
            "type299",
            generators or HkbArray(),
            offsetType,
            animId,
            animeEndEventType,
            enableScript,
            enableTae,
            changeTypeOfSelectedIndexAfterActivate,
            generatorChangedTransitionEffect,
            checkAnimEndSlotNo,
            replanningAI,
            rideSync,
        )

    @property
    def generators(self):
        return self.get("generators")
    
    @property
    def offsetType(self):
        return self.get("offsetType")
    
    @property
    def animId(self):
        return self.get("animId")
    
    @property
    def animeEndEventType(self):
        return self.get("animeEndEventType")
    
    @property
    def enableScript(self):
        return self.get("enableScript")
    
    @property
    def enableTae(self):
        return self.get("enableTae")
    
    @property
    def changeTypeOfSelectedIndexAfterActivate(self):
        return self.get("changeTypeOfSelectedIndexAfterActivate")
    
    @property
    def generatorChangedTransitionEffect(self):
        return self.get("generatorChangedTransitionEffect")
    
    @property
    def checkAnimEndSlotNo(self):
        return self.get("checkAnimEndSlotNo")
    
    @property
    def replanningAI(self):
        return self.get("replanningAI")
    
    @property
    def rideSync(self):
        return self.get("rideSync")
    
    @generators.setter
    def generators(self, val):
        self.set("generators", val)

    @offsetType.setter
    def offsetType(self, val):
        self.set("offsetType", val)

    @animId.setter
    def animId(self, val):
        self.set("animId", val)

    @animeEndEventType.setter
    def animeEndEventType(self, val):
        self.set("animeEndEventType", val)

    @enableScript.setter
    def enableScript(self, val):
        self.set("enableScript", val)

    @enableTae.setter
    def enableTae(self, val):
        self.set("enableTae", val)

    @changeTypeOfSelectedIndexAfterActivate.setter
    def changeTypeOfSelectedIndexAfterActivate(self, val):
        self.set("changeTypeOfSelectedIndexAfterActivate", val)

    @generatorChangedTransitionEffect.setter
    def generatorChangedTransitionEffect(self, val):
        self.set("generatorChangedTransitionEffect", val)

    @checkAnimEndSlotNo.setter
    def checkAnimEndSlotNo(self, val):
        self.set("checkAnimEndSlotNo", val)

    @replanningAI.setter
    def replanningAI(self, val):
        self.set("replanningAI", val)

    @rideSync.setter
    def rideSync(self, val):
        self.set("rideSync", val)
