from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.sim.logging import RunLogger, create_output_path  # noqa: E402
from mclab.sim.reporting import write_outputs_index, write_run_report  # noqa: E402


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
                config_path="configs/lab01_msd/default.yaml",
                output_dir=Path(temp_dir) / "run",
            )
            logger.record(time=0.0, position=0.1)
            output = logger.save_with_artifacts(
                summary={"max_position": 0.1, "settling_time": None, "interaction_events": 1},
                notes="# Lab01\nCheck position.",
                interaction_events=[
                    {
                        "time": 0.01,
                        "kind": "slider",
                        "name": "stiffness",
                        "label": "Stiffness [N/m]",
                        "value": 80.0,
                    }
                ],
            )

            report = output / "report.html"
            self.assertTrue(report.exists())
            html = report.read_text(encoding="utf-8")
            self.assertIn("lab01_msd - default report", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Try", html)
            self.assertIn("Change", html)
            self.assertIn("mass, damping, stiffness", html)
            self.assertIn("max_position", html)
            self.assertIn("n/a", html)
            self.assertIn("Interaction Log", html)
            self.assertIn("Stiffness [N/m]", html)
            self.assertIn("interaction_events.json", html)
            self.assertIn("Check position.", html)
            self.assertIn("config.yaml", html)
            events = json.loads((output / "interaction_events.json").read_text(encoding="utf-8"))
            self.assertEqual(events[0]["name"], "stiffness")
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["config_path"], "configs/lab01_msd/default.yaml")
            self.assertEqual(summary["config_name"], "default")

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

    def test_run_report_updates_parent_outputs_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_150117_lab01_msd"
            (output / "plots").mkdir(parents=True)
            (output / "summary.json").write_text(
                (
                    '{"lab_name": "lab01_msd", "config_path": "configs/lab01_msd/default.yaml", '
                    '"config_name": "default", "samples": 10, "duration": 0.18, "max_abs_position": 0.24}'
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            write_run_report(output)

            index = Path(temp_dir) / "index.html"
            self.assertTrue(index.exists())
            html = index.read_text(encoding="utf-8")
            self.assertIn("20260627_150117_lab01_msd/report.html", html)
            self.assertIn("lab01_msd", html)
            self.assertIn("Config", html)
            self.assertIn("Progress Snapshot", html)
            self.assertIn("Learning Path", html)
            self.assertIn("1/9 steps complete", html)
            self.assertIn("1. Feel 1D physics", html)
            self.assertIn("2. Disturb and tune", html)
            self.assertIn("Not run yet", html)
            self.assertIn("Lab01", html)
            self.assertIn("1 saved run", html)
            self.assertIn("Lesson", html)
            self.assertIn("Next", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Run underdamped", html)
            self.assertIn("configs/lab01_msd/default.yaml", html)
            self.assertIn("max abs position", html)
            self.assertIn("0.24", html)

    def test_outputs_index_links_to_batch_index_when_no_run_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_lab02_pid_compare"
            output.mkdir()
            (output / "summary.json").write_text(
                (
                    '{"lab_name": "batch", "config_name": "lab02_pid_compare", '
                    '"samples": 9, "duration": ""}'
                ),
                encoding="utf-8",
            )
            (output / "index.html").write_text("<html>batch</html>", encoding="utf-8")

            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("20260627_151000_lab02_pid_compare/index.html", html)
            self.assertIn("lab02_pid_compare", html)
            self.assertIn("Progress Snapshot", html)
            self.assertIn("Batches", html)
            self.assertIn("1 saved run", html)

    def test_outputs_index_marks_all_batch_learning_path_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_all_batches"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch_group",
                        "config_name": "all_batches",
                        "batch_name": "all",
                        "samples": 4,
                        "duration": "",
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html>all batches</html>", encoding="utf-8")

            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("Learning Path", html)
            self.assertIn("1/9 steps complete", html)
            self.assertIn("9. Compare the course", html)
            self.assertIn("20260627_151000_all_batches/report.html", html)

    def test_outputs_index_handles_empty_outputs_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("No run reports were found yet.", html)
            self.assertIn("No saved runs yet.", html)
