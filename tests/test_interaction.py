from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.interaction import (  # noqa: E402
    KeyForcePulse,
    LiveStatus,
    LiveTuning,
    SliderSpec,
    StatusSpec,
    TargetOffsetControl,
)


class KeyForcePulseTests(unittest.TestCase):
    def test_a_and_d_keys_create_short_force_pulses(self) -> None:
        pulse = KeyForcePulse({"interaction": {"key_force": True, "force": 12.0, "duration": 0.5}})

        pulse.update_time(1.0)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.1), 12.0)
        self.assertEqual(pulse.value(1.6), 0.0)

        pulse.update_time(2.0)
        pulse.key_callback(ord("A"))
        self.assertEqual(pulse.value(2.1), -12.0)

    def test_disabled_config_ignores_keys(self) -> None:
        pulse = KeyForcePulse({})
        pulse.update_time(1.0)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.1), 0.0)

    def test_target_offset_control_nudges_and_clips(self) -> None:
        control = TargetOffsetControl(
            {"interaction": {"target_nudge": True, "target_step": 0.2, "target_limit": 0.3}}
        )
        control.trigger_right()
        control.trigger_right()
        self.assertEqual(control.value(), 0.3)
        control.trigger_left()
        self.assertAlmostEqual(control.value(), 0.1)

    def test_live_tuning_updates_slider_values(self) -> None:
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)])
        self.assertEqual(tuning.value("kp", 0.0), 20.0)
        tuning.set_value("kp", 42.0)
        self.assertEqual(tuning.value("kp", 0.0), 42.0)
        self.assertEqual(tuning.value("missing", 7.0), 7.0)

    def test_live_status_formats_dashboard_values(self) -> None:
        status = LiveStatus([StatusSpec("position", "Position [m]"), StatusSpec("mode", "Mode")])

        self.assertEqual(status.snapshot()["position"], "--")
        status.set_values(position=1.23456, mode="tracking", ignored=99.0)

        snapshot = status.snapshot()
        self.assertEqual(snapshot["position"], "1.235")
        self.assertEqual(snapshot["mode"], "tracking")
        self.assertNotIn("ignored", snapshot)
