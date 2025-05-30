from typing import Any, Callable
from dearpygui import dearpygui as dpg


def select_simple_array_item_dialog(
    items: list[tuple | str],
    columns: list[str],
    callback: Callable[[str, int, Any], None],
    selected: int = -1,
    *,
    show_index: bool = True,
    title: str = "Select Item",
    user_data: Any = None,
    tag: str = 0,
    **kwargs
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    def on_select(sender, app_data, index: int):
        nonlocal selected
        if index == selected:
            return

        selected = index

        # Deselect all other selectables
        for row in dpg.get_item_children(table, slot=1):
            if dpg.get_item_user_data(row) != index:
                dpg.set_value(dpg.get_item_children(row, slot=1)[0], False)

    def on_okay():
        if selected < 0:
            return

        callback(dialog, selected, user_data)
        dpg.delete_item(dialog)

    def on_cancel():
        dpg.delete_item(dialog)

    with dpg.window(
        width=600,
        height=400,
        label=title,
        tag=tag,
        on_close=lambda: dpg.delete_item(dialog),
        **kwargs,
    ) as dialog:
        dpg.add_input_text(
            hint="Find Object...",
            callback=lambda s, a, u: dpg.set_value(table, dpg.get_value(s)),
        )

        dpg.add_separator()

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            scrollY=True,
            height=310,
            clipper=True,
            tag=f"{tag}_table",
        ) as table:
            if show_index:
                dpg.add_table_column(label="Index")
            else:
                dpg.add_table_column(no_header_label=True, width=1)
            
            dpg.add_table_column(label=columns[0], width_stretch=True)
            for col in columns[1:]:
                dpg.add_table_column(label=col)

            for item_idx, item in enumerate(items):
                if not isinstance(item, (tuple, list)):
                    item = (item,)

                key = ",".join(f"{col}:{val}" for col, val in zip(columns, item))

                with dpg.table_row(filter_key=key, user_data=item_idx):
                    dpg.add_selectable(
                        label=str(item_idx) if show_index else "",
                        span_columns=True,
                        default_value=(item_idx == selected),
                        callback=on_select,
                        user_data=item_idx,
                        tag=f"{tag}_item_selectable_{item_idx}",
                    )

                    for val in item:
                        dpg.add_text(str(val))
    
        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Okay",
                callback=on_okay,
            )
            dpg.add_button(
                label="Cancel",
                callback=on_cancel,
            )
