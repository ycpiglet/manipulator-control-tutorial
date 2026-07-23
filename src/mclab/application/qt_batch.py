"""Qt process controller factory, imported only after the desktop selects Qt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Any

from mclab.application.batch_runs import (
    BatchProgressBusy,
    all_compare_command,
    batch_manifest_status,
    create_all_compare_output,
    read_all_compare_handoff,
    read_batch_progress,
    settle_all_compare_output,
)
from mclab.application.batch_process import BatchProcessTree, create_batch_process_tree
from mclab.application.repositories import ArtifactRepository
from mclab.application.qt_lifecycle import has_active_experiment, reject_running_experiment

_EXPECTED_BATCHES = (
    "lab01_msd_compare",
    "lab02_pid_compare",
    "lab03_2dof_compare",
    "lab04_cartesian_compare",
    "lab04_wall_compare",
)
_CANCEL_GRACE_MS = 2_000
_TREE_POLL_MS = 50
_START_TIMEOUT_MS = 10_000
_PROGRESS_HANDSHAKE_MS = 30_000
_SHUTDOWN_TERM_MS = 3_000
_SHUTDOWN_KILL_MS = 2_000
_SHUTDOWN_SETTLE_MS = 30_000
_DIAGNOSTIC_TAIL_CHARS = 4_000


@dataclass
class _BatchAttempt:
    generation: int
    output: str
    token: str
    process: Any
    tree: BatchProcessTree
    state: str = "starting"
    cancel_requested: bool = False
    requested_status: str = ""
    exit_code: int | None = None
    progress_sequence: int = 0
    kill_sent: bool = False
    settled: bool = False
    detail: str = ""
    settlement_started: bool = False
    settlement_done: bool = False
    settlement_status: str = ""
    settlement_detail: str = ""
    settlement_thread: threading.Thread | None = None


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
            self._tail = ""
            self._generation = 0
            self._attempt: _BatchAttempt | None = None

        @property
        def running(self) -> bool:
            attempt = self._attempt
            return attempt is not None and not attempt.settled

        def start(self) -> str:
            if self.running:
                raise RuntimeError("The course comparison is already running.")
            output = create_all_compare_output()
            token = read_all_compare_handoff(output)
            self.output = str(output)
            self.current = 0
            self.total = 5
            self.name = ""
            self.cancel_requested = False
            self._settled = False
            self._tail = ""
            self._generation += 1
            process = QProcess(self)
            try:
                tree = create_batch_process_tree(QProcess, process)
            except Exception as exc:
                detail = str(exc) or "The batch process tree could not be created."
                self._settle_unstarted(output, token, detail)
                self._settled = True
                self._attempt = None
                self.process = None
                self.changed.emit()
                self.failed.emit(detail, self.output)
                delete_later = getattr(process, "deleteLater", None)
                if callable(delete_later):
                    delete_later()
                return self.output
            attempt = _BatchAttempt(
                generation=self._generation,
                output=self.output,
                token=token,
                process=process,
                tree=tree,
            )
            self._attempt = attempt
            self.process = process
            try:
                tree.configure()
                program, arguments = all_compare_command(
                    output,
                    worker_arguments=tree.worker_arguments,
                )
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"
                self._settle_attempt(attempt, process)
                return self.output
            process.setProcessChannelMode(QProcess.SeparateChannels)
            process.started.connect(
                lambda attempt=attempt, process=process: self._process_started(attempt, process)
            )
            process.readyReadStandardOutput.connect(
                lambda attempt=attempt, process=process: self._read_diagnostics(attempt, process)
            )
            process.readyReadStandardError.connect(
                lambda attempt=attempt, process=process: self._read_diagnostics(attempt, process)
            )
            process.finished.connect(
                lambda exit_code, exit_status, attempt=attempt, process=process: self._finish(
                    attempt,
                    process,
                    exit_code,
                    exit_status,
                )
            )
            process.errorOccurred.connect(
                lambda error, attempt=attempt, process=process: self._process_error(
                    attempt,
                    process,
                    error,
                )
            )
            try:
                process.start(program, arguments)
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"
                self._settle_attempt(attempt, process)
                return self.output
            self._schedule(
                _START_TIMEOUT_MS,
                attempt,
                process,
                self._start_timeout,
            )
            self.changed.emit()
            return self.output

        def cancel(self) -> None:
            attempt = self._attempt
            if attempt is None or attempt.settled:
                return
            self._request_stop(attempt, attempt.process, requested_status="stopped")

        def shutdown(self) -> bool:
            attempt = self._attempt
            if attempt is None or attempt.settled:
                return True
            process = attempt.process
            self._request_stop(attempt, process, requested_status="stopped", schedule_kill=False)
            self._wait_for_direct_process(process, _SHUTDOWN_TERM_MS)
            if self._tree_active(attempt) or process.state() != QProcess.NotRunning:
                self._kill_attempt(attempt, process, schedule_poll=False)
                self._wait_for_direct_process(process, _SHUTDOWN_KILL_MS)
                self._wait_for_tree(attempt, _SHUTDOWN_KILL_MS)
            if self._tree_active(attempt) or process.state() != QProcess.NotRunning:
                attempt.detail = self._merge_detail(
                    attempt.detail,
                    "The batch process tree did not stop during application shutdown.",
                )
                return False
            self._begin_settlement(attempt, process)
            deadline = time.monotonic() + _SHUTDOWN_SETTLE_MS / 1_000
            while not attempt.settled and time.monotonic() < deadline:
                thread = attempt.settlement_thread
                if thread is not None:
                    thread.join(0.025)
                self._process_application_events()
                if attempt.settlement_done:
                    self._complete_settlement(attempt, process)
            return attempt.settled

        def snapshot(self) -> dict[str, Any]:
            return {
                "running": self.running,
                "cancelling": self.cancel_requested and self.running,
                "current": self.current,
                "total": self.total,
                "name": self.name,
                "output": self.output,
                "state": self._attempt.state if self._attempt is not None else "idle",
                "childPid": self._child_pid(),
            }

        def _smoke_inject_active(self, process: Any, output: str) -> None:
            """Install a non-launching UI fixture after the self-test gate."""

            self._generation += 1
            attempt = _BatchAttempt(
                generation=self._generation,
                output=output,
                token="",
                process=process,
                tree=BatchProcessTree(QProcess, process),
                state="running",
            )
            self._attempt = attempt
            self.process = process
            self.output = output
            self.current = 2
            self.total = 5
            self.name = "lab02_pid_compare"
            self.cancel_requested = False
            self._settled = False

        def _current(self, attempt: _BatchAttempt, process: Any) -> bool:
            return self._attempt is attempt and attempt.process is process and not attempt.settled

        def _schedule(
            self,
            delay_ms: int,
            attempt: _BatchAttempt,
            process: Any,
            callback: Any,
        ) -> None:
            QTimer.singleShot(
                delay_ms,
                lambda attempt=attempt, process=process: callback(attempt, process),
            )

        def _process_started(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            try:
                attempt.tree.attach(int(process.processId()))
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"
                self._kill_attempt(attempt, process)
                return
            attempt.state = "running"
            self._schedule(_TREE_POLL_MS, attempt, process, self._poll_progress)
            self._schedule(
                _PROGRESS_HANDSHAKE_MS,
                attempt,
                process,
                self._progress_handshake_timeout,
            )
            if attempt.cancel_requested:
                self._terminate_attempt(attempt, process)
            self.changed.emit()

        def _start_timeout(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process) or attempt.state != "starting":
                return
            attempt.detail = self._merge_detail(
                attempt.detail,
                "The course comparison process did not start within 10 seconds.",
            )
            attempt.requested_status = "error"
            self._kill_attempt(attempt, process)

        def _read_diagnostics(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            chunks: list[bytes] = []
            try:
                chunks.append(bytes(process.readAllStandardOutput()))
            except (AttributeError, RuntimeError):
                pass
            try:
                chunks.append(bytes(process.readAllStandardError()))
            except (AttributeError, RuntimeError):
                pass
            text = b"".join(chunks).decode("utf-8", errors="replace")
            if text:
                self._tail = (self._tail + text)[-_DIAGNOSTIC_TAIL_CHARS:]

        def _progress_handshake_timeout(
            self,
            attempt: _BatchAttempt,
            process: Any,
        ) -> None:
            if not self._current(attempt, process) or attempt.progress_sequence > 0:
                return
            attempt.detail = self._merge_detail(
                attempt.detail,
                "The batch worker did not publish authenticated progress within 30 seconds.",
            )
            self._request_stop(attempt, process, requested_status="error")

        def _poll_progress(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            if attempt.cancel_requested or attempt.state in {"reaping", "settling"}:
                return
            try:
                events = read_batch_progress(attempt.output, attempt.token)
                for event in events:
                    sequence = int(event.sequence)
                    if sequence <= attempt.progress_sequence:
                        continue
                    expected_sequence = attempt.progress_sequence + 1
                    if sequence != expected_sequence:
                        raise RuntimeError("Batch progress sequence is incomplete or out of order.")
                    current = int(event.current)
                    total = int(event.total)
                    name = str(event.name)
                    if (
                        total != len(_EXPECTED_BATCHES)
                        or current != sequence
                        or current > total
                        or name != _EXPECTED_BATCHES[current - 1]
                    ):
                        raise RuntimeError("Batch progress does not match the five-set course contract.")
                    attempt.progress_sequence = sequence
                    self.current, self.total, self.name = current, total, name
                    self.changed.emit()
            except BatchProgressBusy:
                self._schedule(_TREE_POLL_MS, attempt, process, self._poll_progress)
                return
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                self._request_stop(attempt, process, requested_status="error")
                return
            if attempt.progress_sequence >= len(_EXPECTED_BATCHES):
                return
            self._schedule(_TREE_POLL_MS, attempt, process, self._poll_progress)

        def _request_stop(
            self,
            attempt: _BatchAttempt,
            process: Any,
            *,
            requested_status: str,
            schedule_kill: bool = True,
        ) -> None:
            if not self._current(attempt, process):
                return
            if attempt.cancel_requested:
                if requested_status == "error":
                    attempt.requested_status = "error"
                return
            attempt.cancel_requested = True
            attempt.requested_status = requested_status
            attempt.state = "cancelling"
            self.cancel_requested = True
            self._terminate_attempt(attempt, process)
            if schedule_kill:
                self._schedule(_CANCEL_GRACE_MS, attempt, process, self._kill_attempt)
            self.changed.emit()

        def _terminate_attempt(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            try:
                attempt.tree.terminate()
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"

        def _kill_attempt(
            self,
            attempt: _BatchAttempt,
            process: Any,
            *,
            schedule_poll: bool = True,
        ) -> None:
            if not self._current(attempt, process):
                return
            attempt.kill_sent = True
            attempt.state = "killing"
            try:
                attempt.tree.kill()
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"
            if process.state() != QProcess.NotRunning:
                process.kill()
            if schedule_poll:
                self._schedule(_TREE_POLL_MS, attempt, process, self._poll_tree)
            self.changed.emit()

        def _finish(
            self,
            attempt: _BatchAttempt,
            process: Any,
            exit_code: int,
            _exit_status: Any,
        ) -> None:
            if not self._current(attempt, process):
                return
            self._read_diagnostics(attempt, process)
            attempt.exit_code = int(exit_code)
            attempt.state = "reaping"
            if self._tree_active(attempt):
                if not attempt.cancel_requested:
                    attempt.detail = self._merge_detail(
                        attempt.detail,
                        "The batch leader exited while descendant processes remained active.",
                    )
                    attempt.requested_status = "error"
                    self._kill_attempt(attempt, process)
                else:
                    self._schedule(_TREE_POLL_MS, attempt, process, self._poll_tree)
                return
            self._settle_attempt(attempt, process)

        def _process_error(
            self,
            attempt: _BatchAttempt,
            process: Any,
            _error: Any,
        ) -> None:
            if not self._current(attempt, process):
                return
            if not (
                attempt.cancel_requested and attempt.requested_status == "stopped"
            ):
                detail = process.errorString() or "The course comparison process could not start."
                attempt.detail = self._merge_detail(attempt.detail, detail)
                attempt.requested_status = "error"
            if process.state() == QProcess.NotRunning and not self._tree_active(attempt):
                self._settle_attempt(attempt, process)

        def _poll_tree(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            if process.state() == QProcess.NotRunning and not self._tree_active(attempt):
                self._settle_attempt(attempt, process)
                return
            self._schedule(_TREE_POLL_MS, attempt, process, self._poll_tree)

        def _tree_active(self, attempt: _BatchAttempt) -> bool:
            try:
                return attempt.tree.is_active()
            except Exception as exc:
                attempt.detail = self._merge_detail(attempt.detail, str(exc))
                attempt.requested_status = "error"
                return True

        def _settle_attempt(self, attempt: _BatchAttempt, process: Any) -> None:
            self._begin_settlement(attempt, process)

        def _begin_settlement(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            if process.state() != QProcess.NotRunning or self._tree_active(attempt):
                return
            if attempt.settlement_started:
                return
            attempt.settlement_started = True
            attempt.state = "settling"
            requested_status = attempt.requested_status
            detail = self._merge_detail(attempt.detail, self._tail.strip()[-2_000:])
            exit_code = attempt.exit_code

            def settle() -> None:
                status = ""
                settlement_detail = detail
                desired_status = requested_status
                try:
                    if not desired_status:
                        # ``completed`` is preservation-only: exit code zero
                        # cannot manufacture success.  The worker must already
                        # have published a strict completed terminal manifest.
                        completed_manifest = (
                            batch_manifest_status(attempt.output) == "completed"
                        )
                        desired_status = (
                            "completed"
                            if exit_code == 0 and completed_manifest
                            else "error"
                        )
                    if desired_status == "error" and not settlement_detail:
                        settlement_detail = f"Batch process exited with code {exit_code}."
                    status = settle_all_compare_output(
                        attempt.output,
                        attempt.token,
                        desired_status,
                        error=settlement_detail if desired_status == "error" else "",
                    )
                except Exception as exc:
                    settlement_detail = self._merge_detail(
                        settlement_detail,
                        f"Batch settlement failed: {exc}",
                    )
                if status not in {"completed", "stopped", "error"}:
                    status = "error"
                    settlement_detail = self._merge_detail(
                        settlement_detail,
                        "Batch process exited without a valid terminal manifest.",
                    )
                attempt.settlement_status = status
                attempt.settlement_detail = settlement_detail
                attempt.settlement_done = True

            attempt.settlement_thread = threading.Thread(
                target=settle,
                name=f"mclab-batch-settle-{attempt.generation}",
            )
            attempt.settlement_thread.start()
            self._schedule(_TREE_POLL_MS, attempt, process, self._poll_settlement)

        def _poll_settlement(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            if attempt.settlement_done:
                self._complete_settlement(attempt, process)
                return
            self._schedule(_TREE_POLL_MS, attempt, process, self._poll_settlement)

        def _complete_settlement(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process) or not attempt.settlement_done:
                return
            if attempt.state == "containment_error":
                return
            self._publish_result(
                attempt,
                process,
                attempt.settlement_status,
                attempt.settlement_detail,
            )

        @staticmethod
        def _process_application_events() -> None:
            try:
                from PySide6.QtCore import QCoreApplication

                QCoreApplication.processEvents()
            except (ImportError, RuntimeError):
                pass

        def _wait_for_direct_process(self, process: Any, timeout_ms: int) -> bool:
            deadline = time.monotonic() + max(0, timeout_ms) / 1_000
            while process.state() != QProcess.NotRunning and time.monotonic() < deadline:
                remaining_ms = max(1, round((deadline - time.monotonic()) * 1_000))
                process.waitForFinished(min(25, remaining_ms))
                self._process_application_events()
            return process.state() == QProcess.NotRunning

        def _wait_for_tree(self, attempt: _BatchAttempt, timeout_ms: int) -> bool:
            deadline = time.monotonic() + max(0, timeout_ms) / 1_000
            while self._tree_active(attempt) and time.monotonic() < deadline:
                time.sleep(0.01)
                self._process_application_events()
            return not self._tree_active(attempt)

        def _settle_unstarted(self, output: Path, token: str, detail: str) -> None:
            try:
                settle_all_compare_output(output, token, "error", error=detail)
            except Exception:
                pass

        def _publish_result(
            self,
            attempt: _BatchAttempt,
            process: Any,
            status: str,
            detail: str,
        ) -> None:
            if not self._current(attempt, process):
                return
            try:
                attempt.tree.close(require_empty=True)
            except Exception as exc:
                attempt.settlement_status = "error"
                attempt.settlement_detail = self._merge_detail(detail, str(exc))
                attempt.state = "containment_error"
                try:
                    attempt.tree.kill()
                    if process.state() != QProcess.NotRunning:
                        process.kill()
                except Exception as kill_exc:
                    attempt.settlement_detail = self._merge_detail(
                        attempt.settlement_detail,
                        str(kill_exc),
                    )
                self._schedule(_TREE_POLL_MS, attempt, process, self._retry_publication)
                self.changed.emit()
                return
            attempt.settled = True
            attempt.state = status
            self._settled = True
            self.cancel_requested = False
            self.process = None
            self.changed.emit()
            if status == "completed":
                self.completed.emit(attempt.output)
            elif status == "stopped":
                self.stopped.emit(attempt.output)
            else:
                self.failed.emit(detail or "The course comparison failed.", attempt.output)
            delete_later = getattr(process, "deleteLater", None)
            if callable(delete_later):
                delete_later()

        def _retry_publication(self, attempt: _BatchAttempt, process: Any) -> None:
            if not self._current(attempt, process):
                return
            if process.state() != QProcess.NotRunning or self._tree_active(attempt):
                try:
                    attempt.tree.kill()
                    if process.state() != QProcess.NotRunning:
                        process.kill()
                except Exception as exc:
                    attempt.settlement_detail = self._merge_detail(
                        attempt.settlement_detail,
                        str(exc),
                    )
                self._schedule(_TREE_POLL_MS, attempt, process, self._retry_publication)
                return
            self._publish_result(
                attempt,
                process,
                attempt.settlement_status,
                attempt.settlement_detail,
            )

        def _child_pid(self) -> int:
            attempt = self._attempt
            if attempt is None or attempt.settled:
                return 0
            try:
                return int(attempt.process.processId())
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return 0

        @staticmethod
        def _merge_detail(current: str, addition: str) -> str:
            addition = addition.strip()
            if not addition or addition in current:
                return current[-2_000:]
            return f"{current}\n{addition}".strip()[-2_000:]

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

        def _shutdown_batch(self) -> bool:
            return bool(self._batch.shutdown())

    return BatchBackendMixin
