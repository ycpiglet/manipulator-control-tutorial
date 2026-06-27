from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.controllers.pid import PIDController  # noqa: E402


class PidTests(unittest.TestCase):
    def test_pid_zero_error_zero_output(self) -> None:
        controller = PIDController(kp=10.0, ki=1.0, kd=2.0, dt=0.01)
        command = controller.compute(setpoint=1.0, measurement=1.0, measurement_rate=0.0)
        self.assertEqual(command.value, 0.0)
        self.assertEqual(command.error, 0.0)

    def test_pid_saturates_output(self) -> None:
        controller = PIDController(
            kp=10.0,
            ki=0.0,
            kd=0.0,
            dt=0.01,
            output_min=-1.0,
            output_max=1.0,
        )
        command = controller.compute(setpoint=1.0, measurement=0.0)
        self.assertEqual(command.value, 1.0)
        self.assertTrue(command.saturated)
