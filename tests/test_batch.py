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
        self.assertNotIn(batch.ALL_BATCH_NAME, batch.list_batch_sets())
        self.assertIn(batch.ALL_BATCH_NAME, batch.list_batch_sets(include_all=True))
        self.assertIn("lab01_msd_compare", batch.list_batch_sets())
        self.assertIn("lab02_pid_compare", batch.list_batch_sets())
        self.assertIn("lab03_2dof_compare", batch.list_batch_sets())
        self.assertIn("lab04_wall_compare", batch.list_batch_sets())
        self.assertIn("lab04_cartesian_compare", batch.list_batch_sets())
        lab03_labels = {scenario.label for scenario in batch.BATCH_SETS["lab03_2dof_compare"]}
        self.assertIn("condition_aware_dls", lab03_labels)
        self.assertIn("condition_aware_early", lab03_labels)
        self.assertIn("condition_aware_late", lab03_labels)
        lab04_wall_labels = {scenario.label for scenario in batch.BATCH_SETS["lab04_wall_compare"]}
        self.assertIn("low_damping_wall", lab04_wall_labels)
        self.assertIn("high_damping_wall", lab04_wall_labels)
        self.assertIn("near_wall", lab04_wall_labels)
        self.assertIn("far_wall", lab04_wall_labels)
        self.assertIn("max_dls_condition_scale", batch.BATCH_GUIDES["lab03_2dof_compare"].metric_keys)

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
            self.assertIn("Next Experiments", report_html)
            self.assertIn("Reproduce Commands", report_html)
            self.assertIn("python -m mclab batch unit_compare --open-report", report_html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot --plots essential",
                report_html,
            )
            self.assertIn("demo scenario", report_html)
            self.assertIn("Predict", report_html)
            self.assertIn("Question", report_html)
            self.assertIn("Watch", report_html)
            self.assertIn("What baseline motion", report_html)
            self.assertIn("max abs position", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("Plot Previews", report_html)
            self.assertIn("demo_scenario/plots/position.png", report_html)
            parent_index = output.parent / "index.html"
            self.assertIn("batch_output/report.html", parent_index.read_text(encoding="utf-8"))

    def test_run_all_batches_creates_group_report(self) -> None:
        def fake_run_batch(batch_name: str, **kwargs: object) -> Path:
            output = Path(kwargs["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch",
                        "config_name": batch_name,
                        "samples": len(batch.BATCH_SETS[batch_name]),
                    }
                ),
                encoding="utf-8",
            )
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            return output

        expected_batches = list(batch.list_batch_sets())
        expected_scenarios = sum(len(scenarios) for scenarios in batch.BATCH_SETS.values())
        with tempfile.TemporaryDirectory() as tmp:
            with patch("mclab.batch.run_batch", side_effect=fake_run_batch) as runner:
                output = batch.run_all_batches(
                    output_dir=Path(tmp) / "all_output",
                    plot=False,
                    seed=23,
                )

            self.assertEqual([call.args[0] for call in runner.call_args_list], expected_batches)
            for call in runner.call_args_list:
                self.assertFalse(call.kwargs["plot"])
                self.assertEqual(call.kwargs["seed"], 23)
            self.assertTrue((output / "report.html").exists())
            self.assertTrue((output / "index.html").exists())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["batch_name"], batch.ALL_BATCH_NAME)
            self.assertEqual(summary["scenario_runs"], expected_scenarios)
            batch_summary = json.loads((output / "batch_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(batch_summary["batches"]), len(expected_batches))
            report_html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("All Comparison Batches", report_html)
            self.assertIn("lab01_msd_compare/report.html", report_html)
            self.assertIn("lab04_cartesian_compare/report.html", report_html)
            self.assertIn("lab04_wall_compare/report.html", report_html)
            self.assertIn("lab01_msd_compare/report.html", (output / "index.html").read_text(encoding="utf-8"))

    def test_run_batch_rejects_unknown_batch_name(self) -> None:
        with self.assertRaises(ValueError):
            batch.run_batch("missing_batch")

    def test_display_metric_keys_skip_unrelated_all_zero_fallback_metrics(self) -> None:
        guide = batch.BATCH_GUIDES["lab04_cartesian_compare"]
        rows = [
            {
                "summary": {
                    "final_cartesian_error_cm": 0.6,
                    "max_wall_penetration_cm": 0.0,
                    "max_wall_retreat_cm": 0.0,
                    "max_abs_virtual_wall_force": 0.0,
                }
            }
        ]

        keys = batch._display_metric_keys(guide, rows)

        self.assertIn("final_cartesian_error_cm", keys)
        self.assertNotIn("max_wall_penetration_cm", keys)
        self.assertNotIn("max_wall_retreat_cm", keys)
        self.assertNotIn("max_abs_virtual_wall_force", keys)

    def test_comparison_takeaways_rank_error_metrics_by_magnitude(self) -> None:
        rows = [
            {"label": "near_zero", "summary": {"steady_state_error": -0.01}},
            {"label": "far_negative", "summary": {"steady_state_error": -0.5}},
            {"label": "positive", "summary": {"steady_state_error": 0.2}},
        ]

        html = batch._comparison_takeaways(rows, ["steady_state_error"])

        self.assertIn("near_zero</strong> has the smallest error magnitude", html)
        self.assertIn("far_negative</strong> has the largest", html)

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
            self.assertIn("Comparison Takeaways", report_html)
            self.assertIn("Predict", report_html)
            self.assertIn("Which controller reaches the target fastest", report_html)
            self.assertIn("python -m mclab batch lab02_pid_compare --open-report", report_html)
            self.assertIn(
                "python -m mclab run lab02 --config configs/lab02_pid/default.yaml --headless --plot --plots essential",
                report_html,
            )
            self.assertIn("baseline</strong> has the least overshoot", report_html)
            self.assertIn("high gain</strong> overshoots most", report_html)
            self.assertIn("Metric Highlights", report_html)
            self.assertIn("overshoot percent", report_html)
            self.assertIn("high gain", report_html)
            self.assertIn("Baseline Changes", report_html)
            self.assertIn("+12.5", report_html)
            self.assertIn("raise `controller.kd`", report_html)
            self.assertIn("Parameter Differences", report_html)
            self.assertIn("controller.kp", report_html)
            self.assertIn("Comparison Plots", report_html)
            self.assertIn("comparison_plots/position_compare.png", report_html)


if __name__ == "__main__":
    unittest.main()
