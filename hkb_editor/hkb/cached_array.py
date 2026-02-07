from typing import Generic, TypeVar, Generator

from .hkb_types import XmlValueHandler, HkbArray


T = TypeVar("T")


class CachedArray(Generic[T]):
    def __init__(self, array: HkbArray):
        super().__init__()
        self.array = array
        self._cache: list[T] = []
        self._rebuild_cache()

    def _rebuild_cache(self) -> None:
        self._cache = [x.get_value() for x in self.array]

    def clear(self) -> None:
        self.array.clear()
        self._cache.clear()

    def get_value(self) -> list[T]:
        return list(self._cache)

    def set_value(
        self, values: list[XmlValueHandler | T], autowrap: bool = True
    ) -> None:
        self.array.set_value(values, autowrap)
        self._rebuild_cache()

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Generator[T, None, None]:
        yield from self._cache

    def __getitem__(self, index: int) -> T:
        return self._cache[index]

    def __setitem__(self, index: int, value: XmlValueHandler | T) -> None:
        self.array[index].set_value(value)
        val = value.get_value() if isinstance(value, XmlValueHandler) else value
        self._cache[index] = val

    def __delitem__(self, index: int) -> None:
        del self.array[index]
        del self._cache[index]

    def index(self, value: XmlValueHandler | T) -> int:
        if isinstance(value, XmlValueHandler):
            if value.type_id != self.array.element_type_id:
                raise ValueError(
                    f"Non-matching value type {value.type_id} (should be {self.array.element_type_id})"
                )

            value = value.get_value()

        return self._cache.index(value)

    def append(self, value: XmlValueHandler | T) -> None:
        self.array.append(value)
        val = value.get_value() if isinstance(value, XmlValueHandler) else value
        self._cache.append(val)

    def insert(self, index: int, value: XmlValueHandler | T) -> None:
        self.array.insert(index, value)
        val = value.get_value() if isinstance(value, XmlValueHandler) else value
        self._cache.insert(index, val)

    def pop(self, index: int) -> T:
        del self.array[index]
        return self._cache.pop(index)
