from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LaunchScriptTests(unittest.TestCase):
    def test_lab_launchers_use_consistent_viewer_flags(self) -> None:
        expected = {
            "run_lab01.cmd": ("lab01", "configs\\lab01_msd\\default.yaml"),
            "run_lab01_interactive.cmd": ("lab01", "configs\\lab01_msd\\interactive_pull.yaml"),
            "run_lab02.cmd": ("lab02", "configs\\lab02_pid\\default.yaml"),
            "run_lab02_interactive.cmd": ("lab02", "configs\\lab02_pid\\interactive_disturbance.yaml"),
            "run_lab03.cmd": ("lab03", "configs\\lab03_2dof\\minimum_jerk.yaml"),
            "run_lab03_interactive.cmd": ("lab03", "configs\\lab03_2dof\\interactive_tracking.yaml"),
            "run_lab04.cmd": ("lab04", "configs\\lab04_panda\\joint_pd.yaml"),
            "run_lab04_interactive.cmd": ("lab04", "configs\\lab04_panda\\interactive_joint_hold.yaml"),
        }

        for filename, (lab_name, config_path) in expected.items():
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn(f"-m mclab run {lab_name}", text)
                self.assertIn(f"--config {config_path}", text)
                self.assertIn(
                    "--viewer --hide-viewer-ui --realtime --pause-at-end --plot --plots essential",
                    text,
                )
                self.assertIn("scripts\\bootstrap_and_run.py", text)
