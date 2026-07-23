#!/usr/bin/env python3
"""Audit packaged desktop startup without building or modifying the package.

The audit authenticates the existing unsigned development package against the
exact workflow subject, launches twenty new processes with unique explicit INI
settings in temporary storage outside the checkout, and verifies the package
again after the launches. The application-owned ``startup_probe`` records the
interval from immediately before process creation until the QML root has loaded.

Only the bounded canonical JSON file named by ``--output`` is durable. Settings,
runtime state, probe files, and bounded command logs remain below
``--temp-root`` and are removed. This is an internal development gate, not
release, signing, distribution, or aggregate PKG acceptance evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_desktop  # noqa: E402


SCHEMA = "mclab.package-startup.v1"
ARTIFACT_CLASS = "unsigned-development-package-startup-evidence"
PROVENANCE_SCOPE = "internal-pkg-01b-development-evidence"
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_METRIC_BYTES = 4096
MAX_CAPTURED_LOG_BYTES = 256 * 1024
PROCESS_TIMEOUT_SECONDS = 20.0
PROCESS_REAP_SECONDS = 3.0
STARTUP_SAMPLES = 20
STARTUP_P95_LIMIT_MS = 5000.0
REQUIRED_CHECK_CONTEXTS = (
    "Simulator lint and tests",
    "Paper citation and formula gates",
    "Paper LaTeX build",
    "Unsigned development build (windows-2025)",
    "Unsigned development build (ubuntu-24.04)",
    "Unsigned development build (macos-15)",
)

_SHA40_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/]")
_EMBEDDED_POSIX_ABSOLUTE_RE = re.compile(r"(?:^|[\s=:;,(\[{])/(?!/)[^\s\"'<>]+")
_REPARSE_POINT_FLAG = 0x400
_RUNNER_SYSTEM = {"Linux": "Linux", "Windows": "Windows", "macOS": "Darwin"}
_ENV_ALLOWLIST = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "Path",
        "SYSTEMROOT",
        "SystemRoot",
        "TZ",
        "WINDIR",
    }
)


class AuditError(RuntimeError):
    """A fail-closed error whose stable code is safe for durable evidence."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LogSummary:
    bytes: int
    captured_bytes: int
    sha256: str
    truncated: bool


@dataclass(frozen=True)
class CommandResult:
    return_code: int
    duration_ms: float
    timed_out: bool
    forced_cleanup: bool
    stdout: LogSummary
    stderr: LogSummary
    error_code: str

    @property
    def passed(self) -> bool:
        return (
            self.return_code == 0
            and not self.timed_out
            and not self.forced_cleanup
            and not self.error_code
        )


def canonical_json_bytes(payload: object) -> bytes:
    """Return compact, sorted, finite UTF-8 JSON with one final LF."""

    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _canonical(path: Path) -> Path:
    try:
        return _absolute(path).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AuditError("path_canonicalization_failed") from exc


def _within(path: Path, parent: Path) -> bool:
    candidate = _absolute(path)
    boundary = _absolute(parent)
    return candidate == boundary or candidate.is_relative_to(boundary)


def _physically_within(path: Path, parent: Path) -> bool:
    candidate = _canonical(path)
    boundary = _canonical(parent)
    return candidate == boundary or candidate.is_relative_to(boundary)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT_FLAG)


def _require_real_directory(path: Path, code: str) -> Path:
    candidate = _absolute(path)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise AuditError(code) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse_point(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise AuditError(code)
    return candidate


def _require_regular_file(path: Path, code: str) -> Path:
    candidate = _absolute(path)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise AuditError(code) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse_point(metadata)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise AuditError(code)
    return candidate


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite number")


def read_startup_metric(path: Path) -> float:
    """Read the application-owned startup metric as one strict bounded object."""

    source = _require_regular_file(path, "startup_metric_missing_or_unsafe")
    metadata = source.lstat()
    if metadata.st_size <= 0 or metadata.st_size > MAX_METRIC_BYTES:
        raise AuditError("startup_metric_size_invalid")
    try:
        payload = json.loads(
            source.read_bytes().decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise AuditError("startup_metric_json_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"startup_ms"}:
        raise AuditError("startup_metric_shape_invalid")
    value = payload["startup_ms"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError("startup_metric_number_invalid")
    startup_ms = float(value)
    if not math.isfinite(startup_ms) or startup_ms < 0.0:
        raise AuditError("startup_metric_number_invalid")
    return startup_ms


def _assert_no_absolute_strings(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_absolute_strings(key)
            _assert_no_absolute_strings(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_absolute_strings(item)
    elif isinstance(value, str):
        if (
            value.startswith(("/", "\\\\"))
            or _WINDOWS_ABSOLUTE_RE.search(value)
            or _EMBEDDED_POSIX_ABSOLUTE_RE.search(value)
        ):
            raise AuditError("absolute_path_in_evidence")


def _write_atomic(path: Path, payload: bytes) -> None:
    if not payload or len(payload) > MAX_EVIDENCE_BYTES:
        raise AuditError("evidence_size_invalid")
    target = _absolute(path)
    _require_real_directory(target.parent, "evidence_parent_unsafe")
    if target.exists() or target.is_symlink():
        _require_regular_file(target, "evidence_target_unsafe")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def write_canonical_json(path: Path, payload: Mapping[str, Any]) -> int:
    """Atomically write and reread one bounded canonical evidence object."""

    _assert_no_absolute_strings(payload)
    encoded = canonical_json_bytes(payload)
    _write_atomic(path, encoded)
    if _require_regular_file(path, "evidence_missing").read_bytes() != encoded:
        raise AuditError("evidence_reread_mismatch")
    return len(encoded)


def nearest_rank_percentile(
    values: Sequence[float], percentile: float
) -> tuple[float, int]:
    """Return the nearest-rank percentile and one-based rank."""

    if not values or not 0.0 < percentile <= 1.0:
        raise AuditError("percentile_inputs_invalid")
    normalized = [float(value) for value in values]
    if any(not math.isfinite(value) or value < 0.0 for value in normalized):
        raise AuditError("percentile_values_invalid")
    ordered = sorted(normalized)
    rank = int(math.ceil(percentile * len(ordered)))
    return ordered[rank - 1], rank


def fresh_environment(
    inherited: Mapping[str, str],
    state_root: Path,
    *,
    metric_path: Path,
) -> dict[str, str]:
    """Build an injection-scrubbed environment with one unique explicit INI."""

    root = _absolute(state_root)
    root.mkdir(parents=True, exist_ok=False)
    directories = {
        "APPDATA": root / "appdata",
        "HOME": root / "home",
        "LOCALAPPDATA": root / "localappdata",
        "MPLCONFIGDIR": root / "matplotlib",
        "TEMP": root / "temp",
        "TMP": root / "temp",
        "TMPDIR": root / "temp",
        "USERPROFILE": root / "home",
        "XDG_CACHE_HOME": root / "cache",
        "XDG_CONFIG_HOME": root / "config",
        "XDG_DATA_HOME": root / "share",
    }
    for directory in set(directories.values()):
        directory.mkdir(parents=True, exist_ok=True)
    settings_root = root / "settings"
    settings_root.mkdir()

    result = {name: value for name, value in inherited.items() if name in _ENV_ALLOWLIST}
    for name, directory in directories.items():
        result[name] = os.fspath(directory)
    result.update(
        {
            "MCLAB_APP_AUTO_QUIT_MS": "650",
            "MCLAB_DATA_DIR": os.fspath(root / "data"),
            "MCLAB_FAIL_ON_ERROR": "1",
            "MCLAB_INSTANCE_LOCK": os.fspath(root / "instance.lock"),
            "MCLAB_OUTPUT_DIR": os.fspath(root / "outputs"),
            "MCLAB_SELF_TEST": "1",
            "MCLAB_SMOKE_ACTION": "startup_probe",
            "MCLAB_SMOKE_ACTION_MS": "0",
            "MCLAB_STARTUP_SETTINGS_PATH": os.fspath(settings_root / "mclab.ini"),
            "MCLAB_STARTUP_PATH": os.fspath(_absolute(metric_path)),
            "MPLBACKEND": "Agg",
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
        }
    )
    return result


def _drain_log(
    stream: BinaryIO,
    destination: Path,
    result: dict[str, object],
) -> None:
    digest = hashlib.sha256()
    total = 0
    captured = 0
    error_code = ""
    try:
        with destination.open("xb") as output:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
                remaining = MAX_CAPTURED_LOG_BYTES - captured
                if remaining > 0:
                    saved = chunk[:remaining]
                    output.write(saved)
                    captured += len(saved)
    except (OSError, ValueError):
        error_code = "command_log_drain_failed"
    finally:
        try:
            stream.close()
        except OSError:
            error_code = error_code or "command_log_close_failed"
    result.update(
        {
            "bytes": total,
            "captured_bytes": captured,
            "error_code": error_code,
            "sha256": digest.hexdigest(),
            "truncated": total > captured,
        }
    )


def _terminate_process(process: subprocess.Popen[bytes]) -> bool:
    """Terminate the POSIX process group or the direct Windows child within bounds."""

    forced = False
    try:
        if process.poll() is None:
            forced = True
            if os.name == "nt":
                # CREATE_NEW_PROCESS_GROUP does not provide Windows process-tree
                # containment. PKG-01B reaps the direct child; descendant
                # containment remains the separate process-lifecycle gate.
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=PROCESS_REAP_SECONDS)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=PROCESS_REAP_SECONDS)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=PROCESS_REAP_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return forced


def run_command(
    executable: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    log_root: Path,
    label: str,
    timeout_seconds: float = PROCESS_TIMEOUT_SECONDS,
    stamp_startup_begin: bool = False,
) -> CommandResult:
    """Run one absolute executable with a bounded lifetime and bounded temp logs."""

    program = _require_regular_file(executable, "packaged_executable_missing_or_unsafe")
    runtime_cwd = _require_real_directory(cwd, "runtime_cwd_unsafe")
    if not program.is_absolute() or not runtime_cwd.is_absolute():
        raise AuditError("runtime_path_not_absolute")
    if _LABEL_RE.fullmatch(label) is None:
        raise AuditError("command_label_invalid")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0:
        raise AuditError("command_timeout_invalid")
    logs = _absolute(log_root)
    logs.mkdir(parents=True, exist_ok=True)
    _require_real_directory(logs, "command_log_root_unsafe")
    stdout_path = logs / f"{label}.stdout"
    stderr_path = logs / f"{label}.stderr"
    child_env = dict(env)

    popen_kwargs: dict[str, Any] = {
        "cwd": runtime_cwd,
        "env": child_env,
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
        "stdout": subprocess.PIPE,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    started = time.monotonic()
    if stamp_startup_begin:
        child_env["MCLAB_STARTUP_BEGIN_NS"] = str(time.monotonic_ns())
    try:
        process = subprocess.Popen([os.fspath(program), *arguments], **popen_kwargs)
    except (OSError, ValueError) as exc:
        raise AuditError("process_start_failed") from exc
    assert process.stdout is not None and process.stderr is not None
    stdout_result: dict[str, object] = {}
    stderr_result: dict[str, object] = {}
    stdout_thread = threading.Thread(
        target=_drain_log,
        args=(process.stdout, stdout_path, stdout_result),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_log,
        args=(process.stderr, stderr_path, stderr_result),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    forced_cleanup = False
    error_code = ""
    pending_error: BaseException | None = None
    try:
        return_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        forced_cleanup = _terminate_process(process)
        return_code = process.returncode if process.returncode is not None else -9
    except BaseException as exc:
        forced_cleanup = _terminate_process(process)
        return_code = process.returncode if process.returncode is not None else -9
        pending_error = exc

    stdout_thread.join(timeout=PROCESS_REAP_SECONDS)
    stderr_thread.join(timeout=PROCESS_REAP_SECONDS)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        error_code = "command_log_drain_timeout"
        try:
            process.stdout.close()
            process.stderr.close()
        except OSError:
            pass
        stdout_thread.join(timeout=PROCESS_REAP_SECONDS)
        stderr_thread.join(timeout=PROCESS_REAP_SECONDS)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        error_code = "command_log_drain_unsettled"

    empty_digest = hashlib.sha256(b"").hexdigest()

    def log_summary(result: Mapping[str, object]) -> LogSummary:
        return LogSummary(
            bytes=int(result.get("bytes", 0)),
            captured_bytes=int(result.get("captured_bytes", 0)),
            sha256=str(result.get("sha256", empty_digest)),
            truncated=bool(result.get("truncated", False)),
        )

    for result in (stdout_result, stderr_result):
        candidate = result.get("error_code")
        if isinstance(candidate, str) and candidate:
            error_code = error_code or candidate
    if pending_error is not None:
        raise pending_error
    return CommandResult(
        return_code=int(return_code),
        duration_ms=(time.monotonic() - started) * 1000.0,
        timed_out=timed_out,
        forced_cleanup=forced_cleanup,
        stdout=log_summary(stdout_result),
        stderr=log_summary(stderr_result),
        error_code=error_code,
    )


def _log_payload(summary: LogSummary) -> dict[str, object]:
    return {
        "bytes": summary.bytes,
        "captured_bytes": summary.captured_bytes,
        "sha256": summary.sha256,
        "truncated": summary.truncated,
    }


def _command_payload(result: CommandResult) -> dict[str, object]:
    return {
        "duration_ms": result.duration_ms,
        "error_code": result.error_code,
        "forced_cleanup": result.forced_cleanup,
        "passed": result.passed,
        "return_code": result.return_code,
        "stderr": _log_payload(result.stderr),
        "stdout": _log_payload(result.stdout),
        "timed_out": result.timed_out,
    }


def run_startup_sample(
    executable: Path,
    *,
    cwd: Path,
    root: Path,
    index: int,
    inherited_env: Mapping[str, str],
) -> dict[str, object]:
    """Run and summarize one actual QML-root startup probe."""

    metric = root / f"startup-{index}.json"
    env = fresh_environment(
        inherited_env,
        root / f"state-{index}",
        metric_path=metric,
    )
    try:
        command = run_command(
            executable,
            ("app", "--safe-mode", "--lang", "en"),
            cwd=cwd,
            env=env,
            log_root=root / "logs",
            label=f"startup-{index}",
            stamp_startup_begin=True,
        )
    except BaseException as exc:
        return {
            "command": None,
            "error_code": _error_code(exc),
            "passed": False,
            "sample": index,
            "startup_ms": None,
        }
    try:
        startup_ms = read_startup_metric(metric)
    except BaseException as exc:
        startup_ms = None
        error_code = _error_code(exc)
    else:
        if command.passed:
            error_code = ""
        elif command.error_code:
            error_code = command.error_code
        elif command.timed_out:
            error_code = "startup_command_timed_out"
        else:
            error_code = "startup_command_failed"
    passed = command.passed and startup_ms is not None
    return {
        "command": _command_payload(command),
        "error_code": error_code,
        "passed": passed,
        "sample": index,
        "startup_ms": startup_ms,
    }


def evaluate_startup_samples(samples: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Apply the exact 20-sample, zero-failure nearest-rank p95 gate."""

    expected_indexes = list(range(1, STARTUP_SAMPLES + 1))
    indexes = [sample.get("sample") for sample in samples]
    values = [
        float(sample["startup_ms"])
        for sample in samples
        if sample.get("passed") is True
        and isinstance(sample.get("startup_ms"), (int, float))
        and not isinstance(sample.get("startup_ms"), bool)
    ]
    complete = len(samples) == STARTUP_SAMPLES and indexes == expected_indexes
    all_valid = complete and len(values) == STARTUP_SAMPLES
    p95_ms: float | None = None
    rank = int(math.ceil(0.95 * STARTUP_SAMPLES))
    if all_valid:
        try:
            p95_ms, rank = nearest_rank_percentile(values, 0.95)
        except AuditError:
            all_valid = False
            p95_ms = None
    failures = sum(sample.get("passed") is not True for sample in samples)
    passed = all_valid and failures == 0 and p95_ms is not None and (
        p95_ms <= STARTUP_P95_LIMIT_MS
    )
    return {
        "actual_qml_root_probe": True,
        "cold_definition": (
            "new-process-and-explicit-fresh-ini; os-file-cache-not-flushed"
        ),
        "failure_count": failures,
        "method": "nearest-rank",
        "metric_boundary": "process-spawn-to-qml-root-load",
        "p95_ms": p95_ms,
        "passed": passed,
        "rank": rank,
        "sample_count": len(samples),
        "samples": list(samples),
    }


def _package_summary(
    evidence: object,
    *,
    workflow_sha: str,
    runner_os: str,
) -> dict[str, object]:
    """Extract the exact subject, identity, and enforced independent size gates."""

    if runner_os not in _RUNNER_SYSTEM:
        raise AuditError("runner_os_invalid")
    if not isinstance(evidence, dict):
        raise AuditError("package_evidence_shape_invalid")
    source = evidence.get("source")
    identity = evidence.get("package_identity")
    archive = evidence.get("archive")
    gates = evidence.get("gates")
    if not isinstance(source, dict):
        raise AuditError("package_source_shape_invalid")
    if not isinstance(identity, dict) or set(identity) != {"algorithm", "value"}:
        raise AuditError("package_identity_shape_invalid")
    if identity.get("algorithm") != "sha256" or not isinstance(identity.get("value"), str):
        raise AuditError("package_identity_invalid")
    identity_value = str(identity["value"])
    if _SHA256_RE.fullmatch(identity_value) is None:
        raise AuditError("package_identity_invalid")
    if not isinstance(archive, dict):
        raise AuditError("package_archive_shape_invalid")
    archive_sha = archive.get("sha256")
    archive_bytes = archive.get("size_bytes")
    if (
        not isinstance(archive_sha, str)
        or _SHA256_RE.fullmatch(archive_sha) is None
        or type(archive_bytes) is not int
        or archive_bytes < 0
    ):
        raise AuditError("package_archive_identity_invalid")
    if not isinstance(gates, dict) or set(gates) != {"archive", "one_folder"}:
        raise AuditError("package_size_gates_shape_invalid")
    expected_limits = {
        "archive": build_desktop.ARCHIVE_LIMIT_BYTES,
        "one_folder": build_desktop.ONE_FOLDER_LIMIT_BYTES,
    }
    normalized_gates: dict[str, object] = {}
    for name, expected_limit in expected_limits.items():
        gate = gates.get(name)
        if (
            not isinstance(gate, dict)
            or gate.get("enforced") is not True
            or gate.get("passed") is not True
            or gate.get("limit_bytes") != expected_limit
            or gate.get("unit") != "bytes"
            or type(gate.get("measured_bytes")) is not int
        ):
            raise AuditError("package_size_gate_not_enforced_or_passed")
        normalized_gates[name] = dict(gate)
    source_commit = source.get("source_commit")
    source_dirty = source.get("source_dirty")
    source_platform = source.get("platform")
    if (
        source_commit != workflow_sha
        or source_dirty is not False
        or not isinstance(source_platform, dict)
        or source_platform.get("system") != _RUNNER_SYSTEM[runner_os]
    ):
        raise AuditError("package_subject_mismatch")
    return {
        "archive_bytes": archive_bytes,
        "archive_sha256": archive_sha,
        "package_identity": identity_value,
        "size_gates": normalized_gates,
        "source_commit_matches_workflow": True,
    }


def compare_verified_packages(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    workflow_sha: str,
    runner_os: str,
) -> dict[str, object]:
    """Require the authenticated package evidence to remain byte-equivalent."""

    before_summary = _package_summary(
        before,
        workflow_sha=workflow_sha,
        runner_os=runner_os,
    )
    after_summary = _package_summary(
        after,
        workflow_sha=workflow_sha,
        runner_os=runner_os,
    )
    unchanged = canonical_json_bytes(before) == canonical_json_bytes(after)
    return {
        **before_summary,
        "package_unchanged_after_startup": unchanged,
        "passed": unchanged and before_summary == after_summary,
        "verification_count": 2,
    }


class PackageStartupAudit:
    """Run the bounded PKG-01B startup slice against one existing package."""

    def __init__(
        self,
        *,
        bundle_root: Path,
        package_root: Path,
        runner_os: str,
        workflow_sha: str,
        temp_root: Path,
        inherited_env: Mapping[str, str],
    ) -> None:
        self.bundle_root = _absolute(bundle_root)
        self.package_root = _absolute(package_root)
        self.runner_os = runner_os
        self.workflow_sha = workflow_sha
        self.temp_root = _absolute(temp_root)
        self.inherited_env = dict(inherited_env)
        self.checks: dict[str, dict[str, object]] = {}

    def run(self) -> dict[str, object]:
        self._validate_inputs()
        try:
            before = build_desktop.verify_package(self.bundle_root, self.package_root)
            before_summary = _package_summary(
                before,
                workflow_sha=self.workflow_sha,
                runner_os=self.runner_os,
            )
        except BaseException as exc:
            self.checks["package"] = {
                "error_code": _package_error_code(exc, "package_pre_verification_failed"),
                "passed": False,
                "verification_count": 0,
            }
            self.checks["startup"] = {
                "error_code": "startup_not_run_unauthenticated_package",
                "passed": False,
                "sample_count": 0,
            }
            return self._evidence()

        self.checks["package"] = {
            **before_summary,
            "package_unchanged_after_startup": False,
            "passed": False,
            "verification_count": 1,
        }
        with tempfile.TemporaryDirectory(prefix="mclab-pkg-startup-", dir=self.temp_root) as raw:
            workspace = _require_real_directory(Path(raw), "workspace_unsafe")
            runtime_cwd = workspace / "runtime-cwd"
            runtime_cwd.mkdir()
            _require_real_directory(runtime_cwd, "runtime_cwd_unsafe")
            if _within(runtime_cwd, ROOT) or _physically_within(runtime_cwd, ROOT):
                raise AuditError("runtime_cwd_inside_checkout")
            executable = self.bundle_root / (
                "MCLab.exe" if self.runner_os == "Windows" else "MCLab"
            )
            _require_regular_file(executable, "packaged_executable_missing_or_unsafe")
            startup_root = workspace / "startup"
            startup_root.mkdir()
            samples: list[dict[str, object]] = []
            try:
                for index in range(1, STARTUP_SAMPLES + 1):
                    samples.append(
                        run_startup_sample(
                            executable,
                            cwd=runtime_cwd,
                            root=startup_root,
                            index=index,
                            inherited_env=self.inherited_env,
                        )
                    )
                self.checks["startup"] = evaluate_startup_samples(samples)
            except BaseException as exc:
                self.checks["startup"] = {
                    "error_code": _error_code(exc),
                    "passed": False,
                    "sample_count": len(samples),
                    "samples": samples,
                }
            try:
                after = build_desktop.verify_package(self.bundle_root, self.package_root)
                self.checks["package"] = compare_verified_packages(
                    before,
                    after,
                    workflow_sha=self.workflow_sha,
                    runner_os=self.runner_os,
                )
            except BaseException as exc:
                self.checks["package"] = {
                    **before_summary,
                    "error_code": _package_error_code(
                        exc, "package_post_verification_failed"
                    ),
                    "package_unchanged_after_startup": False,
                    "passed": False,
                    "verification_count": 1,
                }
        return self._evidence()

    def _validate_inputs(self) -> None:
        if self.runner_os not in _RUNNER_SYSTEM:
            raise AuditError("runner_os_invalid")
        if _SHA40_RE.fullmatch(self.workflow_sha) is None:
            raise AuditError("workflow_sha_invalid")
        expected_bundle = _absolute(ROOT / "dist" / build_desktop.BUNDLE_NAME)
        expected_package = _absolute(ROOT / "dist" / build_desktop.PACKAGE_DIRECTORY_NAME)
        if self.bundle_root != expected_bundle or self.package_root != expected_package:
            raise AuditError("source_package_layout_invalid")
        checkout = _require_real_directory(ROOT, "checkout_root_unsafe")
        for path in (self.bundle_root, self.package_root):
            if not _within(path, checkout) or not _physically_within(path, checkout):
                raise AuditError("source_package_outside_checkout")
        temp_root = _require_real_directory(self.temp_root, "temp_root_unsafe")
        if _within(temp_root, checkout) or _physically_within(temp_root, checkout):
            raise AuditError("temp_root_inside_checkout")

    def _evidence(self) -> dict[str, object]:
        overall_pass = set(self.checks) == {"package", "startup"} and all(
            check.get("passed") is True for check in self.checks.values()
        )
        settings_verified = self.checks.get("startup", {}).get("passed") is True
        return {
            "artifact_class": ARTIFACT_CLASS,
            "checks": self.checks,
            "environment": {
                "fresh_settings_per_sample": settings_verified,
                "inherited_values_recorded": False,
                "policy": "allowlist-v1",
                "runtime_cwd_outside_checkout": True,
                "settings_fallbacks_enabled": False if settings_verified else None,
                "settings_format": "explicit-ini" if settings_verified else None,
                "settings_isolation_status": (
                    "verified-by-startup-processes"
                    if settings_verified
                    else "not-verified"
                ),
                "settings_path_policy": "required-unique-absolute-per-sample",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_pass": overall_pass,
            "platform": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "runner_os": self.runner_os,
                "system": platform.system(),
            },
            "required_check_contexts": list(REQUIRED_CHECK_CONTEXTS),
            "schema": SCHEMA,
            "subject": {
                "package_class": "unsigned-development",
                "provenance_scope": PROVENANCE_SCOPE,
                "workflow_sha": self.workflow_sha,
            },
            "thresholds": {
                "archive_bytes": build_desktop.ARCHIVE_LIMIT_BYTES,
                "one_folder_bytes": build_desktop.ONE_FOLDER_LIMIT_BYTES,
                "startup_failure_count": 0,
                "startup_p95_ms": STARTUP_P95_LIMIT_MS,
                "startup_samples": STARTUP_SAMPLES,
            },
        }


def _package_error_code(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, AuditError):
        return exc.code
    if isinstance(exc, build_desktop.PackageValidationError):
        return fallback
    return _error_code(exc)


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, AuditError):
        return exc.code
    return f"unexpected_{type(exc).__name__.casefold()}"


def _failure_evidence(
    *,
    runner_os: str,
    workflow_sha: str,
    error_code: str,
) -> dict[str, object]:
    return {
        "artifact_class": ARTIFACT_CLASS,
        "checks": {"harness": {"error_code": error_code, "passed": False}},
        "environment": {
            "fresh_settings_per_sample": False,
            "inherited_values_recorded": False,
            "policy": "allowlist-v1",
            "runtime_cwd_outside_checkout": True,
            "settings_fallbacks_enabled": None,
            "settings_format": None,
            "settings_isolation_status": "not-verified",
            "settings_path_policy": "required-unique-absolute-per-sample",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pass": False,
        "platform": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "runner_os": runner_os,
            "system": platform.system(),
        },
        "required_check_contexts": list(REQUIRED_CHECK_CONTEXTS),
        "schema": SCHEMA,
        "subject": {
            "package_class": "unsigned-development",
            "provenance_scope": PROVENANCE_SCOPE,
            "workflow_sha": workflow_sha,
        },
        "thresholds": {
            "archive_bytes": build_desktop.ARCHIVE_LIMIT_BYTES,
            "one_folder_bytes": build_desktop.ONE_FOLDER_LIMIT_BYTES,
            "startup_failure_count": 0,
            "startup_p95_ms": STARTUP_P95_LIMIT_MS,
            "startup_samples": STARTUP_SAMPLES,
        },
    }


def _resolve_checkout_input(value: Path) -> Path:
    return _absolute(value if value.is_absolute() else ROOT / value)


def _validate_output_path(output: Path, workflow_sha: str, runner_os: str) -> Path:
    if _SHA40_RE.fullmatch(workflow_sha) is None:
        raise AuditError("workflow_sha_invalid")
    if runner_os not in _RUNNER_SYSTEM:
        raise AuditError("runner_os_invalid")
    target = _absolute(output if output.is_absolute() else ROOT / output)
    expected = (
        ROOT
        / "build"
        / "validation"
        / workflow_sha
        / f"pkg-{runner_os}"
        / "package_startup.json"
    )
    if target != _absolute(expected):
        raise AuditError("evidence_output_path_invalid")
    return target


def _prepare_evidence_parent(target: Path) -> None:
    """Create the fixed in-checkout evidence hierarchy without following links."""

    root = _require_real_directory(ROOT, "evidence_root_unsafe")
    try:
        relative = _absolute(target).parent.relative_to(root)
    except ValueError as exc:
        raise AuditError("evidence_parent_outside_checkout") from exc
    current = root
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir(mode=0o755)
        except FileExistsError:
            pass
        _require_real_directory(current, "evidence_parent_unsafe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--runner-os", choices=tuple(_RUNNER_SYSTEM), required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--temp-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = _validate_output_path(args.output, args.workflow_sha, args.runner_os)
    except BaseException as exc:
        print(
            f"Refusing unsafe packaged startup evidence target: {_error_code(exc)}",
            file=sys.stderr,
        )
        return 2
    initial_evidence = _failure_evidence(
        runner_os=args.runner_os,
        workflow_sha=args.workflow_sha,
        error_code="audit_incomplete_or_interrupted",
    )
    try:
        _prepare_evidence_parent(output)
        write_canonical_json(output, initial_evidence)
    except BaseException as exc:
        print(
            f"Could not initialize packaged startup evidence: {_error_code(exc)}",
            file=sys.stderr,
        )
        return 2

    try:
        audit = PackageStartupAudit(
            bundle_root=_resolve_checkout_input(args.bundle_root),
            package_root=_resolve_checkout_input(args.package_root),
            runner_os=args.runner_os,
            workflow_sha=args.workflow_sha,
            temp_root=args.temp_root,
            inherited_env=os.environ,
        )
        evidence = audit.run()
    except BaseException as exc:
        evidence = _failure_evidence(
            runner_os=args.runner_os,
            workflow_sha=args.workflow_sha,
            error_code=_error_code(exc),
        )
    try:
        evidence_bytes = write_canonical_json(output, evidence)
    except BaseException as exc:
        print(
            f"Could not write packaged startup evidence: {_error_code(exc)}",
            file=sys.stderr,
        )
        return 2
    label = "PASS" if evidence.get("overall_pass") is True else "FAIL"
    print(
        f"{label} packaged startup development gate; "
        f"canonical evidence bytes={evidence_bytes}"
    )
    return 0 if evidence.get("overall_pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
