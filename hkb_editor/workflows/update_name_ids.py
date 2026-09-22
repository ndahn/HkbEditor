from typing import Iterable
import re
import logging
from pathlib import Path

from hkb_editor.hkb import HavokBehavior


logger = logging.getLogger(__name__)

# The name ID files a mod's action folder is expected to contain
NAMEID_FILES = ("state", "event", "variable")


def get_nameidfile_folder(behavior: HavokBehavior) -> Path:
    # Default paths
    # Behaviors will usually be located in
    # mod/chr/cXXXX-behbnd-dcx/Behavior/cXXXX.xml
    # and we are looking for the name ID files in
    # mod/action/
    try:
        return Path(behavior.file).parents[3] / "action"
    except IndexError:
        return None


def find_missing_nameid_files(action_path: Path) -> list[str]:
    """Return the names of the name ID files missing from ``action_path``."""
    missing = []

    for kind in NAMEID_FILES:
        if not (action_path / f"{kind}nameid.txt").is_file():
            missing.append(f"{kind}nameid.txt")

    return missing


def update_name_id_file(file_path: Path, known_names: Iterable[str]) -> int:
    """Append any names not yet listed in ``file_path``. Returns how many.

    Existing entries keep their index, since the game references them by
    number. Nothing is ever removed.
    """
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
            f"Expected total ({expected}) did not match number of items "
            f"({len(entries)}) in {file_path.name}, assuming items are correct"
        )

    # Append new names
    entries.extend(new_items)
    logger.debug(f"Adding new items to {file_path.name}: {new_items}")

    with file_path.open("w") as f:
        f.write(f"Num  = {len(entries)}\n")

        for idx, item in enumerate(entries):
            # Pad index with spaces to the right
            f.write(f'{idx + 1:<4} = "{item}"\n')

        # This always comes at the end of these files
        f.write("\x00\x00\x00\x00")

    return len(new_items)


def update_name_ids(behavior: HavokBehavior, action_path: Path) -> list[str]:
    """Sync all name ID files in ``action_path`` with the behavior.

    Returns the names of the files that could not be found; an empty list
    means everything was updated.
    """
    missing = []

    stateids_path = action_path / "statenameid.txt"
    if stateids_path.is_file():
        statenames = [
            obj["name"].get_value()
            for obj in behavior.query("type_name='hkbStateMachine::StateInfo'")
        ]
        update_name_id_file(stateids_path, statenames)
    else:
        missing.append("statenameid.txt")
        logger.warning(f"{stateids_path} not found")

    eventids_path = action_path / "eventnameid.txt"
    if eventids_path.is_file():
        update_name_id_file(eventids_path, behavior.get_events())
    else:
        missing.append("eventnameid.txt")
        logger.warning(f"{eventids_path} not found")

    variableids_path = action_path / "variablenameid.txt"
    if variableids_path.is_file():
        update_name_id_file(variableids_path, behavior.get_variables())
    else:
        missing.append("variablenameid.txt")
        logger.warning(f"{variableids_path} not found")

    return missing
