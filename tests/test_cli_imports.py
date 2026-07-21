from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.batch import BATCH_SETS  # noqa: E402
from mclab.application.artifacts import write_manifest  # noqa: E402
from mclab.application.catalog import CONCRETE_BATCH_NAMES, stable_scenario_id  # noqa: E402
from mclab.cli import (  # noqa: E402
    LABS,
    _batch_handoff_detail_text,
    _scenario_course_lines,
    _scenario_next_command_lines,
    _scenario_primary_command_lines,
    _scenario_replay_command_line,
    main,
)
from mclab.cli import build_parser  # noqa: E402
from mclab.config import load_config  # noqa: E402
from mclab.doctor import DoctorCheck  # noqa: E402
from mclab.learner_menu import BATCH_ACTIONS, LEARNING_PATH, MENU_ACTIONS  # noqa: E402
from mclab.output_cleanup import CleanupOperationError, build_cleanup_plan  # noqa: E402


def _publish_scenario_run(
    run_path: Path,
    lab_name: str,
    config_path: str,
    *,
    events: list[dict[str, object]] | None = None,
    plot: bool = True,
    finished_at: str | None = None,
) -> Path:
    """Publish a digest-matching schema-1 run for completion-facing CLI tests."""

    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": lab_name,
                "config_path": config_path,
                "config_name": Path(config_path).stem,
            }
        ),
        encoding="utf-8",
    )
    if plot:
        plots = run_path / "plots"
        plots.mkdir(exist_ok=True)
        (plots / "position.png").write_bytes(b"fake-png")
    (run_path / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_path / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
    if events is not None:
        (run_path / "interaction_events.json").write_text(
            json.dumps(events),
            encoding="utf-8",
        )
    config = load_config(config_path)
    write_manifest(
        run_path,
        scenario_id=stable_scenario_id(lab_name, config_path),
        status="completed",
        config=config,
        config_path=config_path,
        started_at=finished_at,
        finished_at=finished_at,
    )
    return run_path


def _publish_batch_run(
    run_path: Path,
    batch_name: str,
    *,
    worksheet_text: str = "# Batch worksheet\n\n## Prediction Check\n",
) -> Path:
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch",
                "batch_name": batch_name,
                "config_name": batch_name,
            }
        ),
        encoding="utf-8",
    )
    plots = run_path / "comparison_plots"
    plots.mkdir(exist_ok=True)
    (plots / "comparison.png").write_bytes(b"fake-png")
    (run_path / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_path / "worksheet.md").write_text(worksheet_text, encoding="utf-8")
    write_manifest(
        run_path,
        scenario_id=f"batch.{batch_name}",
        status="completed",
        config={"batch_name": batch_name, "plot": True},
        run_kind="comparison_batch",
    )
    return run_path


def _publish_course_batch_run(run_path: Path) -> Path:
    """Publish all trusted child batches before terminal course artifacts."""

    run_path.mkdir(parents=True, exist_ok=True)
    for batch_name in CONCRETE_BATCH_NAMES:
        worksheet_text = (
            "\n".join(
                (
                    "# Batch worksheet",
                    "",
                    "## Prediction Check",
                    "",
                    "- Review prompt: Compare the prediction with the evidence, then copy the "
                    "outcome into personal/course notes outside the saved-run folder.",
                    "",
                    "## Viewer Handoff",
                    "",
                    "- Start with: underdamped",
                    "- Viewer rerun: python -m mclab run lab01 --config "
                    "configs/lab01_msd/underdamped.yaml --viewer --realtime "
                    "--pause-at-end --plot --plots essential",
                )
            )
            if batch_name == "lab01_msd_compare"
            else "# Batch worksheet\n\n## Prediction Check\n"
        )
        _publish_batch_run(
            run_path / batch_name,
            batch_name,
            worksheet_text=worksheet_text,
        )

    (run_path / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch_group",
                "batch_name": "all",
                "config_name": "all",
            }
        ),
        encoding="utf-8",
    )
    write_manifest(
        run_path,
        scenario_id="batch.all",
        status="running",
        config={"batch_name": "all", "plot": True},
        run_kind="comparison_batch",
    )
    (run_path / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_path / "worksheet.md").write_text(
        "\n".join(
            (
                "# Course worksheet",
                "",
                "## Batch Review",
                "",
                "- Lab01 Mass-Spring-Damper Comparison",
                "  - Viewer handoff: lab01_msd_compare/report.html#viewer-handoff",
            )
        ),
        encoding="utf-8",
    )
    write_manifest(
        run_path,
        scenario_id="batch.all",
        status="completed",
        config={"batch_name": "all", "plot": True},
        run_kind="comparison_batch",
    )
    return run_path


class CliImportTests(unittest.TestCase):
    def test_cli_lists_labs(self) -> None:
        self.assertIn("lab01", LABS)
        self.assertIn("lab02", LABS)
        self.assertIn("lab03", LABS)
        self.assertIn("lab04", LABS)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["list"]), 0)
        printed = output.getvalue()
        self.assertIn("Learner entry points:", printed)
        self.assertIn("python -m mclab doctor", printed)
        self.assertIn("python -m mclab menu", printed)
        self.assertIn("python -m mclab coverage", printed)
        self.assertIn("python -m mclab coverage --details", printed)
        self.assertIn("python -m mclab params wall", printed)
        self.assertIn("python -m mclab next --preview", printed)
        self.assertIn("python -m mclab next", printed)
        self.assertIn("python -m mclab review", printed)
        self.assertIn("python -m mclab index --open", printed)
        self.assertIn("Available labs:", printed)
        self.assertIn("Available batches:", printed)
        self.assertIn("lab01", printed)
        self.assertIn("lab01_msd_compare", BATCH_SETS)
        self.assertIn("lab02_pid_compare", BATCH_SETS)

        default_output = StringIO()
        with redirect_stdout(default_output):
            self.assertEqual(main([]), 0)
        self.assertIn("Learner entry points:", default_output.getvalue())

    def test_cli_accepts_batch_comparison_options(self) -> None:
        args = build_parser().parse_args(
            [
                "batch",
                "lab02_pid_compare",
                "--output-dir",
                "outputs/demo_batch",
                "--no-plot",
                "--open-report",
                "--seed",
                "7",
            ]
        )
        self.assertEqual(args.command, "batch")
        self.assertEqual(args.batch_name, "lab02_pid_compare")
        self.assertEqual(args.output_dir, "outputs/demo_batch")
        self.assertTrue(args.no_plot)
        self.assertTrue(args.open_report)
        self.assertEqual(args.seed, 7)

        all_args = build_parser().parse_args(["batch", "all", "--no-plot"])
        self.assertEqual(all_args.command, "batch")
        self.assertEqual(all_args.batch_name, "all")
        self.assertTrue(all_args.no_plot)

    def test_top_level_help_prints_learner_workflow(self) -> None:
        output = StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            build_parser().parse_args(["--help"])

        help_text = output.getvalue()
        self.assertIn("Learner workflow:", help_text)
        self.assertIn("python -m mclab doctor", help_text)
        self.assertIn("python -m mclab menu", help_text)
        self.assertIn("python -m mclab coverage", help_text)
        self.assertIn("python -m mclab params wall", help_text)
        self.assertIn("python -m mclab next --preview", help_text)
        self.assertIn("python -m mclab next", help_text)
        self.assertIn("python -m mclab review", help_text)
        self.assertIn("python -m mclab index --open", help_text)

    def test_cli_runs_doctor_check(self) -> None:
        args = build_parser().parse_args(["doctor"])
        self.assertEqual(args.command, "doctor")

        with (
            patch(
                "mclab.cli.run_doctor_checks", return_value=[DoctorCheck("Python", "OK", "ready")]
            ),
            patch("builtins.print") as printer,
        ):
            self.assertEqual(main(["doctor"]), 0)

        printed = str(printer.call_args.args[0])
        self.assertIn("MCLab Doctor", printed)
        self.assertIn("[OK] Python", printed)
        self.assertIn("Next learner steps:", printed)
        self.assertIn("python -m mclab coverage --details", printed)
        self.assertIn("python -m mclab params wall --filter hands-on", printed)
        self.assertIn("python -m mclab next --preview", printed)
        self.assertIn("python -m mclab review", printed)
        self.assertIn("python -m mclab index --open", printed)

    def test_cli_generates_outputs_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"
            index_path = output_dir / "index.html"

            args = build_parser().parse_args(["index", "--output-dir", str(output_dir), "--open"])
            self.assertEqual(args.command, "index")
            self.assertEqual(args.output_dir, str(output_dir))
            self.assertTrue(args.open)

            with (
                patch("mclab.cli.write_outputs_index", return_value=index_path) as writer,
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["index", "--output-dir", str(output_dir), "--open"]), 0)

            writer.assert_called_once_with(output_dir)
            opener.assert_called_once_with(index_path)
            printer.assert_called_once_with(f"Outputs index: {index_path}")

    def test_cli_prints_experience_coverage_and_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"

            args = build_parser().parse_args(["coverage", "--output-dir", str(output_dir)])
            self.assertEqual(args.command, "coverage")
            self.assertEqual(args.output_dir, str(output_dir))

            with patch("builtins.print") as printer:
                self.assertEqual(main(["coverage", "--output-dir", str(output_dir)]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Experience coverage: 0/7 types tried", printed)
        self.assertIn("Coverage map: Intro basics: Next", printed)
        self.assertIn("Next experience: Intro basics", printed)
        self.assertIn("Next mode: headless plot run", printed)
        self.assertIn("Next action: Run Lab01 Mass-Spring-Damper - Auto demo.", printed)
        self.assertIn(
            "Evidence needed: A saved run report, priority plot, and worksheet for the baseline 1D plant.",
            printed,
        )
        self.assertIn(
            "Next command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn("Next guide: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn("Mission: Run the demo", printed)
        self.assertIn("Try: Start here and compare position, velocity, and applied force.", printed)
        self.assertIn(
            "Change: mass, damping, stiffness, initial_position, force_input.magnitude", printed
        )
        self.assertIn("Values: mass=1; damping=2; stiffness=50; initial_position=0.1", printed)
        self.assertIn("Prediction: Before changing mass, damping, stiffness", printed)
        self.assertIn("Question:", printed)
        self.assertIn("Watch: How quickly the mass returns near zero.", printed)
        self.assertIn("Start steps:", printed)
        self.assertIn("Challenge:", printed)
        self.assertIn("Controls: Auto run; edit YAML before running", printed)
        self.assertNotIn("Coverage details:", printed)

    def test_cli_prints_experience_coverage_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"

            args = build_parser().parse_args(
                ["coverage", "--output-dir", str(output_dir), "--details"]
            )
            self.assertEqual(args.command, "coverage")
            self.assertEqual(args.output_dir, str(output_dir))
            self.assertTrue(args.details)

            with patch("builtins.print") as printer:
                self.assertEqual(
                    main(["coverage", "--output-dir", str(output_dir), "--details"]), 0
                )

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Coverage details:", printed)
        self.assertIn(
            "- Intro basics: Next; mode: headless plot run; "
            "focus: Run Lab01 Mass-Spring-Damper - Auto demo.; "
            "evidence: A saved run report, priority plot, and worksheet for the baseline 1D plant.",
            printed,
        )
        self.assertIn(
            "Command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn(
            "- Hands-on controls: Missing; mode: hands-on viewer; "
            "focus: Run an interactive viewer and use one button, slider, or preset.; "
            "evidence: At least one learner-control event plus one prediction-backed observation marker.",
            printed,
        )
        self.assertIn("Controls: MCLab Interaction panel, Pull/Push buttons and A/D keys", printed)
        self.assertIn("Counts as control: experiment buttons, live sliders, Quick presets", printed)
        self.assertIn(
            "- Comparison batch: Missing; mode: comparison batch; "
            "focus: Run any Comparison Batches card, then open the worksheet Prediction Check.; "
            "evidence: A batch comparison report and worksheet with a Prediction Check table.",
            printed,
        )
        self.assertIn(
            "Controls: comparison batch; inspect plots and worksheet, then use Viewer Handoff for hands-on rerun.",
            printed,
        )
        self.assertIn(
            "- Virtual wall: Missing; mode: hands-on viewer; "
            "focus: Run Lab04 Virtual wall and try Close wall -> Back away -> Re-enter wall.; "
            "evidence: A virtual-wall run with target crossing, contact/release, force, or wall-gap evidence.",
            printed,
        )
        self.assertIn("Target X - away  A / Left / Target X + into wall  D / Right", printed)
        self.assertIn(
            "view/evidence helpers such as Pause, Playback speed, and Use live status do not count.",
            printed,
        )

    def test_cli_coverage_complete_points_to_learning_path_when_path_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"
            output_dir.mkdir()
            complete_observation = {
                "kind": "marker",
                "name": "observation",
                "value": {
                    "prediction": "The response should change.",
                    "outcome": "Matched",
                    "note": "The change was visible.",
                },
            }
            _publish_scenario_run(
                output_dir / "run_lab01_interactive",
                "lab01_msd",
                "configs/lab01_msd/interactive_pull.yaml",
                events=[
                    {"kind": "button", "name": "push", "label": "Push Right"},
                    complete_observation,
                ],
            )
            _publish_scenario_run(
                output_dir / "run_lab03_dls",
                "lab03_2dof",
                "configs/lab03_2dof/condition_aware_dls_2dof.yaml",
                events=[
                    {"kind": "slider", "name": "dls_gain", "label": "DLS gain", "value": 4.0},
                    complete_observation,
                ],
            )
            _publish_scenario_run(
                output_dir / "run_lab04_wall_auto",
                "lab04_panda",
                "configs/lab04_panda/wall_soft.yaml",
            )
            _publish_scenario_run(
                output_dir / "run_lab04_wall",
                "lab04_panda",
                "configs/lab04_panda/interactive_virtual_wall.yaml",
            )
            _publish_batch_run(output_dir / "batch_lab02", "lab02_pid_compare")

            with patch("builtins.print") as printer:
                self.assertEqual(main(["coverage", "--output-dir", str(output_dir)]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Experience coverage: 7/7 types tried", printed)
        self.assertIn("continue the learning path", printed)
        self.assertIn("Next experience: Coverage complete", printed)
        self.assertIn("Progress:", printed)
        self.assertIn("Next path step:", printed)
        self.assertIn("Next command: python -m mclab", printed)
        self.assertIn("Next guide:", printed)
        self.assertIn(
            "Evidence repair queue: run python -m mclab review --limit 3 to fix saved hands-on evidence.",
            printed,
        )
        self.assertIn(
            "Top repair: run_lab04_wall - Needs required preset Close wall; "
            "Lab04 Panda Manipulator - Virtual wall -> "
            "python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertNotIn("Next command: replay one saved scenario", printed)

    def test_cli_prints_learning_path_progress_and_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"

            args = build_parser().parse_args(["path", "--output-dir", str(output_dir), "--all"])
            self.assertEqual(args.command, "path")
            self.assertEqual(args.output_dir, str(output_dir))
            self.assertTrue(args.all)

            with patch("builtins.print") as printer:
                self.assertEqual(main(["path", "--output-dir", str(output_dir), "--all"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Progress: 0/12 complete", printed)
        self.assertIn("Next: 1. Feel 1D physics", printed)
        self.assertIn("Next step: 1. Feel 1D physics", printed)
        self.assertIn(
            "Next command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn("Next guide: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn("Mission: Run the demo", printed)
        self.assertIn(
            "Change: mass, damping, stiffness, initial_position, force_input.magnitude", printed
        )
        self.assertIn("Values: mass=1; damping=2; stiffness=50; initial_position=0.1", printed)
        self.assertIn("Prediction: Before changing mass, damping, stiffness", printed)
        self.assertNotIn("Viewer: MuJoCo side panels are hidden", printed)
        self.assertIn("Controls: Auto run; edit YAML before running", printed)
        self.assertIn("Path map:", printed)
        self.assertIn("1. Feel 1D physics: Not run yet", printed)

    def test_cli_previews_next_learning_path_step_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"

            args = build_parser().parse_args(["next", "--output-dir", str(output_dir), "--preview"])
            self.assertEqual(args.command, "next")
            self.assertEqual(args.output_dir, str(output_dir))
            self.assertTrue(args.preview)

            with (
                patch("mclab.cli.load_config") as loader,
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["next", "--output-dir", str(output_dir), "--preview"]), 0)

        loader.assert_not_called()
        opener.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Next step: 1. Feel 1D physics", printed)
        self.assertIn(
            "Next command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn("Next guide: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn("Mission: Run the demo", printed)
        self.assertIn("Try: Start here and compare position, velocity, and applied force.", printed)
        self.assertIn(
            "Change: mass, damping, stiffness, initial_position, force_input.magnitude", printed
        )
        self.assertIn("Values: mass=1; damping=2; stiffness=50; initial_position=0.1", printed)
        self.assertIn("Prediction: Before changing mass, damping, stiffness", printed)
        self.assertIn("Question:", printed)
        self.assertIn("Watch: How quickly the mass returns near zero.", printed)
        self.assertIn("Start steps:", printed)
        self.assertNotIn("Viewer: MuJoCo side panels are hidden", printed)
        self.assertIn("Controls: Auto run; edit YAML before running", printed)
        self.assertIn(
            "Next cue: Run this scenario, then review the saved plot and worksheet.", printed
        )
        self.assertNotIn("Running next step:", printed)

    def test_cli_preview_names_first_hands_on_action_for_unrun_viewer_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"
            _publish_scenario_run(
                output_dir / "run_lab01_auto",
                "lab01_msd",
                "configs/lab01_msd/default.yaml",
            )

            with (
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["next", "--output-dir", str(output_dir), "--preview"]), 0)

        opener.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Next step: 2. Disturb and tune", printed)
        self.assertIn("Next guide: Lab01 Mass-Spring-Damper - Interactive", printed)
        self.assertIn(
            "Next cue: Predict, run the viewer, try presets Lightly damped -> Heavy damping -> Stiff spring, "
            "then Mark observation with a prediction and note.",
            printed,
        )
        self.assertNotIn("Running next step:", printed)

    def test_cli_runs_next_learning_path_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"
            output = _publish_scenario_run(
                Path(tmp).resolve() / "next_run",
                "lab01_msd",
                "configs/lab01_msd/default.yaml",
            )
            report = output / "report.html"
            calls: list[dict[str, object]] = []

            def fake_runner(_config: dict[str, object], **kwargs: object) -> Path:
                calls.append(kwargs)
                return output

            with (
                patch.dict("mclab.cli.LABS", {"lab01": fake_runner}, clear=False),
                patch("mclab.cli.load_config", return_value={"model_path": "demo.xml"}) as loader,
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["next", "--output-dir", str(output_dir), "--seed", "11"]), 0)

        loader.assert_called_once_with("configs/lab01_msd/default.yaml")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["config_path"], Path("configs/lab01_msd/default.yaml"))
        self.assertFalse(calls[0]["viewer"])
        self.assertTrue(calls[0]["headless"])
        self.assertFalse(calls[0]["realtime"])
        self.assertFalse(calls[0]["pause_at_end"])
        self.assertTrue(calls[0]["plot"])
        self.assertEqual(calls[0]["plot_selection"], "essential")
        self.assertEqual(calls[0]["seed"], 11)
        opener.assert_called_once_with(report)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Next guide: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn("Running next step: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn(f"Run complete: {output}", printed)
        self.assertIn(f"Plots: {output / 'plots'} (1 PNG; first: position.png)", printed)

    def test_cli_previews_batch_next_step_with_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp).resolve() / "outputs"
            with (
                patch("mclab.cli.learning_path_progress_items", return_value=()),
                patch("mclab.cli.learning_path_summary_text", return_value="Progress: batch next"),
                patch(
                    "mclab.cli.learning_path_milestone_text",
                    return_value="Milestones: compare next",
                ),
                patch("mclab.cli.next_learning_path_step", return_value=LEARNING_PATH[-1]),
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["next", "--output-dir", str(output_dir), "--preview"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Next guide: Comparison Batches - All compare", printed)
        self.assertIn("Worksheet: Not saved yet", printed)
        self.assertIn("Plots: Not saved yet", printed)
        self.assertIn("Plot review: Not available until a plot is saved", printed)
        self.assertIn("Prediction check: Write a prediction before running the batch.", printed)
        self.assertIn("Viewer handoff:", printed)

    def test_cli_prints_review_queue_and_next_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp).resolve() / "outputs"
            run_path = _publish_scenario_run(
                outputs / "run_lab01_interactive",
                "lab01_msd",
                "configs/lab01_msd/interactive_pull.yaml",
            )
            report = run_path / "report.html"
            worksheet = run_path / "worksheet.md"

            args = build_parser().parse_args(["review", "--output-dir", str(outputs), "--open"])
            self.assertEqual(args.command, "review")
            self.assertEqual(args.output_dir, str(outputs))
            self.assertTrue(args.open)
            self.assertEqual(args.limit, 5)

            with patch("mclab.cli._open_path") as opener, patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs), "--open"]), 0)

        opener.assert_called_once_with(report)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Review queue: 0 ready, 1 pending", printed)
        self.assertIn("(1 learner-action, 0 artifact-only)", printed)
        self.assertIn("Next review: run_lab01_interactive - Needs observation.", printed)
        self.assertIn(f"Next review folder: {run_path}", printed)
        self.assertIn("Next review status: Needs observation", printed)
        self.assertIn(f"Next review report: {report}", printed)
        self.assertIn(f"Next review worksheet: {worksheet}", printed)
        self.assertIn("Next review action: Lab01 Mass-Spring-Damper - Interactive", printed)
        self.assertIn(
            "Repair command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
            "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
            printed,
        )
        self.assertIn(
            "Observation next step: use experiment buttons, live sliders, or Quick presets, "
            "then mark one observation with a prediction and note.",
            printed,
        )
        self.assertIn("Learner-action review list (top 1):", printed)
        self.assertIn(
            "1. run_lab01_interactive - Needs observation; Lab01 Mass-Spring-Damper - Interactive -> "
            "python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
            "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
            printed,
        )
        self.assertIn(
            "Plot review: Position - Compare actual motion against target or reference.",
            printed,
        )
        self.assertIn("Course path next: 1. Feel 1D physics", printed)
        self.assertIn(
            "Course path command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn(
            f"Review index command: python -m mclab index --output-dir {outputs} --open", printed
        )

    def test_cli_review_names_required_preset_before_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp).resolve() / "outputs"
            _publish_scenario_run(
                outputs / "run_lab04_wall",
                "lab04_panda",
                "configs/lab04_panda/interactive_virtual_wall.yaml",
            )

            with patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs)]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("required preset: 1", printed)
        self.assertIn("Next review: run_lab04_wall - Needs required preset Close wall.", printed)
        self.assertIn("Next review status: Needs required preset Close wall", printed)
        self.assertIn(
            "Repair command: python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertIn(
            "Observation next step: try required preset Close wall, "
            "then mark one observation with a prediction and note.",
            printed,
        )
        self.assertIn("Learner-action review list (top 1):", printed)
        self.assertIn(
            "1. run_lab04_wall - Needs required preset Close wall; Lab04 Panda Manipulator - Virtual wall -> "
            "python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertIn("Course path next: 1. Feel 1D physics", printed)
        self.assertIn(
            f"Review index command: python -m mclab index --output-dir {outputs} --open", printed
        )

    def test_cli_review_groups_duplicate_repair_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp).resolve() / "outputs"
            _publish_scenario_run(
                outputs / "new_lab04_wall",
                "lab04_panda",
                "configs/lab04_panda/interactive_virtual_wall.yaml",
                finished_at="2026-07-21T03:00:00+00:00",
            )
            _publish_scenario_run(
                outputs / "old_lab04_wall",
                "lab04_panda",
                "configs/lab04_panda/interactive_virtual_wall.yaml",
                finished_at="2026-07-21T02:00:00+00:00",
            )
            _publish_scenario_run(
                outputs / "lab03_interactive",
                "lab03_2dof",
                "configs/lab03_2dof/interactive_2dof.yaml",
                finished_at="2026-07-21T01:00:00+00:00",
            )

            with patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs), "--limit", "3"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Learner-action review list (top 2):", printed)
        self.assertIn(
            "1. new_lab04_wall - Needs required preset Close wall (+1 older saved run); "
            "Lab04 Panda Manipulator - Virtual wall -> "
            "python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertNotIn("old_lab04_wall - Needs required preset Close wall;", printed)
        self.assertIn(
            "2. lab03_interactive - Needs observation; Lab03 2DOF Arm and Trajectories - 2DOF interactive -> "
            "python -m mclab run lab03 --config configs/lab03_2dof/interactive_2dof.yaml "
            "--viewer --realtime --pause-at-end --plot --plots task_disturbance --open-report",
            printed,
        )

    def test_cli_review_handles_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp).resolve() / "outputs"
            with patch("mclab.cli._open_path") as opener, patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs), "--open"]), 0)

        opener.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Review queue: No saved runs yet. Run a scenario first.", printed)
        self.assertIn("Next review: none", printed)
        self.assertIn("Learner-action review list: none", printed)
        self.assertIn("Course path next: 1. Feel 1D physics", printed)
        self.assertIn(
            "Course path command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --plots essential --open-report",
            printed,
        )
        self.assertIn(
            f"Review index command: python -m mclab index --output-dir {outputs} --open", printed
        )

    def test_cli_searches_guided_scenarios(self) -> None:
        args = build_parser().parse_args(
            ["scenarios", "virtual", "wall", "--filter", "wall", "--limit", "0"]
        )
        self.assertEqual(args.command, "scenarios")
        self.assertEqual(args.query, ["virtual", "wall"])
        self.assertEqual(args.filter, "wall")
        self.assertEqual(args.limit, 0)

        with (
            patch(
                "mclab.cli.action_history_text", return_value="History: Latest saved_virtual_wall"
            ),
            patch(
                "mclab.cli.action_mission_evidence_text",
                return_value="Mission evidence: Ready for review",
            ),
            patch(
                "mclab.cli.action_challenge_evidence_text",
                return_value="Challenge evidence: Ready to review",
            ),
            patch(
                "mclab.cli.action_evidence_text",
                return_value="Evidence: 1 observation, 1 prediction, 1 outcome, 1 note",
            ),
            patch(
                "mclab.cli.action_latest_evidence_text",
                return_value="Latest evidence: prediction matched wall force",
            ),
            patch(
                "mclab.cli.action_observation_flow_text",
                return_value="Observation flow: prediction -> observation",
            ),
            patch(
                "mclab.cli.action_observation_next_step_text",
                return_value="Observation next step: Review outcome",
            ),
            patch(
                "mclab.cli.action_preset_evidence_text",
                return_value="Preset evidence: 3 presets tried; required presets ready",
            ),
            patch(
                "mclab.cli.action_activity_mix_text",
                return_value="Activity mix: 3/3 control families",
            ),
            patch(
                "mclab.cli.action_next_cue_text",
                return_value="Next cue: Replay the tuned config, then run Compare.",
            ),
            patch("mclab.cli.action_plot_text", return_value="Plots: Latest virtual_wall.png"),
            patch(
                "mclab.cli.action_plot_review_text",
                return_value="Plot review: Virtual Wall - Compare force and gap",
            ),
            patch("mclab.cli.action_worksheet_text", return_value="Worksheet: Latest worksheet.md"),
            patch(
                "mclab.cli.action_replay_text",
                return_value="Replay: Latest learner_tuned_config.yaml",
            ),
            patch(
                "mclab.cli._scenario_latest_artifact_lines",
                return_value=["Report: Latest report.html", "Folder: Latest saved_virtual_wall"],
            ),
            patch(
                "mclab.cli._scenario_replay_command_line",
                return_value="Replay command: python -m mclab run lab04 --config learner_tuned_config.yaml --viewer",
            ),
            patch("builtins.print") as printer,
        ):
            self.assertEqual(
                main(
                    [
                        "scenarios",
                        "virtual",
                        "wall",
                        "--filter",
                        "wall",
                        "--limit",
                        "0",
                        "--details",
                    ]
                ),
                0,
            )

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Scenarios: showing", printed)
        self.assertIn(
            "Discovery tips: try `python -m mclab scenarios wall --filter hands-on --details`",
            printed,
        )
        self.assertIn("Lab04 Panda Manipulator - Virtual wall", printed)
        self.assertIn("Challenge:", printed)
        self.assertIn("Course step: 11/12 - Touch virtual wall", printed)
        self.assertIn("Done when:", printed)
        self.assertIn("Playbook:", printed)
        self.assertIn("Try:", printed)
        self.assertIn("Change: live sliders/presets: Target X/Y/Z", printed)
        self.assertIn("Values: cartesian_target.position", printed)
        self.assertIn("virtual_wall.stiffness=260", printed)
        self.assertIn("Prediction: Before changing", printed)
        self.assertIn("Question:", printed)
        self.assertIn("Watch: Target X nudge", printed)
        self.assertIn("Controls:", printed)
        self.assertIn("Counts as control:", printed)
        self.assertIn("Viewer: MuJoCo side panels are hidden", printed)
        self.assertIn("Red plane = Virtual wall location.", printed)
        self.assertIn("History: Latest saved_virtual_wall", printed)
        self.assertIn("Report: Latest report.html", printed)
        self.assertIn("Folder: Latest saved_virtual_wall", printed)
        self.assertIn("Mission evidence: Ready for review", printed)
        self.assertIn("Challenge evidence: Ready to review", printed)
        self.assertIn("Evidence: 1 observation, 1 prediction, 1 outcome, 1 note", printed)
        self.assertIn("Latest evidence: prediction matched wall force", printed)
        self.assertIn("Observation flow: prediction -> observation", printed)
        self.assertIn("Observation next step: Review outcome", printed)
        self.assertIn("Preset evidence: 3 presets tried; required presets ready", printed)
        self.assertIn("Activity mix: 3/3 control families", printed)
        self.assertIn("Next cue: Replay the tuned config, then run Compare.", printed)
        self.assertIn("Next command:", printed)
        self.assertIn("Compare command:", printed)
        self.assertIn("python -m mclab batch lab04_wall_compare --open-report", printed)
        self.assertIn("Plots: Latest virtual_wall.png", printed)
        self.assertIn("Plot review: Virtual Wall - Compare force and gap", printed)
        self.assertIn("Worksheet: Latest worksheet.md", printed)
        self.assertIn("Replay: Latest learner_tuned_config.yaml", printed)
        self.assertIn(
            "Replay command: python -m mclab run lab04 --config learner_tuned_config.yaml --viewer",
            printed,
        )
        self.assertIn("Setup: Ready", printed)
        self.assertIn(
            "Command: python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_prints_parameter_guide_for_scenarios(self) -> None:
        args = build_parser().parse_args(
            ["params", "wall", "--filter", "hands-on", "--limit", "1", "--values", "6"]
        )
        self.assertEqual(args.command, "params")
        self.assertEqual(args.query, ["wall"])
        self.assertEqual(args.filter, "hands-on")
        self.assertEqual(args.limit, 1)
        self.assertEqual(args.values, 6)

        with patch("builtins.print") as printer:
            self.assertEqual(
                main(["params", "wall", "--filter", "hands-on", "--limit", "1", "--values", "6"]), 0
            )

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Parameter guide: showing 1 of 1 match(es)", printed)
        self.assertIn("Control surface: edit YAML for auto/comparison runs", printed)
        self.assertIn("MuJoCo side panels stay hidden", printed)
        self.assertIn("Lab04 Panda Manipulator - Virtual wall", printed)
        self.assertIn("Config: configs/lab04_panda/interactive_virtual_wall.yaml", printed)
        self.assertIn("Change: live sliders/presets: Target X/Y/Z", printed)
        self.assertIn("virtual_wall.stiffness=260", printed)
        self.assertIn("Counts as control:", printed)
        self.assertIn("Prediction: Before changing", printed)
        self.assertIn("Start steps: Predict -> Run viewer", printed)
        self.assertIn(
            "Command: python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_parameter_guide_handles_empty_matches(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["params", "not-a-real-scenario-token"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Parameter guide: showing 0 of 0 match(es)", printed)
        self.assertIn("No guided scenarios matched.", printed)
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_scenario_search_handles_empty_matches(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["scenarios", "not-a-real-scenario-token"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Scenarios: showing 0 of 0 match(es)", printed)
        self.assertIn("No guided scenarios matched.", printed)
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_scenario_replay_command_uses_latest_tuned_config(self) -> None:
        action = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/interactive_virtual_wall.yaml"
        )
        tuned_config = Path("outputs/demo/learner_tuned_config.yaml")

        with patch("mclab.cli.action_latest_tuned_config", return_value=tuned_config):
            command = _scenario_replay_command_line(action)

        self.assertEqual(
            command,
            "Replay command: python -m mclab run lab04 --config "
            f"{tuned_config} --viewer --realtime --pause-at-end --plot --plots wall --open-report",
        )

    def test_cli_scenario_primary_command_uses_headless_for_auto_runs(self) -> None:
        soft_wall = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/wall_soft.yaml"
        )
        virtual_wall = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/interactive_virtual_wall.yaml"
        )

        self.assertEqual(
            _scenario_primary_command_lines(soft_wall),
            [
                "Command: python -m mclab run lab04 --config configs/lab04_panda/wall_soft.yaml "
                "--headless --plot --plots wall_compare --open-report",
                "Viewer rerun: python -m mclab run lab04 --config configs/lab04_panda/wall_soft.yaml "
                "--viewer --realtime --pause-at-end --plot --plots wall_compare --open-report",
            ],
        )
        self.assertEqual(
            _scenario_primary_command_lines(virtual_wall),
            [
                "Command: python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
                "--viewer --realtime --pause-at-end --plot --plots wall --open-report"
            ],
        )

    def test_cli_scenario_next_command_lines_include_followup_and_compare(self) -> None:
        action = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/interactive_virtual_wall.yaml"
        )

        lines = _scenario_next_command_lines(action)

        self.assertTrue(any(line.startswith("Next command:") for line in lines))
        self.assertIn(
            "Compare command: Comparison Batches - Lab04 wall compare -> "
            "python -m mclab batch lab04_wall_compare --open-report",
            lines,
        )

    def test_cli_scenario_next_command_uses_headless_for_auto_followups(self) -> None:
        action = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/wall_soft.yaml"
        )

        lines = _scenario_next_command_lines(action)

        self.assertIn(
            "Next command: Lab04 Panda Manipulator - Stiff wall -> "
            "python -m mclab run lab04 --config configs/lab04_panda/wall_stiff.yaml "
            "--headless --plot --plots wall_compare --open-report",
            lines,
        )

    def test_cli_scenario_course_lines_show_path_context(self) -> None:
        path_action = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/interactive_virtual_wall.yaml"
        )
        optional_action = next(
            action
            for action in MENU_ACTIONS
            if action.config_path == "configs/lab04_panda/neutral_hold_30s.yaml"
        )

        path_lines = _scenario_course_lines(path_action)
        optional_lines = _scenario_course_lines(optional_action)

        self.assertIn(
            "Course step: 11/12 - Touch virtual wall; Tune wall position, stiffness, damping, and retreat gain.",
            path_lines,
        )
        self.assertTrue(any(line.startswith("Done when:") for line in path_lines))
        self.assertEqual(
            optional_lines,
            [
                "Course step: Optional exploration - not required by the recommended path; "
                "use Next or Compare when ready.",
                "Done when: the run report, priority plot, and worksheet are saved.",
            ],
        )

    def test_cli_searches_comparison_batches(self) -> None:
        args = build_parser().parse_args(["batches", "wall", "--limit", "0", "--details"])
        self.assertEqual(args.command, "batches")
        self.assertEqual(args.query, ["wall"])
        self.assertEqual(args.limit, 0)
        self.assertTrue(args.details)

        with (
            patch("mclab.cli.action_history_text", return_value="History: Latest saved_batch"),
            patch("mclab.cli.action_worksheet_text", return_value="Worksheet: Latest worksheet.md"),
            patch("mclab.cli.action_plot_text", return_value="Plots: Latest error_compare.png"),
            patch(
                "mclab.cli.action_plot_review_text",
                return_value="Plot review: Error - Compare traces",
            ),
            patch(
                "mclab.cli.batch_prediction_check_text",
                return_value=(
                    "Prediction check: Worksheet is digest-published and read-only; copy Matched, "
                    "Partly matched, or Surprised into personal/course notes outside the saved-run folder."
                ),
            ),
            patch(
                "mclab.cli._batch_handoff_detail_text",
                return_value="Handoff: Latest report.html#viewer-handoff",
            ),
            patch("builtins.print") as printer,
        ):
            self.assertEqual(main(["batches", "wall", "--limit", "0", "--details"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Batches: showing", printed)
        self.assertIn("Discovery tips: try `python -m mclab batches wall --details`", printed)
        self.assertIn("Comparison Batches - Lab04 wall compare", printed)
        self.assertIn("Mission: Run", printed)
        self.assertIn("Setup: Ready", printed)
        self.assertIn("Course step: Optional comparison", printed)
        self.assertIn(
            "Done when: the comparison report, plots, worksheet, and Prediction Check are saved.",
            printed,
        )
        self.assertIn("Playbook: 1. predict the comparison outcome", printed)
        self.assertIn("History: Latest saved_batch", printed)
        self.assertIn("Worksheet: Latest worksheet.md", printed)
        self.assertIn("Plots: Latest error_compare.png", printed)
        self.assertIn("Plot review: Error - Compare traces", printed)
        self.assertIn(
            "Prediction check: Worksheet is digest-published and read-only; copy Matched, "
            "Partly matched, or Surprised into personal/course notes outside the saved-run folder.",
            printed,
        )
        self.assertIn("Handoff: Latest report.html#viewer-handoff", printed)
        self.assertIn("Command: python -m mclab batch lab04_wall_compare --open-report", printed)
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_batch_details_show_course_context_for_all_compare(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["batches", "all", "--details", "--limit", "1"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Comparison Batches - All compare", printed)
        self.assertIn("Course step: 12/12 - Compare the course", printed)
        self.assertIn(
            "Done when: the course comparison report, worksheet, and linked batch Prediction Checks are saved.",
            printed,
        )

    def test_cli_batch_search_handles_empty_matches(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["batches", "not-a-real-batch-token"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Batches: showing 0 of 0 match(es)", printed)
        self.assertIn("No comparison batches matched.", printed)
        self.assertIn(
            "After running: review saved evidence with `python -m mclab review`.", printed
        )
        self.assertIn(
            "All reports: reopen the cumulative browser index with `python -m mclab index --open`.",
            printed,
        )

    def test_cli_batch_handoff_detail_uses_latest_worksheet_viewer_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch"
            output.mkdir()
            (output / "report.html").write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text(
                "\n".join(
                    [
                        "# Batch worksheet",
                        "",
                        "## Viewer Handoff",
                        "",
                        "- Start with: underdamped",
                        "- Viewer rerun: python -m mclab run lab01 --config configs/lab01_msd/underdamped.yaml --viewer --realtime --pause-at-end --plot --plots essential",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_manifest(
                output,
                scenario_id="batch.lab01_msd_compare",
                status="completed",
                config={"batch_name": "lab01_msd_compare", "plot": True},
                run_kind="comparison_batch",
            )
            action = next(
                action for action in BATCH_ACTIONS if action.batch_name == "lab01_msd_compare"
            )

            with patch("mclab.cli.action_latest_output", return_value=output):
                handoff = _batch_handoff_detail_text(action)

        self.assertIn("Handoff: underdamped -> python -m mclab run lab01", handoff)
        self.assertIn("--viewer --realtime --pause-at-end --plot --plots essential", handoff)
        self.assertNotIn("#viewer-handoff", handoff)

    def test_cli_all_batch_handoff_follows_linked_batch_worksheet_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _publish_course_batch_run(
                Path(tmp).resolve() / "all_batches",
            )
            action = next(action for action in BATCH_ACTIONS if action.batch_name == "all")

            with patch("mclab.cli.action_latest_output", return_value=output):
                handoff = _batch_handoff_detail_text(action)

        self.assertIn(
            "Handoff: lab01_msd_compare / underdamped -> python -m mclab run lab01",
            handoff,
        )
        self.assertIn("--viewer --realtime --pause-at-end --plot --plots essential", handoff)
        self.assertNotIn("Open linked batch handoff", handoff)

    def test_cli_opens_batch_report_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "batch"
            output.mkdir()
            all_reports_index = Path(tmp).resolve() / "index.html"
            all_reports_index.write_text("<html></html>", encoding="utf-8")
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text(
                "\n".join(
                    [
                        "# Batch worksheet",
                        "",
                        "## Prediction Check",
                        "",
                        "- Review prompt: Compare your prediction with the plotted evidence.",
                        "",
                        "## Viewer Handoff",
                        "",
                        "- Start with: high damping",
                        "- Why: largest baseline metric change",
                        "- Priority plot: comparison_plots/error_compare.png",
                        "- Viewer rerun: python -m mclab run lab01 --config configs/lab01_msd/over_damped.yaml --viewer --realtime --pause-at-end --plot --plots essential",
                        "- Review prompt: Open this scenario in the side-panel-free viewer before editing another YAML parameter.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "error_compare.png").write_bytes(b"fake-png")
            write_manifest(
                output,
                scenario_id="batch.lab01_msd_compare",
                status="completed",
                config={"batch_name": "lab01_msd_compare", "plot": True},
                run_kind="comparison_batch",
            )

            with (
                patch("mclab.cli.run_batch", return_value=output) as runner,
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(main(["batch", "lab01_msd_compare", "--open-report"]), 0)

            runner.assert_called_once()
            opener.assert_called_once_with(report)
            printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
            self.assertIn(f"Batch complete: {output}", printed)
            self.assertIn(f"Report: {report}", printed)
            self.assertIn(f"Worksheet: {output / 'worksheet.md'}", printed)
            self.assertIn(f"All reports index: {all_reports_index}", printed)
            self.assertIn(
                f"Comparison plots: {output / 'comparison_plots'} (1 PNG; first: error_compare.png)",
                printed,
            )
            self.assertIn(
                f"Priority plot: {output / 'comparison_plots' / 'error_compare.png'}", printed
            )
            self.assertIn(
                "Prediction check: Worksheet is digest-published and read-only; copy outcomes "
                "into personal/course notes outside the saved-run folder.",
                printed,
            )
            self.assertIn(
                "Viewer handoff: high damping -> python -m mclab run lab01 "
                "--config configs/lab01_msd/over_damped.yaml --viewer --realtime --pause-at-end "
                "--plot --plots essential",
                printed,
            )
            self.assertIn(
                "Worksheet review prompt: Compare your prediction with the plotted evidence.",
                printed,
            )

    def test_cli_runs_all_batches_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _publish_course_batch_run(
                Path(tmp).resolve() / "all_batches",
            )
            report = output / "report.html"

            with (
                patch("mclab.cli.run_all_batches", return_value=output) as runner,
                patch("mclab.cli.run_batch") as single_runner,
                patch("mclab.cli._open_path") as opener,
            ):
                self.assertEqual(
                    main(
                        [
                            "batch",
                            "all",
                            "--no-plot",
                            "--open-report",
                            "--handoff-token",
                            "a" * 64,
                        ]
                    ),
                    0,
                )

            runner.assert_called_once()
            self.assertFalse(runner.call_args.kwargs["plot"])
            self.assertEqual(runner.call_args.kwargs["handoff_token"], "a" * 64)
            single_runner.assert_not_called()
            opener.assert_called_once_with(report)

    def test_cli_accepts_viewer_quality_of_life_options(self) -> None:
        default_args = build_parser().parse_args(
            [
                "run",
                "lab04",
                "--config",
                "configs/lab04_panda/joint_pd.yaml",
                "--viewer",
            ]
        )
        self.assertTrue(default_args.viewer)
        self.assertFalse(hasattr(default_args, "show_viewer_ui"))

        args = build_parser().parse_args(
            [
                "run",
                "lab04",
                "--config",
                "configs/lab04_panda/joint_pd.yaml",
                "--viewer",
                "--realtime",
                "--pause-at-end",
                "--plots",
                "essential",
                "--open-report",
            ]
        )
        self.assertTrue(args.viewer)
        self.assertTrue(args.realtime)
        self.assertTrue(args.pause_at_end)
        self.assertEqual(args.plots, "essential")
        self.assertTrue(args.open_report)

        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "run",
                    "lab04",
                    "--config",
                    "configs/lab04_panda/joint_pd.yaml",
                    "--viewer",
                    "--show-viewer-ui",
                ]
            )

    def test_run_help_explains_side_panel_free_viewer(self) -> None:
        output = StringIO()

        with self.assertRaises(SystemExit) as context, redirect_stdout(output):
            build_parser().parse_args(["run", "--help"])

        self.assertEqual(context.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("--viewer", help_text)
        self.assertIn("Open MuJoCo viewer without side panels.", help_text)
        self.assertNotIn("--show-viewer-ui", help_text)

    def test_cli_rejects_conflicting_viewer_modes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "run",
                    "lab04",
                    "--config",
                    "configs/lab04_panda/joint_pd.yaml",
                    "--viewer",
                    "--headless",
                ]
            )

    def test_cli_rejects_viewer_only_flags_without_viewer(self) -> None:
        cases = [
            ["--realtime"],
            ["--pause-at-end"],
            ["--headless", "--realtime"],
            ["--headless", "--pause-at-end"],
        ]
        for extra_args in cases:
            with self.subTest(extra_args=extra_args), patch("mclab.cli.load_config") as loader:
                with self.assertRaises(SystemExit) as context:
                    main(
                        [
                            "run",
                            "lab04",
                            "--config",
                            "configs/lab04_panda/joint_pd.yaml",
                            *extra_args,
                        ]
                    )
                self.assertEqual(context.exception.code, 2)
                loader.assert_not_called()

    def test_cli_rejects_plot_selection_without_plot_flag(self) -> None:
        with patch("mclab.cli.load_config") as loader:
            with self.assertRaises(SystemExit) as context:
                main(
                    [
                        "run",
                        "lab04",
                        "--config",
                        "configs/lab04_panda/joint_pd.yaml",
                        "--plots",
                        "essential",
                    ]
                )
            self.assertEqual(context.exception.code, 2)
            loader.assert_not_called()

    def test_cli_opens_run_report_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "run"
            output.mkdir()
            all_reports_index = Path(tmp).resolve() / "index.html"
            all_reports_index.write_text("<html></html>", encoding="utf-8")
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text(
                (
                    "# Run worksheet\n\n"
                    "## Mission Evidence\n\n"
                    "- Next proof step: Review the priority plot and worksheet, then run Next or Compare.\n\n"
                    "## Plot Review\n\n"
                    "- Priority plot: plots/position.png\n"
                    "- Read first: Position\n"
                    "- What to check: Compare target and actual motion.\n\n"
                    "## Review Checklist\n\n"
                    "- Review prompt: Answer the Prediction prompt before reading the plots.\n\n"
                    "## Course Experience Coverage\n\n"
                    "- Next experience: Hands-on controls\n"
                    "- Next mode: hands-on viewer\n"
                    "- Next action: Run an interactive viewer and use one button, slider, or preset.\n"
                    "- Evidence needed: At least one learner-control event plus one prediction-backed observation marker.\n"
                    "- Next command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                    "--viewer --realtime --pause-at-end --plot --open-report\n"
                ),
                encoding="utf-8",
            )
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"fake-png")
            config_path = "configs/lab01_msd/default.yaml"
            write_manifest(
                output,
                scenario_id=stable_scenario_id("lab01_msd", config_path),
                status="completed",
                config=load_config(config_path),
                config_path=config_path,
            )

            def fake_runner(_config: dict[str, object], **_kwargs: object) -> Path:
                return output

            with (
                patch.dict("mclab.cli.LABS", {"unit_lab": fake_runner}, clear=False),
                patch("mclab.cli.load_config", return_value={"model_path": "demo.xml"}),
                patch("mclab.cli._open_path") as opener,
                patch("builtins.print") as printer,
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "unit_lab",
                            "--config",
                            "configs/lab01_msd/default.yaml",
                            "--open-report",
                        ]
                    ),
                    0,
                )

            opener.assert_called_once_with(report)
            printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
            self.assertIn(f"Run complete: {output}", printed)
            self.assertIn(f"Report: {report}", printed)
            self.assertIn(f"Worksheet: {output / 'worksheet.md'}", printed)
            self.assertIn(f"All reports index: {all_reports_index}", printed)
            self.assertIn(f"Plots: {output / 'plots'} (1 PNG; first: position.png)", printed)
            self.assertIn(f"Priority plot: {output / 'plots' / 'position.png'}", printed)
            self.assertIn("Review focus: Position - Compare target and actual motion.", printed)
            self.assertIn(
                "Next proof step: Review the priority plot and worksheet, then run Next or Compare.",
                printed,
            )
            self.assertIn(
                "Worksheet policy: Saved worksheets are digest-published and read-only; record answers "
                "in personal/course notes outside the saved-run folder.",
                printed,
            )
            self.assertIn(
                "Worksheet review prompt: Answer the Prediction prompt before reading the plots.",
                printed,
            )
            self.assertIn("Next experience: Hands-on controls", printed)
            self.assertIn("Next mode: hands-on viewer", printed)
            self.assertIn(
                "Next action: Run an interactive viewer and use one button, slider, or preset.",
                printed,
            )
            self.assertIn(
                "Evidence needed: At least one learner-control event plus one prediction-backed observation marker.",
                printed,
            )
            self.assertIn(
                "Next command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --open-report",
                printed,
            )


class CleanCommandTests(unittest.TestCase):
    def test_clean_defaults_to_dry_run_and_yes_alone_never_moves_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            run = _write_cleanup_manifest(root, "old-run", minute=0)
            before = _tree_snapshot(root)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--keep", "0"]), 0)
            printed = output.getvalue()
            self.assertIn("Cleanup dry-run", printed)
            self.assertIn(f"QUARANTINE {run}", printed)
            self.assertIn("Plan ID:", printed)
            self.assertTrue(run.exists())

            error = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(StringIO()),
                redirect_stderr(error),
            ):
                self.assertEqual(main(["clean", "--keep", "0", "--yes"]), 2)
            self.assertIn("--yes alone", error.getvalue())
            self.assertTrue(run.exists())
            self.assertEqual(_tree_snapshot(root), before)

    def test_clean_applies_exact_plan_to_quarantine_and_restores_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            old = _write_cleanup_manifest(root, "old-run", minute=0)
            new = _write_cleanup_manifest(root, "new-run", minute=1)
            plan = build_cleanup_plan(root, keep=1, allowed_root=root)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(
                    main(
                        [
                            "clean",
                            "--keep",
                            "1",
                            "--apply",
                            plan.plan_id,
                            "--yes",
                        ]
                    ),
                    0,
                )
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            receipt_line = next(
                line for line in output.getvalue().splitlines() if line.startswith("Receipt: ")
            )
            receipt_id = receipt_line.removeprefix("Receipt: ")

            with patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}):
                self.assertEqual(main(["clean", "--restore", receipt_id]), 0)
            self.assertTrue(old.exists())
            self.assertTrue(new.exists())

    def test_clean_rejects_arbitrary_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            configured = data_root / "outputs"
            configured.mkdir(parents=True)
            other = Path(tmp).resolve() / "other" / "outputs"
            other.mkdir(parents=True)
            run = _write_cleanup_manifest(other, "canary", minute=0)
            before = _tree_snapshot(other)
            error = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stderr(error),
            ):
                self.assertEqual(
                    main(["clean", "--output-dir", str(other), "--keep", "0", "--yes"]),
                    2,
                )
            self.assertIn("configured outputs root", error.getvalue())
            self.assertTrue(run.exists())
            self.assertEqual(_tree_snapshot(other), before)

    def test_clean_missing_dir_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean"]), 0)
            self.assertIn("does not exist", output.getvalue())

    def test_clean_rejects_wrong_plan_even_when_nothing_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            error = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stderr(error),
            ):
                self.assertEqual(
                    main(["clean", "--apply", "0" * 64, "--yes"]),
                    2,
                )
            self.assertIn("plan ID", error.getvalue())
            self.assertFalse((root / ".mclab-trash").exists())

    def test_clean_apply_without_yes_is_a_byte_for_byte_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            _write_cleanup_manifest(root, "old-run", minute=0)
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            before = _tree_snapshot(root)
            error = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(StringIO()),
                redirect_stderr(error),
            ):
                self.assertEqual(
                    main(["clean", "--keep", "0", "--apply", plan.plan_id]),
                    2,
                )
            self.assertIn("requires --yes", error.getvalue())
            self.assertEqual(_tree_snapshot(root), before)

    def test_clean_json_plan_list_and_restore_are_machine_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            run = _write_cleanup_manifest(root, "old-run", minute=0)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--keep", "0", "--json"]), 0)
            plan_payload = json.loads(output.getvalue())
            self.assertEqual(plan_payload["schema_version"], 1)
            self.assertEqual([item["name"] for item in plan_payload["selected"]], [run.name])

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(
                    main(
                        [
                            "clean",
                            "--keep",
                            "0",
                            "--apply",
                            plan_payload["plan_id"],
                            "--yes",
                            "--json",
                        ]
                    ),
                    0,
                )
            receipt_payload = json.loads(output.getvalue())
            self.assertEqual(receipt_payload["status"], "quarantined")
            self.assertIs(receipt_payload["recoverable"], True)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--list-trash", "--json"]), 0)
            listed = json.loads(output.getvalue())
            self.assertEqual(
                [item["receipt_id"] for item in listed], [receipt_payload["receipt_id"]]
            )
            self.assertIs(listed[0]["recoverable"], True)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--list-trash"]), 0)
            self.assertIn("| restorable |", output.getvalue())

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(
                    main(
                        [
                            "clean",
                            "--restore",
                            receipt_payload["receipt_id"],
                            "--json",
                        ]
                    ),
                    0,
                )
            restored = json.loads(output.getvalue())
            self.assertEqual(restored["status"], "restored")
            self.assertIs(restored["recoverable"], False)
            self.assertTrue(run.is_dir())

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--list-trash", "--json"]), 0)
            history = json.loads(output.getvalue())
            self.assertEqual(history[0]["status"], "restored")
            self.assertIs(history[0]["recoverable"], False)

            output = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                redirect_stdout(output),
            ):
                self.assertEqual(main(["clean", "--list-trash"]), 0)
            self.assertIn("| history-only |", output.getvalue())

    def test_clean_operation_failure_returns_one_and_preserves_the_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp).resolve() / "data"
            root = data_root / "outputs"
            root.mkdir(parents=True)
            _write_cleanup_manifest(root, "old-run", minute=0)
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            before = _tree_snapshot(root)
            error = StringIO()
            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                patch(
                    "mclab.cli.quarantine_cleanup_plan",
                    side_effect=CleanupOperationError("injected operation failure"),
                ),
                redirect_stdout(StringIO()),
                redirect_stderr(error),
            ):
                self.assertEqual(
                    main(
                        [
                            "clean",
                            "--keep",
                            "0",
                            "--apply",
                            plan.plan_id,
                            "--yes",
                        ]
                    ),
                    1,
                )
            self.assertIn("operation failed", error.getvalue())
            self.assertEqual(_tree_snapshot(root), before)


def _write_cleanup_manifest(root: Path, name: str, *, minute: int) -> Path:
    run = root / name
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenario_id": "lab01.default",
                "status": "completed",
                "started_at": f"2026-07-20T12:{minute:02d}:00+00:00",
                "finished_at": f"2026-07-20T12:{minute:02d}:30+00:00",
                "config": {"resolved": {"sim_time": 1.0}},
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    return run


def _tree_snapshot(root: Path) -> tuple[tuple[str, str, bytes], ...]:
    rows: list[tuple[str, str, bytes]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append((relative, "link", os.readlink(path).encode()))
        elif path.is_dir():
            rows.append((relative, "dir", b""))
        else:
            rows.append((relative, "file", path.read_bytes()))
    return tuple(rows)
