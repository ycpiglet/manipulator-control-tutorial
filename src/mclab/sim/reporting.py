"""HTML report generation for saved lab runs."""

from __future__ import annotations

import json
import re
import shlex
import time
from copy import deepcopy
from dataclasses import dataclass, replace
from html import escape
from pathlib import Path
from typing import Any

from mclab.application.catalog import (
    ScenarioCatalog,
    stable_scenario_id,
    target_from_legacy_summary,
)
from mclab.application.completion_progress import (
    TargetCompletionAssessment,
    build_completion_assessment_index,
)
from mclab.application.repositories import ArtifactRecord, ArtifactRepository
from mclab.completion import (
    CompletionDecision,
    CompletionEvidence,
    CompletionReason,
    CompletionRecordKind,
    evaluate_completion,
)
from mclab.config import load_config
from mclab.course_progress import course_milestone_label_for_step_index, course_milestone_summary
from mclab.experience_coverage import (
    EXPERIENCE_COVERAGE_ITEMS,
    ExperienceCoverageItem,
    ExperienceCoverageRecord,
    ExperienceCoverageStatus,
    experience_coverage_item_evidence,
    experience_coverage_item_mode,
    experience_coverage_statuses,
    experience_coverage_summary_text,
    next_experience_coverage_item,
)
from mclab.learning_guides import (
    RunGuide,
    VIEWER_CONTROL_SURFACE_TEXT,
    batch_start_steps_text,
    challenge_prompt_for_guide,
    guide_for_config,
    guide_for_run_summary,
    learner_control_action_text_for_config,
    learner_control_families_from_config,
    mission_prompt_for_guide,
    playbook_for_guide,
    prediction_prompt_for_guide,
    question_for_guide,
    start_steps_for_guide,
    viewer_legend_for_guide,
)
from mclab.output_inventory import (
    TERMINAL_STATUSES,
    assert_output_tree_mutable,
)
from mclab.output_publication import (
    OutputPublication,
    OutputPublicationBusyError,
    mutable_collection_publication,
    mutable_run_publication,
)
from mclab.output_safety import MAX_METADATA_BYTES

INDEX_METRIC_KEYS = (
    "max_abs_position",
    "overshoot_percent",
    "settling_time",
    "steady_state_error",
    "max_control_effort",
    "measurement_noise_std",
    "control_delay",
    "max_abs_measurement_error",
    "max_abs_tracking_error",
    "final_tracking_error",
    "max_abs_control_force",
    "max_joint_error_norm",
    "final_joint_error_norm",
    "max_abs_qdot",
    "max_settled_abs_qdot",
    "max_hand_x_speed",
    "max_hand_speed",
    "max_joint_drift_norm",
    "max_task_error_norm",
    "final_task_error_norm",
    "min_manipulability",
    "max_jacobian_condition",
    "max_abs_tau_cmd",
    "max_abs_tau_disturbance",
    "max_abs_tau_total",
    "max_task_error_during_disturbance",
    "disturbance_recovery_duration",
    "disturbance_recovery_time",
    "max_dls_task_speed",
    "min_dls_task_speed_limit",
    "max_dls_task_speed_limit",
    "max_dls_joint_speed",
    "max_dls_damping",
    "max_dls_condition_scale",
    "max_cartesian_error_cm",
    "final_cartesian_error_cm",
    "max_wall_penetration_cm",
    "max_wall_retreat_cm",
    "max_target_wall_gap_cm",
    "first_target_wall_cross_time",
    "first_wall_contact_time",
    "first_wall_release_time",
    "first_target_wall_return_time",
    "last_wall_contact_time",
    "target_past_wall_duration",
    "target_past_wall_fraction",
    "target_wall_cross_episodes",
    "wall_contact_duration",
    "wall_contact_fraction",
    "wall_contact_episodes",
    "max_abs_virtual_wall_force",
    "max_abs_virtual_wall_spring_force",
    "max_abs_virtual_wall_damping_force",
    "interaction_events",
)

INDEX_PLOT_PRIORITY = (
    "position",
    "error",
    "cartesian_error",
    "end_effector",
    "wall_key_moment_timing",
    "virtual_wall",
    "singularity",
    "dls",
    "disturbance",
    "torque",
    "control_force",
    "force",
    "pid_terms",
    "velocity",
    "energy",
)

INDEX_MAX_PLOT_LINKS = 4


def plot_priorities_for_context(
    *,
    config_path: str = "",
    config_name: str = "",
    lab_name: str = "",
    batch_name: str = "",
) -> tuple[str, ...]:
    """Return learner-facing plot priorities for a run or comparison context."""
    context = " ".join((config_path, config_name, lab_name, batch_name)).replace("\\", "/").lower()
    if "lab04_wall_compare" in context:
        return _plot_priority_sequence(
            "wall_key_moment_timing",
            "wall_penetration",
            "wall_force",
            "virtual_wall",
            "wall_target",
        )
    if "lab03_2dof" in context and ("dls" in context or "condition_aware" in context):
        return _plot_priority_sequence("dls", "singularity", "disturbance", "error", "end_effector")
    if "lab04_panda" in context and (
        "wall" in context or "impedance_wall" in context or "virtual_wall" in context
    ):
        return _plot_priority_sequence(
            "wall_target",
            "virtual_wall",
            "wall_key_moment_timing",
            "end_effector",
            "cartesian_error",
            "error",
        )
    if "lab04_panda" in context and ("cartesian" in context or "reach" in context):
        return _plot_priority_sequence("cartesian_error", "end_effector", "error", "position")
    return INDEX_PLOT_PRIORITY


def _plot_priority_sequence(*preferred: str) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in (*preferred, *INDEX_PLOT_PRIORITY):
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return tuple(ordered)


CONFIG_HIGHLIGHT_KEYS = (
    "sim_time",
    "dt",
    "mode",
    "plant",
    "mass",
    "damping",
    "stiffness",
    "initial_position",
    "initial_velocity",
    "force_input.type",
    "force_input.magnitude",
    "force_input.start_time",
    "target.type",
    "target.start",
    "target.end",
    "target.start_time",
    "controller.kp",
    "controller.ki",
    "controller.kd",
    "controller.output_limit",
    "controller.anti_windup",
    "measurement_noise_std",
    "control_delay",
    "trajectory.type",
    "trajectory.start",
    "trajectory.end",
    "trajectory.duration",
    "trajectory.start_time",
    "tracking_controller.kp",
    "tracking_controller.kd",
    "tracking_controller.task_kp",
    "tracking_controller.task_kd",
    "tracking_controller.dls_gain",
    "tracking_controller.dls_damping",
    "tracking_controller.condition_aware_damping",
    "tracking_controller.condition_damping_threshold",
    "tracking_controller.condition_damping_full",
    "tracking_controller.max_dls_damping",
    "tracking_controller.max_task_speed",
    "tracking_controller.max_task_speed_schedule",
    "tracking_controller.max_joint_speed",
    "tracking_controller.force_limit",
    "tracking_controller.torque_limit",
    "link_lengths",
    "initial_q",
    "target_q",
    "target_xy",
    "target_xy_waypoints",
    "controlled_joint_index",
    "cartesian_target.position",
    "cartesian_target.waypoints",
    "cartesian_target.offset",
    "cartesian_target.gain",
    "cartesian_target.max_step",
    "virtual_wall.wall_x",
    "virtual_wall.stiffness",
    "virtual_wall.damping",
    "virtual_wall.force_retreat_gain",
    "interaction.key_force",
    "interaction.force",
    "interaction.duration",
    "interaction.target_nudge",
    "interaction.target_step",
    "interaction.target_limit",
    "interaction.target_left_label",
    "interaction.target_right_label",
    "interaction.target_event_name",
    "interaction.joint_disturbance",
    "interaction.joint_disturbance_torque",
    "interaction.joint_disturbance_duration",
    "interaction.live_tuning",
    "disturbance_torque.start_time",
    "disturbance_torque.duration",
    "disturbance_torque.ramp_time",
    "disturbance_torque.torque",
    "disturbance_torque.pulses",
    "viewer_guides.enabled",
    "viewer_guides.condition_warning",
    "viewer_guides.condition_threshold",
)

CONFIG_PATH_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_*]+)*")


@dataclass(frozen=True)
class IndexPathStep:
    title: str
    description: str
    config_path: str = ""
    batch_name: str = ""
    plots: str = "essential"


@dataclass(frozen=True)
class NextRunSuggestion:
    config_path: str
    reason: str
    plots: str = "essential"


INDEX_LEARNING_PATH: tuple[IndexPathStep, ...] = (
    IndexPathStep(
        "1. Feel 1D physics",
        "Mass-spring-damper baseline response.",
        "configs/lab01_msd/default.yaml",
    ),
    IndexPathStep(
        "2. Disturb and tune",
        "Push the mass and tune physical parameters.",
        "configs/lab01_msd/interactive_pull.yaml",
    ),
    IndexPathStep("3. Close the loop", "PID tracking, error, and control force.", "configs/lab02_pid/default.yaml"),
    IndexPathStep(
        "4. Tune PID live",
        "Tune target, gains, and force limit.",
        "configs/lab02_pid/interactive_disturbance.yaml",
    ),
    IndexPathStep(
        "5. Move 2DOF joints",
        "Joint-space tracking on the two-link arm.",
        "configs/lab03_2dof/joint_space_2dof.yaml",
    ),
    IndexPathStep(
        "6. Control the hand",
        "Task-space hand control with the Jacobian.",
        "configs/lab03_2dof/task_space_2dof.yaml",
        plots="task",
    ),
    IndexPathStep(
        "7. Handle singularity",
        "Condition-aware DLS near poor Jacobian conditioning.",
        "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
        plots="dls_disturbance",
    ),
    IndexPathStep(
        "8. Compare DLS retarget",
        "Adaptive task-speed scheduling on the same near-edge retarget path.",
        "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml",
        plots="dls",
    ),
    IndexPathStep("9. Hold Panda", "Stable neutral-hold baseline for Panda.", "configs/lab04_panda/neutral_hold.yaml"),
    IndexPathStep(
        "10. Reach in Cartesian",
        "Panda hand reaches an explicit XYZ target.",
        "configs/lab04_panda/cartesian_reach.yaml",
        plots="cartesian_reach",
    ),
    IndexPathStep(
        "11. Touch virtual wall",
        "Interactive Panda virtual wall behavior.",
        "configs/lab04_panda/interactive_virtual_wall.yaml",
        plots="wall",
    ),
    IndexPathStep("12. Compare the course", "Full comparison report set.", batch_name="all"),
)


NEXT_RUN_SUGGESTIONS: dict[str, tuple[NextRunSuggestion, ...]] = {
    "configs/lab01_msd/default.yaml": (
        NextRunSuggestion("configs/lab01_msd/underdamped.yaml", "See what changes when damping is too low."),
        NextRunSuggestion("configs/lab01_msd/high_stiffness.yaml", "Compare a sharper spring response."),
        NextRunSuggestion("configs/lab01_msd/interactive_pull.yaml", "Push the mass and tune parameters live."),
    ),
    "configs/lab01_msd/underdamped.yaml": (
        NextRunSuggestion("configs/lab01_msd/over_damped.yaml", "Contrast oscillatory and non-oscillatory settling."),
        NextRunSuggestion("configs/lab01_msd/high_stiffness.yaml", "Separate damping effects from stiffness effects."),
    ),
    "configs/lab01_msd/over_damped.yaml": (
        NextRunSuggestion("configs/lab01_msd/underdamped.yaml", "Compare slow return against oscillatory return."),
        NextRunSuggestion("configs/lab01_msd/low_stiffness.yaml", "Check whether softness or damping is slowing motion."),
    ),
    "configs/lab01_msd/high_stiffness.yaml": (
        NextRunSuggestion("configs/lab01_msd/low_stiffness.yaml", "Use the opposite stiffness case as a clean comparison."),
        NextRunSuggestion("configs/lab01_msd/interactive_pull.yaml", "Tune stiffness live while watching force and energy."),
    ),
    "configs/lab01_msd/low_stiffness.yaml": (
        NextRunSuggestion("configs/lab01_msd/high_stiffness.yaml", "Compare frequency and force against the stiff spring."),
        NextRunSuggestion("configs/lab01_msd/interactive_pull.yaml", "Raise stiffness live and watch the response change."),
    ),
    "configs/lab01_msd/f2_launch_high_energy.yaml": (
        NextRunSuggestion("configs/lab01_msd/f2_launch_precheck.yaml", "See the same displacement with a safe energy budget."),
        NextRunSuggestion("configs/lab01_msd/underdamped.yaml", "Isolate how low damping alone changes settling."),
    ),
    "configs/lab01_msd/f2_launch_precheck.yaml": (
        NextRunSuggestion("configs/lab01_msd/f2_launch_high_energy.yaml", "Revisit the dangerous setting and compare the peak speed."),
        NextRunSuggestion("configs/lab01_msd/interactive_pull.yaml", "Tune stiffness live and watch stored energy react."),
    ),
    "configs/lab01_msd/interactive_pull.yaml": (
        NextRunSuggestion("configs/lab01_msd/underdamped.yaml", "Save a deterministic low-damping comparison."),
        NextRunSuggestion("configs/lab01_msd/over_damped.yaml", "Save a deterministic high-damping comparison."),
        NextRunSuggestion("configs/lab01_msd/high_stiffness.yaml", "Compare the stiff-spring response in a report."),
    ),
    "configs/lab02_pid/default.yaml": (
        NextRunSuggestion("configs/lab02_pid/p_low_gain.yaml", "Start the gain tradeoff with a gentle controller."),
        NextRunSuggestion("configs/lab02_pid/p_high_gain.yaml", "Compare speed against overshoot and control force."),
        NextRunSuggestion("configs/lab02_pid/interactive_disturbance.yaml", "Disturb the plant and tune PID values live."),
    ),
    "configs/lab02_pid/p_low_gain.yaml": (
        NextRunSuggestion("configs/lab02_pid/p_high_gain.yaml", "Increase proportional gain and compare rise time."),
        NextRunSuggestion("configs/lab02_pid/pd_damped.yaml", "Add damping after observing a stronger P response."),
    ),
    "configs/lab02_pid/p_high_gain.yaml": (
        NextRunSuggestion("configs/lab02_pid/pd_damped.yaml", "Use derivative action to calm overshoot."),
        NextRunSuggestion("configs/lab02_pid/saturation_limit.yaml", "Limit the actuator and inspect clipped force."),
    ),
    "configs/lab02_pid/pd_damped.yaml": (
        NextRunSuggestion("configs/lab02_pid/measurement_noise.yaml", "Check how derivative damping reacts to noisy measurements."),
        NextRunSuggestion("configs/lab02_pid/control_delay.yaml", "See how delayed feedback changes the same loop."),
    ),
    "configs/lab02_pid/saturation_limit.yaml": (
        NextRunSuggestion("configs/lab02_pid/pid_with_windup.yaml", "Add integral action and observe windup under limits."),
        NextRunSuggestion("configs/lab02_pid/pid_anti_windup.yaml", "Compare the same limit with anti-windup enabled."),
    ),
    "configs/lab02_pid/pid_with_windup.yaml": (
        NextRunSuggestion("configs/lab02_pid/pid_anti_windup.yaml", "Run the direct fix and compare overshoot."),
        NextRunSuggestion("configs/lab02_pid/saturation_limit.yaml", "Revisit force saturation without integral buildup."),
    ),
    "configs/lab02_pid/pid_anti_windup.yaml": (
        NextRunSuggestion("configs/lab02_pid/pid_with_windup.yaml", "Compare against the windup case side by side."),
        NextRunSuggestion("configs/lab02_pid/interactive_disturbance.yaml", "Tune gains live and mark useful observations."),
    ),
    "configs/lab02_pid/measurement_noise.yaml": (
        NextRunSuggestion("configs/lab02_pid/pd_damped.yaml", "Remove the noise and compare derivative behavior."),
        NextRunSuggestion("configs/lab02_pid/control_delay.yaml", "Switch from noisy sensing to delayed actuation."),
    ),
    "configs/lab02_pid/control_delay.yaml": (
        NextRunSuggestion("configs/lab02_pid/default.yaml", "Return to the baseline to isolate delay effects."),
        NextRunSuggestion("configs/lab02_pid/pd_damped.yaml", "Try damping as a stabilizing change."),
    ),
    "configs/lab02_pid/interactive_disturbance.yaml": (
        NextRunSuggestion("configs/lab02_pid/p_high_gain.yaml", "Save an aggressive gain comparison."),
        NextRunSuggestion("configs/lab02_pid/pd_damped.yaml", "Save the damped response for comparison."),
        NextRunSuggestion("configs/lab02_pid/pid_anti_windup.yaml", "Inspect the anti-windup case after live tuning."),
    ),
    "configs/lab03_2dof/default.yaml": (
        NextRunSuggestion("configs/lab03_2dof/step.yaml", "Use the abrupt profile as a baseline."),
        NextRunSuggestion("configs/lab03_2dof/minimum_jerk.yaml", "Compare against a smooth motion profile."),
        NextRunSuggestion("configs/lab03_2dof/joint_space_2dof.yaml", "Move from the 1D tracker to the two-link arm."),
    ),
    "configs/lab03_2dof/step.yaml": (
        NextRunSuggestion("configs/lab03_2dof/trapezoidal.yaml", "Replace the abrupt step with limited velocity and acceleration."),
        NextRunSuggestion("configs/lab03_2dof/minimum_jerk.yaml", "Compare against a smooth start/stop profile."),
    ),
    "configs/lab03_2dof/trapezoidal.yaml": (
        NextRunSuggestion("configs/lab03_2dof/step.yaml", "Use the step profile as the abrupt baseline."),
        NextRunSuggestion("configs/lab03_2dof/s_curve.yaml", "Smooth jerk transitions and compare effort."),
    ),
    "configs/lab03_2dof/minimum_jerk.yaml": (
        NextRunSuggestion("configs/lab03_2dof/trapezoidal.yaml", "Compare two smooth motion profiles."),
        NextRunSuggestion("configs/lab03_2dof/s_curve.yaml", "Inspect whether S-curve effort is calmer."),
    ),
    "configs/lab03_2dof/s_curve.yaml": (
        NextRunSuggestion("configs/lab03_2dof/step.yaml", "Return to the abrupt baseline for contrast."),
        NextRunSuggestion("configs/lab03_2dof/minimum_jerk.yaml", "Compare smoothness and tracking error."),
    ),
    "configs/lab03_2dof/joint_space_2dof.yaml": (
        NextRunSuggestion("configs/lab03_2dof/task_space_2dof.yaml", "Move from joint targets to hand-position control.", "task"),
        NextRunSuggestion("configs/lab03_2dof/singularity_2dof.yaml", "Approach the workspace edge and inspect conditioning.", "singularity"),
    ),
    "configs/lab03_2dof/task_space_2dof.yaml": (
        NextRunSuggestion("configs/lab03_2dof/singularity_2dof.yaml", "Stress the Jacobian near a difficult posture.", "singularity"),
        NextRunSuggestion("configs/lab03_2dof/interactive_2dof.yaml", "Move the hand target live with sliders.", "task"),
    ),
    "configs/lab03_2dof/singularity_2dof.yaml": (
        NextRunSuggestion("configs/lab03_2dof/dls_singularity_2dof.yaml", "Add damped least-squares and compare joint speed.", "dls"),
        NextRunSuggestion("configs/lab03_2dof/task_space_2dof.yaml", "Return to the regular task-space reach.", "task"),
    ),
    "configs/lab03_2dof/dls_singularity_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Let damping rise automatically near poor conditioning.",
            "dls",
        ),
        NextRunSuggestion("configs/lab03_2dof/singularity_2dof.yaml", "Compare DLS against the undamped singularity case.", "singularity"),
    ),
    "configs/lab03_2dof/condition_aware_dls_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml",
            "Start damping earlier and compare joint speed.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml",
            "Delay damping and compare task error.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "Keep the same damping schedule but constrain actuator effort.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml",
            "Move the target inward to compare conditioning with the same schedule.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml",
            "Keep the edge target but approach it from a mirrored arm branch.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml",
            "Keep the target but add a short shoulder disturbance pulse.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml",
            "Add shoulder and elbow pulses at different times to test repeated recovery.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml",
            "Keep the target and schedule but command the motion faster.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml",
            "Keep the same command but tighten the joint-speed limit.",
            "dls",
        ),
        NextRunSuggestion("configs/lab03_2dof/dls_singularity_2dof.yaml", "Compare against fixed damping on the same target.", "dls"),
    ),
    "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml",
            "Use the same target with a later damping schedule.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default condition-aware schedule.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "Keep the schedule but lower actuator limits.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_late_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_early_2dof.yaml",
            "Compare against earlier, stronger damping.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default condition-aware schedule.",
            "dls",
        ),
        NextRunSuggestion("configs/lab03_2dof/interactive_2dof.yaml", "Move the target live and watch conditioning.", "task"),
    ),
    "configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_edge_target_2dof.yaml",
            "Move the same controller toward the workspace edge.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the interactive default near-edge case.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_edge_target_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_inner_target_2dof.yaml",
            "Move back inward and compare condition scale.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "Keep the edge target and constrain actuator effort.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml",
            "Keep the edge target and compare a different elbow branch.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml",
            "Keep the edge target but command it faster.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml",
            "Keep the edge target and isolate the joint-speed limit.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml",
            "Keep the edge target and add a joint disturbance pulse.",
            "dls_disturbance",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_lower_path_2dof.yaml",
            "Mirror the initial posture and compare the lower hand path.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default condition-aware DLS branch.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_lower_path_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_upper_path_2dof.yaml",
            "Mirror the initial posture and compare the upper hand path.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default condition-aware DLS branch.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml",
            "Move the same pulse to the elbow and compare recovery.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml",
            "Apply shoulder then elbow pulses and compare the second recovery.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the undisturbed condition-aware DLS case.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml",
            "Move the same pulse to the shoulder and compare recovery.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml",
            "Apply shoulder then elbow pulses and compare the second recovery.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the undisturbed condition-aware DLS case.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_staggered_disturbance_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_shoulder_disturbance_2dof.yaml",
            "Isolate the first shoulder pulse by running the single-pulse case.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_elbow_disturbance_2dof.yaml",
            "Isolate the second elbow pulse by running the single-pulse case.",
            "dls_disturbance",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the undisturbed condition-aware DLS case.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml",
            "Use the same target with more actuator effort available.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default torque limits.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_high_torque_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_torque_2dof.yaml",
            "Constrain actuator effort and compare task error.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default torque limits.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_slow_command_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml",
            "Use the same target with a faster hand command.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default command speed.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_fast_command_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_slow_command_2dof.yaml",
            "Slow the same target down and compare task error.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml",
            "Keep the timing but tighten joint-speed clipping.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default command speed.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_high_joint_speed_2dof.yaml",
            "Relax only the joint-speed limit and compare hand error.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default joint-speed limit.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_high_joint_speed_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_low_joint_speed_2dof.yaml",
            "Tighten only the joint-speed limit and compare clipping.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the default joint-speed limit.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_direct_retarget_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml",
            "Route through the inner waypoint and compare speed, torque, and damping.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_fixed_speed_retarget_2dof.yaml",
            "Hold one fixed task-speed limit for the same direct retarget path.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the single near-edge target.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_direct_retarget_2dof.yaml",
            "Remove the inner waypoint and compare the direct edge path.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "Return to the single near-edge target.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_fixed_speed_retarget_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml",
            "Lower the task-speed limit near the edge and compare tracking error.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_direct_retarget_2dof.yaml",
            "Return to the direct retarget reference.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml": (
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_fixed_speed_retarget_2dof.yaml",
            "Remove the speed schedule and compare against one fixed task-speed limit.",
            "dls",
        ),
        NextRunSuggestion(
            "configs/lab03_2dof/condition_aware_dls_inward_retarget_2dof.yaml",
            "Compare speed scheduling against changing the target path itself.",
            "dls",
        ),
    ),
    "configs/lab03_2dof/interactive_tracking.yaml": (
        NextRunSuggestion("configs/lab03_2dof/step.yaml", "Save the abrupt tracking response for comparison."),
        NextRunSuggestion("configs/lab03_2dof/minimum_jerk.yaml", "Save a smooth trajectory comparison."),
        NextRunSuggestion("configs/lab03_2dof/joint_space_2dof.yaml", "Move next to the two-link arm."),
    ),
    "configs/lab03_2dof/interactive_2dof.yaml": (
        NextRunSuggestion("configs/lab03_2dof/task_space_2dof.yaml", "Save the deterministic task-space reach.", "task"),
        NextRunSuggestion("configs/lab03_2dof/singularity_2dof.yaml", "Compare against a near-singular reach.", "singularity"),
        NextRunSuggestion("configs/lab03_2dof/dls_singularity_2dof.yaml", "Compare with damped least-squares enabled.", "dls"),
    ),
    "configs/lab04_panda/neutral_hold.yaml": (
        NextRunSuggestion("configs/lab04_panda/joint_pd.yaml", "Move one joint after confirming stable hold."),
        NextRunSuggestion("configs/lab04_panda/cartesian_reach.yaml", "Move the Panda hand toward a Cartesian target.", "cartesian_reach"),
    ),
    "configs/lab04_panda/neutral_hold_30s.yaml": (
        NextRunSuggestion("configs/lab04_panda/joint_pd.yaml", "Move one joint after the 30-second hold is stable."),
        NextRunSuggestion("configs/lab04_panda/cartesian_reach.yaml", "Move from stability hold to Cartesian hand targeting.", "cartesian_reach"),
    ),
    "configs/lab04_panda/joint_pd.yaml": (
        NextRunSuggestion("configs/lab04_panda/trajectory_tracking.yaml", "Try a different Panda joint and trajectory shape."),
        NextRunSuggestion("configs/lab04_panda/cartesian_reach.yaml", "Switch from joint motion to hand-position control.", "cartesian_reach"),
    ),
    "configs/lab04_panda/trajectory_tracking.yaml": (
        NextRunSuggestion("configs/lab04_panda/joint_pd.yaml", "Compare against the minimum-jerk joint path."),
        NextRunSuggestion("configs/lab04_panda/reach_x.yaml", "Watch which joint motion changes hand X.", "cartesian"),
    ),
    "configs/lab04_panda/reach_x.yaml": (
        NextRunSuggestion("configs/lab04_panda/cartesian_reach.yaml", "Target the hand position directly.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/interactive_joint_hold.yaml", "Nudge the joint target live."),
    ),
    "configs/lab04_panda/cartesian_reach.yaml": (
        NextRunSuggestion("configs/lab04_panda/cartesian_soft.yaml", "Lower reach aggressiveness and compare error.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/cartesian_stiff.yaml", "Raise reach aggressiveness and compare effort.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/interactive_cartesian_reach.yaml", "Move the hand target live.", "cartesian_reach"),
    ),
    "configs/lab04_panda/cartesian_soft.yaml": (
        NextRunSuggestion("configs/lab04_panda/cartesian_stiff.yaml", "Run the direct stiff comparison.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/interactive_cartesian_reach.yaml", "Tune target and gain live.", "cartesian_reach"),
    ),
    "configs/lab04_panda/cartesian_stiff.yaml": (
        NextRunSuggestion("configs/lab04_panda/cartesian_soft.yaml", "Run the direct soft comparison.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/interactive_cartesian_reach.yaml", "Tune target and gain live.", "cartesian_reach"),
    ),
    "configs/lab04_panda/interactive_cartesian_reach.yaml": (
        NextRunSuggestion("configs/lab04_panda/cartesian_soft.yaml", "Save the soft reach as a controlled comparison.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/cartesian_stiff.yaml", "Save the stiff reach as a controlled comparison.", "cartesian_reach"),
        NextRunSuggestion("configs/lab04_panda/impedance_wall.yaml", "Move from free-space reach to wall response.", "wall"),
    ),
    "configs/lab04_panda/interactive_joint_hold.yaml": (
        NextRunSuggestion("configs/lab04_panda/joint_pd.yaml", "Save a deterministic joint-path response."),
        NextRunSuggestion("configs/lab04_panda/cartesian_reach.yaml", "Switch from joint target to hand target.", "cartesian_reach"),
    ),
    "configs/lab04_panda/impedance_wall.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_soft.yaml", "Start the wall stiffness comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_stiff.yaml", "Compare higher stiffness and retreat.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_low_damping.yaml", "Isolate damping with fixed stiffness.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_near.yaml", "Move the wall closer to isolate contact timing.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_slow_approach.yaml", "Slow the same wall approach to isolate damping force.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_shallow_push.yaml", "Command a shallow target push through the wall.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_low_retreat.yaml", "Isolate force-to-retreat gain.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_contact_cycle.yaml", "Cycle the target through and back out of the wall.", "wall_compare"),
    ),
    "configs/lab04_panda/wall_soft.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_stiff.yaml", "Run the direct stiff wall comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_low_damping.yaml", "Keep stiffness fixed and reduce damping.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune wall position and stiffness live.", "wall"),
    ),
    "configs/lab04_panda/wall_stiff.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_soft.yaml", "Run the direct soft wall comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_damping.yaml", "Keep stiffness fixed and raise damping.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune wall position and stiffness live.", "wall"),
    ),
    "configs/lab04_panda/wall_low_damping.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_high_damping.yaml", "Compare the same wall with stronger damping.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_soft.yaml", "Return to the lower-stiffness wall comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_near.yaml", "Keep gains moderate and move the wall closer.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_low_retreat.yaml", "Lower force-to-retreat gain with the same wall force.", "wall_compare"),
    ),
    "configs/lab04_panda/wall_high_damping.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_low_damping.yaml", "Compare the same wall with less damping.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_stiff.yaml", "Compare against the higher-stiffness wall.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_far.yaml", "Keep gains moderate and move the wall farther.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_retreat.yaml", "Raise force-to-retreat gain with the same wall force.", "wall_compare"),
    ),
    "configs/lab04_panda/wall_near.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_far.yaml", "Compare the same wall placed farther away.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_damping.yaml", "Return to damping-only comparison.", "wall_compare"),
    ),
    "configs/lab04_panda/wall_far.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_near.yaml", "Compare the same wall placed closer.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune wall position live.", "wall"),
    ),
    "configs/lab04_panda/wall_slow_approach.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_fast_approach.yaml", "Compare the same wall with a faster approach.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_contact_cycle.yaml", "Repeat contact and release with waypoint targets.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_damping.yaml", "Keep speed fixed next and isolate damping.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune the target and wall live.", "wall"),
    ),
    "configs/lab04_panda/wall_fast_approach.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_slow_approach.yaml", "Compare the same wall with a slower approach.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_deep_push.yaml", "Keep wall settings fixed and command a deeper target push.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_contact_cycle.yaml", "Repeat contact and release with waypoint targets.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_retreat.yaml", "Increase retreat gain to counter the fast contact.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune the target and wall live.", "wall"),
    ),
    "configs/lab04_panda/wall_shallow_push.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_deep_push.yaml", "Command the same wall much deeper past the wall.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_contact_cycle.yaml", "Add target release and re-entry after the push.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Recreate target depth manually with Target X buttons.", "wall"),
    ),
    "configs/lab04_panda/wall_deep_push.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_shallow_push.yaml", "Return to the shallow target push baseline.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_retreat.yaml", "Increase retreat gain to resist the deeper push.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune target depth and retreat gain live.", "wall"),
    ),
    "configs/lab04_panda/wall_contact_cycle.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_shallow_push.yaml", "Simplify to one shallow target push.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_deep_push.yaml", "Simplify to one deep target push.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_slow_approach.yaml", "Return to a single slow approach for a simpler baseline.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_fast_approach.yaml", "Compare against a single fast approach.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Recreate contact and release manually with Target X buttons.", "wall"),
    ),
    "configs/lab04_panda/wall_low_retreat.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_high_retreat.yaml", "Compare the same wall with stronger force-to-retreat gain.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_low_damping.yaml", "Return to the damping-only comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune retreat gain live.", "wall"),
    ),
    "configs/lab04_panda/wall_high_retreat.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_low_retreat.yaml", "Compare the same wall with weaker force-to-retreat gain.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_near.yaml", "Move the same wall closer to change contact timing.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/interactive_virtual_wall.yaml", "Tune retreat gain live.", "wall"),
    ),
    "configs/lab04_panda/interactive_virtual_wall.yaml": (
        NextRunSuggestion("configs/lab04_panda/wall_soft.yaml", "Save a deterministic soft wall comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_stiff.yaml", "Save a deterministic stiff wall comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_damping.yaml", "Save a deterministic damping comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_near.yaml", "Save a deterministic wall-position comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_fast_approach.yaml", "Save a deterministic approach-speed comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_deep_push.yaml", "Save a deterministic target-depth comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_contact_cycle.yaml", "Save repeated contact and release as a deterministic comparison.", "wall_compare"),
        NextRunSuggestion("configs/lab04_panda/wall_high_retreat.yaml", "Save a deterministic retreat-gain comparison.", "wall_compare"),
    ),
}


def write_run_report(
    output_path: str | Path,
    *,
    update_index: bool = True,
    completion_status: str | None = None,
) -> Path:
    output = Path(output_path)
    with mutable_run_publication(output) as publication:
        record = _report_artifact_record(publication.root)
        _assert_report_write_allowed(record)
        if record is None:
            raise RuntimeError("The running output has no trusted artifact snapshot.")
        publication.root_pin.assert_current()
        summary = record.summary
        notes = _publication_text(publication, ("notes.md",))
        config: dict[str, Any] = {}
        plots = sorted(record.plot_paths)
        interaction_events = _display_interaction_events(record.interaction_events)
        learner_snapshot = _publication_json(
            publication,
            ("learner_snapshot.json",),
        )
        completion_evidence, completion_decision = _run_report_completion(
            publication.root,
            summary,
            completion_status=completion_status,
            record=record,
        )
        summary = _trusted_behavior_summary(
            summary,
            _report_completion_target(record, summary),
        )
        config_section = record.manifest.get("config")
        resolved = config_section.get("resolved") if isinstance(config_section, dict) else None
        if isinstance(resolved, dict):
            config = deepcopy(resolved)

        worksheet = _render_worksheet(
            publication.root,
            summary,
            notes,
            plots,
            interaction_events,
            config,
            completion_decision,
            completion_evidence,
        )
        publication.write_text(("worksheet.md",), worksheet)
        html = _render_report(
            publication.root,
            summary,
            notes,
            plots,
            interaction_events,
            config,
            learner_snapshot,
            completion_decision,
            completion_evidence,
        )
        report_path = publication.write_text(("report.html",), html)
    if update_index:
        write_outputs_index(output.parent)
    return report_path


def write_outputs_index(outputs_root: str | Path) -> Path:
    root = Path(outputs_root)
    root.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        try:
            with mutable_collection_publication(root) as publication:
                runs = _discover_runs(publication.root)
                publication.root_pin.assert_current()
                return publication.write_text(
                    ("index.html",),
                    _render_outputs_index(publication.root, runs),
                )
        except OutputPublicationBusyError:
            if attempt == 19:
                raise
            time.sleep(min(0.025 * (2**attempt), 0.25))
    raise AssertionError("unreachable output-index publication retry state")


def _run_report_completion(
    output: Path,
    summary: dict[str, Any],
    *,
    completion_status: str | None,
    record: ArtifactRecord | None,
) -> tuple[CompletionEvidence, CompletionDecision]:
    """Evaluate report completion from producer facts or a strict saved snapshot."""

    catalog = ScenarioCatalog.default()
    if record is not None:
        target = _catalog_target_or_none(catalog, record.scenario_id)
        if (
            target is None
            and record.completion_evidence.record_kind
            == CompletionRecordKind.LEGACY_SUMMARY
        ):
            target = target_from_legacy_summary(catalog, record.summary)
        evidence = record.completion_evidence
        if (
            completion_status is not None
            and evidence.record_kind == CompletionRecordKind.MANIFEST_V1
        ):
            # A running manifest has already digest-published the producer
            # evidence.  Only the prospective terminal status is overridden;
            # raw globs/events never gain completion credit.
            evidence = replace(evidence, status=completion_status)
        decision = evaluate_completion(
            target.completion if target is not None else None,
            evidence,
        )
        return evidence, decision

    scenario_id = stable_scenario_id(
        str(summary.get("lab_name") or ""),
        str(summary.get("config_path") or "") or None,
    )
    target = _catalog_target_or_none(catalog, scenario_id)
    evidence = CompletionEvidence(CompletionRecordKind.MISSING)
    return evidence, evaluate_completion(
        target.completion if target is not None else None,
        evidence,
    )


def _report_artifact_record(output: Path) -> ArtifactRecord | None:
    return next(
        (
            item
            for item in ArtifactRepository(output.parent).list_runs()
            if item.path.name == output.name
        ),
        None,
    )


def assert_run_artifacts_mutable(output_path: str | Path) -> ArtifactRecord | None:
    """Refuse any run-local artifact rewrite after terminal publication."""

    assert_output_tree_mutable(output_path)
    record = _report_artifact_record(Path(output_path))
    _assert_report_write_allowed(record)
    return record


def _assert_report_write_allowed(record: ArtifactRecord | None) -> None:
    if (
        record is not None
        and record.marker_name == "manifest.json"
        and record.status in TERMINAL_STATUSES
    ):
        raise RuntimeError(
            "Refusing to rewrite report artifacts after terminal manifest publication."
        )


def _catalog_target_or_none(catalog: ScenarioCatalog, target_id: str) -> Any | None:
    try:
        return catalog.get_target(target_id)
    except KeyError:
        return None


def _report_completion_target(
    record: ArtifactRecord | None,
    summary: dict[str, Any],
) -> Any | None:
    catalog = ScenarioCatalog.default()
    if record is not None:
        target = _catalog_target_or_none(catalog, record.scenario_id)
        if (
            target is None
            and record.completion_evidence.record_kind
            == CompletionRecordKind.LEGACY_SUMMARY
        ):
            return target_from_legacy_summary(catalog, record.summary)
        return target
    scenario_id = stable_scenario_id(
        str(summary.get("lab_name") or ""),
        str(summary.get("config_path") or "") or None,
    )
    return _catalog_target_or_none(catalog, scenario_id)


def _worksheet_completion_lines(decision: CompletionDecision) -> list[str]:
    verdict = "Complete" if decision.complete else "Incomplete"
    reasons = ", ".join(reason.value for reason in decision.reasons)
    return [
        "## Completion",
        "",
        f"- Completion verdict: {verdict}",
        f"- Completion contract version: {decision.contract_version}",
        f"- Completion reason: {decision.primary_reason.value}",
        f"- Completion reasons: {reasons}",
        "",
    ]


def _completion_section(decision: CompletionDecision) -> str:
    verdict = "Complete" if decision.complete else "Incomplete"
    reasons = ", ".join(reason.value for reason in decision.reasons)
    return (
        '<section class="completion-verdict">'
        "<h2>Completion</h2>"
        f"<p><strong>Completion verdict:</strong> {escape(verdict)}</p>"
        f"<p><strong>Completion contract version:</strong> {decision.contract_version}</p>"
        f"<p><strong>Completion reason:</strong> {escape(decision.primary_reason.value)}</p>"
        f"<p><strong>Completion reasons:</strong> {escape(reasons)}</p>"
        "</section>"
    )


def _render_worksheet(
    output: Path,
    summary: dict[str, Any],
    notes: str,
    plots: list[Path],
    interaction_events: list[dict[str, Any]],
    config: dict[str, Any],
    completion_decision: CompletionDecision,
    completion_evidence: CompletionEvidence,
) -> str:
    guide = guide_for_run_summary(summary)
    lines: list[str] = [
        "# MCLab Learner Worksheet",
        "",
        "## Read-only Evidence",
        "",
        "- This worksheet is digest-published in manifest.json. Do not edit it or any file inside the saved-run folder.",
        "- Copy the prompts below into personal or course notes stored outside the saved-run folder, then record your answers there.",
        "",
        "## Run",
        "",
        f"- Run folder: {_markdown_inline(output.name)}",
        f"- Lab: {_markdown_inline(summary.get('lab_name') or output.name)}",
        f"- Config: {_markdown_inline(summary.get('config_path') or summary.get('config_name') or 'n/a')}",
        f"- Duration [s]: {_markdown_inline(summary.get('duration', 'n/a'))}",
        f"- Samples: {_markdown_inline(summary.get('samples', 'n/a'))}",
        "- Report: report.html",
        "",
    ]
    lines.extend(_worksheet_completion_lines(completion_decision))
    lines.extend(_worksheet_learning_guide_lines(guide, summary, config))
    lines.extend(_worksheet_course_position_lines(summary))
    lines.extend(
        _worksheet_course_experience_coverage_lines(
            output,
            completion_evidence=completion_evidence,
        )
    )
    lines.extend(
        _worksheet_mission_evidence_lines(
            summary,
            interaction_events,
            plots,
            config,
            completion_decision,
        )
    )
    lines.extend(
        _worksheet_challenge_evidence_lines(
            summary,
            interaction_events,
            plots,
            config,
            completion_decision,
        )
    )
    lines.extend(_worksheet_pairs_section("Key Parameters", _config_highlight_pairs(config)))
    lines.extend(_worksheet_key_moments_lines(summary))
    lines.extend(_worksheet_pairs_section("Summary Values", list(summary.items())))
    lines.extend(_worksheet_plot_review_lines(output, plots))
    lines.extend(_worksheet_observation_timeline_lines(interaction_events))
    lines.extend(_worksheet_observation_lines(interaction_events, config))
    lines.extend(_worksheet_review_checklist(interaction_events, config))
    lines.extend(_worksheet_activity_mix_lines(interaction_events, config))
    lines.extend(_worksheet_preset_comparison_lines(interaction_events, config))
    lines.extend(_worksheet_next_experiment_lines(summary, config))
    lines.extend(_worksheet_notes_lines(notes))
    lines.extend(_worksheet_artifact_lines(output, plots))
    return "\n".join(lines).rstrip() + "\n"


def _worksheet_learning_guide_lines(
    guide: RunGuide | None,
    summary: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> list[str]:
    lines = ["## Learning Guide", ""]
    completion_text = _run_completion_text(summary)
    if guide is None:
        lines.extend(["- No configured guide was found for this run.", f"- {completion_text}", ""])
        return lines
    rows: list[tuple[str, Any]] = [
        ("Title", guide.title),
        ("Done when", completion_text.removeprefix("Done when:").strip()),
        ("Mission", mission_prompt_for_guide(guide).removeprefix("Mission:").strip()),
        ("Playbook", playbook_for_guide(guide).removeprefix("Playbook:").strip()),
        ("Start steps", _start_steps_text(guide, config)),
        ("Counts as control", _control_credit_text_for_config(config)),
        ("Challenge", challenge_prompt_for_guide(guide).removeprefix("Challenge:").strip()),
        ("Try", guide.try_this),
        ("Change", guide.change),
        ("Prediction", prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()),
        ("Question", question_for_guide(guide).removeprefix("Question:").strip()),
        ("Watch", guide.watch),
        ("Next", guide.next_step),
    ]
    lines.extend(_worksheet_mapping_lines(dict((label, value) for label, value in rows if value)))
    legend = viewer_legend_for_guide(guide)
    if legend:
        lines.append("- Viewer legend:")
        for label, description in legend:
            lines.append(f"  - {_markdown_inline(label)}: {_markdown_inline(description)}")
    lines.append("")
    return lines


def _worksheet_course_position_lines(summary: dict[str, Any]) -> list[str]:
    position = _course_position_for_summary(summary)
    if position is None:
        return []
    step, _step_number, milestone = position
    rows: list[tuple[str, Any]] = [
        ("Milestone", milestone),
        ("Learning path step", step.title),
        ("Step focus", step.description),
        ("Done when", _learning_path_completion_text(step).removeprefix("Done when:").strip()),
        ("Repeat command", _learning_path_command(step)),
    ]
    lines = ["## Course Position", ""]
    lines.extend(_worksheet_mapping_lines(dict(rows)))
    lines.append("")
    return lines


def _worksheet_course_experience_coverage_lines(
    output: Path,
    *,
    completion_evidence: CompletionEvidence | None = None,
) -> list[str]:
    overrides = (
        {output.name: completion_evidence}
        if completion_evidence is not None
        else None
    )
    runs = _discover_runs(output.parent, evidence_overrides=overrides)
    records = _experience_coverage_records_for_index(runs)
    repair_items = _experience_coverage_repair_items(runs)
    next_item = next_experience_coverage_item(records)
    lines = [
        "## Course Experience Coverage",
        "",
        f"- Summary: {_markdown_inline(experience_coverage_summary_text(records))}",
    ]
    if next_item is None:
        lines.append("- Next experience: All core experience types have saved evidence.")
    else:
        lines.extend(
            [
                f"- Next experience: {_markdown_inline(next_item.label)}",
                f"- Next mode: {_markdown_inline(experience_coverage_item_mode(next_item))}",
                f"- Next action: {_markdown_inline(next_item.next_step)}",
                f"- Evidence needed: {_markdown_inline(experience_coverage_item_evidence(next_item))}",
                f"- Next command: {_markdown_inline(next_item.command)}",
            ]
        )
    lines.append("- Coverage map:")
    for status in experience_coverage_statuses(records):
        state = "Next" if status.next_missing else "Done" if status.covered else "Missing"
        lines.append(
            f"  - {_markdown_inline(status.item.label)}: {_markdown_inline(state)}; "
            f"mode: {_markdown_inline(experience_coverage_item_mode(status.item))}; "
            f"focus: {_markdown_inline(status.item.next_step)}; "
            f"evidence: {_markdown_inline(experience_coverage_item_evidence(status.item))}"
        )
        repair = repair_items.get(status.item.key)
        if repair:
            repair_status, run_name, _report, command = repair
            lines.append(
                f"    Review repair: {_markdown_inline(repair_status)} in {_markdown_inline(run_name)}; "
                f"rerun {_markdown_inline(command)}"
            )
    lines.append("")
    return lines


def _worksheet_mission_evidence_lines(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Path],
    config: dict[str, Any],
    completion_decision: CompletionDecision,
) -> list[str]:
    lines = ["## Mission Evidence", ""]
    lines.extend(
        _worksheet_mapping_lines(
            dict(
                _mission_evidence_items(
                    summary,
                    events,
                    plots,
                    config,
                    completion_decision=completion_decision,
                )
            )
        )
    )
    lines.append("")
    return lines


def _worksheet_challenge_evidence_lines(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Path],
    config: dict[str, Any],
    completion_decision: CompletionDecision,
) -> list[str]:
    lines = ["## Challenge Evidence", ""]
    lines.extend(
        _worksheet_mapping_lines(
            dict(
                _challenge_evidence_items(
                    summary,
                    events,
                    plots,
                    config,
                    completion_decision=completion_decision,
                )
            )
        )
    )
    lines.append("")
    return lines


def _worksheet_pairs_section(title: str, pairs: list[tuple[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not pairs:
        lines.extend(["- No values saved.", ""])
        return lines
    lines.extend(_worksheet_mapping_lines(dict(pairs)))
    lines.append("")
    return lines


def _worksheet_key_moments_lines(summary: dict[str, Any]) -> list[str]:
    moments = _key_moment_rows(summary)
    if not moments:
        return []
    lines = [
        "## Key Moments",
        "",
        "- Use these timestamps with the saved plots before reading every trace.",
    ]
    for title, time_value, value_label, value, detail in moments:
        lines.append(
            f"- {_markdown_inline(title)}: time {_markdown_inline(time_value)} s; "
            f"{_markdown_inline(value_label)}: {_markdown_inline(value)}. {_markdown_inline(detail)}"
        )
    lines.append("")
    return lines


def _worksheet_observation_timeline_lines(events: list[dict[str, Any]]) -> list[str]:
    items = _observation_timeline_items(events)
    if not items:
        return []
    lines = ["## Observation Timeline", ""]
    for item in items:
        details = [
            f"Prediction: {_markdown_inline(item['prediction'])}" if item["prediction"] else "Prediction: missing",
            f"Outcome: {_markdown_inline(item['outcome'])}" if item["outcome"] else "Outcome: missing",
        ]
        if item["note"]:
            details.append(f"Note evidence: {_markdown_inline(item['note'])}")
        if item["challenge_proof"]:
            details.append(f"Challenge proof: {_markdown_inline(item['challenge_proof'])}")
        if item["status"]:
            details.append(f"Status: {_markdown_inline(item['status'])}")
        lines.append(f"- Observation {item['index']} at {_markdown_inline(item['time'])} s: " + "; ".join(details))
    lines.append("")
    return lines


def _worksheet_observation_lines(events: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    markers = [event for event in events if _is_observation_marker(event)]
    lines = ["## Observation Markers", ""]
    if not markers:
        lines.append("- No observation markers saved yet.")
        if _has_observation_workflow(events, config):
            lines.append("- Next: write a prediction, use one learner control, then press Mark observation.")
        else:
            lines.append("- Next: use the Plot Review and Challenge Evidence sections for this auto-run scenario.")
            lines.append("- Hands-on marker evidence comes from interactive scenarios with buttons, sliders, or presets.")
        lines.append("")
        return lines

    lines.extend(_worksheet_evidence_review_cue_lines(events, markers, _report_learner_control_phrase(config)))

    for marker_index, marker in enumerate(markers, start=1):
        payload = marker.get("value")
        value = payload if isinstance(payload, dict) else {}
        lines.extend(
            [
                f"### Observation {marker_index}",
                "",
                f"- Time [s]: {_markdown_inline(marker.get('time', 'n/a'))}",
            ]
        )
        scalar_rows = {
            "Question": value.get("question"),
            "Prediction": value.get("prediction"),
            "Prediction outcome": value.get("outcome"),
            "Evidence prompt": value.get("evidence_prompt"),
            "Challenge proof": value.get("challenge_proof"),
            "Learner note": value.get("note"),
        }
        for label, text in scalar_rows.items():
            if str(text or "").strip():
                lines.append(f"- {label}: {_markdown_inline(text)}")
        note_items = _note_evidence_items(value.get("note"))
        if len(note_items) > 1:
            lines.append("- Learner note evidence:")
            for item in note_items:
                lines.append(f"  - {_markdown_inline(item)}")
        for label, key in (
            ("Changed sliders", "changed_sliders"),
            ("Current sliders", "sliders"),
            ("Live status", "status"),
        ):
            values = value.get(key)
            if isinstance(values, dict) and values:
                lines.append(f"- {label}:")
                lines.extend(_worksheet_mapping_lines(values, indent=2))
        lines.append("")
    return lines


def _worksheet_evidence_review_cue_lines(
    events: list[dict[str, Any]],
    markers: list[dict[str, Any]],
    learner_control_phrase: str = "",
) -> list[str]:
    lines = [
        "### Evidence Review Cue",
        "",
        "- Use this read-only review guide before moving to the next experiment.",
        "- Record any follow-up answer in personal or course notes stored outside the saved-run folder.",
    ]
    for label, value in _evidence_review_cue_items(events, markers, learner_control_phrase=learner_control_phrase):
        lines.append(f"- {label}: {_markdown_inline(value)}")
    lines.append("")
    return lines


def _worksheet_review_checklist(events: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    pending_outcomes = max(0, predictions - outcomes)
    required_labels, required_tried, next_required = _required_preset_progress(config, events)
    has_observation_workflow = _has_observation_workflow(events, config)
    lines = [
        "## Review Checklist",
        "",
        f"- Observation markers: {_markdown_inline(markers)}",
        f"- Predictions: {_markdown_inline(predictions)}",
        f"- Prediction outcomes: {_markdown_inline(outcomes)}",
        f"- Learner notes: {_markdown_inline(notes)}",
    ]
    if required_labels:
        lines.append(f"- Required presets tried: {_markdown_inline(f'{len(required_tried)}/{len(required_labels)}')}")
    if pending_outcomes:
        lines.append(
            f"- Outcome review pending: {_markdown_inline(pending_outcomes)} "
            "prediction(s) still need Matched, Partly matched, or Surprised."
        )
    if not has_observation_workflow:
        lines.extend(
            [
                "- Review prompt: Answer the Prediction prompt in personal or course notes outside the saved-run folder before reading the plots.",
                "- Review prompt: Use Plot Review and Challenge Evidence to decide whether the result matched your expectation.",
                "- Review prompt: Record Matched, Partly matched, or Surprised in personal or course notes outside the saved-run folder.",
                "- Review prompt: Run one Suggested Next Experiment or the Comparison Batch for a controlled comparison.",
                "",
            ]
        )
        return lines
    if markers <= 0:
        if next_required:
            lines.append(
                f"- Review prompt: Rerun the interactive scenario, try required preset {_markdown_inline(next_required)}, "
                "watch live status, then use Mark observation."
            )
        lines.extend(
            [
                "- Review prompt: Rerun the interactive scenario and save one observation marker with a prediction and note.",
                "- Review prompt: Capture one live status or note during that rerun before moving to the next scenario.",
            ]
        )
    elif next_required:
        lines.extend(
            [
                f"- Review prompt: Rerun the interactive scenario, try required preset {_markdown_inline(next_required)}, "
                "watch live status, then use Mark observation.",
                "- Review prompt: Compare the required preset response with the plots in report.html.",
            ]
        )
    else:
        lines.extend(
            [
                "- Review prompt: Compare the latest saved prediction with the plots in report.html.",
                "- Review prompt: Review every saved prediction outcome; for follow-up, rerun and use Mark observation or record Matched, Partly matched, or Surprised in external notes.",
                "- Review prompt: Review the saved learner note; record any follow-up explanation in personal or course notes outside the saved-run folder.",
                "- Review prompt: Decide which suggested next run should be compared against this one.",
            ]
        )
    lines.append("")
    return lines


def _has_observation_workflow(events: list[dict[str, Any]], config: dict[str, Any] | None) -> bool:
    return (
        any(learner_control_families_from_config(config))
        or _learner_control_event_count(events) > 0
        or any(_is_observation_marker(event) for event in events)
    )


def _worksheet_preset_comparison_lines(events: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    configured_labels = _configured_preset_labels(config)
    if len(configured_labels) < 2:
        return []
    tried_labels = _distinct_preset_labels(events, configured_labels)
    required_labels = _configured_required_preset_labels(config)
    required_tried, next_required = _ordered_required_preset_progress(
        required_labels,
        _preset_event_labels(events, configured_labels),
    )
    lines = ["## Preset Comparison", ""]
    lines.extend(
        _worksheet_mapping_lines(
            dict(_preset_comparison_progress_items(configured_labels, tried_labels, required_labels, required_tried, next_required))
        )
    )
    lines.append("")
    return lines


def _worksheet_activity_mix_lines(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[str]:
    items = _activity_mix_items(events, config)
    if not items:
        return []
    lines = ["## Hands-on Activity Mix", ""]
    lines.extend(_worksheet_mapping_lines(dict(items)))
    lines.extend(_worksheet_control_coverage_lines(events, config))
    lines.append("")
    return lines


def _worksheet_control_coverage_lines(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[str]:
    counts = _event_kind_counts(events)
    complete_observation_markers = _complete_observation_evidence_count(events)
    has_buttons, has_sliders, has_presets = _activity_available_control_families(config, counts)
    checks: list[tuple[str, int]] = []
    if has_presets:
        checks.append(("Try one Quick preset to compare a named parameter regime.", counts.get("preset", 0)))
    if has_sliders:
        checks.append(("Move one live slider to test a smaller parameter change.", counts.get("slider", 0)))
    if has_buttons:
        checks.append((_activity_button_next_step(config), counts.get("button", 0)))
    checks.append(("Save one Mark observation with prediction and note.", complete_observation_markers))
    lines = ["", "Control coverage status (read-only):"]
    for label, count in checks:
        status = "Recorded" if count > 0 else "Pending evidence"
        lines.append(f"- {status}: {label} ({count} recorded)")
    return lines


def _complete_observation_evidence_count(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        if not _is_observation_marker(event):
            continue
        value = event.get("value")
        if not isinstance(value, dict):
            continue
        has_prediction = bool(str(value.get("prediction") or "").strip())
        has_note = bool(str(value.get("note") or "").strip())
        if has_prediction and has_note:
            count += 1
    return count


def _required_preset_progress(config: dict[str, Any], events: list[dict[str, Any]]) -> tuple[list[str], list[str], str]:
    required_labels = _configured_required_preset_labels(config)
    if not required_labels:
        return [], [], ""
    configured_labels = _configured_preset_labels(config)
    required_tried, next_required = _ordered_required_preset_progress(
        required_labels,
        _preset_event_labels(events, configured_labels),
    )
    return required_labels, required_tried, next_required


def _worksheet_plot_review_lines(output: Path, plots: list[Path]) -> list[str]:
    lines = ["## Plot Review", ""]
    if not plots:
        return [*lines, "- No plot images were saved for this run.", ""]

    sorted_plots = sorted(plots, key=_index_plot_sort_key)
    guided_plots: list[tuple[Path, tuple[str, str]]] = []
    for plot in sorted_plots:
        guidance = _plot_guidance(plot.name)
        if guidance is not None:
            guided_plots.append((plot, guidance))

    if not guided_plots:
        priority_plot = sorted_plots[0]
        lines.extend(
            [
                f"- Priority plot: {_markdown_inline(_relative(output, priority_plot))}",
                "- What to check: open this plot and compare the trace against your prediction.",
                "",
            ]
        )
        return lines

    priority_plot, (title, detail) = guided_plots[0]
    lines.extend(
        [
            f"- Priority plot: {_markdown_inline(_relative(output, priority_plot))}",
            f"- Read first: {_markdown_inline(title)}",
            f"- What to check: {_markdown_inline(detail)}",
        ]
    )
    if len(guided_plots) > 1:
        lines.append("- Other guided plots:")
        for plot, (other_title, other_detail) in guided_plots[1:5]:
            lines.append(
                f"  - {_markdown_inline(_relative(output, plot))}: "
                f"{_markdown_inline(other_title)} - {_markdown_inline(other_detail)}"
            )
    lines.append("")
    return lines


def _worksheet_next_experiment_lines(summary: dict[str, Any], current_config: dict[str, Any]) -> list[str]:
    config_path = _normalize_path(str(summary.get("config_path") or ""))
    suggestions = NEXT_RUN_SUGGESTIONS.get(config_path, ())
    comparison = _comparison_batch_for_summary(summary)
    if not suggestions and comparison is None:
        return []

    lines = ["## Suggested Next Experiments", ""]
    for suggestion in suggestions[:3]:
        guide = guide_for_config(config_path=suggestion.config_path)
        title = guide.title if guide is not None else Path(suggestion.config_path).stem.replace("_", " ").title()
        lab_name = _cli_lab_name(suggestion.config_path)
        command = (
            f"python -m mclab run {lab_name} --config {suggestion.config_path} "
            f"--viewer --realtime --pause-at-end --plot --plots {suggestion.plots} --open-report"
        )
        lines.extend(
            [
                f"### {title}",
                "",
                f"- Reason: {_markdown_inline(suggestion.reason)}",
                f"- Config: {_markdown_inline(suggestion.config_path)}",
                f"- Plots: {_markdown_inline(suggestion.plots)}",
            ]
        )
        if guide is not None:
            prediction = prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()
            question = question_for_guide(guide).removeprefix("Question:").strip()
            lines.append(f"- Prediction: {_markdown_inline(prediction)}")
            lines.append(f"- Question: {_markdown_inline(question)}")
            start_steps, challenge = _suggested_guide_action_text(guide, suggestion.config_path)
            if start_steps:
                lines.append(f"- Start steps: {_markdown_inline(start_steps)}")
            if challenge:
                lines.append(f"- Challenge: {_markdown_inline(challenge)}")
        controls = _suggested_control_surface_sentence(suggestion.config_path)
        if controls:
            lines.append(f"- Controls: {_markdown_inline(controls)}")
        changes = _suggested_config_change_rows(current_config, suggestion.config_path)
        if changes:
            lines.append("- Key changes:")
            for key, value in changes:
                lines.append(f"  - {_markdown_inline(key)}: {_markdown_inline(value)}")
        lines.append(f"- Command: {command}")
        lines.append("")

    if comparison is not None:
        batch_name, title, reason = comparison
        command = f"python -m mclab batch {batch_name} --open-report"
        lines.extend(
            [
                "## Comparison Batch",
                "",
                f"- Title: {_markdown_inline(title)}",
                f"- Reason: {_markdown_inline(reason)}",
                f"- Batch: {_markdown_inline(batch_name)}",
                f"- Command: {command}",
                "",
            ]
        )
    return lines


def _worksheet_notes_lines(notes: str) -> list[str]:
    text = notes.strip()
    if not text:
        return ["## Notes", "", "- No run notes were saved.", ""]
    return ["## Notes", "", "```markdown", text, "```", ""]


def _worksheet_artifact_lines(output: Path, plots: list[Path]) -> list[str]:
    artifact_names = ["report.html", *_standard_artifact_names()]
    lines = ["## Artifacts", ""]
    for name in artifact_names:
        if name == "report.html" or (output / name).exists():
            lines.append(f"- {name}")
    if plots:
        lines.append("- plots:")
        for plot in plots:
            lines.append(f"  - {_relative(output, plot)}")
    lines.append("")
    return lines


def _standard_artifact_names() -> tuple[str, ...]:
    return (
        "config.yaml",
        "summary.json",
        "notes.md",
        "worksheet.md",
        "log.csv",
        "states.npz",
        "replay.npz",
        "manifest.json",
        "interaction_events.json",
        "learner_snapshot.json",
        "learner_tuned_config.yaml",
    )


def _raw_artifact_names_for_report(output: Path) -> list[str]:
    names = [
        "report.html",
        *_standard_artifact_names(),
    ]
    return [name for name in names if name == "report.html" or (output / name).exists()]


def _worksheet_mapping_lines(values: dict[str, Any], *, indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in values.items():
        if isinstance(value, dict) and value:
            lines.append(f"{prefix}- {_markdown_inline(key)}:")
            lines.extend(_worksheet_mapping_lines(value, indent=indent + 2))
        else:
            lines.append(f"{prefix}- {_markdown_inline(key)}: {_markdown_inline(value)}")
    return lines


def _markdown_inline(value: Any) -> str:
    text = " ".join(_format_value(value).split())
    return text.replace("|", "\\|")


def _render_report(
    output: Path,
    summary: dict[str, Any],
    notes: str,
    plots: list[Path],
    interaction_events: list[dict[str, Any]],
    config: dict[str, Any],
    learner_snapshot: dict[str, Any],
    completion_decision: CompletionDecision,
    completion_evidence: CompletionEvidence,
) -> str:
    title = _report_title(output, summary)
    report_language = str(config.get("language", "en"))
    if report_language not in {"ko", "en"}:
        report_language = "en"
    title = _localized_report_title(summary, fallback=title, language=report_language)
    overview = _result_overview_section(output, summary, plots, language=report_language)
    completion = _completion_section(completion_decision)
    learning_guide = _learning_guide_section(guide_for_run_summary(summary), summary, config)
    course_position = _course_position_section(summary)
    course_coverage = _course_experience_coverage_section(
        output,
        completion_evidence=completion_evidence,
    )
    worksheet = _worksheet_section(output)
    next_actions = _next_actions_section(
        output,
        summary,
        config,
        plots,
        interaction_events,
        language=report_language,
    )
    reproduce_section = _reproduce_section(summary)
    tuned_replay = _learner_tuned_config_section(output, summary)
    next_runs = _suggested_next_runs_section(summary, config)
    comparison_batch = _comparison_batch_section(summary)
    control_surface = _control_surface_section(config)
    config_highlights = _config_highlights_section(config)
    configured_presets = _configured_presets_section(config)
    result_check = _result_check_section(summary)
    key_moments = _key_moments_section(summary)
    mission_evidence = _mission_evidence_section(
        summary,
        interaction_events,
        plots,
        config,
        completion_decision,
    )
    challenge_evidence = _challenge_evidence_section(
        summary,
        interaction_events,
        plots,
        config,
        completion_decision,
    )
    hands_on_evidence = _hands_on_evidence_section(summary, interaction_events, config)
    learner_action_summary = _learner_action_summary_section(interaction_events, config)
    learner_snapshot_section = _learner_snapshot_section(learner_snapshot)
    observation_timeline = _observation_timeline_section(interaction_events)
    observation_markers = _observation_markers_section(interaction_events, config, summary)
    interaction_section = _interaction_section(interaction_events)
    plot_guide = _plot_guide_section(plots)
    rows = "\n".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(_format_value(value))}</td></tr>"
        for key, value in summary.items()
    )
    if not rows:
        rows = '<tr><td colspan="2">No summary values were saved.</td></tr>'

    plot_cards = "\n".join(
        (
            '<figure class="plot">'
            f'<img src="{escape(_relative(output, plot))}" alt="{escape(plot.stem)} plot">'
            f"<figcaption>{escape(plot.name)}</figcaption>"
            "</figure>"
        )
        for plot in plots
    )
    if not plot_cards:
        plot_cards = '<p class="empty">No plots were saved for this run.</p>'

    file_links = "\n".join(
        f'<li><a href="{escape(name)}">{escape(name)}</a></li>'
        for name in _standard_artifact_names()
        if (output / name).exists()
    )
    if not file_links:
        file_links = "<li>No standard artifact files were found.</li>"

    notes_html = f"<pre>{escape(notes.strip())}</pre>" if notes.strip() else "<p>No notes were saved.</p>"

    document_title = f"{title} 실행 보고서" if report_language == "ko" else f"{title} report"
    advanced_label = "고급 세부정보" if report_language == "ko" else "Advanced details"

    return f"""<!doctype html>
<html lang="{report_language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(document_title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Noto Sans KR", "Segoe UI", Arial, sans-serif;
      color: #172033;
      background: #f5f7fb;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 28px;
    }}
    h2 {{
      font-size: 20px;
    }}
    h3 {{
      font-size: 16px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 12px;
      margin-top: 16px;
      padding: 16px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid #edf0f3;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    th {{
      width: 260px;
      color: #3f4752;
      font-weight: 600;
    }}
    .timeline-table th {{
      width: auto;
    }}
    .timeline-table th,
    .timeline-table td {{
      min-width: 112px;
    }}
    .plots {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .plot-guide {{
      margin-bottom: 16px;
    }}
    .plot-guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .plot-guide-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .plot-guide-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .plot-guide-card span {{
      display: block;
      color: #596270;
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px 18px;
    }}
    .guide-item {{
      border-top: 1px solid #edf0f3;
      padding-top: 8px;
    }}
    .guide-item strong {{
      display: block;
      color: #3f4752;
      margin-bottom: 4px;
    }}
    .guide-item span {{
      display: block;
      line-height: 1.4;
    }}
    .guide-subtitle {{
      margin-top: 16px;
    }}
    .command-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }}
    .command-block {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
      min-width: 0;
    }}
    .command-block strong {{
      display: block;
      margin-bottom: 8px;
    }}
    .config-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .config-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .config-card strong {{
      display: block;
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }}
    .config-card span {{
      color: #596270;
      overflow-wrap: anywhere;
    }}
    .check-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .check-card {{
      border: 1px solid #e0e4ea;
      border-left: 4px solid #9aa4b2;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .check-ok {{
      border-left-color: #188038;
    }}
    .check-watch, .check-observed, .check-recorded {{
      border-left-color: #f29900;
    }}
    .check-inspect, .check-review {{
      border-left-color: #d93025;
    }}
    .check-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .marker-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .marker-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .marker-card > strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .marker-time {{
      display: block;
      color: #596270;
      font-size: 13px;
      margin-bottom: 10px;
    }}
    .marker-group {{
      margin-top: 10px;
    }}
    .marker-group ul {{
      list-style: none;
      padding: 0;
      margin: 6px 0 0;
    }}
    .marker-group li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid #edf0f3;
      padding: 5px 0;
    }}
    .marker-group span {{
      color: #596270;
    }}
    .action-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .action-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfd;
      min-width: 0;
    }}
    .action-card > strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .action-card li > a {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
    }}
    .action-wide {{
      grid-column: 1 / -1;
    }}
    .action-list {{
      list-style: none;
      margin: 8px 0 0;
      padding: 0;
    }}
    .action-list li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid #edf0f3;
      padding: 5px 0;
    }}
    .action-list span {{
      color: #596270;
      overflow-wrap: anywhere;
    }}
    .action-list strong {{
      text-align: right;
      overflow-wrap: anywhere;
    }}
    .action-card pre {{
      margin-top: 10px;
      padding: 10px;
      border: 1px solid #e0e4ea;
      border-radius: 6px;
      background: #ffffff;
    }}
    .action-detail {{
      border-top: 1px solid #edf0f3;
      padding-top: 10px;
      margin-top: 10px;
    }}
    .action-detail:first-of-type {{
      border-top: 0;
      padding-top: 0;
      margin-top: 0;
    }}
    .check-state {{
      display: inline-block;
      margin-bottom: 8px;
      color: #3f4752;
      font-size: 13px;
      font-weight: 600;
    }}
    .plot {{
      margin: 0;
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
    }}
    .plot img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    figcaption {{
      border-top: 1px solid #e0e4ea;
      padding: 8px 10px;
      color: #596270;
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      max-width: 100%;
      margin: 0;
      line-height: 1.45;
    }}
    a {{
      color: #2563eb;
    }}
    a:focus-visible, summary:focus-visible, .table-wrap:focus-visible {{
      outline: 3px solid #ffdd00;
      outline-offset: 3px;
      box-shadow: 0 0 0 2px #000000;
    }}
    .result-overview {{
      border-top: 6px solid #2563eb;
    }}
    .result-sentence {{
      font-size: 19px;
      line-height: 1.5;
      margin: 0 0 16px;
    }}
    .priority-plot {{
      max-width: 820px;
      margin: 0 auto 18px;
    }}
    .key-change-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .key-change {{
      border: 1px solid #dce2ec;
      border-radius: 12px;
      padding: 14px;
      background: #f8faff;
    }}
    .key-change strong, .key-change span {{
      display: block;
    }}
    .key-change span {{
      margin-top: 6px;
      font-size: 18px;
    }}
    details.advanced {{
      margin-top: 18px;
      border: 1px solid #d9dde3;
      border-radius: 12px;
      background: #ffffff;
    }}
    details.advanced > summary {{
      cursor: pointer;
      font-size: 18px;
      font-weight: 700;
      padding: 16px;
    }}
    details.advanced > .advanced-body {{
      padding: 0 16px 16px;
    }}
    @media (max-width: 640px) {{
      body {{ padding: 12px; }}
      .plots, .command-grid {{ grid-template-columns: 1fr; }}
      th {{ width: auto; }}
    }}
    .empty {{
      margin: 0;
      color: #596270;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(document_title)}</h1>
    {overview}
    {completion}
    {next_actions}
    <details class="advanced">
      <summary>{advanced_label}</summary>
      <div class="advanced-body">
        {learning_guide}
        {course_position}
        {course_coverage}
        {worksheet}
        {reproduce_section}
        {tuned_replay}
        {next_runs}
        {comparison_batch}
        {control_surface}
        {config_highlights}
        {configured_presets}
        {result_check}
        {key_moments}
        {mission_evidence}
        {challenge_evidence}
        {hands_on_evidence}
        {learner_action_summary}
        {learner_snapshot_section}
        {observation_timeline}
        {observation_markers}
        {interaction_section}
        <section>
          <h2>Summary</h2>
          <table>{rows}</table>
        </section>
        <section>
          <h2>Plots</h2>
          {plot_guide}
          <div class="plots">{plot_cards}</div>
        </section>
        <section>
          <h2>Notes</h2>
          {notes_html}
        </section>
        <section>
          <h2>Files</h2>
          <p class="empty"><a href="./">Open output folder</a></p>
          <ul>{file_links}</ul>
        </section>
      </div>
    </details>
  </main>
</body>
</html>
"""


def _result_overview_section(
    output: Path, summary: dict[str, Any], plots: list[Path], *, language: str = "en"
) -> str:
    samples = _format_value(summary.get("samples", 0))
    duration = _format_value(summary.get("duration", 0.0))
    priority = sorted(plots, key=_index_plot_sort_key)[0] if plots else None
    priority_name = (
        _localized_plot_label(priority, language=language)
        if priority
        else ("저장된 지표" if language == "ko" else "saved metrics")
    )
    if language == "ko":
        sentence = (
            f"이 실행은 {duration}초 동안 {samples}개 샘플을 저장했습니다. "
            f"가장 중요한 응답은 {priority_name} 플롯부터 설명해 보세요."
        )
    else:
        sentence = (
            f"This run saved {samples} samples across {duration} s; start with {priority_name} "
            "to explain the most important response."
        )
    priority_html = ""
    if priority is not None:
        guidance_pair = plot_guidance(priority.name)
        guidance = guidance_pair[1] if guidance_pair else "Review this plot against your prediction."
        if language == "ko":
            guidance = "이 플롯을 실행 전 예측과 비교하세요."
        priority_html = (
            '<figure class="plot priority-plot">'
            f'<img src="{escape(_relative(output, priority))}" '
            f'alt="{escape("우선 증거 플롯" if language == "ko" else "Priority evidence plot")}: '
            f'{escape(priority.stem)}">'
            f"<figcaption>{'우선 플롯' if language == 'ko' else 'Priority plot'} · "
            f"{escape(priority.name)} · {escape(guidance)}</figcaption>"
            "</figure>"
        )
    ignored = {
        "lab_name",
        "config_name",
        "config_path",
        "samples",
        "duration",
        "interaction_events",
    }
    changes = [(key, value) for key, value in summary.items() if key not in ignored][:3]
    if not changes:
        changes = (
            [("샘플 수", samples), ("실행 시간 [초]", duration), ("실행 상태", "저장됨")]
            if language == "ko"
            else [("Samples", samples), ("Duration [s]", duration), ("Run status", "Saved")]
        )
    change_cards = "".join(
        (
            '<div class="key-change">'
            f"<strong>{escape(_localized_metric_label(str(key), language=language))}</strong>"
            f"<span>{escape(_format_value(value))}</span>"
            "</div>"
        )
        for key, value in changes
    )
    return (
        '<section class="result-overview" aria-labelledby="result-overview-title">'
        f'<h2 id="result-overview-title">{"한눈에 보는 결과" if language == "ko" else "Result at a glance"}</h2>'
        f'<p class="result-sentence">{escape(sentence)}</p>'
        f"{priority_html}"
        f'<h3>{"설명할 핵심 값 3개" if language == "ko" else "Three values to explain"}</h3>'
        f'<div class="key-change-grid">{change_cards}</div>'
        "</section>"
    )


def _worksheet_section(output: Path) -> str:
    worksheet = output / "worksheet.md"
    if not worksheet.exists():
        return ""
    return _action_card(
        "Learner Worksheet",
        "Open the digest-published, read-only Markdown worksheet to review saved evidence. "
        "Record follow-up answers in personal or course notes outside this saved-run folder.",
        '<p class="empty"><a href="worksheet.md">Open worksheet.md</a></p>',
    )


def _course_position_section(summary: dict[str, Any]) -> str:
    position = _course_position_for_summary(summary)
    if position is None:
        return ""
    step, _step_number, milestone = position
    body = _action_value_list(
        (
            ("Milestone", milestone),
            ("Learning path step", step.title),
            ("Step focus", step.description),
            ("Done when", _learning_path_completion_text(step).removeprefix("Done when:").strip()),
        )
    )
    command = _learning_path_command(step)
    if command:
        body += f"<pre>{escape(command)}</pre>"
    return (
        "<section>"
        "<h2>Course Position</h2>"
        '<div class="action-grid">'
        f"{_action_card('Learning path role', 'Where this saved run fits in the guided course.', body)}"
        "</div>"
        "</section>"
    )


def _course_experience_coverage_section(
    output: Path,
    *,
    completion_evidence: CompletionEvidence | None = None,
) -> str:
    overrides = (
        {output.name: completion_evidence}
        if completion_evidence is not None
        else None
    )
    runs = _discover_runs(output.parent, evidence_overrides=overrides)
    records = _experience_coverage_records_for_index(runs)
    summary = experience_coverage_summary_text(records)
    next_item = next_experience_coverage_item(records)
    repair_blocks = _experience_coverage_repair_blocks(runs, report_prefix="../")
    status_cards = "\n".join(
        _course_experience_status_card(status, repair_blocks)
        for status in experience_coverage_statuses(records)
    )
    if next_item is None:
        next_body = (
            '<p class="empty">'
            "All core experience types are represented. Replay a tuned run or open a comparison batch to go deeper."
            "</p>"
        )
    else:
        next_body = (
            _action_value_list(
                (
                    ("Next experience", next_item.label),
                    ("Mode", experience_coverage_item_mode(next_item)),
                    ("Next action", next_item.next_step),
                    ("Evidence", experience_coverage_item_evidence(next_item)),
                )
            )
            + f"<pre>{escape(next_item.command)}</pre>"
        )
    return (
        "<section>"
        "<h2>Course Experience Coverage</h2>"
        f'<p class="empty">{escape(summary)}</p>'
        '<div class="action-grid">'
        f"{_action_card('Run next experience', 'Continue toward a varied hands-on course path.', next_body)}"
        f"{status_cards}"
        "</div>"
        '<p class="empty"><a href="../index.html">Open all reports index</a></p>'
        "</section>"
    )


def _course_experience_status_card(status: ExperienceCoverageStatus, repair_blocks: dict[str, str]) -> str:
    if status.next_missing:
        state = "Next"
    elif status.covered:
        state = "Done"
    else:
        state = "Missing"
    repair_block = repair_blocks.get(status.item.key, "")
    body = _action_value_list(
        (
            ("Status", state),
            ("Mode", experience_coverage_item_mode(status.item)),
            ("Focus", status.item.next_step),
            ("Evidence", experience_coverage_item_evidence(status.item)),
        )
    )
    body += _experience_coverage_control_cues(status.item)
    body += repair_block
    return _action_card(status.item.label, "Core learner experience type.", body)


def _course_position_for_summary(summary: dict[str, Any]) -> tuple[IndexPathStep, int, str] | None:
    config_path = _normalize_path(str(summary.get("config_path") or ""))
    batch_name = str(summary.get("batch_name") or summary.get("config_name") or "").strip()
    for step_index, step in enumerate(INDEX_LEARNING_PATH):
        if step.batch_name:
            if batch_name == step.batch_name:
                return step, step_index + 1, course_milestone_label_for_step_index(step_index)
            continue
        if config_path and _normalize_path(step.config_path) == config_path:
            return step, step_index + 1, course_milestone_label_for_step_index(step_index)
    return None


def _learning_guide_section(
    guide: RunGuide | None,
    summary: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> str:
    if guide is None:
        return ""
    items = (
        ("Focus", guide.focus),
        ("Done when", _run_completion_text(summary).removeprefix("Done when:").strip()),
        ("Mission", mission_prompt_for_guide(guide).removeprefix("Mission:").strip()),
        ("Playbook", playbook_for_guide(guide).removeprefix("Playbook:").strip()),
        ("Start steps", _start_steps_text(guide, config)),
        ("Counts as control", _control_credit_text_for_config(config)),
        ("Challenge", challenge_prompt_for_guide(guide).removeprefix("Challenge:").strip()),
        ("Try", guide.try_this),
        ("Change", guide.change),
        ("Prediction", prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()),
        ("Question", question_for_guide(guide).removeprefix("Question:").strip()),
        ("Watch", guide.watch),
        ("Next", guide.next_step),
    )
    body = "\n".join(
        (
            '<div class="guide-item">'
            f"<strong>{escape(label)}</strong>"
            f"<span>{escape(text)}</span>"
            "</div>"
        )
        for label, text in items
        if text
    )
    viewer_legend = _viewer_legend_block(guide)
    return (
        "<section>"
        f"<h2>{escape(guide.title)}</h2>"
        '<div class="guide-grid">'
        f"{body}"
        "</div>"
        f"{viewer_legend}"
        "</section>"
    )


def _viewer_legend_block(guide: RunGuide | None) -> str:
    items = viewer_legend_for_guide(guide)
    if not items:
        return ""
    body = "\n".join(
        (
            '<div class="guide-item">'
            f"<strong>{escape(label)}</strong>"
            f"<span>{escape(text)}</span>"
            "</div>"
        )
        for label, text in items
    )
    return (
        '<h3 class="guide-subtitle">Viewer Legend</h3>'
        '<div class="guide-grid">'
        f"{body}"
        "</div>"
    )


def _start_steps_text(guide: RunGuide | None, config: dict[str, Any] | None = None) -> str:
    if isinstance(config, dict) and config:
        required_labels = _configured_required_preset_labels(config)
        if required_labels:
            return f"Predict -> Run viewer -> try required presets {' -> '.join(required_labels)} -> Mark observation."
        preset_labels = _configured_preset_labels(config)
        if len(preset_labels) >= 2:
            return f"Predict -> Run viewer -> try presets {' -> '.join(preset_labels[:3])} -> Mark observation."
        control_step = _hands_on_control_step_for_config(config)
        if control_step:
            return f"Predict -> Run viewer -> {control_step} -> Mark observation."
    return start_steps_for_guide(guide).removeprefix("Start steps:").strip()


def _reproduce_section(summary: dict[str, Any]) -> str:
    config_path = str(summary.get("config_path") or "").strip()
    lab_name = _cli_lab_name(str(summary.get("lab_name") or ""))
    if not config_path or not lab_name:
        return ""
    viewer_command = (
        f"python -m mclab run {lab_name} --config {config_path} "
        "--viewer --realtime --pause-at-end --plot"
    )
    headless_command = f"python -m mclab run {lab_name} --config {config_path} --headless --plot"
    return (
        "<section>"
        "<h2>Reproduce This Run</h2>"
        '<div class="command-grid">'
        '<div class="command-block">'
        "<strong>Watch it live</strong>"
        f"<pre>{escape(viewer_command)}</pre>"
        "</div>"
        '<div class="command-block">'
        "<strong>Regenerate artifacts</strong>"
        f"<pre>{escape(headless_command)}</pre>"
        "</div>"
        "</div>"
        '<p class="empty">Edit the YAML config, rerun one command, then compare the new report and plots.</p>'
        "</section>"
    )


def _learner_tuned_config_section(output: Path, summary: dict[str, Any]) -> str:
    tuned_config = output / "learner_tuned_config.yaml"
    lab_name = _cli_lab_name(str(summary.get("lab_name") or ""))
    if not tuned_config.exists() or not lab_name:
        return ""
    command = f"python -m mclab run {lab_name} --config {tuned_config} --headless --plot --open-report"
    viewer_command = (
        f"python -m mclab run {lab_name} --config {tuned_config} "
        "--viewer --realtime --pause-at-end --plot --open-report"
    )
    return (
        "<section>"
        "<h2>Replay Tuned Config</h2>"
        '<p class="empty">This generated YAML applies the final learner slider values and disables live controls for repeatable replay.</p>'
        '<div class="command-grid">'
        '<div class="command-block">'
        "<strong>Regenerate tuned artifacts</strong>"
        f"<pre>{escape(command)}</pre>"
        "</div>"
        '<div class="command-block">'
        "<strong>Watch tuned replay</strong>"
        f"<pre>{escape(viewer_command)}</pre>"
        "</div>"
        "</div>"
        f'<p class="empty"><a href="{escape(tuned_config.name)}">Open learner_tuned_config.yaml</a></p>'
        "</section>"
    )


def _next_actions_section(
    output: Path,
    summary: dict[str, Any],
    current_config: dict[str, Any],
    plots: list[Path],
    events: list[dict[str, Any]],
    *,
    language: str = "en",
) -> str:
    cards: list[str] = []
    evidence_card = _next_action_evidence_card(summary, events, language=language)
    if evidence_card:
        cards.append(evidence_card)
    plot_card = _next_action_plot_card(output, plots, language=language)
    if plot_card:
        cards.append(plot_card)
    artifact_card = _next_action_artifacts_card(output, language=language)
    if artifact_card:
        cards.append(artifact_card)
    replay_card = _next_action_replay_card(output, summary, language=language)
    if replay_card:
        cards.append(replay_card)
    suggested_card = _next_action_suggestion_card(summary, current_config, language=language)
    if suggested_card:
        cards.append(suggested_card)
    comparison_card = _next_action_comparison_card(summary, language=language)
    if comparison_card:
        cards.append(comparison_card)
    if not cards:
        return ""
    return (
        "<section>"
        f'<h2>{"다음 행동" if language == "ko" else "Next Actions"}</h2>'
        '<p class="empty">'
        f'{"결과를 읽은 직후 아래 순서로 이어가세요." if language == "ko" else "Use these shortcuts right after reading this report."}'
        "</p>"
        '<div class="action-grid">'
        f"{''.join(cards[:6])}"
        "</div>"
        "</section>"
    )


def _next_action_evidence_card(
    summary: dict[str, Any], events: list[dict[str, Any]], *, language: str = "en"
) -> str:
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    if markers <= 0 and not _summary_requires_hands_on_evidence(summary):
        return ""
    if markers > 0 and predictions > outcomes:
        title = "예측 결과 판단하기" if language == "ko" else "Judge prediction outcome"
        description = (
            "직접 조작 실행을 다시 보거나 반복한 뒤 예측이 일치, 일부 일치, 예상 밖인지 표시하세요."
            if language == "ko"
            else "Repeat or review this hands-on run and mark whether the prediction matched, partly matched, or surprised you."
        )
    elif markers > 0 and predictions > 0:
        title = "저장된 증거 복습하기" if language == "ko" else "Review saved evidence"
        description = (
            "저장된 예측과 메모를 아래 플롯과 비교하세요."
            if language == "ko"
            else "Compare the saved prediction and note against the plots below."
        )
    elif markers > 0:
        title = "예측 증거 추가하기" if language == "ko" else "Add prediction evidence"
        description = (
            "직접 조작 실험을 반복하고 관찰 기록 전에 예측을 작성하세요."
            if language == "ko"
            else "Repeat this hands-on run and fill Prediction before Mark observation."
        )
    else:
        title = "관찰 한 번 기록하기" if language == "ko" else "Mark one observation"
        description = (
            "직접 조작 데모를 실행하고 예측을 작성한 뒤 관찰 한 번을 저장하세요."
            if language == "ko"
            else "Run the interactive demo, write a prediction, then save one observation."
        )
    return _action_card(
        title,
        description,
        _action_value_list(
            (
                ("관찰 기록" if language == "ko" else "Observation markers", markers),
                ("예측" if language == "ko" else "Predictions", predictions),
                ("예측 결과" if language == "ko" else "Prediction outcomes", outcomes),
                ("학습자 메모" if language == "ko" else "Learner notes", notes),
            )
        ),
    )


def _next_action_plot_card(output: Path, plots: list[Path], *, language: str = "en") -> str:
    if not plots:
        return ""
    plot = sorted(plots, key=_index_plot_sort_key)[0]
    label = _localized_plot_label(plot, language=language)
    href = _relative(output, plot)
    body = (
        _action_value_list(
            (
                ("우선 플롯" if language == "ko" else "Priority plot", label),
                ("파일" if language == "ko" else "File", plot.name),
            )
        )
        + f'<p class="empty"><a href="{escape(href)}">'
        f'{"열기" if language == "ko" else "Open"} {escape(plot.name)}</a></p>'
    )
    return _action_card(
        "핵심 플롯 열기" if language == "ko" else "Open the key plot",
        (
            "이 실행에서 우선순위가 가장 높은 플롯부터 확인하세요."
            if language == "ko"
            else "Start with the highest-priority plot for this run."
        ),
        body,
    )


def _next_action_artifacts_card(output: Path, *, language: str = "en") -> str:
    names = _raw_artifact_names_for_report(output)
    if not names:
        return ""
    visible_names = [name for name in names if name != "report.html"]
    if not visible_names:
        visible_names = ["report.html"]
    links = "".join(
        f'<li><a href="{escape(name)}">{escape(name)}</a></li>'
        for name in visible_names[:4]
        if (output / name).exists()
    )
    if not links:
        links = "<li>report.html</li>"
    body = (
        '<p class="empty"><a href="./">'
        f'{"결과 폴더 열기" if language == "ko" else "Open output folder"}</a></p>'
        "<ul>"
        f"{links}"
        "</ul>"
    )
    return _action_card(
        "원본 산출물 열기" if language == "ko" else "Open raw artifacts",
        (
            "이 보고서의 저장된 설정, 로그, 상태, 스냅샷, 학습자 이벤트를 확인하세요."
            if language == "ko"
            else "Inspect the saved config, logs, states, snapshots, and learner events behind this report."
        ),
        body,
    )


def _next_action_replay_card(
    output: Path, summary: dict[str, Any], *, language: str = "en"
) -> str:
    tuned_config = output / "learner_tuned_config.yaml"
    lab_name = _cli_lab_name(str(summary.get("lab_name") or ""))
    if not tuned_config.exists() or not lab_name:
        return ""
    command = (
        f"python -m mclab run {lab_name} --config {tuned_config} "
        "--viewer --realtime --pause-at-end --plot --open-report"
    )
    body = _action_value_list(
        (("설정" if language == "ko" else "Config", tuned_config.name),)
    ) + f"<pre>{escape(command)}</pre>"
    return _action_card(
        "마지막 튜닝 재실행" if language == "ko" else "Replay tuned values",
        (
            "실시간 제어 없이 마지막 슬라이더 값을 다시 확인하세요."
            if language == "ko"
            else "Watch the final slider values again without live controls."
        ),
        body,
    )


def _next_action_suggestion_card(
    summary: dict[str, Any], current_config: dict[str, Any], *, language: str = "en"
) -> str:
    config_path = _normalize_path(str(summary.get("config_path") or ""))
    suggestions = NEXT_RUN_SUGGESTIONS.get(config_path, ())
    if not suggestions:
        return ""
    suggestion = suggestions[0]
    guide = guide_for_config(config_path=suggestion.config_path)
    title = guide.title if guide is not None else Path(suggestion.config_path).stem.replace("_", " ").title()
    if language == "ko":
        title = _localized_scenario_title(suggestion.config_path, fallback=title)
    lab_name = _cli_lab_name(suggestion.config_path)
    command = (
        f"python -m mclab run {lab_name} --config {suggestion.config_path} "
        f"--viewer --realtime --pause-at-end --plot --plots {suggestion.plots} --open-report"
    )
    key_changes = _suggested_config_changes(
        current_config, suggestion.config_path, language=language
    )
    guide_action = (
        ""
        if language == "ko"
        else _suggested_guide_action_html(guide, suggestion.config_path)
    )
    control_summary = (
        ""
        if language == "ko"
        else _suggested_control_surface_summary(suggestion.config_path)
    )
    body = (
        _action_value_list(
            (
                ("설정" if language == "ko" else "Config", suggestion.config_path),
                ("플롯" if language == "ko" else "Plots", suggestion.plots),
            )
        )
        + guide_action
        + control_summary
        + key_changes
        + f"<pre>{escape(command)}</pre>"
    )
    return _action_card(
        f'{"다음 실험" if language == "ko" else "Try next"}: {title}',
        (
            "한 가지 조건만 바꿔 결과 차이를 확인하세요."
            if language == "ko"
            else suggestion.reason
        ),
        body,
    )


def _next_action_comparison_card(summary: dict[str, Any], *, language: str = "en") -> str:
    comparison = _comparison_batch_for_summary(summary)
    if comparison is None:
        return ""
    batch_name, title, reason = comparison
    if language == "ko":
        title, reason = _localized_comparison_text(batch_name, title)
    command = f"python -m mclab batch {batch_name} --open-report"
    body = _action_value_list(
        (("비교 배치" if language == "ko" else "Batch", batch_name),)
    ) + f"<pre>{escape(command)}</pre>"
    return _action_card(
        f'{"비교 배치" if language == "ko" else "Compare batch"}: {title}', reason, body
    )


def _suggested_next_runs_section(summary: dict[str, Any], current_config: dict[str, Any]) -> str:
    config_path = _normalize_path(str(summary.get("config_path") or ""))
    suggestions = NEXT_RUN_SUGGESTIONS.get(config_path, ())
    if not suggestions:
        return ""
    cards = "\n".join(_suggested_next_run_card(suggestion, current_config) for suggestion in suggestions[:3])
    return (
        "<section>"
        "<h2>Suggested Next Runs</h2>"
        '<p class="empty">Run one of these next to turn this result into a comparison.</p>'
        '<div class="action-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _suggested_next_run_card(suggestion: NextRunSuggestion, current_config: dict[str, Any]) -> str:
    guide = guide_for_config(config_path=suggestion.config_path)
    title = guide.title if guide is not None else Path(suggestion.config_path).stem.replace("_", " ").title()
    lab_name = _cli_lab_name(suggestion.config_path)
    command = (
        f"python -m mclab run {lab_name} --config {suggestion.config_path} "
        f"--viewer --realtime --pause-at-end --plot --plots {suggestion.plots} --open-report"
    )
    guide_focus = f'<p class="empty">{escape(guide.focus)}</p>' if guide is not None else ""
    guide_prediction = ""
    guide_question = ""
    guide_action = ""
    if guide is not None:
        prediction = prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()
        guide_prediction = f'<p class="empty"><strong>Prediction:</strong> {escape(prediction)}</p>'
        question = question_for_guide(guide).removeprefix("Question:").strip()
        guide_question = f'<p class="empty"><strong>Question:</strong> {escape(question)}</p>'
        guide_action = _suggested_guide_action_html(guide, suggestion.config_path)
    key_changes = _suggested_config_changes(current_config, suggestion.config_path)
    control_summary = _suggested_control_surface_summary(suggestion.config_path)
    return (
        '<article class="action-card action-wide">'
        f"<strong>{escape(title)}</strong>"
        f'<p class="empty">{escape(suggestion.reason)}</p>'
        f"{guide_focus}"
        f"{guide_prediction}"
        f"{guide_question}"
        f"{guide_action}"
        f"{control_summary}"
        f"{key_changes}"
        '<ul class="action-list">'
        "<li>"
        "<span>Config</span>"
        f"<strong>{escape(suggestion.config_path)}</strong>"
        "</li>"
        "<li>"
        "<span>Plots</span>"
        f"<strong>{escape(suggestion.plots)}</strong>"
        "</li>"
        "</ul>"
        f"<pre>{escape(command)}</pre>"
        "</article>"
    )


def _suggested_guide_action_html(guide: RunGuide | None, config_path: str) -> str:
    start_steps, challenge = _suggested_guide_action_text(guide, config_path)
    if not start_steps and not challenge:
        return ""
    parts: list[str] = []
    if start_steps:
        parts.append(f'<p class="empty"><strong>Start steps:</strong> {escape(start_steps)}</p>')
    if challenge:
        parts.append(f'<p class="empty"><strong>Challenge:</strong> {escape(challenge)}</p>')
    return "".join(parts)


def _suggested_guide_action_text(guide: RunGuide | None, config_path: str) -> tuple[str, str]:
    if guide is None:
        return "", ""
    start_steps = _start_steps_text(guide, _safe_load_config(config_path)).strip()
    challenge = challenge_prompt_for_guide(guide).removeprefix("Challenge:").strip()
    return start_steps, challenge


def _safe_load_config(config_path: str) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _comparison_batch_section(summary: dict[str, Any]) -> str:
    comparison = _comparison_batch_for_summary(summary)
    if comparison is None:
        return ""
    batch_name, title, reason = comparison
    command = f"python -m mclab batch {batch_name} --open-report"
    return (
        "<section>"
        "<h2>Comparison Batch</h2>"
        '<p class="empty">Use this after one run to compare the same concept across controlled scenarios.</p>'
        '<div class="action-grid">'
        '<article class="action-card action-wide">'
        f"<strong>{escape(title)}</strong>"
        f'<p class="empty">{escape(reason)}</p>'
        f"{_action_value_list([('Batch', batch_name), ('Command', command)])}"
        f"<pre>{escape(command)}</pre>"
        "</article>"
        "</div>"
        "</section>"
    )


def _comparison_batch_for_summary(summary: dict[str, Any]) -> tuple[str, str, str] | None:
    lab_name = _cli_lab_name(str(summary.get("lab_name") or ""))
    config_text = _normalize_path(
        " ".join(str(summary.get(key) or "") for key in ("config_path", "config_name"))
    )
    if lab_name == "lab01":
        return (
            "lab01_msd_compare",
            "Lab01 mass-spring-damper comparison",
            "Compare baseline, damping, and stiffness cases in one report.",
        )
    if lab_name == "lab02":
        return (
            "lab02_pid_compare",
            "Lab02 PID comparison",
            "Compare gains, saturation, windup, anti-windup, sensor noise, and delay.",
        )
    if lab_name == "lab03":
        return (
            "lab03_2dof_compare",
            "Lab03 2DOF comparison",
            "Compare joint-space, task-space, singularity, and damped least-squares behavior.",
        )
    if lab_name == "lab04":
        if "wall" in config_text or "impedance" in config_text:
            return (
                "lab04_wall_compare",
                "Lab04 Panda virtual wall comparison",
                "Compare soft and stiff virtual wall penetration, force, retreat, and hand motion.",
            )
        return (
            "lab04_cartesian_compare",
            "Lab04 Panda Cartesian reach comparison",
            "Compare baseline, soft, and stiff Cartesian reach error and actuator effort.",
        )
    return None


def _control_surface_section(config: dict[str, Any]) -> str:
    controls = _control_surface_items(config)
    if not controls:
        return ""
    return (
        "<section>"
        "<h2>Control Surface</h2>"
        '<p class="empty">Use this to choose where to change the experiment before rerunning.</p>'
        '<div class="action-grid">'
        '<article class="action-card action-wide">'
        "<strong>Available controls</strong>"
        f"{_action_value_list(controls)}"
        "</article>"
        "</div>"
        "</section>"
    )


def _suggested_control_surface_summary(config_path: str) -> str:
    try:
        config = load_config(config_path)
    except Exception:
        return ""
    summary = _control_surface_sentence(config)
    if not summary:
        return ""
    return f'<p class="empty"><strong>Controls:</strong> {escape(summary)}</p>'


def _suggested_control_surface_sentence(config_path: str) -> str:
    try:
        config = load_config(config_path)
    except Exception:
        return ""
    return _control_surface_sentence(config)


def _control_surface_sentence(config: dict[str, Any]) -> str:
    controls = _control_surface_items(config)
    if not controls:
        return ""
    values = [str(value) for _label, value in controls]
    return "; ".join(dict.fromkeys(values))


def _control_surface_items(config: dict[str, Any]) -> list[tuple[str, str]]:
    interaction = config.get("interaction")
    viewer_item = ("Viewer UI", VIEWER_CONTROL_SURFACE_TEXT)
    if not isinstance(interaction, dict) or not interaction:
        return [
            viewer_item,
            ("Mode", "Auto run"),
            ("Change values", "Edit YAML or use Config Highlights before rerunning"),
        ]

    panel_enabled = bool(interaction.get("panel", False))
    items: list[tuple[str, str]] = [viewer_item]
    if panel_enabled:
        items.append(("Panel", "MCLab Interaction window"))
    if bool(interaction.get("key_force", False)):
        items.append(("Manual input", "Pull/Push buttons and A/D keys"))
    if bool(interaction.get("target_nudge", False)):
        items.append(("Manual input", _target_nudge_control_label(interaction)))
    if bool(interaction.get("joint_disturbance", False)):
        items.append(("Manual input", "Shoulder/Elbow pulse buttons and A/D keys"))
    if bool(interaction.get("live_tuning", False)):
        items.append(("Live tuning", "Sliders with Changed values summary"))
    presets = _configured_preset_labels(config)
    if presets:
        items.append(("Quick presets", ", ".join(presets)))
    credit_text = _control_credit_text_for_config(config)
    if credit_text:
        items.append(("Counts as control", credit_text))
    if bool(interaction.get("playback_speed", panel_enabled)):
        items.append(("Playback", "Playback speed slider"))
    if bool(interaction.get("pause_resume", interaction.get("pause", panel_enabled))):
        items.append(("Pause/step", "Pause / Resume and Step once"))
    if bool(interaction.get("reset_plant", interaction.get("reset_experiment", panel_enabled))):
        items.append(("Reset", "Reset plant"))
    if panel_enabled:
        items.append(("Evidence", "Prediction, outcome, Use live status, Mark observation"))
    if not items:
        return [
            ("Mode", "Auto run"),
            ("Change values", "Edit YAML or use Config Highlights before rerunning"),
        ]
    return items


def _target_nudge_control_label(interaction: dict[str, Any]) -> str:
    left = str(interaction.get("target_left_label", "Joint Target -  A / Left")).strip()
    right = str(interaction.get("target_right_label", "Joint Target +  D / Right")).strip()
    if left and right:
        return f"{left} / {right}"
    return "Target -/+ buttons and A/D keys"


def _hands_on_control_step_for_config(config: dict[str, Any] | None) -> str:
    interaction = _interaction_config(config)
    if not interaction:
        return ""
    if bool(interaction.get("key_force", False)):
        return "use Pull/Push buttons and A/D keys"
    if bool(interaction.get("target_nudge", False)):
        return f"use {_target_nudge_control_label(interaction)}"
    if bool(interaction.get("joint_disturbance", False)):
        return "use Shoulder/Elbow pulse buttons and A/D keys"
    if bool(interaction.get("live_tuning", False)):
        return "move one live slider"
    panel_enabled = bool(interaction.get("panel", False))
    if bool(interaction.get("reset_plant", interaction.get("reset_experiment", panel_enabled))):
        return "use Reset plant after changing a control"
    return ""


def _control_credit_text_for_config(config: dict[str, Any] | None) -> str:
    controls = _learner_control_labels_for_config(config)
    if not controls:
        return ""
    return f"{', '.join(controls)}; view/evidence helpers such as Pause, Playback speed, and Use live status do not count."


def _learner_control_phrase_for_config(config: dict[str, Any] | None) -> str:
    controls = _learner_control_labels_for_config(config)
    if not controls:
        return ""
    if len(controls) == 1:
        return controls[0]
    if len(controls) == 2:
        return f"{controls[0]} or {controls[1]}"
    return f"{', '.join(controls[:-1])}, or {controls[-1]}"


def _learner_control_labels_for_config(config: dict[str, Any] | None) -> list[str]:
    interaction = _interaction_config(config)
    if not interaction:
        return []
    controls: list[str] = []
    button_label = _button_control_label_for_config(interaction)
    if button_label:
        controls.append(f"experiment buttons ({button_label})")
    if bool(interaction.get("live_tuning", False)):
        controls.append("live sliders")
    if _configured_preset_labels(config or {}):
        controls.append("Quick presets")
    return controls


def _button_control_label_for_config(interaction: dict[str, Any]) -> str:
    primary_labels: list[str] = []
    if bool(interaction.get("key_force", False)):
        primary_labels.append("Pull/Push buttons and A/D keys")
    if bool(interaction.get("target_nudge", False)):
        primary_labels.append(_target_nudge_control_label(interaction))
    if bool(interaction.get("joint_disturbance", False)):
        primary_labels.append("Shoulder/Elbow pulse buttons and A/D keys")
    if primary_labels:
        return "; ".join(dict.fromkeys(primary_labels))
    panel_enabled = bool(interaction.get("panel", False))
    if bool(interaction.get("reset_plant", interaction.get("reset_experiment", panel_enabled))):
        return "Reset plant"
    return ""


def _interaction_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    interaction = config.get("interaction")
    return interaction if isinstance(interaction, dict) else {}


def _suggested_config_changes(
    current_config: dict[str, Any], suggested_config_path: str, *, language: str = "en"
) -> str:
    rows = _suggested_config_change_rows(current_config, suggested_config_path)

    if not rows:
        return ""
    return (
        '<p class="empty"><strong>'
        f'{"핵심 변경값" if language == "ko" else "Key changes"}:</strong></p>'
        f"{_action_value_list(rows)}"
    )


def _suggested_config_change_rows(current_config: dict[str, Any], suggested_config_path: str) -> list[tuple[str, str]]:
    if not current_config:
        return []
    try:
        suggested_config = load_config(suggested_config_path)
    except Exception:
        return []

    current_flat = _flatten_config(current_config)
    suggested_flat = _flatten_config(suggested_config)
    if not current_flat or not suggested_flat:
        return []

    highlight_keys = [key for key in CONFIG_HIGHLIGHT_KEYS if key in current_flat or key in suggested_flat]
    extra_keys = sorted(
        key
        for key in set(current_flat) | set(suggested_flat)
        if key not in CONFIG_HIGHLIGHT_KEYS and _show_config_change_key(key)
    )
    rows: list[tuple[str, str]] = []
    for key in [*highlight_keys, *extra_keys]:
        if not _show_config_change_key(key):
            continue
        current_value = current_flat.get(key)
        suggested_value = suggested_flat.get(key)
        if _config_value_token(current_value) == _config_value_token(suggested_value):
            continue
        rows.append((key, f"{_format_value(current_value)} -> {_format_value(suggested_value)}"))
        if len(rows) >= 5:
            break
    return rows


def _show_config_change_key(key: str) -> bool:
    return key != "model_path" and not key.startswith(("model_path.", "interaction.tuning_presets"))


def _config_value_token(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _cli_lab_name(lab_name: str) -> str:
    normalized = lab_name.lower()
    if "lab01" in normalized or "msd" in normalized:
        return "lab01"
    if "lab02" in normalized or "pid" in normalized:
        return "lab02"
    if "lab04" in normalized or "panda" in normalized:
        return "lab04"
    if "lab03" in normalized or "trajectory" in normalized or "2dof" in normalized:
        return "lab03"
    return ""


def _config_highlights_section(config: dict[str, Any]) -> str:
    pairs = _config_highlight_pairs(config)
    if not pairs:
        return ""
    cards = "\n".join(
        (
            '<article class="config-card">'
            f"<strong>{escape(key)}</strong>"
            f"<span>{escape(_format_value(value))}</span>"
            "</article>"
        )
        for key, value in pairs
    )
    return (
        "<section>"
        "<h2>Config Highlights</h2>"
        '<p class="empty">Edit these YAML values, rerun, then compare the response and report.</p>'
        '<div class="config-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _config_highlight_pairs(config: dict[str, Any]) -> list[tuple[str, Any]]:
    flattened = _flatten_config(config)
    if not flattened:
        return []
    pairs = [(key, flattened[key]) for key in CONFIG_HIGHLIGHT_KEYS if key in flattened]
    if not pairs:
        pairs = [
            (key, value)
            for key, value in flattened.items()
            if key not in {"model_path"} and not key.startswith(("model_path.", "interaction.tuning_presets"))
        ]
    return pairs[:28]


def _configured_presets_section(config: dict[str, Any]) -> str:
    presets = _configured_presets(config)
    if not presets:
        return ""
    cards = "".join(_configured_preset_card(preset) for preset in presets[:6])
    comparison_text = _configured_preset_comparison_text(presets)
    comparison = f'<p class="empty">{escape(comparison_text)}</p>' if comparison_text else ""
    count_text = (
        f"Showing the first 6 of {len(presets)} configured presets."
        if len(presets) > 6
        else f"{len(presets)} configured preset{'s' if len(presets) != 1 else ''} available."
    )
    return (
        "<section>"
        "<h2>Configured Presets</h2>"
        f'<p class="empty">{escape(count_text)} These are the Quick presets shown in the interaction panel.</p>'
        f"{comparison}"
        '<div class="action-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _configured_preset_card(preset: dict[str, Any]) -> str:
    label = str(preset.get("label") or preset.get("name") or "Preset")
    purpose = str(preset.get("purpose") or preset.get("description") or "").strip()
    values = preset.get("values")
    items = values.items() if isinstance(values, dict) else ()
    body = _action_value_list(items) or '<p class="empty">No slider values were configured.</p>'
    purpose_text = f'<p class="empty">{escape(purpose)}</p>' if purpose else ""
    required_text = '<p class="empty"><strong>Required evidence preset.</strong></p>' if preset.get("required") else ""
    return (
        '<article class="action-card">'
        f"<strong>{escape(label)}</strong>"
        f"{purpose_text}"
        f"{required_text}"
        f"{body}"
        "</article>"
    )


def _configured_presets(config: dict[str, Any]) -> list[dict[str, Any]]:
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return []
    presets = interaction.get("tuning_presets")
    if not isinstance(presets, list):
        return []
    return [preset for preset in presets if isinstance(preset, dict)]


def _configured_preset_comparison_text(presets: list[dict[str, Any]]) -> str:
    labels = [
        str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        for index, preset in enumerate(presets, start=1)
    ]
    labels = [label for label in labels if label]
    if len(labels) < 2:
        return ""
    required_labels = [
        str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        for index, preset in enumerate(presets, start=1)
        if bool(preset.get("required", False))
    ]
    required_labels = [label for label in required_labels if label]
    if required_labels:
        return (
            f"Compare presets in order: {' -> '.join(labels)}. "
            f"Required evidence: {' -> '.join(required_labels)}. "
            "Watch live status, then mark one observation."
        )
    return f"Compare presets in order: {' -> '.join(labels)}. Watch live status, then mark one observation."


def _configured_preset_labels(config: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for index, preset in enumerate(_configured_presets(config), start=1):
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return labels


def _configured_required_preset_labels(config: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for index, preset in enumerate(_configured_presets(config), start=1):
        if not bool(preset.get("required", False)):
            continue
        label = str(preset.get("label") or preset.get("name") or f"Preset {index}").strip()
        if label:
            labels.append(label)
    return labels


def _flatten_config(config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in config.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_config(value, path))
        else:
            flattened[path] = value
    return flattened


def _result_check_section(summary: dict[str, Any]) -> str:
    checks = _result_checks(summary)
    if not checks:
        return ""
    cards = "\n".join(
        (
            f'<article class="check-card {_check_state_class(state)}">'
            f"<strong>{escape(title)}</strong>"
            f'<span class="check-state">{escape(state)}</span>'
            f'<p class="empty">{escape(detail)}</p>'
            "</article>"
        )
        for title, state, detail in checks
    )
    return (
        "<section>"
        "<h2>Result Check</h2>"
        '<p class="empty">These prompts are teaching aids, not pass/fail grades.</p>'
        '<div class="check-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _key_moments_section(summary: dict[str, Any]) -> str:
    moments = _key_moment_rows(summary)
    if not moments:
        return ""
    cards = "\n".join(
        _action_card(
            title,
            detail,
            _action_value_list((("Time [s]", _format_value(time_value)), (value_label, _format_value(value)))),
        )
        for title, time_value, value_label, value, detail in moments
    )
    return (
        "<section>"
        "<h2>Key Moments</h2>"
        '<p class="empty">Use these timestamps to jump to the important parts of the plots before reading every trace.</p>'
        '<div class="action-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _key_moment_rows(summary: dict[str, Any]) -> list[tuple[str, float, str, Any, str]]:
    rows: list[tuple[str, float, str, Any, str]] = []

    def add(
        title: str,
        time_key: str,
        value_key: str,
        value_label: str,
        detail: str,
        *,
        include_zero: bool = False,
    ) -> None:
        time_value = _number(summary.get(time_key))
        if time_value is None:
            return
        value = summary.get(value_key)
        numeric_value = _number(value)
        if numeric_value is not None and abs(numeric_value) <= 1e-12 and not include_zero:
            return
        rows.append((title, time_value, value_label, value, detail))

    add(
        "Target crosses wall",
        "first_target_wall_cross_time",
        "target_past_wall_duration",
        "Target past-wall duration [s]",
        "Start reading wall_target.png here; the commanded target has crossed the wall even before hand contact.",
        include_zero=True,
    )
    add(
        "First wall contact",
        "first_wall_contact_time",
        "wall_contact_duration",
        "Contact duration [s]",
        "Start reading virtual_wall.png here; this is where penetration and force first become meaningful.",
        include_zero=True,
    )
    add(
        "Deepest target-wall command",
        "peak_target_wall_gap_time",
        "max_target_wall_gap_cm",
        "Target past wall [cm]",
        "Use wall_target.png to separate the commanded target crossing from the actual hand contact.",
    )
    add(
        "Peak wall penetration",
        "peak_wall_penetration_time",
        "max_wall_penetration_cm",
        "Penetration [cm]",
        "Check whether the hand pushed too far through the virtual wall.",
    )
    add(
        "Peak wall force",
        "peak_wall_force_time",
        "max_abs_virtual_wall_force",
        "Wall force",
        "Compare this moment with wall stiffness, damping, and retreat settings.",
    )
    add(
        "Peak damping force",
        "peak_wall_damping_force_time",
        "max_abs_virtual_wall_damping_force",
        "Damping force",
        "Use this for slow/fast approach comparisons where velocity changes the wall response.",
    )
    add(
        "Wall contact release",
        "first_wall_release_time",
        "final_wall_phase",
        "Final phase",
        "Use this timestamp to check whether backing away actually cleared the wall contact.",
        include_zero=True,
    )
    add(
        "Target backs away",
        "first_target_wall_return_time",
        "final_target_wall_gap_cm",
        "Final target-wall [cm]",
        "This marks the learner or replay command returning the target before the wall plane.",
        include_zero=True,
    )
    add(
        "Peak hand speed",
        "peak_hand_speed_time",
        "max_hand_speed",
        "Hand speed [m/s]",
        "Look at the approach speed that produced the largest wall damping response.",
    )
    add(
        "Peak Cartesian error",
        "peak_cartesian_error_time",
        "max_cartesian_error_cm",
        "Error [cm]",
        "Use this for Cartesian reach runs to find the largest target-tracking gap.",
    )
    return rows


def _result_checks(summary: dict[str, Any]) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    samples = _number(summary.get("samples"))
    if samples is not None:
        state = "OK" if samples > 0 else "Review"
        checks.append(("Data saved", state, f"{_format_value(samples)} samples recorded."))

    duration = _number(summary.get("duration"))
    if duration is not None and duration > 0.0:
        checks.append(("Simulation time", "OK", f"{_format_value(duration)} seconds simulated."))

    _add_abs_limit_check(checks, summary, "final_tracking_error", "Final tracking error", 0.02, "m")
    _add_abs_limit_check(checks, summary, "final_joint_error_norm", "Final joint error", 0.1, "rad norm")
    _add_abs_limit_check(checks, summary, "final_task_error_norm", "Final hand error", 0.05, "m norm")
    _add_abs_limit_check(checks, summary, "final_cartesian_error_cm", "Final Cartesian error", 2.0, "cm")
    _add_abs_limit_check(checks, summary, "max_abs_tau_cmd", "Actuator effort", 60.0, "force / torque proxy")
    disturbance = _number(summary.get("max_abs_tau_disturbance"))
    if disturbance is not None and disturbance > 0.0:
        checks.append(
            (
                "Disturbance pulse",
                "Review",
                f"External torque pulse reached {_format_value(disturbance)} N m; compare disturbance and error plots.",
            )
        )
        recovery_duration = _number(summary.get("disturbance_recovery_duration"))
        if recovery_duration is not None:
            checks.append(
                (
                    "Disturbance recovery",
                    "OK" if bool(summary.get("disturbance_recovered")) else "Inspect",
                    f"Joint error returned to the recovery band after {_format_value(recovery_duration)} seconds.",
                )
            )
        elif summary.get("disturbance_recovered") is False:
            checks.append(
                (
                    "Disturbance recovery",
                    "Inspect",
                    "Joint error did not return to the pre-disturbance recovery band before the run ended.",
                )
            )

    qdot = _number(summary.get("max_settled_abs_qdot"))
    drift = _number(summary.get("max_joint_drift_norm"))
    if duration is not None and duration >= 30.0 and qdot is not None and drift is not None:
        speed_ok = qdot <= 0.02
        drift_ok = drift <= 0.02
        stable = speed_ok and drift_ok
        checks.append(
            (
                "Settled joint speed",
                "OK" if speed_ok else "Inspect",
                f"Maximum joint speed after the first second {_format_value(qdot)} rad/s.",
            )
        )
        checks.append(("Joint drift stability", "OK" if drift_ok else "Inspect", f"Maximum joint drift {_format_value(drift)} rad norm."))
        checks.append(
            (
                "30s stability hold",
                "OK" if stable else "Inspect",
                (
                    f"{_format_value(duration)} second hold with settled max joint speed {_format_value(qdot)} rad/s "
                    f"and drift {_format_value(drift)} rad norm."
                ),
            )
        )

    overshoot = _number(summary.get("overshoot_percent"))
    if overshoot is not None:
        state = "OK" if overshoot <= 20.0 else "Inspect"
        checks.append(("Overshoot", state, f"{_format_value(overshoot)} percent peak overshoot."))

    condition = _number(summary.get("max_jacobian_condition"))
    if condition is not None:
        if condition <= 20.0:
            state = "OK"
        elif condition <= 100.0:
            state = "Watch"
        else:
            state = "Inspect"
        checks.append(
            (
                "Jacobian condition",
                state,
                f"Maximum condition number {_format_value(condition)}; high values mark near-singular motion.",
            )
        )

    manipulability_value = _number(summary.get("min_manipulability"))
    if manipulability_value is not None:
        state = "Inspect" if manipulability_value <= 0.03 else "OK"
        checks.append(
            (
                "Manipulability",
                state,
                f"Minimum manipulability {_format_value(manipulability_value)}; lower values are closer to singularity.",
            )
        )

    dls_speed = _number(summary.get("max_dls_joint_speed"))
    if dls_speed is not None:
        state = "OK" if dls_speed <= 3.5 else "Inspect"
        checks.append(
            (
                "DLS joint speed",
                state,
                f"Maximum DLS joint speed {_format_value(dls_speed)} rad/s proxy; raise damping if this is high.",
            )
        )

    dls_scale = _number(summary.get("max_dls_condition_scale"))
    dls_damping = _number(summary.get("max_dls_damping"))
    if dls_scale is not None and dls_scale > 0.0:
        checks.append(
            (
                "Condition-aware DLS",
                "Observed",
                (
                    f"Damping schedule reached {_format_value(dls_scale)} of its range"
                    + (f" with max damping {_format_value(dls_damping)}." if dls_damping is not None else ".")
                ),
            )
        )

    wall_penetration = _number(summary.get("max_wall_penetration_cm"))
    if wall_penetration is not None and wall_penetration > 0.0:
        state = "Observed" if wall_penetration <= 5.0 else "Inspect"
        checks.append(
            (
                "Virtual wall contact",
                state,
                f"Maximum penetration {_format_value(wall_penetration)} cm; this means the wall lesson was triggered.",
            )
        )

    wall_retreat = _number(summary.get("max_wall_retreat_cm"))
    if wall_retreat is not None and wall_retreat > 0.0:
        checks.append(("Wall retreat", "Observed", f"Maximum retreat command {_format_value(wall_retreat)} cm."))

    wall_contact_start = _number(summary.get("first_wall_contact_time"))
    wall_contact_duration = _number(summary.get("wall_contact_duration"))
    wall_contact_fraction = _number(summary.get("wall_contact_fraction"))
    if wall_contact_start is not None and wall_contact_duration is not None:
        fraction_text = (
            f"; {_format_value(100.0 * wall_contact_fraction)}% of the run"
            if wall_contact_fraction is not None
            else ""
        )
        checks.append(
            (
                "Wall contact timing",
                "Observed",
                (
                    f"First contact at {_format_value(wall_contact_start)} s; "
                    f"contact duration {_format_value(wall_contact_duration)} s{fraction_text}."
                ),
            )
        )

    target_wall_gap = _number(summary.get("max_target_wall_gap_cm"))
    if target_wall_gap is not None and target_wall_gap > 0.0:
        final_phase = str(summary.get("final_wall_phase") or "").strip()
        phase_text = f"; final phase {final_phase}" if final_phase else ""
        first_cross = _number(summary.get("first_target_wall_cross_time"))
        cross_text = f" at {_format_value(first_cross)} s" if first_cross is not None else ""
        checks.append(
            (
                "Target-wall command",
                "Observed",
                f"Target moved {_format_value(target_wall_gap)} cm past the wall{cross_text}{phase_text}.",
            )
        )

    target_return = _number(summary.get("first_target_wall_return_time"))
    if target_return is not None:
        checks.append(
            (
                "Target backed away",
                "Observed",
                f"Target returned before the wall at {_format_value(target_return)} s.",
            )
        )

    wall_release = _number(summary.get("first_wall_release_time"))
    if wall_release is not None:
        checks.append(
            (
                "Wall contact release",
                "Observed",
                f"Penetration returned to zero after contact at {_format_value(wall_release)} s.",
            )
        )

    wall_force = _number(summary.get("max_abs_virtual_wall_force"))
    if wall_force is not None and wall_force > 0.0:
        state = "Observed" if wall_force <= 80.0 else "Inspect"
        checks.append(("Wall force", state, f"Maximum virtual wall force {_format_value(wall_force)}."))

    wall_spring_force = _number(summary.get("max_abs_virtual_wall_spring_force"))
    wall_damping_force = _number(summary.get("max_abs_virtual_wall_damping_force"))
    if wall_spring_force is not None and wall_damping_force is not None and wall_spring_force > 0.0:
        checks.append(
            (
                "Wall force components",
                "Observed" if wall_damping_force > 0.0 else "Inspect",
                (
                    f"Spring force {_format_value(wall_spring_force)}; "
                    f"damping force {_format_value(wall_damping_force)}."
                ),
            )
        )

    interaction_events = _number(summary.get("interaction_events"))
    if interaction_events is not None and interaction_events > 0.0:
        checks.append(("Learner actions", "Recorded", f"{_format_value(interaction_events)} interaction events saved."))

    return checks


def _mission_evidence_items(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Any],
    config: dict[str, Any] | None = None,
    *,
    completion_decision: CompletionDecision | None = None,
) -> list[tuple[str, Any]]:
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    pending_outcomes = max(0, predictions - outcomes)
    learner_controls = _learner_control_event_count(events)
    plot_count = len(plots)
    required_labels, required_tried, next_required = _required_preset_progress(config or {}, events)

    requires_hands_on = _summary_requires_hands_on_evidence(summary)
    evidence_type = "Hands-on observation" if requires_hands_on else "Plot and worksheet artifacts"

    if requires_hands_on:
        if markers <= 0:
            if required_labels and len(required_tried) < len(required_labels):
                status = f"Needs required preset {next_required}" if next_required else "Needs required preset"
                next_step = (
                    f"Try required preset {next_required}, watch live status, then mark one observation."
                    if next_required
                    else "Try the remaining required preset, watch live status, then mark one observation."
                )
            else:
                status = "Needs observation"
                next_step = "Run the demo, write a prediction, then press Mark observation."
        elif predictions <= 0:
            status = "Needs prediction"
            next_step = "Repeat or continue the demo and save a Mark observation with a prediction."
        elif required_labels and len(required_tried) < len(required_labels):
            status = f"Needs required preset {next_required}" if next_required else "Needs required preset"
            next_step = (
                f"Try required preset {next_required}, watch live status, then mark one observation."
                if next_required
                else "Try the remaining required preset, watch live status, then mark one observation."
            )
        elif notes <= 0:
            status = "Ready, add note next"
            next_step = "Compare the prediction with the plots and add a short learner note next time."
        elif learner_controls <= 0:
            status = "Needs learner control"
            next_step = f"Use {_report_learner_control_phrase(config, summary)}, then mark the observation."
        elif predictions > 0 and pending_outcomes > 0:
            status = "Outcome review pending"
            next_step = "Choose Matched, Partly matched, or Surprised for each saved prediction."
        else:
            status = "Ready for review"
            next_step = "Compare mission evidence with the priority plot, then run Next or Compare."
    elif predictions > 0 and pending_outcomes > 0:
        status = "Outcome review pending"
        next_step = "Choose Matched, Partly matched, or Surprised for each saved prediction."
    else:
        evidence_type = "Plot and worksheet artifacts"
        if plot_count > 0:
            status = "Artifacts ready"
            next_step = "Review the priority plot and worksheet, then run Next or Compare."
        else:
            status = "Needs plot"
            next_step = "Rerun with --plot so the mission can be checked visually."

    items: list[tuple[str, Any]] = [
        ("Evidence type", evidence_type),
        ("Status", status),
        ("Observation markers", markers),
        ("Predictions", predictions),
        ("Prediction outcomes", outcomes),
        ("Learner notes", notes),
        ("Learner controls", learner_controls),
        ("Saved plots", plot_count),
        ("Next proof step", next_step),
    ]
    if required_labels:
        items.insert(7, ("Required presets", " -> ".join(required_labels)))
        items.insert(8, ("Required presets tried", f"{len(required_tried)}/{len(required_labels)}"))
    if completion_decision is not None and not completion_decision.complete:
        contract_status = _completion_status_text(completion_decision, summary)
        items = [
            (key, contract_status if key == "Status" else value)
            for key, value in items
        ]
        next_index = next(
            (index for index, (key, _value) in enumerate(items) if key == "Next proof step"),
            len(items),
        )
        items.insert(
            next_index,
            ("Completion reason", completion_decision.primary_reason.value),
        )
        contract_next = (
            f"Resolve {completion_decision.primary_reason.value} before treating this "
            "run as mission evidence."
        )
        items = [
            (key, contract_next if key == "Next proof step" else value)
            for key, value in items
        ]
    return items


def _challenge_evidence_items(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Any],
    config: dict[str, Any] | None = None,
    *,
    completion_decision: CompletionDecision | None = None,
) -> list[tuple[str, Any]]:
    guide = guide_for_run_summary(summary)
    challenge = challenge_prompt_for_guide(guide).removeprefix("Challenge:").strip()
    mission_items = dict(
        _mission_evidence_items(
            summary,
            events,
            plots,
            config,
            completion_decision=completion_decision,
        )
    )
    mission_status = str(mission_items.get("Status") or "")
    mission_next_step = str(mission_items.get("Next proof step") or "")
    requires_hands_on = _summary_requires_hands_on_evidence(summary)
    return [
        ("Challenge", challenge or "Name one visible change and point to the evidence that proves it."),
        ("Challenge status", _challenge_status_text(mission_status)),
        ("Proof source", _challenge_proof_source(requires_hands_on)),
        ("Mission evidence status", mission_status),
        ("Next challenge step", _challenge_next_step(mission_status, mission_next_step, requires_hands_on)),
    ]


def _challenge_status_text(mission_status: str) -> str:
    status = mission_status.strip().lower()
    if status in {"artifacts ready", "ready for review"}:
        return "Ready to review"
    if status == "outcome review pending":
        return "Needs prediction outcome review"
    if status == "ready, add note next":
        return "Needs learner note"
    if status.startswith("needs required preset"):
        return "Needs required preset evidence"
    if status == "needs learner control":
        return "Needs learner control evidence"
    if status == "needs prediction":
        return "Needs prediction evidence"
    if status == "needs observation":
        return "Needs observation evidence"
    if status == "needs plot":
        return "Needs plot evidence"
    return mission_status or "Needs evidence"


def _challenge_proof_source(requires_hands_on: bool) -> str:
    if requires_hands_on:
        return "Learner control, Mark observation, live status, and priority plot"
    return "Priority plot and worksheet"


def _challenge_next_step(mission_status: str, mission_next_step: str, requires_hands_on: bool) -> str:
    status = mission_status.strip().lower()
    if status in {"artifacts ready", "ready for review"}:
        if requires_hands_on:
            return "Compare the prediction-backed observation with the priority plot and worksheet."
        return "Compare the challenge statement with the priority plot and worksheet."
    if mission_next_step:
        return mission_next_step
    return "Rerun the scenario and collect the missing challenge evidence."


def _mission_evidence_section(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Path],
    config: dict[str, Any],
    completion_decision: CompletionDecision,
) -> str:
    return (
        "<section>"
        "<h2>Mission Evidence</h2>"
        '<div class="action-grid">'
        '<article class="action-card action-wide">'
        "<strong>Mission proof status</strong>"
        '<p class="empty">Use this before moving on: it tells whether the mission has enough saved evidence.</p>'
        f"{_action_value_list(_mission_evidence_items(summary, events, plots, config, completion_decision=completion_decision))}"
        "</article>"
        "</div>"
        "</section>"
    )


def _challenge_evidence_section(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[Path],
    config: dict[str, Any],
    completion_decision: CompletionDecision,
) -> str:
    return (
        "<section>"
        "<h2>Challenge Evidence</h2>"
        '<div class="action-grid">'
        '<article class="action-card action-wide">'
        "<strong>Challenge proof status</strong>"
        '<p class="empty">Use this after the run: it turns the visible-effect challenge into evidence to check.</p>'
        f"{_action_value_list(_challenge_evidence_items(summary, events, plots, config, completion_decision=completion_decision))}"
        "</article>"
        "</div>"
        "</section>"
    )


def _report_learner_control_phrase(config: dict[str, Any] | None, summary: dict[str, Any] | None = None) -> str:
    report_config = _report_control_config(config, summary)
    label_phrase = _learner_control_phrase_for_config(report_config)
    if label_phrase:
        return label_phrase
    text = learner_control_action_text_for_config(report_config).strip()
    prefix = "Use "
    suffix = " before moving on."
    if text.startswith(prefix) and text.endswith(suffix):
        phrase = text[len(prefix) : -len(suffix)].strip()
        if phrase and phrase != "one learner control":
            return phrase
    return "at least one button, slider, or preset"


def _report_control_config(config: dict[str, Any] | None, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    if config:
        return config
    if not isinstance(summary, dict):
        return {}
    config_path = str(summary.get("config_path") or "").strip()
    if not config_path:
        return {}
    try:
        return load_config(config_path)
    except (OSError, ValueError):
        return {}


def _report_learner_control_once_phrase(config: dict[str, Any] | None, summary: dict[str, Any] | None = None) -> str:
    phrase = _report_learner_control_phrase(config, summary)
    if phrase.startswith("at least one "):
        return phrase
    return f"{phrase} at least once"


def _hands_on_evidence_section(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> str:
    if not _summary_requires_hands_on_evidence(summary):
        return ""
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    learner_controls = _learner_control_event_count(events)
    control_once = _report_learner_control_once_phrase(config, summary)
    if markers > 0 and predictions > 0 and notes > 0 and learner_controls > 0:
        status = "Done for learning path"
        detail = "This hands-on run has one learner control plus a Mark observation with prediction and note."
    elif markers > 0 and predictions > 0 and notes > 0:
        status = "Needs learner control"
        detail = f"Repeat this hands-on step and use {control_once} before review."
    elif markers > 0 and predictions > 0:
        status = "Needs note"
        detail = "Add a learner note or Use live status before moving on."
    elif markers > 0:
        status = "Needs prediction"
        detail = "Repeat this hands-on step and fill the Prediction field before pressing Mark observation."
    else:
        status = "Needs observation"
        detail = (
            f"Repeat this hands-on step, use {control_once}, write a prediction and note, "
            "then press Mark observation."
        )
    items: list[tuple[str, Any]] = [
        ("Status", status),
        ("Observation markers", markers),
        ("Predictions", predictions),
        ("Prediction outcomes", outcomes),
        ("Learner notes", notes),
        ("Learner controls", learner_controls),
    ]
    return (
        "<section>"
        "<h2>Hands-on Evidence</h2>"
        '<div class="action-grid">'
        '<article class="action-card action-wide">'
        "<strong>Learning path completion</strong>"
        f'<p class="empty">{escape(detail)}</p>'
        f"{_action_value_list(items)}"
        "</article>"
        "</div>"
        "</section>"
    )


def _run_completion_text(summary: dict[str, Any]) -> str:
    if _summary_requires_hands_on_evidence(summary):
        return (
            "Done when: use at least one button, slider, or preset, then save one Mark observation "
            "with a Prediction and note; add the outcome during review."
        )
    return "Done when: report.html, priority plot, and worksheet.md are saved."


def _summary_requires_hands_on_evidence(summary: dict[str, Any]) -> bool:
    config_text = " ".join(str(summary.get(name) or "") for name in ("config_path", "config_name")).lower()
    if "interactive" in config_text:
        return True

    config_path = str(summary.get("config_path") or "").strip()
    if not config_path:
        return False
    interaction = _config_for_path(config_path).get("interaction")
    if not isinstance(interaction, dict):
        return False
    return bool(interaction.get("panel") or interaction.get("live_tuning"))


def _observation_evidence_counts_from_events(events: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    markers = 0
    predictions = 0
    notes = 0
    outcomes = 0
    for event in events:
        if not _is_observation_marker(event):
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


NON_LEARNER_CONTROL_BUTTON_NAMES = {
    "clear_observation_note",
    "pause_simulation",
    "resume_simulation",
    "step_simulation",
    "use_changed_values_note",
    "use_live_status_note",
}
NON_LEARNER_CONTROL_SLIDER_NAMES = {"playback_speed"}


def _learner_control_event_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for event in events if _is_learner_control_event(event))


def _is_learner_control_event(event: dict[str, Any]) -> bool:
    kind = str(event.get("kind") or "").strip().lower()
    name = str(event.get("name") or "").strip().lower()
    if kind == "preset":
        return True
    if kind == "slider":
        return name not in NON_LEARNER_CONTROL_SLIDER_NAMES
    if kind != "button":
        return False
    return name not in NON_LEARNER_CONTROL_BUTTON_NAMES


def _check_state_class(state: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in state).strip("-")
    return f"check-{normalized or 'state'}"


def _add_abs_limit_check(
    checks: list[tuple[str, str, str]],
    summary: dict[str, Any],
    key: str,
    title: str,
    limit: float,
    unit: str,
) -> None:
    value = _number(summary.get(key))
    if value is None:
        return
    state = "OK" if abs(value) <= limit else "Inspect"
    checks.append((title, state, f"{_format_value(value)} {unit}; suggested limit {_format_value(limit)}."))


def _learner_action_summary_section(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> str:
    if not events:
        return ""
    cards = [
        _action_card(
            "Actions recorded",
            f"{len(events)} total learner action{'s' if len(events) != 1 else ''}.",
            _action_value_list(_kind_count_items(events)),
        ),
        _latest_action_card(events[-1]),
    ]
    latest_sliders = _latest_named_event_values(events, "slider")
    if latest_sliders:
        cards.append(
            _action_card(
                "Latest slider values",
                "Most recent value saved for each changed slider.",
                _action_value_list(latest_sliders),
            )
        )
    activity_mix = _activity_mix_card(events, config)
    if activity_mix:
        cards.append(activity_mix)
    preset_progress = _preset_comparison_progress_card(events, config)
    if preset_progress:
        cards.append(preset_progress)
    preset_card = _preset_choices_card(events)
    if preset_card:
        cards.append(preset_card)
    return (
        "<section>"
        "<h2>Learner Action Summary</h2>"
        '<p class="empty">Use this summary to connect live controls and presets to the plots below.</p>'
        '<div class="action-grid">'
        f"{''.join(cards)}"
        "</div>"
        "</section>"
    )


def _learner_snapshot_section(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return ""
    cards: list[str] = []
    slider_values = snapshot.get("slider_values")
    changed_sliders = snapshot.get("changed_sliders")
    live_status = snapshot.get("live_status")

    if isinstance(changed_sliders, dict) and changed_sliders:
        cards.append(
            _action_card(
                "Changed slider values",
                "Final values for sliders that moved away from the run's starting values.",
                _action_value_list(changed_sliders.items()),
            )
        )
    if isinstance(slider_values, dict) and slider_values:
        cards.append(
            _action_card(
                "Final slider values",
                "Complete slider state at the end of the run.",
                _action_value_list(slider_values.items()),
            )
        )
    if isinstance(live_status, dict) and live_status:
        cards.append(
            _action_card(
                "Final live status",
                "Last learner-facing status values computed for the interaction panel.",
                _action_value_list(live_status.items()),
            )
        )

    controls: list[tuple[str, Any]] = []
    if "playback_speed" in snapshot:
        controls.append(("Playback speed", snapshot.get("playback_speed")))
    extra_controls = snapshot.get("extra_controls")
    if isinstance(extra_controls, dict):
        controls.extend(extra_controls.items())
    if controls:
        cards.append(
            _action_card(
                "Final control state",
                "Non-slider learner controls that affect how the run was viewed or nudged.",
                _action_value_list(controls),
            )
        )

    if not cards:
        return ""
    return (
        "<section>"
        "<h2>Learner Snapshot</h2>"
        '<p class="empty">Use this snapshot to reconstruct the final hands-on state without reading the full event log.</p>'
        '<div class="action-grid">'
        f"{''.join(cards)}"
        "</div>"
        "</section>"
    )


def _latest_action_card(event: dict[str, Any]) -> str:
    items = [
        ("Type", str(event.get("kind", ""))),
        ("Control", _event_label(event)),
        ("Time [s]", _format_value(event.get("time"))),
    ]
    return _action_card("Latest action", "Last recorded learner interaction.", _action_value_list(items))


def _preset_comparison_progress_card(events: list[dict[str, Any]], config: dict[str, Any] | None) -> str:
    if not config:
        return ""
    configured_labels = _configured_preset_labels(config)
    if len(configured_labels) < 2:
        return ""
    tried_labels = _distinct_preset_labels(events, configured_labels)
    required_labels = _configured_required_preset_labels(config)
    required_tried, next_required = _ordered_required_preset_progress(
        required_labels,
        _preset_event_labels(events, configured_labels),
    )
    items = _preset_comparison_progress_items(
        configured_labels,
        tried_labels,
        required_labels,
        required_tried,
        next_required,
    )
    return _action_card(
        "Preset comparison progress",
        "Checks whether this hands-on run sampled more than one preset regime.",
        _action_value_list(items),
    )


def _preset_comparison_progress_items(
    configured_labels: list[str],
    tried_labels: list[str],
    required_labels: list[str] | None = None,
    required_tried: list[str] | None = None,
    next_required: str = "",
) -> list[tuple[str, Any]]:
    required_labels = required_labels or []
    required_tried = required_tried or []
    next_label = next((label for label in configured_labels if label not in tried_labels), "")
    if required_labels:
        if next_required:
            status = "Needs required preset"
            next_step = f"Try required preset {next_required}, watch live status, then mark one observation."
        else:
            status = "Ready for comparison review"
            next_step = "Mark or review an observation comparing the required presets."
    elif len(tried_labels) >= 2:
        status = "Ready for comparison review"
        next_step = "Mark or review an observation comparing the tried presets."
    elif next_label:
        status = "Needs another preset"
        next_step = f"Try {next_label}, watch live status, then mark one observation."
    else:
        status = "Needs another preset"
        next_step = "Try at least one more preset, then mark one observation."
    items: list[tuple[str, Any]] = [
        ("Configured presets", len(configured_labels)),
        ("Preset order", " -> ".join(configured_labels)),
        ("Distinct presets tried", f"{len(tried_labels)}/{len(configured_labels)}"),
        ("Tried", ", ".join(tried_labels) if tried_labels else "none yet"),
        ("Next", next_step),
        ("Status", status),
    ]
    if required_labels:
        items.insert(2, ("Required presets", " -> ".join(required_labels)))
        items.insert(4, ("Required presets tried", f"{len(required_tried)}/{len(required_labels)}"))
    return items


def _distinct_preset_labels(events: list[dict[str, Any]], configured_labels: list[str]) -> list[str]:
    seen: list[str] = []
    for canonical in _preset_event_labels(events, configured_labels):
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen


def _preset_event_labels(events: list[dict[str, Any]], configured_labels: list[str]) -> list[str]:
    configured_lookup = {label.lower(): label for label in configured_labels}
    labels: list[str] = []
    for event in events:
        if str(event.get("kind", "")).lower() != "preset":
            continue
        label = _event_label(event)
        canonical = configured_lookup.get(label.lower())
        if canonical:
            labels.append(canonical)
    return labels


def _ordered_required_preset_progress(
    required_labels: list[str],
    attempted_labels: list[str],
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


def _preset_choices_card(events: list[dict[str, Any]]) -> str:
    preset_events = [event for event in events if str(event.get("kind", "")).lower() == "preset"]
    if not preset_events:
        return ""
    details = "".join(_preset_choice_detail(event) for event in preset_events[-4:])
    count_text = (
        f"Showing the latest 4 of {len(preset_events)} preset choices."
        if len(preset_events) > 4
        else f"{len(preset_events)} preset choice{'s' if len(preset_events) != 1 else ''} recorded."
    )
    return (
        '<article class="action-card action-wide">'
        "<strong>Preset choices</strong>"
        f'<p class="empty">{escape(count_text)}</p>'
        f"{details}"
        "</article>"
    )


def _preset_choice_detail(event: dict[str, Any]) -> str:
    value = event.get("value")
    purpose, items = _preset_choice_items(value)
    purpose_text = (
        f'<p class="empty"><strong>Purpose:</strong> {escape(purpose)}</p>'
        if purpose
        else ""
    )
    return (
        '<div class="action-detail">'
        f"<strong>{escape(_event_label(event))}</strong>"
        f'<span class="marker-time">time {_format_value(event.get("time"))} s</span>'
        f"{purpose_text}"
        f"{_action_value_list(items)}"
        "</div>"
    )


def _preset_choice_items(value: Any) -> tuple[str, Any]:
    if not isinstance(value, dict):
        return "", (("value", value),)
    purpose = str(value.get("purpose") or value.get("description") or "").strip()
    items: list[tuple[str, Any]] = []
    if value.get("required"):
        items.append(("Required evidence", "yes"))
    values = value.get("values")
    if isinstance(values, dict):
        items.extend(values.items())
        return purpose, items
    items.extend(
        (key, item)
        for key, item in value.items()
        if key not in {"purpose", "description", "required"}
    )
    return purpose, items


def _action_card(title: str, description: str, body: str) -> str:
    return (
        '<article class="action-card">'
        f"<strong>{escape(title)}</strong>"
        f'<p class="empty">{escape(description)}</p>'
        f"{body}"
        "</article>"
    )


def _action_value_list(items: Any) -> str:
    rows = "\n".join(
        (
            "<li>"
            f"<span>{escape(str(key))}</span>"
            f"<strong>{escape(_format_value(value))}</strong>"
            "</li>"
        )
        for key, value in items
    )
    return f'<ul class="action-list">{rows}</ul>' if rows else ""


def _kind_count_items(events: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for event in events:
        kind = str(event.get("kind", "") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return sorted(counts.items())


def _activity_mix_card(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> str:
    items = _activity_mix_items(events, config)
    if not items:
        return ""
    return _action_card(
        "Hands-on activity mix",
        "Checks whether the run used multiple kinds of learner interaction before review.",
        _action_value_list(items),
    )


def _activity_mix_items(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[tuple[str, Any]]:
    if not events:
        return []
    counts = _event_kind_counts(events)
    control_kinds = ("button", "slider", "preset", "marker")
    observation_markers = sum(1 for event in events if _is_observation_marker(event))
    has_buttons, has_sliders, has_presets = _activity_available_control_families(config, counts)
    available_control_kinds = {
        "button": has_buttons,
        "slider": has_sliders,
        "preset": has_presets,
    }
    used_kinds = [
        kind
        for kind in control_kinds
        if counts.get(kind, 0) > 0
        and (
            (kind == "marker" and observation_markers > 0)
            or available_control_kinds.get(kind, False)
        )
    ]
    available_controls = [kind for kind, available in available_control_kinds.items() if available]
    varied_controls = sum(1 for kind in available_controls if counts.get(kind, 0) > 0)
    total_controls = sum(counts.get(kind, 0) for kind in available_controls)
    next_step = _activity_mix_next_step(
        counts,
        observation_markers,
        config=config,
        has_buttons=has_buttons,
        has_sliders=has_sliders,
        has_presets=has_presets,
    )
    return [
        ("Control types used", " -> ".join(used_kinds) if used_kinds else "none"),
        ("Activity path", _activity_path(events)),
        ("Button actions", counts.get("button", 0)),
        ("Slider changes", counts.get("slider", 0)),
        ("Preset choices", counts.get("preset", 0)),
        ("Observation markers", observation_markers),
        ("Hands-on controls before review", total_controls),
        ("Interaction variety", f"{varied_controls}/{len(available_controls)} control families"),
        ("Next activity step", next_step),
    ]


def _activity_available_control_families(
    config: dict[str, Any] | None,
    counts: dict[str, int],
) -> tuple[bool, bool, bool]:
    if config is None:
        return True, True, True
    interaction = config.get("interaction") if isinstance(config, dict) else None
    if not isinstance(interaction, dict) or not interaction:
        return (
            counts.get("button", 0) > 0,
            counts.get("slider", 0) > 0,
            counts.get("preset", 0) > 0,
        )

    has_buttons, has_sliders, has_presets = learner_control_families_from_config(config)
    return (
        has_buttons or counts.get("button", 0) > 0,
        has_sliders or counts.get("slider", 0) > 0,
        has_presets or counts.get("preset", 0) > 0,
    )


def _activity_path(events: list[dict[str, Any]], *, limit: int = 6) -> str:
    steps: list[str] = []
    for event in events:
        kind = str(event.get("kind", "") or "unknown").lower()
        if kind not in {"button", "slider", "preset", "marker"}:
            continue
        if kind in {"button", "slider", "preset"} and not _is_learner_control_event(event):
            continue
        label = _event_label(event)
        if kind == "marker" and not _is_observation_marker(event):
            continue
        display_kind = "observation" if kind == "marker" else kind
        if display_kind == "observation" and label.lower() == "observation":
            label = "Mark observation"
        steps.append(f"{display_kind}: {label}")
    if not steps:
        return "none"
    shown = steps[:limit]
    if len(steps) > limit:
        shown.append(f"... {len(steps) - limit} more")
    return " -> ".join(shown)


def _event_kind_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        kind = str(event.get("kind", "") or "unknown").lower()
        if kind in {"button", "slider", "preset"} and not _is_learner_control_event(event):
            continue
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _activity_mix_next_step(
    counts: dict[str, int],
    observation_markers: int,
    *,
    config: dict[str, Any] | None = None,
    has_buttons: bool = True,
    has_sliders: bool = True,
    has_presets: bool = True,
) -> str:
    if has_presets and counts.get("preset", 0) <= 0:
        return "Try a Quick preset to compare a named parameter regime."
    if has_sliders and counts.get("slider", 0) <= 0:
        if has_presets:
            return "Move one slider after a preset to test a smaller parameter change."
        return "Move one live slider to test a smaller parameter change."
    if has_buttons and counts.get("button", 0) <= 0:
        return _activity_button_next_step(config)
    if observation_markers <= 0:
        return "Save one Mark observation with prediction and live-status evidence."
    return "Ready: compare this interaction mix against plots and the worksheet."


def _activity_button_next_step(config: dict[str, Any] | None = None) -> str:
    interaction = config.get("interaction") if isinstance(config, dict) else None
    if not isinstance(interaction, dict):
        return "Use one experiment button such as pulse, nudge, or reset."
    if bool(interaction.get("key_force", False)):
        return "Use Pull/Push buttons to apply a force pulse."
    if bool(interaction.get("joint_disturbance", False)):
        return "Use Shoulder/Elbow pulse buttons to disturb a joint."
    if bool(interaction.get("target_nudge", False)):
        left = str(interaction.get("target_left_label") or "").strip()
        right = str(interaction.get("target_right_label") or "").strip()
        if left and right:
            return f"Use {left} / {right} target buttons."
        return "Use target nudge buttons to move the commanded target."
    if bool(interaction.get("reset_plant", interaction.get("reset_experiment", False))):
        return "Use Reset plant after changing a control to repeat the observation."
    return "Use one experiment button such as pulse, nudge, or reset."


def _latest_named_event_values(events: list[dict[str, Any]], kind: str) -> list[tuple[str, Any]]:
    values: dict[str, Any] = {}
    for event in events:
        if str(event.get("kind", "")).lower() != kind:
            continue
        values[_event_label(event)] = event.get("value")
    return list(values.items())


def _event_label(event: dict[str, Any]) -> str:
    return str(event.get("label") or event.get("name") or "").strip()


def _interaction_section(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    shown_events = events[-20:]
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{escape(_format_value(event.get('time')))}</td>"
            f"<td>{escape(str(event.get('kind', '')))}</td>"
            f"<td>{escape(str(event.get('label') or event.get('name') or ''))}</td>"
            f"<td>{escape(str(event.get('name', '')))}</td>"
            f"<td>{escape(_format_value(event.get('value')))}</td>"
            "</tr>"
        )
        for event in shown_events
    )
    count_text = (
        f"Showing the latest {len(shown_events)} of {len(events)} learner actions."
        if len(events) > len(shown_events)
        else f"{len(events)} learner action{'s' if len(events) != 1 else ''} recorded."
    )
    return (
        "<section>"
        "<h2>Interaction Log</h2>"
        f'<p class="empty">{escape(count_text)}</p>'
        '<table class="timeline-table">'
        "<thead><tr><th>Time [s]</th><th>Type</th><th>Control</th><th>Name</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</section>"
    )


def _observation_timeline_section(events: list[dict[str, Any]]) -> str:
    markers = [event for event in events if _is_observation_marker(event)]
    items = _observation_timeline_items(events, limit=12)
    if not items:
        return ""
    rows = "\n".join(
        (
            "<tr>"
            f"<td>Observation {escape(item['index'])}</td>"
            f"<td>{escape(item['time'])}</td>"
            f"<td>{escape(item['prediction'] or 'missing')}</td>"
            f"<td>{escape(item['outcome'] or 'missing')}</td>"
            f"<td>{escape(item['challenge_proof'] or 'missing')}</td>"
            f"<td>{escape(item['note'] or 'missing')}</td>"
            f"<td>{escape(item['status'] or 'n/a')}</td>"
            "</tr>"
        )
        for item in items
    )
    count_text = (
        f"Showing the latest {len(items)} of {len(markers)} observations in time order."
        if len(markers) > len(items)
        else f"{len(items)} observation{'s' if len(items) != 1 else ''} shown in time order."
    )
    return (
        "<section>"
        "<h2>Observation Timeline</h2>"
        f'<p class="empty">{escape(count_text)}</p>'
        "<table>"
        "<thead><tr><th>Marker</th><th>Time [s]</th><th>Prediction</th><th>Outcome</th>"
        "<th>Challenge proof</th><th>Note evidence</th><th>Live status</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</section>"
    )


def _observation_timeline_items(events: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, str]]:
    markers = [
        (index, event)
        for index, event in enumerate((event for event in events if _is_observation_marker(event)), start=1)
    ]
    if limit is not None and len(markers) > limit:
        markers = markers[-limit:]
    items: list[dict[str, str]] = []
    for index, marker in markers:
        payload = marker.get("value")
        value = payload if isinstance(payload, dict) else {}
        prediction = _short_evidence_text(str(value.get("prediction") or ""), max_length=88)
        outcome = _short_evidence_text(str(value.get("outcome") or ""), max_length=40)
        challenge_proof = _short_evidence_text(str(value.get("challenge_proof") or ""), max_length=96)
        note = str(value.get("note") or "").strip()
        note_evidence = _note_evidence_summary(note) or _short_evidence_text(note, max_length=88)
        status = value.get("status")
        status_evidence = _latest_status_evidence(status, limit=3) if isinstance(status, dict) else ""
        items.append(
            {
                "index": str(index),
                "time": _format_value(marker.get("time")),
                "prediction": prediction,
                "outcome": outcome,
                "challenge_proof": challenge_proof,
                "note": note_evidence,
                "status": status_evidence,
            }
        )
    return items


def _observation_flow_text_from_events(events: list[dict[str, Any]]) -> str:
    items = _observation_timeline_items(events)
    if not items:
        return ""
    if len(items) == 1:
        return f"Observation flow: 1 marker; {_observation_flow_item_summary(items[0], include_note=True)}"
    first = items[0]
    latest = items[-1]
    return (
        f"Observation flow: {len(items)} markers; "
        f"first {_observation_flow_item_summary(first, include_note=False)} -> "
        f"latest {_observation_flow_item_summary(latest, include_note=True)}"
    )


def _observation_flow_item_summary(item: dict[str, str], *, include_note: bool) -> str:
    prefix = f"{item['time']} s " if item["time"] and item["time"] != "n/a" else ""
    parts = ["prediction saved" if item["prediction"] else "prediction missing"]
    parts.append(f"outcome {item['outcome']}" if item["outcome"] else "outcome missing")
    if include_note and item["note"]:
        parts.append(f"note {_short_evidence_text(item['note'], max_length=88)}")
    if include_note and item["status"]:
        parts.append(f"status {_short_evidence_text(item['status'], max_length=64)}")
    return prefix + ", ".join(parts)


def _observation_next_step_text_from_events(
    events: list[dict[str, Any]],
    *,
    evidence_required: bool = False,
    learner_control_phrase: str = "",
) -> str:
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    learner_controls = _learner_control_event_count(events)
    needs_control = evidence_required and learner_controls <= 0
    control_phrase = learner_control_phrase.strip() or "at least one learner control"
    if markers <= 0:
        if evidence_required:
            if needs_control:
                return (
                    f"Observation next step: use {control_phrase}, then mark one observation "
                    "with a prediction and note."
                )
            return "Observation next step: mark one observation with a prediction and note."
        return ""
    if predictions < markers:
        missing = markers - predictions
        if needs_control:
            return (
                "Observation next step: add a prediction and use "
                f"{control_phrase} before marking the next observation "
                f"({missing} marker{'s' if missing != 1 else ''} missing prediction; "
                "no learner control yet)."
            )
        return (
            "Observation next step: add a prediction before marking the next observation "
            f"({missing} marker{'s' if missing != 1 else ''} missing prediction)."
        )
    if notes < markers:
        missing = markers - notes
        if needs_control:
            return (
                "Observation next step: add a learner note or Use live status snapshot, then use "
                f"{control_phrase} before marking the next observation "
                f"({missing} marker{'s' if missing != 1 else ''} missing note evidence; "
                "no learner control yet)."
            )
        return (
            "Observation next step: add a learner note or Use live status snapshot "
            f"({missing} marker{'s' if missing != 1 else ''} missing note evidence)."
        )
    if outcomes < predictions:
        missing = predictions - outcomes
        return (
            "Observation next step: judge "
            f"{missing} prediction outcome{'s' if missing != 1 else ''} "
            "(Matched, Partly matched, or Surprised)."
        )
    if needs_control:
        return (
            f"Observation next step: use {control_phrase}, then mark another observation "
            "with a prediction and note."
        )
    return "Observation next step: ready for review; compare the saved markers with plots and worksheet."


def _observation_markers_section(
    events: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
) -> str:
    markers = [event for event in events if _is_observation_marker(event)]
    if not markers:
        return ""
    shown_markers = markers[-12:]
    cards = "\n".join(
        _observation_marker_card(marker, marker_index + 1)
        for marker_index, marker in enumerate(shown_markers)
    )
    count_text = (
        f"Showing the latest {len(shown_markers)} of {len(markers)} marked observations."
        if len(markers) > len(shown_markers)
        else f"{len(markers)} marked observation{'s' if len(markers) != 1 else ''} saved."
    )
    review_prompt = _observation_review_prompt(markers)
    prediction_review = _prediction_review_prompt(markers)
    evidence_review = _evidence_review_cue(
        events,
        markers,
        learner_control_phrase=_report_learner_control_phrase(config, summary),
    )
    return (
        "<section>"
        "<h2>Observation Markers</h2>"
        f'<p class="empty">{escape(count_text)}</p>'
        f"{review_prompt}"
        f"{prediction_review}"
        f"{evidence_review}"
        '<div class="marker-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _is_observation_marker(event: dict[str, Any]) -> bool:
    return str(event.get("kind", "")).lower() == "marker" and str(event.get("name", "")).lower() == "observation"


def _observation_review_prompt(markers: list[dict[str, Any]]) -> str:
    questions: list[str] = []
    predictions: list[str] = []
    outcomes: list[str] = []
    notes: list[str] = []
    for marker in markers:
        payload = marker.get("value")
        value = payload if isinstance(payload, dict) else {}
        question = str(value.get("question") or "").strip()
        prediction = str(value.get("prediction") or "").strip()
        outcome = str(value.get("outcome") or "").strip()
        note = str(value.get("note") or "").strip()
        if question and question not in questions:
            questions.append(question)
        if prediction:
            predictions.append(prediction)
        if outcome:
            outcomes.append(outcome)
        if note:
            notes.append(note)

    question_count = len(questions)
    prediction_count = len(predictions)
    outcome_count = len(outcomes)
    note_count = len(notes)
    latest_prediction = predictions[-1] if predictions else ""
    latest_note = notes[-1] if notes else ""
    latest_prediction_html = (
        f'<p class="empty"><strong>Latest prediction:</strong> {escape(latest_prediction)}</p>'
        if latest_prediction
        else ""
    )
    latest_note_html = (
        f'<p class="empty"><strong>Latest note:</strong> {escape(latest_note)}</p>'
        if latest_note
        else ""
    )
    latest_note_items = _note_evidence_items(latest_note)
    latest_note_evidence_html = ""
    if len(latest_note_items) > 1:
        rows = "\n".join(f"<li>{escape(item)}</li>" for item in latest_note_items)
        latest_note_evidence_html = (
            '<div class="marker-group">'
            "<strong>Latest note evidence</strong>"
            f"<ul>{rows}</ul>"
            "</div>"
        )
    return (
        '<div class="marker-group">'
        "<strong>Review prompt</strong>"
        f'<p>Use these markers as evidence before running the suggested next experiment. '
        f"{question_count} learning question{'s' if question_count != 1 else ''}, "
        f"{prediction_count} prediction{'s' if prediction_count != 1 else ''}, "
        f"{outcome_count} outcome{'s' if outcome_count != 1 else ''}, and "
        f"{note_count} learner note{'s' if note_count != 1 else ''} were saved.</p>"
        f"{latest_prediction_html}"
        f"{latest_note_html}"
        f"{latest_note_evidence_html}"
        "</div>"
    )


def _prediction_review_prompt(markers: list[dict[str, Any]]) -> str:
    predictions: list[str] = []
    notes: list[str] = []
    outcomes: list[str] = []
    evidence_prompts: list[str] = []
    for marker in markers:
        payload = marker.get("value")
        value = payload if isinstance(payload, dict) else {}
        prediction = str(value.get("prediction") or "").strip()
        note = str(value.get("note") or "").strip()
        outcome = str(value.get("outcome") or "").strip()
        evidence_prompt = str(value.get("evidence_prompt") or "").strip()
        if prediction:
            predictions.append(prediction)
        if note:
            notes.append(note)
        if outcome:
            outcomes.append(outcome)
        if evidence_prompt and evidence_prompt not in evidence_prompts:
            evidence_prompts.append(evidence_prompt)
    if not predictions:
        return ""

    items: list[tuple[str, Any]] = [
        ("Predictions saved", len(predictions)),
        ("Observation notes", len(notes)),
        ("Latest prediction", predictions[-1]),
    ]
    if notes:
        items.append(("Latest observation", notes[-1]))
    if outcomes:
        items.append(("Latest outcome", outcomes[-1]))
    if evidence_prompts:
        items.append(("Evidence to compare", evidence_prompts[-1]))
    return _action_card(
        "Prediction Review",
        "Compare each saved prediction against the plots, evidence prompt, and live status snapshot.",
        _action_value_list(items),
    )


def _evidence_review_cue_items(
    events: list[dict[str, Any]],
    markers: list[dict[str, Any]],
    *,
    learner_control_phrase: str = "",
) -> list[tuple[str, Any]]:
    ready_pairs = 0
    prediction_only = 0
    note_only = 0
    missing_both = 0
    outcome_judgments = 0
    learner_controls = _learner_control_event_count(events)
    control_phrase = learner_control_phrase.strip() or "one counted button, slider, or preset"
    for marker in markers:
        payload = marker.get("value")
        value = payload if isinstance(payload, dict) else {}
        has_prediction = bool(str(value.get("prediction") or "").strip())
        has_note = bool(str(value.get("note") or "").strip())
        has_outcome = bool(str(value.get("outcome") or "").strip())
        if has_outcome:
            outcome_judgments += 1
        if has_prediction and has_note:
            ready_pairs += 1
        elif has_prediction:
            prediction_only += 1
        elif has_note:
            note_only += 1
        else:
            missing_both += 1

    if learner_controls <= 0 and ready_pairs:
        next_step = f"Use {control_phrase}, then mark another observation with prediction and note."
    elif learner_controls <= 0 and prediction_only:
        next_step = (
            f"Add an observation note or live status snapshot, use {control_phrase}, "
            "then mark another observation."
        )
    elif learner_controls <= 0 and note_only:
        next_step = f"Write a prediction, use {control_phrase}, then mark the observation again."
    elif learner_controls <= 0:
        next_step = f"Use {control_phrase}, fill Prediction and Note, then mark the observation."
    elif ready_pairs:
        next_step = "Decide whether each prediction matched, partially matched, or surprised you."
    elif prediction_only:
        next_step = "Add an observation note or live status snapshot before using this as evidence."
    elif note_only:
        next_step = "Repeat the run and write a prediction before observing, then mark the observation again."
    else:
        next_step = "Repeat the run, fill Prediction and Note, then mark the observation."

    return [
        ("Review-ready pairs", ready_pairs),
        ("Prediction-only markers", prediction_only),
        ("Observation-only markers", note_only),
        ("Empty markers", missing_both),
        ("Outcome judgments", outcome_judgments),
        ("Learner controls", learner_controls),
        ("Next review step", next_step),
    ]


def _evidence_review_cue(
    events: list[dict[str, Any]],
    markers: list[dict[str, Any]],
    *,
    learner_control_phrase: str = "",
) -> str:
    return _action_card(
        "Evidence Review Cue",
        "Use this read-only review guide before moving to the next experiment; record follow-up answers "
        "in personal or course notes outside the saved-run folder.",
        _action_value_list(_evidence_review_cue_items(events, markers, learner_control_phrase=learner_control_phrase)),
    )


def _observation_marker_card(event: dict[str, Any], marker_index: int) -> str:
    payload = event.get("value")
    value = payload if isinstance(payload, dict) else {}
    question = _marker_text_group("Question", value.get("question"))
    prediction = _marker_text_group("Prediction", value.get("prediction"))
    outcome = _marker_text_group("Prediction outcome", value.get("outcome"))
    evidence_prompt = _marker_text_group("Evidence prompt", value.get("evidence_prompt"))
    challenge_proof = _marker_text_group("Challenge proof", value.get("challenge_proof"))
    note = _marker_note_group(value.get("note"))
    changed_sliders = _marker_value_group("Changed sliders", value.get("changed_sliders"))
    sliders = _marker_value_group("Sliders", value.get("sliders"))
    status = _marker_value_group("Live status", value.get("status"))
    body = question + prediction + outcome + evidence_prompt + challenge_proof + note + changed_sliders + sliders + status
    if not body:
        body = '<p class="empty">No slider or status snapshot was saved for this marker.</p>'
    return (
        '<article class="marker-card">'
        f"<strong>Observation {marker_index}</strong>"
        f'<span class="marker-time">time {_format_value(event.get("time"))} s</span>'
        f"{body}"
        "</article>"
    )


def _marker_value_group(title: str, values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return ""
    rows = "\n".join(
        (
            "<li>"
            f"<span>{escape(str(key))}</span>"
            f"<strong>{escape(_format_value(value))}</strong>"
            "</li>"
        )
        for key, value in values.items()
    )
    return (
        '<div class="marker-group">'
        f"<strong>{escape(title)}</strong>"
        f"<ul>{rows}</ul>"
        "</div>"
    )


def _marker_text_group(title: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        '<div class="marker-group">'
        f"<strong>{escape(title)}</strong>"
        f"<p>{escape(text)}</p>"
        "</div>"
    )


def _marker_note_group(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    items = _note_evidence_items(text)
    if len(items) <= 1:
        return _marker_text_group("Learner note", text)
    rows = "\n".join(f"<li>{escape(item)}</li>" for item in items)
    return (
        '<div class="marker-group">'
        "<strong>Learner note</strong>"
        f"<p>{escape(text)}</p>"
        "<strong>Learner note evidence</strong>"
        f"<ul>{rows}</ul>"
        "</div>"
    )


def _note_evidence_items(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _plot_guide_section(plots: list[Path]) -> str:
    cards: list[str] = []
    for plot in plots:
        card = _plot_guide_card(plot)
        if card:
            cards.append(card)
    if not cards:
        return ""
    return (
        '<div class="plot-guide">'
        "<h3>Plot Guide</h3>"
        '<div class="plot-guide-grid">'
        f"{''.join(cards)}"
        "</div>"
        "</div>"
    )


def _plot_guide_card(plot: Path) -> str:
    guidance = plot_guidance(plot.name)
    if guidance is None:
        return ""
    title, detail = guidance
    return (
        '<article class="plot-guide-card">'
        f"<strong>{escape(title)}</strong>"
        f"<span>{escape(plot.name)}</span>"
        f'<p class="empty">{escape(detail)}</p>'
        "</article>"
    )


def plot_guidance(filename: str) -> tuple[str, str] | None:
    return _plot_guidance(filename)


def _plot_guidance(filename: str) -> tuple[str, str] | None:
    name = filename.lower()
    if "wall_key_moment_timing" in name:
        return (
            "Wall Timing",
            "Compare when contact, peak penetration, peak force, peak damping, and peak hand speed occur across wall scenarios.",
        )
    if "target_wall_gap" in name:
        return (
            "Target-Wall Gap",
            "Compare how far the commanded target moves past the wall. Use this before penetration and force plots to separate command depth from actual contact.",
        )
    if "virtual_wall" in name:
        return (
            "Virtual Wall",
            "Watch penetration, wall force, and retreat. A useful wall demo shows contact response without runaway motion.",
        )
    if "wall_parameters" in name:
        return (
            "Wall Parameters",
            "Connect slider changes to wall position, stiffness, damping, and retreat settings used during the run.",
        )
    if "wall_penetration" in name:
        return (
            "Wall Penetration",
            "Compare how far the hand moves through the virtual wall. Larger penetration usually means a softer wall, later retreat, or faster approach.",
        )
    if "wall_retreat" in name:
        return (
            "Wall Retreat",
            "Compare how strongly the controller backs the target away from the wall after contact.",
        )
    if "hand_x_speed" in name:
        return (
            "Hand X Speed",
            "Compare approach velocity along the wall normal. Faster approach should make damping force easier to see.",
        )
    if "hand_x" in name:
        return (
            "Hand X Position",
            "Compare horizontal hand motion across scenarios. For wall demos, this also shows approach and retreat along the wall normal.",
        )
    if "hand_y" in name:
        return (
            "Hand Y Position",
            "Compare vertical hand motion across scenarios. Mirrored 2DOF paths should separate most clearly in this plot.",
        )
    if "end_effector" in name:
        return (
            "End Effector",
            "Compare hand position against the target path. This is the clearest plot for task-space control behavior.",
        )
    if "cartesian_error" in name:
        return (
            "Cartesian Error",
            "Check whether hand error falls and stays small. Persistent error usually means target, gain, or actuator limits need attention.",
        )
    if "pid_terms" in name:
        return (
            "PID Terms",
            "Compare P, I, and D contributions. Large integral buildup or noisy derivative terms explain many controller surprises.",
        )
    if "dls_task_speed_limit" in name:
        return (
            "DLS Speed Limit",
            "Check whether the adaptive schedule actually lowers the task-speed cap before comparing task error and joint speed.",
        )
    if "dls" in name:
        return (
            "Damped Least Squares",
            "Compare task speed, joint speed, and damping. More damping usually calms joint motion near singularity but leaves more task error.",
        )
    if "disturbance_recovery" in name:
        return (
            "Disturbance Recovery",
            "Compare how long each disturbance case takes to return joint error to its pre-disturbance recovery band.",
        )
    if "disturbance" in name:
        return (
            "Disturbance Torque",
            "Check when the external torque pulse is applied and how quickly the controller recovers task error afterward.",
        )
    if "current_proxy" in name:
        return (
            "Current Proxy",
            "Use this as an actuator effort proxy. Peaks show where the command would demand more motor current.",
        )
    if "singularity" in name:
        return (
            "Singularity",
            "Low manipulability or high condition number means the same hand motion can require much larger joint motion or torque.",
        )
    if "torque" in name:
        return (
            "Torque",
            "Look for peaks, clipping, and sign changes. High torque often comes from aggressive targets or gains.",
        )
    if "control_force" in name or "force" in name:
        return (
            "Force / Control Effort",
            "Compare effort against motion. Saturation, chatter, or delayed sign changes are good clues for tuning.",
        )
    if "energy" in name:
        return (
            "Energy",
            "Energy should decay with damping in passive demos. Slow decay means the system will keep oscillating longer.",
        )
    if "jerk" in name:
        return (
            "Jerk",
            "Jerk shows abrupt changes in acceleration. Smoother profiles are easier for actuators to track.",
        )
    if "acceleration" in name:
        return (
            "Acceleration",
            "Spikes indicate abrupt commands or aggressive gains. Smooth acceleration usually produces calmer effort plots.",
        )
    if "velocity" in name:
        return (
            "Velocity",
            "Use velocity to see oscillation and settling. A well damped run loses speed cleanly near the target.",
        )
    if "error" in name:
        return (
            "Error",
            "Check how quickly error shrinks and whether it settles near zero without repeated sign changes.",
        )
    if "position" in name:
        return (
            "Position",
            "Compare actual motion against target or reference. Look for overshoot, lag, oscillation, and steady-state error.",
        )
    return None


def _discover_runs(
    root: Path,
    *,
    evidence_overrides: dict[str, CompletionEvidence] | None = None,
) -> list[dict[str, Any]]:
    records = ArtifactRepository(root).list_runs()
    if evidence_overrides:
        records = tuple(
            replace(
                record,
                status=(
                    evidence_overrides[record.path.name].status
                    or record.status
                ),
                completion_evidence=evidence_overrides[record.path.name],
            )
            if record.path.name in evidence_overrides
            else record
            for record in records
        )
    catalog = ScenarioCatalog.default()
    assessment_index = build_completion_assessment_index(catalog.targets(), records)
    runs: list[dict[str, Any]] = []
    for record in records:
        child = record.path
        saved_summary = record.summary
        target = _catalog_target_or_none(catalog, record.scenario_id)
        direct_target = target is not None
        if (
            target is None
            and record.completion_evidence.record_kind
            == CompletionRecordKind.LEGACY_SUMMARY
        ):
            target = target_from_legacy_summary(catalog, saved_summary)
        summary = _trusted_behavior_summary(saved_summary, target)
        decision = evaluate_completion(
            target.completion if target is not None else None,
            record.completion_evidence,
        )
        assessment = (
            assessment_index.get(record.scenario_id) if direct_target else None
        )
        guide = guide_for_run_summary(summary)
        interaction_events = _display_interaction_events(record.interaction_events)
        config = _index_run_config(record, target)
        observation_markers, learner_predictions, learner_notes, learner_outcomes = (
            _observation_evidence_counts_from_events(interaction_events)
        )
        outcome_counts = _observation_outcome_counts_from_events(interaction_events)
        latest_evidence = _latest_observation_evidence_from_events(interaction_events)
        observation_flow = _observation_flow_text_from_events(interaction_events)
        observation_next_step = _index_observation_next_step(summary, interaction_events, config)
        plots = _discover_trusted_run_plots(record, summary)
        worksheet = _trusted_worksheet_link(record)
        runs.append(
            {
                "name": child.name,
                "scenario_id": record.scenario_id,
                "lab_name": saved_summary.get("lab_name", ""),
                "config_name": saved_summary.get("config_name", ""),
                "config_path": saved_summary.get("config_path", ""),
                "samples": summary.get("samples", ""),
                "duration": summary.get("duration", ""),
                "report": (
                    f"{child.name}/report.html" if record.report_available else child.name
                ),
                "folder": _discover_output_folder(child),
                "worksheet": worksheet,
                "plots": plots,
                "replay": _trusted_replay_config(record),
                "modified": record.sort_timestamp,
                "summary": summary,
                "lesson_title": guide.title if guide is not None else "",
                "next_step": guide.next_step if guide is not None else "",
                "observation_markers": observation_markers,
                "learner_predictions": learner_predictions,
                "learner_notes": learner_notes,
                "learner_outcomes": learner_outcomes,
                "outcome_counts": outcome_counts,
                "latest_evidence": latest_evidence,
                "observation_flow": observation_flow,
                "observation_next_step": observation_next_step,
                "activity_mix": _activity_mix_index_text(interaction_events, config),
                "mission_evidence": _mission_evidence_index_text(
                    summary,
                    interaction_events,
                    plots,
                    config,
                    worksheet=worksheet,
                    completion_decision=decision,
                ),
                "challenge_evidence": _challenge_evidence_index_text(
                    summary,
                    interaction_events,
                    plots,
                    config,
                    worksheet=worksheet,
                    completion_decision=decision,
                ),
                "config": config,
                "interaction_events": interaction_events,
                "record": record,
                "completion_decision": decision,
                "completion_complete": decision.complete,
                "completion_assessment": assessment,
                "completion_target": target,
            }
        )
    return runs


def _index_run_config(
    record: ArtifactRecord,
    target: Any | None,
) -> dict[str, Any]:
    config_path = str(getattr(target, "config_path", "") or "").strip()
    source_config: dict[str, Any] = {}
    if config_path:
        try:
            source_config = load_config(config_path)
        except (OSError, ValueError):
            source_config = {}
    config_section = record.manifest.get("config")
    resolved = config_section.get("resolved") if isinstance(config_section, dict) else None
    config = deepcopy(resolved) if isinstance(resolved, dict) else {}
    if config:
        return _merge_source_learning_metadata(config, source_config)
    if source_config:
        return source_config
    return {}


def _trusted_behavior_summary(
    summary: dict[str, Any],
    target: Any | None,
) -> dict[str, Any]:
    """Keep metrics while sourcing executable metadata only from the catalog."""

    safe = deepcopy(summary)
    config_path = str(getattr(target, "config_path", "") or "").strip()
    batch_name = str(getattr(target, "batch_name", "") or "").strip()
    lab_name = str(getattr(target, "lab_name", "") or "").strip()
    safe["config_path"] = config_path
    if config_path:
        safe["config_name"] = Path(config_path).stem
    elif batch_name:
        safe["config_name"] = batch_name
    else:
        safe["config_name"] = ""
    safe["lab_name"] = lab_name or ("batch" if batch_name else "")
    safe["batch_name"] = batch_name
    return safe


def _merge_source_learning_metadata(config: dict[str, Any], source_config: dict[str, Any]) -> dict[str, Any]:
    """Preserve saved run values while using current source metadata for learner cues."""
    if not source_config:
        return config
    source_interaction = source_config.get("interaction")
    if not isinstance(source_interaction, dict):
        return config
    source_presets = source_interaction.get("tuning_presets")
    if not isinstance(source_presets, list) or not source_presets:
        return config
    merged = deepcopy(config)
    interaction = merged.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    else:
        interaction = dict(interaction)
    interaction["tuning_presets"] = deepcopy(source_presets)
    merged["interaction"] = interaction
    return merged


def _index_observation_next_step(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    evidence_required = _summary_requires_hands_on_evidence(summary)
    if evidence_required:
        required_labels, required_tried, next_required = _required_preset_progress(config, events)
        if required_labels and len(required_tried) < len(required_labels):
            if next_required:
                return (
                    f"Observation next step: try required preset {next_required}, "
                    "then mark one observation with a prediction and note."
                )
            return (
                "Observation next step: try the remaining required preset, "
                "then mark one observation with a prediction and note."
            )
    return _observation_next_step_text_from_events(
        events,
        evidence_required=evidence_required,
        learner_control_phrase=_report_learner_control_phrase(config, summary) if evidence_required else "",
    )


def _render_outputs_index(root: Path, runs: list[dict[str, Any]]) -> str:
    metric_keys = _index_metric_keys(runs)
    metric_headers = "".join(f"<th>{escape(_metric_label(key))}</th>" for key in metric_keys)
    learning_path = _learning_path_section(runs)
    experience_coverage = _experience_coverage_section(runs)
    progress_cards = _progress_cards(runs)
    rows = "\n".join(
        (
            "<tr>"
            f'<td><a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></td>'
            f"<td>{escape(str(run['lab_name']))}</td>"
            f"<td>{_run_folder_cell(run)}</td>"
            f"<td>{escape(_config_cell(run))}</td>"
            f"<td>{escape(str(run.get('lesson_title', '')))}</td>"
            f"<td>{escape(str(run.get('next_step', '')))}</td>"
            f'<td class="cue-cell">{_run_next_cue_cell(run)}</td>'
            f"<td>{_run_repeat_command_cell(run)}</td>"
            f"<td>{escape(_run_evidence_cell(run))}</td>"
            f"<td>{escape(str(run.get('activity_mix', '')))}</td>"
            f"<td>{escape(str(run.get('mission_evidence', '')))}</td>"
            f"<td>{escape(str(run.get('challenge_evidence', '')))}</td>"
            f"<td>{_run_worksheet_cell(run)}</td>"
            f"<td>{_run_replay_cell(run)}</td>"
            f"<td>{_run_plots_cell(run)}</td>"
            f"<td>{escape(_run_plot_review_cell(run))}</td>"
            f"<td>{escape(_format_value(run['duration']))}</td>"
            f"<td>{escape(str(run['samples']))}</td>"
            + "".join(
                f"<td>{escape(_format_value(run.get('summary', {}).get(key, '')))}</td>"
                for key in metric_keys
            )
            + "</tr>"
        )
        for run in runs
    )
    if not rows:
        rows = f'<tr><td colspan="{18 + len(metric_keys)}">No run reports were found yet.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MCLab results</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Noto Sans KR", "Segoe UI", Arial, sans-serif;
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
    section {{
      background: #ffffff;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      margin-top: 16px;
      padding: 16px;
    }}
    h1, p {{
      margin-top: 0;
      letter-spacing: 0;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    a:focus-visible, summary:focus-visible, .table-wrap:focus-visible {{
      outline: 3px solid #ffdd00;
      outline-offset: 3px;
      box-shadow: 0 0 0 2px #000000;
    }}
    details.advanced {{
      margin-top: 16px;
      border: 1px solid #d9dde3;
      border-radius: 8px;
      background: #ffffff;
    }}
    details.advanced > summary {{
      cursor: pointer;
      padding: 16px;
      font-size: 18px;
      font-weight: 700;
    }}
    details.advanced > .advanced-body {{
      padding: 0 16px 16px;
    }}
    .progress-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .progress-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .progress-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .path-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .path-card {{
      border: 1px solid #e0e4ea;
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .path-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .path-command {{
      margin: 10px 0 0;
      padding: 10px;
      border: 1px solid #e0e4ea;
      border-radius: 6px;
      background: #fbfcfd;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
    }}
    .status {{
      display: inline-block;
      margin-top: 8px;
      color: #3f4752;
      font-size: 13px;
      font-weight: 600;
    }}
    .muted {{
      color: #596270;
      font-size: 13px;
    }}
    .cue-cell {{
      min-width: 260px;
      max-width: 360px;
      white-space: normal;
    }}
    .command-cell {{
      min-width: 300px;
      max-width: 420px;
      white-space: normal;
    }}
    .command-cell code {{
      display: block;
      padding: 8px;
      border: 1px solid #e0e4ea;
      border-radius: 6px;
      background: #fbfcfd;
      color: #202124;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
    }}
    .plot-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-width: 180px;
      white-space: normal;
    }}
    .plot-chip {{
      display: inline-block;
      border: 1px solid #c8d7f4;
      border-radius: 999px;
      padding: 3px 8px;
      background: #f3f7ff;
      color: #0b57d0;
      font-size: 12px;
      text-decoration: none;
    }}
    .path-links {{
      margin-top: 8px;
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
    <h1>MCLab results</h1>
    <section>
      <h2>Saved evidence overview</h2>
      <p>Open a run report to inspect the learning guide, summary values, notes, plots, and saved artifacts.</p>
      {progress_cards}
    </section>
    {learning_path}
    {experience_coverage}
    {_starter_commands_section()}
    <section>
      <div class="table-wrap" tabindex="0" aria-label="Scrollable data table">
        <table>
          <thead><tr><th>Run</th><th>Lab</th><th>Folder</th><th>Config</th><th>Lesson</th><th>Next</th><th>Next cue</th><th>Repeat command</th><th>Evidence</th><th>Activity</th><th>Mission evidence</th><th>Challenge evidence</th><th>Worksheet</th><th>Replay</th><th>Plots</th><th>Plot review</th><th>Duration [s]</th><th>Samples</th>{metric_headers}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _starter_commands_section() -> str:
    items = (
        (
            "Check setup",
            "Verify Python packages, MuJoCo assets, scenario readiness, and output-folder access before class.",
            "python -m mclab doctor",
        ),
        (
            "Open the MCLab app",
            "Best first step: continue the recommended path or browse saved reports with buttons.",
            "python -m mclab app",
        ),
        (
            "See next experience",
            "Print the coverage map plus the next missing experience and its compact guide in the terminal.",
            "python -m mclab coverage",
        ),
        (
            "Compare all experiences",
            "Print every core experience type with its mode, focus, evidence cue, and ready command.",
            "python -m mclab coverage --details",
        ),
        (
            "Inspect parameters",
            "Show what a learner can change, current YAML values, controls, prediction prompt, and command.",
            "python -m mclab params wall --filter hands-on",
        ),
        (
            "Find hands-on scenarios",
            "Search guided scenario cards by topic, mission, controls, viewer markers, and ready commands.",
            "python -m mclab scenarios wall --filter hands-on --details",
        ),
        (
            "Find comparison batches",
            "Search batch cards with missions, prediction checks, worksheets, plots, and viewer handoff cues.",
            "python -m mclab batches wall --details",
        ),
        (
            "Preview next path step",
            "Read the next recommended step, mission, start steps, controls guide, and command without running it.",
            "python -m mclab next --preview",
        ),
        (
            "Review saved evidence",
            "Find the next saved run that still needs observation, preset, outcome, note, plot, or worksheet evidence.",
            "python -m mclab review",
        ),
        (
            "Open all reports",
            "Regenerate this browser index so reports, worksheets, plots, replay configs, and repair commands are one click away.",
            "python -m mclab index --open",
        ),
        (
            "Generate first artifacts",
            "Run the baseline 1D physics demo headless and save the first report, worksheet, and plots.",
            "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential --open-report",
        ),
        (
            "Try first hands-on demo",
            "Open the side-panel-free viewer plus MCLab Interaction controls for live push, preset, and slider practice.",
            (
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --plots essential --open-report"
            ),
        ),
        (
            "Run first comparison",
            "Generate the first multi-scenario report and worksheet so learners can compare damping and stiffness.",
            "python -m mclab batch lab01_msd_compare --open-report",
        ),
    )
    cards = "\n".join(
        (
            '<article class="path-card">'
            f"<strong>{escape(title)}</strong>"
            f'<p class="muted">{escape(description)}</p>'
            f'<pre class="path-command">{escape(command)}</pre>'
            "</article>"
        )
        for title, description, command in items
    )
    return (
        '<details class="advanced">'
        "<summary>Commands and terminal tools</summary>"
        '<div class="advanced-body">'
        '<p class="muted">Open these when you need setup, discovery, repair, or low-level rerun commands.</p>'
        '<div class="path-grid">'
        f"{cards}"
        "</div>"
        "</div>"
        "</details>"
    )


def _experience_coverage_section(runs: list[dict[str, Any]]) -> str:
    records = _experience_coverage_records_for_index(runs)
    summary = experience_coverage_summary_text(records)
    next_item = next_experience_coverage_item(records)
    repair_blocks = _experience_coverage_repair_blocks(runs)
    status_cards = _experience_coverage_status_cards(experience_coverage_statuses(records), repair_blocks)
    if next_item is None:
        next_block = (
            '<p class="muted">'
            "All core experience types are represented. Continue the Learning Path below if it still shows "
            "pending evidence, or replay a tuned run or comparison batch to go deeper."
            "</p>"
        )
    else:
        command_block = (
            f'<pre class="path-command">{escape(next_item.command)}</pre>' if next_item.command else ""
        )
        next_block = (
            '<article class="path-card">'
            f"<strong>Run next: {escape(next_item.label)}</strong>"
            f'<p class="muted"><strong>Mode:</strong> {escape(experience_coverage_item_mode(next_item))}</p>'
            f'<p class="muted"><strong>Next action:</strong> {escape(next_item.next_step)}</p>'
            f'<p class="muted"><strong>Evidence:</strong> {escape(experience_coverage_item_evidence(next_item))}</p>'
            f"{_experience_coverage_control_cues(next_item)}"
            f"{command_block}"
            "</article>"
        )
    return (
        "<section>"
        "<h2>Experience Coverage</h2>"
        f'<p class="muted">{escape(summary)}</p>'
        f"{next_block}"
        f"{status_cards}"
        "</section>"
    )


def _experience_coverage_status_cards(
    statuses: tuple[ExperienceCoverageStatus, ...],
    repair_blocks: dict[str, str],
) -> str:
    cards = "\n".join(_experience_coverage_status_card(status, repair_blocks) for status in statuses)
    return f'<div class="path-grid">{cards}</div>'


def _experience_coverage_status_card(status: ExperienceCoverageStatus, repair_blocks: dict[str, str]) -> str:
    if status.next_missing:
        status_label = "Next"
    elif status.covered:
        status_label = "Done"
    else:
        status_label = "Missing"
    repair_block = repair_blocks.get(status.item.key, "")
    command = status.item.command
    if repair_block and command and escape(command) in repair_block:
        command = ""
    command_block = f'<pre class="path-command">{escape(command)}</pre>' if command else ""
    return (
        '<article class="path-card">'
        f"<strong>{escape(status.item.label)}</strong>"
        f'<span class="status">{escape(status_label)}</span>'
        f'<p class="muted"><strong>Mode:</strong> {escape(experience_coverage_item_mode(status.item))}</p>'
        f'<p class="muted"><strong>Focus:</strong> {escape(status.item.next_step)}</p>'
        f'<p class="muted"><strong>Evidence:</strong> {escape(experience_coverage_item_evidence(status.item))}</p>'
        f"{_experience_coverage_control_cues(status.item)}"
        f"{repair_block}"
        f"{command_block}"
        "</article>"
    )


def _experience_coverage_repair_blocks(runs: list[dict[str, Any]], *, report_prefix: str = "") -> dict[str, str]:
    repairs: dict[str, str] = {}
    for key, (status, name, report, command) in _experience_coverage_repair_items(runs).items():
        command_block = f'<pre class="path-command">{escape(command)}</pre>' if command else ""
        href = f"{report_prefix}{report}" if report else ""
        link = f'<a href="{escape(href)}">{escape(name)}</a>' if href else escape(name)
        repairs[key] = (
            '<p class="muted"><strong>Review repair:</strong> '
            f"{escape(status)} in {link}</p>"
            f"{command_block}"
        )
    return repairs


def _experience_coverage_repair_items(runs: list[dict[str, Any]]) -> dict[str, tuple[str, str, str, str]]:
    repairs: dict[str, tuple[str, str, str, str]] = {}
    for run in _mission_review_prioritized_runs(runs):
        key = _experience_coverage_repair_key_for_run(run)
        if not key or key in repairs:
            continue
        status = _mission_review_status(run)
        command = _run_repeat_command(run)
        report = str(run.get("report") or "")
        name = str(run.get("name") or "")
        repairs[key] = (status, name, report, command)
    return repairs


def _mission_review_prioritized_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for bucket in ("outcome", "preset", "observation", "prediction", "note", "control"):
        for run in runs:
            if _mission_review_bucket(_mission_review_status(run)) == bucket:
                matches.append(run)
    return matches


def _experience_coverage_repair_key_for_run(run: dict[str, Any]) -> str:
    tags = _experience_tags_for_index_run(run)
    for key in ("wall", "singularity", "2dof", "panda", "compare", "intro"):
        item = _experience_coverage_item_for_key(key)
        if item is not None and any(tag in tags for tag in item.tags):
            return key
    if "hands-on" in tags:
        return "hands-on"
    return ""


def _experience_coverage_item_for_key(key: str) -> ExperienceCoverageItem | None:
    for item in EXPERIENCE_COVERAGE_ITEMS:
        if item.key == key:
            return item
    return None


def _experience_coverage_control_cues(item: ExperienceCoverageItem) -> str:
    if " batch " in f" {item.command} ":
        return (
            '<p class="muted"><strong>Controls:</strong> '
            "comparison batch; inspect plots and worksheet, then use Viewer Handoff for hands-on rerun."
            "</p>"
        )
    config = _experience_coverage_item_config(item)
    controls = _coverage_control_surface_sentence(config)
    if not controls:
        return ""
    credit = _control_credit_text_for_config(config)
    credit_block = (
        f'<p class="muted"><strong>Counts as control:</strong> {escape(credit)}</p>' if credit else ""
    )
    return f'<p class="muted"><strong>Controls:</strong> {escape(controls)}</p>{credit_block}'


def _coverage_control_surface_sentence(config: dict[str, Any]) -> str:
    controls = _control_surface_items(config)
    values = [str(value) for label, value in controls if label != "Counts as control"]
    return "; ".join(dict.fromkeys(values))


def _experience_coverage_item_config(item: ExperienceCoverageItem) -> dict[str, Any]:
    try:
        tokens = shlex.split(item.command)
    except ValueError:
        return {}
    for index, token in enumerate(tokens):
        if token == "--config" and index + 1 < len(tokens):
            return _safe_load_config(tokens[index + 1])
    return {}


def _experience_coverage_records_for_index(runs: list[dict[str, Any]]) -> list[ExperienceCoverageRecord]:
    records: list[ExperienceCoverageRecord] = []
    for run in runs:
        if not bool(run.get("completion_complete", False)):
            continue
        tags = _experience_tags_for_index_run(run)
        record = run.get("record")
        has_control = bool(
            isinstance(record, ArtifactRecord)
            and record.completion_evidence.interaction.learner_control_count > 0
        )
        records.append(
            ExperienceCoverageRecord(
                frozenset(tags),
                has_control=has_control,
            )
        )
    return records


def _experience_tags_for_index_run(run: dict[str, Any]) -> set[str]:
    target = run.get("completion_target")
    config_path = _normalize_path(str(getattr(target, "config_path", "")))
    config_name = Path(config_path).stem.lower()
    lab_name = str(getattr(target, "lab_name", "")).lower()
    batch_name = str(getattr(target, "batch_name", "") or config_name).lower()
    text = " ".join((config_path, config_name, lab_name, batch_name))
    tags: set[str] = set()

    if "batch" in lab_name or batch_name in {"all", "all_batches"} or batch_name.endswith("_compare"):
        tags.update({"batch", "compare"})
    if batch_name == "all" or batch_name == "all_batches":
        tags.update({"intro", "2dof", "singularity", "dls", "panda", "wall"})
    if "lab01" in text or "lab02" in text:
        tags.add("intro")
    if "interactive" in text or "dls_singularity" in text or "condition_aware_dls_2dof" in text:
        tags.add("hands-on")
    if "lab03" in text or "2dof" in text:
        tags.add("2dof")
    if any(term in text for term in ("singularity", "condition", "dls")):
        tags.update({"singularity", "dls"})
    if "lab04" in text or "panda" in text:
        tags.add("panda")
    if "wall" in text:
        tags.add("wall")
    return tags


def _learning_path_section(runs: list[dict[str, Any]]) -> str:
    items = [_learning_path_item(step, runs) for step in INDEX_LEARNING_PATH]
    summary = _learning_path_summary(items)
    milestones = _learning_path_milestone_summary(items)
    cards = "\n".join(_learning_path_card(item) for item in items)
    return (
        "<section>"
        "<h2>Learning Path</h2>"
        f'<p class="muted">{escape(summary)}</p>'
        f'<p class="muted">{escape(milestones)}</p>'
        '<div class="path-grid">'
        f"{cards}"
        "</div>"
        "</section>"
    )


def _learning_path_item(step: IndexPathStep, runs: list[dict[str, Any]]) -> dict[str, Any]:
    run = _latest_learning_path_run(step, runs)
    evidence_required = _learning_path_requires_evidence(step)
    markers = int(run.get("observation_markers", 0)) if run is not None else 0
    predictions = int(run.get("learner_predictions", 0)) if run is not None else 0
    notes = int(run.get("learner_notes", 0)) if run is not None else 0
    outcomes = int(run.get("learner_outcomes", 0)) if run is not None else 0
    events = run.get("interaction_events") if run is not None else []
    if not isinstance(events, list):
        events = []
    learner_controls = _learner_control_event_count(events)
    required_total, required_tried, next_required = _learning_path_required_preset_progress(step, run)
    assessment = run.get("completion_assessment") if run is not None else None
    completed = bool(
        isinstance(assessment, TargetCompletionAssessment) and assessment.complete
    )
    credited_run = None
    if isinstance(assessment, TargetCompletionAssessment):
        credited_record = assessment.credited_record
        credited_run = next(
            (
                candidate
                for candidate in runs
                if candidate.get("record") is credited_record
            ),
            None,
        )
    return {
        "step": step,
        "run": run,
        "completed": completed,
        "credited_run": credited_run,
        "evidence_required": evidence_required,
        "observation_markers": markers,
        "learner_predictions": predictions,
        "learner_notes": notes,
        "learner_outcomes": outcomes,
        "learner_controls": learner_controls,
        "required_presets": required_total,
        "required_presets_tried": required_tried,
        "next_required_preset": next_required,
    }


def _learning_path_required_preset_progress(step: IndexPathStep, run: dict[str, Any] | None) -> tuple[int, int, str]:
    if run is None:
        return 0, 0, ""
    config = run.get("config")
    if not isinstance(config, dict):
        config = _index_step_config(step)
    events = run.get("interaction_events")
    if not isinstance(events, list):
        events = []
    required_labels, required_tried, next_required = _required_preset_progress(config, events)
    return len(required_labels), len(required_tried), next_required


def _learning_path_summary(items: list[dict[str, Any]]) -> str:
    total = len(items)
    completed = sum(1 for item in items if item["completed"])
    evidence_pending = sum(
        1
        for item in items
        if item["run"] is not None and item["evidence_required"] and not item["completed"]
    )
    outcome_pending = sum(
        1
        for item in items
        if item["run"] is not None
        and item["evidence_required"]
        and int(item["learner_predictions"]) > int(item["learner_outcomes"])
    )
    next_item = next((item for item in items if not item["completed"]), None)
    evidence_text = f" Evidence pending: {evidence_pending} hands-on step(s)." if evidence_pending else ""
    outcome_text = f" Outcome review pending: {outcome_pending} hands-on step(s)." if outcome_pending else ""
    if next_item is None:
        review_text = (
            " Next review: add missing Prediction outcome(s), then open All reports."
            if outcome_pending
            else " Course path complete."
        )
        return f"{completed}/{total} steps complete.{outcome_text}{review_text}"
    next_step: IndexPathStep = next_item["step"]
    return (
        f"{completed}/{total} steps complete.{evidence_text}{outcome_text} "
        f"Next: {next_step.title}. Next action: {_learning_path_action_label(next_step)}. "
        f"{_learning_path_completion_text(next_step)}"
    )


def _learning_path_milestone_summary(items: list[dict[str, Any]]) -> str:
    return course_milestone_summary(tuple(bool(item["completed"]) for item in items))


def _learning_path_card(item: dict[str, Any]) -> str:
    step: IndexPathStep = item["step"]
    run = item["run"]
    quick_links = _learning_path_quick_links(run)
    plot_review = _learning_path_plot_review(run)
    latest_evidence = _learning_path_latest_evidence(run)
    observation_flow = _learning_path_observation_flow(run)
    observation_next_step = _learning_path_observation_next_step(run)
    activity_mix = _learning_path_activity_mix(run)
    mission_evidence = _learning_path_mission_evidence(run)
    challenge_evidence = _learning_path_challenge_evidence(run)
    next_cue = _learning_path_next_cue(item)
    plan_cue = _learning_path_plan_cue(step)
    start_steps = _learning_path_start_steps(step)
    control_credit = _learning_path_control_credit(step)
    mission_challenge = _learning_path_mission_challenge(step)
    viewer_cue = _learning_path_viewer_cue(step)
    parameter_cues = _learning_path_parameter_cues(step)
    learning_cue = _learning_path_learning_cue(step)
    completion_text = _learning_path_completion_text(step)
    command_label = "Run this step" if run is None else "Repeat this step"
    command = _learning_path_command(step)
    command_block = (
        f'<p class="muted">{escape(command_label)}</p>'
        f'<pre class="path-command">{escape(command)}</pre>'
        if command
        else ""
    )
    if run is None:
        status = '<span class="status">Not run yet</span>'
    elif item["completed"]:
        outcome_review = (
            '<p class="muted">Add one Prediction outcome while reviewing.</p>'
            if item["evidence_required"] and int(item["learner_predictions"]) > int(item["learner_outcomes"])
            else ""
        )
        credited_run = item.get("credited_run")
        latest_decision = run.get("completion_decision")
        if (
            isinstance(credited_run, dict)
            and credited_run is not run
            and isinstance(latest_decision, CompletionDecision)
            and not latest_decision.complete
        ):
            latest_status = _completion_status_text(latest_decision, run.get("summary"))
            status = (
                f'<span class="status">Done{escape(_learning_path_evidence_suffix(item))}</span>'
                '<p class="muted"><strong>Historical credit:</strong> '
                f'<a href="{escape(str(credited_run["report"]))}">{escape(str(credited_run["name"]))}</a>; '
                '<strong>latest attempt:</strong> '
                f'<a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a> — '
                f'{escape(latest_status)} ({escape(latest_decision.primary_reason.value)}).</p>'
                f"{outcome_review}"
            )
        else:
            status = (
                f'<span class="status">Done{escape(_learning_path_evidence_suffix(item))}</span>'
                f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
                f"{outcome_review}"
            )
    elif int(item["observation_markers"]) > 0 and int(item["learner_predictions"]) == 0:
        status = (
            f'<span class="status">Needs prediction{escape(_learning_path_evidence_suffix(item))}</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
            '<p class="muted">Add one Prediction in Mark observation before moving on.</p>'
        )
    elif int(item.get("required_presets", 0)) > int(item.get("required_presets_tried", 0)):
        next_required = str(item.get("next_required_preset") or "").strip()
        next_text = (
            f"Try required preset {next_required} before moving on."
            if next_required
            else "Try the remaining required preset before moving on."
        )
        status = (
            f'<span class="status">Needs required preset{escape(_learning_path_evidence_suffix(item))}</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
            f'<p class="muted">{escape(next_text)}</p>'
        )
    elif int(item["observation_markers"]) > 0 and int(item["learner_notes"]) == 0:
        status = (
            f'<span class="status">Needs note{escape(_learning_path_evidence_suffix(item))}</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
            '<p class="muted">Add a short note or Use live status before moving on.</p>'
        )
    elif (
        item["evidence_required"]
        and int(item["observation_markers"]) > 0
        and int(item.get("learner_controls", 0)) <= 0
    ):
        control_action = ""
        step_config = _index_step_config(step)
        if step_config:
            control_phrase = _learner_control_phrase_for_config(step_config)
            if control_phrase:
                control_action = f"Use {control_phrase} before moving on."
            else:
                control_action = learner_control_action_text_for_config(step_config)
        status = (
            f'<span class="status">Needs learner control{escape(_learning_path_evidence_suffix(item))}</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
            f'<p class="muted">{escape(control_action or "Use one button, slider, or preset before moving on.")}</p>'
        )
    else:
        status = (
            '<span class="status">Needs observation</span>'
            f'<p class="muted">Latest: <a href="{escape(str(run["report"]))}">{escape(str(run["name"]))}</a></p>'
            '<p class="muted">Add one Mark observation entry before moving on.</p>'
        )
    return (
        '<article class="path-card">'
        f"<strong>{escape(step.title)}</strong>"
        f'<p class="muted">{escape(step.description)}</p>'
        f"{plan_cue}"
        f'<p class="muted"><strong>Done when:</strong> {escape(completion_text.removeprefix("Done when:").strip())}</p>'
        f"{start_steps}"
        f"{control_credit}"
        f"{mission_challenge}"
        f"{viewer_cue}"
        f"{parameter_cues}"
        f"{learning_cue}"
        f"{status}"
        f"{next_cue}"
        f"{latest_evidence}"
        f"{observation_flow}"
        f"{observation_next_step}"
        f"{activity_mix}"
        f"{mission_evidence}"
        f"{challenge_evidence}"
        f"{quick_links}"
        f"{plot_review}"
        f"{command_block}"
        "</article>"
    )


def _learning_path_next_cue(item: dict[str, Any]) -> str:
    step: IndexPathStep = item["step"]
    run = item["run"]
    cue = ""
    if run is None and bool(item.get("evidence_required")):
        control_step = _learning_path_first_run_control_step(step)
        cue = (
            f"Predict, run the viewer, {control_step}, "
            "then Mark observation with a prediction and note."
        )
    elif isinstance(run, dict):
        cue = _run_next_cue_text(run).removeprefix("Next cue:").strip()
    if not cue:
        return ""
    return f'<p class="muted"><strong>Next cue:</strong> {escape(cue)}</p>'


def _learning_path_first_run_control_step(step: IndexPathStep) -> str:
    config = _index_step_config(step)
    required_labels = _configured_required_preset_labels(config)
    if required_labels:
        return f"try required presets {' -> '.join(required_labels)}"
    preset_labels = _configured_preset_labels(config)
    if len(preset_labels) >= 2:
        return f"try presets {' -> '.join(preset_labels[:3])}"
    control_step = _hands_on_control_step_for_config(config)
    if control_step:
        return control_step
    return "use one button, slider, or preset"


def _learning_path_plan_cue(step: IndexPathStep) -> str:
    return f'<p class="muted"><strong>Plan:</strong> {escape(_learning_path_plan_text(step))}</p>'


def _learning_path_plan_text(step: IndexPathStep) -> str:
    if step.batch_name:
        if step.batch_name == "all":
            return "Compare; course batch; all comparison batches; saves combined reports/worksheets"
        return f"Compare; batch; {step.batch_name}; saves combined report/worksheet"

    config = _index_step_config(step)
    duration = _learning_path_duration_text(config)
    experience = "hands-on viewer" if _learning_path_requires_evidence(step) else "headless plot run"
    return f"{_learning_path_level(step)}; {experience}; {duration}; saves report/plots/worksheet"


def _learning_path_level(step: IndexPathStep) -> str:
    context = " ".join((step.title, step.description, step.config_path)).lower()
    if step.batch_name:
        return "Compare"
    if "lab01" in context or "lab02" in context:
        return "Intro"
    if any(term in context for term in ("dls", "singularity", "wall", "condition")):
        return "Deep dive"
    if "lab03" in context or "lab04" in context or "panda" in context:
        return "Build"
    return "Build"


def _learning_path_duration_text(config: dict[str, Any]) -> str:
    sim_time = config.get("sim_time") if isinstance(config, dict) else None
    if isinstance(sim_time, int | float):
        return f"{float(sim_time):g}s simulated"
    return "configured sim time"


def _learning_path_latest_evidence(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    latest = str(run.get("latest_evidence") or "").strip()
    if not latest:
        return ""
    return f'<p class="muted">Latest evidence: {escape(latest)}</p>'


def _learning_path_observation_flow(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    flow = str(run.get("observation_flow") or "").strip()
    if not flow:
        return ""
    return f'<p class="muted">{escape(flow)}</p>'


def _learning_path_observation_next_step(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    next_step = str(run.get("observation_next_step") or "").strip()
    if not next_step:
        return ""
    return f'<p class="muted">{escape(next_step)}</p>'


def _learning_path_activity_mix(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    activity = str(run.get("activity_mix") or "").strip()
    if not activity or activity == "No learner controls":
        return ""
    return f'<p class="muted">Activity mix: {escape(activity)}</p>'


def _learning_path_mission_evidence(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    mission = str(run.get("mission_evidence") or "").strip()
    if not mission:
        return ""
    return f'<p class="muted">Mission evidence: {escape(mission)}</p>'


def _learning_path_challenge_evidence(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    challenge = str(run.get("challenge_evidence") or "").strip()
    if not challenge:
        return ""
    return f'<p class="muted">Challenge evidence: {escape(challenge)}</p>'


def _learning_path_quick_links(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    links = [(str(run.get("report") or ""), "Report")]
    worksheet = run.get("worksheet")
    if isinstance(worksheet, dict):
        links.append((str(worksheet.get("href") or ""), str(worksheet.get("label") or "Worksheet")))
    plots = run.get("plots")
    if isinstance(plots, list):
        for plot in plots:
            if not isinstance(plot, dict):
                continue
            href = str(plot.get("href") or "")
            label = str(plot.get("label") or "")
            if href and label:
                links.append((href, f"Plot: {label}"))
                break
    folder = run.get("folder")
    if isinstance(folder, dict):
        links.append((str(folder.get("href") or ""), str(folder.get("label") or "Folder")))
    replay = run.get("replay")
    if isinstance(replay, dict):
        links.append((str(replay.get("href") or ""), "Replay tuned"))
    chips = [
        f'<a class="plot-chip" href="{escape(href)}">{escape(label)}</a>'
        for href, label in links
        if href and label
    ]
    if not chips:
        return ""
    return '<p class="muted">Latest artifacts</p><div class="plot-links path-links">' + "".join(chips) + "</div>"


def _learning_path_plot_review(run: dict[str, Any] | None) -> str:
    if run is None:
        return ""
    review = _run_plot_review_cell(run)
    if not review or review == "Plot review: Not available until a plot is saved.":
        return ""
    return f'<p class="muted">{escape(review)}</p>'


def _learning_path_evidence_suffix(item: dict[str, Any]) -> str:
    markers = int(item.get("observation_markers", 0))
    if markers <= 0:
        return ""
    predictions = int(item.get("learner_predictions", 0))
    notes = int(item.get("learner_notes", 0))
    outcomes = int(item.get("learner_outcomes", 0))
    prediction_text = f", {predictions} prediction{'s' if predictions != 1 else ''}" if predictions else ""
    outcome_text = f", {outcomes} outcome{'s' if outcomes != 1 else ''}" if outcomes else ""
    note_text = f", {notes} note{'s' if notes != 1 else ''}" if notes else ""
    control_text = ""
    if item.get("evidence_required"):
        controls = int(item.get("learner_controls", 0))
        control_text = f", {controls} control{'s' if controls != 1 else ''}"
    required_total = int(item.get("required_presets", 0))
    required_tried = int(item.get("required_presets_tried", 0))
    preset_text = f", required presets {required_tried}/{required_total}" if required_total else ""
    return (
        f" ({markers} observation{'s' if markers != 1 else ''}{prediction_text}{outcome_text}{note_text}"
        f"{control_text}{preset_text})"
    )


def _learning_path_action_label(step: IndexPathStep) -> str:
    if step.batch_name:
        return f"run batch {step.batch_name}"
    lab_name = _cli_lab_name(step.config_path)
    if lab_name:
        return f"run {lab_name}"
    return "open the saved command"


def _learning_path_start_steps(step: IndexPathStep) -> str:
    if step.batch_name:
        text = batch_start_steps_text(course_level=step.batch_name == "all").removeprefix("Start steps:").strip()
        return f'<p class="muted"><strong>Start steps:</strong> {escape(text)}</p>'
    if not step.config_path:
        return ""
    config = _index_step_config(step)
    guide = guide_for_config(config_path=step.config_path)
    text = _start_steps_text(guide, config)
    if not text:
        return ""
    return f'<p class="muted"><strong>Start steps:</strong> {escape(text)}</p>'


def _learning_path_control_credit(step: IndexPathStep) -> str:
    if step.batch_name or not step.config_path:
        return ""
    text = _control_credit_text_for_config(_index_step_config(step))
    if not text:
        return ""
    return f'<p class="muted"><strong>Counts as control:</strong> {escape(text)}</p>'


def _learning_path_mission_challenge(step: IndexPathStep) -> str:
    if step.batch_name or not step.config_path:
        return ""
    guide = guide_for_config(config_path=step.config_path)
    if guide is None:
        return ""

    rows = (
        ("Mission", mission_prompt_for_guide(guide).removeprefix("Mission:").strip()),
        ("Challenge", challenge_prompt_for_guide(guide).removeprefix("Challenge:").strip()),
    )
    return "".join(
        f'<p class="muted"><strong>{escape(label)}:</strong> {escape(text)}</p>'
        for label, text in rows
        if text
    )


def _learning_path_viewer_cue(step: IndexPathStep) -> str:
    if not _learning_path_requires_evidence(step):
        return ""
    guide = guide_for_config(config_path=step.config_path)
    legend = viewer_legend_for_guide(guide)
    if not legend:
        text = f"{VIEWER_CONTROL_SURFACE_TEXT}; standard MuJoCo scene; use plots and live status for exact values"
    else:
        legend_text = "; ".join(f"{label} = {description}" for label, description in legend)
        text = f"{VIEWER_CONTROL_SURFACE_TEXT}; {legend_text}"
    return f'<p class="muted"><strong>Viewer:</strong> {escape(_short_evidence_text(text, max_length=220))}</p>'


def _learning_path_parameter_cues(step: IndexPathStep) -> str:
    if step.batch_name or not step.config_path:
        return ""
    guide = guide_for_config(config_path=step.config_path)
    if guide is None:
        return ""

    lines: list[str] = []
    change = str(guide.change or "").strip()
    if change:
        lines.append(f'<p class="muted"><strong>Change:</strong> {escape(change)}</p>')
    value_preview = _config_value_preview_from_hint(_index_step_config(step), change, max_items=6)
    if value_preview:
        value_text = value_preview.removeprefix("Values:").strip()
        lines.append(f'<p class="muted"><strong>Values:</strong> {escape(value_text)}</p>')
    return "".join(lines)


def _config_value_preview_from_hint(config: dict[str, Any], hint: str, *, max_items: int) -> str:
    if not config:
        return "Values: Config unavailable"

    entries: list[str] = []
    for path in _hint_config_paths(hint):
        for resolved_path, value in _resolve_preview_values(config, path):
            entries.append(f"{resolved_path}={_format_config_preview_value(value)}")
            if len(entries) >= max_items:
                return f"Values: {'; '.join(entries)}"
    if not entries:
        return "Values: Open Config to inspect YAML"
    return f"Values: {'; '.join(entries)}"


def _hint_config_paths(hint: str) -> tuple[str, ...]:
    paths: list[str] = []
    for raw_part in str(hint).replace(";", ",").split(","):
        candidate = raw_part.strip()
        if ":" in candidate:
            candidate = candidate.split(":", 1)[1].strip()
        candidate = candidate.strip("` ")
        if _is_hint_config_path(candidate):
            paths.append(candidate)
            continue
        for token in CONFIG_PATH_TOKEN_RE.findall(candidate):
            if _is_hint_config_token(token):
                paths.append(token)
    return tuple(dict.fromkeys(paths))


def _is_hint_config_path(candidate: str) -> bool:
    if not candidate or " " in candidate or "/" in candidate:
        return False
    if candidate == "config" or candidate.startswith("live"):
        return False
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.*"
    return all(character in allowed for character in candidate)


def _is_hint_config_token(token: str) -> bool:
    if token in {"YAML", "Config"} or token.lower() in {"with", "same", "live", "presets", "buttons"}:
        return False
    if "." in token or "_" in token:
        return _is_hint_config_path(token)
    return False


def _resolve_preview_values(config: dict[str, Any], path: str) -> tuple[tuple[str, Any], ...]:
    if path.endswith(".*"):
        parent_path = path.removesuffix(".*")
        parent = _get_config_value(config, parent_path)
        if not isinstance(parent, dict):
            return ()
        return tuple(
            (f"{parent_path}.{key}", value)
            for key, value in parent.items()
            if _is_config_preview_value(value)
        )

    value = _get_config_value(config, path)
    if path.endswith("waypoints") and _is_preview_waypoint_list(value):
        return ((path, value),)
    if path.endswith("schedule") and _is_preview_schedule_list(value):
        return ((path, value),)
    if not _is_config_preview_value(value):
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


def _is_config_preview_value(value: Any) -> bool:
    if isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list | tuple):
        return all(isinstance(item, bool | int | float | str) for item in value)
    return False


def _is_preview_waypoint_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _is_preview_schedule_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) and ("value" in item or "speed" in item) for item in value)
    )


def _format_config_preview_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return f"{value:g}"
    if isinstance(value, str):
        return value if len(value) <= 32 else f"{value[:29]}..."
    if _is_preview_schedule_list(value):
        return _format_schedule_preview(value)
    if _is_preview_waypoint_list(value):
        return _format_waypoint_preview(value)
    if isinstance(value, list | tuple):
        shown = [_format_config_preview_value(item) for item in value[:4]]
        suffix = ", ..." if len(value) > 4 else ""
        return f"[{', '.join(shown)}{suffix}]"
    return str(value)


def _format_waypoint_preview(waypoints: list[dict[str, Any]]) -> str:
    first = _waypoint_position_preview(waypoints[0])
    last = _waypoint_position_preview(waypoints[-1])
    return f"{len(waypoints)} waypoints: {first} -> {last}"


def _format_schedule_preview(points: list[dict[str, Any]]) -> str:
    def point_value(point: dict[str, Any]) -> str:
        return _format_config_preview_value(point.get("value", point.get("speed", "?")))

    return f"{len(points)} points: {point_value(points[0])} -> {point_value(points[-1])}"


def _waypoint_position_preview(waypoint: dict[str, Any]) -> str:
    raw_position = waypoint.get("position", waypoint.get("xy"))
    if raw_position is None:
        raw_position = [waypoint.get("x", "?"), waypoint.get("y", "?")]
    if isinstance(raw_position, list | tuple):
        shown = [_format_config_preview_value(item) for item in raw_position[:3]]
        suffix = ", ..." if len(raw_position) > 3 else ""
        return f"[{', '.join(shown)}{suffix}]"
    return _format_config_preview_value(raw_position)


def _index_step_required_preset_labels(step: IndexPathStep) -> list[str]:
    return _configured_required_preset_labels(_index_step_config(step))


def _index_step_config(step: IndexPathStep) -> dict[str, Any]:
    if not step.config_path:
        return {}
    try:
        return load_config(step.config_path)
    except (OSError, ValueError):
        return {}


def _learning_path_completion_text(step: IndexPathStep) -> str:
    if step.batch_name:
        if step.batch_name == "all":
            return "Done when: the course comparison report, worksheet, and linked batch Prediction Checks are saved."
        return "Done when: the comparison report, plots, worksheet, and Prediction Check are saved."
    if _learning_path_requires_evidence(step):
        required_labels = _index_step_required_preset_labels(step)
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


def _learning_path_learning_cue(step: IndexPathStep) -> str:
    if step.batch_name:
        return (
            '<p class="muted"><strong>Compare:</strong> Generate the course batch report set. '
            "<strong>Prediction check:</strong> Review the digest-published, read-only worksheet, then copy "
            "Matched, Partly matched, or Surprised into personal or course notes outside the saved-run folder. "
            "<strong>Watch:</strong> How the same control ideas scale from 1D plants to Panda wall behavior.</p>"
        )
    if not step.config_path:
        return ""
    guide = guide_for_config(config_path=step.config_path)
    if guide is None:
        return f'<p class="muted"><strong>Watch:</strong> {escape(step.description)}</p>'
    prediction = _learning_path_prediction_cue_text(
        prediction_prompt_for_guide(guide).removeprefix("Prediction:").strip()
    )
    prediction_text = (
        f"<strong>Predict:</strong> {escape(_short_evidence_text(prediction, max_length=136))} "
        if prediction
        else ""
    )
    watch = str(guide.watch or step.description)
    return (
        '<p class="muted">'
        f"{prediction_text}<strong>Watch:</strong> {escape(_short_evidence_text(watch, max_length=112))}"
        "</p>"
    )


def _learning_path_prediction_cue_text(prediction: str) -> str:
    text = " ".join(str(prediction).split())
    marker = "predict how "
    marker_index = text.find(marker)
    if marker_index < 0:
        return text
    tail_index = marker_index + len(marker)
    tail = text[tail_index:]
    if tail.startswith("How "):
        return text[:tail_index] + tail.removeprefix("How ")
    if tail:
        return text[:tail_index] + _lowercase_sentence_start_unless_acronym(tail)
    return text


def _lowercase_sentence_start_unless_acronym(text: str) -> str:
    if len(text) >= 2 and text[0].isupper() and text[1].isupper():
        return text
    return text[:1].lower() + text[1:]


def _learning_path_requires_evidence(step: IndexPathStep) -> bool:
    if step.batch_name or not step.config_path:
        return False
    if "interactive" in Path(step.config_path).stem.lower():
        return True
    try:
        config = load_config(step.config_path)
    except Exception:
        return False
    interaction = config.get("interaction")
    if not isinstance(interaction, dict):
        return False
    return bool(interaction.get("panel") or interaction.get("live_tuning"))


def _learning_path_command(step: IndexPathStep) -> str:
    if step.batch_name:
        return f"python -m mclab batch {step.batch_name} --open-report"
    if not step.config_path:
        return ""
    lab_name = _cli_lab_name(step.config_path)
    if not lab_name:
        return ""
    if _learning_path_requires_evidence(step):
        return (
            f"python -m mclab run {lab_name} --config {step.config_path} "
            f"--viewer --realtime --pause-at-end --plot --plots {step.plots} --open-report"
        )
    return (
        f"python -m mclab run {lab_name} --config {step.config_path} "
        f"--headless --plot --plots {step.plots} --open-report"
    )


def _latest_learning_path_run(step: IndexPathStep, runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    target_id = _learning_path_target_id(step)
    for run in runs:
        if run.get("scenario_id") == target_id:
            return run
    return None


def _learning_path_target_id(step: IndexPathStep) -> str:
    if step.batch_name:
        return f"batch.{step.batch_name}"
    return stable_scenario_id(_cli_lab_name(step.config_path), step.config_path)


def _progress_cards(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return (
            '<article class="progress-card">'
            "<strong>No saved evidence yet</strong>"
            '<p class="muted">Open MCLab and use Start next experiment. Results appear here automatically.</p>'
            '<pre class="path-command">python -m mclab app</pre>'
            "</article>"
        )
    categories = (
        ("Lab01", "lab01"),
        ("Lab02", "lab02"),
        ("Lab03", "lab03"),
        ("Lab04", "lab04"),
        ("Batches", "batch"),
    )
    cards = [_evidence_quality_card(runs), _mission_review_queue_card(runs)]
    for label, key in categories:
        matches = [_run for _run in runs if _run_matches_category(_run, key)]
        latest = matches[0] if matches else None
        latest_link = (
            f'<a href="{escape(str(latest["report"]))}">{escape(str(latest["name"]))}</a>'
            if latest is not None
            else "Not run yet"
        )
        cards.append(
            "<div class=\"progress-card\">"
            f"<strong>{escape(label)}</strong>"
            f'<span class="muted">{len(matches)} saved run{"s" if len(matches) != 1 else ""}</span>'
            f'<p class="muted">Latest: {latest_link}</p>'
            "</div>"
        )
    return '<div class="progress-grid">' + "\n".join(cards) + "</div>"


def _evidence_quality_card(runs: list[dict[str, Any]]) -> str:
    markers = sum(int(run.get("observation_markers", 0)) for run in runs)
    predictions = sum(int(run.get("learner_predictions", 0)) for run in runs)
    outcomes = sum(int(run.get("learner_outcomes", 0)) for run in runs)
    notes = sum(int(run.get("learner_notes", 0)) for run in runs)
    outcome_counts = _merge_outcome_counts(runs)
    coverage = f"{(100.0 * outcomes / predictions):.0f}%" if predictions else "0%"
    mix = _format_outcome_mix(outcome_counts)
    return (
        '<div class="progress-card">'
        "<strong>Evidence Quality</strong>"
        f'<span class="muted">{markers} observation{"s" if markers != 1 else ""}</span>'
        f'<p class="muted">{predictions} prediction{"s" if predictions != 1 else ""}, '
        f'{outcomes} outcome{"s" if outcomes != 1 else ""}, '
        f'{notes} note{"s" if notes != 1 else ""}</p>'
        f'<p class="muted">Outcome coverage: {escape(coverage)} of predictions</p>'
        f'<p class="muted">Outcome mix: {escape(mix)}</p>'
        "</div>"
    )


def _mission_review_queue_card(runs: list[dict[str, Any]]) -> str:
    counts = _mission_review_queue_counts(runs)
    ready = counts.get("ready", 0)
    pending = len(runs) - ready
    artifact_pending = counts.get("artifact", 0)
    learner_action_pending = max(0, pending - artifact_pending)
    next_review = _mission_review_next_run(runs)
    next_review_text = "No pending mission evidence."
    repair_command_block = ""
    if next_review is not None:
        status = _mission_review_status(next_review)
        next_review_text = (
            f'<a href="{escape(str(next_review["report"]))}">{escape(str(next_review["name"]))}</a>'
            f" - {escape(status)}"
        )
        repair_command = _run_repeat_command(next_review)
        if repair_command:
            repair_command_block = (
                '<p class="muted"><strong>Repair command:</strong></p>'
                f'<pre class="path-command">{escape(repair_command)}</pre>'
            )

    return (
        '<div class="progress-card">'
        "<strong>Mission Review Queue</strong>"
        f'<span class="muted">{ready} ready, {pending} pending '
        f"({learner_action_pending} learner-action, {artifact_pending} artifact-only)</span>"
        '<p class="muted">'
        f"Needs observation: {counts.get('observation', 0)}; "
        f"prediction: {counts.get('prediction', 0)}; "
        f"outcome: {counts.get('outcome', 0)}; "
        f"required preset: {counts.get('preset', 0)}; "
        f"note: {counts.get('note', 0)}; "
        f"control: {counts.get('control', 0)}; "
        f"artifact: {counts.get('artifact', 0)}"
        "</p>"
        f'<p class="muted">Next review: {next_review_text}</p>'
        f"{repair_command_block}"
        f"{_mission_review_course_path_block(runs)}"
        "</div>"
    )


def _mission_review_course_path_block(runs: list[dict[str, Any]]) -> str:
    path_items = [_learning_path_item(step, runs) for step in INDEX_LEARNING_PATH]
    next_item = next((item for item in path_items if not item["completed"]), None)
    if next_item is None:
        return (
            '<p class="muted"><strong>Course path next:</strong> Course path complete</p>'
            '<p class="muted"><strong>Course path command:</strong> open outputs/index.html or rerun a comparison batch '
            "for deeper review.</p>"
        )
    step: IndexPathStep = next_item["step"]
    command = _learning_path_command(step)
    command_block = f'<pre class="path-command">{escape(command)}</pre>' if command else ""
    return (
        f'<p class="muted"><strong>Course path next:</strong> {escape(step.title)}</p>'
        f'<p class="muted"><strong>Course path command:</strong></p>'
        f"{command_block}"
    )


def _mission_review_queue_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        key: 0
        for key in ("ready", "observation", "prediction", "outcome", "preset", "note", "control", "artifact", "other")
    }
    for run in runs:
        bucket = _mission_review_bucket(_mission_review_status(run))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _mission_review_next_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    priority = ("outcome", "preset", "observation", "prediction", "note", "control", "artifact", "other")
    for bucket in priority:
        for run in runs:
            if _mission_review_bucket(_mission_review_status(run)) == bucket:
                return run
    return None


def _mission_review_status(run: dict[str, Any]) -> str:
    text = str(run.get("mission_evidence") or "").strip()
    return text.split(";", 1)[0].strip() if text else "Unknown"


def _mission_review_bucket(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"ready for review", "artifacts ready", "course artifacts ready"}:
        return "ready"
    if normalized == "outcome review pending":
        return "outcome"
    if normalized == "needs observation":
        return "observation"
    if normalized == "needs prediction":
        return "prediction"
    if normalized.startswith("needs required preset"):
        return "preset"
    if normalized == "ready, add note next":
        return "note"
    if normalized == "needs learner control":
        return "control"
    if normalized in {"needs plot", "needs worksheet", "needs required artifact"}:
        return "artifact"
    return "other"


def _merge_outcome_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        outcome_counts = run.get("outcome_counts", {})
        if not isinstance(outcome_counts, dict):
            continue
        for label, count in outcome_counts.items():
            counts[str(label)] = counts.get(str(label), 0) + int(count)
    return counts


def _format_outcome_mix(outcome_counts: dict[str, int]) -> str:
    if not outcome_counts:
        return "No outcomes yet"
    return ", ".join(f"{label} {count}" for label, count in sorted(outcome_counts.items()))


def _run_matches_category(run: dict[str, Any], key: str) -> bool:
    text = " ".join(
        str(run.get(name, ""))
        for name in ("lab_name", "config_name", "config_path", "name")
    ).lower()
    return key in text


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").lower()


def _index_metric_keys(runs: list[dict[str, Any]]) -> list[str]:
    summaries = [run.get("summary", {}) for run in runs]
    return [
        key
        for key in INDEX_METRIC_KEYS
        if any(_has_display_value(summary.get(key)) for summary in summaries)
    ]


def _has_display_value(value: Any) -> bool:
    return value is not None and value != ""


def _metric_label(key: str) -> str:
    return key.replace("_", " ")


def _localized_metric_label(key: str, *, language: str) -> str:
    label = _metric_label(key)
    if language != "ko":
        return {
            "samples": "Samples",
            "duration": "Run time [s]",
            "max abs position": "Peak position [m]",
            "max abs velocity": "Peak velocity [m/s]",
            "max abs force": "Peak force [N]",
            "max abs control force": "Peak control force [N]",
            "max joint error norm": "Peak joint error [rad]",
            "final joint error norm": "Final joint error [rad]",
            "max task error norm": "Peak task-space error [m]",
            "final task error norm": "Final task-space error [m]",
            "max cartesian error cm": "Peak Cartesian error [cm]",
            "final cartesian error cm": "Final Cartesian error [cm]",
            "max abs qdot": "Peak joint speed [rad/s]",
            "max abs tau cmd": "Peak commanded torque [N·m]",
            "max abs tau total": "Peak total torque [N·m]",
            "max jacobian condition": "Peak Jacobian condition number",
            "min manipulability": "Minimum manipulability",
            "max wall penetration": "Peak wall penetration [m]",
            "max abs virtual wall force": "Peak virtual-wall force [N]",
            "max hand speed": "Peak hand speed [m/s]",
            "settling time": "Settling time [s]",
            "overshoot": "Overshoot [%]",
        }.get(label, label.title())
    return {
        "samples": "샘플 수",
        "duration": "실행 시간 [초]",
        "max abs position": "최대 위치 절댓값",
        "max abs velocity": "최대 속도 절댓값",
        "max abs force": "최대 힘 절댓값",
        "max abs control force": "최대 제어력 절댓값",
        "max joint error norm": "최대 관절 오차 [rad]",
        "final joint error norm": "최종 관절 오차 [rad]",
        "max task error norm": "최대 작업공간 오차 [m]",
        "final task error norm": "최종 작업공간 오차 [m]",
        "max cartesian error cm": "최대 데카르트 오차 [cm]",
        "final cartesian error cm": "최종 데카르트 오차 [cm]",
        "max abs qdot": "최대 관절 속도 [rad/s]",
        "max abs tau cmd": "최대 명령 토크 [N·m]",
        "max abs tau total": "최대 총 토크 [N·m]",
        "max jacobian condition": "최대 자코비안 조건수",
        "min manipulability": "최소 조작성",
        "max wall penetration": "최대 벽 침투량 [m]",
        "max abs virtual wall force": "최대 가상 벽 힘 [N]",
        "max hand speed": "최대 손끝 속도 [m/s]",
        "settling time": "정착 시간 [s]",
        "overshoot": "오버슈트 [%]",
    }.get(label, label)


def _localized_plot_label(plot: Path, *, language: str) -> str:
    label = _index_plot_label(plot)
    if language != "ko":
        return label
    return {
        "Position": "위치",
        "Error": "오차",
        "Cartesian Error": "데카르트 오차",
        "End Effector": "손끝 위치",
        "Wall Timing": "가상 벽 주요 시점",
        "Target-Wall Gap": "목표-벽 간격",
        "Virtual Wall": "가상 벽 응답",
        "Wall Parameters": "가상 벽 파라미터",
        "Wall Penetration": "가상 벽 침투량",
        "Wall Retreat": "가상 벽 후퇴",
        "Hand X Speed": "손끝 X 속도",
        "Hand X Position": "손끝 X 위치",
        "Hand Y Position": "손끝 Y 위치",
        "Singularity": "특이점",
        "DLS": "DLS 응답",
        "Disturbance": "외란 응답",
        "Torque": "토크",
        "Control Force": "제어력",
        "Force": "힘",
        "PID Terms": "PID 항",
        "Velocity": "속도",
        "Energy": "에너지",
    }.get(label, label)


def _localized_scenario_title(
    config_path: str, *, fallback: str, language: str = "ko"
) -> str:
    try:
        from mclab.application.catalog import ScenarioCatalog
        from mclab.application.i18n import localized_scenario_text

        scenario = ScenarioCatalog.default().find_by_config(config_path)
    except Exception:
        return fallback
    if scenario is None:
        return fallback
    return localized_scenario_text(
        language=language,
        scenario_id=scenario.id,
        title=scenario.title,
        purpose=scenario.purpose,
        lab_name=scenario.lab_name,
    )[0]


def _localized_report_title(
    summary: dict[str, Any], *, fallback: str, language: str = "ko"
) -> str:
    config_path = _normalize_path(str(summary.get("config_path") or ""))
    scenario_title = _localized_scenario_title(
        config_path, fallback="", language=language
    )
    if not scenario_title:
        return fallback
    lab_name = _cli_lab_name(str(summary.get("lab_name") or config_path))
    lab_titles = {
        "ko": {
            "lab01": "Lab01 질량·스프링·감쇠",
            "lab02": "Lab02 PID 제어",
            "lab03": "Lab03 2DOF 로봇",
            "lab04": "Lab04 Panda 매니퓰레이터",
        },
        "en": {
            "lab01": "Lab01 Mass-spring-damper",
            "lab02": "Lab02 PID control",
            "lab03": "Lab03 2DOF robot",
            "lab04": "Lab04 Panda manipulator",
        },
    }
    lab_title = lab_titles.get(language, lab_titles["en"]).get(lab_name, lab_name)
    return f"{lab_title} · {scenario_title}" if lab_title else scenario_title


def _localized_comparison_text(batch_name: str, fallback: str) -> tuple[str, str]:
    titles = {
        "lab01_msd_compare": "Lab01 질량·스프링·감쇠 비교",
        "lab02_pid_compare": "Lab02 PID 비교",
        "lab03_2dof_compare": "Lab03 2DOF 비교",
        "lab04_wall_compare": "Lab04 Panda 가상 벽 비교",
        "lab04_cartesian_compare": "Lab04 Panda 데카르트 이동 비교",
    }
    return (
        titles.get(batch_name, fallback),
        "제어된 여러 조건을 한 보고서에서 비교해 파라미터 변화의 영향을 확인하세요.",
    )


def _report_title(output: Path, summary: dict[str, Any]) -> str:
    lab_name = str(summary.get("lab_name") or output.name)
    config_name = str(summary.get("config_name") or "")
    return f"{lab_name} - {config_name}" if config_name else lab_name


def _config_cell(run: dict[str, Any]) -> str:
    config_name = str(run.get("config_name") or "")
    config_path = str(run.get("config_path") or "")
    return config_path or config_name


def _run_repeat_command_cell(run: dict[str, Any]) -> str:
    command = _run_repeat_command(run)
    if not command:
        return '<span class="muted">No command</span>'
    return f'<div class="command-cell"><code>{escape(command)}</code></div>'


def _run_repeat_command(run: dict[str, Any]) -> str:
    summary = run.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    if _summary_is_all_batch(summary):
        return "python -m mclab batch all --open-report"
    if _summary_is_comparison_batch(summary):
        batch_name = _summary_batch_command_name(summary)
        return f"python -m mclab batch {batch_name} --open-report" if batch_name else ""

    config_path = str(summary.get("config_path") or run.get("config_path") or "").strip()
    lab_name = _cli_lab_name(str(summary.get("lab_name") or run.get("lab_name") or config_path))
    if not config_path or not lab_name:
        return ""
    plot_args = _plot_selection_args_for_config(config_path)
    if _summary_requires_hands_on_evidence(summary):
        return (
            f"python -m mclab run {lab_name} --config {config_path} "
            f"--viewer --realtime --pause-at-end --plot{plot_args} --open-report"
        )
    return f"python -m mclab run {lab_name} --config {config_path} --headless --plot{plot_args} --open-report"


def _plot_selection_args_for_config(config_path: str) -> str:
    selection = _plot_selection_for_config(config_path)
    return f" --plots {selection}" if selection else ""


def _plot_selection_for_config(config_path: str) -> str:
    normalized = _normalize_path(config_path)
    config = _config_for_path(config_path)
    config_selection = str(config.get("plots") or "").strip() if isinstance(config, dict) else ""
    if config_selection:
        return config_selection

    for step in INDEX_LEARNING_PATH:
        if step.config_path and _normalize_path(step.config_path) == normalized:
            return step.plots

    for suggestions in NEXT_RUN_SUGGESTIONS.values():
        for suggestion in suggestions:
            if _normalize_path(suggestion.config_path) == normalized:
                return suggestion.plots

    return _inferred_plot_selection(normalized, config)


def _config_for_path(config_path: str) -> dict[str, Any]:
    try:
        config = load_config(config_path)
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _inferred_plot_selection(normalized_config_path: str, config: dict[str, Any]) -> str:
    mode = str(config.get("mode") or "").strip().lower()
    context = f"{normalized_config_path} {mode}"
    if "interactive_virtual_wall" in context:
        return "wall"
    if "wall" in context or "impedance_wall" in context or "virtual_wall" in context:
        return "wall_compare"
    if "interactive_cartesian_reach" in context or "cartesian" in context or "ee_reach" in context:
        return "cartesian_reach"
    if "neutral_hold_30s" in context:
        return "stability"
    if "dls_singularity" in context or "condition_aware_dls" in context:
        return "dls_disturbance"
    if "task_space" in context:
        return "task"
    return "essential"


def _summary_batch_command_name(summary: dict[str, Any]) -> str:
    for key in ("batch_name", "config_name"):
        value = str(summary.get(key) or "").strip()
        if value:
            return value
    return ""


def _run_next_cue_text(run: dict[str, Any]) -> str:
    summary = run.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    events = run.get("interaction_events")
    events = events if isinstance(events, list) else []
    config = run.get("config")
    config = config if isinstance(config, dict) else {}
    has_plots = bool(run.get("plots"))
    has_worksheet = isinstance(run.get("worksheet"), dict)

    if _summary_is_all_batch(summary):
        if has_worksheet:
            return (
                "Next cue: Open the course worksheet, then compare each linked batch Prediction Check "
                "and Viewer Handoff."
            )
        return "Next cue: Rerun all comparison batches to regenerate the course worksheet."

    if _summary_is_comparison_batch(summary):
        if not has_worksheet:
            return "Next cue: Rerun the comparison batch to regenerate the worksheet."
        if not has_plots:
            return "Next cue: Rerun the comparison batch with plots, then inspect the comparison plots."
        return (
            "Next cue: Open the worksheet Prediction Check, then open the report Viewer Handoff "
            "and run the recommended viewer scenario."
        )

    if _summary_requires_hands_on_evidence(summary):
        return _hands_on_run_next_cue(summary, events, config, has_plots=has_plots, has_worksheet=has_worksheet, run=run)

    if not has_plots:
        return "Next cue: Rerun with --plot, then inspect the priority graph."
    if not has_worksheet:
        return "Next cue: Rerun or regenerate the worksheet before moving on."
    next_step = str(run.get("next_step") or "").strip()
    if next_step:
        return f"Next cue: Review the priority plot and worksheet, then try: {_short_evidence_text(next_step, max_length=96)}"
    return "Next cue: Review the priority plot and worksheet, then run the next guided scenario."


def _run_next_cue_cell(run: dict[str, Any]) -> str:
    cue = escape(_run_next_cue_text(run))
    handoff_href = _run_viewer_handoff_href(run)
    if not handoff_href:
        return cue
    return (
        f"{cue}"
        '<div class="path-links">'
        f'<a class="plot-chip" href="{escape(handoff_href)}">Viewer Handoff</a>'
        "</div>"
    )


def _run_viewer_handoff_href(run: dict[str, Any]) -> str:
    summary = run.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    if _summary_is_all_batch(summary) or not _summary_is_comparison_batch(summary):
        return ""
    report = str(run.get("report") or "").strip()
    if not report or not report.endswith("/report.html"):
        return ""
    return f"{report}#viewer-handoff"


def _hands_on_run_next_cue(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    has_plots: bool,
    has_worksheet: bool,
    run: dict[str, Any],
) -> str:
    markers, predictions, notes, outcomes = _observation_evidence_counts_from_events(events)
    learner_controls = _learner_control_event_count(events)
    if predictions > outcomes:
        return "Next cue: Review latest evidence and choose the missing prediction outcome."

    labels = _configured_preset_labels(config)
    if len(labels) >= 2:
        required_labels, _required_tried, next_required = _required_preset_progress(config, events)
        if required_labels and next_required:
            return f"Next cue: Try required preset {next_required}, then mark a prediction-backed observation."
        tried = _distinct_preset_labels(events, labels)
        if not required_labels and markers <= 0 and len(tried) < 2:
            next_label = next((label for label in labels if label not in tried), "")
            preset_text = f"preset {next_label}" if next_label else "one more preset"
            return f"Next cue: Try {preset_text}, then mark a prediction-backed observation."

    control_phrase = _report_learner_control_phrase(config, summary)
    if markers <= 0:
        if learner_controls > 0:
            return "Next cue: Mark observation with a prediction and note for the control you changed."
        return f"Next cue: Use {control_phrase}, then Mark observation with a prediction and note."
    if predictions <= 0:
        return "Next cue: Add a prediction before marking the next observation."
    if notes <= 0:
        return "Next cue: Add a short note or Use live status before moving on."
    if learner_controls <= 0:
        return f"Next cue: Use {control_phrase}, then mark another observation with a prediction and note."
    if len(labels) >= 2:
        tried = _distinct_preset_labels(events, labels)
        if len(tried) < 2:
            next_label = next((label for label in labels if label not in tried), "")
            preset_text = f"preset {next_label}" if next_label else "one more preset"
            return f"Next cue: Try {preset_text}, then mark a prediction-backed observation."
    if isinstance(run.get("replay"), dict):
        return "Next cue: Replay the tuned config, then run Compare for the broader tradeoff."
    if not has_plots:
        return "Next cue: Rerun with plots, then inspect the priority graph."
    if not has_worksheet:
        return "Next cue: Rerun or regenerate the worksheet before moving on."
    return "Next cue: Review the latest plot and worksheet, then run Next or Compare."


def _run_evidence_cell(run: dict[str, Any]) -> str:
    markers = int(run.get("observation_markers", 0))
    predictions = int(run.get("learner_predictions", 0))
    notes = int(run.get("learner_notes", 0))
    outcomes = int(run.get("learner_outcomes", 0))
    if markers <= 0:
        return "No markers"
    parts = [f"{markers} observation{'s' if markers != 1 else ''}"]
    parts.append(f"{predictions} prediction{'s' if predictions != 1 else ''}")
    if outcomes:
        parts.append(f"{outcomes} outcome{'s' if outcomes != 1 else ''}")
    if notes:
        parts.append(f"{notes} note{'s' if notes != 1 else ''}")
    latest = str(run.get("latest_evidence") or "").strip()
    if latest:
        parts.append(f"Latest: {latest}")
    flow = str(run.get("observation_flow") or "").strip()
    if flow:
        parts.append(flow)
    next_step = str(run.get("observation_next_step") or "").strip()
    if next_step:
        parts.append(next_step)
    return ", ".join(parts)


def _activity_mix_index_text(events: list[dict[str, Any]], config: dict[str, Any] | None = None) -> str:
    items = dict(_activity_mix_items(events, config))
    if not items:
        return "No learner controls"
    next_step = str(items.get("Next activity step") or "").strip()
    next_text = f"; next: {_short_evidence_text(next_step, max_length=72)}" if next_step else ""
    path = str(items.get("Activity path") or "").strip()
    path_text = f"; path: {_short_evidence_text(path, max_length=96)}" if path and path != "none" else ""
    return (
        f"{items.get('Interaction variety')}; "
        f"buttons {items.get('Button actions')}, sliders {items.get('Slider changes')}, "
        f"presets {items.get('Preset choices')}, markers {items.get('Observation markers')}"
        f"{next_text}"
        f"{path_text}"
    )


def _mission_evidence_index_text(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[dict[str, str]],
    config: dict[str, Any] | None = None,
    *,
    worksheet: dict[str, str] | None = None,
    completion_decision: CompletionDecision,
) -> str:
    status = _completion_status_text(completion_decision, summary)
    items = dict(_mission_evidence_items(summary, events, plots, config))
    next_step = str(items.get("Next proof step") or "").strip()
    if _summary_is_all_batch(summary):
        next_step = (
            "Open the course worksheet, then follow each linked batch Prediction Check."
            if completion_decision.complete
            else "Rerun all batches to regenerate canonical course review artifacts."
        )
    reason = completion_decision.primary_reason.value
    if status and next_step:
        return (
            f"{status}; {_short_evidence_text(next_step, max_length=96)}; "
            f"contract {reason}"
        )
    return f"{status or next_step}; contract {reason}"


def _completion_status_text(
    decision: CompletionDecision,
    summary: dict[str, Any] | None = None,
) -> str:
    if decision.complete:
        if decision.outcome_review_pending:
            return "Outcome review pending"
        if summary is not None and _summary_is_all_batch(summary):
            return "Course artifacts ready"
        if summary is not None and _summary_is_comparison_batch(summary):
            return "Artifacts ready"
        return "Ready for review"
    statuses = {
        CompletionReason.RUN_NOT_COMPLETED: "Run not completed",
        CompletionReason.PLOT_MISSING: "Needs plot",
        CompletionReason.REQUIRED_ARTIFACT_MISSING: "Needs required artifact",
        CompletionReason.INTERACTION_EVIDENCE_INVALID: "Invalid interaction evidence",
        CompletionReason.OBSERVATION_MISSING: "Needs observation",
        CompletionReason.PREDICTION_MISSING: "Needs prediction",
        CompletionReason.NOTE_MISSING: "Ready, add note next",
        CompletionReason.REQUIRED_PRESET_MISSING: "Needs required preset",
        CompletionReason.LEARNER_CONTROL_MISSING: "Needs learner control",
        CompletionReason.LEGACY_MANIFEST_MISSING: "Legacy manifest missing",
        CompletionReason.MANIFEST_MISSING: "Manifest missing",
        CompletionReason.MANIFEST_INVALID: "Manifest invalid",
        CompletionReason.MANIFEST_SCHEMA_UNSUPPORTED: "Manifest schema unsupported",
        CompletionReason.SCENARIO_MISMATCH: "Scenario mismatch",
        CompletionReason.RULE_UNAVAILABLE: "Completion rule unavailable",
        CompletionReason.RULE_INVALID: "Completion rule invalid",
    }
    status = statuses.get(decision.primary_reason, "Completion incomplete")
    if (
        decision.primary_reason == CompletionReason.REQUIRED_PRESET_MISSING
        and decision.next_required_preset
    ):
        status = f"{status} {decision.next_required_preset}"
    return status


def _challenge_evidence_index_text(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    plots: list[dict[str, str]],
    config: dict[str, Any] | None = None,
    *,
    worksheet: dict[str, str] | None = None,
    completion_decision: CompletionDecision,
) -> str:
    if not completion_decision.complete:
        status = _completion_status_text(completion_decision, summary)
        return (
            f"{status}; contract {completion_decision.primary_reason.value}; "
            "resolve the completion contract before challenge review."
        )
    if _summary_is_all_batch(summary):
        if isinstance(worksheet, dict):
            return "Ready to review; source course worksheet; compare linked batch Prediction Checks."
        return "Needs worksheet evidence; Rerun all batches to regenerate course review artifacts."
    items = dict(
        _challenge_evidence_items(
            summary,
            events,
            plots,
            config,
            completion_decision=completion_decision,
        )
    )
    status = str(items.get("Challenge status") or "").strip()
    source = str(items.get("Proof source") or "").strip()
    next_step = str(items.get("Next challenge step") or "").strip()
    details = []
    if source:
        details.append(f"source {source}")
    if next_step:
        details.append(_short_evidence_text(next_step, max_length=96))
    suffix = f"; {'; '.join(details)}" if details else ""
    return f"{status or 'Needs evidence'}{suffix}"


def _summary_is_all_batch(summary: dict[str, Any]) -> bool:
    batch_name = str(summary.get("batch_name") or summary.get("config_name") or "").strip()
    return batch_name == "all"


def _summary_is_comparison_batch(summary: dict[str, Any]) -> bool:
    if _summary_is_all_batch(summary):
        return False
    lab_name = str(summary.get("lab_name") or "").strip()
    batch_name = str(summary.get("batch_name") or "").strip()
    config_name = str(summary.get("config_name") or "").strip()
    return bool(batch_name) or lab_name in {"batch", "batch_group"} or config_name.endswith("_compare")


def _run_replay_cell(run: dict[str, Any]) -> str:
    replay = run.get("replay")
    if not isinstance(replay, dict):
        return '<span class="muted">No replay</span>'
    href = str(replay.get("href") or "")
    label = str(replay.get("label") or "Tuned config")
    if not href:
        return '<span class="muted">No replay</span>'
    return f'<a class="plot-chip" href="{escape(href)}">{escape(label)}</a>'


def _run_folder_cell(run: dict[str, Any]) -> str:
    folder = run.get("folder")
    if not isinstance(folder, dict):
        return '<span class="muted">No folder</span>'
    href = str(folder.get("href") or "")
    label = str(folder.get("label") or "Folder")
    if not href:
        return '<span class="muted">No folder</span>'
    return f'<a class="plot-chip" href="{escape(href)}">{escape(label)}</a>'


def _run_worksheet_cell(run: dict[str, Any]) -> str:
    worksheet = run.get("worksheet")
    if not isinstance(worksheet, dict):
        return '<span class="muted">No worksheet</span>'
    href = str(worksheet.get("href") or "")
    label = str(worksheet.get("label") or "Worksheet")
    if not href:
        return '<span class="muted">No worksheet</span>'
    return f'<a class="plot-chip" href="{escape(href)}">{escape(label)}</a>'


def _run_plots_cell(run: dict[str, Any]) -> str:
    plots = run.get("plots", [])
    if not plots:
        return '<span class="muted">No plots</span>'
    links = []
    for plot in plots:
        if not isinstance(plot, dict):
            continue
        href = str(plot.get("href") or "")
        label = str(plot.get("label") or "")
        if not href or not label:
            continue
        links.append(f'<a class="plot-chip" href="{escape(href)}">{escape(label)}</a>')
    if not links:
        return '<span class="muted">No plots</span>'
    return '<div class="plot-links">' + "".join(links) + "</div>"


def _run_plot_review_cell(run: dict[str, Any]) -> str:
    plots = run.get("plots", [])
    if not isinstance(plots, list) or not plots:
        return "Plot review: Not available until a plot is saved."
    for plot in plots:
        if not isinstance(plot, dict):
            continue
        href = str(plot.get("href") or "")
        label = str(plot.get("label") or "").strip()
        if not href:
            continue
        guidance = _plot_guidance(Path(href).name)
        if guidance is not None:
            title, detail = guidance
            return f"Plot review: {title} - {_short_evidence_text(detail, max_length=96)}"
        if label:
            return f"Plot review: Open {label} and compare it with the worksheet."
    return "Plot review: Open the saved plot and compare it with the worksheet."


def _discover_output_folder(child: Path) -> dict[str, str]:
    return {
        "href": f"{child.name}/",
        "label": "Folder",
    }


def _trusted_replay_config(record: ArtifactRecord) -> dict[str, str] | None:
    if not record.tuned_available:
        return None
    return {
        "href": f"{record.path.name}/learner_tuned_config.yaml",
        "label": "Tuned config",
    }


def _trusted_worksheet_link(record: ArtifactRecord) -> dict[str, str] | None:
    if not record.worksheet_available:
        return None
    return {
        "href": f"{record.path.name}/worksheet.md",
        "label": "Worksheet",
    }


def _discover_trusted_run_plots(
    record: ArtifactRecord,
    summary: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    summary = summary or {}
    priorities = plot_priorities_for_context(
        config_path=str(summary.get("config_path") or ""),
        config_name=str(summary.get("config_name") or ""),
        lab_name=str(summary.get("lab_name") or ""),
        batch_name=str(summary.get("batch_name") or ""),
    )
    plots = sorted(
        record.plot_paths,
        key=lambda plot: _index_plot_sort_key(plot, priorities),
    )
    return [
        {
            "href": f"{record.path.name}/{plot.relative_to(record.path).as_posix()}",
            "label": _index_plot_label(plot),
        }
        for plot in plots[:INDEX_MAX_PLOT_LINKS]
    ]


def _index_plot_sort_key(plot: Path, priorities: tuple[str, ...] = INDEX_PLOT_PRIORITY) -> tuple[int, str]:
    name = _index_plot_name(plot)
    for index, priority in enumerate(priorities):
        if name == priority or name.startswith(f"{priority}_") or name.endswith(f"_{priority}"):
            return index, name
    return len(priorities), name


def _index_plot_label(plot: Path) -> str:
    guidance = _plot_guidance(plot.name)
    if guidance is not None:
        return guidance[0]
    return _index_plot_name(plot).replace("_", " ").title()


def _index_plot_name(plot: Path) -> str:
    return plot.stem.lower().replace("-", "_").removesuffix("_compare")


def _publication_json(
    publication: OutputPublication,
    relative: tuple[str, ...],
) -> dict[str, Any]:
    if not publication.regular_file_exists(relative):
        return {}
    data = publication.read_bytes(
        relative,
        description="report JSON input",
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=False,
    )
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _publication_text(
    publication: OutputPublication,
    relative: tuple[str, ...],
) -> str:
    if not publication.regular_file_exists(relative):
        return ""
    data = publication.read_bytes(
        relative,
        description="report text input",
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=True,
    )
    return data.decode("utf-8", errors="replace")


def _display_interaction_events(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _observation_outcome_counts_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if not _is_observation_marker(event):
            continue
        value = event.get("value")
        if not isinstance(value, dict):
            continue
        outcome = str(value.get("outcome") or "").strip()
        if outcome:
            counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def _latest_observation_evidence_from_events(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if not _is_observation_marker(event):
            continue
        value = event.get("value")
        if not isinstance(value, dict):
            return "marker saved without details"
        parts: list[str] = []
        prediction = str(value.get("prediction") or "").strip()
        note = str(value.get("note") or "").strip()
        outcome = str(value.get("outcome") or "").strip()
        status = value.get("status")
        if prediction:
            parts.append(f"Prediction: {_short_evidence_text(prediction)}")
        if outcome:
            parts.append(f"Outcome: {_short_evidence_text(outcome, max_length=40)}")
        elif prediction:
            parts.append("Outcome: missing review")
        if note:
            parts.append(f"Note: {_short_evidence_text(note)}")
            note_summary = _note_evidence_summary(note)
            if note_summary:
                parts.append(f"Note evidence: {note_summary}")
        if isinstance(status, dict):
            status_text = _latest_status_evidence(status)
            if status_text:
                parts.append(f"Status: {status_text}")
        if parts:
            return "; ".join(parts)
        return "marker saved without prediction or note"
    return ""


def _latest_status_evidence(status: dict[str, Any], *, limit: int = 3) -> str:
    pairs: list[str] = []
    for key, value in status.items():
        text = _format_value(value).strip()
        if not text or text in {"--", "n/a"}:
            continue
        pairs.append(f"{key}={_short_evidence_text(text, max_length=36)}")
        if len(pairs) >= limit:
            break
    return ", ".join(pairs)


def _note_evidence_summary(value: Any, *, limit: int = 3) -> str:
    items = _note_evidence_items(value)
    if len(items) <= 1:
        return ""
    shown = [_short_evidence_text(item, max_length=64) for item in items[:limit]]
    if len(items) > limit:
        shown.append("...")
    return " | ".join(shown)


def _short_evidence_text(value: str, *, max_length: int = 88) -> str:
    text = " ".join(str(value).split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()
