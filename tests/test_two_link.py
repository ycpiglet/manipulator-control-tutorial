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

    def test_two_link_viewer_guides_default_to_enabled(self) -> None:
        guides = _two_link_viewer_guides({})

        self.assertTrue(guides["enabled"])
        self.assertTrue(guides["target"])
        self.assertTrue(guides["hand"])
        self.assertEqual(guides["condition_threshold"], 20.0)
        self.assertFalse(_two_link_viewer_guides({"viewer_guides": {"enabled": False}})["enabled"])

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
