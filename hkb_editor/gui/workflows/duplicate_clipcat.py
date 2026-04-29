from typing import Any, Callable
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.templates.common import CommonActionsMixin, Animation
from hkb_editor.gui.helpers import (
    center_window,
    add_paragraphs,
)
from hkb_editor.gui import style
from hkb_editor.gui.dialogs import select_animation


def duplicate_clipcat_dialog(
    behavior: HavokBehavior,
    callback: Callable[[str, list[HkbRecord], Any], None],
    *,
    tag: str = 0,
    user_data: Any = None,
) -> str:
    if tag in (0, "", None):
        tag = f"duplicate_clipcat_dialog_{dpg.generate_uuid()}"

    util = CommonActionsMixin(behavior)

    def on_anims_selected(sender: str, anims: list[int], user_data: Any) -> None:
        current_values = set(x for x in dpg.get_value(f"{tag}_anims").splitlines() if x)
        current_values.update(behavior.get_animation(aid) for aid in anims)
        lines = "\n".join(sorted(current_values))
        dpg.set_value(f"{tag}_anims", lines)

    def open_add_anims_dialog() -> None:
        select_animation(
            behavior,
            on_anims_selected,
            title="Select Animations",
            multiple=True,
        )

    def show_message(
        msg: str = None, color: tuple[int, int, int, int] = style.red
    ) -> None:
        if msg:
            # TODO log
            dpg.configure_item(
                f"{tag}_notification",
                default_value=msg,
                color=color,
                show=True,
            )
        else:
            dpg.hide_item(f"{tag}_notification")

    def on_okay():
        lines = dpg.get_value(f"{tag}_anims").splitlines()
        valid = set(behavior.get_animations())
        selected = []

        for anim in lines:
            anim = anim.strip()
            if not anim:
                continue

            if anim not in valid:
                show_message(f"{anim} is not an existing animation")
                return

            selected.append(anim)

        show_message()
        anim_cat: int = dpg.get_value(f"{tag}_target_category")
        replace_existing: bool = dpg.get_value(f"{tag}_replace_existing")
        copies: list[HkbRecord] = []

        with behavior.transaction():
            all_clips = behavior.query("type=hkbClipGenerator")
            for anim_name in selected:
                # Find all clips using this animation
                anim_clips = [c for c in all_clips if c["animationName"].get_value() == anim_name]
                anim = util.animation(anim_name, create=False)
                new_anim_name = Animation.make_name(anim_cat, anim.anim_id)
                
                for clip in anim_clips:
                    # Only create animation entries when there are actually clips for them
                    new_anim = util.animation(new_anim_name)

                    # Duplicate the clip in each of its parents
                    parents = behavior.get_immediate_parents(clip)
                    clip_copy = None

                    for parent in parents:
                        generators: HkbArray[HkbPointer] = parent.get_field(
                            "generators", None
                        )
                        if not generators:
                            show_message(
                                f"Could not determine generator field for {clip.object_id} in parent {parent}"
                            )
                            continue

                        skip = False
                        for ptr in generators:
                            target = ptr.get_target()
                            if target["animationName"].get_value() == new_anim_name:
                                if replace_existing:
                                    util.copy_attributes(clip, target)
                                    copies.append(target)

                                skip = True
                                break

                        if skip:
                            continue

                        # Make a copy if we don't have one already. All parents are referencing
                        # the same instance, so we will do the same.
                        if not clip_copy:
                            new_name = clip["name"].get_value().replace(
                                f"a{anim.category}_", f"a{new_anim.category}"
                            )
                            clip_copy: HkbRecord = util.make_copy(
                                clip,
                                name=new_name,
                                animationName=new_anim.name,
                                animationInternalId=new_anim.index,
                            )
                            copies.append(clip_copy)
                        
                        # Add the copy to the parent's generators
                        generators.append(clip_copy)

        callback(tag, copies, user_data)
        dpg.delete_item(dialog)

    # Dialog content
    with dpg.window(
        label="Duplicate Animation Clips",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        dpg.add_input_text(
            label="Clips",
            hint="a123_456789",
            multiline=True,
            tag=f"{tag}_anims",
        )
        dpg.add_button(
            label="Add Clips...",
            callback=open_add_anims_dialog,
        )
        dpg.add_input_int(
            label="Target Category",
            min_value=0,
            min_clamped=True,
            max_value=999,
            max_clamped=True,
            tag=f"{tag}_target_category",
        )
        dpg.add_checkbox(
            label="Replace existing",
            default_value=False,
            tag=f"{tag}_replace_existing",
        )

        dpg.add_spacer(height=3)

        instructions = """\
For each selected animation, a new animation with new category (aXXX) will be created. All ClipGenerators using them will be duplicated within their respective parents.
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
            dpg.add_checkbox(
                label="Pin created objects",
                default_value=True,
                tag=f"{tag}_pin_objects",
            )

    dpg.split_frame()
    center_window(dialog)

    dpg.focus_item(tag)
    return dialog
