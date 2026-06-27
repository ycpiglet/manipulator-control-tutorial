"""Batch comparison runs for learner-facing experiments."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mclab.config import PROJECT_ROOT, load_config, resolve_project_path
from mclab.labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda
from mclab.sim.reporting import write_outputs_index

LabRunner = Callable[..., Path]

LAB_RUNNERS: dict[str, LabRunner] = {
    "lab01": lab01_msd.run,
    "lab02": lab02_pid.run,
    "lab03": lab03_2dof.run,
    "lab04": lab04_panda.run,
}


@dataclass(frozen=True)
class BatchScenario:
    label: str
    lab_name: str
    config_path: str
    plots: str = "essential"


BATCH_SETS: dict[str, tuple[BatchScenario, ...]] = {
    "lab01_msd_compare": (
        BatchScenario("baseline", "lab01", "configs/lab01_msd/default.yaml"),
        BatchScenario("underdamped", "lab01", "configs/lab01_msd/underdamped.yaml"),
        BatchScenario("overdamped", "lab01", "configs/lab01_msd/over_damped.yaml"),
        BatchScenario("high_stiffness", "lab01", "configs/lab01_msd/high_stiffness.yaml"),
        BatchScenario("low_stiffness", "lab01", "configs/lab01_msd/low_stiffness.yaml"),
    ),
    "lab02_pid_compare": (
        BatchScenario("baseline", "lab02", "configs/lab02_pid/default.yaml"),
        BatchScenario("low_p_gain", "lab02", "configs/lab02_pid/p_low_gain.yaml"),
        BatchScenario("high_p_gain", "lab02", "configs/lab02_pid/p_high_gain.yaml"),
        BatchScenario("pd_damping", "lab02", "configs/lab02_pid/pd_damped.yaml"),
        BatchScenario("saturation", "lab02", "configs/lab02_pid/saturation_limit.yaml"),
        BatchScenario("windup", "lab02", "configs/lab02_pid/pid_with_windup.yaml"),
        BatchScenario("anti_windup", "lab02", "configs/lab02_pid/pid_anti_windup.yaml"),
        BatchScenario("sensor_noise", "lab02", "configs/lab02_pid/measurement_noise.yaml", "pid"),
        BatchScenario("control_delay", "lab02", "configs/lab02_pid/control_delay.yaml"),
    ),
}


def list_batch_sets() -> tuple[str, ...]:
    return tuple(sorted(BATCH_SETS))


def run_batch(
    batch_name: str,
    *,
    output_dir: str | Path | None = None,
    plot: bool = True,
    seed: int | None = None,
) -> Path:
    scenarios = BATCH_SETS.get(batch_name)
    if scenarios is None:
        raise ValueError(f"Unknown batch set: {batch_name}")

    batch_output = create_batch_output_path(batch_name, output_dir)
    completed: list[dict[str, Any]] = []
    for scenario in scenarios:
        config = load_config(scenario.config_path)
        runner = LAB_RUNNERS[scenario.lab_name]
        scenario_output = batch_output / _safe_name(scenario.label)
        result_path = runner(
            config,
            config_path=Path(scenario.config_path),
            output_dir=scenario_output,
            plot=plot,
            viewer=False,
            headless=True,
            realtime=False,
            pause_at_end=False,
            show_viewer_ui=False,
            plot_selection=scenario.plots,
            seed=seed,
        )
        completed.append({**asdict(scenario), "output_path": str(result_path)})

    (batch_output / "batch_summary.json").write_text(
        json.dumps({"batch_name": batch_name, "scenarios": completed}, indent=2),
        encoding="utf-8",
    )
    (batch_output / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch",
                "config_name": batch_name,
                "samples": len(completed),
                "duration": "",
                "batch_name": batch_name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_outputs_index(batch_output)
    write_outputs_index(batch_output.parent)
    return batch_output


def create_batch_output_path(batch_name: str, output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        path = resolve_project_path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = PROJECT_ROOT / "outputs" / f"{stamp}_{batch_name}"
    return _create_unique_directory(base_path)


def _create_unique_directory(base_path: Path) -> Path:
    for index in range(1000):
        path = base_path if index == 0 else base_path.with_name(f"{base_path.name}_{index:03d}")
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not create a unique output directory for {base_path}")


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized.strip("._") or "scenario"
