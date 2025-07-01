from typing import Any
import os
import pyperclip
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.tagfile import Tagfile
from hkb_editor.hkb.hkb_types import HkbArray, HkbRecord
from hkb_editor.hkb.skeleton import load_skeleton_bones
from hkb_editor.gui.dialogs import open_file_dialog, save_file_dialog


def open_bone_mirror_dialog(
    skeleton_path: str = None,
    character_path: str = None,
    *,
    title: str = "Generate Bone Mirror Map",
    tag: str = None,
) -> HkbArray:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    bones: list[str] = None
    mirror_info: HkbRecord = None

    def select_skeleton_file() -> None:
        path = open_file_dialog(
            title="Select Skeleton File", filetypes={"Skeleton.xml": "*.xml"}
        )

        nonlocal bones
        bones = load_skeleton_bones(path)

        if mirror_info and len(mirror_info["bonePairMap"]) != len(bones):
            dpg.set_value(f"{tag}_notification", f"Skeleton does not match loaded Character!")
            dpg.show_item(f"{tag}_notification")
            bones = None
            return

        dpg.set_value(f"{tag}_skeleton_file", path)
        fill_table()

    def select_character_file() -> None:
        path = open_file_dialog(
            title="Select Character File", filetypes={"Character/cXXXX.xml": "*.xml"}
        )

        nonlocal mirror_info
        character = Tagfile(path)
        mirror_info = character.find_first_by_type_name("hkbMirroredSkeletonInfo")

        if bones and len(mirror_info["bonePairMap"]) != len(bones):
            dpg.set_value(f"{tag}_notification", f"Character does not match loaded Skeleton!")
            dpg.show_item(f"{tag}_notification")
            mirror_info = None
            return
        
        dpg.set_value(f"{tag}_character_file", path)
        fill_table()

    def check_ready() -> bool:
        dpg.hide_item(f"{tag}_notification")

        if not bones or not mirror_info:
            if bones:
                dpg.set_value(f"{tag}_notification", f"No character loaded!")
            elif mirror_info:
                dpg.set_value(f"{tag}_notification", f"No skeleton loaded!")
            else:
                dpg.set_value(f"{tag}_notification", f"Load a skeleton and character file first!")
            
            dpg.show_item(f"{tag}_notification")
            return False

        return True

    def fill_table() -> None:
        if not check_ready():
            return

        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)
        
        pair_map = mirror_info["bonePairMap"]

        for idx, bone in enumerate(bones):
            alt_idx = pair_map[idx].get_value()
            alt_bone = bones[alt_idx]

            with dpg.table_row(
                tag=f"{tag}_bone_{idx}",
                parent=f"{tag}_table",
            ):
                dpg.add_text(str(idx))
                dpg.add_text(bone)
                # Can only contain already existing bones, use different widget 
                dpg.add_input_text(default_value=alt_bone)

    def update_mirror_info() -> None:
        if not check_ready():
            return

        pair_map: HkbArray = mirror_info["bonePairMap"]
        rows = dpg.get_item_children(f"{tag}_table", slot=1)

        try:
            for i in range(len(pair_map)):
                row = rows[i]
                # TODO different widget
                alt_bone = dpg.get_value(dpg.get_item_children(row, slot=1)[2])
                alt_idx = bones.index(alt_bone)
                pair_map[i] = alt_idx
        except ValueError:
            dpg.set_value(f"{tag}_notification", f"{alt_bone} ({i}) is not a valid bone name")
            dpg.show_item(f"{tag}_notification")

    def auto_mirror() -> None:
        if not check_ready():
            return

        pair_map: HkbArray = mirror_info["bonePairMap"]
        rows = dpg.get_item_children(f"{tag}_table", slot=1)

        for i in range(len(pair_map)):
            row = rows[i]
            bone = bones[i]

            if bone.startswith("L_"):
                alt_bone = "R_" + bone[2:]
            elif bone.startswith("R_"):
                alt_bone = "L_" + bone[2:]
            elif bone.endswith("_L"):
                alt_bone = bone[:-2] + "_R"
            elif bone.endswith("_R"):
                alt_bone = bone[:-2] + "_L"
            else:
                continue

            if alt_bone in bones:
                # TODO different widget
                dpg.set_value(dpg.get_item_children(row, slot=1)[2], alt_bone)

    def save_character() -> None:
        if not check_ready():
            return

        update_mirror_info()

        char_path = dpg.get_value(f"{tag}_character_file")
        save_file_dialog(
            title="Save Character File",
            default_dir=os.path.dirname(char_path),
            default_file=os.path.basename(char_path),
        )

    def copy_to_clipboard() -> None:
        if not check_ready():
            return

        update_mirror_info()
        pyperclip.copy(mirror_info.xml())

    with dpg.window(
        label=title,
        width=600,
        height=900,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        with dpg.group(horizontal=True, width=400):
            dpg.add_input_text(
                default_value=skeleton_path or "",
                readonly=True,
                tag=f"{tag}_skeleton_file",
            )
            dpg.add_button(label="Load Skeleton...", callback=select_skeleton_file)

        with dpg.group(horizontal=True, width=400):
            dpg.add_input_text(
                default_value=character_path or "",
                readonly=True,
                tag=f"{tag}_character_file",
            )
            dpg.add_button(label="Load Character...", callback=select_character_file)

        dpg.add_separator()

        with dpg.table(tag=f"{tag}_table", height=500, scrollY=True):
            dpg.add_table_column(label="Index", width=50, width_fixed=True)
            dpg.add_table_column(label="Bone")
            dpg.add_table_column(label="Mirrored")

        dpg.add_separator()

        instructions = """\
This dialog allows you to generate a 'hkbMirroredSkeletonInfo', which is an array
in Character/cXXXX.hkb that is used when using clips with the MIRROR flag enabled.

To the correct bone pairings (i.e. left/right), load a Skeleton file and the 
Character/cXXXX.hkx from an unpacked behavior (both have to be converted to XML). 
Then hit 'Auto Mirror' and/or adjust manually as needed. You can directly write 
back to the Character file, or copy to clipboard to use otherwise. 

Note that the object ID and type IDs may be different when inserting into other 
behaviors or games.\
"""
        with dpg.group():
            for line in instructions.split("\n"):
                dpg.add_text(line)

        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=(255, 0, 0))

        with dpg.group(horizontal=False):
            dpg.add_button(label="Auto Mirror", callback=auto_mirror)
            dpg.add_button(label="Copy XML", callback=copy_to_clipboard)
            dpg.add_button(label="Save...", callback=save_character)

    # Fill table if we already have everything
    if skeleton_path:
        bones = load_skeleton_bones(skeleton_path)

    if character_path:
        character = Tagfile(character_path)
        mirror_info = character.find_first_by_type_name("hkbMirroredSkeletonInfo")

    if bones and mirror_info:
        fill_table()
