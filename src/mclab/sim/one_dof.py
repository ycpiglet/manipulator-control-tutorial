"""Helpers for the shared 1D slide-joint MuJoCo plant."""

from __future__ import annotations

from dataclasses import dataclass
from math import sin, tau
from typing import Any

from mclab.sim.mujoco_utils import add_viewer_box, reset_viewer_overlays


@dataclass(frozen=True)
class SliderHandles:
    joint_id: int
    body_id: int
    actuator_id: int
    qpos_adr: int
    dof_adr: int


def configure_slider_plant(mujoco: Any, model: Any, data: Any, config: dict[str, Any]) -> SliderHandles:
    dt = float(config.get("dt", config.get("timestep", model.opt.timestep)))
    model.opt.timestep = dt

    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "slider")
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "block")
    actuator_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "force_x")
    if min(joint_id, body_id, actuator_id) < 0:
        raise RuntimeError("The 1D plant model must define slider, block, and force_x names.")

    qpos_adr = int(model.jnt_qposadr[joint_id])
    dof_adr = int(model.jnt_dofadr[joint_id])

    model.body_mass[body_id] = float(config.get("mass", 1.0))
    model.dof_damping[dof_adr] = float(config.get("damping", 0.0))
    model.jnt_stiffness[joint_id] = float(config.get("stiffness", 0.0))
    if hasattr(model, "qpos_spring"):
        model.qpos_spring[qpos_adr] = float(config.get("spring_reference", 0.0))

    data.qpos[qpos_adr] = float(config.get("initial_position", 0.0))
    data.qvel[dof_adr] = float(config.get("initial_velocity", 0.0))
    mujoco.mj_forward(model, data)
    return SliderHandles(
        joint_id=joint_id,
        body_id=body_id,
        actuator_id=actuator_id,
        qpos_adr=qpos_adr,
        dof_adr=dof_adr,
    )


def reset_slider_plant_state(
    mujoco: Any,
    model: Any,
    data: Any,
    handles: SliderHandles,
    config: dict[str, Any],
    *,
    control_force: float = 0.0,
) -> None:
    data.time = 0.0
    data.qpos[handles.qpos_adr] = float(config.get("initial_position", 0.0))
    data.qvel[handles.dof_adr] = float(config.get("initial_velocity", 0.0))
    data.ctrl[handles.actuator_id] = float(control_force)
    mujoco.mj_forward(model, data)


def force_input_at(t: float, config: dict[str, Any] | float | int | None) -> float:
    if config is None:
        return 0.0
    if isinstance(config, (float, int)):
        return float(config)

    kind = str(config.get("type", "constant")).lower()
    magnitude = float(config.get("magnitude", 0.0))
    start_time = float(config.get("start_time", 0.0))
    end_time = config.get("end_time")
    if t < start_time:
        return 0.0
    if end_time is not None and t > float(end_time):
        return 0.0

    if kind in {"constant", "step"}:
        return magnitude
    if kind == "pulse":
        return magnitude
    if kind == "sine":
        frequency = float(config.get("frequency", 1.0))
        return magnitude * sin(tau * frequency * (t - start_time))
    raise ValueError(f"Unknown force input type: {config.get('type')}")


def slider_state(data: Any, handles: SliderHandles) -> tuple[float, float, float]:
    return (
        float(data.qpos[handles.qpos_adr]),
        float(data.qvel[handles.dof_adr]),
        float(data.qacc[handles.dof_adr]),
    )


def mechanical_energy(
    *,
    position: float,
    velocity: float,
    mass: float,
    stiffness: float,
    spring_reference: float = 0.0,
) -> tuple[float, float, float]:
    kinetic = 0.5 * mass * velocity**2
    potential = 0.5 * stiffness * (position - spring_reference) ** 2
    return kinetic, potential, kinetic + potential


def update_slider_viewer_guides(
    mujoco: Any,
    viewer_handle: Any | None,
    *,
    position: float,
    force: float,
    reference_position: float = 0.0,
    target_position: float | None = None,
    enabled: bool = True,
) -> None:
    if viewer_handle is None:
        return
    reset_viewer_overlays(viewer_handle)
    if not enabled:
        return

    add_viewer_box(
        mujoco,
        viewer_handle,
        [reference_position, -0.11, 0.045],
        half_size=[0.006, 0.025, 0.09],
        rgba=[0.38, 0.43, 0.50, 0.70],
    )
    if target_position is not None:
        add_viewer_box(
            mujoco,
            viewer_handle,
            [target_position, 0.11, 0.045],
            half_size=[0.008, 0.028, 0.10],
            rgba=[0.10, 0.82, 0.28, 0.82],
        )
    if abs(force) > 1e-9:
        length = min(0.22, max(0.035, abs(force) / 450.0))
        direction = 1.0 if force >= 0.0 else -1.0
        add_viewer_box(
            mujoco,
            viewer_handle,
            [position + direction * length, 0.0, 0.095],
            half_size=[length, 0.018, 0.018],
            rgba=[1.0, 0.48, 0.10, 0.84],
        )
