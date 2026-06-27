"""Mass-spring-damper lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.config import resolve_project_path
from mclab.sim.interaction import (
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
from mclab.sim.one_dof import configure_slider_plant, force_input_at, mechanical_energy, slider_state
from mclab.sim.plotting import PlotSelection, save_time_series_plots, select_plot_specs


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
    damping = float(config.get("damping", 0.0))

    key_force = KeyForcePulse(config)
    live_tuning = _live_tuning(config)
    live_status = LiveStatus(
        [
            StatusSpec("position", "Position [m]"),
            StatusSpec("velocity", "Velocity [m/s]"),
            StatusSpec("force", "Applied force [N]"),
            StatusSpec("energy", "Total energy [J]"),
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
            title="MCLab Lab01 Interaction",
            tuning=live_tuning,
            status=live_status,
        )
        if viewer and not headless
        else None
    )
    wall_start = viewer_clock()
    sim_start = float(data.time)
    completed = False
    current_mass = mass
    try:
        while data.time < sim_time:
            if not viewer_is_running(viewer_handle):
                break
            mass = live_tuning.value("mass", mass)
            damping = live_tuning.value("damping", damping)
            stiffness = live_tuning.value("stiffness", stiffness)
            if abs(mass - current_mass) > 1e-9:
                model.body_mass[handles.body_id] = mass
                if hasattr(mujoco, "mj_setConst"):
                    mujoco.mj_setConst(model, data)
                current_mass = mass
            model.dof_damping[handles.dof_adr] = damping
            model.jnt_stiffness[handles.joint_id] = stiffness
            key_force.update_time(float(data.time))
            input_force = force_input_at(float(data.time), force_config)
            manual_force = key_force.value(float(data.time))
            force = input_force + manual_force
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
            live_status.set_values(position=position, velocity=velocity, force=force, energy=total)
            logger.record(
                time=float(data.time),
                position=position,
                velocity=velocity,
                acceleration=acceleration,
                control_force=force,
                external_force=input_force,
                manual_force=manual_force,
                tuned_mass=mass,
                tuned_damping=damping,
                tuned_stiffness=stiffness,
                kinetic_energy=kinetic,
                potential_energy=potential,
                total_energy=total,
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


def _live_tuning(config: dict[str, Any]) -> LiveTuning:
    interaction = dict(config.get("interaction", {}))
    if not bool(interaction.get("live_tuning", False)):
        return LiveTuning([])
    return LiveTuning(
        [
            SliderSpec("mass", "Mass [kg]", 0.2, 5.0, float(config.get("mass", 1.0)), 0.1),
            SliderSpec("damping", "Damping [N s/m]", 0.0, 12.0, float(config.get("damping", 0.0)), 0.1),
            SliderSpec("stiffness", "Stiffness [N/m]", 0.0, 120.0, float(config.get("stiffness", 0.0)), 1.0),
        ]
    )


def _save_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    specs = [
        ("position.png", "Mass-Spring-Damper Position", "position [m]", ["position"]),
        ("velocity.png", "Mass-Spring-Damper Velocity", "velocity [m/s]", ["velocity"]),
        (
            "acceleration.png",
            "Mass-Spring-Damper Acceleration",
            "acceleration [m/s^2]",
            ["acceleration"],
        ),
        ("force.png", "Applied Force", "force [N]", ["control_force", "external_force", "manual_force"]),
        (
            "energy.png",
            "Mechanical Energy",
            "energy [J]",
            ["kinetic_energy", "potential_energy", "total_energy"],
        ),
    ]
    presets = {
        "essential": ["position", "velocity", "force"],
        "energy": ["position", "energy"],
    }
    save_time_series_plots(output_path, rows, select_plot_specs(specs, selection, presets=presets))


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
