"""Small interactive controls for viewer-based teaching demos."""

from __future__ import annotations

from collections.abc import Callable
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
        self.panel_enabled = bool(interaction.get("panel", False))
        self.left_label = "Pull Left  A / Left"
        self.right_label = "Push Right  D / Right"
        self.panel_description = f"Force: {self.magnitude:g} N, duration: {self.duration:g} s"
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
            self.trigger_left()
        elif key in RIGHT_KEYS:
            self.trigger_right()

    def trigger_left(self) -> None:
        if self.enabled:
            self._start_pulse(-self.magnitude)

    def trigger_right(self) -> None:
        if self.enabled:
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


class TargetOffsetControl:
    def __init__(self, config: dict[str, Any]) -> None:
        interaction = dict(config.get("interaction", {}))
        self.enabled = bool(interaction.get("target_nudge", False))
        self.panel_enabled = bool(interaction.get("panel", False))
        self.step = float(interaction.get("target_step", 0.05))
        self.limit = abs(float(interaction.get("target_limit", 0.4)))
        self.left_label = "Joint Target -  A / Left"
        self.right_label = "Joint Target +  D / Right"
        self.panel_description = f"Target offset step: {self.step:g} rad, limit: +/-{self.limit:g} rad"
        self._offset = 0.0
        self._lock = Lock()

    def key_callback(self, key: int) -> None:
        if not self.enabled:
            return
        if key in LEFT_KEYS:
            self.trigger_left()
        elif key in RIGHT_KEYS:
            self.trigger_right()

    def trigger_left(self) -> None:
        if self.enabled:
            self._add_offset(-self.step)

    def trigger_right(self) -> None:
        if self.enabled:
            self._add_offset(self.step)

    def value(self) -> float:
        if not self.enabled:
            return 0.0
        with self._lock:
            return self._offset

    def _add_offset(self, delta: float) -> None:
        with self._lock:
            self._offset = max(-self.limit, min(self.limit, self._offset + delta))


class InteractionPanel:
    def __init__(self, close: Callable[[], None]) -> None:
        self._close = close

    def close(self) -> None:
        self._close()


def maybe_start_interaction_panel(control: Any, *, title: str) -> InteractionPanel | None:
    if not control.enabled or not control.panel_enabled:
        return None

    try:
        import tkinter as tk
        from threading import Thread
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        print(f"Interaction panel could not be started: {exc}")
        return None

    holder: dict[str, Any] = {}

    def run_panel() -> None:
        try:
            root = tk.Tk()
            holder["root"] = root
            root.title(title)
            root.resizable(False, False)

            frame = tk.Frame(root, padx=14, pady=12)
            frame.pack()

            tk.Label(frame, text="Interactive controls").grid(row=0, column=0, columnspan=2, pady=(0, 8))
            tk.Button(frame, text=control.left_label, width=22, command=control.trigger_left).grid(
                row=1, column=0, padx=4, pady=4
            )
            tk.Button(frame, text=control.right_label, width=22, command=control.trigger_right).grid(
                row=1, column=1, padx=4, pady=4
            )
            tk.Label(
                frame,
                text=control.panel_description,
            ).grid(row=2, column=0, columnspan=2, pady=(8, 0))
            root.mainloop()
        except Exception as exc:  # pragma: no cover - depends on local GUI support.
            print(f"Interaction panel stopped: {exc}")

    thread = Thread(target=run_panel, daemon=True)
    thread.start()

    def close() -> None:
        root = holder.get("root")
        if root is not None:
            try:
                root.after(0, root.destroy)
            except Exception:
                pass

    return InteractionPanel(close)
