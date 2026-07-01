from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.interaction import (  # noqa: E402
    ExperimentResetControl,
    InteractionLog,
    JointTorquePulse,
    KeyForcePulse,
    LiveStatus,
    LiveTuning,
    SimulationPlaybackControl,
    SimulationPauseControl,
    SliderSpec,
    StatusSpec,
    TargetOffsetControl,
    TuningPreset,
    _activity_mix_button_next_step_for_panel,
    _activity_mix_status_message,
    _append_observation_note,
    _available_learner_control_families,
    _bounded_panel_dimension,
    _changed_tuning_observation_note,
    _changed_tuning_summary,
    _live_status_observation_note,
    _observation_challenge_proof_status,
    _observation_checklist_status,
    _observation_evidence_quality,
    _panel_control_credit_text,
    _panel_guide_rows,
    _panel_guide_title,
    _panel_viewer_legend_rows,
    _observation_marker_count,
    _observation_marker_status_message,
    _observation_note_preview,
    _observation_note_value,
    _observation_next_action,
    _ordered_required_prefix,
    _panel_completion_text,
    _preset_button_label,
    _preset_panel_status,
    _recent_action_status_message,
    _run_clock_cue,
    _saved_observation_marker_review_message,
    learner_snapshot,
    learner_tuned_config,
    runtime_status_specs,
    runtime_status_values,
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

    def test_joint_torque_pulse_applies_independent_shoulder_and_elbow_pulses(self) -> None:
        log = InteractionLog()
        pulse = JointTorquePulse(
            {
                "interaction": {
                    "joint_disturbance": True,
                    "joint_disturbance_torque": [0.14, 0.16],
                    "joint_disturbance_duration": 0.3,
                }
            },
            event_log=log,
        )

        pulse.update_time(1.0)
        log.set_time(1.0)
        pulse.trigger_left()
        self.assertEqual(pulse.value(1.1), [0.14, 0.0])

        pulse.update_time(1.2)
        log.set_time(1.2)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.25), [0.14, 0.16])
        self.assertEqual(pulse.value(1.55), [0.0, 0.0])
        self.assertEqual([event["name"] for event in log.events()], ["manual_joint_disturbance"] * 2)
        self.assertEqual(log.events()[0]["value"]["joint"], "shoulder")
        self.assertEqual(log.events()[1]["value"]["joint"], "elbow")

    def test_joint_torque_pulse_can_be_disabled(self) -> None:
        pulse = JointTorquePulse({})
        pulse.update_time(1.0)
        pulse.key_callback(ord("D"))
        self.assertEqual(pulse.value(1.1), [0.0, 0.0])

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

    def test_target_offset_control_uses_custom_labels_and_event_name(self) -> None:
        log = InteractionLog()
        log.set_time(0.5)
        control = TargetOffsetControl(
            {
                "interaction": {
                    "target_nudge": True,
                    "target_step": 0.04,
                    "target_unit": "m",
                    "target_event_name": "target_x_nudge",
                    "target_left_label": "Target X - away",
                    "target_right_label": "Target X + into wall",
                }
            },
            event_log=log,
        )

        control.trigger_right()

        self.assertEqual(control.value(), 0.04)
        self.assertEqual(control.right_label, "Target X + into wall")
        self.assertIn("0.04 m", control.panel_description)
        self.assertEqual(log.events()[0]["name"], "target_x_nudge")
        self.assertEqual(log.events()[0]["label"], "Target X + into wall")

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

    def test_changed_tuning_summary_tracks_visible_slider_changes(self) -> None:
        tuning = LiveTuning(
            [
                SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0),
                SliderSpec("kd", "Kd", 0.0, 50.0, 4.0, 0.5),
            ]
        )

        self.assertEqual(_changed_tuning_summary(None), "Changed values: none yet")
        self.assertEqual(_changed_tuning_summary(tuning), "Changed values: none yet")

        tuning.set_value("kp", 35.0)
        self.assertEqual(_changed_tuning_summary(tuning), "Changed values: Kp=35")

        tuning.set_value("kd", 9.5)
        self.assertEqual(_changed_tuning_summary(tuning), "Changed values: Kp=35, Kd=9.5")

        tuning.reset()
        self.assertEqual(_changed_tuning_summary(tuning), "Changed values: none yet")

    def test_interaction_panel_dimensions_are_bounded_to_screen(self) -> None:
        self.assertEqual(
            _bounded_panel_dimension(1200, 720, default=820, maximum=820, minimum=320),
            600,
        )
        self.assertEqual(
            _bounded_panel_dimension(460, 1440, default=820, maximum=820, minimum=320),
            460,
        )
        self.assertEqual(
            _bounded_panel_dimension("bad", "bad", default=520, maximum=560, minimum=1),
            520,
        )

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
                TuningPreset(
                    "aggressive",
                    "Aggressive",
                    {"kp": 180.0, "kd": 2.0, "unknown": 99.0},
                    purpose="Fast response with lower damping.",
                ),
            ],
        )

        values = tuning.apply_preset("aggressive")

        self.assertEqual(values, {"kp": 100.0, "kd": 2.0})
        self.assertEqual(tuning.value("kp", 0.0), 100.0)
        self.assertEqual(tuning.value("kd", 0.0), 2.0)
        self.assertEqual(log.events()[-1]["kind"], "preset")
        self.assertEqual(log.events()[-1]["label"], "Aggressive")
        self.assertEqual(
            log.events()[-1]["value"],
            {
                "purpose": "Fast response with lower damping.",
                "values": {"kp": 100.0, "kd": 2.0},
            },
        )
        self.assertEqual(
            tuning.preset_summary("aggressive"),
            "Aggressive: Fast response with lower damping.; Kp=100, Kd=2",
        )
        self.assertEqual(tuning.preset_comparison_hint(), "")
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
                            "purpose": "Slow the response for inspection.",
                            "required": True,
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
        self.assertEqual(presets[0].purpose, "Slow the response for inspection.")
        self.assertTrue(presets[0].required)
        self.assertEqual(presets[0].values, {"kp": 20.0, "kd": 10.0})
        tuning = LiveTuning(specs, presets=presets)
        self.assertEqual(
            tuning.preset_summary("calm"),
            "Calm (required): Slow the response for inspection.; Kp=20, Kd=10",
        )

        self.assertEqual(_preset_button_label(presets[0]), "Calm (required)")
        self.assertEqual(_preset_button_label(TuningPreset("soft", "Soft", {"kp": 20.0})), "Soft")

        comparison = LiveTuning(
            specs,
            presets=[
                TuningPreset("soft", "Soft", {"kp": 20.0}),
                TuningPreset("stiff", "Stiff", {"kp": 80.0}),
            ],
        )
        self.assertEqual(
            comparison.preset_comparison_hint(),
            "Compare presets: Soft -> Stiff. Watch live status, then save one Mark observation.",
        )
        self.assertEqual(
            comparison.preset_progress_summary(),
            "Preset progress: 0/2 tried; next: Soft. Try at least two presets before Mark observation.",
        )
        self.assertEqual(
            _preset_panel_status(comparison),
            (
                "Hover a preset to preview its slider values.\n"
                "Preset progress: 0/2 tried; next: Soft. Try at least two presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs another preset")
        comparison.apply_preset("soft")
        self.assertEqual(
            comparison.preset_progress_summary(),
            "Preset progress: 1/2 tried; next: Stiff. Try at least two presets before Mark observation.",
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs another preset")
        comparison.apply_preset("soft")
        self.assertEqual(
            comparison.preset_progress_summary(),
            "Preset progress: 1/2 tried; next: Stiff. Try at least two presets before Mark observation.",
        )
        comparison.apply_preset("stiff")
        self.assertEqual(
            comparison.preset_progress_summary(),
            "Preset progress: 2/2 tried; ready to Mark observation comparing Soft, Stiff.",
        )
        self.assertEqual(comparison.preset_checklist_state(), "ready")

    def test_required_tuning_presets_gate_progress_readiness(self) -> None:
        specs = [SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)]
        log = InteractionLog()
        comparison = LiveTuning(
            specs,
            event_log=log,
            presets=[
                TuningPreset("soft", "Soft", {"kp": 20.0}),
                TuningPreset("close", "Close", {"kp": 80.0}, required=True),
                TuningPreset("back", "Back", {"kp": 35.0}, required=True),
            ],
        )

        self.assertEqual(
            comparison.preset_comparison_hint(),
            "Compare presets: Soft -> Close -> Back. Required evidence: Close -> Back. Watch live status, then save one Mark observation.",
        )
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 0/3 tried; 0/2 required; next required: Close; "
                "remaining required: Close -> Back. Try required presets before Mark observation."
            ),
        )
        self.assertEqual(
            _preset_panel_status(comparison, "close"),
            (
                "Close (required): Kp=80\n"
                "Preset progress: 0/3 tried; 0/2 required; next required: Close; "
                "remaining required: Close -> Back. "
                "Try required presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs required preset Close")
        comparison.apply_preset("soft")
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 1/3 tried; 0/2 required; next required: Close; "
                "remaining required: Close -> Back. Try required presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs required preset Close")
        comparison.apply_preset("close")
        self.assertEqual(log.events()[-1]["label"], "Close")
        self.assertEqual(log.events()[-1]["value"]["required"], True)
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 2/3 tried; 1/2 required; next required: Back; "
                "remaining required: Back. Try required presets before Mark observation."
            ),
        )
        self.assertEqual(
            _preset_panel_status(comparison, "close", applied=True),
            (
                "Applied Close (required): Kp=80\n"
                "Preset progress: 2/3 tried; 1/2 required; next required: Back; "
                "remaining required: Back. "
                "Try required presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs required preset Back")
        comparison.apply_preset("back")
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 3/3 tried; 2/2 required; required path complete; "
                "ready to Mark observation comparing Close -> Back."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "ready")

    def test_required_tuning_presets_must_follow_order(self) -> None:
        specs = [SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)]
        comparison = LiveTuning(
            specs,
            presets=[
                TuningPreset("soft", "Soft", {"kp": 20.0}),
                TuningPreset("close", "Close", {"kp": 80.0}, required=True),
                TuningPreset("back", "Back", {"kp": 35.0}, required=True),
            ],
        )

        self.assertEqual(_ordered_required_prefix(("close", "back"), ("back", "close")), ["close"])
        comparison.apply_preset("back")
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 1/3 tried; 0/2 required; next required: Close; "
                "remaining required: Close -> Back. Try required presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs required preset Close")

        comparison.apply_preset("close")
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 2/3 tried; 1/2 required; next required: Back; "
                "remaining required: Back. Try required presets before Mark observation."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "needs required preset Back")

        comparison.apply_preset("back")
        self.assertEqual(
            comparison.preset_progress_summary(),
            (
                "Preset progress: 2/3 tried; 2/2 required; required path complete; "
                "ready to Mark observation comparing Close -> Back."
            ),
        )
        self.assertEqual(comparison.preset_checklist_state(), "ready")

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
                ["Soft wall", "Stiff wall", "Close wall", "Back away", "Re-enter wall"],
            ),
        ]
        for tuning, expected_labels in cases:
            with self.subTest(expected_labels=expected_labels):
                self.assertEqual([preset.label for preset in tuning.presets], expected_labels)
                self.assertTrue(all(preset.purpose for preset in tuning.presets))
                self.assertTrue(all(preset.values for preset in tuning.presets))
        wall_tuning = lab04_panda._live_tuning(lab04_wall_config)
        self.assertEqual(
            [preset.label for preset in wall_tuning.presets if preset.required],
            ["Close wall", "Back away", "Re-enter wall"],
        )

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

    def test_lab04_cartesian_target_nudge_replays_as_cartesian_target_x(self) -> None:
        config = load_config("configs/lab04_panda/interactive_cartesian_reach.yaml")
        tuning = lab04_panda._live_tuning(config)
        target_offset = TargetOffsetControl(config)

        target_offset.trigger_right()
        updates = lab04_panda._learner_tuned_updates(
            config,
            tuning,
            target_offset,
            cartesian_target_nudge=True,
        )

        self.assertAlmostEqual(updates["cartesian_target"]["position"][0], 0.625)
        self.assertNotIn("trajectory", updates)

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
        back_away = next(preset for preset in tuning.presets if preset.label == "Back away")
        self.assertLess(back_away.values["target_x"], back_away.values["wall_x"])
        self.assertIn("contact release", back_away.purpose)

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
            outcome="Matched",
            note="Kp 35 reduced error without visible jitter.",
            challenge_proof="Challenge proof: review-ready; compare the saved observation with plots after the run.",
        )

        self.assertEqual(
            payload,
            {
                "question": "Question: Which gain gives the cleanest response?",
                "prediction": "Kp 35 should reduce error without making force noisy.",
                "outcome": "Matched",
                "challenge_proof": "review-ready; compare the saved observation with plots after the run.",
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
            _observation_marker_status_message(log, "", "The response settled."),
            "Marked observation 1 - add a prediction next time; use one button, slider, or preset to complete the learning path.",
        )
        self.assertEqual(
            _observation_marker_status_message(
                log,
                "",
                "The response settled.",
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
            ),
            "Marked observation 1 - add a prediction next time; "
            "use experiment buttons, live sliders, or Quick presets to complete the learning path.",
        )
        self.assertEqual(
            _observation_marker_status_message(
                log,
                "",
                "The response settled.",
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
                button_next_step="Use Target X - away or Target X + into wall.",
            ),
            "Marked observation 1 - add a prediction next time; use experiment buttons "
            "(Target X - away or Target X + into wall), live sliders, or Quick presets "
            "to complete the learning path.",
        )

        log.mark_observation(prediction="A softer preset should reduce force.")
        self.assertEqual(
            _observation_marker_status_message(
                log,
                "A softer preset should reduce force.",
                "",
                "needs another preset",
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "Marked observation 2 - use Pull Left A / Left or Push Right D / Right; "
            "add a short note or Use live status; "
            "try another preset to complete the learning path.",
        )

        log.mark_observation(prediction="Backing away should release contact.")
        self.assertEqual(
            _observation_marker_status_message(
                log,
                "Backing away should release contact.",
                "",
                "needs required preset Back away",
            ),
            "Marked observation 3 - use one button, slider, or preset; add a short note or Use live status; "
            "try required preset Back away to complete the learning path.",
        )

        log.record("slider", "damping", 4.0, label="Damping")
        log.mark_observation(prediction="More damping should settle faster.", note="Energy dropped.")
        self.assertEqual(
            _observation_marker_status_message(log, "More damping should settle faster.", "Energy dropped."),
            "Marked observation 4 - saved prediction, 1 note item, learner control; learning path evidence saved.",
        )
        self.assertEqual(
            _observation_marker_status_message(
                log,
                "More damping should settle faster.",
                "Energy dropped; Settling time shortened.",
                "ready",
                outcome="Matched",
            ),
            "Marked observation 4 - saved prediction, outcome, 2 note items, learner control, "
            "preset comparison; learning path evidence saved.",
        )

    def test_saved_observation_marker_review_message_summarizes_latest_marker(self) -> None:
        self.assertEqual(_saved_observation_marker_review_message(0), "Saved observation: none yet.")
        self.assertEqual(
            _saved_observation_marker_review_message(
                1,
                note="The response settled.",
            ),
            "Saved observation 1: prediction missing; outcome not judged; 1 note item; "
            "learner control missing. Next: write a prediction and use learner control in another marker.",
        )
        self.assertEqual(
            _saved_observation_marker_review_message(
                2,
                prediction="More damping should settle faster.",
                note="Settling time shortened",
                learner_controls=1,
            ),
            "Saved observation 2: prediction saved; outcome not judged; 1 note item; "
            "learner control saved. Next: choose an outcome in another marker or compare with plots after the run.",
        )
        self.assertEqual(
            _saved_observation_marker_review_message(
                3,
                prediction="Stiffer wall should push back harder.",
                outcome="Matched",
                note="Wall force rose; Hand stayed outside",
                learner_controls=3,
                preset_state="ready",
            ),
            "Saved observation 3: prediction saved; outcome saved; 2 note items; "
            "learner control saved; preset comparison saved. Next: compare this marker with plots after the run.",
        )

    def test_observation_checklist_status_guides_before_marking(self) -> None:
        self.assertEqual(
            _observation_checklist_status("", "Not judged yet", ""),
            "Evidence checklist: Prediction missing; Control needed; Outcome optional; Note recommended.",
        )
        self.assertEqual(
            _observation_checklist_status(
                "",
                "Not judged yet",
                "",
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "Evidence checklist: Prediction missing; Control needed "
            "(use Pull Left A / Left or Push Right D / Right); Outcome optional; Note recommended.",
        )
        self.assertEqual(
            _observation_checklist_status(
                "More damping should settle faster.",
                "Matched",
                "Energy dropped.",
                learner_controls=1,
            ),
            "Evidence checklist: Prediction ready; Control tried; Outcome selected; Note ready.",
        )
        self.assertEqual(
            _observation_checklist_status(
                "More damping should settle faster.",
                "Matched",
                "Energy dropped.",
                preset_state="needs another preset",
                learner_controls=1,
            ),
            "Evidence checklist: Prediction ready; Control tried; Preset comparison needs another preset; "
            "Outcome selected; Note ready.",
        )
        self.assertEqual(
            _observation_checklist_status(
                "Target should release after backing away.",
                "Matched",
                "Wall phase returned before contact.",
                preset_state="needs required preset Back away",
                learner_controls=1,
            ),
            "Evidence checklist: Prediction ready; Control tried; Preset comparison needs required preset Back away; "
            "Outcome selected; Note ready.",
        )
        self.assertEqual(
            _observation_checklist_status(
                "More damping should settle faster.",
                "Matched",
                "Energy dropped.",
                preset_state="ready",
                learner_controls=1,
            ),
            "Evidence checklist: Prediction ready; Control tried; Preset comparison ready; Outcome selected; Note ready.",
        )

    def test_observation_evidence_quality_summarizes_review_readiness(self) -> None:
        self.assertEqual(
            _observation_evidence_quality("", "Not judged yet", ""),
            "Evidence quality: incomplete - add prediction, learner control, note.",
        )
        self.assertEqual(
            _observation_evidence_quality(
                "",
                "Not judged yet",
                "",
                has_buttons=True,
                has_sliders=True,
                button_next_step="Use Target X - away or Target X + into wall.",
            ),
            "Evidence quality: incomplete - add prediction, control evidence "
            "(use experiment buttons (Target X - away or Target X + into wall) or live sliders), note.",
        )
        self.assertEqual(
            _observation_evidence_quality(
                "Stiffer wall should push harder.",
                "Not judged yet",
                "Force increased.",
                preset_state="needs required preset Back away",
                learner_controls=1,
            ),
            "Evidence quality: incomplete - add preset comparison.",
        )
        self.assertEqual(
            _observation_evidence_quality(
                "More damping should settle faster.",
                "Not judged yet",
                "Energy dropped.",
                learner_controls=1,
            ),
            "Evidence quality: ready to mark - add outcome now or during review.",
        )
        self.assertEqual(
            _observation_evidence_quality(
                "More damping should settle faster.",
                "Matched",
                "Energy dropped.",
                learner_controls=1,
            ),
            "Evidence quality: review-ready - prediction, outcome, note, and required controls are ready.",
        )

    def test_observation_challenge_proof_status_summarizes_missing_evidence(self) -> None:
        self.assertEqual(
            _observation_challenge_proof_status("", "Not judged yet", ""),
            "Challenge proof: needs prediction, then learner control.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "",
                "Not judged yet",
                "",
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "Challenge proof: needs prediction, then use Pull Left A / Left or Push Right D / Right.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "",
                "Not judged yet",
                "",
                preset_state="needs required preset Back away",
                learner_controls=1,
            ),
            "Challenge proof: needs prediction, then try required preset Back away.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "Backing away should release contact.",
                "Not judged yet",
                "",
                preset_state="needs required preset Back away",
                learner_controls=1,
            ),
            "Challenge proof: needs preset evidence - try required preset Back away.",
        )
        self.assertEqual(
            _observation_challenge_proof_status("Stiff wall should push harder.", "Not judged yet", ""),
            "Challenge proof: needs learner control evidence.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
                button_next_step="Use Target X - away or Target X + into wall.",
            ),
            "Challenge proof: needs control evidence - use experiment buttons "
            "(Target X - away or Target X + into wall), live sliders, or Quick presets.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                learner_controls=1,
            ),
            "Challenge proof: needs note or live-status evidence.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "Stiff wall should push harder.",
                "Not judged yet",
                "Force increased.",
                learner_controls=1,
            ),
            "Challenge proof: ready to mark; outcome can be added now or during review.",
        )
        self.assertEqual(
            _observation_challenge_proof_status(
                "Stiff wall should push harder.",
                "Matched",
                "Force increased.",
                learner_controls=1,
            ),
            "Challenge proof: review-ready; compare the saved observation with plots after the run.",
        )

    def test_observation_next_action_names_the_next_learner_step(self) -> None:
        self.assertEqual(
            _observation_next_action("", "Not judged yet", ""),
            "Next action: Write a prediction, then use one button, slider, or preset.",
        )
        self.assertEqual(
            _observation_next_action(
                "",
                "Not judged yet",
                "",
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
            ),
            "Next action: Write a prediction, then use experiment buttons, live sliders, or Quick presets.",
        )
        self.assertEqual(
            _observation_next_action(
                "",
                "Not judged yet",
                "",
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
                button_next_step="Use Target X - away or Target X + into wall.",
            ),
            "Next action: Write a prediction, then use experiment buttons "
            "(Target X - away or Target X + into wall), live sliders, or Quick presets.",
        )
        self.assertEqual(
            _observation_next_action("", "Not judged yet", "", preset_state="needs required preset Close wall"),
            "Next action: Write a prediction, then try required preset Close wall.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                preset_state="needs required preset Back away",
                learner_controls=1,
            ),
            "Next action: Try required preset Back away, then capture the result.",
        )
        self.assertEqual(
            _observation_next_action("Stiff wall should push harder.", "Not judged yet", ""),
            "Next action: Use one button, slider, or preset, then capture the result.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "Next action: Use Pull Left A / Left or Push Right D / Right, then capture the result.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                has_sliders=True,
            ),
            "Next action: Use live sliders, then capture the result.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Not judged yet",
                "",
                learner_controls=1,
            ),
            "Next action: Use live status or write a short observation note.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Not judged yet",
                "Force increased.",
                learner_controls=1,
            ),
            "Next action: Optional: choose a prediction outcome, then press Mark observation.",
        )
        self.assertEqual(
            _observation_next_action(
                "Stiff wall should push harder.",
                "Matched",
                "Force increased.",
                learner_controls=1,
            ),
            "Next action: Press Mark observation.",
        )

    def test_activity_mix_status_guides_live_control_variety(self) -> None:
        log = InteractionLog()

        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=True),
            "Activity mix: 0/3 control families; buttons 0, sliders 0, presets 0, markers 0. "
            "Next: Try a Quick preset to compare a named parameter regime.",
        )

        log.record("preset", "soft", {"kp": 20.0}, label="Soft")
        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=True),
            "Activity mix: 1/3 control families; buttons 0, sliders 0, presets 1, markers 0. "
            "Next: Move one slider after a preset to test a smaller parameter change.",
        )

        log.record("slider", "kp", 35.0, label="Kp")
        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=True),
            "Activity mix: 2/3 control families; buttons 0, sliders 1, presets 1, markers 0. "
            "Next: Use one experiment button such as pulse, nudge, or reset.",
        )
        self.assertEqual(
            _activity_mix_status_message(
                log,
                has_buttons=True,
                has_sliders=True,
                has_presets=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "Activity mix: 2/3 control families; buttons 0, sliders 1, presets 1, markers 0. "
            "Next: Use Pull Left A / Left or Push Right D / Right.",
        )

        log.record("button", "manual_force", 12.0, label="Push Right")
        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=True),
            "Activity mix: 3/3 control families; buttons 1, sliders 1, presets 1, markers 0. "
            "Next: Save one Mark observation with prediction and live-status evidence.",
        )

        log.mark_observation(prediction="Stiffer control should react faster.", note="Error fell quickly.")
        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=True),
            "Activity mix: 3/3 control families; buttons 1, sliders 1, presets 1, markers 1. "
            "Next: Ready: compare this interaction mix against plots and the worksheet.",
        )

    def test_activity_mix_status_uses_available_live_controls(self) -> None:
        log = InteractionLog()

        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=False),
            "Activity mix: 0/2 control families; buttons 0, sliders 0, presets 0, markers 0. "
            "Next: Move one slider to test a smaller parameter change.",
        )

        slider_only_log = InteractionLog()
        slider_only_log.record("slider", "kp", 35.0, label="Kp")
        self.assertEqual(
            _activity_mix_status_message(slider_only_log, has_buttons=False, has_sliders=True, has_presets=False),
            "Activity mix: 1/1 control families; buttons 0, sliders 1, presets 0, markers 0. "
            "Next: Save one Mark observation with prediction and live-status evidence.",
        )

        button_only_log = InteractionLog()
        button_only_log.record("button", "manual_force", 12.0, label="Push Right")
        self.assertEqual(
            _activity_mix_status_message(button_only_log, has_buttons=False, has_sliders=False, has_presets=False),
            "Activity mix: 1/1 control families; buttons 1, sliders 0, presets 0, markers 0. "
            "Next: Save one Mark observation with prediction and live-status evidence.",
        )

    def test_available_learner_control_families_ignore_view_helpers(self) -> None:
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)])
        preset_tuning = LiveTuning(
            [SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)],
            presets=[TuningPreset("soft", "Soft", {"kp": 10.0})],
        )

        self.assertEqual(
            _available_learner_control_families(control_enabled=False, reset_enabled=False, tuning=tuning),
            (False, True, False),
        )
        self.assertEqual(
            _available_learner_control_families(control_enabled=True, reset_enabled=False, tuning=None),
            (True, False, False),
        )
        self.assertEqual(
            _available_learner_control_families(control_enabled=False, reset_enabled=True, tuning=None),
            (True, False, False),
        )
        self.assertEqual(
            _available_learner_control_families(control_enabled=False, reset_enabled=False, tuning=preset_tuning),
            (False, True, True),
        )

    def test_activity_mix_button_next_step_names_live_panel_buttons(self) -> None:
        pulse = KeyForcePulse({"interaction": {"key_force": True, "panel": True}})
        self.assertEqual(
            _activity_mix_button_next_step_for_panel(pulse),
            "Use Pull Left A / Left or Push Right D / Right.",
        )

        target = TargetOffsetControl(
            {
                "interaction": {
                    "target_nudge": True,
                    "panel": True,
                    "target_left_label": "Target X - away",
                    "target_right_label": "Target X + into wall",
                }
            }
        )
        self.assertEqual(
            _activity_mix_button_next_step_for_panel(target),
            "Use Target X - away or Target X + into wall.",
        )

        reset = ExperimentResetControl({"interaction": {"panel": True, "reset_plant": True}})
        disabled_control = TargetOffsetControl({"interaction": {"target_nudge": False}})
        self.assertEqual(
            _activity_mix_button_next_step_for_panel(disabled_control, reset),
            "Use Reset plant after changing a control to repeat the observation.",
        )

    def test_activity_mix_status_ignores_helper_and_view_buttons_as_controls(self) -> None:
        log = InteractionLog()

        log.record("button", "use_live_status_note", "position=0.1", label="Use live status")
        log.record("button", "use_changed_values_note", "Kp=40", label="Use changed values")
        log.record("button", "clear_observation_note", {"items_removed": 2}, label="Clear note")
        log.record("button", "pause_simulation", True, label="Pause simulation")
        log.record("button", "step_simulation", True, label="Step once")
        log.record("slider", "playback_speed", 0.5, label="Playback speed")
        self.assertEqual(
            _activity_mix_status_message(log, has_buttons=True, has_sliders=True, has_presets=False),
            "Activity mix: 0/2 control families; buttons 0, sliders 0, presets 0, markers 0. "
            "Next: Move one slider to test a smaller parameter change.",
        )
        self.assertEqual(
            _observation_evidence_quality(
                "Stiffer control should react faster.",
                "Matched",
                "Live status: position=0.1",
                learner_controls=0,
            ),
            "Evidence quality: incomplete - add learner control.",
        )

    def test_recent_action_status_confirms_latest_logged_control(self) -> None:
        log = InteractionLog()

        self.assertEqual(_recent_action_status_message(log), "Action log: no learner actions yet.")

        log.record("button", "manual_force", 12.0, label="Push Right")
        self.assertEqual(
            _recent_action_status_message(log),
            "Action log: 1 event; 1 learner control; last Push Right.",
        )

        log.set_time(1.25)
        log.record("slider", "kp", 40.0, label="Kp")
        self.assertEqual(
            _recent_action_status_message(log),
            "Action log: 2 events; 2 learner controls; last Kp at t=1.250s.",
        )

        log.record("button", "use_live_status_note", "position=0.1", label="Use live status")
        self.assertEqual(
            _recent_action_status_message(log),
            "Action log: 3 events; 2 learner controls; last learner control Kp at t=1.250s; "
            "last action Use live status at t=1.250s.",
        )

    def test_recent_action_status_separates_helper_only_events(self) -> None:
        log = InteractionLog()

        log.record("button", "use_live_status_note", "position=0.1", label="Use live status")
        self.assertEqual(
            _recent_action_status_message(log),
            "Action log: 1 event; no learner-control event yet; last action Use live status.",
        )

        log.set_time(0.5)
        log.record("button", "clear_observation_note", {"items_removed": 2}, label="Clear note")
        self.assertEqual(
            _recent_action_status_message(log),
            "Action log: 2 events; no learner-control event yet; last action Clear note at t=0.500s.",
        )

    def test_live_status_formats_dashboard_values(self) -> None:
        status = LiveStatus([StatusSpec("position", "Position [m]"), StatusSpec("mode", "Mode")])

        self.assertEqual(status.snapshot()["position"], "--")
        status.set_values(position=1.23456, mode="tracking", ignored=99.0)

        snapshot = status.snapshot()
        self.assertEqual(snapshot["position"], "1.235")
        self.assertEqual(snapshot["mode"], "tracking")
        self.assertNotIn("ignored", snapshot)

    def test_live_status_observation_note_summarizes_available_values(self) -> None:
        status = LiveStatus(
            [
                StatusSpec("position", "Position [m]"),
                StatusSpec("force", "Force [N]"),
                StatusSpec("pending", "Pending value"),
            ]
        )

        self.assertEqual(_live_status_observation_note(None), "")
        self.assertEqual(_live_status_observation_note(status), "")

        status.set_values(position=0.125, force=-3.5)

        self.assertEqual(
            _live_status_observation_note(status),
            "Position [m]: 0.125; Force [N]: -3.500",
        )

    def test_runtime_status_helpers_show_elapsed_and_remaining_time(self) -> None:
        status = LiveStatus(runtime_status_specs())

        status.set_values(**runtime_status_values(1.25, 3.0))

        self.assertEqual(status.snapshot()["run_time"], "1.250")
        self.assertEqual(status.snapshot()["remaining_time"], "1.750")
        self.assertEqual(
            _live_status_observation_note(status),
            "Run time [s]: 1.250; Remaining [s]: 1.750",
        )
        self.assertEqual(runtime_status_values(4.0, 3.0)["remaining_time"], 0.0)

    def test_run_clock_cue_turns_remaining_time_into_action(self) -> None:
        self.assertEqual(_run_clock_cue({}), "")
        self.assertEqual(
            _run_clock_cue({"run_time": "1.250", "remaining_time": "1.750"}, pause_available=True),
            "Run clock: t=1.250s, 1.750s left.",
        )
        self.assertEqual(
            _run_clock_cue({"run_time": "2.400", "remaining_time": "0.600"}, pause_available=True),
            "Run clock: 0.600s left - press Pause / Resume now if you need more time to inspect.",
        )
        self.assertEqual(
            _run_clock_cue({"run_time": "2.400", "remaining_time": "0.600"}, pause_available=False),
            "Run clock: 0.600s left - the run will finish soon.",
        )
        self.assertEqual(
            _run_clock_cue({"run_time": "3.000", "remaining_time": "0.000"}, pause_available=True),
            "Run clock: run finished; review the report or rerun with a longer sim_time.",
        )

    def test_changed_tuning_observation_note_summarizes_slider_changes(self) -> None:
        tuning = LiveTuning(
            [
                SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0),
                SliderSpec("kd", "Kd", 0.0, 20.0, 2.0, 0.5),
            ]
        )

        self.assertEqual(_changed_tuning_observation_note(None), "")
        self.assertEqual(_changed_tuning_observation_note(tuning), "")

        tuning.set_value("kp", 35.0)

        self.assertEqual(_changed_tuning_observation_note(tuning), "Changed values: Kp=35")

    def test_append_observation_note_preserves_existing_evidence(self) -> None:
        self.assertEqual(_append_observation_note("", "Position [m]: 0.100"), "Position [m]: 0.100")
        self.assertEqual(_append_observation_note("Manual note", ""), "Manual note")
        self.assertEqual(
            _append_observation_note("Manual note", "Changed values: Kp=35"),
            "Manual note; Changed values: Kp=35",
        )
        self.assertEqual(
            _append_observation_note("Manual note; Changed values: Kp=35", "Changed values: Kp=35"),
            "Manual note; Changed values: Kp=35",
        )
        self.assertEqual(
            _append_observation_note(
                "Manual note; Position [m]: 0.100; Force [N]: 2.000",
                "Position [m]: 0.100; Force [N]: 2.000",
            ),
            "Manual note; Position [m]: 0.100; Force [N]: 2.000",
        )

    def test_observation_note_preview_shows_current_saved_text(self) -> None:
        self.assertEqual(_observation_note_preview(""), "Note preview: empty")
        self.assertEqual(
            _observation_note_preview(
                "Manual note; Position [m]: 0.100; Force [N]: 2.000; Changed values: Kp=35"
            ),
            "Note preview (4 items): Manual note | Position [m]: 0.100 | Force [N]: 2.000 | "
            "Changed values: Kp=35",
        )
        self.assertEqual(
            _observation_note_preview("Manual note\nChanged values: Kp=35"),
            "Note preview (2 items): Manual note | Changed values: Kp=35",
        )
        self.assertEqual(
            _observation_note_value("Manual note\n\nChanged values: Kp=35;  Force [N]: 2.000"),
            "Manual note; Changed values: Kp=35; Force [N]: 2.000",
        )

    def test_learner_snapshot_collects_final_interactive_state(self) -> None:
        log = InteractionLog()
        tuning = LiveTuning([SliderSpec("kp", "Kp", 0.0, 100.0, 20.0, 1.0)], event_log=log)
        status = LiveStatus([StatusSpec("error", "Error [m]")])
        playback = SimulationPlaybackControl({"interaction": {"panel": True}}, event_log=log)

        tuning.set_value("kp", 35.0)
        status.set_values(error=0.125)
        playback.set_speed(1.5)

        snapshot = learner_snapshot(
            tuning=tuning,
            status=status,
            playback_control=playback,
            extra_controls={"joint_target_offset": 0.2},
        )

        self.assertEqual(
            snapshot,
            {
                "slider_values": {"kp": 35.0},
                "changed_sliders": {"kp": 35.0},
                "live_status": {"error": "0.125"},
                "playback_speed": 1.5,
                "extra_controls": {"joint_target_offset": 0.2},
            },
        )

    def test_learner_tuned_config_merges_updates_and_disables_live_controls(self) -> None:
        base_config = {
            "target": {"end": 0.0, "start": 0.0},
            "controller": {"kp": 20.0, "kd": 2.0},
            "interaction": {
                "panel": True,
                "live_tuning": True,
                "key_force": True,
                "target_nudge": True,
                "joint_disturbance": True,
                "playback_speed": True,
            },
        }

        tuned = learner_tuned_config(
            base_config,
            {"target": {"end": 0.35}, "controller": {"kp": 60.0}},
        )

        self.assertEqual(tuned["target"], {"end": 0.35, "start": 0.0})
        self.assertEqual(tuned["controller"], {"kp": 60.0, "kd": 2.0})
        self.assertFalse(tuned["interaction"]["panel"])
        self.assertFalse(tuned["interaction"]["live_tuning"])
        self.assertFalse(tuned["interaction"]["key_force"])
        self.assertFalse(tuned["interaction"]["target_nudge"])
        self.assertFalse(tuned["interaction"]["joint_disturbance"])
        self.assertFalse(tuned["interaction"]["playback_speed"])
        self.assertTrue(base_config["interaction"]["panel"])

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
                ("Mission", "Move the slider; prove it with Tracking error."),
                (
                    "Playbook",
                    "1. predict how Tracking error will change; 2. change controller.kp; "
                    "3. mark one observation with Tracking error.",
                ),
                ("Start steps", "Predict -> Run viewer -> move one live slider -> Mark observation."),
                (
                    "Viewer controls",
                    "MuJoCo side panels are hidden; use YAML configs or the MCLab Interaction controls instead",
                ),
                (
                    "Challenge",
                    "Use controller.kp to create a visible change in Tracking error, "
                    "then save one prediction-backed observation.",
                ),
                ("Try", "Move the slider."),
                ("Change", "controller.kp"),
                (
                    "Done when",
                    "use at least one button, slider, or preset, then write a Prediction and note, "
                    "choose an outcome if known, and press Mark observation.",
                ),
                ("Prediction", "Before changing controller.kp, predict how Tracking error will change."),
                ("Question", "Which gain gives the cleanest response?"),
                ("Watch", "Tracking error."),
            ],
        )
        self.assertEqual(_panel_guide_rows(None), [])

        rows_with_course = _panel_guide_rows(
            guide,
            config_path="configs/lab04_panda/interactive_virtual_wall.yaml",
        )
        self.assertEqual(
            rows_with_course[0],
            ("Course step", "11/12 - Touch virtual wall; Tune wall position, stiffness, damping, and retreat gain."),
        )

    def test_panel_guidance_names_controls_that_count_for_completion(self) -> None:
        guide = RunGuide(
            title="Demo Guide",
            focus="Focus text",
            try_this="Move the slider.",
            change="controller.kp",
            question="Which gain gives the cleanest response?",
            watch="Tracking error.",
            next_step="Run the comparison.",
        )

        self.assertIn(
            (
                "Counts as control",
                "experiment buttons, live sliders, Quick presets; "
                "view/evidence helpers such as Pause, Playback speed, and Use live status do not count.",
            ),
            _panel_guide_rows(guide, has_buttons=True, has_sliders=True, has_presets=True),
        )
        self.assertIn(
            (
                "Done when",
                "use experiment buttons, live sliders, or Quick presets at least once, "
                "then write a Prediction and note, choose an outcome if known, and press Mark observation.",
            ),
            _panel_guide_rows(guide, has_buttons=True, has_sliders=True, has_presets=True),
        )
        labeled_rows = _panel_guide_rows(
            guide,
            has_buttons=True,
            has_sliders=True,
            has_presets=True,
            button_next_step="Use Target X - away or Target X + into wall.",
        )
        self.assertIn(
            (
                "Start steps",
                "Predict -> Run viewer -> use experiment buttons "
                "(Target X - away or Target X + into wall), live sliders, or Quick presets -> Mark observation.",
            ),
            labeled_rows,
        )
        self.assertIn(
            (
                "Counts as control",
                "experiment buttons (Target X - away or Target X + into wall), live sliders, Quick presets; "
                "view/evidence helpers such as Pause, Playback speed, and Use live status do not count.",
            ),
            labeled_rows,
        )
        self.assertIn(
            (
                "Done when",
                "use experiment buttons (Target X - away or Target X + into wall), live sliders, "
                "or Quick presets at least once, then write a Prediction and note, "
                "choose an outcome if known, and press Mark observation.",
            ),
            labeled_rows,
        )
        self.assertEqual(
            _panel_completion_text(has_sliders=True),
            "use live sliders at least once, then write a Prediction and note, "
            "choose an outcome if known, and press Mark observation.",
        )
        self.assertEqual(
            _panel_completion_text(
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
            "use Pull Left A / Left or Push Right D / Right at least once, "
            "then write a Prediction and note, choose an outcome if known, and press Mark observation.",
        )
        self.assertIn(
            (
                "Start steps",
                "Predict -> Run viewer -> use Pull Left A / Left or Push Right D / Right -> Mark observation.",
            ),
            _panel_guide_rows(
                guide,
                has_buttons=True,
                button_next_step="Use Pull Left A / Left or Push Right D / Right.",
            ),
        )
        self.assertEqual(_panel_control_credit_text(False, False, False), "")

    def test_panel_guidance_names_required_preset_start_steps(self) -> None:
        guide = RunGuide(
            title="Wall Guide",
            focus="Create and release virtual wall contact.",
            try_this="Use the required presets.",
            change="live sliders/presets: wall target",
            question="Which preset releases contact?",
            watch="Wall phase and penetration.",
            next_step="Review the worksheet.",
        )
        tuning = LiveTuning(
            [SliderSpec("target_x", "Target X", 0.0, 1.0, 0.5, 0.01)],
            presets=[
                TuningPreset("soft_wall", "Soft wall", {"target_x": 0.55}),
                TuningPreset("close_wall", "Close wall", {"target_x": 0.64}, required=True),
                TuningPreset("back_away", "Back away", {"target_x": 0.52}, required=True),
                TuningPreset("re_enter_wall", "Re-enter wall", {"target_x": 0.65}, required=True),
            ],
        )

        self.assertIn(
            (
                "Start steps",
                "Predict -> Run viewer -> try required presets Close wall -> Back away -> Re-enter wall -> Mark observation.",
            ),
            _panel_guide_rows(guide, tuning=tuning, has_sliders=True, has_presets=True),
        )
        self.assertIn(
            (
                "Start steps",
                "Predict -> Run viewer -> try required presets Close wall -> Back away -> Re-enter wall -> Mark observation.",
            ),
            _panel_guide_rows(
                guide,
                tuning=tuning,
                has_buttons=True,
                button_next_step="Use Target X - away or Target X + into wall.",
            ),
        )
        self.assertIn(
            (
                "Done when",
                "try required presets Close wall -> Back away -> Re-enter wall, then "
                "write a Prediction and note, choose an outcome if known, and press Mark observation.",
            ),
            _panel_guide_rows(guide, tuning=tuning, has_sliders=True, has_presets=True),
        )

    def test_panel_guidance_exposes_viewer_legend(self) -> None:
        guide = RunGuide(
            "Lab04 Virtual Wall Interactive",
            "Tune the hand target and virtual wall parameters.",
            "Move Target X through the wall.",
            "live sliders/presets: Target X/Y/Z, wall X, stiffness",
            "Target-Wall gap, Wall penetration, wall force, hand X, green target marker, and orange contact hand marker.",
            "Compare virtual_wall.png with the live settings.",
        )

        rows = _panel_viewer_legend_rows(guide)

        self.assertIn(("Green sphere", "Cartesian hand target."), rows)
        self.assertIn(("Red plane", "Virtual wall location."), rows)
