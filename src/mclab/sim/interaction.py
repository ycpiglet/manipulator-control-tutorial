"""Small interactive controls for viewer-based teaching demos."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from mclab.learning_guides import observation_prompt_for_guide, question_for_guide


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
class TuningPreset:
    name: str
    label: str
    values: dict[str, float]


@dataclass(frozen=True)
class StatusSpec:
    name: str
    label: str


class InteractionLog:
    """Thread-safe record of learner actions during an interactive run."""

    def __init__(self, max_events: int = 500) -> None:
        self.max_events = max(1, int(max_events))
        self._events: list[dict[str, Any]] = []
        self._current_time: float | None = None
        self._lock = Lock()

    def set_time(self, time: float) -> None:
        with self._lock:
            self._current_time = float(time)

    def record(self, kind: str, name: str, value: Any = None, *, label: str = "") -> None:
        with self._lock:
            event = {
                "time": self._current_time,
                "kind": str(kind),
                "name": str(name),
                "label": str(label or name),
                "value": _event_value(value),
            }
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events]

    def summary(self) -> dict[str, Any]:
        events = self.events()
        if not events:
            return {}
        last_time = events[-1].get("time")
        return {
            "interaction_events": len(events),
            "last_interaction_time": last_time,
            "last_interaction": events[-1].get("label") or events[-1].get("name"),
        }

    def mark_observation(
        self,
        *,
        sliders: dict[str, Any] | None = None,
        changed_sliders: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
        question: str = "",
        note: str = "",
        evidence_prompt: str = "",
    ) -> dict[str, Any]:
        value: dict[str, Any] = {}
        if question.strip():
            value["question"] = question.strip()
        if evidence_prompt.strip():
            value["evidence_prompt"] = evidence_prompt.strip()
        if note.strip():
            value["note"] = note.strip()
        if changed_sliders:
            value["changed_sliders"] = dict(changed_sliders)
        if sliders:
            value["sliders"] = dict(sliders)
        if status:
            value["status"] = dict(status)
        self.record("marker", "observation", value, label="Mark observation")
        return value


class LiveTuning:
    def __init__(
        self,
        specs: list[SliderSpec],
        event_log: InteractionLog | None = None,
        presets: list[TuningPreset] | None = None,
    ) -> None:
        self.specs = specs
        self.presets = presets or []
        self.enabled = bool(specs)
        self._values = {spec.name: float(spec.initial) for spec in specs}
        self._initial_values = dict(self._values)
        self._specs = {spec.name: spec for spec in specs}
        self._event_log = event_log
        self._lock = Lock()

    def value(self, name: str, default: float) -> float:
        with self._lock:
            return float(self._values.get(name, default))

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._values)

    def changed_values(self) -> dict[str, float]:
        with self._lock:
            return {
                name: value
                for name, value in self._values.items()
                if abs(value - self._initial_values.get(name, value)) > 1e-12
            }

    def set_value(self, name: str, value: float) -> None:
        should_record = False
        number = float(value)
        spec = self._specs.get(name)
        if spec is not None:
            number = _clamp(number, spec.minimum, spec.maximum)
        with self._lock:
            if name in self._values:
                old_value = self._values[name]
                self._values[name] = number
                should_record = abs(old_value - number) > 1e-12
        if should_record and self._event_log is not None:
            self._event_log.record(
                "slider",
                name,
                number,
                label=spec.label if spec is not None else name,
            )

    def apply_preset(self, name: str) -> dict[str, float]:
        preset = next((item for item in self.presets if item.name == name), None)
        if preset is None:
            return self.snapshot()
        applied: dict[str, float] = {}
        with self._lock:
            for value_name, value in preset.values.items():
                spec = self._specs.get(value_name)
                if spec is None:
                    continue
                number = _clamp(float(value), spec.minimum, spec.maximum)
                self._values[value_name] = number
                applied[value_name] = number
            values = dict(self._values)
        if applied and self._event_log is not None:
            self._event_log.record("preset", preset.name, applied, label=preset.label)
        return values

    def preset_summary(self, name: str) -> str:
        preset = next((item for item in self.presets if item.name == name), None)
        if preset is None:
            return ""
        parts: list[str] = []
        for value_name, value in preset.values.items():
            spec = self._specs.get(value_name)
            if spec is None:
                continue
            number = _clamp(float(value), spec.minimum, spec.maximum)
            parts.append(f"{spec.label}={_format_tuning_value(number)}")
        if not parts:
            return preset.label
        return f"{preset.label}: {', '.join(parts)}"

    def reset(self) -> dict[str, float]:
        with self._lock:
            changed = any(
                abs(self._values.get(name, initial) - initial) > 1e-12
                for name, initial in self._initial_values.items()
            )
            self._values = dict(self._initial_values)
            values = dict(self._values)
        if changed and self._event_log is not None:
            self._event_log.record("button", "reset_sliders", None, label="Reset sliders")
        return values


def tuning_presets_from_config(config: dict[str, Any], specs: list[SliderSpec]) -> list[TuningPreset]:
    interaction = dict(config.get("interaction", {}))
    raw_presets = interaction.get("tuning_presets", [])
    if not isinstance(raw_presets, list):
        return []
    allowed_names = {spec.name for spec in specs}
    presets: list[TuningPreset] = []
    for index, raw_preset in enumerate(raw_presets, start=1):
        if not isinstance(raw_preset, dict):
            continue
        raw_values = raw_preset.get("values", {})
        if not isinstance(raw_values, dict):
            continue
        values: dict[str, float] = {}
        for raw_name, raw_value in raw_values.items():
            name = str(raw_name)
            if name not in allowed_names:
                continue
            try:
                values[name] = float(raw_value)
            except (TypeError, ValueError):
                continue
        if not values:
            continue
        label = str(raw_preset.get("label") or raw_preset.get("name") or f"Preset {index}")
        name = str(raw_preset.get("name") or _preset_name(label, index))
        presets.append(TuningPreset(name=name, label=label, values=values))
    return presets


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

    def __init__(self, config: dict[str, Any], event_log: InteractionLog | None = None) -> None:
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
        self._event_log = event_log
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
            self._start_pulse(-self.magnitude, self.left_label)

    def trigger_right(self) -> None:
        if self.enabled:
            self._start_pulse(self.magnitude, self.right_label)

    def value(self, time: float) -> float:
        if not self.enabled:
            return 0.0
        with self._lock:
            if time <= self._until:
                return self._value
            return 0.0

    def _start_pulse(self, value: float, label: str) -> None:
        with self._lock:
            self._value = value
            self._until = self._time + self.duration
        if self._event_log is not None:
            self._event_log.record("button", "manual_force", value, label=label)


class TargetOffsetControl:
    def __init__(self, config: dict[str, Any], event_log: InteractionLog | None = None) -> None:
        interaction = dict(config.get("interaction", {}))
        self.enabled = bool(interaction.get("target_nudge", False))
        self.panel_enabled = bool(interaction.get("panel", False))
        self.step = float(interaction.get("target_step", 0.05))
        self.limit = abs(float(interaction.get("target_limit", 0.4)))
        self.left_label = "Joint Target -  A / Left"
        self.right_label = "Joint Target +  D / Right"
        self.panel_description = f"Target offset step: {self.step:g} rad, limit: +/-{self.limit:g} rad"
        self._offset = 0.0
        self._event_log = event_log
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
            offset = self._offset
        if self._event_log is not None:
            label = self.left_label if delta < 0.0 else self.right_label
            self._event_log.record("button", "joint_target_offset", offset, label=label)


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
    guide: Any | None = None,
    event_log: InteractionLog | None = None,
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
            guide_title = _panel_guide_title(guide)
            guide_rows = _panel_guide_rows(guide)
            if guide_title or guide_rows:
                if guide_title:
                    tk.Label(frame, text=guide_title).grid(row=row, column=0, columnspan=2, pady=(0, 4))
                    row += 1
                for label, text in guide_rows:
                    tk.Label(
                        frame,
                        text=f"{label}: {text}",
                        justify="left",
                        anchor="w",
                        wraplength=430,
                    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=1)
                    row += 1
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
                tuning_header = tk.Frame(frame)
                tuning_header.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 4))
                tuning_header.columnconfigure(0, weight=1)
                tk.Label(tuning_header, text="Live tuning").grid(row=0, column=0, sticky="w")
                scale_widgets: dict[str, Any] = {}

                def set_scale_values(values: dict[str, float]) -> None:
                    for name, value in values.items():
                        scale = scale_widgets.get(name)
                        if scale is not None:
                            scale.set(value)

                def reset_sliders() -> None:
                    set_scale_values(tuning.reset())

                def apply_preset(preset_name: str) -> None:
                    set_scale_values(tuning.apply_preset(preset_name))
                    if preset_status is not None:
                        preset_status.set(f"Applied {tuning.preset_summary(preset_name)}")

                def preview_preset(preset_name: str) -> None:
                    if preset_status is not None:
                        preset_status.set(tuning.preset_summary(preset_name))

                tk.Button(tuning_header, text="Reset sliders", command=reset_sliders).grid(
                    row=0,
                    column=1,
                    sticky="e",
                    padx=(12, 0),
                )
                row += 1
                preset_status: Any | None = None
                if tuning.presets:
                    tk.Label(frame, text="Quick presets").grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 2))
                    row += 1
                    preset_frame = tk.Frame(frame)
                    preset_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
                    for index, preset in enumerate(tuning.presets):
                        button = tk.Button(
                            preset_frame,
                            text=preset.label,
                            width=20,
                            command=lambda preset_name=preset.name: apply_preset(preset_name),
                        )
                        button.grid(row=index // 2, column=index % 2, padx=4, pady=3, sticky="ew")
                        button.bind("<Enter>", lambda _event, preset_name=preset.name: preview_preset(preset_name))
                    preset_status = tk.StringVar(value="Hover a preset to preview its slider values.")
                    tk.Label(
                        frame,
                        textvariable=preset_status,
                        justify="left",
                        anchor="w",
                        wraplength=430,
                    ).grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(0, 6))
                    row += 2
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
                    scale_widgets[spec.name] = scale
                    scale.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
                    row += 1

            if event_log is not None:
                marker_frame = tk.Frame(frame)
                marker_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 4))
                marker_frame.columnconfigure(1, weight=1)
                marker_status = tk.StringVar(value="")
                marker_note = tk.StringVar(value="")
                marker_prompt = observation_prompt_for_guide(guide)

                def mark_observation() -> None:
                    event_log.mark_observation(
                        changed_sliders=tuning.changed_values() if tuning is not None else None,
                        sliders=tuning.snapshot() if tuning is not None else None,
                        status=status.snapshot() if status is not None else None,
                        question=question_for_guide(guide),
                        note=marker_note.get(),
                        evidence_prompt=marker_prompt,
                    )
                    marker_note.set("")
                    marker_status.set(f"Marked observation {_observation_marker_count(event_log)}")

                marker_row = 0
                if marker_prompt:
                    tk.Label(
                        marker_frame,
                        text=marker_prompt,
                        justify="left",
                        anchor="w",
                        wraplength=430,
                    ).grid(row=marker_row, column=0, columnspan=2, sticky="w", pady=(0, 6))
                    marker_row += 1
                tk.Label(marker_frame, text="Observation note").grid(
                    row=marker_row,
                    column=0,
                    sticky="w",
                )
                tk.Entry(marker_frame, textvariable=marker_note, width=40).grid(
                    row=marker_row,
                    column=1,
                    sticky="ew",
                    padx=(12, 0),
                )
                marker_row += 1
                tk.Button(marker_frame, text="Mark observation", command=mark_observation).grid(
                    row=marker_row,
                    column=0,
                    sticky="w",
                    pady=(6, 0),
                )
                tk.Label(marker_frame, textvariable=marker_status, anchor="w").grid(
                    row=marker_row,
                    column=1,
                    sticky="ew",
                    padx=(12, 0),
                    pady=(6, 0),
                )
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


def _panel_guide_title(guide: Any | None) -> str:
    if guide is None:
        return ""
    return str(getattr(guide, "title", "") or "").strip()


def _panel_guide_rows(guide: Any | None) -> list[tuple[str, str]]:
    if guide is None:
        return []
    rows = [
        ("Try", str(getattr(guide, "try_this", "") or "").strip()),
        ("Change", str(getattr(guide, "change", "") or "").strip()),
        ("Question", question_for_guide(guide).removeprefix("Question:").strip()),
        ("Watch", str(getattr(guide, "watch", "") or "").strip()),
    ]
    return [(label, text) for label, text in rows if text]


def _observation_marker_count(event_log: InteractionLog) -> int:
    return sum(
        1
        for event in event_log.events()
        if str(event.get("kind", "")).lower() == "marker"
        and str(event.get("name", "")).lower() == "observation"
    )


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


def _format_tuning_value(value: float) -> str:
    return f"{float(value):.6g}"


def _preset_name(label: str, index: int) -> str:
    name = "_".join(label.lower().split())
    return name or f"preset_{index}"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(float(minimum), min(float(maximum), float(value)))


def _event_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return {str(key): _event_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_event_value(item) for item in value]
    if isinstance(value, str):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)
