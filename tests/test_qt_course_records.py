from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from mclab.application.qt_course_records import (
    course_records_or_strict,
    emit_with_course_records,
    result_records_or_strict,
    strict_course_records,
)
from mclab.application.artifacts import write_manifest
from mclab.application.repositories import ArtifactRepository


def test_strict_course_records_reuses_the_full_repository_inventory() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": tmp},
    ):
        root = Path(tmp).resolve() / "outputs"
        output = root / "course"
        output.mkdir(parents=True)
        run = root / "run"
        run.mkdir()
        (run / "summary.json").write_text(
            '{"lab_name":"lab01_msd","config_name":"default"}',
            encoding="utf-8",
        )
        (run / "replay.npz").write_bytes(b"not a valid replay archive")
        write_manifest(
            run,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
        )
        expected = ArtifactRepository(root).list_runs(validate_replays=True)
        original_list_runs = ArtifactRepository.list_runs
        with patch.object(
            ArtifactRepository,
            "list_runs",
            autospec=True,
            side_effect=lambda repository, **kwargs: original_list_runs(
                repository,
                **kwargs,
            ),
        ) as list_runs:
            actual = strict_course_records(str(output))

    assert actual == expected
    assert [record.scenario_id for record in actual] == ["lab01.default"]
    assert not actual[0].replay_available
    assert actual[0].replay_reason
    assert list_runs.call_count == 1
    list_runs.assert_called_once_with(ANY, validate_replays=True)


def test_strict_course_records_rejects_a_non_runtime_root_without_scanning() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {"MCLAB_DATA_DIR": str(Path(tmp) / "runtime")},
    ):
        output = Path(tmp).resolve() / "other" / "course"
        with patch.object(ArtifactRepository, "list_runs") as list_runs:
            assert strict_course_records(str(output)) is None
    list_runs.assert_not_called()


def test_course_records_exist_only_during_synchronous_notification() -> None:
    observed: list[object] = []

    class ResultsChanged:
        def __init__(self, owner: object) -> None:
            self.owner = owner

        def emit(self) -> None:
            observed.append(self.owner._course_records_snapshot)  # type: ignore[attr-defined]

    class Owner:
        _course_records_snapshot: object = "stale"

        def __init__(self) -> None:
            self.results_changed = ResultsChanged(self)

    owner = Owner()
    emit_with_course_records(owner, ())

    assert observed == [()]
    assert owner._course_records_snapshot is None


def test_prevalidated_empty_snapshot_does_not_repeat_repository_scan() -> None:
    with patch.object(ArtifactRepository, "list_runs") as list_runs:
        assert course_records_or_strict(()) == ()
    list_runs.assert_not_called()


def test_missing_snapshot_retains_the_strict_repository_fallback() -> None:
    sentinel = (object(),)
    with patch.object(ArtifactRepository, "list_runs", return_value=sentinel) as list_runs:
        assert course_records_or_strict(None) is sentinel
    list_runs.assert_called_once_with()


def test_results_snapshot_avoids_replay_validation_on_ui_thread() -> None:
    sentinel = (object(),)
    with patch.object(ArtifactRepository, "list_runs") as list_runs:
        assert result_records_or_strict(sentinel) is sentinel
    list_runs.assert_not_called()


def test_missing_results_snapshot_retains_replay_validated_fallback() -> None:
    sentinel = (object(),)
    with patch.object(ArtifactRepository, "list_runs", return_value=sentinel) as list_runs:
        assert result_records_or_strict(None) is sentinel
    list_runs.assert_called_once_with(validate_replays=True)


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
def test_qml_notify_consumes_snapshot_before_it_is_cleared() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Property, QObject, QUrl, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    application = QGuiApplication.instance() or QGuiApplication([])

    class Backend(QObject):
        results_changed = Signal()

        @Property("QVariantList", notify=results_changed)
        def courseRecords(self) -> list[object]:  # noqa: N802
            records = getattr(self, "_course_records_snapshot", None)
            return list(course_records_or_strict(records))

        @Property("QVariantList", notify=results_changed)
        def resultRecords(self) -> list[object]:  # noqa: N802
            records = getattr(self, "_course_records_snapshot", None)
            return list(result_records_or_strict(records))

    backend = Backend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", backend)
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQml\nQtObject {'
        b' property var course: backend.courseRecords;'
        b' property var results: backend.resultRecords;'
        b' property int observedCount: course.length;'
        b' property int observedResultCount: results.length }',
        QUrl(),
    )
    with patch.object(ArtifactRepository, "list_runs", return_value=()):
        root = component.create()
    assert root is not None, component.errorString()
    assert root.property("observedCount") == 0

    with patch.object(
        ArtifactRepository,
        "list_runs",
        side_effect=AssertionError("UI-thread strict inventory repeated"),
    ) as list_runs:
        emit_with_course_records(backend, ("cached",))  # type: ignore[arg-type]
        application.processEvents()

    list_runs.assert_not_called()
    assert root.property("observedCount") == 1
    assert root.property("observedResultCount") == 1
    assert backend._course_records_snapshot is None  # noqa: SLF001
    with patch.object(ArtifactRepository, "list_runs", return_value=()) as list_runs:
        assert backend.resultRecords == []
    list_runs.assert_called_once_with(validate_replays=True)
    root.deleteLater()
    engine.deleteLater()
