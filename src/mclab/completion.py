"""Versioned, read-only course-completion contract.

This module deliberately contains no filesystem or UI code.  Readers normalize
saved-run metadata and interaction events into :class:`CompletionEvidence`, then
all learner surfaces can apply the same deterministic rule in COMP-02.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


COMPLETION_CONTRACT_VERSION = 1


class CompletionRecordKind(str, Enum):
    """Provenance state for the metadata used by a completion decision."""

    MANIFEST_V1 = "manifest_v1"
    LEGACY_SUMMARY = "legacy_summary"
    MISSING = "missing"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    SCENARIO_MISMATCH = "scenario_mismatch"


class CompletionReason(str, Enum):
    """Stable, versioned wire reasons in deterministic evaluation order."""

    COMPLETE = "completion.v1.complete"
    RULE_UNAVAILABLE = "completion.v1.rule_unavailable"
    RULE_INVALID = "completion.v1.rule_invalid"
    MANIFEST_MISSING = "completion.v1.manifest_missing"
    LEGACY_MANIFEST_MISSING = "completion.v1.legacy_manifest_missing"
    MANIFEST_INVALID = "completion.v1.manifest_invalid"
    MANIFEST_SCHEMA_UNSUPPORTED = "completion.v1.manifest_schema_unsupported"
    SCENARIO_MISMATCH = "completion.v1.scenario_mismatch"
    RUN_NOT_COMPLETED = "completion.v1.run_not_completed"
    PLOT_MISSING = "completion.v1.plot_missing"
    REQUIRED_ARTIFACT_MISSING = "completion.v1.required_artifact_missing"
    INTERACTION_EVIDENCE_INVALID = "completion.v1.interaction_evidence_invalid"
    OBSERVATION_MISSING = "completion.v1.observation_missing"
    PREDICTION_MISSING = "completion.v1.prediction_missing"
    NOTE_MISSING = "completion.v1.note_missing"
    REQUIRED_PRESET_MISSING = "completion.v1.required_preset_missing"
    LEARNER_CONTROL_MISSING = "completion.v1.learner_control_missing"


@dataclass(frozen=True)
class CompletionRule:
    """Evidence explicitly required for one catalog scenario."""

    requires_run: bool = True
    requires_plot: bool = False
    requires_learner_control: bool = False
    requires_observation: bool = False
    requires_prediction: bool = False
    requires_note: bool = False
    required_presets: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservationEvidence:
    """Correlated evidence from one observation marker."""

    has_prediction: bool = False
    has_note: bool = False
    has_outcome: bool = False


@dataclass(frozen=True)
class InteractionEvidence:
    """Normalized learner evidence without retaining arbitrary event payloads."""

    valid: bool = True
    learner_control_count: int = 0
    observations: tuple[ObservationEvidence, ...] = ()
    preset_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletionEvidence:
    """Read-only facts supplied to the completion evaluator."""

    record_kind: CompletionRecordKind
    status: str | None = None
    plot_count: int = 0
    interaction: InteractionEvidence = InteractionEvidence()
    artifact_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletionDecision:
    """Deterministic result suitable for every learner-facing consumer."""

    contract_version: int
    complete: bool
    primary_reason: CompletionReason
    reasons: tuple[CompletionReason, ...]
    outcome_review_pending: bool = False
    next_required_preset: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a stable serialization containing only versioned wire values."""

        return {
            "contract_version": self.contract_version,
            "complete": self.complete,
            "primary_reason": self.primary_reason.value,
            "reasons": [reason.value for reason in self.reasons],
            "outcome_review_pending": self.outcome_review_pending,
            "next_required_preset": self.next_required_preset,
        }


NON_LEARNER_CONTROL_BUTTON_NAMES = frozenset(
    {
        "clear_observation_note",
        "pause_simulation",
        "resume_simulation",
        "step_simulation",
        "use_changed_values_note",
        "use_live_status_note",
    }
)
NON_LEARNER_CONTROL_SLIDER_NAMES = frozenset({"playback_speed"})
PREDICTION_OUTCOMES = frozenset({"matched", "partly matched", "surprised"})


def summarize_interaction_events(events: object) -> InteractionEvidence:
    """Normalize an event list while preserving observation-marker correlation.

    ``None`` represents an absent optional event file and is a valid empty set.
    A present non-list payload or a non-object list entry is invalid evidence and
    therefore fails closed only when the selected rule requires interaction data.
    """

    if events is None:
        return InteractionEvidence()
    if not isinstance(events, list | tuple):
        return InteractionEvidence(valid=False)

    valid = True
    learner_controls = 0
    observations: list[ObservationEvidence] = []
    preset_labels: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            valid = False
            continue
        kind = _normalized_text(event.get("kind"))
        name = _normalized_text(event.get("name"))
        if not kind:
            valid = False
            continue
        if _is_learner_control_event(kind, name):
            learner_controls += 1
        if kind == "preset":
            label = _clean_text(event.get("label")) or _clean_text(event.get("name"))
            if label:
                preset_labels.append(label)
        if kind != "marker" or name != "observation":
            continue
        value = event.get("value")
        if not isinstance(value, Mapping):
            valid = False
            continue
        observations.append(
            ObservationEvidence(
                has_prediction=bool(_clean_text(value.get("prediction"))),
                has_note=bool(_clean_text(value.get("note"))),
                has_outcome=_normalized_text(value.get("outcome")) in PREDICTION_OUTCOMES,
            )
        )
    return InteractionEvidence(
        valid=valid,
        learner_control_count=learner_controls,
        observations=tuple(observations),
        preset_labels=tuple(preset_labels),
    )


def completion_evidence_from_payloads(
    manifest: object,
    *,
    expected_scenario_id: str,
    plot_count: int = 0,
    interaction_events: object = None,
    legacy_summary: object = None,
    artifact_keys: tuple[str, ...] = (),
) -> CompletionEvidence:
    """Normalize already-read payloads without mutating or rewriting them."""

    interaction = summarize_interaction_events(interaction_events)
    if manifest is None:
        kind = (
            CompletionRecordKind.LEGACY_SUMMARY
            if isinstance(legacy_summary, Mapping)
            else CompletionRecordKind.MISSING
        )
        return CompletionEvidence(
            kind,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    if not isinstance(manifest, Mapping):
        return CompletionEvidence(
            CompletionRecordKind.INVALID,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        return CompletionEvidence(
            CompletionRecordKind.UNSUPPORTED,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    scenario_id = manifest.get("scenario_id")
    status = manifest.get("status")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        return CompletionEvidence(
            CompletionRecordKind.INVALID,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    if scenario_id != expected_scenario_id:
        return CompletionEvidence(
            CompletionRecordKind.SCENARIO_MISMATCH,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    if not isinstance(status, str) or not status:
        return CompletionEvidence(
            CompletionRecordKind.INVALID,
            plot_count=plot_count,
            interaction=interaction,
            artifact_keys=artifact_keys,
        )
    return CompletionEvidence(
        CompletionRecordKind.MANIFEST_V1,
        status=status,
        plot_count=plot_count,
        interaction=interaction,
        artifact_keys=artifact_keys,
    )


def evaluate_completion(
    rule: CompletionRule | None,
    evidence: CompletionEvidence,
) -> CompletionDecision:
    """Evaluate declared requirements with stable fail-closed reason ordering."""

    if rule is None:
        return _decision((CompletionReason.RULE_UNAVAILABLE,))
    if not _valid_rule(rule):
        return _decision((CompletionReason.RULE_INVALID,))
    if not isinstance(evidence, CompletionEvidence):
        return _decision((CompletionReason.MANIFEST_INVALID,))

    source_reason = _source_reason(evidence.record_kind)
    if source_reason is not None:
        return _decision((source_reason,))

    reasons: list[CompletionReason] = []
    if rule.requires_run and evidence.status != "completed":
        reasons.append(CompletionReason.RUN_NOT_COMPLETED)
    if rule.requires_plot:
        if not _valid_count(evidence.plot_count) or evidence.plot_count <= 0:
            reasons.append(CompletionReason.PLOT_MISSING)
    available_artifacts = (
        frozenset(evidence.artifact_keys)
        if _valid_artifact_keys(evidence.artifact_keys)
        else frozenset()
    )
    if any(key not in available_artifacts for key in rule.required_artifacts):
        reasons.append(CompletionReason.REQUIRED_ARTIFACT_MISSING)

    requires_interaction = bool(
        rule.requires_learner_control
        or rule.requires_observation
        or rule.requires_prediction
        or rule.requires_note
        or rule.required_presets
    )
    interaction = evidence.interaction
    if not _valid_interaction(interaction):
        if requires_interaction:
            reasons.append(CompletionReason.INTERACTION_EVIDENCE_INVALID)
            return _decision(tuple(reasons))
        interaction = InteractionEvidence()

    observations = interaction.observations
    predicted = tuple(item for item in observations if item.has_prediction)
    noted = tuple(item for item in observations if item.has_note)
    predicted_and_noted = tuple(item for item in predicted if item.has_note)
    if rule.requires_observation and not observations:
        reasons.append(CompletionReason.OBSERVATION_MISSING)
    if rule.requires_prediction and not predicted:
        reasons.append(CompletionReason.PREDICTION_MISSING)
    note_evidence = predicted_and_noted if rule.requires_prediction else noted
    if rule.requires_note and not note_evidence:
        reasons.append(CompletionReason.NOTE_MISSING)

    next_required_preset = _next_required_preset(
        rule.required_presets,
        interaction.preset_labels,
    )
    if next_required_preset:
        reasons.append(CompletionReason.REQUIRED_PRESET_MISSING)
    if rule.requires_learner_control and interaction.learner_control_count <= 0:
        reasons.append(CompletionReason.LEARNER_CONTROL_MISSING)
    if reasons:
        return _decision(tuple(reasons), next_required_preset=next_required_preset)

    outcome_candidates = predicted_and_noted if rule.requires_note else predicted
    outcome_review_pending = bool(
        rule.requires_observation
        and rule.requires_prediction
        and outcome_candidates
        and any(not item.has_outcome for item in outcome_candidates)
    )
    return _decision(
        (CompletionReason.COMPLETE,),
        complete=True,
        outcome_review_pending=outcome_review_pending,
    )


def _decision(
    reasons: tuple[CompletionReason, ...],
    *,
    complete: bool = False,
    outcome_review_pending: bool = False,
    next_required_preset: str = "",
) -> CompletionDecision:
    return CompletionDecision(
        contract_version=COMPLETION_CONTRACT_VERSION,
        complete=complete,
        primary_reason=reasons[0],
        reasons=reasons,
        outcome_review_pending=outcome_review_pending,
        next_required_preset=next_required_preset,
    )


def _source_reason(record_kind: object) -> CompletionReason | None:
    reasons = {
        CompletionRecordKind.LEGACY_SUMMARY: CompletionReason.LEGACY_MANIFEST_MISSING,
        CompletionRecordKind.MISSING: CompletionReason.MANIFEST_MISSING,
        CompletionRecordKind.INVALID: CompletionReason.MANIFEST_INVALID,
        CompletionRecordKind.UNSUPPORTED: CompletionReason.MANIFEST_SCHEMA_UNSUPPORTED,
        CompletionRecordKind.SCENARIO_MISMATCH: CompletionReason.SCENARIO_MISMATCH,
    }
    if record_kind == CompletionRecordKind.MANIFEST_V1:
        return None
    return reasons.get(record_kind, CompletionReason.MANIFEST_INVALID)


def _valid_rule(rule: CompletionRule) -> bool:
    flags = (
        rule.requires_run,
        rule.requires_plot,
        rule.requires_learner_control,
        rule.requires_observation,
        rule.requires_prediction,
        rule.requires_note,
    )
    return (
        all(type(flag) is bool for flag in flags)
        and isinstance(rule.required_presets, tuple)
        and all(isinstance(label, str) and bool(label.strip()) for label in rule.required_presets)
        and len({_normalized_text(label) for label in rule.required_presets})
        == len(rule.required_presets)
        and _valid_artifact_keys(rule.required_artifacts)
    )


def _valid_interaction(interaction: object) -> bool:
    return (
        isinstance(interaction, InteractionEvidence)
        and type(interaction.valid) is bool
        and interaction.valid
        and _valid_count(interaction.learner_control_count)
        and isinstance(interaction.observations, tuple)
        and all(
            isinstance(item, ObservationEvidence)
            and type(item.has_prediction) is bool
            and type(item.has_note) is bool
            and type(item.has_outcome) is bool
            for item in interaction.observations
        )
        and isinstance(interaction.preset_labels, tuple)
        and all(isinstance(label, str) and bool(label.strip()) for label in interaction.preset_labels)
    )


def _valid_count(value: object) -> bool:
    return type(value) is int and value >= 0


def _valid_artifact_keys(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and all(isinstance(key, str) and key == key.strip() and bool(key) for key in value)
        and len(set(value)) == len(value)
    )


def _is_learner_control_event(kind: str, name: str) -> bool:
    if kind == "preset":
        return bool(name)
    if kind == "slider":
        return bool(name) and name not in NON_LEARNER_CONTROL_SLIDER_NAMES
    if kind != "button":
        return False
    return bool(name) and name not in NON_LEARNER_CONTROL_BUTTON_NAMES


def _next_required_preset(
    required_labels: Sequence[str],
    attempted_labels: Sequence[str],
) -> str:
    index = 0
    for attempted in attempted_labels:
        if index >= len(required_labels):
            break
        if _normalized_text(attempted) == _normalized_text(required_labels[index]):
            index += 1
    return required_labels[index] if index < len(required_labels) else ""


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalized_text(value: object) -> str:
    return _clean_text(value).casefold()
