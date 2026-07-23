from __future__ import annotations

import json
import importlib.util
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application import batch_worker  # noqa: E402
from mclab.application.batch_process import (  # noqa: E402
    PosixBatchProcessTree,
    ProcessContainmentError,
    WindowsBatchProcessTree,
)
from mclab.application.qt_batch_probe import (  # noqa: E402
    _BatchLifecycleProbe,
    _read_batch_probe_request,
)


class _ProcessType:
    NotRunning = 0


class _Process:
    def __init__(self, state: int = 1) -> None:
        self.current_state = state
        self.killed = 0
        self.waited: list[int] = []

    def state(self) -> int:
        return self.current_state

    def kill(self) -> None:
        self.killed += 1
        self.current_state = _ProcessType.NotRunning

    def terminate(self) -> None:
        self.current_state = _ProcessType.NotRunning

    def waitForFinished(self, timeout_ms: int) -> bool:  # noqa: N802
        self.waited.append(timeout_ms)
        return self.current_state == _ProcessType.NotRunning


class _WindowsApi:
    def __init__(self) -> None:
        self.job = object()
        self.event = object()
        self.active = 1
        self.assign_error: Exception | None = None
        self.assigned: list[int] = []
        self.terminated = 0
        self.closed: list[object] = []
        self.queries = 0
        self.calls: list[str] = []

    def create_job(self) -> object:
        self.calls.append("create_job")
        return self.job

    def create_event(self, _name: str) -> object:
        self.calls.append("create_event")
        return self.event

    def assign(self, _job: object, pid: int) -> None:
        self.calls.append("assign")
        if self.assign_error is not None:
            raise self.assign_error
        self.assigned.append(pid)

    def release_event(self, _event: object) -> None:
        self.calls.append("release")
        return None

    def active_processes(self, _job: object) -> int:
        self.queries += 1
        return self.active

    def terminate(self, _job: object) -> None:
        self.terminated += 1
        self.active = 0

    def close_handle(self, handle: object) -> None:
        self.closed.append(handle)


class BatchContainmentTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX process groups are unavailable")
    def test_posix_configures_new_session_and_guards_group_identity(self) -> None:
        class PosixProcessType:
            NotRunning = 0

            class UnixProcessFlag:
                CreateNewSession = 8

            class UnixProcessParameters:
                def __init__(self) -> None:
                    self.flags = 0

        class PosixProcess(_Process):
            parameters: object | None = None

            def setUnixProcessParameters(self, parameters: object) -> None:  # noqa: N802
                self.parameters = parameters

        process = PosixProcess()
        tree = PosixBatchProcessTree(PosixProcessType, process)
        tree.configure()
        self.assertEqual(process.parameters.flags, 8)
        with (
            patch("mclab.application.batch_process.os.getpgid", return_value=4123),
            patch("mclab.application.batch_process.os.getsid", return_value=4123),
            patch("mclab.application.batch_process.os.getpgrp", return_value=99),
        ):
            tree.attach(4123)
        with patch("mclab.application.batch_process.os.killpg") as kill_group:
            tree.kill()
        kill_group.assert_called_once()

        tree.pgid = 99
        with patch("mclab.application.batch_process.os.getpgrp", return_value=99):
            with self.assertRaisesRegex(ProcessContainmentError, "Refusing"):
                tree.kill()

    def test_windows_zero_job_count_still_requires_qprocess_reaping(self) -> None:
        process = _Process(state=1)
        api = _WindowsApi()
        tree = WindowsBatchProcessTree(_ProcessType, process, api=api)
        tree.attach(4312)
        self.assertEqual(
            api.calls[:4],
            ["create_job", "create_event", "assign", "release"],
        )
        self.assertEqual(
            tree.worker_arguments,
            ("--start-event", tree._event_name),  # noqa: SLF001
        )
        api.active = 0

        self.assertTrue(tree.is_active())
        process.current_state = _ProcessType.NotRunning
        self.assertFalse(tree.is_active())

        tree.close()
        queries_after_close = api.queries
        tree.close()
        self.assertEqual(api.queries, queries_after_close)
        self.assertCountEqual(api.closed, [api.event, api.job])

    def test_windows_attach_failure_kills_and_waits_unassigned_leader(self) -> None:
        process = _Process(state=1)
        api = _WindowsApi()
        api.assign_error = OSError("injected assignment failure")
        tree = WindowsBatchProcessTree(_ProcessType, process, api=api)

        with self.assertRaises(ProcessContainmentError):
            tree.attach(8123)

        self.assertEqual(process.killed, 1)
        self.assertEqual(process.waited, [2_000])
        self.assertEqual(process.state(), _ProcessType.NotRunning)
        self.assertEqual(api.terminated, 0)
        tree.close()


class BatchWorkerTests(unittest.TestCase):
    def test_global_quit_filter_vetoes_failed_shutdown(self) -> None:
        from mclab.application.qt_lifecycle import create_shutdown_event_filter

        class QObject:
            def __init__(self, _parent: object = None) -> None:
                return None

        class QEvent:
            class Type:
                Quit = 20

        class Event:
            def __init__(self, kind: int) -> None:
                self.kind = kind

            def type(self) -> int:
                return self.kind

        class Backend:
            safe = False
            raises = False

            def shutdown(self) -> bool:
                if self.raises:
                    raise RuntimeError("injected shutdown failure")
                return self.safe

        backend = Backend()
        event_filter = create_shutdown_event_filter(QObject, QEvent)(backend)
        self.assertTrue(event_filter.eventFilter(None, Event(QEvent.Type.Quit)))
        self.assertFalse(event_filter.eventFilter(None, Event(10)))
        backend.raises = True
        self.assertTrue(event_filter.eventFilter(None, Event(QEvent.Type.Quit)))
        backend.raises = False
        backend.safe = True
        self.assertFalse(event_filter.eventFilter(None, Event(QEvent.Type.Quit)))

    def test_main_window_vetoes_close_when_shutdown_is_not_safe(self) -> None:
        source = (ROOT / "src/mclab/application/qml/Main.qml").read_text(encoding="utf-8")
        self.assertIn("onClosing: function(close)", source)
        self.assertIn("if (!backend.shutdown())", source)
        self.assertIn("close.accepted = false", source)

    def test_packaged_entrypoint_installs_stdio_before_cli_import(self) -> None:
        source = (ROOT / "packaging/entrypoint.py").read_text(encoding="utf-8")
        ensure_call = source.index("    ensure_standard_streams()")
        worker_route = source.index('arguments[:1] == ["__batch-worker"]')
        cli_import = source.index("    from mclab.cli import main")
        self.assertLess(ensure_call, worker_route)
        self.assertLess(worker_route, cli_import)

    def test_hidden_worker_requires_windows_gate_and_rejects_it_elsewhere(self) -> None:
        with patch.object(batch_worker.os, "name", "nt"):
            with self.assertRaisesRegex(RuntimeError, "required"):
                batch_worker._wait_for_windows_start_event("")  # noqa: SLF001
        with patch.object(batch_worker.os, "name", "posix"):
            with self.assertRaisesRegex(RuntimeError, "non-Windows"):
                batch_worker._wait_for_windows_start_event(  # noqa: SLF001
                    "Local\\MCLabBatch-" + "a" * 32
                )

    def test_worker_forwards_only_batch_all_after_private_gate_arguments(self) -> None:
        event = "Local\\MCLabBatch-" + "b" * 32
        parsed_event, forwarded = batch_worker._worker_arguments(  # noqa: SLF001
            ["--start-event", event, "batch", "all", "--plot"]
        )
        self.assertEqual(parsed_event, event)
        self.assertEqual(forwarded, ["batch", "all", "--plot"])
        with self.assertRaises(ValueError):
            batch_worker._worker_arguments(["run", "lab01"])  # noqa: SLF001

    def test_stdio_fallback_replaces_only_none_for_process_lifetime(self) -> None:
        original_stdout = sys.stdout
        before = len(batch_worker._DEVNULL_STREAMS)  # noqa: SLF001
        try:
            with patch.object(sys, "stdin", None), patch.object(sys, "stderr", None):
                batch_worker.ensure_standard_streams()
                self.assertIsNotNone(sys.stdin)
                self.assertIs(sys.stdout, original_stdout)
                self.assertIsNotNone(sys.stderr)
                self.assertFalse(sys.stdin.closed)
                self.assertFalse(sys.stderr.closed)
        finally:
            created = batch_worker._DEVNULL_STREAMS[before:]  # noqa: SLF001
            del batch_worker._DEVNULL_STREAMS[before:]  # noqa: SLF001
            for stream in created:
                stream.close()


class BatchProbeTests(unittest.TestCase):
    def test_request_requires_exact_bounded_regular_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = Path(tmp) / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "schema": "mclab.batch-probe-request.v1",
                        "action": "cancel",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                _read_batch_probe_request(
                    request,
                    "cancel",
                    max_bytes=1_024,
                    schema="mclab.batch-probe-request.v1",
                )
            )
            request.write_text(
                json.dumps(
                    {
                        "schema": "mclab.batch-probe-request.v1",
                        "action": "cancel",
                        "token": "must-not-be-accepted",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                _read_batch_probe_request(
                    request,
                    "cancel",
                    max_bytes=1_024,
                    schema="mclab.batch-probe-request.v1",
                )
            request.write_bytes(
                b'{"schema":"mclab.batch-probe-request.v1",'
                b'"schema":"mclab.batch-probe-request.v1","action":"cancel"}'
            )
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                _read_batch_probe_request(
                    request,
                    "cancel",
                    max_bytes=1_024,
                    schema="mclab.batch-probe-request.v1",
                )

    @unittest.skipUnless(
        importlib.util.find_spec("PySide6"),
        "PySide6 is not installed",
    )
    def test_ready_probe_is_written_once_without_heartbeat_fsync(self) -> None:
        class Signal:
            def connect(self, _callback: object) -> None:
                return None

        class Controller:
            changed = completed = stopped = failed = Signal()
            running = True

            @staticmethod
            def snapshot() -> dict[str, object]:
                return {
                    "output": output,
                    "childPid": 2345,
                    "current": 1,
                    "total": 5,
                    "name": "lab01_msd_compare",
                    "state": "running",
                    "cancelling": False,
                }

        class Backend:
            _batch = Controller()

        class Timer:
            callbacks: list[object] = []

            @classmethod
            def singleShot(cls, _delay: int, callback: object) -> None:  # noqa: N802
                cls.callbacks.append(callback)

        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "mclab-batch")
            ready = Path(tmp) / "ready.json"
            probe_path = Path(tmp) / "probe.json"
            with (
                patch.dict(
                    os.environ,
                    {
                        "MCLAB_BATCH_PROBE_PATH": str(probe_path),
                        "MCLAB_BATCH_READY_PATH": str(ready),
                        "MCLAB_BATCH_REQUEST_PATH": str(Path(tmp) / "request.json"),
                    },
                ),
                patch("mclab.application.qt_batch_probe._atomic_probe_write") as write,
            ):
                lifecycle = _BatchLifecycleProbe(
                    Timer, Backend(), None, "batch_probe_complete"
                )
                lifecycle.started_at = lifecycle.last_heartbeat = time.monotonic()
                lifecycle._changed()  # noqa: SLF001
                lifecycle._heartbeat()  # noqa: SLF001

        self.assertTrue(lifecycle.ready)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(write.call_args.args[0], ready)
        self.assertNotEqual(write.call_args.args[0], probe_path)
        self.assertEqual(len(Timer.callbacks), 1)

    @unittest.skipUnless(
        importlib.util.find_spec("PySide6"),
        "PySide6 is not installed",
    )
    def test_terminal_probe_includes_gap_since_last_heartbeat(self) -> None:
        class Signal:
            def connect(self, _callback: object) -> None:
                return None

        class Controller:
            changed = completed = stopped = failed = Signal()
            running = False

            def snapshot(self) -> dict[str, object]:
                return {
                    "output": self.output,
                    "childPid": 2345,
                    "current": 5,
                    "total": 5,
                    "name": "lab04_wall_compare",
                    "state": "completed",
                    "cancelling": False,
                }

            output = ""

        class Backend:
            _batch = Controller()

        class Timer:
            @staticmethod
            def singleShot(_delay: int, _callback: object) -> None:  # noqa: N802
                return None

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "MCLAB_BATCH_PROBE_PATH": str(Path(tmp) / "probe.json"),
                "MCLAB_BATCH_READY_PATH": str(Path(tmp) / "ready.json"),
                "MCLAB_BATCH_REQUEST_PATH": str(Path(tmp) / "request.json"),
            },
        ):
            Backend._batch.output = str(Path(tmp) / "mclab-batch")
            probe = _BatchLifecycleProbe(Timer, Backend(), None, "batch_probe_complete")
            probe.started_at = 10.0
            probe.last_heartbeat = 12.0
            probe.current = 5
            probe.ready = True
            probe.progress = [
                {
                    "current": 5,
                    "total": 5,
                    "name": "lab04_wall_compare",
                    "elapsed_ms": 2_000.0,
                }
            ]
            written: list[dict[str, object]] = []
            with (
                patch("mclab.application.qt_batch_probe.time.monotonic", return_value=12.75),
                patch(
                    "mclab.application.qt_batch_probe._atomic_probe_write",
                    side_effect=lambda _path, payload, _bound: written.append(payload),
                ),
                patch("PySide6.QtCore.QCoreApplication.quit"),
            ):
                probe._finish("completed", Backend._batch.output, "")  # noqa: SLF001

        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["phase"], "terminal")
        self.assertEqual(written[0]["max_ui_gap_ms"], 750.0)
        self.assertTrue(written[0]["settled"])


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
class BatchControllerLifecycleTests(unittest.TestCase):
    @staticmethod
    def _controller_type() -> tuple[object, object, object]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QObject, QProcess, QTimer, Signal
        from PySide6.QtGui import QGuiApplication

        from mclab.application.qt_batch import create_batch_controller

        application = QGuiApplication.instance() or QGuiApplication([])
        return create_batch_controller(QObject, QProcess, QTimer, Signal), QProcess, application

    def test_real_qt_quit_event_is_vetoed_when_shutdown_raises(self) -> None:
        from PySide6.QtCore import QEvent, QObject, QTimer
        from PySide6.QtGui import QGuiApplication

        from mclab.application.qt_lifecycle import create_shutdown_event_filter

        application = QGuiApplication.instance() or QGuiApplication([])

        class Backend:
            calls = 0

            def shutdown(self) -> bool:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected shutdown failure")
                return True

        backend = Backend()
        event_filter = create_shutdown_event_filter(QObject, QEvent)(backend, application)
        application.installEventFilter(event_filter)
        survived_first_quit: list[bool] = []

        def safe_quit() -> None:
            survived_first_quit.append(True)
            application.quit()

        QTimer.singleShot(0, application.quit)
        QTimer.singleShot(20, safe_quit)
        application.exec()
        application.removeEventFilter(event_filter)

        self.assertEqual(survived_first_quit, [True])
        self.assertEqual(backend.calls, 2)

    def test_settlement_is_async_and_double_callbacks_publish_once(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, application = self._controller_type()

        class Process:
            deleted = 0

            @staticmethod
            def state() -> object:
                return process_type.NotRunning

            def deleteLater(self) -> None:  # noqa: N802
                self.deleted += 1

        class Tree:
            closed = 0

            @staticmethod
            def is_active() -> bool:
                return False

            @staticmethod
            def kill() -> None:
                return None

            def close(self, *, require_empty: bool = True) -> None:
                self.closed += 1

        process = Process()
        tree = Tree()
        controller = controller_type()
        output = str((ROOT / ".batch-lifecycle-test").resolve())
        attempt = _BatchAttempt(1, output, "a" * 64, process, tree, exit_code=0)
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001
        completed: list[str] = []
        controller.completed.connect(completed.append)
        release = threading.Event()

        def settle(*_args: object, **_kwargs: object) -> str:
            release.wait(5)
            return "completed"

        with (
            patch("mclab.application.qt_batch.batch_manifest_status", return_value="completed"),
            patch("mclab.application.qt_batch.settle_all_compare_output", side_effect=settle),
        ):
            started = time.monotonic()
            controller._settle_attempt(attempt, process)  # noqa: SLF001
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertTrue(controller.running)
            self.assertEqual(completed, [])
            release.set()
            attempt.settlement_thread.join(2)
            controller._complete_settlement(attempt, process)  # noqa: SLF001
            controller._complete_settlement(attempt, process)  # noqa: SLF001
            controller._process_error(attempt, process, None)  # noqa: SLF001
            application.processEvents()

        self.assertEqual(completed, [output])
        self.assertEqual(tree.closed, 1)
        self.assertEqual(process.deleted, 1)
        self.assertFalse(controller.running)

    def test_smoke_fixture_shutdown_never_writes_batch_artifacts(self) -> None:
        controller_type, process_type, _application = self._controller_type()

        class Process:
            def __init__(self) -> None:
                self.active = True

            def state(self) -> object:
                return process_type.Running if self.active else process_type.NotRunning

            def terminate(self) -> None:
                self.active = False

            @staticmethod
            def waitForFinished(_timeout: int) -> bool:  # noqa: N802
                return True

            def kill(self) -> None:
                self.active = False

        controller = controller_type()
        stopped: list[str] = []
        controller.stopped.connect(stopped.append)
        controller._smoke_inject_active(Process(), "")  # noqa: SLF001

        with patch("mclab.application.qt_batch.settle_all_compare_output") as settle:
            self.assertTrue(controller.shutdown())

        settle.assert_not_called()
        self.assertEqual(stopped, [""])
        self.assertFalse(controller.running)

    def test_progress_lock_contention_reschedules_without_cancelling(self) -> None:
        from mclab.application.batch_runs import BatchProgressBusy, BatchProgressEvent
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, _process_type, _application = self._controller_type()
        process = object()
        controller = controller_type()
        attempt = _BatchAttempt(
            1,
            str((ROOT / ".batch-progress-lock-test").resolve()),
            "a" * 64,
            process,
            object(),
            state="running",
        )
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001
        event = BatchProgressEvent(1, 1, 5, "lab01_msd_compare")

        with (
            patch(
                "mclab.application.qt_batch.read_batch_progress",
                side_effect=[BatchProgressBusy("peer writer"), (event,)],
            ),
            patch.object(controller, "_schedule") as schedule,
            patch.object(controller, "_request_stop") as request_stop,
        ):
            controller._poll_progress(attempt, process)  # noqa: SLF001
            self.assertFalse(attempt.cancel_requested)
            self.assertEqual(attempt.detail, "")
            self.assertEqual(attempt.progress_sequence, 0)
            controller._poll_progress(attempt, process)  # noqa: SLF001

        request_stop.assert_not_called()
        self.assertEqual(schedule.call_count, 2)
        self.assertEqual(attempt.progress_sequence, 1)
        self.assertEqual(controller.current, 1)
        self.assertEqual(controller.name, "lab01_msd_compare")

    def test_natural_exit_waits_for_containment_accounting_to_quiesce(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, _application = self._controller_type()

        class Process:
            @staticmethod
            def state() -> object:
                return process_type.NotRunning

            @staticmethod
            def readAllStandardOutput() -> bytes:  # noqa: N802
                return b""

            @staticmethod
            def readAllStandardError() -> bytes:  # noqa: N802
                return b""

        class Tree:
            observations = iter((True, False))

            def is_active(self) -> bool:
                return next(self.observations)

        process = Process()
        controller = controller_type()
        attempt = _BatchAttempt(1, "/batch", "a" * 64, process, Tree(), state="running")
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001

        with (
            patch("mclab.application.qt_batch.time.monotonic", return_value=100.0),
            patch.object(controller, "_schedule") as schedule,
            patch.object(controller, "_settle_attempt") as settle,
            patch.object(controller, "_kill_attempt") as kill,
        ):
            controller._finish(attempt, process, 0, None)  # noqa: SLF001
            scheduled_callback = schedule.call_args.args[3]
            scheduled_callback(attempt, process)

        settle.assert_called_once_with(attempt, process)
        kill.assert_not_called()
        self.assertEqual(attempt.requested_status, "")
        self.assertEqual(attempt.reap_deadline, 101.0)

    def test_natural_exit_kills_persistent_descendants_after_grace(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, _application = self._controller_type()

        class Process:
            @staticmethod
            def state() -> object:
                return process_type.NotRunning

            @staticmethod
            def readAllStandardOutput() -> bytes:  # noqa: N802
                return b""

            @staticmethod
            def readAllStandardError() -> bytes:  # noqa: N802
                return b""

        class Tree:
            @staticmethod
            def is_active() -> bool:
                return True

        process = Process()
        controller = controller_type()
        attempt = _BatchAttempt(1, "/batch", "a" * 64, process, Tree(), state="running")
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001

        with (
            patch("mclab.application.qt_batch.time.monotonic", side_effect=(100.0, 102.0)),
            patch.object(controller, "_schedule") as schedule,
            patch.object(controller, "_kill_attempt") as kill,
        ):
            controller._finish(attempt, process, 0, None)  # noqa: SLF001
            scheduled_callback = schedule.call_args.args[3]
            scheduled_callback(attempt, process)

        kill.assert_called_once_with(attempt, process)
        self.assertEqual(attempt.requested_status, "error")
        self.assertIn("descendant processes remained active", attempt.detail)

    def test_containment_close_failure_blocks_restart_until_retry_proves_close(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, application = self._controller_type()

        class Process:
            @staticmethod
            def state() -> object:
                return process_type.NotRunning

            @staticmethod
            def kill() -> None:
                return None

            @staticmethod
            def deleteLater() -> None:  # noqa: N802
                return None

        class Tree:
            close_calls = 0
            kill_calls = 0

            @staticmethod
            def is_active() -> bool:
                return False

            def kill(self) -> None:
                self.kill_calls += 1

            def close(self, *, require_empty: bool = True) -> None:
                self.close_calls += 1
                if self.close_calls == 1:
                    raise ProcessContainmentError("injected close failure")

        process = Process()
        tree = Tree()
        controller = controller_type()
        output = str((ROOT / ".batch-lifecycle-test").resolve())
        attempt = _BatchAttempt(1, output, "a" * 64, process, tree)
        attempt.settlement_started = attempt.settlement_done = True
        attempt.settlement_status = "completed"
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001
        failures: list[tuple[str, str]] = []
        controller.failed.connect(lambda detail, output: failures.append((detail, output)))

        controller._publish_result(attempt, process, "completed", "")  # noqa: SLF001
        self.assertTrue(controller.running)
        self.assertEqual(failures, [])
        with self.assertRaisesRegex(RuntimeError, "already running"):
            controller.start()

        controller._retry_publication(attempt, process)  # noqa: SLF001
        application.processEvents()
        self.assertFalse(controller.running)
        self.assertEqual(len(failures), 1)
        self.assertIn("injected close failure", failures[0][0])
        self.assertEqual(tree.kill_calls, 1)

    def test_shutdown_synchronously_settles_only_after_tree_is_dead(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, _application = self._controller_type()

        class Process:
            def __init__(self) -> None:
                self.active = True

            def state(self) -> object:
                return process_type.Running if self.active else process_type.NotRunning

            def waitForFinished(self, _timeout: int) -> bool:  # noqa: N802
                return not self.active

            def kill(self) -> None:
                self.active = False

            @staticmethod
            def deleteLater() -> None:  # noqa: N802
                return None

        class Tree:
            def __init__(self, process: Process) -> None:
                self.process = process
                self.close_saw_dead = False

            def terminate(self) -> None:
                self.process.active = False

            def kill(self) -> None:
                self.process.active = False

            def is_active(self) -> bool:
                return self.process.active

            def close(self, *, require_empty: bool = True) -> None:
                self.close_saw_dead = not self.process.active

        process = Process()
        tree = Tree(process)
        controller = controller_type()
        output = str((ROOT / ".batch-lifecycle-test").resolve())
        attempt = _BatchAttempt(1, output, "a" * 64, process, tree)
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001
        stopped: list[str] = []
        controller.stopped.connect(stopped.append)
        with patch(
            "mclab.application.qt_batch.settle_all_compare_output",
            return_value="stopped",
        ):
            self.assertTrue(controller.shutdown())

        self.assertTrue(tree.close_saw_dead)
        self.assertEqual(stopped, [output])
        self.assertFalse(controller.running)

    def test_shutdown_refuses_exit_while_process_tree_remains_active(self) -> None:
        from mclab.application.qt_batch import _BatchAttempt

        controller_type, process_type, _application = self._controller_type()

        class Process:
            kill_calls = 0

            @staticmethod
            def state() -> object:
                return process_type.Running

            @staticmethod
            def waitForFinished(_timeout: int) -> bool:  # noqa: N802
                return False

            def kill(self) -> None:
                self.kill_calls += 1

        class Tree:
            terminate_calls = 0
            kill_calls = 0
            close_calls = 0

            def terminate(self) -> None:
                self.terminate_calls += 1

            def kill(self) -> None:
                self.kill_calls += 1

            @staticmethod
            def is_active() -> bool:
                return True

            def close(self, *, require_empty: bool = True) -> None:
                self.close_calls += 1

        process = Process()
        tree = Tree()
        controller = controller_type()
        attempt = _BatchAttempt(
            1,
            str((ROOT / ".batch-lifecycle-stuck").resolve()),
            "a" * 64,
            process,
            tree,
            state="running",
        )
        controller._attempt = attempt  # noqa: SLF001
        controller.process = process
        controller._settled = False  # noqa: SLF001

        with (
            patch.object(controller, "_wait_for_direct_process", return_value=False),
            patch.object(controller, "_wait_for_tree", return_value=False),
        ):
            self.assertFalse(controller.shutdown())

        self.assertTrue(controller.running)
        self.assertFalse(attempt.settlement_started)
        self.assertIn("did not stop", attempt.detail)
        self.assertEqual(tree.terminate_calls, 1)
        self.assertEqual(tree.kill_calls, 1)
        self.assertEqual(tree.close_calls, 0)
        self.assertEqual(process.kill_calls, 1)

    def test_old_generation_kill_timer_cannot_touch_replacement_run(self) -> None:
        from mclab.application.qt_batch import create_batch_controller

        class BoundSignal:
            def __init__(self) -> None:
                self.callbacks: list[object] = []

            def connect(self, callback: object) -> None:
                self.callbacks.append(callback)

            def emit(self, *args: object) -> None:
                for callback in tuple(self.callbacks):
                    callback(*args)

        class SignalDescriptor:
            def __set_name__(self, _owner: object, name: str) -> None:
                self.name = name

            def __get__(self, instance: object, _owner: object) -> object:
                if instance is None:
                    return self
                key = f"_signal_{self.name}"
                if not hasattr(instance, key):
                    setattr(instance, key, BoundSignal())
                return getattr(instance, key)

        def Signal(*_args: object) -> SignalDescriptor:  # noqa: N802
            return SignalDescriptor()

        class QObject:
            def __init__(self, _parent: object = None) -> None:
                return None

        class Timer:
            callbacks: list[tuple[int, object]] = []

            @classmethod
            def singleShot(cls, delay: int, callback: object) -> None:  # noqa: N802
                cls.callbacks.append((delay, callback))

        class Process:
            NotRunning = 0
            Starting = 1
            Running = 2
            SeparateChannels = 3
            instances: list["Process"] = []

            def __init__(self, _parent: object = None) -> None:
                self.started = BoundSignal()
                self.readyReadStandardOutput = BoundSignal()  # noqa: N815
                self.readyReadStandardError = BoundSignal()  # noqa: N815
                self.finished = BoundSignal()
                self.errorOccurred = BoundSignal()  # noqa: N815
                self.current_state = self.NotRunning
                self.kill_calls = 0
                self.terminate_calls = 0
                self.pid = 5000 + len(self.instances)
                self.instances.append(self)

            def setProcessChannelMode(self, _mode: object) -> None:  # noqa: N802
                return None

            def start(self, _program: str, _arguments: list[str]) -> None:
                self.current_state = self.Running

            def state(self) -> int:
                return self.current_state

            def processId(self) -> int:  # noqa: N802
                return self.pid

            def terminate(self) -> None:
                self.terminate_calls += 1

            def kill(self) -> None:
                self.kill_calls += 1
                self.current_state = self.NotRunning

            @staticmethod
            def readAllStandardOutput() -> bytes:  # noqa: N802
                return b""

            @staticmethod
            def readAllStandardError() -> bytes:  # noqa: N802
                return b""

            @staticmethod
            def errorString() -> str:  # noqa: N802
                return ""

            @staticmethod
            def deleteLater() -> None:  # noqa: N802
                return None

        class Tree:
            def __init__(self, process: Process) -> None:
                self.process = process
                self.active = False
                self.kill_calls = 0

            @staticmethod
            def configure() -> None:
                return None

            @property
            def worker_arguments(self) -> tuple[str, ...]:
                return ()

            def attach(self, _pid: int) -> None:
                self.active = True

            def terminate(self) -> None:
                self.process.terminate()

            def kill(self) -> None:
                self.kill_calls += 1
                self.active = False
                self.process.kill()

            def is_active(self) -> bool:
                return self.active

            @staticmethod
            def close(*, require_empty: bool = True) -> None:
                return None

        trees: list[Tree] = []

        def tree_factory(_process_type: object, process: Process) -> Tree:
            tree = Tree(process)
            trees.append(tree)
            return tree

        outputs = iter(
            [
                (ROOT / ".batch-generation-a").resolve(),
                (ROOT / ".batch-generation-b").resolve(),
            ]
        )
        controller_type = create_batch_controller(QObject, Process, Timer, Signal)
        controller = controller_type()
        stopped: list[str] = []
        controller.stopped.connect(stopped.append)
        with (
            patch(
                "mclab.application.qt_batch.create_all_compare_output",
                side_effect=lambda: next(outputs),
            ),
            patch(
                "mclab.application.qt_batch.read_all_compare_handoff",
                return_value="a" * 64,
            ),
            patch(
                "mclab.application.qt_batch.all_compare_command",
                return_value=(sys.executable, ["batch", "all"]),
            ),
            patch(
                "mclab.application.qt_batch.create_batch_process_tree",
                side_effect=tree_factory,
            ),
            patch("mclab.application.qt_batch.read_batch_progress", return_value=()),
            patch("mclab.application.qt_batch.settle_all_compare_output", return_value="stopped"),
            ):
            controller.start()
            first_process = Process.instances[-1]
            controller.cancel()
            self.assertEqual(first_process.terminate_calls, 0)
            self.assertEqual(trees[0].kill_calls, 0)
            first_process.started.emit()
            self.assertEqual(first_process.terminate_calls, 1)
            stale_kill = next(callback for delay, callback in Timer.callbacks if delay == 2_000)
            first_process.current_state = Process.NotRunning
            trees[0].active = False
            first_process.finished.emit(-15, None)
            controller._attempt.settlement_thread.join(2)  # noqa: SLF001
            controller._complete_settlement(  # noqa: SLF001
                controller._attempt,  # noqa: SLF001
                first_process,
            )

            controller.start()
            second_attempt = controller._attempt  # noqa: SLF001
            second_process = Process.instances[-1]
            second_process.started.emit()
            stale_kill()
            self.assertIs(controller._attempt, second_attempt)  # noqa: SLF001
            self.assertTrue(controller.running)
            self.assertEqual(second_process.kill_calls, 0)
            self.assertEqual(trees[1].kill_calls, 0)

            controller.cancel()
            second_process.current_state = Process.NotRunning
            trees[1].active = False
            second_process.finished.emit(-15, None)
            second_attempt.settlement_thread.join(2)
            controller._complete_settlement(second_attempt, second_process)  # noqa: SLF001

        self.assertEqual(len(stopped), 2)


if __name__ == "__main__":
    unittest.main()
