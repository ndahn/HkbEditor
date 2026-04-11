from typing import Any, Callable
import logging
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbArray
from hkb_editor.templates.common import Animation
from hkb_editor.gui.helpers import (
    center_window,
    add_paragraphs,
    common_loading_indicator,
)
from hkb_editor.gui import style


def fix_common_problems_dialog(
    behavior: HavokBehavior,
    callback: Callable[[None], None] = None,
    *,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = f"fix_common_problems_{dpg.generate_uuid()}"

    logger = logging.getLogger("fix_common_problems")

    def fix_array_null_pointers() -> int:
        issues = 0
        for record in behavior:
            array: HkbArray
            for _, array in record.find_fields_by_class(HkbArray):
                if array.is_pointer_array:
                    invalid = []
                    for idx, ptr in enumerate(array):
                        if not ptr.is_set():
                            invalid.append(idx)

                    for idx in reversed(invalid):
                        array.pop(idx)

                    issues += len(invalid)

        logger.info(f"Removed {issues} stray null pointers from arrays")
        return issues

    def fix_clip_animation_ids() -> int:
        issues = 0
        new_anims = 0
        for record in behavior:
            if record.type_name == "hkbClipGenerator":
                anim_name = record["animationName"].get_value()
                if not Animation.is_valid_name(anim_name):
                    logger.warning(f"{record} has invalid animationName {anim_name}")
                    continue

                anim_id = record["animationInternalId"].get_value()
                true_anim_id = behavior.find_animation(anim_name, None)

                if anim_id != true_anim_id:
                    if true_anim_id is None:
                        true_anim_id = behavior.create_animation(anim_name)
                        new_anims += 1

                    record["animationInternalId"] = true_anim_id
                    issues += 1

        logger.info(f"Added {new_anims} missing animation IDs")
        logger.info(f"Fixed {issues} clip generators")
        return issues

    def remove_orphans() -> int:
        root = behavior.behavior_root
        g = behavior.build_graph(root.object_id)

        unmapped_ids = set(behavior.objects.keys()).difference(g.nodes)
        orphans = [behavior.objects[oid] for oid in unmapped_ids]

        for obj in orphans:
            behavior.delete_object(obj)

        logger.info(f"Removed {len(orphans)} abandoned objects")
        return len(orphans)

    def show_message(msg: str = None, color: style.Color = style.red) -> None:
        if msg:
            dpg.configure_item(
                f"{tag}_notification",
                default_value=msg,
                color=color,
                show=True,
            )
        else:
            dpg.hide_item(f"{tag}_notification")

    def on_okay():
        show_message()
        loading = common_loading_indicator("Fixing")

        try:
            with behavior.transaction():
                fixes = 0
                if dpg.get_value(f"{tag}_array_null_pointers"):
                    fixes += fix_array_null_pointers()

                if dpg.get_value(f"{tag}_clip_animation_ids"):
                    fixes += fix_clip_animation_ids()

                if dpg.get_value(f"{tag}_remove_orphans"):
                    fixes += remove_orphans()

            logger.info(f"Fixed {fixes} issues")
            show_message(f"Fixed {fixes} issues", color=style.blue)
            dpg.set_item_label(f"{tag}_button_okay", "Again?")

            if callback:
                callback(tag, fixes, user_data)
        except Exception:
            show_message("Error fixing behavior, check terminal!")
            raise
        finally:
            dpg.delete_item(loading)

    # Dialog content
    with dpg.window(
        label="Fix Common Problems",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        dpg.add_checkbox(
            label="Remove null pointers from arrays",
            default_value=True,
            tag=f"{tag}_array_null_pointers",
        )
        dpg.add_checkbox(
            label="Fix clip animation IDs",
            default_value=True,
            tag=f"{tag}_clip_animation_ids",
        )
        dpg.add_checkbox(
            label="Remove orphaned objects",
            default_value=False,
            tag=f"{tag}_remove_orphans",
        )

        instructions = """\
Note that most severe issues cannot be fixed automatically. Use "Workflows -> Verify Behavior" and watch the terminal output carefully!
"""
        add_paragraphs(instructions, 50, color=style.light_blue)

        # Main form done, now just some buttons and such
        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.red)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(dialog),
            )

    dpg.split_frame()
    center_window(dialog)

    return dialog
