"""Qt process controller factory, imported only after the desktop selects Qt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.application.batch_runs import (
    all_compare_command,
    batch_manifest_status,
    create_all_compare_output,
    parse_batch_progress,
    update_batch_manifest,
)
from mclab.application.repositories import ArtifactRepository
from mclab.application.qt_lifecycle import has_active_experiment, reject_running_experiment


def create_batch_controller(
    QObject: Any,
    QProcess: Any,
    QTimer: Any,
    Signal: Any,
) -> type:
    class BatchController(QObject):
        changed = Signal()
        completed = Signal(str)
        stopped = Signal(str)
        failed = Signal(str, str)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self.process: Any = None
            self.output = ""
            self.current = 0
            self.total = 5
            self.name = ""
            self.cancel_requested = False
            self._settled = True
            self._text = ""
            self._tail = ""

        @property
        def running(self) -> bool:
            return self.process is not None and self.process.state() != QProcess.NotRunning

        def start(self) -> str:
            if self.running:
                raise RuntimeError("The course comparison is already running.")
            output = create_all_compare_output()
            program, arguments = all_compare_command(output)
            self.output = str(output)
            self.current = 0
            self.total = 5
            self.name = ""
            self.cancel_requested = False
            self._settled = False
            self._text = ""
            self._tail = ""
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._read_output)
            self.process.finished.connect(self._finish)
            self.process.errorOccurred.connect(self._process_error)
            self.process.start(program, arguments)
            self.changed.emit()
            return self.output

        def cancel(self) -> None:
            if not self.running:
                return
            self.cancel_requested = True
            self.process.terminate()
            QTimer.singleShot(2000, self._kill_if_running)
            self.changed.emit()

        def shutdown(self) -> None:
            if not self.running:
                return
            self.cancel_requested = True
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(1000)

        def snapshot(self) -> dict[str, Any]:
            return {
                "running": self.running,
                "cancelling": self.cancel_requested and self.running,
                "current": self.current,
                "total": self.total,
                "name": self.name,
                "output": self.output,
            }

        def _read_output(self) -> None:
            chunk = bytes(self.process.readAllStandardOutput()).decode(
                "utf-8", errors="replace"
            )
            self._tail = (self._tail + chunk)[-4000:]
            self._text += chunk
            lines = self._text.splitlines(keepends=True)
            self._text = lines.pop() if lines and not lines[-1].endswith(("\n", "\r")) else ""
            for line in lines:
                parsed = parse_batch_progress(line.strip())
                if parsed is not None:
                    self.current, self.total, self.name = parsed
                    self.changed.emit()

        def _finish(self, exit_code: int, _exit_status: Any) -> None:
            self._read_output()
            if self._settled:
                return
            terminal_status = batch_manifest_status(self.output)
            if terminal_status:
                status = terminal_status
            elif self.cancel_requested:
                status = "stopped"
            else:
                status = "completed" if exit_code == 0 else "error"
            detail = self._tail.strip()[-2000:]
            if status == "completed" and terminal_status != "completed":
                status = "error"
                detail = (
                    detail + "\nBatch process exited without a completed manifest."
                ).strip()
            if not terminal_status:
                update_batch_manifest(
                    self.output,
                    status=status,
                    error=detail if status == "error" else "",
                )
            self._settled = True
            self.changed.emit()
            if status == "completed":
                self.completed.emit(self.output)
            elif status == "stopped":
                self.stopped.emit(self.output)
            elif status == "error":
                self.failed.emit(detail or f"Batch process exited with code {exit_code}.", self.output)

        def _process_error(self, _error: Any) -> None:
            if self._settled or self.running or self.cancel_requested:
                return
            detail = self.process.errorString() or "The course comparison process could not start."
            terminal_status = batch_manifest_status(self.output)
            if terminal_status:
                self._settled = True
                self.changed.emit()
                if terminal_status == "completed":
                    self.completed.emit(self.output)
                elif terminal_status == "stopped":
                    self.stopped.emit(self.output)
                else:
                    self.failed.emit(detail, self.output)
                return
            update_batch_manifest(self.output, status="error", error=detail)
            self._settled = True
            self.changed.emit()
            self.failed.emit(detail, self.output)

        def _kill_if_running(self) -> None:
            if self.running:
                self.process.kill()

    return BatchController


def create_batch_backend_mixin(QObject: Any, Property: Any, Signal: Any, Slot: Any) -> type:
    class BatchBackendMixin(QObject):
        batch_changed = Signal()

        def _init_batch(self, controller: Any) -> None:
            self._batch = controller
            controller.changed.connect(self.batch_changed.emit)
            controller.completed.connect(self._batch_completed)
            controller.stopped.connect(self._batch_stopped)
            controller.failed.connect(self._batch_failed)

        @Property("QVariantMap", notify=batch_changed)
        def batchProgress(self) -> dict[str, Any]:  # noqa: N802
            snapshot = self._batch.snapshot()
            name = str(snapshot.get("name", ""))
            snapshot["label"] = (
                self.translator.text(f"path.batch_set.{name}") if name else ""
            )
            return snapshot

        @Slot()
        def startCourseNext(self) -> None:  # noqa: N802
            course = self.courseProgress
            if course["complete"]:
                self.navigate("results")
            elif course["nextKind"] == "batch":
                self.startAllCompare()
            else:
                self.startScenario(str(course["nextId"]))

        @Slot()
        def startAllCompare(self) -> None:  # noqa: N802
            if self._batch.running:
                self._set_error(
                    "The course comparison is already running.",
                    "Use Cancel comparison or wait for the five sets to finish.",
                )
                return
            if reject_running_experiment(self):
                return
            try:
                self._batch.start()
                self.results_changed.emit()
            except Exception as exc:
                self._set_error(str(exc), self.translator.text("path.batch_recovery"))

        @Slot()
        def cancelBatch(self) -> None:  # noqa: N802
            self._batch.cancel()

        @Slot(str, str, str, result=bool)
        def deleteRun(  # noqa: N802
            self,
            run_path: str,
            confirm_path: str,
            cleanup_token: str,
        ) -> bool:
            if has_active_experiment(self):
                self._set_error(
                    "Saved evidence cannot be moved to quarantine while an experiment is active.",
                    "Return to the active experiment, or end and save it before starting another.",
                )
                return False
            if self._batch.running and Path(run_path).resolve() == Path(self._batch.output).resolve():
                self._set_error(
                    "The active course comparison cannot be moved to quarantine.",
                    "Cancel the comparison and wait for it to stop before cleanup.",
                )
                return False
            try:
                ArtifactRepository().delete_path(
                    run_path,
                    confirm_path=confirm_path,
                    cleanup_token=cleanup_token,
                )
            except Exception as exc:
                self._set_error(str(exc), self.translator.text("results.delete_recovery"))
                return False
            else:
                self.results_changed.emit()
                return True

        def _batch_completed(self, output: str) -> None:
            self._last_output = output
            self.results_changed.emit()

        def _batch_stopped(self, output: str) -> None:
            self._last_output = output
            self.results_changed.emit()

        def _batch_failed(self, detail: str, output: str) -> None:
            self._last_output = output
            self.results_changed.emit()
            self._set_error(detail, self.translator.text("path.batch_recovery"))

        def _shutdown_batch(self) -> None:
            self._batch.shutdown()

    return BatchBackendMixin
