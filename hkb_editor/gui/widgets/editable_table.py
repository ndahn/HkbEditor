from typing import Any, Callable, TypeVar
from pathlib import Path
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior
from hkb_editor.gui import style
from hkb_editor.gui.helpers import shorten_path, create_value_widget
from hkb_editor.gui.dialogs.file_dialog import open_multiple_dialog, choose_folder
from .dpg_item import DpgItem


_T = TypeVar("_T")


class add_widget_table(DpgItem):
    """A generic editable table widget for Dear PyGui.

    Renders a list of items as table rows via a caller-supplied ``create_row``
    function. Optionally supports adding, removing, selecting, and clearing
    items. If ``new_item`` is not set, add/remove controls are hidden.

    Row selection is implemented with a narrow dedicated button column rather
    than a span_columns selectable, so the remove button remains clickable.

    Parameters
    ----------
    initial_values : list
        Items to populate the table with on construction.
    create_row : callable
        Called as ``create_row(value, index)`` to build each row's DPG items.
    new_item : callable, optional
        Called as ``new_item(done_callback)`` when the add button is clicked.
        ``done_callback`` accepts the new item to append.
    on_add : callable, optional
        Fired as ``on_add(tag, (index, item, all_items), user_data)``.
    on_remove : callable, optional
        Fired as ``on_remove(tag, (index, item, all_items), user_data)``.
    on_select : callable, optional
        Fired as ``on_select(tag, (index, item, all_items), user_data)``.
    header_row : bool
        Show column headers.
    columns : list of str
        Column header labels.
    label : str, optional
        Text label rendered above the table.
    add_item_label : str
        Label for the add button.
    show_clear : bool
        Show a clear-all button next to the add button.
    parent : int or str
        DPG parent item.
    tag : int or str
        Explicit tag; auto-generated if 0 or None.
    user_data : any
        Passed through to all callbacks.
    """

    def __init__(
        self,
        initial_values: list[_T],
        create_row: Callable[[_T, int], None],
        *,
        new_item: Callable[[Callable[[_T], None]], None] = None,
        on_add: Callable[[str, tuple[int, _T, list[_T]], Any], None] = None,
        on_remove: Callable[[str, tuple[int, _T, list[_T]], Any], None] = None,
        on_select: Callable[[str, tuple[int, _T, list[_T]], Any], None] = None,
        header_row: bool = False,
        columns: list[str] = ("Value",),
        selected_row_color: style.RGBA = style.light_blue,
        label: str = None,
        add_item_label: str = "+",
        show_clear: bool = False,
        width: int = 0,
        height: int = 0,
        parent: str | int = 0,
        tag: str | int = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._values: list[_T] = list(initial_values)
        self._create_row = create_row
        self._new_item = new_item
        self._on_add = on_add
        self._on_remove = on_remove
        self._on_select = on_select
        self._selected_row_color = selected_row_color
        self._add_item_label = add_item_label
        self._columns = columns
        self._show_clear = show_clear
        self._user_data = user_data
        self._selected_idx: int = -1
        # Maps row index -> tag of its select-indicator button
        self._sel_buttons: dict[int, int] = {}

        self._build(header_row, columns, label, parent, width, height)
        self.refresh()

    # === Build =========================================================

    def _build(
        self,
        header_row: bool,
        columns: list[str],
        label: str,
        parent: str | int,
        width: int,
        height: int,
    ) -> None:
        if label:
            dpg.add_text(label, parent=parent, tag=self.tag)

        with dpg.child_window(
            border=False, autosize_x=True, auto_resize_y=True, parent=parent
        ):
            with dpg.table(
                header_row=header_row,
                policy=dpg.mvTable_SizingFixedFit,
                borders_outerH=True,
                borders_outerV=True,
                width=width,
                height=height,
                scrollX=(width != 0),
                scrollY=(height != 0),
                tag=self._t("table"),
            ):
                if self._on_select:
                    # Narrow indicator column; never spans other columns
                    dpg.add_table_column(
                        label="", width_fixed=True, init_width_or_weight=14
                    )
                for col in columns:
                    dpg.add_table_column(
                        label=col, width_stretch=True, init_width_or_weight=100
                    )
                if self._new_item:
                    dpg.add_table_column(
                        label="", width_fixed=True, init_width_or_weight=20
                    )

            dpg.add_group(tag=self._t("footer"))
            dpg.add_spacer(height=3)

    # === Internal row management =======================================

    def refresh(self) -> None:
        self._sel_buttons.clear()
        dpg.delete_item(self._t("table"), children_only=True, slot=1)
        for i, val in enumerate(self._values):
            self._add_row(val, i)
        self._add_footer()

        if self._on_select and self._selected_idx >= 0:
            dpg.highlight_table_row(
                self._t("table"), self._selected_idx, self._selected_row_color
            )

    def _add_row(self, val: _T, idx: int) -> None:
        with dpg.table_row(parent=self._t("table")) as row:
            if self._on_select:
                btn = dpg.add_button(
                    label=" ",
                    callback=self._on_select_clicked,
                    user_data=idx,
                    small=True,
                )
                self._sel_buttons[idx] = btn

            self._create_row(val, idx)

            remove_btn = None
            if self._new_item:
                remove_btn = dpg.add_button(
                    label="x",
                    callback=self._on_remove_clicked,
                    user_data=idx,
                    small=True,
                )

        # Bind a clicked handler to every content child (not the indicator or
        # remove button) so clicking text, inputs, etc. also triggers selection.
        # One registry per row; clicked_handler fires for both static text and
        # input widgets. idx is captured via closure since the handler has no
        # user_data forwarding.
        if self._on_select:
            registry = self._t(f"select_handler_{idx}")
            if not dpg.does_item_exist(registry):
                dpg.add_item_handler_registry(tag=registry)

            # DPG calls handlers as (sender, app_data, user_data) even when no
            # user_data is set, passing None — which overrides a default argument.
            def _make_handler(i: int) -> Callable:
                return lambda s, a, u: self._on_select_clicked(s, True, i)

            dpg.add_item_clicked_handler(
                parent=registry,
                callback=_make_handler(idx),
            )

            for child in dpg.get_item_children(row, slot=1):
                if child in (remove_btn, self._sel_buttons.get(idx)):
                    continue
                try:
                    dpg.bind_item_handler_registry(child, registry)
                except Exception:
                    pass  # item types that don't support handlers; skip silently

    def _add_footer(self) -> None:
        if not self._new_item:
            return
        with dpg.table_row(parent=self._t("table")):
            # When a selector column exists we must advance past it so the
            # add/clear buttons land in a cell that spans the content columns.
            if self._on_select:
                dpg.add_table_cell()
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label=self._add_item_label, callback=self._on_add_clicked
                )
                if self._show_clear:
                    dpg.add_button(
                        label="Clear", callback=self._on_clear_clicked
                    )

    def _update_indicators(self) -> None:
        """Refresh all row indicator labels to reflect the current selection."""
        for idx, btn in self._sel_buttons.items():
            try:
                dpg.set_item_label(btn, ">" if idx == self._selected_idx else " ")
            except Exception:
                pass  # row may have been deleted mid-refresh

    # === DPG callbacks =================================================

    def _on_remove_clicked(self, sender: int, app_data: Any, idx: int) -> None:
        prev = self._values.pop(idx)
        if idx == self._selected_idx:
            self._selected_idx = -1
        elif idx < self._selected_idx:
            self._selected_idx -= 1

        # Refresh first in case an outside caller needs the updated table state
        self.refresh()
        if self._on_remove:
            self._on_remove(self.tag, (idx, prev, self._values), self._user_data)

    def _on_add_item_done(self, result: _T) -> None:
        if not result:
            return

        pos = len(self._values)
        self._values.append(result)

        self.refresh()
        if self._on_add:
            self._on_add(self.tag, (pos, result, self._values), self._user_data)

    def _on_add_clicked(self) -> None:
        self._new_item(self._on_add_item_done)

    def _on_clear_clicked(self) -> None:
        self._values.clear()
        self._selected_idx = -1

        self.refresh()
        if self._on_remove:
            self._on_remove(self.tag, (0, None, self._values), self._user_data)

    def _on_select_clicked(self, sender: int, app_data: Any, idx: int) -> None:
        if self._selected_idx >= 0:
            dpg.unhighlight_table_row(self._t("table"), self._selected_idx)

        dpg.highlight_table_row(self._t("table"), idx, self._selected_row_color)

        self._selected_idx = idx
        self._update_indicators()
        if self._on_select:
            self._on_select(
                self.tag, (idx, self._values[idx], self._values), self._user_data
            )

    # === Public ========================================================

    @property
    def items(self) -> list[_T]:
        """Current item list (read-only copy)."""
        return self._values

    @items.setter
    def items(self, items: list[_T]) -> None:
        self._selected_idx = -1
        self._values = list(items)
        self.refresh()

    def select(self, index: int) -> None:
        if index is None:
            index = -1
        self._selected_idx = index
        self.refresh()

    def append(self, item: _T, *, fire_callbacks: bool = False) -> None:
        """Append an item and refresh the table."""
        pos = len(self._values)
        self._values.append(item)
        if fire_callbacks and self._on_add:
            self._on_add(self.tag, (pos, item, self._values), self._user_data)
        self.refresh()

    def remove(self, idx: int, *, fire_callbacks: bool = False) -> None:
        """Remove the item at ``idx`` and refresh the table."""
        prev = self._values.pop(idx)
        if idx == self._selected_idx:
            self._selected_idx = -1
        elif idx < self._selected_idx:
            self._selected_idx -= 1
        if fire_callbacks and self._on_remove:
            self._on_remove(self.tag, (idx, prev, self._values), self._user_data)
        self.refresh()

    def clear(self, *, fire_callbacks: bool = False) -> None:
        """Remove all items and refresh the table."""
        self._selected_idx = -1
        self._values.clear()
        if fire_callbacks and self._on_remove:
            self._on_remove(self.tag, (0, None, self._values), self._user_data)
        self.refresh()


# ===========================================================================


class add_simple_items_table(DpgItem):
    def __init__(
        self,
        behavior: HavokBehavior,
        columns: dict[str, type],
        make_item: Callable[[], tuple],
        on_value_changed: Callable[[str, list[tuple], Any], None] = None,
        *,
        initial_values: list[tuple] = None,
        label: str = None,
        on_select: Callable[[str, tuple, Any], None] = None,
        selected_row_color: style.RGBA = style.blue,
        add_item_label: str = "+ Item",
        show_clear: bool = False,
        header_row: bool = False,
        parent: str | int = 0,
        tag: str | int = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._columns = columns
        self._make_item = make_item
        self._on_value_changed = on_value_changed
        self._on_select_cb = on_select
        self._user_data = user_data

        self._table = add_widget_table(
            initial_values or [],
            self._item_to_row,
            new_item=self._add_item,
            on_add=self._on_add,
            on_remove=self._on_remove,
            on_select=self._on_select if on_select else None,
            add_item_label=add_item_label,
            selected_row_color=selected_row_color,
            show_clear=show_clear,
            columns=list(columns.keys()),
            header_row=header_row,
            label=label,
            parent=parent,
            tag=self.tag,
            user_data=user_data,
        )

    def _item_to_row(self, item: tuple, idx: int) -> None:
        for val, (col, tp) in zip(item, self._columns.items()):
            create_value_widget(
                self._behavior,
                tp,
                None,
                self._on_item_edit,
                default=val,
                user_data=(idx, col),
                tag=self._t(f"item_{idx}:{col}"),
            )

    def _on_item_edit(self, sender: str, value: Any, info: tuple[int, str]) -> None:
        idx, col = info
        col_idx = self._table._columns.index(col)
        item = list(self._table.items[idx])
        item[col_idx] = value
        self._table.items[idx] = tuple(item)

    def _add_item(self, done: Callable[[tuple], None]) -> None:
        done(self._make_item())

    def _on_add(self, sender: str, info: tuple[int, tuple, list[tuple]], user_data: Any) -> None:
        if self._on_value_changed:
            self._on_value_changed(self.tag, info[2], self._user_data)

    def _on_remove(self, sender: str, info: tuple[int, tuple, list[tuple]], user_data: Any) -> None:
        if self._on_value_changed:
            self._on_value_changed(self.tag, info[2], self._user_data)

    def _on_select(self, sender: str, info: tuple[int, tuple, list[tuple]], user_data: Any) -> None:
        if self._on_select_cb:
            self._on_select_cb(self.tag, info[1], self._user_data)

    # === Public ========================================================

    @property
    def items(self) -> list[tuple]:
        return self._table.items

    @items.setter
    def items(self, items: list[tuple]) -> None:
        self._table.items = items

    def select(self, index: int) -> None:
        self._table.select(index)

    def append(self, item: tuple, *, fire_callbacks: bool = False) -> None:
        self._table.append(item, fire_callbacks=fire_callbacks)

    def remove(self, idx: int, *, fire_callbacks: bool = False) -> None:
        self._table.remove(idx, fire_callbacks=fire_callbacks)

    def clear(self, *, fire_callbacks: bool = False) -> None:
        self._table.clear(fire_callbacks=fire_callbacks)


# ===========================================================================


class add_filepaths_table(DpgItem):
    """A file/folder path list widget built on ``add_widget_table``.

    Provides an add-files (or add-folders) button that opens a native dialog.
    Each path is shown as a read-only shortened text field.

    Parameters
    ----------
    initial_paths : list of Path
        Paths to pre-populate the table with.
    on_value_changed : callable, optional
        Fired as ``on_value_changed(tag, all_paths, user_data)`` after any add
        or remove.
    folders : bool
        Use folder-picker dialog instead of file-picker.
    label : str
        Text label rendered above the table.
    filetypes : dict, optional
        Passed to ``open_multiple_dialog`` when ``folders`` is False.
    on_select : callable, optional
        Fired as ``on_select(tag, path, user_data)`` when a row is clicked.
    show_clear : bool
        Show a clear-all button.
    parent : int or str
        DPG parent item.
    tag : int or str
        Explicit tag; auto-generated if 0.
    user_data : any
        Passed through to callbacks.
    """

    def __init__(
        self,
        initial_paths: list[Path],
        on_value_changed: Callable[[str, list[Path], Any], None] = None,
        *,
        folders: bool = False,
        label: str = "Files",
        filetypes: dict[str, str] = None,
        on_select: Callable[[str, Path, Any], None] = None,
        selected_row_color: style.RGBA = style.muted_blue,
        show_clear: bool = False,
        parent: str | int = 0,
        tag: str | int = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._on_value_changed = on_value_changed
        self._on_select_cb = on_select
        self._folders = folders
        self._label = label
        self._filetypes = filetypes
        self._user_data = user_data

        self._table = add_widget_table(
            initial_paths,
            self._create_row,
            new_item=self._add_item,
            on_add=self._on_add,
            on_remove=self._on_remove,
            on_select=self._on_select if on_select else None,
            add_item_label="+ Add Paths" if folders else "+ Add Files",
            selected_row_color=selected_row_color,
            show_clear=show_clear,
            label=label,
            parent=parent,
            tag=self.tag,
            user_data=user_data,
        )

    # === Callbacks =====================================================

    def _add_item(self, done: Callable[[Path], None]) -> None:
        if self._folders:
            res = choose_folder(title=self._label)
        else:
            res = open_multiple_dialog(title=self._label, filetypes=self._filetypes)

        if res:
            if isinstance(res, list):
                for p in res:
                    done(Path(p))
            else:
                done(Path(res))

    def _create_row(self, path: Path, idx: int) -> None:
        dpg.add_input_text(
            default_value=shorten_path(path, maxlen=40),
            enabled=False,
            readonly=True,
            width=-1,
        )

    def _on_add(
        self, sender: str, info: tuple[int, Path, list[Path]], cb_user_data: Any
    ) -> None:
        if self._on_value_changed:
            self._on_value_changed(self.tag, info[2], self._user_data)

    def _on_remove(
        self, sender: str, info: tuple[int, Path, list[Path]], cb_user_data: Any
    ) -> None:
        if self._on_value_changed:
            self._on_value_changed(self.tag, info[2], self._user_data)

    def _on_select(
        self, sender: str, info: tuple[int, Path, list[Path]], cb_user_data: Any
    ) -> None:
        if self._on_select_cb:
            self._on_select_cb(self.tag, info[1], self._user_data)

    # === Public ========================================================

    @property
    def paths(self) -> list[Path]:
        return self._table.items

    @paths.setter
    def paths(self, items: list[Path]) -> None:
        self._table.items = items

    def select(self, index: int) -> None:
        self._table.select(index)

    def append(self, path: Path, *, fire_callbacks: bool = False) -> None:
        self._table.append(path, fire_callbacks=fire_callbacks)

    def remove(self, idx: int, *, fire_callbacks: bool = False) -> None:
        self._table.remove(idx, fire_callbacks=fire_callbacks)

    def clear(self, *, fire_callbacks: bool = False) -> None:
        self._table.clear(fire_callbacks=fire_callbacks)
