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
from mclab.learning_guides import guide_for_config  # noqa: E402
from mclab.sim.reporting import NEXT_RUN_SUGGESTIONS, _normalize_path, write_outputs_index, write_run_report  # noqa: E402


class FixedDatetime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 6, 27, 20, 50, 0)


class LoggingTests(unittest.TestCase):
    def test_guided_configs_have_suggested_next_runs(self) -> None:
        missing: list[str] = []
        for config_path in sorted((ROOT / "configs").glob("**/*.yaml")):
            relative = config_path.relative_to(ROOT).as_posix()
            if guide_for_config(config_path=relative) and _normalize_path(relative) not in NEXT_RUN_SUGGESTIONS:
                missing.append(relative)

        self.assertEqual(missing, [])

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
                summary={"max_position": 0.1, "settling_time": None, "interaction_events": 3},
                notes="# Lab01\nCheck position.",
                interaction_events=[
                    {
                        "time": 0.01,
                        "kind": "slider",
                        "name": "stiffness",
                        "label": "Stiffness [N/m]",
                        "value": 80.0,
                    },
                    {
                        "time": 0.015,
                        "kind": "preset",
                        "name": "stiff_spring",
                        "label": "Stiff spring",
                        "value": {"damping": 1.0, "stiffness": 90.0},
                    },
                    {
                        "time": 0.02,
                        "kind": "marker",
                        "name": "observation",
                        "label": "Mark observation",
                        "value": {
                            "changed_sliders": {"stiffness": 80.0},
                            "sliders": {"stiffness": 80.0},
                            "status": {"energy": "0.125"},
                        },
                    },
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
            self.assertIn("Reproduce This Run", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --viewer",
                html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot",
                html,
            )
            self.assertIn("Config Highlights", html)
            self.assertIn("force_input.magnitude", html)
            self.assertIn("stiffness", html)
            self.assertIn("Result Check", html)
            self.assertIn("Data saved", html)
            self.assertIn("Learner actions", html)
            self.assertIn("max_position", html)
            self.assertIn("n/a", html)
            self.assertIn("Learner Action Summary", html)
            self.assertIn("Actions recorded", html)
            self.assertIn("Latest slider values", html)
            self.assertIn("Preset choices", html)
            self.assertIn("Stiff spring", html)
            self.assertIn("90", html)
            self.assertIn("Observation Markers", html)
            self.assertIn("1 marked observation saved.", html)
            self.assertIn("Changed sliders", html)
            self.assertIn("Sliders", html)
            self.assertIn("Live status", html)
            self.assertIn("Interaction Log", html)
            self.assertIn("Stiffness [N/m]", html)
            self.assertIn("Mark observation", html)
            self.assertIn("0.125", html)
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
            self.assertIn("Plot Guide", html)
            self.assertIn("Position", html)
            self.assertIn("steady-state error", html)

    def test_run_report_renders_configured_presets_as_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                '{"lab_name": "lab02_pid", "config_name": "interactive_disturbance"}',
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")
            (output / "config.yaml").write_text(
                (
                    "model_path: models/lab02_pid/scene.xml\n"
                    "interaction:\n"
                    "  live_tuning: true\n"
                    "  tuning_presets:\n"
                    "    - label: Damped PD\n"
                    "      values:\n"
                    "        kp: 60.0\n"
                    "        kd: 16.0\n"
                    "    - label: Aggressive PID\n"
                    "      values:\n"
                    "        kp: 120.0\n"
                    "        output_limit: 120.0\n"
                ),
                encoding="utf-8",
            )

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Configured Presets", html)
            self.assertIn("Damped PD", html)
            self.assertIn("Aggressive PID", html)
            self.assertIn("<span>kp</span>", html)
            self.assertIn("<strong>60</strong>", html)
            self.assertNotIn("interaction.tuning_presets", html)

    def test_run_report_suggests_next_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/p_high_gain.yaml",
                        "config_name": "p_high_gain",
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Suggested Next Runs", html)
            self.assertIn("Lab02 PD Damping", html)
            self.assertIn("configs/lab02_pid/pd_damped.yaml", html)
            self.assertIn("Use derivative action to calm overshoot.", html)
            self.assertIn("Lab02 Saturation", html)
            self.assertIn(
                "python -m mclab run lab02 --config configs/lab02_pid/pd_damped.yaml",
                html,
            )
            self.assertIn("--plots essential --open-report", html)

    def test_run_report_includes_domain_specific_result_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/dls_singularity_2dof.yaml",
                        "config_name": "dls_singularity_2dof",
                        "samples": 120,
                        "max_jacobian_condition": 150.0,
                        "min_manipulability": 0.01,
                        "max_dls_joint_speed": 4.2,
                        "max_abs_tau_cmd": 75.0,
                        "max_wall_penetration_cm": 1.2,
                        "max_wall_retreat_cm": 0.5,
                        "max_abs_virtual_wall_force": 22.0,
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Jacobian condition", html)
            self.assertIn("near-singular motion", html)
            self.assertIn("Manipulability", html)
            self.assertIn("DLS joint speed", html)
            self.assertIn("Actuator effort", html)
            self.assertIn("Virtual wall contact", html)
            self.assertIn("Wall retreat", html)
            self.assertIn("Wall force", html)
            self.assertIn("check-inspect", html)
            self.assertIn("check-observed", html)

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
            self.assertIn("1/10 steps complete", html)
            self.assertIn("1. Feel 1D physics", html)
            self.assertIn("2. Disturb and tune", html)
            self.assertIn("Not run yet", html)
            self.assertIn("Run this step", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml",
                html,
            )
            self.assertIn("--plots essential --open-report", html)
            self.assertIn("Repeat this step", html)
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
            self.assertIn("1/10 steps complete", html)
            self.assertIn("10. Compare the course", html)
            self.assertIn("20260627_151000_all_batches/report.html", html)
            self.assertIn("python -m mclab batch all --open-report", html)

    def test_outputs_index_handles_empty_outputs_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("No run reports were found yet.", html)
            self.assertIn("No saved runs yet.", html)
