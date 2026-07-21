from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mclab import batch
from mclab.application.artifacts import write_manifest
from mclab.application.catalog import CONCRETE_BATCH_NAMES, ScenarioCatalog
from mclab.application.repositories import ArtifactRecord, ArtifactRepository
from mclab.completion import CompletionReason, evaluate_completion
from mclab.output_publication import (
    OutputPublicationBusyError,
    mutable_collection_publication,
)
from mclab.output_root import pinned_output_root
from mclab.output_safety import CleanupOperationError, CleanupSafetyError
from mclab.sim import reporting
from mclab.sim.plotting import save_time_series_plots
from mclab.sim.logging import RunLogger
from mclab.sim.reporting import write_outputs_index, write_run_report


def test_run_finalization_refreshes_parent_index_after_terminal_manifest() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger("lab01_msd", {}, output_dir=output)

        def write_manifest(*, status: str) -> Path:
            events.append(f"manifest:{status}")
            return output / "manifest.json"

        with (
            patch.object(logger, "_write_manifest", side_effect=write_manifest),
            patch(
                "mclab.sim.logging.write_run_report",
                side_effect=lambda *_args, **kwargs: events.append(
                    f"report:{kwargs.get('completion_status')}:"
                    f"index={kwargs.get('update_index')}"
                ),
            ),
            patch(
                "mclab.sim.logging.write_outputs_index",
                side_effect=lambda _path: events.append("index:parent"),
            ),
        ):
            logger.finalize_artifacts()

    assert events == [
        "report:running:index=False",
        "manifest:running",
        "report:completed:index=False",
        "manifest:completed",
        "index:parent",
    ]


def test_batch_parent_index_observes_terminal_manifest() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"

        def write_index(path: str | Path) -> Path:
            target = Path(path)
            events.append("index:local" if target == output else "index:parent")
            return target / "index.html"

        def write_manifest(*_args: object, **kwargs: object) -> Path:
            events.append(f"manifest:{kwargs['status']}")
            return output / "manifest.json"

        with (
            patch.dict(batch.BATCH_SETS, {"unit": ()}),
            patch("mclab.batch.write_outputs_index", side_effect=write_index),
            patch(
                "mclab.batch.write_batch_report",
                side_effect=lambda *_args: events.append("report"),
            ),
            patch("mclab.application.artifacts.write_manifest", side_effect=write_manifest),
        ):
            result = batch.run_batch("unit", output_dir=output, plot=False)

    assert result == output
    assert events == [
        "manifest:running",
        "index:local",
        "manifest:running",
        "report",
        "manifest:completed",
        "index:parent",
    ]


def test_run_parent_index_failure_cannot_reopen_terminal_publication() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger("lab01_msd", {}, output_dir=output)
        with (
            patch("mclab.sim.logging.write_run_report"),
            patch(
                "mclab.sim.logging.write_outputs_index",
                side_effect=OSError("index unavailable"),
            ),
            patch("mclab.sim.logging.LOGGER.warning") as warning,
        ):
            manifest = logger.finalize_artifacts()

        warning.assert_called_once()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["status"] == "completed"
        with pytest.raises(RuntimeError, match="already finalized"):
            logger.finalize_artifacts()
        assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "completed"


def test_concrete_batch_parent_index_failure_is_post_commit_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"

        def write_index(path: str | Path) -> Path:
            target = Path(path)
            if target == output:
                return target / "index.html"
            raise OSError("parent index unavailable")

        with (
            patch.dict(batch.BATCH_SETS, {"unit": ()}),
            patch("mclab.batch.write_outputs_index", side_effect=write_index),
            patch("mclab.batch.write_batch_report"),
            patch("mclab.batch.LOGGER.warning") as warning,
        ):
            result = batch.run_batch("unit", output_dir=output, plot=False)

        warning.assert_called_once()
        payload = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "completed"
        assert "error" not in payload


def test_all_batch_parent_index_failure_is_post_commit_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"

        def write_index(path: str | Path) -> Path:
            target = Path(path)
            if target == output:
                return target / "index.html"
            raise OSError("parent index unavailable")

        with (
            patch("mclab.batch.list_batch_sets", return_value=[]),
            patch("mclab.batch.write_outputs_index", side_effect=write_index),
            patch("mclab.batch.write_all_batches_report"),
            patch("mclab.batch.LOGGER.warning") as warning,
        ):
            result = batch.run_all_batches(output_dir=output, plot=False)

        warning.assert_called_once()
        payload = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "completed"
        assert "error" not in payload


def test_terminal_run_refuses_report_and_plot_rewrites_without_byte_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        output.mkdir()
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "lab_name": "lab01_msd",
                    "config_path": "configs/lab01_msd/default.yaml",
                }
            ),
            encoding="utf-8",
        )
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
        )
        before = _tree_bytes(output)

        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            write_run_report(output, update_index=False)
        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            save_time_series_plots(
                output,
                [{"time": 0.0, "position": 0.0}],
                [("position.png", "Position", "x", ("position",))],
            )

        assert _tree_bytes(output) == before


@pytest.mark.skipif(os.name == "nt", reason="symlink fixture is POSIX-only")
def test_report_writer_refuses_symlink_alias_to_terminal_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        terminal = root / "terminal"
        terminal.mkdir()
        write_manifest(
            terminal,
            scenario_id="lab01.default",
            status="completed",
            config={},
        )
        alias = root / "alias"
        alias.symlink_to(terminal, target_is_directory=True)
        before = _tree_bytes(terminal)

        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            write_run_report(alias, update_index=False)

        assert _tree_bytes(terminal) == before


def test_terminal_batch_reports_are_immutable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        concrete = root / "concrete"
        concrete.mkdir()
        write_manifest(
            concrete,
            scenario_id="batch.lab01_msd_compare",
            status="completed",
            config={"batch_name": "lab01_msd_compare", "plot": True},
        )
        course = root / "course"
        course.mkdir()
        write_manifest(
            course,
            scenario_id="batch.all",
            status="completed",
            config={"batch_name": "all", "plot": True},
        )
        concrete_before = _tree_bytes(concrete)
        course_before = _tree_bytes(course)

        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            batch.write_batch_report(concrete, "lab01_msd_compare", ())
        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            batch.write_comparison_plots(concrete, "lab01_msd_compare", ())
        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            batch.write_all_batches_report(course, [])

        assert _tree_bytes(concrete) == concrete_before
        assert _tree_bytes(course) == course_before


def test_outputs_index_refuses_terminal_run_without_byte_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        output.mkdir()
        (output / "index.html").write_text("published index", encoding="utf-8")
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
        )
        before = _tree_bytes(output)

        with pytest.raises(RuntimeError, match="terminal or unsafe"):
            write_outputs_index(output)

        assert _tree_bytes(output) == before


@pytest.mark.skipif(os.name == "nt", reason="open-directory rename fixture is POSIX-only")
def test_report_writer_never_follows_root_swapped_after_inventory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "run"
        output.mkdir()
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "lab_name": "lab01_msd",
                    "config_path": "configs/lab01_msd/default.yaml",
                }
            ),
            encoding="utf-8",
        )
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="running",
            config={"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
        )
        moved = root / "pinned-run"
        outside = root / "outside"
        outside.mkdir()
        (outside / "report.html").write_text("outside sentinel", encoding="utf-8")
        before = _tree_bytes(output)
        original_record = reporting._report_artifact_record

        def swap_after_inventory(path: Path) -> object:
            record = original_record(path)
            output.rename(moved)
            output.symlink_to(outside, target_is_directory=True)
            return record

        with (
            patch.object(
                reporting,
                "_report_artifact_record",
                side_effect=swap_after_inventory,
            ),
            pytest.raises(RuntimeError, match="terminal or unsafe"),
        ):
            write_run_report(output, update_index=False)

        assert _tree_bytes(moved) == before
        assert (outside / "report.html").read_text(encoding="utf-8") == "outside sentinel"
        assert not (outside / "worksheet.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="open-directory rename fixture is POSIX-only")
def test_index_writer_never_follows_root_swapped_during_discovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "outputs"
        output.mkdir()
        (output / "index.html").write_text("pinned sentinel", encoding="utf-8")
        moved = root / "pinned-outputs"
        outside = root / "outside"
        outside.mkdir()
        (outside / "index.html").write_text("outside sentinel", encoding="utf-8")

        def swap_root(_path: Path) -> list[dict[str, object]]:
            output.rename(moved)
            output.symlink_to(outside, target_is_directory=True)
            return []

        with (
            patch("mclab.sim.reporting._discover_runs", side_effect=swap_root),
            pytest.raises(RuntimeError, match="terminal or unsafe"),
        ):
            write_outputs_index(output)

        assert (moved / "index.html").read_text(encoding="utf-8") == "pinned sentinel"
        assert (outside / "index.html").read_text(encoding="utf-8") == "outside sentinel"


def test_index_writer_refuses_marker_changed_to_terminal_during_discovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        output.mkdir()
        (output / "index.html").write_text("published index", encoding="utf-8")
        manifest = write_manifest(
            output,
            scenario_id="lab01.default",
            status="running",
            config={"sim_time": 1.0},
        )
        original_index = (output / "index.html").read_bytes()

        def publish_terminal(_path: Path) -> list[dict[str, object]]:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["status"] = "completed"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            return []

        with (
            patch(
                "mclab.sim.reporting._discover_runs",
                side_effect=publish_terminal,
            ),
            pytest.raises(RuntimeError, match="terminal or unsafe"),
        ):
            write_outputs_index(output)

        assert (output / "index.html").read_bytes() == original_index


def test_index_writer_refuses_collection_reclassified_during_discovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "outputs"
        output.mkdir()
        (output / "index.html").write_text("published index", encoding="utf-8")
        original_index = (output / "index.html").read_bytes()

        def publish_marker(_path: Path) -> list[dict[str, object]]:
            (output / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scenario_id": "lab01.default",
                        "status": "completed",
                    }
                ),
                encoding="utf-8",
            )
            return []

        with (
            patch(
                "mclab.sim.reporting._discover_runs",
                side_effect=publish_marker,
            ),
            pytest.raises(RuntimeError, match="terminal or unsafe"),
        ):
            write_outputs_index(output)

        assert (output / "index.html").read_bytes() == original_index


def test_index_writer_preserves_existing_index_when_root_inventory_is_unbounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "outputs"
        output.mkdir()
        (output / "index.html").write_text("published index", encoding="utf-8")
        original_index = (output / "index.html").read_bytes()

        with (
            patch(
                "mclab.output_publication.PinnedOutputRoot.list_names",
                side_effect=CleanupSafetyError("too many output entries"),
            ),
            pytest.raises(RuntimeError, match="terminal or unsafe"),
        ):
            write_outputs_index(output)

        assert (output / "index.html").read_bytes() == original_index


def test_index_writer_retries_only_publication_contention() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "outputs"
        original_publication = reporting.mutable_collection_publication
        attempts = 0

        def contend_once(path: Path) -> object:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OutputPublicationBusyError("publication is busy")
            return original_publication(path)

        with (
            patch.object(
                reporting,
                "mutable_collection_publication",
                side_effect=contend_once,
            ),
            patch.object(reporting.time, "sleep") as sleep,
        ):
            index = write_outputs_index(output)

        assert index.is_file()
        assert attempts == 2
        sleep.assert_called_once_with(0.025)


def test_publication_maps_only_an_occupied_root_lease_to_busy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "outputs"
        output.mkdir()
        with pinned_output_root(output, allowed_root=output) as (
            _root,
            _exists,
            root_pin,
        ):
            assert root_pin is not None
            with root_pin.operation_lock():
                with pytest.raises(OutputPublicationBusyError):
                    with mutable_collection_publication(output):
                        pass


def test_publication_does_not_misclassify_inventory_io_as_busy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "outputs"
        output.mkdir()

        with (
            patch(
                "mclab.output_publication.PinnedOutputRoot.list_names",
                side_effect=CleanupOperationError("inventory I/O failed"),
            ),
            pytest.raises(RuntimeError) as caught,
        ):
            with mutable_collection_publication(output):
                pass

        assert not isinstance(caught.value, OutputPublicationBusyError)


def test_concrete_completed_publication_failure_recovers_running_not_error() -> None:
    statuses: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"

        def manifest(*_args: object, **kwargs: object) -> Path:
            status = str(kwargs["status"])
            statuses.append(status)
            if status == "completed":
                raise OSError("completed publication failed")
            return output / "manifest.json"

        with (
            patch.dict(batch.BATCH_SETS, {"unit": ()}),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_batch_report"),
            patch("mclab.application.artifacts.write_manifest", side_effect=manifest),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            batch.run_batch("unit", output_dir=output, plot=False)

    assert "error" not in statuses
    assert statuses[-2:] == ["completed", "running"]


def test_all_completed_publication_failure_recovers_running_not_error() -> None:
    statuses: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"

        def manifest(*_args: object, **kwargs: object) -> Path:
            status = str(kwargs["status"])
            statuses.append(status)
            if status == "completed":
                raise OSError("completed publication failed")
            return output / "manifest.json"

        with (
            patch("mclab.batch.list_batch_sets", return_value=[]),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_all_batches_report"),
            patch("mclab.application.artifacts.write_manifest", side_effect=manifest),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            batch.run_all_batches(output_dir=output, plot=False)

    assert "error" not in statuses
    assert statuses[-2:] == ["completed", "running"]


@pytest.mark.parametrize("repair_fails", [False, True], ids=["repair-succeeds", "repair-fails"])
def test_run_completed_publication_failure_never_trusts_stale_complete_documents(
    repair_fails: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
        )
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )
        (output / "plots" / "position.png").write_bytes(b"prospective complete plot")
        original_manifest = logger._write_manifest
        original_report = reporting.write_run_report
        prospective_complete_written = False
        terminal_failed = False

        def fail_completed_manifest(*, status: str) -> Path:
            nonlocal terminal_failed
            if status == "completed":
                terminal_failed = True
                raise OSError("completed publication failed")
            return original_manifest(status=status)

        def report_with_repair_fault(
            output_path: str | Path,
            *,
            update_index: bool = True,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written
            if completion_status == "running" and repair_fails and terminal_failed:
                raise RuntimeError("running report repair failed")
            result = original_report(
                output_path,
                update_index=update_index,
                completion_status=completion_status,
            )
            if completion_status == "completed":
                prospective_complete_written = True
                assert "Completion verdict:</strong> Complete" in result.read_text(
                    encoding="utf-8"
                )
                assert "Completion verdict: Complete" in (
                    Path(output_path) / "worksheet.md"
                ).read_text(encoding="utf-8")
            return result

        with (
            patch.object(logger, "_write_manifest", side_effect=fail_completed_manifest),
            patch("mclab.sim.logging.write_run_report", side_effect=report_with_repair_fault),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            logger.finalize_artifacts()

        assert prospective_complete_written
        _assert_running_recovery_snapshot(output, repaired=not repair_fails)


@pytest.mark.parametrize(
    "retry_preflight_fails",
    [False, True],
    ids=["retry-preflight-succeeds", "retry-preflight-fails"],
)
def test_run_retry_never_seals_stale_complete_documents_under_running_manifest(
    retry_preflight_fails: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
        )
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )
        (output / "plots" / "position.png").write_bytes(b"retry plot")
        original_manifest = logger._write_manifest
        original_report = reporting.write_run_report
        first_terminal_failed = False
        completed_attempts = 0
        running_reports_after_failure = 0
        boundaries: list[dict[str, object]] = []

        def manifest_with_first_terminal_failure(*, status: str) -> Path:
            nonlocal completed_attempts, first_terminal_failed
            if status == "completed":
                completed_attempts += 1
                if completed_attempts == 1:
                    first_terminal_failed = True
                    raise OSError("first completed publication failed")
            manifest = original_manifest(status=status)
            boundaries.append(
                _strict_manifest_boundary(
                    output,
                    status=status,
                    after_failure=first_terminal_failed,
                )
            )
            return manifest

        def report_with_retry_fault(
            output_path: str | Path,
            *,
            update_index: bool = True,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal running_reports_after_failure
            if completion_status == "running" and first_terminal_failed:
                running_reports_after_failure += 1
                if running_reports_after_failure == 1 or retry_preflight_fails:
                    raise RuntimeError("running report repair failed")
            return original_report(
                output_path,
                update_index=update_index,
                completion_status=completion_status,
            )

        with (
            patch.object(
                logger,
                "_write_manifest",
                side_effect=manifest_with_first_terminal_failure,
            ),
            patch("mclab.sim.logging.write_run_report", side_effect=report_with_retry_fault),
        ):
            with pytest.raises(OSError, match="first completed publication failed"):
                logger.finalize_artifacts()
            _assert_running_recovery_snapshot(output, repaired=False)

            if retry_preflight_fails:
                with pytest.raises(RuntimeError, match="running report repair failed"):
                    logger.finalize_artifacts()
                _assert_running_recovery_snapshot(output, repaired=False)
            else:
                logger.finalize_artifacts()

        for boundary in boundaries:
            if boundary["status"] != "running":
                continue
            assert boundary["reason"] == CompletionReason.RUN_NOT_COMPLETED
            if boundary["report_available"]:
                assert boundary["worksheet_available"]
                assert "Incomplete" in str(boundary["report_text"])
                assert "Incomplete" in str(boundary["worksheet_text"])
                assert CompletionReason.RUN_NOT_COMPLETED.value in str(
                    boundary["report_text"]
                )
                assert CompletionReason.RUN_NOT_COMPLETED.value in str(
                    boundary["worksheet_text"]
                )

        if retry_preflight_fails:
            assert not any(
                boundary["after_failure"] and boundary["status"] == "completed"
                for boundary in boundaries
            )
        else:
            repaired_index = next(
                index
                for index, boundary in enumerate(boundaries)
                if boundary["after_failure"]
                and boundary["status"] == "running"
                and boundary["report_available"]
                and boundary["worksheet_available"]
            )
            completed_index = next(
                index
                for index, boundary in enumerate(boundaries)
                if boundary["after_failure"] and boundary["status"] == "completed"
            )
            assert repaired_index < completed_index
            final_record = _strict_output_record(output)
            final_target = ScenarioCatalog.default().get_target(final_record.scenario_id)
            final_decision = evaluate_completion(
                final_target.completion,
                final_record.completion_evidence,
            )
            assert final_decision.complete
            assert final_decision.primary_reason == CompletionReason.COMPLETE


def test_save_with_artifacts_retry_does_not_publish_stale_docs_before_first_producer_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
        )
        (output / "plots" / "position.png").write_bytes(b"save retry plot")
        original_manifest = logger._write_manifest
        original_report = reporting.write_run_report
        first_terminal_failed = False
        prospective_complete_written = False
        boundaries: list[dict[str, object]] = []

        def manifest_with_terminal_failure(*, status: str) -> Path:
            nonlocal first_terminal_failed
            if status == "completed":
                first_terminal_failed = True
                raise OSError("completed publication failed")
            manifest = original_manifest(status=status)
            boundaries.append(
                _strict_manifest_boundary(
                    output,
                    status=status,
                    after_failure=first_terminal_failed,
                )
            )
            return manifest

        def report_with_failed_repair(
            output_path: str | Path,
            *,
            update_index: bool = True,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written
            if completion_status == "running" and first_terminal_failed:
                raise RuntimeError("running report repair failed")
            report = original_report(
                output_path,
                update_index=update_index,
                completion_status=completion_status,
            )
            prospective_complete_written |= completion_status == "completed"
            return report

        with (
            patch.object(
                logger,
                "_write_manifest",
                side_effect=manifest_with_terminal_failure,
            ),
            patch("mclab.sim.logging.write_run_report", side_effect=report_with_failed_repair),
        ):
            with pytest.raises(OSError, match="completed publication failed"):
                logger.save_with_artifacts(
                    summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
                )
            assert prospective_complete_written
            _assert_running_recovery_snapshot(output, repaired=False)

            with (
                patch.object(
                    logger,
                    "_save_config_snapshot",
                    side_effect=RuntimeError("first producer write failed"),
                ),
                pytest.raises(RuntimeError, match="first producer write failed"),
            ):
                logger.save_with_artifacts(
                    summary={"lab_name": "lab01_msd", "duration": 2.0, "samples": 2},
                )

        _assert_running_recovery_snapshot(output, repaired=False)
        assert not any(boundary["after_failure"] for boundary in boundaries)


@pytest.mark.parametrize(
    "retry_repair_fails",
    [False, True],
    ids=["retry-repair-succeeds", "retry-repair-fails"],
)
def test_save_with_artifacts_finalize_false_retry_repairs_before_running_manifest(
    retry_repair_fails: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
        )
        (output / "plots" / "position.png").write_bytes(b"finalize false retry plot")
        original_manifest = logger._write_manifest
        original_report = reporting.write_run_report
        first_terminal_failed = False
        running_repairs_after_failure = 0
        prospective_complete_written = False
        boundaries: list[dict[str, object]] = []

        def manifest_with_terminal_failure(*, status: str) -> Path:
            nonlocal first_terminal_failed
            if status == "completed":
                first_terminal_failed = True
                raise OSError("completed publication failed")
            manifest = original_manifest(status=status)
            boundaries.append(
                _strict_manifest_boundary(
                    output,
                    status=status,
                    after_failure=first_terminal_failed,
                )
            )
            return manifest

        def report_with_retry_repair_fault(
            output_path: str | Path,
            *,
            update_index: bool = True,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written, running_repairs_after_failure
            if completion_status == "running" and first_terminal_failed:
                running_repairs_after_failure += 1
                if running_repairs_after_failure == 1 or retry_repair_fails:
                    raise RuntimeError("running report repair failed")
            report = original_report(
                output_path,
                update_index=update_index,
                completion_status=completion_status,
            )
            prospective_complete_written |= completion_status == "completed"
            return report

        with (
            patch.object(
                logger,
                "_write_manifest",
                side_effect=manifest_with_terminal_failure,
            ),
            patch(
                "mclab.sim.logging.write_run_report",
                side_effect=report_with_retry_repair_fault,
            ),
        ):
            with pytest.raises(OSError, match="completed publication failed"):
                logger.save_with_artifacts(
                    summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
                )
            assert prospective_complete_written
            _assert_running_recovery_snapshot(output, repaired=False)

            retry_summary = {
                "lab_name": "lab01_msd",
                "duration": 2.0,
                "samples": 2,
            }
            if retry_repair_fails:
                with pytest.raises(RuntimeError, match="running report repair failed"):
                    logger.save_with_artifacts(
                        summary=retry_summary,
                        notes="retry producers completed",
                        finalize=False,
                    )
            else:
                logger.save_with_artifacts(
                    summary=retry_summary,
                    notes="retry producers completed",
                    finalize=False,
                )

        saved_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert saved_summary["duration"] == 2.0
        assert saved_summary["samples"] == 2
        assert (output / "notes.md").read_text(encoding="utf-8") == (
            "retry producers completed\n"
        )

        after_failure = [
            boundary for boundary in boundaries if boundary["after_failure"]
        ]
        if retry_repair_fails:
            assert after_failure == []
            _assert_running_recovery_snapshot(output, repaired=False)
        else:
            assert [boundary["status"] for boundary in after_failure] == ["running"]
            boundary = after_failure[0]
            assert boundary["reason"] == CompletionReason.RUN_NOT_COMPLETED
            assert boundary["report_available"]
            assert boundary["worksheet_available"]
            for text in (
                str(boundary["report_text"]),
                str(boundary["worksheet_text"]),
            ):
                assert "Incomplete" in text
                assert CompletionReason.RUN_NOT_COMPLETED.value in text
            _assert_running_recovery_snapshot(output, repaired=True)


@pytest.mark.parametrize("repair_fails", [False, True], ids=["repair-succeeds", "repair-fails"])
def test_concrete_batch_completed_publication_failure_never_trusts_stale_complete_documents(
    repair_fails: bool,
) -> None:
    batch_name = "lab01_msd_compare"
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"
        prospective_complete_written = False

        def comparison_plot(
            batch_output: str | Path,
            _batch_name: str,
            _scenarios: tuple[object, ...],
        ) -> list[Path]:
            plot = Path(batch_output) / "comparison_plots" / "evidence.png"
            plot.parent.mkdir(parents=True, exist_ok=True)
            plot.write_bytes(b"prospective complete comparison plot")
            return [plot]

        def report_with_repair_fault(
            batch_output: str | Path,
            _batch_name: str,
            _scenarios: tuple[object, ...],
            *,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written
            if completion_status == "running" and repair_fails:
                raise RuntimeError("running batch report repair failed")
            _write_fault_injection_documents(
                Path(batch_output),
                completion_status=completion_status,
                prediction_check=True,
            )
            prospective_complete_written |= completion_status == "completed"
            return Path(batch_output) / "report.html"

        def fail_completed_manifest(*args: object, **kwargs: object) -> Path:
            if kwargs.get("status") == "completed":
                raise OSError("completed publication failed")
            return write_manifest(*args, **kwargs)

        with (
            patch.dict(batch.BATCH_SETS, {batch_name: ()}, clear=False),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_comparison_plots", side_effect=comparison_plot),
            patch("mclab.batch.write_batch_report", side_effect=report_with_repair_fault),
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=fail_completed_manifest,
            ),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            batch.run_batch(batch_name, output_dir=output, plot=True)

        assert prospective_complete_written
        _assert_running_recovery_snapshot(output, repaired=not repair_fails)


@pytest.mark.parametrize("repair_fails", [False, True], ids=["repair-succeeds", "repair-fails"])
def test_all_batches_completed_publication_failure_never_trusts_stale_complete_documents(
    repair_fails: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"
        prospective_complete_written = False

        def completed_child_batch(
            batch_name: str,
            *,
            output_dir: str | Path,
            **_kwargs: object,
        ) -> Path:
            child = Path(output_dir)
            _write_strict_complete_child_batch(child, batch_name)
            return child

        def report_with_repair_fault(
            group_output: str | Path,
            _completed: list[dict[str, object]],
            *,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written
            if completion_status == "running" and repair_fails:
                raise RuntimeError("running course report repair failed")
            _write_fault_injection_documents(
                Path(group_output),
                completion_status=completion_status,
                prediction_check=False,
            )
            prospective_complete_written |= completion_status == "completed"
            return Path(group_output) / "report.html"

        def fail_completed_manifest(*args: object, **kwargs: object) -> Path:
            if kwargs.get("status") == "completed":
                raise OSError("completed publication failed")
            return write_manifest(*args, **kwargs)

        with (
            patch("mclab.batch.list_batch_sets", return_value=CONCRETE_BATCH_NAMES),
            patch("mclab.batch.run_batch", side_effect=completed_child_batch),
            patch("mclab.batch.write_outputs_index"),
            patch(
                "mclab.batch.write_all_batches_report",
                side_effect=report_with_repair_fault,
            ),
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=fail_completed_manifest,
            ),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            batch.run_all_batches(output_dir=output, plot=True)

        assert prospective_complete_written
        _assert_running_recovery_snapshot(output, repaired=not repair_fails)


@pytest.mark.parametrize("repair_fails", [False, True], ids=["repair-succeeds", "repair-fails"])
def test_concrete_batch_post_write_report_failure_recovers_without_trusting_stale_complete_documents(
    repair_fails: bool,
) -> None:
    batch_name = "lab01_msd_compare"
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"
        prospective_complete_written = False
        report_failed = False
        boundaries: list[dict[str, object]] = []

        def comparison_plot(
            batch_output: str | Path,
            _batch_name: str,
            _scenarios: tuple[object, ...],
        ) -> list[Path]:
            plot = Path(batch_output) / "comparison_plots" / "evidence.png"
            plot.parent.mkdir(parents=True, exist_ok=True)
            plot.write_bytes(b"post-write failure comparison plot")
            return [plot]

        def report_with_post_write_failure(
            batch_output: str | Path,
            _batch_name: str,
            _scenarios: tuple[object, ...],
            *,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written, report_failed
            if completion_status == "error" and repair_fails:
                raise RuntimeError("error batch report repair failed")
            _write_fault_injection_documents(
                Path(batch_output),
                completion_status=completion_status,
                prediction_check=True,
            )
            if completion_status == "completed":
                prospective_complete_written = True
                report_failed = True
                raise OSError("batch report failed after complete write")
            return Path(batch_output) / "report.html"

        def recording_manifest(*args: object, **kwargs: object) -> Path:
            manifest = write_manifest(*args, **kwargs)
            boundaries.append(
                _strict_manifest_boundary(
                    output,
                    status=str(kwargs["status"]),
                    after_failure=report_failed,
                )
            )
            return manifest

        with (
            patch.dict(batch.BATCH_SETS, {batch_name: ()}, clear=False),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_comparison_plots", side_effect=comparison_plot),
            patch(
                "mclab.batch.write_batch_report",
                side_effect=report_with_post_write_failure,
            ),
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=recording_manifest,
            ),
            pytest.raises(OSError, match="batch report failed after complete write"),
        ):
            batch.run_batch(batch_name, output_dir=output, plot=True)

        assert prospective_complete_written
        _assert_post_write_error_recovery(
            output,
            boundaries=boundaries,
            repaired=not repair_fails,
        )


@pytest.mark.parametrize("repair_fails", [False, True], ids=["repair-succeeds", "repair-fails"])
def test_all_batches_post_write_report_failure_recovers_without_trusting_stale_complete_documents(
    repair_fails: bool,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"
        prospective_complete_written = False
        report_failed = False
        boundaries: list[dict[str, object]] = []

        def completed_child_batch(
            batch_name: str,
            *,
            output_dir: str | Path,
            **_kwargs: object,
        ) -> Path:
            child = Path(output_dir)
            _write_strict_complete_child_batch(child, batch_name)
            return child

        def report_with_post_write_failure(
            group_output: str | Path,
            _completed: list[dict[str, object]],
            *,
            completion_status: str = "completed",
        ) -> Path:
            nonlocal prospective_complete_written, report_failed
            if completion_status == "error" and repair_fails:
                raise RuntimeError("error course report repair failed")
            _write_fault_injection_documents(
                Path(group_output),
                completion_status=completion_status,
                prediction_check=False,
            )
            if completion_status == "completed":
                prospective_complete_written = True
                report_failed = True
                raise OSError("course report failed after complete write")
            return Path(group_output) / "report.html"

        def recording_manifest(*args: object, **kwargs: object) -> Path:
            manifest = write_manifest(*args, **kwargs)
            boundaries.append(
                _strict_manifest_boundary(
                    output,
                    status=str(kwargs["status"]),
                    after_failure=report_failed,
                )
            )
            return manifest

        with (
            patch("mclab.batch.list_batch_sets", return_value=CONCRETE_BATCH_NAMES),
            patch("mclab.batch.run_batch", side_effect=completed_child_batch),
            patch("mclab.batch.write_outputs_index"),
            patch(
                "mclab.batch.write_all_batches_report",
                side_effect=report_with_post_write_failure,
            ),
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=recording_manifest,
            ),
            pytest.raises(OSError, match="course report failed after complete write"),
        ):
            batch.run_all_batches(output_dir=output, plot=True)

        assert prospective_complete_written
        _assert_post_write_error_recovery(
            output,
            boundaries=boundaries,
            repaired=not repair_fails,
        )


def test_all_handoff_release_precedes_terminal_publication() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"
        output.mkdir()

        def manifest(*_args: object, **kwargs: object) -> Path:
            events.append(f"manifest:{kwargs['status']}")
            return output / "manifest.json"

        with (
            patch("mclab.batch.create_batch_output_path", return_value=output),
            patch("mclab.batch.list_batch_sets", return_value=[]),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_all_batches_report", side_effect=lambda *_args: events.append("report")),
            patch("mclab.batch.release_all_compare_handoff", side_effect=lambda _path: events.append("release")),
            patch("mclab.application.artifacts.write_manifest", side_effect=manifest),
        ):
            batch.run_all_batches(
                output_dir=output,
                plot=False,
                handoff_token="unit-token",
            )

    assert events[-3:] == ["report", "release", "manifest:completed"]


def test_all_handoff_release_precedes_terminal_error_publication() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"
        output.mkdir()

        def manifest(*_args: object, **kwargs: object) -> Path:
            events.append(f"manifest:{kwargs['status']}")
            return output / "manifest.json"

        with (
            patch("mclab.batch.create_batch_output_path", return_value=output),
            patch("mclab.batch.list_batch_sets", side_effect=OSError("batch discovery failed")),
            patch("mclab.batch.write_outputs_index"),
            patch("mclab.batch.write_all_batches_report", side_effect=lambda *_args, **_kwargs: events.append("report")),
            patch("mclab.batch.release_all_compare_handoff", side_effect=lambda _path: events.append("release")),
            patch("mclab.application.artifacts.write_manifest", side_effect=manifest),
            pytest.raises(OSError, match="batch discovery failed"),
        ):
            batch.run_all_batches(
                output_dir=output,
                plot=False,
                handoff_token="unit-token",
            )

    assert events[-2:] == ["release", "manifest:error"]


def test_all_error_report_repair_failure_never_publishes_terminal_error() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"
        output.mkdir()

        def manifest(*_args: object, **kwargs: object) -> Path:
            events.append(f"manifest:{kwargs['status']}")
            return output / "manifest.json"

        with (
            patch("mclab.batch.create_batch_output_path", return_value=output),
            patch("mclab.batch.list_batch_sets", side_effect=OSError("batch discovery failed")),
            patch("mclab.batch.write_outputs_index"),
            patch(
                "mclab.batch.write_all_batches_report",
                side_effect=RuntimeError("error report repair failed"),
            ),
            patch(
                "mclab.batch.release_all_compare_handoff",
                side_effect=lambda _path: events.append("release"),
            ),
            patch("mclab.application.artifacts.write_manifest", side_effect=manifest),
            pytest.raises(OSError, match="batch discovery failed"),
        ):
            batch.run_all_batches(
                output_dir=output,
                plot=False,
                handoff_token="unit-token",
            )

    assert "manifest:error" not in events
    assert events[-2:] == ["manifest:running", "release"]


def _write_fault_injection_documents(
    output: Path,
    *,
    completion_status: str,
    prediction_check: bool,
) -> None:
    complete = completion_status == "completed"
    verdict = "Complete" if complete else "Incomplete"
    reason = (
        CompletionReason.COMPLETE.value
        if complete
        else CompletionReason.RUN_NOT_COMPLETED.value
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.html").write_text(
        (
            "<html><body>"
            f"<p><strong>Completion verdict:</strong> {verdict}</p>"
            f"<p><strong>Completion reason:</strong> {reason}</p>"
            "</body></html>"
        ),
        encoding="utf-8",
    )
    prediction_section = "\n\n## Prediction Check\n" if prediction_check else ""
    (output / "worksheet.md").write_text(
        (
            "# Worksheet\n\n"
            f"- Completion verdict: {verdict}\n"
            f"- Completion reason: {reason}"
            f"{prediction_section}"
        ),
        encoding="utf-8",
    )


def _write_strict_complete_child_batch(output: Path, batch_name: str) -> None:
    output.mkdir(parents=True)
    (output / "summary.json").write_text(
        json.dumps(
            {
                "lab_name": "batch",
                "batch_name": batch_name,
                "config_name": batch_name,
            }
        ),
        encoding="utf-8",
    )
    plot = output / "comparison_plots" / "evidence.png"
    plot.parent.mkdir()
    plot.write_bytes(b"trusted child comparison plot")
    _write_fault_injection_documents(
        output,
        completion_status="completed",
        prediction_check=True,
    )
    write_manifest(
        output,
        scenario_id=f"batch.{batch_name}",
        status="completed",
        config={"batch_name": batch_name, "plot": True},
        run_kind="comparison_batch",
    )


def _strict_output_record(output: Path) -> ArtifactRecord:
    return next(
        item
        for item in ArtifactRepository(output.parent).list_runs()
        if item.path.name == output.name
    )


def _strict_manifest_boundary(
    output: Path,
    *,
    status: str,
    after_failure: bool,
) -> dict[str, object]:
    record = _strict_output_record(output)
    assert record.status == status
    target = ScenarioCatalog.default().get_target(record.scenario_id)
    decision = evaluate_completion(target.completion, record.completion_evidence)
    return {
        "status": status,
        "after_failure": after_failure,
        "reason": decision.primary_reason,
        "report_available": record.report_available,
        "worksheet_available": record.worksheet_available,
        "report_text": (
            (output / "report.html").read_text(encoding="utf-8")
            if record.report_available
            else ""
        ),
        "worksheet_text": record.worksheet_text if record.worksheet_available else "",
    }


def _assert_post_write_error_recovery(
    output: Path,
    *,
    boundaries: list[dict[str, object]],
    repaired: bool,
) -> None:
    after_failure = [boundary for boundary in boundaries if boundary["after_failure"]]
    if repaired:
        assert [boundary["status"] for boundary in after_failure] == ["running", "error"]
        for boundary in after_failure:
            assert boundary["reason"] == CompletionReason.RUN_NOT_COMPLETED
            assert boundary["report_available"]
            assert boundary["worksheet_available"]
            assert "Incomplete" in str(boundary["report_text"])
            assert "Incomplete" in str(boundary["worksheet_text"])
            assert CompletionReason.RUN_NOT_COMPLETED.value in str(
                boundary["report_text"]
            )
            assert CompletionReason.RUN_NOT_COMPLETED.value in str(
                boundary["worksheet_text"]
            )
    else:
        assert after_failure == []
        assert not any(boundary["status"] == "error" for boundary in boundaries)

    record = _strict_output_record(output)
    expected_status = "error" if repaired else "running"
    assert record.status == expected_status
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))[
        "status"
    ] == expected_status
    target = ScenarioCatalog.default().get_target(record.scenario_id)
    decision = evaluate_completion(target.completion, record.completion_evidence)
    assert not decision.complete
    assert decision.primary_reason == CompletionReason.RUN_NOT_COMPLETED

    if repaired:
        assert record.report_available
        assert record.worksheet_available
        for text in (
            (output / "report.html").read_text(encoding="utf-8"),
            record.worksheet_text,
        ):
            assert "Incomplete" in text
            assert CompletionReason.RUN_NOT_COMPLETED.value in text
        return

    assert not record.report_available
    assert not record.worksheet_available
    for filename in ("report.html", "worksheet.md"):
        stale_text = (output / filename).read_text(encoding="utf-8")
        assert "Complete" in stale_text
        assert CompletionReason.COMPLETE.value in stale_text


def _assert_running_recovery_snapshot(output: Path, *, repaired: bool) -> None:
    record = _strict_output_record(output)
    assert isinstance(record, ArtifactRecord)
    assert record.status == "running"
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))[
        "status"
    ] == "running"

    target = ScenarioCatalog.default().get_target(record.scenario_id)
    decision = evaluate_completion(target.completion, record.completion_evidence)
    assert not decision.complete
    assert decision.primary_reason == CompletionReason.RUN_NOT_COMPLETED

    availability = {
        "report.html": record.report_available,
        "worksheet.md": record.worksheet_available,
    }
    if repaired:
        assert availability == {"report.html": True, "worksheet.md": True}
    else:
        assert availability == {"report.html": False, "worksheet.md": False}

    for filename, trusted in availability.items():
        path = output / filename
        if not trusted:
            if path.exists():
                stale_text = path.read_text(encoding="utf-8")
                assert "Complete" in stale_text
                assert CompletionReason.COMPLETE.value in stale_text
            continue
        text = path.read_text(encoding="utf-8")
        assert "Completion verdict:" in text
        assert "Incomplete" in text
        assert CompletionReason.RUN_NOT_COMPLETED.value in text


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
