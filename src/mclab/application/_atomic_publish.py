"""Atomic no-clobber directory publication for supported desktop platforms."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


def rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename ``source`` only when ``destination`` is absent."""

    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        os.rename(source, destination)
        return
    if sys.platform == "linux":
        _linux_rename_no_replace(source, destination)
        return
    if sys.platform == "darwin":  # pragma: no cover - exercised by macOS CI
        _darwin_rename_no_replace(source, destination)
        return
    raise OSError(
        errno.ENOTSUP,
        "atomic no-clobber asset publication is unsupported on this platform",
        destination,
    )


def _linux_rename_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        operation = libc.renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOTSUP,
            "renameat2 is unavailable; refusing non-atomic asset publication",
            destination,
        ) from exc
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    result = operation(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    _raise_rename_error(result, destination)


def _darwin_rename_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        operation = libc.renamex_np
    except AttributeError as exc:
        raise OSError(
            errno.ENOTSUP,
            "renamex_np is unavailable; refusing non-atomic asset publication",
            destination,
        ) from exc
    operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    result = operation(os.fsencode(source), os.fsencode(destination), _RENAME_EXCL)
    _raise_rename_error(result, destination)


def _raise_rename_error(result: int, destination: Path) -> None:
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)
