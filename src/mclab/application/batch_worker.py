"""Held packaged worker for the desktop course-comparison process.

The frozen executable enters this module before importing :mod:`mclab.cli`.
On Windows the parent passes a named manual-reset event and assigns this held
process to a kill-on-close Job Object before releasing it.  Source launches use
the same module without a gate.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import IO, Sequence

_DEVNULL_STREAMS: list[IO[str]] = []
_WINDOWS_GATE_TIMEOUT_MS = 30_000
_WINDOWS_EVENT_NAME = re.compile(r"Local\\MCLabBatch-[0-9a-f]{32}\Z")


def ensure_standard_streams() -> None:
    """Install process-lifetime null streams only for unavailable stdio."""

    specifications = (
        ("stdin", "r"),
        ("stdout", "w"),
        ("stderr", "w"),
    )
    for name, mode in specifications:
        if getattr(sys, name) is not None:
            continue
        stream = open(os.devnull, mode, encoding="utf-8")  # noqa: SIM115
        _DEVNULL_STREAMS.append(stream)
        setattr(sys, name, stream)


def _worker_arguments(arguments: Sequence[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--start-event", default="")
    known, forwarded = parser.parse_known_args(list(arguments))
    if forwarded[:2] != ["batch", "all"]:
        raise ValueError("The internal batch worker accepts only the full course comparison.")
    return str(known.start_event), forwarded


def _wait_for_windows_start_event(name: str) -> None:
    if not name:
        if os.name == "nt":
            raise RuntimeError("The Windows batch start event is required.")
        return
    if os.name != "nt":
        raise RuntimeError("A Windows batch start event was supplied on a non-Windows platform.")
    if len(name) > 64 or _WINDOWS_EVENT_NAME.fullmatch(name) is None:
        raise ValueError("The batch start event name is invalid.")

    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_failed = 0xFFFFFFFF
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    event = kernel32.OpenEventW(synchronize, False, name)
    if not event:
        raise OSError(ctypes.get_last_error(), "Could not open the batch start gate")
    try:
        result = kernel32.WaitForSingleObject(event, _WINDOWS_GATE_TIMEOUT_MS)
        if result == wait_failed:
            error = ctypes.get_last_error()
            raise OSError(error, f"Could not wait for the batch start gate: {ctypes.FormatError(error)}")
        if result != wait_object_0:
            raise RuntimeError(f"The batch start gate was not released (wait result {result}).")
    finally:
        kernel32.CloseHandle(event)


def main(argv: Sequence[str] | None = None) -> int:
    """Wait for containment, then forward the exact internal batch command."""

    ensure_standard_streams()
    try:
        start_event, arguments = _worker_arguments(sys.argv[1:] if argv is None else argv)
        _wait_for_windows_start_event(start_event)
    except Exception as exc:
        print(f"Batch worker refused to start: {exc}", file=sys.stderr, flush=True)
        return 75

    # Keep this import below the Windows gate.  Importing the CLI imports the
    # simulation graph, and no worker-controlled code may run before the parent
    # has assigned the process to its Job Object.
    from mclab.cli import main as cli_main

    return cli_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
