from .base import HkbObject, HkbArray


class HkbLayerGenerator(HkbObject):
    @classmethod
    def create(
        self,
        id: str,
        layers: HkbArray = None,
        indexOfSyncMasterChild: int = -1,
        flags: int = 0,
    ):
        super().create(
            id,
            "type287",
            layers or HkbArray(),
            indexOfSyncMasterChild,
            flags,
        )

    @property
    def layers(self):
        return self.get("layers")

    @property
    def indexOfSyncMasterChild(self):
        return self.get("indexOfSyncMasterChild")

    @property
    def flags(self):
        return self.get("flags")

    @layers.setter
    def layers(self, val):
        self.set("layers", val)

    @indexOfSyncMasterChild.setter
    def indexOfSyncMasterChild(self, val):
        self.set("indexOfSyncMasterChild", val)

    @flags.setter
    def flags(self, val):
        self.set("flags", val)
