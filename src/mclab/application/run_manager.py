"""Duplicate-safe lifecycle manager for desktop simulation sessions."""

from __future__ import annotations

import threading
from collections.abc import Callable

from .session import SimulationSession


SessionFactory = Callable[[], SimulationSession]


class RunManager:
    def __init__(self) -> None:
        self._active: dict[str, SimulationSession] = {}
        self._lock = threading.RLock()

    def create(self, scenario_id: str, factory: SessionFactory) -> SimulationSession:
        with self._lock:
            if scenario_id in self._active:
                raise RuntimeError(f"Scenario {scenario_id} is already running.")
            session = factory()
            self._active[scenario_id] = session
            return session

    def get(self, scenario_id: str) -> SimulationSession | None:
        with self._lock:
            return self._active.get(scenario_id)

    def release(self, scenario_id: str) -> None:
        with self._lock:
            session = self._active.pop(scenario_id, None)
        if session is not None:
            session.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._active.items())
            self._active.clear()
        for _, session in items:
            session.close()
