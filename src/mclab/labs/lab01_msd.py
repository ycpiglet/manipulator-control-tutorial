"""Mass-spring-damper lab."""

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
from mclab.sim.one_dof import configure_slider_plant, force_input_at, mechanical_energy, slider_state
from mclab.sim.plotting import save_time_series_plots


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
    lab_name = "lab01_msd"
    model_path = config.get("model_path", "models/lab01_msd/scene.xml")
    mujoco, model, data = load_model_and_data(model_path)
    handles = configure_slider_plant(mujoco, model, data, config)
    logger = RunLogger(lab_name, config, config_path=config_path, output_dir=output_dir)

    sim_time = float(config.get("sim_time", 5.0))
    mass = float(config.get("mass", 1.0))
    stiffness = float(config.get("stiffness", 50.0))
    spring_reference = float(config.get("spring_reference", 0.0))
    force_config = config.get("force_input", config.get("external_force", 0.0))

    viewer_handle = maybe_launch_viewer(mujoco, model, data, enabled=viewer and not headless)
    wall_start = viewer_clock()
    sim_start = float(data.time)
    completed = False
    try:
        while data.time < sim_time:
            force = force_input_at(float(data.time), force_config)
            data.ctrl[handles.actuator_id] = force
            mujoco.mj_step(model, data)
            sync_viewer(
                viewer_handle,
                data,
                realtime=realtime,
                wall_start=wall_start,
                sim_start=sim_start,
            )

            position, velocity, acceleration = slider_state(data, handles)
            kinetic, potential, total = mechanical_energy(
                position=position,
                velocity=velocity,
                mass=mass,
                stiffness=stiffness,
                spring_reference=spring_reference,
            )
            logger.record(
                time=float(data.time),
                position=position,
                velocity=velocity,
                acceleration=acceleration,
                control_force=force,
                external_force=force,
                kinetic_energy=kinetic,
                potential_energy=potential,
                total_energy=total,
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
                ("position.png", "Mass-Spring-Damper Position", "position [m]", ["position"]),
                ("velocity.png", "Mass-Spring-Damper Velocity", "velocity [m/s]", ["velocity"]),
                (
                    "acceleration.png",
                    "Mass-Spring-Damper Acceleration",
                    "acceleration [m/s^2]",
                    ["acceleration"],
                ),
                ("force.png", "Applied Force", "force [N]", ["external_force"]),
                (
                    "energy.png",
                    "Mechanical Energy",
                    "energy [J]",
                    ["kinetic_energy", "potential_energy", "total_energy"],
                ),
            ],
        )
    return resolve_project_path(output_path)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    positions = [abs(float(row["position"])) for row in rows]
    return {
        "max_abs_position": max(positions),
        "final_position": rows[-1]["position"],
        "final_velocity": rows[-1]["velocity"],
        "final_total_energy": rows[-1]["total_energy"],
    }


def _notes(config: dict[str, Any]) -> str:
    return f"""# Lab01 Mass-Spring-Damper

MuJoCo slide-joint plant for:

```text
m x_ddot + c x_dot + k x = F
```

- mass: {config.get("mass", 1.0)}
- damping: {config.get("damping", 0.0)}
- stiffness: {config.get("stiffness", 0.0)}
"""
