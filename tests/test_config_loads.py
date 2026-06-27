from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.config import load_config  # noqa: E402


class ConfigLoadTests(unittest.TestCase):
    def test_lab_configs_load(self) -> None:
        paths = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "configs").rglob("*.yaml"))
        for path in paths:
            with self.subTest(path=path):
                config = load_config(path)
                self.assertIsInstance(config, dict)
                self.assertIn("model_path", config)
                self.assertGreater(config["sim_time"], 0)
