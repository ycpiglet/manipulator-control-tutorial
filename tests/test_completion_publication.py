from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mclab import batch
from mclab.application.artifacts import (
    verify_manifest,
    verify_terminal_batch_output,
    write_manifest,
)
from mclab.application.batch_runs import (
    claim_all_compare_handoff,
    create_all_compare_output,
    read_all_compare_handoff,
    settle_all_compare_output,
)
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

        def write_manifest(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            assert untrusted_artifacts in ((), ("report.html", "worksheet.md"))
            trust = "deferred" if untrusted_artifacts else "trusted"
            events.append(f"manifest:{status}:{trust}")
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
        "manifest:running:deferred",
        "report:completed:index=False",
        "manifest:completed:trusted",
        "index:parent",
    ]


def test_nested_run_finalization_defers_only_parent_index() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {},
            output_dir=output,
            publish_parent_index=False,
        )

        def write_manifest(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            assert untrusted_artifacts in ((), ("report.html", "worksheet.md"))
            trust = "deferred" if untrusted_artifacts else "trusted"
            events.append(f"manifest:{status}:{trust}")
            return output / "manifest.json"

        with (
            patch.object(logger, "_write_manifest", side_effect=write_manifest),
            patch(
                "mclab.sim.logging.write_run_report",
                side_effect=lambda *_args, **kwargs: events.append(
                    f"report:{kwargs.get('completion_status')}"
                ),
            ),
            patch("mclab.sim.logging.write_outputs_index") as write_index,
        ):
            logger.finalize_artifacts()

    assert events == [
        "manifest:running:deferred",
        "report:completed",
        "manifest:completed:trusted",
    ]
    write_index.assert_not_called()


def test_abrupt_run_report_rewrite_leaves_documents_untrusted_and_tree_verifiable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "course"
        root.mkdir()
        output = root / "scenario"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
            publish_parent_index=False,
        )
        (output / "plots" / "position.png").write_bytes(b"plot evidence")
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )
        write_run_report(output, update_index=False, completion_status="running")
        logger._write_manifest(status="running")
        old_report = (output / "report.html").read_bytes()
        old_worksheet = (output / "worksheet.md").read_bytes()

        def interrupt_after_terminal_worksheet(*args: object, **kwargs: object) -> str:
            assert (output / "worksheet.md").read_bytes() != old_worksheet
            assert (output / "report.html").read_bytes() == old_report
            raise SystemExit("forced stop after worksheet replacement")

        with (
            patch.object(
                reporting,
                "_render_report",
                side_effect=interrupt_after_terminal_worksheet,
            ),
            pytest.raises(SystemExit, match="forced stop after worksheet replacement"),
        ):
            logger.finalize_artifacts()

        payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "running"
        assert "report.html" not in payload["artifacts"]
        assert "worksheet.md" not in payload["artifacts"]
        assert (output / "worksheet.md").read_bytes() != old_worksheet
        assert (output / "report.html").read_bytes() == old_report
        assert verify_manifest(output) == []

        record = ArtifactRepository(root).get_direct_child(output)
        assert record is not None
        assert not record.report_available
        assert not record.worksheet_available

        write_manifest(
            root,
            scenario_id="batch.all",
            status="stopped",
            config={"batch_name": "all", "plot": True},
            run_kind="comparison_batch",
        )
        assert verify_terminal_batch_output(root, expected_status="stopped") == []
        assert verify_manifest(output) == []


def test_abrupt_running_report_retry_with_previously_trusted_documents_is_verifiable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
            publish_parent_index=False,
        )
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )
        write_run_report(
            output,
            update_index=False,
            completion_status="running",
        )
        logger._write_manifest(status="running")
        trusted = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert {"report.html", "worksheet.md"} <= set(trusted["artifacts"])
        old_worksheet = (output / "worksheet.md").read_bytes()

        (output / "notes.md").write_text("changed retry evidence\n", encoding="utf-8")
        logger._write_manifest(status="running")
        assert verify_manifest(output) == []

        with (
            patch.object(
                reporting,
                "_render_report",
                side_effect=SystemExit("forced stop during running report repair"),
            ),
            pytest.raises(SystemExit, match="forced stop during running report repair"),
        ):
            logger.finalize_artifacts()

        interrupted = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert interrupted["status"] == "running"
        assert "report.html" not in interrupted["artifacts"]
        assert "worksheet.md" not in interrupted["artifacts"]
        assert (output / "worksheet.md").read_bytes() != old_worksheet
        assert verify_manifest(output) == []


def test_failed_report_deferral_never_enters_fallback_document_rewrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
            publish_parent_index=False,
        )
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )
        write_run_report(output, update_index=False, completion_status="running")
        logger._write_manifest(status="running")
        original_manifest = logger._write_manifest
        before_report = (output / "report.html").read_bytes()
        before_worksheet = (output / "worksheet.md").read_bytes()

        def reject_deferral(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            if untrusted_artifacts:
                raise OSError("injected deferral failure")
            return original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )

        with (
            patch.object(logger, "_write_manifest", side_effect=reject_deferral),
            patch("mclab.sim.logging.write_run_report") as rewrite,
            pytest.raises(OSError, match="injected deferral failure"),
        ):
            logger.finalize_artifacts()

        rewrite.assert_not_called()
        assert (output / "report.html").read_bytes() == before_report
        assert (output / "worksheet.md").read_bytes() == before_worksheet
        assert verify_manifest(output) == []


def test_abrupt_concrete_batch_report_rewrite_remains_untrusted() -> None:
    batch_name = "lab01_msd_compare"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "course"
        root.mkdir()
        output = root / "concrete"

        with (
            patch.dict(batch.BATCH_SETS, {batch_name: ()}, clear=False),
            patch("mclab.batch.write_outputs_index"),
            patch.object(
                batch,
                "_render_batch_report",
                side_effect=SystemExit("forced stop after batch worksheet replacement"),
            ),
            pytest.raises(SystemExit, match="forced stop after batch worksheet replacement"),
        ):
            batch.run_batch(
                batch_name,
                output_dir=output,
                plot=False,
                publish_parent_index=False,
            )

        payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "running"
        assert "report.html" not in payload["artifacts"]
        assert "worksheet.md" not in payload["artifacts"]
        assert (output / "worksheet.md").is_file()
        assert not (output / "report.html").exists()
        assert verify_manifest(output) == []
        record = ArtifactRepository(root).get_direct_child(output)
        assert record is not None
        assert not record.report_available
        assert not record.worksheet_available

        write_manifest(
            root,
            scenario_id="batch.all",
            status="stopped",
            config={"batch_name": "all", "plot": False},
            run_kind="comparison_batch",
        )
        assert verify_terminal_batch_output(root, expected_status="stopped") == []
        assert verify_manifest(output) == []


def test_authenticated_settlement_removes_interrupted_root_report_documents() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "data")},
    ):
        output = create_all_compare_output()
        token = read_all_compare_handoff(output)

        with (
            patch("mclab.batch.list_batch_sets", return_value=[]),
            patch("mclab.batch.write_outputs_index"),
            patch.object(
                batch,
                "_render_all_batches_report",
                side_effect=SystemExit("forced stop after course worksheet replacement"),
            ),
            pytest.raises(SystemExit, match="forced stop after course worksheet replacement"),
        ):
            batch.run_all_batches(
                output_dir=output,
                plot=False,
                handoff_token=token,
            )

        running = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert running["status"] == "running"
        assert "report.html" not in running["artifacts"]
        assert "worksheet.md" not in running["artifacts"]
        assert (output / "worksheet.md").is_file()
        assert not (output / "report.html").exists()
        assert verify_manifest(output) == []
        running_record = ArtifactRepository(output.parent).get_direct_child(output)
        assert running_record is not None
        assert not running_record.report_available
        assert not running_record.worksheet_available

        assert settle_all_compare_output(output, token, "stopped") == "stopped"
        assert not (output / "report.html").exists()
        assert not (output / "worksheet.md").exists()
        assert verify_terminal_batch_output(output, expected_status="stopped") == []


def test_authenticated_settlement_removes_manifest_listed_digest_mismatch_pair() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "data")},
    ):
        output = create_all_compare_output()
        token = read_all_compare_handoff(output)
        assert claim_all_compare_handoff(output, token)
        report = output / "report.html"
        worksheet = output / "worksheet.md"
        report.write_text("trusted running report", encoding="utf-8")
        worksheet.write_text("trusted running worksheet", encoding="utf-8")
        write_manifest(
            output,
            scenario_id="batch.all",
            status="running",
            config={"batch_name": "all", "plot": False},
            run_kind="comparison_batch",
        )
        published = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert {"report.html", "worksheet.md"} <= set(published["artifacts"])
        worksheet.write_text("partial prospective terminal worksheet", encoding="utf-8")

        assert settle_all_compare_output(output, token, "stopped") == "stopped"
        assert not report.exists()
        assert not worksheet.exists()
        assert verify_terminal_batch_output(output, expected_status="stopped") == []


def test_authenticated_settlement_terminal_publication_failure_remains_retryable() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "data")},
    ):
        output = create_all_compare_output()
        token = read_all_compare_handoff(output)
        assert claim_all_compare_handoff(output, token)
        report = output / "report.html"
        worksheet = output / "worksheet.md"
        report.write_text("partial prospective terminal report", encoding="utf-8")
        worksheet.write_text("partial prospective terminal worksheet", encoding="utf-8")

        with (
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=OSError("injected terminal publication failure"),
            ),
            pytest.raises(RuntimeError, match="injected terminal publication failure"),
        ):
            settle_all_compare_output(output, token, "stopped")

        running = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert running["status"] == "running"
        assert not report.exists()
        assert not worksheet.exists()
        assert not (output / ".mclab-batch-handoff").exists()
        assert verify_manifest(output) == []

        assert settle_all_compare_output(output, token, "stopped") == "stopped"
        assert verify_terminal_batch_output(output, expected_status="stopped") == []


def test_authenticated_settlement_rejects_root_swap_before_terminal_publication() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "data")},
    ):
        output = create_all_compare_output()
        token = read_all_compare_handoff(output)
        detached = output.with_name(f"{output.name}-detached")
        impostor = output.with_name(f"{output.name}-impostor")
        relocated_impostor = output.with_name(f"{output.name}-relocated-impostor")
        impostor.mkdir()
        sentinel = impostor / "sentinel.txt"
        sentinel.write_text("must remain untouched", encoding="utf-8")
        original_manifest_writer = write_manifest
        swapped = False

        def swap_before_terminal_publication(
            *args: object,
            **kwargs: object,
        ) -> Path:
            nonlocal swapped
            assert kwargs.get("expected_root_identity")
            output.rename(detached)
            impostor.rename(output)
            swapped = True
            return original_manifest_writer(*args, **kwargs)

        with (
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=swap_before_terminal_publication,
            ),
            pytest.raises(RuntimeError),
        ):
            settle_all_compare_output(output, token, "stopped")

        if swapped:
            assert (output / "sentinel.txt").read_text(encoding="utf-8") == (
                "must remain untouched"
            )
            assert not (output / "manifest.json").exists()
            detached_manifest = json.loads(
                (detached / "manifest.json").read_text(encoding="utf-8")
            )
            assert detached_manifest["status"] == "running"
            assert verify_manifest(detached) == []
            output.rename(relocated_impostor)
            detached.rename(output)
            preserved_impostor = relocated_impostor
        else:
            running_manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            assert running_manifest["status"] == "running"
            assert verify_manifest(output) == []
            preserved_impostor = impostor

        assert settle_all_compare_output(output, token, "stopped") == "stopped"
        assert verify_terminal_batch_output(output, expected_status="stopped") == []
        assert (preserved_impostor / "sentinel.txt").read_text(encoding="utf-8") == (
            "must remain untouched"
        )


def test_authenticated_settlement_rejects_root_swap_before_terminal_verification() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "data")},
    ):
        output = create_all_compare_output()
        token = read_all_compare_handoff(output)
        detached = output.with_name(f"{output.name}-detached")
        impostor = output.with_name(f"{output.name}-impostor")
        relocated_impostor = output.with_name(f"{output.name}-relocated-impostor")
        impostor.mkdir()
        write_manifest(
            impostor,
            scenario_id="batch.all",
            status="running",
            config={"batch_name": "all", "plot": True},
            run_kind="comparison_batch",
        )
        write_manifest(
            impostor,
            scenario_id="batch.all",
            status="stopped",
            config={"batch_name": "all", "plot": True},
            run_kind="comparison_batch",
        )
        assert verify_terminal_batch_output(impostor, expected_status="stopped") == []
        original_manifest_writer = write_manifest
        swapped = False

        def swap_after_terminal_publication(
            *args: object,
            **kwargs: object,
        ) -> Path:
            nonlocal swapped
            result = original_manifest_writer(*args, **kwargs)
            output.rename(detached)
            impostor.rename(output)
            swapped = True
            return result

        with (
            patch(
                "mclab.application.artifacts.write_manifest",
                side_effect=swap_after_terminal_publication,
            ),
            pytest.raises(RuntimeError),
        ):
            settle_all_compare_output(output, token, "stopped")

        if swapped:
            assert verify_terminal_batch_output(detached, expected_status="stopped") == []
            assert verify_terminal_batch_output(output, expected_status="stopped") == []
            output.rename(relocated_impostor)
            detached.rename(output)
            preserved_impostor = relocated_impostor
        else:
            assert verify_terminal_batch_output(output, expected_status="stopped") == []
            preserved_impostor = impostor

        assert settle_all_compare_output(output, token, "stopped") == "stopped"
        assert verify_terminal_batch_output(output, expected_status="stopped") == []
        assert verify_terminal_batch_output(
            preserved_impostor,
            expected_status="stopped",
        ) == []


def test_batch_parent_index_observes_terminal_manifest() -> None:
    events: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"

        def write_index(path: str | Path) -> Path:
            target = Path(path)
            events.append("index:local" if target == output else "index:parent")
            return target / "index.html"

        def write_manifest(*_args: object, **kwargs: object) -> Path:
            deferred = kwargs.get("untrusted_artifacts", ())
            assert deferred in ((), ("report.html", "worksheet.md"))
            trust = "deferred" if deferred else "trusted"
            events.append(f"manifest:{kwargs['status']}:{trust}")
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
        "manifest:running:trusted",
        "index:local",
        "manifest:running:deferred",
        "report",
        "manifest:completed:trusted",
        "index:parent",
    ]


def test_nested_full_course_publishes_exactly_seven_indexes() -> None:
    names = tuple(f"unit_{index}" for index in range(5))
    index_paths: list[Path] = []

    def write_index(path: str | Path) -> Path:
        target = Path(path)
        index_paths.append(target)
        return target / "index.html"

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve() / "all"
        with (
            patch.dict(batch.BATCH_SETS, {name: () for name in names}, clear=True),
            patch("mclab.batch.list_batch_sets", return_value=list(names)),
            patch("mclab.batch.write_outputs_index", side_effect=write_index),
            patch("mclab.batch.write_batch_report"),
            patch("mclab.batch.write_all_batches_report"),
        ):
            result = batch.run_all_batches(output_dir=output, plot=False)

    assert result == output
    assert index_paths == [
        *(output / name for name in names),
        output,
        output.parent,
    ]


def test_nested_batch_flushes_local_index_before_terminal_error() -> None:
    scenarios = (
        batch.BatchScenario("first", "lab01", "first.yaml"),
        batch.BatchScenario("second", "lab01", "second.yaml"),
    )
    events: list[str] = []

    def runner(_config: dict[str, object], **kwargs: object) -> Path:
        if Path(kwargs["config_path"]).name == "second.yaml":
            raise RuntimeError("scenario failed")
        return Path(kwargs["output_dir"])

    def write_manifest(*_args: object, **kwargs: object) -> Path:
        deferred = tuple(kwargs.get("untrusted_artifacts", ()))
        assert deferred in ((), ("report.html", "worksheet.md"))
        trust = "deferred" if deferred else "trusted"
        events.append(f"manifest:{kwargs['status']}:{trust}")
        return Path("manifest.json")

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve() / "batch"
        with (
            patch.dict(batch.BATCH_SETS, {"unit": scenarios}, clear=False),
            patch.dict(batch.LAB_RUNNERS, {"lab01": runner}, clear=False),
            patch("mclab.batch.load_config", return_value={}),
            patch(
                "mclab.batch.write_outputs_index",
                side_effect=lambda path: events.append(f"index:{Path(path).name}"),
            ),
            patch(
                "mclab.batch.write_batch_report",
                side_effect=lambda *_args, **kwargs: events.append(
                    f"report:{kwargs.get('completion_status')}"
                ),
            ),
            patch("mclab.application.artifacts.write_manifest", side_effect=write_manifest),
            pytest.raises(RuntimeError, match="scenario failed"),
        ):
            batch.run_batch(
                "unit",
                output_dir=output,
                plot=False,
                publish_parent_index=False,
            )

    assert events == [
        "manifest:running:trusted",
        "index:batch",
        "manifest:running:deferred",
        "report:error",
        "manifest:running:trusted",
        "manifest:error:trusted",
    ]


@pytest.mark.parametrize("course", [False, True], ids=["concrete", "all"])
def test_batch_recovery_never_rewrites_documents_when_deferral_fails(
    course: bool,
) -> None:
    publications: list[tuple[str, tuple[str, ...]]] = []

    def reject_deferral(*_args: object, **kwargs: object) -> Path:
        status = str(kwargs["status"])
        deferred = tuple(kwargs.get("untrusted_artifacts", ()))
        publications.append((status, deferred))
        if deferred:
            raise OSError("injected batch document deferral failure")
        return Path("manifest.json")

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve() / ("all" if course else "batch")
        if course:
            with (
                patch("mclab.batch.list_batch_sets", return_value=[]),
                patch("mclab.batch.write_outputs_index"),
                patch("mclab.batch.write_all_batches_report") as report,
                patch(
                    "mclab.application.artifacts.write_manifest",
                    side_effect=reject_deferral,
                ),
                pytest.raises(
                    OSError,
                    match="injected batch document deferral failure",
                ),
            ):
                batch.run_all_batches(output_dir=output, plot=False)
        else:
            with (
                patch.dict(batch.BATCH_SETS, {"unit": ()}),
                patch("mclab.batch.write_outputs_index"),
                patch("mclab.batch.write_batch_report") as report,
                patch(
                    "mclab.application.artifacts.write_manifest",
                    side_effect=reject_deferral,
                ),
                pytest.raises(
                    OSError,
                    match="injected batch document deferral failure",
                ),
            ):
                batch.run_batch("unit", output_dir=output, plot=False)

    report.assert_not_called()
    assert publications == [
        ("running", ()),
        ("running", ("report.html", "worksheet.md")),
        ("running", ("report.html", "worksheet.md")),
    ]


def test_partial_batch_index_links_the_completed_scenario() -> None:
    scenarios = (
        batch.BatchScenario("first scenario", "lab01", "first.yaml"),
        batch.BatchScenario("second scenario", "lab01", "second.yaml"),
    )

    def runner(config: dict[str, object], **kwargs: object) -> Path:
        config_path = Path(kwargs["config_path"])
        if config_path.name == "second.yaml":
            raise RuntimeError("scenario failed")
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        (output / "summary.json").write_text(
            '{"lab_name":"lab01_msd","config_name":"first"}',
            encoding="utf-8",
        )
        (output / "report.html").write_text("<html></html>", encoding="utf-8")
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config=config,
            config_path=config_path,
        )
        return output

    def error_report(output: Path, *_args: object, **_kwargs: object) -> Path:
        (output / "report.html").write_text("<html>error</html>", encoding="utf-8")
        (output / "worksheet.md").write_text("# Error\n", encoding="utf-8")
        return output / "report.html"

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve() / "batch"
        with (
            patch.dict(batch.BATCH_SETS, {"unit": scenarios}, clear=False),
            patch.dict(batch.LAB_RUNNERS, {"lab01": runner}, clear=False),
            patch("mclab.batch.load_config", return_value={}),
            patch("mclab.batch.write_batch_report", side_effect=error_report),
            pytest.raises(RuntimeError, match="scenario failed"),
        ):
            batch.run_batch(
                "unit",
                output_dir=output,
                plot=False,
                publish_parent_index=False,
            )

        index = (output / "index.html").read_text(encoding="utf-8")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert "first_scenario/report.html" in index
    assert "second_scenario" not in index
    assert manifest["status"] == "error"


def test_partial_index_failure_does_not_mask_the_scenario_error() -> None:
    scenario = batch.BatchScenario("broken", "lab01", "broken.yaml")

    def runner(_config: dict[str, object], **_kwargs: object) -> Path:
        raise RuntimeError("scenario failed")

    with tempfile.TemporaryDirectory() as tmp:
        with (
            patch.dict(batch.BATCH_SETS, {"unit": (scenario,)}, clear=True),
            patch.dict(batch.LAB_RUNNERS, {"lab01": runner}, clear=True),
            patch("mclab.batch.load_config", return_value={}),
            patch("mclab.batch.write_outputs_index", side_effect=OSError("index failed")),
            patch("mclab.batch.write_batch_report"),
            patch("mclab.batch.LOGGER.warning") as warning,
            pytest.raises(RuntimeError, match="scenario failed"),
        ):
            batch.run_batch(
                "unit",
                output_dir=Path(tmp).resolve() / "batch",
                plot=False,
                publish_parent_index=False,
            )

    warning.assert_called_once()


def test_partial_course_index_links_the_completed_batch() -> None:
    names = ("lab01_msd_compare", "lab02_pid_compare")

    def run_batch(batch_name: str, **kwargs: object) -> Path:
        if batch_name == names[1]:
            raise RuntimeError("batch failed")
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        (output / "summary.json").write_text(
            json.dumps({"lab_name": "batch", "config_name": batch_name}),
            encoding="utf-8",
        )
        (output / "report.html").write_text("<html></html>", encoding="utf-8")
        (output / "worksheet.md").write_text("# Batch\n", encoding="utf-8")
        write_manifest(
            output,
            scenario_id=f"batch.{batch_name}",
            status="completed",
            config={"batch_name": batch_name, "plot": False},
            run_kind="comparison_batch",
        )
        return output

    def error_report(output: Path, *_args: object, **_kwargs: object) -> Path:
        (output / "report.html").write_text("<html>error</html>", encoding="utf-8")
        (output / "worksheet.md").write_text("# Error\n", encoding="utf-8")
        return output / "report.html"

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve() / "course"
        with (
            patch("mclab.batch.list_batch_sets", return_value=list(names)),
            patch("mclab.batch.run_batch", side_effect=run_batch),
            patch("mclab.batch.write_all_batches_report", side_effect=error_report),
            pytest.raises(RuntimeError, match="batch failed"),
        ):
            batch.run_all_batches(output_dir=output, plot=False)

        index = (output / "index.html").read_text(encoding="utf-8")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert f"{names[0]}/report.html" in index
    assert names[1] not in index
    assert manifest["status"] == "error"


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


@pytest.mark.parametrize(
    ("write_report", "expected_calls"),
    [(True, 1), (False, 0)],
    ids=["standalone-default", "managed-finalization"],
)
def test_plot_report_refresh_is_default_preserving_and_can_be_deferred(
    write_report: bool,
    expected_calls: int,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {},
            output_dir=output,
            publish_parent_index=False,
        )
        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
            finalize=False,
        )

        with patch("mclab.sim.plotting.write_run_report") as write_report_mock:
            args = (
                output,
                [{"time": 0.0, "position": 0.0}],
                [("position.png", "Position", "x", ("position",))],
            )
            if write_report:
                save_time_series_plots(*args)
            else:
                save_time_series_plots(*args, write_report=False)

        assert (output / "plots" / "position.png").read_bytes().startswith(b"\x89PNG")
        assert write_report_mock.call_count == expected_calls
        if expected_calls:
            write_report_mock.assert_called_once_with(output, update_index=False)
        else:
            logger.finalize_artifacts()
            assert verify_manifest(output) == []
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["status"] == "completed"
            assert {"report.html", "worksheet.md", "plots/position.png"} <= set(
                manifest["artifacts"]
            )
            assert "plots/position.png" in (output / "report.html").read_text(
                encoding="utf-8"
            )


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
    publications: list[tuple[str, tuple[str, ...]]] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "batch"

        def manifest(*_args: object, **kwargs: object) -> Path:
            status = str(kwargs["status"])
            publications.append(
                (status, tuple(kwargs.get("untrusted_artifacts", ())))
            )
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

    assert all(status != "error" for status, _untrusted in publications)
    assert publications[-3:] == [
        ("completed", ()),
        ("running", ("report.html", "worksheet.md")),
        ("running", ()),
    ]


def test_all_completed_publication_failure_recovers_running_not_error() -> None:
    publications: list[tuple[str, tuple[str, ...]]] = []
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "all"

        def manifest(*_args: object, **kwargs: object) -> Path:
            status = str(kwargs["status"])
            publications.append(
                (status, tuple(kwargs.get("untrusted_artifacts", ())))
            )
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

    assert all(status != "error" for status, _untrusted in publications)
    assert publications[-3:] == [
        ("completed", ()),
        ("running", ("report.html", "worksheet.md")),
        ("running", ()),
    ]


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

        def fail_completed_manifest(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            nonlocal terminal_failed
            if status == "completed":
                terminal_failed = True
                raise OSError("completed publication failed")
            return original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )

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


def test_run_successful_fallback_refreshes_documents_after_producer_retry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run"
        logger = RunLogger(
            "lab01_msd",
            {"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            output_dir=output,
            publish_parent_index=False,
        )
        original_manifest = logger._write_manifest
        terminal_failed = False

        def fail_first_completed_manifest(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            nonlocal terminal_failed
            if status == "completed" and not terminal_failed:
                terminal_failed = True
                raise OSError("completed publication failed")
            return original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )

        with (
            patch.object(
                logger,
                "_write_manifest",
                side_effect=fail_first_completed_manifest,
            ),
            pytest.raises(OSError, match="completed publication failed"),
        ):
            logger.save_with_artifacts(
                summary={"lab_name": "lab01_msd", "duration": 1.0, "samples": 1},
                notes="OLD_NOTE",
            )

        _assert_running_recovery_snapshot(output, repaired=True)
        for name in ("report.html", "worksheet.md"):
            assert "OLD_NOTE" in (output / name).read_text(encoding="utf-8")

        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 2.0, "samples": 2},
            notes="NEW_NOTE",
            finalize=False,
        )

        assert verify_manifest(output) == []
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "running"
        assert {"report.html", "worksheet.md"} <= set(manifest["artifacts"])
        for name in ("report.html", "worksheet.md"):
            text = (output / name).read_text(encoding="utf-8")
            assert "NEW_NOTE" in text
            assert "OLD_NOTE" not in text

        logger.save_with_artifacts(
            summary={"lab_name": "lab01_msd", "duration": 3.0, "samples": 3},
            notes="SECOND_RETRY",
            finalize=False,
        )

        assert verify_manifest(output) == []
        second_manifest = json.loads(
            (output / "manifest.json").read_text(encoding="utf-8")
        )
        assert second_manifest["status"] == "running"
        assert {"report.html", "worksheet.md"} <= set(second_manifest["artifacts"])
        for name in ("report.html", "worksheet.md"):
            text = (output / name).read_text(encoding="utf-8")
            assert "SECOND_RETRY" in text
            assert "NEW_NOTE" not in text
            assert "OLD_NOTE" not in text


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

        def manifest_with_first_terminal_failure(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            nonlocal completed_attempts, first_terminal_failed
            if status == "completed":
                completed_attempts += 1
                if completed_attempts == 1:
                    first_terminal_failed = True
                    raise OSError("first completed publication failed")
            manifest = original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )
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

        def manifest_with_terminal_failure(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            nonlocal first_terminal_failed
            if status == "completed":
                first_terminal_failed = True
                raise OSError("completed publication failed")
            manifest = original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )
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
        after_failure = [
            boundary for boundary in boundaries if boundary["after_failure"]
        ]
        assert [boundary["status"] for boundary in after_failure] == ["running"]
        deferred = after_failure[0]
        assert deferred["reason"] == CompletionReason.RUN_NOT_COMPLETED
        assert not deferred["report_available"]
        assert not deferred["worksheet_available"]


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

        def manifest_with_terminal_failure(
            *,
            status: str,
            untrusted_artifacts: tuple[str, ...] = (),
        ) -> Path:
            nonlocal first_terminal_failed
            if status == "completed":
                first_terminal_failed = True
                raise OSError("completed publication failed")
            manifest = original_manifest(
                status=status,
                untrusted_artifacts=untrusted_artifacts,
            )
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
            assert [boundary["status"] for boundary in after_failure] == [
                "running",
                "running",
            ]
            assert all(
                not boundary["report_available"]
                and not boundary["worksheet_available"]
                for boundary in after_failure
            )
            assert all(
                boundary["reason"] == CompletionReason.RUN_NOT_COMPLETED
                for boundary in after_failure
            )
            _assert_running_recovery_snapshot(output, repaired=False)
        else:
            assert [boundary["status"] for boundary in after_failure] == [
                "running",
                "running",
                "running",
            ]
            deferred = after_failure[:2]
            assert all(
                not boundary["report_available"]
                and not boundary["worksheet_available"]
                for boundary in deferred
            )
            assert all(
                boundary["reason"] == CompletionReason.RUN_NOT_COMPLETED
                for boundary in deferred
            )
            boundary = after_failure[-1]
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
        assert [boundary["status"] for boundary in after_failure] == [
            "running",
            "running",
            "error",
        ]
        deferred = after_failure[0]
        assert deferred["reason"] == CompletionReason.RUN_NOT_COMPLETED
        assert not deferred["report_available"]
        assert not deferred["worksheet_available"]
        for boundary in after_failure[1:]:
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
        assert [boundary["status"] for boundary in after_failure] == ["running"]
        deferred = after_failure[0]
        assert deferred["reason"] == CompletionReason.RUN_NOT_COMPLETED
        assert not deferred["report_available"]
        assert not deferred["worksheet_available"]
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
