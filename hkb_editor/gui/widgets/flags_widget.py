from typing import Any, Type, Callable
from enum import IntFlag
import logging
from dearpygui import dearpygui as dpg


def add_flag_checkboxes(
    flag_type: Type[IntFlag],
    callback: Callable[[str, int, Any], None],
    *,
    readonly: bool = False,
    base_tag: str = 0,
    parent: str = 0,
    active_flags: int = 0,
    user_data: Any = None,
) -> str:
    if base_tag in (None, 0, ""):
        base_tag = dpg.generate_uuid()

    zero_name = flag_type(0).name or "DISABLED"

    def on_flag_changed(sender: str, checked: bool, flag: IntFlag):
        nonlocal active_flags

        if checked:
            # Checking 0 will disable all other flags
            if flag == 0:
                active_flags = flag_type(0)
            else:
                active_flags |= flag
        else:
            # Prevent disabling 0
            if flag == 0:
                dpg.set_value(f"{base_tag}_{zero_name}", True)
                return

            active_flags &= ~flag

        # Flags are not required to have a 0 mapping
        if dpg.does_item_exist(f"{base_tag}_{zero_name}"):
            # 0 disables all other flags and enables 0
            if active_flags == 0:
                for flag in flag_type:
                    dpg.set_value(f"{base_tag}_{flag.name}", False)
                dpg.set_value(f"{base_tag}_{zero_name}", True)
            # 0 is disabled by any other flag
            else:
                dpg.set_value(f"{base_tag}_{zero_name}", False)

        dpg.set_value(f"{base_tag}_numeric", active_flags)

        if callback:
            callback(base_tag, active_flags, user_data)

    def set_from_int(sender: str, new_value: int, user_data: Any):
        new_flags = flag_type(new_value)
        for flag in flag_type:
            active = flag in new_flags
            if flag.value == 0 and new_flags > 0:
                active = False

            dpg.set_value(f"{base_tag}_{flag.name}", active)
            on_flag_changed(sender, active, flag)

    if not isinstance(active_flags, flag_type):
        try:
            active_flags = flag_type(active_flags)
        except ValueError:
            logging.getLogger(__name__).error(
                f"{active_flags} is not valid for flag type {flag_type.__name__}"
            )
            active_flags = 0

    with dpg.group(parent=parent, tag=base_tag):
        dpg.add_input_int(
            default_value=active_flags,
            callback=set_from_int,
            readonly=readonly,
            enabled=not readonly,
            tag=f"{base_tag}_numeric",
        )

        for flag in flag_type:
            if flag == 0:
                # 0 is in every flag
                active = active_flags == 0
            else:
                active = flag in active_flags

            dpg.add_checkbox(
                default_value=active,
                callback=on_flag_changed,
                enabled=not readonly,
                label=flag.name,
                tag=f"{base_tag}_{flag.name}",
                user_data=flag,
            )

    return base_tag
