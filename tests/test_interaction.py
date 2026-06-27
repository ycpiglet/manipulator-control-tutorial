from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.interaction import (  # noqa: E402
    InteractionLog,
    KeyForcePulse,
    LiveStatus,
    LiveTuning,
    SliderSpec,
    StatusSpec,
    TargetOffsetControl,
    _panel_guide_rows,
    _panel_guide_title,
)
from mclab.learning_guides import RunGuide  # noqa: E402


class KeyForcePulseTests(unittest.TestCase):
    def test_a_and_d_keys_create_short_force_pulses(self) -> None:
        log = InteractionLog()
        pulse = KeyForcePulse({"interaction": {"key_force": True, "force": 12.0, "duration": 0.5}}, event_log=log)

        pulse.update_time(1.0)
        log.set_time(1.0)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.1), 12.0)
        self.assertEqual(pulse.value(1.6), 0.0)

        pulse.update_time(2.0)
        log.set_time(2.0)
        pulse.key_callback(ord("A"))
        self.assertEqual(pulse.value(2.1), -12.0)
        self.assertEqual([event["value"] for event in log.events()], [12.0, -12.0])

    def test_disabled_config_ignores_keys(self) -> None:
        pulse = KeyForcePulse({})
        pulse.update_time(1.0)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.1), 0.0)

    def test_target_offset_control_nudges_and_clips(self) -> None:
        log = InteractionLog()
        log.set_time(0.5)
        control = TargetOffsetControl(
            {"interaction": {"target_nudge": True, "target_step": 0.2, "target_limit": 0.3}},
            event_log=log,
        )
        control.trigger_right()
        control.trigger_right()
        self.assertEqual(control.value(), 0.3)
        control.trigger_left()
        self.assertAlmostEqual(control.value(), 0.1)
        self.assertEqual([event["name"] for event in log.events()], ["joint_target_offset"] * 3)
        self.assertAlmostEqual(log.events()[-1]["value"], 0.1)

    def test_live_tuning_updates_slider_values(self) -> None:
        log = InteractionLog()
        log.set_time(1.25)
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)], event_log=log)
        self.assertEqual(tuning.value("kp", 0.0), 20.0)
        tuning.set_value("kp", 42.0)
        self.assertEqual(tuning.value("kp", 0.0), 42.0)
        self.assertEqual(tuning.value("missing", 7.0), 7.0)
        self.assertEqual(
            log.events(),
            [{"time": 1.25, "kind": "slider", "name": "kp", "label": "Kp", "value": 42.0}],
        )
        self.assertEqual(log.summary()["interaction_events"], 1)

    def test_live_tuning_reset_restores_initial_values(self) -> None:
        log = InteractionLog()
        log.set_time(2.5)
        tuning = LiveTuning(
            [
                SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0),
                SliderSpec("kd", "Kd", 0.0, 50.0, 4.0, 0.5),
            ],
            event_log=log,
        )

        tuning.set_value("kp", 55.0)
        tuning.set_value("kd", 11.0)
        reset_values = tuning.reset()

        self.assertEqual(reset_values, {"kp": 20.0, "kd": 4.0})
        self.assertEqual(tuning.value("kp", 0.0), 20.0)
        self.assertEqual(tuning.value("kd", 0.0), 4.0)
        self.assertEqual([event["kind"] for event in log.events()], ["slider", "slider", "button"])
        self.assertEqual(log.events()[-1]["name"], "reset_sliders")
        self.assertEqual(log.events()[-1]["label"], "Reset sliders")

    def test_mark_observation_records_slider_and_status_snapshot(self) -> None:
        log = InteractionLog()
        log.set_time(3.0)
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)], event_log=log)
        status = LiveStatus([StatusSpec("error", "Error [m]")])

        tuning.set_value("kp", 35.0)
        status.set_values(error=0.125)
        payload = log.mark_observation(sliders=tuning.snapshot(), status=status.snapshot())

        self.assertEqual(payload, {"sliders": {"kp": 35.0}, "status": {"error": "0.125"}})
        event = log.events()[-1]
        self.assertEqual(event["kind"], "marker")
        self.assertEqual(event["name"], "observation")
        self.assertEqual(event["label"], "Mark observation")
        self.assertEqual(event["value"], payload)
        self.assertEqual(log.summary()["last_interaction"], "Mark observation")

    def test_live_status_formats_dashboard_values(self) -> None:
        status = LiveStatus([StatusSpec("position", "Position [m]"), StatusSpec("mode", "Mode")])

        self.assertEqual(status.snapshot()["position"], "--")
        status.set_values(position=1.23456, mode="tracking", ignored=99.0)

        snapshot = status.snapshot()
        self.assertEqual(snapshot["position"], "1.235")
        self.assertEqual(snapshot["mode"], "tracking")
        self.assertNotIn("ignored", snapshot)

    def test_panel_guidance_uses_try_change_watch_fields(self) -> None:
        guide = RunGuide(
            title="Demo Guide",
            focus="Focus text",
            try_this="Move the slider.",
            change="controller.kp",
            watch="Tracking error.",
            next_step="Run the comparison.",
        )

        self.assertEqual(_panel_guide_title(guide), "Demo Guide")
        self.assertEqual(
            _panel_guide_rows(guide),
            [
                ("Try", "Move the slider."),
                ("Change", "controller.kp"),
                ("Watch", "Tracking error."),
            ],
        )
        self.assertEqual(_panel_guide_rows(None), [])
