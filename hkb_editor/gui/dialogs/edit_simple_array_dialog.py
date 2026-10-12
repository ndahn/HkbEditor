from typing import Any, Callable, Type, Optional
import logging
import re
from dearpygui import dearpygui as dpg

from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window, table_sort
from hkb_editor.gui.widgets import (
    DpgItem,
    add_generic_widget,
    add_paragraphs,
    get_paragraph_height,
)
from .new_tuple_dialog import new_tuple_dialog


search_help_text = """\
By default this will filter the items by simple string match.

For more advanced searches you may combine several filters separated by commas (,). These filters will be applied in the order they are specified.

To only search specific index ranges you may use the ">X" or "<X" filters, where X is a number.
"""


class edit_simple_array_dialog(DpgItem):
    """A table editor for a list of same-shaped tuples.

    Rows can be added, removed and reordered, and every cell gets an input
    widget matching its column type. The ``on_*`` hooks may veto a change by
    raising.

    Parameters
    ----------
    items : list of tuple
        The list to edit; mutated in place.
    columns : dict
        Maps column name to the type of its value.
    title : str
        Window title bar label.
    help : str, optional
        Explanation shown at the bottom of the dialog.
    choices : dict, optional
        Maps column index to a list of choices for that column.
    on_add : callable, optional
        ``on_add(index, new_value)``; may edit ``new_value`` or raise to veto.
    on_update : callable, optional
        ``on_update(index, old_item, new_item)``; may return a replacement
        item or raise to veto.
    on_delete : callable, optional
        ``on_delete(index)``; may raise to veto.
    on_move : callable, optional
        ``on_move(index, new_index)``; may raise to veto.
    on_close : callable, optional
        Called as ``callback(tag, items, user_data)`` when the dialog closes.
    get_item_hint : callable, optional
        Enables a per-row '(?)' button. Not implemented yet.
    item_limit : int, optional
        Max rows to render; derived from the column count if omitted.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    user_data : any, optional
        Passed through to ``on_close``.
    """

    def __init__(
        self,
        items: list[tuple],
        columns: dict[str, Type],
        *,
        title: str = "Edit Array",
        help: str = None,
        choices: dict[int, list[str | tuple[str, Any]]] = None,
        on_add: Callable[[int, list], bool] = None,
        on_update: Callable[[int, tuple, list], Optional[tuple]] = None,
        on_delete: Callable[[int], None] = None,
        on_move: Callable[[int, int], None] = None,
        on_close: Callable[[str, list[str], Any], None] = None,
        get_item_hint: Callable[[int], list[str]] = None,
        item_limit: int = None,
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        if item_limit is None:
            item_limit = 4000 / len(columns)
            # round to nearest hundred
            item_limit = max(100, int(round(item_limit / 100)) * 100)

        self._items = items
        self._columns = columns
        self._choices = choices
        self._on_add = on_add
        self._on_update = on_update
        self._on_delete = on_delete
        self._on_move = on_move
        self._on_close = on_close
        self._get_item_hint = get_item_hint
        self._item_limit = item_limit
        self._user_data = user_data

        self._window: str = None
        self._table: str = None
        self._entry_dialog: new_tuple_dialog = None
        self._logger = logging.getLogger(__name__)

        self._build(title, help)

    def destroy(self) -> None:
        # The entry dialog is a root level window and outlives us
        if self._entry_dialog is not None:
            self._entry_dialog.destroy()
            self._delete_item(self._entry_dialog.tag)
            self._entry_dialog = None

    # === Build ========================================================

    def _build(self, title: str, help: str) -> None:
        with dpg.window(
            width=600,
            height=460,
            label=title,
            on_close=self.close,
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    hint="Filter Entries",
                    callback=self.fill_table,
                    tag=self._t("filter"),
                )

                dpg.add_button(label="?")
                with dpg.tooltip(dpg.last_item()):
                    add_paragraphs(search_help_text, 70, color=style.yellow)

                dpg.add_text("", tag=self._t("total"))

            with dpg.table(
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                width=-1,
                # height set once the help paragraph has been measured
                borders_outerH=True,
                sortable=True,
                # sort_tristate=True,
                sort_multi=True,
                callback=table_sort,
                tag=self._t("table"),
            ) as self._table:
                dpg.add_table_column(label="Index")
                for col in self._columns.keys():
                    dpg.add_table_column(label=col, width_stretch=True)
                dpg.add_table_column(tag=self._t("column_advanced"), enabled=False)

            with dpg.group(horizontal=True, show=True):
                dpg.add_button(label="Add New", callback=self._on_new_entry)
                dpg.add_button(label="Delete Last", callback=self._on_delete_entry)
                # Vertical separator :)
                dpg.add_text("|")
                dpg.add_checkbox(
                    label="Advanced",
                    default_value=False,
                    callback=self._on_toggle_advanced,
                )

            par = None
            if help:
                dpg.add_separator()
                par = add_paragraphs(help, 90, color=style.light_blue)

        dpg.focus_item(self._t("filter"))
        self.fill_table(self._t("filter"), "", None)

        # Adjust table height to content below it
        dpg.split_frame()
        table_h = 25
        if par is not None:
            table_h += get_paragraph_height(par)

        # Round to nearest 10
        table_h = max(10, int(round(table_h / 10)) * 10)
        dpg.configure_item(self._t("table"), height=-table_h)

    # === DPG callbacks ================================================

    def _on_new_entry(self, sender: str = None, app_data: Any = None,
                      item_idx: int = None) -> None:
        self.destroy()
        self._entry_dialog = new_tuple_dialog(
            self._columns,
            self._on_entry_created,
            choices=self._choices,
            user_data=item_idx,
        )

        dpg.split_frame()
        center_window(self._entry_dialog.tag, parent=self._window)

    def _on_entry_created(self, sender: str, new_value: tuple, index: int) -> None:
        # In case on_add wants to edit the values
        new_value = list(new_value)

        if index is None:
            index = len(self._items)

        # May raise as a veto
        if self._on_add:
            self._on_add(index, new_value)

        self._items.insert(index, tuple(new_value))
        self.fill_table()

    def _on_move_entry(
        self, sender: str, app_data: Any, move: tuple[int, int]
    ) -> None:
        idx, offset = move
        new_idx = idx + offset

        if not 0 <= new_idx < len(self._items):
            return

        # May raise as a veto
        if self._on_move:
            self._on_move(idx, new_idx)

        self._items[new_idx], self._items[idx] = self._items[idx], self._items[new_idx]
        self.fill_table()

    def _on_delete_entry(
        self, sender: str = None, app_data: Any = None, index: int = None
    ) -> None:
        if index is None:
            index = len(self._items) - 1

        # May raise as a veto
        if self._on_delete:
            self._on_delete(index)

        del self._items[index]
        self.fill_table()

    def _on_update_entry(
        self, sender: str, new_value: Any, user_data: tuple[int, int]
    ) -> None:
        item_idx, val_idx = user_data

        if self._choices and val_idx in self._choices:
            for item in self._choices[val_idx]:
                if item == new_value:
                    break
                if isinstance(item, tuple) and item[0] == new_value:
                    new_value = item[1]
                    break

        old_item = self._items[item_idx]
        new_item = list(old_item)
        new_item[val_idx] = new_value

        # May raise as a veto
        if self._on_update:
            try:
                redacted = self._on_update(item_idx, old_item, new_item)
                if redacted:
                    # on_update may edit the new item
                    new_item = redacted
            except Exception as e:
                # on_update may veto the change
                self._logger.error(f"Update rejected: {e}")
                return

        self._items[item_idx] = tuple(new_item)
        self.fill_table()

    def _on_toggle_advanced(
        self, sender: str, enabled: bool, user_data: Any
    ) -> None:
        if enabled:
            dpg.enable_item(self._t("column_advanced"))
        else:
            dpg.disable_item(self._t("column_advanced"))

    def _on_show_item_hint(self, sender: str, app_data: Any, index: int) -> None:
        # TODO can use this to show where items are referenced
        print("TODO not implemented yet")

    # === Helpers ======================================================

    def _is_match(self, filt: str, idx: int, item: Any) -> bool:
        filt = filt.strip().lower()
        if re.match(r"[<>][0-9]+", filt):
            num = int(filt[1:])
            if filt[0] == "<" and idx < num:
                return True
            elif filt[0] == ">" and idx > num:
                return True
        else:
            return filt in str(idx) or filt in str(item).lower()

    def _get_matching_items(self, filt: str) -> list[tuple[int, Any]]:
        if not filt:
            return list(enumerate(self._items))

        filt_parts = filt.lower().split(",")
        matches = list(enumerate(self._items))
        for part in filt_parts:
            matches = [
                (idx, item) for idx, item in matches if self._is_match(part, idx, item)
            ]

        return matches

    def _add_row(self, item_idx: int, item: tuple) -> None:
        with dpg.table_row(filter_key=f"{item_idx}:{item}", parent=self._table):
            dpg.add_text(str(item_idx))

            for val_idx, (val_type, val) in enumerate(
                zip(self._columns.values(), item)
            ):
                add_generic_widget(
                    val_type,
                    "",
                    self._on_update_entry,
                    default=val,
                    choices=self._choices.get(val_idx) if self._choices else None,
                    user_data=(item_idx, val_idx),
                    width=-1,
                )

            with dpg.group(horizontal=True, horizontal_spacing=2):
                dpg.add_button(
                    label="+",
                    callback=self._on_new_entry,
                    user_data=item_idx + 1,
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Down,
                    callback=self._on_move_entry,
                    user_data=(item_idx, 1),
                )
                dpg.add_button(
                    arrow=True,
                    direction=dpg.mvDir_Up,
                    callback=self._on_move_entry,
                    user_data=(item_idx, -1),
                )
                dpg.add_button(
                    label="-",
                    callback=self._on_delete_entry,
                    user_data=item_idx,
                )

                if self._get_item_hint:
                    dpg.add_button(
                        label="(?)",
                        small=True,
                        callback=self._on_show_item_hint,
                        user_data=item_idx,
                    )

    # === Public =======================================================

    @property
    def items(self) -> list[tuple]:
        return self._items

    def fill_table(
        self, sender: str = None, filt: str = None, user_data: Any = None
    ) -> None:
        """Rebuild the table from the current items and filter."""
        if sender is None:
            sender = self._t("filter")

        if filt is None:
            filt = dpg.get_value(self._t("filter"))

        dpg.delete_item(self._table, slot=1, children_only=True)

        matches = self._get_matching_items(filt)
        if len(matches) > self._item_limit:
            dpg.set_value(
                self._t("total"),
                f"(showing {self._item_limit}/{len(matches)})",
            )
            matches = matches[: self._item_limit]
        else:
            dpg.set_value(self._t("total"), f"({len(matches)} matches)")

        for item_idx, item in matches:
            if filt != dpg.get_value(sender):
                # Crude attempt to return early
                break

            self._add_row(item_idx, item)

    def close(self) -> None:
        if self._on_close:
            self._on_close(self._tag, self._items, self._user_data)

        self.destroy()
        dpg.delete_item(self._window)
