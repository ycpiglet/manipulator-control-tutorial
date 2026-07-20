"""Windows handle primitives for the saved-output safety boundary."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from mclab.output_safety import CleanupOperationError, CleanupSafetyError, _lexists


@contextmanager
def exclusive_windows_operation_mutex(name: str) -> Iterator[None]:
    """Acquire one fail-fast, crash-released named mutex."""

    import ctypes
    from ctypes import wintypes

    create_mutex = ctypes.windll.kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    get_last_error = ctypes.windll.kernel32.GetLastError
    get_last_error.argtypes = []
    get_last_error.restype = wintypes.DWORD
    raw_handle = create_mutex(None, True, name)
    error_code = int(get_last_error())
    handle_value = raw_handle if isinstance(raw_handle, int) else raw_handle.value
    if handle_value is None:
        raise CleanupOperationError(
            f"Could not lock saved-output operations: {ctypes.WinError(error_code)}"
        )
    handle = int(handle_value)
    if error_code == 183:
        close_windows_handles((handle,))
        raise CleanupOperationError(
            "Another saved-output cleanup or restore operation is active"
        )
    release_mutex = ctypes.windll.kernel32.ReleaseMutex
    release_mutex.argtypes = [wintypes.HANDLE]
    release_mutex.restype = wintypes.BOOL
    try:
        yield
    finally:
        release_mutex(handle)
        close_windows_handles((handle,))


def pin_windows_lexical_chain(root: Path) -> tuple[tuple[int, ...], bool]:
    """Hold each lexical ancestor without following a reparse point."""

    paths = [*reversed(root.parents), root]
    handles: list[int] = []
    try:
        for path in paths:
            try:
                handles.append(open_windows_directory(path, delete_access=False))
            except FileNotFoundError:
                return tuple(handles), False
    except Exception:
        close_windows_handles(tuple(handles))
        raise
    return tuple(handles), True


def open_windows_directory(path: Path, *, delete_access: bool) -> int:
    """Open one physical directory and reject reparse points."""

    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    # FILE_LIST_DIRECTORY makes the retained handle participate in ordinary
    # directory sharing checks; omitting FILE_SHARE_DELETE then prevents a
    # configured output directory from being renamed out from under the pin.
    desired_access = 0x00000001 | 0x00000080 | (0x00010000 if delete_access else 0)
    raw_handle = create_file(
        str(path),
        desired_access,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    handle_value = raw_handle if isinstance(raw_handle, int) else raw_handle.value
    if handle_value is None or int(handle_value) == ctypes.c_void_p(-1).value:
        error = ctypes.WinError()
        if getattr(error, "winerror", None) in {2, 3}:
            raise FileNotFoundError(str(path)) from error
        raise CleanupSafetyError(f"Could not pin Windows output directory {path}: {error}")
    handle = int(handle_value)
    try:
        attributes = _windows_file_information(handle).dwFileAttributes
        if attributes & 0x00000400 or not attributes & 0x00000010:
            raise CleanupSafetyError("A Windows output directory became a reparse point")
    except Exception:
        close_windows_handles((handle,))
        raise
    return handle


def close_windows_handles(handles: tuple[int, ...]) -> None:
    """Close handles with a pointer-sized Win32 signature."""

    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    for handle in reversed(handles):
        close_handle(handle)


def windows_file_id(handle: int) -> tuple[int, int]:
    """Return stable volume and file IDs for an open directory handle."""

    information = _windows_file_information(handle)
    file_index = (int(information.nFileIndexHigh) << 32) | int(information.nFileIndexLow)
    return int(information.dwVolumeSerialNumber), file_index


def _windows_file_information(handle: int):  # type: ignore[no-untyped-def]
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    information = ByHandleFileInformation()
    get_information = ctypes.windll.kernel32.GetFileInformationByHandle
    get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(ByHandleFileInformation)]
    get_information.restype = wintypes.BOOL
    if not get_information(handle, ctypes.byref(information)):
        raise CleanupSafetyError(
            f"Could not inspect pinned Windows directory: {ctypes.WinError()}"
        )
    return information


def rename_windows_directory_noreplace(
    source: Path,
    destination: Path,
    *,
    expected_source_id: tuple[int, int],
) -> None:
    """Rename one directory handle without replacing a destination."""

    import ctypes
    from ctypes import wintypes

    if destination.exists() or _lexists(destination):
        raise FileExistsError(f"destination already exists: {destination}")
    source_handle = open_windows_directory(source, delete_access=True)
    try:
        if windows_file_id(source_handle) != expected_source_id:
            raise CleanupSafetyError("Move source changed before the Windows rename")
    except Exception:
        close_windows_handles((source_handle,))
        raise
    try:
        destination_handle = open_windows_directory(destination.parent, delete_access=False)
    except Exception:
        close_windows_handles((source_handle,))
        raise
    try:
        class FileRenameInfo(ctypes.Structure):
            _fields_ = [
                ("ReplaceIfExists", wintypes.BOOLEAN),
                ("RootDirectory", wintypes.HANDLE),
                ("FileNameLength", wintypes.DWORD),
                ("FileName", wintypes.WCHAR * 1),
            ]

        encoded_name = str(destination).encode("utf-16-le")
        # FileNameLength excludes the terminator, while the ABI requires at
        # least sizeof(FILE_RENAME_INFO) plus the encoded name. The zero-filled
        # trailing storage also supplies the WCHAR terminator.
        size = ctypes.sizeof(FileRenameInfo) + len(encoded_name)
        buffer = ctypes.create_string_buffer(size)
        info = FileRenameInfo.from_buffer(buffer)
        info.ReplaceIfExists = False
        info.RootDirectory = None
        info.FileNameLength = len(encoded_name)
        ctypes.memmove(
            ctypes.addressof(buffer) + FileRenameInfo.FileName.offset,
            encoded_name,
            len(encoded_name),
        )
        set_information = ctypes.windll.kernel32.SetFileInformationByHandle
        set_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        set_information.restype = wintypes.BOOL
        if not set_information(source_handle, 3, buffer, size):
            raise OSError(f"Windows no-replace rename failed: {ctypes.WinError()}")
    finally:
        close_windows_handles((destination_handle, source_handle))
