from typing import Any, Callable
from types import MethodType
from collections import deque
import itertools
import logging
from functools import wraps
from contextlib import contextmanager, ExitStack

from hkb_editor.hkb.hkb_types import XmlValueHandler, HkbArray, HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior, VariableType
from hkb_editor.hkb.tagfile import Tagfile


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
        logger = logging.getLogger()
        for a in reversed(self.actions):
            try:
                a.undo()
            except Exception as e:
                # The show must go on!
                logger.warning(f"Undo partially failed: {e}", exc_info=True)

    def redo(self):
        for a in self.actions:
            a.redo()

    def __str__(self):
        return f"{len(self.actions)} actions"


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


class skip_if_guarded:
    """Decorator that skips call when the first argument has `_is_guarded` set.
    For methods, `self._is_guarded` is checked. The original callable is
    available as `._internal` (bound for methods)."""

    def __init__(self, func: Callable):
        self.func = func
        self._internal = func  # unbound for free functions
        wraps(func)(self)

    # Class methods will call __get__ to bind the function instance
    def __get__(self, instance, owner):
        if instance is None:
            return self

        @wraps(self.func)
        def bound(*args, **kwargs):
            if args and getattr(args[0], "_is_guarded", False):
                return
            return self.func(instance, *args, **kwargs)

        # Bound original so that it can still be called directly
        bound._internal = MethodType(self.func, instance)
        return bound

    # Used for free functions
    def __call__(self, *args, **kwargs):
        if args and getattr(args[0], "_is_guarded", False):
            return
        return self.func(*args, **kwargs)


class UndoManager:
    def __init__(self, maxlen: int = 100):
        self.history: deque[UndoAction] = deque(maxlen=maxlen)
        self.index = -1
        self._combo_stack: list[ComboAction] = []

    def clear(self) -> None:
        self.history = deque(maxlen=self.history.maxlen)
        self.index = -1

    def top(self) -> UndoAction:
        if not self.history:
            return None

        return self.history[self.index]

    def can_undo(self) -> None:
        return self.history and self.index >= 0

    def can_redo(self) -> None:
        return self.history and self.index + 1 < len(self.history)

    def undo(self) -> UndoAction:
        if not self.can_undo():
            raise ValueError("Nothing to undo")

        # Index points at the current action to be undone
        action = self.history[self.index]
        action.undo()
        self.index -= 1

        return action

    def redo(self) -> UndoAction:
        if not self.can_redo():
            raise ValueError("Nothing to redo")

        if self.index >= len(self.history):
            return

        # Index points at the positoin before the action to be redone
        action = self.history[self.index + 1]
        action.redo()
        self.index += 1

        return action

    def _on_action(self, action: UndoAction) -> None:
        if self._combo_stack:
            self._combo_stack[-1].add(action)
        else:
            # Remove subsequent actions that could have been redone until now. Deque doesn't
            # support slice notation it seems
            self.history = deque(
                itertools.islice(self.history, 0, self.index + 1), self.history.maxlen
            )
            self.history.append(action)
            self.index += 1

    def on_complex_action(self, undo_func: Callable, redo_func: Callable) -> None:
        self._on_action(CustomUndoAction(undo_func, redo_func))

    @skip_if_guarded
    def on_update_value(
        self, handler: XmlValueHandler, old_value: Any, new_value: Any
    ) -> None:
        self._on_action(UpdateValueAction(handler, old_value, new_value))

    @skip_if_guarded
    def on_update_array_item(
        self, array: HkbArray, index: int, old_value: Any, new_value: Any
    ) -> None:
        self._on_action(UpdateArrayItem(array, index, old_value, new_value))

    @skip_if_guarded
    def on_create_object(
        self,
        tagfile: Tagfile,
        new_object: HkbRecord,
    ) -> None:
        self.on_complex_action(
            lambda obj=new_object: tagfile.remove_object(obj.object_id),
            lambda obj=new_object: tagfile.add_object(obj),
        )

    @skip_if_guarded
    def on_delete_object(
        self,
        tagfile: Tagfile,
        obj: HkbRecord,
    ) -> None:
        self.on_complex_action(
            lambda obj=obj: tagfile.add_object(obj),
            lambda object_id=obj.object_id: tagfile.remove_object(object_id),
        )

    @skip_if_guarded
    def on_create_variable(
        self,
        behavior: HavokBehavior,
        variable_info: tuple[str, int, int, int],
        idx: int = -1,
    ) -> None:
        self.on_complex_action(
            lambda i=idx: behavior.delete_variable(i),
            lambda i=idx, v=variable_info: behavior.create_variable(*v, i),
        )

    @skip_if_guarded
    def on_update_variable(
        self,
        behavior: HavokBehavior,
        idx: int,
        old_value: tuple[str, int, int, int],
        new_value: tuple[str, int, int, int],
    ) -> None:
        # Easier than updating each field individually
        def local_update(idx: int, val: tuple):
            behavior.delete_variable(idx)
            behavior.create_variable(*val, idx=idx)

        self.on_complex_action(
            lambda i=idx, v=old_value: local_update(i, v),
            lambda i=idx, v=new_value: local_update(i, v),
        )

    @skip_if_guarded
    def on_delete_variable(
        self,
        behavior: HavokBehavior,
        idx: int,
    ) -> None:
        old_value = behavior.get_variable(idx).astuple()
        undo_manager.on_complex_action(
            lambda i=idx: behavior.delete_variable(i),
            lambda i=idx, v=old_value: behavior.create_variable(*v, i),
        )

    @skip_if_guarded
    def on_create_event(
        self, behavior: HavokBehavior, event: str, idx: int = -1
    ) -> None:
        self.on_complex_action(
            lambda i=idx: behavior.delete_event(i),
            lambda i=idx, v=event: behavior.create_event(v, i),
        )

    @skip_if_guarded
    def on_update_event(
        self,
        behavior: HavokBehavior,
        idx: int,
        old_value: str,
        new_value: str,
    ) -> None:
        self.on_complex_action(
            lambda i=idx, v=old_value: behavior.rename_event(i, v),
            lambda i=idx, v=new_value: behavior.rename_event(i, v),
        )

    @skip_if_guarded
    def on_delete_event(
        self,
        behavior: HavokBehavior,
        idx: int,
    ) -> None:
        old_value = behavior.get_event(idx)
        undo_manager.on_complex_action(
            lambda i=idx: behavior.delete_event(i),
            lambda i=idx, v=old_value: behavior.create_event(v, i),
        )

    @skip_if_guarded
    def on_create_animation(
        self, behavior: HavokBehavior, animation: str, idx: int = -1
    ) -> None:
        self.on_complex_action(
            lambda i=idx: behavior.delete_animation(i),
            lambda i=idx, v=animation: behavior.create_animation(v, i),
        )

    @skip_if_guarded
    def on_update_animation(
        self,
        behavior: HavokBehavior,
        idx: int,
        old_value: str,
        new_value: str,
    ) -> None:
        self.on_complex_action(
            lambda i=idx, v=old_value: behavior.rename_animation(i, v),
            lambda i=idx, v=new_value: behavior.rename_animation(i, v),
        )

    @skip_if_guarded
    def on_delete_animation(
        self,
        behavior: HavokBehavior,
        idx: int,
    ) -> None:
        old_value = behavior.get_animation(idx)
        undo_manager.on_complex_action(
            lambda i=idx: behavior.delete_animation(i),
            lambda i=idx, v=old_value: behavior.create_animation(v, i),
        )

    @contextmanager
    def combine(self):
        try:
            self._combo_stack.append(ComboAction())
            yield
        finally:
            action = self._combo_stack.pop()
            if action.actions:
                self._on_action(action)

    @contextmanager
    def guard(self, *objects: Tagfile | XmlValueHandler, combine: bool = True):
        """Track modifications of the passed object while this context exists.

        Parameters
        ----------
        objects : Tagfile | XmlValueHandler
            Objects to track. It is possible to circumvent tracking with e.g. 
            setattr, but this is of course frowned on.
        combine : bool, optional
            If true, any tracked actions within this context will be combined 
            into one single undo action.
        """
        def get_contexts_for(obj: Any) -> list:
            stack = []

            if isinstance(obj, Tagfile):
                stack.append(lambda: self._patch_tagfile(obj))

                if isinstance(obj, HavokBehavior):
                    stack.append(lambda: self._patch_behavior(obj))

            elif isinstance(obj, XmlValueHandler):
                stack.append(lambda: self._patch_xmlvaluehandler(obj))

                if isinstance(obj, HkbArray):
                    stack.append(lambda: self._patch_hkbarray(obj))

                elif isinstance(obj, HkbRecord):
                    stack.append(lambda: self._patch_hkbrecord(obj))

            return stack

        try:
            contexts = []

            for obj in objects:
                contexts.extend(get_contexts_for(obj))

            if combine:
                contexts.append(self.combine)

            # Combine all of our monkey patch context managers in one stack
            with ExitStack() as stack:
                # If the object is guarded our manual functions would result in
                # duplicate undo actions
                for obj in objects:
                    obj._is_guarded = True

                for ctx in contexts:
                    stack.enter_context(ctx())

                del contexts
                yield
        finally:
            for obj in objects:
                try:
                    delattr(obj, "_is_guarded")
                except AttributeError:
                    pass

    @contextmanager
    def _patch_tagfile(self, tagfile: Tagfile):
        add_object_original = tagfile.add_object
        remove_object_original = tagfile.remove_object
        
        def monkey_add_object(record: HkbRecord, id: str = None) -> str:
            result = add_object_original(record, id)
            self.on_create_object._internal(tagfile, record)
            return result

        def monkey_remove_object(id: str) -> HkbRecord:
            result = remove_object_original(id)
            self.on_delete_object._internal(tagfile, result)
            return result

        try:
            # Apply patches
            tagfile.add_object = monkey_add_object
            tagfile.remove_object = monkey_remove_object
            
            yield
        finally:
            # Restore original methods
            tagfile.add_object = add_object_original
            tagfile.remove_object = remove_object_original

    @contextmanager
    def _patch_behavior(self, behavior: HavokBehavior):
        create_event_original = behavior.create_event
        delete_event_original = behavior.delete_event
        create_variable_original = behavior.create_variable
        delete_variable_original = behavior.delete_variable
        create_animation_original = behavior.create_animation
        delete_animation_original = behavior.delete_animation
        
        def monkey_create_event(event_name: str, idx: int = -1) -> int:
            result = create_event_original(event_name, idx)
            self.on_create_event._internal(behavior, event_name, idx)
            return result
        
        def monkey_delete_event(idx: int) -> None:
            delete_event_original(idx)
            self.on_delete_event._internal(behavior, idx)
        
        def monkey_create_variable(
            variable_name: str,
            var_type: VariableType = VariableType.INT32,
            range_min: int = 0,
            range_max: int = 0,
            default: Any = 0,
            idx: int = None,
        ) -> int:
            result = create_variable_original(variable_name, var_type, range_min, range_max, default, idx)
            var = behavior.get_variable(result)
            self.on_create_variable._internal(behavior, var.astuple(), result)
            return result
        
        def monkey_delete_variable(idx: int) -> None:
            delete_variable_original(idx)
            self.on_delete_variable._internal(behavior, idx)
        
        def monkey_create_animation(animation_name: str, idx: int = -1) -> int:
            result = create_animation_original(animation_name, idx)
            self.on_create_animation._internal(behavior, animation_name, idx)
            return result
        
        def monkey_delete_animation(idx: int) -> None:
            delete_animation_original(idx)
            self.on_delete_animation._internal(behavior, idx)
        
        try:
            # Apply patches
            behavior.create_event = monkey_create_event
            behavior.delete_event = monkey_delete_event
            behavior.create_variable = monkey_create_variable
            behavior.delete_variable = monkey_delete_variable
            behavior.create_animation = monkey_create_animation
            behavior.delete_animation = monkey_delete_animation
            
            yield
        finally:
            # Restore original methods
            behavior.create_event = create_event_original
            behavior.delete_event = delete_event_original
            behavior.create_variable = create_variable_original
            behavior.delete_variable = delete_variable_original
            behavior.create_animation = create_animation_original
            behavior.delete_animation = delete_animation_original

    @contextmanager
    def _patch_xmlvaluehandler(self, handler: XmlValueHandler):
        set_value_original = handler.set_value

        def monkey_set_value(value: Any) -> None:
            old_value = handler.get_value()
            set_value_original(value)
            self.on_update_value._internal(handler, old_value, value)

        try:
            # Apply patches
            handler.set_value = monkey_set_value
        finally:
            # Restore original methods
            handler.set_value = set_value_original

    @contextmanager
    def _patch_hkbarray(self, array: HkbArray):
        setattr_original = array.__setattr__
        setitem_original = array.__setitem__
        delitem_original = array.__delitem__
        append_original = array.append
        insert_original = array.insert
        pop_original = array.pop
        clear_original = array.clear

        # properties affect the class definition, but we only want to guard this 
        # single array instance
        def monkey_setattr(name: str, value: Any) -> None:
            if name == 'element_type_id':
                old_value = getattr(array, 'element_type_id')
                setattr_original(name, value)
                undo_manager.on_complex_action(
                    lambda: setattr(array, 'element_type_id', old_value),
                    lambda: setattr(array, 'element_type_id', value)
                )
            else:
                setattr_original(name, value)

        def monkey_setitem(index: int, value: Any) -> None:
            old_value = array[index]
            setitem_original(index, value)
            self.on_update_array_item._internal(array, index, old_value, value)

        def monkey_delitem(index: int) -> None:
            old_value = array[index]
            delitem_original(index)
            self.on_update_array_item._internal(array, index, old_value, None)

        def monkey_append(value: Any) -> None:
            append_original(value)
            self.on_update_array_item._internal(array, -1, None, value)

        def monkey_insert(index: int, value: Any) -> None:
            insert_original(index, value)
            self.on_complex_action(
                lambda: array.pop(index),
                lambda: array.insert(index, value),
            )

        def monkey_pop(index: int) -> Any:
            result = pop_original(index)
            self.on_update_array_item._internal(array, index, result, None)
            return result

        def monkey_clear():
            old_values = array.get_value()
            clear_original()
            self.on_complex_action(
                lambda: array.set_value(old_values),
                lambda: array.clear(),
            )

        try:
            # Apply patches
            array.__setattr__ = monkey_setattr
            array.__setitem__ = monkey_setitem
            array.__delitem__ = monkey_delitem
            array.append = monkey_append
            array.insert = monkey_insert
            array.pop = monkey_pop
            array.clear = monkey_clear

            yield
        finally:
            # Restore original methods
            array.__setattr__ = setattr_original
            array.__setitem__ = setitem_original
            array.__delitem__ = delitem_original
            array.append = append_original
            array.insert = insert_original
            array.pop = pop_original
            array.clear = clear_original

    @contextmanager
    def _patch_hkbrecord(self, record: HkbRecord):
        set_field_original = record.set_field
        setitem_original = record.__setitem__

        def monkey_set_field(path: str, value: XmlValueHandler | Any) -> None:
            old_value = record.get_field(path, resolve=True)
            set_field_original(path, value)
            self.on_complex_action(
                lambda: record.set_field(path, old_value),
                lambda: record.set_value(path, value)
            )

        def monkey_setitem(key: str, value: XmlValueHandler | Any) -> None:
            old_value = record[key]
            setitem_original(key, value)
            self.on_complex_action(
                lambda: record.__setitem__(key, old_value),
                lambda: record.__setitem__(key, value)
            )

        try:
            # Apply patches
            record.set_field = monkey_set_field
            record.__setitem__ = monkey_setitem

            yield
        finally:
            # Restore original methods
            record.set_field = set_field_original
            record.__setitem__ = setitem_original


undo_manager = UndoManager(100)
