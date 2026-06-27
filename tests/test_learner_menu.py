from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402
from mclab.learner_menu import MENU_ACTIONS, build_run_args, lesson_text  # noqa: E402


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
                self.assertIn("--hide-viewer-ui", args)
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
