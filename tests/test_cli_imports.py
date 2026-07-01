from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.batch import BATCH_SETS  # noqa: E402
from mclab.cli import LABS, main  # noqa: E402
from mclab.cli import build_parser  # noqa: E402
from mclab.doctor import DoctorCheck  # noqa: E402


class CliImportTests(unittest.TestCase):
    def test_cli_lists_labs(self) -> None:
        self.assertIn("lab01", LABS)
        self.assertIn("lab02", LABS)
        self.assertIn("lab03", LABS)
        self.assertIn("lab04", LABS)
        self.assertEqual(main(["list"]), 0)
        self.assertIn("lab01_msd_compare", BATCH_SETS)
        self.assertIn("lab02_pid_compare", BATCH_SETS)

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

    def test_cli_runs_doctor_check(self) -> None:
        args = build_parser().parse_args(["doctor"])
        self.assertEqual(args.command, "doctor")

        with (
            patch("mclab.cli.run_doctor_checks", return_value=[DoctorCheck("Python", "OK", "ready")]),
            patch("builtins.print") as printer,
        ):
            self.assertEqual(main(["doctor"]), 0)

        printed = str(printer.call_args.args[0])
        self.assertIn("MCLab Doctor", printed)
        self.assertIn("[OK] Python", printed)

    def test_cli_generates_outputs_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"
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
            output_dir = Path(tmp) / "outputs"

            args = build_parser().parse_args(["coverage", "--output-dir", str(output_dir)])
            self.assertEqual(args.command, "coverage")
            self.assertEqual(args.output_dir, str(output_dir))

            with patch("builtins.print") as printer:
                self.assertEqual(main(["coverage", "--output-dir", str(output_dir)]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Experience coverage: 0/7 types tried", printed)
        self.assertIn("Coverage map: Intro basics: Next", printed)
        self.assertIn("Next experience: Intro basics", printed)
        self.assertIn(
            "Next command: python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
            "--headless --plot --open-report",
            printed,
        )

    def test_cli_prints_learning_path_progress_and_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"

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
            "--viewer --realtime --pause-at-end --plot --plots essential --open-report",
            printed,
        )
        self.assertIn("Path map:", printed)
        self.assertIn("1. Feel 1D physics: Not run yet", printed)

    def test_cli_previews_next_learning_path_step_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"

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
        self.assertIn("Next command: python -m mclab run lab01", printed)
        self.assertNotIn("Running next step:", printed)

    def test_cli_runs_next_learning_path_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"
            output = Path(tmp) / "next_run"
            output.mkdir()
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            (output / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"fake-png")
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
        self.assertTrue(calls[0]["viewer"])
        self.assertFalse(calls[0]["headless"])
        self.assertTrue(calls[0]["realtime"])
        self.assertTrue(calls[0]["pause_at_end"])
        self.assertTrue(calls[0]["plot"])
        self.assertEqual(calls[0]["plot_selection"], "essential")
        self.assertEqual(calls[0]["seed"], 11)
        opener.assert_called_once_with(report)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Running next step: Lab01 Mass-Spring-Damper - Auto demo", printed)
        self.assertIn(f"Run complete: {output}", printed)
        self.assertIn(f"Plots: {output / 'plots'} (1 PNG; first: position.png)", printed)

    def test_cli_prints_review_queue_and_next_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            run_path = outputs / "run_lab01_interactive"
            run_path.mkdir(parents=True)
            report = run_path / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            worksheet = run_path / "worksheet.md"
            worksheet.write_text("# Worksheet\n", encoding="utf-8")
            (run_path / "summary.json").write_text(
                (
                    '{"lab_name": "lab01_msd", "config_path": '
                    '"configs/lab01_msd/interactive_pull.yaml", "config_name": "interactive_pull"}'
                ),
                encoding="utf-8",
            )

            args = build_parser().parse_args(["review", "--output-dir", str(outputs), "--open"])
            self.assertEqual(args.command, "review")
            self.assertEqual(args.output_dir, str(outputs))
            self.assertTrue(args.open)

            with patch("mclab.cli._open_path") as opener, patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs), "--open"]), 0)

        opener.assert_called_once_with(report)
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Review queue: 0 ready, 1 pending", printed)
        self.assertIn("Next review: run_lab01_interactive - Needs observation.", printed)
        self.assertIn(f"Next review folder: {run_path}", printed)
        self.assertIn("Next review status: Needs observation", printed)
        self.assertIn(f"Next review report: {report}", printed)
        self.assertIn(f"Next review worksheet: {worksheet}", printed)

    def test_cli_review_handles_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            with patch("mclab.cli._open_path") as opener, patch("builtins.print") as printer:
                self.assertEqual(main(["review", "--output-dir", str(outputs), "--open"]), 0)

        opener.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Review queue: No saved runs yet. Run a scenario first.", printed)
        self.assertIn("Next review: none", printed)

    def test_cli_searches_guided_scenarios(self) -> None:
        args = build_parser().parse_args(["scenarios", "virtual", "wall", "--filter", "wall", "--limit", "0"])
        self.assertEqual(args.command, "scenarios")
        self.assertEqual(args.query, ["virtual", "wall"])
        self.assertEqual(args.filter, "wall")
        self.assertEqual(args.limit, 0)

        with patch("builtins.print") as printer:
            self.assertEqual(
                main(["scenarios", "virtual", "wall", "--filter", "wall", "--limit", "0", "--details"]),
                0,
            )

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Scenarios: showing", printed)
        self.assertIn("Lab04 Panda Manipulator - Virtual wall", printed)
        self.assertIn("Challenge:", printed)
        self.assertIn("Playbook:", printed)
        self.assertIn("Controls:", printed)
        self.assertIn("Counts as control:", printed)
        self.assertIn("Viewer: MuJoCo side panels are hidden", printed)
        self.assertIn("Red plane = Virtual wall location.", printed)
        self.assertIn("Setup: Ready", printed)
        self.assertIn(
            "Command: python -m mclab run lab04 --config configs/lab04_panda/interactive_virtual_wall.yaml "
            "--viewer --realtime --pause-at-end --plot --plots wall --open-report",
            printed,
        )

    def test_cli_scenario_search_handles_empty_matches(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["scenarios", "not-a-real-scenario-token"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Scenarios: showing 0 of 0 match(es)", printed)
        self.assertIn("No guided scenarios matched.", printed)

    def test_cli_searches_comparison_batches(self) -> None:
        args = build_parser().parse_args(["batches", "wall", "--limit", "0", "--details"])
        self.assertEqual(args.command, "batches")
        self.assertEqual(args.query, ["wall"])
        self.assertEqual(args.limit, 0)
        self.assertTrue(args.details)

        with patch("builtins.print") as printer:
            self.assertEqual(main(["batches", "wall", "--limit", "0", "--details"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Batches: showing", printed)
        self.assertIn("Comparison Batches - Lab04 wall compare", printed)
        self.assertIn("Mission: Run", printed)
        self.assertIn("Setup: Ready", printed)
        self.assertIn("Command: python -m mclab batch lab04_wall_compare --open-report", printed)

    def test_cli_batch_search_handles_empty_matches(self) -> None:
        with patch("builtins.print") as printer:
            self.assertEqual(main(["batches", "not-a-real-batch-token"]), 0)

        printed = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Batches: showing 0 of 0 match(es)", printed)
        self.assertIn("No comparison batches matched.", printed)

    def test_cli_opens_batch_report_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            output.mkdir()
            all_reports_index = Path(tmp) / "index.html"
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
                        "- Use this after writing a prediction: mark each item as Matched, Partly matched, or Surprised.",
                        "",
                        "## Viewer Handoff",
                        "",
                        "- Start with: high damping",
                        "- Why: largest baseline metric change",
                        "- Priority plot: comparison_plots/error_compare.png",
                        "- Viewer rerun: python -m mclab run lab01 --config configs/lab01_msd/over_damped.yaml --viewer --realtime --pause-at-end --plot --plots essential",
                        "- [ ] Open this scenario in the side-panel-free viewer before editing another YAML parameter.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "error_compare.png").write_bytes(b"fake-png")

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
            self.assertIn(f"Comparison plots: {output / 'comparison_plots'} (1 PNG; first: error_compare.png)", printed)
            self.assertIn(f"Priority plot: {output / 'comparison_plots' / 'error_compare.png'}", printed)
            self.assertIn(
                "Prediction check: Mark Matched, Partly matched, or Surprised in worksheet.md.",
                printed,
            )
            self.assertIn(
                "Viewer handoff: high damping -> python -m mclab run lab01 "
                "--config configs/lab01_msd/over_damped.yaml --viewer --realtime --pause-at-end "
                "--plot --plots essential",
                printed,
            )
            self.assertIn(
                "Review checklist: Open this scenario in the side-panel-free viewer before editing another YAML parameter.",
                printed,
            )

    def test_cli_runs_all_batches_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "all_batches"
            output.mkdir()
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")

            with (
                patch("mclab.cli.run_all_batches", return_value=output) as runner,
                patch("mclab.cli.run_batch") as single_runner,
                patch("mclab.cli._open_path") as opener,
            ):
                self.assertEqual(main(["batch", "all", "--no-plot", "--open-report"]), 0)

            runner.assert_called_once()
            self.assertFalse(runner.call_args.kwargs["plot"])
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
            output = Path(tmp) / "run"
            output.mkdir()
            all_reports_index = Path(tmp) / "index.html"
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
                    "- [ ] Answer the Prediction prompt before reading the plots.\n\n"
                    "## Course Experience Coverage\n\n"
                    "- Next experience: Hands-on controls\n"
                    "- Next command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                    "--viewer --realtime --pause-at-end --plot --open-report\n"
                ),
                encoding="utf-8",
            )
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"fake-png")

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
            self.assertIn("Next proof step: Review the priority plot and worksheet, then run Next or Compare.", printed)
            self.assertIn("Review checklist: Answer the Prediction prompt before reading the plots.", printed)
            self.assertIn("Next experience: Hands-on controls", printed)
            self.assertIn(
                "Next command: python -m mclab run lab01 --config configs/lab01_msd/interactive_pull.yaml "
                "--viewer --realtime --pause-at-end --plot --open-report",
                printed,
            )
