from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.logging import RunLogger, create_output_path  # noqa: E402
from mclab.sim.reporting import write_run_report  # noqa: E402


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

    def test_run_logger_writes_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RunLogger(
                "lab01_msd",
                {"model_path": "models/lab01_msd/scene.xml", "mass": 1.0},
                output_dir=Path(temp_dir) / "run",
            )
            logger.record(time=0.0, position=0.1)
            output = logger.save(summary={"max_position": 0.1}, notes="# Lab01\nCheck position.")

            report = output / "report.html"
            self.assertTrue(report.exists())
            html = report.read_text(encoding="utf-8")
            self.assertIn("lab01_msd report", html)
            self.assertIn("max_position", html)
            self.assertIn("Check position.", html)
            self.assertIn("config.yaml", html)

    def test_run_report_includes_saved_plot_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            (output / "plots").mkdir(parents=True)
            (output / "summary.json").write_text('{"lab_name": "demo"}', encoding="utf-8")
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "plots" / "position.png").write_bytes(b"fake-png")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("plots/position.png", html)
            self.assertIn("position.png", html)
