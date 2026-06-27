from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.two_link import (  # noqa: E402
    TwoLinkGeometry,
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
