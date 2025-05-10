from .base import HkbObject, HkbReference


class HkbScriptGenerator(HkbObject):
    @classmethod
    def create(
        cls,
        id: str,
        child: HkbReference = "object0",
        onActivateScript: str = "",
        onPreUpdateScript: str = "",
        onGenerateScript: str = "",
        onHandleEventScript: str = "",
        onDeactivateScript: str = "",
    ):
        return super().create(
            id,
            "type146",
            child,
            onActivateScript,
            onPreUpdateScript,
            onGenerateScript,
            onHandleEventScript,
            onDeactivateScript,
        )

    @property
    def child(self):
        return self.get("child")
        
    @property
    def onActivateScript(self):
        return self.get("onActivateScript")
        
    @property
    def onPreUpdateScript(self):
        return self.get("onPreUpdateScript")
        
    @property
    def onGenerateScript(self):
        return self.get("onGenerateScript")
        
    @property
    def onHandleEventScript(self):
        return self.get("onHandleEventScript")
        
    @property
    def onDeactivateScript(self):
        return self.get("onDeactivateScript")

    @child.setter
    def child(self, val):
        self.set("child", val)

    @onActivateScript.setter
    def onActivateScript(self, val):
        self.set("onActivateScript", val)

    @onPreUpdateScript.setter
    def onPreUpdateScript(self, val):
        self.set("onPreUpdateScript", val)

    @onGenerateScript.setter
    def onGenerateScript(self, val):
        self.set("onGenerateScript", val)

    @onHandleEventScript.setter
    def onHandleEventScript(self, val):
        self.set("onHandleEventScript", val)

    @onDeactivateScript.setter
    def onDeactivateScript(self, val):
        self.set("onDeactivateScript", val)
