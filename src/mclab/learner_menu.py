"""Learner-facing launcher menu for local MuJoCo labs."""

from __future__ import annotations

import json
import subprocess
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Thread
from typing import Any

from mclab.batch import ALL_BATCH_NAME, BATCH_SETS
from mclab.config import PROJECT_ROOT, load_config
from mclab.course_progress import course_milestone_summary
from mclab.learning_guides import (
    batch_start_steps_text,
    challenge_prompt_for_guide,
    control_credit_text_for_config,
    guide_for_config,
    playbook_for_guide,
    prediction_prompt_for_guide,
    reflection_question_for_context,
    start_steps_for_guide,
    viewer_legend_for_guide,
)
from mclab.sim.reporting import (
    INDEX_PLOT_PRIORITY,
    _activity_mix_items,
    _challenge_evidence_items,
    _learner_control_event_count,
    _latest_observation_evidence_from_events,
    _observation_flow_text_from_events,
    _observation_next_step_text_from_events,
    _read_config,
    plot_guidance,
    write_outputs_index,
)

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
    evidence_required: bool = False
    observation_markers: int = 0
    learner_predictions: int = 0
    learner_notes: int = 0
    learner_outcomes: int = 0
    learner_controls: int = 0
    required_presets: int = 0
    required_presets_tried: int = 0
    next_required_preset: str = ""


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


BatchMenuStateItem = tuple[BatchMenuAction, Any, Any, Any]
BatchMenuStateItemWithWorksheet = tuple[BatchMenuAction, Any, Any, Any, Any]


EXPERIENCE_FILTERS: tuple[ExperienceFilter, ...] = (
    ExperienceFilter("all", "All", "Show every guided scenario."),
    ExperienceFilter("intro", "Intro", "First-pass demos for 1D dynamics and basic closed-loop control."),
    ExperienceFilter("build", "Build", "Bridge demos that extend the same ideas to arms and Panda motion."),
    ExperienceFilter("deep-dive", "Deep dive", "Advanced singularity, wall, and manipulator behavior."),
    ExperienceFilter("hands-on", "Hands-on", "Live tuning, presets, and disturbance controls."),
    ExperienceFilter("compare", "Compare", "Paired scenarios that make one design tradeoff visible."),
    ExperienceFilter("pid", "PID", "Gain tuning, saturation, windup, noise, and delay."),
    ExperienceFilter("trajectory", "Trajectory", "Step, trapezoid, minimum-jerk, S-curve, and joint paths."),
    ExperienceFilter("2dof", "2DOF", "Two-link arm joint-space, task-space, and singularity demos."),
    ExperienceFilter("panda", "Panda", "Full manipulator joint, Cartesian, and wall demos."),
    ExperienceFilter("wall", "Wall", "Virtual wall stiffness, damping, penetration, and retreat."),
    ExperienceFilter("singularity", "Singularity", "Jacobian conditioning and DLS behavior."),
)

ACTION_BADGE_PRIORITY = (
    "hands-on",
    "compare",
    "pid",
    "2dof",
    "panda",
    "wall",
    "singularity",
    "trajectory",
    "cartesian",
    "tuning",
    "dynamics",
)

ACTION_BADGE_LABELS = {
    "hands-on": "Hands-on",
    "compare": "Compare",
    "pid": "PID",
    "2dof": "2DOF",
    "panda": "Panda",
    "wall": "Wall",
    "singularity": "Singularity",
    "trajectory": "Trajectory",
    "cartesian": "Cartesian",
    "tuning": "Tuning",
    "dynamics": "Dynamics",
}


def experience_filter_description(key: str) -> str:
    normalized = _normalize_filter_key(key)
    for filter_option in EXPERIENCE_FILTERS:
        if filter_option.key == normalized:
            return filter_option.description
    return EXPERIENCE_FILTERS[0].description


def _normalize_filter_key(key: str) -> str:
    return key.lower().strip().replace(" ", "-")


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
        description="Run Panda virtual wall stiffness, damping, wall-position, and retreat-gain cases.",
        try_this="Compare wall penetration, virtual force, retreat, and hand X motion.",
        watch="How wall stiffness, damping, wall position, and retreat gain change the contact-like response.",
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
        title="7. Handle singularity",
        action_kind="run",
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF condition-aware DLS",
        description="Use DLS damping when the arm approaches poor Jacobian conditioning.",
    ),
    LearningPathStep(
        title="8. Hold Panda",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Neutral hold",
        description="Use a stable neutral pose as the full manipulator baseline.",
    ),
    LearningPathStep(
        title="9. Reach in Cartesian",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Cartesian reach",
        description="Move the Panda hand toward an XYZ target before adding wall response.",
    ),
    LearningPathStep(
        title="10. Touch virtual wall",
        action_kind="run",
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        description="Tune wall position, stiffness, damping, and retreat gain.",
    ),
    LearningPathStep(
        title="11. Compare the course",
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
        plots="dls_disturbance",
        description="Damped least-squares limits inverse-Jacobian motion near the workspace edge.",
        try_this="Open with the viewer, try DLS damping presets, then press Shoulder pulse or Elbow pulse.",
        watch="DLS joint speed, hand error, damping, condition number, disturbance, and torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF condition-aware DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_2dof.yaml",
        plots="dls_disturbance",
        description="Automatically increases DLS damping as Jacobian conditioning worsens.",
        try_this="Open with the viewer, try damping schedule presets, then disturb the shoulder or elbow.",
        watch="Condition scale, DLS damping, joint speed, condition number, disturbance, and task error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF early DLS damping",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_early_2dof.yaml",
        plots="dls",
        description="Starts condition-aware damping earlier and allows a higher damping ceiling.",
        try_this="Run before late DLS damping and compare how soon dls_damping rises.",
        watch="Earlier condition scale, lower joint speed demand, and possible task-error tradeoff.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF late DLS damping",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_late_2dof.yaml",
        plots="dls",
        description="Delays condition-aware damping and caps the maximum damping lower.",
        try_this="Compare against early DLS damping on the same near-edge target.",
        watch="Later condition scale, faster joint motion, and hand tracking near the singularity.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF inner-target DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml",
        plots="dls",
        description="Uses the same condition-aware DLS schedule on a comfortable inner-workspace target.",
        try_this="Run before edge-target DLS and compare condition scale.",
        watch="Lower condition scale, small task error, and modest DLS damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF edge-target DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_edge_target_2dof.yaml",
        plots="dls",
        description="Uses the same condition-aware DLS schedule near the workspace edge.",
        try_this="Compare against inner-target DLS with the same controller settings.",
        watch="Higher condition scale, larger DLS damping, and hand-error tradeoff.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF upper-path DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml",
        plots="dls",
        description="Reaches the same near-edge target from the upper hand path and mirrored elbow branch.",
        try_this="Run before lower-path DLS and compare the viewer arm branch.",
        watch="Hand Y motion, elbow torque sign, DLS damping, and task error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF lower-path DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_lower_path_2dof.yaml",
        plots="dls",
        description="Reaches the same near-edge target from the lower hand path and mirrored elbow branch.",
        try_this="Compare directly against upper-path DLS with the same target and damping schedule.",
        watch="Hand Y motion, elbow torque sign, DLS damping, and task error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF shoulder-disturbance DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml",
        plots="dls_disturbance",
        description="Applies a short shoulder torque pulse during the condition-aware DLS reach.",
        try_this="Run before elbow-disturbance DLS and compare disturbance recovery.",
        watch="Shoulder disturbance torque, total torque, task error during the pulse, and DLS damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF elbow-disturbance DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml",
        plots="dls_disturbance",
        description="Applies a short elbow torque pulse during the condition-aware DLS reach.",
        try_this="Compare directly against shoulder-disturbance DLS and the undisturbed reach.",
        watch="Elbow disturbance torque, total torque, task error during the pulse, and DLS damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF staggered-disturbance DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml",
        plots="dls_disturbance",
        description="Applies shoulder and elbow torque pulses at different times during the same near-edge DLS reach.",
        try_this="Compare against the single-joint disturbance runs and inspect the second recovery.",
        watch="Two disturbance windows, total torque, task error after each pulse, and DLS damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF low-torque DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
        plots="dls",
        description="Uses the same condition-aware DLS target but constrains actuator torque.",
        try_this="Run before high-torque DLS and look for torque clipping.",
        watch="Larger task error, clipped shoulder torque, DLS joint speed, and condition number.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF high-torque DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml",
        plots="dls",
        description="Allows more torque for the same condition-aware DLS target and damping schedule.",
        try_this="Compare directly against low-torque DLS on the same near-edge target.",
        watch="Whether task error shrinks and torque peaks grow while the DLS schedule stays similar.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF slow-command DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_slow_command_2dof.yaml",
        plots="dls",
        description="Moves the same near-edge DLS target slowly to reduce task-speed demand.",
        try_this="Run before fast-command DLS and compare dls_task_speed and task error.",
        watch="Lower task speed, DLS joint speed, damping schedule, and final hand error.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF fast-command DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml",
        plots="dls",
        description="Commands the same near-edge DLS target quickly to expose speed limits.",
        try_this="Compare against slow-command DLS with the same target and damping schedule.",
        watch="Task-speed clipping, DLS joint speed, task error, and torque peaks.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF low-joint-speed DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml",
        plots="dls",
        description="Keeps the same near-edge command but tightens the DLS joint-speed limit.",
        try_this="Run before high-joint-speed DLS and compare dls_joint_speed clipping.",
        watch="Lower joint-speed ceiling, larger hand error, and similar condition-aware damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF high-joint-speed DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_high_joint_speed_2dof.yaml",
        plots="dls",
        description="Relaxes the DLS joint-speed limit while keeping target and damping schedule fixed.",
        try_this="Compare directly against low-joint-speed DLS.",
        watch="Higher allowed joint speed, hand tracking, torque, and DLS damping.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF direct-retarget DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_direct_retarget_2dof.yaml",
        plots="dls",
        description="Moves the hand target directly from the start pose to the near-edge DLS target.",
        try_this="Run before inward-retarget DLS and compare target path effects.",
        watch="Condition scale, DLS damping, joint speed, task error, and torque during retargeting.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF inward-retarget DLS",
        lab_name="lab03",
        config_path="configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml",
        plots="dls",
        description="Moves through an inner waypoint before returning to the near-edge DLS target.",
        try_this="Compare directly against direct-retarget DLS with the same controller limits.",
        watch="Whether the detour lowers condition cost or raises command speed and torque.",
    ),
    MenuAction(
        group="Lab03 2DOF Arm and Trajectories",
        label="2DOF interactive",
        lab_name="lab03",
        config_path="configs/lab03_2dof/interactive_2dof.yaml",
        plots="task_disturbance",
        description="Tune the hand target and gains, then disturb the shoulder or elbow live.",
        try_this="Move target X/Y sliders, click a reach preset, then press Shoulder pulse or Elbow pulse.",
        watch="Live status hand position, target marker, error norm, max torque, and disturbance torque.",
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
        label="30s stability hold",
        lab_name="lab04",
        config_path="configs/lab04_panda/neutral_hold_30s.yaml",
        plots="stability",
        description="Hold the Panda neutral pose for a 30-second live-demo stability check.",
        try_this="Run headless first, then inspect velocity, error, and torque plots.",
        watch="Max joint speed, joint drift, final joint error, and actuator effort.",
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
        description="Tune hand target X/Y/Z and nudge Target X live.",
        try_this="Move sliders, click a reach preset, or use Target X -/+ buttons.",
        watch="Live target X nudge, hand error, and end-effector plot after the run.",
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
        label="Low damping wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_low_damping.yaml",
        plots="wall_compare",
        description="Keeps wall stiffness fixed but uses little damping.",
        try_this="Compare against High damping wall to isolate damping effects.",
        watch="Wall force, penetration, retreat, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="High damping wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_high_damping.yaml",
        plots="wall_compare",
        description="Keeps wall stiffness fixed but uses strong damping.",
        try_this="Compare against Low damping wall with the same stiffness and retreat gain.",
        watch="Damping contribution, wall force, penetration, retreat, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Near wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_near.yaml",
        plots="wall_compare",
        description="Moves the same virtual wall closer to the Panda hand path.",
        try_this="Compare against Far wall with stiffness and damping fixed.",
        watch="Earlier contact, larger penetration, stronger retreat, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Far wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_far.yaml",
        plots="wall_compare",
        description="Moves the same virtual wall farther along the hand path.",
        try_this="Compare against Near wall with stiffness and damping fixed.",
        watch="Later contact, smaller penetration, weaker retreat, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Slow approach wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_slow_approach.yaml",
        plots="wall_compare",
        description="Moves toward the same virtual wall slowly.",
        try_this="Run before Fast approach wall with wall settings fixed.",
        watch="Lower hand X speed, damping force, contact duration, and penetration.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Fast approach wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_fast_approach.yaml",
        plots="wall_compare",
        description="Moves toward the same virtual wall quickly.",
        try_this="Compare against Slow approach wall to isolate velocity-dependent damping.",
        watch="Higher hand X speed, damping force, retreat, and actuator effort.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Shallow push wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_shallow_push.yaml",
        plots="wall_compare",
        description="Moves the green hand target just past the same virtual wall for a shallow target-depth test.",
        try_this="Run before Deep push wall and compare target depth, target-wall gap, and penetration.",
        watch="Small target-wall gap, wall contact timing, penetration, force, and retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Deep push wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_deep_push.yaml",
        plots="wall_compare",
        description="Moves the green hand target deeper through the same virtual wall for a target-depth test.",
        try_this="Compare target depth against Shallow push wall with wall stiffness and damping fixed.",
        watch="Larger target-wall gap, hand penetration, wall force, retreat, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Contact cycle wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_contact_cycle.yaml",
        plots="wall_compare",
        description="Moves the hand target through, back out of, and back into the same virtual wall.",
        try_this="Compare against Slow/Fast approach wall to isolate repeated contact and release timing.",
        watch="Target-wall crossing episodes, wall contact episodes, release timing, force, and retreat.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Low retreat wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_low_retreat.yaml",
        plots="wall_compare",
        description="Keeps wall force settings fixed but maps force into a small retreat.",
        try_this="Compare against High retreat wall with stiffness, damping, and wall position fixed.",
        watch="Smaller target retreat, deeper penetration, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="High retreat wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/wall_high_retreat.yaml",
        plots="wall_compare",
        description="Keeps wall force settings fixed but maps force into a stronger retreat.",
        try_this="Compare against Low retreat wall to isolate force-to-retreat gain.",
        watch="Larger target retreat, reduced penetration, and hand X response.",
    ),
    MenuAction(
        group="Lab04 Panda Manipulator",
        label="Virtual wall",
        lab_name="lab04",
        config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
        plots="wall",
        description="Tune hand target and virtual wall response live.",
        try_this="Use Target X + into wall, then try Soft/Stiff/Close wall and Back away presets.",
        watch="Target X nudge, Target-Wall gap, Wall phase, Wall penetration, total/spring/damping force, retreat, and hand X.",
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


def build_tuned_replay_args(action: MenuAction, tuned_config_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "mclab",
        "run",
        action.lab_name,
        "--config",
        str(tuned_config_path),
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


def launch_tuned_replay(action: MenuAction, tuned_config_path: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        build_tuned_replay_args(action, tuned_config_path),
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


def learning_path_completion_text(step: LearningPathStep) -> str:
    action = learning_path_target(step)
    if isinstance(action, BatchMenuAction):
        if action.batch_name == ALL_BATCH_NAME:
            return "Done when: the course comparison report, worksheet, and linked batch Prediction Checks are saved."
        return "Done when: the comparison report, plots, worksheet, and Prediction Check are saved."
    if "hands-on" in action_tags(action):
        required_labels = configured_required_preset_labels(action.config_path)
        if required_labels:
            return (
                "Done when: use at least one button, slider, or preset, then save one Mark observation "
                "with a Prediction and note after required presets: "
                f"{' -> '.join(required_labels)}; add the outcome during review."
            )
        return (
            "Done when: use at least one button, slider, or preset, then save one Mark observation "
            "with a Prediction and note; add the outcome during review."
        )
    return "Done when: the run report, priority plot, and worksheet are saved."


def learning_path_text(step: LearningPathStep) -> str:
    action = learning_path_target(step)
    return (
        f"{step.description}\n"
        f"Run: {action.group} - {action.label}\n"
        f"{action_mission_text(action)}\n"
        f"{learning_path_completion_text(step)}\n"
        f"Watch: {action.watch}"
    )


def learning_path_progress(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> LearningPathProgress:
    latest = learning_path_latest_output(step, outputs_root)
    evidence_required = learning_path_requires_evidence(step)
    events = _read_json_list(latest / "interaction_events.json") if latest is not None else []
    markers, predictions, notes, outcomes = (
        _observation_evidence_counts(latest) if latest is not None else (0, 0, 0, 0)
    )
    learner_controls = _learner_control_event_count(events)
    action = learning_path_target(step)
    required_total, required_tried, next_required = (
        _required_preset_progress_for_action(action, latest) if latest is not None else (0, 0, "")
    )
    required_ready = required_total == 0 or required_tried >= required_total
    if isinstance(action, BatchMenuAction):
        has_worksheet = action_latest_worksheet(action, outputs_root) is not None
        has_plot = action.batch_name == ALL_BATCH_NAME or action_latest_plot(action, outputs_root) is not None
        completed = latest is not None and has_worksheet and has_plot
    else:
        completed = latest is not None and (
            not evidence_required
            or (markers > 0 and predictions > 0 and notes > 0 and learner_controls > 0 and required_ready)
        )
    return LearningPathProgress(
        completed=completed,
        latest_output=latest,
        evidence_required=evidence_required,
        observation_markers=markers,
        learner_predictions=predictions,
        learner_notes=notes,
        learner_outcomes=outcomes,
        learner_controls=learner_controls,
        required_presets=required_total,
        required_presets_tried=required_tried,
        next_required_preset=next_required,
    )


def learning_path_progress_text(
    step: LearningPathStep,
    progress: LearningPathProgress | None = None,
) -> str:
    current = progress if progress is not None else learning_path_progress(step)
    if current.latest_output is None:
        status = "Status: Not run yet"
    elif current.completed:
        status = f"Status: Done - latest {current.latest_output.name}{_learning_path_evidence_suffix(current)}"
        if current.evidence_required and current.learner_predictions > current.learner_outcomes:
            status += ". Add one Prediction outcome while reviewing."
    elif current.observation_markers > 0 and current.learner_predictions == 0:
        status = (
            f"Status: Needs prediction - latest {current.latest_output.name}"
            f"{_learning_path_evidence_suffix(current)}. "
            "Add one Prediction in Mark observation before moving on."
        )
    elif current.required_presets > 0 and current.required_presets_tried < current.required_presets:
        next_text = (
            f"Try required preset {current.next_required_preset} before moving on."
            if current.next_required_preset
            else "Try the remaining required preset before moving on."
        )
        status = (
            f"Status: Needs required preset - latest {current.latest_output.name}"
            f"{_learning_path_evidence_suffix(current)}. {next_text}"
        )
    elif current.observation_markers > 0 and current.learner_notes == 0:
        status = (
            f"Status: Needs note - latest {current.latest_output.name}"
            f"{_learning_path_evidence_suffix(current)}. "
            "Add a short note or Use live status before moving on."
        )
    elif current.evidence_required and current.observation_markers > 0 and current.learner_controls <= 0:
        status = (
            f"Status: Needs learner control - latest {current.latest_output.name}"
            f"{_learning_path_evidence_suffix(current)}. "
            "Use one button, slider, or preset before moving on."
        )
    else:
        status = (
            f"Status: Needs observation - latest {current.latest_output.name}. "
            "Add one Mark observation entry before moving on."
        )
    return f"{learning_path_text(step)}\n{status}"


def _learning_path_evidence_suffix(progress: LearningPathProgress) -> str:
    if progress.observation_markers <= 0:
        return ""
    prediction_text = (
        f", {progress.learner_predictions} prediction{'s' if progress.learner_predictions != 1 else ''}"
        if progress.learner_predictions
        else ""
    )
    note_text = (
        f", {progress.learner_notes} note{'s' if progress.learner_notes != 1 else ''}"
        if progress.learner_notes
        else ""
    )
    outcome_text = (
        f", {progress.learner_outcomes} outcome{'s' if progress.learner_outcomes != 1 else ''}"
        if progress.learner_outcomes
        else ""
    )
    control_text = (
        f", {progress.learner_controls} control{'s' if progress.learner_controls != 1 else ''}"
        if progress.evidence_required
        else ""
    )
    preset_text = (
        f", required presets {progress.required_presets_tried}/{progress.required_presets}"
        if progress.required_presets
        else ""
    )
    return (
        f" ({progress.observation_markers} observation"
        f"{'s' if progress.observation_markers != 1 else ''}{prediction_text}{outcome_text}{note_text}"
        f"{control_text}{preset_text})"
    )


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
    evidence_pending = sum(
        1
        for _step, progress in items
        if progress.latest_output is not None and progress.evidence_required and not progress.completed
    )
    outcome_pending = sum(
        1
        for _step, progress in items
        if progress.latest_output is not None
        and progress.evidence_required
        and progress.learner_predictions > progress.learner_outcomes
    )
    next_step = next_learning_path_step(items)
    if next_step is None:
        outcome_text = f" Outcome review pending: {outcome_pending} hands-on step(s)." if outcome_pending else ""
        review_text = (
            " Next review: add missing Prediction outcome(s), then open All reports."
            if outcome_pending
            else " Course path complete - open All reports to review."
        )
        return f"Progress: {completed}/{total} complete.{outcome_text}{review_text}"
    evidence_text = f" Evidence pending: {evidence_pending} hands-on step(s)." if evidence_pending else ""
    outcome_text = f" Outcome review pending: {outcome_pending} hands-on step(s)." if outcome_pending else ""
    description = next_step.description.rstrip(".")
    return (
        f"Progress: {completed}/{total} complete.{evidence_text}{outcome_text} "
        f"Next: {next_step.title} - {description}. {_learning_path_next_action_text(next_step)}"
    )


def learning_path_milestone_text(
    progress_items: tuple[LearningPathProgressItem, ...] | None = None,
) -> str:
    items = progress_items if progress_items is not None else learning_path_progress_items()
    return course_milestone_summary(tuple(progress.completed for _step, progress in items))


def _learning_path_next_action_text(step: LearningPathStep) -> str:
    action = learning_path_target(step)
    if isinstance(action, BatchMenuAction):
        return (
            f"Next action: run {action.group} - {action.label}. "
            f"{_short_text(learning_path_completion_text(step), 92)} "
            f"Compare: {_short_text(action.try_this, 88)} Watch: {_short_text(action.watch, 88)}"
        )
    prompt = prediction_prompt(action).removeprefix("Prediction:").strip()
    if not prompt:
        prompt = f"Before running, predict how {action.watch} will change."
    return (
        f"Next action: run {action.group} - {action.label}. "
        f"{_short_text(learning_path_completion_text(step), 92)} "
        f"Predict: {_short_text(prompt, 112)} Watch: {_short_text(action.watch, 88)}"
    )


def learning_path_latest_output(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> Path | None:
    return action_latest_output(learning_path_target(step), outputs_root)


def learning_path_latest_worksheet(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> Path | None:
    return action_latest_worksheet(learning_path_target(step), outputs_root)


def learning_path_requires_evidence(step: LearningPathStep) -> bool:
    action = learning_path_target(step)
    return isinstance(action, MenuAction) and "hands-on" in action_tags(action)


def launch_learning_path_latest_output(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    latest = learning_path_latest_output(step, outputs_root)
    if latest is None:
        return None
    return open_path(_preferred_output_entry(latest))


def launch_learning_path_latest_plot(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    latest_plot = learning_path_latest_plot(step, outputs_root)
    if latest_plot is None:
        return None
    return open_path(latest_plot)


def launch_learning_path_latest_worksheet(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    worksheet = learning_path_latest_worksheet(step, outputs_root)
    if worksheet is None:
        return None
    return open_path(worksheet)


def learning_path_latest_tuned_config(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> Path | None:
    target = learning_path_target(step)
    if not isinstance(target, MenuAction):
        return None
    return action_latest_tuned_config(target, outputs_root)


def action_latest_output(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> Path | None:
    root = outputs_root if outputs_root is not None else PROJECT_ROOT / "outputs"
    return _latest_matching_output(action, root)


def action_latest_plot(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> Path | None:
    return latest_output_plot(action_latest_output(action, outputs_root))


def action_latest_worksheet(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> Path | None:
    return latest_output_worksheet(action_latest_output(action, outputs_root))


def action_latest_tuned_config(action: MenuAction, outputs_root: Path | None = None) -> Path | None:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return None
    tuned = latest / "learner_tuned_config.yaml"
    return tuned if tuned.exists() else None


def learning_path_latest_plot(
    step: LearningPathStep,
    outputs_root: Path | None = None,
) -> Path | None:
    return action_latest_plot(learning_path_target(step), outputs_root)


def action_history_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "History: Not run yet"
    return f"History: Latest {latest.name}"


def action_evidence_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Evidence: No observation markers yet"
    markers, predictions, notes, outcomes = _observation_evidence_counts(latest)
    if markers == 0:
        return "Evidence: No observation markers yet"
    prediction_text = f", {predictions} prediction{'s' if predictions != 1 else ''}"
    outcome_text = f", {outcomes} outcome{'s' if outcomes != 1 else ''}" if outcomes else ""
    note_text = f", {notes} note{'s' if notes != 1 else ''}" if notes else ""
    review_text = "; outcome review pending" if predictions > outcomes else ""
    return (
        f"Evidence: {markers} observation{'s' if markers != 1 else ''}"
        f"{prediction_text}{outcome_text}{note_text}{review_text}"
    )


def action_latest_evidence_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Latest evidence: None yet"
    evidence = _latest_observation_evidence_from_events(_read_json_list(latest / "interaction_events.json"))
    if not evidence:
        return "Latest evidence: None yet"
    if evidence == "marker saved without details":
        return "Latest evidence: Observation marker saved without details"
    if evidence == "marker saved without prediction or note":
        return "Latest evidence: Observation marker saved without prediction or note"
    return f"Latest evidence: {evidence}"


def action_observation_flow_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return ""
    return _observation_flow_text_from_events(_read_json_list(latest / "interaction_events.json"))


def action_observation_next_step_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    evidence_required = isinstance(action, MenuAction) and "hands-on" in action_tags(action)
    if latest is None:
        if evidence_required:
            return _observation_next_step_text_from_events([], evidence_required=True)
        return ""
    return _observation_next_step_text_from_events(
        _read_json_list(latest / "interaction_events.json"),
        evidence_required=evidence_required,
    )


def action_mission_evidence_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Mission evidence: Not run yet"

    events = _read_json_list(latest / "interaction_events.json")
    learner_controls = _learner_control_event_count(events)
    markers, predictions, notes, outcomes = _observation_evidence_counts(latest)

    if isinstance(action, MenuAction) and "hands-on" in action_tags(action):
        required_total, required_tried, next_required = _required_preset_progress_for_action(action, latest)
        if markers <= 0:
            status = "Needs observation"
        elif predictions <= 0:
            status = "Needs prediction"
        elif required_total and required_tried < required_total:
            status = f"Needs required preset {next_required}" if next_required else "Needs required preset"
        elif notes <= 0:
            status = "Ready; add note next"
        elif learner_controls <= 0:
            status = "Needs learner control"
        elif predictions > outcomes:
            status = "Outcome review pending"
        else:
            status = "Ready for review"
        preset_text = _required_preset_progress_text(required_total, required_tried)
        return (
            f"Mission evidence: {status}; "
            f"{_mission_evidence_counts(markers, predictions, outcomes, notes, learner_controls)}{preset_text}"
        )

    if predictions > outcomes:
        return f"Mission evidence: Outcome review pending; {_mission_evidence_counts(markers, predictions, outcomes, notes)}"

    if isinstance(action, BatchMenuAction) and action.batch_name == ALL_BATCH_NAME:
        worksheet = action_latest_worksheet(action, outputs_root)
        if worksheet is None:
            return "Mission evidence: Needs worksheet; rerun all batches to regenerate course review artifacts"
        return f"Mission evidence: Course artifacts ready; worksheet {worksheet.name}"

    plot = action_latest_plot(action, outputs_root)
    worksheet = action_latest_worksheet(action, outputs_root)
    if plot is None:
        return "Mission evidence: Needs plot; rerun with plots enabled"
    if worksheet is None:
        return "Mission evidence: Needs worksheet; rerun or regenerate review artifacts"
    return f"Mission evidence: Artifacts ready; plot {plot.name}; worksheet {worksheet.name}"


def action_challenge_evidence_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Challenge evidence: Not run yet"

    summary = _read_json(latest / "summary.json")
    if not summary:
        summary = _summary_for_action(action)

    if isinstance(action, BatchMenuAction) and action.batch_name == ALL_BATCH_NAME:
        worksheet = action_latest_worksheet(action, outputs_root)
        if worksheet is None:
            return "Challenge evidence: Needs worksheet evidence; rerun all batches to regenerate course review artifacts"
        return "Challenge evidence: Ready to review; source course worksheet; compare linked batch Prediction Checks"

    events = _read_json_list(latest / "interaction_events.json")
    config = _config_for_action(action, latest)
    plots = _challenge_plot_inputs(action, outputs_root)
    items = dict(_challenge_evidence_items(summary, events, plots, config))
    status = str(items.get("Challenge status") or "").strip()
    source = str(items.get("Proof source") or "").strip()
    next_step = str(items.get("Next challenge step") or "").strip()
    details = []
    if source:
        details.append(f"source {source}")
    if next_step:
        details.append(_short_menu_text(next_step, max_length=96))
    suffix = f"; {'; '.join(details)}" if details else ""
    return f"Challenge evidence: {status or 'Needs evidence'}{suffix}"


def _summary_for_action(action: MenuAction | BatchMenuAction) -> dict[str, Any]:
    if isinstance(action, BatchMenuAction):
        return {
            "lab_name": "batch_group",
            "batch_name": action.batch_name,
            "config_name": action.batch_name,
        }
    return {
        "lab_name": action.lab_name,
        "config_path": action.config_path,
        "config_name": Path(action.config_path).stem,
    }


def _config_for_action(action: MenuAction | BatchMenuAction, latest: Path) -> dict[str, Any]:
    config = _read_config(latest / "config.yaml")
    if config:
        return config
    if isinstance(action, MenuAction):
        return _loaded_action_config(action.config_path)
    return {}


def _challenge_plot_inputs(action: MenuAction | BatchMenuAction, outputs_root: Path | None = None) -> list[Path]:
    plot = action_latest_plot(action, outputs_root)
    return [plot] if plot is not None else []


def _short_menu_text(text: str, *, max_length: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3].rstrip()}..."


def _mission_evidence_counts(
    markers: int,
    predictions: int,
    outcomes: int,
    notes: int,
    learner_controls: int | None = None,
) -> str:
    control_text = (
        f", {learner_controls} control{'s' if learner_controls != 1 else ''}"
        if learner_controls is not None
        else ""
    )
    return (
        f"{markers} observation{'s' if markers != 1 else ''}, "
        f"{predictions} prediction{'s' if predictions != 1 else ''}, "
        f"{outcomes} outcome{'s' if outcomes != 1 else ''}, "
        f"{notes} note{'s' if notes != 1 else ''}"
        f"{control_text}"
    )


def _required_preset_progress_text(required_total: int, required_tried: int) -> str:
    if required_total <= 0:
        return ""
    return f"; required presets {required_tried}/{required_total}"


def review_queue_summary_text(outputs_root: Path | None = None) -> str:
    root = outputs_root if outputs_root is not None else PROJECT_ROOT / "outputs"
    items = _review_queue_items(root)
    if not items:
        return "Review queue: No saved runs yet. Run a scenario first."

    counts = _review_queue_counts(items)
    ready = counts.get("ready", 0)
    pending = len(items) - ready
    gap_text = (
        f"Needs observation: {counts.get('observation', 0)}; "
        f"prediction: {counts.get('prediction', 0)}; "
        f"outcome: {counts.get('outcome', 0)}; "
        f"required preset: {counts.get('preset', 0)}; "
        f"note: {counts.get('note', 0)}; "
        f"control: {counts.get('control', 0)}; "
        f"artifact: {counts.get('artifact', 0)}."
    )
    next_item = _next_review_queue_item(items)
    if next_item is None:
        next_text = "Next review: all saved mission evidence is ready."
    else:
        next_text = f"Next review: {next_item[0].name} - {next_item[1]}."
    return f"Review queue: {ready} ready, {pending} pending. {gap_text} {next_text}"


def next_review_output(outputs_root: Path | None = None) -> Path | None:
    root = outputs_root if outputs_root is not None else PROJECT_ROOT / "outputs"
    next_item = _next_review_queue_item(_review_queue_items(root))
    return next_item[0] if next_item is not None else None


def _review_queue_items(outputs_root: Path) -> list[tuple[Path, str, str, float]]:
    if not outputs_root.exists():
        return []
    items = []
    for output_path, summary, modified in _iter_output_summaries(outputs_root):
        status = _review_queue_status(output_path, summary)
        items.append((output_path, status, _review_queue_bucket(status), modified))
    return sorted(items, key=lambda item: item[3], reverse=True)


def _review_queue_status(output_path: Path, summary: dict[str, Any]) -> str:
    markers, predictions, notes, outcomes = _observation_evidence_counts(output_path)

    if _summary_requires_hands_on_evidence(summary):
        if markers <= 0:
            return "Needs observation"
        if predictions <= 0:
            return "Needs prediction"
        required_total, required_tried, next_required = _required_preset_progress_for_summary(summary, output_path)
        if required_total and required_tried < required_total:
            return f"Needs required preset {next_required}" if next_required else "Needs required preset"
        if notes <= 0:
            return "Ready; add note next"
        if _learner_control_event_count(_read_json_list(output_path / "interaction_events.json")) <= 0:
            return "Needs learner control"
        if predictions > outcomes:
            return "Outcome review pending"
        return "Ready for review"

    if predictions > outcomes:
        return "Outcome review pending"

    if _summary_is_all_batch(summary):
        return "Artifacts ready" if (output_path / "worksheet.md").exists() else "Needs worksheet"

    if latest_output_plot(output_path) is None:
        return "Needs plot"
    if latest_output_worksheet(output_path) is None:
        return "Needs worksheet"
    return "Artifacts ready"


def _summary_is_all_batch(summary: dict[str, Any]) -> bool:
    batch_name = str(summary.get("batch_name") or summary.get("config_name") or "").strip()
    return batch_name == ALL_BATCH_NAME


def _summary_requires_hands_on_evidence(summary: dict[str, Any]) -> bool:
    config_text = " ".join(str(summary.get(name) or "") for name in ("config_path", "config_name")).lower()
    return "interactive" in config_text


def _required_preset_progress_for_summary(summary: dict[str, Any], output_path: Path) -> tuple[int, int, str]:
    config_path = str(summary.get("config_path") or "").strip()
    if not config_path:
        return 0, 0, ""
    required_labels = list(configured_required_preset_labels(config_path))
    if not required_labels:
        return 0, 0, ""
    labels = list(configured_preset_labels(config_path))
    tried_required, next_required = _ordered_required_preset_progress(
        required_labels,
        _preset_event_labels(output_path, labels),
    )
    return len(required_labels), len(tried_required), next_required


def _review_queue_bucket(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"ready for review", "artifacts ready"}:
        return "ready"
    if normalized == "outcome review pending":
        return "outcome"
    if normalized == "needs observation":
        return "observation"
    if normalized == "needs prediction":
        return "prediction"
    if normalized.startswith("needs required preset"):
        return "preset"
    if normalized == "ready; add note next":
        return "note"
    if normalized == "needs learner control":
        return "control"
    if normalized in {"needs plot", "needs worksheet"}:
        return "artifact"
    return "other"


def _review_queue_counts(items: list[tuple[Path, str, str, float]]) -> dict[str, int]:
    counts = {
        key: 0
        for key in ("ready", "observation", "prediction", "outcome", "preset", "note", "control", "artifact", "other")
    }
    for _path, _status, bucket, _modified in items:
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _next_review_queue_item(items: list[tuple[Path, str, str, float]]) -> tuple[Path, str, str, float] | None:
    priority = ("outcome", "observation", "prediction", "preset", "note", "control", "artifact", "other")
    for bucket in priority:
        for item in items:
            if item[2] == bucket:
                return item
    return None


def action_preset_evidence_text(action: MenuAction, outputs_root: Path | None = None) -> str:
    labels = list(configured_preset_labels(action.config_path))
    if len(labels) < 2:
        return ""
    required_labels = list(configured_required_preset_labels(action.config_path))
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Preset evidence: Not run yet"
    tried = _distinct_preset_labels(latest, labels)
    count = f"{len(tried)}/{len(labels)}"
    if required_labels:
        required_tried, next_required = _ordered_required_preset_progress(
            required_labels,
            _preset_event_labels(latest, labels),
        )
        if not next_required:
            return f"Preset evidence: {count} presets tried; required presets ready"
        remaining = " -> ".join(required_labels[len(required_tried) :])
        return f"Preset evidence: {count} presets tried; required next {next_required}; remaining {remaining}"
    next_label = next((label for label in labels if label not in tried), "")
    if len(tried) >= 2:
        return f"Preset evidence: {count} presets tried; ready to review comparison"
    if next_label:
        return f"Preset evidence: {count} presets tried; next {next_label}"
    return f"Preset evidence: {count} presets tried; try one more preset"


def action_activity_mix_text(action: MenuAction, outputs_root: Path | None = None) -> str:
    if "hands-on" not in action_tags(action):
        return ""
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Activity mix: Not run yet"
    items = dict(_activity_mix_items(_read_json_list(latest / "interaction_events.json"), _loaded_action_config(action.config_path)))
    if not items:
        return "Activity mix: No learner controls yet"
    path = str(items.get("Activity path") or "").strip()
    path_text = f"; path {_short_text(path, 96)}" if path and path != "none" else ""
    return (
        f"Activity mix: {items.get('Interaction variety')}; "
        f"buttons {items.get('Button actions')}, sliders {items.get('Slider changes')}, "
        f"presets {items.get('Preset choices')}, markers {items.get('Observation markers')}; "
        f"next {_short_text(str(items.get('Next activity step') or ''), 80)}"
        f"{path_text}"
    )


def _required_preset_progress_for_action(
    action: MenuAction | BatchMenuAction,
    output_path: Path | None,
) -> tuple[int, int, str]:
    if not isinstance(action, MenuAction) or output_path is None:
        return 0, 0, ""
    required_labels = list(configured_required_preset_labels(action.config_path))
    if not required_labels:
        return 0, 0, ""
    labels = list(configured_preset_labels(action.config_path))
    tried_required, next_required = _ordered_required_preset_progress(
        required_labels,
        _preset_event_labels(output_path, labels),
    )
    return len(required_labels), len(tried_required), next_required


def action_next_cue_text(action: MenuAction, outputs_root: Path | None = None) -> str:
    readiness = action_readiness(action)
    if readiness.status != "ok":
        fix = f" {readiness.fix}" if readiness.fix else ""
        return f"Next cue: Fix setup first - {readiness.label}.{fix}"

    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Next cue: Run this scenario, then review the saved plot and worksheet."

    markers, predictions, notes, outcomes = _observation_evidence_counts(latest)
    if predictions > outcomes:
        return "Next cue: Review latest evidence and choose the missing prediction outcome."

    labels = list(configured_preset_labels(action.config_path))
    if len(labels) >= 2:
        tried = _distinct_preset_labels(latest, labels)
        required_labels = list(configured_required_preset_labels(action.config_path))
        if required_labels:
            _required_tried, next_required = _ordered_required_preset_progress(
                required_labels,
                _preset_event_labels(latest, labels),
            )
            if next_required:
                return f"Next cue: Try required preset {next_required}, then mark a comparison observation."
        elif len(tried) < 2:
            next_label = next((label for label in labels if label not in tried), "")
            preset_text = f"preset {next_label}" if next_label else "one more preset"
            return f"Next cue: Try {preset_text}, then mark a comparison observation."

    hands_on = "hands-on" in action_tags(action)
    if hands_on and markers == 0:
        return "Next cue: Change one control and Mark observation with a prediction."
    if hands_on and predictions == 0:
        return "Next cue: Add a prediction before marking the next observation."
    if hands_on and notes == 0:
        return "Next cue: Add a short note or Use live status before moving on."

    if action_latest_tuned_config(action, outputs_root) is not None:
        return "Next cue: Replay the tuned config, then run Compare for the broader tradeoff."

    if action_latest_plot(action, outputs_root) is None:
        return "Next cue: Re-run with plots, then inspect the priority graph."
    if action_latest_worksheet(action, outputs_root) is None:
        return "Next cue: Re-run or regenerate the worksheet before moving on."
    return "Next cue: Review the latest plot and worksheet, then run Next or Compare."


def action_plot_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest_plot = action_latest_plot(action, outputs_root)
    if latest_plot is None:
        return "Plots: Not saved yet"
    return f"Plots: Latest {latest_plot.name}"


def action_plot_review_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest_plot = action_latest_plot(action, outputs_root)
    if latest_plot is None:
        return "Plot review: Not available until a plot is saved"
    guidance = plot_guidance(latest_plot.name)
    if guidance is None:
        return "Plot review: Open the latest plot and compare it with the worksheet"
    title, detail = guidance
    return f"Plot review: {title} - {detail}"


def action_worksheet_text(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    worksheet = action_latest_worksheet(action, outputs_root)
    if worksheet is None:
        return "Worksheet: Not saved yet"
    return f"Worksheet: Latest {worksheet.name}"


def batch_prediction_check_text(
    action: BatchMenuAction,
    outputs_root: Path | None = None,
) -> str:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return "Prediction check: Write a prediction before running the batch."
    worksheet = action_latest_worksheet(action, outputs_root)
    if worksheet is None:
        return "Prediction check: Not saved yet; rerun or regenerate the worksheet."
    try:
        text = worksheet.read_text(encoding="utf-8")
    except OSError:
        return "Prediction check: Worksheet unreadable; open the batch report instead."
    if "## Prediction Check" in text:
        return "Prediction check: Ready in worksheet; mark Matched, Partly matched, or Surprised."
    return "Prediction check: Worksheet saved; use the comparison notes to judge your prediction."


def action_replay_text(action: MenuAction, outputs_root: Path | None = None) -> str:
    tuned_config = action_latest_tuned_config(action, outputs_root)
    if tuned_config is None:
        return "Replay: No tuned config yet"
    return f"Replay: Latest {tuned_config.name}"


def refresh_batch_menu_state(
    items: tuple[BatchMenuStateItem | BatchMenuStateItemWithWorksheet, ...],
    outputs_root: Path | None = None,
) -> None:
    for item in items:
        action, text_variable, report_button, plot_button = item[:4]
        worksheet_button = item[4] if len(item) > 4 else None
        text_variable.set(lesson_text_for_batch(action, outputs_root))
        report_button.state(
            ["!disabled"] if action_latest_output(action, outputs_root) is not None else ["disabled"]
        )
        plot_button.state(["!disabled"] if action_latest_plot(action, outputs_root) is not None else ["disabled"])
        if worksheet_button is not None:
            worksheet_button.state(
                ["!disabled"] if action_latest_worksheet(action, outputs_root) is not None else ["disabled"]
            )


def action_followup(action: MenuAction) -> MenuAction | BatchMenuAction:
    for index, candidate in enumerate(MENU_ACTIONS):
        if candidate == action:
            if index + 1 < len(MENU_ACTIONS):
                return MENU_ACTIONS[index + 1]
            return BATCH_ACTIONS[0]
    raise ValueError(f"Menu action was not found: {action.group} - {action.label}")


def action_followup_text(action: MenuAction) -> str:
    target = action_followup(action)
    return f"Next: {target.group} - {target.label}"


def action_compare_batch(action: MenuAction) -> BatchMenuAction:
    if action.lab_name == "lab01":
        return _batch_action_by_name("lab01_msd_compare")
    if action.lab_name == "lab02":
        return _batch_action_by_name("lab02_pid_compare")
    if action.lab_name == "lab03":
        return _batch_action_by_name("lab03_2dof_compare")
    if action.lab_name == "lab04":
        action_text = f"{action.label} {action.config_path}".lower()
        if "wall" in action_text:
            return _batch_action_by_name("lab04_wall_compare")
        return _batch_action_by_name("lab04_cartesian_compare")
    return _batch_action_by_name(ALL_BATCH_NAME)


def action_compare_text(action: MenuAction) -> str:
    target = action_compare_batch(action)
    return f"Compare: {target.group} - {target.label}"


def _batch_action_by_name(batch_name: str) -> BatchMenuAction:
    for action in BATCH_ACTIONS:
        if action.batch_name == batch_name:
            return action
    raise ValueError(f"Batch action was not found: {batch_name}")


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


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _observation_evidence_counts(output_path: Path) -> tuple[int, int, int, int]:
    markers = 0
    predictions = 0
    notes = 0
    outcomes = 0
    for event in _read_json_list(output_path / "interaction_events.json"):
        if not _is_observation_marker_event(event):
            continue
        markers += 1
        value = event.get("value")
        if not isinstance(value, dict):
            continue
        if str(value.get("prediction") or "").strip():
            predictions += 1
        if str(value.get("outcome") or "").strip():
            outcomes += 1
        if str(value.get("note") or "").strip():
            notes += 1
    return markers, predictions, notes, outcomes


def _latest_observation_marker(output_path: Path) -> dict[str, Any] | None:
    for event in reversed(_read_json_list(output_path / "interaction_events.json")):
        if _is_observation_marker_event(event):
            return event
    return None


def _distinct_preset_labels(output_path: Path, configured_labels: list[str]) -> list[str]:
    seen: list[str] = []
    for canonical in _preset_event_labels(output_path, configured_labels):
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen


def _preset_event_labels(output_path: Path, configured_labels: list[str]) -> list[str]:
    configured_lookup = {label.lower(): label for label in configured_labels}
    labels: list[str] = []
    for event in _read_json_list(output_path / "interaction_events.json"):
        if str(event.get("kind", "")).lower() != "preset":
            continue
        label = str(event.get("label") or event.get("name") or "").strip()
        canonical = configured_lookup.get(label.lower())
        if canonical:
            labels.append(canonical)
    return labels


def _ordered_required_preset_progress(
    required_labels: Sequence[str],
    attempted_labels: Sequence[str],
) -> tuple[list[str], str]:
    tried: list[str] = []
    index = 0
    for label in attempted_labels:
        if index >= len(required_labels):
            break
        if label == required_labels[index]:
            tried.append(label)
            index += 1
    next_required = required_labels[index] if index < len(required_labels) else ""
    return tried, next_required


def _is_observation_marker_event(event: dict[str, Any]) -> bool:
    return str(event.get("kind", "")).lower() == "marker" and str(event.get("name", "")).lower() == "observation"


def _short_text(value: str, limit: int = 96) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _short_sentence(value: str, limit: int = 96) -> str:
    text = _short_text(value, limit)
    if text.endswith("..."):
        return text
    return text.removesuffix(".")


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


def batch_readiness(action: BatchMenuAction, root: Path | None = None) -> ActionReadiness:
    project_root = root if root is not None else PROJECT_ROOT
    return _batch_readiness(action.batch_name, str(project_root))


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


@lru_cache(maxsize=64)
def _batch_readiness(batch_name: str, root: str) -> ActionReadiness:
    if batch_name == ALL_BATCH_NAME:
        scenarios = tuple(scenario for name in sorted(BATCH_SETS) for scenario in BATCH_SETS[name])
    else:
        scenarios = BATCH_SETS.get(batch_name)
        if scenarios is None:
            return ActionReadiness(
                "fail",
                "Unknown batch",
                batch_name,
                "Choose another comparison batch.",
            )

    failures: list[str] = []
    first_fix = ""
    for scenario in scenarios:
        readiness = _action_readiness(scenario.config_path, root)
        if readiness.status == "ok":
            continue
        detail = readiness.detail or scenario.config_path
        failures.append(f"{scenario.label}: {readiness.label} - {detail}")
        if not first_fix and readiness.fix:
            first_fix = readiness.fix
    if failures:
        visible = "; ".join(failures[:2])
        suffix = f"; +{len(failures) - 2} more" if len(failures) > 2 else ""
        return ActionReadiness(
            "fail",
            "Batch not ready",
            f"{visible}{suffix}",
            first_fix or "Run Check setup for diagnosis.",
        )
    return ActionReadiness("ok", "Ready", f"{len(scenarios)} scenarios")


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
    write_outputs_index(outputs)
    return open_path(index)


def launch_next_review_output(outputs_root: Path | None = None) -> subprocess.Popen[Any] | None:
    output_path = next_review_output(outputs_root)
    if output_path is None:
        return None
    return open_path(_preferred_output_entry(output_path))


def launch_latest_output(latest_output: dict[str, Path | None]) -> subprocess.Popen[Any] | None:
    path = latest_output.get("path")
    if path is None:
        return None
    return open_path(_preferred_output_entry(path))


def launch_latest_plot(latest_output: dict[str, Path | None]) -> subprocess.Popen[Any] | None:
    path = latest_output_plot(latest_output.get("path"))
    if path is None:
        return None
    return open_path(path)


def launch_latest_worksheet(latest_output: dict[str, Path | None]) -> subprocess.Popen[Any] | None:
    path = latest_output_worksheet(latest_output.get("path"))
    if path is None:
        return None
    return open_path(path)


def launch_action_latest_output(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    latest = action_latest_output(action, outputs_root)
    if latest is None:
        return None
    return open_path(_preferred_output_entry(latest))


def launch_action_latest_plot(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    latest_plot = action_latest_plot(action, outputs_root)
    if latest_plot is None:
        return None
    return open_path(latest_plot)


def launch_action_latest_worksheet(
    action: MenuAction | BatchMenuAction,
    outputs_root: Path | None = None,
) -> subprocess.Popen[Any] | None:
    worksheet = action_latest_worksheet(action, outputs_root)
    if worksheet is None:
        return None
    return open_path(worksheet)


def _preferred_output_entry(path: Path) -> Path:
    report = path / "report.html"
    if report.exists():
        return report
    index = path / "index.html"
    if index.exists():
        return index
    return path


def latest_output_plot(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidates: list[Path] = []
    for directory_name in ("plots", "comparison_plots"):
        plot_dir = path / directory_name
        if plot_dir.exists():
            candidates.extend(plot_dir.glob("*.png"))
    if not candidates:
        return None
    return sorted(candidates, key=_plot_sort_key)[0]


def latest_output_worksheet(path: Path | None) -> Path | None:
    if path is None:
        return None
    worksheet = path / "worksheet.md"
    return worksheet if worksheet.exists() else None


def _plot_sort_key(plot: Path) -> tuple[int, str]:
    name = plot.stem.lower().replace("-", "_").removesuffix("_compare")
    for index, priority in enumerate(INDEX_PLOT_PRIORITY):
        if name == priority or name.startswith(f"{priority}_") or name.endswith(f"_{priority}"):
            return index, name
    return len(INDEX_PLOT_PRIORITY), name


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
                "buttons: Shoulder/Elbow pulse; YAML: target_xy, interaction.joint_disturbance_torque, "
                "tracking_controller.task_kp, tracking_controller.task_kd, tracking_controller.torque_limit"
            )
        if label == "2dof dls singularity":
            return (
                "live sliders/presets: Target X/Y, DLS task gain, DLS damping, torque limit; "
                "YAML: target_xy, tracking_controller.dls_gain, tracking_controller.dls_damping, "
                "viewer_guides.condition_threshold"
            )
        if label in {
            "2dof condition-aware dls",
            "2dof early dls damping",
            "2dof late dls damping",
            "2dof inner-target dls",
            "2dof edge-target dls",
            "2dof upper-path dls",
            "2dof lower-path dls",
            "2dof shoulder-disturbance dls",
            "2dof elbow-disturbance dls",
            "2dof staggered-disturbance dls",
            "2dof low-torque dls",
            "2dof high-torque dls",
            "2dof slow-command dls",
            "2dof fast-command dls",
            "2dof low-joint-speed dls",
            "2dof high-joint-speed dls",
            "2dof direct-retarget dls",
            "2dof inward-retarget dls",
        }:
            if label == "2dof condition-aware dls":
                return (
                    "live sliders/presets: Target X/Y, DLS task gain, DLS damping, condition threshold/full, "
                    "max DLS damping, torque limit; buttons: Shoulder/Elbow pulse; "
                    "YAML: target_xy, interaction.joint_disturbance_torque, tracking_controller.condition_damping_threshold, "
                    "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
                )
            if label in {"2dof low-torque dls", "2dof high-torque dls"}:
                return (
                    "target_xy, tracking_controller.torque_limit, tracking_controller.condition_damping_threshold, "
                    "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
                )
            if label in {"2dof inner-target dls", "2dof edge-target dls"}:
                return (
                    "target_xy, tracking_controller.condition_damping_threshold, "
                    "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
                )
            if label in {"2dof upper-path dls", "2dof lower-path dls"}:
                return (
                    "initial_q, target_xy, tracking_controller.condition_damping_threshold, "
                    "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
                )
            if label in {"2dof shoulder-disturbance dls", "2dof elbow-disturbance dls"}:
                return (
                    "disturbance_torque.start_time, disturbance_torque.duration, disturbance_torque.torque, "
                    "target_xy, tracking_controller.condition_damping_threshold"
                )
            if label == "2dof staggered-disturbance dls":
                return (
                    "disturbance_torque.pulses, disturbance_torque.duration, disturbance_torque.ramp_time, "
                    "target_xy, tracking_controller.condition_damping_threshold"
                )
            if label in {"2dof slow-command dls", "2dof fast-command dls"}:
                return (
                    "trajectory.duration, tracking_controller.max_task_speed, target_xy, "
                    "tracking_controller.condition_damping_threshold, tracking_controller.max_dls_damping"
                )
            if label in {"2dof low-joint-speed dls", "2dof high-joint-speed dls"}:
                return (
                    "tracking_controller.max_joint_speed, target_xy, tracking_controller.max_task_speed, "
                    "tracking_controller.condition_damping_threshold, tracking_controller.max_dls_damping"
                )
            if label in {"2dof direct-retarget dls", "2dof inward-retarget dls"}:
                return (
                    "target_xy_waypoints, target_xy, tracking_controller.max_task_speed, "
                    "tracking_controller.condition_damping_threshold, tracking_controller.max_dls_damping"
                )
            return (
                "target_xy, tracking_controller.dls_damping, tracking_controller.condition_damping_threshold, "
                "tracking_controller.condition_damping_full, tracking_controller.max_dls_damping"
            )
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
        if config_name == "neutral_hold_30s.yaml":
            return "sim_time, dt, home_q"
        if label == "cartesian interactive":
            return (
                "live sliders/presets: Target X/Y/Z, Cartesian gain; buttons: Target X -/+; "
                "YAML: cartesian_target.*, interaction.target_step, interaction.target_limit"
            )
        if config_name == "interactive_virtual_wall.yaml":
            return (
                "live sliders/presets: Target X/Y/Z, Cartesian gain, wall X, stiffness, damping, retreat gain; "
                "buttons: Target X into/away from wall; YAML: cartesian_target.position, "
                "cartesian_target.gain, virtual_wall.wall_x, virtual_wall.stiffness, "
                "virtual_wall.damping, interaction.target_step, virtual_wall.force_retreat_gain"
            )
        if "cartesian" in label:
            return "cartesian_target.position, cartesian_target.gain, cartesian_target.max_step"
        if label in {"slow approach wall", "fast approach wall"}:
            return "trajectory.duration, trajectory.start_time, virtual_wall.wall_x, virtual_wall.damping"
        if label in {"shallow push wall", "deep push wall"}:
            return (
                "cartesian_target.waypoints.2.position.0, cartesian_target.waypoints.3.position.0, "
                "virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping"
            )
        if label == "contact cycle wall":
            return "cartesian_target.waypoints, virtual_wall.wall_x, virtual_wall.stiffness, virtual_wall.damping"
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


def action_controls_text(action: MenuAction) -> str:
    return _action_controls_text(action.config_path)


def action_control_credit_text(action: MenuAction) -> str:
    return _action_control_credit_text(action.config_path)


def action_plan_text(action: MenuAction) -> str:
    return (
        f"Plan: {_action_level(action)}; {_action_experience_kind(action)}; "
        f"{_action_duration_text(action.config_path)}; saves report/plots/worksheet"
    )


def batch_plan_text(action: BatchMenuAction) -> str:
    return f"Plan: Batch compare; {_batch_scenario_count(action)} headless scenarios; saves combined report/worksheet"


def action_mission_text(action: MenuAction | BatchMenuAction) -> str:
    if isinstance(action, BatchMenuAction):
        return (
            f"Mission: Run {_batch_scenario_count(action)} scenarios; compare "
            f"{_short_sentence(action.try_this, 88)}; prove it with {_short_sentence(action.watch, 88)}."
        )

    watch = _short_sentence(action.watch, 96)
    if "hands-on" in action_tags(action):
        return f"Mission: Change {_short_sentence(parameter_hint(action), 88)}; prove it with {watch}."
    if _is_compare_action(action):
        return f"Mission: Isolate {_short_sentence(parameter_hint(action), 88)}; prove it with {watch}."
    return f"Mission: Run the demo; {_short_sentence(action.try_this, 88)}; prove it with {watch}."


def action_playbook_text(action: MenuAction | BatchMenuAction) -> str:
    if isinstance(action, BatchMenuAction):
        return (
            f"Playbook: 1. predict the comparison outcome; 2. run {_batch_scenario_count(action)} scenarios; "
            "3. review the report, plots, worksheet, and Prediction Check table."
        )
    guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
    playbook = playbook_for_guide(guide)
    if playbook:
        return playbook
    return "Playbook: 1. predict the response; 2. run the scenario; 3. review the saved plot and worksheet."


def action_start_steps_text(action: MenuAction | BatchMenuAction) -> str:
    if isinstance(action, BatchMenuAction):
        return batch_start_steps_text(
            scenario_count=_batch_scenario_count(action),
            course_level=action.batch_name == ALL_BATCH_NAME,
        )

    if "hands-on" in action_tags(action):
        control_step = _hands_on_start_control_step(action)
        return f"Start steps: Predict -> Run viewer -> {control_step} -> Mark observation."

    if _is_compare_action(action):
        guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
        return start_steps_for_guide(guide) or "Start steps: Predict -> Run scenario -> Compare priority plot and worksheet."

    guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
    return start_steps_for_guide(guide) or "Start steps: Predict -> Run scenario -> Review priority plot and worksheet."


def _hands_on_start_control_step(action: MenuAction) -> str:
    required_labels = configured_required_preset_labels(action.config_path)
    if required_labels:
        return f"try required presets {' -> '.join(required_labels)}"

    preset_labels = configured_preset_labels(action.config_path)
    if len(preset_labels) >= 2:
        return f"try presets {' -> '.join(preset_labels[:3])}"

    interaction = _loaded_action_config(action.config_path).get("interaction", {})
    if not isinstance(interaction, dict):
        interaction = {}
    if bool(interaction.get("key_force", False)):
        return "use Pull/Push"
    if bool(interaction.get("target_nudge", False)):
        return "use Target X buttons"
    if bool(interaction.get("joint_disturbance", False)):
        return "use Shoulder/Elbow pulse"
    if bool(interaction.get("live_tuning", False)):
        return "move one live slider"
    return "use one button, slider, or preset"


def action_challenge_text(action: MenuAction | BatchMenuAction) -> str:
    if isinstance(action, BatchMenuAction):
        return (
            "Challenge: Choose the scenario you expect to show the strongest effect before running, "
            "then mark the Prediction Check outcome in the worksheet."
        )
    guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
    challenge = challenge_prompt_for_guide(guide)
    if challenge:
        return challenge
    return "Challenge: Run the scenario, name one visible change, and point to the plot or observation that proves it."


def _batch_scenario_count(action: BatchMenuAction) -> int:
    if action.batch_name == ALL_BATCH_NAME:
        return sum(len(scenarios) for scenarios in BATCH_SETS.values())
    return len(BATCH_SETS[action.batch_name])


@lru_cache(maxsize=256)
def _action_controls_text(config_path: str) -> str:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return "Controls: Config unavailable"

    interaction = config.get("interaction")
    if not isinstance(interaction, dict) or not interaction:
        return "Controls: Auto run; edit YAML before running"

    panel_enabled = bool(interaction.get("panel", False))
    controls: list[str] = []
    if panel_enabled:
        controls.append("MCLab Interaction panel")
    if bool(interaction.get("key_force", False)):
        controls.append("Pull/Push buttons and A/D keys")
    if bool(interaction.get("target_nudge", False)):
        controls.append(_target_nudge_control_label(interaction))
    if bool(interaction.get("joint_disturbance", False)):
        controls.append("Shoulder/Elbow pulse buttons and A/D keys")
    if bool(interaction.get("live_tuning", False)):
        controls.append("live sliders with Changed values")

    preset_labels = configured_preset_labels(config_path)
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
        return "Controls: Auto run; edit YAML before running"
    return f"Controls: {', '.join(dict.fromkeys(controls))}"


@lru_cache(maxsize=256)
def _action_control_credit_text(config_path: str) -> str:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return ""
    text = control_credit_text_for_config(config)
    return f"Counts as control: {text}" if text else ""


def _target_nudge_control_label(interaction: dict[str, Any]) -> str:
    left = str(interaction.get("target_left_label", "")).strip()
    right = str(interaction.get("target_right_label", "")).strip()
    if left and right:
        return f"{left} / {right}"
    return "Target -/+ buttons and A/D keys"


def _action_level(action: MenuAction) -> str:
    return {
        "intro": "Intro",
        "build": "Build",
        "deep-dive": "Deep dive",
        "compare": "Compare",
    }.get(_action_level_key(action), "Build")


def _action_level_key(action: MenuAction) -> str:
    label = action.label.lower()
    if action.lab_name in {"lab01", "lab02"} and label in {"auto demo", "interactive"}:
        return "intro"
    if action.lab_name == "lab03" and label in {"2dof joint-space", "2dof task-space", "2dof interactive"}:
        return "build"
    if action.lab_name == "lab04" and label in {"neutral hold", "joint target", "cartesian reach", "cartesian interactive"}:
        return "build"
    if action.lab_name == "lab04" or "wall" in label or "singularity" in label or "condition" in label or "dls" in label:
        return "deep-dive"
    if _is_compare_action(action):
        return "compare"
    return "build"


def _action_experience_kind(action: MenuAction) -> str:
    tags = set(action_tags(action))
    if "hands-on" in tags:
        return "hands-on viewer"
    if _is_compare_action(action):
        return "comparison scenario"
    return "baseline demo"


@lru_cache(maxsize=256)
def _action_duration_text(config_path: str) -> str:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return "configured sim time"
    sim_time = config.get("sim_time")
    if isinstance(sim_time, int | float):
        return f"{float(sim_time):g}s simulated"
    return "configured sim time"


def action_viewer_text(action: MenuAction) -> str:
    guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
    legend = viewer_legend_for_guide(guide)
    if not legend:
        return "Viewer: Standard MuJoCo scene; use plots and live status for exact values"
    items = [f"{label} = {text}" for label, text in legend]
    return f"Viewer: {'; '.join(items)}"


def reflection_question(action: MenuAction) -> str:
    return reflection_question_for_context(
        lab_name=action.lab_name,
        label=action.label,
        config_path=action.config_path,
    )


def prediction_prompt(action: MenuAction) -> str:
    guide = guide_for_config(config_path=action.config_path, lab_name=action.lab_name)
    return prediction_prompt_for_guide(guide)


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
    if path.endswith("waypoints") and _is_preview_waypoint_list(value):
        return ((path, value),)
    if not _is_preview_value(value):
        return ()
    return ((path, value),)


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if not 0 <= index < len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def _is_preview_value(value: Any) -> bool:
    if isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list | tuple):
        return all(isinstance(item, bool | int | float | str) for item in value)
    return False


def _is_preview_waypoint_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _format_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return f"{value:g}"
    if isinstance(value, str):
        return value if len(value) <= 32 else f"{value[:29]}..."
    if _is_preview_waypoint_list(value):
        return _format_waypoint_preview(value)
    if isinstance(value, list | tuple):
        shown = [_format_config_value(item) for item in value[:4]]
        suffix = ", ..." if len(value) > 4 else ""
        return f"[{', '.join(shown)}{suffix}]"
    return str(value)


def _format_waypoint_preview(waypoints: list[dict[str, Any]]) -> str:
    first = _waypoint_position_preview(waypoints[0])
    last = _waypoint_position_preview(waypoints[-1])
    return f"{len(waypoints)} waypoints: {first} -> {last}"


def _waypoint_position_preview(waypoint: dict[str, Any]) -> str:
    raw_position = waypoint.get("position", waypoint.get("xy"))
    if raw_position is None:
        raw_position = [waypoint.get("x", "?"), waypoint.get("y", "?")]
    if isinstance(raw_position, list | tuple):
        shown = [_format_config_value(item) for item in raw_position[:3]]
        suffix = ", ..." if len(raw_position) > 3 else ""
        return f"[{', '.join(shown)}{suffix}]"
    return _format_config_value(raw_position)


def lesson_text(action: MenuAction, outputs_root: Path | None = None) -> str:
    preset_labels = configured_preset_labels(action.config_path)
    presets = f"\nPresets: {', '.join(preset_labels)}" if preset_labels else ""
    preset_purposes = configured_preset_purposes(action.config_path)
    preset_purpose_text = f"\nPreset purpose: {'; '.join(preset_purposes)}" if preset_purposes else ""
    preset_compare = configured_preset_comparison(action.config_path)
    preset_compare_text = f"\nPreset compare: {preset_compare}" if preset_compare else ""
    preset_evidence = action_preset_evidence_text(action, outputs_root)
    preset_evidence_text = f"{preset_evidence}\n" if preset_evidence else ""
    activity_mix = action_activity_mix_text(action, outputs_root)
    activity_mix_text = f"{activity_mix}\n" if activity_mix else ""
    observation_flow = action_observation_flow_text(action, outputs_root)
    observation_flow_text = f"{observation_flow}\n" if observation_flow else ""
    observation_next_step = action_observation_next_step_text(action, outputs_root)
    observation_next_step_text = f"{observation_next_step}\n" if observation_next_step else ""
    control_credit = action_control_credit_text(action)
    control_credit_line = f"{control_credit}\n" if control_credit else ""
    readiness = action_readiness(action)
    setup_detail = f" - {readiness.detail}" if readiness.status != "ok" and readiness.detail else ""
    setup_fix = f" Fix: {readiness.fix}" if readiness.status != "ok" and readiness.fix else ""
    return (
        f"{action.description}\n"
        f"Setup: {readiness.label}{setup_detail}{setup_fix}\n"
        f"Badges: {', '.join(action_badges(action))}\n"
        f"{action_plan_text(action)}\n"
        f"{action_mission_text(action)}\n"
        f"{action_playbook_text(action)}\n"
        f"{action_start_steps_text(action)}\n"
        f"{action_challenge_text(action)}\n"
        f"{action_history_text(action, outputs_root)}\n"
        f"{action_evidence_text(action, outputs_root)}\n"
        f"{action_latest_evidence_text(action, outputs_root)}\n"
        f"{observation_flow_text}"
        f"{observation_next_step_text}"
        f"{action_mission_evidence_text(action, outputs_root)}\n"
        f"{action_challenge_evidence_text(action, outputs_root)}\n"
        f"{preset_evidence_text}"
        f"{activity_mix_text}"
        f"{action_next_cue_text(action, outputs_root)}\n"
        f"{action_plot_text(action, outputs_root)}\n"
        f"{action_plot_review_text(action, outputs_root)}\n"
        f"{action_worksheet_text(action, outputs_root)}\n"
        f"{action_replay_text(action, outputs_root)}\n"
        f"{action_controls_text(action)}\n"
        f"{control_credit_line}"
        f"{action_viewer_text(action)}\n"
        f"Try: {action.try_this}\n"
        f"Change: {parameter_hint(action)}\n"
        f"{config_value_preview(action)}\n"
        f"{prediction_prompt(action)}\n"
        f"{reflection_question(action)}\n"
        f"{action_followup_text(action)}\n"
        f"{action_compare_text(action)}\n"
        f"Watch: {action.watch}"
        f"{presets}"
        f"{preset_purpose_text}"
        f"{preset_compare_text}"
    )


@lru_cache(maxsize=128)
def _loaded_action_config(config_path: str) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except (OSError, ValueError):
        return {}
    return config if isinstance(config, dict) else {}


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


@lru_cache(maxsize=128)
def configured_required_preset_labels(config_path: str) -> tuple[str, ...]:
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
        if not isinstance(preset, dict) or not bool(preset.get("required", False)):
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return tuple(labels)


@lru_cache(maxsize=128)
def configured_preset_purposes(config_path: str) -> tuple[str, ...]:
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
    purposes: list[str] = []
    for index, preset in enumerate(presets, start=1):
        if not isinstance(preset, dict):
            continue
        purpose = str(preset.get("purpose") or preset.get("description") or "").strip()
        if not purpose:
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        purposes.append(f"{label}: {purpose}" if label else purpose)
    return tuple(purposes)


@lru_cache(maxsize=128)
def configured_preset_comparison(config_path: str) -> str:
    labels = configured_preset_labels(config_path)
    if len(labels) < 2:
        return ""
    required_labels = configured_required_preset_labels(config_path)
    if required_labels:
        return (
            f"{' -> '.join(labels)}; required evidence: {' -> '.join(required_labels)}; "
            "watch live status, then mark one observation."
        )
    return f"{' -> '.join(labels)}; watch live status, then mark one observation."


def action_tags(action: MenuAction) -> tuple[str, ...]:
    label = action.label.lower()
    config_name = Path(action.config_path).name.lower()
    tags = {action.lab_name, action.lab_name.replace("lab", "lab "), action.group.lower(), _action_level_key(action)}

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
    if label in {"2dof dls singularity", "2dof condition-aware dls"}:
        tags.add("hands-on")
    if label == "joint target":
        tags.add("hands-on")
    if _is_compare_action(action):
        tags.add("compare")
    if "wall" in label or "wall" in config_name:
        tags.add("wall")
    if "singularity" in label or "condition" in label or "condition" in config_name:
        tags.update({"singularity", "dls" if "dls" in label else "conditioning"})
    if "cartesian" in label or "reach" in label:
        tags.add("cartesian")
    if any(term in label for term in ("step", "trapezoid", "minimum jerk", "s-curve", "path")):
        tags.add("trajectory")
    if (
        "gain" in label
        or "damping" in label
        or "retreat" in label
        or "torque" in label
        or "windup" in label
        or "saturation" in label
    ):
        tags.add("tuning")

    return tuple(sorted(tags))


def action_badges(action: MenuAction) -> tuple[str, ...]:
    tags = set(action_tags(action))
    return tuple(ACTION_BADGE_LABELS[tag] for tag in ACTION_BADGE_PRIORITY if tag in tags)


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
        "2dof early dls damping",
        "2dof late dls damping",
        "2dof inner-target dls",
        "2dof edge-target dls",
        "2dof upper-path dls",
        "2dof lower-path dls",
        "2dof shoulder-disturbance dls",
        "2dof elbow-disturbance dls",
        "2dof staggered-disturbance dls",
        "2dof low-torque dls",
        "2dof high-torque dls",
        "2dof slow-command dls",
        "2dof fast-command dls",
        "2dof low-joint-speed dls",
        "2dof high-joint-speed dls",
        "2dof direct-retarget dls",
        "2dof inward-retarget dls",
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
        "low damping wall",
        "high damping wall",
        "near wall",
        "far wall",
        "contact cycle wall",
        "low retreat wall",
        "high retreat wall",
    }
    return label in compare_labels


def filter_menu_actions(
    query: str,
    actions: tuple[MenuAction, ...] = MENU_ACTIONS,
    experience_filter: str = "all",
) -> tuple[MenuAction, ...]:
    filter_key = _normalize_filter_key(experience_filter)
    if filter_key and filter_key != "all":
        actions = tuple(action for action in actions if filter_key in action_tags(action))
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return actions
    return tuple(action for action in actions if _action_matches_terms(action, terms))


def _action_matches_terms(action: MenuAction, terms: list[str]) -> bool:
    fields = [
        action.group,
        action.label,
        action.lab_name,
        action.config_path,
        action.plots,
        action.description,
        action.try_this,
        action.watch,
        parameter_hint(action),
        prediction_prompt(action),
        reflection_question(action),
        action_controls_text(action),
        action_control_credit_text(action),
        action_viewer_text(action),
        action_plan_text(action),
        action_mission_text(action),
        action_playbook_text(action),
        action_start_steps_text(action),
        action_challenge_text(action),
        "mission evidence challenge evidence artifact observation prediction outcome note proof",
        "playbook predict change mark review worksheet",
        "start steps first action run viewer priority plot",
        "challenge visible effect prove strongest effect proof source",
        "next cue run preset observation outcome replay compare",
        " ".join(configured_preset_labels(action.config_path)),
        " ".join(configured_preset_purposes(action.config_path)),
        configured_preset_comparison(action.config_path),
        action_readiness(action).label,
        action_readiness(action).detail,
        " ".join(action_tags(action)),
        " ".join(tag.replace("-", " ") for tag in action_tags(action)),
        config_value_preview(action),
    ]
    if "next" in terms:
        fields.append(action_followup_text(action))
    if "compare" in terms:
        fields.append(action_compare_text(action))
    text = " ".join(fields).lower()
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
    path_report_buttons: list[tuple[LearningPathStep, Any]] = []
    path_plot_buttons: list[tuple[LearningPathStep, Any]] = []
    path_worksheet_buttons: list[tuple[LearningPathStep, Any]] = []
    path_replay_buttons: list[tuple[LearningPathStep, Any]] = []
    path_summary = tk.StringVar(value=learning_path_summary_text())
    path_milestones = tk.StringVar(value=learning_path_milestone_text())
    next_step_ref: dict[str, LearningPathStep | None] = {"step": next_learning_path_step()}
    next_button_ref: dict[str, Any | None] = {"button": None}
    next_review_button_ref: dict[str, Any | None] = {"button": None}
    batch_state_items: list[BatchMenuStateItem | BatchMenuStateItemWithWorksheet] = []
    post_run_refresh_ref: dict[str, Callable[[], None]] = {}
    review_queue = tk.StringVar(value=review_queue_summary_text())

    def refresh_learning_path_progress() -> None:
        progress_items: list[LearningPathProgressItem] = []
        progress_by_step: dict[LearningPathStep, LearningPathProgress] = {}
        for step, variable in path_status_vars:
            progress = learning_path_progress(step)
            progress_items.append((step, progress))
            progress_by_step[step] = progress
            variable.set(learning_path_progress_text(step, progress))
        for step, button in path_report_buttons:
            progress = progress_by_step.get(step) or learning_path_progress(step)
            button.state(["!disabled"] if progress.latest_output is not None else ["disabled"])
        for step, button in path_plot_buttons:
            button.state(["!disabled"] if learning_path_latest_plot(step) is not None else ["disabled"])
        for step, button in path_worksheet_buttons:
            button.state(["!disabled"] if learning_path_latest_worksheet(step) is not None else ["disabled"])
        for step, button in path_replay_buttons:
            button.state(["!disabled"] if learning_path_latest_tuned_config(step) is not None else ["disabled"])
        items = tuple(progress_items) if progress_items else learning_path_progress_items()
        next_step = next_learning_path_step(items)
        next_step_ref["step"] = next_step
        path_summary.set(learning_path_summary_text(items))
        path_milestones.set(learning_path_milestone_text(items))
        review_queue.set(review_queue_summary_text())
        next_button = next_button_ref["button"]
        if next_button is not None:
            next_button.state(["disabled"] if next_step is None else ["!disabled"])
        next_review_button = next_review_button_ref["button"]
        if next_review_button is not None:
            next_review_button.state(["!disabled"] if next_review_output() is not None else ["disabled"])

    def refresh_after_run() -> None:
        refresh_callback = post_run_refresh_ref.get("callback", refresh_learning_path_progress)
        refresh_callback()

    def refresh_batch_cards() -> None:
        refresh_batch_menu_state(tuple(batch_state_items))

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
            latest_plot_button=latest_plot_button,
            latest_worksheet_button=latest_worksheet_button,
            progress_callback=refresh_after_run,
        )

    def launch_next_review_from_menu() -> None:
        if launch_next_review_output() is None:
            status.set("Review queue has no pending run to open.")
            return
        status.set("Opened the next review run.")

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
    ttk.Label(experience_bar, text="Explore").grid(row=0, column=0, rowspan=2, sticky="nw")
    filter_buttons = ttk.Frame(experience_bar)
    filter_buttons.grid(row=0, column=1, sticky="w")
    for filter_index, filter_option in enumerate(EXPERIENCE_FILTERS):
        filter_row, filter_column = divmod(filter_index, 7)
        ttk.Radiobutton(
            filter_buttons,
            text=filter_option.label,
            value=filter_option.key,
            variable=active_experience_filter,
            command=update_experience_filter,
        ).grid(row=filter_row, column=filter_column, sticky="w", padx=(8, 0), pady=(0, 3))
    ttk.Label(experience_bar, textvariable=filter_description, wraplength=760, justify="left").grid(
        row=1,
        column=1,
        sticky="w",
        padx=(8, 0),
        pady=(2, 0),
    )

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
    ttk.Label(path_header, textvariable=path_milestones, wraplength=760, justify="left").grid(
        row=1, column=0, sticky="w", pady=(4, 0)
    )
    next_button = ttk.Button(path_header, text="Run next", command=launch_next_learning_path_step)
    next_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
    next_button_ref["button"] = next_button
    review_header = ttk.Frame(path_frame)
    review_header.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
    review_header.columnconfigure(0, weight=1)
    ttk.Label(review_header, textvariable=review_queue, wraplength=760, justify="left").grid(
        row=0, column=0, sticky="w"
    )
    next_review_button = ttk.Button(
        review_header,
        text="Open next review",
        command=launch_next_review_from_menu,
    )
    next_review_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
    next_review_button_ref["button"] = next_review_button
    ttk.Button(review_header, text="Open review queue", command=launch_outputs_index).grid(
        row=0, column=2, sticky="e", padx=(8, 0)
    )
    for step_index, step in enumerate(LEARNING_PATH):
        row_index, column_index = divmod(step_index, 3)
        cell = ttk.Frame(path_frame)
        cell.grid(row=row_index + 2, column=column_index, sticky="ew", padx=(0, 12), pady=(0, 8))
        progress_text = tk.StringVar(value=learning_path_progress_text(step))
        path_status_vars.append((step, progress_text))
        step_buttons = ttk.Frame(cell)
        step_buttons.pack(anchor="w")
        ttk.Button(
            step_buttons,
            text=step.title,
            width=22,
            command=lambda selected=step: _launch_learning_path_from_menu(
                selected,
                status,
                root=root,
                latest_output=latest_output,
                latest_button=latest_button,
                latest_plot_button=latest_plot_button,
                latest_worksheet_button=latest_worksheet_button,
                progress_callback=refresh_after_run,
            ),
        ).pack(side="left")
        step_report_button = ttk.Button(
            step_buttons,
            text="Report",
            width=8,
            command=lambda selected=step: launch_learning_path_latest_output(selected),
        )
        if learning_path_latest_output(step) is None:
            step_report_button.state(["disabled"])
        step_report_button.pack(side="left", padx=(6, 0))
        path_report_buttons.append((step, step_report_button))
        step_plot_button = ttk.Button(
            step_buttons,
            text="Plot",
            width=8,
            command=lambda selected=step: launch_learning_path_latest_plot(selected),
        )
        if learning_path_latest_plot(step) is None:
            step_plot_button.state(["disabled"])
        step_plot_button.pack(side="left", padx=(6, 0))
        path_plot_buttons.append((step, step_plot_button))
        step_worksheet_button = ttk.Button(
            step_buttons,
            text="Worksheet",
            width=10,
            command=lambda selected=step: launch_learning_path_latest_worksheet(selected),
        )
        if learning_path_latest_worksheet(step) is None:
            step_worksheet_button.state(["disabled"])
        step_worksheet_button.pack(side="left", padx=(6, 0))
        path_worksheet_buttons.append((step, step_worksheet_button))
        step_replay_button = ttk.Button(
            step_buttons,
            text="Replay",
            width=8,
            command=lambda selected=step: _launch_learning_path_tuned_replay_from_menu(
                selected,
                status,
                root=root,
                latest_output=latest_output,
                latest_button=latest_button,
                latest_plot_button=latest_plot_button,
                latest_worksheet_button=latest_worksheet_button,
                progress_callback=refresh_after_run,
            ),
        )
        if learning_path_latest_tuned_config(step) is None:
            step_replay_button.state(["disabled"])
        step_replay_button.pack(side="left", padx=(6, 0))
        path_replay_buttons.append((step, step_replay_button))
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
        readiness = batch_readiness(action)
        batch_button = ttk.Button(
            cell,
            text=action.label,
            width=18,
            command=lambda selected=action: _launch_batch_from_menu(
                selected,
                status,
                root=root,
                latest_output=latest_output,
                latest_button=latest_button,
                latest_plot_button=latest_plot_button,
                latest_worksheet_button=latest_worksheet_button,
                progress_callback=refresh_after_run,
            ),
        )
        if readiness.status != "ok":
            batch_button.state(["disabled"])
        batch_button.pack(anchor="w")
        batch_latest = action_latest_output(action)
        report_button = ttk.Button(
            cell,
            text="Report",
            width=10,
            command=lambda selected=action: launch_action_latest_output(selected),
        )
        if batch_latest is None:
            report_button.state(["disabled"])
        report_button.pack(anchor="w", pady=(4, 0))
        batch_plot = action_latest_plot(action)
        plot_button = ttk.Button(
            cell,
            text="Plot",
            width=10,
            command=lambda selected=action: launch_action_latest_plot(selected),
        )
        if batch_plot is None:
            plot_button.state(["disabled"])
        plot_button.pack(anchor="w", pady=(4, 0))
        batch_worksheet = action_latest_worksheet(action)
        worksheet_button = ttk.Button(
            cell,
            text="Worksheet",
            width=10,
            command=lambda selected=action: launch_action_latest_worksheet(selected),
        )
        if batch_worksheet is None:
            worksheet_button.state(["disabled"])
        worksheet_button.pack(anchor="w", pady=(4, 0))
        batch_text = tk.StringVar(value=lesson_text_for_batch(action))
        ttk.Label(cell, textvariable=batch_text, wraplength=360, justify="left").pack(
            anchor="w", pady=(4, 0)
        )
        batch_state_items.append((action, batch_text, report_button, plot_button, worksheet_button))

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
    ttk.Button(bottom, text="Refresh path", command=refresh_after_run).pack(side="left")
    ttk.Button(bottom, text="Check setup", command=lambda: _launch_doctor_from_menu(status, root=root)).pack(
        side="left", padx=(8, 0)
    )
    ttk.Button(bottom, text="Open all reports", command=launch_outputs_index).pack(side="left", padx=(8, 0))
    ttk.Button(bottom, text="Open outputs folder", command=launch_outputs_folder).pack(side="left", padx=(8, 0))
    latest_button = ttk.Button(bottom, text="Open latest report", command=lambda: launch_latest_output(latest_output))
    latest_button.pack(side="left", padx=(8, 0))
    latest_button.state(["disabled"])
    latest_plot_button = ttk.Button(bottom, text="Open latest plot", command=lambda: launch_latest_plot(latest_output))
    latest_plot_button.pack(side="left", padx=(8, 0))
    latest_plot_button.state(["disabled"])
    latest_worksheet_button = ttk.Button(
        bottom,
        text="Open latest worksheet",
        command=lambda: launch_latest_worksheet(latest_output),
    )
    latest_worksheet_button.pack(side="left", padx=(8, 0))
    latest_worksheet_button.state(["disabled"])
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
                text="No matching scenarios. Try All, Intro, Deep dive, PID, noise, wall, 2DOF, or hands-on.",
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
            frame.columnconfigure(9, weight=1)
            row += 1
            for action_index, action in enumerate(actions):
                readiness = action_readiness(action)
                latest = action_latest_output(action)
                latest_plot = action_latest_plot(action)
                latest_worksheet = action_latest_worksheet(action)
                latest_tuned_config = action_latest_tuned_config(action)
                followup = action_followup(action)
                compare_batch = action_compare_batch(action)
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
                        latest_plot_button=latest_plot_button,
                        latest_worksheet_button=latest_worksheet_button,
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
                plot_button = ttk.Button(
                    frame,
                    text="Plot",
                    width=8,
                    command=lambda selected=action: launch_action_latest_plot(selected),
                )
                if latest_plot is None:
                    plot_button.state(["disabled"])
                plot_button.grid(row=action_index, column=4, sticky="w", padx=(0, 12), pady=4)
                worksheet_button = ttk.Button(
                    frame,
                    text="Worksheet",
                    width=10,
                    command=lambda selected=action: launch_action_latest_worksheet(selected),
                )
                if latest_worksheet is None:
                    worksheet_button.state(["disabled"])
                worksheet_button.grid(row=action_index, column=5, sticky="w", padx=(0, 12), pady=4)
                replay_button = ttk.Button(
                    frame,
                    text="Replay",
                    width=8,
                    command=lambda selected=action: _launch_tuned_replay_from_menu(
                        selected,
                        status,
                        root=root,
                        latest_output=latest_output,
                        latest_button=latest_button,
                        latest_plot_button=latest_plot_button,
                        latest_worksheet_button=latest_worksheet_button,
                        progress_callback=refresh_after_run,
                    ),
                )
                if latest_tuned_config is None:
                    replay_button.state(["disabled"])
                replay_button.grid(row=action_index, column=6, sticky="w", padx=(0, 12), pady=4)
                next_button = ttk.Button(
                    frame,
                    text="Next",
                    width=8,
                    command=lambda selected=followup: _launch_target_from_menu(
                        selected,
                        status,
                        root=root,
                        latest_output=latest_output,
                        latest_button=latest_button,
                        latest_plot_button=latest_plot_button,
                        latest_worksheet_button=latest_worksheet_button,
                        progress_callback=refresh_after_run,
                    ),
                )
                if isinstance(followup, MenuAction) and action_readiness(followup).status != "ok":
                    next_button.state(["disabled"])
                if isinstance(followup, BatchMenuAction) and batch_readiness(followup).status != "ok":
                    next_button.state(["disabled"])
                next_button.grid(row=action_index, column=7, sticky="w", padx=(0, 12), pady=4)
                compare_button = ttk.Button(
                    frame,
                    text="Compare",
                    width=8,
                    command=lambda selected=compare_batch: _launch_batch_from_menu(
                        selected,
                        status,
                        root=root,
                        latest_output=latest_output,
                        latest_button=latest_button,
                        latest_plot_button=latest_plot_button,
                        latest_worksheet_button=latest_worksheet_button,
                        progress_callback=refresh_after_run,
                    ),
                )
                if batch_readiness(compare_batch).status != "ok":
                    compare_button.state(["disabled"])
                compare_button.grid(row=action_index, column=8, sticky="w", padx=(0, 12), pady=4)
                ttk.Label(frame, text=lesson_text(action), wraplength=500, justify="left").grid(
                    row=action_index, column=9, sticky="w", pady=4
                )
        canvas.configure(scrollregion=canvas.bbox("all"))

    def refresh_progress_and_actions() -> None:
        refresh_learning_path_progress()
        refresh_batch_cards()
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
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    action = learning_path_target(step)
    _launch_target_from_menu(
        action,
        status,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
        latest_plot_button=latest_plot_button,
        latest_worksheet_button=latest_worksheet_button,
        progress_callback=progress_callback,
    )


def _launch_target_from_menu(
    target: MenuAction | BatchMenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    if isinstance(target, BatchMenuAction):
        _launch_batch_from_menu(
            target,
            status,
            root=root,
            latest_output=latest_output,
            latest_button=latest_button,
            latest_plot_button=latest_plot_button,
            latest_worksheet_button=latest_worksheet_button,
            progress_callback=progress_callback,
        )
        return
    _launch_from_menu(
        target,
        status,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
        latest_plot_button=latest_plot_button,
        latest_worksheet_button=latest_worksheet_button,
        progress_callback=progress_callback,
    )


def _launch_from_menu(
    action: MenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
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
            "latest_plot_button": latest_plot_button,
            "latest_worksheet_button": latest_worksheet_button,
            "progress_callback": progress_callback,
        },
        daemon=True,
    ).start()


def _launch_tuned_replay_from_menu(
    action: MenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    tuned_config = action_latest_tuned_config(action)
    if tuned_config is None:
        status.set(f"Cannot replay {action.group} - {action.label}: no learner_tuned_config.yaml yet.")
        return
    process = launch_tuned_replay(action, tuned_config)
    status.set(
        f"Started tuned replay for {action.group} - {action.label} "
        f"(pid {process.pid}). Close the viewer to finish."
    )
    Thread(
        target=_watch_process,
        args=(process, action, status),
        kwargs={
            "root": root,
            "latest_output": latest_output,
            "latest_button": latest_button,
            "latest_plot_button": latest_plot_button,
            "latest_worksheet_button": latest_worksheet_button,
            "progress_callback": progress_callback,
        },
        daemon=True,
    ).start()


def _launch_learning_path_tuned_replay_from_menu(
    step: LearningPathStep,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    target = learning_path_target(step)
    if not isinstance(target, MenuAction):
        status.set(f"Cannot replay {step.title}: comparison batch steps do not have learner_tuned_config.yaml.")
        return
    _launch_tuned_replay_from_menu(
        target,
        status,
        root=root,
        latest_output=latest_output,
        latest_button=latest_button,
        latest_plot_button=latest_plot_button,
        latest_worksheet_button=latest_worksheet_button,
        progress_callback=progress_callback,
    )


def _launch_batch_from_menu(
    action: BatchMenuAction,
    status: Any,
    *,
    root: Any | None = None,
    latest_output: dict[str, Path | None] | None = None,
    latest_button: Any | None = None,
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    readiness = batch_readiness(action)
    if readiness.status != "ok":
        detail = f" - {readiness.detail}" if readiness.detail else ""
        fix = f" {readiness.fix}" if readiness.fix else ""
        status.set(f"Cannot start {action.group} - {action.label}: {readiness.label}{detail}.{fix}")
        return
    process = launch_batch_action(action)
    status.set(f"Started {action.group} - {action.label} (pid {process.pid}).")
    Thread(
        target=_watch_process,
        args=(process, action, status),
        kwargs={
            "root": root,
            "latest_output": latest_output,
            "latest_button": latest_button,
            "latest_plot_button": latest_plot_button,
            "latest_worksheet_button": latest_worksheet_button,
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
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
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
        latest_plot_button=latest_plot_button,
        latest_worksheet_button=latest_worksheet_button,
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
    latest_plot_button: Any | None = None,
    latest_worksheet_button: Any | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    def update_ui() -> None:
        if return_code == 0:
            if output_path is not None:
                if latest_output is not None:
                    latest_output["path"] = output_path
                if latest_button is not None:
                    latest_button.state(["!disabled"])
                latest_plot = latest_output_plot(output_path)
                if latest_plot_button is not None:
                    latest_plot_button.state(["!disabled"] if latest_plot is not None else ["disabled"])
                latest_worksheet = latest_output_worksheet(output_path)
                if latest_worksheet_button is not None:
                    latest_worksheet_button.state(["!disabled"] if latest_worksheet is not None else ["disabled"])
                latest = _preferred_output_entry(output_path)
                plot_suffix = f" Latest plot: {latest_plot}" if latest_plot is not None else " No plot saved yet."
                worksheet_suffix = (
                    f" Latest worksheet: {latest_worksheet}"
                    if latest_worksheet is not None
                    else " No worksheet saved yet."
                )
                status.set(
                    f"Completed {action.group} - {action.label}. "
                    f"Latest report: {latest}.{plot_suffix}{worksheet_suffix}"
                )
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


def lesson_text_for_batch(action: BatchMenuAction, outputs_root: Path | None = None) -> str:
    scenario_count = _batch_scenario_count(action)
    readiness = batch_readiness(action)
    setup_detail = f" - {readiness.detail}" if readiness.status != "ok" and readiness.detail else ""
    setup_fix = f" Fix: {readiness.fix}" if readiness.status != "ok" and readiness.fix else ""
    return (
        f"{action.description}\n"
        f"Setup: {readiness.label}{setup_detail}{setup_fix}\n"
        f"{batch_plan_text(action)}\n"
        f"{action_mission_text(action)}\n"
        f"{action_playbook_text(action)}\n"
        f"{action_start_steps_text(action)}\n"
        f"{action_challenge_text(action)}\n"
        f"{action_history_text(action, outputs_root)}\n"
        f"{action_mission_evidence_text(action, outputs_root)}\n"
        f"{action_challenge_evidence_text(action, outputs_root)}\n"
        f"{action_plot_text(action, outputs_root)}\n"
        f"{action_plot_review_text(action, outputs_root)}\n"
        f"{action_worksheet_text(action, outputs_root)}\n"
        f"{batch_prediction_check_text(action, outputs_root)}\n"
        f"Try: {action.try_this}\n"
        f"Watch: {action.watch}\n"
        f"Runs: {scenario_count} scenarios"
    )
