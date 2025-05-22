import sys
import os
import crossfiledialog


_dialog_open = False


def open_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: dict[str, str] = None,
) -> str:
    global _dialog_open
    if _dialog_open:
        return

    _dialog_open = True

    if not title:
        title = "Select file to load"

    if not default_dir:
        default_dir = os.path.dirname(sys.argv[0])

    # dpg file dialog sucks, so we use the native one instead
    # TODO default_file not supported
    ret = crossfiledialog.open_file(
        title=title,
        start_dir=default_dir,
        filter=filetypes,
    )
    _dialog_open = False

    return ret


def save_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: dict[str, str] = None,
) -> str:
    global _dialog_open
    if _dialog_open:
        return
        
    _dialog_open = True

    if not title:
        title = "Select file to load"

    if not default_dir:
        default_dir = os.path.dirname(sys.argv[0])

    # dpg file dialog sucks, so we use the native one instead
    # TODO default_file and filetypes not supported
    ret = crossfiledialog.save_file(
        title=title,
        start_dir=default_dir,
    )

    _dialog_open = False
    
    return ret
