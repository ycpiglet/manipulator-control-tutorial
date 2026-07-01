"""Shared learner experience coverage summaries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ExperienceCoverageItem:
    key: str
    label: str
    tags: tuple[str, ...]
    next_step: str
    requires_control: bool = False


@dataclass(frozen=True)
class ExperienceCoverageRecord:
    tags: frozenset[str]
    has_control: bool = False


EXPERIENCE_COVERAGE_ITEMS: tuple[ExperienceCoverageItem, ...] = (
    ExperienceCoverageItem(
        "intro",
        "Intro basics",
        ("intro",),
        "Run Lab01 Mass-Spring-Damper - Auto demo.",
    ),
    ExperienceCoverageItem(
        "hands-on",
        "Hands-on controls",
        ("hands-on",),
        "Run an interactive viewer and use one button, slider, or preset.",
        requires_control=True,
    ),
    ExperienceCoverageItem(
        "compare",
        "Comparison batch",
        ("batch",),
        "Run any Comparison Batches card, then open the worksheet Prediction Check.",
    ),
    ExperienceCoverageItem(
        "2dof",
        "2DOF/Jacobian",
        ("2dof",),
        "Run Lab03 2DOF task-space or condition-aware DLS.",
    ),
    ExperienceCoverageItem(
        "singularity",
        "Singularity/DLS",
        ("singularity", "dls"),
        "Run Lab03 2DOF condition-aware DLS.",
    ),
    ExperienceCoverageItem(
        "panda",
        "Panda manipulator",
        ("panda",),
        "Run Lab04 Cartesian reach or Virtual wall.",
    ),
    ExperienceCoverageItem(
        "wall",
        "Virtual wall",
        ("wall",),
        "Run Lab04 Virtual wall and try Close wall -> Back away -> Re-enter wall.",
    ),
)


def experience_coverage_summary_text(records: Iterable[ExperienceCoverageRecord]) -> str:
    covered = experience_coverage_keys(records)
    done_items = [item for item in EXPERIENCE_COVERAGE_ITEMS if item.key in covered]
    missing_items = [item for item in EXPERIENCE_COVERAGE_ITEMS if item.key not in covered]
    done_labels = ", ".join(item.label for item in done_items) if done_items else "none yet"
    missing_labels = ", ".join(item.label for item in missing_items[:4]) if missing_items else "none"
    next_text = (
        missing_items[0].next_step
        if missing_items
        else "All core experience types have saved evidence; replay or compare one topic more deeply."
    )
    return (
        f"Experience coverage: {len(done_items)}/{len(EXPERIENCE_COVERAGE_ITEMS)} types tried. "
        f"Done: {done_labels}. Missing: {missing_labels}. Next: {next_text}"
    )


def experience_coverage_keys(records: Iterable[ExperienceCoverageRecord]) -> set[str]:
    covered: set[str] = set()
    for record in records:
        for item in EXPERIENCE_COVERAGE_ITEMS:
            if item.key in covered:
                continue
            if not any(tag in record.tags for tag in item.tags):
                continue
            if item.requires_control and not record.has_control:
                continue
            covered.add(item.key)
    return covered
