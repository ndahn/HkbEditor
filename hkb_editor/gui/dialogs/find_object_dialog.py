from typing import Any, Callable, Iterable, Generator
import webbrowser
import time
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.query import query_objects, lucene_help_text, lucene_url
from hkb_editor.gui import style
from hkb_editor.gui.helpers import make_copy_menu, table_sort
from hkb_editor.gui.widgets import DpgItem, add_paragraphs


class find_dialog(DpgItem):
    """A filterable table of items with optional selection.

    The workhorse behind all the ``select_*`` dialogs. Items are pulled from
    ``item_getter`` every time the filter changes and rendered through
    ``item_to_row``. Supports single and multi selection (ctrl/shift click),
    an optional right-click context menu and an optional Okay/Cancel row.

    Parameters
    ----------
    item_getter : callable
        Called as ``item_getter(filter)``; may return a generator.
    columns : list of str
        Table column labels.
    item_to_row : callable
        Turns one item into a cell tuple (or a single string).
    context_menu_func : callable, optional
        Called with the right-clicked item to populate a context menu.
    okay_callback : callable, optional
        Called as ``callback(tag, item_or_items, user_data)``. Omit to hide
        the button row and make this a pure search window.
    allow_clear : bool
        Add a Clear button that reports ``None`` as the selection.
    item_limit : int, optional
        Max rows to render; derived from the column count if omitted.
    initial_filter : str
        Filter to apply right away.
    show_index : bool
        Prepend a running index column.
    title : str
        Window title bar label.
    filter_help : str, optional
        Help text shown in a tooltip behind a '?' button.
    on_filter_help_click : callable, optional
        Called when the '?' button is clicked.
    on_result_callback : callable, optional
        Called with the full match list after every filter update.
    select_color : style.RGBA
        Row highlight color.
    multiple : bool
        Allow selecting more than one row.
    modal : bool
        Make the window modal.
    hide_on_close : bool
        Hide instead of delete when closed, so the dialog can be reopened.
    tag : int or str, optional
        Explicit tag; auto-generated if 0.
    user_data : any, optional
        Passed through to the callbacks.
    """

    def __init__(
        self,
        item_getter: Callable[[str], Iterable[Any]],
        columns: list[str],
        item_to_row: Callable[[Any], tuple[str, ...] | str] = str,
        *,
        context_menu_func: Callable[[Any], None] = None,
        okay_callback: Callable[[str, Any | list[Any], Any], None] = None,
        allow_clear: bool = False,
        item_limit: int = None,
        initial_filter: str = "",
        show_index: bool = False,
        title: str = "Find...",
        filter_help: str = None,
        on_filter_help_click: Callable[[], None] = None,
        on_result_callback: Callable[[list[Any]], None] = None,
        select_color: style.RGBA = style.muted_green,
        multiple: bool = False,
        modal: bool = False,
        hide_on_close: bool = False,
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        if item_limit is None:
            item_limit = 6000 / len(columns)
            # round to nearest hundred
            item_limit = max(100, int(round(item_limit / 100)) * 100)

        self._item_getter = item_getter
        self._columns = columns
        self._item_to_row = item_to_row
        self._context_menu_func = context_menu_func
        self._okay_callback = okay_callback
        self._on_result_callback = on_result_callback
        self._select_color = select_color
        self._item_limit = item_limit
        self._show_index = show_index
        self._multiple = multiple
        self._hide_on_close = hide_on_close
        self._user_data = user_data

        self._window: str = None
        self._table: str = None
        self._anchor_idx: int = None
        self._selected_rows: set[str] = set()

        self._build(
            title, initial_filter, filter_help, on_filter_help_click, allow_clear, modal
        )

    def destroy(self) -> None:
        # Handler registries are root level items and outlive the window
        self._delete_item(self._t("right_click_handler"))

    # === Build ========================================================

    def _build(
        self,
        title: str,
        initial_filter: str,
        filter_help: str,
        on_filter_help_click: Callable[[], None],
        allow_clear: bool,
        modal: bool,
    ) -> None:
        if self._context_menu_func:
            handler = self._t("right_click_handler")
            if not dpg.does_item_exist(handler):
                dpg.add_item_handler_registry(tag=handler)
            
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right,
                callback=self._on_context_menu,
                parent=handler,
            )

        with dpg.window(
            width=600,
            height=400,
            label=title,
            modal=modal,
            on_close=self._on_window_close,
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            # Way too many options, instead fill the table according to user input
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    default_value=initial_filter or "",
                    hint="Filter...",
                    callback=self._on_filter_update,
                    tag=self._t("filter"),
                    no_undo_redo=True,
                )

                # A helpful tooltip full of help
                if filter_help:
                    dpg.add_button(label="?", callback=on_filter_help_click)
                    with dpg.tooltip(dpg.last_item()):
                        add_paragraphs(filter_help, 70, color=style.yellow)

                        if on_filter_help_click:
                            dpg.add_text(
                                "(Click the '?' for more information)",
                                color=style.blue,
                            )

                dpg.add_text("", tag=self._t("total"))
                dpg.add_loading_indicator(
                    circle_count=1,
                    radius=3,
                    show=False,
                    tag=self._t("loading"),
                )

            dpg.add_separator()

            table_height = -30 if self._okay_callback else -5

            with dpg.table(
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                scrollY=True,
                height=table_height,
                sortable=True,
                # sort_tristate=True,
                sort_multi=True,
                callback=table_sort,
                tag=self._t("table"),
            ) as self._table:
                if self._show_index:
                    dpg.add_table_column(label="Index")

                for i, col in enumerate(self._columns):
                    dpg.add_table_column(label=col, default_sort=(i == 0))

            dpg.add_separator()

            if self._okay_callback:
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Okay", callback=self._on_okay)
                    dpg.add_button(
                        label="Cancel",
                        callback=lambda: dpg.delete_item(self._window),
                    )
                    if allow_clear:
                        dpg.add_button(label="Clear", callback=self._on_clear)

        # Wait a frame so the size of our widgets is known
        dpg.split_frame()
        self._on_filter_update(self._t("filter"), initial_filter, None)

        # The dpg loading indicator has a fixed size depending on the radius of
        # the circles, so we have to position it manually
        filt_box_max = dpg.get_item_rect_max(self._t("filter"))
        indicator_pos = (filt_box_max[0] - 33, filt_box_max[1] - 62)
        dpg.set_item_pos(self._t("loading"), indicator_pos)

        dpg.focus_item(self._t("filter"))

    # === DPG callbacks ================================================

    def _on_filter_update(self, sender: str, filt: str, user_data: Any) -> None:
        dpg.delete_item(self._table, children_only=True, slot=1)

        # Get matching items and update total count. May take a while
        # depending on the query.
        dpg.show_item(self._t("loading"))
        dpg.set_value(self._t("total"), "(Searching...)")

        # filt might be None when called from a higher function like select_objects
        if filt is None:
            filt = ""

        # Short delay in case the user is still typing
        time.sleep(0.3)
        if filt != dpg.get_value(sender):
            # No need to continue if the query has changed already
            return

        # matches might be a generator which we only want to exhaust once
        items = []
        matches = self._item_getter(filt)
        idx = -1

        def get_matches(matches):
            # Helper to catch exceptions from invalid queries
            # and cancel early when the query changes
            try:
                for item in matches:
                    if filt != dpg.get_value(sender):
                        break

                    yield item
            except Exception:
                return

        for idx, item in enumerate(get_matches(matches)):
            items.append(item)

            if idx > self._item_limit:
                # Item limit reached, indicate that we are done but more matches exist
                items.extend(matches)
                dpg.set_value(
                    self._t("total"),
                    f"(showing {self._item_limit}/{len(items)})",
                )
                break

            cells = self._item_to_row(item)
            if isinstance(cells, str):
                cells = (cells,)

            if self._show_index:
                cells = (str(idx),) + cells

            with dpg.table_row(parent=self._table, user_data=item):
                dpg.add_selectable(
                    label=cells[0],
                    span_columns=True,
                    callback=self._on_select,
                    user_data=item,
                    tag=self._t(f"item_row_{idx}"),
                )
                if self._context_menu_func:
                    dpg.bind_item_handler_registry(
                        dpg.last_item(), self._t("right_click_handler")
                    )

                for c in cells[1:]:
                    dpg.add_text(c)
        else:
            # Items fit into the search limit
            dpg.set_value(self._t("total"), f"({idx + 1} matches)")

        # Don't pass results if no filter was set
        if filt and self._on_result_callback:
            self._on_result_callback(items)

        dpg.hide_item(self._t("loading"))

    def _on_select(self, sender: str, select: bool, item: Any) -> None:
        dpg.set_value(sender, False)
        item_row = dpg.get_item_parent(sender)
        rows = dpg.get_item_children(self._table, slot=1)

        # Find the clicked row's index
        item_idx = next((i for i, r in enumerate(rows) if r == item_row), None)
        if item_idx is None:
            raise ValueError(f"Could not determine row for item {item}")

        if self._multiple:
            if dpg.is_key_down(dpg.mvKey_ModShift) and self._anchor_idx is not None:
                # Extend selection from anchor to clicked row - always select, never toggle
                start, end = sorted((self._anchor_idx, item_idx))
                for i in range(start, end + 1):
                    self._set_row_selected(rows[i], item_idx, True)
                # Don't update anchor on shift-click
                return
            elif dpg.is_key_down(dpg.mvKey_ModCtrl):
                # Toggle just this row
                self._set_row_selected(item_row, item_idx, select)
            else:
                # Plain click: replace selection
                self.clear_selection()
                self._set_row_selected(item_row, item_idx, select)
        else:
            # Single-select: clear others, apply this
            self.clear_selection()
            self._set_row_selected(item_row, item_idx, select)

        self._anchor_idx = item_idx

    def _on_context_menu(self, sender: str, app_data: tuple[int, int]) -> None:
        _, selectable = app_data
        item = dpg.get_item_user_data(selectable)

        if item is not None:
            # Force select the right-clicked item
            self._on_select(selectable, True, item)
            self._context_menu_func(item)

    def _on_okay(self) -> None:
        if not self._selected_rows:
            return

        if self._multiple:
            items = [dpg.get_item_user_data(row) for row in self._selected_rows]
            self._okay_callback(self._tag, items, self._user_data)
        else:
            rows = dpg.get_item_children(self._table, slot=1)
            item = dpg.get_item_user_data(rows[self._anchor_idx])
            self._okay_callback(self._tag, item, self._user_data)

        self._on_window_close()

    def _on_clear(self) -> None:
        self._okay_callback(self._tag, None, self._user_data)
        self._on_window_close()

    def _on_window_close(self) -> None:
        if self._hide_on_close:
            dpg.hide_item(self._window)
        else:
            self.destroy()
            dpg.delete_item(self._window)

    # === Helpers ======================================================

    def _set_row_selected(self, row: str, idx: int, select: bool) -> None:
        if select:
            dpg.highlight_table_row(self._table, idx, self._select_color)
            self._selected_rows.add(row)
        else:
            dpg.unhighlight_table_row(self._table, idx)
            self._selected_rows.discard(row)

    # === Public =======================================================

    @property
    def selected_items(self) -> list[Any]:
        return [dpg.get_item_user_data(row) for row in self._selected_rows]

    def clear_selection(self) -> None:
        for idx, row in enumerate(dpg.get_item_children(self._table, 1)):
            dpg.unhighlight_table_row(self._table, idx)
            children = dpg.get_item_children(row, slot=1)
            if children:
                dpg.set_value(children[0], False)

        self._selected_rows.clear()

    def refresh(self) -> None:
        """Re-run the current filter."""
        self._on_filter_update(
            self._t("filter"), dpg.get_value(self._t("filter")), None
        )


class search_objects_dialog(find_dialog):
    """A non-modal object search window with pin/jump context actions.

    Hides instead of closing so it can be reopened cheaply.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to query.
    pin_callback : callable, optional
        Called as ``callback(tag, object_id, user_data)`` from the context menu.
    jump_callback : callable, optional
        Called as ``callback(tag, object_id, user_data)`` from the context menu.
    result_callback : callable, optional
        Called as ``callback(tag, records, user_data)`` after each search.

    See :class:`find_dialog` for the remaining parameters.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        pin_callback: Callable[[str, str, Any], None] = None,
        jump_callback: Callable[[str, str, Any], None] = None,
        *,
        initial_filter: str = "",
        result_callback: Callable[[str, list[HkbRecord], Any], None] = None,
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        self._behavior = behavior
        self._pin_callback = pin_callback
        self._jump_callback = jump_callback
        self._result_callback = result_callback

        super().__init__(
            behavior.query,
            ["ID", "Name", "Type"],
            self._record_to_row,
            context_menu_func=self._make_context_menu,
            okay_callback=None,
            initial_filter=initial_filter,
            filter_help=lucene_help_text,
            hide_on_close=True,
            on_filter_help_click=lambda: webbrowser.open(lucene_url),
            on_result_callback=self._on_results,
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )

    def destroy(self) -> None:
        super().destroy()
        # Popups are root level items and outlive the window
        self._delete_item(self._t("context_popup"))

    def _record_to_row(self, item: HkbRecord) -> tuple[str, ...]:
        name = item.get_field("name", "", resolve=True)
        type_name = self._behavior.type_registry.get_name(item.type_id)
        return (item.object_id, name, type_name)

    def _make_context_menu(self, item: HkbRecord) -> None:
        # Only one context menu can be open at a time
        self._delete_item(self._t("context_popup"))

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            autosize=True,
            tag=self._t("context_popup"),
            on_close=lambda: self._delete_item(self._t("context_popup")),
        ) as popup:
            if self._pin_callback:
                dpg.add_selectable(
                    label="Pin",
                    callback=lambda: self._pin_callback(
                        self._tag, item.object_id, self._user_data
                    ),
                )
            if self._jump_callback:
                dpg.add_selectable(
                    label="Jump To",
                    callback=lambda: self._jump_callback(
                        self._tag, item.object_id, self._user_data
                    ),
                )
            make_copy_menu(item)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))

    def _on_results(self, items: list[HkbRecord]) -> None:
        if self._result_callback:
            self._result_callback(self._tag, items, self._user_data)


class select_object(find_dialog):
    """Pick one or more records, optionally restricted to a type.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior to query.
    target_type_id : str or None
        Restrict candidates to this type; None allows any object.
    on_pointer_selected : callable
        Called as ``callback(tag, record_or_records, user_data)``.
    include_derived : bool
        Also accept subtypes of ``target_type_id``.

    See :class:`find_dialog` for the remaining parameters.
    """

    def __init__(
        self,
        behavior: HavokBehavior,
        target_type_id: str,
        on_pointer_selected: Callable[[str, HkbRecord | list[HkbRecord], Any], None],
        *,
        include_derived: bool = True,
        initial_filter: str = "",
        allow_clear: bool = True,
        title: str = None,
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        self._behavior = behavior

        # Valid objects can be cached
        if target_type_id:
            self._candidates = list(
                behavior.find_objects_by_type(
                    target_type_id, include_derived=include_derived
                )
            )
        else:
            self._candidates = behavior.objects.values()

        if not title:
            if target_type_id:
                target_type_name = behavior.type_registry.get_name(target_type_id)
                title = f"Select {target_type_name}"
            else:
                title = "Select Object"

        super().__init__(
            self._find_matches,
            ["ID", "Name", "Type"],
            self._record_to_row,
            okay_callback=on_pointer_selected,
            allow_clear=allow_clear,
            initial_filter=initial_filter,
            title=title,
            filter_help=lucene_help_text,
            on_filter_help_click=lambda: webbrowser.open(lucene_url),
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )

    def _find_matches(self, filt: str) -> list[HkbRecord]:
        return query_objects(self._candidates, filt)

    def _record_to_row(self, item: HkbRecord) -> tuple[str, ...]:
        name = item.get_field("name", "", resolve=True)
        type_name = self._behavior.type_registry.get_name(item.type_id)
        return (item.object_id, name, type_name)


class _select_indexed(find_dialog):
    """Shared base for the index-based pickers (variables, events, animations).

    Subclasses provide the ``(index, value)`` pairs; the selection is reported
    back as the index (or a list of indices when ``multiple`` is set).
    """

    def __init__(
        self,
        entries: list[tuple[int, Any]],
        columns: list[str],
        callback: Callable[[str, int | list[int], Any], None],
        *,
        initial_filter: str = "",
        allow_clear: bool = True,
        title: str = "Select",
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        self._entries = entries
        self._selection_callback = callback

        super().__init__(
            self._find_matches,
            columns,
            self._entry_to_row,
            okay_callback=self._on_selection,
            allow_clear=allow_clear,
            initial_filter=initial_filter,
            title=title,
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )

    def _matches(self, filt: str, value: Any) -> bool:
        return filt in str(value).lower()

    def _find_matches(self, filt: str) -> Generator[tuple[int, Any], None, None]:
        filt = filt.lower()
        for idx, value in self._entries:
            if self._matches(filt, value):
                yield (idx, value)

    def _entry_to_row(self, entry: tuple[int, Any]) -> tuple[str, ...]:
        return entry

    def _on_selection(
        self,
        sender: str,
        selected: tuple[int, Any] | list[tuple[int, Any]],
        user_data: Any,
    ) -> None:
        if selected is None:
            val = None
        elif self._multiple:
            val = [s[0] for s in selected]
        else:
            val = selected[0]

        self._selection_callback(sender, val, user_data)


class select_variable(_select_indexed):
    """Pick one or more behavior variables by index."""

    def __init__(
        self,
        behavior: HavokBehavior,
        on_variable_selected: Callable[[str, int | list[int], Any], None],
        *,
        initial_filter: str = "",
        allow_clear: bool = True,
        title: str = "Select Variable",
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        entries = list(enumerate(behavior.get_variables(full_info=True)))

        super().__init__(
            entries,
            ["ID", "Variable", "Type", "Min", "Max"],
            on_variable_selected,
            initial_filter=initial_filter,
            allow_clear=allow_clear,
            title=title,
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )

    def _matches(self, filt: str, value: HkbVariable) -> bool:
        return filt in value.name.lower()

    def _entry_to_row(self, entry: tuple[int, HkbVariable]) -> tuple[str, ...]:
        return (entry[0], *[str(v) for v in entry[1].astuple()])


class select_event(_select_indexed):
    """Pick one or more behavior events by index."""

    def __init__(
        self,
        behavior: HavokBehavior,
        on_event_selected: Callable[[str, int | list[int], Any], None],
        *,
        initial_filter: str = "",
        allow_clear: bool = True,
        title: str = "Select Event",
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        entries = list(enumerate(behavior.get_events()))

        super().__init__(
            entries,
            ["ID", "Event"],
            on_event_selected,
            initial_filter=initial_filter,
            allow_clear=allow_clear,
            title=title,
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )


class select_animation(_select_indexed):
    """Pick one or more animation names by index."""

    def __init__(
        self,
        behavior: HavokBehavior,
        on_animation_selected: Callable[[str, int | list[int], Any], None],
        *,
        initial_filter: str = "",
        allow_clear: bool = True,
        full_names: bool = False,
        title: str = "Select Animation Name",
        multiple: bool = False,
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        entries = list(enumerate(behavior.get_animations(full_names=full_names)))

        super().__init__(
            entries,
            ["ID", "Animation"],
            on_animation_selected,
            initial_filter=initial_filter,
            allow_clear=allow_clear,
            title=title,
            multiple=multiple,
            tag=tag,
            user_data=user_data,
        )

    def _matches(self, filt: str, value: str) -> bool:
        # Animation names are already lowercase
        return filt in value
