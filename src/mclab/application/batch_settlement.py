"""Fail-closed recovery of producer-created empty batch directories."""

from __future__ import annotations

import os
from typing import Any

from mclab.application.batch_progress import ALL_COMPARE_BATCH_NAMES

MAX_RECOVERABLE_BATCH_MEMBERS = 256

# This is a deletion allowlist, not a second learner catalog.  A parity test
# binds it to ``mclab.batch.BATCH_SETS`` so a catalog change cannot silently
# widen or stale the paths that cancellation settlement may remove.
RECOVERABLE_BATCH_SCENARIOS = {
    "lab01_msd_compare": frozenset(
        {"baseline", "underdamped", "overdamped", "high_stiffness", "low_stiffness"}
    ),
    "lab02_pid_compare": frozenset(
        {
            "baseline",
            "low_p_gain",
            "high_p_gain",
            "pd_damping",
            "saturation",
            "windup",
            "anti_windup",
            "sensor_noise",
            "control_delay",
        }
    ),
    "lab03_2dof_compare": frozenset(
        {
            "joint_space",
            "task_space",
            "singularity",
            "dls_singularity",
            "condition_aware_dls",
            "condition_aware_early",
            "condition_aware_late",
            "condition_aware_inner_target",
            "condition_aware_edge_target",
            "condition_aware_upper_path",
            "condition_aware_lower_path",
            "condition_aware_shoulder_disturbance",
            "condition_aware_elbow_disturbance",
            "condition_aware_staggered_disturbance",
            "condition_aware_low_torque",
            "condition_aware_high_torque",
            "condition_aware_slow_command",
            "condition_aware_fast_command",
            "condition_aware_low_joint_speed",
            "condition_aware_high_joint_speed",
            "condition_aware_direct_retarget",
            "condition_aware_inward_retarget",
            "condition_aware_fixed_speed_retarget",
            "condition_aware_adaptive_speed_retarget",
        }
    ),
    "lab04_wall_compare": frozenset(
        {
            "soft_wall",
            "stiff_wall",
            "low_damping_wall",
            "high_damping_wall",
            "near_wall",
            "far_wall",
            "low_retreat_wall",
            "high_retreat_wall",
            "slow_approach_wall",
            "fast_approach_wall",
            "shallow_push_wall",
            "deep_push_wall",
            "contact_cycle_wall",
        }
    ),
    "lab04_cartesian_compare": frozenset(
        {"baseline_reach", "soft_reach", "stiff_reach"}
    ),
}


def _remove_empty_directory(root_pin: Any, relative: tuple[str, ...]) -> bool:
    names = root_pin.list_names(
        relative,
        max_entries=MAX_RECOVERABLE_BATCH_MEMBERS,
    )
    if names:
        return False
    root_pin.rmdir(relative)
    return True


def prune_interrupted_batch_directories(root_pin: Any) -> None:
    """Remove only allowlisted empty POSIX directories left by the worker."""

    # POSIX directory descriptors give the required ancestor-relative deletion
    # proof. Windows stays fail-closed because an intermediate junction cannot
    # be pinned with the same proof by the current output-root implementation.
    if os.name == "nt":
        return
    for batch_name in ALL_COMPARE_BATCH_NAMES:
        batch = (batch_name,)
        if not root_pin.lexists(batch):
            continue
        root_pin.validate_directory(
            batch,
            description="interrupted course-comparison batch",
        )
        remove_batch = False
        with root_pin.scoped_directory_pin(
            batch,
            description="interrupted course-comparison batch",
        ):
            names = root_pin.list_names(
                batch,
                max_entries=MAX_RECOVERABLE_BATCH_MEMBERS,
            )
            for name in names:
                if name == "comparison_plots":
                    comparison_plots = (*batch, name)
                    root_pin.validate_directory(
                        comparison_plots,
                        description="interrupted batch comparison plots",
                    )
                    _remove_empty_directory(root_pin, comparison_plots)
                    continue
                if name not in RECOVERABLE_BATCH_SCENARIOS[batch_name]:
                    continue
                scenario = (*batch, name)
                root_pin.validate_directory(
                    scenario,
                    description="interrupted course-comparison scenario",
                )
                with root_pin.scoped_directory_pin(
                    scenario,
                    description="interrupted course-comparison scenario",
                ):
                    if root_pin.lexists((*scenario, "plots")):
                        plots = (*scenario, "plots")
                        root_pin.validate_directory(
                            plots,
                            description="interrupted course-comparison plots",
                        )
                        _remove_empty_directory(root_pin, plots)
                _remove_empty_directory(root_pin, scenario)
            remove_batch = not root_pin.list_names(
                batch,
                max_entries=MAX_RECOVERABLE_BATCH_MEMBERS,
            )
        if remove_batch:
            root_pin.rmdir(batch)
    root_pin.assert_transaction_boundaries()
