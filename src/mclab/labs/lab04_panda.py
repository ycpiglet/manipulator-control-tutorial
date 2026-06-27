"""6/7DOF manipulator lab using the MuJoCo Menagerie Panda model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.config import resolve_project_path
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import load_model_and_data, maybe_launch_viewer
from mclab.sim.plotting import save_time_series_plots
from mclab.trajectories import build_trajectory


ARM_JOINT_NAMES = [f"joint{i}" for i in range(1, 8)]
ARM_ACTUATOR_NAMES = [f"actuator{i}" for i in range(1, 8)]
DEFAULT_HOME_Q = [0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853]
DEFAULT_FINGER_Q = [0.04, 0.04]
DEFAULT_GRIPPER_CTRL = 255.0


def run(
    config: dict[str, Any],
    *,
    config_path: Path | None = None,
    output_dir: Path | None = None,
    plot: bool = False,
    viewer: bool = False,
    headless: bool = False,
    seed: int | None = None,
) -> Path:
    del seed
    lab_name = "lab04_panda"
    model_path = config.get(
        "model_path",
        "third_party/mujoco_menagerie/franka_emika_panda/scene.xml",
    )
    mujoco, model, data = load_model_and_data(model_path)
    _configure_timestep(model, config)

    handles = _build_handles(mujoco, model, config)
    logger = RunLogger(lab_name, config, config_path=config_path, output_dir=output_dir)

    sim_time = float(config.get("sim_time", 5.0))
    home_q = _float_list(config.get("home_q", DEFAULT_HOME_Q), 7)
    finger_q = _float_list(config.get("finger_q", DEFAULT_FINGER_Q), 2)
    kt = float(config.get("torque_constant", 1.0))
    mode = str(config.get("mode", "joint_trajectory")).lower()

    _set_initial_state(data, home_q, finger_q)
    mujoco.mj_forward(model, data)

    trajectory_config = _trajectory_config(config, home_q)
    trajectory = build_trajectory(trajectory_config)
    controlled_joint_index = int(config.get("controlled_joint_index", 3))
    if not 0 <= controlled_joint_index < 7:
        raise ValueError("controlled_joint_index must be in [0, 6]")

    viewer_handle = maybe_launch_viewer(mujoco, model, data, enabled=viewer and not headless)
    try:
        while data.time < sim_time:
            target_q = home_q.copy()
            target = trajectory.evaluate(float(data.time))
            target_q[controlled_joint_index] = target.position

            ee_position, ee_velocity, jacobian = _end_effector_state(mujoco, model, data, handles)
            wall_force = [0.0, 0.0, 0.0]
            if mode in {"impedance_wall", "virtual_wall", "wall"}:
                wall_force = _virtual_wall_force(ee_position, ee_velocity, dict(config.get("virtual_wall", {})))
                target_q = _apply_wall_target_offset(
                    target_q,
                    jacobian,
                    ee_position,
                    wall_force,
                    config,
                )

            target_q = _clip_to_ctrl_range(model, handles["actuator_ids"], target_q)
            _apply_arm_control(data, handles["actuator_ids"], target_q, config)
            mujoco.mj_step(model, data)
            if viewer_handle is not None:
                viewer_handle.sync()

            q = [float(data.qpos[index]) for index in handles["qpos_indices"]]
            qdot = [float(data.qvel[index]) for index in handles["dof_indices"]]
            ee_position, ee_velocity, _ = _end_effector_state(mujoco, model, data, handles)
            actuator_force = [float(data.actuator_force[index]) for index in handles["actuator_ids"]]
            current_proxy = [force / kt for force in actuator_force]
            position_errors = [target_q[index] - q[index] for index in range(7)]
            wall_penetration = max(
                0.0,
                ee_position[0] - float(config.get("virtual_wall", {}).get("wall_x", 10.0)),
            )
            logger.record(
                time=float(data.time),
                q=q,
                qdot=qdot,
                target_q=target_q,
                ctrl=[float(data.ctrl[index]) for index in handles["actuator_ids"]],
                tau_cmd=actuator_force,
                current_proxy=current_proxy,
                x_ee=ee_position,
                xdot_ee=ee_velocity,
                position_error=position_errors,
                error_norm=_norm(position_errors),
                force_virtual=wall_force,
                wall_penetration=wall_penetration,
                wall_penetration_cm=100.0 * wall_penetration,
            )
    finally:
        if viewer_handle is not None:
            viewer_handle.close()

    summary = _summary(logger.rows)
    output_path = logger.save(summary=summary, notes=_notes(config))
    if plot:
        _save_plots(output_path, logger.rows)
    return resolve_project_path(output_path)


def _configure_timestep(model: Any, config: dict[str, Any]) -> None:
    if "dt" in config:
        model.opt.timestep = float(config["dt"])


def _build_handles(mujoco: Any, model: Any, config: dict[str, Any]) -> dict[str, Any]:
    joint_names = list(config.get("joint_names", ARM_JOINT_NAMES))
    actuator_names = list(config.get("actuator_names", ARM_ACTUATOR_NAMES))
    ee_body_name = str(config.get("end_effector_body", "hand"))

    joint_ids = [_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in joint_names]
    actuator_ids = [_id(mujoco, model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in actuator_names]
    ee_body_id = _id(mujoco, model, mujoco.mjtObj.mjOBJ_BODY, ee_body_name)
    return {
        "joint_ids": joint_ids,
        "actuator_ids": actuator_ids,
        "qpos_indices": [int(model.jnt_qposadr[index]) for index in joint_ids],
        "dof_indices": [int(model.jnt_dofadr[index]) for index in joint_ids],
        "ee_body_id": ee_body_id,
    }


def _id(mujoco: Any, model: Any, kind: Any, name: str) -> int:
    item_id = int(mujoco.mj_name2id(model, kind, name))
    if item_id < 0:
        raise RuntimeError(f"MuJoCo object not found: {name}")
    return item_id


def _set_initial_state(data: Any, home_q: list[float], finger_q: list[float]) -> None:
    for index, value in enumerate(home_q):
        data.qpos[index] = value
    data.qpos[7] = finger_q[0]
    data.qpos[8] = finger_q[1]
    for index, value in enumerate(home_q):
        data.ctrl[index] = value
    data.ctrl[7] = DEFAULT_GRIPPER_CTRL


def _trajectory_config(config: dict[str, Any], home_q: list[float]) -> dict[str, Any]:
    trajectory = dict(config.get("trajectory", {}))
    controlled_joint_index = int(config.get("controlled_joint_index", 3))
    start = float(trajectory.get("start", home_q[controlled_joint_index]))
    end = float(trajectory.get("end", start + float(config.get("joint_delta", 0.2))))
    trajectory.setdefault("type", "minimum_jerk")
    trajectory["start"] = start
    trajectory["end"] = end
    trajectory.setdefault("duration", 2.0)
    trajectory.setdefault("start_time", 0.5)
    return trajectory


def _end_effector_state(mujoco: Any, model: Any, data: Any, handles: dict[str, Any]) -> tuple[list[float], list[float], Any]:
    import numpy as np

    jacp = np.zeros((3, model.nv), dtype=float)
    jacr = np.zeros((3, model.nv), dtype=float)
    mujoco.mj_jacBody(model, data, jacp, jacr, handles["ee_body_id"])
    velocity = jacp @ data.qvel
    position = data.xpos[handles["ee_body_id"]]
    arm_jacobian = jacp[:, handles["dof_indices"]].copy()
    return [float(value) for value in position], [float(value) for value in velocity], arm_jacobian


def _virtual_wall_force(
    ee_position: list[float],
    ee_velocity: list[float],
    wall_config: dict[str, Any],
) -> list[float]:
    wall_x = float(wall_config.get("wall_x", 0.52))
    stiffness = float(wall_config.get("stiffness", 250.0))
    damping = float(wall_config.get("damping", 12.0))
    penetration = ee_position[0] - wall_x
    if penetration <= 0.0:
        return [0.0, 0.0, 0.0]
    force_x = -stiffness * penetration - damping * max(0.0, ee_velocity[0])
    return [force_x, 0.0, 0.0]


def _apply_wall_target_offset(
    target_q: list[float],
    jacobian: Any,
    ee_position: list[float],
    wall_force: list[float],
    config: dict[str, Any],
) -> list[float]:
    import numpy as np

    if not any(abs(force) > 1e-12 for force in wall_force):
        return target_q
    wall_config = dict(config.get("virtual_wall", {}))
    wall_x = float(wall_config.get("wall_x", 0.52))
    penetration = max(0.0, ee_position[0] - wall_x)
    cartesian_gain = float(wall_config.get("cartesian_retreat_gain", 1.2))
    max_cartesian_retreat = float(wall_config.get("max_cartesian_retreat", 0.04))
    desired_task_offset = np.asarray(
        [-min(max_cartesian_retreat, penetration * cartesian_gain), 0.0, 0.0],
        dtype=float,
    )
    damping = float(wall_config.get("damped_least_squares", 0.08))
    task_matrix = jacobian @ jacobian.T + (damping**2) * np.eye(3)
    joint_offset = jacobian.T @ np.linalg.solve(task_matrix, desired_task_offset)

    scale = float(config.get("wall_target_offset_scale", 1.0))
    max_offset = float(config.get("wall_target_max_offset", 0.18))
    adjusted = target_q.copy()
    for index, delta_q in enumerate(joint_offset):
        offset = scale * float(delta_q)
        adjusted[index] += max(-max_offset, min(max_offset, offset))
    return adjusted


def _clip_to_ctrl_range(model: Any, actuator_ids: list[int], target_q: list[float]) -> list[float]:
    clipped = target_q.copy()
    for index, actuator_id in enumerate(actuator_ids):
        low, high = model.actuator_ctrlrange[actuator_id]
        clipped[index] = max(float(low), min(float(high), clipped[index]))
    return clipped


def _apply_arm_control(data: Any, actuator_ids: list[int], target_q: list[float], config: dict[str, Any]) -> None:
    for actuator_id, value in zip(actuator_ids, target_q):
        data.ctrl[actuator_id] = value
    gripper_ctrl = float(config.get("gripper_ctrl", DEFAULT_GRIPPER_CTRL))
    if len(data.ctrl) > 7:
        data.ctrl[7] = gripper_ctrl


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return {
        "max_joint_error_norm": max(float(row["error_norm"]) for row in rows),
        "final_joint_error_norm": rows[-1]["error_norm"],
        "max_abs_tau_cmd": max(
            abs(float(value))
            for row in rows
            for key, value in row.items()
            if key.startswith("tau_cmd_")
        ),
        "max_wall_penetration": max(float(row.get("wall_penetration", 0.0)) for row in rows),
        "final_x_ee_0": rows[-1].get("x_ee_0"),
        "final_x_ee_1": rows[-1].get("x_ee_1"),
        "final_x_ee_2": rows[-1].get("x_ee_2"),
    }


def _save_plots(output_path: Path, rows: list[dict[str, Any]]) -> None:
    q_keys = [f"q_{index}" for index in range(7)]
    target_keys = [f"target_q_{index}" for index in range(7)]
    tau_keys = [f"tau_cmd_{index}" for index in range(7)]
    current_keys = [f"current_proxy_{index}" for index in range(7)]
    save_time_series_plots(
        output_path,
        rows,
        [
            ("position.png", "Panda Joint Positions", "joint position [rad]", q_keys + target_keys),
            ("velocity.png", "Panda Joint Velocities", "joint velocity [rad/s]", [f"qdot_{index}" for index in range(7)]),
            ("torque.png", "Panda Actuator Force", "force / torque proxy", tau_keys),
            ("current_proxy.png", "Panda Current Proxy", "current proxy", current_keys),
            ("end_effector.png", "End-Effector Position", "position [m]", ["x_ee_0", "x_ee_1", "x_ee_2"]),
            ("error.png", "Joint Tracking Error Norm", "norm [rad]", ["error_norm"]),
            (
                "virtual_wall.png",
                "Virtual Wall Response",
                "force / penetration",
                ["force_virtual_0", "wall_penetration_cm"],
            ),
        ],
    )


def _notes(config: dict[str, Any]) -> str:
    return f"""# Lab04 Panda Manipulator

This lab uses the MuJoCo Menagerie Franka Emika Panda model.

The Menagerie model is position-actuated, so `ctrl` is a target joint position.
The logged `tau_cmd` and `current_proxy` come from MuJoCo actuator force output.

- mode: {config.get("mode", "joint_trajectory")}
- model_path: {config.get("model_path", "third_party/mujoco_menagerie/franka_emika_panda/scene.xml")}
"""


def _float_list(values: Any, expected_length: int) -> list[float]:
    result = [float(value) for value in values]
    if len(result) != expected_length:
        raise ValueError(f"Expected {expected_length} values, got {len(result)}")
    return result


def _norm(values: list[float]) -> float:
    return sum(value * value for value in values) ** 0.5
