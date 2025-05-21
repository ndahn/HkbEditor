from typing import Any, Callable
from logging import getLogger
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import (
    XmlValueHandler,
    HkbArray,
    HkbString,
    HkbInteger,
    HkbFloat,
    HkbBool,
    get_value_handler
)
from hkb_editor.gui.workflows.undo import undo_manager


_logger = getLogger(__name__)


def edit_simple_array_dialog(
    array: HkbArray,
    title: str = "Edit Array",
    *,
    on_change: Callable[[HkbArray, int, Any], bool] = None,
    on_add: Callable[[HkbArray, Any], bool] = None,
    on_delete: Callable[[HkbArray, int], bool] = None,
    #on_insert: Callable[[HkbArray, int, Any], bool] = None,
    #on_move: Callable[[HkbArray, int, int], bool] = None,
) -> None:
    def update_entry(sender, new_value: Any, index: int):
        old_value = array[index].get_value()
        if on_change:
            veto = on_change(array, index, new_value)
            if veto:
                dpg.set_value(sender, array[index].get_value())
                return

        undo_manager.on_update_value(array[index], old_value, new_value)
        array[index].set_value(new_value)

    def get_new_entry_value(sender, app_data, callback: Callable):
        Handler = get_value_handler(array.element_type_id)
        val = Handler.new(array.element_type_id)

        def on_value_update(sender, app_data, user_data):
            val.set_value(app_data)

        def on_okay():
            if not val.get_value():
                return
            
            callback(sender, val, None)
            dpg.delete_item(wnd)

        with dpg.window(
            modal=True,
            label="New Entry",
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            add_value_widget(-1, val, on_value_update)
            
            with dpg.group(horizontal=True):
                dpg.add_button(label="Okay", callback=on_okay)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(wnd))

    def add_entry(sender, app_data, user_data):
        if on_add:
            veto = on_add(array, app_data)
            if veto:
                return

        Handler = get_value_handler(array.element_type_id)
        val = Handler.new(array.element_type_id, app_data)
        
        undo_manager.on_update_array_item(array, -1, None, val)
        array.append(val)
        
        fill_table()
        dpg.split_frame()
        dpg.set_y_scroll(table, dpg.get_y_scroll_max(table))

    def delete_entry(sender, app_data, index: int):
        if on_delete:
            veto = on_delete(array, index)
            if veto:
                return

        undo_manager.on_update_array_item(array, -1, array[index], None)
        del array[index]
        fill_table()

    # TODO insert, move

    def fill_table():
        dpg.delete_item(table, children_only=True, slot=1)

        for idx, item in enumerate(array):
            with dpg.table_row(filter_key=f"{idx}:{item.get_value()}", parent=table):
                dpg.add_text(str(idx))
                add_value_widget(idx, item, update_entry)
                dpg.add_button(
                    label="(-)", 
                    small=True, 
                    callback=delete_entry, 
                    user_data=idx,
                )

    def add_value_widget(idx: int, val: XmlValueHandler, callback):
        if isinstance(val, HkbString):
            dpg.add_input_text(
                callback=callback,
                user_data=idx,
                default_value=val.get_value(),
            )
        elif isinstance(val, HkbInteger):
            dpg.add_input_int(
                callback=callback,
                user_data=idx,
                default_value=val.get_value(),
            )
        elif isinstance(val, HkbFloat):
            dpg.add_input_double(
                callback=callback,
                user_data=idx,
                default_value=val.get_value(),
            )
        elif isinstance(val, HkbBool):
            dpg.add_checkbox(
                callback=callback,
                user_data=idx,
                default_value=val.get_value(),
            )
        else:
            _logger.warning("Unknown array value type %s", type(val))

    with dpg.window(
        width=600,
        height=400,
        label=title,
        #modal=True,
        on_close=lambda: dpg.delete_item(dialog),
    ) as dialog:
        dpg.add_input_text(
            hint="Filter Entries",
            callback=lambda s, a, u: dpg.set_value(table, dpg.get_value(s)),
        )

        dpg.add_separator()

        with dpg.table(
            delay_search=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchSame,
            scrollY=True,
            height=310,
        ) as table:
            dpg.add_table_column(label="Index")
            dpg.add_table_column(label="Name", width_stretch=True)
            dpg.add_table_column()

        dpg.add_separator()

        dpg.add_button(
            label="Add...",
            #small=True,
            callback=get_new_entry_value,
            user_data=add_entry,
        )

    fill_table()
