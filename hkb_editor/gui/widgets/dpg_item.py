from __future__ import annotations
import atexit
from dearpygui import dearpygui as dpg


# Prevent interactions with dpg once python is exiting
_shutting_down = False


@atexit.register
def _mark_shutdown() -> None:
    global _shutting_down
    _shutting_down = True


class DpgItem:
    """Base class for Dear PyGui widget wrappers.

    Parameters
    ----------
    tag : int or str
        Unique identifier; auto-generated if 0.
    width : int
        Pixel width of the widget.
    """

    __instance_store: dict[str | int, DpgItem] = {}

    @classmethod
    def get_instance(cls, tag: str | int) -> DpgItem:
        item = cls.__instance_store.get(tag)
        if item is not None:
            return item

        # dpg hands out integer ids when walking the item tree, but items
        # created with a string tag are registered under that alias
        if not isinstance(tag, str) and dpg.does_item_exist(tag):
            alias = dpg.get_item_alias(tag)
            if alias:
                return cls.__instance_store.get(alias)

        return None

    @classmethod
    def instances(cls) -> list[DpgItem]:
        """All DpgItems currently alive, newest last."""
        return list(cls.__instance_store.values())

    @staticmethod
    def destroy_tree(tag: str | int) -> None:
        """Call ``destroy()`` on every DpgItem at or below ``tag``.

        Popups, windows and handler registries are root level containers and
        may keep other objects alive through closures. Rather than have every
        widget report its items for cleanup, we walk the dpg tree and let the
        items clean up after themselves.
        """
        if not dpg.does_item_exist(tag):
            return

        for children in dpg.get_item_children(tag).values():
            for child in children:
                DpgItem.destroy_tree(child)

        item = DpgItem.get_instance(tag)
        if item:
            item.destroy()

    def __init__(self, tag: str = 0, ctx: str = None) -> None:
        if not tag:
            tag = dpg.generate_uuid()

        self._tag = tag
        self._ctx = ctx
        DpgItem.__instance_store[tag] = self

    def __del__(self):
        DpgItem.__instance_store.pop(self._tag, None)

    def destroy(self) -> None:
        pass

    def _delete_item(self, tag: str) -> bool:
        if _shutting_down:
            # dpg is gone, and the OS is about to reclaim everything anyway
            return False

        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
            try:
                dpg.remove_alias(tag)
            except SystemError:
                pass

            return True

        return False

    @property
    def tag(self) -> str:
        return self._tag

    def _t(self, suffix: str) -> str:
        if self._ctx:
            suffix = f"{self._ctx}/{suffix}"
        return f"{self._tag}/{suffix}"

    @property
    def size(self) -> tuple[int, int]:
        return dpg.get_item_rect_size(self._tag)

    @property
    def width(self) -> int:
        return dpg.get_item_rect_size(self._tag)[0]

    @property
    def height(self) -> int:
        return dpg.get_item_rect_size(self._tag)[1]
