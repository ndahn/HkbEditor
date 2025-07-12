from typing import Any, Callable
import re
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray
from hkb_editor.hkb.common import CommonActionsMixin
from hkb_editor.hkb.hkb_enums import hkbClipGenerator_PlaybackMode as PlaybackMode
from hkb_editor.hkb.hkb_flags import hkbClipGenerator_Flags as ClipFlags
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.dialogs import select_animation, select_object
from hkb_editor.gui.helpers import center_window, create_flag_checkboxes, add_paragraphs
from hkb_editor.gui import style


def register_clip_dialog(
    behavior: HavokBehavior,
    callback: Callable[[str, tuple[str, str], Any], None],
    *,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    util = CommonActionsMixin(behavior)
    selected_cmsg: HkbRecord = None
    cmsg_query: str = ""

    def on_animation_selected(sender: str, animation_id: int, user_data: Any):
        nonlocal cmsg_query
        animation_name = behavior.get_animation(animation_id)
        dpg.set_value(f"{tag}_animation", animation_name)

        current_name = dpg.get_value(f"{tag}_name")
        if not current_name or re.fullmatch(r"a[0-9]{3}_[0-9]{6}", current_name):
            # Update the name only if it doesn't look as if the user changed it
            dpg.set_value(f"{tag}_name", animation_name)

        # Find CMSGs with a matching animation
        anim_id = int(animation_name.split("_")[-1])
        cmsg_query = f"animId:{anim_id}"
        first_cmsg = next(
            behavior.query("type_name:CustomManualSelectorGenerator " + cmsg_query),
            None,
        )
        if first_cmsg:
            on_cmsg_selected(sender, first_cmsg, user_data)

        # Find a clip with the same animation ID to copy some other attributes
        model_clip = next(
            behavior.query(
                f"type_name:hkbClipGenerator animationName:{animation_name}"
            ),
            None,
        )
        if model_clip:
            playback_mode = PlaybackMode(model_clip["mode"].get_value())
            dpg.set_value(f"{tag}_playback_mode", playback_mode.name)

            clip_flags = ClipFlags(model_clip["flags"].get_value())
            for flag in ClipFlags:
                flag_enabled = flag in clip_flags
                dpg.set_value(f"{tag}_clipflags_{flag.name}", flag_enabled)

    def on_cmsg_selected(sender: str, cmsg: HkbRecord, user_data: Any):
        nonlocal selected_cmsg
        selected_cmsg = cmsg
        name = cmsg["name"].get_value() if cmsg else ""
        dpg.set_value(f"{tag}_cmsg_name", name)

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def on_okay():
        clip_name = dpg.get_value(f"{tag}_name")
        animation_name = dpg.get_value(f"{tag}_animation")
        playback_mode_name = dpg.get_value(f"{tag}_playback_mode")

        if not clip_name:
            show_warning("Name not set")
            return

        if not animation_name:
            show_warning("Animation not set")
            return

        if not selected_cmsg:
            show_warning("CMSG not set")
            return

        # dpg combo only gives us the item, not the index
        playback_mode = PlaybackMode[playback_mode_name].value

        clip_flags = 0
        for flag in ClipFlags:
            if dpg.get_value(f"{tag}_clipflags_{flag.name}"):
                clip_flags |= flag

        # Do the deed
        with undo_manager.combine():
            clip = util.new_clip(
                animation_name,
                name=clip_name,
                mode=playback_mode,
                flags=clip_flags,
            )

            generators: HkbArray = selected_cmsg["generators"]
            generators.append(clip.object_id)
            undo_manager.on_update_array_item(generators, -1, None, clip.object_id)

        callback(dialog, (selected_cmsg, clip), user_data)
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
        # ClipGenerator name
        dpg.add_input_text(
            default_value="",
            label="Name",
            tag=f"{tag}_name",
        )

        # Animation name
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                default_value="",
                hint="aXXX_YYYYYY",
                readonly=True,
                tag=f"{tag}_animation",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda: select_animation(
                    behavior, on_animation_selected, allow_clear=False
                ),
            )
            dpg.add_text("Animation")

        # CMSG to register the clip in (selected from animation name)
        with dpg.group(horizontal=True):
            cmsg_type_id = behavior.type_registry.find_first_type_by_name(
                "CustomManualSelectorGenerator"
            )

            dpg.add_input_text(
                readonly=True,
                default_value="",
                tag=f"{tag}_cmsg_name",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                callback=lambda s, a, u: select_object(
                    behavior,
                    cmsg_type_id,
                    on_cmsg_selected,
                    initial_filter=cmsg_query,
                ),
            )
            dpg.add_text("CMSG")

        # Playback mode
        dpg.add_combo(
            [e.name for e in PlaybackMode],
            default_value=PlaybackMode.SINGLE_PLAY.name,
            label="Playback Mode",
            tag=f"{tag}_playback_mode",
        )

        # Flags
        with dpg.tree_node(label="Flags"):
            create_flag_checkboxes(
                ClipFlags,
                None,
                base_tag=f"{tag}_clipflags",
                active_flags=0,
            )

        # TODO instructions
        instructions = """\
Registers an animation in an existing CMSG, allowing it to be played in-game. 

See "Create CMSG" instead if you want to register an entirely new animation 
slot (that is, a TAE ID that is not used by the game yet).
"""
        add_paragraphs(instructions, 50, color=style.light_blue)

        # Main form done, now just some buttons and such
        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=(255, 0, 0))

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

    dpg.focus_item(f"{tag}_name")
    return dialog
