from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LaunchScriptTests(unittest.TestCase):
    def test_top_level_menu_launcher_exists(self) -> None:
        text = (ROOT / "run_mclab.cmd").read_text(encoding="utf-8")
        self.assertIn("scripts\\bootstrap_and_run.py", text)
        self.assertIn("-m mclab menu", text)

    def test_lab_launchers_use_consistent_viewer_flags(self) -> None:
        expected = {
            "run_lab01.cmd": ("lab01", "configs\\lab01_msd\\default.yaml", "essential"),
            "run_lab01_interactive.cmd": ("lab01", "configs\\lab01_msd\\interactive_pull.yaml", "essential"),
            "run_lab02.cmd": ("lab02", "configs\\lab02_pid\\default.yaml", "essential"),
            "run_lab02_interactive.cmd": ("lab02", "configs\\lab02_pid\\interactive_disturbance.yaml", "essential"),
            "run_lab03.cmd": ("lab03", "configs\\lab03_2dof\\joint_space_2dof.yaml", "essential"),
            "run_lab03_interactive.cmd": ("lab03", "configs\\lab03_2dof\\interactive_2dof.yaml", "task"),
            "run_lab04.cmd": ("lab04", "configs\\lab04_panda\\joint_pd.yaml", "essential"),
            "run_lab04_interactive.cmd": ("lab04", "configs\\lab04_panda\\interactive_joint_hold.yaml", "essential"),
            "run_lab04_wall_interactive.cmd": (
                "lab04",
                "configs\\lab04_panda\\interactive_virtual_wall.yaml",
                "wall",
            ),
        }

        for filename, (lab_name, config_path, plot_selection) in expected.items():
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn(f"-m mclab run {lab_name}", text)
                self.assertIn(f"--config {config_path}", text)
                self.assertIn(
                    f"--viewer --realtime --pause-at-end --plot --plots {plot_selection}",
                    text,
                )
                self.assertNotIn("--show-viewer-ui", text)
                self.assertIn("--open-report", text)
                self.assertIn("scripts\\bootstrap_and_run.py", text)

    def test_launchers_stop_when_setup_fails(self) -> None:
        setup_command = 'scripts\\bootstrap_and_run.py" --setup-only'
        guard_command = "if errorlevel 1 exit /b %errorlevel%"

        for path in sorted(ROOT.glob("*.cmd")):
            with self.subTest(filename=path.name):
                text = path.read_text(encoding="utf-8")
                if setup_command not in text:
                    continue
                self.assertIn(guard_command, text)
                self.assertLess(text.index(setup_command), text.index(guard_command))

    def test_batch_launchers_use_headless_comparison_batches(self) -> None:
        expected = {
            "run_batch_lab01.cmd": "lab01_msd_compare",
            "run_batch_lab02.cmd": "lab02_pid_compare",
            "run_batch_lab03.cmd": "lab03_2dof_compare",
            "run_batch_lab04.cmd": "lab04_wall_compare",
            "run_all_batches.cmd": "all",
        }

        for filename, batch_name in expected.items():
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn(f"-m mclab batch {batch_name}", text)
                self.assertIn("--open-report", text)
                self.assertNotIn("--viewer", text)
                self.assertIn("scripts\\bootstrap_and_run.py", text)

        lab04_text = (ROOT / "run_batch_lab04.cmd").read_text(encoding="utf-8")
        self.assertIn("third_party\\mujoco_menagerie\\franka_emika_panda\\scene.xml", lab04_text)
        all_text = (ROOT / "run_all_batches.cmd").read_text(encoding="utf-8")
        self.assertIn("third_party\\mujoco_menagerie\\franka_emika_panda\\scene.xml", all_text)
