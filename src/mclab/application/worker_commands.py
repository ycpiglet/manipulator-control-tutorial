"""Thread-safe command handoff for the simulation worker."""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue


class CommandQueue:
    """Run UI-requested commands on the thread that owns MuJoCo rendering."""

    def __init__(self, on_error: Callable[[Exception], None]) -> None:
        self._commands: SimpleQueue[Callable[[], None]] = SimpleQueue()
        self._on_error = on_error

    def submit(self, command: Callable[[], None]) -> None:
        self._commands.put(command)

    def drain(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except Empty:
                return
            try:
                command()
            except Exception as exc:
                self._on_error(exc)
