from os import path
from pathlib import Path
import logging
import subprocess

from hkb_editor.hkb import HavokBehavior
from hkb_editor.external.config import config
from hkb_editor.external.reload import reload_character


def _convert(input_path: str, hklib_exe: str) -> str:
    args = [hklib_exe, input_path]
    ret = subprocess.check_call(args)

    if input_path.lower().endswith(".xml"):
        ext = ".hkx"
    else:
        ext = ".xml"

    hkx_filename = path.splitext(path.basename(input_path))[0] + ext
    hkx_path = path.join(path.dirname(input_path), hkx_filename)

    if not path.isfile(hkx_path):
        raise subprocess.CalledProcessError(ret, args, "Failed to locate output file")

    return hkx_path


def xml_to_hkx(xml_path: str) -> str:
    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    return _convert(xml_path, config.hklib_exe)


def hkx_to_xml(hkx_path: str) -> str:
    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    return _convert(hkx_path, config.hklib_exe)


def pack_binder(behavior_path: str) -> None:
    if not path.isfile(config.witchy_exe):
        raise RuntimeError("Could not locate witchybnd")

    p = Path(behavior_path)
    if p.parent.name != "Behaviors":
        raise RuntimeError("Behavior is not located inside a binder folder")

    if not p.parent.parent.name.endswith("-behbnd-dcx"):
        raise RuntimeError("Behavior is not located inside a binder folder")

    args = [config.witchy_exe, behavior_path]
    subprocess.check_call(args)


def open_binder(binder_path: str) -> str:
    if not path.isfile(config.witchy_exe):
        raise RuntimeError("Could not locate witchybnd")

    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    # Unpack the binder
    args = [config.witchy_exe, binder_path]
    subprocess.check_call(args)

    p = Path(binder_path)
    chr = p.name.split(".")[0]
    binder_dir = p.name.replace(".", "-")
    behavior_path = p.parent / binder_dir / "Behavior" / f"{chr}.hkx"

    # Convert from hkx to xml
    args = [config.hklib_exe, behavior_path.as_posix()]
    subprocess.check_call(args)
    return behavior_path.parent / f"{chr}.xml"


def on_save_behavior(behavior: HavokBehavior, behavior_path: str) -> None:
    try:
        if not config.convert_on_save:
            return
        
        xml_to_hkx(behavior_path)

        if not config.pack_on_save:
            return

        pack_binder(behavior_path)

        if not config.reload_on_save:
            return

        chr = behavior.get_character_id()
        if not chr:
            raise RuntimeError("Could not identify chr ID")

        reload_character(chr)
    except RuntimeError as e:
        logging.getLogger().warning(f"Could not run configured conversion: {e}")
    except subprocess.CalledProcessError as e:
        logging.getLogger().error(f"{e.cmd} failed ({e.returncode}): {e.output}")
