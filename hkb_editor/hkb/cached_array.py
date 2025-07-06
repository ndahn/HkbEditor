from typing import Generic, TypeVar, Generator
from lxml import etree as ET

from .tagfile import Tagfile
from .hkb_types import XmlValueHandler, HkbArray


T = TypeVar("T")


class CachedArray(HkbArray, Generic[T]):
    @classmethod
    def wrap(cls, array: HkbArray) -> "CachedArray[T]":
        return cls(array.tagfile, array.element, array.type_id)

    def __init__(self, tagfile: Tagfile, element: ET._Element, type_id: str):
        super().__init__(tagfile, element, type_id)
        self._cache: list[T] = []
        self._rebuild_cache()

    def _rebuild_cache(self) -> None:
        self._cache = [
            super(CachedArray, self).__getitem__(i).get_value() 
            for i in range(self._count)
        ]

    def clear(self) -> None:
        super().clear()
        self._cache.clear()

    def get_value(self) -> list[T]:
        return list(self._cache)

    def set_value(
        self, values: list[XmlValueHandler | T], autowrap: bool = True
    ) -> None:
        super().set_value(values, autowrap)
        self._rebuild_cache()

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Generator[T, None, None]:
        yield from self._cache

    def __getitem__(self, index: int) -> T:
        return self._cache[index]

    def __setitem__(self, index: int, value: XmlValueHandler | T) -> None:
        super().__setitem__(index, value)
        self._cache[index] = self[index]

    def __delitem__(self, index: int) -> None:
        super().__delitem__(index)
        del self._cache[index]

    def index(self, value: XmlValueHandler | T) -> int:
        if isinstance(value, XmlValueHandler):
            if value.type_id != self.element_type_id:
                raise ValueError(
                    f"Non-matching value type {value.type_id} (should be {self.element_type_id})"
                )

            value = value.get_value()

        return self._cache.index(value)

    def append(self, value: XmlValueHandler | T) -> None:
        super().append(value)
        self._cache.append(self[-1])

    def insert(self, index: int, value: XmlValueHandler | T) -> None:
        super().insert(index, value)
        self._cache.insert(index, self[-1])

    def pop(self, index: int) -> T:
        super().__delitem__(index)
        return self._cache.pop(index)
