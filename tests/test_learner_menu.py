from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    _launch_from_menu,
    _set_status_after_run,
    _set_status_after_doctor,
    action_config_path,
    action_history_text,
    action_latest_output,
    action_readiness,
    action_tags,
    action_doc_path,
    build_batch_args,
    build_doctor_args,
    build_run_args,
    experience_filter_description,
    filter_menu_actions,
    learning_path_progress_items,
    learning_path_progress,
    learning_path_progress_text,
    learning_path_summary_text,
    learning_path_target,
    learning_path_text,
    lesson_text_for_batch,
    lesson_text,
    configured_preset_labels,
    launch_action_latest_output,
    launch_outputs_index,
    launch_latest_output,
    next_learning_path_step,
    open_editable_path,
    parameter_hint,
    parse_run_output_path,
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
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF interactive"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Step profile"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Minimum jerk"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "1D interactive"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Neutral hold"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Reach X"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian reach"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Soft Cartesian"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Stiff Cartesian"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian interactive"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Joint target"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Soft wall"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Stiff wall"), labels)
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
                self.assertIn("Try:", text)
                self.assertIn("Watch:", text)
                self.assertIn("Runs:", text)

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
        self.assertGreaterEqual(len(LEARNING_PATH), 8)
        self.assertEqual(LEARNING_PATH[0].title, "1. Feel 1D physics")
        self.assertEqual(LEARNING_PATH[-1].label, "All compare")

        for step in LEARNING_PATH:
            with self.subTest(step=step.title):
                action = learning_path_target(step)
                text = learning_path_text(step)
                self.assertIn("Run:", text)
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

        self.assertTrue(first_progress.completed)
        self.assertEqual(first_progress.latest_output.name, "run_lab01")
        self.assertIn("Status: Done - latest run_lab01", learning_path_progress_text(first_step, first_progress))
        self.assertTrue(last_progress.completed)
        self.assertEqual(last_progress.latest_output.name, "all_batches")
        self.assertFalse(second_progress.completed)
        self.assertIn("Status: Not run yet", learning_path_progress_text(LEARNING_PATH[1], second_progress))
        self.assertEqual(next_learning_path_step(progress_items), LEARNING_PATH[1])
        self.assertIn("Progress: 2/10 complete", learning_path_summary_text(progress_items))
        self.assertIn("Next: 2. Disturb and tune", learning_path_summary_text(progress_items))

    def test_recommended_learning_path_summary_detects_completion(self) -> None:
        progress_items = tuple(
            (step, LearningPathProgress(completed=True, latest_output=Path(f"run_{index}")))
            for index, step in enumerate(LEARNING_PATH, start=1)
        )

        self.assertIsNone(next_learning_path_step(progress_items))
        self.assertIn("Progress: 10/10 complete", learning_path_summary_text(progress_items))
        self.assertIn("Course path complete", learning_path_summary_text(progress_items))

    def test_menu_actions_have_valid_guided_lesson_cards(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                self.assertTrue(action.description)
                self.assertTrue(action.try_this)
                self.assertTrue(action.watch)
                text = lesson_text(action)
                self.assertIn("Setup:", text)
                self.assertIn("History:", text)
                self.assertIn("Try:", text)
                self.assertIn("Change:", text)
                self.assertIn("Watch:", text)
                self.assertTrue(parameter_hint(action))
                config = load_config(action.config_path)
                self.assertIn("model_path", config)

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

    def test_interactive_menu_cards_show_configured_presets(self) -> None:
        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab02_interactive = by_label[("Lab02 PID Control", "Interactive")]
        lab04_cartesian = by_label[("Lab04 Panda Manipulator", "Cartesian interactive")]

        self.assertEqual(
            configured_preset_labels(lab02_interactive.config_path),
            ("Gentle P", "Damped PD", "Aggressive PID"),
        )
        self.assertIn("Presets: Gentle P, Damped PD, Aggressive PID", lesson_text(lab02_interactive))
        self.assertIn("Presets: Soft reach, Default reach, Far target", lesson_text(lab04_cartesian))

    def test_filter_menu_actions_matches_search_terms(self) -> None:
        labels = {action.label for action in filter_menu_actions("pid noise")}
        self.assertIn("Sensor noise", labels)
        self.assertNotIn("Control delay", labels)

        wall_labels = {action.label for action in filter_menu_actions("wall stiffness")}
        self.assertIn("Soft wall", wall_labels)
        self.assertIn("Stiff wall", wall_labels)
        self.assertIn("Virtual wall", wall_labels)

        interactive_labels = {action.label for action in filter_menu_actions("interactive")}
        self.assertIn("Interactive", interactive_labels)
        self.assertIn("2DOF interactive", interactive_labels)
        self.assertIn("Cartesian interactive", interactive_labels)

        preset_labels = {(action.group, action.label) for action in filter_menu_actions("far target")}
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian interactive"), preset_labels)

    def test_experience_filters_group_scenarios_by_learning_mode(self) -> None:
        filter_keys = {filter_option.key for filter_option in EXPERIENCE_FILTERS}
        self.assertIn("hands-on", filter_keys)
        self.assertIn("compare", filter_keys)
        self.assertIn("wall", filter_keys)
        self.assertEqual(experience_filter_description("missing"), EXPERIENCE_FILTERS[0].description)

        by_label = {(action.group, action.label): action for action in MENU_ACTIONS}
        lab04_wall = by_label[("Lab04 Panda Manipulator", "Virtual wall")]
        self.assertIn("hands-on", action_tags(lab04_wall))
        self.assertIn("wall", action_tags(lab04_wall))
        self.assertIn("panda", action_tags(lab04_wall))
        self.assertIn("singularity", action_tags(by_label[("Lab03 2DOF Arm and Trajectories", "2DOF DLS singularity")]))

        hands_on = {(action.group, action.label) for action in filter_menu_actions("", experience_filter="hands-on")}
        self.assertIn(("Lab01 Mass-Spring-Damper", "Interactive"), hands_on)
        self.assertIn(("Lab04 Panda Manipulator", "Joint target"), hands_on)
        self.assertNotIn(("Lab04 Panda Manipulator", "Cartesian reach"), hands_on)

        two_dof_labels = {action.label for action in filter_menu_actions("", experience_filter="2dof")}
        self.assertIn("2DOF joint-space", two_dof_labels)
        self.assertIn("2DOF task-space", two_dof_labels)
        self.assertNotIn("Step profile", two_dof_labels)

        wall_labels = {action.label for action in filter_menu_actions("", experience_filter="wall")}
        self.assertEqual(wall_labels, {"Soft wall", "Stiff wall", "Virtual wall"})

        singularity_labels = {action.label for action in filter_menu_actions("", experience_filter="singularity")}
        self.assertEqual(singularity_labels, {"2DOF singularity", "2DOF DLS singularity"})

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
            "cartesian_target.gain",
            parameter_hint(by_label[("Lab04 Panda Manipulator", "Soft Cartesian")]),
        )
        self.assertIn("virtual_wall.stiffness", parameter_hint(by_label[("Lab04 Panda Manipulator", "Virtual wall")]))

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

            self.assertEqual(action_latest_output(MENU_ACTIONS[0], outputs), run_path)
            self.assertIn("History: Latest run_lab01", action_history_text(MENU_ACTIONS[0], outputs))
            self.assertEqual(action_history_text(MENU_ACTIONS[1], outputs), "History: Not run yet")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_action_latest_output(MENU_ACTIONS[0], outputs)
                missing = launch_action_latest_output(MENU_ACTIONS[1], outputs)

            opener.assert_called_once_with(report)
            self.assertIsNone(missing)

    def test_launch_latest_output_opens_report_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run"
            run_path.mkdir()
            report = run_path / "report.html"
            report.write_text("<html></html>", encoding="utf-8")

            with patch("mclab.learner_menu.open_path") as opener:
                launch_latest_output({"path": run_path})

            opener.assert_called_once_with(report)

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

    def test_failed_run_status_reports_exit_code(self) -> None:
        status = FakeStatus()

        _set_status_after_run(MENU_ACTIONS[0], status, 2, None)

        self.assertIn("Failed", status.value)
        self.assertIn("exit code 2", status.value)
