from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import HkbRecord


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
                callback=lambda: dpg.delete_item(dialog),
            )


def select_pointer(
    behavior: HavokBehavior,
    target_type_id: str,
    callback: Callable[[str, str, Any], None], 
    *,
    include_derived: bool = True,
    title: str = None,
    user_data: Any = None,
) -> None:
    def on_pointer_selected(sender: str, idx: int, candidates: list[HkbRecord]):
        new_value = candidates[idx].object_id
        callback(sender, new_value, user_data)

    candidates = list(behavior.find_objects_by_type(target_type_id, include_derived=include_derived))
    items = [
        (c.object_id, c.get_field("name", "", resolve=True), c.type_name)
        for c in candidates
    ]

    if not title:
        target_type_name = behavior.type_registry.get_name(target_type_id)
        title = f"Select {target_type_name}"

    select_simple_array_item_dialog(
        items,
        ["ID", "Name", "Type"],
        on_pointer_selected,
        title=title,
        user_data=candidates,
    )


def select_variable(
    behavior: HavokBehavior,
    callback: Callable[[str, int, Any], None],
    *,
    selected: int = -1,
    title: str = "Select Variable",
    user_data: Any = None,
) -> None:
    variables = [
        (v.name, v.vtype.name, v.vmin, v.vmax) for v in behavior.get_variables()
    ]

    select_simple_array_item_dialog(
        variables,
        ["Variable", "Type", "Min", "Max"],
        callback,
        selected=selected,
        title=title,
        user_data=user_data,
    )


def select_event(
    behavior: HavokBehavior,
    callback: Callable[[str, int, Any], None],
    *,
    selected: int = -1,
    title: str = "Select Event",
    user_data: Any = None,
) -> None:
    events = [
        (e,) for e in behavior.get_events()
    ]

    select_simple_array_item_dialog(
        events,
        ["Name"],
        callback,
        selected=selected,
        title=title,
        user_data=user_data,
    )


def select_animation_name(
    behavior: HavokBehavior,
    callback: Callable[[str, int, Any], None],
    *,
    full_names: bool = False,
    selected: int = -1,
    title: str = "Select Animation Name",
    user_data: Any = None,
) -> None:
    events = [
        (a,) for a in behavior.get_animations(full_names=full_names)
    ]

    select_simple_array_item_dialog(
        events,
        ["Name"],
        callback,
        selected=selected,
        title=title,
        user_data=user_data,
    )
