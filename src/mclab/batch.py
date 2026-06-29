"""Batch comparison runs for learner-facing experiments."""

from __future__ import annotations

import json
import re
import csv
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from mclab.config import PROJECT_ROOT, load_config, resolve_project_path
from mclab.labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda
from mclab.learning_guides import guide_for_config, prediction_prompt_for_guide, question_for_guide
from mclab.sim.reporting import INDEX_METRIC_KEYS, INDEX_PLOT_PRIORITY, write_outputs_index

LabRunner = Callable[..., Path]

ALL_BATCH_NAME = "all"

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


@dataclass(frozen=True)
class BatchGuide:
    title: str
    focus: str
    questions: tuple[str, ...]
    followups: tuple[str, ...]
    metric_keys: tuple[str, ...]
    preview_plots: tuple[str, ...]
    comparison_specs: tuple[tuple[str, str, str, str], ...]


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
    "lab03_2dof_compare": (
        BatchScenario("joint_space", "lab03", "configs/lab03_2dof/joint_space_2dof.yaml", "essential"),
        BatchScenario("task_space", "lab03", "configs/lab03_2dof/task_space_2dof.yaml", "task"),
        BatchScenario("singularity", "lab03", "configs/lab03_2dof/singularity_2dof.yaml", "singularity"),
        BatchScenario("dls_singularity", "lab03", "configs/lab03_2dof/dls_singularity_2dof.yaml", "dls"),
        BatchScenario("condition_aware_dls", "lab03", "configs/lab03_2dof/condition_aware_dls_2dof.yaml", "dls"),
        BatchScenario(
            "condition_aware_early",
            "lab03",
            "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml",
            "dls",
        ),
        BatchScenario(
            "condition_aware_late",
            "lab03",
            "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml",
            "dls",
        ),
        BatchScenario(
            "condition_aware_low_torque",
            "lab03",
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "dls",
        ),
        BatchScenario(
            "condition_aware_high_torque",
            "lab03",
            "configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml",
            "dls",
        ),
    ),
    "lab04_wall_compare": (
        BatchScenario("soft_wall", "lab04", "configs/lab04_panda/wall_soft.yaml", "wall_compare"),
        BatchScenario("stiff_wall", "lab04", "configs/lab04_panda/wall_stiff.yaml", "wall_compare"),
        BatchScenario("low_damping_wall", "lab04", "configs/lab04_panda/wall_low_damping.yaml", "wall_compare"),
        BatchScenario("high_damping_wall", "lab04", "configs/lab04_panda/wall_high_damping.yaml", "wall_compare"),
        BatchScenario("near_wall", "lab04", "configs/lab04_panda/wall_near.yaml", "wall_compare"),
        BatchScenario("far_wall", "lab04", "configs/lab04_panda/wall_far.yaml", "wall_compare"),
    ),
    "lab04_cartesian_compare": (
        BatchScenario("baseline_reach", "lab04", "configs/lab04_panda/cartesian_reach.yaml", "cartesian_reach"),
        BatchScenario("soft_reach", "lab04", "configs/lab04_panda/cartesian_soft.yaml", "cartesian_reach"),
        BatchScenario("stiff_reach", "lab04", "configs/lab04_panda/cartesian_stiff.yaml", "cartesian_reach"),
    ),
}

BATCH_GUIDES: dict[str, BatchGuide] = {
    "lab01_msd_compare": BatchGuide(
        title="Lab01 Mass-Spring-Damper Comparison",
        focus="Compare how damping and stiffness change free response, force, and remaining energy.",
        questions=(
            "Which case oscillates the most before settling?",
            "Which case returns slowly even though it barely overshoots?",
            "How does stiffness change the motion frequency and peak restoring force?",
        ),
        followups=(
            "Copy `configs/lab01_msd/underdamped.yaml` and double `damping` to see when oscillation disappears.",
            "Copy `configs/lab01_msd/high_stiffness.yaml` and reduce `mass` to watch frequency change.",
            "Add a larger `force_input.magnitude` and compare peak position against the baseline.",
        ),
        metric_keys=(
            "max_abs_position",
            "final_position",
            "final_velocity",
            "final_total_energy",
        ),
        preview_plots=("position.png", "force.png"),
        comparison_specs=(
            ("position_compare.png", "Position Comparison", "position [m]", "position"),
            ("force_compare.png", "Applied Force Comparison", "force [N]", "control_force"),
        ),
    ),
    "lab02_pid_compare": BatchGuide(
        title="Lab02 PID Control Comparison",
        focus="Compare speed, overshoot, control effort, windup, sensor noise, and delay sensitivity.",
        questions=(
            "Which controller reaches the target fastest, and what did it cost in overshoot or force?",
            "How do windup and anti-windup differ after saturation?",
            "How do measurement noise and control delay show up in the plots and metrics?",
        ),
        followups=(
            "Copy `configs/lab02_pid/p_high_gain.yaml` and raise `controller.kd` until overshoot drops.",
            "Copy `configs/lab02_pid/measurement_noise.yaml` and compare `controller.kd` values under noise.",
            "Copy `configs/lab02_pid/control_delay.yaml` and reduce `controller.kp` to recover stability.",
        ),
        metric_keys=(
            "overshoot_percent",
            "settling_time",
            "steady_state_error",
            "max_control_effort",
            "measurement_noise_std",
            "control_delay",
            "max_abs_measurement_error",
        ),
        preview_plots=("position.png", "control_force.png", "error.png"),
        comparison_specs=(
            ("position_compare.png", "Position Tracking Comparison", "position [m]", "position"),
            ("error_compare.png", "Tracking Error Comparison", "error [m]", "position_error"),
            ("control_force_compare.png", "Control Force Comparison", "force [N]", "control_force"),
        ),
    ),
    "lab03_2dof_compare": BatchGuide(
        title="Lab03 2DOF Manipulator Comparison",
        focus=(
            "Compare joint-space tracking, task-space hand control, near-singular motion, "
            "and damped least-squares singularity handling on the same 2DOF arm."
        ),
        questions=(
            "Which controller keeps joint error small, and which keeps hand error small?",
            "What happens to manipulability and Jacobian condition near the singular posture?",
            "How does DLS damping limit joint speed near a poorly conditioned target?",
            "When does condition-aware damping start increasing, and what does it trade for lower joint speed?",
            "How do early and late damping schedules change task error near the same workspace edge?",
            "How much does a lower torque limit increase task error when the damping schedule is unchanged?",
            "How do the torque plots change when the task is expressed in end-effector space?",
        ),
        followups=(
            "Copy `configs/lab03_2dof/task_space_2dof.yaml` and move `target_xy` closer to the workspace edge.",
            "Copy `configs/lab03_2dof/singularity_2dof.yaml` and change `target_q` to approach a straighter arm.",
            "Copy `configs/lab03_2dof/dls_singularity_2dof.yaml` and vary `tracking_controller.dls_damping`.",
            "Compare `condition_aware_dls_early_2dof.yaml` and `condition_aware_dls_late_2dof.yaml`.",
            "Compare `condition_aware_dls_low_torque_2dof.yaml` and `condition_aware_dls_high_torque_2dof.yaml`.",
            "Copy `configs/lab03_2dof/condition_aware_dls_2dof.yaml` and change `condition_damping_threshold`.",
            "Lower `tracking_controller.torque_limit` and compare how joint and task errors grow.",
        ),
        metric_keys=(
            "max_joint_error_norm",
            "final_joint_error_norm",
            "max_task_error_norm",
            "final_task_error_norm",
            "min_manipulability",
            "max_jacobian_condition",
            "max_abs_tau_cmd",
            "max_dls_joint_speed",
            "max_dls_damping",
            "max_dls_condition_scale",
        ),
        preview_plots=("dls.png", "end_effector.png", "singularity.png", "error.png"),
        comparison_specs=(
            ("joint_error_compare.png", "Joint Error Norm Comparison", "error norm", "joint_error_norm"),
            ("task_error_compare.png", "Task Error Norm Comparison", "error norm", "task_error_norm"),
            ("hand_x_compare.png", "End-Effector X Comparison", "x [m]", "x_ee_0"),
            ("manipulability_compare.png", "Manipulability Comparison", "manipulability", "manipulability"),
            ("dls_joint_speed_compare.png", "DLS Joint Speed Comparison", "joint speed", "dls_joint_speed"),
            ("dls_damping_compare.png", "DLS Damping Schedule Comparison", "damping / scale", "dls_damping"),
            ("shoulder_torque_compare.png", "Shoulder Torque Comparison", "torque [N m]", "tau_cmd_0"),
        ),
    ),
    "lab04_wall_compare": BatchGuide(
        title="Lab04 Panda Virtual Wall Comparison",
        focus="Compare wall stiffness, damping, and wall position on the Panda end-effector response.",
        questions=(
            "Which wall allows more penetration before retreating?",
            "How much more virtual wall force does the stiff wall produce?",
            "How does the hand X position change as retreat and damping increase?",
            "With stiffness fixed, how does damping change penetration, force, and retreat?",
            "With stiffness and damping fixed, how does wall position change contact timing and penetration?",
        ),
        followups=(
            "Copy `configs/lab04_panda/wall_soft.yaml` and raise `virtual_wall.stiffness` gradually.",
            "Copy `configs/lab04_panda/wall_stiff.yaml` and lower `virtual_wall.damping` to inspect force spikes.",
            "Compare `wall_low_damping.yaml` and `wall_high_damping.yaml` to isolate damping.",
            "Compare `wall_near.yaml` and `wall_far.yaml` to isolate wall position.",
        ),
        metric_keys=(
            "max_wall_penetration_cm",
            "max_wall_retreat_cm",
            "first_wall_contact_time",
            "wall_contact_duration",
            "wall_contact_fraction",
            "max_abs_virtual_wall_force",
            "max_abs_virtual_wall_spring_force",
            "max_abs_virtual_wall_damping_force",
            "max_joint_error_norm",
            "max_abs_tau_cmd",
            "final_x_ee_0",
        ),
        preview_plots=("virtual_wall.png", "end_effector.png", "error.png"),
        comparison_specs=(
            ("hand_x_compare.png", "Panda Hand X Comparison", "x [m]", "x_ee_0"),
            ("wall_penetration_compare.png", "Wall Penetration Comparison", "penetration [cm]", "wall_penetration_cm"),
            ("wall_force_compare.png", "Virtual Wall Force Comparison", "force", "force_virtual_0"),
            ("wall_spring_force_compare.png", "Virtual Wall Spring Force Comparison", "force", "force_virtual_spring_0"),
            ("wall_damping_force_compare.png", "Virtual Wall Damping Force Comparison", "force", "force_virtual_damping_0"),
            ("wall_retreat_compare.png", "Wall Retreat Comparison", "retreat [cm]", "wall_retreat_cm"),
        ),
    ),
    "lab04_cartesian_compare": BatchGuide(
        title="Lab04 Panda Cartesian Reach Comparison",
        focus=(
            "Compare baseline, soft, and stiff Cartesian reach settings before adding the virtual wall."
        ),
        questions=(
            "Which reach setting reduces final hand error most quickly?",
            "How do actuator force traces change when the reach command is more aggressive?",
            "Does a softer reach leave more Cartesian error even though the motion is calmer?",
        ),
        followups=(
            "Copy `configs/lab04_panda/cartesian_soft.yaml` and raise `cartesian_target.gain` gradually.",
            "Copy `configs/lab04_panda/cartesian_stiff.yaml` and lower `cartesian_target.max_step` to calm the response.",
            "Move `cartesian_target.position` a few centimeters and compare final Cartesian error.",
        ),
        metric_keys=(
            "max_cartesian_error_cm",
            "final_cartesian_error_cm",
            "max_joint_error_norm",
            "max_abs_tau_cmd",
            "final_x_ee_0",
            "final_x_ee_1",
            "final_x_ee_2",
        ),
        preview_plots=("cartesian_error.png", "end_effector.png", "torque.png"),
        comparison_specs=(
            ("cartesian_error_compare.png", "Cartesian Error Comparison", "error [cm]", "cartesian_error_cm"),
            ("hand_x_compare.png", "Panda Hand X Comparison", "x [m]", "x_ee_0"),
            ("hand_y_compare.png", "Panda Hand Y Comparison", "y [m]", "x_ee_1"),
            ("shoulder_actuator_compare.png", "Shoulder Actuator Force Comparison", "force / torque proxy", "tau_cmd_0"),
        ),
    ),
}


def list_batch_sets(*, include_all: bool = False) -> tuple[str, ...]:
    names = sorted(BATCH_SETS)
    if include_all:
        names.append(ALL_BATCH_NAME)
    return tuple(names)


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
    if plot:
        write_comparison_plots(batch_output, batch_name, scenarios)
    write_batch_report(batch_output, batch_name, scenarios)
    write_outputs_index(batch_output.parent)
    return batch_output


def run_all_batches(
    *,
    output_dir: str | Path | None = None,
    plot: bool = True,
    seed: int | None = None,
) -> Path:
    group_output = create_batch_output_path("all_batches", output_dir)
    completed: list[dict[str, Any]] = []
    for batch_name in list_batch_sets():
        batch_output = run_batch(
            batch_name,
            output_dir=group_output / batch_name,
            plot=plot,
            seed=seed,
        )
        guide = BATCH_GUIDES.get(batch_name)
        scenario_count = len(BATCH_SETS[batch_name])
        completed.append(
            {
                "batch_name": batch_name,
                "title": guide.title if guide else batch_name.replace("_", " ").title(),
                "output_path": str(batch_output),
                "report": f"{batch_name}/report.html"
                if (batch_output / "report.html").exists()
                else f"{batch_name}/index.html",
                "scenario_count": scenario_count,
            }
        )

    scenario_runs = sum(int(item["scenario_count"]) for item in completed)
    (group_output / "batch_summary.json").write_text(
        json.dumps(
            {
                "batch_name": ALL_BATCH_NAME,
                "batches": completed,
                "scenario_runs": scenario_runs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (group_output / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch_group",
                "config_name": ALL_BATCH_NAME,
                "samples": scenario_runs,
                "duration": "",
                "batch_name": ALL_BATCH_NAME,
                "child_batches": len(completed),
                "scenario_runs": scenario_runs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_outputs_index(group_output)
    write_all_batches_report(group_output, completed)
    write_outputs_index(group_output.parent)
    return group_output


def create_batch_output_path(batch_name: str, output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        path = resolve_project_path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = PROJECT_ROOT / "outputs" / f"{stamp}_{batch_name}"
    return _create_unique_directory(base_path)


def write_batch_report(
    batch_output: str | Path,
    batch_name: str,
    scenarios: tuple[BatchScenario, ...],
) -> Path:
    output = Path(batch_output)
    guide = BATCH_GUIDES.get(
        batch_name,
        BatchGuide(
            title=batch_name.replace("_", " ").title(),
            focus="Compare the scenario reports and summary metrics.",
            questions=("Open each run report and compare the response plots.",),
            followups=("Copy one scenario config, change a single parameter, and rerun the batch.",),
            metric_keys=INDEX_METRIC_KEYS,
            preview_plots=("position.png",),
            comparison_specs=(),
        ),
    )
    rows = _batch_rows(output, scenarios)
    report = output / "report.html"
    report.write_text(_render_batch_report(output, batch_name, guide, rows), encoding="utf-8")
    return report


def write_all_batches_report(batch_output: str | Path, completed_batches: list[dict[str, Any]]) -> Path:
    output = Path(batch_output)
    report = output / "report.html"
    report.write_text(_render_all_batches_report(completed_batches), encoding="utf-8")
    return report


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


def _batch_rows(output: Path, scenarios: tuple[BatchScenario, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        run_dir = output / _safe_name(scenario.label)
        summary = _read_json(run_dir / "summary.json")
        rows.append(
            {
                "label": scenario.label,
                "lab_name": scenario.lab_name,
                "config_path": scenario.config_path,
                "plot_selection": scenario.plots,
                "config": _load_config_for_report(run_dir, scenario.config_path),
                "run_dir": run_dir.name,
                "report": f"{run_dir.name}/report.html" if (run_dir / "report.html").exists() else run_dir.name,
                "summary": summary,
                "plots": _available_plot_paths(run_dir),
            }
        )
    return rows


def _render_batch_report(output: Path, batch_name: str, guide: BatchGuide, rows: list[dict[str, Any]]) -> str:
    metric_keys = _display_metric_keys(guide, rows)
    question_items = "\n".join(f"<li>{escape(question)}</li>" for question in guide.questions)
    next_experiments = _next_experiments(guide)
    reproduce_commands = _reproduce_commands(batch_name, rows)
    baseline_config = rows[0].get("config", {}) if rows else {}
    baseline_summary = rows[0].get("summary", {}) if rows else {}
    scenario_cards = "\n".join(
        _scenario_card(
            row,
            metric_keys,
            baseline_config=baseline_config,
            baseline_summary=baseline_summary,
        )
        for row in rows
    )
    comparison_takeaways = _comparison_takeaways(rows, metric_keys)
    metric_highlights = _metric_highlights(rows, metric_keys)
    baseline_changes = _baseline_metric_changes(rows, metric_keys)
    parameter_differences = _parameter_differences(rows)
    comparison_plots = _comparison_plots(output)
    plot_previews = _plot_previews(rows, guide.preview_plots)
    metric_headers = "".join(f"<th>{escape(_label(key))}</th>" for key in metric_keys)
    metric_rows = "\n".join(_metric_row(row, metric_keys) for row in rows)
    if not metric_rows:
        metric_rows = f'<tr><td colspan="{3 + len(metric_keys)}">No scenario summaries were found.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(guide.title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #202124;
      background: #f6f7f9;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    h1, h2, p {{
      margin-top: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
      margin-bottom: 8px;
    }}
    h2 {{
      font-size: 20px;
      margin-bottom: 12px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      margin-top: 16px;
      padding: 16px;
    }}
    .scenario-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .scenario {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .scenario h3 {{
      margin: 0 0 8px;
      font-size: 16px;
    }}
    .takeaway-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .takeaway {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfe;
    }}
    .takeaway h3 {{
      margin: 0 0 8px;
      font-size: 15px;
    }}
    .muted {{
      color: #596270;
      font-size: 13px;
    }}
    .metric {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid #edf0f3;
      padding-top: 7px;
      margin-top: 7px;
      font-size: 13px;
    }}
    .cue {{
      border-top: 1px solid #edf0f3;
      padding-top: 7px;
      margin-top: 7px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .cue strong {{
      display: block;
      color: #3f4752;
      margin-bottom: 2px;
    }}
    .quick-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 8px 0;
      font-size: 13px;
    }}
    .quick-links a, .quick-links span {{
      border: 1px solid #d9dde3;
      border-radius: 6px;
      padding: 4px 8px;
      background: #f8fafc;
      text-decoration: none;
    }}
    .change-item {{
      display: block;
      margin-top: 3px;
    }}
    .command {{
      display: block;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 1px solid #d9dde3;
      border-radius: 6px;
      background: #f8fafc;
      color: #202124;
      padding: 8px 10px;
      margin-top: 8px;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
      line-height: 1.4;
    }}
    .preview-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }}
    .comparison-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 12px;
    }}
    .preview, .comparison {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
    }}
    .preview img, .comparison img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .preview figcaption, .comparison figcaption {{
      border-top: 1px solid #e0e4ea;
      padding: 8px 10px;
      color: #596270;
      font-size: 13px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid #edf0f3;
      padding: 9px 10px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: #3f4752;
      font-weight: 600;
    }}
    a {{
      color: #0b57d0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(guide.title)}</h1>
    <section>
      <h2>Learning Focus</h2>
      <p>{escape(guide.focus)}</p>
      <ul>{question_items}</ul>
      <p class="muted"><a href="index.html">Open the detailed run index</a> for every saved artifact.</p>
    </section>
    {next_experiments}
    {reproduce_commands}
    <section>
      <h2>Scenario Cards</h2>
      <div class="scenario-grid">{scenario_cards}</div>
    </section>
    {comparison_takeaways}
    {metric_highlights}
    {baseline_changes}
    {parameter_differences}
    {comparison_plots}
    {plot_previews}
    <section>
      <h2>Metric Table</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Scenario</th><th>Lab</th><th>Config</th>{metric_headers}</tr></thead>
          <tbody>{metric_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _render_all_batches_report(completed_batches: list[dict[str, Any]]) -> str:
    total_scenarios = sum(int(row.get("scenario_count", 0)) for row in completed_batches)
    cards = "\n".join(_all_batch_card(row) for row in completed_batches)
    rows = "\n".join(_all_batch_row(row) for row in completed_batches)
    if not rows:
        rows = '<tr><td colspan="3">No batch runs were found.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>All Comparison Batches</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #202124;
      background: #f6f7f9;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    h1, h2, p {{
      margin-top: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
      margin-bottom: 8px;
    }}
    h2 {{
      font-size: 20px;
      margin-bottom: 12px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      margin-top: 16px;
      padding: 16px;
    }}
    .batch-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .batch-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .batch-card h3 {{
      margin: 0 0 8px;
      font-size: 16px;
    }}
    .muted {{
      color: #596270;
      font-size: 13px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid #edf0f3;
      padding: 9px 10px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: #3f4752;
      font-weight: 600;
    }}
    a {{
      color: #0b57d0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>All Comparison Batches</h1>
    <section>
      <h2>Learning Flow</h2>
      <p>This run creates the complete comparison report set for Lab01 through Lab04.</p>
      <p class="muted">{len(completed_batches)} batch reports, {total_scenarios} scenario runs. Open each batch report to compare plots, metrics, parameter differences, and follow-up experiments.</p>
      <p class="muted"><a href="index.html">Open the detailed output index</a> for every saved artifact.</p>
    </section>
    <section>
      <h2>Batch Reports</h2>
      <div class="batch-grid">{cards}</div>
    </section>
    <section>
      <h2>Summary Table</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Batch</th><th>Scenarios</th><th>Report</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _all_batch_card(row: dict[str, Any]) -> str:
    return (
        '<article class="batch-card">'
        f'<h3><a href="{escape(str(row["report"]))}">{escape(str(row["title"]))}</a></h3>'
        f'<p class="muted">{escape(str(row["batch_name"]))}</p>'
        f'<p>{escape(str(row["scenario_count"]))} scenarios</p>'
        "</article>"
    )


def _all_batch_row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(row['title']))}</td>"
        f"<td>{escape(str(row['scenario_count']))}</td>"
        f'<td><a href="{escape(str(row["report"]))}">{escape(str(row["report"]))}</a></td>'
        "</tr>"
    )


def _scenario_card(
    row: dict[str, Any],
    metric_keys: list[str],
    baseline_config: dict[str, Any] | None = None,
    baseline_summary: dict[str, Any] | None = None,
) -> str:
    summary = row.get("summary", {})
    metrics = "\n".join(
        (
            '<div class="metric">'
            f"<span>{escape(_label(key))}</span>"
            f"<strong>{escape(_format_value(summary.get(key)))}</strong>"
            "</div>"
        )
        for key in metric_keys[:4]
        if _has_value(summary.get(key))
    )
    if not metrics:
        metrics = '<p class="muted">No summary metrics were saved.</p>'
    learning_cues = _scenario_learning_cues(row)
    control_surface = _scenario_control_surface(row)
    command = _scenario_run_command(row)
    quick_links = _scenario_quick_links(row)
    changes = _scenario_change_summary(row, baseline_config)
    metric_changes = _scenario_metric_change_summary(row, metric_keys, baseline_summary)
    return (
        '<article class="scenario">'
        f'<h3><a href="{escape(str(row["report"]))}">{escape(str(row["label"]))}</a></h3>'
        f'<p class="muted">{escape(str(row["config_path"]))}</p>'
        f"{quick_links}"
        f"{changes}"
        f"{metric_changes}"
        f"{learning_cues}"
        f"{control_surface}"
        f'<code class="command">{escape(command)}</code>'
        f"{metrics}"
        "</article>"
    )


def _scenario_change_summary(
    row: dict[str, Any],
    baseline_config: dict[str, Any] | None,
    *,
    max_items: int = 4,
) -> str:
    if baseline_config is None:
        return ""
    baseline = _flatten_config(baseline_config)
    current = _flatten_config(row.get("config", {}))
    if not baseline and not current:
        return ""

    diffs = [
        key
        for key in sorted(set(baseline) | set(current))
        if _normalized_config_value(baseline.get(key)) != _normalized_config_value(current.get(key))
    ]
    if not diffs:
        body = '<span class="muted">Baseline reference</span>'
    else:
        visible = diffs[:max_items]
        body = "".join(
            (
                '<span class="change-item">'
                f"{escape(key)}: {escape(_format_value(baseline.get(key)))} -&gt; "
                f"{escape(_format_value(current.get(key)))}"
                "</span>"
            )
            for key in visible
        )
        hidden_count = len(diffs) - len(visible)
        if hidden_count > 0:
            body += f'<span class="muted change-item">+ {hidden_count} more in Parameter Differences</span>'
    return '<div class="cue"><strong>Changed from baseline</strong>' + body + "</div>"


def _scenario_metric_change_summary(
    row: dict[str, Any],
    metric_keys: list[str],
    baseline_summary: dict[str, Any] | None,
    *,
    max_items: int = 3,
) -> str:
    if baseline_summary is None:
        return ""
    summary = row.get("summary", {})
    numeric_changes: list[tuple[float, str, float, float]] = []
    for key in metric_keys:
        baseline_value = _as_finite_float(baseline_summary.get(key))
        value = _as_finite_float(summary.get(key))
        if baseline_value is None or value is None:
            continue
        delta = value - baseline_value
        if abs(delta) < 1e-12:
            continue
        rank = abs(delta) if abs(baseline_value) < 1e-12 else abs(delta / baseline_value)
        numeric_changes.append((rank, key, baseline_value, value))

    if not numeric_changes:
        body = '<span class="muted">Baseline metric reference</span>'
    else:
        visible = sorted(numeric_changes, key=lambda item: item[0], reverse=True)[:max_items]
        body = "".join(
            (
                '<span class="change-item">'
                f"{escape(_label(key))}: {escape(_signed_value(value - baseline_value))}"
                f" ({escape(_percent_change(value - baseline_value, baseline_value))})"
                "</span>"
            )
            for _rank, key, baseline_value, value in visible
        )
    return '<div class="cue"><strong>Metric change from baseline</strong>' + body + "</div>"


def _scenario_quick_links(row: dict[str, Any]) -> str:
    plot = _priority_plot_link(row.get("plots", {}))
    plot_link = (
        f'<a href="{escape(plot[1])}">Open {escape(plot[0])}</a>'
        if plot is not None
        else '<span class="muted">No plot link saved</span>'
    )
    return (
        '<div class="quick-links">'
        f'<a href="{escape(str(row["report"]))}">Open report</a>'
        f"{plot_link}"
        "</div>"
    )


def _priority_plot_link(plots: Any) -> tuple[str, str] | None:
    if not isinstance(plots, dict) or not plots:
        return None
    plot_names = sorted(str(name) for name in plots if str(name).endswith(".png"))
    if not plot_names:
        return None
    selected = min(plot_names, key=_plot_priority_key)
    return selected, str(plots[selected])


def _plot_priority_key(name: str) -> tuple[int, str]:
    stem = Path(name).stem
    for index, priority in enumerate(INDEX_PLOT_PRIORITY):
        if stem == priority or stem.startswith(f"{priority}_") or stem.endswith(f"_{priority}"):
            return index, name
    return len(INDEX_PLOT_PRIORITY), name


def _reproduce_commands(batch_name: str, rows: list[dict[str, Any]]) -> str:
    batch_command = f"python -m mclab batch {batch_name} --open-report"
    scenario_commands = "\n".join(
        (
            "<tr>"
            f"<td>{escape(str(row['label']))}</td>"
            f'<td><code class="command">{escape(_scenario_run_command(row))}</code></td>'
            "</tr>"
        )
        for row in rows
    )
    if not scenario_commands:
        scenario_commands = '<tr><td colspan="2">No scenario commands are available.</td></tr>'
    return (
        "<section>"
        "<h2>Reproduce Commands</h2>"
        '<p class="muted">Run the whole comparison again, or rerun one scenario before editing its YAML.</p>'
        f'<code class="command">{escape(batch_command)}</code>'
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Scenario</th><th>Headless run command</th></tr></thead>"
        f"<tbody>{scenario_commands}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _scenario_run_command(row: dict[str, Any]) -> str:
    command = (
        f"python -m mclab run {row.get('lab_name', '')} "
        f"--config {row.get('config_path', '')} --headless --plot"
    )
    plot_selection = str(row.get("plot_selection") or "").strip()
    if plot_selection:
        command += f" --plots {plot_selection}"
    return command


def _scenario_learning_cues(row: dict[str, Any]) -> str:
    guide = guide_for_config(config_path=str(row.get("config_path", "")), lab_name=str(row.get("lab_name", "")))
    if guide is None:
        return ""
    cues = [
        ("Predict", prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()),
        ("Question", question_for_guide(guide).removeprefix("Question:").strip()),
        ("Watch", str(getattr(guide, "watch", "") or "").strip()),
    ]
    return "".join(
        (
            '<div class="cue">'
            f"<strong>{escape(label)}</strong>"
            f"{escape(text)}"
            "</div>"
        )
        for label, text in cues
        if text
    )


def _scenario_control_surface(row: dict[str, Any]) -> str:
    summary = _control_surface_summary(row.get("config", {}))
    if not summary:
        return ""
    return (
        '<div class="cue">'
        "<strong>Control surface</strong>"
        f"{escape(summary)}"
        "</div>"
    )


def _control_surface_summary(config: Any) -> str:
    if not isinstance(config, dict):
        return ""
    interaction = config.get("interaction")
    if not isinstance(interaction, dict) or not interaction:
        return "Auto run; edit YAML before rerunning."

    panel_enabled = bool(interaction.get("panel", False))
    controls: list[str] = []
    if panel_enabled:
        controls.append("MCLab Interaction window")
    if bool(interaction.get("key_force", False)):
        controls.append("Pull/Push buttons and A/D keys")
    if bool(interaction.get("target_nudge", False)):
        controls.append("Target -/+ buttons and A/D keys")
    if bool(interaction.get("live_tuning", False)):
        controls.append("live sliders with Changed values")
    preset_labels = _configured_preset_labels(config)
    if preset_labels:
        controls.append(f"quick presets ({', '.join(preset_labels)})")
    if bool(interaction.get("playback_speed", panel_enabled)):
        controls.append("playback speed")
    if bool(interaction.get("pause_resume", interaction.get("pause", panel_enabled))):
        controls.append("Pause/Step")
    if bool(interaction.get("reset_plant", interaction.get("reset_experiment", panel_enabled))):
        controls.append("Reset plant")
    if panel_enabled:
        controls.append("Mark observation")
    if not controls:
        return "Auto run; edit YAML before rerunning."
    return "; ".join(dict.fromkeys(controls)) + "."


def _configured_preset_labels(config: dict[str, Any]) -> list[str]:
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return []
    presets = interaction.get("tuning_presets")
    if not isinstance(presets, list):
        return []
    labels: list[str] = []
    for index, preset in enumerate(presets, start=1):
        if not isinstance(preset, dict):
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return labels


def _next_experiments(guide: BatchGuide) -> str:
    if not guide.followups:
        return ""
    items = "\n".join(f"<li>{escape(item)}</li>" for item in guide.followups)
    return (
        "<section>"
        "<h2>Next Experiments</h2>"
        "<ul>"
        f"{items}"
        "</ul>"
        "</section>"
    )


def _comparison_takeaways(rows: list[dict[str, Any]], metric_keys: list[str]) -> str:
    cards: list[str] = []
    for key in metric_keys:
        values = [
            (str(row["label"]), numeric, _takeaway_rank_value(key, numeric))
            for row in rows
            if (numeric := _as_finite_float(row.get("summary", {}).get(key))) is not None
        ]
        if len(values) < 2:
            continue
        min_label, min_value, min_rank = min(values, key=lambda item: item[2])
        max_label, max_value, max_rank = max(values, key=lambda item: item[2])
        if abs(max_rank - min_rank) < 1e-12:
            continue
        cards.append(_takeaway_card(key, min_label, min_value, max_label, max_value))
        if len(cards) >= 4:
            break
    if not cards:
        return ""
    return (
        "<section>"
        "<h2>Comparison Takeaways</h2>"
        '<p class="muted">Use these as starting hypotheses, then confirm the story in the plots and YAML differences.</p>'
        '<div class="takeaway-grid">'
        + "\n".join(cards)
        + "</div>"
        "</section>"
    )


def _takeaway_card(
    key: str,
    min_label: str,
    min_value: float,
    max_label: str,
    max_value: float,
) -> str:
    direction = _metric_direction(key)
    label = escape(_label(key))
    if direction == "higher":
        body = (
            f"<strong>{escape(max_label)}</strong> has the strongest capability signal "
            f"({_format_value(max_value)}), while <strong>{escape(min_label)}</strong> is lowest "
            f"({_format_value(min_value)})."
        )
    elif direction == "lower":
        body = _lower_metric_takeaway_body(key, min_label, min_value, max_label, max_value)
    else:
        body = (
            f"This metric ranges from <strong>{escape(min_label)}</strong> "
            f"({_format_value(min_value)}) to <strong>{escape(max_label)}</strong> "
            f"({_format_value(max_value)})."
        )
    return (
        '<article class="takeaway">'
        f"<h3>{label}</h3>"
        f"<p>{body}</p>"
        "</article>"
    )


def _lower_metric_takeaway_body(
    key: str,
    min_label: str,
    min_value: float,
    max_label: str,
    max_value: float,
) -> str:
    lowered = key.lower()
    low = f"<strong>{escape(min_label)}</strong>"
    high = f"<strong>{escape(max_label)}</strong>"
    low_value = _format_value(min_value)
    high_value = _format_value(max_value)
    if "settling" in lowered:
        return f"{low} settles fastest ({low_value}), while {high} takes longest ({high_value})."
    if "overshoot" in lowered:
        return f"{low} has the least overshoot ({low_value}), while {high} overshoots most ({high_value})."
    if "error" in lowered:
        return f"{low} has the smallest error magnitude ({low_value}), while {high} has the largest ({high_value})."
    if "condition" in lowered:
        return f"{low} is best-conditioned here ({low_value}), while {high} is closest to a singular response ({high_value})."
    if any(term in lowered for term in ("effort", "force", "tau", "torque", "current", "speed")):
        return f"{low} uses the least demand ({low_value}), while {high} is the most demanding ({high_value})."
    if any(term in lowered for term in ("penetration", "retreat")):
        return f"{low} has the smallest wall response ({low_value}), while {high} has the largest ({high_value})."
    return f"{low} is lowest for this metric ({low_value}), while {high} is highest ({high_value})."


def _metric_direction(key: str) -> str:
    lowered = key.lower()
    if "manipulability" in lowered:
        return "higher"
    lower_is_calmer = (
        "error",
        "overshoot",
        "settling",
        "effort",
        "force",
        "tau",
        "torque",
        "current",
        "penetration",
        "retreat",
        "condition",
        "speed",
        "noise",
        "delay",
    )
    if any(term in lowered for term in lower_is_calmer):
        return "lower"
    return "neutral"


def _takeaway_rank_value(key: str, value: float) -> float:
    if _metric_direction(key) != "lower":
        return value
    magnitude_terms = (
        "error",
        "effort",
        "force",
        "tau",
        "torque",
        "current",
        "penetration",
        "retreat",
        "speed",
    )
    lowered = key.lower()
    if any(term in lowered for term in magnitude_terms):
        return abs(value)
    return value


def _parameter_differences(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    flattened = [
        (str(row["label"]), _flatten_config(row.get("config", {})))
        for row in rows
    ]
    keys = sorted(
        {
            key
            for _label_name, config in flattened
            for key in config
            if _has_different_values(key, flattened)
        }
    )
    if not keys:
        body = f'<tr><td colspan="{1 + len(rows)}">No differing config values were found.</td></tr>'
    else:
        body = "\n".join(
            (
                "<tr>"
                f"<td>{escape(key)}</td>"
                + "".join(
                    f"<td>{escape(_format_value(config.get(key)))}</td>"
                    for _label_name, config in flattened
                )
                + "</tr>"
            )
            for key in keys
        )
    headers = "".join(f"<th>{escape(str(row['label']))}</th>" for row in rows)
    return (
        "<section>"
        "<h2>Parameter Differences</h2>"
        '<p class="muted">Only YAML values that differ across scenarios are shown. n/a means the value is omitted in that YAML file.</p>'
        '<div class="table-wrap">'
        "<table>"
        f"<thead><tr><th>Parameter</th>{headers}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _metric_highlights(rows: list[dict[str, Any]], metric_keys: list[str]) -> str:
    highlight_rows: list[str] = []
    for key in metric_keys:
        values = [
            (str(row["label"]), numeric)
            for row in rows
            if (numeric := _as_finite_float(row.get("summary", {}).get(key))) is not None
        ]
        if len(values) < 2:
            continue
        min_label, min_value = min(values, key=lambda item: item[1])
        max_label, max_value = max(values, key=lambda item: item[1])
        highlight_rows.append(
            "<tr>"
            f"<td>{escape(_label(key))}</td>"
            f"<td>{escape(min_label)}</td>"
            f"<td>{escape(_format_value(min_value))}</td>"
            f"<td>{escape(max_label)}</td>"
            f"<td>{escape(_format_value(max_value))}</td>"
            "</tr>"
        )
    if not highlight_rows:
        return ""
    return (
        "<section>"
        "<h2>Metric Highlights</h2>"
        '<p class="muted">Min/max values are descriptive comparisons, not automatic grades.</p>'
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Metric</th><th>Minimum scenario</th><th>Minimum</th><th>Maximum scenario</th><th>Maximum</th></tr></thead>"
        f"<tbody>{''.join(highlight_rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _baseline_metric_changes(rows: list[dict[str, Any]], metric_keys: list[str]) -> str:
    if len(rows) < 2 or not metric_keys:
        return ""
    baseline = rows[0]
    baseline_summary = baseline.get("summary", {})
    baseline_label = str(baseline.get("label", "baseline"))
    change_rows: list[str] = []
    for row in rows[1:]:
        summary = row.get("summary", {})
        for key in metric_keys:
            baseline_value = _as_finite_float(baseline_summary.get(key))
            value = _as_finite_float(summary.get(key))
            if baseline_value is None or value is None:
                continue
            delta = value - baseline_value
            if abs(delta) < 1e-12:
                continue
            percent = _percent_change(delta, baseline_value)
            change_rows.append(
                "<tr>"
                f"<td>{escape(str(row['label']))}</td>"
                f"<td>{escape(_label(key))}</td>"
                f"<td>{escape(_format_value(baseline_value))}</td>"
                f"<td>{escape(_format_value(value))}</td>"
                f"<td>{escape(_signed_value(delta))}</td>"
                f"<td>{escape(percent)}</td>"
                "</tr>"
            )
    if not change_rows:
        return ""
    return (
        "<section>"
        "<h2>Baseline Changes</h2>"
        f'<p class="muted">Each row compares a scenario against the first scenario, {escape(baseline_label)}. '
        "Use this as a quick direction-of-change view before inspecting the plots.</p>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Scenario</th><th>Metric</th><th>Baseline</th><th>Scenario</th><th>Delta</th><th>Change</th></tr></thead>"
        f"<tbody>{''.join(change_rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _has_different_values(key: str, flattened: list[tuple[str, dict[str, Any]]]) -> bool:
    values = {_normalized_config_value(config.get(key)) for _label_name, config in flattened}
    return len(values) > 1


def _flatten_config(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    flattened: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, dict):
            flattened.update(_flatten_config(child, path))
        else:
            flattened[path] = child
    return flattened


def _normalized_config_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _plot_previews(rows: list[dict[str, Any]], preview_plots: tuple[str, ...]) -> str:
    figures: list[str] = []
    for row in rows:
        plots = row.get("plots", {})
        if not isinstance(plots, dict):
            continue
        for plot_name in preview_plots:
            plot_path = plots.get(plot_name)
            if not plot_path:
                continue
            figures.append(
                (
                    '<figure class="preview">'
                    f'<a href="{escape(str(row["report"]))}">'
                    f'<img src="{escape(str(plot_path))}" alt="{escape(str(row["label"]))} {escape(plot_name)}">'
                    "</a>"
                    f'<figcaption>{escape(str(row["label"]))} - {escape(plot_name)}</figcaption>'
                    "</figure>"
                )
            )
            break
    if not figures:
        return ""
    return (
        "<section>"
        "<h2>Plot Previews</h2>"
        '<div class="preview-grid">'
        + "\n".join(figures)
        + "</div>"
        "</section>"
    )


def _comparison_plots(output: Path) -> str:
    plot_dir = output / "comparison_plots"
    if not plot_dir.exists():
        return ""
    figures = "\n".join(
        (
            '<figure class="comparison">'
            f'<img src="comparison_plots/{escape(plot.name)}" alt="{escape(plot.stem)}">'
            f"<figcaption>{escape(plot.name)}</figcaption>"
            "</figure>"
        )
        for plot in sorted(plot_dir.glob("*.png"))
    )
    if not figures:
        return ""
    return (
        "<section>"
        "<h2>Comparison Plots</h2>"
        '<div class="comparison-grid">'
        + figures
        + "</div>"
        "</section>"
    )


def _metric_row(row: dict[str, Any], metric_keys: list[str]) -> str:
    summary = row.get("summary", {})
    values = "".join(
        f"<td>{escape(_format_value(summary.get(key)))}</td>"
        for key in metric_keys
    )
    return (
        "<tr>"
        f'<td><a href="{escape(str(row["report"]))}">{escape(str(row["label"]))}</a></td>'
        f"<td>{escape(str(row['lab_name']))}</td>"
        f"<td>{escape(str(row['config_path']))}</td>"
        f"{values}"
        "</tr>"
    )


def _display_metric_keys(guide: BatchGuide, rows: list[dict[str, Any]]) -> list[str]:
    summaries = [row.get("summary", {}) for row in rows]
    primary_keys = [
        key
        for key in guide.metric_keys
        if any(_has_value(summary.get(key)) for summary in summaries)
    ]
    extra_keys = [
        key
        for key in INDEX_METRIC_KEYS
        if key not in guide.metric_keys and any(_has_interesting_metric_value(summary.get(key)) for summary in summaries)
    ]
    return primary_keys + extra_keys


def _available_plot_paths(run_dir: Path) -> dict[str, str]:
    plots_dir = run_dir / "plots"
    if not plots_dir.exists():
        return {}
    return {
        path.name: f"{run_dir.name}/plots/{path.name}"
        for path in sorted(plots_dir.glob("*.png"))
    }


def _load_config_for_report(run_dir: Path, config_path: str) -> dict[str, Any]:
    snapshot = run_dir / "config.yaml"
    try:
        return load_config(snapshot if snapshot.exists() else config_path)
    except (OSError, ValueError):
        return {}


def write_comparison_plots(
    batch_output: str | Path,
    batch_name: str,
    scenarios: tuple[BatchScenario, ...],
) -> list[Path]:
    guide = BATCH_GUIDES.get(batch_name)
    if guide is None or not guide.comparison_specs:
        return []

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("matplotlib is required when batch plots are enabled.") from exc

    output = Path(batch_output)
    plot_dir = output / "comparison_plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    datasets = [
        (scenario.label, _read_csv_rows(output / _safe_name(scenario.label) / "log.csv"))
        for scenario in scenarios
    ]
    written: list[Path] = []
    for filename, title, ylabel, signal_key in guide.comparison_specs:
        available = [
            (label, rows)
            for label, rows in datasets
            if rows and any(signal_key in row for row in rows)
        ]
        if not available:
            continue
        fig, axis = plt.subplots(figsize=(8.5, 4.8), constrained_layout=True)
        for label, rows in available:
            time = [_as_float(row.get("time", index)) for index, row in enumerate(rows)]
            values = [_as_float(row.get(signal_key)) for row in rows]
            axis.plot(time, values, label=label)
        axis.set_title(title)
        axis.set_xlabel("time [s]")
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize="small")
        target = plot_dir / filename
        fig.savefig(target, dpi=150)
        plt.close(fig)
        written.append(target)
    return written


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _has_interesting_metric_value(value: Any) -> bool:
    if not _has_value(value):
        return False
    number = _as_finite_float(value)
    if number is None:
        return True
    return abs(number) > 1e-12


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _signed_value(value: float) -> str:
    formatted = _format_value(abs(value))
    if value > 0.0:
        return f"+{formatted}"
    if value < 0.0:
        return f"-{formatted}"
    return formatted


def _percent_change(delta: float, baseline_value: float) -> str:
    if abs(baseline_value) < 1e-12:
        return "n/a"
    return f"{100.0 * delta / abs(baseline_value):+.3g}%"


def _as_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _label(key: str) -> str:
    return key.replace("_", " ")


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
