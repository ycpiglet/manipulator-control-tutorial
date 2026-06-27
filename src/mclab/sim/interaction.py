"""Small interactive controls for viewer-based teaching demos."""

from __future__ import annotations

from threading import Lock
from typing import Any


LEFT_KEYS = {ord("A"), 263}
RIGHT_KEYS = {ord("D"), 262}


class KeyForcePulse:
    """Keyboard-triggered force pulse for 1D plants.

    The MuJoCo viewer passes GLFW key codes to the callback. We support both
    A/D and left/right arrow keys so the interaction works on common keyboards.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        interaction = dict(config.get("interaction", {}))
        self.enabled = bool(interaction.get("key_force", False))
        self.magnitude = float(interaction.get("force", 25.0))
        self.duration = float(interaction.get("duration", 0.2))
        self._value = 0.0
        self._until = -1.0
        self._time = 0.0
        self._lock = Lock()

    def update_time(self, time: float) -> None:
        with self._lock:
            self._time = time

    def key_callback(self, key: int) -> None:
        if not self.enabled:
            return
        if key in LEFT_KEYS:
            self._start_pulse(-self.magnitude)
        elif key in RIGHT_KEYS:
            self._start_pulse(self.magnitude)

    def value(self, time: float) -> float:
        if not self.enabled:
            return 0.0
        with self._lock:
            if time <= self._until:
                return self._value
            return 0.0

    def _start_pulse(self, value: float) -> None:
        with self._lock:
            self._value = value
            self._until = self._time + self.duration
