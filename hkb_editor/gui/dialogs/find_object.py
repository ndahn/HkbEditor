from typing import Any, Callable, Iterable, Generator
import webbrowser
from dearpygui import dearpygui as dpg
import time

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior, HkbVariable
from hkb_editor.hkb.query import query_objects, lucene_help_text, lucene_url
from hkb_editor.gui.helpers import make_copy_menu, table_sort, add_paragraphs
from hkb_editor.gui import style


def find_dialog(
    item_getter: Callable[[str], Iterable[Any]],
    columns: list[str],
    item_to_row: Callable[[Any], tuple[str, ...] | str] = str,
    *,
    context_menu_func: Callable[[Any], None] = None,
    okay_callback: Callable[[str, Any, Any], None] = None,
    allow_clear: bool = False,
    item_limit: int = None,
    initial_filter: str = "",
    show_index: bool = False,
    title: str = "Find...",
    filter_help: str = None,
    on_filter_help_click: Callable[[], None] = None,
    on_result_callback: Callable[[list[Any]], None] = None,
    modal: bool = False,
    hide_on_close: bool = True,
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    selected_item = None

    if item_limit is None:
        item_limit = 2000 / len(columns)
        # round to nearest hundred
        item_limit = max(100, int(round(item_limit / 100)) * 100)

    def on_filter_update(sender, filt, user_data):
        dpg.delete_item(table, children_only=True, slot=1)

        # Get matching items and update total count. May take a while depending on the query.
        dpg.show_item(f"{tag}_loading")
        dpg.set_value(f"{tag}_total", "(Searching...)")

        # Short delay in case the user is still typing
        time.sleep(0.3)
        if filt != dpg.get_value(sender):
            # No need to continue if the query has changed already
            return

        # matches might be a generator which we only want to exhaust once
        items = []
        matches = item_getter(filt)
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

            if idx > item_limit:
                # Item limit reached, indicate that we are done but more matches exist
                items.extend(matches)
                dpg.set_value(f"{tag}_total", f"(showing {item_limit}/{len(items)})")
                break

            cells = item_to_row(item)
            if isinstance(cells, str):
                cells = (cells,)

            if show_index:
                cells = (str(idx),) + cells

            with dpg.table_row(parent=table, user_data=item):
                dpg.add_selectable(
                    label=cells[0],
                    span_columns=True,
                    callback=on_select,
                    user_data=item,
                    tag=f"{tag}_item_row_{idx}",
                )
                if context_menu_func:
                    dpg.bind_item_handler_registry(dpg.last_item(), right_click_handler)

                for c in cells[1:]:
                    dpg.add_text(c)
        else:
            # Items fit into the search limit
            dpg.set_value(f"{tag}_total", f"({idx + 1} matches)")

        # Don't pass results if no filter was set
        if filt and on_result_callback:
            on_result_callback(items)

        dpg.hide_item(f"{tag}_loading")

    def on_select(sender, is_selected: bool, item: Any):
        nonlocal selected_item
        if selected_item == item:
            return

        selected_item = item

        # Deselect all other selectables
        if is_selected:
            for row in dpg.get_item_children(table, slot=1):
                row_selected = dpg.get_item_user_data(row) == item
                dpg.set_value(dpg.get_item_children(row, slot=1)[0], row_selected)

    def on_okay():
        if selected_item is None:
            return

        okay_callback(dialog, selected_item, user_data)
        on_window_close()

    def on_clear():
        okay_callback(dialog, None, user_data)
        on_window_close()

    if context_menu_func:

        def open_context_menu(sender: str, app_data: tuple[int, int]):
            _, row = app_data
            item = dpg.get_item_user_data(row)

            if item is not None:
                # Force select the right-clicked item
                on_select(sender, True, item)
                context_menu_func(selected_item)

        with dpg.item_handler_registry() as right_click_handler:
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right, callback=open_context_menu
            )

    def on_window_close():
        if hide_on_close:
            dpg.hide_item(dialog)
        else:
            dpg.delete_item(dialog)
            if context_menu_func:
                dpg.delete_item(right_click_handler)

    # Window content
    with dpg.window(
        width=600,
        height=400,
        label=title,
        modal=modal,
        on_close=on_window_close,
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        # Way too many options, instead fill the table according to user input
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                default_value=initial_filter,
                hint="Filter...",
                callback=on_filter_update,
                tag=f"{tag}_filter",
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

            dpg.add_text("", tag=f"{tag}_total")
            dpg.add_loading_indicator(
                circle_count=1,
                radius=3,
                show=False,
                tag=f"{tag}_loading",
            )

        dpg.add_separator()

        table_height = -5
        if okay_callback:
            table_height = -30

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            scrollY=True,
            height=table_height,
            sortable=True,
            # sort_tristate=True,
            sort_multi=True,
            callback=table_sort,
            tag=f"{tag}_table",
        ) as table:
            if show_index:
                dpg.add_table_column(label="Index")

            for i, col in enumerate(columns):
                dpg.add_table_column(label=col, default_sort=(i == 0))

        dpg.add_separator()

        if okay_callback:
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=on_okay,
                )
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.delete_item(dialog),
                )
                if allow_clear:
                    dpg.add_button(
                        label="Clear",
                        callback=on_clear,
                    )

    # Wait a frame so the size of our widgets is known
    dpg.split_frame()
    on_filter_update(f"{tag}_filter", initial_filter, None)

    # The dpg loading indicator has a fixed size depending on the radius of the circles, 
    # so we have to position it manually 
    filt_box_max = dpg.get_item_rect_max(f"{tag}_filter")
    indicator_pos = (
        filt_box_max[0] - 33, filt_box_max[1] - 62
    )
    dpg.set_item_pos(f"{tag}_loading", indicator_pos)

    dpg.focus_item(f"{tag}_filter")
    return dialog


def search_objects_dialog(
    behavior: HavokBehavior,
    pin_callback: Callable[[str, str, Any], None] = None,
    jump_callback: Callable[[str, str, Any], None] = None,
    *,
    initial_filter: str = "",
    result_callback: Callable[[str, list[HkbRecord], Any], None] = None,
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, "", 0):
        tag = dpg.generate_uuid()

    def item_to_row(item: HkbRecord):
        name = item.get_field("name", "", resolve=True)
        type_name = behavior.type_registry.get_name(item.type_id)
        return (item.object_id, name, type_name)

    def make_context_menu(item: HkbRecord):
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            autosize=True,
            on_close=lambda: dpg.delete_item(popup),
        ) as popup:
            if pin_callback:
                dpg.add_selectable(
                    label="Pin",
                    callback=lambda: pin_callback(tag, item.object_id, user_data),
                )
            if jump_callback:
                dpg.add_selectable(
                    label="Jump To",
                    callback=lambda: jump_callback(tag, item.object_id, user_data),
                )
            make_copy_menu(item)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))

    def on_results(items: list[HkbRecord]):
        if result_callback:
            result_callback(tag, items, user_data)

    return find_dialog(
        behavior.query,
        ["ID", "Name", "Type"],
        item_to_row,
        context_menu_func=make_context_menu,
        okay_callback=None,
        initial_filter=initial_filter,
        filter_help=lucene_help_text,
        on_filter_help_click=lambda: webbrowser.open(lucene_url),
        on_result_callback=on_results,
        tag=tag,
        user_data=user_data,
    )


def select_object(
    behavior: HavokBehavior,
    target_type_id: str,
    on_pointer_selected: Callable[[str, HkbRecord, Any], None],
    *,
    include_derived: bool = True,
    initial_filter: str = "",
    allow_clear: bool = True,
    title: str = None,
    tag: str = None,
    user_data: Any = None,
) -> None:
    if tag in (None, "", 0):
        tag = dpg.generate_uuid()

    # Valid objects can be cached
    if target_type_id:
        candidates = list(
            behavior.find_objects_by_type(
                target_type_id, include_derived=include_derived
            )
        )
    else:
        candidates = behavior.objects.values()

    def find_matches(filt: str) -> list[HkbRecord]:
        return query_objects(candidates, filt)

    def item_to_row(item: HkbRecord):
        name = item.get_field("name", "", resolve=True)
        type_name = behavior.type_registry.get_name(item.type_id)
        return (item.object_id, name, type_name)

    if not title:
        if target_type_id:
            target_type_name = behavior.type_registry.get_name(target_type_id)
            title = f"Select {target_type_name}"
        else:
            title = "Select Object"

    return find_dialog(
        find_matches,
        ["ID", "Name", "Type"],
        item_to_row,
        okay_callback=on_pointer_selected,
        allow_clear=allow_clear,
        initial_filter=initial_filter,
        title=title,
        filter_help=lucene_help_text,
        on_filter_help_click=lambda: webbrowser.open(lucene_url),
        tag=tag,
        user_data=user_data,
    )


def select_variable(
    behavior: HavokBehavior,
    on_variable_selected: Callable[[str, int, Any], None],
    *,
    initial_filter: str = "",
    allow_clear: bool = True,
    title: str = "Select Variable",
    tag: str = None,
    user_data: Any = None,
) -> str:
    if tag in (None, "", 0):
        tag = dpg.generate_uuid()

    variables = [
        (idx, var) for idx, var in enumerate(behavior.get_variables(full_info=True))
    ]

    def find_matches(filt: str) -> Generator[HkbVariable, None, None]:
        filt = filt.lower()
        for idx, var in variables:
            if filt in var.name.lower():
                yield (idx, var)

    def item_to_row(item: tuple[int, HkbVariable]) -> tuple[str, ...]:
        return (item[0], *[str(v) for v in item[1].astuple()])

    def on_okay(sender: str, selected: tuple[int, HkbVariable], user_data: Any):
        on_variable_selected(
            sender,
            selected[0] if selected is not None else None,
            user_data,
        )

    return find_dialog(
        find_matches,
        ["ID", "Variable", "Type", "Min", "Max"],
        item_to_row,
        okay_callback=on_okay,
        allow_clear=allow_clear,
        # item_limit=len(variables) * 1.1,
        initial_filter=initial_filter,
        title=title,
        tag=tag,
        user_data=user_data,
    )


def select_event(
    behavior: HavokBehavior,
    on_event_selected: Callable[[str, int, Any], None],
    *,
    initial_filter: str = "",
    allow_clear: bool = True,
    title: str = "Select Event",
    tag: str = None,
    user_data: Any = None,
) -> None:
    if tag in (None, "", 0):
        tag = dpg.generate_uuid()

    events = [(idx, evt) for idx, evt in enumerate(behavior.get_events())]

    def find_matches(filt: str) -> Generator[str, None, None]:
        filt = filt.lower()
        for idx, evt in events:
            if filt in evt.lower():
                yield (idx, evt)

    def item_to_row(item: tuple[int, str]) -> tuple[str, ...]:
        return item

    def on_okay(sender: str, selected: tuple[int, str], user_data: Any):
        on_event_selected(
            sender,
            selected[0] if selected is not None else None,
            user_data,
        )

    return find_dialog(
        find_matches,
        ["ID", "Event"],
        item_to_row,
        okay_callback=on_okay,
        allow_clear=allow_clear,
        # item_limit=len(events) * 1.1,
        initial_filter=initial_filter,
        title=title,
        tag=tag,
        user_data=user_data,
    )


def select_animation(
    behavior: HavokBehavior,
    on_animation_name_selected: Callable[[str, int, Any], None],
    *,
    initial_filter: str = "",
    allow_clear: bool = True,
    full_names: bool = False,
    title: str = "Select Animation Name",
    tag: str = None,
    user_data: Any = None,
) -> None:
    if tag in (None, "", 0):
        tag = dpg.generate_uuid()

    animations = [
        (idx, anim)
        for idx, anim in enumerate(behavior.get_animations(full_names=full_names))
    ]

    def find_matches(filt: str) -> Generator[str, None, None]:
        filt = filt.lower()
        for idx, anim in animations:
            if filt in anim:
                yield (idx, anim)

    def item_to_row(item: tuple[int, str]) -> tuple[str, ...]:
        return item

    def on_okay(sender: str, selected: tuple[int, str], user_data: Any):
        on_animation_name_selected(
            sender,
            selected[0] if selected is not None else None,
            user_data,
        )

    return find_dialog(
        find_matches,
        ["ID", "Animation"],
        item_to_row,
        okay_callback=on_okay,
        allow_clear=allow_clear,
        # item_limit=len(animations) * 1.1,
        initial_filter=initial_filter,
        title=title,
        tag=tag,
        user_data=user_data,
    )
