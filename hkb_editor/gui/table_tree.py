from typing import Generator, Callable, Any
from contextlib import contextmanager
import dearpygui.dearpygui as dpg


INDENT_STEP = 14  # actually depends on font size
_foldable_row_sentinel = object()


def is_foldable_row(item: str) -> bool:
    data = dpg.get_item_user_data(item)
    return isinstance(data, tuple) and data[0] == _foldable_row_sentinel


def is_row_index_visible(table, row_level: int, row_idx: int = -1) -> bool:
    rows = dpg.get_item_children(table, slot=1)
    if row_idx >= 0:
        rows = rows[:row_idx]

    for parent in reversed(rows):
        if not is_foldable_row(parent):
            return True

        _, parent_level, parent_node = dpg.get_item_user_data(parent)
        if parent_node is not None and parent_level < row_level:
            return dpg.get_value(parent_node)

    return True


def is_row_visible(table: str, row: str | int) -> bool:
    if not is_foldable_row(row):
        return True

    _, row_level, _ = dpg.get_item_user_data(row)

    rows = dpg.get_item_children(table, slot=1)
    row_idx = rows.index(row)
    return is_row_index_visible(table, row_level, row_idx)


def get_row_node_item(row: str):
    return dpg.get_item_user_data(row)[2]


def on_row_clicked(sender, value, user_data):
    # Make sure it happens quickly and without flickering
    with dpg.mutex():
        # We don't want to highlight the selectable as "selected"
        dpg.set_value(sender, False)

        table, row, callback = user_data
        _, root_level, node = dpg.get_item_user_data(row)
        is_leaf = node is not None

        # Toggle the node's "expanded" status
        if is_leaf:
            is_expanded = not dpg.get_value(node)
            dpg.set_value(node, is_expanded)

        if callback:
            callback(row, is_expanded, None)

        # All children *beyond* this level (but not on this level) will be hidden
        hide_level = 10000 if is_expanded else root_level

        rows = dpg.get_item_children(table, slot=1)
        root_idx = rows.index(dpg.get_alias_id(row))
        rows = rows[root_idx + 1 :]

        for child_row in rows:
            if not is_foldable_row(child_row):
                break

            _, child_level, child_node = dpg.get_item_user_data(child_row)

            if child_level <= root_level:
                break

            if child_level > hide_level:
                dpg.hide_item(child_row)
            else:
                dpg.show_item(child_row)
                if child_node is not None:
                    hide_level = 10000 if dpg.get_value(child_node) else child_level


@contextmanager
def table_tree_node(
    label: str,
    *,
    table: str = None,
    folded: bool = True,
    tag: str = 0,
    callback: Callable[[str, bool, Any], None] = None,
) -> Generator[str, None, None]:
    if not table:
        table = dpg.top_container_stack()

    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    cur_level = dpg.get_item_user_data(table) or 0
    tree_node = f"{tag}_foldable_row_node"
    selectable = f"{tag}_foldable_row_selectable"
    show = is_row_index_visible(table, cur_level)

    with dpg.table_row(
        parent=table,
        tag=tag,
        user_data=(_foldable_row_sentinel, cur_level, tree_node),
        show=show,
    ) as row:
        with dpg.group(horizontal=True, horizontal_spacing=0):
            dpg.add_selectable(
                span_columns=True,
                callback=on_row_clicked,
                user_data=(table, row, callback),
                tag=selectable,
            )
            dpg.add_tree_node(
                tag=tree_node,
                label=label,
                indent=cur_level * INDENT_STEP,
                default_open=not folded,
            )

    try:
        # We're not truly entering the row context, as the next node should just go into the
        # next row of the table
        dpg.set_item_user_data(table, cur_level + 1)
        yield tree_node
    finally:
        dpg.set_item_user_data(table, cur_level)


@contextmanager
def table_tree_leaf(table: str = None, tag: str = 0) -> Generator[str, None, None]:
    if not table:
        table = dpg.top_container_stack()

    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    cur_level = dpg.get_item_user_data(table) or 0
    show = is_row_index_visible(table, cur_level)

    try:
        with dpg.table_row(
            parent=table,
            tag=tag,
            user_data=(_foldable_row_sentinel, cur_level, None),
            show=show,
        ) as row:
            yield row
    finally:
        children = dpg.get_item_children(row, slot=1)
        if children:
            dpg.set_item_indent(children[0], cur_level * INDENT_STEP)
