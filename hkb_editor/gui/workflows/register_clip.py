from typing import Any, Callable
from logging import getLogger
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray
from hkb_editor.hkb.hkb_enums import hkbClipGenerator_PlaybackMode as PlaybackMode
from hkb_editor.hkb.hkb_flags import hkbClipGenerator_Flags
from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.gui.dialogs import select_animation_name
from hkb_editor.gui.helpers import center_window, create_flag_checkboxes


def open_register_clip_dialog(
    behavior: HavokBehavior,
    callback: Callable[[str, tuple[str, str], Any], None],
    *,
    tag: str = 0,
    user_data: Any = None,
) -> None:
    if tag in (0, "", None):
        tag = dpg.generate_uuid()

    cmsg_type = behavior.type_registry.find_first_type_by_name(
        "CustomManualSelectorGenerator"
    )
    clipgen_type = behavior.type_registry.find_first_type_by_name("hkbClipGenerator")
    cmsg_candidates: list[HkbRecord] = []

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def on_okay():
        clip_name = dpg.get_value(f"{tag}_name")
        animation_name = dpg.get_value(f"{tag}_animation")
        cmsg_name = dpg.get_value(f"{tag}_cmsg")
        playback_mode_name = dpg.get_value(f"{tag}_playback_mode")

        if not clip_name:
            show_warning("Name not set")
            return

        if not animation_name:
            show_warning("Animation not set")
            return

        if not cmsg_name:
            show_warning("CMSG not set")
            return

        clipgen_id = behavior.new_id()
        # Unfortunately dpg combo only gives us the item, not the index
        cmsg = next(c for c in cmsg_candidates if c["name"].get_value() == cmsg_name)
        playback_mode = PlaybackMode[playback_mode_name].value
        anim_idx = behavior.find_animation(animation_name)

        clip_flags = 0
        for flag in hkbClipGenerator_Flags:
            if dpg.get_value(f"{tag}_clipflags_{flag.name}"):
                clip_flags |= flag

        clipgen = HkbRecord.new(
            behavior,
            clipgen_type,
            {
                "name": clip_name,
                "animationName": animation_name,
                "mode": playback_mode,
                "animationInternalId": anim_idx,
                "flags": clip_flags,
            },
            clipgen_id,
        )

        with undo_manager.combine():
            # Add objects with IDs to behavior
            undo_manager.on_create_object(behavior, clipgen)
            behavior.add_object(clipgen)

            generators: HkbArray = cmsg["generators"]
            undo_manager.on_update_array_item(generators, -1, None, clipgen_id)
            generators.append(clipgen_id)

        callback(dialog, (clipgen_id, cmsg.object_id), user_data)
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

            def on_animation_selected(sender: str, animation_id: int, user_data: Any):
                nonlocal cmsg_candidates
                animation_name = behavior.get_animation(animation_id)
                dpg.set_value(f"{tag}_animation", animation_name)
                dpg.set_value(f"{tag}_name", animation_name)

                # Find CMSGs with a matching animId
                anim_id = animation_name.split("_")[1]
                cmsg_candidates = list(
                    behavior.query(f"type_id:{cmsg_type} AND animId:{anim_id}")
                )
                items = [c["name"].get_value() for c in cmsg_candidates]

                dpg.configure_item(
                    f"{tag}_cmsg",
                    items=items,
                    default_value=items[0] if items else "",
                )

            dpg.add_input_text(
                default_value="",
                hint="aXXX_YYYYYY",
                readonly=True,
                tag=f"{tag}_animation",
            )
            dpg.add_button(
                arrow=True,
                direction=dpg.mvDir_Right,
                # TODO allow creating new animations from selection dialog
                callback=lambda s, a, u: select_animation_name(*u),
                user_data=(behavior, on_animation_selected),
            )
            dpg.add_text("Animation")

        # CMSG to register the clip in (selected from animation name)
        dpg.add_combo(
            label="CMSG",
            tag=f"{tag}_cmsg",
        )

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
                hkbClipGenerator_Flags,
                None,
                base_tag=f"{tag}_clipflags",
                active_flags=0,
            )

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
