from typing import Any, Callable, Annotated
import logging
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbRecord
from hkb_editor.hkb.hkb_enums import hkbClipGenerator_PlaybackMode as PlaybackMode
from hkb_editor.hkb.hkb_flags import hkbClipGenerator_Flags as ClipFlags
from hkb_editor.templates.common import CommonActionsMixin, Animation
from hkb_editor.gui.dialogs import select_animation
from hkb_editor.gui.helpers import center_window, add_paragraphs, create_value_widget
from hkb_editor.gui import style


def register_clips_dialog(
    behavior: HavokBehavior,
    callback: Callable[[str, tuple[str, str], Any], None],
    *,
    active_cmsg: HkbRecord | str = None,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = f"register_clip_dialog_{dpg.generate_uuid()}"

    util = CommonActionsMixin(behavior)
    active_cmsg = util.resolve_object(active_cmsg)

    values = {
        "animations": [],
        "cmsg": active_cmsg,
        "playback_mode": PlaybackMode.SINGLE_PLAY.name,
        "flags": ClipFlags.NONE,
    }

    def on_value_change(sender: str, value: Any, key: Any):
        if key == "animations" and isinstance(value, str):
            value = value.splitlines()

        values[key] = value

    def check_animations():
        lines: list[str] = values["animations"]
        valid_anims = []
        for n in lines:
            if Animation.is_valid_name(n):
                valid_anims.append(n)

        if not valid_anims:
            return

        prev_id = ""

        for anim in valid_anims:
            anim_id = anim.split("_")[-1]
            if prev_id and anim_id != prev_id:
                logging.warning("Animations should have the same IDs")
                break
            prev_id = anim_id

        cmsg: HkbRecord = values["cmsg"]
        if cmsg and cmsg["animId"].get_value() != prev_id:
            cmsg_anim_id = cmsg["animId"].get_value()
            logging.warning(f"CMSG with animId={cmsg_anim_id} does not match animations")

    def on_animation_selected(sender: str, animation_id: int, user_data: Any):
        new_anim = util.animation(animation_id)
        animations: list[Animation] = values["animations"]

        for anim in animations:
            if anim == new_anim:
                return
            
        animations.append(new_anim.name)
        dpg.set_value(f"{tag}_animations", "\n".join(str(v) for v in animations))
        on_value_change(sender, animations, "animations")

    def show_warning(msg: str) -> None:
        if msg:
            dpg.set_value(f"{tag}_notification", msg)
            dpg.show_item(f"{tag}_notification")
        else:
            dpg.hide_item(f"{tag}_notification")

    def on_okay():
        anim_lines: list[str] = values["animations"]
        cmsg: HkbRecord = values["cmsg"]
        playback_mode_val: str = values["playback_mode"]
        flags = ClipFlags(values["flags"])

        playback_mode = PlaybackMode[playback_mode_val]

        if not anim_lines:
            show_warning("No animations added")
            return

        for line in anim_lines:
            if line and not Animation.is_valid_name(line):
                show_warning(f"Invalid animation {line}")
                return

        if not cmsg:
            show_warning("CMSG not set")
            return

        check_animations()

        # Do the deed
        clips = []
        with behavior.transaction():
            for line in anim_lines:
                if not line:
                    continue

                animation = util.animation(line)
                clip = util.new_clip(
                    animation,
                    mode=playback_mode,
                    flags=flags,
                )

                cmsg["generators"].append(clip)
                clips.append(clip)

        callback(dialog, (cmsg, clips), user_data)  
        dpg.delete_item(dialog)

    # Dialog content
    with dpg.window(
        label="Register Clip",
        width=400,
        height=600,
        autosize=True,
        on_close=lambda: dpg.delete_item(dialog),
        no_saved_settings=True,
        tag=tag,
    ) as dialog:
        # Animation name
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                hint="aXXX_YYYYYY",
                multiline=True,
                callback=on_value_change,
                default_value="\n".join(str(v) for v in values["animations"]),
                tag=f"{tag}_animations",
                user_data="animations",
            )
            dpg.add_button(
                label="+",
                callback=lambda: select_animation(
                    behavior, on_animation_selected, allow_clear=False
                ),
            )
            dpg.add_text("Animations")
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Animations to register, one animation per line")

        # CMSG to register the clip in (selected from animation name)
        create_value_widget(
            behavior,
            Annotated[HkbRecord, "CustomManualSelectorGenerator"],
            "CMSG",
            on_value_change,
            default=values["cmsg"],
            tag=f"{tag}_cmsg",
            user_data="cmsg",
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("CMSG to add the clips to")

        # Clip playback mode
        create_value_widget(
            behavior,
            PlaybackMode,
            "Playback Mode",
            on_value_change,
            default=values["playback_mode"],
            tag=f"{tag}_playback_mode",
            user_data="playback_mode",
        )

        # Flags
        with dpg.tree_node(label="Flags"):
            create_value_widget(
                behavior,
                ClipFlags,
                "Flags",
                on_value_change,
                default=values["flags"],
                tag=f"{tag}_flags",
                user_data="flags",
            )

        instructions = """\
Registers one or more animations in an existing CMSG. All animations should have the same ID (the Y part of aXXX_YYYYYY), and the ID should be compatible with the CMSG's animId.

See "Create Slot" instead if you want to setup an animation ID for which no CMSG exists yet.
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

    dpg.focus_item(f"{tag}_animations")
    return dialog
