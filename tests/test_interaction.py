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
    TuningPreset,
    _panel_guide_rows,
    _panel_guide_title,
    tuning_presets_from_config,
)
from mclab.config import load_config  # noqa: E402
from mclab.labs import lab01_msd, lab02_pid, lab03_2dof, lab04_panda  # noqa: E402
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

    def test_live_tuning_applies_preset_and_clips_values(self) -> None:
        log = InteractionLog()
        log.set_time(3.5)
        tuning = LiveTuning(
            [
                SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0),
                SliderSpec("kd", "Kd", 0.0, 50.0, 4.0, 0.5),
            ],
            event_log=log,
            presets=[
                TuningPreset("aggressive", "Aggressive", {"kp": 180.0, "kd": 2.0, "unknown": 99.0}),
            ],
        )

        values = tuning.apply_preset("aggressive")

        self.assertEqual(values, {"kp": 100.0, "kd": 2.0})
        self.assertEqual(tuning.value("kp", 0.0), 100.0)
        self.assertEqual(tuning.value("kd", 0.0), 2.0)
        self.assertEqual(log.events()[-1]["kind"], "preset")
        self.assertEqual(log.events()[-1]["label"], "Aggressive")
        self.assertEqual(log.events()[-1]["value"], {"kp": 100.0, "kd": 2.0})
        self.assertEqual(tuning.preset_summary("aggressive"), "Aggressive: Kp=100, Kd=2")
        self.assertEqual(tuning.preset_summary("missing"), "")

    def test_tuning_presets_from_config_filters_to_known_numeric_sliders(self) -> None:
        specs = [
            SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0),
            SliderSpec("kd", "Kd", 0.0, 50.0, 4.0, 0.5),
        ]

        presets = tuning_presets_from_config(
            {
                "interaction": {
                    "tuning_presets": [
                        {
                            "label": "Calm",
                            "values": {"kp": 20, "kd": 10, "missing": 1, "bad": "nope"},
                        },
                        {"label": "Empty", "values": {"missing": 2}},
                    ]
                }
            },
            specs,
        )

        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0].name, "calm")
        self.assertEqual(presets[0].label, "Calm")
        self.assertEqual(presets[0].values, {"kp": 20.0, "kd": 10.0})

    def test_interactive_configs_expose_quick_presets(self) -> None:
        lab01_config = load_config("configs/lab01_msd/interactive_pull.yaml")
        lab02_config = load_config("configs/lab02_pid/interactive_disturbance.yaml")
        lab03_config = load_config("configs/lab03_2dof/interactive_2dof.yaml")
        lab03_tracking_config = load_config("configs/lab03_2dof/interactive_tracking.yaml")
        lab04_cartesian_config = load_config("configs/lab04_panda/interactive_cartesian_reach.yaml")
        lab04_wall_config = load_config("configs/lab04_panda/interactive_virtual_wall.yaml")

        cases = [
            (lab01_msd._live_tuning(lab01_config), ["Lightly damped", "Heavy damping", "Stiff spring"]),
            (
                lab02_pid._live_tuning(
                    lab02_config,
                    dict(lab02_config["controller"]),
                    float(lab02_config["controller"]["output_limit"]),
                ),
                ["Gentle P", "Damped PD", "Aggressive PID"],
            ),
            (
                lab03_2dof._two_link_live_tuning(
                    lab03_config,
                    str(lab03_config["mode"]),
                    dict(lab03_config["tracking_controller"]),
                    tuple(lab03_config["tracking_controller"]["torque_limit"]),
                    tuple(lab03_config["target_xy"]),
                ),
                ["Soft reach", "Default reach", "Near edge"],
            ),
            (
                lab03_2dof._live_tuning(
                    lab03_tracking_config,
                    dict(lab03_tracking_config["tracking_controller"]),
                    float(lab03_tracking_config["tracking_controller"]["force_limit"]),
                ),
                ["Soft tracking", "Fast tracking"],
            ),
            (
                lab04_panda._live_tuning(lab04_cartesian_config),
                ["Soft reach", "Default reach", "Far target"],
            ),
            (
                lab04_panda._live_tuning(lab04_wall_config),
                ["Soft wall", "Stiff wall", "Close wall"],
            ),
        ]
        for tuning, expected_labels in cases:
            with self.subTest(expected_labels=expected_labels):
                self.assertEqual([preset.label for preset in tuning.presets], expected_labels)
                self.assertTrue(all(preset.values for preset in tuning.presets))

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
