from typing import TYPE_CHECKING, Callable, Any
import logging
from enum import IntEnum
from dataclasses import dataclass
from collections import deque
from contextlib import contextmanager
from weakref import WeakKeyDictionary
from lxml import etree as ET

if TYPE_CHECKING:
    from .tagfile import Tagfile


class MutationType(IntEnum):
    ATTRIBUTE = 0
    TEXT = 1
    STRUCTURE = 2


@dataclass(slots=True)
class UndoAction:
    id: int
    action_type: MutationType
    undo_fn: Callable
    redo_fn: Callable


class UndoStack:
    def __init__(self, max_size: int = 50):
        self._undos: deque[UndoAction] = deque(maxlen=max_size)
        self._redos: deque[UndoAction] = deque(maxlen=max_size)
        self._action_id = 0
        self._max_size = max_size
        self._transaction_buffer: list[UndoAction] = None

    def record(self, action_type: MutationType, undo_fn: Callable, redo_fn: Callable):
        if self._transaction_buffer is not None:
            # Inside a transaction - buffer the operation
            self._transaction_buffer.append(
                UndoAction(self._action_id, action_type, undo_fn, redo_fn)
            )
        else:
            # Normal operation - record immediately
            self._undos.append(
                UndoAction(self._action_id, action_type, undo_fn, redo_fn)
            )
            self._redos.clear()
            self._action_id += 1

    @contextmanager
    def transaction(self):
        """
        Group multiple mutations into a single undo/redo action.

        Usage:
            with undo_stack.transaction():
                element.set("a", "1")
                element.set("b", "2")
                element.append(child)
            # All three operations undo/redo together
        """
        if self._transaction_buffer is not None:
            # Nested transactions - just continue with current buffer
            yield
            return

        # Start new transaction
        self._transaction_buffer = []
        try:
            yield
        finally:
            # Commit transaction
            operations = self._transaction_buffer
            self._transaction_buffer = None

            if operations:
                action_type = max(a.action_type for a in operations)

                # Combine all operations into single undo/redo
                def combined_undo():
                    # Execute undos in reverse order
                    for action in reversed(operations):
                        action.undo_fn()

                def combined_redo():
                    # Execute redos in forward order
                    for action in operations:
                        action.redo_fn()

                self.record(action_type, combined_undo, combined_redo)

    def top_undo_id(self) -> int:
        if not self._undos:
            return -1

        # Implementing this for redo is not useful I think
        return self._undos[-1].id

    def top_undo_type(self) -> MutationType:
        if not self._undos:
            return None

        return self._undos[-1].action_type

    def can_undo(self) -> bool:
        return bool(self._undos)

    def can_redo(self) -> bool:
        return bool(self._redos)

    def undo(self) -> MutationType:
        if not self._undos:
            return None

        action = self._undos.pop()
        action.undo_fn()
        self._redos.append(action)
        return action.action_type

    def redo(self) -> MutationType:
        if not self._redos:
            return None

        action = self._redos.pop()
        action.redo_fn()
        self._undos.append(action)
        return action.action_type

    def clear(self):
        self._undos.clear()
        self._redos.clear()


class UndoAttrib(dict):
    """Wrapper around element.attrib that tracks mutations."""

    def __init__(self, element: "HkbXmlElement", attrib_dict):
        self._element = element
        self._attrib = attrib_dict
        super().__init__(attrib_dict)

    def __setitem__(self, key, value):
        undo_stack = self._element.undo_stack
        if undo_stack is not None:
            old_value = self._attrib.get(key)

            def undo():
                if old_value is None:
                    self._attrib.pop(key, None)
                else:
                    self._attrib[key] = old_value

            def redo():
                self._attrib[key] = value

            undo_stack.record(MutationType.ATTRIBUTE, undo, redo)

        self._attrib[key] = value
        super().__setitem__(key, value)

    def __delitem__(self, key: str):
        undo_stack = self._element.undo_stack
        if undo_stack is not None:
            old_value = self._attrib.get(key)

            if old_value is not None:
                undo_stack.record(
                    MutationType.ATTRIBUTE, 
                    undo_fn=lambda: self._attrib.__setitem__(key, old_value),
                    redo_fn=lambda: self._attrib.pop(key, None),
                )

        self._attrib.pop(key, None)
        super().__delitem__(key)

    def __getitem__(self, key: str):
        return self._attrib[key]

    def __contains__(self, key):
        return key in self._attrib

    def __iter__(self):
        return iter(self._attrib)

    def __len__(self):
        return len(self._attrib)

    def get(self, key, default=None):
        return self._attrib.get(key, default)

    def keys(self):
        return self._attrib.keys()

    def values(self):
        return self._attrib.values()

    def items(self):
        return self._attrib.items()

    def pop(self, key: str, default: Any):
        undo_stack = self._element.undo_stack
        if undo_stack is not None:
            old_value = self._attrib.get(key)

            if old_value is not None:
                undo_stack.record(
                    MutationType.ATTRIBUTE, 
                    undo_fn=lambda: self._attrib.__setitem__(key, old_value),
                    redo_fn=lambda: self._attrib.pop(key, None),
                )

        result = self._attrib.pop(key, default)
        if key in self:
            super().__delitem__(key)
        return result

    def update(self, *args, **kwargs):
        updates = dict(*args, **kwargs)

        undo_stack = self._element.undo_stack
        if undo_stack is not None and updates:
            old_values = {k: self._attrib.get(k) for k in updates}

            def undo():
                for key, old_val in old_values.items():
                    if old_val is None:
                        self._attrib.pop(key, None)
                    else:
                        self._attrib[key] = old_val

            def redo():
                self._attrib.update(updates)

            undo_stack.record(MutationType.ATTRIBUTE, undo, redo)

        self._attrib.update(updates)
        super().update(updates)

    def clear(self):
        undo_stack = self._element.undo_stack
        if undo_stack is not None:
            old_attrib = dict(self._attrib)

            if old_attrib:
                undo_stack.record(
                    MutationType.ATTRIBUTE, 
                    undo_fn=lambda: self._attrib.update(old_attrib),
                    redo_fn=lambda: self._attrib.clear(),
                )

        self._attrib.clear()
        super().clear()

    def setdefault(self, key: str, default: Any = None):
        if key not in self._attrib:
            undo_stack = self._element.undo_stack
            if undo_stack is not None:
                undo_stack.record(
                    MutationType.ATTRIBUTE, 
                    undo_fn=lambda: self._attrib.pop(key, None),
                    redo_fn=lambda: self._attrib.__setitem__(key, default),
                )
            self._attrib[key] = default
            super().__setitem__(key, default)

        return self._attrib[key]


class HkbXmlElement(ET.ElementBase):
    """Custom lxml Element that tracks mutations for undo/redo."""

    _undo_stacks: WeakKeyDictionary["HkbXmlElement", UndoStack] = WeakKeyDictionary()

    # NOTE custom element classes should never have a constructor!

    @classmethod
    def new(cls, tag: str, **kwargs) -> "HkbXmlElement":
        # ET.Element won't know about our custom class, and calling 
        # HkbXmlElement("tag") directly is wrong and won't work
        parser = _get_xml_parser()
        return parser.makeelement(tag, **kwargs)

    @property
    def undo_stack(self) -> UndoStack:
        root = self.getroottree().getroot()
        return HkbXmlElement._undo_stacks.get(root)

    @property
    def attrib(self):
        """Incurs slight overhead as it wraps the actual element's attrib dict in a class that tracks mutations. Consider using get and set instead. It is discouraged to keep references to the returned dict. Accessing the same dict instance before and after an undo/redo operation may result in undefined behavior."""
        return UndoAttrib(self, super(HkbXmlElement, self).attrib)

    def _check_move(self, el):
        if el.getparent() is not None:
            attrs = " ".join(f"{k}={v}" for k, v in el.attrib.items())
            logging.getLogger().warning(
                f"Element is about to be moved, this might be a bug: <{el.tag} {attrs}>"
            )

    @property
    def text(self) -> str:
        return super(HkbXmlElement, self).text

    @text.setter
    def text(self, value: str):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_text = self.text

            def undo():
                super(HkbXmlElement, __class__).text.__set__(self, old_text)

            def redo():
                super(HkbXmlElement, __class__).text.__set__(self, value)

            undo_stack.record(MutationType.TEXT, undo, redo)

        # lxml is implemented in C and uses a "getset_descriptor" which works slightly different
        super(HkbXmlElement, __class__).text.__set__(self, value)

    @property
    def tail(self) -> str:
        return super(HkbXmlElement, self).tail

    @tail.setter
    def tail(self, value: str):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_tail = self.tail

            def undo():
                super(HkbXmlElement, __class__).text.__set__(self, old_tail)

            def redo():
                super(HkbXmlElement, __class__).text.__set__(self, value)

            undo_stack.record(MutationType.TEXT, undo, redo)

        super(HkbXmlElement, __class__).text.__set__(self, value)

    def set(self, key: str, value: str):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_value = self.get(key)

            def undo():
                if old_value is None:
                    self.attrib.pop(key, None)
                else:
                    super(HkbXmlElement, self).set(key, old_value)

            def redo():
                super(HkbXmlElement, self).set(key, value)

            undo_stack.record(MutationType.ATTRIBUTE, undo, redo)

        super(HkbXmlElement, self).set(key, value)

    def __setitem__(self, key: str, value: str):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_value = self.get(key)

            def undo():
                if old_value is None:
                    self.attrib.pop(key, None)
                else:
                    super(HkbXmlElement, self).set(key, old_value)

            def redo():
                super(HkbXmlElement, self).set(key, value)

            undo_stack.record(MutationType.ATTRIBUTE, undo, redo)

        super(HkbXmlElement, self).__setitem__(key, value)

    def __delitem__(self, key: str):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_value = self.get(key)

            if old_value is not None:
                undo_stack.record(
                    MutationType.ATTRIBUTE,
                    undo_fn=lambda: super(HkbXmlElement, self).set(key, old_value),
                    redo_fn=lambda: self.attrib.pop(key, None),
                )

        super(HkbXmlElement, self).__delitem__(key)

    def append(self, child) -> None:
        self._check_move(child)
        undo_stack = self.undo_stack
        if undo_stack is not None:
            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: super(HkbXmlElement, self).remove(child),
                redo_fn=lambda: super(HkbXmlElement, self).append(child),
            )

        super(HkbXmlElement, self).append(child)

    def remove(self, child) -> None:
        undo_stack = self.undo_stack
        if undo_stack is not None:
            index = list(self).index(child)
            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: super(HkbXmlElement, self).insert(index, child),
                redo_fn=lambda: super(HkbXmlElement, self).remove(child),
            )

        super(HkbXmlElement, self).remove(child)

    def insert(self, index: int, child) -> None:
        self._check_move(child)
        undo_stack = self.undo_stack
        if undo_stack is not None:
            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: super(HkbXmlElement, self).remove(child),
                redo_fn=lambda: super(HkbXmlElement, self).insert(index, child),
            )

        super(HkbXmlElement, self).insert(index, child)

    def clear(self):
        undo_stack = self.undo_stack
        if undo_stack is not None:
            old_attrib = dict(self.attrib)
            old_text = self.text
            old_tail = self.tail
            old_children = list(self)

            def undo():
                super(HkbXmlElement, self).clear()
                for key, val in old_attrib.items():
                    super(HkbXmlElement, self).set(key, val)
                type(self).text.fset(self, old_text)
                type(self).tail.fset(self, old_tail)
                for child in old_children:
                    super(HkbXmlElement, self).append(child)

            def redo():
                super(HkbXmlElement, self).clear()

            undo_stack.record(MutationType.STRUCTURE, undo, redo)

        super(HkbXmlElement, self).clear()

    def extend(self, elements: list):
        for e in elements:
            self._check_move(e)

        undo_stack = self.undo_stack
        if undo_stack is not None:
            elements_list = list(elements)

            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: [
                    super(HkbXmlElement, self).remove(e) for e in elements_list
                ],
                redo_fn=lambda: super(HkbXmlElement, self).extend(elements_list),
            )

        super(HkbXmlElement, self).extend(elements)

    def replace(self, old_element, new_element):
        self._check_move(new_element)
        undo_stack = self.undo_stack
        if undo_stack is not None:
            index = list(self).index(old_element)

            def undo():
                super(HkbXmlElement, self).remove(new_element)
                super(HkbXmlElement, self).insert(index, old_element)

            def redo():
                super(HkbXmlElement, self).remove(old_element)
                super(HkbXmlElement, self).insert(index, new_element)

            undo_stack.record(MutationType.STRUCTURE, undo, redo)

        super(HkbXmlElement, self).replace(old_element, new_element)

    def addnext(self, element):
        self._check_move(element)
        undo_stack = self.undo_stack
        if undo_stack is not None:
            parent = self.getparent()

            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: parent.remove(element) if parent is not None else None,
                redo_fn=lambda: super(HkbXmlElement, self).addnext(element),
            )

        super(HkbXmlElement, self).addnext(element)

    def addprevious(self, element):
        self._check_move(element)
        undo_stack = self.undo_stack
        if undo_stack is not None:
            parent = self.getparent()

            undo_stack.record(
                MutationType.STRUCTURE,
                undo_fn=lambda: parent.remove(element) if parent is not None else None,
                redo_fn=lambda: super(HkbXmlElement, self).addprevious(element),
            )

        super(HkbXmlElement, self).addprevious(element)


def _get_xml_parser() -> ET.XMLParser:
    lookup = ET.ElementDefaultClassLookup(element=HkbXmlElement)

    # lxml keeps comments, which affect subelement counts and iterations.
    parser = ET.XMLParser(remove_comments=True)
    parser.set_element_class_lookup(lookup)

    return parser


def make_element(tag: str, **kwargs) -> HkbXmlElement:
    return HkbXmlElement.new(tag, **kwargs)


def make_subelement(parent: ET.Element, tag: str, **kwargs) -> HkbXmlElement:
    child = HkbXmlElement.new(tag, **kwargs)
    parent.append(child)
    return child


def xml_from_str(xml: str, undo: bool = False) -> HkbXmlElement:
    tree = ET.fromstring(xml, parser=_get_xml_parser())
    if hasattr(tree, "getroot"):
        root = tree.getroot()
    else:
        root = tree.getroottree().getroot()

    if undo:
        HkbXmlElement._undo_stacks[root] = UndoStack()
    return root


def xml_from_file(path: str, undo: bool = False) -> HkbXmlElement:
    tree = ET.parse(path, parser=_get_xml_parser())
    root = tree.getroot()
    if undo:
        HkbXmlElement._undo_stacks[root] = UndoStack()
    return root


def xml_to_str(xml: ET.Element) -> str:
    return ET.tostring(xml, pretty_print=True, encoding="unicode")


def add_type_comments(root: ET.Element, tagfile: "Tagfile") -> None:
    for el in root.findall(".//object"):
        oid = el.get("id")
        type_name = tagfile.objects[oid].type_name
        el.insert(0, ET.Comment(type_name))
