from enum import IntEnum

from .new_base import HkbObject, HkbReference, HkbArray


class HkbStateMachine(HkbObject):
    class StartStateMode(IntEnum):
        DEFAULT = 0
        # TODO add remaining values

    class SelfTransitionMode(IntEnum):
        NO_TRANSITION = 0
        CONTINUE = 1
        # TODO add remaining values

    @classmethod
    def create(
        cls,
        id: str,
        eventToSendWhenStateOrTransitionChanges: dict = None,  # hkbEvent
        startStateIdSelector: HkbReference = "",
        startStateId: int = -1,
        returnToPreviousStateEventId: int = -1,
        randomTransitionEventId: int = -1,
        transitionToNextHigherStateEventId: int = -1,
        transitionToNextLowerStateEventId: int = -1,
        syncVariableIndex: int = -1,
        wrapAroundStateId: bool = False,
        maxSimultaneousTransitions: int = 0,
        startStateMode: StartStateMode = StartStateMode.DEFAULT,
        selfTransitionMode: SelfTransitionMode = SelfTransitionMode.NO_TRANSITION,
        states: HkbArray = [],  # [StateInfo]
        wildcardTransitions: HkbArray = [],  # TransitionInfoArray
    ):
        return super().create(
            id,
            "type100",
            eventToSendWhenStateOrTransitionChanges or {},
            startStateIdSelector,
            startStateId,
            returnToPreviousStateEventId,
            randomTransitionEventId,
            transitionToNextHigherStateEventId,
            transitionToNextLowerStateEventId,
            syncVariableIndex,
            wrapAroundStateId,
            maxSimultaneousTransitions,
            startStateMode,
            selfTransitionMode,
            states or HkbArray("type113"),
            wildcardTransitions or HkbArray("type123"),
        )

    @property
    def eventToSendWhenStateOrTransitionChanges(self):
        return self.get("eventToSendWhenStateOrTransitionChanges")

    @property
    def startStateIdSelector(self):
        return self.get("startStateIdSelector")

    @property
    def startStateId(self):
        return self.get("startStateId")

    @property
    def returnToPreviousStateEventId(self):
        return self.get("returnToPreviousStateEventId")

    @property
    def randomTransitionEventId(self):
        return self.get("randomTransitionEventId")

    @property
    def transitionToNextHigherStateEventId(self):
        return self.get("transitionToNextHigherStateEventId")

    @property
    def transitionToNextLowerStateEventId(self):
        return self.get("transitionToNextLowerStateEventId")

    @property
    def syncVariableIndex(self):
        return self.get("syncVariableIndex")

    @property
    def wrapAroundStateId(self):
        return self.get("wrapAroundStateId")

    @property
    def maxSimultaneousTransitions(self):
        return self.get("maxSimultaneousTransitions")

    @property
    def startStateMode(self):
        return self.get("startStateMode")

    @property
    def selfTransitionMode(self):
        return self.get("selfTransitionMode")

    @property
    def states(self):
        return self.get("states")

    @property
    def wildcardTransitions(self):
        return self.get("wildcardTransitions")

    @eventToSendWhenStateOrTransitionChanges.setter
    def eventToSendWhenStateOrTransitionChanges(self, val):
        self.set("eventToSendWhenStateOrTransitionChanges", val)

    @startStateIdSelector.setter
    def startStateIdSelector(self, val):
        self.set("startStateIdSelector", val)

    @startStateId.setter
    def startStateId(self, val):
        self.set("startStateId", val)

    @returnToPreviousStateEventId.setter
    def returnToPreviousStateEventId(self, val):
        self.set("returnToPreviousStateEventId", val)

    @randomTransitionEventId.setter
    def randomTransitionEventId(self, val):
        self.set("randomTransitionEventId", val)

    @transitionToNextHigherStateEventId.setter
    def transitionToNextHigherStateEventId(self, val):
        self.set("transitionToNextHigherStateEventId", val)

    @transitionToNextLowerStateEventId.setter
    def transitionToNextLowerStateEventId(self, val):
        self.set("transitionToNextLowerStateEventId", val)

    @syncVariableIndex.setter
    def syncVariableIndex(self, val):
        self.set("syncVariableIndex", val)

    @wrapAroundStateId.setter
    def wrapAroundStateId(self, val):
        self.set("wrapAroundStateId", val)

    @maxSimultaneousTransitions.setter
    def maxSimultaneousTransitions(self, val):
        self.set("maxSimultaneousTransitions", val)

    @startStateMode.setter
    def startStateMode(self, val):
        self.set("startStateMode", val)

    @selfTransitionMode.setter
    def selfTransitionMode(self, val):
        self.set("selfTransitionMode", val)

    @states.setter
    def states(self, val):
        self.set("states", val)

    @wildcardTransitions.setter
    def wildcardTransitions(self, val):
        self.set("wildcardTransitions", val)
