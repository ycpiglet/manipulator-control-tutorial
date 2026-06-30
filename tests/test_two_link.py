from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.labs.lab03_2dof import (  # noqa: E402
    _condition_aware_dls_damping,
    _interpolate_two_link_target_xy_waypoints,
    _smooth_pulse_scale,
    _two_link_target_xy_command,
    _two_link_target_xy_waypoints,
    _two_link_disturbance_recovery_metrics,
    _two_link_disturbance_torque,
    _two_link_viewer_guides,
    _update_two_link_viewer_guides,
)
from mclab.sim.two_link import (  # noqa: E402
    TwoLinkGeometry,
    damped_least_squares_joint_velocity,
    forward_kinematics,
    inverse_kinematics,
    jacobian,
    jacobian_condition_number,
    jacobian_determinant,
    manipulability,
)


class TwoLinkKinematicsTests(unittest.TestCase):
    def test_forward_kinematics_at_zero_angle(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)

        x, y = forward_kinematics([0.0, 0.0], geometry)

        self.assertAlmostEqual(x, 1.05)
        self.assertAlmostEqual(y, 0.0)

    def test_jacobian_at_zero_angle_maps_joint_rates_to_y_velocity(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)

        matrix = jacobian([0.0, 0.0], geometry)

        self.assertAlmostEqual(matrix[0][0], 0.0)
        self.assertAlmostEqual(matrix[0][1], 0.0)
        self.assertAlmostEqual(matrix[1][0], 1.05)
        self.assertAlmostEqual(matrix[1][1], 0.45)

    def test_inverse_kinematics_reaches_target(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)
        target = (0.55, 0.35)

        q = inverse_kinematics(target, geometry)
        reached = forward_kinematics(q, geometry)

        self.assertAlmostEqual(reached[0], target[0], places=6)
        self.assertAlmostEqual(reached[1], target[1], places=6)

    def test_singularity_metrics_detect_straight_arm(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)

        determinant = jacobian_determinant([0.0, 0.0], geometry)
        condition = jacobian_condition_number([0.0, 0.0], geometry)

        self.assertAlmostEqual(determinant, 0.0)
        self.assertAlmostEqual(manipulability([0.0, 0.0], geometry), 0.0)
        self.assertEqual(condition, float("inf"))

    def test_bent_arm_has_positive_manipulability(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)

        self.assertAlmostEqual(manipulability([0.0, 1.57079632679], geometry), 0.27, places=6)
        self.assertLess(jacobian_condition_number([0.0, 1.57079632679], geometry), 3.0)

    def test_damped_least_squares_maps_task_velocity_near_regular_pose(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)
        q = [0.25, -1.0]
        task_velocity = [0.04, 0.03]

        qdot = damped_least_squares_joint_velocity(q, task_velocity, geometry, damping=1e-6)
        matrix = jacobian(q, geometry)
        reconstructed = (
            matrix[0][0] * qdot[0] + matrix[0][1] * qdot[1],
            matrix[1][0] * qdot[0] + matrix[1][1] * qdot[1],
        )

        self.assertAlmostEqual(reconstructed[0], task_velocity[0], places=5)
        self.assertAlmostEqual(reconstructed[1], task_velocity[1], places=5)

    def test_damped_least_squares_stays_bounded_at_singularity(self) -> None:
        geometry = TwoLinkGeometry(link1=0.6, link2=0.45)

        qdot = damped_least_squares_joint_velocity([0.0, 0.0], [0.2, 0.0], geometry, damping=0.08)

        self.assertAlmostEqual(qdot[0], 0.0)
        self.assertAlmostEqual(qdot[1], 0.0)

    def test_condition_aware_dls_damping_scales_with_condition_number(self) -> None:
        config = {
            "condition_damping_threshold": 10.0,
            "condition_damping_full": 20.0,
            "max_dls_damping": 0.24,
        }

        disabled_damping, disabled_scale = _condition_aware_dls_damping(0.04, 100.0, config, enabled=False)
        low_damping, low_scale = _condition_aware_dls_damping(0.04, 8.0, config, enabled=True)
        mid_damping, mid_scale = _condition_aware_dls_damping(0.04, 15.0, config, enabled=True)
        high_damping, high_scale = _condition_aware_dls_damping(0.04, 40.0, config, enabled=True)

        self.assertEqual((disabled_damping, disabled_scale), (0.04, 0.0))
        self.assertEqual((low_damping, low_scale), (0.04, 0.0))
        self.assertAlmostEqual(mid_scale, 0.5)
        self.assertAlmostEqual(mid_damping, 0.14)
        self.assertEqual((high_damping, high_scale), (0.24, 1.0))

    def test_two_link_target_xy_waypoints_use_smooth_interpolation_and_velocity(self) -> None:
        waypoints = _two_link_target_xy_waypoints(
            {
                "target_xy_waypoints": [
                    {"time": 1.0, "xy": [0.80, 0.10]},
                    {"time": 0.0, "position": [0.50, 0.20]},
                    {"time": 2.0, "x": 1.04, "y": 0.0},
                ]
            }
        )

        self.assertEqual(waypoints[0], (0.0, (0.50, 0.20)))
        self.assertEqual(_interpolate_two_link_target_xy_waypoints(waypoints, -0.1), ([0.50, 0.20], [0.0, 0.0]))
        self.assertEqual(_interpolate_two_link_target_xy_waypoints(waypoints, 2.5), ([1.04, 0.0], [0.0, 0.0]))
        position, velocity = _interpolate_two_link_target_xy_waypoints(waypoints, 0.5)

        self.assertAlmostEqual(position[0], 0.65)
        self.assertAlmostEqual(position[1], 0.15)
        self.assertGreater(velocity[0], 0.0)
        self.assertLess(velocity[1], 0.0)

    def test_two_link_target_xy_command_preserves_existing_single_goal_behavior(self) -> None:
        class DummyLiveTuning:
            def value(self, _name: str, default: float) -> float:
                return default

        target_xy, target_xdot = _two_link_target_xy_command(
            start_xy=(0.40, 0.10),
            goal_xy=(0.80, 0.50),
            alpha=0.25,
            alpha_dot=0.5,
            time=1.0,
            waypoints=[],
            live_tuning=DummyLiveTuning(),  # type: ignore[arg-type]
        )

        self.assertEqual(target_xy, [0.50, 0.20])
        self.assertEqual(target_xdot, [0.20, 0.20])

    def test_two_link_target_xy_command_prefers_waypoints_when_configured(self) -> None:
        class DummyLiveTuning:
            def value(self, _name: str, default: float) -> float:
                return default + 10.0

        target_xy, target_xdot = _two_link_target_xy_command(
            start_xy=(0.40, 0.10),
            goal_xy=(0.80, 0.50),
            alpha=0.25,
            alpha_dot=0.5,
            time=0.5,
            waypoints=[(0.0, (0.50, 0.20)), (1.0, (0.70, 0.20))],
            live_tuning=DummyLiveTuning(),  # type: ignore[arg-type]
        )

        self.assertAlmostEqual(target_xy[0], 0.60)
        self.assertAlmostEqual(target_xy[1], 0.20)
        self.assertGreater(target_xdot[0], 0.0)
        self.assertAlmostEqual(target_xdot[1], 0.0)

    def test_two_link_disturbance_torque_uses_smooth_window(self) -> None:
        config = {
            "disturbance_torque": {
                "start_time": 1.0,
                "duration": 0.4,
                "ramp_time": 0.1,
                "torque": [0.2, -0.1],
            }
        }

        self.assertEqual(_two_link_disturbance_torque(config, 0.9), [0.0, 0.0])
        self.assertEqual(_two_link_disturbance_torque(config, 1.2), [0.2, -0.1])
        self.assertEqual(_two_link_disturbance_torque(config, 1.5), [0.0, 0.0])
        ramped = _two_link_disturbance_torque(config, 1.05)
        self.assertAlmostEqual(ramped[0], 0.1)
        self.assertAlmostEqual(ramped[1], -0.05)
        self.assertEqual(
            _two_link_disturbance_torque({"disturbance_torque": {"enabled": False, "torque": [1.0, 1.0]}}, 1.2),
            [0.0, 0.0],
        )

    def test_two_link_disturbance_torque_sums_staggered_pulses(self) -> None:
        config = {
            "disturbance_torque": {
                "duration": 0.4,
                "ramp_time": 0.0,
                "pulses": [
                    {"start_time": 1.0, "torque": [0.2, 0.0]},
                    {"start_time": 1.2, "torque": [0.0, -0.1]},
                ],
            }
        }

        self.assertEqual(_two_link_disturbance_torque(config, 0.9), [0.0, 0.0])
        self.assertEqual(_two_link_disturbance_torque(config, 1.1), [0.2, 0.0])
        self.assertEqual(_two_link_disturbance_torque(config, 1.3), [0.2, -0.1])
        self.assertEqual(_two_link_disturbance_torque(config, 1.7), [0.0, 0.0])

    def test_smooth_pulse_scale_handles_zero_ramp(self) -> None:
        self.assertEqual(_smooth_pulse_scale(elapsed=0.0, duration=0.2, ramp_time=0.0), 1.0)

    def test_two_link_disturbance_recovery_metrics_find_return_to_pre_error_band(self) -> None:
        rows = [
            {"time": 0.9, "disturbance_active": 0.0, "joint_error_norm": 0.001, "task_error_norm": 0.002},
            {"time": 1.0, "disturbance_active": 1.0, "joint_error_norm": 0.004, "task_error_norm": 0.008},
            {"time": 1.1, "disturbance_active": 1.0, "joint_error_norm": 0.006, "task_error_norm": 0.012},
            {"time": 1.2, "disturbance_active": 0.0, "joint_error_norm": 0.003, "task_error_norm": 0.007},
            {"time": 1.3, "disturbance_active": 0.0, "joint_error_norm": 0.0012, "task_error_norm": 0.004},
        ]

        metrics = _two_link_disturbance_recovery_metrics(rows)

        self.assertEqual(metrics["first_disturbance_time"], 1.0)
        self.assertEqual(metrics["last_disturbance_time"], 1.1)
        self.assertAlmostEqual(metrics["disturbance_duration"], 0.1)
        self.assertEqual(metrics["pre_disturbance_joint_error_norm"], 0.001)
        self.assertEqual(metrics["pre_disturbance_task_error_norm"], 0.002)
        self.assertEqual(metrics["disturbance_recovery_threshold"], 0.00125)
        self.assertTrue(metrics["disturbance_recovered"])
        self.assertEqual(metrics["disturbance_recovery_time"], 1.3)
        self.assertAlmostEqual(metrics["disturbance_recovery_duration"], 0.2)
        self.assertEqual(metrics["peak_task_error_during_disturbance_time"], 1.1)
        self.assertEqual(metrics["peak_joint_error_during_disturbance_time"], 1.1)

    def test_two_link_disturbance_recovery_metrics_skip_runs_without_disturbance(self) -> None:
        rows = [
            {"time": 0.0, "disturbance_active": 0.0, "joint_error_norm": 0.001, "task_error_norm": 0.002},
            {"time": 0.1, "disturbance_active": 0.0, "joint_error_norm": 0.001, "task_error_norm": 0.002},
        ]

        self.assertEqual(_two_link_disturbance_recovery_metrics(rows), {})

    def test_two_link_viewer_guides_default_to_enabled(self) -> None:
        guides = _two_link_viewer_guides({})

        self.assertTrue(guides["enabled"])
        self.assertTrue(guides["target"])
        self.assertTrue(guides["target_path"])
        self.assertTrue(guides["hand"])
        self.assertEqual(guides["condition_threshold"], 20.0)
        self.assertFalse(_two_link_viewer_guides({"viewer_guides": {"enabled": False}})["enabled"])
        self.assertFalse(_two_link_viewer_guides({"viewer_guides": {"target_path": False}})["target_path"])

    def test_two_link_viewer_guides_draw_target_and_hand(self) -> None:
        def init_geom(geom, geom_type, size, pos, mat, rgba):
            geom.geom_type = geom_type
            geom.pos = [float(value) for value in pos]
            geom.rgba = [float(value) for value in rgba]

        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(side_effect=init_geom),
            mjtGeom=types.SimpleNamespace(mjGEOM_SPHERE="sphere"),
            mjtCatBit=types.SimpleNamespace(mjCAT_DECOR="decor"),
        )
        scene = types.SimpleNamespace(ngeom=0, geoms=[types.SimpleNamespace() for _ in range(3)])
        viewer = types.SimpleNamespace(user_scn=scene)

        _update_two_link_viewer_guides(
            fake_mujoco,
            viewer,
            guide_config={
                "enabled": True,
                "hand": True,
                "target": True,
                "condition_warning": True,
                "condition_threshold": 20.0,
            },
            x_ee=(0.50, 0.20),
            target_xy=[0.62, 0.42],
            condition=5.0,
        )

        self.assertEqual(scene.ngeom, 2)
        self.assertEqual(scene.geoms[0].geom_type, "sphere")
        self.assertEqual(scene.geoms[0].pos, [0.62, 0.42, 0.11])
        self.assertEqual(scene.geoms[1].geom_type, "sphere")
        self.assertEqual(scene.geoms[1].rgba, [0.1, 0.42, 1.0, 0.78])

        _update_two_link_viewer_guides(
            fake_mujoco,
            viewer,
            guide_config={
                "enabled": True,
                "hand": True,
                "target": False,
                "condition_warning": True,
                "condition_threshold": 20.0,
            },
            x_ee=(1.03, 0.02),
            target_xy=[1.05, 0.0],
            condition=45.0,
        )

        self.assertEqual(scene.ngeom, 1)
        self.assertEqual(scene.geoms[0].pos, [1.03, 0.02, 0.11])
        self.assertEqual(scene.geoms[0].rgba, [1.0, 0.48, 0.1, 0.9])

    def test_two_link_viewer_guides_draw_retarget_waypoints(self) -> None:
        def init_geom(geom, geom_type, size, pos, mat, rgba):
            geom.geom_type = geom_type
            geom.size = [float(value) for value in size]
            geom.pos = [float(value) for value in pos]
            geom.rgba = [float(value) for value in rgba]

        fake_mujoco = types.SimpleNamespace(
            mjv_initGeom=Mock(side_effect=init_geom),
            mjtGeom=types.SimpleNamespace(mjGEOM_SPHERE="sphere"),
            mjtCatBit=types.SimpleNamespace(mjCAT_DECOR="decor"),
        )
        scene = types.SimpleNamespace(ngeom=0, geoms=[types.SimpleNamespace() for _ in range(8)])
        viewer = types.SimpleNamespace(user_scn=scene)
        waypoints = [
            (0.0, (0.50, 0.20)),
            (1.0, (0.70, 0.10)),
            (2.0, (1.04, 0.0)),
        ]

        _update_two_link_viewer_guides(
            fake_mujoco,
            viewer,
            guide_config={
                "enabled": True,
                "hand": True,
                "target": True,
                "target_path": True,
                "condition_warning": True,
                "condition_threshold": 20.0,
            },
            x_ee=(0.55, 0.22),
            target_xy=[0.62, 0.16],
            target_path=waypoints,
            condition=5.0,
        )

        self.assertEqual(scene.ngeom, 5)
        self.assertEqual(scene.geoms[0].pos, [0.50, 0.20, 0.075])
        self.assertEqual(scene.geoms[1].pos, [0.70, 0.10, 0.075])
        self.assertEqual(scene.geoms[2].pos, [1.04, 0.0, 0.075])
        self.assertEqual(scene.geoms[0].rgba, [0.62, 1.0, 0.22, 0.46])
        self.assertEqual(scene.geoms[3].pos, [0.62, 0.16, 0.11])
        self.assertEqual(scene.geoms[4].pos, [0.55, 0.22, 0.11])
