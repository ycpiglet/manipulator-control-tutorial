from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.logging import create_output_path  # noqa: E402


class FixedDatetime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 6, 27, 20, 50, 0)


class LoggingTests(unittest.TestCase):
    def test_automatic_output_paths_are_unique_within_same_second(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("mclab.sim.logging.PROJECT_ROOT", Path(temp_dir)),
                patch("mclab.sim.logging.datetime", FixedDatetime),
            ):
                first = create_output_path("lab01_msd")
                second = create_output_path("lab01_msd")

            self.assertEqual(first.name, "20260627_205000_lab01_msd")
            self.assertEqual(second.name, "20260627_205000_lab01_msd_001")
            self.assertTrue((first / "plots").is_dir())
            self.assertTrue((second / "plots").is_dir())
