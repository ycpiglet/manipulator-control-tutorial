"""Strict saved-record snapshot for batch completion UI notifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.application.repositories import ArtifactRecord, ArtifactRepository


def course_records_or_strict(
    records: tuple[ArtifactRecord, ...] | None,
) -> tuple[ArtifactRecord, ...]:
    """Use an off-thread strict snapshot, or retain the normal strict fallback."""

    return records if records is not None else ArtifactRepository().list_runs()


def result_records_or_strict(
    records: tuple[ArtifactRecord, ...] | None,
) -> tuple[ArtifactRecord, ...]:
    """Use an off-thread snapshot, or retain replay validation as fallback."""

    return (
        records
        if records is not None
        else ArtifactRepository().list_runs(validate_replays=True)
    )


def strict_course_records(output: str) -> tuple[ArtifactRecord, ...] | None:
    """Read the replay-validated inventory off-thread for the exact runtime root."""

    root = Path(output).parent
    repository = ArtifactRepository()
    if root != repository.outputs_root:
        return None
    try:
        return repository.list_runs(validate_replays=True)
    except Exception:
        return None


def emit_with_course_records(owner: Any, records: tuple[ArtifactRecord, ...] | None) -> None:
    """Expose a strict snapshot only during synchronous Qt notification delivery."""

    owner._course_records_snapshot = records
    try:
        owner.results_changed.emit()
    finally:
        owner._course_records_snapshot = None
