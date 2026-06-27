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

        for batch_name, scenarios in batch.BATCH_SETS.items():
            with self.subTest(batch=batch_name):
                self.assertGreaterEqual(len(scenarios), 2)
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
            self.assertIn("demo_scenario/report.html", (output / "index.html").read_text(encoding="utf-8"))
            parent_index = output.parent / "index.html"
            self.assertIn("batch_output/index.html", parent_index.read_text(encoding="utf-8"))

    def test_run_batch_rejects_unknown_batch_name(self) -> None:
        with self.assertRaises(ValueError):
            batch.run_batch("missing_batch")


if __name__ == "__main__":
    unittest.main()
