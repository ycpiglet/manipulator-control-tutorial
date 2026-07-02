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
    command: str = ""


@dataclass(frozen=True)
class ExperienceCoverageRecord:
    tags: frozenset[str]
    has_control: bool = False


@dataclass(frozen=True)
class ExperienceCoverageStatus:
    item: ExperienceCoverageItem
    covered: bool
    next_missing: bool = False


EXPERIENCE_COVERAGE_ITEMS: tuple[ExperienceCoverageItem, ...] = (
    ExperienceCoverageItem(
        "intro",
        "Intro basics",
        ("intro",),
        "Run Lab01 Mass-Spring-Damper - Auto demo.",
        command=(
            "python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report"
        ),
    ),
    ExperienceCoverageItem(
        "hands-on",
        "Hands-on controls",
        ("hands-on",),
        "Run an interactive viewer and use one button, slider, or preset.",
        requires_control=True,
        command=(
            "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
            "--viewer --realtime --pause-at-end --plot --plots essential --open-report"
        ),
    ),
    ExperienceCoverageItem(
        "compare",
        "Comparison batch",
        ("batch",),
        "Run any Comparison Batches card, then open the worksheet Prediction Check.",
        command="python -m mclab batch lab01_msd_compare --open-report",
    ),
    ExperienceCoverageItem(
        "2dof",
        "2DOF/Jacobian",
        ("2dof",),
        "Run Lab03 2DOF task-space or condition-aware DLS.",
        command=(
            "python -m mclab run lab03 --config configs/lab03_2dof/task_space_2dof.yaml "
            "--headless --plot --plots task --open-report"
        ),
    ),
    ExperienceCoverageItem(
        "singularity",
        "Singularity/DLS",
        ("singularity", "dls"),
        "Run Lab03 2DOF condition-aware DLS.",
        command=(
            "python -m mclab run lab03 --config configs/lab03_2dof/condition_aware_dls_2dof.yaml "
            "--viewer --realtime --pause-at-end --plot --plots dls_disturbance --open-report"
        ),
    ),
    ExperienceCoverageItem(
        "panda",
        "Panda manipulator",
        ("panda",),
        "Run Lab04 Cartesian reach or Virtual wall.",
        command=(
            "python -m mclab run lab04 --config configs/lab04_panda/cartesian_reach.yaml "
            "--headless --plot --plots cartesian_reach --open-report"
        ),
    ),
    ExperienceCoverageItem(
        "wall",
        "Virtual wall",
        ("wall",),
        "Run Lab04 Virtual wall and try Close wall -> Back away -> Re-enter wall.",
        command=(
            "python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report"
        ),
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
        else "All core experience types have saved evidence; continue the learning path or replay one topic more deeply."
    )
    return (
        f"Experience coverage: {len(done_items)}/{len(EXPERIENCE_COVERAGE_ITEMS)} types tried. "
        f"Done: {done_labels}. Missing: {missing_labels}. Next: {next_text}"
    )


def next_experience_coverage_item(records: Iterable[ExperienceCoverageRecord]) -> ExperienceCoverageItem | None:
    covered = experience_coverage_keys(records)
    for item in EXPERIENCE_COVERAGE_ITEMS:
        if item.key not in covered:
            return item
    return None


def experience_coverage_statuses(records: Iterable[ExperienceCoverageRecord]) -> tuple[ExperienceCoverageStatus, ...]:
    record_list = tuple(records)
    covered = experience_coverage_keys(record_list)
    next_item = next_experience_coverage_item(record_list)
    return tuple(
        ExperienceCoverageStatus(
            item,
            covered=item.key in covered,
            next_missing=next_item is not None and item.key == next_item.key,
        )
        for item in EXPERIENCE_COVERAGE_ITEMS
    )


def experience_coverage_item_mode(item: ExperienceCoverageItem) -> str:
    command = str(item.command or "")
    if " batch " in f" {command} ":
        return "comparison batch"
    if "--viewer" in command:
        return "hands-on viewer"
    return "headless plot run"


def experience_coverage_item_evidence(item: ExperienceCoverageItem) -> str:
    return {
        "intro": "A saved run report, priority plot, and worksheet for the baseline 1D plant.",
        "hands-on": "At least one learner-control event plus one prediction-backed observation marker.",
        "compare": "A batch comparison report and worksheet with a Prediction Check table.",
        "2dof": "A Lab03 2DOF/Jacobian run report, priority plot, and worksheet.",
        "singularity": "A DLS/singularity run with damping, condition, speed, or task-error evidence.",
        "panda": "A Panda manipulator run report and Cartesian or joint-control evidence plot.",
        "wall": "A virtual-wall run with target crossing, contact/release, force, or wall-gap evidence.",
    }.get(item.key, "A saved report, plot, and worksheet for this experience type.")


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
