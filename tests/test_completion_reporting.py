from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mclab.application.artifacts import write_manifest
from mclab.application.catalog import (
    CONCRETE_BATCH_NAMES,
    CONCRETE_BATCH_TARGET_IDS,
    stable_scenario_id,
)
from mclab.batch import BatchScenario, write_all_batches_report, write_batch_report
from mclab.completion import CompletionReason
from mclab.sim.reporting import (
    INDEX_LEARNING_PATH,
    _discover_runs,
    _experience_coverage_records_for_index,
    _learning_path_item,
    write_outputs_index,
    write_run_report,
)


class CompletionReportingTests(unittest.TestCase):
    def test_run_report_and_worksheet_publish_same_explicit_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            output.mkdir()
            self._write_scenario_inputs(output, plot=True)
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="running",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )

            report = write_run_report(
                output,
                update_index=False,
                completion_status="completed",
            )
            html = report.read_text(encoding="utf-8")
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")

        for text in (html, worksheet):
            self.assertIn("Completion verdict:", text)
            self.assertIn("Complete", text)
            self.assertIn("Completion contract version:", text)
            self.assertIn(CompletionReason.COMPLETE.value, text)
            self.assertIn("Experience coverage: 1/7 types tried", text)

    def test_incomplete_run_never_advertises_ready_mission_or_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            output.mkdir()
            self._write_scenario_inputs(output, plot=True)
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="running",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )

            html = write_run_report(
                output,
                update_index=False,
                completion_status="error",
            ).read_text(encoding="utf-8")
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")

        for text in (html, worksheet):
            self.assertIn(CompletionReason.RUN_NOT_COMPLETED.value, text)
            self.assertIn("Run not completed", text)
            self.assertNotIn("Artifacts ready", text)
            self.assertNotIn("Ready to review", text)

    def test_png_named_directory_never_gains_embedded_or_final_plot_credit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "run"
            output.mkdir()
            self._write_scenario_inputs(output, plot=False)
            (output / "plots").mkdir()
            (output / "plots" / "fake.png").mkdir()
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="running",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )

            html = write_run_report(
                output,
                update_index=False,
                completion_status="completed",
            ).read_text(encoding="utf-8")
            write_manifest(
                output,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )
            final_decision = _discover_runs(root)[0]["completion_decision"]

        self.assertIn(CompletionReason.PLOT_MISSING.value, html)
        self.assertEqual(final_decision.primary_reason, CompletionReason.PLOT_MISSING)

    def test_manual_report_regeneration_refuses_future_terminal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "future"
            output.mkdir()
            self._write_scenario_inputs(output, plot=True)
            manifest = write_manifest(
                output,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            before = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }

            with self.assertRaisesRegex(RuntimeError, "terminal or unsafe"):
                write_run_report(output, update_index=False)
            after = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }

        self.assertEqual(after, before)

    def test_concrete_batch_report_and_worksheet_share_prospective_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            complete = root / "complete"
            complete.mkdir()
            (complete / "comparison_plots").mkdir()
            (complete / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            scenarios = self._write_batch_scenarios(complete)
            write_manifest(
                complete,
                scenario_id=CONCRETE_BATCH_TARGET_IDS[0],
                status="running",
                config={"batch_name": CONCRETE_BATCH_NAMES[0], "plot": True},
            )
            complete_report = write_batch_report(
                complete,
                CONCRETE_BATCH_NAMES[0],
                scenarios,
            ).read_text(encoding="utf-8")
            complete_worksheet = (complete / "worksheet.md").read_text(encoding="utf-8")

            incomplete = root / "incomplete"
            incomplete.mkdir()
            incomplete_scenarios = self._write_batch_scenarios(incomplete)
            write_manifest(
                incomplete,
                scenario_id=CONCRETE_BATCH_TARGET_IDS[0],
                status="running",
                config={"batch_name": CONCRETE_BATCH_NAMES[0], "plot": True},
            )
            incomplete_report = write_batch_report(
                incomplete,
                CONCRETE_BATCH_NAMES[0],
                incomplete_scenarios,
            ).read_text(encoding="utf-8")
            incomplete_worksheet = (incomplete / "worksheet.md").read_text(encoding="utf-8")

        for text in (complete_report, complete_worksheet):
            self.assertIn("Completion verdict:", text)
            self.assertIn("Complete", text)
            self.assertIn(CompletionReason.COMPLETE.value, text)
        for text in (incomplete_report, incomplete_worksheet):
            self.assertIn("Completion verdict:", text)
            self.assertIn("Incomplete", text)
            self.assertIn(CompletionReason.PLOT_MISSING.value, text)

    def test_batch_without_prediction_metrics_has_matching_incomplete_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "batch"
            output.mkdir()
            (output / "comparison_plots").mkdir()
            (output / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            scenarios = self._write_batch_scenarios(
                output,
                include_prediction_metrics=False,
            )
            write_manifest(
                output,
                scenario_id=CONCRETE_BATCH_TARGET_IDS[0],
                status="running",
                config={"batch_name": CONCRETE_BATCH_NAMES[0], "plot": True},
            )

            html = write_batch_report(
                output,
                CONCRETE_BATCH_NAMES[0],
                scenarios,
            ).read_text(encoding="utf-8")
            worksheet = (output / "worksheet.md").read_text(encoding="utf-8")
            write_manifest(
                output,
                scenario_id=CONCRETE_BATCH_TARGET_IDS[0],
                status="completed",
                config={"batch_name": CONCRETE_BATCH_NAMES[0], "plot": True},
            )
            final_decision = _discover_runs(root)[0]["completion_decision"]

        for text in (html, worksheet):
            self.assertIn(CompletionReason.REQUIRED_ARTIFACT_MISSING.value, text)
        self.assertEqual(
            final_decision.primary_reason,
            CompletionReason.REQUIRED_ARTIFACT_MISSING,
        )

    def test_course_batch_report_and_worksheet_require_all_trusted_children(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = self._write_complete_child_batches(root)
            write_manifest(
                root,
                scenario_id="batch.all",
                status="running",
                config={"batch_name": "all", "plot": True},
            )
            report = write_all_batches_report(root, completed).read_text(encoding="utf-8")
            worksheet = (root / "worksheet.md").read_text(encoding="utf-8")

            damaged = root / CONCRETE_BATCH_NAMES[0] / "report.html"
            damaged.write_text("<html>tampered</html>", encoding="utf-8")
            damaged_report = write_all_batches_report(root, completed).read_text(encoding="utf-8")
            damaged_worksheet = (root / "worksheet.md").read_text(encoding="utf-8")

        for text in (report, worksheet):
            self.assertIn("Completion verdict:", text)
            self.assertIn("Complete", text)
            self.assertIn(CompletionReason.COMPLETE.value, text)
        for text in (damaged_report, damaged_worksheet):
            self.assertIn("Completion verdict:", text)
            self.assertIn("Incomplete", text)
            self.assertIn(CompletionReason.REQUIRED_ARTIFACT_MISSING.value, text)

    def test_index_challenge_cue_fails_closed_after_course_child_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outputs = Path(temporary) / "outputs"
            outputs.mkdir()
            course = outputs / "course"
            course.mkdir()
            completed = self._write_complete_child_batches(course)
            write_manifest(
                course,
                scenario_id="batch.all",
                status="running",
                config={"batch_name": "all", "plot": True},
            )
            write_all_batches_report(course, completed)
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )
            (course / CONCRETE_BATCH_NAMES[0] / "report.html").write_text(
                "<html>tampered</html>",
                encoding="utf-8",
            )

            html = write_outputs_index(outputs).read_text(encoding="utf-8")

        self.assertIn("Challenge evidence: Needs required artifact", html)
        self.assertNotIn("Challenge evidence: Ready to review", html)

    def test_index_keeps_historical_credit_and_latest_incomplete_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older = root / "older-complete"
            older.mkdir()
            self._write_scenario_inputs(older, plot=True)
            write_manifest(
                older,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
                started_at="2026-07-21T00:00:00+00:00",
                finished_at="2026-07-21T00:01:00+00:00",
            )

            newer = root / "newer-incomplete"
            newer.mkdir()
            self._write_scenario_inputs(newer, plot=False)
            write_manifest(
                newer,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
                started_at="2026-07-21T01:00:00+00:00",
                finished_at="2026-07-21T01:01:00+00:00",
            )

            runs = _discover_runs(root)
            item = _learning_path_item(INDEX_LEARNING_PATH[0], runs)
            coverage = _experience_coverage_records_for_index(runs)
            html = write_outputs_index(root).read_text(encoding="utf-8")

        self.assertEqual(item["run"]["name"], "newer-incomplete")
        self.assertTrue(item["completed"])
        self.assertEqual(
            item["run"]["completion_decision"].primary_reason,
            CompletionReason.PLOT_MISSING,
        )
        self.assertEqual(len(coverage), 1)
        self.assertIn("Historical credit", html)
        self.assertIn("older-complete", html)
        self.assertIn("newer-incomplete", html)
        self.assertIn("completion.v1.plot_missing", html)
        self.assertIn("1/12 steps complete", html)

    def test_index_ignores_unpublished_plot_and_reports_legacy_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unpublished = root / "unpublished"
            unpublished.mkdir()
            self._write_scenario_inputs(unpublished, plot=False)
            write_manifest(
                unpublished,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
                config_path="configs/lab01_msd/default.yaml",
            )
            (unpublished / "plots").mkdir()
            (unpublished / "plots" / "late.png").write_bytes(b"not published")

            legacy = root / "legacy"
            legacy.mkdir()
            (legacy / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "lab01_msd",
                        "config_name": "default",
                        "config_path": "configs/lab01_msd/default.yaml",
                    }
                ),
                encoding="utf-8",
            )
            (legacy / "plots").mkdir()
            (legacy / "plots" / "position.png").write_bytes(b"legacy plot")

            runs = {run["name"]: run for run in _discover_runs(root)}

        self.assertEqual(runs["unpublished"]["plots"], [])
        self.assertEqual(
            runs["unpublished"]["completion_decision"].primary_reason,
            CompletionReason.PLOT_MISSING,
        )
        self.assertEqual(
            runs["legacy"]["completion_decision"].primary_reason,
            CompletionReason.LEGACY_MANIFEST_MISSING,
        )

    @staticmethod
    def _write_scenario_inputs(output: Path, *, plot: bool) -> None:
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "lab_name": "lab01_msd",
                    "config_name": "default",
                    "config_path": "configs/lab01_msd/default.yaml",
                    "duration": 1.0,
                    "samples": 10,
                }
            ),
            encoding="utf-8",
        )
        (output / "config.yaml").write_text("sim_time: 1.0\n", encoding="utf-8")
        (output / "notes.md").write_text("# Notes\n", encoding="utf-8")
        (output / "report.html").write_text("<html>report</html>", encoding="utf-8")
        (output / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
        if plot:
            (output / "plots").mkdir()
            (output / "plots" / "position.png").write_bytes(b"plot")

    @staticmethod
    def _write_complete_child_batches(root: Path) -> list[dict[str, object]]:
        completed: list[dict[str, object]] = []
        for batch_name, target_id in zip(
            CONCRETE_BATCH_NAMES,
            CONCRETE_BATCH_TARGET_IDS,
            strict=True,
        ):
            child = root / batch_name
            child.mkdir()
            (child / "comparison_plots").mkdir()
            (child / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            (child / "worksheet.md").write_text(
                "# Worksheet\n\n## Prediction Check\n",
                encoding="utf-8",
            )
            (child / "report.html").write_text("<html>report</html>", encoding="utf-8")
            write_manifest(
                child,
                scenario_id=target_id,
                status="completed",
                config={"batch_name": batch_name, "plot": True},
            )
            completed.append(
                {
                    "batch_name": batch_name,
                    "title": batch_name,
                    "scenario_count": 1,
                    "report": f"{batch_name}/report.html",
                    "output_path": str(child),
                }
            )
        return completed

    @staticmethod
    def _write_batch_scenarios(
        output: Path,
        *,
        include_prediction_metrics: bool = True,
    ) -> tuple[BatchScenario, ...]:
        scenarios = (
            BatchScenario(
                "baseline",
                "lab01",
                "configs/lab01_msd/default.yaml",
            ),
            BatchScenario(
                "underdamped",
                "lab01",
                "configs/lab01_msd/underdamped.yaml",
            ),
        )
        for index, scenario in enumerate(scenarios):
            child = output / scenario.label
            child.mkdir()
            summary = (
                {"overshoot_percent": float(index * 10)}
                if include_prediction_metrics
                else {"duration": 1.0}
            )
            (child / "summary.json").write_text(
                json.dumps(summary),
                encoding="utf-8",
            )
            (child / "report.html").write_text("<html>report</html>", encoding="utf-8")
            write_manifest(
                child,
                scenario_id=stable_scenario_id(scenario.lab_name, scenario.config_path),
                status="completed",
                config={},
                config_path=scenario.config_path,
            )
        return scenarios


if __name__ == "__main__":
    unittest.main()
