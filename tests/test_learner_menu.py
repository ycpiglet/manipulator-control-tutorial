from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402
from mclab.learner_menu import (  # noqa: E402
    ActionReadiness,
    BATCH_ACTIONS,
    EXPERIENCE_FILTERS,
    LEARNING_PATH,
    LearningPathProgress,
    MENU_ACTIONS,
    MenuAction,
    _launch_batch_from_menu,
    _launch_from_menu,
    _launch_learning_path_tuned_replay_from_menu,
    _launch_tuned_replay_from_menu,
    _set_status_after_run,
    _set_status_after_doctor,
    action_badges,
    action_compare_batch,
    action_compare_text,
    action_controls_text,
    action_activity_mix_text,
    action_evidence_text,
    action_followup,
    action_followup_text,
    action_config_path,
    action_history_text,
    action_latest_evidence_text,
    action_latest_output,
    action_latest_plot,
    action_latest_tuned_config,
    action_latest_worksheet,
    action_mission_text,
    action_mission_evidence_text,
    action_next_cue_text,
    action_plan_text,
    action_plot_review_text,
    action_plot_text,
    action_preset_evidence_text,
    action_readiness,
    action_replay_text,
    action_tags,
    action_worksheet_text,
    action_doc_path,
    action_viewer_text,
    batch_readiness,
    batch_plan_text,
    build_batch_args,
    build_doctor_args,
    build_run_args,
    build_tuned_replay_args,
    config_value_preview,
    experience_filter_description,
    filter_menu_actions,
    learning_path_completion_text,
    learning_path_progress_items,
    learning_path_latest_output,
    learning_path_latest_tuned_config,
    learning_path_latest_worksheet,
    learning_path_progress,
    learning_path_requires_evidence,
    learning_path_progress_text,
    learning_path_summary_text,
    learning_path_target,
    learning_path_text,
    lesson_text_for_batch,
    lesson_text,
    configured_preset_comparison,
    configured_preset_labels,
    configured_preset_purposes,
    configured_required_preset_labels,
    launch_action_latest_output,
    launch_action_latest_plot,
    launch_action_latest_worksheet,
    launch_learning_path_latest_output,
    launch_learning_path_latest_worksheet,
    launch_next_review_output,
    launch_latest_plot,
    launch_latest_worksheet,
    launch_outputs_index,
    launch_latest_output,
    next_review_output,
    next_learning_path_step,
    open_editable_path,
    parameter_hint,
    parse_run_output_path,
    prediction_prompt,
    reflection_question,
    review_queue_summary_text,
    refresh_batch_menu_state,
)


class FakeStatus:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class FakeButton:
    def __init__(self) -> None:
        self.state_calls: list[list[str]] = []

    def state(self, states: list[str]) -> None:
        self.state_calls.append(states)


class FakeTextVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class LearnerMenuTests(unittest.TestCase):
    def test_menu_covers_core_learner_experiences(self) -> None:
        labels = {(action.group, action.label) for action in MENU_ACTIONS}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Underdamped"), labels)
        self.assertIn(("Lab01 Mass-Spring-Damper", "Overdamped"), labels)
        self.assertIn(("Lab01 Mass-Spring-Damper", "Interactive"), labels)
        self.assertIn(("Lab02 PID Control", "Low P gain"), labels)
        self.assertIn(("Lab02 PID Control", "Anti-windup"), labels)
        self.assertIn(("Lab02 PID Control", "Sensor noise"), labels)
        self.assertIn(("Lab02 PID Control", "Control delay"), labels)
        self.assertIn(("Lab02 PID Control", "Interactive"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF joint-space"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF task-space"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF singularity"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF early DLS damping"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF late DLS damping"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF inner-target DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF edge-target DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF shoulder-disturbance DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF elbow-disturbance DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF staggered-disturbance DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF high-torque DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF slow-command DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF fast-command DLS"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF interactive"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Step profile"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Minimum jerk"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "1D interactive"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Neutral hold"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "30s stability hold"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Reach X"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian reach"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Soft Cartesian"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Stiff Cartesian"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian interactive"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Joint target"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Soft wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Stiff wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Low damping wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "High damping wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Near wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Far wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Slow approach wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Fast approach wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Contact cycle wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Low retreat wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "High retreat wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Virtual wall"), labels)

    def test_menu_actions_launch_learner_viewer_commands(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                args = build_run_args(action)
                self.assertEqual(args[1:4], ["-m", "mclab", "run"])
                self.assertIn("--viewer", args)
                self.assertNotIn("--show-viewer-ui", args)
                self.assertIn("--realtime", args)
                self.assertIn("--pause-at-end", args)
                self.assertIn("--plot", args)
                self.assertIn("--open-report", args)
                self.assertIn(action.config_path, args)
                plot_index = args.index("--plots")
                self.assertEqual(args[plot_index + 1], action.plots)

    def test_tuned_replay_commands_use_saved_config_without_debug_side_panels(self) -> None:
        for action in MENU_ACTIONS:
            tuned_config = ROOT / "outputs" / "run" / "learner_tuned_config.yaml"
            with self.subTest(label=action.label, config=action.config_path):
                args = build_tuned_replay_args(action, tuned_config)
                self.assertEqual(args[1:4], ["-m", "mclab", "run"])
                self.assertIn(action.lab_name, args)
                self.assertIn(str(tuned_config), args)
                self.assertIn("--viewer", args)
                self.assertIn("--realtime", args)
                self.assertIn("--pause-at-end", args)
                self.assertIn("--plot", args)
                self.assertIn("--open-report", args)
                self.assertNotIn("--show-viewer-ui", args)
                plot_index = args.index("--plots")
                self.assertEqual(args[plot_index + 1], action.plots)

    def test_batch_actions_launch_headless_comparison_commands(self) -> None:
        labels = {action.label for action in BATCH_ACTIONS}
        self.assertIn("All compare", labels)
        self.assertIn("Lab01 compare", labels)
        self.assertIn("Lab02 PID compare", labels)
        self.assertIn("Lab03 2DOF compare", labels)
        self.assertIn("Lab04 wall compare", labels)
        self.assertIn("Lab04 Cartesian compare", labels)

        for action in BATCH_ACTIONS:
            with self.subTest(label=action.label):
                args = build_batch_args(action)
                self.assertEqual(args[1:4], ["-m", "mclab", "batch"])
                self.assertIn(action.batch_name, args)
                self.assertIn("--open-report", args)
                self.assertNotIn("--viewer", args)
                self.assertNotIn("--show-viewer-ui", args)
                text = lesson_text_for_batch(action)
                self.assertIn("Setup:", text)
                self.assertIn("Mission:", text)
                self.assertIn(action_mission_text(action), text)
                self.assertIn("Mission evidence:", text)
                self.assertIn("History:", text)
                self.assertIn("Try:", text)
                self.assertIn("Watch:", text)
                self.assertIn("Runs:", text)
                self.assertEqual(batch_readiness(action).status, "ok")

    def test_menu_can_launch_setup_check(self) -> None:
        args = build_doctor_args()
        self.assertEqual(args[1:], ["-m", "mclab", "doctor"])

        status = FakeStatus()
        _set_status_after_doctor(status, 0, "Summary: 5 OK, 0 WARN, 0 FAIL")
        self.assertIn("Setup check passed", status.value)
        self.assertIn("5 OK", status.value)

        _set_status_after_doctor(status, 1, "Summary: 4 OK, 0 WARN, 1 FAIL")
        self.assertIn("Setup check found issues", status.value)
        self.assertIn("python -m mclab doctor", status.value)

    def test_recommended_learning_path_targets_real_actions(self) -> None:
        self.assertGreaterEqual(len(LEARNING_PATH), 11)
        self.assertEqual(LEARNING_PATH[0].title, "1. Feel 1D physics")
        self.assertEqual(LEARNING_PATH[6].title, "7. Handle singularity")
        self.assertEqual(LEARNING_PATH[-1].label, "All compare")

        for step in LEARNING_PATH:
            with self.subTest(step=step.title):
                action = learning_path_target(step)
                text = learning_path_text(step)
                self.assertIn("Run:", text)
                self.assertIn("Mission:", text)
                self.assertIn(action_mission_text(action), text)
                self.assertIn("Done when:", text)
                self.assertIn(learning_path_completion_text(step), text)
                self.assertIn("Watch:", text)
                if step.action_kind == "run":
                    self.assertIn(action, MENU_ACTIONS)
                    args = build_run_args(action)
                    self.assertIn("--open-report", args)
                    self.assertIn("--viewer", args)
                else:
                    self.assertIn(action, BATCH_ACTIONS)
                    args = build_batch_args(action)
                    self.assertIn("--open-report", args)
                    self.assertNotIn("--viewer", args)

        self.assertEqual(
            learning_path_completion_text(LEARNING_PATH[0]),
            "Done when: the run report, priority plot, and worksheet are saved.",
        )
        self.assertEqual(
            learning_path_completion_text(LEARNING_PATH[1]),
            "Done when: save one Mark observation with a Prediction and note; add the outcome during review.",
        )
        self.assertEqual(
            learning_path_completion_text(LEARNING_PATH[-1]),
            "Done when: the comparison report, plots, and worksheet are saved.",
        )

    def test_recommended_learning_path_reads_saved_progress(self) -> None:
        first_step = LEARNING_PATH[0]
        last_step = LEARNING_PATH[-1]
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_dir = outputs / "run_lab01"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
            worksheet = run_dir / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")
            tuned_config = run_dir / "learner_tuned_config.yaml"
            tuned_config.write_text("interaction:\n  panel: false\n", encoding="utf-8")

            batch_dir = outputs / "all_batches"
            batch_dir.mkdir()
            (batch_dir / "summary.json").write_text(
                json.dumps({"lab_name": "batch_group", "batch_name": "all", "config_name": "all"}),
                encoding="utf-8",
            )
            (batch_dir / "report.html").write_text("<html></html>", encoding="utf-8")

            first_progress = learning_path_progress(first_step, outputs)
            last_progress = learning_path_progress(last_step, outputs)
            second_progress = learning_path_progress(LEARNING_PATH[1], outputs)
            progress_items = learning_path_progress_items(outputs)
            first_latest = learning_path_latest_output(first_step, outputs)
            last_latest = learning_path_latest_output(last_step, outputs)
            first_worksheet = learning_path_latest_worksheet(first_step, outputs)
            last_worksheet = learning_path_latest_worksheet(last_step, outputs)
            first_tuned = learning_path_latest_tuned_config(first_step, outputs)
            last_tuned = learning_path_latest_tuned_config(last_step, outputs)

        self.assertTrue(first_progress.completed)
        self.assertEqual(first_progress.latest_output.name, "run_lab01")
        assert first_latest is not None
        self.assertEqual(first_latest.name, "run_lab01")
        self.assertEqual(first_worksheet, worksheet)
        self.assertEqual(first_tuned, tuned_config)
        self.assertIn("Status: Done - latest run_lab01", learning_path_progress_text(first_step, first_progress))
        self.assertTrue(last_progress.completed)
        self.assertEqual(last_progress.latest_output.name, "all_batches")
        assert last_latest is not None
        self.assertEqual(last_latest.name, "all_batches")
        self.assertIsNone(last_worksheet)
        self.assertIsNone(last_tuned)
        self.assertFalse(second_progress.completed)
        self.assertIn("Status: Not run yet", learning_path_progress_text(LEARNING_PATH[1], second_progress))
        self.assertEqual(next_learning_path_step(progress_items), LEARNING_PATH[1])
        self.assertIn("Progress: 2/11 complete", learning_path_summary_text(progress_items))
        self.assertIn("Next: 2. Disturb and tune", learning_path_summary_text(progress_items))
        self.assertIn("Next action: run Lab01 Mass-Spring-Damper - Interactive", learning_path_summary_text(progress_items))
        self.assertIn("Done when: save one Mark observation with a Prediction", learning_path_summary_text(progress_items))
        self.assertIn("Predict:", learning_path_summary_text(progress_items))
        self.assertIn("Watch:", learning_path_summary_text(progress_items))

    def test_recommended_learning_path_requires_observation_for_hands_on_steps(self) -> None:
        first_step = LEARNING_PATH[0]
        second_step = LEARNING_PATH[1]
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_dir = outputs / "run_lab01"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")

            interactive_dir = outputs / "run_lab01_interactive"
            interactive_dir.mkdir()
            (interactive_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (interactive_dir / "report.html").write_text("<html></html>", encoding="utf-8")

            needs_evidence = learning_path_progress(second_step, outputs)
            needs_summary = learning_path_summary_text(learning_path_progress_items(outputs))

            (interactive_dir / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"question": "Question: demo?", "note": "Saw the mass settle."},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            needs_prediction = learning_path_progress(second_step, outputs)
            needs_prediction_summary = learning_path_summary_text(learning_path_progress_items(outputs))

            (interactive_dir / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "note": "Saw the mass settle.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            needs_outcome = learning_path_progress(second_step, outputs)
            needs_outcome_summary = learning_path_summary_text(learning_path_progress_items(outputs))

            (interactive_dir / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            needs_note = learning_path_progress(second_step, outputs)
            needs_note_summary = learning_path_summary_text(learning_path_progress_items(outputs))

            (interactive_dir / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                                "note": "Saw the mass settle.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            complete_progress = learning_path_progress(second_step, outputs)
            complete_summary = learning_path_summary_text(learning_path_progress_items(outputs))

        self.assertFalse(learning_path_requires_evidence(first_step))
        self.assertTrue(learning_path_requires_evidence(second_step))
        self.assertFalse(needs_evidence.completed)
        self.assertEqual(needs_evidence.observation_markers, 0)
        self.assertIn("Status: Needs observation - latest run_lab01_interactive", learning_path_progress_text(second_step, needs_evidence))
        self.assertIn("Add one Mark observation entry", learning_path_progress_text(second_step, needs_evidence))
        self.assertIn("Progress: 1/11 complete", needs_summary)
        self.assertIn("Evidence pending: 1 hands-on step(s).", needs_summary)
        self.assertIn("Next: 2. Disturb and tune", needs_summary)

        self.assertFalse(needs_prediction.completed)
        self.assertEqual(needs_prediction.observation_markers, 1)
        self.assertEqual(needs_prediction.learner_predictions, 0)
        self.assertEqual(needs_prediction.learner_notes, 1)
        self.assertIn(
            "Status: Needs prediction - latest run_lab01_interactive (1 observation, 1 note)",
            learning_path_progress_text(second_step, needs_prediction),
        )
        self.assertIn("Add one Prediction in Mark observation", learning_path_progress_text(second_step, needs_prediction))
        self.assertIn("Progress: 1/11 complete", needs_prediction_summary)
        self.assertIn("Evidence pending: 1 hands-on step(s).", needs_prediction_summary)

        self.assertTrue(needs_outcome.completed)
        self.assertEqual(needs_outcome.learner_predictions, 1)
        self.assertEqual(needs_outcome.learner_outcomes, 0)
        self.assertIn("Outcome review pending: 1 hands-on step(s).", needs_outcome_summary)
        self.assertIn("Add one Prediction outcome while reviewing.", learning_path_progress_text(second_step, needs_outcome))

        self.assertFalse(needs_note.completed)
        self.assertEqual(needs_note.learner_notes, 0)
        self.assertIn("Progress: 1/11 complete", needs_note_summary)
        self.assertIn("Evidence pending: 1 hands-on step(s).", needs_note_summary)
        self.assertIn(
            "Status: Needs note - latest run_lab01_interactive (1 observation, 1 prediction, 1 outcome)",
            learning_path_progress_text(second_step, needs_note),
        )
        self.assertIn(
            "Add a short note or Use live status before moving on.",
            learning_path_progress_text(second_step, needs_note),
        )

        self.assertTrue(complete_progress.completed)
        self.assertEqual(complete_progress.observation_markers, 1)
        self.assertEqual(complete_progress.learner_predictions, 1)
        self.assertEqual(complete_progress.learner_outcomes, 1)
        self.assertEqual(complete_progress.learner_notes, 1)
        self.assertIn(
            "Status: Done - latest run_lab01_interactive (1 observation, 1 prediction, 1 outcome, 1 note)",
            learning_path_progress_text(second_step, complete_progress),
        )
        self.assertNotIn("Outcome review pending", complete_summary)

    def test_recommended_learning_path_includes_condition_aware_dls_evidence_step(self) -> None:
        dls_step = LEARNING_PATH[6]
        action = learning_path_target(dls_step)

        self.assertEqual(dls_step.title, "7. Handle singularity")
        self.assertEqual(action.label, "2DOF condition-aware DLS")
        self.assertTrue(learning_path_requires_evidence(dls_step))
        self.assertIn("condition-aware DLS", learning_path_text(dls_step))

    def test_recommended_learning_path_requires_wall_required_presets(self) -> None:
        wall_step = LEARNING_PATH[9]
        action = learning_path_target(wall_step)
        assert isinstance(action, MenuAction)

        def write_events(run_path: Path, preset_labels: list[str]) -> None:
            events = [
                {"kind": "preset", "name": label.lower().replace(" ", "_"), "label": label}
                for label in preset_labels
            ]
            events.append(
                {
                    "kind": "marker",
                    "name": "observation",
                    "value": {
                        "question": "Question: wall release?",
                        "prediction": "Back away should release contact.",
                        "outcome": "Matched",
                        "note": "Wall phase returned before contact.",
                    },
                }
            )
            (run_path / "interaction_events.json").write_text(json.dumps(events), encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab04_wall_interactive"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": action.lab_name,
                        "config_path": action.config_path,
                        "config_name": Path(action.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )

            write_events(run_path, ["Soft wall", "Stiff wall"])
            missing_close = learning_path_progress(wall_step, outputs)

            write_events(run_path, ["Close wall"])
            missing_back = learning_path_progress(wall_step, outputs)
            missing_back_text = learning_path_progress_text(wall_step, missing_back)
            missing_back_mission = action_mission_evidence_text(action, outputs)

            write_events(run_path, ["Close wall", "Back away"])
            missing_reenter = learning_path_progress(wall_step, outputs)
            missing_reenter_text = learning_path_progress_text(wall_step, missing_reenter)

            write_events(run_path, ["Re-enter wall", "Close wall", "Back away"])
            out_of_order = learning_path_progress(wall_step, outputs)

            write_events(run_path, ["Close wall", "Back away", "Re-enter wall"])
            complete = learning_path_progress(wall_step, outputs)

        self.assertEqual(wall_step.title, "10. Touch virtual wall")
        self.assertIn("required presets: Close wall -> Back away -> Re-enter wall", learning_path_completion_text(wall_step))
        self.assertFalse(missing_close.completed)
        self.assertEqual(missing_close.required_presets, 3)
        self.assertEqual(missing_close.required_presets_tried, 0)
        self.assertEqual(missing_close.next_required_preset, "Close wall")
        self.assertFalse(missing_back.completed)
        self.assertEqual(missing_back.required_presets_tried, 1)
        self.assertEqual(missing_back.next_required_preset, "Back away")
        self.assertIn("Status: Needs required preset", missing_back_text)
        self.assertIn("required presets 1/3", missing_back_text)
        self.assertIn("Try required preset Back away", missing_back_text)
        self.assertIn(
            "Mission evidence: Needs required preset Back away; 1 observation, 1 prediction, 1 outcome, 1 note; required presets 1/3",
            missing_back_mission,
        )
        self.assertFalse(missing_reenter.completed)
        self.assertEqual(missing_reenter.required_presets_tried, 2)
        self.assertEqual(missing_reenter.next_required_preset, "Re-enter wall")
        self.assertIn("Try required preset Re-enter wall", missing_reenter_text)
        self.assertFalse(out_of_order.completed)
        self.assertEqual(out_of_order.required_presets_tried, 2)
        self.assertEqual(out_of_order.next_required_preset, "Re-enter wall")
        self.assertTrue(complete.completed)
        self.assertEqual(complete.required_presets_tried, 3)

    def test_recommended_learning_path_report_opens_latest_output(self) -> None:
        first_step = LEARNING_PATH[0]
        second_step = LEARNING_PATH[1]
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_dir = outputs / "run_lab01"
            run_dir.mkdir()
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            report = run_dir / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            worksheet = run_dir / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_learning_path_latest_output(first_step, outputs)
                missing = launch_learning_path_latest_output(second_step, outputs)

            opener.assert_called_once_with(report)
            self.assertIsNone(missing)

            with patch("mclab.learner_menu.open_path") as opener:
                launch_learning_path_latest_worksheet(first_step, outputs)
                missing_worksheet = launch_learning_path_latest_worksheet(second_step, outputs)

            opener.assert_called_once_with(worksheet)
            self.assertIsNone(missing_worksheet)

    def test_recommended_learning_path_summary_detects_completion(self) -> None:
        progress_items = tuple(
            (step, LearningPathProgress(completed=True, latest_output=Path(f"run_{index}")))
            for index, step in enumerate(LEARNING_PATH, start=1)
        )

        self.assertIsNone(next_learning_path_step(progress_items))
        self.assertIn("Progress: 11/11 complete", learning_path_summary_text(progress_items))
        self.assertIn("Course path complete", learning_path_summary_text(progress_items))

        batch_next_items = tuple(
            (
                step,
                LearningPathProgress(completed=index < len(LEARNING_PATH), latest_output=Path(f"run_{index}")),
            )
            for index, step in enumerate(LEARNING_PATH, start=1)
        )
        batch_summary = learning_path_summary_text(batch_next_items)
        self.assertIn("Next: 11. Compare the course", batch_summary)
        self.assertIn("Next action: run Comparison Batches - All compare", batch_summary)
        self.assertIn("Compare:", batch_summary)

        outcome_pending_items = tuple(
            (
                step,
                LearningPathProgress(
                    completed=True,
                    latest_output=Path(f"run_{index}"),
                    evidence_required=index == 2,
                    observation_markers=1 if index == 2 else 0,
                    learner_predictions=1 if index == 2 else 0,
                    learner_outcomes=0,
                ),
            )
            for index, step in enumerate(LEARNING_PATH, start=1)
        )
        outcome_summary = learning_path_summary_text(outcome_pending_items)
        self.assertIn("Outcome review pending: 1 hands-on step(s).", outcome_summary)
        self.assertIn("Next review: add missing Prediction outcome", outcome_summary)

    def test_menu_actions_have_valid_guided_lesson_cards(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                self.assertTrue(action.description)
                self.assertTrue(action.try_this)
                self.assertTrue(action.watch)
                text = lesson_text(action)
                self.assertIn("Setup:", text)
                self.assertIn("Badges:", text)
                self.assertIn("Plan:", text)
                self.assertIn(action_plan_text(action), text)
                self.assertIn("Mission:", text)
                self.assertIn(action_mission_text(action), text)
                self.assertIn("History:", text)
                self.assertIn("Evidence:", text)
                self.assertIn("Latest evidence:", text)
                self.assertIn("Mission evidence:", text)
                self.assertIn("Controls:", text)
                self.assertIn("Viewer:", text)
                self.assertIn("Try:", text)
                self.assertIn("Change:", text)
                self.assertIn("Values:", text)
                self.assertIn("Prediction:", text)
                self.assertIn("Question:", text)
                self.assertIn("Next:", text)
                self.assertIn("Compare:", text)
                self.assertIn("Watch:", text)
                self.assertTrue(parameter_hint(action))
                self.assertTrue(prediction_prompt(action).startswith("Prediction: "))
                self.assertTrue(reflection_question(action).startswith("Question: "))
                config = load_config(action.config_path)
                self.assertIn("model_path", config)

        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        auto_demo = by_label[("Lab01 Mass-Spring-Damper", "Auto demo")]
        lab03_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]
        self.assertIn("Plan: Intro; baseline demo", action_plan_text(auto_demo))
        self.assertIn("saves report/plots/worksheet", action_plan_text(auto_demo))
        self.assertIn("Mission: Run the demo", action_mission_text(auto_demo))
        self.assertIn("Plan: Deep dive; hands-on viewer", action_plan_text(lab03_dls))
        self.assertIn("Mission: Change", action_mission_text(lab03_dls))

    def test_menu_cards_show_actual_control_affordances(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        auto_demo = by_label[("Lab01 Mass-Spring-Damper", "Auto demo")]
        lab01_interactive = by_label[("Lab01 Mass-Spring-Damper", "Interactive")]
        lab03_condition_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]
        lab04_cartesian = by_label[("Lab04 Panda Manipulator", "Cartesian interactive")]
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]

        self.assertEqual(
            action_controls_text(auto_demo),
            "Controls: Auto run; edit YAML before running",
        )

        lab01_controls = action_controls_text(lab01_interactive)
        self.assertIn("MCLab Interaction panel", lab01_controls)
        self.assertIn("Pull/Push buttons and A/D keys", lab01_controls)
        self.assertIn("live sliders with Changed values", lab01_controls)
        self.assertIn("Pause/Step", lab01_controls)
        self.assertIn("Reset plant", lab01_controls)
        self.assertIn("Mark observation", lab01_controls)
        self.assertIn(lab01_controls, lesson_text(lab01_interactive))

        dls_controls = action_controls_text(lab03_condition_dls)
        self.assertIn("Shoulder/Elbow pulse buttons and A/D keys", dls_controls)
        self.assertIn("quick presets (Early damping, Balanced schedule, Late damping)", dls_controls)
        self.assertIn("live sliders with Changed values", dls_controls)

        cartesian_controls = action_controls_text(lab04_cartesian)
        self.assertIn("Target X +", cartesian_controls)
        self.assertIn("quick presets (Soft reach, Default reach, Far target)", cartesian_controls)

        wall_controls = action_controls_text(lab04_wall)
        self.assertIn("Target X + into wall", wall_controls)
        self.assertIn("quick presets (Soft wall, Stiff wall, Close wall, Back away, Re-enter wall)", wall_controls)

    def test_menu_cards_show_viewer_marker_legend(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab01_interactive = by_label[("Lab01 Mass-Spring-Damper", "Interactive")]
        lab03_condition_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]
        lab04_joint = by_label[("Lab04 Panda Manipulator", "Joint target")]

        self.assertIn("Green marker = Target position.", action_viewer_text(lab01_interactive))
        self.assertIn("Orange sphere = Singularity warning", action_viewer_text(lab03_condition_dls))
        self.assertIn("Red plane = Virtual wall location.", action_viewer_text(lab04_wall))
        self.assertIn("Standard MuJoCo scene", action_viewer_text(lab04_joint))
        lesson = lesson_text(lab01_interactive)
        self.assertIn("Viewer:", lesson)
        self.assertIn("Green marker = Target position.", lesson)

    def test_menu_action_readiness_checks_config_and_model_assets(self) -> None:
        action = MenuAction(
            group="Demo",
            label="Ready demo",
            lab_name="lab01",
            config_path="configs/demo/default.yaml",
            plots="essential",
            description="Demo",
            try_this="Run it.",
            watch="Output.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs" / "demo").mkdir(parents=True)
            (root / "configs" / "demo" / "default.yaml").write_text(
                "model_path: models/demo/scene.xml\n",
                encoding="utf-8",
            )

            missing = action_readiness(action, root=root)

        self.assertEqual(missing.label, "Missing model")
        self.assertIn("models/demo/scene.xml", missing.detail)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs" / "demo").mkdir(parents=True)
            (root / "models" / "demo").mkdir(parents=True)
            (root / "configs" / "demo" / "default.yaml").write_text(
                "model_path: models/demo/scene.xml\n",
                encoding="utf-8",
            )
            (root / "models" / "demo" / "scene.xml").write_text("<mujoco/>\n", encoding="utf-8")
            ready = action_readiness(action, root=root)

        self.assertEqual(ready.status, "ok")
        self.assertEqual(ready.label, "Ready")
        self.assertIn("models/demo/scene.xml", ready.detail)

    def test_batch_readiness_checks_all_scenario_assets(self) -> None:
        lab01_batch = next(action for action in BATCH_ACTIONS if action.batch_name == "lab01_msd_compare")
        config_names = (
            "default.yaml",
            "underdamped.yaml",
            "over_damped.yaml",
            "high_stiffness.yaml",
            "low_stiffness.yaml",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "configs" / "lab01_msd"
            config_dir.mkdir(parents=True)
            for config_name in config_names:
                (config_dir / config_name).write_text(
                    "model_path: models/lab01_msd/scene.xml\n",
                    encoding="utf-8",
                )

            missing = batch_readiness(lab01_batch, root=root)

        self.assertEqual(missing.label, "Batch not ready")
        self.assertIn("Missing model", missing.detail)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "configs" / "lab01_msd"
            model_dir = root / "models" / "lab01_msd"
            config_dir.mkdir(parents=True)
            model_dir.mkdir(parents=True)
            for config_name in config_names:
                (config_dir / config_name).write_text(
                    "model_path: models/lab01_msd/scene.xml\n",
                    encoding="utf-8",
                )
            (model_dir / "scene.xml").write_text("<mujoco/>\n", encoding="utf-8")

            ready = batch_readiness(lab01_batch, root=root)

        self.assertEqual(ready.status, "ok")
        self.assertEqual(ready.label, "Ready")
        self.assertIn("5 scenarios", ready.detail)

    def test_launch_from_menu_blocks_not_ready_actions(self) -> None:
        status = FakeStatus()
        with (
            patch(
                "mclab.learner_menu.action_readiness",
                return_value=ActionReadiness("fail", "Missing model", "demo.xml", "Run Check setup."),
            ),
            patch("mclab.learner_menu.launch_action") as launcher,
        ):
            _launch_from_menu(MENU_ACTIONS[0], status)

        launcher.assert_not_called()
        self.assertIn("Cannot start", status.value)
        self.assertIn("Missing model", status.value)

    def test_launch_batch_from_menu_blocks_not_ready_batches(self) -> None:
        status = FakeStatus()
        with (
            patch(
                "mclab.learner_menu.batch_readiness",
                return_value=ActionReadiness("fail", "Batch not ready", "missing model", "Run Check setup."),
            ),
            patch("mclab.learner_menu.launch_batch_action") as launcher,
        ):
            _launch_batch_from_menu(BATCH_ACTIONS[1], status)

        launcher.assert_not_called()
        self.assertIn("Cannot start", status.value)
        self.assertIn("Batch not ready", status.value)

    def test_interactive_menu_cards_show_configured_presets(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab02_interactive = by_label[("Lab02 PID Control", "Interactive")]
        lab03_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]
        lab03_condition_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]
        lab04_cartesian = by_label[("Lab04 Panda Manipulator", "Cartesian interactive")]
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]

        self.assertEqual(
            configured_preset_labels(lab02_interactive.config_path),
            ("Gentle P", "Damped PD", "Aggressive PID"),
        )
        self.assertIn(
            "Damped PD: Show damping reducing overshoot.",
            configured_preset_purposes(lab02_interactive.config_path),
        )
        self.assertEqual(
            configured_preset_comparison(lab02_interactive.config_path),
            "Gentle P -> Damped PD -> Aggressive PID; watch live status, then mark one observation.",
        )
        self.assertIn("Presets: Gentle P, Damped PD, Aggressive PID", lesson_text(lab02_interactive))
        self.assertIn("Preset purpose: Gentle P: Slow but calm disturbance recovery.", lesson_text(lab02_interactive))
        self.assertIn(
            "Preset compare: Gentle P -> Damped PD -> Aggressive PID; watch live status, then mark one observation.",
            lesson_text(lab02_interactive),
        )
        self.assertIn("Presets: Low DLS damping, Balanced DLS, High DLS damping", lesson_text(lab03_dls))
        self.assertIn("Presets: Early damping, Balanced schedule, Late damping", lesson_text(lab03_condition_dls))
        self.assertIn("Presets: Soft reach, Default reach, Far target", lesson_text(lab04_cartesian))
        self.assertEqual(configured_required_preset_labels(lab04_wall.config_path), ("Close wall", "Back away", "Re-enter wall"))
        self.assertIn(
            "required evidence: Close wall -> Back away -> Re-enter wall",
            configured_preset_comparison(lab04_wall.config_path),
        )
        self.assertIn("Presets: Soft wall, Stiff wall, Close wall, Back away, Re-enter wall", lesson_text(lab04_wall))
        self.assertIn("required evidence: Close wall -> Back away -> Re-enter wall", lesson_text(lab04_wall))

    def test_menu_cards_show_readable_experience_badges(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab01_interactive = by_label[("Lab01 Mass-Spring-Damper", "Interactive")]
        lab03_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]
        lab03_low_torque = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS")]
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]

        self.assertIn("Hands-on", action_badges(lab01_interactive))
        self.assertIn("Dynamics", action_badges(lab01_interactive))
        self.assertIn("Badges: Hands-on", lesson_text(lab01_interactive))

        self.assertIn("2DOF", action_badges(lab03_dls))
        self.assertIn("Singularity", action_badges(lab03_dls))
        self.assertIn("Badges: Hands-on, Compare, 2DOF", lesson_text(lab03_dls))

        self.assertIn("Compare", action_badges(lab03_low_torque))
        self.assertIn("Singularity", action_badges(lab03_low_torque))
        self.assertIn("Tuning", action_badges(lab03_low_torque))
        self.assertIn("Badges: Compare, 2DOF", lesson_text(lab03_low_torque))

        self.assertIn("Panda", action_badges(lab04_wall))
        self.assertIn("Wall", action_badges(lab04_wall))
        self.assertIn("Badges: Hands-on, Panda, Wall", lesson_text(lab04_wall))

    def test_menu_action_followups_point_to_real_next_experiences(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                followup = action_followup(action)
                self.assertIn(followup, (*MENU_ACTIONS, *BATCH_ACTIONS))
                self.assertIn(followup.group, action_followup_text(action))
                self.assertIn(followup.label, action_followup_text(action))

        self.assertEqual(action_followup(MENU_ACTIONS[0]), MENU_ACTIONS[1])
        self.assertEqual(action_followup(MENU_ACTIONS[-1]), BATCH_ACTIONS[0])

    def test_menu_actions_map_to_relevant_comparison_batches(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}

        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                compare_batch = action_compare_batch(action)
                self.assertIn(compare_batch, BATCH_ACTIONS)
                self.assertIn(compare_batch.label, action_compare_text(action))

        self.assertEqual(action_compare_batch(by_label[("Lab01 Mass-Spring-Damper", "Interactive")]).batch_name, "lab01_msd_compare")
        self.assertEqual(action_compare_batch(by_label[("Lab02 PID Control", "Windup")]).batch_name, "lab02_pid_compare")
        self.assertEqual(
            action_compare_batch(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(
            action_compare_batch(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS")]).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(
            action_compare_batch(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF fast-command DLS")]).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(
            action_compare_batch(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF upper-path DLS")]).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(
            action_compare_batch(
                by_label[("Lab03 2DOF Arm and Trajectories", "2DOF shoulder-disturbance DLS")]
            ).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(
            action_compare_batch(
                by_label[("Lab03 2DOF Arm and Trajectories", "2DOF staggered-disturbance DLS")]
            ).batch_name,
            "lab03_2dof_compare",
        )
        self.assertEqual(action_compare_batch(by_label[("Lab04 Panda Manipulator", "Virtual wall")]).batch_name, "lab04_wall_compare")
        self.assertEqual(
            action_compare_batch(by_label[("Lab04 Panda Manipulator", "Cartesian reach")]).batch_name,
            "lab04_cartesian_compare",
        )

    def test_config_value_preview_summarizes_current_knob_values(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}

        underdamped = config_value_preview(by_label[("Lab01 Mass-Spring-Damper", "Underdamped")])
        self.assertIn("damping=", underdamped)
        self.assertIn("stiffness=", underdamped)

        windup = config_value_preview(by_label[("Lab02 PID Control", "Windup")])
        self.assertIn("controller.ki=", windup)
        self.assertIn("controller.anti_windup=", windup)

        task_space = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF task-space")])
        self.assertIn("target_xy=", task_space)
        self.assertIn("tracking_controller.task_kp=", task_space)

        wall = config_value_preview(by_label[("Lab04 Panda Manipulator", "Virtual wall")])
        self.assertIn("virtual_wall.stiffness=", wall)
        self.assertIn("virtual_wall.damping=", wall)

        interactive = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF interactive")])
        self.assertIn("target_xy=", interactive)
        self.assertIn("interaction.joint_disturbance_torque=", interactive)

        low_torque = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS")])
        self.assertIn("tracking_controller.torque_limit=", low_torque)
        edge_target = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF edge-target DLS")])
        self.assertIn("target_xy=", edge_target)
        self.assertIn("tracking_controller.condition_damping_threshold=", edge_target)
        upper_path = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF upper-path DLS")])
        self.assertIn("initial_q=", upper_path)
        self.assertIn("target_xy=", upper_path)
        self.assertIn("tracking_controller.condition_damping_threshold=", upper_path)
        shoulder_disturbance = config_value_preview(
            by_label[("Lab03 2DOF Arm and Trajectories", "2DOF shoulder-disturbance DLS")]
        )
        self.assertIn("disturbance_torque.start_time=", shoulder_disturbance)
        self.assertIn("disturbance_torque.torque=", shoulder_disturbance)
        staggered_disturbance = config_value_preview(
            by_label[("Lab03 2DOF Arm and Trajectories", "2DOF staggered-disturbance DLS")]
        )
        self.assertIn("disturbance_torque.duration=", staggered_disturbance)
        self.assertIn("disturbance_torque.ramp_time=", staggered_disturbance)
        fast_command = config_value_preview(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF fast-command DLS")])
        self.assertIn("trajectory.duration=", fast_command)
        self.assertIn("tracking_controller.max_task_speed=", fast_command)

    def test_filter_menu_actions_matches_search_terms(self) -> None:
        labels = {action.label for action in filter_menu_actions("pid noise")}
        self.assertIn("Sensor noise", labels)
        self.assertNotIn("Control delay", labels)

        wall_labels = {action.label for action in filter_menu_actions("wall stiffness")}
        self.assertIn("Soft wall", wall_labels)
        self.assertIn("Stiff wall", wall_labels)
        self.assertIn("Virtual wall", wall_labels)
        contact_labels = {action.label for action in filter_menu_actions("contact release")}
        self.assertIn("Contact cycle wall", contact_labels)
        retreat_labels = {action.label for action in filter_menu_actions("retreat gain")}
        self.assertIn("Low retreat wall", retreat_labels)
        self.assertIn("High retreat wall", retreat_labels)
        intro_labels = {(action.group, action.label) for action in filter_menu_actions("intro")}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Auto demo"), intro_labels)
        deep_dive_labels = {(action.group, action.label) for action in filter_menu_actions("deep dive")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS"), deep_dive_labels)

        interactive_labels = {action.label for action in filter_menu_actions("interactive")}
        self.assertIn("Interactive", interactive_labels)
        self.assertIn("2DOF interactive", interactive_labels)
        self.assertIn("Cartesian interactive", interactive_labels)

        preset_labels = {(action.group, action.label) for action in filter_menu_actions("far target")}
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian interactive"), preset_labels)
        preset_purpose_labels = {(action.group, action.label) for action in filter_menu_actions("safer joints")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity"), preset_purpose_labels)
        preset_compare_labels = {(action.group, action.label) for action in filter_menu_actions("mark one observation")}
        self.assertIn(("Lab02 PID Control", "Interactive"), preset_compare_labels)

        value_labels = {(action.group, action.label) for action in filter_menu_actions("anti_windup=true")}
        self.assertIn(("Lab02 PID Control", "Anti-windup"), value_labels)

        followup_labels = {(action.group, action.label) for action in filter_menu_actions("next anti-windup")}
        self.assertIn(("Lab02 PID Control", "Windup"), followup_labels)

        compare_batch_labels = {
            (action.group, action.label) for action in filter_menu_actions("compare lab04 wall")
        }
        self.assertIn(("Lab04 Panda Manipulator", "Virtual wall"), compare_batch_labels)

        question_labels = {(action.group, action.label) for action in filter_menu_actions("question overshoot")}
        self.assertIn(("Lab02 PID Control", "High P gain"), question_labels)

        prediction_labels = {(action.group, action.label) for action in filter_menu_actions("prediction live target")}
        self.assertIn(("Lab02 PID Control", "Interactive"), prediction_labels)

        torque_labels = {(action.group, action.label) for action in filter_menu_actions("torque limit")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS"), torque_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF high-torque DLS"), torque_labels)
        target_labels = {(action.group, action.label) for action in filter_menu_actions("target dls")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF edge-target DLS"), target_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF inner-target DLS"), target_labels)
        command_labels = {(action.group, action.label) for action in filter_menu_actions("fast command speed")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF fast-command DLS"), command_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF slow-command DLS"), command_labels)
        edge_target_labels = {(action.group, action.label) for action in filter_menu_actions("edge target dls")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF edge-target DLS"), edge_target_labels)
        path_branch_labels = {(action.group, action.label) for action in filter_menu_actions("elbow branch")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF upper-path DLS"), path_branch_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF lower-path DLS"), path_branch_labels)
        disturbance_labels = {(action.group, action.label) for action in filter_menu_actions("disturbance pulse")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF shoulder-disturbance DLS"), disturbance_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF elbow-disturbance DLS"), disturbance_labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF staggered-disturbance DLS"), disturbance_labels)

        controls_labels = {(action.group, action.label) for action in filter_menu_actions("pull push")}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Interactive"), controls_labels)

        pause_labels = {(action.group, action.label) for action in filter_menu_actions("pause step")}
        self.assertIn(("Lab04 Panda Manipulator", "Virtual wall"), pause_labels)

        red_plane_labels = {(action.group, action.label) for action in filter_menu_actions("red plane")}
        self.assertIn(("Lab04 Panda Manipulator", "Virtual wall"), red_plane_labels)

        orange_sphere_labels = {(action.group, action.label) for action in filter_menu_actions("orange sphere")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS"), orange_sphere_labels)

    def test_experience_filters_group_scenarios_by_learning_mode(self) -> None:
        filter_keys = {filter_option.key for filter_option in EXPERIENCE_FILTERS}
        self.assertIn("intro", filter_keys)
        self.assertIn("build", filter_keys)
        self.assertIn("deep-dive", filter_keys)
        self.assertIn("hands-on", filter_keys)
        self.assertIn("compare", filter_keys)
        self.assertIn("wall", filter_keys)
        self.assertEqual(experience_filter_description("deep dive"), "Advanced singularity, wall, and manipulator behavior.")
        self.assertEqual(experience_filter_description("missing"), EXPERIENCE_FILTERS[0].description)

        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab01_auto = by_label[("Lab01 Mass-Spring-Damper", "Auto demo")]
        lab03_task_space = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF task-space")]
        lab03_condition_dls = by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]
        self.assertIn("intro", action_tags(lab01_auto))
        self.assertIn("build", action_tags(lab03_task_space))
        self.assertIn("deep-dive", action_tags(lab03_condition_dls))
        self.assertIn("hands-on", action_tags(lab04_wall))
        self.assertIn("deep-dive", action_tags(lab04_wall))
        self.assertIn("wall", action_tags(lab04_wall))
        self.assertIn("panda", action_tags(lab04_wall))
        self.assertIn("singularity", action_tags(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]))

        intro = {(action.group, action.label) for action in filter_menu_actions("", experience_filter="intro")}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Auto demo"), intro)
        self.assertIn(("Lab02 PID Control", "Interactive"), intro)
        self.assertNotIn(("Lab03 2DOF Arm and Trajectories", "2DOF task-space"), intro)

        build = {(action.group, action.label) for action in filter_menu_actions("", experience_filter="build")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF task-space"), build)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian interactive"), build)
        self.assertNotIn(("Lab04 Panda Manipulator", "Virtual wall"), build)

        deep_dive = {(action.group, action.label) for action in filter_menu_actions("", experience_filter="deep dive")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS"), deep_dive)
        self.assertIn(("Lab04 Panda Manipulator", "Virtual wall"), deep_dive)
        self.assertNotIn(("Lab01 Mass-Spring-Damper", "Auto demo"), deep_dive)

        hands_on = {(action.group, action.label) for action in filter_menu_actions("", experience_filter="hands-on")}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Interactive"), hands_on)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity"), hands_on)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS"), hands_on)
        self.assertIn(("Lab04 Panda Manipulator", "Joint target"), hands_on)
        self.assertNotIn(("Lab04 Panda Manipulator", "Cartesian reach"), hands_on)

        two_dof_labels = {action.label for action in filter_menu_actions("", experience_filter="2dof")}
        self.assertIn("2DOF joint-space", two_dof_labels)
        self.assertIn("2DOF task-space", two_dof_labels)
        self.assertNotIn("Step profile", two_dof_labels)

        wall_labels = {action.label for action in filter_menu_actions("", experience_filter="wall")}
        self.assertEqual(
            wall_labels,
            {
                "Soft wall",
                "Stiff wall",
                "Low damping wall",
                "High damping wall",
                "Near wall",
                "Far wall",
                "Slow approach wall",
                "Fast approach wall",
                "Contact cycle wall",
                "Low retreat wall",
                "High retreat wall",
                "Virtual wall",
            },
        )

        singularity_labels = {action.label for action in filter_menu_actions("", experience_filter="singularity")}
        self.assertEqual(
            singularity_labels,
            {
                "2DOF singularity",
                "2DOF DLS singularity",
                "2DOF condition-aware DLS",
                "2DOF early DLS damping",
                "2DOF late DLS damping",
                "2DOF inner-target DLS",
                "2DOF edge-target DLS",
                "2DOF upper-path DLS",
                "2DOF lower-path DLS",
                "2DOF shoulder-disturbance DLS",
                "2DOF elbow-disturbance DLS",
                "2DOF staggered-disturbance DLS",
                "2DOF low-torque DLS",
                "2DOF high-torque DLS",
                "2DOF slow-command DLS",
                "2DOF fast-command DLS",
            },
        )

        compare_labels = {action.label for action in filter_menu_actions("windup", experience_filter="compare")}
        self.assertEqual(compare_labels, {"Windup", "Anti-windup"})

        hands_on_search = {(action.group, action.label) for action in filter_menu_actions("hands on")}
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF interactive"), hands_on_search)

    def test_filter_menu_actions_empty_query_returns_all_actions(self) -> None:
        self.assertEqual(filter_menu_actions(""), MENU_ACTIONS)
        self.assertEqual(filter_menu_actions("   "), MENU_ACTIONS)

    def test_parameter_hints_point_to_key_learning_knobs(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}

        self.assertIn("damping", parameter_hint(by_label[("Lab01 Mass-Spring-Damper", "Underdamped")]))
        self.assertIn("controller.anti_windup", parameter_hint(by_label[("Lab02 PID Control", "Windup")]))
        self.assertIn("measurement_noise_std", parameter_hint(by_label[("Lab02 PID Control", "Sensor noise")]))
        self.assertIn("control_delay", parameter_hint(by_label[("Lab02 PID Control", "Control delay")]))
        self.assertIn(
            "target_xy",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF task-space")]),
        )
        self.assertIn(
            "dls_damping",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]),
        )
        self.assertIn(
            "live sliders/presets",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]),
        )
        self.assertIn(
            "condition_damping_threshold",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF condition-aware DLS")]),
        )
        self.assertIn(
            "Shoulder/Elbow pulse",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF interactive")]),
        )
        self.assertIn(
            "condition_damping_full",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF early DLS damping")]),
        )
        self.assertIn(
            "target_xy",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF edge-target DLS")]),
        )
        self.assertIn(
            "tracking_controller.torque_limit",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF low-torque DLS")]),
        )
        self.assertIn(
            "disturbance_torque.torque",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF shoulder-disturbance DLS")]),
        )
        self.assertIn(
            "disturbance_torque.pulses",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF staggered-disturbance DLS")]),
        )
        self.assertIn(
            "tracking_controller.max_task_speed",
            parameter_hint(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF fast-command DLS")]),
        )
        self.assertIn(
            "cartesian_target.gain",
            parameter_hint(by_label[("Lab04 Panda Manipulator", "Soft Cartesian")]),
        )
        self.assertIn(
            "interaction.target_step",
            parameter_hint(by_label[("Lab04 Panda Manipulator", "Cartesian interactive")]),
        )
        self.assertIn("sim_time", parameter_hint(by_label[("Lab04 Panda Manipulator", "30s stability hold")]))
        self.assertIn("virtual_wall.stiffness", parameter_hint(by_label[("Lab04 Panda Manipulator", "Virtual wall")]))
        self.assertIn("virtual_wall.damping", parameter_hint(by_label[("Lab04 Panda Manipulator", "Low damping wall")]))
        self.assertIn("virtual_wall.wall_x", parameter_hint(by_label[("Lab04 Panda Manipulator", "Near wall")]))
        self.assertIn("trajectory.duration", parameter_hint(by_label[("Lab04 Panda Manipulator", "Fast approach wall")]))
        self.assertIn("cartesian_target.waypoints", parameter_hint(by_label[("Lab04 Panda Manipulator", "Contact cycle wall")]))
        self.assertIn(
            "virtual_wall.force_retreat_gain",
            parameter_hint(by_label[("Lab04 Panda Manipulator", "High retreat wall")]),
        )

    def test_menu_actions_link_to_existing_config_and_lesson_files(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                self.assertTrue(action_config_path(action).exists())
                self.assertTrue(action_doc_path(action).exists())

    def test_open_editable_path_prefers_vscode_for_files_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.yaml"
            path.write_text("lab: demo\n", encoding="utf-8")

            with (
                patch("mclab.learner_menu.shutil.which", return_value="code"),
                patch("mclab.learner_menu.subprocess.Popen") as popen,
            ):
                open_editable_path(path)

            popen.assert_called_once_with(["code", "-r", str(path)])

    def test_action_history_tracks_latest_matching_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab01"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            report = run_path / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            (run_path / "plots").mkdir()
            (run_path / "plots" / "energy.png").write_bytes(b"fake-png")
            priority_plot = run_path / "plots" / "position.png"
            priority_plot.write_bytes(b"fake-png")
            tuned_config = run_path / "learner_tuned_config.yaml"
            tuned_config.write_text("interaction:\n  panel: false\n", encoding="utf-8")
            worksheet = run_path / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")

            self.assertEqual(action_latest_output(MENU_ACTIONS[0], outputs), run_path)
            self.assertEqual(action_latest_plot(MENU_ACTIONS[0], outputs), priority_plot)
            self.assertEqual(action_latest_worksheet(MENU_ACTIONS[0], outputs), worksheet)
            self.assertEqual(action_latest_tuned_config(MENU_ACTIONS[0], outputs), tuned_config)
            self.assertIn("History: Latest run_lab01", action_history_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(action_latest_evidence_text(MENU_ACTIONS[0], outputs), "Latest evidence: None yet")
            self.assertEqual(action_plot_text(MENU_ACTIONS[0], outputs), "Plots: Latest position.png")
            self.assertIn("Plot review: Position - Compare actual motion", action_plot_review_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(action_worksheet_text(MENU_ACTIONS[0], outputs), "Worksheet: Latest worksheet.md")
            self.assertIn("Plot review: Position - Compare actual motion", lesson_text(MENU_ACTIONS[0], outputs))
            self.assertIn("Worksheet: Latest worksheet.md", lesson_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(
                action_replay_text(MENU_ACTIONS[0], outputs),
                "Replay: Latest learner_tuned_config.yaml",
            )
            self.assertIn("Replay: Latest learner_tuned_config.yaml", lesson_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(action_history_text(MENU_ACTIONS[1], outputs), "History: Not run yet")
            self.assertEqual(action_plot_text(MENU_ACTIONS[1], outputs), "Plots: Not saved yet")
            self.assertEqual(
                action_plot_review_text(MENU_ACTIONS[1], outputs),
                "Plot review: Not available until a plot is saved",
            )
            self.assertIsNone(action_latest_worksheet(MENU_ACTIONS[1], outputs))
            self.assertEqual(action_worksheet_text(MENU_ACTIONS[1], outputs), "Worksheet: Not saved yet")
            self.assertIsNone(action_latest_tuned_config(MENU_ACTIONS[1], outputs))
            self.assertEqual(action_replay_text(MENU_ACTIONS[1], outputs), "Replay: No tuned config yet")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_output(MENU_ACTIONS[0], outputs)
                missing = launch_action_latest_output(MENU_ACTIONS[1], outputs)

            opener.assert_called_once_with(report)
            self.assertIsNone(missing)

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_plot(MENU_ACTIONS[0], outputs)
                missing_plot = launch_action_latest_plot(MENU_ACTIONS[1], outputs)

            opener.assert_called_once_with(priority_plot)
            self.assertIsNone(missing_plot)

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_worksheet(MENU_ACTIONS[0], outputs)
                missing_worksheet = launch_action_latest_worksheet(MENU_ACTIONS[1], outputs)

            opener.assert_called_once_with(worksheet)
            self.assertIsNone(missing_worksheet)

    def test_action_evidence_summarizes_latest_observation_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab01"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": MENU_ACTIONS[0].lab_name,
                        "config_path": MENU_ACTIONS[0].config_path,
                        "config_name": Path(MENU_ACTIONS[0].config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "The response should overshoot.",
                                "outcome": "Matched",
                                "note": "Saw overshoot.",
                            },
                        },
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"question": "Question: demo?"},
                        },
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_evidence_text(MENU_ACTIONS[0], outputs),
                "Evidence: 2 observations, 1 prediction, 1 outcome, 1 note",
            )
            self.assertIn("Evidence: 2 observations, 1 prediction, 1 outcome, 1 note", lesson_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(action_evidence_text(MENU_ACTIONS[1], outputs), "Evidence: No observation markers yet")

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "The response should overshoot.",
                                "note": "Saw overshoot.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_evidence_text(MENU_ACTIONS[0], outputs),
                "Evidence: 1 observation, 1 prediction, 1 note; outcome review pending",
            )
            self.assertIn("outcome review pending", lesson_text(MENU_ACTIONS[0], outputs))

    def test_action_latest_evidence_summarizes_prediction_note_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab01"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": MENU_ACTIONS[0].lab_name,
                        "config_path": MENU_ACTIONS[0].config_path,
                        "config_name": Path(MENU_ACTIONS[0].config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "The response should overshoot.",
                                "outcome": "Matched",
                                "note": "Plot: Saw overshoot in the position plot.; Changed values: damping=0.8",
                                "status": {"Position [m]": "0.125", "Energy [J]": "0.040"},
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            text = action_latest_evidence_text(MENU_ACTIONS[0], outputs)
            lesson = lesson_text(MENU_ACTIONS[0], outputs)

            self.assertIn("Latest evidence:", text)
            self.assertIn("Prediction: The response should overshoot.", text)
            self.assertIn("Outcome: Matched", text)
            self.assertIn("Note: Plot: Saw overshoot in the position plot.; Changed values: damping=0.8", text)
            self.assertIn(
                "Note evidence: Plot: Saw overshoot in the position plot. | Changed values: damping=0.8",
                text,
            )
            self.assertIn("Status: Position [m]=0.125", text)
            self.assertIn(text, lesson)

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "The response should overshoot.",
                                "note": "Saw overshoot in the position plot.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            missing_outcome_text = action_latest_evidence_text(MENU_ACTIONS[0], outputs)
            self.assertIn("Outcome: missing review", missing_outcome_text)
            self.assertIn("Outcome: missing review", lesson_text(MENU_ACTIONS[0], outputs))

    def test_action_activity_mix_summarizes_latest_hands_on_controls(self) -> None:
        lab02_interactive = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab02_pid/interactive_disturbance.yaml"
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)

            self.assertEqual(action_activity_mix_text(MENU_ACTIONS[0], outputs), "")
            self.assertEqual(action_activity_mix_text(lab02_interactive, outputs), "Activity mix: Not run yet")

            run_path = outputs / "run_lab02_interactive"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": lab02_interactive.lab_name,
                        "config_path": lab02_interactive.config_path,
                        "config_name": Path(lab02_interactive.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "slider", "name": "kp", "label": "Kp", "value": 40.0},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"prediction": "More gain should overshoot.", "note": "Overshoot increased."},
                        },
                    ]
                ),
                encoding="utf-8",
            )

            text = action_activity_mix_text(lab02_interactive, outputs)
            self.assertIn("Activity mix: 2/3 control families", text)
            self.assertIn("buttons 0, sliders 1, presets 1, markers 1", text)
            self.assertIn("Use one button control such as pulse, nudge, pause", text)
            self.assertIn(text, lesson_text(lab02_interactive, outputs))

    def test_action_mission_evidence_summarizes_latest_proof_status(self) -> None:
        lab02_interactive = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab02_pid/interactive_disturbance.yaml"
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)

            self.assertEqual(action_mission_evidence_text(MENU_ACTIONS[0], outputs), "Mission evidence: Not run yet")

            auto_path = outputs / "run_lab01"
            auto_path.mkdir()
            (auto_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": MENU_ACTIONS[0].lab_name,
                        "config_path": MENU_ACTIONS[0].config_path,
                        "config_name": Path(MENU_ACTIONS[0].config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_mission_evidence_text(MENU_ACTIONS[0], outputs),
                "Mission evidence: Needs plot; rerun with plots enabled",
            )
            (auto_path / "plots").mkdir()
            (auto_path / "plots" / "position.png").write_bytes(b"fake-png")
            (auto_path / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            self.assertEqual(
                action_mission_evidence_text(MENU_ACTIONS[0], outputs),
                "Mission evidence: Artifacts ready; plot position.png; worksheet worksheet.md",
            )

            interactive_path = outputs / "run_lab02_interactive"
            interactive_path.mkdir()
            (interactive_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": lab02_interactive.lab_name,
                        "config_path": lab02_interactive.config_path,
                        "config_name": Path(lab02_interactive.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_mission_evidence_text(lab02_interactive, outputs),
                "Mission evidence: Needs observation; 0 observations, 0 predictions, 0 outcomes, 0 notes",
            )

            (interactive_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"prediction": "Higher Kp will overshoot.", "note": "Overshoot was visible."},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_mission_evidence_text(lab02_interactive, outputs),
                "Mission evidence: Outcome review pending; 1 observation, 1 prediction, 0 outcomes, 1 note",
            )

            (interactive_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Higher Kp will overshoot.",
                                "outcome": "Matched",
                                "note": "Overshoot was visible.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_mission_evidence_text(lab02_interactive, outputs),
                "Mission evidence: Ready for review; 1 observation, 1 prediction, 1 outcome, 1 note",
            )
            self.assertIn("Mission evidence: Ready for review", lesson_text(lab02_interactive, outputs))

    def test_review_queue_summary_counts_saved_mission_evidence_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self.assertEqual(
                review_queue_summary_text(outputs),
                "Review queue: No saved runs yet. Run a scenario first.",
            )

            def write_summary(path: Path, lab_name: str, config_path: str) -> None:
                path.mkdir()
                (path / "summary.json").write_text(
                    json.dumps(
                        {
                            "lab_name": lab_name,
                            "config_path": config_path,
                            "config_name": Path(config_path).stem,
                        }
                    ),
                    encoding="utf-8",
                )
                (path / "report.html").write_text("<html></html>", encoding="utf-8")

            ready = outputs / "run_lab01_ready"
            write_summary(ready, "lab01_msd", "configs/lab01_msd/default.yaml")
            (ready / "plots").mkdir()
            (ready / "plots" / "position.png").write_bytes(b"fake-png")
            (ready / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")

            write_summary(outputs / "run_lab01_needs_plot", "lab01_msd", "configs/lab01_msd/default.yaml")
            write_summary(
                outputs / "run_lab01_needs_observation",
                "lab01_msd",
                "configs/lab01_msd/interactive_pull.yaml",
            )

            needs_prediction = outputs / "run_lab02_needs_prediction"
            write_summary(
                needs_prediction,
                "lab02_pid",
                "configs/lab02_pid/interactive_disturbance.yaml",
            )
            (needs_prediction / "interaction_events.json").write_text(
                json.dumps([{"kind": "marker", "name": "observation", "value": {"note": "Changed response."}}]),
                encoding="utf-8",
            )

            outcome_pending = outputs / "run_lab03_outcome_pending"
            write_summary(outcome_pending, "lab03_2dof", "configs/lab03_2dof/interactive_2dof.yaml")
            (outcome_pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Farther target should need more torque.",
                                "note": "Torque rose.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            preset_pending = outputs / "run_lab04_preset_pending"
            write_summary(
                preset_pending,
                "lab04_panda",
                "configs/lab04_panda/interactive_virtual_wall.yaml",
            )
            (preset_pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Stiffer wall should retreat more.",
                                "outcome": "Matched",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            note_pending = outputs / "run_lab02_note_pending"
            write_summary(note_pending, "lab02_pid", "configs/lab02_pid/interactive_disturbance.yaml")
            (note_pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Higher Kp should overshoot.",
                                "outcome": "Matched",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                review_queue_summary_text(outputs),
                (
                    "Review queue: 1 ready, 6 pending. "
                    "Needs observation: 1; prediction: 1; outcome: 1; required preset: 1; note: 1; artifact: 1. "
                    "Next review: run_lab03_outcome_pending - Outcome review pending."
                ),
            )
            self.assertEqual(next_review_output(outputs), outcome_pending)

            preset_only_root = outputs / "preset_only_root"
            preset_only_root.mkdir()
            preset_only = preset_only_root / "run_lab04_preset_only"
            write_summary(preset_only, "lab04_panda", "configs/lab04_panda/interactive_virtual_wall.yaml")
            (preset_only / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Back away should release contact.",
                                "outcome": "Matched",
                                "note": "Contact stayed until backing away.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "Next review: run_lab04_preset_only - Needs required preset Back away.",
                review_queue_summary_text(preset_only_root),
            )
            self.assertEqual(next_review_output(preset_only_root), preset_only)

    def test_launch_next_review_output_opens_the_pending_run_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            ready = outputs / "run_ready"
            ready.mkdir()
            (ready / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (ready / "plots").mkdir()
            (ready / "plots" / "position.png").write_bytes(b"fake-png")
            (ready / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")

            pending = outputs / "run_pending"
            pending.mkdir()
            (pending / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/interactive_disturbance.yaml",
                        "config_name": "interactive_disturbance",
                    }
                ),
                encoding="utf-8",
            )
            (pending / "report.html").write_text("<html>pending</html>", encoding="utf-8")
            (pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"prediction": "More gain should overshoot.", "note": "It did."},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch("mclab.learner_menu.open_path") as opener:
                launch_next_review_output(outputs)

            opener.assert_called_once_with(pending / "report.html")

            (pending / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "More gain should overshoot.",
                                "outcome": "Matched",
                                "note": "It did.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertIsNone(next_review_output(outputs))

    def test_action_preset_evidence_summarizes_latest_preset_progress(self) -> None:
        lab02_interactive = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab02_pid/interactive_disturbance.yaml"
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab02_interactive"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": lab02_interactive.lab_name,
                        "config_path": lab02_interactive.config_path,
                        "config_name": Path(lab02_interactive.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "preset",
                            "name": "gentle_p",
                            "label": "Gentle P",
                            "value": {"values": {"kp": 25.0}},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_preset_evidence_text(lab02_interactive, outputs),
                "Preset evidence: 1/3 presets tried; next Damped PD",
            )
            self.assertIn(
                "Preset evidence: 1/3 presets tried; next Damped PD",
                lesson_text(lab02_interactive, outputs),
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "preset", "name": "damped_pd", "label": "Damped PD"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_preset_evidence_text(lab02_interactive, outputs),
                "Preset evidence: 2/3 presets tried; ready to review comparison",
            )

    def test_required_preset_evidence_keeps_wall_flow_honest(self) -> None:
        lab04_wall = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/interactive_virtual_wall.yaml"
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            run_path = outputs / "run_lab04_wall"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": lab04_wall.lab_name,
                        "config_path": lab04_wall.config_path,
                        "config_name": Path(lab04_wall.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "soft_wall", "label": "Soft wall"},
                        {"kind": "preset", "name": "stiff_wall", "label": "Stiff wall"},
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_preset_evidence_text(lab04_wall, outputs),
                (
                    "Preset evidence: 2/5 presets tried; required next Close wall; "
                    "remaining Close wall -> Back away -> Re-enter wall"
                ),
            )
            self.assertEqual(
                action_next_cue_text(lab04_wall, outputs),
                "Next cue: Try required preset Close wall, then mark a comparison observation.",
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {"kind": "preset", "name": "back_away", "label": "Back away"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_preset_evidence_text(lab04_wall, outputs),
                "Preset evidence: 2/5 presets tried; required next Re-enter wall; remaining Re-enter wall",
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "re-enter_wall", "label": "Re-enter wall"},
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {"kind": "preset", "name": "back_away", "label": "Back away"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_preset_evidence_text(lab04_wall, outputs),
                "Preset evidence: 3/5 presets tried; required next Re-enter wall; remaining Re-enter wall",
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "close_wall", "label": "Close wall"},
                        {"kind": "preset", "name": "back_away", "label": "Back away"},
                        {"kind": "preset", "name": "re-enter_wall", "label": "Re-enter wall"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_preset_evidence_text(lab04_wall, outputs),
                "Preset evidence: 3/5 presets tried; required presets ready",
            )

    def test_action_next_cue_guides_the_next_best_learner_step(self) -> None:
        lab02_interactive = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab02_pid/interactive_disturbance.yaml"
        )

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Run this scenario, then review the saved plot and worksheet.",
            )

            run_path = outputs / "run_lab02_interactive"
            run_path.mkdir()
            (run_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": lab02_interactive.lab_name,
                        "config_path": lab02_interactive.config_path,
                        "config_name": Path(lab02_interactive.config_path).stem,
                    }
                ),
                encoding="utf-8",
            )
            (run_path / "interaction_events.json").write_text(
                json.dumps([{"kind": "preset", "name": "gentle_p", "label": "Gentle P"}]),
                encoding="utf-8",
            )

            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Try preset Damped PD, then mark a comparison observation.",
            )
            self.assertIn("Next cue: Try preset Damped PD", lesson_text(lab02_interactive, outputs))

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "preset", "name": "damped_pd", "label": "Damped PD"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Change one control and Mark observation with a prediction.",
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "preset", "name": "damped_pd", "label": "Damped PD"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {"prediction": "High gain will overshoot.", "note": "Overshoot happened."},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Review latest evidence and choose the missing prediction outcome.",
            )

            plot_dir = run_path / "plots"
            plot_dir.mkdir()
            (plot_dir / "position.png").write_bytes(b"fake-png")
            (run_path / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            (run_path / "learner_tuned_config.yaml").write_text("interaction:\n  panel: false\n", encoding="utf-8")
            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "preset", "name": "damped_pd", "label": "Damped PD"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "High gain will overshoot.",
                                "outcome": "Matched",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Add a short note or Use live status before moving on.",
            )

            (run_path / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {"kind": "preset", "name": "gentle_p", "label": "Gentle P"},
                        {"kind": "preset", "name": "damped_pd", "label": "Damped PD"},
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "High gain will overshoot.",
                                "outcome": "Matched",
                                "note": "Overshoot happened.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                action_next_cue_text(lab02_interactive, outputs),
                "Next cue: Replay the tuned config, then run Compare for the broader tradeoff.",
            )

    def test_batch_history_tracks_latest_matching_report(self) -> None:
        lab01_batch = next(action for action in BATCH_ACTIONS if action.batch_name == "lab01_msd_compare")
        lab02_batch = next(action for action in BATCH_ACTIONS if action.batch_name == "lab02_pid_compare")

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            batch_path = outputs / "batch_lab01"
            batch_path.mkdir()
            (batch_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": "lab01_msd_compare",
                        "batch_name": "lab01_msd_compare",
                    }
                ),
                encoding="utf-8",
            )
            report = batch_path / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            worksheet = batch_path / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")
            (batch_path / "comparison_plots").mkdir()
            batch_plot = batch_path / "comparison_plots" / "error_compare.png"
            batch_plot.write_bytes(b"fake-png")

            self.assertEqual(action_latest_output(lab01_batch, outputs), batch_path)
            self.assertEqual(action_latest_plot(lab01_batch, outputs), batch_plot)
            self.assertEqual(action_latest_worksheet(lab01_batch, outputs), worksheet)
            self.assertIn("History: Latest batch_lab01", action_history_text(lab01_batch, outputs))
            self.assertEqual(action_plot_text(lab01_batch, outputs), "Plots: Latest error_compare.png")
            self.assertIn("Plot review: Error - Check how quickly error shrinks", action_plot_review_text(lab01_batch, outputs))
            self.assertEqual(action_worksheet_text(lab01_batch, outputs), "Worksheet: Latest worksheet.md")
            self.assertIn("Plan: Batch compare", lesson_text_for_batch(lab01_batch, outputs))
            self.assertIn(batch_plan_text(lab01_batch), lesson_text_for_batch(lab01_batch, outputs))
            self.assertIn("Plot review: Error - Check how quickly error shrinks", lesson_text_for_batch(lab01_batch, outputs))
            self.assertIn("Worksheet: Latest worksheet.md", lesson_text_for_batch(lab01_batch, outputs))
            self.assertEqual(action_history_text(lab02_batch, outputs), "History: Not run yet")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_output(lab01_batch, outputs)
                missing = launch_action_latest_output(lab02_batch, outputs)

            opener.assert_called_once_with(report)
            self.assertIsNone(missing)

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_plot(lab01_batch, outputs)
                missing_plot = launch_action_latest_plot(lab02_batch, outputs)

            opener.assert_called_once_with(batch_plot)
            self.assertIsNone(missing_plot)

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_worksheet(lab01_batch, outputs)
                missing_worksheet = launch_action_latest_worksheet(lab02_batch, outputs)

            opener.assert_called_once_with(worksheet)
            self.assertIsNone(missing_worksheet)

    def test_lab04_wall_batch_prioritizes_timing_comparison_plot(self) -> None:
        lab04_wall_batch = next(action for action in BATCH_ACTIONS if action.batch_name == "lab04_wall_compare")

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            batch_path = outputs / "batch_lab04_wall"
            batch_path.mkdir()
            (batch_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": "lab04_wall_compare",
                        "batch_name": "lab04_wall_compare",
                    }
                ),
                encoding="utf-8",
            )
            (batch_path / "report.html").write_text("<html></html>", encoding="utf-8")
            (batch_path / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            plot_dir = batch_path / "comparison_plots"
            plot_dir.mkdir()
            timing_plot = plot_dir / "wall_key_moment_timing_compare.png"
            timing_plot.write_bytes(b"fake-png")
            (plot_dir / "wall_force_compare.png").write_bytes(b"fake-png")
            (plot_dir / "wall_penetration_compare.png").write_bytes(b"fake-png")

            self.assertEqual(action_latest_plot(lab04_wall_batch, outputs), timing_plot)
            self.assertEqual(
                action_plot_text(lab04_wall_batch, outputs),
                "Plots: Latest wall_key_moment_timing_compare.png",
            )
            self.assertIn("Plot review: Wall Timing - Compare when contact", action_plot_review_text(lab04_wall_batch, outputs))
            self.assertIn("Plot review: Wall Timing - Compare when contact", lesson_text_for_batch(lab04_wall_batch, outputs))

    def test_refresh_batch_menu_state_updates_text_and_buttons(self) -> None:
        lab01_batch = next(action for action in BATCH_ACTIONS if action.batch_name == "lab01_msd_compare")
        text_variable = FakeTextVariable()
        report_button = FakeButton()
        plot_button = FakeButton()
        worksheet_button = FakeButton()

        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            refresh_batch_menu_state(((lab01_batch, text_variable, report_button, plot_button, worksheet_button),), outputs)

            self.assertIn("History: Not run yet", text_variable.value)
            self.assertIn("Plots: Not saved yet", text_variable.value)
            self.assertIn("Plot review: Not available until a plot is saved", text_variable.value)
            self.assertIn("Worksheet: Not saved yet", text_variable.value)
            self.assertEqual(report_button.state_calls[-1], ["disabled"])
            self.assertEqual(plot_button.state_calls[-1], ["disabled"])
            self.assertEqual(worksheet_button.state_calls[-1], ["disabled"])

            batch_path = outputs / "batch_lab01"
            batch_path.mkdir()
            (batch_path / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": "lab01_msd_compare",
                        "batch_name": "lab01_msd_compare",
                    }
                ),
                encoding="utf-8",
            )
            (batch_path / "report.html").write_text("<html></html>", encoding="utf-8")
            (batch_path / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            (batch_path / "comparison_plots").mkdir()
            (batch_path / "comparison_plots" / "position_compare.png").write_bytes(b"fake-png")

            refresh_batch_menu_state(((lab01_batch, text_variable, report_button, plot_button, worksheet_button),), outputs)

        self.assertIn("History: Latest batch_lab01", text_variable.value)
        self.assertIn("Plots: Latest position_compare.png", text_variable.value)
        self.assertIn("Plot review: Position - Compare actual motion", text_variable.value)
        self.assertIn("Worksheet: Latest worksheet.md", text_variable.value)
        self.assertEqual(report_button.state_calls[-1], ["!disabled"])
        self.assertEqual(plot_button.state_calls[-1], ["!disabled"])
        self.assertEqual(worksheet_button.state_calls[-1], ["!disabled"])

    def test_launch_latest_output_opens_report_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run"
            run_path.mkdir()
            report = run_path / "report.html"
            report.write_text("<html></html>", encoding="utf-8")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_latest_output({"path": run_path})

            opener.assert_called_once_with(report)

    def test_launch_latest_plot_opens_priority_plot_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run"
            plot_dir = run_path / "plots"
            plot_dir.mkdir(parents=True)
            (plot_dir / "energy.png").write_bytes(b"fake-png")
            priority_plot = plot_dir / "position.png"
            priority_plot.write_bytes(b"fake-png")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_latest_plot({"path": run_path})

            opener.assert_called_once_with(priority_plot)

    def test_launch_latest_worksheet_opens_worksheet_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run"
            run_path.mkdir()
            worksheet = run_path / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_latest_worksheet({"path": run_path})

            opener.assert_called_once_with(worksheet)

    def test_launch_latest_plot_returns_none_when_no_plot_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run"
            run_path.mkdir()

            with patch("mclab.learner_menu.open_path") as opener:
                result = launch_latest_plot({"path": run_path})

            opener.assert_not_called()
            self.assertIsNone(result)

    def test_launch_tuned_replay_starts_from_latest_tuned_config(self) -> None:
        action = MENU_ACTIONS[0]
        tuned_config = ROOT / "outputs" / "run" / "learner_tuned_config.yaml"
        status = FakeStatus()
        process = Mock(pid=345)

        with (
            patch("mclab.learner_menu.action_latest_tuned_config", return_value=tuned_config),
            patch("mclab.learner_menu.launch_tuned_replay", return_value=process) as launcher,
            patch("mclab.learner_menu.Thread") as thread,
        ):
            _launch_tuned_replay_from_menu(action, status)

        launcher.assert_called_once_with(action, tuned_config)
        thread.assert_called_once()
        self.assertIn("Started tuned replay", status.value)
        self.assertIn("pid 345", status.value)

    def test_launch_tuned_replay_reports_missing_config(self) -> None:
        status = FakeStatus()

        with (
            patch("mclab.learner_menu.action_latest_tuned_config", return_value=None),
            patch("mclab.learner_menu.launch_tuned_replay") as launcher,
        ):
            _launch_tuned_replay_from_menu(MENU_ACTIONS[0], status)

        launcher.assert_not_called()
        self.assertIn("Cannot replay", status.value)
        self.assertIn("learner_tuned_config.yaml", status.value)

    def test_launch_learning_path_tuned_replay_delegates_run_steps_only(self) -> None:
        status = FakeStatus()

        with patch("mclab.learner_menu._launch_tuned_replay_from_menu") as launcher:
            _launch_learning_path_tuned_replay_from_menu(LEARNING_PATH[0], status)

        launcher.assert_called_once()
        self.assertEqual(launcher.call_args.args[0], learning_path_target(LEARNING_PATH[0]))

        with patch("mclab.learner_menu._launch_tuned_replay_from_menu") as launcher:
            _launch_learning_path_tuned_replay_from_menu(LEARNING_PATH[-1], status)

        launcher.assert_not_called()
        self.assertIn("comparison batch steps", status.value)

    def test_launch_latest_output_opens_index_for_batch_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_path = Path(tmp) / "batch"
            batch_path.mkdir()
            index = batch_path / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_latest_output({"path": batch_path})

            opener.assert_called_once_with(index)

    def test_launch_outputs_index_opens_index_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            outputs.mkdir()
            index = outputs / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            with (
                patch("mclab.learner_menu.PROJECT_ROOT", Path(tmp)),
                patch("mclab.learner_menu.open_path") as opener,
            ):
                launch_outputs_index()

            opener.assert_called_once_with(index)

    def test_launch_outputs_index_creates_index_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "outputs" / "index.html"

            with (
                patch("mclab.learner_menu.PROJECT_ROOT", Path(tmp)),
                patch("mclab.learner_menu.open_path") as opener,
            ):
                launch_outputs_index()

            self.assertTrue(index.exists())
            opener.assert_called_once_with(index)

    def test_parse_run_output_path_detects_completed_run(self) -> None:
        parsed = parse_run_output_path(r"Run complete: C:\tmp\outputs\20260627_150117_lab04_panda")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.name, "20260627_150117_lab04_panda")

    def test_parse_run_output_path_detects_completed_batch(self) -> None:
        parsed = parse_run_output_path(r"Batch complete: C:\tmp\outputs\20260627_151000_lab02_pid_compare")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.name, "20260627_151000_lab02_pid_compare")

    def test_parse_run_output_path_ignores_noncompletion_lines(self) -> None:
        self.assertIsNone(parse_run_output_path("Simulation complete. Close the MuJoCo viewer window to exit."))
        self.assertIsNone(parse_run_output_path("Run complete: "))

    def test_completed_run_status_enables_latest_output_button(self) -> None:
        status = FakeStatus()
        button = FakeButton()
        latest_output: dict[str, Path | None] = {"path": None}
        output_path = Path(r"C:\tmp\outputs\20260627_150117_lab04_panda")

        _set_status_after_run(
            MENU_ACTIONS[0],
            status,
            0,
            output_path,
            latest_output=latest_output,
            latest_button=button,
        )

        self.assertEqual(latest_output["path"], output_path)
        self.assertEqual(button.state_calls, [["!disabled"]])
        self.assertIn("Completed", status.value)
        self.assertIn(str(output_path), status.value)

    def test_completed_run_status_enables_latest_plot_button_when_plot_exists(self) -> None:
        status = FakeStatus()
        report_button = FakeButton()
        plot_button = FakeButton()
        worksheet_button = FakeButton()
        latest_output: dict[str, Path | None] = {"path": None}

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "run_lab01"
            plot_dir = output_path / "plots"
            plot_dir.mkdir(parents=True)
            priority_plot = plot_dir / "position.png"
            priority_plot.write_bytes(b"fake-png")
            worksheet = output_path / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")

            _set_status_after_run(
                MENU_ACTIONS[0],
                status,
                0,
                output_path,
                latest_output=latest_output,
                latest_button=report_button,
                latest_plot_button=plot_button,
                latest_worksheet_button=worksheet_button,
            )

        self.assertEqual(latest_output["path"], output_path)
        self.assertEqual(report_button.state_calls, [["!disabled"]])
        self.assertEqual(plot_button.state_calls, [["!disabled"]])
        self.assertEqual(worksheet_button.state_calls, [["!disabled"]])
        self.assertIn("Latest plot:", status.value)
        self.assertIn("position.png", status.value)
        self.assertIn("Latest worksheet:", status.value)
        self.assertIn("worksheet.md", status.value)

    def test_failed_run_status_reports_exit_code(self) -> None:
        status = FakeStatus()

        _set_status_after_run(MENU_ACTIONS[0], status, 2, None)

        self.assertIn("Failed", status.value)
        self.assertIn("exit code 2", status.value)
