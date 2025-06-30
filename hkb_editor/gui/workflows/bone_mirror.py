from typing import Any
import pyperclip
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.tagfile import Tagfile
from hkb_editor.hkb.hkb_types import HkbArray
from hkb_editor.hkb.skeleton import load_boneweight_array
from hkb_editor.gui.dialogs import open_file_dialog


def open_bone_mirror_dialog(
    tagfile: Tagfile,
    skeleton_path: str = None,
    *,
    title: str = "Generate Bone Mirror Map",
    tag: str = None,
) -> HkbArray:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    bones = []

    def select_skeleton_file() -> str:
        return open_file_dialog(
            title="Select Skeleton", filetypes={"Skeleton files": "*.xml"}
        )

    def load_skeleton(skeleton_path: str) -> None:
        nonlocal bones
        
        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)
        bones = [b["name"] for b in load_boneweight_array(skeleton_path)]

        for idx, bone in enumerate(bones):
            with dpg.table_row(
                tag=f"{tag}_bone_{idx}",
                parent=f"{tag}_table",
            ):
                dpg.add_text(str(idx))
                dpg.add_text(bone)
                dpg.add_input_text(
                    default_value=get_mirror(bone),
                )

    def get_mirror(bone_name: str) -> str:
        if bone_name.startswith("L_"):
            return "R_" + bone_name[2:]

        if bone_name.startswith("R_"):
            return "L_" + bone_name[2:]

        if bone_name.endswith("_L"):
            return bone_name[:-2] + "_R"

        if bone_name.endswith("_R"):
            return bone_name[:-2] + "_L"

        return ""

    def copy_mirror_map() -> None:
        mirrored_bones = {}

        for row in dpg.get_item_children(f"{tag}_table", slot=1):
            alt_bone = dpg.get_value(dpg.get_item_children(row, slot=1)[2])
            if alt_bone:
                idx = int(dpg.get_value(dpg.get_item_children(row, slot=1)[0]))
                alt_idx = bones.index(alt_bone)
                mirrored_bones[idx] = alt_idx
        
        # TODO what type are we producing?
        skeleton_type_id = tagfile.type_registry.find_first_type_by_name("hkaSkeleton")
        # TODO create proper values from mirrored_bones 
        mirror = HkbArray.new(tagfile, skeleton_type_id, mirrored_bones)
        
        pyperclip.copy(mirror.xml())

    with dpg.window(
        label=title,
        width=400,
        height=800,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                default_value=skeleton_path,
                readonly=True,
                hint="Skeleton path",
                tag=f"{tag}_skeleton_path",
            )
            dpg.add_button(label="Load Skeleton...", callback=select_skeleton_file)

        with dpg.table(tag=f"{tag}_table"):
            dpg.add_table_column(label="Index")
            dpg.add_table_column(label="Bone")
            dpg.add_table_column(label="Mirrored")

        instructions = """\
TODO
"""
        with dpg.group():
            for line in instructions.split("\n"):
                dpg.add_text(line)

        dpg.add_button(label="Copy to Clipboard", callback=copy_mirror_map)

    if skeleton_path:
        load_skeleton(skeleton_path)
