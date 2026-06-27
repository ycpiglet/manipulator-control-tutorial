"""Small interactive controls for viewer-based teaching demos."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any


LEFT_KEYS = {ord("A"), 263}
RIGHT_KEYS = {ord("D"), 262}


@dataclass(frozen=True)
class SliderSpec:
    name: str
    label: str
    minimum: float
    maximum: float
    initial: float
    resolution: float


@dataclass(frozen=True)
class StatusSpec:
    name: str
    label: str


class LiveTuning:
    def __init__(self, specs: list[SliderSpec]) -> None:
        self.specs = specs
        self.enabled = bool(specs)
        self._values = {spec.name: float(spec.initial) for spec in specs}
        self._lock = Lock()

    def value(self, name: str, default: float) -> float:
        with self._lock:
            return float(self._values.get(name, default))

    def set_value(self, name: str, value: float) -> None:
        with self._lock:
            if name in self._values:
                self._values[name] = float(value)


class LiveStatus:
    def __init__(self, specs: list[StatusSpec]) -> None:
        self.specs = specs
        self.enabled = bool(specs)
        self._values = {spec.name: "--" for spec in specs}
        self._lock = Lock()

    def set_values(self, **values: Any) -> None:
        with self._lock:
            for name, value in values.items():
                if name in self._values:
                    self._values[name] = _format_status_value(value)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._values)


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


def maybe_start_interaction_panel(
    control: Any,
    *,
    title: str,
    tuning: LiveTuning | None = None,
    status: LiveStatus | None = None,
) -> InteractionPanel | None:
    control_enabled = bool(getattr(control, "enabled", False))
    panel_enabled = bool(getattr(control, "panel_enabled", False))
    tuning_enabled = bool(tuning is not None and tuning.enabled)
    status_enabled = bool(status is not None and status.enabled)
    if not panel_enabled or not (control_enabled or tuning_enabled or status_enabled):
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

            row = 0
            tk.Label(frame, text="Interactive controls").grid(row=row, column=0, columnspan=2, pady=(0, 8))
            row += 1
            if control_enabled:
                tk.Button(frame, text=control.left_label, width=22, command=control.trigger_left).grid(
                    row=row, column=0, padx=4, pady=4
                )
                tk.Button(frame, text=control.right_label, width=22, command=control.trigger_right).grid(
                    row=row, column=1, padx=4, pady=4
                )
                row += 1
                tk.Label(
                    frame,
                    text=control.panel_description,
                ).grid(row=row, column=0, columnspan=2, pady=(8, 0))
                row += 1

            if tuning_enabled and tuning is not None:
                tk.Label(frame, text="Live tuning").grid(row=row, column=0, columnspan=2, pady=(12, 4))
                row += 1
                for spec in tuning.specs:
                    scale = tk.Scale(
                        frame,
                        from_=spec.minimum,
                        to=spec.maximum,
                        resolution=spec.resolution,
                        orient=tk.HORIZONTAL,
                        length=360,
                        label=spec.label,
                        command=lambda raw_value, name=spec.name: tuning.set_value(name, float(raw_value)),
                    )
                    scale.set(spec.initial)
                    scale.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
                    row += 1

            if status_enabled and status is not None:
                tk.Label(frame, text="Live status").grid(row=row, column=0, columnspan=2, pady=(12, 4))
                row += 1
                status_vars: dict[str, Any] = {}
                for spec in status.specs:
                    tk.Label(frame, text=spec.label, anchor="w").grid(row=row, column=0, sticky="w", padx=4, pady=2)
                    variable = tk.StringVar(value="--")
                    status_vars[spec.name] = variable
                    tk.Label(frame, textvariable=variable, width=14, anchor="e").grid(
                        row=row,
                        column=1,
                        sticky="e",
                        padx=4,
                        pady=2,
                    )
                    row += 1

                def refresh_status() -> None:
                    snapshot = status.snapshot()
                    for name, variable in status_vars.items():
                        variable.set(snapshot.get(name, "--"))
                    root.after(200, refresh_status)

                refresh_status()
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


def _format_status_value(value: Any) -> str:
    if value is None:
        return "--"
    if isinstance(value, bool):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.3f}"
