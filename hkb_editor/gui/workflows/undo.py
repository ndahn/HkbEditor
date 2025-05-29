from typing import Any, Callable
from collections import deque
import itertools
from contextlib import contextmanager

from hkb_editor.hkb.hkb_types import XmlValueHandler, HkbArray, HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior


class UndoAction:
    def undo(self) -> None:
        raise NotImplementedError()

    def redo(self) -> None:
        raise NotImplementedError()


class ComboAction(UndoAction):
    def __init__(self, *actions: UndoAction):
        self.actions = list(actions)

    def add(self, action: UndoAction) -> None:
        self.actions.append(action)

    def undo(self):
        for a in reversed(self.actions):
            a.undo()

    def redo(self):
        for a in self.actions:
            a.redo()

    def __str__(self):
        return str([str(a) for a in self.actions])


class UpdateValueAction(UndoAction):
    def __init__(self, handler: XmlValueHandler, old_value: Any, new_value: Any):
        super().__init__()
        self.handler = handler
        self.old_value = old_value
        self.new_value = new_value

    def undo(self):
        self.handler.set_value(self.old_value)

    def redo(self):
        self.handler.set_value(self.new_value)

    def __str__(self):
        return f"{self.old_value} -> {self.new_value}"


class UpdateArrayItem(UndoAction):
    def __init__(
        self,
        array: HkbArray,
        index: int,
        old_value: XmlValueHandler,
        new_value: XmlValueHandler,
    ):
        super().__init__()
        self.array = array
        self.index = index
        self.old_value = old_value
        self.new_value = new_value

    def undo(self):
        if self.old_value is None:
            # A new value was inserted, remove it again
            del self.array[self.index]
        elif self.new_value is None:
            # A value was removed, insert it again
            self.array.insert(self.index, self.old_value)
        else:
            self.array[self.index].set_value(self.old_value)

    def redo(self):
        if self.new_value is None:
            # A value was removed, do it again
            del self.array[self.index]
        elif self.old_value is None:
            # A new value was placed, do it again
            self.array.insert(self.index, self.new_value)
        else:
            self.array[self.index].set_value(self.new_value)

    def __str__(self):
        return f"[{self.index}]: {self.old_value} -> {self.new_value}"


class AddBehaviorObjectAction(UndoAction):
    def __init__(self, behavior: HavokBehavior, object: HkbRecord):
        super().__init__()
        self.behavior = behavior
        self.object = object

    def undo(self):
        self.behavior.remove_object(self.object)

    def redo(self):
        self.behavior.add_object(self.object)

    def __str__(self):
        return f"new object {self.object.object_id}"


class CustomUndoAction(UndoAction):
    def __init__(self, undo_func: Callable, redo_func: Callable):
        super().__init__()
        self.undo_func = undo_func
        self.redo_func = redo_func

    def undo(self):
        self.undo_func()

    def redo(self):
        self.redo_func()

    def __str__(self):
        return f"call {self.undo_func} <-> {self.redo_func}"


class UndoManager:
    def __init__(self, maxlen: int = 100):
        self.history: deque[UndoAction] = deque(maxlen=maxlen)
        self.index = -1
        self._combining: ComboAction = None

    def clear(self) -> None:
        self.history = deque(maxlen=self.history.maxlen)
        self.index = -1

    def top(self) -> None:
        if not self.history:
            return None

        return self.history[self.index]

    def can_undo(self) -> None:
        return self.history and self.index >= 0

    def can_redo(self) -> None:
        return self.history and self.index + 1 < len(self.history)

    def undo(self) -> None:
        if not self.can_undo():
            raise ValueError("Nothing to undo")

        # Index points at the current action to be undone
        action = self.history[self.index]
        action.undo()
        self.index -= 1

    def redo(self) -> None:
        if not self.can_redo():
            raise ValueError("Nothing to redo")

        if self.index >= len(self.history):
            return

        # Index points at the positoin before the action to be redone
        action = self.history[self.index + 1]
        action.redo()
        self.index += 1

    def _on_action(self, action: UndoAction) -> None:
        if self._combining:
            self._combining.add(action)
        else:
            # Remove subsequent actions that could have been redone until now. Deque doesn't
            # support slice notation it seems
            self.history = deque(
                itertools.islice(self.history, 0, self.index + 1), self.history.maxlen
            )
            self.history.append(action)
            self.index += 1

    def on_update_value(
        self, handler: XmlValueHandler, old_value: Any, new_value: Any
    ) -> None:
        self._on_action(UpdateValueAction(handler, old_value, new_value))

    def on_update_array_item(
        self, array: HkbArray, index: int, old_value: Any, new_value: Any
    ) -> None:
        self._on_action(UpdateArrayItem(array, index, old_value, new_value))

    def on_add_behavior_object(
        self, behavior: HavokBehavior, object: HkbRecord
    ) -> None:
        self._on_action(AddBehaviorObjectAction(behavior, object))

    def on_complex_action(
        self, undo_func: Callable, redo_func: Callable
    ) -> None:
        self._on_action(CustomUndoAction(undo_func, redo_func))

    @contextmanager
    def combine(self):
        if self._combining:
            raise ValueError(
                "Cannot assemble a combo action with another one already open"
            )

        try:
            self._combining = ComboAction()
            yield
        finally:
            action = self._combining
            self._combining = None

            if action.actions:
                self._on_action(self._combining)


undo_manager = UndoManager(100)
