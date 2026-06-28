"""Learner-facing launcher menu for local MuJoCo labs."""

from __future__ import annotations

import json
import subprocess
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Thread
from typing import Any

from mclab.batch import ALL_BATCH_NAME, BATCH_SETS
from mclab.config import PROJECT_ROOT, load_config
from mclab.sim.reporting import write_outputs_index

RUN_COMPLETE_PREFIX = "Run complete:"
BATCH_COMPLETE_PREFIX = "Batch complete:"
COMPLETE_PREFIXES = (RUN_COMPLETE_PREFIX, BATCH_COMPLETE_PREFIX)
DOC_PATHS = {
    "lab01": "docs/lab01_mass_spring_damper.md",
    "lab02": "docs/lab02_pid_control.md",
    "lab03": "docs/lab03_trajectory_planning.md",
    "lab04": "docs/lab04_panda_manipulator.md",
}


@dataclass(frozen=True)
class MenuAction:
    group: str
    label: str
    lab_name: str
    config_path: str
    plots: str
    description: str
    try_this: str
    watch: str


@dataclass(frozen=True)
class BatchMenuAction:
    group: str
    label: str
    batch_name: str
    description: str
    try_this: str
    watch: str


@dataclass(frozen=True)
class LearningPathStep:
    title: str
    action_kind: str
    group: str
    label: str
    description: str


@dataclass(frozen=True)
class LearningPathProgress:
    completed: bool
    latest_output: Path | None = None


LearningPathProgressItem = tuple[LearningPathStep, LearningPathProgress]


@dataclass(frozen=True)
class ActionReadiness:
    status: str
    label: str
    detail: str = ""
    fix: str = ""


@dataclass(frozen=True)
class ExperienceFilter:
    key: str
    label: str
    description: str


EXPERIENCE_FILTERS: tuple[ExperienceFilter, ...] = (
    ExperienceFilter("all", "All", "Show every guided scenario."),
    ExperienceFilter("hands-on", "Hands-on", "Live tuning, presets, and disturbance controls."),
    ExperienceFilter("compare", "Compare", "Paired scenarios that make one design tradeoff visible."),
    ExperienceFilter("pid", "PID", "Gain tuning, saturation, windup, noise, and delay."),
    ExperienceFilter("trajectory", "Trajectory", "Step, trapezoid, minimum-jerk, S-curve, and joint paths."),
    ExperienceFilter("2dof", "2DOF", "Two-link arm joint-space, task-space, and singularity demos."),
    ExperienceFilter("panda", "Panda", "Full manipulator joint, Cartesian, and wall demos."),
    ExperienceFilter("wall", "Wall", "Virtual wall stiffness, damping, penetration, and retreat."),
    ExperienceFilter("singularity", "Singularity", "Jacobian conditioning and DLS behavior."),
)


def experience_filter_description(key: str) -> str:
    normalized = key.lower().strip()
    for filter_option in EXPERIENCE_FILTERS:
        if filter_option.key == normalized:
            return filter_option.description
    return EXPERIENCE_FILTERS[0].description


BATCH_ACTIONS: tuple[BatchMenuAction, ...] = (
    BatchMenuAction(
        group="Comparison Batches",
        label="All compare",
        batch_name=ALL_BATCH_NAME,
        description="Run every comparison batch and create a course-level report set.",
        try_this="Open the top report, then step through Lab01 to Lab04 in order.",
        watch="How the same control ideas scale from 1D plants to Panda virtual wall behavior.",
    ),
    BatchMenuAction(
        group="Comparison Batches",
        label="Lab01 compare",
        batch_name="lab01_msd_compare",
        description="Run baseline, damping, and stiffness mass-spring-damper cases.",
        try_this="Open the generated index and compare max position and settling behavior.",
        watch="Which physical parameter changes oscillation frequency and damping.",
    ),
    BatchMenuAction(
        group="Comparison Batches",
        label="Lab02 PID compare",
        batch_name="lab02_pid_compare",
        description="Run gain, saturation, windup, noise, and delay PID cases.",
        try_this="Open the generated index and compare overshoot, settling, and effort.",
        watch="Which controller choice trades speed for overshoot or noisy force.",
    ),
    BatchMenuAction(
        group="Comparison Batches",
        label="Lab03 2DOF compare",
        batch_name="lab03_2dof_compare",
        description="Run joint-space, task-space, singularity, and DLS 2DOF arm cases.",
        try_this="Compare joint error, hand error, torque, manipulability, and DLS joint speed.",
        watch="How task-space control, singularity, and DLS damping change the arm response.",
    ),
    BatchMenuAction(
        group="Comparison Batches",
        label="Lab04 wall compare",
        batch_name="lab04_wall_compare",
        description="Run soft and stiff Panda virtual wall cases.",
        try_this="Compare wall penetration, virtual force, retreat, and hand X motion.",
        watch="How wall stiffness and damping change the contact-like response.",
    ),
    BatchMenuAction(
        group="Comparison Batches",
        label="Lab04 Cartesian compare",
        batch_name="lab04_cartesian_compare",
        description="Run baseline, soft, and stiff Panda Cartesian reach cases.",
        try_this="Compare Cartesian error, hand position, and actuator effort.",
        watch="How reach gain and step limits trade tracking error against effort.",
    ),
)


LEARNING_PATH: tuple[LearningPathStep, ...] = (
    LearningPathStep(
        title="1. Feel 1D physics",
        action_kind="run",
        group="Lab01 Mass-Spring-Damper",
        label="Auto demo",
        description="Start with position, velocity, force, and energy.",
    ),
    LearningPathStep(
        title="2. Disturb and tune",
        action_kind="run",
        group="Lab01 Mass-Spring-Damper",
        label="Interactive",
        description="Push the mass and tune mass, damping, and stiffness live.",
    ),
    LearningPathStep(
        title="3. Close the loop",
        action_kind="run",
        group="Lab02 PID Control",
        label="Auto demo",
        description="Watch PID tracking, error, and control force.",
    ),
    LearningPathStep(
        title="4. Tune PID live",
        action_kind="run",
        group="Lab02 PID Control",
        label="Interactive",
        description="Disturb the plant and tune target, Kp, Ki, Kd, and force limit.",
    ),
    LearningPathStep(
        title="5. Move 2DOF joints",
        action_kind="run",
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF joint-space",
        description="Track shoulder and elbow targets on the two-link arm.",
    ),
    LearningPathStep(
        title="6. Control the hand",
        action_kind="run",
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF task-space",
        description="Move the end-effector toward an XY target with the Jacobian.",
    ),
    LearningPathStep(
        title="7. Hold Panda",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Neutral hold",
        description="Use a stable neutral pose as the full manipulator baseline.",
    ),
    LearningPathStep(
        title="8. Reach in Cartesian",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Cartesian reach",
        description="Move the Panda hand toward an XYZ target before adding wall response.",
    ),
    LearningPathStep(
        title="9. Touch virtual wall",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        description="Tune wall position, stiffness, damping, and retreat gain.",
    ),
    LearningPathStep(
        title="10. Compare the course",
        action_kind="batch",
        group="Comparison Batches",
        label="All compare",
        description="Generate the full comparison report set across all labs.",
    ),
)


MENU_ACTIONS: tuple[MenuAction, ...] = (
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Auto demo",
        lab_name="lab01",
        config_path="configs/lab01_msd/default.yaml",
        plots="essential",
        description="Watch free response and force/position plots.",
        try_this="Start here and compare position, velocity, and applied force.",
        watch="How quickly the mass returns near zero.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Underdamped",
        lab_name="lab01",
        config_path="configs/lab01_msd/underdamped.yaml",
        plots="essential",
        description="Low damping makes the mass oscillate before settling.",
        try_this="Run this after Auto demo and compare the number of swings.",
        watch="Large overshoot and slow energy decay.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Overdamped",
        lab_name="lab01",
        config_path="configs/lab01_msd/over_damped.yaml",
        plots="essential",
        description="High damping removes oscillation but slows the return.",
        try_this="Run after Underdamped and compare settling behavior.",
        watch="Little overshoot, slower motion.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="High stiffness",
        lab_name="lab01",
        config_path="configs/lab01_msd/high_stiffness.yaml",
        plots="essential",
        description="A stiffer spring creates faster, sharper motion.",
        try_this="Compare against Low stiffness.",
        watch="Higher frequency motion and larger force changes.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Low stiffness",
        lab_name="lab01",
        config_path="configs/lab01_msd/low_stiffness.yaml",
        plots="essential",
        description="A softer spring responds more slowly.",
        try_this="Compare against High stiffness.",
        watch="Lower frequency motion and slower return.",
    ),
    MenuAction(
        group="Lab01 Mass-Spring-Damper",
        label="Interactive",
        lab_name="lab01",
        config_path="configs/lab01_msd/interactive_pull.yaml",
        plots="essential",
        description="Push the mass and tune mass, damping, stiffness.",
        try_this="Click Pull/Push, then try damping and stiffness presets.",
        watch="Gray equilibrium marker, position, force, and total energy.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Auto demo",
        lab_name="lab02",
        config_path="configs/lab02_pid/default.yaml",
        plots="essential",
        description="Watch PID tracking, error, and force.",
        try_this="Start here and use the plots as the baseline response.",
        watch="Tracking error and control force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Low P gain",
        lab_name="lab02",
        config_path="configs/lab02_pid/p_low_gain.yaml",
        plots="essential",
        description="Low proportional gain responds gently but slowly.",
        try_this="Compare against High P gain.",
        watch="Slow rise and persistent error.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="High P gain",
        lab_name="lab02",
        config_path="configs/lab02_pid/p_high_gain.yaml",
        plots="essential",
        description="High proportional gain reacts strongly.",
        try_this="Compare against Low P gain.",
        watch="Overshoot, oscillation, and larger force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="PD damping",
        lab_name="lab02",
        config_path="configs/lab02_pid/pd_damped.yaml",
        plots="essential",
        description="Derivative action damps the P response.",
        try_this="Run after High P gain.",
        watch="Reduced overshoot and smoother force.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Saturation",
        lab_name="lab02",
        config_path="configs/lab02_pid/saturation_limit.yaml",
        plots="essential",
        description="Force limits cap the controller output.",
        try_this="Compare response speed against Auto demo.",
        watch="Control force clipping and slower tracking.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Windup",
        lab_name="lab02",
        config_path="configs/lab02_pid/pid_with_windup.yaml",
        plots="essential",
        description="Integral windup can keep pushing after saturation.",
        try_this="Run before Anti-windup.",
        watch="Overshoot after the error has changed sign.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Anti-windup",
        lab_name="lab02",
        config_path="configs/lab02_pid/pid_anti_windup.yaml",
        plots="essential",
        description="Anti-windup limits integral buildup.",
        try_this="Compare directly against Windup.",
        watch="Less overshoot and cleaner settling.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Sensor noise",
        lab_name="lab02",
        config_path="configs/lab02_pid/measurement_noise.yaml",
        plots="pid",
        description="Noisy position measurement makes the controller push unevenly.",
        try_this="Compare measured_position against true position.",
        watch="Force jitter and larger measured tracking error.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Control delay",
        lab_name="lab02",
        config_path="configs/lab02_pid/control_delay.yaml",
        plots="essential",
        description="A delayed control force reacts to old error.",
        try_this="Compare against Auto demo with the same gains.",
        watch="Slower correction, overshoot, and settling time.",
    ),
    MenuAction(
        group="Lab02 PID Control",
        label="Interactive",
        lab_name="lab02",
        config_path="configs/lab02_pid/interactive_disturbance.yaml",
        plots="essential",
        description="Disturb the mass and tune target, Kp, Ki, Kd, force limit.",
        try_this="Move the target slider or click a PID preset.",
        watch="Target marker, error, PID force, and disturbance force.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF joint-space",
        lab_name="lab03",
        config_path="configs/lab03_2dof/joint_space_2dof.yaml",
        plots="essential",
        description="A two-link arm tracks shoulder and elbow joint targets.",
        try_this="Start here to see the actual 2DOF manipulator.",
        watch="Joint positions, end-effector motion, and torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF task-space",
        lab_name="lab03",
        config_path="configs/lab03_2dof/task_space_2dof.yaml",
        plots="task",
        description="The arm moves its hand toward an XY target with Jacobian-transpose PD.",
        try_this="Watch the blue hand point move toward the green target point.",
        watch="Hand X/Y tracking, task error, and joint torque distribution.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF singularity",
        lab_name="lab03",
        config_path="configs/lab03_2dof/singularity_2dof.yaml",
        plots="singularity",
        description="The arm approaches a nearly straight singular posture.",
        try_this="Watch for the orange hand marker near the workspace edge.",
        watch="Jacobian condition number rises while manipulability falls.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF DLS singularity",
        lab_name="lab03",
        config_path="configs/lab03_2dof/dls_singularity_2dof.yaml",
        plots="dls",
        description="Damped least-squares limits inverse-Jacobian motion near the workspace edge.",
        try_this="Watch the hand marker near the workspace edge, then compare dls.png.",
        watch="DLS joint speed, damping, condition number, and torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_2dof.yaml",
        plots="task",
        description="Tune the hand target, task stiffness, damping, and torque limit live.",
        try_this="Move target X/Y sliders or click a reach preset.",
        watch="Live status hand position, target marker, error norm, and max torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Step profile",
        lab_name="lab03",
        config_path="configs/lab03_2dof/step.yaml",
        plots="essential",
        description="A sudden target step demands abrupt control effort.",
        try_this="Run before smoother trajectory profiles.",
        watch="Force spike and tracking error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Trapezoid",
        lab_name="lab03",
        config_path="configs/lab03_2dof/trapezoidal.yaml",
        plots="essential",
        description="A trapezoidal profile limits velocity and acceleration.",
        try_this="Compare against Step profile.",
        watch="Lower force peaks and smoother velocity.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="Minimum jerk",
        lab_name="lab03",
        config_path="configs/lab03_2dof/minimum_jerk.yaml",
        plots="essential",
        description="Minimum-jerk motion starts and stops smoothly.",
        try_this="Compare against Trapezoid and S-curve.",
        watch="Smooth position/velocity and smaller error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="S-curve",
        lab_name="lab03",
        config_path="configs/lab03_2dof/s_curve.yaml",
        plots="essential",
        description="S-curve motion smooths jerk transitions.",
        try_this="Compare against Step profile.",
        watch="Reduced abruptness in control effort.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="1D interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_tracking.yaml",
        plots="essential",
        description="Disturb the tracker and tune gains, target offset, force limit.",
        try_this="Disturb the mass, then change Kp, Kd, and force limit.",
        watch="Live status target, error, and control force.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Neutral hold",
        lab_name="lab04",
        config_path="configs/lab04_panda/neutral_hold.yaml",
        plots="essential",
        description="Hold the Panda at a neutral pose.",
        try_this="Use this as the stable manipulator baseline.",
        watch="Joint error norm stays small.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint 4 path",
        lab_name="lab04",
        config_path="configs/lab04_panda/joint_pd.yaml",
        plots="essential",
        description="Move one Panda joint with a minimum-jerk target.",
        try_this="Compare q_3 against target_q_3 in the saved plot.",
        watch="Tracking error during the motion.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint 6 S-curve",
        lab_name="lab04",
        config_path="configs/lab04_panda/trajectory_tracking.yaml",
        plots="essential",
        description="Move another Panda joint with an S-curve target.",
        try_this="Compare against Joint 4 path.",
        watch="Which joint moves and how the hand position changes.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Reach X",
        lab_name="lab04",
        config_path="configs/lab04_panda/reach_x.yaml",
        plots="cartesian",
        description="Move a joint that visibly changes hand X position.",
        try_this="Watch the end-effector plot after the run.",
        watch="Hand X/Y/Z motion and joint error.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Cartesian reach",
        lab_name="lab04",
        config_path="configs/lab04_panda/cartesian_reach.yaml",
        plots="cartesian_reach",
        description="Move the Panda hand toward an explicit XYZ target.",
        try_this="Compare target_x_ee and x_ee in end_effector.png.",
        watch="Cartesian error, actuator force, and joint tracking error.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Soft Cartesian",
        lab_name="lab04",
        config_path="configs/lab04_panda/cartesian_soft.yaml",
        plots="cartesian_reach",
        description="A softer Cartesian reach command moves calmly toward the hand target.",
        try_this="Run before Stiff Cartesian and compare cartesian_error.png.",
        watch="Larger remaining hand error with a calmer target-offset command.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Stiff Cartesian",
        lab_name="lab04",
        config_path="configs/lab04_panda/cartesian_stiff.yaml",
        plots="cartesian_reach",
        description="A stiffer Cartesian reach command pursues the same hand target more aggressively.",
        try_this="Run after Soft Cartesian and compare torque.png.",
        watch="Smaller hand error and any changes in actuator force traces.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Cartesian interactive",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_cartesian_reach.yaml",
        plots="cartesian_reach",
        description="Tune hand target X/Y/Z and Cartesian gain live.",
        try_this="Move Target X/Y/Z sliders or click a reach preset.",
        watch="Live hand error and end-effector plot after the run.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Joint target",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_joint_hold.yaml",
        plots="essential",
        description="Nudge a Panda joint target and watch tracking error.",
        try_this="Click Joint Target -/+ several times.",
        watch="Live status target offset and error norm.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Soft wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_soft.yaml",
        plots="wall_compare",
        description="A lower-stiffness virtual wall lets the hand penetrate more.",
        try_this="Run before Stiff wall and compare virtual_wall.png.",
        watch="Higher penetration, lower force, smaller retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Stiff wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_stiff.yaml",
        plots="wall_compare",
        description="A higher-stiffness virtual wall retreats more aggressively.",
        try_this="Run after Soft wall with the same trajectory.",
        watch="Lower penetration, higher force, larger retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
        plots="wall",
        description="Tune wall position, stiffness, damping, and retreat gain.",
        try_this="Move wall X or click Soft/Stiff/Close wall presets.",
        watch="Wall penetration, wall force, and hand X position.",
    ),
)


def build_run_args(action: MenuAction) -> list[str]:
    return [
        sys.executable,
        "-m",
        "mclab",
        "run",
        action.lab_name,
        "--config",
        action.config_path,
        "--viewer",
        "--realtime",
        "--pause-at-end",
        "--plot",
        "--plots",
        action.plots,
        "--open-report",
    ]


def launch_action(action: MenuAction) -> subprocess.Popen[str]:
    return subprocess.Popen(
        build_run_args(action),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def build_batch_args(action: BatchMenuAction) -> list[str]:
    return [
        sys.executable,
        "-m",
        "mclab",
        "batch",
        action.batch_name,
        "--open-report",
    ]


def build_doctor_args() -> list[str]:
    return [sys.executable, "-m", "mclab", "doctor"]


def launch_batch_action(action: BatchMenuAction) -> subprocess.Popen[str]:
    return subprocess.Popen(
        build_batch_args(action),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def launch_doctor_check() -> subprocess.Popen[str]:
    return subprocess.Popen(
        build_doctor_args(),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def learning_path_target(step: LearningPathStep) -> MenuAction | BatchMenuAction:
    actions: tuple[MenuAction | BatchMenuAction, ...]
    if step.action_kind == "run":
        actions = MENU_ACTIONS
    elif step.action_kind == "batch":
        actions = BATCH_ACTIONS
    else:
        raise ValueError(f"Unknown learning path action kind: {step.action_kind}")

    for action in actions:
        if action.group == step.group and action.label == step.label:
            return action
    raise ValueError(f"Learning path target was not found: {step.group} - {step.label}")


def learning_path_text(step: LearningPathStep) -> str:
    action = learning_path_target(step)
    return f"{step.description}\nRun: {action.group} - {action.label}\nWatch: {action.watch}"


def learning_path_progress(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> LearningPathProgress:
    action = learning_path_target(step)
    latest = action_latest_output(action, outputs_root)
    return LearningPathProgress(completed=latest is not None, latest_output=latest)


def learning_path_progress_text(
    step: LearningPathStep,
    progress: LearningPathProgress | None = None,
) -> str:
    current = progress if progress is not None else learning_path_progress(step)
    status = (
        f"Status: Done - latest {current.latest_output.name}"
        if current.latest_output is not None
        else "Status: Not run yet"
    )
    return f"{learning_path_text(step)}\n{status}"


def learning_path_progress_items(
    outputs_root: Path | None = None,
) -> tuple[LearningPathProgressItem, ...]:
    return tuple((step, learning_path_progress(step, outputs_root)) for step in LEARNING_PATH)


def next_learning_path_step(
    progress_items: tuple[LearningPathProgressItem, ...] | None = None,
) -> LearningPathStep | None:
    items = progress_items if progress_items is not None else learning_path_progress_items()
    for step, progress in items:
        if not progress.completed:
            return step
    return None


def learning_path_summary_text(
    progress_items: tuple[LearningPathProgressItem, ...] | None = None,
) -> str:
    items = progress_items if progress_items is not None else learning_path_progress_items()
    total = len(items)
    completed = sum(1 for _step, progress in items if progress.completed)
    next_step = next_learning_path_step(items)
    if next_step is None:
        return f"Progress: {completed}/{total} complete. Course path complete - open All reports to review."
    return f"Progress: {completed}/{total} complete. Next: {next_step.title} - {next_step.description}"


def action_latest_output(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> Path | None:
    root = outputs_root if outputs_root is not None else PROJECT_ROOT / "outputs"
    return _latest_matching_output(action, root)


def action_history_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "History: Not run yet"
    return f"History: Latest {latest.name}"


def _latest_matching_output(action: MenuAction | BatchMenuAction, outputs_root: Path) -> Path | None:
    if not outputs_root.exists():
        return None
    matches: list[tuple[float, Path]] = []
    for output_path, summary, modified in _iter_output_summaries(outputs_root):
        if _summary_matches_action(summary, action):
            matches.append((modified, output_path))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def _iter_output_summaries(outputs_root: Path) -> list[tuple[Path, dict[str, Any], float]]:
    summaries: list[tuple[Path, dict[str, Any], float]] = []
    for child in outputs_root.iterdir():
        if not child.is_dir():
            continue
        summary_path = child / "summary.json"
        summary = _read_json(summary_path)
        if not summary:
            continue
        modified = max(
            (
                path.stat().st_mtime
                for path in (child / "report.html", child / "index.html", summary_path)
                if path.exists()
            ),
            default=child.stat().st_mtime,
        )
        summaries.append((child, summary, modified))
    return summaries


def _summary_matches_action(summary: dict[str, Any], action: MenuAction | BatchMenuAction) -> bool:
    if isinstance(action, BatchMenuAction):
        batch_name = str(summary.get("batch_name") or summary.get("config_name") or "")
        return batch_name == action.batch_name

    config_path = _normalize_config_path(str(summary.get("config_path") or ""))
    if config_path:
        return config_path == _normalize_config_path(action.config_path)

    config_name = str(summary.get("config_name") or "")
    lab_name = str(summary.get("lab_name") or "")
    return config_name == Path(action.config_path).stem and action.lab_name in lab_name


def _normalize_config_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").lower()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_run_output_path(line: str) -> Path | None:
    stripped = line.strip()
    for prefix in COMPLETE_PREFIXES:
        if not stripped.startswith(prefix):
            continue
        raw_path = stripped.removeprefix(prefix).strip()
        if not raw_path:
            return None
        return Path(raw_path)
    return None


def action_config_path(action: MenuAction) -> Path:
    return PROJECT_ROOT / action.config_path


def action_doc_path(action: MenuAction) -> Path:
    return PROJECT_ROOT / DOC_PATHS[action.lab_name]


def action_readiness(action: MenuAction, root: Path | None = None) -> ActionReadiness:
    project_root = root if root is not None else PROJECT_ROOT
    return _action_readiness(action.config_path, str(project_root))


@lru_cache(maxsize=256)
def _action_readiness(config_path: str, root: str) -> ActionReadiness:
    project_root = Path(root)
    resolved_config = project_root / config_path
    if not resolved_config.exists():
        return ActionReadiness(
            "fail",
            "Missing config",
            config_path,
            "Restore the YAML file or choose another scenario.",
        )
    try:
        config = load_config(resolved_config)
    except Exception as exc:
        return ActionReadiness(
            "fail",
            "Config error",
            f"{config_path}: {exc}",
            "Open Config and fix the YAML before running.",
        )
    model_path = config.get("model_path")
    if not isinstance(model_path, str) or not model_path.strip():
        return ActionReadiness(
            "fail",
            "Missing model_path",
            config_path,
            "Add model_path to the YAML config.",
        )
    resolved_model = Path(model_path)
    if not resolved_model.is_absolute():
        resolved_model = project_root / resolved_model
    if not resolved_model.exists():
        fix = "Run Check setup for diagnosis."
        if "mujoco_menagerie" in model_path.replace("\\", "/"):
            fix = "Run `python scripts/bootstrap_and_run.py --setup-only` to fetch MuJoCo Menagerie."
        return ActionReadiness("fail", "Missing model", model_path, fix)
    return ActionReadiness("ok", "Ready", f"model: {model_path}")


def launch_action_config(action: MenuAction) -> subprocess.Popen[Any] | None:
    return open_editable_path(action_config_path(action))


def launch_action_doc(action: MenuAction) -> subprocess.Popen[Any] | None:
    return open_editable_path(action_doc_path(action))


def launch_outputs_folder() -> subprocess.Popen[Any] | None:
    outputs = PROJECT_ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    return open_path(outputs)


def launch_outputs_index() -> subprocess.Popen[Any] | None:
    outputs = PROJECT_ROOT / "outputs"
    index = outputs / "index.html"
    if not index.exists():
        write_outputs_index(outputs)
    return open_path(index)


def launch_latest_output(latest_output: dict[str, Path | None]) -> subprocess.Popen[Any] | None:
    path = latest_output.get("path")
    if path is None:
        return None
    return open_path(_preferred_output_entry(path))


def launch_action_latest_output(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return None
    return open_path(_preferred_output_entry(latest))


def _preferred_output_entry(path: Path) -> Path:
    report = path / "report.html"
    if report.exists():
        return report
    index = path / "index.html"
    if index.exists():
        return index
    return path


def open_path(path: Path) -> subprocess.Popen[Any] | None:
    if not path.exists():
        return None
    if sys.platform.startswith("win"):
        import os

        os.startfile(str(path))
        return None
    if sys.platform == "darwin":
        return subprocess.Popen(["open", str(path)])
    return subprocess.Popen(["xdg-open", str(path)])


def open_editable_path(path: Path) -> subprocess.Popen[Any] | None:
    if not path.exists():
        return None
    code_command = shutil.which("code")
    if path.is_file() and code_command:
        return subprocess.Popen([code_command, "-r", str(path)])
    return open_path(path)


def parameter_hint(action: MenuAction) -> str:
    label = action.label.lower()
    config_name = Path(action.config_path).name

    if action.lab_name == "lab01":
        if label == "interactive":
            return "live sliders/presets: mass, damping, stiffness; YAML: interaction.force, viewer_guides.enabled"
        if "damped" in label:
            return "damping, stiffness, initial_position"
        if "stiffness" in label:
            return "stiffness, damping, initial_position"
        return "mass, damping, stiffness, initial_position, force_input.magnitude"

    if action.lab_name == "lab02":
        if label == "interactive":
            return "live sliders/presets: target, Kp, Ki, Kd, force limit; YAML: target.end, controller.*"
        if label in {"windup", "anti-windup"}:
            return "controller.ki, controller.anti_windup, controller.output_limit"
        if label == "saturation":
            return "controller.output_limit, target.end"
        if label == "sensor noise":
            return "measurement_noise_std, controller.kp, controller.kd"
        if label == "control delay":
            return "control_delay, controller.kp, controller.kd"
        if "gain" in label or label == "pd damping":
            return "controller.kp, controller.kd, target.end"
        return "target.end, controller.kp, controller.ki, controller.kd, controller.output_limit"

    if action.lab_name == "lab03":
        if label == "2dof interactive":
            return (
                "live sliders/presets: Target X/Y, task stiffness, task damping, torque limit; "
                "YAML: target_xy, tracking_controller.task_kp, tracking_controller.task_kd, "
                "tracking_controller.torque_limit, viewer_guides.*"
            )
        if label == "2dof dls singularity":
            return "target_xy, tracking_controller.dls_gain, tracking_controller.dls_damping, viewer_guides.condition_threshold"
        if label == "2dof task-space":
            return "target_xy, tracking_controller.task_kp, tracking_controller.task_kd, viewer_guides.enabled"
        if label in {"2dof joint-space", "2dof singularity"}:
            return "initial_q, target_q, trajectory.duration, tracking_controller.kp, tracking_controller.kd"
        if config_name == "interactive_tracking.yaml":
            return (
                "live sliders/presets: target offset, Kp, Kd, force limit; "
                "YAML: trajectory.end, tracking_controller.kp, tracking_controller.kd, "
                "tracking_controller.force_limit"
            )
        return (
            "trajectory.type, trajectory.duration, tracking_controller.kp, "
            "tracking_controller.kd, tracking_controller.force_limit"
        )

    if action.lab_name == "lab04":
        if label == "cartesian interactive":
            return "live sliders/presets: Target X/Y/Z, Cartesian gain; YAML: cartesian_target.*"
        if config_name == "interactive_virtual_wall.yaml":
            return (
                "live sliders/presets: wall X, stiffness, damping, retreat gain; "
                "YAML: virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, "
                "virtual_wall.force_retreat_gain"
            )
        if "cartesian" in label:
            return "cartesian_target.position, cartesian_target.gain, cartesian_target.max_step"
        if "wall" in label:
            return "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping, virtual_wall.force_retreat_gain"
        if label == "joint target":
            return "interaction.target_step, interaction.target_limit, trajectory.end"
        if label == "neutral hold":
            return "home_q, sim_time"
        return "controlled_joint_index, trajectory.start, trajectory.end, trajectory.duration"

    return "config YAML values"


def config_value_preview(action: MenuAction, *, max_items: int = 5) -> str:
    return _config_value_preview(action.config_path, parameter_hint(action), max_items)


@lru_cache(maxsize=256)
def _config_value_preview(config_path: str, hint: str, max_items: int) -> str:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return "Values: Config unavailable"

    entries: list[str] = []
    for path in _hint_config_paths(hint):
        for resolved_path, value in _resolve_preview_values(config, path):
            entries.append(f"{resolved_path}={_format_config_value(value)}")
            if len(entries) >= max_items:
                return f"Values: {'; '.join(entries)}"
    if not entries:
        return "Values: Open Config to inspect YAML"
    return f"Values: {'; '.join(entries)}"


def _hint_config_paths(hint: str) -> tuple[str, ...]:
    paths: list[str] = []
    for raw_part in hint.replace(";", ",").split(","):
        candidate = raw_part.strip()
        if ":" in candidate:
            candidate = candidate.split(":", 1)[1].strip()
        candidate = candidate.strip("` ")
        if not candidate or " " in candidate or "/" in candidate:
            continue
        if candidate == "config" or candidate.startswith("live"):
            continue
        if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.*" for character in candidate):
            continue
        paths.append(candidate)
    return tuple(dict.fromkeys(paths))


def _resolve_preview_values(config: dict[str, Any], path: str) -> tuple[tuple[str, Any], ...]:
    if path.endswith(".*"):
        parent_path = path.removesuffix(".*")
        parent = _get_config_value(config, parent_path)
        if not isinstance(parent, dict):
            return ()
        return tuple(
            (f"{parent_path}.{key}", value)
            for key, value in parent.items()
            if _is_preview_value(value)
        )

    value = _get_config_value(config, path)
    if not _is_preview_value(value):
        return ()
    return ((path, value),)


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_preview_value(value: Any) -> bool:
    if isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list | tuple):
        return all(isinstance(item, bool | int | float | str) for item in value)
    return False


def _format_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return f"{value:g}"
    if isinstance(value, str):
        return value if len(value) <= 32 else f"{value[:29]}..."
    if isinstance(value, list | tuple):
        shown = [_format_config_value(item) for item in value[:4]]
        suffix = ", ..." if len(value) > 4 else ""
        return f"[{', '.join(shown)}{suffix}]"
    return str(value)


def lesson_text(action: MenuAction) -> str:
    preset_labels = configured_preset_labels(action.config_path)
    presets = f"\nPresets: {', '.join(preset_labels)}" if preset_labels else ""
    readiness = action_readiness(action)
    setup_detail = f" - {readiness.detail}" if readiness.status != "ok" and readiness.detail else ""
    setup_fix = f" Fix: {readiness.fix}" if readiness.status != "ok" and readiness.fix else ""
    return (
        f"{action.description}\n"
        f"Setup: {readiness.label}{setup_detail}{setup_fix}\n"
        f"{action_history_text(action)}\n"
        f"Try: {action.try_this}\n"
        f"Change: {parameter_hint(action)}\n"
        f"{config_value_preview(action)}\n"
        f"Watch: {action.watch}"
        f"{presets}"
    )


@lru_cache(maxsize=128)
def configured_preset_labels(config_path: str) -> tuple[str, ...]:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return ()
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return ()
    presets = interaction.get("tuning_presets")
    if not isinstance(presets, list):
        return ()
    labels: list[str] = []
    for index, preset in enumerate(presets, start=1):
        if not isinstance(preset, dict):
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return tuple(labels)


def action_tags(action: MenuAction) -> tuple[str, ...]:
    label = action.label.lower()
    config_name = Path(action.config_path).name.lower()
    tags = {action.lab_name, action.lab_name.replace("lab", "lab "), action.group.lower()}

    if action.lab_name == "lab01":
        tags.update({"basics", "dynamics", "mass", "spring", "damper"})
    elif action.lab_name == "lab02":
        tags.update({"pid", "control", "closed-loop"})
    elif action.lab_name == "lab03":
        tags.add("trajectory")
        if "2dof" in label or "2dof" in config_name:
            tags.update({"2dof", "jacobian"})
    elif action.lab_name == "lab04":
        tags.update({"panda", "manipulator", "7dof"})

    if "interactive" in label or config_name.startswith("interactive_"):
        tags.add("hands-on")
    if label == "joint target":
        tags.add("hands-on")
    if _is_compare_action(action):
        tags.add("compare")
    if "wall" in label or "wall" in config_name:
        tags.add("wall")
    if "singularity" in label:
        tags.update({"singularity", "dls" if "dls" in label else "conditioning"})
    if "cartesian" in label or "reach" in label:
        tags.add("cartesian")
    if any(term in label for term in ("step", "trapezoid", "minimum jerk", "s-curve", "path")):
        tags.add("trajectory")
    if "gain" in label or "damping" in label or "windup" in label or "saturation" in label:
        tags.add("tuning")

    return tuple(sorted(tags))


def _is_compare_action(action: MenuAction) -> bool:
    label = action.label.lower()
    compare_labels = {
        "underdamped",
        "overdamped",
        "high stiffness",
        "low stiffness",
        "low p gain",
        "high p gain",
        "pd damping",
        "saturation",
        "windup",
        "anti-windup",
        "sensor noise",
        "control delay",
        "2dof joint-space",
        "2dof task-space",
        "2dof singularity",
        "2dof dls singularity",
        "step profile",
        "trapezoid",
        "minimum jerk",
        "s-curve",
        "joint 4 path",
        "joint 6 s-curve",
        "reach x",
        "cartesian reach",
        "soft cartesian",
        "stiff cartesian",
        "soft wall",
        "stiff wall",
    }
    return label in compare_labels


def filter_menu_actions(
    query: str,
    actions: tuple[MenuAction, ...] = MENU_ACTIONS,
    experience_filter: str = "all",
) -> tuple[MenuAction, ...]:
    filter_key = experience_filter.lower().strip()
    if filter_key and filter_key != "all":
        actions = tuple(action for action in actions if filter_key in action_tags(action))
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return actions
    return tuple(action for action in actions if _action_matches_terms(action, terms))


def _action_matches_terms(action: MenuAction, terms: list[str]) -> bool:
    text = " ".join(
        (
            action.group,
            action.label,
            action.lab_name,
            action.config_path,
            action.plots,
            action.description,
            action.try_this,
            action.watch,
            parameter_hint(action),
            " ".join(configured_preset_labels(action.config_path)),
            action_readiness(action).label,
            action_readiness(action).detail,
            " ".join(action_tags(action)),
            " ".join(tag.replace("-", " ") for tag in action_tags(action)),
            config_value_preview(action),
        )
    ).lower()
    return all(term in text for term in terms)


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        print(f"Learner menu could not start: {exc}")
        return 1

    root = tk.Tk()
    root.title("MuJoCo Control Lab")
    root.geometry("1120x820")
    root.minsize(960, 700)

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)

    title = ttk.Label(outer, text="MuJoCo Control Lab", font=("Segoe UI", 18, "bold"))
    title.pack(anchor="w")
    subtitle = ttk.Label(
        outer,
        text="Choose or search for a guided scenario, then disturb, tune, observe, and compare the run report.",
    )
    subtitle.pack(anchor="w", pady=(4, 12))

    status = tk.StringVar(value="Ready.")
    latest_output: dict[str, Path | None] = {"path": None}
    search = tk.StringVar(value="")
    active_experience_filter = tk.StringVar(value="all")
    filter_description = tk.StringVar(value=experience_filter_description("all"))
    path_status_vars: list[tuple[LearningPathStep, Any]] = []
    path_summary = tk.StringVar(value=learning_path_summary_text())
    next_step_ref: dict[str, LearningPathStep | None] = {"step": next_learning_path_step()}
    next_button_ref: dict[str, Any | None] = {"button": None}
    post_run_refresh_ref: dict[str, Callable[[], None]] = {}

    def refresh_learning_path_progress() -> None:
        progress_items: list[LearningPathProgressItem] = []
        for step, variable in path_status_vars:
            progress = learning_path_progress(step)
            progress_items.append((step, progress))
            variable.set(learning_path_progress_text(step, progress))
        items = tuple(progress_items) if progress_items else learning_path_progress_items()
        next_step = next_learning_path_step(items)
        next_step_ref["step"] = next_step
        path_summary.set(learning_path_summary_text(items))
        next_button = next_button_ref["button"]
        if next_button is not None:
            next_button.state(["disabled"] if next_step is None else ["!disabled"])

    def refresh_after_run() -> None:
        refresh_callback = post_run_refresh_ref.get("callback", refresh_learning_path_progress)
        refresh_callback()

    def launch_next_learning_path_step() -> None:
        step = next_step_ref["step"]
        if step is None:
            status.set("Learning path is complete. Open all reports to review the saved runs.")
            return
        _launch_learning_path_from_menu(
            step,
            status,
            root=root,
            latest_output=latest_output,
            latest_button=latest_button,
            progress_callback=refresh_after_run,
        )

    search_bar = ttk.Frame(outer)
    search_bar.pack(fill="x", pady=(0, 10))
    ttk.Label(search_bar, text="Search").pack(side="left")
    search_entry = ttk.Entry(search_bar, textvariable=search, width=42)
    search_entry.pack(side="left", padx=(8, 8))
    ttk.Button(search_bar, text="Clear", command=lambda: search.set("")).pack(side="left")
    match_count = ttk.Label(search_bar)
    match_count.pack(side="left", padx=(12, 0))

    def update_experience_filter() -> None:
        filter_description.set(experience_filter_description(active_experience_filter.get()))
        render_actions()

    experience_bar = ttk.Frame(outer)
    experience_bar.pack(fill="x", pady=(0, 10))
    ttk.Label(experience_bar, text="Explore").pack(side="left")
    for filter_option in EXPERIENCE_FILTERS:
        ttk.Radiobutton(
            experience_bar,
            text=filter_option.label,
            value=filter_option.key,
            variable=active_experience_filter,
            command=update_experience_filter,
        ).pack(side="left", padx=(8, 0))
    ttk.Label(experience_bar, textvariable=filter_description).pack(side="left", padx=(14, 0))

    path_frame = ttk.LabelFrame(outer, text="Recommended learning path", padding=10)
    path_frame.pack(fill="x", pady=(0, 10))
    for column_index in range(3):
        path_frame.columnconfigure(column_index, weight=1)
    path_header = ttk.Frame(path_frame)
    path_header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
    path_header.columnconfigure(0, weight=1)
    ttk.Label(path_header, textvariable=path_summary, wraplength=760, justify="left").grid(
        row=0, column=0, sticky="w"
    )
    next_button = ttk.Button(path_header, text="Run next", command=launch_next_learning_path_step)
    next_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
    next_button_ref["button"] = next_button
    for step_index, step in enumerate(LEARNING_PATH):
        row_index, column_index = divmod(step_index, 3)
        cell = ttk.Frame(path_frame)
        cell.grid(row=row_index + 1, column=column_index, sticky="ew", padx=(0, 12), pady=(0, 8))
        progress_text = tk.StringVar(value=learning_path_progress_text(step))
        path_status_vars.append((step, progress_text))
        ttk.Button(
            cell,
            text=step.title,
            width=22,
            command=lambda selected=step: _launch_learning_path_from_menu(
                selected,
                status,
                root=root,
                latest_output=latest_output,
                latest_button=latest_button,
                progress_callback=refresh_after_run,
            ),
        ).pack(anchor="w")
        ttk.Label(cell, textvariable=progress_text, wraplength=280, justify="left").pack(
            anchor="w", pady=(4, 0)
        )
    refresh_learning_path_progress()

    batch_frame = ttk.LabelFrame(outer, text="Comparison batches", padding=10)
    batch_frame.pack(fill="x", pady=(0, 10))
    for column_index in range(2):
        batch_frame.columnconfigure(column_index, weight=1)
    for action_index, action in enumerate(BATCH_ACTIONS):
        row_index, column_index = divmod(action_index, 2)
        cell = ttk.Frame(batch_frame)
        cell.grid(row=row_index, column=column_index, sticky="ew", padx=(0, 12), pady=(0, 8))
        ttk.Button(
            cell,
            text=action.label,
            width=18,
            command=lambda selected=action: _launch_batch_from_menu(
                selected,
                status,
                root=root,
                latest_output=latest_output,
                latest_button=latest_button,
                progress_callback=refresh_after_run,
            ),
        ).pack(anchor="w")
        ttk.Label(cell, text=lesson_text_for_batch(action), wraplength=360, justify="left").pack(
            anchor="w", pady=(4, 0)
        )

    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)
    scroll_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    bottom = ttk.Frame(outer)
    bottom.pack(fill="x", pady=(12, 0))
    ttk.Button(bottom, text="Refresh path", command=refresh_learning_path_progress).pack(side="left")
    ttk.Button(bottom, text="Check setup", command=lambda: _launch_doctor_from_menu(status, root=root)).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(bottom, text="Open all reports", command=launch_outputs_index).pack(side="left", padx=(8, 0))
    ttk.Button(bottom, text="Open outputs folder", command=launch_outputs_folder).pack(side="left", padx=(8, 0))
    latest_button = ttk.Button(bottom, text="Open latest report", command=lambda: launch_latest_output(latest_output))
    latest_button.pack(side="left", padx=(8, 0))
    latest_button.state(["disabled"])
    ttk.Label(bottom, textvariable=status).pack(side="left", padx=12)

    def render_actions(*_args: Any) -> None:
        for child in scroll_frame.winfo_children():
            child.destroy()

        selected_filter = active_experience_filter.get()
        matched = filter_menu_actions(search.get(), experience_filter=selected_filter)
        filter_label = next(
            (
                filter_option.label
                for filter_option in EXPERIENCE_FILTERS
                if filter_option.key == selected_filter
            ),
            "All",
        )
        match_count.configure(text=f"{filter_label}: {len(matched)} of {len(MENU_ACTIONS)} scenarios")
        if not matched:
            ttk.Label(
                scroll_frame,
                text="No matching scenarios. Try All, PID, noise, wall, 2DOF, or hands-on.",
            ).grid(row=0, column=0, sticky="w", pady=12)
            canvas.configure(scrollregion=canvas.bbox("all"))
            return

        grouped: dict[str, list[MenuAction]] = {}
        for action in matched:
            grouped.setdefault(action.group, []).append(action)

        row = 0
        for group, actions in grouped.items():
            frame = ttk.LabelFrame(scroll_frame, text=group, padding=12)
            frame.grid(row=row, column=0, sticky="ew", pady=6)
            frame.columnconfigure(4, weight=1)
            row += 1
            for action_index, action in enumerate(actions):
                readiness = action_readiness(action)
                latest = action_latest_output(action)
                run_button = ttk.Button(
                    frame,
                    text=action.label,
                    width=16,
                    command=lambda selected=action: _launch_from_menu(
                        selected,
                        status,
                        root=root,
                        latest_output=latest_output,
                        latest_button=latest_button,
                        progress_callback=refresh_after_run,
                    ),
                )
                if readiness.status != "ok":
                    run_button.state(["disabled"])
                run_button.grid(row=action_index, column=0, sticky="w", padx=(0, 12), pady=4)
                ttk.Button(
                    frame,
                    text="Config",
                    width=8,
                    command=lambda selected=action: launch_action_config(selected),
                ).grid(row=action_index, column=1, sticky="w", padx=(0, 6), pady=4)
                ttk.Button(
                    frame,
                    text="Lesson",
                    width=8,
                    command=lambda selected=action: launch_action_doc(selected),
                ).grid(row=action_index, column=2, sticky="w", padx=(0, 6), pady=4)
                report_button = ttk.Button(
                    frame,
                    text="Report",
                    width=8,
                    command=lambda selected=action: launch_action_latest_output(selected),
                )
                if latest is None:
                    report_button.state(["disabled"])
                report_button.grid(row=action_index, column=3, sticky="w", padx=(0, 12), pady=4)
                ttk.Label(frame, text=lesson_text(action), wraplength=560, justify="left").grid(
                    row=action_index, column=4, sticky="w", pady=4
                )
        canvas.configure(scrollregion=canvas.bbox("all"))

    def refresh_progress_and_actions() -> None:
        refresh_learning_path_progress()
        render_actions()

    post_run_refresh_ref["callback"] = refresh_progress_and_actions
    search.trace_add("write", render_actions)
    render_actions()
    search_entry.focus_set()

    root.mainloop()
    return 0


def _launch_learning_path_from_menu(
    step: LearningPathStep,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    action = learning_path_target(step)
    if isinstance(action, BatchMenuAction):
        _launch_batch_from_menu(
            action,
            status,
            root=root,
            latest_output=latest_output,
            latest_button=latest_button,
            progress_callback=progress_callback,
        )
        return
    _launch_from_menu(
        action,
        status,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
        progress_callback=progress_callback,
    )


def _launch_from_menu(
    action: MenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    readiness = action_readiness(action)
    if readiness.status != "ok":
        detail = f" - {readiness.detail}" if readiness.detail else ""
        fix = f" {readiness.fix}" if readiness.fix else ""
        status.set(f"Cannot start {action.group} - {action.label}: {readiness.label}{detail}.{fix}")
        return
    process = launch_action(action)
    status.set(f"Started {action.group} - {action.label} (pid {process.pid}). Close the viewer to finish.")
    Thread(
        target=_watch_process,
        args=(process, action, status),
        kwargs={
            "root": root,
            "latest_output": latest_output,
            "latest_button": latest_button,
            "progress_callback": progress_callback,
        },
        daemon=True,
    ).start()


def _launch_batch_from_menu(
    action: BatchMenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    process = launch_batch_action(action)
    status.set(f"Started {action.group} - {action.label} (pid {process.pid}).")
    Thread(
        target=_watch_process,
        args=(process, action, status),
        kwargs={
            "root": root,
            "latest_output": latest_output,
            "latest_button": latest_button,
            "progress_callback": progress_callback,
        },
        daemon=True,
    ).start()


def _launch_doctor_from_menu(status: Any, *, root: Any | None = None) -> None:
    process = launch_doctor_check()
    status.set(f"Started setup check (pid {process.pid}).")
    Thread(
        target=_watch_doctor_process,
        args=(process, status),
        kwargs={"root": root},
        daemon=True,
    ).start()


def _watch_doctor_process(
    process: subprocess.Popen[str],
    status: Any,
    *,
    root: Any | None = None,
) -> None:
    lines: list[str] = []
    if process.stdout is not None:
        for line in process.stdout:
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return_code = process.wait()
    summary = next((line for line in reversed(lines) if line.startswith("Summary:")), "")
    _set_status_after_doctor(status, return_code, summary, root=root)


def _set_status_after_doctor(
    status: Any,
    return_code: int,
    summary: str = "",
    *,
    root: Any | None = None,
) -> None:
    def update_ui() -> None:
        suffix = f" {summary}" if summary else ""
        if return_code == 0:
            status.set(f"Setup check passed.{suffix}")
            return
        status.set(f"Setup check found issues.{suffix} Run `python -m mclab doctor` for details.")

    if root is not None:
        root.after(0, update_ui)
    else:
        update_ui()


def _watch_process(
    process: subprocess.Popen[str],
    action: MenuAction | BatchMenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    output_path: Path | None = None
    if process.stdout is not None:
        for line in process.stdout:
            parsed = parse_run_output_path(line)
            if parsed is not None:
                output_path = parsed
    return_code = process.wait()
    _set_status_after_run(
        action,
        status,
        return_code,
        output_path,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
        progress_callback=progress_callback,
    )


def _set_status_after_run(
    action: MenuAction | BatchMenuAction,
    status: Any,
    return_code: int,
    output_path: Path | None,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    def update_ui() -> None:
        if return_code == 0:
            if output_path is not None:
                if latest_output is not None:
                    latest_output["path"] = output_path
                if latest_button is not None:
                    latest_button.state(["!disabled"])
                latest = _preferred_output_entry(output_path)
                status.set(f"Completed {action.group} - {action.label}. Latest report: {latest}")
            else:
                status.set(f"Completed {action.group} - {action.label}. Open the outputs folder for results.")
            if progress_callback is not None:
                progress_callback()
            return
        status.set(f"Failed {action.group} - {action.label} with exit code {return_code}.")

    if root is not None:
        root.after(0, update_ui)
    else:
        update_ui()


def lesson_text_for_batch(action: BatchMenuAction) -> str:
    scenario_count = (
        sum(len(scenarios) for scenarios in BATCH_SETS.values())
        if action.batch_name == ALL_BATCH_NAME
        else len(BATCH_SETS[action.batch_name])
    )
    return (
        f"{action.description}\n"
        f"Try: {action.try_this}\n"
        f"Watch: {action.watch}\n"
        f"Runs: {scenario_count} scenarios"
    )
