from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.interaction import (  # noqa: E402
    ExperimentResetControl,
    InteractionLog,
    KeyForcePulse,
    LiveStatus,
    LiveTuning,
    SimulationPlaybackControl,
    SimulationPauseControl,
    SliderSpec,
    StatusSpec,
    TargetOffsetControl,
    TuningPreset,
    _panel_guide_rows,
    _panel_guide_title,
    _observation_marker_count,
    _observation_marker_status_message,
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

    def test_experiment_reset_control_records_and_consumes_one_request(self) -> None:
        log = InteractionLog()
        log.set_time(1.25)
        control = ExperimentResetControl({"interaction": {"panel": True}}, event_log=log)

        self.assertTrue(control.enabled)
        self.assertTrue(control.panel_enabled)
        self.assertFalse(control.consume())

        control.request()

        self.assertTrue(control.consume())
        self.assertFalse(control.consume())
        self.assertEqual(
            log.events(),
            [{"time": 1.25, "kind": "button", "name": "reset_plant", "label": "Reset plant", "value": None}],
        )

    def test_experiment_reset_control_can_be_disabled(self) -> None:
        log = InteractionLog()
        control = ExperimentResetControl({"interaction": {"panel": True, "reset_plant": False}}, event_log=log)

        control.request()

        self.assertFalse(control.enabled)
        self.assertFalse(control.consume())
        self.assertEqual(log.events(), [])

    def test_simulation_pause_control_toggles_and_records_state(self) -> None:
        log = InteractionLog()
        log.set_time(2.0)
        control = SimulationPauseControl({"interaction": {"panel": True}}, event_log=log)

        self.assertTrue(control.enabled)
        self.assertFalse(control.paused())

        self.assertTrue(control.toggle())
        self.assertTrue(control.paused())
        self.assertFalse(control.toggle())
        self.assertFalse(control.paused())
        self.assertEqual(
            [(event["name"], event["label"], event["value"]) for event in log.events()],
            [
                ("pause_simulation", "Pause simulation", True),
                ("resume_simulation", "Resume simulation", False),
            ],
        )

    def test_simulation_pause_control_steps_once_while_staying_paused(self) -> None:
        log = InteractionLog()
        log.set_time(2.5)
        control = SimulationPauseControl({"interaction": {"panel": True}}, event_log=log)

        self.assertTrue(control.request_step())

        self.assertTrue(control.paused())
        self.assertTrue(control.consume_step())
        self.assertFalse(control.consume_step())
        self.assertTrue(control.paused())
        self.assertEqual(
            log.events(),
            [{"time": 2.5, "kind": "button", "name": "step_simulation", "label": "Step once", "value": True}],
        )

        control.toggle()
        self.assertFalse(control.paused())

    def test_simulation_pause_control_can_be_disabled(self) -> None:
        log = InteractionLog()
        control = SimulationPauseControl({"interaction": {"panel": True, "pause_resume": False}}, event_log=log)

        self.assertFalse(control.toggle())

        self.assertFalse(control.enabled)
        self.assertFalse(control.paused())
        self.assertEqual(log.events(), [])

    def test_simulation_playback_control_clips_speed_and_records_changes(self) -> None:
        log = InteractionLog()
        log.set_time(1.75)
        control = SimulationPlaybackControl(
            {"interaction": {"panel": True, "playback_min": 0.25, "playback_max": 2.0}},
            event_log=log,
        )

        self.assertEqual(control.speed(), 1.0)
        self.assertFalse(control.consume_change())

        self.assertEqual(control.set_speed(0.1), 0.25)
        self.assertTrue(control.consume_change())
        self.assertFalse(control.consume_change())
        self.assertEqual(control.set_speed(3.0), 2.0)

        self.assertEqual(control.speed(), 2.0)
        self.assertEqual(
            [(event["kind"], event["name"], event["label"], event["value"]) for event in log.events()],
            [
                ("slider", "playback_speed", "Playback speed", 0.25),
                ("slider", "playback_speed", "Playback speed", 2.0),
            ],
        )

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

    def test_live_tuning_step_adjusts_and_clips_values(self) -> None:
        log = InteractionLog()
        log.set_time(1.0)
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 10.0, 9.5, 0.5)], event_log=log)

        self.assertEqual(tuning.adjust_value("kp", 1), {"kp": 10.0})
        self.assertEqual(tuning.adjust_value("kp", 1), {"kp": 10.0})
        self.assertEqual(tuning.adjust_value("kp", -3), {"kp": 8.5})
        self.assertEqual(tuning.adjust_value("missing", 1), {"kp": 8.5})
        self.assertEqual([event["value"] for event in log.events()], [10.0, 8.5])

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
        lab03_dls_config = load_config("configs/lab03_2dof/dls_singularity_2dof.yaml")
        lab03_condition_dls_config = load_config("configs/lab03_2dof/condition_aware_dls_2dof.yaml")
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
                lab03_2dof._two_link_live_tuning(
                    lab03_dls_config,
                    str(lab03_dls_config["mode"]),
                    dict(lab03_dls_config["tracking_controller"]),
                    tuple(lab03_dls_config["tracking_controller"]["torque_limit"]),
                    tuple(lab03_dls_config["target_xy"]),
                ),
                ["Low DLS damping", "Balanced DLS", "High DLS damping"],
            ),
            (
                lab03_2dof._two_link_live_tuning(
                    lab03_condition_dls_config,
                    str(lab03_condition_dls_config["mode"]),
                    dict(lab03_condition_dls_config["tracking_controller"]),
                    tuple(lab03_condition_dls_config["tracking_controller"]["torque_limit"]),
                    tuple(lab03_condition_dls_config["target_xy"]),
                ),
                ["Early damping", "Balanced schedule", "Late damping"],
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

    def test_interactive_configs_enable_plant_reset_by_default(self) -> None:
        paths = [
            "configs/lab01_msd/interactive_pull.yaml",
            "configs/lab02_pid/interactive_disturbance.yaml",
            "configs/lab03_2dof/interactive_tracking.yaml",
            "configs/lab03_2dof/interactive_2dof.yaml",
            "configs/lab03_2dof/dls_singularity_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "configs/lab04_panda/interactive_joint_hold.yaml",
            "configs/lab04_panda/interactive_cartesian_reach.yaml",
            "configs/lab04_panda/interactive_virtual_wall.yaml",
        ]

        for path in paths:
            with self.subTest(path=path):
                control = ExperimentResetControl(load_config(path))
                self.assertTrue(control.panel_enabled)
                self.assertTrue(control.enabled)

    def test_interactive_configs_enable_pause_resume_by_default(self) -> None:
        paths = [
            "configs/lab01_msd/interactive_pull.yaml",
            "configs/lab02_pid/interactive_disturbance.yaml",
            "configs/lab03_2dof/interactive_tracking.yaml",
            "configs/lab03_2dof/interactive_2dof.yaml",
            "configs/lab03_2dof/dls_singularity_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "configs/lab04_panda/interactive_joint_hold.yaml",
            "configs/lab04_panda/interactive_cartesian_reach.yaml",
            "configs/lab04_panda/interactive_virtual_wall.yaml",
        ]

        for path in paths:
            with self.subTest(path=path):
                control = SimulationPauseControl(load_config(path))
                self.assertTrue(control.panel_enabled)
                self.assertTrue(control.enabled)

    def test_interactive_configs_enable_playback_speed_by_default(self) -> None:
        paths = [
            "configs/lab01_msd/interactive_pull.yaml",
            "configs/lab02_pid/interactive_disturbance.yaml",
            "configs/lab03_2dof/interactive_tracking.yaml",
            "configs/lab03_2dof/interactive_2dof.yaml",
            "configs/lab03_2dof/dls_singularity_2dof.yaml",
            "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
            "configs/lab04_panda/interactive_joint_hold.yaml",
            "configs/lab04_panda/interactive_cartesian_reach.yaml",
            "configs/lab04_panda/interactive_virtual_wall.yaml",
        ]

        for path in paths:
            with self.subTest(path=path):
                control = SimulationPlaybackControl(load_config(path))
                self.assertTrue(control.panel_enabled)
                self.assertTrue(control.enabled)
                self.assertEqual(control.speed(), 1.0)

    def test_condition_aware_dls_live_tuning_exposes_schedule_sliders(self) -> None:
        config = load_config("configs/lab03_2dof/condition_aware_dls_2dof.yaml")

        tuning = lab03_2dof._two_link_live_tuning(
            config,
            str(config["mode"]),
            dict(config["tracking_controller"]),
            tuple(config["tracking_controller"]["torque_limit"]),
            tuple(config["target_xy"]),
        )

        slider_names = {spec.name for spec in tuning.specs}
        self.assertIn("condition_damping_threshold", slider_names)
        self.assertIn("condition_damping_full", slider_names)
        self.assertIn("max_dls_damping", slider_names)

    def test_lab04_wall_live_tuning_exposes_hand_target_sliders(self) -> None:
        config = load_config("configs/lab04_panda/interactive_virtual_wall.yaml")

        tuning = lab04_panda._live_tuning(config)

        slider_names = {spec.name for spec in tuning.specs}
        self.assertIn("target_x", slider_names)
        self.assertIn("target_y", slider_names)
        self.assertIn("target_z", slider_names)
        self.assertIn("cartesian_gain", slider_names)
        self.assertIn("wall_x", slider_names)
        self.assertIn("wall_stiffness", slider_names)
        self.assertTrue(all("target_x" in preset.values for preset in tuning.presets))

    def test_mark_observation_records_slider_and_status_snapshot(self) -> None:
        log = InteractionLog()
        log.set_time(3.0)
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)], event_log=log)
        status = LiveStatus([StatusSpec("error", "Error [m]")])

        tuning.set_value("kp", 35.0)
        status.set_values(error=0.125)
        payload = log.mark_observation(
            changed_sliders=tuning.changed_values(),
            sliders=tuning.snapshot(),
            status=status.snapshot(),
            question="Question: Which gain gives the cleanest response?",
            prediction="Kp 35 should reduce error without making force noisy.",
            note="Kp 35 reduced error without visible jitter.",
        )

        self.assertEqual(
            payload,
            {
                "question": "Question: Which gain gives the cleanest response?",
                "prediction": "Kp 35 should reduce error without making force noisy.",
                "note": "Kp 35 reduced error without visible jitter.",
                "changed_sliders": {"kp": 35.0},
                "sliders": {"kp": 35.0},
                "status": {"error": "0.125"},
            },
        )
        event = log.events()[-1]
        self.assertEqual(event["kind"], "marker")
        self.assertEqual(event["name"], "observation")
        self.assertEqual(event["label"], "Mark observation")
        self.assertEqual(event["value"], payload)
        self.assertEqual(log.summary()["last_interaction"], "Mark observation")
        self.assertEqual(_observation_marker_count(log), 1)

        log.record("button", "demo", None, label="Demo")
        self.assertEqual(_observation_marker_count(log), 1)

        tuning.reset()
        self.assertEqual(tuning.changed_values(), {})

    def test_mark_observation_records_evidence_prompt_when_available(self) -> None:
        log = InteractionLog()

        payload = log.mark_observation(
            question="Question: What changed?",
            prediction="Force should increase.",
            evidence_prompt="Evidence to capture: position error and force.",
        )

        self.assertEqual(
            payload,
            {
                "question": "Question: What changed?",
                "prediction": "Force should increase.",
                "evidence_prompt": "Evidence to capture: position error and force.",
            },
        )
        self.assertEqual(log.events()[-1]["value"]["prediction"], payload["prediction"])
        self.assertEqual(log.events()[-1]["value"]["evidence_prompt"], payload["evidence_prompt"])

    def test_observation_marker_status_message_reports_learning_path_evidence(self) -> None:
        log = InteractionLog()

        log.mark_observation(note="The response settled.")
        self.assertEqual(
            _observation_marker_status_message(log, ""),
            "Marked observation 1 - add a prediction next time to complete the learning path.",
        )

        log.mark_observation(prediction="More damping should settle faster.")
        self.assertEqual(
            _observation_marker_status_message(log, "More damping should settle faster."),
            "Marked observation 2 with prediction - learning path evidence saved.",
        )

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
            question="Which gain gives the cleanest response?",
            watch="Tracking error.",
            next_step="Run the comparison.",
        )

        self.assertEqual(_panel_guide_title(guide), "Demo Guide")
        self.assertEqual(
            _panel_guide_rows(guide),
            [
                ("Try", "Move the slider."),
                ("Change", "controller.kp"),
                ("Prediction", "Before changing controller.kp, predict how Tracking error will change."),
                ("Question", "Which gain gives the cleanest response?"),
                ("Watch", "Tracking error."),
            ],
        )
        self.assertEqual(_panel_guide_rows(None), [])
