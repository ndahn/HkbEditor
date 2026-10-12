from typing import Generator
import os
import pyperclip
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.tagfile import Tagfile
from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.hkb.skeleton import load_skeleton_bones
from hkb_editor.gui import style
from hkb_editor.gui.widgets import DpgItem, add_paragraphs
from hkb_editor.workflows.mirror_skeleton import (
    auto_mirror_bones,
    update_bone_pair_map,
    bone_pairs_to_csv,
)
from .file_dialog import open_file_dialog, save_file_dialog
from .find_object_dialog import find_dialog


_instructions = """\
This dialog allows you to generate a 'hkbMirroredSkeletonInfo', which is an array
in Character/cXXXX.hkb that is used for clips with the MIRROR flag enabled.

To generate the correct left/right pairings, load a Skeleton and hit 'Auto Mirror'
or adjust manually as needed. You can also load pairings from a Character file
(e.g. Character/c0000.xml from an unpacked behavior).

Full instructions:
https://ndahn.github.io/HkbEditor/howto/tools/mirror_skeleton/\
"""


class mirror_skeleton_dialog(DpgItem):
    """Build the left/right bone pairings of a ``hkbMirroredSkeletonInfo``.

    Loads bone names from a Skeleton.xml and, optionally, existing pairings
    from a Character file. Pairings can be guessed from the bone names or
    edited per row, then copied out as CSV/XML or written back to a file.

    Parameters
    ----------
    skeleton_path : str, optional
        Skeleton.xml to load right away.
    character_path : str, optional
        Character file to load existing pairings from.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    """

    def __init__(
        self,
        skeleton_path: str = None,
        character_path: str = None,
        *,
        title: str = "Mirror Skeleton",
        tag: str = None,
    ) -> None:
        super().__init__(tag)

        self._bones: list[str] = None
        self._mirror_info: HkbRecord = None
        self._window: str = None
        self._bone_dialog: find_dialog = None

        self._build(title, skeleton_path, character_path)

        # Fill table if we already have everything
        if skeleton_path:
            self._bones = load_skeleton_bones(skeleton_path)

        if character_path:
            character = Tagfile(character_path)
            self._mirror_info = character.find_first_by_type_name(
                "hkbMirroredSkeletonInfo"
            )

        if self._bones and self._mirror_info:
            self.fill_table()

    def destroy(self) -> None:
        # The bone picker is a root level window and outlives us
        if self._bone_dialog is not None:
            self._bone_dialog.destroy()
            self._delete_item(self._bone_dialog.tag)
            self._bone_dialog = None

    # === Build ========================================================

    def _build(
        self, title: str, skeleton_path: str, character_path: str
    ) -> None:
        with dpg.window(
            label=title,
            width=600,
            height=900,
            autosize=True,
            no_saved_settings=True,
            tag=self._tag,
            on_close=self.close,
        ) as self._window:
            with dpg.group(horizontal=True, width=300):
                dpg.add_input_text(
                    default_value=skeleton_path or "",
                    readonly=True,
                    tag=self._t("skeleton_file"),
                )
                dpg.add_button(
                    label="Load Skeleton...",
                    callback=self._on_select_skeleton,
                )

            with dpg.group(horizontal=True, width=300):
                dpg.add_input_text(
                    default_value=character_path or "",
                    readonly=True,
                    tag=self._t("character_file"),
                )
                dpg.add_button(
                    label="Load Pairings from Character...",
                    callback=self._on_select_character,
                )

            dpg.add_separator()

            with dpg.table(
                tag=self._t("table"),
                height=500,
                scrollY=True,
                policy=dpg.mvTable_SizingStretchProp,
            ):
                dpg.add_table_column(label="Index", width=100)
                dpg.add_table_column(label="Bone")
                dpg.add_table_column(label="Mirrored")

            dpg.add_separator()
            add_paragraphs(_instructions, 90, color=style.light_blue)

            dpg.add_button(label="Auto Mirror", callback=self.auto_mirror)
            dpg.add_separator()

            dpg.add_text(show=False, tag=self._t("notification"), color=style.red)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Copy CSV", callback=self._on_copy_csv)
                dpg.add_button(label="Copy XML", callback=self._on_copy_xml)
                dpg.add_button(label="Save...", callback=self._on_save_character)

    # === DPG callbacks ================================================

    def _on_select_skeleton(self) -> None:
        path = open_file_dialog(
            title="Select Skeleton File", filetypes={"Skeleton.xml": "*.xml"}
        )
        if not path:
            return

        bones = load_skeleton_bones(path)

        if self._mirror_info and len(self._mirror_info["bonePairMap"]) != len(
            bones
        ):
            self.show_message("Skeleton does not match loaded Character!")
            return

        self._bones = bones
        dpg.set_value(self._t("skeleton_file"), path)
        self.fill_table()

    def _on_select_character(self) -> None:
        path = open_file_dialog(
            title="Select Character File",
            filetypes={"Character/cXXXX.xml": "*.xml"},
        )
        if not path:
            return

        character = Tagfile(path)
        mirror_info = character.find_first_by_type_name("hkbMirroredSkeletonInfo")

        if self._bones and len(mirror_info["bonePairMap"]) != len(self._bones):
            self.show_message("Character does not match loaded Skeleton!")
            return

        self._mirror_info = mirror_info
        dpg.set_value(self._t("character_file"), path)
        self.fill_table()

    def _on_select_mirror_bone(self, bone_idx: int) -> None:
        if self._bone_dialog is not None and dpg.does_item_exist(
            self._bone_dialog.tag
        ):
            dpg.focus_item(self._bone_dialog.tag)
            return

        def find_bones(filt: str) -> Generator[tuple[int, str], None, None]:
            filt = filt.lower()
            for idx, bone in enumerate(self._bones):
                if filt in bone.lower():
                    yield (idx, bone)

        def on_bone_selected(sender: str, item: tuple[int, str], ud) -> None:
            dpg.set_value(self._t(f"alt_bone_{bone_idx}"), item[1])

        self._bone_dialog = find_dialog(
            find_bones,
            ["Index", "Bone"],
            lambda item: item,
            okay_callback=on_bone_selected,
            title="Select Mirror Bone",
            tag=self._t("select_mirror_bone"),
        )

    def _on_copy_csv(self) -> None:
        if not self._require_bones():
            return

        pyperclip.copy(bone_pairs_to_csv(self._bones, self.mirrors))

    def _on_copy_xml(self) -> None:
        if not self._require_bones() or not self._require_character():
            return

        if not self.update_mirror_info():
            return

        pyperclip.copy(self._mirror_info.xml())

    def _on_save_character(self) -> None:
        if not self._require_bones() or not self._require_character():
            return

        if not self.update_mirror_info():
            return

        char_path = dpg.get_value(self._t("character_file"))
        dest_file = save_file_dialog(
            title="Save Character File",
            default_dir=os.path.dirname(char_path),
            default_file=os.path.basename(char_path),
        )

        if dest_file:
            self._mirror_info.tagfile.save_to_file(dest_file)

    # === Helpers ======================================================

    def _require_bones(self) -> bool:
        self.show_message()

        if not self._bones:
            self.show_message("No skeleton loaded!")
            return False

        return True

    def _require_character(self) -> bool:
        self.show_message()

        if not self._mirror_info:
            self.show_message("No character loaded!")
            return False

        return True

    # === Public =======================================================

    @property
    def mirrors(self) -> list[str]:
        """The mirror bone name currently entered for each bone."""
        return [
            dpg.get_value(self._t(f"alt_bone_{idx}"))
            for idx in range(len(self._bones))
        ]

    def fill_table(self) -> None:
        """Rebuild the bone table from the loaded skeleton and character."""
        if not self._require_bones():
            return

        dpg.delete_item(self._t("table"), slot=1, children_only=True)

        pair_map = self._mirror_info["bonePairMap"] if self._mirror_info else None

        for idx, bone in enumerate(self._bones):
            if pair_map is not None:
                alt_bone = self._bones[pair_map[idx].get_value()]
            else:
                alt_bone = bone

            with dpg.table_row(
                tag=self._t(f"bone_{idx}"),
                parent=self._t("table"),
            ):
                dpg.add_text(str(idx))
                dpg.add_text(bone)
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        default_value=alt_bone,
                        readonly=True,
                        tag=self._t(f"alt_bone_{idx}"),
                    )
                    dpg.add_button(
                        arrow=True,
                        direction=dpg.mvDir_Right,
                        callback=lambda s, a, u: self._on_select_mirror_bone(u),
                        user_data=idx,
                    )

    def auto_mirror(self) -> None:
        """Guess the mirror bones from their left/right affixes."""
        if not self._require_bones():
            return

        for idx, alt_bone in auto_mirror_bones(self._bones).items():
            dpg.set_value(self._t(f"alt_bone_{idx}"), alt_bone)

    def update_mirror_info(self) -> bool:
        """Write the table back into the character's bonePairMap."""
        if not self._require_bones() or not self._require_character():
            return False

        try:
            update_bone_pair_map(self._mirror_info, self._bones, self.mirrors)
        except ValueError as e:
            self.show_message(str(e))
            return False

        return True

    def show_message(self, msg: str = None, color: style.RGBA = style.red) -> None:
        """Show or hide the notification label. Pass ``msg=None`` to hide."""
        if not msg:
            dpg.hide_item(self._t("notification"))
            return

        dpg.configure_item(
            self._t("notification"),
            default_value=msg,
            color=color,
            show=True,
        )

    def close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)


if __name__ == "__main__":
    dpg.create_context()
    dpg.create_viewport(title="Mirror Skeleton", width=600, height=600)

    dialog = mirror_skeleton_dialog()
    dpg.set_primary_window(dialog.tag, True)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
