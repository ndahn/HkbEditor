from os import path
from pathlib import Path
import subprocess

from hkb_editor.external.config import get_config


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
    config = get_config()
    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    return _convert(xml_path, config.hklib_exe)


def hkx_to_xml(hkx_path: str) -> str:
    config = get_config()
    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    return _convert(hkx_path, config.hklib_exe)


def locate_binder(behavior_path: str) -> str:
    p = Path(behavior_path)
    if p.parent.name != "Behaviors":
        raise RuntimeError("Behavior is not located inside a binder folder")

    if not p.parent.parent.name.endswith("-behbnd-dcx"):
        raise RuntimeError("Behavior is not located inside a binder folder")

    return str(p.parent.parent)


def pack_binder(behavior_path: str) -> None:
    config = get_config()
    if not path.isfile(config.witchy_exe):
        raise RuntimeError("Could not locate witchybnd")

    binder = locate_binder(behavior_path)
    args = [config.witchy_exe, "--passive", binder]
    subprocess.check_call(args)


def unpack_binder(binder_path: str) -> str:
    config = get_config()
    if not path.isfile(config.witchy_exe):
        raise RuntimeError("Could not locate witchybnd")

    if not path.isfile(config.hklib_exe):
        raise RuntimeError("Could not locate hklib")

    # Unpack the binder
    args = [config.witchy_exe, "--passive", binder_path]
    try:
        subprocess.check_call(args)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"WitchyBND failed: {e.output}") from e

    p = Path(binder_path)
    chr = p.name.split(".")[0]
    binder_dir = p.name.replace(".", "-")
    behavior_path = p.parent / binder_dir / "Behaviors" / f"{chr}.hkx"

    # Convert from hkx to xml
    args = [config.hklib_exe, str(behavior_path)]
    try:
        subprocess.check_call(args)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"HKLib failed: {e.output}") from e

    return str(behavior_path.parent / f"{chr}.xml")
