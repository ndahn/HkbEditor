from typing import Any, Callable
import dearpygui.dearpygui as dpg


def add_multilist(
    items: list[Any],
    callback: Callable[[str, tuple[int, Any] | list[tuple[int, Any]], Any], None],
    *,
    item_to_str: Callable[[Any], str] = str,
    width: int = 180,
    height: int = 400,
    parent: str = 0,
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if not tag:
        tag = dpg.generate_uuid()

    selected: set[tuple[int, str]] = []

    def set_item_selected(idx: int, state: bool) -> None:
        w = f"{tag}_item_{idx}"
        dpg.set_value(w, state)
        if state:
            selected.add((idx, w))
        else:
            selected.discard((idx, w))

    def clear_selected() -> None:
        for _, w in selected:
            dpg.set_value(w, False)
        selected.clear()

    def on_item_select(sender: str, state: bool, idx: int) -> None:
        key = (idx, sender)
        if not state:
            selected.discard(key)
            return

        if dpg.is_key_pressed(dpg.mvKey_ModShift):
            # Range selection
            predecessor = min(idx, max(*(i for i, _ in selected), default=idx))
            for prev in range(predecessor, idx):
                set_item_selected(prev)
        
        elif dpg.is_key_pressed(dpg.mvKey_ModCtrl):
            # Additional selection
            pass
            
        else:
            # Replace selection
            clear_selected()
        
        set_item_selected(idx)
        selected_items = sorted([(i, items[i]) for i, _ in selected])
        callback(sender, selected_items, user_data)
        
    with dpg.child_window(
        border=False, width=width, height=height, parent=parent, tag=tag
    ):
        for idx, item in items:
            dpg.add_selectable(
                label=item_to_str(item),
                width=-1,
                callback=on_item_select,
                user_data=idx,
                tag=f"{tag}_item_{idx}",
            )
