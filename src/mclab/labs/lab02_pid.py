"""PID control lab."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from random import Random
from typing import Any

from mclab.analysis.metrics import step_response_metrics
from mclab.config import resolve_project_path
from mclab.controllers.pid import PIDController
from mclab.learning_guides import guide_for_config
from mclab.sim.interaction import (
    InteractionLog,
    KeyForcePulse,
    LiveStatus,
    LiveTuning,
    SliderSpec,
    StatusSpec,
    maybe_start_interaction_panel,
)
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import (
    load_model_and_data,
    maybe_launch_viewer,
    pause_viewer_at_end,
    sync_viewer,
    viewer_clock,
    viewer_is_running,
)
from mclab.sim.one_dof import configure_slider_plant, slider_state, update_slider_viewer_guides
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
    show_viewer_ui: bool = False,
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
    output_limit_value = max(abs(limit) for limit in (output_min, output_max) if limit is not None) if output_limit else 80.0
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
    viewer_guides_enabled = bool(dict(config.get("viewer_guides", {})).get("enabled", True))

    interaction_log = InteractionLog()
    key_force = KeyForcePulse(config, event_log=interaction_log)
    run_guide = guide_for_config(config_path=str(config_path or ""), lab_name=lab_name)
    live_tuning = _live_tuning(config, pid_config, output_limit_value, interaction_log)
    live_status = LiveStatus(
        [
            StatusSpec("target", "Target [m]"),
            StatusSpec("position", "Position [m]"),
            StatusSpec("error", "Error [m]"),
            StatusSpec("control", "PID force [N]"),
            StatusSpec("manual", "Disturbance [N]"),
        ]
    )
    viewer_handle = maybe_launch_viewer(
        mujoco,
        model,
        data,
        enabled=viewer and not headless,
        key_callback=key_force.key_callback if key_force.enabled else None,
        show_ui=show_viewer_ui,
    )
    interaction_panel = (
        maybe_start_interaction_panel(
            key_force,
            title="MCLab Lab02 Interaction",
            tuning=live_tuning,
            status=live_status,
            guide=run_guide,
            event_log=interaction_log,
        )
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
            interaction_log.set_time(float(data.time))
            key_force.update_time(float(data.time))
            position, velocity, _ = slider_state(data, handles)
            measured_position = position + (random.gauss(0.0, noise_std) if noise_std > 0.0 else 0.0)
            measurement_error = measured_position - position
            target_state = target.evaluate(float(data.time))
            controller.kp = live_tuning.value("kp", controller.kp)
            controller.ki = live_tuning.value("ki", controller.ki)
            controller.kd = live_tuning.value("kd", controller.kd)
            live_output_limit = abs(live_tuning.value("output_limit", output_limit_value))
            controller.output_min = -live_output_limit
            controller.output_max = live_output_limit
            target_position = live_tuning.value("target_position", target_state.position)
            command = controller.compute(
                setpoint=target_position,
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

            position, velocity, acceleration = slider_state(data, handles)
            live_status.set_values(
                target=target_position,
                position=position,
                error=target_position - position,
                control=applied_force,
                manual=manual_force,
            )
            logger.record(
                time=float(data.time),
                position=position,
                measured_position=measured_position,
                measurement_error=measurement_error,
                velocity=velocity,
                acceleration=acceleration,
                target_position=target_position,
                target_velocity=target_state.velocity,
                position_error=target_position - position,
                control_force=applied_force,
                manual_force=manual_force,
                total_force=total_force,
                tuned_kp=controller.kp,
                tuned_ki=controller.ki,
                tuned_kd=controller.kd,
                tuned_output_limit=live_output_limit,
                control_unsaturated=command.unsaturated_value,
                pid_p=command.proportional,
                pid_i=command.integral,
                pid_d=command.derivative,
                saturated=float(command.saturated),
            )
            update_slider_viewer_guides(
                mujoco,
                viewer_handle,
                position=position,
                force=total_force,
                target_position=target_position,
                enabled=viewer_guides_enabled,
            )
            sync_viewer(
                viewer_handle,
                data,
                realtime=realtime,
                wall_start=wall_start,
                sim_start=sim_start,
            )
        completed = True
    finally:
        if interaction_panel is not None:
            interaction_panel.close()
        if viewer_handle is not None:
            if completed:
                pause_viewer_at_end(viewer_handle, enabled=pause_at_end)
            viewer_handle.close()

    summary = {**step_response_metrics(logger.rows), **_summary(logger.rows, config), **interaction_log.summary()}
    events = interaction_log.events()
    output_path = logger.save_with_artifacts(
        summary=summary,
        notes=_notes(config),
        interaction_events=events if events else None,
    )
    if plot:
        _save_plots(output_path, logger.rows, plot_selection or config.get("plots"))
    return resolve_project_path(output_path)


def _live_tuning(
    config: dict[str, Any],
    pid_config: dict[str, Any],
    output_limit: float,
    interaction_log: InteractionLog | None = None,
) -> LiveTuning:
    interaction = dict(config.get("interaction", {}))
    if not bool(interaction.get("live_tuning", False)):
        return LiveTuning([])
    target = dict(config.get("target", {}))
    return LiveTuning(
        [
            SliderSpec("target_position", "Target position [m]", -0.8, 0.8, float(target.get("end", 0.0)), 0.01),
            SliderSpec("kp", "Kp", 0.0, 180.0, float(pid_config.get("kp", 40.0)), 1.0),
            SliderSpec("ki", "Ki", 0.0, 20.0, float(pid_config.get("ki", 0.0)), 0.1),
            SliderSpec("kd", "Kd", 0.0, 40.0, float(pid_config.get("kd", 4.0)), 0.5),
            SliderSpec("output_limit", "Force limit [N]", 5.0, 200.0, output_limit, 1.0),
        ],
        event_log=interaction_log,
    )


def _save_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    specs = [
        (
            "position.png",
            "PID Position Tracking",
            "position [m]",
            ["position", "measured_position", "target_position"],
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


def _summary(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {}
    measurement_errors = [
        abs(float(row["measurement_error"]))
        for row in rows
        if "measurement_error" in row
    ]
    return {
        "measurement_noise_std": float(config.get("measurement_noise_std", 0.0)),
        "control_delay": float(config.get("control_delay", 0.0)),
        "max_abs_measurement_error": max(measurement_errors) if measurement_errors else 0.0,
    }


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
