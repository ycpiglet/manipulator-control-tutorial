"""Qt-free factory for the guided prediction and observation workflow."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from mclab.application.presentation import scenario_payload
from mclab.application.session import SessionState

PREDICTION_LIMIT = 240
OBSERVATION_LIMIT = 300
PREDICTION_OUTCOMES = frozenset({"Matched", "Partly matched", "Surprised"})

_LAB03_PRESET_CONFIG_PATHS = {
    "target_x": "target_xy.0",
    "target_y": "target_xy.1",
    "dls_gain": "tracking_controller.dls_gain",
    "dls_damping": "tracking_controller.dls_damping",
    "condition_damping_threshold": "tracking_controller.condition_damping_threshold",
    "condition_damping_full": "tracking_controller.condition_damping_full",
    "max_dls_damping": "tracking_controller.max_dls_damping",
    "task_kp": "tracking_controller.task_kp",
    "task_kd": "tracking_controller.task_kd",
    "kp": "tracking_controller.kp",
    "kd": "tracking_controller.kd",
    "force_limit": "tracking_controller.force_limit",
}
_LAB04_PRESET_CONFIG_PATHS = {
    "target_x": "cartesian_target.position.0",
    "target_y": "cartesian_target.position.1",
    "target_z": "cartesian_target.position.2",
    "cartesian_gain": "cartesian_target.gain",
    "wall_x": "virtual_wall.wall_x",
    "wall_stiffness": "virtual_wall.stiffness",
    "wall_damping": "virtual_wall.damping",
    "wall_retreat_gain": "virtual_wall.cartesian_retreat_gain",
}


def apply_desktop_preset(adapter: Any, preset: Mapping[str, Any]) -> dict[str, float]:
    """Atomically apply one canonical YAML preset to either desktop adapter family."""

    preset_id, label, values = _validated_preset(preset)
    live_tuning = getattr(adapter, "live_tuning", None)
    if live_tuning is not None and callable(getattr(live_tuning, "apply_preset", None)):
        configured = next(
            (item for item in getattr(live_tuning, "presets", ()) if item.name == preset_id),
            None,
        )
        if configured is None:
            raise KeyError(f"Unknown Quick preset: {preset_id}")
        if str(configured.label).strip() != label:
            raise ValueError(f"Quick preset label mismatch for {preset_id}")
        missing = set(values) - set(configured.values)
        if missing:
            raise ValueError(
                f"Quick preset {preset_id} cannot apply values: {', '.join(sorted(missing))}"
            )
        snapshot = live_tuning.apply_preset(preset_id)
        applied = {name: float(snapshot[name]) for name in values if name in snapshot}
        if set(applied) != set(values):
            raise ValueError(f"Quick preset {preset_id} did not apply every configured value")
        if any(not math.isclose(applied[name], value, abs_tol=1e-12) for name, value in values.items()):
            raise ValueError(f"Quick preset {preset_id} changed a configured value while applying")
        return applied

    parameters = getattr(adapter, "parameters", None)
    events = getattr(adapter, "events", None)
    if not isinstance(parameters, dict) or not isinstance(events, list):
        raise RuntimeError("This desktop adapter does not support Quick presets")
    missing = set(values) - set(parameters)
    if missing:
        raise ValueError(
            f"Quick preset {preset_id} cannot apply values: {', '.join(sorted(missing))}"
        )

    # Replacing the mapping makes the whole preset visible to the next physics
    # tick at once; no partial per-slider state is observable.
    adapter.parameters = {**parameters, **values}
    events.append(
        {
            "time": _adapter_time(adapter),
            "kind": "preset",
            "name": preset_id,
            "label": label,
            "value": _preset_event_value(preset, values),
        }
    )
    return dict(values)


def config_with_desktop_preset(
    scenario: Any,
    base_config: Mapping[str, Any],
    active_config: Mapping[str, Any],
    preset: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the active config after applying every preset value."""

    _preset_id, _label, values = _validated_preset(preset)
    updated = deepcopy(dict(active_config))
    control_paths = {
        str(control.id): str(control.config_path)
        for control in getattr(scenario, "controls", ())
        if str(control.config_path)
    }
    lab_name = str(getattr(scenario, "lab_name", ""))
    fallback_paths = (
        _LAB03_PRESET_CONFIG_PATHS
        if lab_name == "lab03"
        else _LAB04_PRESET_CONFIG_PATHS
        if lab_name == "lab04"
        else {}
    )

    for name, value in values.items():
        if lab_name == "lab03" and name == "target_offset":
            _apply_trajectory_offset(updated, base_config, value)
            continue
        if lab_name == "lab04" and name == "joint_target_offset":
            _apply_trajectory_offset(updated, base_config, value)
            continue
        if lab_name == "lab03" and name == "torque_limit":
            _set_nested_config_value(
                updated,
                "tracking_controller.torque_limit",
                _capped_torque_limits(base_config, value),
            )
            continue
        path = control_paths.get(name) or fallback_paths.get(name)
        if not path:
            raise ValueError(f"Quick preset value {name!r} has no active-config path")
        _set_nested_config_value(updated, path, value)
    return updated


def create_evidence_backend_mixin(
    base: type,
    Property: Any,
    Signal: Any,
    Slot: Any,
) -> type:
    """Build a QObject mixin after PySide6 is selected by the CLI."""

    class EvidenceBackendMixin(base):
        evidence_changed = Signal()

        def _init_evidence(self) -> None:
            self._prediction = ""
            self._learner_action_count = 0
            self._observation = {}
            self._active_control_values: dict[str, float] = {}
            self._preset_base_config: dict[str, Any] = {}

        def _set_preset_config(
            self, config: dict[str, Any], *, base: bool = False
        ) -> None:
            self._active_config = config
            self._active_control_values = {}
            self._preset_base_config = deepcopy(config) if base else {}

        def _preset_scenario_payload(
            self, scenario: Any, translator: Any, config: dict[str, Any] | None
        ) -> dict[str, Any]:
            return scenario_payload(
                scenario,
                translator,
                config_override=config,
                control_values_override=(
                    self._active_control_values if config is not None else None
                ),
            )

        @Property(bool, notify=evidence_changed)
        def hasPrediction(self) -> bool:  # noqa: N802
            return bool(self._prediction)

        @Property(bool, notify=evidence_changed)
        def hasLearnerAction(self) -> bool:  # noqa: N802
            return self._learner_action_count > 0

        @Property(bool, notify=evidence_changed)
        def hasObservation(self) -> bool:  # noqa: N802
            return bool(self._observation)

        @Property(int, notify=evidence_changed)
        def learnerActionCount(self) -> int:  # noqa: N802
            return self._learner_action_count

        @Property(str, notify=evidence_changed)
        def predictionText(self) -> str:  # noqa: N802
            return self._prediction

        @Property(bool, notify=evidence_changed)
        def waitingForPrediction(self) -> bool:  # noqa: N802
            return (
                self._requires_evidence()
                and not bool(getattr(self, "_replay_mode", False))
                and not self._prediction
            )

        @Slot(str)
        def savePrediction(self, text: str) -> None:  # noqa: N802
            prediction = _clean_text(text, PREDICTION_LIMIT)
            if len(prediction) < 3:
                self._evidence_error("evidence.prediction_short")
                return
            if not self._evidence_editable():
                self._evidence_error("evidence.live_only")
                return
            self._prediction = prediction
            self._observation = {}
            self._queue_evidence(
                "prediction",
                "prediction",
                prediction,
                "Prediction",
                resume=True,
            )
            self.evidence_changed.emit()

        @Slot(str, str)
        def saveObservation(self, note: str, outcome: str) -> None:  # noqa: N802
            observation = _clean_text(note, OBSERVATION_LIMIT)
            canonical_outcome = str(outcome).strip()
            if not self._prediction:
                self._evidence_error("evidence.prediction_first")
                return
            if self._learner_action_count <= 0:
                self._evidence_error("evidence.control_first")
                return
            if canonical_outcome not in PREDICTION_OUTCOMES:
                self._evidence_error("evidence.outcome_required")
                return
            if len(observation) < 3:
                self._evidence_error("evidence.observation_short")
                return
            if not self._evidence_editable():
                self._evidence_error("evidence.live_only")
                return
            value = {
                "prediction": self._prediction,
                "outcome": canonical_outcome,
                "note": observation,
                "status": dict(self._telemetry),
            }
            self._observation = value
            self._queue_evidence("marker", "observation", value, "Mark observation")
            self.evidence_changed.emit()

        @Slot(str)
        def applyPreset(self, preset_id: str) -> None:  # noqa: N802
            selected = getattr(self, "_selected", None)
            session = getattr(self, "session", None)
            if (
                selected is None
                or session is None
                or bool(getattr(self, "_replay_mode", False))
                or not self._evidence_editable()
            ):
                self._evidence_error("evidence.live_only")
                return
            if not self.hasPrediction:
                self._evidence_error("evidence.prediction_first")
                return

            scenario = self._scenario_map(selected)
            preset = next(
                (
                    item
                    for item in scenario.get("presets", ())
                    if str(item.get("id", "")) == str(preset_id)
                ),
                None,
            )
            if preset is None:
                self._set_error(
                    f"Unknown Quick preset: {preset_id}",
                    "Choose a Quick preset shown for the active experiment.",
                )
                return

            try:
                next_config = config_with_desktop_preset(
                    selected,
                    getattr(self, "_preset_base_config", {}) or selected.config,
                    getattr(self, "_active_config", {}) or selected.config,
                    preset,
                )

                def apply() -> None:
                    applied = apply_desktop_preset(self.adapter, preset)
                    recorder = getattr(session, "recorder", None)
                    if recorder is not None and callable(getattr(recorder, "event", None)):
                        recorder.event(
                            time=_adapter_time(self.adapter),
                            kind="preset",
                            name=str(preset["id"]),
                            value=_preset_event_value(preset, applied),
                        )

                self._submit_session(apply)
            except Exception as exc:
                self._set_error(
                    str(exc),
                    "Restart the live experiment and choose the preset again.",
                )
                return

            self._active_config = next_config
            control_values = dict(getattr(self, "_active_control_values", {}) or {})
            control_values.update(_validated_preset(preset)[2])
            self._active_control_values = control_values
            self.selected_changed.emit()
            self._mark_learner_action(str(preset["id"]))

        def _reset_evidence(self) -> None:
            self._prediction = ""
            self._learner_action_count = 0
            self._observation = {}
            self.evidence_changed.emit()

        def _mark_learner_action(self, name: str) -> None:
            if not self._requires_evidence() or not self._is_experiment_control(name):
                return
            self._learner_action_count += 1
            self.evidence_changed.emit()

        def _requires_evidence(self) -> bool:
            selected = getattr(self, "_selected", None)
            completion = getattr(selected, "completion", None)
            return bool(
                completion
                and (
                    completion.requires_learner_control
                    or completion.requires_observation
                )
            )

        def _is_experiment_control(self, name: str) -> bool:
            if str(name) in {"orbit", "pan", "zoom", "reset_camera"}:
                return False
            if getattr(self, "_selected", None) is None:
                return False
            payload = self._scenario_map(self._selected)
            ids = {
                str(item.get("id", ""))
                for item in (
                    *payload.get("actions", ()),
                    *payload.get("presets", ()),
                    *payload.get("controls", ()),
                )
            }
            return str(name) in ids

        def _evidence_editable(self) -> bool:
            session = getattr(self, "session", None)
            return bool(
                self._requires_evidence()
                and session is not None
                and not bool(getattr(self, "_replay_mode", False))
                and session.replay_archive is None
                and session.state
                in {SessionState.READY, SessionState.RUNNING, SessionState.PAUSED}
            )

        def _queue_evidence(
            self,
            kind: str,
            name: str,
            value: Any,
            label: str,
            *,
            resume: bool = False,
        ) -> None:
            session = self.session

            def record() -> None:
                session.record_evidence(kind, name, value, label=label)
                if resume and session.state == SessionState.PAUSED:
                    session.resume()

            self._submit_session(record)

        def _evidence_error(self, key: str) -> None:
            self._set_error(
                self.translator.text(key),
                self.translator.text("evidence.recovery"),
            )

    return EvidenceBackendMixin


def _clean_text(value: str, limit: int) -> str:
    return " ".join(str(value).split())[:limit].strip()


def _validated_preset(
    preset: Mapping[str, Any],
) -> tuple[str, str, dict[str, float]]:
    preset_id = str(preset.get("id") or "").strip()
    label = str(preset.get("canonicalLabel") or preset.get("label") or "").strip()
    raw_values = preset.get("values")
    if not preset_id or not label or not isinstance(raw_values, Mapping):
        raise ValueError("Quick preset metadata is incomplete")
    values: dict[str, float] = {}
    for raw_name, raw_value in raw_values.items():
        if isinstance(raw_value, bool):
            raise ValueError(f"Quick preset value {raw_name!r} is not numeric")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Quick preset value {raw_name!r} is not numeric") from exc
        if not math.isfinite(value):
            raise ValueError(f"Quick preset value {raw_name!r} is not finite")
        values[str(raw_name)] = value
    if not values:
        raise ValueError("Quick preset has no values")
    return preset_id, label, values


def _preset_event_value(
    preset: Mapping[str, Any], values: Mapping[str, float]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"values": dict(values)}
    purpose = str(preset.get("purpose") or "").strip()
    if purpose:
        payload["purpose"] = purpose
    if bool(preset.get("required", False)):
        payload["required"] = True
    return payload


def _adapter_time(adapter: Any) -> float:
    try:
        return float(getattr(adapter, "time", 0.0))
    except (AttributeError, TypeError, ValueError):
        return 0.0


def _apply_trajectory_offset(
    target: dict[str, Any], base_config: Mapping[str, Any], offset: float
) -> None:
    trajectory = base_config.get("trajectory")
    trajectory = trajectory if isinstance(trajectory, Mapping) else {}
    start = float(trajectory.get("start", 0.0))
    end = float(trajectory.get("end", start))
    _set_nested_config_value(target, "trajectory.start", start + offset)
    _set_nested_config_value(target, "trajectory.end", end + offset)


def _capped_torque_limits(base_config: Mapping[str, Any], value: float) -> list[float]:
    controller = base_config.get("tracking_controller")
    controller = controller if isinstance(controller, Mapping) else {}
    raw = controller.get("torque_limit", [value, value])
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        limits = [abs(float(raw[0])), abs(float(raw[1]))]
    else:
        limit = abs(float(raw))
        limits = [limit, limit]
    cap = abs(float(value))
    return [min(limit, cap) for limit in limits]


def _set_nested_config_value(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = target
    for index, part in enumerate(parts[:-1]):
        next_part = parts[index + 1]
        if isinstance(current, dict):
            if part not in current:
                current[part] = [] if next_part.isdigit() else {}
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise ValueError(f"Cannot update active config path {path!r}")
    final = parts[-1]
    if isinstance(current, dict):
        current[final] = deepcopy(value)
    elif isinstance(current, list) and final.isdigit() and int(final) < len(current):
        current[int(final)] = deepcopy(value)
    else:
        raise ValueError(f"Cannot update active config path {path!r}")
