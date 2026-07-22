from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import bootstrap_and_run, start_mclab  # noqa: E402
from scripts.bootstrap_and_run import verify_output_artifacts  # noqa: E402


class BootstrapVerifyTests(unittest.TestCase):
    def test_bootstrap_refuses_linked_venv_before_running_commands(self) -> None:
        with (
            patch.object(bootstrap_and_run, "VENV", Path("/project/.venv")),
            patch.object(bootstrap_and_run, "VENV_PYTHON", Path("/project/.venv/bin/python")),
            patch.object(
                bootstrap_and_run,
                "project_venv_redirect_error",
                return_value="lib is a link or reparse point",
            ),
            patch.object(bootstrap_and_run, "run") as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "unsafe project environment"):
                bootstrap_and_run.ensure_venv()

        run.assert_not_called()

    def test_bootstrap_refuses_incomplete_venv_before_running_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            venv.mkdir()
            with (
                patch.object(bootstrap_and_run, "VENV", venv),
                patch.object(bootstrap_and_run, "VENV_PYTHON", venv / "bin/python"),
                patch.object(bootstrap_and_run, "run") as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "incomplete project environment"):
                    bootstrap_and_run.ensure_venv()

            run.assert_not_called()

    def test_app_bootstrap_refuses_incomplete_venv_before_running_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            venv.mkdir()
            with (
                patch.object(start_mclab, "VENV", venv),
                patch.object(start_mclab, "VENV_PYTHON", venv / "bin/python"),
                patch.object(start_mclab, "_run") as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "incomplete project environment"):
                    start_mclab._ensure_venv()

            run.assert_not_called()

    def test_bootstrap_checks_full_platform_support_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            with (
                patch.object(bootstrap_and_run, "VENV", venv),
                patch.object(bootstrap_and_run, "VENV_PYTHON", venv / "bin/python"),
                patch.object(
                    bootstrap_and_run,
                    "support_error",
                    return_value="unsupported platform",
                ) as support,
                patch.object(bootstrap_and_run, "run") as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "unsupported platform"):
                    bootstrap_and_run.ensure_venv("dev")

            support.assert_called_once_with("dev")
            run.assert_not_called()

    def test_app_bootstrap_reuses_existing_venv_without_host_support_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            python = venv / "bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
            with (
                patch.object(start_mclab, "VENV", venv),
                patch.object(start_mclab, "VENV_PYTHON", python),
                patch.object(start_mclab, "support_error") as support,
                patch.object(start_mclab, "_run") as run,
            ):
                start_mclab._ensure_venv()

            support.assert_not_called()
            run.assert_not_called()

    def test_setup_only_reconciles_the_runtime_profile(self) -> None:
        with (
            patch.object(sys, "argv", ["bootstrap_and_run.py", "--setup-only"]),
            patch.object(bootstrap_and_run, "ensure_venv") as ensure_venv,
            patch.object(bootstrap_and_run, "ensure_dependencies") as ensure_dependencies,
            patch.object(bootstrap_and_run, "ensure_menagerie"),
        ):
            self.assertEqual(bootstrap_and_run.main(), 0)

        ensure_venv.assert_called_once_with("runtime")
        ensure_dependencies.assert_called_once_with("runtime")

    def test_skip_tests_reconciles_runtime_while_tested_runs_use_dev(self) -> None:
        for arguments, expected_profile in ((["--skip-tests", "--no-plot"], "runtime"), ([], "dev")):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as tmp:
                with (
                    patch.object(sys, "argv", ["bootstrap_and_run.py", *arguments]),
                    patch.object(bootstrap_and_run, "ROOT", Path(tmp)),
                    patch.object(bootstrap_and_run, "ensure_venv") as ensure_venv,
                    patch.object(
                        bootstrap_and_run, "ensure_dependencies"
                    ) as ensure_dependencies,
                    patch.object(bootstrap_and_run, "ensure_menagerie"),
                    patch.object(bootstrap_and_run, "run"),
                    patch.object(bootstrap_and_run, "verify_output_artifacts"),
                ):
                    self.assertEqual(bootstrap_and_run.main(), 0)

                ensure_venv.assert_called_once_with(expected_profile)
                ensure_dependencies.assert_called_once_with(expected_profile)

    def test_dependency_reconciliation_uses_only_the_locked_installer(self) -> None:
        with patch.object(bootstrap_and_run, "run") as run:
            bootstrap_and_run.ensure_dependencies("dev")

        command = run.call_args.args[0]
        self.assertEqual(command[-2:], [str(ROOT / "scripts" / "install_locked.py"), "dev"])
        source = (ROOT / "scripts/bootstrap_and_run.py").read_text(encoding="utf-8")
        self.assertNotIn('"pip", "install"', source)
        self.assertNotIn('"--upgrade"', source)

    def test_menagerie_setup_delegates_only_to_the_pinned_asset_installer(self) -> None:
        python = Path("/project/.venv/bin/python")
        with (
            patch.object(bootstrap_and_run, "VENV_PYTHON", python),
            patch.object(bootstrap_and_run, "run") as run,
        ):
            bootstrap_and_run.ensure_menagerie()

        run.assert_called_once_with(
            [str(python), "-m", "mclab", "assets", "install"]
        )
        source = (ROOT / "scripts/bootstrap_and_run.py").read_text(encoding="utf-8")
        self.assertNotIn("mujoco_menagerie.git", source)
        self.assertNotIn("sparse-checkout", source)
        self.assertNotIn('"git", "clone"', source)

    def test_verify_output_artifacts_accepts_complete_plotted_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=True)

            verify_output_artifacts(output, expect_plots=True)

    def test_verify_output_artifacts_allows_no_plot_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=False)

            verify_output_artifacts(output, expect_plots=False)

    def test_verify_output_artifacts_reports_missing_report_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=True)
            (output / "report.html").write_text("<html><body>Summary</body></html>", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Config Highlights"):
                verify_output_artifacts(output, expect_plots=True)

    def test_verify_output_artifacts_reports_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=True)
            (output / "summary.json").unlink()

            with self.assertRaisesRegex(RuntimeError, "summary.json"):
                verify_output_artifacts(output, expect_plots=True)

    def test_verify_output_artifacts_requires_readme_core_evidence(self) -> None:
        for filename in ("states.npz", "replay.npz", "manifest.json", "worksheet.md"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "run"
                _write_output(output, with_plot=True)
                (output / filename).unlink()

                with self.assertRaisesRegex(RuntimeError, filename.replace(".", r"\.")):
                    verify_output_artifacts(output, expect_plots=True)

    def test_verify_output_artifacts_rejects_directory_in_place_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=True)
            (output / "states.npz").unlink()
            (output / "states.npz").mkdir()

            with self.assertRaisesRegex(RuntimeError, r"states\.npz"):
                verify_output_artifacts(output, expect_plots=True)

    def test_verify_output_artifacts_rejects_png_named_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            _write_output(output, with_plot=True)
            plot = output / "plots" / "position.png"
            plot.unlink()
            plot.mkdir()

            with self.assertRaisesRegex(RuntimeError, r"plots/\*\.png"):
                verify_output_artifacts(output, expect_plots=True)


def _write_output(output: Path, *, with_plot: bool) -> None:
    output.mkdir(parents=True)
    (output / "config.yaml").write_text("sim_time: 0.02\n", encoding="utf-8")
    (output / "summary.json").write_text('{"lab_name": "lab01_msd"}', encoding="utf-8")
    (output / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (output / "log.csv").write_text("time,position\n0.0,0.0\n", encoding="utf-8")
    (output / "states.npz").write_bytes(b"fake-states")
    (output / "replay.npz").write_bytes(b"fake-replay")
    (output / "manifest.json").write_text('{"status": "completed"}', encoding="utf-8")
    (output / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
    report_sections = [
        "Reproduce This Run",
        "Suggested Next Runs",
        "Config Highlights",
        "Result Check",
        "Summary",
        "Files",
    ]
    if with_plot:
        plot_dir = output / "plots"
        plot_dir.mkdir()
        (plot_dir / "position.png").write_bytes(b"fake-png")
        report_sections.extend(["Plots", "Plot Guide"])
    (output / "report.html").write_text(
        "<html><body>" + "\n".join(report_sections) + "</body></html>",
        encoding="utf-8",
    )
