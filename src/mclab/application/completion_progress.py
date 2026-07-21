"""Pure course-progress assessment over canonical completion evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from mclab.completion import (
    CompletionDecision,
    CompletionEvidence,
    CompletionRecordKind,
    CompletionRule,
    evaluate_completion,
)


class CompletionTarget(Protocol):
    """Minimal catalog target shape consumed by the progress assessor."""

    id: str
    completion: CompletionRule


class CompletionRecord(Protocol):
    """Minimal saved-record shape supplied by the trusted artifact reader."""

    scenario_id: str
    completion_evidence: CompletionEvidence


@dataclass(frozen=True)
class TargetCompletionAssessment:
    """Historical credit and newest-attempt diagnostics for one target."""

    target_id: str
    complete: bool
    latest_record: object | None
    latest_decision: CompletionDecision
    credited_record: object | None
    credited_decision: CompletionDecision | None


@dataclass(frozen=True)
class CompletionAssessmentIndex:
    """Immutable ordered assessments shared by learner-facing surfaces."""

    assessments: tuple[TargetCompletionAssessment, ...]

    def get(self, target_id: str) -> TargetCompletionAssessment:
        for assessment in self.assessments:
            if assessment.target_id == target_id:
                return assessment
        raise KeyError(f"Unknown completion target ID: {target_id}")

    @property
    def completed_target_ids(self) -> frozenset[str]:
        return frozenset(item.target_id for item in self.assessments if item.complete)


def assess_target_completion(
    target: CompletionTarget,
    records_newest_first: Iterable[CompletionRecord],
) -> TargetCompletionAssessment:
    """Assess each matching run independently without merging evidence.

    The input order is part of this dependency-light boundary: callers provide
    newest-first records.  The newest matching record remains diagnostic even
    when an older independently complete record supplies durable course credit.
    """

    latest_record: object | None = None
    latest_decision = evaluate_completion(
        target.completion,
        CompletionEvidence(CompletionRecordKind.MISSING),
    )
    credited_record: object | None = None
    credited_decision: CompletionDecision | None = None

    for record in records_newest_first:
        if record.scenario_id != target.id:
            continue
        decision = evaluate_completion(target.completion, record.completion_evidence)
        if latest_record is None:
            latest_record = record
            latest_decision = decision
        if credited_record is None and decision.complete:
            credited_record = record
            credited_decision = decision

    return TargetCompletionAssessment(
        target_id=target.id,
        complete=credited_record is not None,
        latest_record=latest_record,
        latest_decision=latest_decision,
        credited_record=credited_record,
        credited_decision=credited_decision,
    )


def build_completion_assessment_index(
    targets: Iterable[CompletionTarget],
    records_newest_first: Iterable[CompletionRecord],
) -> CompletionAssessmentIndex:
    """Build an ordered index while consuming a record iterable only once."""

    records = tuple(records_newest_first)
    return CompletionAssessmentIndex(
        tuple(assess_target_completion(target, records) for target in targets)
    )
