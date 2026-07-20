"""MuJoCo adapters used by the integrated desktop session."""

from __future__ import annotations

from copy import deepcopy
from collections import deque
from pathlib import Path
from random import Random
from typing import Any

import numpy as np

from mclab.application.artifacts import ReplayFrame, ReplayRecorder
from mclab.application.catalog import ScenarioDefinition
from mclab.application.rendering import (
    add_arrow,
    add_box,
    add_circle,
    add_dashed_segment,
    add_segment,
    add_sphere,
    add_wall_grid,
    close_mujoco_renderer,
    create_mujoco_renderer,
    spring_polyline,
)
from mclab.analysis.metrics import step_response_metrics
from mclab.config import resolve_project_path
from mclab.controllers.pid import PIDController
from mclab.sim.logging import RunLogger
from mclab.sim.mujoco_utils import load_model_and_data
from mclab.sim.one_dof import (
    configure_slider_plant,
    mechanical_energy,
    reset_slider_plant_state,
    slider_state,
)
from mclab.trajectories import build_trajectory


class Lab01Adapter:
    """Interactive Lab01 physics behind the common SimulationSession API."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None = None,
        safe_mode: bool = False,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        self.scenario = scenario
        self.config = deepcopy(config_override if config_override is not None else scenario.config)
        self.output_dir = Path(output_dir) if output_dir else None
        self.safe_mode = safe_mode
        self.mujoco: Any | None = None
        self.model: Any | None = None
        self.data: Any | None = None
        self.handles: Any | None = None
        self.renderer: Any | None = None
        self.camera: Any | None = None
        self.logger: RunLogger | None = None
        self.parameters = {
            "mass": float(self.config.get("mass", 1.0)),
            "damping": float(self.config.get("damping", 0.0)),
            "stiffness": float(self.config.get("stiffness", 50.0)),
        }
        self.defaults = dict(self.parameters)
        self.spring_reference = float(self.config.get("spring_reference", 0.0))
        self.manual_force = 0.0
        self.force_until = 0.0
        self.events: list[dict[str, Any]] = []
        self.position_trail: deque[float] = deque(maxlen=18)
        self._closed = False

    @property
    def time(self) -> float:
        return float(self.data.time) if self.data is not None else 0.0

    @property
    def timestep(self) -> float:
        if self.model is not None:
            return float(self.model.opt.timestep)
        return float(self.config.get("dt", 0.002))

    def prepare(self) -> None:
        if self.data is not None:
            return
        model_path = self.config.get("model_path", "models/lab01_msd/scene.xml")
        self.mujoco, self.model, self.data = load_model_and_data(model_path)
        self.handles = configure_slider_plant(self.mujoco, self.model, self.data, self.config)
        self.logger = RunLogger(
            "lab01_msd",
            self.config,
            config_path=Path(self.scenario.config_path),
            output_dir=self.output_dir,
        )
        self.camera = self.mujoco.MjvCamera()
        self.camera.type = self.mujoco.mjtCamera.mjCAMERA_FREE
        self.reset_camera()

    def step(self) -> dict[str, float]:
        self._require_ready()
        assert self.model is not None and self.data is not None and self.handles is not None
        if self.time >= self.force_until:
            self.manual_force = 0.0
        self.model.body_mass[self.handles.body_id] = self.parameters["mass"]
        self.model.dof_damping[self.handles.dof_adr] = self.parameters["damping"]
        self.model.jnt_stiffness[self.handles.joint_id] = self.parameters["stiffness"]
        self.data.ctrl[self.handles.actuator_id] = self.manual_force
        self.mujoco.mj_step(self.model, self.data)
        position, velocity, acceleration = slider_state(self.data, self.handles)
        self._remember_position(position)
        kinetic, potential, total = mechanical_energy(
            position=position,
            velocity=velocity,
            mass=self.parameters["mass"],
            stiffness=self.parameters["stiffness"],
            spring_reference=self.spring_reference,
        )
        telemetry = {
            "time": self.time,
            "position": position,
            "velocity": velocity,
            "acceleration": acceleration,
            "force": self.manual_force,
            "energy": total,
        }
        assert self.logger is not None
        self.logger.record(
            **telemetry,
            control_force=self.manual_force,
            tuned_mass=self.parameters["mass"],
            tuned_damping=self.parameters["damping"],
            tuned_stiffness=self.parameters["stiffness"],
            kinetic_energy=kinetic,
            potential_energy=potential,
            total_energy=total,
        )
        return telemetry

    def reset(self) -> None:
        self._require_ready()
        assert self.model is not None and self.data is not None and self.handles is not None
        reset_slider_plant_state(self.mujoco, self.model, self.data, self.handles, self.config)
        self.manual_force = 0.0
        self.force_until = 0.0
        self.position_trail.clear()
        self._remember_position(float(self.data.qpos[self.handles.qpos_adr]))

    def apply_action(self, name: str, value: Any = None) -> None:
        self._require_ready()
        if name in self.parameters:
            self.parameters[name] = float(value)
        elif name in {"pull", "push"}:
            interaction = dict(self.config.get("interaction", {}))
            magnitude = abs(float(interaction.get("force", 80.0)))
            self.manual_force = -magnitude if name == "pull" else magnitude
            self.force_until = self.time + float(interaction.get("duration", 0.35))
        elif name == "restore_defaults":
            self.parameters = dict(self.defaults)
        elif name == "reset_camera":
            self.reset_camera()
        elif name == "orbit":
            dx, dy = value
            self.orbit(float(dx), float(dy))
        elif name == "pan":
            dx, dy = value
            self.pan(float(dx), float(dy))
        elif name == "zoom":
            self.zoom(float(value))
        else:
            raise KeyError(f"Unsupported Lab01 action: {name}")
        if name not in {"orbit", "pan", "zoom", "reset_camera"}:
            kind = "slider" if name in self.parameters else "button"
            self.events.append(
                {"time": self.time, "kind": kind, "name": name, "label": name, "value": value}
            )

    def state_vectors(self) -> tuple[Any, Any, Any]:
        self._require_ready()
        assert self.data is not None
        return self.data.qpos, self.data.qvel, self.data.ctrl

    def restore_frame(self, frame: ReplayFrame) -> None:
        self._require_ready()
        assert self.model is not None and self.data is not None
        _copy_vector(self.data.qpos, frame.qpos)
        _copy_vector(self.data.qvel, frame.qvel)
        _copy_vector(self.data.ctrl, frame.ctrl)
        self.data.time = frame.time
        self.mujoco.mj_forward(self.model, self.data)
        self._remember_position(float(self.data.qpos[self.handles.qpos_adr]))

    def render(self, width: int, height: int) -> np.ndarray:
        self._require_ready()
        if self.safe_mode:
            return _safe_frame(width, height)
        assert self.model is not None and self.data is not None
        width, height = _render_size(self.model, width, height)
        if self.renderer is None or self.renderer.width != width or self.renderer.height != height:
            if self.renderer is not None:
                close_mujoco_renderer(self.renderer)
            self.renderer = create_mujoco_renderer(
                self.mujoco,
                self.model,
                height=height,
                width=width,
            )
        self.renderer.update_scene(self.data, camera=self.camera)
        self._add_slider_overlays(self.renderer.scene)
        return np.asarray(self.renderer.render()).copy()

    def _add_slider_overlays(self, scene: Any) -> None:
        assert self.data is not None and self.handles is not None
        block_x = float(self.data.xpos[self.handles.body_id][0])
        target_x = float(self.parameters.get("target_position", self.spring_reference))
        foreground_y = -0.24
        diamond_rotation = [0.707, 0.0, 0.707, 0.0, 1.0, 0.0, -0.707, 0.0, 0.707]
        add_box(
            self.mujoco,
            scene,
            [target_x, foreground_y, 0.23],
            half_size=[0.045, 0.018, 0.045],
            rgba=[0.75, 0.52, 0.99, 0.95],
            rotation=diamond_rotation,
        )
        for index, position in enumerate(self.position_trail):
            alpha = 0.12 + 0.55 * (index + 1) / max(1, len(self.position_trail))
            add_sphere(
                self.mujoco,
                scene,
                [position, foreground_y, 0.23],
                radius=0.018,
                rgba=[0.13, 0.83, 0.93, alpha],
            )
        add_sphere(
            self.mujoco,
            scene,
            [block_x, foreground_y, 0.23],
            radius=0.035,
            rgba=[0.13, 0.83, 0.93, 1.0],
        )
        if "target_position" in self.parameters:
            _add_dashed_link(self.mujoco, scene, block_x, target_x, foreground_y)
        else:
            spring = spring_polyline(
                [-1.40, foreground_y, 0.08],
                [block_x - 0.19, foreground_y, 0.08],
            )
            for start, end in zip(spring, spring[1:]):
                add_segment(
                    self.mujoco,
                    scene,
                    start,
                    end,
                    width=0.014,
                    rgba=[0.98, 0.75, 0.14, 0.95],
                )
        damper_end = block_x - 0.19
        damper_mid = -1.05 + 0.55 * (damper_end + 1.05)
        add_segment(
            self.mujoco,
            scene,
            [-1.40, foreground_y, -0.13],
            [damper_mid, foreground_y, -0.13],
            width=0.035,
            rgba=[0.38, 0.44, 0.54, 1.0],
        )
        add_segment(
            self.mujoco,
            scene,
            [damper_mid, foreground_y, -0.13],
            [damper_end, foreground_y, -0.13],
            width=0.014,
            rgba=[0.92, 0.95, 0.98, 1.0],
        )
        force = float(self.data.ctrl[self.handles.actuator_id])
        if abs(force) > 0.05:
            length = max(0.20, min(0.70, abs(force) * 0.007))
            add_arrow(
                self.mujoco,
                scene,
                [block_x, foreground_y, 0.38],
                [block_x + (length if force > 0 else -length), foreground_y, 0.38],
                width=0.025,
                rgba=[0.98, 0.45, 0.52, 1.0],
            )

    def _remember_position(self, position: float) -> None:
        if not self.position_trail or abs(position - self.position_trail[-1]) >= 0.018:
            self.position_trail.append(float(position))

    def reset_camera(self) -> None:
        if self.camera is None:
            return
        self.camera.lookat[:] = (0.0, 0.0, 0.0)
        self.camera.azimuth = 90.0
        self.camera.elevation = -20.0
        self.camera.distance = 3.2

    def orbit(self, dx: float, dy: float) -> None:
        if self.camera is None:
            return
        self.camera.azimuth += dx * 0.35
        self.camera.elevation = max(-89.0, min(30.0, self.camera.elevation + dy * 0.25))

    def pan(self, dx: float, dy: float) -> None:
        if self.camera is None:
            return
        scale = max(0.0005, float(self.camera.distance) * 0.0015)
        self.camera.lookat[0] -= dx * scale
        self.camera.lookat[2] += dy * scale

    def zoom(self, delta: float) -> None:
        if self.camera is None:
            return
        self.camera.distance = max(0.5, min(8.0, self.camera.distance * (1.0 - delta * 0.001)))

    def finalize(self, recorder: ReplayRecorder, *, status: str) -> Path:
        self._require_ready()
        assert self.logger is not None
        self.logger.replay = recorder
        rows = self.logger.rows
        max_position = max((abs(float(row.get("position", 0.0))) for row in rows), default=0.0)
        output = self.logger.save_with_artifacts(
            summary={
                "max_abs_position": max_position,
                "interaction_events": len(self.events),
            },
            notes=(
                "# Lab01 integrated session\n\nRecorded by the MCLab desktop SimulationSession.\n"
            ),
            interaction_events=self.events or None,
            learner_snapshot={"slider_values": dict(self.parameters)},
            learner_tuned_config={**self.config, **self.parameters},
            run_status=status,
            finalize=False,
        )
        from mclab.labs.lab01_msd import _save_plots

        _save_plots(output, rows, self.scenario.plot_preset)
        self.logger.finalize_artifacts()
        return output

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.renderer is not None:
            close_mujoco_renderer(self.renderer)
            self.renderer = None

    def _require_ready(self) -> None:
        if self.data is None or self.mujoco is None:
            raise RuntimeError("Lab01 adapter is not prepared.")


def _add_dashed_link(mujoco: Any, scene: Any, start_x: float, end_x: float, y: float) -> None:
    for index in range(0, 10, 2):
        first = start_x + (end_x - start_x) * index / 10
        last = start_x + (end_x - start_x) * (index + 1) / 10
        add_segment(
            mujoco,
            scene,
            [first, y, 0.08],
            [last, y, 0.08],
            width=0.012,
            rgba=[0.75, 0.52, 0.99, 0.92],
        )


class Lab02Adapter(Lab01Adapter):
    """PID slider plant using the same integrated session and transport."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        output_dir: str | Path | None = None,
        safe_mode: bool = False,
        seed: int | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            scenario,
            output_dir=output_dir,
            safe_mode=safe_mode,
            config_override=config_override,
        )
        controller = dict(self.config.get("controller", {}))
        target = dict(self.config.get("target", {}))
        limit = controller.get("output_limit", self.config.get("force_limit", 80.0))
        if isinstance(limit, (list, tuple)):
            limit = max(abs(float(item)) for item in limit)
        self.parameters = {
            "target_position": float(target.get("end", 0.2)),
            "kp": float(controller.get("kp", 40.0)),
            "ki": float(controller.get("ki", 0.0)),
            "kd": float(controller.get("kd", 4.0)),
            "output_limit": abs(float(limit or 80.0)),
        }
        self.defaults = dict(self.parameters)
        self.seed = seed
        self.random = Random(seed)
        self.controller: PIDController | None = None
        self.trajectory: Any | None = None
        self.delay_buffer: deque[float] = deque()
        self.delay_steps = 0

    def prepare(self) -> None:
        if self.data is not None:
            return
        model_path = self.config.get("model_path", "models/lab02_pid/scene.xml")
        self.mujoco, self.model, self.data = load_model_and_data(model_path)
        self.handles = configure_slider_plant(self.mujoco, self.model, self.data, self.config)
        self.logger = RunLogger(
            "lab02_pid",
            self.config,
            config_path=Path(self.scenario.config_path),
            output_dir=self.output_dir,
            seed=self.seed,
        )
        dt = float(self.config.get("dt", self.model.opt.timestep))
        controller = dict(self.config.get("controller", {}))
        self.controller = PIDController(
            kp=self.parameters["kp"],
            ki=self.parameters["ki"],
            kd=self.parameters["kd"],
            dt=dt,
            output_min=-self.parameters["output_limit"],
            output_max=self.parameters["output_limit"],
            integral_min=_optional_float(controller.get("integral_min")),
            integral_max=_optional_float(controller.get("integral_max")),
            anti_windup=bool(controller.get("anti_windup", True)),
        )
        self.trajectory = build_trajectory(
            dict(self.config.get("target", {"type": "step", "start": 0.0, "end": 0.2}))
        )
        self.delay_steps = max(0, int(round(float(self.config.get("control_delay", 0.0)) / dt)))
        self.delay_buffer = deque([0.0] * self.delay_steps, maxlen=self.delay_steps)
        self.camera = self.mujoco.MjvCamera()
        self.camera.type = self.mujoco.mjtCamera.mjCAMERA_FREE
        self.reset_camera()

    def step(self) -> dict[str, float]:
        self._require_ready()
        assert self.data is not None and self.handles is not None and self.controller is not None
        if self.time >= self.force_until:
            self.manual_force = 0.0
        position, velocity, _ = slider_state(self.data, self.handles)
        noise_std = float(self.config.get("measurement_noise_std", 0.0))
        measured = position + (self.random.gauss(0.0, noise_std) if noise_std else 0.0)
        target_state = self.trajectory.evaluate(self.time)
        self.controller.kp = self.parameters["kp"]
        self.controller.ki = self.parameters["ki"]
        self.controller.kd = self.parameters["kd"]
        self.controller.output_min = -self.parameters["output_limit"]
        self.controller.output_max = self.parameters["output_limit"]
        command = self.controller.compute(
            setpoint=self.parameters["target_position"],
            measurement=measured,
            measurement_rate=velocity,
        )
        if self.delay_steps:
            self.delay_buffer.append(command.value)
            control_force = self.delay_buffer[0]
        else:
            control_force = command.value
        total_force = control_force + self.manual_force
        self.data.ctrl[self.handles.actuator_id] = total_force
        self.mujoco.mj_step(self.model, self.data)
        position, velocity, acceleration = slider_state(self.data, self.handles)
        telemetry = {
            "time": self.time,
            "position": position,
            "velocity": velocity,
            "target_position": self.parameters["target_position"],
            "position_error": self.parameters["target_position"] - position,
            "force": total_force,
        }
        assert self.logger is not None
        self.logger.record(
            **telemetry,
            measured_position=measured,
            measurement_error=measured - position,
            acceleration=acceleration,
            target_velocity=target_state.velocity,
            control_force=control_force,
            manual_force=self.manual_force,
            total_force=total_force,
            tuned_kp=self.parameters["kp"],
            tuned_ki=self.parameters["ki"],
            tuned_kd=self.parameters["kd"],
            tuned_output_limit=self.parameters["output_limit"],
            control_unsaturated=command.unsaturated_value,
            pid_p=command.proportional,
            pid_i=command.integral,
            pid_d=command.derivative,
            saturated=float(command.saturated),
        )
        return telemetry

    def reset(self) -> None:
        super().reset()
        assert self.controller is not None
        self.controller.reset()
        self.delay_buffer.clear()
        self.delay_buffer.extend([0.0] * self.delay_steps)

    def finalize(self, recorder: ReplayRecorder, *, status: str) -> Path:
        self._require_ready()
        assert self.logger is not None
        self.logger.replay = recorder
        rows = self.logger.rows
        output = self.logger.save_with_artifacts(
            summary={**step_response_metrics(rows), "interaction_events": len(self.events)},
            notes="# Lab02 integrated PID session\n",
            interaction_events=self.events or None,
            learner_snapshot={"slider_values": dict(self.parameters)},
            learner_tuned_config={
                **self.config,
                "target": {
                    **dict(self.config.get("target", {})),
                    "end": self.parameters["target_position"],
                },
                "controller": {
                    **dict(self.config.get("controller", {})),
                    "kp": self.parameters["kp"],
                    "ki": self.parameters["ki"],
                    "kd": self.parameters["kd"],
                    "output_limit": self.parameters["output_limit"],
                },
            },
            run_status=status,
            finalize=False,
        )
        from mclab.labs.lab02_pid import _save_plots

        _save_plots(output, rows, self.scenario.plot_preset)
        self.logger.finalize_artifacts()
        return output


class MujocoReplayAdapter:
    """Render recorded MuJoCo state for any lab without recomputing physics."""

    def __init__(self, model_path: str | Path, *, safe_mode: bool = False) -> None:
        self.model_path = model_path
        self.safe_mode = safe_mode
        self.mujoco: Any | None = None
        self.model: Any | None = None
        self.data: Any | None = None
        self.renderer: Any | None = None
        self.camera: Any | None = None
        self.semantic: dict[str, float] = {}
        self._closed = False

    @property
    def time(self) -> float:
        return float(self.data.time) if self.data is not None else 0.0

    @property
    def timestep(self) -> float:
        return float(self.model.opt.timestep) if self.model is not None else 1.0 / 60.0

    def prepare(self) -> None:
        if self.data is not None:
            return
        self.mujoco, self.model, self.data = load_model_and_data(self.model_path)
        self.camera = self.mujoco.MjvCamera()
        self.mujoco.mjv_defaultFreeCamera(self.model, self.camera)

    def step(self) -> dict[str, float]:
        raise RuntimeError("Replay adapters do not step physics.")

    def reset(self) -> None:
        assert self.model is not None and self.data is not None
        self.mujoco.mj_resetData(self.model, self.data)

    def apply_action(self, name: str, value: Any = None) -> None:
        del name, value

    def state_vectors(self) -> tuple[Any, Any, Any]:
        assert self.data is not None
        return self.data.qpos, self.data.qvel, self.data.ctrl

    def restore_frame(self, frame: ReplayFrame) -> None:
        assert self.model is not None and self.data is not None
        _copy_vector(self.data.qpos, frame.qpos)
        _copy_vector(self.data.qvel, frame.qvel)
        _copy_vector(self.data.ctrl, frame.ctrl)
        self.data.time = frame.time
        self.semantic = dict(frame.semantic)
        self.mujoco.mj_forward(self.model, self.data)

    def render(self, width: int, height: int) -> np.ndarray:
        if self.safe_mode:
            return _safe_frame(width, height)
        assert self.model is not None and self.data is not None
        width, height = _render_size(self.model, width, height)
        if self.renderer is None or self.renderer.width != width or self.renderer.height != height:
            if self.renderer is not None:
                close_mujoco_renderer(self.renderer)
            self.renderer = create_mujoco_renderer(
                self.mujoco,
                self.model,
                height=height,
                width=width,
            )
        self.renderer.update_scene(self.data, camera=self.camera)
        self._add_semantic_overlays(self.renderer.scene)
        return np.asarray(self.renderer.render()).copy()

    def _add_semantic_overlays(self, scene: Any) -> None:
        semantic = self.semantic
        if "position" in semantic:
            position = float(semantic["position"])
            target = float(semantic.get("target_position", 0.0))
            y = -0.24
            add_sphere(
                self.mujoco,
                scene,
                [position, y, 0.23],
                radius=0.035,
                rgba=[0.13, 0.83, 0.93, 1.0],
            )
            add_box(
                self.mujoco,
                scene,
                [target, y, 0.23],
                half_size=[0.045, 0.018, 0.045],
                rgba=[0.75, 0.52, 0.99, 0.95],
                rotation=[0.707, 0.0, 0.707, 0.0, 1.0, 0.0, -0.707, 0.0, 0.707],
            )
            if "lab01" in str(self.model_path):
                spring = spring_polyline([-1.40, y, 0.08], [position - 0.19, y, 0.08])
                for start, end in zip(spring, spring[1:]):
                    add_segment(
                        self.mujoco,
                        scene,
                        start,
                        end,
                        width=0.014,
                        rgba=[0.98, 0.75, 0.14, 0.95],
                    )
            else:
                _add_dashed_link(self.mujoco, scene, position, target, y)
            force = float(semantic.get("force", 0.0))
            if abs(force) > 0.05:
                length = max(0.20, min(0.70, abs(force) * 0.007))
                add_arrow(
                    self.mujoco,
                    scene,
                    [position, y, 0.38],
                    [position + (length if force > 0 else -length), y, 0.38],
                    width=0.025,
                    rgba=[0.98, 0.45, 0.52, 1.0],
                )
        if "hand_x" in semantic:
            default_z = 0.13 if "lab03" in str(self.model_path) else 0.11
            hand = [
                semantic.get("hand_x", 0.0),
                semantic.get("hand_y", 0.0),
                semantic.get("hand_z", default_z),
            ]
            target = [
                semantic.get("target_x", hand[0]),
                semantic.get("target_y", hand[1]),
                semantic.get("target_z", hand[2]),
            ]
            add_dashed_segment(
                self.mujoco,
                scene,
                hand,
                target,
                width=0.007,
                rgba=[0.75, 0.52, 0.99, 0.75],
            )
            add_sphere(
                self.mujoco,
                scene,
                hand,
                radius=0.034,
                rgba=[0.13, 0.83, 0.93, 0.96],
            )
            add_box(
                self.mujoco,
                scene,
                target,
                half_size=[0.032, 0.032, 0.032],
                rgba=[0.75, 0.52, 0.99, 0.96],
                rotation=[0.707, -0.707, 0.0, 0.707, 0.707, 0.0, 0.0, 0.0, 1.0],
            )
            if float(semantic.get("condition", 0.0)) >= 20.0:
                add_sphere(
                    self.mujoco,
                    scene,
                    hand,
                    radius=0.065,
                    rgba=[0.98, 0.45, 0.52, 0.25],
                )
                add_circle(
                    self.mujoco,
                    scene,
                    hand,
                    radius=0.075,
                    width=0.008,
                    rgba=[0.98, 0.45, 0.52, 0.90],
                )
            if "wall_x" in semantic:
                wall_x = float(semantic["wall_x"])
                add_box(
                    self.mujoco,
                    scene,
                    [wall_x, 0.0, 0.55],
                    half_size=[0.006, 0.55, 0.55],
                    rgba=[0.98, 0.75, 0.14, 0.11],
                )
                add_wall_grid(
                    self.mujoco,
                    scene,
                    wall_x,
                    y_extent=0.55,
                    z_min=0.0,
                    z_max=1.10,
                    rgba=[0.98, 0.75, 0.14, 0.72],
                )
                contact = [wall_x, hand[1], hand[2]]
                if float(semantic.get("wall_penetration", 0.0)) > 0.0:
                    add_circle(
                        self.mujoco,
                        scene,
                        contact,
                        radius=0.055,
                        width=0.008,
                        rgba=[0.98, 0.45, 0.52, 0.98],
                        axes=((0, 1, 0), (0, 0, 1)),
                    )
                force = semantic.get("wall_force_x", semantic.get("force", 0.0))
                if abs(force) > 1e-6:
                    force_length = min(0.35, max(0.08, 0.004 * abs(force)))
                    force_sign = 1.0 if force > 0.0 else -1.0
                    add_arrow(
                        self.mujoco,
                        scene,
                        contact,
                        [wall_x + force_sign * force_length, hand[1], hand[2]],
                        width=0.014,
                        rgba=[0.98, 0.45, 0.52, 0.98],
                    )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.renderer is not None:
            close_mujoco_renderer(self.renderer)
            self.renderer = None


def replay_adapter_from_manifest(
    run_dir: str | Path, *, safe_mode: bool = False
) -> MujocoReplayAdapter:
    import json

    manifest_path = Path(run_dir) / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_path = payload.get("model", {}).get("path")
    if not model_path:
        raise ValueError("The recording manifest does not name a MuJoCo model.")
    resolved = resolve_project_path(str(model_path))
    if not resolved.exists():
        raise FileNotFoundError(f"Recorded model is missing: {model_path}")
    return MujocoReplayAdapter(resolved, safe_mode=safe_mode)


def _copy_vector(target: Any, source: Any) -> None:
    count = min(len(target), len(source))
    target[:count] = source[:count]
    if len(target) > count:
        target[count:] = 0.0


def _safe_frame(width: int, height: int) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, :] = (17, 24, 39)
    frame[height // 2 - 1 : height // 2 + 1, :, :] = (55, 65, 81)
    frame[:, width // 2 - 1 : width // 2 + 1, :] = (55, 65, 81)
    return frame


def _render_size(model: Any, width: int, height: int) -> tuple[int, int]:
    framebuffer = model.vis.global_
    return min(width, int(framebuffer.offwidth)), min(height, int(framebuffer.offheight))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
