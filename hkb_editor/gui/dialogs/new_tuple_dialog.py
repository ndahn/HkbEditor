from typing import Any, Callable, Type
from enum import Enum
from dearpygui import dearpygui as dpg

from hkb_editor.gui.widgets import DpgItem, add_generic_widget


class new_tuple_dialog(DpgItem):
    """A small modal form for entering one row of a typed table.

    Renders one input widget per column and reports the assembled tuple to
    ``callback`` when confirmed.

    Parameters
    ----------
    columns : dict
        Maps column name to the type of its value.
    callback : callable
        Called as ``callback(tag, values, user_data)`` on confirm.
    choices : dict, optional
        Maps column index to a list of choices; items may be
        ``(label, value)`` tuples.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    user_data : any, optional
        Passed through to ``callback``.
    """

    def __init__(
        self,
        columns: dict[str, Type],
        callback: Callable[[str, tuple, Any], None],
        *,
        choices: dict[int, list[str | tuple[str, Any]]] = None,
        title: str = "New Item",
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._columns = columns
        self._callback = callback
        self._choices = choices
        self._user_data = user_data
        self._window: str = None

        self._values = [None] * len(columns)
        for idx, t in enumerate(columns.values()):
            if issubclass(t, Enum):
                self._values[idx] = list(t)[0]
            else:
                self._values[idx] = t()

        self._build(title)

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            modal=True,
            min_size=(100, 30),
            autosize=True,
            label=title,
            no_saved_settings=True,
            tag=self._tag,
            on_close=lambda: dpg.delete_item(self._window),
        ) as self._window:
            for idx, (col, col_type) in enumerate(self._columns.items()):
                add_generic_widget(
                    col_type,
                    col,
                    self._on_value_changed,
                    choices=self._choices.get(idx) if self._choices else None,
                    default=self._values[idx],
                    tag=self._t(f"widget_{idx}"),
                    user_data=idx,
                )

            with dpg.group(horizontal=True):
                dpg.add_button(label="Okay", callback=self._on_okay)
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.delete_item(self._window),
                )

        dpg.focus_item(self._t("widget_0"))

    # === DPG callbacks ================================================

    def _on_value_changed(self, sender: str, new_value: Any, val_idx: int) -> None:
        if self._choices and val_idx in self._choices:
            for item in self._choices[val_idx]:
                if item == new_value:
                    break
                if isinstance(item, tuple) and item[0] == new_value:
                    new_value = item[1]
                    break

        self._values[val_idx] = new_value

    def _on_okay(self) -> None:
        self._callback(self._tag, self._values, self._user_data)
        dpg.delete_item(self._window)

    # === Public =======================================================

    @property
    def values(self) -> list[Any]:
        return self._values
