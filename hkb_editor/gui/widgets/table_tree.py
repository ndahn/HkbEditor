from typing import Generator, Callable, Any
from contextlib import contextmanager
import dearpygui.dearpygui as dpg


INDENT_STEP = 14  # actually depends on font size
_foldable_row_sentinel = object()


def is_foldable_row(row: str) -> bool:
    if not dpg.does_item_exist(row):
        return False
    
    data = dpg.get_item_user_data(row)
    return isinstance(data, tuple) and data[0] == _foldable_row_sentinel


def is_foldable_row_leaf(row: str) -> bool:
    if not is_foldable_row(row):
        return False

    if not get_row_selectable_item(row):
        return True

    return False


def get_row_level(row: str, default: int = 0) -> bool:
    data = dpg.get_item_user_data(row)
    try:
        return int(data[1])
    except TypeError:
        return default


def is_row_index_visible(table, row_level: int, row_idx: int = -1) -> bool:
    rows = dpg.get_item_children(table, slot=1)
    if row_idx >= 0:
        rows = rows[:row_idx]

    for parent in reversed(rows):
        if not is_foldable_row(parent):
            return True

        _, parent_level, parent_node, _ = dpg.get_item_user_data(parent)
        if parent_node is not None and parent_level < row_level:
            return dpg.get_value(parent_node)

    return True


def is_row_visible(table: str, row: str | int) -> bool:
    if not is_foldable_row(row):
        return True

    _, row_level, _, _ = dpg.get_item_user_data(row)

    rows = dpg.get_item_children(table, slot=1)
    row_idx = rows.index(row)
    return is_row_index_visible(table, row_level, row_idx)


def get_row_node_item(row: str):
    return dpg.get_item_user_data(row)[2]


def get_row_selectable_item(row: str):
    return dpg.get_item_user_data(row)[3]


def get_foldable_child_rows(table: str, row: int | str) -> Generator[str, None, None]:
    if row in (None, "", 0):
        return

    if isinstance(row, str):
        row = dpg.get_alias_id(row)

    rows = dpg.get_item_children(table, slot=1)
    row_idx = rows.index(row)

    if row_idx >= 0:
        rows = rows[row_idx + 1 :]

    for child_row in rows:
        if not is_foldable_row(child_row):
            break

        yield child_row


def get_foldable_row_parent(table: str, row: int | str) -> int:
    if isinstance(row, str):
        row = dpg.get_alias_id(row)

    rows = dpg.get_item_children(table, slot=1)
    row_idx = rows.index(row)

    if row_idx > 0:
        rows = rows[:row_idx]

    for parent in reversed(list(rows)):
        if is_foldable_row(parent):
            return parent

    return None


def get_next_foldable_row_sibling(table: str, row: str) -> int:
    if isinstance(row, str):
        row = dpg.get_alias_id(row)

    row_level = get_row_level(row)
    rows = dpg.get_item_children(table, slot=1)
    row_idx = rows.index(row)

    if row_idx > 0:
        rows = rows[row_idx + 1 :]

    for child_row in rows:
        if get_row_level(child_row) <= row_level:
            return child_row

    return 0


def get_row_indent(table: str, row: str) -> int:
    # TODO indent of last foldable row if no row is given
    parent = get_foldable_row_parent(table, row)
    if not parent:
        return 0

    _, row_level, _, _ = dpg.get_item_user_data(parent)
    return row_level * INDENT_STEP


@contextmanager
def apply_row_indent(
    table: str,
    indent_level: int,
    parent_row: str,
    until: int | str = 0,
) -> Generator[str, None, None]:
    try:
        yield
    finally:
        children = get_foldable_child_rows(table, parent_row)

        if isinstance(until, str):
            until = dpg.get_alias_id(until)

        for child_row in children:
            if until != 0 and child_row == until:
                break

            child_row_content = dpg.get_item_children(child_row, slot=1)
            if child_row_content:
                dpg.set_item_indent(child_row_content[0], indent_level * INDENT_STEP)

            if is_foldable_row(child_row):
                data = list(dpg.get_item_user_data(child_row))
                data[1] = indent_level
                dpg.set_item_user_data(child_row, tuple(data))


def set_foldable_row_status(row: str, expanded: bool) -> None:
    if not is_foldable_row(row) or is_foldable_row_leaf(row):
        return

    selectable = get_row_selectable_item(row)
    # Will be toggled by the click function
    dpg.set_value(selectable, not expanded)
    # We basically simulate a click on the selectable
    _on_row_clicked(selectable, expanded, dpg.get_item_user_data(selectable))


def _on_row_clicked(sender, value, user_data):
    # Make sure it happens quickly and without flickering
    with dpg.mutex():
        # We don't want to highlight the selectable as "selected"
        dpg.set_value(sender, False)

        table, row, callback, cb_user_data = user_data
        _, root_level, node, _ = dpg.get_item_user_data(row)
        is_leaf = node is None
        is_expanded = not dpg.get_value(node)

        # Toggle the node's "expanded" status
        if not is_leaf:
            dpg.set_value(node, is_expanded)

        if callback:
            callback(row, is_leaf or is_expanded, cb_user_data)

        # All children *beyond* this level (but not on this level) will be hidden
        hide_level = 10000 if is_expanded else root_level

        for child_row in get_foldable_child_rows(table, row):
            _, child_level, child_node, _ = dpg.get_item_user_data(child_row)

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
    before: str = 0,
    callback: Callable[[str, bool, Any], None] = None,
    user_data: Any = None,
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
        before=before,
        user_data=(_foldable_row_sentinel, cur_level, tree_node, selectable),
        show=show,
    ) as row:
        with dpg.group(horizontal=True, horizontal_spacing=0):
            dpg.add_selectable(
                span_columns=True,
                callback=_on_row_clicked,
                user_data=(table, row, callback, user_data),
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
def table_tree_leaf(
    table: str = None,
    tag: str = 0,
    before: str = 0,
) -> Generator[str, None, None]:
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
            before=before,
            user_data=(_foldable_row_sentinel, cur_level, None, None),
            show=show,
        ) as row:
            yield row
    finally:
        children = dpg.get_item_children(row, slot=1)
        if children:
            dpg.set_item_indent(children[0], cur_level * INDENT_STEP)


def add_lazy_table_tree_node(
    label: str,
    content_callback: Callable,
    *,
    table: str = None,
    tag: str = 0,
    before: str = 0,
) -> str:
    if not table:
        table = dpg.top_container_stack()

    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    def fold_unfold_attributes(
        tree_node_row: str,
        expanded: bool,
        user_data: Any,
    ):
        anchor = get_next_foldable_row_sibling(table, tree_node_row)
        indent_level = get_row_level(tree_node_row) + 1

        if expanded:
            with apply_row_indent(table, indent_level, tree_node_row, until=anchor):
                content_callback(anchor)
        else:
            child_rows = list(get_foldable_child_rows(table, tree_node_row))

            until = anchor
            if isinstance(until, str):
                until = dpg.get_alias_id(anchor)

            for child_row in child_rows:
                if until != 0 and child_row == until:
                    break

                dpg.delete_item(child_row)

    with table_tree_node(
        label,
        table=table,
        folded=True,
        tag=tag,
        callback=fold_unfold_attributes,
        before=before,
    ) as node:
        pass

    return node
