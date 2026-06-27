from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402


class ConfigLoadTests(unittest.TestCase):
    def test_lab_configs_load(self) -> None:
        paths = [
            "configs/lab01_msd/default.yaml",
            "configs/lab01_msd/interactive_pull.yaml",
            "configs/lab02_pid/default.yaml",
            "configs/lab02_pid/interactive_disturbance.yaml",
            "configs/lab03_2dof/minimum_jerk.yaml",
            "configs/lab03_2dof/interactive_tracking.yaml",
            "configs/lab04_panda/joint_pd.yaml",
            "configs/lab04_panda/interactive_joint_hold.yaml",
            "configs/lab04_panda/impedance_wall.yaml",
        ]
        for path in paths:
            with self.subTest(path=path):
                config = load_config(path)
                self.assertIsInstance(config, dict)
                self.assertIn("model_path", config)
                self.assertGreater(config["sim_time"], 0)
