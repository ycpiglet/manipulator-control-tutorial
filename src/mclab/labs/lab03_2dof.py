"""Trajectory planning and 2DOF manipulator lab."""

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
from mclab.sim.one_dof import configure_slider_plant, slider_state
from mclab.sim.plotting import PlotSelection, save_time_series_plots, select_plot_specs
from mclab.sim.two_link import (
    TwoLinkGeometry,
    end_effector_velocity,
    forward_kinematics,
    inverse_kinematics,
    jacobian,
    jacobian_condition_number,
    jacobian_determinant,
    manipulability,
)
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
    if _is_two_link_config(config):
        return _run_two_link_arm(
            config,
            config_path=config_path,
            output_dir=output_dir,
            plot=plot,
            viewer=viewer,
            headless=headless,
            realtime=realtime,
            pause_at_end=pause_at_end,
            show_viewer_ui=show_viewer_ui,
            plot_selection=plot_selection,
            seed=seed,
        )
    return _run_slider_trajectory(
        config,
        config_path=config_path,
        output_dir=output_dir,
        plot=plot,
        viewer=viewer,
        headless=headless,
        realtime=realtime,
        pause_at_end=pause_at_end,
        show_viewer_ui=show_viewer_ui,
        plot_selection=plot_selection,
        seed=seed,
    )


def _run_slider_trajectory(
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
    force_limit_value = max(abs(limit) for limit in (lower_limit, upper_limit) if limit is not None) if force_limit else 200.0
    kt = float(config.get("torque_constant", 1.0))

    key_force = KeyForcePulse(config)
    live_tuning = _live_tuning(config, controller_config, force_limit_value)
    live_status = LiveStatus(
        [
            StatusSpec("target", "Target [m]"),
            StatusSpec("position", "Position [m]"),
            StatusSpec("error", "Tracking error [m]"),
            StatusSpec("control", "Control force [N]"),
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
            title="MCLab Lab03 Interaction",
            tuning=live_tuning,
            status=live_status,
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
            key_force.update_time(float(data.time))
            position, velocity, _ = slider_state(data, handles)
            target = trajectory.evaluate(float(data.time))
            tuned_kp = live_tuning.value("kp", kp)
            tuned_kd = live_tuning.value("kd", kd)
            tuned_force_limit = abs(live_tuning.value("force_limit", force_limit_value))
            target_position = target.position + live_tuning.value("target_offset", 0.0)
            feedback = tuned_kp * (target_position - position) + tuned_kd * (target.velocity - velocity)
            feedforward = feedforward_mass * target.acceleration if use_feedforward else 0.0
            control_force = _clip(feedback + feedforward, -tuned_force_limit, tuned_force_limit)
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
            live_status.set_values(
                target=target_position,
                position=position,
                error=target_position - position,
                control=control_force,
                manual=manual_force,
            )
            logger.record(
                time=float(data.time),
                position=position,
                velocity=velocity,
                acceleration=acceleration,
                target_position=target_position,
                target_velocity=target.velocity,
                target_acceleration=target.acceleration,
                target_jerk=target.jerk,
                position_error=target_position - position,
                velocity_error=target.velocity - velocity,
                control_force=control_force,
                manual_force=manual_force,
                total_force=total_force,
                tuned_kp=tuned_kp,
                tuned_kd=tuned_kd,
                tuned_force_limit=tuned_force_limit,
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


def _run_two_link_arm(
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
    lab_name = "lab03_2dof"
    model_path = config.get("model_path", "models/lab03_2dof/two_link.xml")
    mujoco, model, data = load_model_and_data(model_path)
    if "dt" in config:
        model.opt.timestep = float(config["dt"])

    handles = _two_link_handles(mujoco, model, config)
    logger = RunLogger(lab_name, config, config_path=config_path, output_dir=output_dir)

    sim_time = float(config.get("sim_time", 5.0))
    mode = str(config.get("mode", "joint_space")).lower()
    geometry = _two_link_geometry(config)
    initial_q = _pair(config.get("initial_q", [0.25, -1.0]), "initial_q")
    _set_two_link_state(data, handles, initial_q)
    mujoco.mj_forward(model, data)

    trajectory = build_trajectory(dict(config.get("trajectory", {"type": "minimum_jerk", "start": 0.0, "end": 1.0})))
    controller_config = dict(config.get("tracking_controller", {}))
    torque_limit = _pair(controller_config.get("torque_limit", [50.0, 40.0]), "torque_limit")
    kt = float(config.get("torque_constant", 1.0))

    target_q_goal = _pair(config.get("target_q", [0.9, -1.1]), "target_q")
    start_xy = forward_kinematics(initial_q, geometry)
    target_xy_goal = _pair(config.get("target_xy", start_xy), "target_xy")

    panel_control = KeyForcePulse(config)
    live_tuning = _two_link_live_tuning(config, mode, controller_config, torque_limit, target_xy_goal)
    live_status = LiveStatus(
        [
            StatusSpec("q1", "q1 [rad]"),
            StatusSpec("q2", "q2 [rad]"),
            StatusSpec("ee_x", "Hand X [m]"),
            StatusSpec("ee_y", "Hand Y [m]"),
            StatusSpec("error", "Error norm"),
            StatusSpec("tau", "Max torque [N m]"),
            StatusSpec("condition", "Jacobian cond."),
            StatusSpec("manipulability", "Manipulability"),
        ]
    )
    viewer_handle = maybe_launch_viewer(
        mujoco,
        model,
        data,
        enabled=viewer and not headless,
        key_callback=None,
        show_ui=show_viewer_ui,
    )
    interaction_panel = (
        maybe_start_interaction_panel(
            panel_control,
            title="MCLab Lab03 2DOF Interaction",
            tuning=live_tuning,
            status=live_status,
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

            q, qdot = _two_link_state(data, handles)
            target = trajectory.evaluate(float(data.time))
            alpha = target.position
            alpha_dot = target.velocity

            if mode in {"task_space", "cartesian", "jacobian"}:
                target_xy_goal = (
                    live_tuning.value("target_x", target_xy_goal[0]),
                    live_tuning.value("target_y", target_xy_goal[1]),
                )
                command = _task_space_command(
                    q=q,
                    qdot=qdot,
                    start_xy=start_xy,
                    goal_xy=target_xy_goal,
                    alpha=alpha,
                    alpha_dot=alpha_dot,
                    geometry=geometry,
                    controller_config=controller_config,
                    live_tuning=live_tuning,
                    torque_limit=torque_limit,
                )
            else:
                command = _joint_space_command(
                    q=q,
                    qdot=qdot,
                    start_q=initial_q,
                    goal_q=target_q_goal,
                    alpha=alpha,
                    alpha_dot=alpha_dot,
                    geometry=geometry,
                    controller_config=controller_config,
                    live_tuning=live_tuning,
                    torque_limit=torque_limit,
                )

            for index, actuator_id in enumerate(handles["actuator_ids"]):
                data.ctrl[actuator_id] = command["tau"][index]

            mujoco.mj_step(model, data)
            sync_viewer(
                viewer_handle,
                data,
                realtime=realtime,
                wall_start=wall_start,
                sim_start=sim_start,
            )

            q, qdot = _two_link_state(data, handles)
            x_ee = forward_kinematics(q, geometry)
            xdot_ee = end_effector_velocity(q, qdot, geometry)
            joint_error = [command["target_q"][index] - q[index] for index in range(2)]
            task_error = [command["target_xy"][index] - x_ee[index] for index in range(2)]
            joint_error_norm = _norm(joint_error)
            task_error_norm = _norm(task_error)
            max_tau = max(abs(value) for value in command["tau"])
            condition = jacobian_condition_number(q, geometry)
            condition_capped = _cap_infinite(condition)
            manipulability_value = manipulability(q, geometry)
            determinant = jacobian_determinant(q, geometry)
            live_status.set_values(
                q1=q[0],
                q2=q[1],
                ee_x=x_ee[0],
                ee_y=x_ee[1],
                error=task_error_norm if mode in {"task_space", "cartesian", "jacobian"} else joint_error_norm,
                tau=max_tau,
                condition=condition_capped,
                manipulability=manipulability_value,
            )
            logger.record(
                time=float(data.time),
                mode=mode,
                q=q,
                qdot=qdot,
                target_q=command["target_q"],
                joint_error=joint_error,
                joint_error_norm=joint_error_norm,
                x_ee=x_ee,
                xdot_ee=xdot_ee,
                target_x_ee=command["target_xy"],
                task_error=task_error,
                task_error_norm=task_error_norm,
                tau_cmd=command["tau"],
                current_proxy=[value / kt for value in command["tau"]],
                jacobian_determinant=determinant,
                manipulability=manipulability_value,
                jacobian_condition=condition_capped,
                tuned_kp=command["kp"],
                tuned_kd=command["kd"],
                tuned_torque_limit=command["torque_limit"],
            )
        completed = True
    finally:
        if interaction_panel is not None:
            interaction_panel.close()
        if viewer_handle is not None:
            if completed:
                pause_viewer_at_end(viewer_handle, enabled=pause_at_end)
            viewer_handle.close()

    summary = _two_link_summary(logger.rows)
    output_path = logger.save(summary=summary, notes=_two_link_notes(config))
    if plot:
        _save_two_link_plots(output_path, logger.rows, plot_selection or config.get("plots"))
    return resolve_project_path(output_path)


def _live_tuning(config: dict[str, Any], controller_config: dict[str, Any], force_limit: float) -> LiveTuning:
    interaction = dict(config.get("interaction", {}))
    if not bool(interaction.get("live_tuning", False)):
        return LiveTuning([])
    return LiveTuning(
        [
            SliderSpec("target_offset", "Target offset [m]", -0.5, 0.5, 0.0, 0.01),
            SliderSpec("kp", "Tracking Kp", 0.0, 250.0, float(controller_config.get("kp", 120.0)), 1.0),
            SliderSpec("kd", "Tracking Kd", 0.0, 60.0, float(controller_config.get("kd", 18.0)), 0.5),
            SliderSpec("force_limit", "Force limit [N]", 10.0, 250.0, force_limit, 1.0),
        ]
    )


def _two_link_live_tuning(
    config: dict[str, Any],
    mode: str,
    controller_config: dict[str, Any],
    torque_limit: tuple[float, float],
    target_xy: tuple[float, float],
) -> LiveTuning:
    interaction = dict(config.get("interaction", {}))
    if not bool(interaction.get("live_tuning", False)):
        return LiveTuning([])
    if mode in {"task_space", "cartesian", "jacobian"}:
        return LiveTuning(
            [
                SliderSpec("target_x", "Target X [m]", -0.95, 0.95, target_xy[0], 0.01),
                SliderSpec("target_y", "Target Y [m]", -0.85, 0.85, target_xy[1], 0.01),
                SliderSpec("task_kp", "Task stiffness", 5.0, 180.0, float(controller_config.get("task_kp", 90.0)), 1.0),
                SliderSpec("task_kd", "Task damping", 0.0, 45.0, float(controller_config.get("task_kd", 16.0)), 0.5),
                SliderSpec("torque_limit", "Torque limit [N m]", 5.0, 80.0, max(torque_limit), 1.0),
            ]
        )
    return LiveTuning(
        [
            SliderSpec("q1_offset", "q1 target offset [rad]", -0.8, 0.8, 0.0, 0.01),
            SliderSpec("q2_offset", "q2 target offset [rad]", -0.8, 0.8, 0.0, 0.01),
            SliderSpec("joint_kp", "Joint Kp scale", 0.2, 2.0, 1.0, 0.05),
            SliderSpec("joint_kd", "Joint Kd scale", 0.2, 2.0, 1.0, 0.05),
            SliderSpec("torque_limit", "Torque limit [N m]", 5.0, 80.0, max(torque_limit), 1.0),
        ]
    )


def _two_link_handles(mujoco: Any, model: Any, config: dict[str, Any]) -> dict[str, Any]:
    joint_names = list(config.get("joint_names", ["shoulder", "elbow"]))
    actuator_names = list(config.get("actuator_names", ["shoulder_motor", "elbow_motor"]))
    site_name = str(config.get("end_effector_site", "ee"))
    joint_ids = [_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in joint_names]
    actuator_ids = [_id(mujoco, model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in actuator_names]
    site_id = _id(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, site_name)
    return {
        "joint_ids": joint_ids,
        "actuator_ids": actuator_ids,
        "site_id": site_id,
        "qpos_indices": [int(model.jnt_qposadr[index]) for index in joint_ids],
        "dof_indices": [int(model.jnt_dofadr[index]) for index in joint_ids],
    }


def _id(mujoco: Any, model: Any, kind: Any, name: str) -> int:
    item_id = int(mujoco.mj_name2id(model, kind, name))
    if item_id < 0:
        raise RuntimeError(f"MuJoCo object not found: {name}")
    return item_id


def _set_two_link_state(data: Any, handles: dict[str, Any], q: tuple[float, float]) -> None:
    for index, value in enumerate(q):
        data.qpos[handles["qpos_indices"][index]] = value
        data.qvel[handles["dof_indices"][index]] = 0.0


def _two_link_state(data: Any, handles: dict[str, Any]) -> tuple[list[float], list[float]]:
    q = [float(data.qpos[index]) for index in handles["qpos_indices"]]
    qdot = [float(data.qvel[index]) for index in handles["dof_indices"]]
    return q, qdot


def _joint_space_command(
    *,
    q: list[float],
    qdot: list[float],
    start_q: tuple[float, float],
    goal_q: tuple[float, float],
    alpha: float,
    alpha_dot: float,
    geometry: TwoLinkGeometry,
    controller_config: dict[str, Any],
    live_tuning: LiveTuning,
    torque_limit: tuple[float, float],
) -> dict[str, Any]:
    goal = (
        goal_q[0] + live_tuning.value("q1_offset", 0.0),
        goal_q[1] + live_tuning.value("q2_offset", 0.0),
    )
    target_q = [start_q[index] + alpha * (goal[index] - start_q[index]) for index in range(2)]
    target_qdot = [alpha_dot * (goal[index] - start_q[index]) for index in range(2)]
    kp_base = _gain_pair(controller_config.get("kp", [80.0, 60.0]), "kp")
    kd_base = _gain_pair(controller_config.get("kd", [8.0, 6.0]), "kd")
    kp_scale = live_tuning.value("joint_kp", 1.0)
    kd_scale = live_tuning.value("joint_kd", 1.0)
    limit_value = abs(live_tuning.value("torque_limit", max(torque_limit)))
    limit = (min(torque_limit[0], limit_value), min(torque_limit[1], limit_value))
    tau = []
    for index in range(2):
        command = kp_base[index] * kp_scale * (target_q[index] - q[index])
        command += kd_base[index] * kd_scale * (target_qdot[index] - qdot[index])
        tau.append(_clip(command, -limit[index], limit[index]))
    return {
        "target_q": target_q,
        "target_xy": list(forward_kinematics(target_q, geometry)),
        "tau": tau,
        "kp": sum(kp_base) * 0.5 * kp_scale,
        "kd": sum(kd_base) * 0.5 * kd_scale,
        "torque_limit": max(limit),
    }


def _task_space_command(
    *,
    q: list[float],
    qdot: list[float],
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
    alpha: float,
    alpha_dot: float,
    geometry: TwoLinkGeometry,
    controller_config: dict[str, Any],
    live_tuning: LiveTuning,
    torque_limit: tuple[float, float],
) -> dict[str, Any]:
    x_ee = forward_kinematics(q, geometry)
    xdot_ee = end_effector_velocity(q, qdot, geometry)
    target_xy = [start_xy[index] + alpha * (goal_xy[index] - start_xy[index]) for index in range(2)]
    target_xdot = [alpha_dot * (goal_xy[index] - start_xy[index]) for index in range(2)]
    kp = live_tuning.value("task_kp", float(controller_config.get("task_kp", 90.0)))
    kd = live_tuning.value("task_kd", float(controller_config.get("task_kd", 16.0)))
    joint_damping = float(controller_config.get("joint_damping", 0.5))
    force = [kp * (target_xy[index] - x_ee[index]) + kd * (target_xdot[index] - xdot_ee[index]) for index in range(2)]
    j = jacobian(q, geometry)
    tau = [
        j[0][0] * force[0] + j[1][0] * force[1] - joint_damping * qdot[0],
        j[0][1] * force[0] + j[1][1] * force[1] - joint_damping * qdot[1],
    ]
    limit_value = abs(live_tuning.value("torque_limit", max(torque_limit)))
    limit = (min(torque_limit[0], limit_value), min(torque_limit[1], limit_value))
    tau = [_clip(tau[index], -limit[index], limit[index]) for index in range(2)]
    return {
        "target_q": list(inverse_kinematics(target_xy, geometry)),
        "target_xy": target_xy,
        "tau": tau,
        "kp": kp,
        "kd": kd,
        "torque_limit": max(limit),
    }


def _save_two_link_plots(output_path: Path, rows: list[dict[str, Any]], selection: PlotSelection = None) -> None:
    specs = [
        ("position.png", "2DOF Joint Position Tracking", "joint position [rad]", ["q_0", "q_1", "target_q_0", "target_q_1"]),
        ("end_effector.png", "2DOF End-Effector Tracking", "position [m]", ["x_ee_0", "x_ee_1", "target_x_ee_0", "target_x_ee_1"]),
        ("torque.png", "2DOF Joint Torques", "torque [N m]", ["tau_cmd_0", "tau_cmd_1"]),
        ("current_proxy.png", "2DOF Current Proxy", "current proxy", ["current_proxy_0", "current_proxy_1"]),
        ("error.png", "2DOF Tracking Error", "error norm", ["joint_error_norm", "task_error_norm"]),
        (
            "singularity.png",
            "2DOF Jacobian Singularity Metrics",
            "condition / manipulability",
            ["jacobian_condition", "manipulability", "jacobian_determinant"],
        ),
    ]
    presets = {
        "essential": ["position", "end_effector", "torque", "error"],
        "joint": ["position", "torque", "error"],
        "task": ["end_effector", "torque", "error"],
        "singularity": ["position", "end_effector", "torque", "singularity", "error"],
        "control": ["position", "end_effector", "torque", "current_proxy", "singularity", "error"],
    }
    save_time_series_plots(output_path, rows, select_plot_specs(specs, selection, presets=presets))


def _two_link_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return {
        "max_joint_error_norm": max(float(row["joint_error_norm"]) for row in rows),
        "final_joint_error_norm": rows[-1]["joint_error_norm"],
        "max_task_error_norm": max(float(row["task_error_norm"]) for row in rows),
        "final_task_error_norm": rows[-1]["task_error_norm"],
        "min_manipulability": min(float(row["manipulability"]) for row in rows),
        "max_jacobian_condition": max(float(row["jacobian_condition"]) for row in rows),
        "max_abs_tau_cmd": max(
            abs(float(value))
            for row in rows
            for key, value in row.items()
            if key.startswith("tau_cmd_")
        ),
    }


def _two_link_notes(config: dict[str, Any]) -> str:
    return f"""# Lab03 2DOF Manipulator

This run uses a planar two-link MuJoCo arm with torque motors at the shoulder and elbow.

- mode: {config.get("mode", "joint_space")}
- model_path: {config.get("model_path", "models/lab03_2dof/two_link.xml")}
- link_lengths: {config.get("link_lengths", [0.6, 0.45])}

Joint-space mode tracks desired joint angles with PD torque control.
Task-space mode uses a Jacobian-transpose PD command on end-effector position.
Singularity metrics log Jacobian determinant, manipulability, and condition number.
"""


def _is_two_link_config(config: dict[str, Any]) -> bool:
    plant = str(config.get("plant", "")).lower()
    mode = str(config.get("mode", "")).lower()
    return plant in {"two_link", "two_link_arm", "2dof", "2dof_arm"} or mode in {
        "joint_space",
        "task_space",
        "cartesian",
        "jacobian",
    }


def _two_link_geometry(config: dict[str, Any]) -> TwoLinkGeometry:
    lengths = _pair(config.get("link_lengths", [0.6, 0.45]), "link_lengths")
    return TwoLinkGeometry(link1=lengths[0], link2=lengths[1])


def _pair(value: Any, name: str) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    scalar = float(value)
    return scalar, scalar


def _gain_pair(value: Any, name: str) -> tuple[float, float]:
    try:
        return _pair(value, name)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a scalar or a length-2 list") from exc


def _norm(values: list[float]) -> float:
    return sum(value * value for value in values) ** 0.5


def _cap_infinite(value: float, cap: float = 1.0e6) -> float:
    if value == float("inf"):
        return cap
    return min(value, cap)


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
