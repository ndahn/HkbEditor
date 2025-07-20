from typing import Iterable
import re
import logging
from pathlib import Path
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HavokBehavior
from hkb_editor.gui.dialogs import open_file_dialog
from hkb_editor.gui.helpers import add_paragraphs, center_window
from hkb_editor.gui import style


def update_name_ids_dialog(
    behavior: HavokBehavior,
    *,
    title: str = "Update Name ID Files",
    tag: str = None,
) -> None:
    if tag in (None, 0, ""):
        tag = dpg.generate_uuid()

    logger = logging.getLogger()

    # Default paths
    # Behaviors will usually be located in
    # mod/chr/cXXXX-behbnd-dcx/Behavior/cXXXX.xml
    # and we are looking for the name ID files in
    # mod/action/
    try:
        action_path = Path(behavior.file).parents[3] / "action"
    except IndexError:
        action_path = ""

    def show_warning(msg: str) -> None:
        dpg.set_value(f"{tag}_notification", msg)
        dpg.show_item(f"{tag}_notification")

    def select_action_folder() -> None:
        nonlocal action_path

        path = open_file_dialog(
            title="Locate mod/action folder",
            filetypes={"Name ID Files": "*.txt"},
        )

        if path:
            action_path = Path(path).parent
            dpg.set_value(f"{tag}_action_path", str(path))

            missing = []
            for kind in ("event", "variable", "state"):
                nameid_path = action_path / f"{kind}nameid.txt"
                if not nameid_path.is_file():
                    missing.append(f"{kind}nameid.txt")

            if missing:
                show_warning(
                    f"{tuple(missing)} not found"
                )

    def update_name_ids(kind: str, known_names: Iterable[str]) -> None:
        file_path = action_path / f"{kind}nameid.txt"

        expected = 0
        entries = []
        line_pattern = re.compile(r"([0-9]+)\s*=\s*\"(.+)\"")
        new_items = list(known_names)

        with file_path.open(errors="ignore") as f:
            for line in f.readlines():
                line = line.strip()

                if line.startswith("\x00"):
                    break

                if line.startswith("Num "):
                    expected = int(line.split("=")[-1])
                    continue

                match = re.match(line_pattern, line)
                if match:
                    # idx = int(match.group(1))
                    name = match.group(2)
                    entries.append(name)

                    try:
                        new_items.remove(name)
                    except (KeyError, ValueError):
                        pass

                # All others ignored

        if len(entries) != expected:
            logger.warning(
                f"Expected total ({expected}) did not match number of items ({len(entries)}) in {kind}nameid.txt, assuming items are correct"
            )

        # Append new names
        entries.extend(new_items)
        logger.debug(f"Adding new items to {kind}nameid.txt: {new_items}")

        with file_path.open("w") as f:
            f.write(f"Num  = {len(entries)}\n")

            for idx, item in enumerate(entries):
                # Pad index with spaces to the right
                f.write(f'{idx + 1:<4} = "{item}"\n')

            # This always comes at the end of these files
            f.write("\x00\x00\x00\x00")

        return len(new_items)

    def on_okay() -> None:
        if not action_path or not action_path.is_dir():
            show_warning("Please locate your mod/action folder first")
            return

        missing = []

        stateids_path = action_path / f"statenameid.txt"
        if stateids_path.is_file():
            statenames = [
                obj["name"].get_value()
                for obj in behavior.query("type_name:'hkbStateMachine::StateInfo'")
            ]
            update_name_ids("state", statenames)
        else:
            missing.append("statenameid.txt")
            logger.warning(f"{stateids_path} not found")

        eventids_path = action_path / f"eventnameid.txt"
        if eventids_path.is_file():
            eventnames = behavior.get_events()
            update_name_ids("event", eventnames)
        else:
            missing.append("eventnameid.txt")
            logger.warning(f"{eventids_path} not found")

        variableids_path = action_path / f"variablenameid.txt"
        if variableids_path.is_file():
            variablenames = behavior.get_variables()
            update_name_ids("variable", variablenames)
        else:
            missing.append("variablenameid.txt")
            logger.warning(f"{variableids_path} not found")

        if missing:
            show_warning("At least one ID file was missing, check logs!")
        else:
            logger.info("All name ID files were updated")
            dpg.delete_item(dialog)

    with dpg.window(
        label=title,
        width=700,
        height=400,
        autosize=True,
        no_saved_settings=True,
        tag=tag,
        on_close=lambda: dpg.delete_item(dialog),
    ) as dialog:
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                default_value=str(action_path),
                readonly=True,
                hint="mod/action",
                tag=f"{tag}_action_path",
            )
            dpg.add_button(
                label="Locate action folder...", callback=select_action_folder
            )

        dpg.add_spacer(height=3)

        instructions = """\
When adding new events, variables or StateInfo objects, they need to be recorded in a text file located in your mod's action folder. These are not character-specific and are required to correctly synchronize game state in online sessions. 

Since these text files cover all behaviors in the entire game, they cannot be generated on the fly. This tool can only add new entries and will never remove any. 

NOTE: If you don't have these files in your mod yet, copy them from the base game first!
"""
        add_paragraphs(instructions, color=style.light_blue)

        dpg.add_separator()

        dpg.add_text(show=False, tag=f"{tag}_notification", color=style.orange)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Okay", callback=on_okay, tag=f"{tag}_button_okay")
            dpg.add_button(
                label="Cancel",
                callback=lambda: dpg.delete_item(dialog),
            )

    dpg.split_frame()
    center_window(dialog)

    return dialog
