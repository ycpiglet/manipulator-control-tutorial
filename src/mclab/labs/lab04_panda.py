"""6/7DOF manipulator lab using the MuJoCo Menagerie Panda model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.config import resolve_project_path
from mclab.learning_guides import guide_for_config
from mclab.sim.interaction import (
    InteractionLog,
    LiveStatus,
    LiveTuning,
    SliderSpec,
    StatusSpec,
    TargetOffsetControl,
    maybe_start_interaction_panel,
    tuning_presets_from_config,
)
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import (
    add_viewer_box,
    add_viewer_sphere,
    load_model_and_data,
    maybe_launch_viewer,
    pause_viewer_at_end,
    reset_viewer_overlays,
    sync_viewer,
    viewer_clock,
    viewer_is_running,
)
from mclab.sim.plotting import PlotSelection, save_time_series_plots, select_plot_specs
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
    realtime: bool = False,
    pause_at_end: bool = False,
    show_viewer_ui: bool = False,
    plot_selection: PlotSelection = None,
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
    viewer_guides = _viewer_guides(config, mode)

    _set_initial_state(data, home_q, finger_q)
    mujoco.mj_forward(model, data)
    initial_ee_position, _, _ = _end_effector_state(mujoco, model, data, handles)

    trajectory_config = _trajectory_config(config, home_q)
    trajectory = build_trajectory(trajectory_config)
    controlled_joint_index = int(config.get("controlled_joint_index", 3))
    if not 0 <= controlled_joint_index < 7:
        raise ValueError("controlled_joint_index must be in [0, 6]")

    interaction_log = InteractionLog()
    target_offset = TargetOffsetControl(config, event_log=interaction_log)
    run_guide = guide_for_config(config_path=str(config_path or ""), lab_name=lab_name)
    live_tuning = _live_tuning(config, interaction_log)
    live_status = LiveStatus(_live_status_specs(mode))
    viewer_handle = maybe_launch_viewer(
        mujoco,
        model,
        data,
        enabled=viewer and not headless,
        key_callback=target_offset.key_callback if target_offset.enabled else None,
        show_ui=show_viewer_ui,
    )
    interaction_panel = (
        maybe_start_interaction_panel(
            target_offset,
            title="MCLab Lab04 Interaction",
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
            target_q = home_q.copy()
            target = trajectory.evaluate(float(data.time))
            button_joint_offset = target_offset.value()
            tuned_joint_offset = live_tuning.value("joint_target_offset", 0.0)
            target_q[controlled_joint_index] = target.position + button_joint_offset + tuned_joint_offset

            ee_position, ee_velocity, jacobian = _end_effector_state(mujoco, model, data, handles)
            wall_force = [0.0, 0.0, 0.0]
            wall_spring_force = [0.0, 0.0, 0.0]
            wall_damping_force = [0.0, 0.0, 0.0]
            wall_retreat = 0.0
            target_x_ee = ee_position
            cartesian_error = [0.0, 0.0, 0.0]
            wall_config = _wall_config(config, live_tuning)
            tracks_cartesian_target = mode in {"cartesian_reach", "task_space", "ee_reach"}
            if mode in {"cartesian_reach", "task_space", "ee_reach"}:
                q_before = [float(data.qpos[index]) for index in handles["qpos_indices"]]
                target_x_ee = _cartesian_target_position(
                    config,
                    live_tuning,
                    initial_ee_position,
                    float(target.position),
                )
                cartesian_error = [target_x_ee[index] - ee_position[index] for index in range(3)]
                target_q = _apply_cartesian_target_offset(
                    q_before,
                    jacobian,
                    cartesian_error,
                    config,
                    live_tuning,
                )
            if mode in {"impedance_wall", "virtual_wall", "wall"}:
                if _wall_cartesian_target_enabled(config):
                    tracks_cartesian_target = True
                    target_x_ee = _cartesian_target_position(
                        config,
                        live_tuning,
                        initial_ee_position,
                        1.0,
                    )
                    cartesian_error = [target_x_ee[index] - ee_position[index] for index in range(3)]
                    target_q = _apply_cartesian_target_offset(
                        target_q,
                        jacobian,
                        cartesian_error,
                        config,
                        live_tuning,
                    )
                wall_force, wall_spring_force, wall_damping_force = _virtual_wall_force_components(
                    ee_position,
                    ee_velocity,
                    wall_config,
                )
                wall_retreat = _wall_retreat_distance(ee_position, wall_force, wall_config)
                target_q = _apply_wall_target_offset(
                    target_q,
                    jacobian,
                    ee_position,
                    wall_force,
                    config,
                    wall_config,
                )

            target_q = _clip_to_ctrl_range(model, handles["actuator_ids"], target_q)
            _apply_arm_control(data, handles["actuator_ids"], target_q, config)
            mujoco.mj_step(model, data)

            q = [float(data.qpos[index]) for index in handles["qpos_indices"]]
            qdot = [float(data.qvel[index]) for index in handles["dof_indices"]]
            ee_position, ee_velocity, _ = _end_effector_state(mujoco, model, data, handles)
            actuator_force = [float(data.actuator_force[index]) for index in handles["actuator_ids"]]
            current_proxy = [force / kt for force in actuator_force]
            position_errors = [target_q[index] - q[index] for index in range(7)]
            wall_penetration = max(
                0.0,
                ee_position[0] - float(wall_config.get("wall_x", 10.0)),
            )
            error_norm = _norm(position_errors)
            if tracks_cartesian_target:
                cartesian_error = [target_x_ee[index] - ee_position[index] for index in range(3)]
            else:
                target_x_ee = ee_position
                cartesian_error = [0.0, 0.0, 0.0]
            cartesian_error_norm = _norm(cartesian_error)
            live_status.set_values(
                joint_offset=button_joint_offset + tuned_joint_offset,
                error_norm=error_norm,
                ee_x=ee_position[0],
                target_x=target_x_ee[0],
                cartesian_error_cm=100.0 * cartesian_error_norm,
                wall_x=wall_config.get("wall_x"),
                target_wall_gap_cm=100.0 * (target_x_ee[0] - float(wall_config.get("wall_x", target_x_ee[0]))),
                wall_penetration_cm=100.0 * wall_penetration,
                wall_force_x=wall_force[0],
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
                target_x_ee=target_x_ee,
                cartesian_error=cartesian_error,
                cartesian_error_norm=cartesian_error_norm,
                cartesian_error_cm=100.0 * cartesian_error_norm,
                position_error=position_errors,
                error_norm=error_norm,
                force_virtual=wall_force,
                force_virtual_spring=wall_spring_force,
                force_virtual_damping=wall_damping_force,
                wall_penetration=wall_penetration,
                wall_penetration_cm=100.0 * wall_penetration,
                wall_retreat=wall_retreat,
                wall_retreat_cm=100.0 * wall_retreat,
                tuned_target_x=live_tuning.value("target_x", target_x_ee[0]),
                tuned_target_y=live_tuning.value("target_y", target_x_ee[1]),
                tuned_target_z=live_tuning.value("target_z", target_x_ee[2]),
                target_wall_gap_cm=100.0 * (target_x_ee[0] - float(wall_config.get("wall_x", target_x_ee[0]))),
                tuned_joint_target_offset=tuned_joint_offset,
                tuned_wall_x=float(wall_config.get("wall_x", 10.0)),
                tuned_wall_stiffness=float(wall_config.get("stiffness", 0.0)),
                tuned_wall_damping=float(wall_config.get("damping", 0.0)),
                tuned_wall_retreat_gain=float(wall_config.get("cartesian_retreat_gain", 0.0)),
                tuned_wall_force_retreat_gain=float(wall_config.get("force_retreat_gain", 0.0)),
                tuned_cartesian_gain=live_tuning.value(
                    "cartesian_gain",
                    float(dict(config.get("cartesian_target", {})).get("gain", 1.0)),
                ),
            )
            _update_viewer_guides(
                mujoco,
                viewer_handle,
                mode=mode,
                guide_config=viewer_guides,
                ee_position=ee_position,
                target_x_ee=target_x_ee,
                wall_config=wall_config,
                wall_penetration=wall_penetration,
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

    summary = {**_summary(logger.rows), **interaction_log.summary()}
    events = interaction_log.events()
    output_path = logger.save_with_artifacts(
        summary=summary,
        notes=_notes(config),
        interaction_events=events if events else None,
    )
    if plot:
        _save_plots(output_path, logger.rows, plot_selection or config.get("plots"))
    return resolve_project_path(output_path)


def _viewer_guides(config: dict[str, Any], mode: str) -> dict[str, bool]:
    guide_config = dict(config.get("viewer_guides", {}))
    default_enabled = mode in {"cartesian_reach", "task_space", "ee_reach", "impedance_wall", "virtual_wall", "wall"}
    return {
        "enabled": bool(guide_config.get("enabled", default_enabled)),
        "hand": bool(guide_config.get("hand", True)),
        "target": bool(guide_config.get("target", True)),
        "wall": bool(guide_config.get("wall", True)),
    }


def _live_status_specs(mode: str) -> list[StatusSpec]:
    specs = [
        StatusSpec("joint_offset", "Joint target [rad]"),
        StatusSpec("error_norm", "Joint error norm"),
        StatusSpec("ee_x", "Hand X [m]"),
    ]
    if mode in {"cartesian_reach", "task_space", "ee_reach", "impedance_wall", "virtual_wall", "wall"}:
        specs.extend(
            [
                StatusSpec("target_x", "Target X [m]"),
                StatusSpec("cartesian_error_cm", "Hand error [cm]"),
            ]
        )
    if mode in {"impedance_wall", "virtual_wall", "wall"}:
        specs.extend(
            [
                StatusSpec("wall_x", "Wall X [m]"),
                StatusSpec("target_wall_gap_cm", "Target-Wall [cm]"),
                StatusSpec("wall_penetration_cm", "Wall penetration [cm]"),
                StatusSpec("wall_force_x", "Wall force X [N]"),
            ]
        )
    return specs


def _update_viewer_guides(
    mujoco: Any,
    viewer_handle: Any | None,
    *,
    mode: str,
    guide_config: dict[str, bool],
    ee_position: list[float],
    target_x_ee: list[float],
    wall_config: dict[str, Any],
    wall_penetration: float,
) -> None:
    if viewer_handle is None:
        return
    reset_viewer_overlays(viewer_handle)
    if not guide_config.get("enabled", True):
        return

    is_cartesian = mode in {"cartesian_reach", "task_space", "ee_reach"}
    is_wall = mode in {"impedance_wall", "virtual_wall", "wall"}
    if guide_config.get("wall", True) and is_wall:
        wall_x = float(wall_config.get("wall_x", 0.57))
        add_viewer_box(
            mujoco,
            viewer_handle,
            [wall_x, 0.0, 0.58],
            half_size=[0.006, 0.36, 0.30],
            rgba=[1.0, 0.18, 0.12, 0.24],
        )
    if guide_config.get("target", True) and (is_cartesian or is_wall):
        add_viewer_sphere(
            mujoco,
            viewer_handle,
            target_x_ee,
            radius=0.024,
            rgba=[0.10, 0.82, 0.28, 0.85],
        )
    if guide_config.get("hand", True) and (is_cartesian or is_wall):
        hand_color = [1.0, 0.48, 0.10, 0.90] if wall_penetration > 0.0 else [0.10, 0.42, 1.0, 0.78]
        add_viewer_sphere(
            mujoco,
            viewer_handle,
            ee_position,
            radius=0.016,
            rgba=hand_color,
        )


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


def _live_tuning(config: dict[str, Any], interaction_log: InteractionLog | None = None) -> LiveTuning:
    interaction = dict(config.get("interaction", {}))
    if not bool(interaction.get("live_tuning", False)):
        return LiveTuning([])
    mode = str(config.get("mode", "")).lower()
    if mode in {"cartesian_reach", "task_space", "ee_reach"}:
        target_config = dict(config.get("cartesian_target", {}))
        target_position = _float_list(target_config.get("position", [0.60, 0.10, 0.59]), 3)
        specs = [
            SliderSpec("target_x", "Target X [m]", 0.35, 0.75, target_position[0], 0.005),
            SliderSpec("target_y", "Target Y [m]", -0.35, 0.35, target_position[1], 0.005),
            SliderSpec("target_z", "Target Z [m]", 0.35, 0.80, target_position[2], 0.005),
            SliderSpec("cartesian_gain", "Cartesian gain", 0.2, 2.0, float(target_config.get("gain", 1.0)), 0.05),
        ]
        return LiveTuning(
            specs,
            event_log=interaction_log,
            presets=tuning_presets_from_config(config, specs),
        )
    target_specs: list[SliderSpec] = []
    target_config = dict(config.get("cartesian_target", {}))
    if target_config:
        target_position = _float_list(target_config.get("position", [0.61, 0.0, 0.58]), 3)
        target_specs = [
            SliderSpec("target_x", "Target X [m]", 0.35, 0.75, target_position[0], 0.005),
            SliderSpec("target_y", "Target Y [m]", -0.35, 0.35, target_position[1], 0.005),
            SliderSpec("target_z", "Target Z [m]", 0.35, 0.80, target_position[2], 0.005),
            SliderSpec("cartesian_gain", "Cartesian gain", 0.2, 2.0, float(target_config.get("gain", 1.0)), 0.05),
        ]
    wall_config = dict(config.get("virtual_wall", {}))
    specs = [
        *target_specs,
        SliderSpec("joint_target_offset", "Joint target offset [rad]", -0.35, 0.35, 0.0, 0.01),
        SliderSpec("wall_x", "Virtual wall X [m]", 0.50, 0.70, float(wall_config.get("wall_x", 0.57)), 0.005),
        SliderSpec(
            "wall_stiffness",
            "Wall stiffness [N/m]",
            0.0,
            800.0,
            float(wall_config.get("stiffness", 260.0)),
            10.0,
        ),
        SliderSpec(
            "wall_damping",
            "Wall damping [N s/m]",
            0.0,
            40.0,
            float(wall_config.get("damping", 12.0)),
            0.5,
        ),
        SliderSpec(
            "wall_retreat_gain",
            "Retreat gain",
            0.0,
            1.5,
            float(wall_config.get("cartesian_retreat_gain", 0.4)),
            0.05,
        ),
    ]
    return LiveTuning(
        specs,
        event_log=interaction_log,
        presets=tuning_presets_from_config(config, specs),
    )


def _wall_cartesian_target_enabled(config: dict[str, Any]) -> bool:
    return bool(dict(config.get("cartesian_target", {})))


def _cartesian_target_position(
    config: dict[str, Any],
    live_tuning: LiveTuning,
    initial_ee_position: list[float],
    alpha: float,
) -> list[float]:
    target_config = dict(config.get("cartesian_target", {}))
    if "position" in target_config:
        goal = _float_list(target_config["position"], 3)
    else:
        offset = _float_list(target_config.get("offset", [0.05, 0.10, -0.03]), 3)
        goal = [initial_ee_position[index] + offset[index] for index in range(3)]
    goal = [
        live_tuning.value("target_x", goal[0]),
        live_tuning.value("target_y", goal[1]),
        live_tuning.value("target_z", goal[2]),
    ]
    alpha = max(0.0, min(1.0, alpha))
    return [initial_ee_position[index] + alpha * (goal[index] - initial_ee_position[index]) for index in range(3)]


def _apply_cartesian_target_offset(
    q: list[float],
    jacobian: Any,
    cartesian_error: list[float],
    config: dict[str, Any],
    live_tuning: LiveTuning,
) -> list[float]:
    import numpy as np

    target_config = dict(config.get("cartesian_target", {}))
    gain = live_tuning.value("cartesian_gain", float(target_config.get("gain", 1.0)))
    max_step = float(target_config.get("max_step", 0.08))
    damping = float(target_config.get("damped_least_squares", 0.08))
    desired_task_offset = np.asarray([gain * value for value in cartesian_error], dtype=float)
    norm = float(np.linalg.norm(desired_task_offset))
    if norm > max_step:
        desired_task_offset *= max_step / norm
    task_matrix = jacobian @ jacobian.T + (damping**2) * np.eye(3)
    joint_offset = jacobian.T @ np.linalg.solve(task_matrix, desired_task_offset)
    max_joint_offset = float(target_config.get("max_joint_offset", 0.18))
    adjusted = q.copy()
    for index, delta_q in enumerate(joint_offset):
        adjusted[index] += max(-max_joint_offset, min(max_joint_offset, float(delta_q)))
    return adjusted


def _wall_config(config: dict[str, Any], live_tuning: LiveTuning) -> dict[str, Any]:
    wall_config = dict(config.get("virtual_wall", {}))
    wall_config["wall_x"] = live_tuning.value("wall_x", float(wall_config.get("wall_x", 10.0)))
    wall_config["stiffness"] = live_tuning.value("wall_stiffness", float(wall_config.get("stiffness", 250.0)))
    wall_config["damping"] = live_tuning.value("wall_damping", float(wall_config.get("damping", 12.0)))
    wall_config["cartesian_retreat_gain"] = live_tuning.value(
        "wall_retreat_gain",
        float(wall_config.get("cartesian_retreat_gain", 1.2)),
    )
    wall_config["force_retreat_gain"] = float(wall_config.get("force_retreat_gain", 0.00008))
    return wall_config


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
    return _virtual_wall_force_components(ee_position, ee_velocity, wall_config)[0]


def _virtual_wall_force_components(
    ee_position: list[float],
    ee_velocity: list[float],
    wall_config: dict[str, Any],
) -> tuple[list[float], list[float], list[float]]:
    wall_x = float(wall_config.get("wall_x", 0.52))
    stiffness = float(wall_config.get("stiffness", 250.0))
    damping = float(wall_config.get("damping", 12.0))
    penetration = ee_position[0] - wall_x
    if penetration <= 0.0:
        zeros = [0.0, 0.0, 0.0]
        return zeros, zeros.copy(), zeros.copy()
    spring_x = -stiffness * penetration
    damping_x = -damping * max(0.0, ee_velocity[0])
    return [spring_x + damping_x, 0.0, 0.0], [spring_x, 0.0, 0.0], [damping_x, 0.0, 0.0]


def _apply_wall_target_offset(
    target_q: list[float],
    jacobian: Any,
    ee_position: list[float],
    wall_force: list[float],
    config: dict[str, Any],
    wall_config: dict[str, Any],
) -> list[float]:
    import numpy as np

    if not any(abs(force) > 1e-12 for force in wall_force):
        return target_q
    desired_task_offset = np.asarray([-_wall_retreat_distance(ee_position, wall_force, wall_config), 0.0, 0.0])
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


def _wall_retreat_distance(
    ee_position: list[float],
    wall_force: list[float],
    wall_config: dict[str, Any],
) -> float:
    wall_x = float(wall_config.get("wall_x", 0.52))
    penetration = max(0.0, ee_position[0] - wall_x)
    cartesian_gain = float(wall_config.get("cartesian_retreat_gain", 1.2))
    force_retreat_gain = float(wall_config.get("force_retreat_gain", 0.00008))
    max_cartesian_retreat = float(wall_config.get("max_cartesian_retreat", 0.04))
    force_retreat = max(0.0, -float(wall_force[0])) * force_retreat_gain
    return min(max_cartesian_retreat, penetration * cartesian_gain + force_retreat)


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
    qdot_keys = [key for key in rows[0] if key.startswith("qdot_")]
    start_time = float(rows[0].get("time", 0.0))
    settled_rows = [row for row in rows if float(row.get("time", start_time)) >= start_time + 1.0]
    if not settled_rows:
        settled_rows = rows
    first_q = [float(value) for key, value in rows[0].items() if key.startswith("q_")]
    joint_drift_norms = []
    if first_q:
        for row in rows:
            q = [float(row.get(f"q_{index}", 0.0)) for index in range(len(first_q))]
            joint_drift_norms.append(_norm([q[index] - first_q[index] for index in range(len(first_q))]))
    wall_contact = _wall_contact_metrics(rows)
    return {
        "max_joint_error_norm": max(float(row["error_norm"]) for row in rows),
        "final_joint_error_norm": rows[-1]["error_norm"],
        "max_abs_qdot": max(abs(float(row.get(key, 0.0))) for row in rows for key in qdot_keys) if qdot_keys else 0.0,
        "max_settled_abs_qdot": (
            max(abs(float(row.get(key, 0.0))) for row in settled_rows for key in qdot_keys) if qdot_keys else 0.0
        ),
        "max_joint_drift_norm": max(joint_drift_norms) if joint_drift_norms else 0.0,
        "max_abs_tau_cmd": max(
            abs(float(value))
            for row in rows
            for key, value in row.items()
            if key.startswith("tau_cmd_")
        ),
        "max_wall_penetration": max(float(row.get("wall_penetration", 0.0)) for row in rows),
        "max_wall_penetration_cm": max(float(row.get("wall_penetration_cm", 0.0)) for row in rows),
        "max_wall_retreat_cm": max(float(row.get("wall_retreat_cm", 0.0)) for row in rows),
        "first_wall_contact_time": wall_contact["first_wall_contact_time"],
        "last_wall_contact_time": wall_contact["last_wall_contact_time"],
        "wall_contact_duration": wall_contact["wall_contact_duration"],
        "wall_contact_fraction": wall_contact["wall_contact_fraction"],
        "max_abs_virtual_wall_force": max(abs(float(row.get("force_virtual_0", 0.0))) for row in rows),
        "max_abs_virtual_wall_spring_force": max(
            abs(float(row.get("force_virtual_spring_0", 0.0))) for row in rows
        ),
        "max_abs_virtual_wall_damping_force": max(
            abs(float(row.get("force_virtual_damping_0", 0.0))) for row in rows
        ),
        "max_cartesian_error_cm": max(float(row.get("cartesian_error_cm", 0.0)) for row in rows),
        "final_cartesian_error_cm": rows[-1].get("cartesian_error_cm", 0.0),
        "final_x_ee_0": rows[-1].get("x_ee_0"),
        "final_x_ee_1": rows[-1].get("x_ee_1"),
        "final_x_ee_2": rows[-1].get("x_ee_2"),
    }


def _wall_contact_metrics(rows: list[dict[str, Any]], threshold_cm: float = 1e-9) -> dict[str, float | None]:
    times = [float(row.get("time", 0.0)) for row in rows]
    contact = [float(row.get("wall_penetration_cm", 0.0)) > threshold_cm for row in rows]
    contact_indices = [index for index, is_contact in enumerate(contact) if is_contact]
    if not contact_indices:
        return {
            "first_wall_contact_time": None,
            "last_wall_contact_time": None,
            "wall_contact_duration": 0.0,
            "wall_contact_fraction": 0.0,
        }

    duration = 0.0
    for index, is_contact in enumerate(contact[:-1]):
        if is_contact:
            duration += max(0.0, times[index + 1] - times[index])
    total_duration = max(0.0, times[-1] - times[0])
    fraction = duration / total_duration if total_duration > 0.0 else 0.0
    return {
        "first_wall_contact_time": times[contact_indices[0]],
        "last_wall_contact_time": times[contact_indices[-1]],
        "wall_contact_duration": duration,
        "wall_contact_fraction": fraction,
    }


def _save_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    q_keys = [f"q_{index}" for index in range(7)]
    target_keys = [f"target_q_{index}" for index in range(7)]
    tau_keys = [f"tau_cmd_{index}" for index in range(7)]
    current_keys = [f"current_proxy_{index}" for index in range(7)]
    specs = [
        ("position.png", "Panda Joint Positions", "joint position [rad]", q_keys + target_keys),
        ("velocity.png", "Panda Joint Velocities", "joint velocity [rad/s]", [f"qdot_{index}" for index in range(7)]),
        ("torque.png", "Panda Actuator Force", "force / torque proxy", tau_keys),
        ("current_proxy.png", "Panda Current Proxy", "current proxy", current_keys),
        (
            "end_effector.png",
            "End-Effector Position",
            "position [m]",
            ["x_ee_0", "x_ee_1", "x_ee_2", "target_x_ee_0", "target_x_ee_1", "target_x_ee_2"],
        ),
        ("error.png", "Joint Tracking Error Norm", "norm [rad]", ["error_norm"]),
        ("cartesian_error.png", "Cartesian Tracking Error", "error [cm]", ["cartesian_error_cm"]),
        (
            "virtual_wall.png",
            "Virtual Wall Response",
            "force / penetration",
            [
                "force_virtual_0",
                "force_virtual_spring_0",
                "force_virtual_damping_0",
                "wall_penetration_cm",
                "wall_retreat_cm",
            ],
        ),
        (
            "wall_parameters.png",
            "Virtual Wall Parameters",
            "parameter value",
            [
                "tuned_target_x",
                "tuned_wall_x",
                "target_wall_gap_cm",
                "tuned_wall_stiffness",
                "tuned_wall_damping",
                "tuned_wall_retreat_gain",
            ],
        ),
    ]
    presets = {
        "essential": ["position", "error"],
        "stability": ["position", "velocity", "error", "torque"],
        "control": ["position", "error", "torque", "current_proxy"],
        "cartesian": ["end_effector", "cartesian_error", "torque", "error"],
        "cartesian_reach": ["end_effector", "cartesian_error", "torque", "current_proxy", "error"],
        "wall": ["end_effector", "virtual_wall", "torque", "error"],
        "wall_compare": ["end_effector", "virtual_wall", "wall_parameters", "torque", "error"],
    }
    save_time_series_plots(output_path, rows, select_plot_specs(specs, selection, presets=presets))


def _notes(config: dict[str, Any]) -> str:
    return f"""# Lab04 Panda Manipulator

This lab uses the MuJoCo Menagerie Franka Emika Panda model.

The Menagerie model is position-actuated, so `ctrl` is a target joint position.
The logged `tau_cmd` and `current_proxy` come from MuJoCo actuator force output.
Cartesian reach mode uses damped-least-squares Jacobian target offsets on top of the position actuators.

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
