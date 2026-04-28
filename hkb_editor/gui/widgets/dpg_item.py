from dearpygui import dearpygui as dpg


class DpgItem:
    """Base class for Dear PyGui widget wrappers.

    Parameters
    ----------
    tag : int or str
        Unique identifier; auto-generated if 0.
    width : int
        Pixel width of the widget.
    """

    def __init__(self, tag: str = 0, ctx: str = None) -> None:
        if not tag:
            tag = dpg.generate_uuid()

        self._tag = tag
        self._ctx = ctx

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
