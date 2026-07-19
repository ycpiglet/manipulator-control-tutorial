"""Integrated Panda adapter for joint, Cartesian, and virtual-wall labs."""

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
    add_sphere,
    add_wall_grid,
)
from mclab.labs import lab04_panda as legacy
from mclab.sim.interaction import InteractionLog, learner_tuned_config
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import load_model_and_data
from mclab.trajectories import build_trajectory

_LEARNER_CAMERA_DISTANCE = 1.7


class _TargetOffset:
    def __init__(self, config: dict[str, Any]) -> None:
        interaction = dict(config.get("interaction", {}))
        self.enabled = bool(interaction.get("target_nudge", False))
        self.step = abs(float(interaction.get("target_step", 0.025)))
        self.limit = abs(float(interaction.get("target_limit", 0.10)))
        self.offset = 0.0

    def value(self) -> float:
        return self.offset

    def adjust(self, direction: float) -> float:
        self.offset = max(-self.limit, min(self.limit, self.offset + direction * self.step))
        return self.offset


class Lab04Adapter(MujocoRenderMixin):
    """Run all Panda modes in the common threaded SimulationSession."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None = None,
        safe_mode: bool = False,
        seed: int | None = None,
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
        self.mode = str(self.config.get("mode", "joint_trajectory")).lower()
        self.home_q = legacy._float_list(self.config.get("home_q", legacy.DEFAULT_HOME_Q), 7)
        self.finger_q = legacy._float_list(self.config.get("finger_q", legacy.DEFAULT_FINGER_Q), 2)
        self.controlled_joint = int(self.config.get("controlled_joint_index", 3))
        self.target_offset = _TargetOffset(self.config)
        self.cartesian_nudge = legacy._target_nudge_is_cartesian(self.config, self.mode)
        self.initial_hand = [0.0, 0.0, 0.0]
        self.last_hand = [0.0, 0.0, 0.0]
        self.last_target = [0.0, 0.0, 0.0]
        self.last_wall = 10.0
        self.last_wall_force = [0.0, 0.0, 0.0]
        self.last_penetration = 0.0
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
            self.config.get(
                "model_path",
                "third_party/mujoco_menagerie/franka_emika_panda/scene.xml",
            )
        )
        legacy._configure_timestep(self.model, self.config)
        self.handles = legacy._build_handles(self.mujoco, self.model, self.config)
        legacy._set_initial_state(self.data, self.home_q, self.finger_q)
        self.mujoco.mj_forward(self.model, self.data)
        self.initial_hand, _, _ = legacy._end_effector_state(
            self.mujoco, self.model, self.data, self.handles
        )
        self.last_hand = list(self.initial_hand)
        self.last_target = list(self.initial_hand)
        self.trajectory = build_trajectory(legacy._trajectory_config(self.config, self.home_q))
        self.live_tuning = legacy._live_tuning(self.config, self.events)
        self.logger = RunLogger(
            "lab04_panda",
            self.config,
            config_path=Path(self.scenario.config_path),
            output_dir=self.output_dir,
            seed=self.seed,
        )
        self._initialize_semantic_state()
        self.setup_camera()
        self.camera.distance = _LEARNER_CAMERA_DISTANCE

    def _initialize_semantic_state(self) -> None:
        """Show configured teaching guides before the first physics step."""

        cartesian_modes = {"cartesian_reach", "task_space", "ee_reach"}
        wall_modes = {"impedance_wall", "virtual_wall", "wall"}
        if self.mode in cartesian_modes or (
            self.mode in wall_modes and legacy._wall_cartesian_target_enabled(self.config)
        ):
            self.last_target = legacy._cartesian_target_position(
                self.config,
                self.live_tuning,
                self.initial_hand,
                1.0,
                time=self.time,
            )
        if self.mode in wall_modes:
            wall_config = legacy._wall_config(self.config, self.live_tuning)
            self.last_wall = float(wall_config.get("wall_x", self.last_target[0]))
            self.last_penetration = max(0.0, self.last_hand[0] - self.last_wall)

    def step(self) -> dict[str, float]:
        self._require_ready()
        self.events.set_time(self.time)
        target_q = self.home_q.copy()
        target_state = self.trajectory.evaluate(self.time)
        button_offset = self.target_offset.value()
        joint_button_offset = 0.0 if self.cartesian_nudge else button_offset
        target_x_button_offset = button_offset if self.cartesian_nudge else 0.0
        tuned_joint_offset = self.live_tuning.value("joint_target_offset", 0.0)
        target_q[self.controlled_joint] = (
            target_state.position + joint_button_offset + tuned_joint_offset
        )
        hand, hand_velocity, jacobian = legacy._end_effector_state(
            self.mujoco, self.model, self.data, self.handles
        )
        wall_force = [0.0, 0.0, 0.0]
        wall_spring = [0.0, 0.0, 0.0]
        wall_damping = [0.0, 0.0, 0.0]
        wall_retreat = 0.0
        target_hand = list(hand)
        cartesian_error = [0.0, 0.0, 0.0]
        wall_config = legacy._wall_config(self.config, self.live_tuning)
        tracks_cartesian = self.mode in {"cartesian_reach", "task_space", "ee_reach"}
        if tracks_cartesian:
            q_before = [float(self.data.qpos[index]) for index in self.handles["qpos_indices"]]
            target_hand = legacy._cartesian_target_position(
                self.config,
                self.live_tuning,
                self.initial_hand,
                float(target_state.position),
                time=self.time,
            )
            target_hand[0] += target_x_button_offset
            cartesian_error = [target_hand[index] - hand[index] for index in range(3)]
            target_q = legacy._apply_cartesian_target_offset(
                q_before,
                jacobian,
                cartesian_error,
                self.config,
                self.live_tuning,
            )
        if self.mode in {"impedance_wall", "virtual_wall", "wall"}:
            if legacy._wall_cartesian_target_enabled(self.config):
                tracks_cartesian = True
                target_hand = legacy._cartesian_target_position(
                    self.config,
                    self.live_tuning,
                    self.initial_hand,
                    1.0,
                    time=self.time,
                )
                target_hand[0] += target_x_button_offset
                cartesian_error = [target_hand[index] - hand[index] for index in range(3)]
                target_q = legacy._apply_cartesian_target_offset(
                    target_q,
                    jacobian,
                    cartesian_error,
                    self.config,
                    self.live_tuning,
                )
            wall_force, wall_spring, wall_damping = legacy._virtual_wall_force_components(
                hand, hand_velocity, wall_config
            )
            wall_retreat = legacy._wall_retreat_distance(hand, wall_force, wall_config)
            target_q = legacy._apply_wall_target_offset(
                target_q,
                jacobian,
                hand,
                wall_force,
                self.config,
                wall_config,
            )
        target_q = legacy._clip_to_ctrl_range(self.model, self.handles["actuator_ids"], target_q)
        legacy._apply_arm_control(self.data, self.handles["actuator_ids"], target_q, self.config)
        self.mujoco.mj_step(self.model, self.data)
        q = [float(self.data.qpos[index]) for index in self.handles["qpos_indices"]]
        qdot = [float(self.data.qvel[index]) for index in self.handles["dof_indices"]]
        hand, hand_velocity, _ = legacy._end_effector_state(
            self.mujoco, self.model, self.data, self.handles
        )
        actuator_force = [
            float(self.data.actuator_force[index]) for index in self.handles["actuator_ids"]
        ]
        errors = [target_q[index] - q[index] for index in range(7)]
        wall_x = float(wall_config.get("wall_x", target_hand[0]))
        penetration = max(0.0, hand[0] - float(wall_config.get("wall_x", 10.0)))
        if tracks_cartesian:
            cartesian_error = [target_hand[index] - hand[index] for index in range(3)]
        else:
            target_hand = list(hand)
            cartesian_error = [0.0, 0.0, 0.0]
        error_norm = legacy._norm(errors)
        cartesian_error_norm = legacy._norm(cartesian_error)
        target_wall_gap = target_hand[0] - wall_x
        wall_phase = legacy._wall_phase(
            target_wall_gap_m=target_wall_gap,
            wall_penetration_m=penetration,
            wall_force_x=wall_force[0],
        )
        self.last_hand = list(hand)
        self.last_target = list(target_hand)
        self.last_wall = wall_x
        self.last_wall_force = list(wall_force)
        self.last_penetration = penetration
        telemetry = {
            "time": self.time,
            "hand_x": hand[0],
            "hand_y": hand[1],
            "hand_z": hand[2],
            "target_x": target_hand[0],
            "target_y": target_hand[1],
            "target_z": target_hand[2],
            "error": 100.0 * cartesian_error_norm if tracks_cartesian else error_norm,
            "force": wall_force[0]
            if self.mode in {"impedance_wall", "virtual_wall", "wall"}
            else max(abs(value) for value in actuator_force),
            "wall_penetration": 100.0 * penetration,
            "wall_x": wall_x,
            "wall_force_x": wall_force[0],
            "velocity": legacy._norm(hand_velocity),
        }
        kt = float(self.config.get("torque_constant", 1.0))
        self.logger.record(
            time=self.time,
            q=q,
            qdot=qdot,
            target_q=target_q,
            ctrl=[float(self.data.ctrl[index]) for index in self.handles["actuator_ids"]],
            tau_cmd=actuator_force,
            current_proxy=[force / kt for force in actuator_force],
            x_ee=hand,
            xdot_ee=hand_velocity,
            target_x_ee=target_hand,
            cartesian_error=cartesian_error,
            cartesian_error_norm=cartesian_error_norm,
            cartesian_error_cm=100.0 * cartesian_error_norm,
            position_error=errors,
            error_norm=error_norm,
            force_virtual=wall_force,
            force_virtual_spring=wall_spring,
            force_virtual_damping=wall_damping,
            wall_penetration=penetration,
            wall_penetration_cm=100.0 * penetration,
            wall_retreat=wall_retreat,
            wall_retreat_cm=100.0 * wall_retreat,
            tuned_target_x=self.live_tuning.value("target_x", target_hand[0]),
            tuned_target_y=self.live_tuning.value("target_y", target_hand[1]),
            tuned_target_z=self.live_tuning.value("target_z", target_hand[2]),
            target_wall_gap_m=target_wall_gap,
            target_wall_gap_cm=100.0 * target_wall_gap,
            wall_phase=wall_phase,
            target_x_nudge=target_x_button_offset,
            joint_target_nudge=joint_button_offset,
            tuned_joint_target_offset=tuned_joint_offset,
            tuned_wall_x=wall_x,
            tuned_wall_stiffness=float(wall_config.get("stiffness", 0.0)),
            tuned_wall_damping=float(wall_config.get("damping", 0.0)),
            tuned_wall_retreat_gain=float(wall_config.get("cartesian_retreat_gain", 0.0)),
            tuned_wall_force_retreat_gain=float(wall_config.get("force_retreat_gain", 0.0)),
            tuned_cartesian_gain=self.live_tuning.value(
                "cartesian_gain",
                float(dict(self.config.get("cartesian_target", {})).get("gain", 1.0)),
            ),
        )
        return telemetry

    def reset(self) -> None:
        self._require_ready()
        self.mujoco.mj_resetData(self.model, self.data)
        legacy._set_initial_state(self.data, self.home_q, self.finger_q)
        self.target_offset.offset = 0.0
        self.mujoco.mj_forward(self.model, self.data)

    def reset_camera(self) -> None:
        """Restore a closer teaching view that keeps the Panda and wall legible."""

        super().reset_camera()
        self.camera.distance = _LEARNER_CAMERA_DISTANCE

    def apply_action(self, name: str, value: Any = None) -> None:
        self._require_ready()
        tuning_names = {spec.name for spec in self.live_tuning.specs}
        if name in tuning_names:
            self.live_tuning.set_value(name, float(value))
        elif name in {"target_x_decrease", "target_x_increase"}:
            direction = -1.0 if name == "target_x_decrease" else 1.0
            offset = self.target_offset.adjust(direction)
            self.events.record("button", name, offset, label=name.replace("_", " ").title())
        elif name == "restore_defaults":
            self.live_tuning.reset()
            self.target_offset.offset = 0.0
        elif name == "reset_camera":
            self.reset_camera()
        elif name in {"orbit", "pan"}:
            getattr(self, name)(float(value[0]), float(value[1]))
        elif name == "zoom":
            self.zoom(float(value))
        else:
            raise KeyError(f"Unsupported Lab04 action: {name}")

    def add_semantic_overlays(self, scene: Any) -> None:
        add_dashed_segment(
            self.mujoco,
            scene,
            self.last_hand,
            self.last_target,
            width=0.006,
            rgba=[0.75, 0.52, 0.99, 0.78],
        )
        add_sphere(
            self.mujoco,
            scene,
            self.last_hand,
            radius=0.034,
            rgba=[0.13, 0.83, 0.93, 0.96],
        )
        add_box(
            self.mujoco,
            scene,
            self.last_target,
            half_size=[0.032, 0.032, 0.032],
            rgba=[0.75, 0.52, 0.99, 0.96],
            rotation=[0.707, -0.707, 0.0, 0.707, 0.707, 0.0, 0.0, 0.0, 1.0],
        )
        if self.mode in {"impedance_wall", "virtual_wall", "wall"}:
            add_box(
                self.mujoco,
                scene,
                [self.last_wall, 0.0, 0.55],
                half_size=[0.006, 0.55, 0.55],
                rgba=[0.98, 0.75, 0.14, 0.11],
            )
            add_wall_grid(
                self.mujoco,
                scene,
                self.last_wall,
                y_extent=0.55,
                z_min=0.0,
                z_max=1.10,
                rgba=[0.98, 0.75, 0.14, 0.72],
            )
            contact = [self.last_wall, self.last_hand[1], self.last_hand[2]]
            if self.last_penetration > 0.0:
                add_circle(
                    self.mujoco,
                    scene,
                    contact,
                    radius=0.055,
                    width=0.008,
                    rgba=[0.98, 0.45, 0.52, 0.98],
                    axes=((0, 1, 0), (0, 0, 1)),
                )
            if abs(self.last_wall_force[0]) > 1e-6:
                force_length = min(0.35, max(0.08, 0.004 * abs(self.last_wall_force[0])))
                force_sign = 1.0 if self.last_wall_force[0] > 0.0 else -1.0
                end = [
                    contact[0] + force_sign * force_length,
                    self.last_hand[1],
                    self.last_hand[2],
                ]
                add_arrow(
                    self.mujoco,
                    scene,
                    contact,
                    end,
                    width=0.014,
                    rgba=[0.98, 0.45, 0.52, 0.98],
                )

    def finalize(self, recorder: ReplayRecorder, *, status: str) -> Path:
        self._require_ready()
        self.logger.replay = recorder
        output = self.logger.save_with_artifacts(
            summary={**legacy._summary(self.logger.rows), **self.events.summary()},
            notes=legacy._notes(self.config),
            interaction_events=self.events.events() or None,
            learner_snapshot={
                "slider_values": self.live_tuning.snapshot(),
                "target_x_nudge": self.target_offset.value(),
            },
            learner_tuned_config=learner_tuned_config(
                self.config,
                legacy._learner_tuned_updates(
                    self.config,
                    self.live_tuning,
                    self.target_offset,
                    cartesian_target_nudge=self.cartesian_nudge,
                ),
            ),
            run_status=status,
        )
        legacy._save_plots(output, self.logger.rows, self.scenario.plot_preset)
        self.logger.finalize_artifacts()
        return output

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.close_renderer()

    def _require_ready(self) -> None:
        if self.data is None:
            raise RuntimeError("Lab04 adapter is not prepared.")
