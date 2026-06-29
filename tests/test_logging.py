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
                            "question": "Question: Which slider change made the response easiest to explain?",
                            "prediction": "Higher stiffness should create a sharper force peak.",
                            "outcome": "Matched",
                            "evidence_prompt": "Evidence to capture: position, force, and total energy.",
                            "note": "Higher stiffness made the force spike easier to see.",
                            "changed_sliders": {"stiffness": 80.0},
                            "sliders": {"stiffness": 80.0},
                            "status": {"energy": "0.125"},
                        },
                    },
                ],
                learner_snapshot={
                    "slider_values": {"stiffness": 80.0, "damping": 1.0},
                    "changed_sliders": {"stiffness": 80.0},
                    "live_status": {"energy": "0.125"},
                    "playback_speed": 1.5,
                    "extra_controls": {"joint_target_offset": 0.1},
                },
                learner_tuned_config={
                    "model_path": "models/lab01_msd/scene.xml",
                    "mass": 1.0,
                    "damping": 1.0,
                    "stiffness": 80.0,
                    "interaction": {"panel": False, "live_tuning": False},
                },
            )

            report = output / "report.html"
            self.assertTrue(report.exists())
            html = report.read_text(encoding="utf-8")
            self.assertIn("lab01_msd - default report", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Try", html)
            self.assertIn("Change", html)
            self.assertIn("Prediction", html)
            self.assertIn("Question", html)
            self.assertIn("Before changing mass, damping, stiffness", html)
            self.assertIn("Viewer Legend", html)
            self.assertIn("Gray marker", html)
            self.assertIn("Green marker", html)
            self.assertIn(
                "What baseline motion should later damping and stiffness cases be compared against?",
                html,
            )
            self.assertIn("mass, damping, stiffness", html)
            self.assertIn("Next Actions", html)
            self.assertIn("Use these shortcuts right after reading this report.", html)
            self.assertIn("Review saved evidence", html)
            self.assertIn("Replay tuned values", html)
            self.assertIn("Try next: Lab01 Underdamped", html)
            self.assertIn("Controls:", html)
            self.assertIn("Pull/Push buttons and A/D keys", html)
            self.assertIn("Compare batch: Lab01 mass-spring-damper comparison", html)
            self.assertIn("Reproduce This Run", html)
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --viewer",
                html,
            )
            self.assertIn(
                "python -m mclab run lab01 --config configs/lab01_msd/default.yaml --headless --plot",
                html,
            )
            self.assertIn("Comparison Batch", html)
            self.assertIn("python -m mclab batch lab01_msd_compare --open-report", html)
            self.assertIn("Control Surface", html)
            self.assertIn("Auto run", html)
            self.assertIn("Edit YAML or use Config Highlights before rerunning", html)
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
            self.assertIn("Learner Snapshot", html)
            self.assertIn("Changed slider values", html)
            self.assertIn("Final slider values", html)
            self.assertIn("Final live status", html)
            self.assertIn("Final control state", html)
            self.assertIn("Playback speed", html)
            self.assertIn("joint_target_offset", html)
            self.assertIn("Replay Tuned Config", html)
            self.assertIn("Regenerate tuned artifacts", html)
            self.assertIn("Watch tuned replay", html)
            self.assertIn("Learner Worksheet", html)
            self.assertIn("Open worksheet.md", html)
            self.assertIn("Observation Markers", html)
            self.assertIn("1 marked observation saved.", html)
            self.assertIn("Review prompt", html)
            self.assertIn("1 learning question, 1 prediction, 1 outcome, and 1 learner note were saved.", html)
            self.assertIn("Prediction Review", html)
            self.assertIn("Predictions saved", html)
            self.assertIn("Observation notes", html)
            self.assertIn("Latest observation", html)
            self.assertIn("Latest outcome", html)
            self.assertIn("Matched", html)
            self.assertIn("Evidence to compare", html)
            self.assertIn("Evidence Review Cue", html)
            self.assertIn("Review-ready pairs", html)
            self.assertIn("Prediction-only markers", html)
            self.assertIn("Observation-only markers", html)
            self.assertIn("Outcome judgments", html)
            self.assertIn("Decide whether each prediction matched, partially matched, or surprised you.", html)
            self.assertIn("Latest prediction:", html)
            self.assertIn("Latest note:", html)
            self.assertIn("Which slider change made the response easiest to explain?", html)
            self.assertIn("Prediction", html)
            self.assertIn("Higher stiffness should create a sharper force peak.", html)
            self.assertIn("Evidence prompt", html)
            self.assertIn("position, force, and total energy", html)
            self.assertIn("Higher stiffness made the force spike easier to see.", html)
            self.assertIn("Changed sliders", html)
            self.assertIn("Sliders", html)
            self.assertIn("Live status", html)
            self.assertIn("Interaction Log", html)
            self.assertIn("Stiffness [N/m]", html)
            self.assertIn("Mark observation", html)
            self.assertIn("0.125", html)
            self.assertIn("interaction_events.json", html)
            self.assertIn("learner_snapshot.json", html)
            self.assertIn("learner_tuned_config.yaml", html)
            self.assertIn("worksheet.md", html)
            self.assertIn("Check position.", html)
            self.assertIn("config.yaml", html)
            worksheet = output / "worksheet.md"
            self.assertTrue(worksheet.exists())
            worksheet_text = worksheet.read_text(encoding="utf-8")
            self.assertIn("# MCLab Learner Worksheet", worksheet_text)
            self.assertIn("## Learning Guide", worksheet_text)
            self.assertIn("## Key Parameters", worksheet_text)
            self.assertIn("## Observation Markers", worksheet_text)
            self.assertIn("Higher stiffness should create a sharper force peak.", worksheet_text)
            self.assertIn("Prediction outcome: Matched", worksheet_text)
            self.assertIn("Live status", worksheet_text)
            self.assertIn("energy: 0.125", worksheet_text)
            self.assertIn("## Review Checklist", worksheet_text)
            self.assertIn("- [ ] Compare the latest prediction with the plots in report.html.", worksheet_text)
            self.assertIn("## Suggested Next Experiments", worksheet_text)
            self.assertIn("### Lab01 Underdamped", worksheet_text)
            self.assertIn("Reason: See what changes when damping is too low.", worksheet_text)
            self.assertIn(
                "Command: python -m mclab run lab01 --config configs/lab01_msd/underdamped.yaml",
                worksheet_text,
            )
            self.assertIn("## Comparison Batch", worksheet_text)
            self.assertIn("Command: python -m mclab batch lab01_msd_compare --open-report", worksheet_text)
            self.assertIn("- report.html", worksheet_text)
            events = json.loads((output / "interaction_events.json").read_text(encoding="utf-8"))
            self.assertEqual(events[0]["name"], "stiffness")
            snapshot = json.loads((output / "learner_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["changed_sliders"], {"stiffness": 80.0})
            self.assertEqual(snapshot["playback_speed"], 1.5)
            tuned_config = (output / "learner_tuned_config.yaml").read_text(encoding="utf-8")
            self.assertIn("stiffness: 80.0", tuned_config)
            self.assertIn("live_tuning: False", tuned_config)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["config_path"], "configs/lab01_msd/default.yaml")
            self.assertEqual(summary["config_name"], "default")

    def test_run_report_points_to_relevant_comparison_batch(self) -> None:
        cases = [
            (
                {
                    "lab_name": "lab04_panda",
                    "config_path": "configs/lab04_panda/interactive_virtual_wall.yaml",
                    "config_name": "interactive_virtual_wall",
                },
                "python -m mclab batch lab04_wall_compare --open-report",
            ),
            (
                {
                    "lab_name": "lab04_panda",
                    "config_path": "configs/lab04_panda/cartesian_reach.yaml",
                    "config_name": "cartesian_reach",
                },
                "python -m mclab batch lab04_cartesian_compare --open-report",
            ),
            (
                {
                    "lab_name": "lab03_2dof",
                    "config_path": "configs/lab03_2dof/task_space_2dof.yaml",
                    "config_name": "task_space_2dof",
                },
                "python -m mclab batch lab03_2dof_compare --open-report",
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (summary, command) in enumerate(cases):
                output = Path(temp_dir) / f"run_{index}"
                output.mkdir()
                (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
                (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

                html = write_run_report(output).read_text(encoding="utf-8")

                self.assertIn("Comparison Batch", html)
                self.assertIn(command, html)

    def test_interactive_run_report_shows_hands_on_evidence_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "interactive"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Interactive\n", encoding="utf-8")

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Hands-on Evidence", html)
            self.assertIn("Needs observation", html)
            self.assertIn("write a prediction and note", html)

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {"note": "The mass settled after the pulse."},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Needs prediction", html)
            self.assertIn("fill the Prediction field", html)
            self.assertIn("Observation markers", html)
            self.assertIn("Evidence Review Cue", html)
            self.assertIn("Observation-only markers", html)
            self.assertIn("Repeat the run and write a prediction before observing", html)

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "note": "The mass settled after the pulse.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Done for learning path", html)
            self.assertIn("Judge prediction outcome", html)
            self.assertIn("mark whether the prediction matched", html)

            (output / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "label": "Mark observation",
                            "value": {
                                "prediction": "More damping should settle faster.",
                                "outcome": "Partly matched",
                                "note": "The mass settled after the pulse.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_run_report(output).read_text(encoding="utf-8")
            self.assertIn("Done for learning path", html)
            self.assertIn("at least one Mark observation entry with a prediction", html)
            self.assertIn("Prediction outcome", html)
            self.assertIn("Partly matched", html)

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
            self.assertIn("Next Actions", html)
            self.assertIn("Open the key plot", html)
            self.assertIn("Priority plot", html)
            self.assertIn("Plot Guide", html)
            self.assertIn("Position", html)
            self.assertIn("steady-state error", html)
            worksheet_text = (output / "worksheet.md").read_text(encoding="utf-8")
            self.assertIn("## Plot Review", worksheet_text)
            self.assertIn("Priority plot: plots/position.png", worksheet_text)
            self.assertIn("Read first: Position", worksheet_text)
            self.assertIn("Compare actual motion against target", worksheet_text)

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
                    "  panel: true\n"
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
            self.assertIn("Control Surface", html)
            self.assertIn("MCLab Interaction window", html)
            self.assertIn("Sliders with Changed values summary", html)
            self.assertIn("Prediction, outcome, Use live status, Mark observation", html)
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
            (output / "config.yaml").write_text(
                (ROOT / "configs/lab02_pid/p_high_gain.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Suggested Next Runs", html)
            self.assertIn("Lab02 PD Damping", html)
            self.assertIn("configs/lab02_pid/pd_damped.yaml", html)
            self.assertIn("Use derivative action to calm overshoot.", html)
            self.assertIn("Prediction:", html)
            self.assertIn("Before changing controller.kp, controller.kd", html)
            self.assertIn("Question:", html)
            self.assertIn("Which gain change trades speed for overshoot or smoother force?", html)
            self.assertIn("Key changes:", html)
            self.assertIn("controller.kd", html)
            self.assertIn("0 -&gt; 18", html)
            self.assertIn("Lab02 Saturation", html)
            self.assertIn(
                "python -m mclab run lab02 --config configs/lab02_pid/pd_damped.yaml",
                html,
            )
            self.assertIn("--plots essential --open-report", html)

    def test_run_report_next_actions_use_correct_lab_for_panda_trajectory_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run"
            output.mkdir()
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab04_panda",
                        "config_path": "configs/lab04_panda/joint_pd.yaml",
                        "config_name": "joint_pd",
                    }
                ),
                encoding="utf-8",
            )
            (output / "config.yaml").write_text(
                (ROOT / "configs/lab04_panda/joint_pd.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (output / "notes.md").write_text("# Demo\n", encoding="utf-8")

            report = write_run_report(output)

            html = report.read_text(encoding="utf-8")
            self.assertIn("Try next: Lab04 Panda S-Curve Joint Path", html)
            self.assertIn(
                "python -m mclab run lab04 --config configs/lab04_panda/trajectory_tracking.yaml",
                html,
            )
            self.assertNotIn(
                "python -m mclab run lab03 --config configs/lab04_panda/trajectory_tracking.yaml",
                html,
            )

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
                        "max_dls_condition_scale": 0.82,
                        "max_dls_damping": 0.21,
                        "max_abs_qdot": 0.01,
                        "max_settled_abs_qdot": 0.0001,
                        "max_joint_drift_norm": 0.004,
                        "duration": 30.0,
                        "max_wall_penetration_cm": 1.2,
                        "max_wall_retreat_cm": 0.5,
                        "first_wall_contact_time": 1.4,
                        "wall_contact_duration": 2.2,
                        "wall_contact_fraction": 0.44,
                        "max_abs_virtual_wall_force": 22.0,
                        "max_abs_virtual_wall_spring_force": 18.0,
                        "max_abs_virtual_wall_damping_force": 4.0,
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
            self.assertIn("Condition-aware DLS", html)
            self.assertIn("Damping schedule reached", html)
            self.assertIn("30s stability hold", html)
            self.assertIn("Settled joint speed", html)
            self.assertIn("Joint drift stability", html)
            self.assertIn("Actuator effort", html)
            self.assertIn("Virtual wall contact", html)
            self.assertIn("Wall retreat", html)
            self.assertIn("Wall contact timing", html)
            self.assertIn("First contact at", html)
            self.assertIn("Wall force", html)
            self.assertIn("Wall force components", html)
            self.assertIn("check-inspect", html)
            self.assertIn("check-observed", html)

    def test_run_report_updates_parent_outputs_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_150117_lab01_msd"
            (output / "plots").mkdir(parents=True)
            (output / "plots" / "position.png").write_bytes(b"fake-png")
            (output / "plots" / "energy.png").write_bytes(b"fake-png")
            (output / "learner_tuned_config.yaml").write_text("interaction:\n  panel: false\n", encoding="utf-8")
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
            self.assertIn("1/11 steps complete", html)
            self.assertIn("Next action: run lab01", html)
            self.assertIn("1. Feel 1D physics", html)
            self.assertIn("2. Disturb and tune", html)
            self.assertIn("7. Handle singularity", html)
            self.assertIn("configs/lab03_2dof/condition_aware_dls_2dof.yaml", html)
            self.assertIn("<strong>Predict:</strong>", html)
            self.assertIn("<strong>Watch:</strong>", html)
            self.assertNotIn("predict how How", html)
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
            self.assertIn("Evidence", html)
            self.assertIn("<th>Worksheet</th>", html)
            self.assertIn("20260627_150117_lab01_msd/worksheet.md", html)
            self.assertIn("Worksheet", html)
            self.assertIn("<th>Replay</th>", html)
            self.assertIn("20260627_150117_lab01_msd/learner_tuned_config.yaml", html)
            self.assertIn("Tuned config", html)
            self.assertIn("Plots", html)
            self.assertIn("20260627_150117_lab01_msd/plots/position.png", html)
            self.assertIn("20260627_150117_lab01_msd/plots/energy.png", html)
            self.assertIn("Position", html)
            self.assertIn("Energy", html)
            self.assertIn("Lab01 Baseline", html)
            self.assertIn("Run underdamped", html)
            self.assertIn("configs/lab01_msd/default.yaml", html)
            self.assertIn("Latest artifacts", html)
            self.assertIn(">Report</a>", html)
            self.assertIn(">Plot: Position</a>", html)
            self.assertIn(">Replay tuned</a>", html)
            self.assertIn("No markers", html)
            self.assertIn("max abs position", html)
            self.assertIn("0.24", html)

    def test_outputs_index_links_to_batch_index_when_no_run_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "20260627_151000_lab02_pid_compare"
            output.mkdir()
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "error_compare.png").write_bytes(b"fake-png")
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
            self.assertIn("20260627_151000_lab02_pid_compare/comparison_plots/error_compare.png", html)

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
            self.assertIn("1/11 steps complete", html)
            self.assertIn("11. Compare the course", html)
            self.assertIn("<strong>Compare:</strong> Generate the course batch report set.", html)
            self.assertIn("Next action: run lab01", html)
            self.assertIn("20260627_151000_all_batches/report.html", html)
            self.assertIn("python -m mclab batch all --open-report", html)

    def test_outputs_index_requires_hands_on_prediction_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline = Path(temp_dir) / "20260627_150000_lab01_msd"
            baseline.mkdir()
            (baseline / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/default.yaml",
                        "config_name": "default",
                    }
                ),
                encoding="utf-8",
            )
            (baseline / "report.html").write_text("<html>baseline</html>", encoding="utf-8")

            interactive = Path(temp_dir) / "20260627_150100_lab01_interactive"
            interactive.mkdir()
            (interactive / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_path": "configs/lab01_msd/interactive_pull.yaml",
                        "config_name": "interactive_pull",
                    }
                ),
                encoding="utf-8",
            )
            (interactive / "report.html").write_text("<html>interactive</html>", encoding="utf-8")

            index = write_outputs_index(temp_dir)
            html = index.read_text(encoding="utf-8")

            self.assertIn("1/11 steps complete. Evidence pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 2. Disturb and tune", html)
            self.assertIn("Needs observation", html)
            self.assertIn("Add one Mark observation entry before moving on.", html)
            self.assertIn("20260627_150100_lab01_interactive/report.html", html)
            self.assertIn("<th>Evidence</th>", html)
            self.assertIn("No markers", html)

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("1/11 steps complete. Evidence pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 2. Disturb and tune", html)
            self.assertIn("Needs prediction (1 observation, 1 note)", html)
            self.assertIn("Add one Prediction in Mark observation before moving on.", html)
            self.assertIn("1 observation, 0 predictions, 1 note", html)
            self.assertIn(
                "Latest evidence: Note: The mass settled faster after damping changed.",
                html,
            )
            self.assertIn("Latest: Note: The mass settled faster after damping changed.", html)

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("2/11 steps complete. Outcome review pending: 1 hands-on step(s).", html)
            self.assertIn("Next: 3. Close the loop", html)
            self.assertIn("Done (1 observation, 1 prediction, 1 note)", html)
            self.assertIn("Add one Prediction outcome while reviewing.", html)

            (interactive / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: demo?",
                                "prediction": "More damping should settle faster.",
                                "outcome": "Matched",
                                "note": "The mass settled faster after damping changed.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")
            self.assertIn("2/11 steps complete. Next: 3. Close the loop", html)
            self.assertIn("Done (1 observation, 1 prediction, 1 outcome, 1 note)", html)
            self.assertIn("1 observation, 1 prediction, 1 outcome, 1 note", html)
            self.assertIn(
                "Latest evidence: Prediction: More damping should settle faster.; "
                "Outcome: Matched; "
                "Note: The mass settled faster after damping changed.",
                html,
            )
            self.assertIn(
                "Latest: Prediction: More damping should settle faster.; "
                "Outcome: Matched; "
                "Note: The mass settled faster after damping changed.",
                html,
            )

    def test_outputs_index_summarizes_latest_observation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "20260627_151500_lab02_interactive"
            run.mkdir()
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab02_pid",
                        "config_path": "configs/lab02_pid/interactive_disturbance.yaml",
                        "config_name": "interactive_disturbance",
                    }
                ),
                encoding="utf-8",
            )
            (run / "report.html").write_text("<html>pid</html>", encoding="utf-8")
            (run / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Old prediction should not be summarized.",
                                "note": "Old note should not be summarized.",
                            },
                        },
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "prediction": "Higher damping should reduce overshoot.",
                                "outcome": "Surprised",
                                "note": "The trace settled faster after the preset.",
                                "status": {
                                    "Error [m]": 0.0123456,
                                    "Control [N]": 4.2,
                                    "Unused": "--",
                                    "Energy": "n/a",
                                    "Mode": "observe",
                                },
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("Evidence Quality", html)
            self.assertIn("Outcome coverage: 50% of predictions", html)
            self.assertIn("Outcome mix: Surprised 1", html)
            self.assertIn("2 observations, 2 predictions, 1 outcome, 2 notes", html)
            self.assertIn(
                "Latest: Prediction: Higher damping should reduce overshoot.; "
                "Outcome: Surprised; "
                "Note: The trace settled faster after the preset.; "
                "Status: Error [m]=0.0123456, Control [N]=4.2, Mode=observe",
                html,
            )
            self.assertNotIn("Old prediction should not be summarized.", html)

    def test_outputs_index_requires_evidence_for_live_tuning_learning_path_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dls_run = Path(temp_dir) / "20260627_150200_lab03_dls"
            dls_run.mkdir()
            (dls_run / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab03_2dof",
                        "config_path": "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
                        "config_name": "condition_aware_dls_2dof",
                    }
                ),
                encoding="utf-8",
            )
            (dls_run / "report.html").write_text("<html>dls</html>", encoding="utf-8")

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("7. Handle singularity", html)
            self.assertIn("Needs observation", html)
            self.assertIn("20260627_150200_lab03_dls/report.html", html)

            (dls_run / "interaction_events.json").write_text(
                json.dumps(
                    [
                        {
                            "kind": "marker",
                            "name": "observation",
                            "value": {
                                "question": "Question: What changed near the singularity?",
                                "prediction": "More damping should reduce joint speed.",
                                "note": "DLS damping rose as condition number increased.",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            html = write_outputs_index(temp_dir).read_text(encoding="utf-8")

            self.assertIn("Done (1 observation, 1 prediction, 1 note)", html)
            self.assertIn("1 observation, 1 prediction, 1 note", html)

    def test_outputs_index_handles_empty_outputs_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = write_outputs_index(temp_dir)

            html = index.read_text(encoding="utf-8")
            self.assertIn("No run reports were found yet.", html)
            self.assertIn("No saved runs yet.", html)
