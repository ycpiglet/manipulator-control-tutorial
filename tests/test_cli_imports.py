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

    def test_cli_opens_batch_report_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            output.mkdir()
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")

            with (
                patch("mclab.cli.run_batch", return_value=output) as runner,
                patch("mclab.cli._open_path") as opener,
            ):
                self.assertEqual(main(["batch", "lab01_msd_compare", "--open-report"]), 0)

            runner.assert_called_once()
            opener.assert_called_once_with(report)

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
            report = output / "report.html"
            report.write_text("<html></html>", encoding="utf-8")

            def fake_runner(_config: dict[str, object], **_kwargs: object) -> Path:
                return output

            with (
                patch.dict("mclab.cli.LABS", {"unit_lab": fake_runner}, clear=False),
                patch("mclab.cli.load_config", return_value={"model_path": "demo.xml"}),
                patch("mclab.cli._open_path") as opener,
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
