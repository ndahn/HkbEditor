import sys
import os
import crossfiledialog
from crossfiledialog.exceptions import FileDialogException

try:
    import ctypes
except ImportError:
    raise ImportError(
        "Running 'filedialog' on Windows requires the 'pywin32' package.")


class Win32Exception(FileDialogException):
    pass


last_cwd = None


def get_preferred_cwd():
    possible_cwd = os.environ.get('FILEDIALOG_CWD', '')
    if possible_cwd:
        return possible_cwd

    global last_cwd
    if last_cwd:
        return last_cwd


def set_last_cwd(cwd):
    global last_cwd
    last_cwd = os.path.dirname(cwd)



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


def open_multiple_dialog(
    *,
    title: str = None,
    default_dir: str = None,
    filetypes: dict[str, str] = None,
) -> list[str]:
    global _dialog_open
    if _dialog_open:
        return

    _dialog_open = True

    if not title:
        title = ("Select files to load",)

    if not default_dir:
        default_dir = os.path.dirname(sys.argv[0])

    ret = crossfiledialog.open_multiple(
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

    # TODO default_file and filetypes not supported
    ret = crossfiledialog.save_file(
        title=title,
        start_dir=default_dir,
    )

    _dialog_open = False

    return ret


# TODO doesn't work on linux
def choose_folder(title: str = "Select folder", start_dir: str = None) -> str:
    """
    Open a folder selection dialog using the modern Windows IFileOpenDialog COM
    interface, which provides the full Explorer-style experience including drive
    switching, network locations, favourites, and the ability to create new folders.

    Args:
        title (str, optional): The title of the folder selection dialog.
            Default is 'Choose a folder'
        start_dir (str, optional): The starting directory for the dialog.

    Returns:
        str: The selected folder's path, or None if the dialog was cancelled.

    Example:
        result = choose_folder(title="Choose folder", start_dir="C:/Documents")
    """
    ole32   = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32

    S_OK = 0
    CLSCTX_INPROC_SERVER = 1

    # GUIDs as raw bytes (little-endian struct)
    def _guid(s):
        import uuid
        b = uuid.UUID(s).bytes_le
        buf = (ctypes.c_byte * 16)(*b)
        return buf

    CLSID_FileOpenDialog = _guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")
    IID_IFileOpenDialog  = _guid("D57C7288-D4AD-4768-BE02-9D969532D960")
    IID_IShellItem       = _guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")

    FOS_PICKFOLDERS     = 0x00000020
    FOS_FORCEFILESYSTEM = 0x00000040
    FOS_PATHMUSTEXIST   = 0x00000800
    FOS_FILEMUSTEXIST   = 0x00001000
    OPTIONS = FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_FILEMUSTEXIST

    SIGDN_FILESYSPATH = ctypes.c_int(0x80058000)

    ole32.CoInitialize(None)
    try:
        # --- Create IFileOpenDialog ---
        dialog_ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            CLSID_FileOpenDialog,
            None,
            CLSCTX_INPROC_SERVER,
            IID_IFileOpenDialog,
            ctypes.byref(dialog_ptr),
        )
        if hr != S_OK:
            return None

        # COM vtable helpers
        # IFileDialog vtable layout (IUnknown + IModalWindow + IFileDialog + IFileOpenDialog):
        #   0  QueryInterface
        #   1  AddRef
        #   2  Release
        #   3  Show                (IModalWindow)
        #   4  SetFileTypes        (IFileDialog)
        #   5  SetFileTypeIndex
        #   6  GetFileTypeIndex
        #   7  Advise
        #   8  Unadvise
        #   9  SetOptions
        #  10  GetOptions
        #  11  SetDefaultFolder
        #  12  SetFolder
        #  13  GetFolder
        #  14  GetCurrentSelection
        #  15  SetFileName
        #  16  GetFileName
        #  17  SetTitle
        #  18  SetOkButtonLabel
        #  19  SetFileNameLabel
        #  20  GetResult
        #  21  AddPlace
        #  22  SetDefaultExtension
        #  23  Close
        #  24  SetClientGuid
        #  25  ClearClientData
        #  26  SetFilter
        #  27  GetResults           (IFileOpenDialog)
        #  28  GetSelectedItems

        vt = ctypes.cast(
            ctypes.cast(dialog_ptr, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )

        def vtcall(index, restype, *argtypes_and_args):
            # argtypes_and_args: alternating (type, value) pairs
            argtypes = [ctypes.c_void_p] + list(argtypes_and_args[0::2])
            args     = [dialog_ptr]      + list(argtypes_and_args[1::2])
            fn = ctypes.WINFUNCTYPE(restype, *argtypes)(vt[index])
            return fn(*args)

        # SetOptions
        vtcall(9, ctypes.c_int, ctypes.c_uint, OPTIONS)

        # SetTitle
        if title:
            vtcall(17, ctypes.c_int, ctypes.c_wchar_p, title)

        # SetFolder to start_dir (or last_cwd)
        initial = start_dir or get_preferred_cwd()
        if initial and os.path.isdir(initial):
            item_ptr = ctypes.c_void_p()
            hr2 = shell32.SHCreateItemFromParsingName(
                ctypes.c_wchar_p(initial),
                None,
                IID_IShellItem,
                ctypes.byref(item_ptr),
            )
            if hr2 == S_OK and item_ptr:
                vtcall(12, ctypes.c_int, ctypes.c_void_p, item_ptr)
                # Release the shell item
                item_vt = ctypes.cast(
                    ctypes.cast(item_ptr, ctypes.POINTER(ctypes.c_void_p))[0],
                    ctypes.POINTER(ctypes.c_void_p),
                )
                ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(item_vt[2])(item_ptr)

        # Show(hwnd=0)
        hr_show = vtcall(3, ctypes.c_int, ctypes.c_void_p, None)

        path = None
        if hr_show == S_OK:
            # GetResult -> IShellItem
            result_ptr = ctypes.c_void_p()
            hr3 = vtcall(20, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.byref(result_ptr))
            if hr3 == S_OK and result_ptr:
                # IShellItem::GetDisplayName(SIGDN_FILESYSPATH)
                res_vt = ctypes.cast(
                    ctypes.cast(result_ptr, ctypes.POINTER(ctypes.c_void_p))[0],
                    ctypes.POINTER(ctypes.c_void_p),
                )
                name_ptr = ctypes.c_wchar_p()
                # IShellItem vtable: 0 QI, 1 AddRef, 2 Release, 3 BindToHandler,
                #                    4 GetParent, 5 GetDisplayName, 6 GetAttributes, 7 Compare
                get_display_name = ctypes.WINFUNCTYPE(
                    ctypes.c_int,
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_wchar_p),
                )(res_vt[5])
                hr4 = get_display_name(result_ptr, SIGDN_FILESYSPATH, ctypes.byref(name_ptr))
                if hr4 == S_OK and name_ptr.value:
                    path = name_ptr.value
                    ole32.CoTaskMemFree(name_ptr)

                # Release result IShellItem
                ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(res_vt[2])(result_ptr)

        # Release dialog
        vtcall(2, ctypes.c_ulong)

        if path:
            set_last_cwd(os.path.join(path, "x"))  # set_last_cwd expects a file path
            return path
        return None

    finally:
        ole32.CoUninitialize()
