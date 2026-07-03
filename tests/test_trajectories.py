from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.trajectories import (  # noqa: E402
    MinimumJerkTrajectory,
    SCurveTrajectory,
    StepTrajectory,
    TrapezoidalTrajectory,
    build_trajectory,
)


class TrajectoryTests(unittest.TestCase):
    def test_minimum_jerk_boundary_conditions(self) -> None:
        trajectory = MinimumJerkTrajectory(start=0.0, end=1.0, duration=2.0, start_time=0.5)
        start = trajectory.evaluate(0.5)
        end = trajectory.evaluate(2.5)
        self.assertEqual(start.position, 0.0)
        self.assertEqual(start.velocity, 0.0)
        self.assertEqual(end.position, 1.0)
        self.assertEqual(end.velocity, 0.0)

    def test_trapezoidal_trajectory_boundary_conditions(self) -> None:
        trajectory = TrapezoidalTrajectory(
            start=0.0,
            end=1.0,
            max_velocity=0.5,
            max_acceleration=1.0,
            start_time=0.2,
        )
        self.assertEqual(trajectory.evaluate(0.0).position, 0.0)
        self.assertEqual(trajectory.evaluate(0.2 + trajectory.duration + 0.1).position, 1.0)

    def test_step_trajectory_switches_at_start_time(self) -> None:
        trajectory = StepTrajectory(start=0.0, end=1.0, start_time=1.0)
        self.assertEqual(trajectory.evaluate(0.5).position, 0.0)
        self.assertEqual(trajectory.evaluate(1.0).position, 1.0)

    def test_s_curve_midpoint_is_halfway_for_symmetric_move(self) -> None:
        trajectory = SCurveTrajectory(start=0.0, end=1.0, duration=2.0)
        self.assertTrue(
            math.isclose(trajectory.evaluate(1.0).position, 0.5, rel_tol=1e-9, abs_tol=1e-9)
        )

    def test_build_trajectory_factory(self) -> None:
        trajectory = build_trajectory({"type": "minimum_jerk", "start": 0, "end": 1, "duration": 1})
        self.assertEqual(trajectory.evaluate(1.0).position, 1.0)
