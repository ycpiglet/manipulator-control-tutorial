"""Dependency-free view models for the Qt Quick scenario cards."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from mclab.application.batch_runs import ALL_COMPARE_ID
from mclab.application.catalog import (
    BatchDefinition,
    ScenarioCatalog,
    ScenarioDefinition,
    target_from_legacy_summary,
)
from mclab.application.completion_progress import (
    TargetCompletionAssessment,
    assess_target_completion,
    build_completion_assessment_index,
)
from mclab.application.i18n import Translator, localized_scenario_text
from mclab.application.readiness import scenario_readiness, scenario_readiness_payload
from mclab.application.repositories import ArtifactRecord
from mclab.completion import CompletionRecordKind, evaluate_completion

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
    control_values_override: dict[str, float] | None = None,
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
        if control_values_override is not None and control.id in control_values_override:
            value = control_values_override[control.id]
        else:
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
    presets = _scenario_presets(config)
    required_preset_labels = [
        str(preset["canonicalLabel"]) for preset in presets if preset["required"]
    ]
    required_preset_guide = ""
    if required_preset_labels:
        prefix = "필수 순서" if translator.language == "ko" else "Required order"
        required_preset_guide = f"{prefix}: {' → '.join(required_preset_labels)}"
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
        "presets": presets,
        "requiredPresetGuide": required_preset_guide,
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
    catalog: ScenarioCatalog | None = None,
) -> dict[str, Any]:
    """Build one canonical path snapshot from independently assessed runs."""

    items = tuple(scenarios)
    saved_records = tuple(records)
    scenario_catalog = catalog or _cached_default_catalog()
    scenario_index = build_completion_assessment_index(items, saved_records)
    batch_target = scenario_catalog.get_batch(ALL_COMPARE_ID)
    batch_assessment = assess_target_completion(batch_target, saved_records)
    completed_ids = set(scenario_index.completed_target_ids)
    if batch_assessment.complete:
        completed_ids.add(ALL_COMPARE_ID)
    path = learning_path_payload(items, translator, completed_ids)
    for scenario, payload in zip(items, path, strict=True):
        payload.update(_completion_assessment_payload(scenario_index.get(scenario.id)))
    next_scenario = next((item for item in items if item.id not in completed_ids), None)
    batch = _all_compare_payload(translator, batch_readiness)
    batch.update(
        step=len(path) + 1,
        completed=ALL_COMPARE_ID in completed_ids,
        isNext=next_scenario is None and ALL_COMPARE_ID not in completed_ids,
    )
    batch.update(_completion_assessment_payload(batch_assessment))
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


def _completion_assessment_payload(
    assessment: TargetCompletionAssessment,
) -> dict[str, Any]:
    latest = assessment.latest_record
    credited = assessment.credited_record
    latest_decision = assessment.latest_decision.to_dict()
    credited_decision = (
        assessment.credited_decision.to_dict()
        if assessment.credited_decision is not None
        else {}
    )
    return {
        # Keep the compatibility field aligned with ``completed`` while exposing
        # the newest-attempt diagnostic under an unambiguous name.
        "completionDecision": credited_decision or latest_decision,
        "latestCompletionDecision": latest_decision,
        "creditedCompletionDecision": credited_decision,
        "latestRun": str(latest.path) if isinstance(latest, ArtifactRecord) else "",
        "creditedRun": str(credited.path) if isinstance(credited, ArtifactRecord) else "",
    }


@lru_cache(maxsize=1)
def _cached_default_catalog() -> ScenarioCatalog:
    """Avoid rebuilding the immutable on-disk catalog for every QML binding."""

    return ScenarioCatalog.default()


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
    scenario_catalog = catalog or _cached_default_catalog()
    collection_summary = translator.text(
        "results.collection",
        count=len(records),
        size=format_size(sum(item.size_bytes for item in records)),
    )
    payloads: list[dict[str, Any]] = []
    active_batch = Path(active_batch_path).resolve() if active_batch_path else None
    for index, item in enumerate(records, start=1):
        try:
            target = scenario_catalog.get_target(item.scenario_id)
        except KeyError:
            target = None
        if (
            target is None
            and item.completion_evidence.record_kind
            == CompletionRecordKind.LEGACY_SUMMARY
        ):
            target = target_from_legacy_summary(scenario_catalog, item.summary)
            if target is not None:
                item = replace(item, scenario_id=target.id)
        completion = evaluate_completion(
            target.completion if target is not None else None,
            item.completion_evidence,
        )
        is_batch = isinstance(target, BatchDefinition) or item.scenario_id == ALL_COMPARE_ID
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
        scenario = target if isinstance(target, ScenarioDefinition) else None
        if is_batch:
            title = (
                translator.text("path.batch_title")
                if item.scenario_id == ALL_COMPARE_ID
                else str(getattr(target, "batch_name", item.scenario_id)).replace("_", " ").title()
            )
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
        lifecycle_status = display_item.status.casefold()
        completion_incomplete = not completion.complete and lifecycle_status not in {
            "running",
            "stopped",
            "error",
        }
        recording_missing = (
            completion.complete
            and not is_batch
            and lifecycle_status == "completed"
            and not display_item.replay_available
        )
        status_code = (
            "warning"
            if completion_incomplete or recording_missing
            else display_item.status
        )
        if completion_incomplete:
            status_text = translator.text("results.status.completion_incomplete")
        elif recording_missing:
            status_text = translator.text("results.status.recording_missing")
        else:
            status_text = translator.mapping().get(
                f"status.{display_item.status}", display_item.status
            )
        availability = _result_availability(item, translator, is_batch=is_batch)
        payloads.append(
            {
                "path": str(item.path),
                "name": item.path.name,
                "cleanupToken": item.cleanup_token,
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
                "outcome": _result_outcome(
                    display_item,
                    translator,
                    completion_complete=completion.complete,
                    is_batch=is_batch,
                ),
                "nextAction": _result_next_action(
                    display_item,
                    translator,
                    completion_complete=completion.complete,
                    is_batch=is_batch,
                ),
                "metrics": metrics,
                "availability": availability,
                "replay": item.replay_available,
                "rerun": item.rerun_available,
                "tuned": item.tuned_available,
                "report": item.report_available,
                "worksheet": item.worksheet_available,
                "canRerunBatch": item.scenario_id == ALL_COMPARE_ID,
                "reportPath": str(item.path / "report.html"),
                "legacy": item.legacy,
                "replayReason": item.replay_reason,
                "completed": completion.complete,
                "completionReason": completion.primary_reason.value,
                "completionReasonText": translator.text(
                    "results.completion_reason."
                    + completion.primary_reason.value.rsplit(".", 1)[-1]
                ),
                "completionDecision": completion.to_dict(),
            }
        )
    return payloads


def _result_outcome(
    item: ArtifactRecord,
    translator: Translator,
    *,
    completion_complete: bool,
    is_batch: bool,
) -> str:
    if (
        item.scenario_id == ALL_COMPARE_ID
        and item.status == "completed"
        and completion_complete
    ):
        return translator.text(
            "results.outcome.batch_completed",
            sets=item.summary.get("child_batches", "—"),
            runs=item.summary.get("scenario_runs", "—"),
        )
    if is_batch and item.status == "completed" and completion_complete:
        return translator.text("results.outcome.batch_target_completed")
    if not completion_complete and item.status not in {"running", "stopped", "error"}:
        outcome = "incomplete"
    elif (
        not is_batch
        and item.status == "completed"
        and completion_complete
        and not item.replay_available
    ):
        outcome = "recording_missing"
    else:
        outcome = (
            item.status
            if item.status in {"completed", "running", "stopped", "error"}
            else "completed"
        )
    duration = item.summary.get("duration")
    seconds = f"{float(duration):.1f}" if isinstance(duration, (int, float)) else "—"
    return translator.text(f"results.outcome.{outcome}", duration=seconds)


def _result_next_action(
    item: ArtifactRecord,
    translator: Translator,
    *,
    completion_complete: bool,
    is_batch: bool,
) -> str:
    if is_batch and item.scenario_id == ALL_COMPARE_ID:
        key = (
            "results.next.wait"
            if item.status == "running"
            else "results.next.compare"
            if item.status == "completed" and completion_complete
            else "results.next.retry_compare"
        )
    elif is_batch:
        key = (
            "results.next.wait_batch"
            if item.status == "running"
            else "results.next.review_batch"
            if item.status == "completed" and completion_complete and item.report_available
            else "results.next.details"
        )
    elif item.replay_available:
        key = "results.next.replay"
    elif completion_complete and item.rerun_available:
        key = "results.next.restore_recording"
    elif item.status in {"stopped", "error"} and item.rerun_available:
        key = "results.next.finish"
    elif item.rerun_available:
        key = "results.next.rerun"
    else:
        key = "results.next.details"
    return translator.text(key)


def _result_availability(
    item: ArtifactRecord,
    translator: Translator,
    *,
    is_batch: bool,
) -> str:
    if not is_batch:
        return " · ".join(
            translator.text(key)
            for key in (
                "results.recording_yes" if item.replay_available else "results.recording_no",
                "results.rerun_yes" if item.rerun_available else "results.rerun_no",
                "results.tuned_yes" if item.tuned_available else "results.tuned_no",
            )
        )
    if item.report_available and item.worksheet_available:
        return translator.text("results.batch_evidence")
    return " · ".join(
        (
            translator.text(
                "results.report_yes" if item.report_available else "results.report_no"
            ),
            translator.text(
                "results.worksheet_yes"
                if item.worksheet_available
                else "results.worksheet_no"
            ),
            translator.text("results.batch_recording_not_expected"),
        )
    )


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


def _scenario_presets(config: dict[str, Any]) -> list[dict[str, Any]]:
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return []
    raw_presets = interaction.get("tuning_presets")
    if not isinstance(raw_presets, list):
        return []

    presets: list[dict[str, Any]] = []
    required_order = 0
    required_total = sum(
        1 for item in raw_presets if isinstance(item, dict) and bool(item.get("required"))
    )
    for index, raw_preset in enumerate(raw_presets, start=1):
        if not isinstance(raw_preset, dict):
            continue
        raw_values = raw_preset.get("values")
        if not isinstance(raw_values, dict):
            continue
        values: dict[str, float] = {}
        for raw_name, raw_value in raw_values.items():
            if isinstance(raw_value, bool):
                continue
            try:
                number = float(raw_value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                values[str(raw_name)] = number
        if not values:
            continue

        label = str(raw_preset.get("label") or raw_preset.get("name") or f"Preset {index}").strip()
        preset_id = str(raw_preset.get("name") or _preset_id(label, index))
        required = bool(raw_preset.get("required", False))
        if required:
            required_order += 1
        presets.append(
            {
                "id": preset_id,
                "label": label,
                # Completion evidence always records this YAML label, even if
                # a future UI localizes the visible label.
                "canonicalLabel": label,
                "purpose": str(
                    raw_preset.get("purpose") or raw_preset.get("description") or ""
                ).strip(),
                "required": required,
                "requiredOrder": required_order if required else 0,
                "requiredTotal": required_total,
                "values": values,
            }
        )
    return presets


def _preset_id(label: str, index: int) -> str:
    name = "_".join(label.lower().split())
    return name or f"preset_{index}"


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
