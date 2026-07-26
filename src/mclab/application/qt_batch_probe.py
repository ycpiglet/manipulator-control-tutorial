"""Self-test-only Qt lifecycle probe for the packaged course comparison."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any

BATCH_PROBE_ACTIONS = frozenset(
    {
        "batch_probe_complete",
        "batch_probe_cancel",
        "batch_probe_close",
    }
)
_LIFECYCLE_PROBE_ACTIONS = {
    "batch_probe_cancel": "cancel",
    "batch_probe_close": "close",
}
_REQUEST_SCHEMA = "mclab.batch-probe-request.v1"
_WORKER_SAFE_POINT_SCHEMA = "mclab.batch-worker-safe-point.v1"
_MAX_REQUEST_BYTES = 1_024
_WORKER_HOLD_SECONDS = 30.0


def schedule_batch_lifecycle_probe(
    timer: Any,
    backend: Any,
    root: Any,
    action: str,
    delay_ms: int,
) -> None:
    """Schedule one isolated lifecycle probe after the caller's self-test gate."""

    probe = _BatchLifecycleProbe(timer, backend, root, action)
    timer.singleShot(delay_ms, probe.start)


class _BatchLifecycleProbe:
    """Bounded self-test observer for one real packaged all-batch lifecycle."""

    _SCHEMA = "mclab.batch-probe.v1"
    _REQUEST_SCHEMA = _REQUEST_SCHEMA
    _HEARTBEAT_MS = 100
    _MAX_SECONDS = 360.0
    _MAX_REQUEST_BYTES = _MAX_REQUEST_BYTES
    _MAX_PROBE_BYTES = 16_384

    def __init__(self, timer: Any, backend: Any, root: Any, action: str) -> None:
        self.timer = timer
        self.backend = backend
        self.root = root
        self.action = action
        self.controller = backend._batch  # noqa: SLF001
        self.probe_path = self._required_absolute_path("MCLAB_BATCH_PROBE_PATH")
        self.ready_path = self._required_absolute_path("MCLAB_BATCH_READY_PATH")
        self.request_path = self._required_absolute_path("MCLAB_BATCH_REQUEST_PATH")
        self.worker_safe_path = _worker_safe_point_path(self.request_path)
        self.started_at = 0.0
        self.last_heartbeat = 0.0
        self.heartbeat_count = 0
        self.max_ui_gap_ms = 0.0
        self.output = ""
        self.child_pid = 0
        self.current = 0
        self.total = 5
        self.name = ""
        self.progress: list[dict[str, Any]] = []
        self.ready = False
        self.request_seen = False
        self.cancel_requested = False
        self.terminal = False
        self.timeout_requested = False
        self.failure_code = ""
        self.abort_started_at = 0.0
        self.shutdown_attempted = False

    @staticmethod
    def _required_absolute_path(variable: str) -> Path:
        value = os.environ.get(variable, "")
        path = Path(value)
        if not value or not path.is_absolute():
            raise RuntimeError(f"{variable} must name an absolute self-test path.")
        return path

    def start(self) -> None:
        if self.action in _LIFECYCLE_PROBE_ACTIONS and any(
            os.path.lexists(path) for path in (self.request_path, self.worker_safe_path)
        ):
            raise RuntimeError(
                "The batch probe request and worker safe point must not exist before startup."
            )
        self.started_at = self.last_heartbeat = time.monotonic()
        self.controller.changed.connect(self._changed)
        self.controller.completed.connect(lambda output: self._finish("completed", output, ""))
        self.controller.stopped.connect(lambda output: self._finish("stopped", output, ""))
        self.controller.failed.connect(
            lambda _detail, output: self._finish("error", output, "batch_failed")
        )
        # Arm the first sample before synchronous startup work.  Otherwise that
        # work is charged together with an additional nominal timer interval.
        self.timer.singleShot(self._HEARTBEAT_MS, self._heartbeat)
        self.backend.startAllCompare()
        self._changed()
        if not self.terminal and not self.controller.running:
            self._finish("error", self.output, "start_failed_without_terminal")

    def _changed(self) -> None:
        if self.terminal:
            return
        snapshot = self.controller.snapshot()
        output = str(snapshot.get("output", ""))
        if output:
            output_path = Path(output)
            if not output_path.is_absolute():
                self._abort("non_absolute_output")
                return
            self.output = str(output_path)
        child_pid = int(snapshot.get("childPid", 0) or 0)
        if child_pid > 0:
            self.child_pid = child_pid
        current = int(snapshot.get("current", 0) or 0)
        total = int(snapshot.get("total", 0) or 0)
        name = str(snapshot.get("name", ""))
        self.cancel_requested = self.cancel_requested or bool(
            snapshot.get("cancelling", False)
        )
        if current > self.current:
            if current != self.current + 1 or total != 5 or not name:
                self._abort("invalid_progress")
                return
            self.progress.append(
                {
                    "current": current,
                    "total": total,
                    "name": name,
                    "elapsed_ms": round((time.monotonic() - self.started_at) * 1_000, 3),
                }
            )
        self.current, self.total, self.name = current, total, name
        if (
            not self.ready
            and self.output
            and self.child_pid > 0
            and self.current >= 1
            and self.progress
        ):
            expected_action = _LIFECYCLE_PROBE_ACTIONS.get(self.action)
            if expected_action is not None:
                try:
                    worker_safe = _read_batch_probe_request(
                        self.worker_safe_path,
                        expected_action,
                        max_bytes=self._MAX_REQUEST_BYTES,
                        schema=_WORKER_SAFE_POINT_SCHEMA,
                    )
                except Exception:
                    self._abort("invalid_worker_safe_point")
                    return
                if not worker_safe:
                    return
            self.ready = True
            payload = self._payload("ready", str(snapshot.get("state", "running")), False, "")
            _atomic_probe_write(
                self.ready_path,
                payload,
                self._MAX_PROBE_BYTES,
                durable=False,
            )

    def _heartbeat(self) -> None:
        if self.terminal:
            return
        now = time.monotonic()
        gap_ms = (now - self.last_heartbeat) * 1_000
        self.last_heartbeat = now
        self.heartbeat_count += 1
        self.max_ui_gap_ms = max(self.max_ui_gap_ms, gap_ms)
        self._changed()
        if self.terminal:
            return
        if self.ready:
            if self.action in {"batch_probe_cancel", "batch_probe_close"}:
                try:
                    requested = _read_batch_probe_request(
                        self.request_path,
                        self.action.removeprefix("batch_probe_"),
                        max_bytes=self._MAX_REQUEST_BYTES,
                        schema=self._REQUEST_SCHEMA,
                    )
                except Exception:
                    self._abort("invalid_request")
                    return
                if requested and not self.request_seen:
                    self.request_seen = True
                    self.cancel_requested = True
                    if self.action == "batch_probe_cancel":
                        self.backend.cancelBatch()
                    elif self.root is None or not callable(getattr(self.root, "close", None)):
                        self._abort("close_target_missing")
                        return
                    else:
                        self.root.close()
                        return
        elapsed = now - self.started_at
        if (
            self.timeout_requested
            and self.abort_started_at > 0
            and now - self.abort_started_at >= 10.0
            and not self.shutdown_attempted
        ):
            self.shutdown_attempted = True
            if self.controller.shutdown() and not self.terminal and not self.controller.running:
                self._finish("error", self.output, self.failure_code or "probe_timeout")
            return
        if elapsed >= self._MAX_SECONDS and not self.timeout_requested:
            self.timeout_requested = True
            self._abort("probe_timeout")
            return
        self.timer.singleShot(self._HEARTBEAT_MS, self._heartbeat)

    def _abort(self, error_code: str) -> None:
        if self.terminal:
            return
        self.failure_code = self.failure_code or error_code
        self.abort_started_at = self.abort_started_at or time.monotonic()
        self.timeout_requested = True
        self.cancel_requested = True
        if self.controller.running:
            self.backend.cancelBatch()
            self.timer.singleShot(self._HEARTBEAT_MS, self._heartbeat)
        else:
            self._finish("error", self.output, error_code)

    def _finish(self, status: str, output: str, error_code: str) -> None:
        if self.terminal:
            return
        now = time.monotonic()
        self.max_ui_gap_ms = max(
            self.max_ui_gap_ms,
            (now - self.last_heartbeat) * 1_000,
        )
        self.last_heartbeat = now
        self._changed()
        self.terminal = True
        error_code = self.failure_code or error_code
        if output:
            path = Path(output)
            if path.is_absolute():
                self.output = str(path)
            else:
                error_code = error_code or "non_absolute_output"
        expected = "completed" if self.action == "batch_probe_complete" else "stopped"
        if status != expected:
            error_code = error_code or "unexpected_terminal_status"
        payload = self._payload("terminal", status, True, error_code)
        _atomic_probe_write(self.probe_path, payload, self._MAX_PROBE_BYTES)
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.quit()

    def _payload(
        self,
        phase: str,
        status: str,
        settled: bool,
        error_code: str,
    ) -> dict[str, Any]:
        return {
            "schema": self._SCHEMA,
            "action": self.action,
            "phase": phase,
            "status": status,
            "output": self.output,
            "child_pid": self.child_pid,
            "current": self.current,
            "total": self.total,
            "name": self.name,
            "progress": self.progress[:5],
            "heartbeat_count": self.heartbeat_count,
            "max_ui_gap_ms": round(self.max_ui_gap_ms, 3),
            "elapsed_seconds": round(max(0.0, time.monotonic() - self.started_at), 3),
            "cancel_requested": self.cancel_requested,
            "settled": settled,
            "error_code": error_code,
        }


def _stat_is_link_or_reparse(result: os.stat_result) -> bool:
    attributes = int(getattr(result, "st_file_attributes", 0))
    return stat.S_ISLNK(result.st_mode) or bool(attributes & 0x400)


def _read_batch_probe_request(
    path: Path,
    expected_action: str,
    *,
    max_bytes: int,
    schema: str,
) -> bool:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return False
    if (
        _stat_is_link_or_reparse(before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_size > max_bytes
    ):
        raise RuntimeError("The batch probe request is not a bounded regular file.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            _stat_is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_size > max_bytes
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise RuntimeError("The batch probe request changed while it was opened.")
        data = os.read(descriptor, max_bytes + 1)
        after = os.lstat(path)
        if (
            _stat_is_link_or_reparse(after)
            or not stat.S_ISREG(after.st_mode)
            or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RuntimeError("The batch probe request changed while it was read.")
    finally:
        os.close(descriptor)
    if len(data) > max_bytes:
        raise RuntimeError("The batch probe request is too large.")
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError(f"Duplicate batch probe request key: {key}")
            payload[key] = value
        return payload

    def reject_constant(value: str) -> None:
        raise ValueError(f"Invalid batch probe request constant: {value}")

    payload = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=strict_object,
        parse_constant=reject_constant,
    )
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "action"}
        or payload.get("schema") != schema
        or payload.get("action") != expected_action
    ):
        raise RuntimeError("The batch probe request does not match the active action.")
    return True


def _worker_safe_point_path(request_path: Path) -> Path:
    return request_path.with_name(".mclab-worker-safe-point.json")


def _probe_path_identity(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _require_real_directory(path: Path) -> None:
    result = os.lstat(path)
    if _stat_is_link_or_reparse(result) or not stat.S_ISDIR(result.st_mode):
        raise RuntimeError("The lifecycle probe parent must be a real directory.")


def hold_batch_worker_at_lifecycle_safe_point(
    current: int,
    handoff_token: str | None,
) -> None:
    """Keep lifecycle self-tests at the first authenticated progress boundary."""

    if current != 1 or os.environ.get("MCLAB_SELF_TEST") != "1":
        return
    action = os.environ.get("MCLAB_SMOKE_ACTION", "")
    expected_action = _LIFECYCLE_PROBE_ACTIONS.get(action)
    if expected_action is None:
        return
    if (
        not isinstance(handoff_token, str)
        or len(handoff_token) != 64
        or any(character not in "0123456789abcdef" for character in handoff_token)
    ):
        raise RuntimeError("The lifecycle probe requires an authenticated batch handoff.")

    variables = (
        "MCLAB_BATCH_PROBE_PATH",
        "MCLAB_BATCH_READY_PATH",
        "MCLAB_BATCH_REQUEST_PATH",
    )
    paths: list[Path] = []
    for variable in variables:
        value = os.environ.get(variable, "")
        path = Path(value)
        if not value or not path.is_absolute():
            raise RuntimeError(f"{variable} must name an absolute self-test path.")
        if os.path.normcase(os.path.normpath(value)) != os.path.normcase(value):
            raise RuntimeError(f"{variable} must name a normalized self-test path.")
        paths.append(path)
    identities = {_probe_path_identity(path) for path in paths}
    parent_identities = {_probe_path_identity(path.parent) for path in paths}
    if len(identities) != len(paths) or len(parent_identities) != 1:
        raise RuntimeError("The lifecycle probe paths must be distinct siblings.")
    _require_real_directory(paths[0].parent)

    request_path = paths[-1]
    worker_safe_path = _worker_safe_point_path(request_path)
    if worker_safe_path in paths or os.path.lexists(worker_safe_path):
        raise RuntimeError("The lifecycle worker safe-point destination is already occupied.")
    _atomic_probe_write(
        worker_safe_path,
        {"action": expected_action, "schema": _WORKER_SAFE_POINT_SCHEMA},
        _MAX_REQUEST_BYTES,
        durable=False,
    )
    deadline = time.monotonic() + _WORKER_HOLD_SECONDS
    while time.monotonic() < deadline:
        if _read_batch_probe_request(
            request_path,
            expected_action,
            max_bytes=_MAX_REQUEST_BYTES,
            schema=_REQUEST_SCHEMA,
        ):
            # The controller owns termination. Returning here would start a
            # child batch and reintroduce a platform-dependent cleanup race.
            while time.monotonic() < deadline:
                time.sleep(0.025)
            raise RuntimeError("The lifecycle probe worker was not terminated after its request.")
        time.sleep(0.025)
    raise RuntimeError("The lifecycle probe request was not published before its deadline.")


def _atomic_probe_write(
    path: Path,
    payload: dict[str, Any],
    max_bytes: int,
    *,
    durable: bool = True,
) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(data) > max_bytes:
        raise RuntimeError("The batch lifecycle probe exceeded its size bound.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    if existing is not None and (
        _stat_is_link_or_reparse(existing) or not stat.S_ISREG(existing.st_mode)
    ):
        raise RuntimeError("The batch lifecycle probe destination is unsafe.")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, 0o600)
    try:
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                if durable:
                    stream.flush()
                    os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
