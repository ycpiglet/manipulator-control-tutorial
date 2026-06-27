from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab import batch  # noqa: E402
from mclab.config import load_config  # noqa: E402


class BatchTests(unittest.TestCase):
    def test_batch_sets_reference_valid_configs(self) -> None:
        self.assertIn("lab01_msd_compare", batch.list_batch_sets())
        self.assertIn("lab02_pid_compare", batch.list_batch_sets())
        self.assertIn("lab03_2dof_compare", batch.list_batch_sets())
        self.assertIn("lab04_wall_compare", batch.list_batch_sets())

        for batch_name, scenarios in batch.BATCH_SETS.items():
            with self.subTest(batch=batch_name):
                self.assertGreaterEqual(len(scenarios), 2)
                self.assertIn(batch_name, batch.BATCH_GUIDES)
                self.assertTrue(batch.BATCH_GUIDES[batch_name].comparison_specs)
            for scenario in scenarios:
                with self.subTest(batch=batch_name, scenario=scenario.label):
                    self.assertIn(scenario.lab_name, batch.LAB_RUNNERS)
                    config = load_config(scenario.config_path)
                    self.assertIn("model_path", config)
                    self.assertTrue(scenario.plots)

    def test_run_batch_creates_child_runs_and_index(self) -> None:
        calls: list[dict[str, object]] = []
        scenario = batch.BatchScenario(
            label="demo scenario",
            lab_name="lab01",
            config_path="configs/lab01_msd/default.yaml",
            plots="essential",
        )

        def fake_runner(config: dict[str, object], **kwargs: object) -> Path:
            output = Path(kwargs["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            config_path = Path(kwargs["config_path"])
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": config_path.as_posix(),
                        "config_name": config_path.stem,
                        "duration": 1.0,
                        "samples": 3,
                        "max_abs_position": 0.5,
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"fake-png")
            calls.append({"config": config, **kwargs})
            return output

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(batch.BATCH_SETS, {"unit_compare": (scenario,)}, clear=False),
                patch.dict(batch.LAB_RUNNERS, {"lab01": fake_runner}, clear=False),
            ):
                output = batch.run_batch(
                    "unit_compare",
                    output_dir=Path(tmp) / "batch_output",
                    plot=False,
                    seed=11,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["plot"], False)
            self.assertEqual(calls[0]["viewer"], False)
            self.assertEqual(calls[0]["headless"], True)
            self.assertEqual(calls[0]["plot_selection"], "essential")
            self.assertEqual(calls[0]["seed"], 11)
            self.assertTrue((output / "demo_scenario" / "summary.json").exists())
            self.assertTrue((output / "batch_summary.json").exists())
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue((output / "report.html").exists())
            self.assertIn("demo_scenario/report.html", (output / "index.html").read_text(encoding="utf-8"))
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("Learning Focus", report_html)
            self.assertIn("demo scenario", report_html)
            self.assertIn("max abs position", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("Plot Previews", report_html)
            self.assertIn("demo_scenario/plots/position.png", report_html)
            parent_index = output.parent / "index.html"
            self.assertIn("batch_output/report.html", parent_index.read_text(encoding="utf-8"))

    def test_run_batch_rejects_unknown_batch_name(self) -> None:
        with self.assertRaises(ValueError):
            batch.run_batch("missing_batch")

    def test_comparison_plots_are_written_from_run_logs(self) -> None:
        scenarios = (
            batch.BatchScenario("baseline", "lab02", "configs/lab02_pid/default.yaml"),
            batch.BatchScenario("high gain", "lab02", "configs/lab02_pid/p_high_gain.yaml"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch_output"
            for scenario in scenarios:
                run_dir = output / scenario.label.replace(" ", "_")
                run_dir.mkdir(parents=True)
                (run_dir / "log.csv").write_text(
                    (
                        "time,position,position_error,control_force\n"
                        "0.0,0.0,0.2,12.0\n"
                        "0.1,0.1,0.1,6.0\n"
                        "0.2,0.2,0.0,0.0\n"
                    ),
                    encoding="utf-8",
                )
                (run_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "lab_name": "lab02_pid",
                            "overshoot_percent": 0.0 if scenario.label == "baseline" else 12.5,
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")

            written = batch.write_comparison_plots(output, "lab02_pid_compare", scenarios)
            batch.write_batch_report(output, "lab02_pid_compare", scenarios)

            self.assertTrue(written)
            self.assertTrue((output / "comparison_plots" / "position_compare.png").exists())
            self.assertTrue((output / "comparison_plots" / "error_compare.png").exists())
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("Metric Highlights", report_html)
            self.assertIn("overshoot percent", report_html)
            self.assertIn("high gain", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("controller.kp", report_html)
            self.assertIn("Comparison Plots", report_html)
            self.assertIn("comparison_plots/position_compare.png", report_html)


if __name__ == "__main__":
    unittest.main()
