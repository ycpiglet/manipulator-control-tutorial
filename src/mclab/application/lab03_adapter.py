"""Integrated Lab03 adapters for trajectory and 2DOF experiments."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from mclab.application.artifacts import ReplayRecorder
from mclab.application.catalog import ScenarioDefinition
from mclab.application.rendering import (
    MujocoRenderMixin,
    add_arrow,
    add_box,
    add_circle,
    add_dashed_segment,
    add_digit_marker,
    add_sphere,
)
from mclab.sim.interaction import InteractionLog, learner_tuned_config
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import load_model_and_data
from mclab.sim.one_dof import configure_slider_plant, reset_slider_plant_state, slider_state
from mclab.sim.two_link import (
    end_effector_velocity,
    forward_kinematics,
    jacobian_condition_number,
    jacobian_determinant,
    manipulability,
)
from mclab.trajectories import build_trajectory

from mclab.labs import lab03_2dof as legacy


class Lab03Adapter:
    """Select the integrated 1D or two-link Lab03 implementation."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None = None,
        safe_mode: bool = False,
        seed: int | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        config = config_override if config_override is not None else scenario.config
        implementation = (
            Lab03TwoLinkAdapter
            if legacy._is_two_link_config(config)
            else Lab03SliderAdapter
        )
        self._implementation = implementation(
            scenario,
            output_dir=output_dir,
            safe_mode=safe_mode,
            seed=seed,
            config_override=config_override,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._implementation, name)


class Lab03SliderAdapter(MujocoRenderMixin):
    """Trajectory tracking on the shared one-dimensional MuJoCo plant."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None,
        safe_mode: bool,
        seed: int | None,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        self.scenario = scenario
        self.config = deepcopy(config_override if config_override is not None else scenario.config)
        self.output_dir = Path(output_dir) if output_dir else None
        self.safe_mode = safe_mode
        self.seed = seed
        self.mujoco = self.model = self.data = self.handles = None
        self.renderer = self.camera = self.logger = None
        self.trajectory = None
        self.live_tuning = None
        self.events = InteractionLog()
        self.manual_force = 0.0
        self.force_until = 0.0
        self._closed = False

    @property
    def time(self) -> float:
        return float(self.data.time) if self.data is not None else 0.0

    @property
    def timestep(self) -> float:
        return (
            float(self.model.opt.timestep)
            if self.model is not None
            else float(self.config.get("dt", 0.002))
        )

    def prepare(self) -> None:
        if self.data is not None:
            return
        self.mujoco, self.model, self.data = load_model_and_data(
            self.config.get("model_path", "models/lab03_2dof/scene.xml")
        )
        self.handles = configure_slider_plant(self.mujoco, self.model, self.data, self.config)
        self.logger = RunLogger(
            "lab03_trajectory",
            self.config,
            config_path=Path(self.scenario.config_path),
            output_dir=self.output_dir,
            seed=self.seed,
        )
        self.trajectory = build_trajectory(dict(self.config.get("trajectory", {})))
        controller = dict(self.config.get("tracking_controller", {}))
        force_limit = controller.get("force_limit", 200.0)
        _, upper = legacy._limits(force_limit)
        self.live_tuning = legacy._live_tuning(
            self.config,
            controller,
            abs(float(upper or 200.0)),
            self.events,
        )
        self.setup_camera()

    def step(self) -> dict[str, float]:
        self._require_ready()
        self.events.set_time(self.time)
        if self.time >= self.force_until:
            self.manual_force = 0.0
        position, velocity, _ = slider_state(self.data, self.handles)
        target = self.trajectory.evaluate(self.time)
        controller = dict(self.config.get("tracking_controller", {}))
        kp = self.live_tuning.value("kp", float(controller.get("kp", 120.0)))
        kd = self.live_tuning.value("kd", float(controller.get("kd", 18.0)))
        force_limit = abs(self.live_tuning.value("force_limit", 200.0))
        target_position = target.position + self.live_tuning.value("target_offset", 0.0)
        feedback = kp * (target_position - position) + kd * (target.velocity - velocity)
        feedforward = 0.0
        if bool(controller.get("feedforward_acceleration", True)):
            feedforward = (
                float(controller.get("feedforward_mass", self.config.get("mass", 1.0)))
                * target.acceleration
            )
        control = legacy._clip(feedback + feedforward, -force_limit, force_limit)
        total = control + self.manual_force
        self.data.ctrl[self.handles.actuator_id] = total
        self.mujoco.mj_step(self.model, self.data)
        position, velocity, acceleration = slider_state(self.data, self.handles)
        telemetry = {
            "time": self.time,
            "position": position,
            "velocity": velocity,
            "target_position": target_position,
            "position_error": target_position - position,
            "force": total,
        }
        self.logger.record(
            **telemetry,
            acceleration=acceleration,
            target_velocity=target.velocity,
            target_acceleration=target.acceleration,
            control_force=control,
            manual_force=self.manual_force,
            total_force=total,
            tuned_kp=kp,
            tuned_kd=kd,
            tuned_force_limit=force_limit,
        )
        return telemetry

    def reset(self) -> None:
        self._require_ready()
        reset_slider_plant_state(self.mujoco, self.model, self.data, self.handles, self.config)
        self.manual_force = 0.0
        self.force_until = 0.0

    def apply_action(self, name: str, value: Any = None) -> None:
        self._require_ready()
        if name in {spec.name for spec in self.live_tuning.specs}:
            self.live_tuning.set_value(name, float(value))
        elif name in {"pull", "push"}:
            interaction = dict(self.config.get("interaction", {}))
            magnitude = abs(float(interaction.get("force", 80.0)))
            self.manual_force = -magnitude if name == "pull" else magnitude
            self.force_until = self.time + float(interaction.get("duration", 0.35))
            self.events.record("button", name, self.manual_force, label=name.title())
        elif name == "restore_defaults":
            self.live_tuning.reset()
        else:
            self._camera_action(name, value)

    def finalize(self, recorder: ReplayRecorder, *, status: str) -> Path:
        self._require_ready()
        self.logger.replay = recorder
        output = self.logger.save_with_artifacts(
            summary={**legacy._summary(self.logger.rows), **self.events.summary()},
            notes=legacy._notes(self.config),
            interaction_events=self.events.events() or None,
            learner_snapshot={"slider_values": self.live_tuning.snapshot()},
            learner_tuned_config=learner_tuned_config(
                self.config,
                legacy._slider_learner_tuned_updates(self.config, self.live_tuning),
            ),
            run_status=status,
            finalize=False,
        )
        legacy._save_plots(output, self.logger.rows, self.scenario.plot_preset)
        self.logger.finalize_artifacts()
        return output

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.close_renderer()

    def _camera_action(self, name: str, value: Any) -> None:
        if name == "reset_camera":
            self.reset_camera()
        elif name in {"orbit", "pan"}:
            getattr(self, name)(float(value[0]), float(value[1]))
        elif name == "zoom":
            self.zoom(float(value))
        else:
            raise KeyError(f"Unsupported Lab03 action: {name}")

    def _require_ready(self) -> None:
        if self.data is None:
            raise RuntimeError("Lab03 trajectory adapter is not prepared.")


class Lab03TwoLinkAdapter(MujocoRenderMixin):
    """Joint-space, task-space, and DLS control behind SimulationSession."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None,
        safe_mode: bool,
        seed: int | None,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        self.scenario = scenario
        self.config = deepcopy(config_override if config_override is not None else scenario.config)
        self.output_dir = Path(output_dir) if output_dir else None
        self.safe_mode = safe_mode
        self.seed = seed
        self.mujoco = self.model = self.data = self.handles = None
        self.renderer = self.camera = self.logger = None
        self.trajectory = self.live_tuning = None
        self.events = InteractionLog()
        self.mode = str(self.config.get("mode", "joint_space")).lower()
        self.geometry = legacy._two_link_geometry(self.config)
        self.initial_q = legacy._pair(self.config.get("initial_q", [0.25, -1.0]), "initial_q")
        self.start_xy = forward_kinematics(self.initial_q, self.geometry)
        self.target_q_goal = legacy._pair(self.config.get("target_q", [0.9, -1.1]), "target_q")
        self.target_xy_goal = legacy._pair(self.config.get("target_xy", self.start_xy), "target_xy")
        self.target_waypoints = legacy._two_link_target_xy_waypoints(self.config)
        self.dls_target_q = list(self.initial_q)
        self.manual_tau = [0.0, 0.0]
        self.manual_until = 0.0
        self.last_hand = list(self.start_xy)
        self.last_target = list(self.start_xy)
        self.last_condition = 0.0
        self.shoulder_body_id = self.elbow_body_id = -1
        self._closed = False

    @property
    def time(self) -> float:
        return float(self.data.time) if self.data is not None else 0.0

    @property
    def timestep(self) -> float:
        return (
            float(self.model.opt.timestep)
            if self.model is not None
            else float(self.config.get("dt", 0.002))
        )

    def prepare(self) -> None:
        if self.data is not None:
            return
        self.mujoco, self.model, self.data = load_model_and_data(
            self.config.get("model_path", "models/lab03_2dof/two_link.xml")
        )
        if "dt" in self.config:
            self.model.opt.timestep = float(self.config["dt"])
        self.handles = legacy._two_link_handles(self.mujoco, self.model, self.config)
        self.shoulder_body_id = self.mujoco.mj_name2id(
            self.model, self.mujoco.mjtObj.mjOBJ_BODY, "link1"
        )
        self.elbow_body_id = self.mujoco.mj_name2id(
            self.model, self.mujoco.mjtObj.mjOBJ_BODY, "link2"
        )
        legacy._set_two_link_state(self.data, self.handles, self.initial_q)
        self.mujoco.mj_forward(self.model, self.data)
        self.logger = RunLogger(
            "lab03_2dof",
            self.config,
            config_path=Path(self.scenario.config_path),
            output_dir=self.output_dir,
            seed=self.seed,
        )
        self.trajectory = build_trajectory(
            dict(self.config.get("trajectory", {"type": "minimum_jerk", "start": 0.0, "end": 1.0}))
        )
        controller = dict(self.config.get("tracking_controller", {}))
        torque_limit = legacy._pair(controller.get("torque_limit", [50.0, 40.0]), "torque_limit")
        self.live_tuning = legacy._two_link_live_tuning(
            self.config,
            self.mode,
            controller,
            torque_limit,
            self.target_xy_goal,
            self.events,
        )
        self.setup_camera()
        self.camera.lookat[:] = (0.15, 0.0, 0.1)
        self.camera.distance = 2.6

    def step(self) -> dict[str, float]:
        self._require_ready()
        self.events.set_time(self.time)
        q, qdot = legacy._two_link_state(self.data, self.handles)
        target = self.trajectory.evaluate(self.time)
        controller = dict(self.config.get("tracking_controller", {}))
        torque_limit = legacy._pair(controller.get("torque_limit", [50.0, 40.0]), "torque_limit")
        target_xy, target_xdot = legacy._two_link_target_xy_command(
            start_xy=self.start_xy,
            goal_xy=self.target_xy_goal,
            alpha=target.position,
            alpha_dot=target.velocity,
            time=self.time,
            waypoints=self.target_waypoints,
            live_tuning=self.live_tuning,
        )
        if self.mode in legacy.DLS_MODES:
            command = legacy._dls_task_space_command(
                q=q,
                qdot=qdot,
                target_q_state=self.dls_target_q,
                target_xy=target_xy,
                target_xdot=target_xdot,
                time=self.time,
                dt=self.timestep,
                geometry=self.geometry,
                controller_config=controller,
                live_tuning=self.live_tuning,
                torque_limit=torque_limit,
                condition_aware=self.mode in legacy.CONDITION_AWARE_DLS_MODES
                or bool(controller.get("condition_aware_damping", False)),
            )
            self.dls_target_q = list(command["target_q"])
        elif self.mode in legacy.TASK_SPACE_MODES:
            command = legacy._task_space_command(
                q=q,
                qdot=qdot,
                target_xy=target_xy,
                target_xdot=target_xdot,
                geometry=self.geometry,
                controller_config=controller,
                live_tuning=self.live_tuning,
                torque_limit=torque_limit,
            )
        else:
            command = legacy._joint_space_command(
                q=q,
                qdot=qdot,
                start_q=self.initial_q,
                goal_q=self.target_q_goal,
                alpha=target.position,
                alpha_dot=target.velocity,
                geometry=self.geometry,
                controller_config=controller,
                live_tuning=self.live_tuning,
                torque_limit=torque_limit,
            )
        scripted = legacy._two_link_disturbance_torque(self.config, self.time)
        if self.time >= self.manual_until:
            self.manual_tau = [0.0, 0.0]
        disturbance = [scripted[index] + self.manual_tau[index] for index in range(2)]
        total_tau = [command["tau"][index] + disturbance[index] for index in range(2)]
        for index, actuator_id in enumerate(self.handles["actuator_ids"]):
            self.data.ctrl[actuator_id] = total_tau[index]
        self.mujoco.mj_step(self.model, self.data)
        q, qdot = legacy._two_link_state(self.data, self.handles)
        hand = list(forward_kinematics(q, self.geometry))
        hand_velocity = list(end_effector_velocity(q, qdot, self.geometry))
        joint_error = [command["target_q"][index] - q[index] for index in range(2)]
        task_error = [command["target_xy"][index] - hand[index] for index in range(2)]
        condition = legacy._cap_infinite(jacobian_condition_number(q, self.geometry))
        self.last_hand = hand
        self.last_target = list(command["target_xy"])
        self.last_condition = condition
        telemetry = {
            "time": self.time,
            "hand_x": hand[0],
            "hand_y": hand[1],
            "target_x": command["target_xy"][0],
            "target_y": command["target_xy"][1],
            "error": legacy._norm(
                task_error
                if self.mode in legacy.TASK_SPACE_MODES | legacy.DLS_MODES
                else joint_error
            ),
            "condition": condition,
            "force": max(abs(value) for value in total_tau),
            "velocity": legacy._norm(hand_velocity),
        }
        self.logger.record(
            time=self.time,
            mode=self.mode,
            q=q,
            qdot=qdot,
            target_q=command["target_q"],
            joint_error=joint_error,
            joint_error_norm=legacy._norm(joint_error),
            x_ee=hand,
            xdot_ee=hand_velocity,
            target_x_ee=command["target_xy"],
            target_xdot_ee=command.get("target_xdot", [0.0, 0.0]),
            task_error=task_error,
            task_error_norm=legacy._norm(task_error),
            tau_cmd=command["tau"],
            tau_scripted_disturbance=scripted,
            tau_manual_disturbance=self.manual_tau,
            tau_disturbance=disturbance,
            tau_total=total_tau,
            current_proxy=command["tau"],
            jacobian_determinant=jacobian_determinant(q, self.geometry),
            manipulability=manipulability(q, self.geometry),
            jacobian_condition=condition,
            disturbance_active=float(any(abs(value) > 1e-12 for value in disturbance)),
            tuned_kp=command["kp"],
            tuned_kd=command["kd"],
            tuned_torque_limit=command["torque_limit"],
            **legacy._dls_log_fields(command),
        )
        return telemetry

    def reset(self) -> None:
        self._require_ready()
        self.mujoco.mj_resetData(self.model, self.data)
        legacy._set_two_link_state(self.data, self.handles, self.initial_q)
        self.dls_target_q = list(self.initial_q)
        self.manual_tau = [0.0, 0.0]
        self.manual_until = 0.0
        self.mujoco.mj_forward(self.model, self.data)

    def apply_action(self, name: str, value: Any = None) -> None:
        self._require_ready()
        tuning_names = {spec.name for spec in self.live_tuning.specs}
        if name in tuning_names:
            self.live_tuning.set_value(name, float(value))
        elif name in {"shoulder_pulse", "elbow_pulse"}:
            interaction = dict(self.config.get("interaction", {}))
            configured = legacy._pair(
                interaction.get("joint_disturbance_torque", [0.14, 0.16]),
                "joint_disturbance_torque",
            )
            index = 0 if name == "shoulder_pulse" else 1
            self.manual_tau = [0.0, 0.0]
            self.manual_tau[index] = configured[index]
            self.manual_until = self.time + float(
                interaction.get("joint_disturbance_duration", 0.3)
            )
            self.events.record(
                "button", name, self.manual_tau[index], label=name.replace("_", " ").title()
            )
        elif name == "restore_defaults":
            self.live_tuning.reset()
        else:
            self._camera_action(name, value)

    def add_semantic_overlays(self, scene: Any) -> None:
        current = [self.last_hand[0], self.last_hand[1], 0.13]
        target = [self.last_target[0], self.last_target[1], 0.13]
        outer_reach = self.geometry.link1 + self.geometry.link2
        inner_reach = abs(self.geometry.link1 - self.geometry.link2)
        add_circle(
            self.mujoco,
            scene,
            [0.0, 0.0, 0.065],
            radius=outer_reach,
            width=0.006,
            rgba=[0.22, 0.42, 0.68, 0.50],
        )
        add_circle(
            self.mujoco,
            scene,
            [0.0, 0.0, 0.066],
            radius=inner_reach,
            width=0.004,
            rgba=[0.22, 0.42, 0.68, 0.35],
        )
        shoulder = list(self.data.xpos[self.shoulder_body_id])
        elbow = list(self.data.xpos[self.elbow_body_id])
        add_digit_marker(
            self.mujoco,
            scene,
            [shoulder[0] - 0.10, shoulder[1] + 0.10, 0.13],
            1,
        )
        add_digit_marker(
            self.mujoco,
            scene,
            [elbow[0], elbow[1] + 0.11, 0.13],
            2,
        )
        add_dashed_segment(
            self.mujoco,
            scene,
            current,
            target,
            width=0.007,
            rgba=[0.75, 0.52, 0.99, 0.75],
        )
        add_sphere(self.mujoco, scene, current, radius=0.034, rgba=[0.13, 0.83, 0.93, 0.95])
        add_box(
            self.mujoco,
            scene,
            target,
            half_size=[0.034, 0.034, 0.034],
            rgba=[0.75, 0.52, 0.99, 0.95],
            rotation=[0.707, -0.707, 0.0, 0.707, 0.707, 0.0, 0.0, 0.0, 1.0],
        )
        threshold = float(
            dict(self.config.get("viewer_guides", {})).get("condition_threshold", 20.0)
        )
        if self.last_condition >= threshold:
            add_sphere(self.mujoco, scene, current, radius=0.065, rgba=[0.98, 0.45, 0.52, 0.25])
            add_circle(
                self.mujoco,
                scene,
                current,
                radius=0.075,
                width=0.008,
                rgba=[0.98, 0.45, 0.52, 0.90],
            )
        for torque, position in zip(self.manual_tau, (shoulder, elbow)):
            if abs(torque) <= 1e-6:
                continue
            direction = 1.0 if torque > 0.0 else -1.0
            start = [position[0], position[1], 0.17]
            end = [position[0], position[1] + direction * 0.20, 0.17]
            add_arrow(
                self.mujoco,
                scene,
                start,
                end,
                width=0.014,
                rgba=[0.98, 0.45, 0.52, 0.98],
            )

    def finalize(self, recorder: ReplayRecorder, *, status: str) -> Path:
        self._require_ready()
        controller = dict(self.config.get("tracking_controller", {}))
        torque_limit = legacy._pair(controller.get("torque_limit", [50.0, 40.0]), "torque_limit")
        self.logger.replay = recorder
        output = self.logger.save_with_artifacts(
            summary={**legacy._two_link_summary(self.logger.rows), **self.events.summary()},
            notes=legacy._two_link_notes(self.config),
            interaction_events=self.events.events() or None,
            learner_snapshot={"slider_values": self.live_tuning.snapshot()},
            learner_tuned_config=learner_tuned_config(
                self.config,
                legacy._two_link_learner_tuned_updates(
                    self.config,
                    self.live_tuning,
                    mode=self.mode,
                    torque_limit=torque_limit,
                    target_q_goal=self.target_q_goal,
                    target_xy_goal=self.target_xy_goal,
                ),
            ),
            run_status=status,
            finalize=False,
        )
        legacy._save_two_link_plots(output, self.logger.rows, self.scenario.plot_preset)
        self.logger.finalize_artifacts()
        return output

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.close_renderer()

    def _camera_action(self, name: str, value: Any) -> None:
        if name == "reset_camera":
            self.reset_camera()
        elif name in {"orbit", "pan"}:
            getattr(self, name)(float(value[0]), float(value[1]))
        elif name == "zoom":
            self.zoom(float(value))
        else:
            raise KeyError(f"Unsupported Lab03 action: {name}")

    def _require_ready(self) -> None:
        if self.data is None:
            raise RuntimeError("Lab03 two-link adapter is not prepared.")
