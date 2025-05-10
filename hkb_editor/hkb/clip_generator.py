from enum import IntEnum

from .base import HkbObject, HkbReference


class HkbClipGenerator(HkbObject):
    class PlaybackMode(IntEnum):
        SINGLE_PLAY = 0
        LOOPING = 1

    @classmethod
    def create(
        cls,
        id: str,
        animationName: str = "",
        triggers: HkbReference = "object0",
        userPartitionMask: int = -1,
        cropStartAmountLocalTime: float = 0.0,
        cropEndAmountLocalTime: float = 0.0,
        startTime: float = 0.0,
        playbackSpeed: float = 0.0,
        enforcedDuration: float = 0.0,
        userControlledTimeFraction: float = 0.0,
        mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
        flags: int = 0,
        animationInternalId: int = 0,  # TODO should be unique?
    ):
        return super().create(
            id,
            "type320",
            animationName,
            triggers,
            userPartitionMask,
            cropStartAmountLocalTime,
            cropEndAmountLocalTime,
            startTime,
            playbackSpeed,
            enforcedDuration,
            userControlledTimeFraction,
            mode,
            flags,
            animationInternalId,
        )

    @property
    def animationName(self):
        return self.get("animationName")

    @property
    def triggers(self):
        return self.get("triggers")

    @property
    def userPartitionMask(self):
        return self.get("userPartitionMask")

    @property
    def cropStartAmountLocalTime(self):
        return self.get("cropStartAmountLocalTime")

    @property
    def cropEndAmountLocalTime(self):
        return self.get("cropEndAmountLocalTime")

    @property
    def startTime(self):
        return self.get("startTime")

    @property
    def playbackSpeed(self):
        return self.get("playbackSpeed")

    @property
    def enforcedDuration(self):
        return self.get("enforcedDuration")

    @property
    def userControlledTimeFraction(self):
        return self.get("userControlledTimeFraction")

    @property
    def mode(self):
        return self.get("mode")

    @property
    def flags(self):
        return self.get("flags")

    @property
    def animationInternalId(self):
        return self.get("animationInternalId")

    @animationName.setter
    def animationName(self, val):
        self.set("animationName", val)
    
    @triggers.setter
    def triggers(self, val):
        self.set("triggers", val)
    
    @userPartitionMask.setter
    def userPartitionMask(self, val):
        self.set("userPartitionMask", val)
    
    @cropStartAmountLocalTime.setter
    def cropStartAmountLocalTime(self, val):
        self.set("cropStartAmountLocalTime", val)
    
    @cropEndAmountLocalTime.setter
    def cropEndAmountLocalTime(self, val):
        self.set("cropEndAmountLocalTime", val)
    
    @startTime.setter
    def startTime(self, val):
        self.set("startTime", val)
    
    @playbackSpeed.setter
    def playbackSpeed(self, val):
        self.set("playbackSpeed", val)
    
    @enforcedDuration.setter
    def enforcedDuration(self, val):
        self.set("enforcedDuration", val)
    
    @userControlledTimeFraction.setter
    def userControlledTimeFraction(self, val):
        self.set("userControlledTimeFraction", val)
    
    @mode.setter
    def mode(self, val):
        self.set("mode", val)
    
    @flags.setter
    def flags(self, val):
        self.set("flags", val)
    
    @animationInternalId.setter
    def animationInternalId(self, val):
        self.set("animationInternalId", val)
    
