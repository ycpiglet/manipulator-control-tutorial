"""Trajectory planning and 1D tracking lab.

This is an incremental Lab03 implementation focused on trajectory profiles
before the later 2DOF manipulator work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.config import resolve_project_path
from mclab.sim.interaction import KeyForcePulse, maybe_start_interaction_panel
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import (
    load_model_and_data,
    maybe_launch_viewer,
    pause_viewer_at_end,
    sync_viewer,
    viewer_clock,
    viewer_is_running,
)
from mclab.sim.one_dof import configure_slider_plant, slider_state
from mclab.sim.plotting import PlotSelection, save_time_series_plots, select_plot_specs
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
    show_viewer_ui: bool = True,
    plot_selection: PlotSelection = None,
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

    key_force = KeyForcePulse(config)
    viewer_handle = maybe_launch_viewer(
        mujoco,
        model,
        data,
        enabled=viewer and not headless,
        key_callback=key_force.key_callback if key_force.enabled else None,
        show_ui=show_viewer_ui,
    )
    interaction_panel = (
        maybe_start_interaction_panel(key_force, title="MCLab Lab03 Interaction")
        if viewer and not headless
        else None
    )
    wall_start = viewer_clock()
    sim_start = float(data.time)
    completed = False
    try:
        while data.time < sim_time:
            if not viewer_is_running(viewer_handle):
                break
            key_force.update_time(float(data.time))
            position, velocity, _ = slider_state(data, handles)
            target = trajectory.evaluate(float(data.time))
            feedback = kp * (target.position - position) + kd * (target.velocity - velocity)
            feedforward = feedforward_mass * target.acceleration if use_feedforward else 0.0
            control_force = _clip(feedback + feedforward, lower_limit, upper_limit)
            manual_force = key_force.value(float(data.time))
            total_force = control_force + manual_force

            data.ctrl[handles.actuator_id] = total_force
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
                manual_force=manual_force,
                total_force=total_force,
                current_proxy=total_force / kt,
            )
        completed = True
    finally:
        if interaction_panel is not None:
            interaction_panel.close()
        if viewer_handle is not None:
            if completed:
                pause_viewer_at_end(viewer_handle, enabled=pause_at_end)
            viewer_handle.close()

    summary = _summary(logger.rows)
    output_path = logger.save(summary=summary, notes=_notes(config))
    if plot:
        _save_plots(output_path, logger.rows, plot_selection or config.get("plots"))
    return resolve_project_path(output_path)


def _save_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    specs = [
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
        ("torque.png", "Control Effort", "force / torque proxy", ["control_force", "manual_force", "total_force"]),
        ("current_proxy.png", "Current Proxy", "current proxy", ["current_proxy"]),
        ("error.png", "Tracking Error", "error [m]", ["position_error"]),
    ]
    presets = {
        "essential": ["position", "velocity", "torque", "error"],
        "profile": ["position", "velocity", "acceleration", "jerk"],
        "control": ["position", "torque", "current_proxy", "error"],
    }
    save_time_series_plots(output_path, rows, select_plot_specs(specs, selection, presets=presets))


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
