from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.bootstrap_and_run import verify_output_artifacts  # noqa: E402


class BootstrapVerifyTests(unittest.TestCase):
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


def _write_output(output: Path, *, with_plot: bool) -> None:
    output.mkdir(parents=True)
    (output / "config.yaml").write_text("sim_time: 0.02\n", encoding="utf-8")
    (output / "summary.json").write_text('{"lab_name": "lab01_msd"}', encoding="utf-8")
    (output / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (output / "log.csv").write_text("time,position\n0.0,0.0\n", encoding="utf-8")
    (output / "states.json").write_text("[]", encoding="utf-8")
    report_sections = [
        "Reproduce This Run",
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
