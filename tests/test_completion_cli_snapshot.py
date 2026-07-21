from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application.artifacts import write_manifest  # noqa: E402
from mclab.application.catalog import CONCRETE_BATCH_NAMES, stable_scenario_id  # noqa: E402
from mclab.application.repositories import ArtifactRepository  # noqa: E402
from mclab.cli import (  # noqa: E402
    LABS,
    _output_artifact_lines,
    _preferred_output_entry,
    _worksheet_viewer_handoff,
    build_parser,
    main,
)
from mclab.config import load_config  # noqa: E402
from mclab.learner_menu import completion_snapshot  # noqa: E402


def _publish_run(root: Path, name: str) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "lab01_msd",
                "config_path": "configs/lab01_msd/default.yaml",
                "config_name": "default",
            }
        ),
        encoding="utf-8",
    )
    (run / "report.html").write_text("<html>report</html>", encoding="utf-8")
    (run / "worksheet.md").write_text(
        "\n".join(
            (
                "# Worksheet",
                "",
                "## Plot Review",
                "",
                "- Priority plot: plots/position.png",
                "- Read first: Position",
                "- What to check: Compare target and actual motion.",
                "",
                "## Viewer Handoff",
                "",
                "- Start with: baseline",
                "- Viewer rerun: python -m mclab run lab01 --viewer",
            )
        ),
        encoding="utf-8",
    )
    plots = run / "plots"
    plots.mkdir()
    (plots / "position.png").write_bytes(b"trusted plot")
    config_path = "configs/lab01_msd/default.yaml"
    write_manifest(
        run,
        scenario_id=stable_scenario_id("lab01_msd", config_path),
        status="completed",
        config=load_config(config_path),
        config_path=config_path,
    )
    return run


def _publish_course_batch(
    outputs_root: Path,
    *,
    linked_handoff: str = "lab01_msd_compare/report.html#viewer-handoff",
    child_scenario_id: str = "batch.lab01_msd_compare",
) -> Path:
    course = outputs_root / "all_batches"
    course.mkdir(parents=True)
    (course / "report.html").write_text("<html>course</html>", encoding="utf-8")
    (course / "worksheet.md").write_text(
        "\n".join(
            (
                "# Course worksheet",
                "",
                "## Batch Review",
                "",
                "- Lab01 Mass-Spring-Damper Comparison",
                f"  - Viewer handoff: {linked_handoff}",
            )
        ),
        encoding="utf-8",
    )
    for batch_name in CONCRETE_BATCH_NAMES:
        child = course / batch_name
        child.mkdir()
        (child / "summary.json").write_text(
            json.dumps(
                {
                    "lab_name": "batch",
                    "batch_name": batch_name,
                    "config_name": batch_name,
                }
            ),
            encoding="utf-8",
        )
        (child / "report.html").write_text("<html>child</html>", encoding="utf-8")
        worksheet_lines = [
            "# Batch worksheet",
            "",
            "## Prediction Check",
            "",
            # Deliberately preserve a pre-policy worksheet prompt to verify historical compatibility.
            "- [ ] Mark Matched, Partly matched, or Surprised.",
        ]
        if batch_name == "lab01_msd_compare":
            worksheet_lines.extend(
                (
                    "",
                    "## Viewer Handoff",
                    "",
                    "- Start with: underdamped",
                    "- Viewer rerun: python -m mclab run lab01 --viewer --realtime",
                )
            )
        (child / "worksheet.md").write_text(
            "\n".join(worksheet_lines),
            encoding="utf-8",
        )
        comparison_plots = child / "comparison_plots"
        comparison_plots.mkdir()
        (comparison_plots / "comparison.png").write_bytes(b"trusted comparison plot")
        write_manifest(
            child,
            scenario_id=(
                child_scenario_id
                if batch_name == "lab01_msd_compare"
                else f"batch.{batch_name}"
            ),
            status="completed",
            config={"batch_name": batch_name, "plot": True},
            run_kind="comparison_batch",
        )
    write_manifest(
        course,
        scenario_id="batch.all",
        status="completed",
        config={"batch_name": "all", "plot": True},
        run_kind="comparison_batch",
    )
    return course


class CompletionCliSnapshotTests(unittest.TestCase):
    def test_cli_and_menu_share_the_configured_default_outputs_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary).resolve()
            expected = data_root / "outputs"
            captured_roots: list[Path] = []

            def inventory(repository: ArtifactRepository) -> tuple[()]:
                captured_roots.append(Path(repository.outputs_root).absolute())
                return ()

            with (
                patch.dict(os.environ, {"MCLAB_DATA_DIR": str(data_root)}),
                patch.object(
                    ArtifactRepository,
                    "list_runs",
                    autospec=True,
                    side_effect=inventory,
                ),
            ):
                parsed = build_parser().parse_args(["coverage"])
                with completion_snapshot():
                    pass

        self.assertEqual(Path(parsed.output_dir), expected)
        self.assertEqual(captured_roots, [expected])

    def test_read_only_completion_commands_inventory_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary).resolve()
            outputs_root = data_root / "outputs"
            outputs_root.mkdir()
            cases = (
                ["scenarios", "wall", "--details", "--limit", "2"],
                ["batches", "wall", "--details", "--limit", "2"],
                ["coverage", "--output-dir", str(outputs_root), "--details"],
                ["path", "--output-dir", str(outputs_root), "--all"],
                ["review", "--output-dir", str(outputs_root), "--limit", "3"],
                ["next", "--output-dir", str(outputs_root), "--preview"],
            )

            for argv in cases:
                with (
                    self.subTest(command=argv[0]),
                    patch.dict(
                        os.environ,
                        {"MCLAB_DATA_DIR": str(data_root)},
                    ),
                    patch.object(
                        ArtifactRepository,
                        "list_runs",
                        autospec=True,
                        return_value=(),
                    ) as inventory,
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(argv), 0)
                    self.assertEqual(inventory.call_count, 1)

    def test_mutating_next_uses_pre_and_post_run_inventories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary).resolve() / "outputs"
            outputs_root.mkdir()
            output = outputs_root / "new-run"

            def fake_runner(_config: dict[str, object], **_kwargs: object) -> Path:
                return output

            with (
                patch.dict(LABS, {"lab01": fake_runner}, clear=False),
                patch("mclab.cli.load_config", return_value={"model_path": "demo.xml"}),
                patch.object(
                    ArtifactRepository,
                    "list_runs",
                    autospec=True,
                    return_value=(),
                ) as inventory,
                patch("mclab.cli._open_path") as opener,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    main(["next", "--output-dir", str(outputs_root)]),
                    0,
                )

            self.assertEqual(inventory.call_count, 2)
            opener.assert_called_once_with(output)

    def test_output_summary_uses_snapshot_artifacts_without_reopening_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = _publish_run(root, "valid")

            with (
                completion_snapshot(root),
                patch.object(
                    Path,
                    "read_text",
                    side_effect=AssertionError("CLI reopened trusted worksheet text"),
                ),
                patch.object(
                    Path,
                    "glob",
                    side_effect=AssertionError("CLI globbed trusted plot paths"),
                ),
            ):
                lines = _output_artifact_lines(run)
                entry = _preferred_output_entry(run)
                handoff = _worksheet_viewer_handoff(run)

        self.assertEqual(entry, run / "report.html")
        self.assertIn(f"Report: {run / 'report.html'}", lines)
        self.assertIn(f"Worksheet: {run / 'worksheet.md'}", lines)
        self.assertIn(f"Plots: {run / 'plots'} (1 PNG; first: position.png)", lines)
        self.assertIn(f"Priority plot: {run / 'plots' / 'position.png'}", lines)
        self.assertIn(
            "Viewer handoff: baseline -> python -m mclab run lab01 --viewer",
            lines,
        )
        self.assertEqual(
            handoff,
            ("baseline", "python -m mclab run lab01 --viewer"),
        )

    def test_invalid_and_future_manifests_never_fall_back_to_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            invalid = _publish_run(root, "invalid-v1")
            future = _publish_run(root, "future")

            invalid_manifest = json.loads((invalid / "manifest.json").read_text(encoding="utf-8"))
            invalid_manifest.pop("runtime")
            (invalid / "manifest.json").write_text(
                json.dumps(invalid_manifest),
                encoding="utf-8",
            )
            future_manifest = json.loads((future / "manifest.json").read_text(encoding="utf-8"))
            future_manifest["schema_version"] = 2
            (future / "manifest.json").write_text(
                json.dumps(future_manifest),
                encoding="utf-8",
            )

            with completion_snapshot(root):
                for run in (invalid, future):
                    with self.subTest(run=run.name):
                        self.assertEqual(_output_artifact_lines(run), [])
                        self.assertEqual(_preferred_output_entry(run), run)
                        self.assertEqual(_worksheet_viewer_handoff(run), ("", ""))

    def test_all_batch_details_resolve_one_trusted_child_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary).resolve()
            outputs_root = data_root / "outputs"
            outputs_root.mkdir()
            course = _publish_course_batch(outputs_root)
            list_runs = ArtifactRepository.list_runs

            with (
                patch.dict(
                    os.environ,
                    {"MCLAB_DATA_DIR": str(data_root)},
                ),
                patch.object(
                    ArtifactRepository,
                    "list_runs",
                    autospec=True,
                    side_effect=list_runs,
                ) as inventory,
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(
                    main(["batches", "all", "--details", "--limit", "1"]),
                    0,
                )

        rendered = stdout.getvalue()
        self.assertIn(
            "Handoff: lab01_msd_compare / underdamped -> "
            "python -m mclab run lab01 --viewer --realtime",
            rendered,
        )
        self.assertEqual(inventory.call_count, 2)
        inventoried_roots = [
            Path(call.args[0].outputs_root).absolute() for call in inventory.call_args_list
        ]
        self.assertEqual(inventoried_roots, [outputs_root, course])

    def test_all_batch_details_reject_arbitrary_parent_links(self) -> None:
        injected_links = (
            "evil/report.html#viewer-handoff",
            "../lab01_msd_compare/report.html#viewer-handoff",
            "/tmp/lab01_msd_compare/report.html#viewer-handoff",
            "lab01_msd_compare/extra/report.html#viewer-handoff",
        )
        for linked_handoff in injected_links:
            with (
                self.subTest(linked_handoff=linked_handoff),
                tempfile.TemporaryDirectory() as temporary,
            ):
                data_root = Path(temporary).resolve()
                outputs_root = data_root / "outputs"
                outputs_root.mkdir()
                _publish_course_batch(outputs_root, linked_handoff=linked_handoff)
                list_runs = ArtifactRepository.list_runs

                with (
                    patch.dict(
                        os.environ,
                        {"MCLAB_DATA_DIR": str(data_root)},
                    ),
                    patch.object(
                        ArtifactRepository,
                        "list_runs",
                        autospec=True,
                        side_effect=list_runs,
                    ) as inventory,
                    redirect_stdout(io.StringIO()) as stdout,
                ):
                    self.assertEqual(
                        main(["batches", "all", "--details", "--limit", "1"]),
                        0,
                    )

                rendered = stdout.getvalue()
                self.assertIn(
                    "Handoff: Open the course worksheet, then follow a linked batch Viewer Handoff.",
                    rendered,
                )
                self.assertNotIn("python -m mclab run lab01 --viewer", rendered)
                self.assertEqual(inventory.call_count, 1)

    def test_all_batch_details_withhold_course_handoff_for_wrong_child_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary).resolve()
            outputs_root = data_root / "outputs"
            outputs_root.mkdir()
            _publish_course_batch(
                outputs_root,
                child_scenario_id="batch.lab02_pid_compare",
            )
            list_runs = ArtifactRepository.list_runs

            with (
                patch.dict(
                    os.environ,
                    {"MCLAB_DATA_DIR": str(data_root)},
                ),
                patch.object(
                    ArtifactRepository,
                    "list_runs",
                    autospec=True,
                    side_effect=list_runs,
                ) as inventory,
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(
                    main(["batches", "all", "--details", "--limit", "1"]),
                    0,
                )

        rendered = stdout.getvalue()
        self.assertIn(
            "Handoff: Latest batch output has no trusted worksheet; rerun the batch.",
            rendered,
        )
        self.assertNotIn("python -m mclab run lab01 --viewer", rendered)
        self.assertEqual(inventory.call_count, 1)


if __name__ == "__main__":
    unittest.main()
