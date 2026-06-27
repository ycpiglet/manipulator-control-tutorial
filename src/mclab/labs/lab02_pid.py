"""PID control lab."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from random import Random
from typing import Any

from mclab.analysis.metrics import step_response_metrics
from mclab.config import resolve_project_path
from mclab.controllers.pid import PIDController
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
    plot_selection: PlotSelection = None,
    seed: int | None = None,
) -> Path:
    lab_name = "lab02_pid"
    model_path = config.get("model_path", "models/lab02_pid/scene.xml")
    mujoco, model, data = load_model_and_data(model_path)
    handles = configure_slider_plant(mujoco, model, data, config)
    logger = RunLogger(lab_name, config, config_path=config_path, output_dir=output_dir)

    dt = float(config.get("dt", model.opt.timestep))
    sim_time = float(config.get("sim_time", 5.0))
    pid_config = dict(config.get("controller", {}))
    output_limit = pid_config.get("output_limit", config.get("force_limit"))
    output_min, output_max = _limits(output_limit)
    controller = PIDController(
        kp=float(pid_config.get("kp", 40.0)),
        ki=float(pid_config.get("ki", 0.0)),
        kd=float(pid_config.get("kd", 4.0)),
        dt=dt,
        output_min=output_min,
        output_max=output_max,
        integral_min=_optional_float(pid_config.get("integral_min")),
        integral_max=_optional_float(pid_config.get("integral_max")),
        anti_windup=bool(pid_config.get("anti_windup", True)),
    )
    target = build_trajectory(dict(config.get("target", {"type": "step", "start": 0.0, "end": 0.2})))

    random = Random(seed)
    noise_std = float(config.get("measurement_noise_std", 0.0))
    delay_steps = max(0, int(round(float(config.get("control_delay", 0.0)) / dt)))
    delay_buffer: deque[float] = deque([0.0] * delay_steps, maxlen=delay_steps)

    key_force = KeyForcePulse(config)
    viewer_handle = maybe_launch_viewer(
        mujoco,
        model,
        data,
        enabled=viewer and not headless,
        key_callback=key_force.key_callback if key_force.enabled else None,
    )
    interaction_panel = (
        maybe_start_interaction_panel(key_force, title="MCLab Lab02 Interaction")
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
            measured_position = position + (random.gauss(0.0, noise_std) if noise_std > 0.0 else 0.0)
            target_state = target.evaluate(float(data.time))
            command = controller.compute(
                setpoint=target_state.position,
                measurement=measured_position,
                measurement_rate=velocity,
            )

            if delay_steps:
                delay_buffer.append(command.value)
                applied_force = delay_buffer[0]
            else:
                applied_force = command.value

            manual_force = key_force.value(float(data.time))
            total_force = applied_force + manual_force
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
                measured_position=measured_position,
                velocity=velocity,
                acceleration=acceleration,
                target_position=target_state.position,
                target_velocity=target_state.velocity,
                position_error=target_state.position - position,
                control_force=applied_force,
                manual_force=manual_force,
                total_force=total_force,
                control_unsaturated=command.unsaturated_value,
                pid_p=command.proportional,
                pid_i=command.integral,
                pid_d=command.derivative,
                saturated=float(command.saturated),
            )
        completed = True
    finally:
        if interaction_panel is not None:
            interaction_panel.close()
        if viewer_handle is not None:
            if completed:
                pause_viewer_at_end(viewer_handle, enabled=pause_at_end)
            viewer_handle.close()

    summary = step_response_metrics(logger.rows)
    output_path = logger.save(summary=summary, notes=_notes(config))
    if plot:
        _save_plots(output_path, logger.rows, plot_selection or config.get("plots"))
    return resolve_project_path(output_path)


def _save_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    specs = [
        (
            "position.png",
            "PID Position Tracking",
            "position [m]",
            ["position", "target_position"],
        ),
        ("velocity.png", "Plant Velocity", "velocity [m/s]", ["velocity"]),
        ("acceleration.png", "Plant Acceleration", "acceleration [m/s^2]", ["acceleration"]),
        (
            "control_force.png",
            "PID Control Effort",
            "force [N]",
            ["control_force", "manual_force", "total_force", "control_unsaturated"],
        ),
        (
            "pid_terms.png",
            "PID Terms",
            "force contribution [N]",
            ["pid_p", "pid_i", "pid_d"],
        ),
        ("error.png", "Tracking Error", "error [m]", ["position_error"]),
    ]
    presets = {
        "essential": ["position", "control_force", "error"],
        "pid": ["position", "control_force", "pid_terms", "error"],
    }
    save_time_series_plots(output_path, rows, select_plot_specs(specs, selection, presets=presets))


def _limits(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _optional_float(value[0]), _optional_float(value[1])
    magnitude = abs(float(value))
    return -magnitude, magnitude


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _notes(config: dict[str, Any]) -> str:
    controller = config.get("controller", {})
    return f"""# Lab02 PID Control

Scalar PID control on the same MuJoCo slide-joint plant used by Lab01.

```text
u = Kp * e + Ki * integral(e) + Kd * e_dot
```

- Kp: {controller.get("kp", 40.0)}
- Ki: {controller.get("ki", 0.0)}
- Kd: {controller.get("kd", 4.0)}
- anti_windup: {controller.get("anti_windup", True)}
"""
