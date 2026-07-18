"""Dependency-free view models for the Qt Quick scenario cards."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from mclab.application.batch_runs import ALL_COMPARE_ID
from mclab.application.catalog import ScenarioCatalog, ScenarioDefinition
from mclab.application.i18n import Translator, localized_scenario_text
from mclab.application.readiness import scenario_readiness, scenario_readiness_payload
from mclab.application.repositories import ArtifactRecord

_CONTROL_UNITS = {
    "mass": "kg",
    "damping": "N·s/m",
    "stiffness": "N/m",
    "target_position": "m",
    "target_offset": "m",
    "target_x": "m",
    "target_y": "m",
    "target_z": "m",
    "wall_x": "m",
    "wall_stiffness": "N/m",
    "wall_damping": "N·s/m",
    "output_limit": "N",
    "force_limit": "N",
    "q1_offset": "rad",
    "q2_offset": "rad",
    "joint_target_offset": "rad",
    "torque_limit": "N·m",
}


def _display_digits(step: float) -> int:
    text = f"{abs(float(step)):.8f}".rstrip("0").rstrip(".")
    return len(text.rsplit(".", 1)[1]) if "." in text else 0


def scenario_payload(
    scenario: ScenarioDefinition | None,
    translator: Translator,
    *,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scenario is None:
        return {}
    config = config_override or scenario.config
    title, purpose = localized_scenario_text(
        language=translator.language,
        scenario_id=scenario.id,
        title=scenario.title,
        purpose=scenario.purpose,
        lab_name=scenario.lab_name,
    )
    controls = []
    for control in scenario.controls:
        value = _nested_value(
            config,
            control.config_path,
            control.default if control.default is not None else control.minimum,
        )
        if isinstance(value, (list, tuple)):
            value = max(abs(float(item)) for item in value)
        controls.append(
            {
                "id": control.id,
                "label": translator.text(control.label_key),
                "minimum": control.minimum,
                "maximum": control.maximum,
                "step": control.step,
                "value": float(value),
                "digits": _display_digits(control.step),
                "unit": _CONTROL_UNITS.get(control.id, ""),
            }
        )
    actions = _scenario_actions(scenario, config, translator)
    mode = str(config.get("mode", "")).lower()
    is_two_link = (
        scenario.lab_name == "lab03"
        and str(config.get("plant", "")).lower() == "two_link_arm"
    )
    is_wall = scenario.lab_name == "lab04" and mode in {
        "impedance_wall",
        "virtual_wall",
        "wall",
    }
    application = dict(config.get("application", {}))
    requires_evidence = bool(
        scenario.completion.requires_learner_control
        or scenario.completion.requires_observation
    )
    payload = {
        "id": scenario.id,
        "kind": "scenario",
        "lab": scenario.lab_name,
        "title": title,
        "displayTitle": f"{scenario.lab_name.upper()} · {title}",
        "purpose": purpose,
        "nowPrompt": _now_prompt(actions, controls, translator),
        "predictionPrompt": translator.text(
            _prediction_prompt_key(scenario, mode, is_two_link, is_wall)
        ) if requires_evidence else "",
        "requiresEvidence": requires_evidence,
        "difficultyId": scenario.difficulty,
        "difficulty": translator.text(f"difficulty.{scenario.difficulty}"),
        "minutes": scenario.estimated_minutes,
        "controls": controls,
        "actions": actions,
        "startsPaused": bool(application.get("start_paused", False)),
        "config": scenario.config_path,
        "plotPreset": scenario.plot_preset,
        "spatialMotion": is_two_link or scenario.lab_name == "lab04",
        "showForce": scenario.lab_name in {"lab01", "lab02"} or is_wall,
        "showWall": is_wall,
        "showSingularity": is_two_link,
        "showWorkspace": is_two_link,
    }
    payload.update(scenario_readiness_payload(scenario_readiness(scenario), translator))
    return payload


def learning_path_payload(
    scenarios: Iterable[ScenarioDefinition],
    translator: Translator,
    tried_ids: set[str],
) -> list[dict[str, Any]]:
    """Add explicit position and completion state to the recommended path."""

    items = tuple(scenarios)
    next_id = next((item.id for item in items if item.id not in tried_ids), None)
    payloads: list[dict[str, Any]] = []
    for index, scenario in enumerate(items, start=1):
        payload = scenario_payload(scenario, translator)
        payload.update(
            step=index,
            completed=scenario.id in tried_ids,
            isNext=scenario.id == next_id,
        )
        payloads.append(payload)
    return payloads


def course_progress_payload(
    scenarios: Iterable[ScenarioDefinition],
    translator: Translator,
    records: Iterable[ArtifactRecord],
    *,
    batch_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one consistent path snapshot from successful saved runs."""

    items = tuple(scenarios)
    completed_ids = {
        record.scenario_id for record in records if record.status.casefold() == "completed"
    }
    path = learning_path_payload(items, translator, completed_ids)
    next_scenario = next((item for item in items if item.id not in completed_ids), None)
    batch = _all_compare_payload(translator, batch_readiness)
    batch.update(
        step=len(path) + 1,
        completed=ALL_COMPARE_ID in completed_ids,
        isNext=next_scenario is None and ALL_COMPARE_ID not in completed_ids,
    )
    path.append(batch)
    next_item = scenario_payload(next_scenario, translator) if next_scenario else batch
    complete = next_scenario is None and ALL_COMPARE_ID in completed_ids
    done = sum(item.id in completed_ids for item in items) + int(
        ALL_COMPARE_ID in completed_ids
    )
    return {
        "done": done,
        "total": len(path),
        "complete": complete,
        "nextId": "" if complete else str(next_item["id"]),
        "nextKind": "" if complete else str(next_item["kind"]),
        "next": {} if complete else next_item,
        "path": path,
    }


def _all_compare_payload(
    translator: Translator,
    readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "id": ALL_COMPARE_ID,
        "kind": "batch",
        "lab": translator.text("path.course"),
        "title": translator.text("path.batch_title"),
        "purpose": translator.text("path.batch_purpose"),
        "difficulty": translator.text("path.review"),
        "minutes": 10,
        "ready": True,
        "readinessDetail": "",
        "readinessAction": "",
    }
    if readiness is not None and not readiness.get("ready", True):
        payload.update(
            ready=False,
            readinessDetail=str(readiness.get("detail", "")),
            readinessAction=str(readiness.get("action", "")),
        )
    return payload


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def telemetry_items(
    scenario: ScenarioDefinition | None,
    config: dict[str, Any],
    telemetry: dict[str, float],
    translator: Translator,
) -> list[dict[str, str]]:
    if scenario is None:
        return []
    lab = scenario.lab_name
    if lab in {"lab01", "lab02"} or (
        lab == "lab03" and str(config.get("plant", "")).lower() != "two_link_arm"
    ):
        items = (
            ("value.position", "position", "m", 3),
            ("value.velocity", "velocity", "m/s", 3),
            ("value.force", "force", "N", 1),
        )
    elif lab == "lab03":
        items = (
            ("value.hand_x", "hand_x", "m", 3),
            ("value.tracking_error", "error", "", 3),
            ("value.condition", "condition", "", 1),
        )
    else:
        wall_mode = str(config.get("mode", "")).lower() in {
            "impedance_wall",
            "virtual_wall",
            "wall",
        }
        items = (
            ("value.hand_x", "hand_x", "m", 3),
            ("value.tracking_error", "error", "cm" if wall_mode else "", 2),
            (
                "value.wall_penetration" if wall_mode else "value.force",
                "wall_penetration" if wall_mode else "force",
                "cm" if wall_mode else "N",
                2 if wall_mode else 1,
            ),
        )
    return [
        {
            "label": translator.text(label),
            "value": f"{float(telemetry.get(key, 0.0)):.{digits}f}",
            "unit": unit,
        }
        for label, key, unit, digits in items
    ]


def result_payloads(
    records: tuple[ArtifactRecord, ...],
    translator: Translator,
    catalog: ScenarioCatalog | None = None,
    active_batch_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    scenario_catalog = catalog or ScenarioCatalog.default()
    collection_summary = translator.text(
        "results.collection",
        count=len(records),
        size=format_size(sum(item.size_bytes for item in records)),
    )
    payloads: list[dict[str, Any]] = []
    active_batch = Path(active_batch_path).resolve() if active_batch_path else None
    for index, item in enumerate(records, start=1):
        is_batch = item.scenario_id == ALL_COMPARE_ID
        active_batch_record = (
            is_batch and active_batch is not None and item.path.resolve() == active_batch
        )
        display_item = (
            replace(item, status="stopped")
            if is_batch
            and item.status == "running"
            and (active_batch is None or item.path.resolve() != active_batch)
            else item
        )
        try:
            scenario = scenario_catalog.get(item.scenario_id)
        except KeyError:
            scenario = None
        if is_batch:
            title = translator.text("path.batch_title")
            lab = translator.text("path.course")
        elif scenario is None:
            title = item.scenario_id
            lab = item.scenario_id.split(".", 1)[0].upper()
        else:
            title, _ = localized_scenario_text(
                language=translator.language,
                scenario_id=scenario.id,
                title=scenario.title,
                purpose=scenario.purpose,
                lab_name=scenario.lab_name,
            )
            lab = scenario.lab_name.upper()
        metrics = _result_metric_items(item.summary, translator)
        status_code = (
            "warning"
            if not is_batch
            and display_item.status == "completed"
            and not display_item.replay_available
            else display_item.status
        )
        status_text = (
            translator.text("results.status.recording_missing")
            if status_code == "warning"
            else translator.mapping().get(
                f"status.{display_item.status}", display_item.status
            )
        )
        availability = translator.text("results.batch_evidence") if is_batch else " · ".join(
            translator.text(key)
            for key in (
                "results.recording_yes" if item.replay_available else "results.recording_no",
                "results.rerun_yes" if item.rerun_available else "results.rerun_no",
                "results.tuned_yes" if item.tuned_available else "results.tuned_no",
            )
        )
        payloads.append(
            {
                "path": str(item.path),
                "name": item.path.name,
                "scenarioId": item.scenario_id,
                "isBatch": is_batch,
                "activeBatch": active_batch_record,
                "title": title,
                "lab": lab,
                "runLabel": translator.text(
                    "results.latest" if index == 1 else "results.older_run",
                    index=index,
                ),
                "status": status_text,
                "statusCode": status_code,
                "size": format_size(item.size_bytes),
                "deleteWarning": translator.text(
                    "results.delete_warning", size=format_size(item.size_bytes)
                ),
                "collectionSummary": collection_summary,
                "outcome": _result_outcome(display_item, translator),
                "nextAction": _result_next_action(display_item, translator),
                "metrics": metrics,
                "availability": availability,
                "replay": item.replay_available,
                "rerun": item.rerun_available,
                "tuned": item.tuned_available,
                "report": (item.path / "report.html").is_file(),
                "reportPath": str(item.path / "report.html"),
                "legacy": item.legacy,
                "replayReason": item.replay_reason,
            }
        )
    return payloads


def _result_outcome(
    item: ArtifactRecord,
    translator: Translator,
) -> str:
    if item.scenario_id == ALL_COMPARE_ID and item.status == "completed":
        return translator.text(
            "results.outcome.batch_completed",
            sets=item.summary.get("child_batches", "—"),
            runs=item.summary.get("scenario_runs", "—"),
        )
    if item.status == "completed" and not item.replay_available:
        outcome = "incomplete"
    else:
        outcome = (
            item.status
            if item.status in {"completed", "running", "stopped", "error"}
            else "completed"
        )
    duration = item.summary.get("duration")
    seconds = f"{float(duration):.1f}" if isinstance(duration, (int, float)) else "—"
    return translator.text(f"results.outcome.{outcome}", duration=seconds)


def _result_next_action(item: ArtifactRecord, translator: Translator) -> str:
    if item.scenario_id == ALL_COMPARE_ID:
        key = (
            "results.next.wait"
            if item.status == "running"
            else "results.next.compare"
            if item.status == "completed"
            else "results.next.retry_compare"
        )
    elif item.replay_available:
        key = "results.next.replay"
    elif item.status in {"stopped", "error"} and item.rerun_available:
        key = "results.next.finish"
    elif item.rerun_available:
        key = "results.next.rerun"
    else:
        key = "results.next.details"
    return translator.text(key)


def _result_metric_items(
    summary: dict[str, Any],
    translator: Translator,
) -> list[dict[str, str]]:
    if summary.get("batch_name") == "all":
        specs = (
            ("child_batches", "results.metric.batch_count", "", 0),
            ("scenario_runs", "results.metric.scenario_runs", "", 0),
            ("duration", "results.metric.batch_duration", "s", 1),
        )
    elif "max_wall_penetration_cm" in summary:
        specs = (
            ("max_wall_penetration_cm", "results.metric.wall_penetration", "cm", 2),
            ("max_abs_virtual_wall_force", "results.metric.wall_force", "N", 1),
            ("wall_contact_episodes", "results.metric.contact_count", "", 0),
        )
    elif "max_jacobian_condition" in summary:
        specs = (
            ("final_task_error_norm", "results.metric.final_error", "m", 4),
            ("max_jacobian_condition", "results.metric.condition", "", 1),
            ("max_abs_tau_total", "results.metric.peak_torque", "N·m", 2),
        )
    elif "settling_time" in summary:
        specs = (
            ("steady_state_error", "results.metric.final_error", "m", 4),
            ("settling_time", "results.metric.settling_time", "s", 2),
            ("overshoot_percent", "results.metric.overshoot", "%", 1),
        )
    else:
        specs = (
            ("max_abs_position", "results.metric.peak_position", "m", 3),
            ("duration", "results.metric.duration", "s", 1),
            ("interaction_events", "results.metric.actions", "", 0),
        )
    items: list[dict[str, str]] = []
    for key, label, unit, digits in specs:
        value = summary.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        items.append(
            {
                "label": translator.text(label),
                "value": f"{float(value):.{digits}f}",
                "unit": unit,
            }
        )
    return items


def _scenario_actions(
    scenario: ScenarioDefinition,
    config: dict[str, Any],
    translator: Translator,
) -> list[dict[str, str]]:
    interaction = dict(config.get("interaction", {}))
    if scenario.lab_name == "lab03" and str(config.get("plant", "")).lower() == "two_link_arm":
        if interaction.get("joint_disturbance"):
            return [
                {"id": "shoulder_pulse", "label": translator.text("control.shoulder_pulse")},
                {"id": "elbow_pulse", "label": translator.text("control.elbow_pulse")},
            ]
        return []
    if scenario.lab_name == "lab04" and interaction.get("target_nudge"):
        return [
            {"id": "target_x_decrease", "label": translator.text("control.target_x_decrease")},
            {"id": "target_x_increase", "label": translator.text("control.target_x_increase")},
        ]
    if interaction.get("key_force") or scenario.lab_name in {"lab01", "lab02"}:
        return [
            {"id": "pull", "label": translator.text("control.pull")},
            {"id": "push", "label": translator.text("control.push")},
        ]
    return []


def _now_prompt(
    actions: list[dict[str, str]],
    controls: list[dict[str, Any]],
    translator: Translator,
) -> str:
    preferred_ids = ("target_x_increase", "push", "elbow_pulse")
    action = next(
        (item for action_id in preferred_ids for item in actions if item["id"] == action_id),
        actions[0] if actions else None,
    )
    control = controls[0] if controls else None
    if action is not None and control is not None:
        return translator.text(
            "experiment.prompt_action_control",
            action=action["label"],
            control=control["label"],
        )
    if action is not None:
        return translator.text("experiment.prompt_action", action=action["label"])
    if control is not None:
        return translator.text("experiment.prompt_control", control=control["label"])
    return translator.text("experiment.prompt_observe")


def _prediction_prompt_key(
    scenario: ScenarioDefinition,
    mode: str,
    is_two_link: bool,
    is_wall: bool,
) -> str:
    if scenario.lab_name == "lab01":
        return "evidence.prediction.lab01"
    if scenario.lab_name == "lab02":
        return "evidence.prediction.lab02"
    if scenario.lab_name == "lab03":
        if not is_two_link:
            return "evidence.prediction.lab03_tracking"
        return (
            "evidence.prediction.lab03_singularity"
            if "dls" in mode
            else "evidence.prediction.lab03_arm"
        )
    if is_wall:
        return "evidence.prediction.lab04_wall"
    if scenario.lab_name == "lab04" and mode.startswith("joint"):
        return "evidence.prediction.lab04_joint"
    if scenario.lab_name == "lab04":
        return "evidence.prediction.lab04_cartesian"
    return "evidence.prediction_placeholder"


def _nested_value(config: Any, path: str, default: Any) -> Any:
    if not path:
        return default
    value = config
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, (list, tuple)) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return default
    return value
