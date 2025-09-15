from typing import Generator
import os
import io
import csv
import pyperclip
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.tagfile import Tagfile
from hkb_editor.hkb.hkb_types import HkbArray, HkbRecord
from hkb_editor.hkb.skeleton import load_skeleton_bones
from hkb_editor.gui.dialogs import open_file_dialog, save_file_dialog, find_dialog
from hkb_editor.gui.helpers import add_paragraphs
from hkb_editor.gui import style


def bone_mirror_dialog(
    skeleton_path: str = None,
    character_path: str = None,
    *,
    title: str = "Generate Bone Mirror Map",
    tag: str = None,
) -> HkbArray:
    if tag in (None, 0, ""):
        tag = f"bone_mirror_dialog_{dpg.generate_uuid()}"

    bones: list[str] = None
    mirror_info: HkbRecord = None

    def select_skeleton_file() -> None:
        path = open_file_dialog(
            title="Select Skeleton File", filetypes={"Skeleton.xml": "*.xml"}
        )

        if not path:
            return

        nonlocal bones
        bones = load_skeleton_bones(path)

        if mirror_info and len(mirror_info["bonePairMap"]) != len(bones):
            dpg.set_value(
                f"{tag}_notification", f"Skeleton does not match loaded Character!"
            )
            dpg.show_item(f"{tag}_notification")
            bones = None
            return

        dpg.set_value(f"{tag}_skeleton_file", path)
        fill_table()

    def select_character_file() -> None:
        path = open_file_dialog(
            title="Select Character File", filetypes={"Character/cXXXX.xml": "*.xml"}
        )

        if not path:
            return

        nonlocal mirror_info
        character = Tagfile(path)
        mirror_info = character.find_first_by_type_name("hkbMirroredSkeletonInfo")

        if bones and len(mirror_info["bonePairMap"]) != len(bones):
            dpg.set_value(
                f"{tag}_notification", f"Character does not match loaded Skeleton!"
            )
            dpg.show_item(f"{tag}_notification")
            mirror_info = None
            return

        dpg.set_value(f"{tag}_character_file", path)
        fill_table()

    def is_bones_loaded() -> bool:
        dpg.hide_item(f"{tag}_notification")

        if not bones:
            dpg.set_value(f"{tag}_notification", f"No skeleton loaded!")
            dpg.show_item(f"{tag}_notification")
            return False

        return True

    def is_character_loaded() -> bool:
        dpg.hide_item(f"{tag}_notification")

        if not mirror_info:
            dpg.set_value(f"{tag}_notification", f"No character loaded!")
            dpg.show_item(f"{tag}_notification")
            return False

        return True

    def fill_table() -> None:
        if not is_bones_loaded():
            return

        dpg.delete_item(f"{tag}_table", slot=1, children_only=True)

        if mirror_info:
            pair_map = mirror_info["bonePairMap"]

        for idx, bone in enumerate(bones):
            if mirror_info:
                alt_idx = pair_map[idx].get_value()
                alt_bone = bones[alt_idx]
            else:
                alt_bone = bone

            with dpg.table_row(
                tag=f"{tag}_bone_{idx}",
                parent=f"{tag}_table",
            ):
                dpg.add_text(str(idx))
                dpg.add_text(bone)
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        default_value=alt_bone,
                        readonly=True,
                        tag=f"{tag}_alt_bone_{idx}",
                    )
                    dpg.add_button(
                        arrow=True,
                        direction=dpg.mvDir_Right,
                        callback=lambda s, a, u: select_mirror_bone(u),
                        user_data=idx,
                    )

    def select_mirror_bone(bone_idx: int) -> str:
        dialog = f"{tag}_select_mirror_bone"
        if dpg.does_item_exist(dialog):
            dpg.focus_item(dialog)
            return

        def on_bone_selected(sender: str, item: tuple[int, str], user_data) -> None:
            alt_bone = item[1]
            dpg.set_value(f"{tag}_alt_bone_{bone_idx}", alt_bone)

        def find_bones(filt: str) -> Generator[str, None, None]:
            filt = filt.lower()
            for idx, bone in enumerate(bones):
                if filt in bone.lower():
                    yield (idx, bone)

        find_dialog(
            find_bones,
            ["Index", "Bone"],
            lambda item: item,
            okay_callback=on_bone_selected,
            title="Select Mirror Bone",
            tag=dialog,
        )

    def update_mirror_info() -> None:
        if not is_bones_loaded() or not is_character_loaded():
            return

        pair_map: HkbArray = mirror_info["bonePairMap"]

        try:
            for idx in range(len(pair_map)):
                alt_bone = dpg.get_value(f"{tag}_alt_bone_{idx}")
                alt_idx = bones.index(alt_bone)
                pair_map[idx] = alt_idx
        except ValueError:
            dpg.set_value(
                f"{tag}_notification", f"{alt_bone} ({idx}) is not a valid bone name"
            )
            dpg.show_item(f"{tag}_notification")

    def auto_mirror() -> None:
        if not is_bones_loaded():
            return

        for idx, bone in enumerate(bones):
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
                dpg.set_value(f"{tag}_alt_bone_{idx}", alt_bone)

    def copy_csv() -> None:
        if not is_bones_loaded():
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["idx", "bone", "mirror_idx", "mirror_bone"])
        rows = dpg.get_item_children(f"{tag}_table", slot=1)

        for idx, (row, bone) in enumerate(zip(rows, bones)):
            alt_bone = dpg.get_value(dpg.get_item_children(row, slot=1)[2])
            alt_idx = bones.index(alt_bone)
            writer.writerow([idx, bone, alt_idx, alt_bone])

        pyperclip.copy(output.getvalue())

    def copy_xml() -> None:
        if not is_bones_loaded() or not is_character_loaded():
            return

        update_mirror_info()
        pyperclip.copy(mirror_info.xml())

    def save_character() -> None:
        if not is_bones_loaded() or not is_character_loaded():
            return

        update_mirror_info()

        char_path = dpg.get_value(f"{tag}_character_file")
        dest_file = save_file_dialog(
            title="Save Character File",
            default_dir=os.path.dirname(char_path),
            default_file=os.path.basename(char_path),
        )

        mirror_info.tagfile.save_to_file(dest_file)

    with dpg.window(
        label=title,
        width=600,
        height=900,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(window),
    ) as window:
        with dpg.group(horizontal=True, width=300):
            dpg.add_input_text(
                default_value=skeleton_path or "",
                readonly=True,
                tag=f"{tag}_skeleton_file",
            )
            dpg.add_button(label="Load Skeleton...", callback=select_skeleton_file)

        with dpg.group(horizontal=True, width=300):
            dpg.add_input_text(
                default_value=character_path or "",
                readonly=True,
                tag=f"{tag}_character_file",
            )
            dpg.add_button(
                label="Load Pairings from Character...", callback=select_character_file
            )

        dpg.add_separator()

        with dpg.table(
            tag=f"{tag}_table",
            height=500,
            scrollY=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            dpg.add_table_column(label="Index", width=100)
            dpg.add_table_column(label="Bone")
            dpg.add_table_column(label="Mirrored")

        dpg.add_separator()

        instructions = """\
This dialog allows you to generate a 'hkbMirroredSkeletonInfo', which is an array
in Character/cXXXX.hkb that is used for clips with the MIRROR flag enabled.

To generate the correct left/right pairings, load a Skeleton and hit 'Auto Mirror' 
or adjust manually as needed. You can also load pairings from a Character file
(e.g. Character/c0000.xml from an unpacked behavior).

Note that the object ID and type IDs may differ between characters and games.\
"""
        add_paragraphs(instructions, 90, color=style.light_blue)

        dpg.add_button(label="Auto Mirror", callback=auto_mirror)
        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.red)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Copy CSV", callback=copy_csv)
            dpg.add_button(label="Copy XML", callback=copy_xml)
            dpg.add_button(label="Save...", callback=save_character)

    # Fill table if we already have everything
    if skeleton_path:
        bones = load_skeleton_bones(skeleton_path)

    if character_path:
        character = Tagfile(character_path)
        mirror_info = character.find_first_by_type_name("hkbMirroredSkeletonInfo")

    if bones and mirror_info:
        fill_table()

    return window
