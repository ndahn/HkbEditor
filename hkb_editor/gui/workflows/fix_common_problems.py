from typing import Any, Callable
import logging
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbArray, HkbPointer
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
            for path, array in record.find_fields_by_class(HkbArray):
                # Some pointer arrays in the root objects must not be altered, so we limit
                # it to generators for now where we know how they work
                if not path.endswith("generators"):
                    continue

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

    def clear_invalid_pointers() -> int:
        invalid = 0

        for record in behavior.objects.values():
            ptr: HkbPointer
            for _, ptr in record.find_fields_by_class(HkbPointer):
                oid = ptr.get_value()
                if oid:
                    try:
                        behavior.objects[oid]
                    except KeyError:
                        ptr.set_value(None)
                        invalid += 1

        logger.info(f"Unset {invalid} invalid pointers")
        return invalid

    def remove_orphans() -> int:
        root = behavior.behavior_root
        g = behavior.build_graph(root.object_id)

        unmapped_ids = set(behavior.objects.keys()).difference(g.nodes)
        orphans = [behavior.objects[oid] for oid in unmapped_ids]

        for obj in orphans:
            behavior.delete_object(obj)

        logger.info(f"Removed {len(orphans)} abandoned objects")
        return len(orphans)

    def show_message(msg: str = None, color: style.RGBA = style.red) -> None:
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

                if dpg.get_value(f"{tag}_clear_invalid_pointers"):
                    fixes += clear_invalid_pointers()

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
            label="Remove null pointers from generators",
            default_value=True,
            tag=f"{tag}_array_null_pointers",
        )
        with dpg.tooltip(dpg.last_item()):
            add_paragraphs("Null pointers inside generator arrays can cause game crashes when accessed. When removed from manual selectors this will change array indices.")

        dpg.add_checkbox(
            label="Fix clip animation IDs",
            default_value=True,
            tag=f"{tag}_clip_animation_ids",
        )
        with dpg.tooltip(dpg.last_item()):
            add_paragraphs("ClipGenerators refer to an entry in the animations array that is not updated by ERClipGenerator. This ensures that this array contains all animations and references are valid.")

        dpg.add_checkbox(
            label="Clear invalid pointers",
            default_value=True,
            tag=f"{tag}_clear_invalid_pointers",
        )
        with dpg.tooltip(dpg.last_item()):
            add_paragraphs("Any pointers referencing non-existing object IDs will prevent converting the behavior back to havok format.")

        dpg.add_checkbox(
            label="Remove orphaned objects",
            default_value=False,
            tag=f"{tag}_remove_orphans",
        )
        with dpg.tooltip(dpg.last_item()):
            add_paragraphs("Removes all objects that are not referenced by any other object. The behavior root items are protected.")

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
