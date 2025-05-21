import tkinter as tk
from tkinter import filedialog


# TODO try using windows-filedialogs if available
# TODO tk is difficult to integrate if we want to use it more than once


_dialog_open = False


def open_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: list[tuple[str, str]] = None,
) -> str:
    global _dialog_open
    if _dialog_open:
        return

    _dialog_open = True

    if not title:
        title = "Select file to load"

    # dpg file dialog sucks, so we use the tk one instead
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    ret = filedialog.askopenfilename(
        title=title,
        filetypes=filetypes,
        initialdir=default_dir,
        initialfile=default_file,
    )

    root.destroy()
    _dialog_open = False

    return ret


def save_file_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    default_file: str = None,
    filetypes: list[tuple[str, str]] = None,
) -> str:
    global _dialog_open
    if _dialog_open:
        return
        
    _dialog_open = True

    if not title:
        title = "Select file to load"

    # dpg file dialog sucks, so we use the tk one instead
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    ret = filedialog.asksaveasfilename(
        title=title,
        filetypes=filetypes,
        initialdir=default_dir,
        initialfile=default_file,
    )

    root.destroy()
    _dialog_open = False
    
    return ret
