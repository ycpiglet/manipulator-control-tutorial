"""Trajectory planning and 1D tracking lab.

This is an incremental Lab03 implementation focused on trajectory profiles
before the later 2DOF manipulator work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.config import resolve_project_path
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import (
    load_model_and_data,
    maybe_launch_viewer,
    pause_viewer_at_end,
    sync_viewer,
    viewer_clock,
)
from mclab.sim.one_dof import configure_slider_plant, slider_state
from mclab.sim.plotting import save_time_series_plots
from mclab.trajectories import build_trajectory


def run(
    config: dict[str, Any],
    *,
    config_path: Path | None = None,
    output_dir: Path | None = None,
    plot: bool = False,
    viewer: bool = False,
    headless: bool = False,
    realtime: bool = False,
    pause_at_end: bool = False,
    seed: int | None = None,
) -> Path:
    del seed
    lab_name = "lab03_trajectory"
    model_path = config.get("model_path", "models/lab03_2dof/scene.xml")
    mujoco, model, data = load_model_and_data(model_path)
    handles = configure_slider_plant(mujoco, model, data, config)
    logger = RunLogger(lab_name, config, config_path=config_path, output_dir=output_dir)

    sim_time = float(config.get("sim_time", 5.0))
    trajectory = build_trajectory(dict(config.get("trajectory", {})))
    controller_config = dict(config.get("tracking_controller", {}))
    kp = float(controller_config.get("kp", 120.0))
    kd = float(controller_config.get("kd", 18.0))
    feedforward_mass = float(controller_config.get("feedforward_mass", config.get("mass", 1.0)))
    use_feedforward = bool(controller_config.get("feedforward_acceleration", True))
    force_limit = controller_config.get("force_limit", 200.0)
    lower_limit, upper_limit = _limits(force_limit)
    kt = float(config.get("torque_constant", 1.0))

    viewer_handle = maybe_launch_viewer(mujoco, model, data, enabled=viewer and not headless)
    wall_start = viewer_clock()
    sim_start = float(data.time)
    completed = False
    try:
        while data.time < sim_time:
            position, velocity, _ = slider_state(data, handles)
            target = trajectory.evaluate(float(data.time))
            feedback = kp * (target.position - position) + kd * (target.velocity - velocity)
            feedforward = feedforward_mass * target.acceleration if use_feedforward else 0.0
            control_force = _clip(feedback + feedforward, lower_limit, upper_limit)

            data.ctrl[handles.actuator_id] = control_force
            mujoco.mj_step(model, data)
            sync_viewer(
                viewer_handle,
                data,
                realtime=realtime,
                wall_start=wall_start,
                sim_start=sim_start,
            )

            position, velocity, acceleration = slider_state(data, handles)
            logger.record(
                time=float(data.time),
                position=position,
                velocity=velocity,
                acceleration=acceleration,
                target_position=target.position,
                target_velocity=target.velocity,
                target_acceleration=target.acceleration,
                target_jerk=target.jerk,
                position_error=target.position - position,
                velocity_error=target.velocity - velocity,
                control_force=control_force,
                current_proxy=control_force / kt,
            )
        completed = True
    finally:
        if viewer_handle is not None:
            if completed:
                pause_viewer_at_end(viewer_handle, enabled=pause_at_end)
            viewer_handle.close()

    summary = _summary(logger.rows)
    output_path = logger.save(summary=summary, notes=_notes(config))
    if plot:
        save_time_series_plots(
            output_path,
            logger.rows,
            [
                (
                    "position.png",
                    "Trajectory Position Tracking",
                    "position [m]",
                    ["position", "target_position"],
                ),
                (
                    "velocity.png",
                    "Trajectory Velocity",
                    "velocity [m/s]",
                    ["velocity", "target_velocity"],
                ),
                (
                    "acceleration.png",
                    "Trajectory Acceleration",
                    "acceleration [m/s^2]",
                    ["acceleration", "target_acceleration"],
                ),
                ("jerk.png", "Trajectory Jerk", "jerk [m/s^3]", ["target_jerk"]),
                ("torque.png", "Control Effort", "force / torque proxy", ["control_force"]),
                ("current_proxy.png", "Current Proxy", "current proxy", ["current_proxy"]),
                ("error.png", "Tracking Error", "error [m]", ["position_error"]),
            ],
        )
    return resolve_project_path(output_path)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    max_error = max(abs(float(row["position_error"])) for row in rows)
    max_effort = max(abs(float(row["control_force"])) for row in rows)
    return {
        "max_abs_tracking_error": max_error,
        "final_tracking_error": rows[-1]["position_error"],
        "max_abs_control_force": max_effort,
    }


def _limits(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    magnitude = abs(float(value))
    return -magnitude, magnitude


def _clip(value: float, lower: float | None, upper: float | None) -> float:
    if lower is not None and value < lower:
        return lower
    if upper is not None and value > upper:
        return upper
    return value


def _notes(config: dict[str, Any]) -> str:
    trajectory = config.get("trajectory", {})
    return f"""# Lab03 Trajectory Planning

Incremental trajectory-planning lab on a MuJoCo slide-joint plant.

Generated profiles include target position, velocity, acceleration, and jerk.

- trajectory type: {trajectory.get("type", "minimum_jerk")}
- start: {trajectory.get("start", trajectory.get("start_position", 0.0))}
- end: {trajectory.get("end", trajectory.get("goal_position", 1.0))}
"""
