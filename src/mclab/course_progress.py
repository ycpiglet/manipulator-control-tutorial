"""Shared course progress helpers for learner-facing summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CourseMilestone:
    label: str
    step_count: int


COURSE_MILESTONES: tuple[CourseMilestone, ...] = (
    CourseMilestone("1D Dynamics", 2),
    CourseMilestone("PID Control", 2),
    CourseMilestone("2DOF Control", 3),
    CourseMilestone("Panda Manipulation", 3),
    CourseMilestone("Course Compare", 1),
)


def course_milestone_summary(completed_steps: Sequence[bool]) -> str:
    """Summarize learning-path completion by conceptual course milestone."""
    parts: list[str] = []
    next_label = ""
    cursor = 0
    for milestone in COURSE_MILESTONES:
        done = sum(
            1
            for index in range(cursor, cursor + milestone.step_count)
            if index < len(completed_steps) and completed_steps[index]
        )
        parts.append(f"{milestone.label} {done}/{milestone.step_count}")
        if not next_label and done < milestone.step_count:
            next_label = milestone.label
        cursor += milestone.step_count
    if len(completed_steps) > cursor:
        extra_done = sum(1 for item in completed_steps[cursor:] if item)
        extra_total = len(completed_steps) - cursor
        parts.append(f"Extra {extra_done}/{extra_total}")
        if not next_label and extra_done < extra_total:
            next_label = "Extra"
    suffix = f" Next milestone: {next_label}." if next_label else " All milestones ready for review."
    return f"Milestones: {'; '.join(parts)}.{suffix}"
