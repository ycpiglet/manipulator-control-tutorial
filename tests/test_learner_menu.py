from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402
from mclab.learner_menu import (  # noqa: E402
    MENU_ACTIONS,
    _set_status_after_run,
    build_run_args,
    lesson_text,
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
        self.assertIn(("Lab02 PID Control", "Interactive"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF joint-space"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF task-space"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF singularity"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "2DOF interactive"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Step profile"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "Minimum jerk"), labels)
        self.assertIn(("Lab03 2DOF Arm and Trajectories", "1D interactive"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Neutral hold"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Reach X"), labels)
        self.assertIn(("Lab04 Panda Manipulator", "Cartesian reach"), labels)
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
                self.assertIn(action.config_path, args)
                self.assertEqual(args[-2:], ["--plots", action.plots])

    def test_menu_actions_have_valid_guided_lesson_cards(self) -> None:
        for action in MENU_ACTIONS:
            with self.subTest(label=action.label, config=action.config_path):
                self.assertTrue(action.description)
                self.assertTrue(action.try_this)
                self.assertTrue(action.watch)
                text = lesson_text(action)
                self.assertIn("Try:", text)
                self.assertIn("Watch:", text)
                config = load_config(action.config_path)
                self.assertIn("model_path", config)

    def test_parse_run_output_path_detects_completed_run(self) -> None:
        parsed = parse_run_output_path(r"Run complete: C:\tmp\outputs\20260627_150117_lab04_panda")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.name, "20260627_150117_lab04_panda")

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
