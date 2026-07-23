#!/usr/bin/env python3
"""Audit one copied unsigned desktop package against the internal G2 gate.

The package is first authenticated against the clean checkout, copied into an
exact ``dist/MCLab`` + ``dist/MCLab-package`` layout below runner temporary
storage, and verified again in explicitly non-gating offline mode.  Every
runtime command then executes the copied absolute executable from a third
directory outside both the checkout and copied package.

Only the bounded canonical summary named by ``--output`` is durable.  Package
copies, simulated learner outputs, cleanup fixtures, Qt probes, and process
logs are temporary.  This script never applies cleanup and does not turn an
unsigned development artifact into release provenance.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scripts import build_desktop  # noqa: E402
from scripts.bootstrap_and_run import verify_output_artifacts  # noqa: E402
from mclab.application.artifacts import (  # noqa: E402
    verify_manifest,
    verify_terminal_batch_output,
)
from mclab.output_cleanup import build_cleanup_plan  # noqa: E402


SCHEMA = "mclab.package-e2e.v1"
ARTIFACT_CLASS = "unsigned-development-g2-readiness-evidence"
PROBE_SCHEMA = "mclab.batch-probe.v1"
REQUEST_SCHEMA = "mclab.batch-probe-request.v1"
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_PROBE_BYTES = 256 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TREE_ENTRIES = 200_000
MAX_PROCESS_IDENTITIES = 128
MIB = 1024 * 1024

STARTUP_SAMPLES = 20
STARTUP_P95_LIMIT_MS = 5000.0
COURSE_TIMEOUT_SECONDS = 300.0
COURSE_PROCESS_TIMEOUT_SECONDS = 330.0
COURSE_UI_GAP_LIMIT_MS = 500.0
COURSE_OUTPUT_LIMIT_BYTES = 150 * MIB
REPRO_ABS_TOL = 1e-12
REPRO_REL_TOL = 1e-10
REPRO_SEED = 104729
PROCESS_EXIT_DEADLINE_SECONDS = 10.0

REPRO_METRICS = (
    "max_abs_position",
    "final_position",
    "final_velocity",
    "final_total_energy",
)
EXPECTED_PROGRESS_NAMES = (
    "lab01_msd_compare",
    "lab02_pid_compare",
    "lab03_2dof_compare",
    "lab04_cartesian_compare",
    "lab04_wall_compare",
)
EXPECTED_PROBE_KEYS = frozenset(
    {
        "action",
        "cancel_requested",
        "child_pid",
        "current",
        "elapsed_seconds",
        "error_code",
        "heartbeat_count",
        "max_ui_gap_ms",
        "name",
        "output",
        "phase",
        "progress",
        "schema",
        "settled",
        "status",
        "total",
    }
)
EXPECTED_PROGRESS_KEYS = frozenset({"current", "elapsed_ms", "name", "total"})
OBSERVABLE_PROBE_TERMINAL_STATUSES = frozenset({"completed", "error", "stopped"})
OBSERVABLE_PROBE_ERROR_CODES = frozenset(
    {
        "",
        "batch_failed",
        "close_target_missing",
        "invalid_progress",
        "invalid_request",
        "non_absolute_output",
        "probe_timeout",
        "start_failed_without_terminal",
        "unexpected_terminal_status",
    }
)
EXPECTED_CLEANUP_PLAN_KEYS = frozenset(
    {
        "eligible",
        "keep",
        "plan_id",
        "retained",
        "root",
        "root_exists",
        "root_token",
        "schema_version",
        "selected",
        "skipped",
    }
)
EXPECTED_CLEANUP_ENTRY_KEYS = frozenset(
    {"finished_at", "name", "path", "scenario_id", "status", "token"}
)
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
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/]")
_EMBEDDED_POSIX_ABSOLUTE_RE = re.compile(r"(?:^|[\s=:;,(\[{])/(?!/)[^\s\"'<>]+")
_REPARSE_POINT_FLAG = 0x400
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
        "SYSTEMROOT",
        "SystemRoot",
        "TZ",
        "WINDIR",
    }
)
_INJECTION_ENV_NAMES = frozenset(
    {
        "CONDA_DEFAULT_ENV",
        "CONDA_PREFIX",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "MPLCONFIGDIR",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
        "QT_PLUGIN_PATH",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    }
)


class AuditError(RuntimeError):
    """A stable fail-closed E2E error safe to summarize without raw paths."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CommandResult:
    return_code: int
    duration_ms: float
    timed_out: bool
    stdout_bytes: int
    stderr_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    process_lifecycle_passed: bool = True
    process_forced_cleanup: bool = False
    process_observation_error_code: str = ""
    process_orphan_count: int = 0
    process_post_cleanup_survivor_count: int = 0

    @property
    def passed(self) -> bool:
        return self.return_code == 0 and not self.timed_out and self.process_lifecycle_passed


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    ppid: int
    start_marker: str


def canonical_json_bytes(payload: object) -> bytes:
    """Return compact canonical UTF-8 JSON with one final LF."""

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT_FLAG)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _within(path: Path, parent: Path) -> bool:
    candidate = _absolute(path)
    boundary = _absolute(parent)
    return candidate == boundary or candidate.is_relative_to(boundary)


def _canonical(path: Path) -> Path:
    """Resolve the physical path, including links in any existing ancestor."""

    try:
        return _absolute(path).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AuditError("path_canonicalization_failed") from exc


def _physically_within(path: Path, parent: Path) -> bool:
    candidate = _canonical(path)
    boundary = _canonical(parent)
    return candidate == boundary or candidate.is_relative_to(boundary)


def _inside_boundary(path: Path, parent: Path) -> bool:
    """Treat either lexical or canonical containment as inside a boundary."""

    return _within(path, parent) or _physically_within(path, parent)


def _strictly_within_boundary(path: Path, parent: Path) -> bool:
    """Require both lexical and canonical containment for an allowed child."""

    return _within(path, parent) and _physically_within(path, parent)


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


def read_json_mapping(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    """Read a bounded, duplicate-key-free JSON object without following a link."""

    source = _require_regular_file(path, "json_not_regular")
    metadata = source.lstat()
    if metadata.st_size <= 0 or metadata.st_size > max_bytes:
        raise AuditError("json_size_invalid")
    try:
        raw = source.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise AuditError("json_invalid") from exc
    if not isinstance(payload, dict):
        raise AuditError("json_root_not_object")
    return payload


def _write_atomic(path: Path, payload: bytes, *, max_bytes: int) -> None:
    if not payload or len(payload) > max_bytes:
        raise AuditError("evidence_size_invalid")
    target = _absolute(path)
    target.parent.mkdir(parents=True, exist_ok=True)
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


def write_canonical_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    max_bytes: int = MAX_EVIDENCE_BYTES,
) -> int:
    encoded = canonical_json_bytes(payload)
    _write_atomic(path, encoded, max_bytes=max_bytes)
    if _require_regular_file(path, "evidence_missing").read_bytes() != encoded:
        raise AuditError("evidence_reread_mismatch")
    return len(encoded)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    source = _require_regular_file(path, "hash_source_unsafe")
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_digest() -> str:
    return hashlib.sha256(b"").hexdigest()


def _file_summary(path: Path) -> tuple[int, str]:
    try:
        source = _require_regular_file(path, "command_log_unsafe")
    except AuditError:
        return 0, _empty_digest()
    return source.stat().st_size, _sha256_file(source)


def _command_payload(result: CommandResult, *, passed: bool | None = None) -> dict[str, Any]:
    return {
        "duration_ms": result.duration_ms,
        "passed": result.passed if passed is None else bool(passed),
        "process_forced_cleanup": result.process_forced_cleanup,
        "process_lifecycle_passed": result.process_lifecycle_passed,
        "process_observation_error_code": result.process_observation_error_code,
        "process_orphan_count": result.process_orphan_count,
        "process_post_cleanup_survivor_count": result.process_post_cleanup_survivor_count,
        "return_code": result.return_code,
        "stderr_bytes": result.stderr_bytes,
        "stderr_sha256": result.stderr_sha256,
        "stdout_bytes": result.stdout_bytes,
        "stdout_sha256": result.stdout_sha256,
        "timed_out": result.timed_out,
    }


def _command_aggregate_payload(result: CommandResult) -> dict[str, Any]:
    """Return command counts/state without fingerprints of private stdout content."""

    return {
        "duration_ms": result.duration_ms,
        "passed": result.passed,
        "process_forced_cleanup": result.process_forced_cleanup,
        "process_lifecycle_passed": result.process_lifecycle_passed,
        "process_observation_error_code": result.process_observation_error_code,
        "process_orphan_count": result.process_orphan_count,
        "process_post_cleanup_survivor_count": result.process_post_cleanup_survivor_count,
        "return_code": result.return_code,
        "stderr_bytes": result.stderr_bytes,
        "stdout_bytes": result.stdout_bytes,
        "timed_out": result.timed_out,
    }


def _with_process_lifecycle(
    result: CommandResult,
    lifecycle: Mapping[str, Any],
) -> CommandResult:
    """Attach safe settlement aggregates to a completed command result."""

    return CommandResult(
        return_code=result.return_code,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
        stdout_bytes=result.stdout_bytes,
        stderr_bytes=result.stderr_bytes,
        stdout_sha256=result.stdout_sha256,
        stderr_sha256=result.stderr_sha256,
        process_lifecycle_passed=bool(lifecycle["passed"]),
        process_forced_cleanup=bool(lifecycle["forced_cleanup"]),
        process_observation_error_code=str(lifecycle["observation_error_code"]),
        process_orphan_count=int(lifecycle["orphan_count"]),
        process_post_cleanup_survivor_count=int(lifecycle["post_cleanup_survivor_count"]),
    )


def validate_cleanup_plan(
    payload: Mapping[str, Any],
    *,
    cleanup_root: Path,
    synthetic_run: Path,
    expected_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact synthetic ``CleanupPlan`` without retaining identifiers."""

    if set(payload) != EXPECTED_CLEANUP_PLAN_KEYS:
        raise AuditError("cleanup_plan_keys_invalid")
    if type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1:
        raise AuditError("cleanup_plan_schema_invalid")
    if type(payload.get("root_exists")) is not bool or payload.get("root_exists") is not True:
        raise AuditError("cleanup_plan_root_state_invalid")
    if type(payload.get("keep")) is not int or payload.get("keep") != 0:
        raise AuditError("cleanup_plan_keep_invalid")
    if payload.get("root") != os.fspath(_absolute(cleanup_root)):
        raise AuditError("cleanup_plan_root_invalid")
    for name in ("plan_id", "root_token"):
        value = payload.get(name)
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise AuditError("cleanup_plan_digest_invalid")

    eligible = payload.get("eligible")
    retained = payload.get("retained")
    selected = payload.get("selected")
    skipped = payload.get("skipped")
    if (
        not isinstance(eligible, list)
        or len(eligible) != 1
        or retained != []
        or not isinstance(selected, list)
        or len(selected) != 1
        or skipped != []
        or selected != eligible
    ):
        raise AuditError("cleanup_plan_selection_invalid")
    entry = eligible[0]
    if not isinstance(entry, dict) or set(entry) != EXPECTED_CLEANUP_ENTRY_KEYS:
        raise AuditError("cleanup_plan_entry_keys_invalid")
    if any(not isinstance(entry.get(name), str) for name in EXPECTED_CLEANUP_ENTRY_KEYS):
        raise AuditError("cleanup_plan_entry_type_invalid")
    if (
        entry.get("name") != synthetic_run.name
        or entry.get("path") != os.fspath(_absolute(synthetic_run))
        or entry.get("scenario_id") != "lab01.default"
        or entry.get("status") != "completed"
        or not entry.get("finished_at")
    ):
        raise AuditError("cleanup_plan_entry_identity_invalid")
    token = entry.get("token")
    if not isinstance(token, str) or _SHA256_RE.fullmatch(token) is None:
        raise AuditError("cleanup_plan_entry_token_invalid")
    if payload != expected_plan:
        raise AuditError("cleanup_plan_binding_invalid")
    return {
        "eligible_count": 1,
        "exact_synthetic_selection": True,
        "retained_count": 0,
        "schema_version": 1,
        "selected_count": 1,
        "skipped_count": 0,
    }


def evaluate_cleanup_dry_run(
    command: CommandResult,
    stdout_path: Path,
    *,
    cleanup_root: Path,
    synthetic_run: Path,
    expected_plan: Mapping[str, Any],
    before_fingerprint: str,
    after_fingerprint: str,
    trash_absent: bool,
) -> dict[str, Any]:
    """Evaluate a dry-run while retaining only bounded, non-identifying aggregates."""

    plan = {
        "contract_error_code": "",
        "eligible_count": 0,
        "exact_synthetic_selection": False,
        "retained_count": 0,
        "schema_version": 0,
        "selected_count": 0,
        "skipped_count": 0,
    }
    try:
        raw_plan = read_json_mapping(stdout_path, max_bytes=MAX_PROBE_BYTES)
        plan.update(
            validate_cleanup_plan(
                raw_plan,
                cleanup_root=cleanup_root,
                synthetic_run=synthetic_run,
                expected_plan=expected_plan,
            )
        )
    except BaseException as exc:
        plan["contract_error_code"] = _error_code(exc)
    tree_unchanged = before_fingerprint == after_fingerprint
    passed = (
        command.passed
        and not plan["contract_error_code"]
        and plan["exact_synthetic_selection"] is True
        and tree_unchanged
        and trash_absent
    )
    return {
        "command": _command_aggregate_payload(command),
        "passed": passed,
        "plan": plan,
        "synthetic_temp_only": True,
        "trash_absent": bool(trash_absent),
        "tree_unchanged": tree_unchanged,
    }


def run_command(
    executable: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    log_root: Path,
    label: str,
    timeout_seconds: float,
) -> CommandResult:
    """Run a copied GUI or CLI executable while keeping output bounded off-memory."""
    command, lifecycle = run_observed_command(
        executable,
        arguments,
        cwd=cwd,
        env=env,
        log_root=log_root,
        label=label,
        timeout_seconds=timeout_seconds,
    )
    return _with_process_lifecycle(command, lifecycle)


def scrubbed_environment(
    inherited: Mapping[str, str],
    state_root: Path,
    *,
    extra: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build an allowlisted child environment and record names, never values."""

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

    result = {name: value for name, value in inherited.items() if name in _ENV_ALLOWLIST}
    for name, directory in directories.items():
        result[name] = os.fspath(directory)
    result.update(
        {
            "MCLAB_DATA_DIR": os.fspath(root / "data"),
            "MCLAB_INSTANCE_LOCK": os.fspath(root / "instance.lock"),
            "MPLBACKEND": "Agg",
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
        }
    )
    if extra:
        for name, value in extra.items():
            if not name.startswith("MCLAB_"):
                raise AuditError("extra_environment_not_mclab")
            result[name] = value

    injection_names = sorted(
        name
        for name in inherited
        if name.startswith(("MCLAB_", "PYTHON", "DYLD_", "CONDA_"))
        or name in _INJECTION_ENV_NAMES
    )
    metadata = {
        "inherited_name_count": len(inherited),
        "passed_inherited_names": sorted(name for name in inherited if name in _ENV_ALLOWLIST),
        "policy": "allowlist-v1",
        "scrubbed_injection_names": injection_names,
        "values_recorded": False,
    }
    return result, metadata


def _copytree_no_hardlinks(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
    for source_member in source.rglob("*"):
        if source_member.is_symlink() or not source_member.is_file():
            continue
        relative = source_member.relative_to(source)
        copied_member = destination / relative
        try:
            if os.path.samefile(source_member, copied_member):
                raise AuditError("package_copy_hardlink")
        except FileNotFoundError as exc:
            raise AuditError("package_copy_missing_member") from exc


def copy_package_layout(
    bundle_root: Path,
    package_root: Path,
    destination_parent: Path,
    *,
    checkout_root: Path = ROOT,
) -> tuple[Path, Path]:
    """Copy both package trees into the verifier's fixed outside-checkout layout."""

    bundle = _require_real_directory(bundle_root, "bundle_root_unsafe")
    package = _require_real_directory(package_root, "package_root_unsafe")
    if (
        bundle.name != build_desktop.BUNDLE_NAME
        or package.name != build_desktop.PACKAGE_DIRECTORY_NAME
        or bundle.parent != package.parent
        or bundle.parent.name != "dist"
    ):
        raise AuditError("source_package_layout_invalid")
    destination = _absolute(destination_parent)
    if _inside_boundary(destination, checkout_root):
        raise AuditError("package_copy_inside_checkout")
    if destination.exists() or destination.is_symlink():
        raise AuditError("package_copy_destination_exists")
    dist = destination / "dist"
    dist.mkdir(parents=True)
    if _inside_boundary(dist, checkout_root):
        raise AuditError("package_copy_inside_checkout")
    _require_real_directory(dist, "package_copy_destination_unsafe")
    copied_bundle = dist / build_desktop.BUNDLE_NAME
    copied_package = dist / build_desktop.PACKAGE_DIRECTORY_NAME
    _copytree_no_hardlinks(bundle, copied_bundle)
    _copytree_no_hardlinks(package, copied_package)
    return copied_bundle, copied_package


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> tuple[float, int]:
    if not values or not 0.0 < percentile <= 1.0:
        raise AuditError("percentile_inputs_invalid")
    normalized = [float(value) for value in values]
    if any(not math.isfinite(value) for value in normalized):
        raise AuditError("percentile_nonfinite")
    ordered = sorted(normalized)
    rank = int(math.ceil(percentile * len(ordered)))
    return ordered[rank - 1], rank


def compare_reproducibility(
    summaries: Sequence[Mapping[str, Any]],
    config_sha256: Sequence[str],
    manifest_error_counts: Sequence[int],
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    valid = len(summaries) == 3 and len(config_sha256) == 3 and len(manifest_error_counts) == 3
    if not valid:
        return {
            "comparisons": comparisons,
            "config_digest_count": len(set(config_sha256)),
            "hash_error_count": sum(manifest_error_counts),
            "passed": False,
        }
    baseline = summaries[0]
    for run_index, summary in enumerate(summaries[1:], start=2):
        for metric in REPRO_METRICS:
            try:
                expected = float(baseline[metric])
                actual = float(summary[metric])
            except (KeyError, TypeError, ValueError):
                metric_passed = False
                difference = None
            else:
                metric_passed = (
                    math.isfinite(expected)
                    and math.isfinite(actual)
                    and math.isclose(
                        actual,
                        expected,
                        abs_tol=REPRO_ABS_TOL,
                        rel_tol=REPRO_REL_TOL,
                    )
                )
                difference = abs(actual - expected) if math.isfinite(actual - expected) else None
            comparisons.append(
                {
                    "absolute_difference": difference,
                    "metric": metric,
                    "passed": metric_passed,
                    "run": run_index,
                }
            )
    passed = (
        all(item["passed"] for item in comparisons)
        and len(comparisons) == 2 * len(REPRO_METRICS)
        and len(set(config_sha256)) == 1
        and sum(manifest_error_counts) == 0
    )
    return {
        "comparisons": comparisons,
        "config_digest_count": len(set(config_sha256)),
        "hash_error_count": sum(manifest_error_counts),
        "passed": passed,
    }


def _tree_members(root: Path) -> tuple[list[Path], int]:
    boundary = _require_real_directory(root, "tree_root_unsafe")
    files: list[Path] = []
    total_bytes = 0
    pending = [boundary]
    seen = 0
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise AuditError("tree_scan_failed") from exc
        seen += len(entries)
        if seen > MAX_TREE_ENTRIES:
            raise AuditError("tree_member_limit")
        for entry in entries:
            member = Path(entry.path)
            metadata = member.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                raise AuditError("tree_link_rejected")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(member)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(member)
                total_bytes += int(metadata.st_size)
            else:
                raise AuditError("tree_special_file_rejected")
    return files, total_bytes


def tree_fingerprint(root: Path) -> str:
    files, _total = _tree_members(root)
    records = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return hashlib.sha256(canonical_json_bytes(records)).hexdigest()


def verify_manifest_tree(root: Path) -> dict[str, Any]:
    files, _total = _tree_members(root)
    manifest_dirs = sorted(
        {path.parent for path in files if path.name == "manifest.json"},
        key=lambda item: item.relative_to(root).as_posix(),
    )
    error_count = 0
    status_counts: dict[str, int] = {}
    for directory in manifest_dirs:
        error_count += len(verify_manifest(directory))
        try:
            status = _manifest_status(directory)
        except AuditError:
            status = ""
        label = status or "invalid"
        status_counts[label] = status_counts.get(label, 0) + 1
    return {
        "hash_error_count": error_count,
        "manifest_count": len(manifest_dirs),
        "passed": bool(manifest_dirs) and error_count == 0,
        "status_counts": status_counts,
    }


def transient_batch_members(root: Path) -> list[str]:
    files, _total = _tree_members(root)
    matches: set[str] = set()
    for path in files:
        if path.name.startswith(".mclab-batch-"):
            matches.add(path.name)
    for directory, names, _files in os.walk(root, followlinks=False):
        del directory
        for name in names:
            if name.startswith(".mclab-batch-"):
                matches.add(name)
    return sorted(matches)


def _manifest_status(path: Path) -> str:
    payload = read_json_mapping(path / "manifest.json")
    status = payload.get("status")
    return status if isinstance(status, str) else ""


def _number(payload: Mapping[str, Any], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError("probe_number_invalid")
    result = float(value)
    if not math.isfinite(result):
        raise AuditError("probe_number_nonfinite")
    return result


def _integer(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if type(value) is not int:
        raise AuditError("probe_integer_invalid")
    return int(value)


def validate_probe_payload(
    payload: Mapping[str, Any],
    *,
    action: str,
    phase: str,
    status: str,
) -> list[dict[str, Any]]:
    """Validate the exact bounded Qt/batch lifecycle probe contract."""

    if set(payload) != EXPECTED_PROBE_KEYS:
        raise AuditError("probe_keys_invalid")
    identity = {
        "schema": PROBE_SCHEMA,
        "action": action,
        "phase": phase,
        "status": status,
    }
    for name, expected in identity.items():
        if payload.get(name) != expected:
            raise AuditError(f"probe_{name}_invalid")
    if type(payload.get("cancel_requested")) is not bool or type(
        payload.get("settled")
    ) is not bool:
        raise AuditError("probe_boolean_invalid")
    expected_cancel = phase == "terminal" and action in {
        "batch_probe_cancel",
        "batch_probe_close",
    }
    if payload.get("cancel_requested") is not expected_cancel:
        raise AuditError("probe_cancel_state_invalid")
    if payload.get("settled") is not (phase == "terminal"):
        raise AuditError("probe_settle_state_invalid")
    error_code = payload.get("error_code")
    if not isinstance(error_code, str) or error_code:
        raise AuditError("probe_error_invalid")
    output = payload.get("output")
    name = payload.get("name")
    if not isinstance(output, str) or not output or not Path(output).is_absolute():
        raise AuditError("probe_output_invalid")
    if not isinstance(name, str) or not name:
        raise AuditError("probe_name_invalid")
    child_pid = _integer(payload, "child_pid")
    current = _integer(payload, "current")
    total = _integer(payload, "total")
    heartbeat_count = _integer(payload, "heartbeat_count")
    elapsed_seconds = _number(payload, "elapsed_seconds")
    max_ui_gap_ms = _number(payload, "max_ui_gap_ms")
    if (
        child_pid <= 0
        or total != 5
        or not 1 <= current <= total
        or heartbeat_count < 0
        or elapsed_seconds < 0
        or max_ui_gap_ms < 0
    ):
        raise AuditError("probe_range_invalid")
    progress_value = payload.get("progress")
    if not isinstance(progress_value, list) or len(progress_value) != current:
        raise AuditError("probe_progress_invalid")
    progress: list[dict[str, Any]] = []
    previous_elapsed = -1.0
    for expected_current, item in enumerate(progress_value, start=1):
        if not isinstance(item, dict) or set(item) != EXPECTED_PROGRESS_KEYS:
            raise AuditError("probe_progress_keys_invalid")
        item_current = _integer(item, "current")
        item_total = _integer(item, "total")
        item_elapsed = _number(item, "elapsed_ms")
        item_name = item.get("name")
        if (
            item_current != expected_current
            or item_total != 5
            or item_name != EXPECTED_PROGRESS_NAMES[expected_current - 1]
            or item_elapsed < previous_elapsed
        ):
            raise AuditError("probe_progress_sequence_invalid")
        previous_elapsed = item_elapsed
        progress.append(
            {
                "current": item_current,
                "elapsed_ms": item_elapsed,
                "name": item_name,
                "total": item_total,
            }
        )
    if name != EXPECTED_PROGRESS_NAMES[current - 1]:
        raise AuditError("probe_current_name_invalid")
    return progress


def evaluate_course_output(
    output: Path,
    probe: Mapping[str, Any],
    command: CommandResult,
    *,
    allowed_root: Path,
) -> dict[str, Any]:
    if (
        not _strictly_within_boundary(output, allowed_root)
        or _canonical(output) == _canonical(allowed_root)
    ):
        raise AuditError("course_output_outside_isolation")
    output = _require_real_directory(output, "course_output_missing")
    summary = read_json_mapping(output / "summary.json")
    manifest = read_json_mapping(output / "manifest.json")
    files, output_bytes = _tree_members(output)
    direct_child_reports = [path for path in output.glob("*/report.html") if path.is_file()]
    course_reports = int((output / "report.html").is_file()) + len(direct_child_reports)
    comparison_plots = [
        path
        for path in files
        if path.suffix.casefold() == ".png" and path.parent.name == "comparison_plots"
    ]
    integrity = verify_manifest_tree(output)
    terminal_errors = verify_terminal_batch_output(output, expected_status="completed")
    transients = transient_batch_members(output)
    progress = validate_probe_payload(
        probe,
        action="batch_probe_complete",
        phase="terminal",
        status="completed",
    )
    elapsed_seconds = _number(probe, "elapsed_seconds")
    max_ui_gap_ms = _number(probe, "max_ui_gap_ms")
    heartbeat_count = _integer(probe, "heartbeat_count")
    checks = {
        "artifact_integrity": integrity["passed"]
        and integrity["manifest_count"] == 60
        and integrity.get("status_counts") == {"completed": 60},
        "comparison_plots": len(comparison_plots) >= 5,
        "completed": probe.get("status") == "completed" and command.return_code == 0,
        "five_batch_sets": summary.get("child_batches") == 5 and len(direct_child_reports) == 5,
        "manifest_complete": manifest.get("scenario_id") == "batch.all"
        and manifest.get("status") == "completed",
        "output_size": output_bytes <= COURSE_OUTPUT_LIMIT_BYTES,
        "probe_contract": True,
        "progress_1_through_5": [item["current"] for item in progress] == [1, 2, 3, 4, 5]
        and [item["name"] for item in progress] == list(EXPECTED_PROGRESS_NAMES)
        and all(item["total"] == 5 for item in progress),
        "scenario_runs": summary.get("scenario_runs") == 54,
        "six_course_reports": course_reports == 6,
        "strict_terminal": not terminal_errors,
        "transient_cleanup": not transients,
        "ui_heartbeat": heartbeat_count >= 10 and max_ui_gap_ms <= COURSE_UI_GAP_LIMIT_MS,
        "within_timeout": elapsed_seconds <= COURSE_TIMEOUT_SECONDS and not command.timed_out,
    }
    return {
        "checks": checks,
        "comparison_plot_count": len(comparison_plots),
        "course_report_count": course_reports,
        "elapsed_seconds": elapsed_seconds if math.isfinite(elapsed_seconds) else None,
        "hash_error_count": integrity["hash_error_count"],
        "heartbeat_count": heartbeat_count,
        "manifest_count": integrity["manifest_count"],
        "max_ui_gap_ms": max_ui_gap_ms if math.isfinite(max_ui_gap_ms) else None,
        "output_bytes": output_bytes,
        "passed": all(checks.values()),
        "progress": progress,
        "scenario_runs": summary.get("scenario_runs"),
        "status_counts": integrity.get("status_counts", {}),
        "strict_terminal_error_count": len(terminal_errors),
        "transient_member_count": len(transients),
    }


def _linux_process_snapshot() -> dict[int, ProcessIdentity]:
    result: dict[int, ProcessIdentity] = {}
    proc = Path("/proc")
    try:
        candidates = [path for path in proc.iterdir() if path.name.isdigit()]
    except OSError as exc:
        raise AuditError("process_snapshot_failed") from exc
    for candidate in candidates:
        pid = int(candidate.name)
        try:
            status_lines = (candidate / "status").read_text(encoding="utf-8").splitlines()
            ppid = int(next(line.split()[1] for line in status_lines if line.startswith("PPid:")))
            raw_stat = (candidate / "stat").read_text(encoding="utf-8")
            remainder = raw_stat[raw_stat.rfind(")") + 2 :].split()
            start_marker = remainder[19]
        except (OSError, StopIteration, ValueError, IndexError):
            result[pid] = ProcessIdentity(pid=pid, ppid=-1, start_marker="unknown")
            continue
        result[pid] = ProcessIdentity(pid=pid, ppid=ppid, start_marker=start_marker)
    if not result:
        raise AuditError("process_snapshot_empty")
    return result


def _darwin_process_snapshot() -> dict[int, ProcessIdentity]:
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid=,lstart="],
            check=False,
            capture_output=True,
            text=True,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except OSError as exc:
        raise AuditError("process_snapshot_failed") from exc
    if completed.returncode != 0:
        raise AuditError("process_snapshot_failed")
    result: dict[int, ProcessIdentity] = {}
    for line in completed.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        try:
            pid = int(parts[0])
        except (IndexError, ValueError):
            continue
        try:
            ppid = int(parts[1])
            start_marker = parts[2] if len(parts) == 3 and parts[2] else "unknown"
        except (IndexError, ValueError):
            ppid = -1
            start_marker = "unknown"
        result[pid] = ProcessIdentity(pid=pid, ppid=ppid, start_marker=start_marker)
    if not result:
        raise AuditError("process_snapshot_empty")
    return result


def _configure_windows_process_api(kernel32: Any, process_entry_type: Any | None = None) -> None:
    """Declare every Win32 process API boundary used by the harness."""

    from ctypes import wintypes

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    filetime_pointer = ctypes.POINTER(wintypes.FILETIME)
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        filetime_pointer,
        filetime_pointer,
        filetime_pointer,
        filetime_pointer,
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    if process_entry_type is not None:
        entry_pointer = ctypes.POINTER(process_entry_type)
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, entry_pointer]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, entry_pointer]
        kernel32.Process32NextW.restype = wintypes.BOOL


def _windows_handle_valid(handle: object) -> bool:
    if handle is None:
        return False
    try:
        value = ctypes.cast(handle, ctypes.c_void_p).value
    except (TypeError, ValueError):
        try:
            value = int(handle)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    return value not in {None, 0, ctypes.c_void_p(-1).value}


def _windows_process_start_marker(kernel32: Any, pid: int) -> str:
    from ctypes import wintypes

    _configure_windows_process_api(kernel32)
    process = kernel32.OpenProcess(0x1000, False, pid)
    if not _windows_handle_valid(process):
        return "unknown"
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    try:
        if not kernel32.GetProcessTimes(
            process,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return "unknown"
        value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return str(value)
    finally:
        kernel32.CloseHandle(process)


def _windows_process_snapshot(kernel32: Any | None = None) -> dict[int, ProcessIdentity]:
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configure_windows_process_api(kernel32, ProcessEntry32W)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not _windows_handle_valid(snapshot):
        raise AuditError("process_snapshot_failed")
    result: dict[int, ProcessIdentity] = {}
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        available = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        if not available:
            raise AuditError("process_snapshot_empty")
        while available:
            pid = int(entry.th32ProcessID)
            result[pid] = ProcessIdentity(
                pid=pid,
                ppid=int(entry.th32ParentProcessID),
                start_marker=_windows_process_start_marker(kernel32, pid),
            )
            set_last_error = getattr(ctypes, "set_last_error", None)
            get_last_error = getattr(ctypes, "get_last_error", None)
            if not callable(set_last_error) or not callable(get_last_error):
                raise AuditError("process_snapshot_failed")
            set_last_error(0)
            available = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
            if not available and int(get_last_error()) != 18:
                raise AuditError("process_snapshot_failed")
    finally:
        kernel32.CloseHandle(snapshot)
    if not result:
        raise AuditError("process_snapshot_empty")
    return result


def process_snapshot() -> dict[int, ProcessIdentity]:
    if os.name == "nt":
        return _windows_process_snapshot()
    if sys.platform == "darwin":
        return _darwin_process_snapshot()
    return _linux_process_snapshot()


def descendant_identities(
    snapshot: Mapping[int, ProcessIdentity], root_pid: int
) -> dict[int, ProcessIdentity]:
    descendants: dict[int, ProcessIdentity] = {}
    frontier = {root_pid}
    while frontier:
        next_frontier: set[int] = set()
        for identity in snapshot.values():
            if identity.ppid in frontier and identity.pid not in descendants:
                descendants[identity.pid] = identity
                next_frontier.add(identity.pid)
        frontier = next_frontier
        if len(descendants) > MAX_PROCESS_IDENTITIES:
            raise AuditError("process_identity_limit")
    return descendants


def _identity_still_alive(identity: ProcessIdentity, snapshot: Mapping[int, ProcessIdentity]) -> bool:
    current = snapshot.get(identity.pid)
    if current is None:
        return False
    return (
        identity.start_marker == "unknown"
        or current.start_marker == "unknown"
        or current.start_marker == identity.start_marker
    )


def await_identities_absent(
    identities: Mapping[int, ProcessIdentity], *, timeout_seconds: float
) -> tuple[list[ProcessIdentity], float]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    remaining = list(identities.values())
    while remaining and time.monotonic() < deadline:
        snapshot = process_snapshot()
        remaining = [item for item in remaining if _identity_still_alive(item, snapshot)]
        if remaining:
            time.sleep(0.05)
    return remaining, time.monotonic() - started


def _record_process_tree(
    snapshot: Mapping[int, ProcessIdentity],
    root_pid: int,
    observed: dict[tuple[int, str], ProcessIdentity],
) -> None:
    root = snapshot.get(root_pid)
    if root is not None:
        observed[(root.pid, root.start_marker)] = root
    for identity in descendant_identities(snapshot, root_pid).values():
        observed[(identity.pid, identity.start_marker)] = identity
    if len(observed) > MAX_PROCESS_IDENTITIES:
        raise AuditError("process_identity_limit")


def await_observed_tree_absent(
    observed: dict[tuple[int, str], ProcessIdentity],
    *,
    timeout_seconds: float,
) -> tuple[list[ProcessIdentity], float]:
    """Wait for an observed tree while continuing to discover live descendants."""

    started = time.monotonic()
    deadline = started + timeout_seconds
    remaining = list(observed.values())
    while remaining and time.monotonic() < deadline:
        snapshot = process_snapshot()
        live_roots = [item for item in observed.values() if _identity_still_alive(item, snapshot)]
        for identity in live_roots:
            _record_process_tree(snapshot, identity.pid, observed)
        remaining = [
            item for item in observed.values() if _identity_still_alive(item, snapshot)
        ]
        if remaining:
            time.sleep(0.05)
    return remaining, time.monotonic() - started


def _terminate_identity(identity: ProcessIdentity) -> None:
    snapshot = process_snapshot()
    if not _identity_still_alive(identity, snapshot):
        return
    try:
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            _configure_windows_process_api(kernel32)
            process = kernel32.OpenProcess(0x0001, False, identity.pid)
            if _windows_handle_valid(process):
                try:
                    kernel32.TerminateProcess(process, 9)
                finally:
                    kernel32.CloseHandle(process)
        else:
            os.kill(identity.pid, signal.SIGKILL)
    except (OSError, ValueError):
        pass


def _identity_payload(identity: ProcessIdentity) -> dict[str, Any]:
    return {
        "pid": identity.pid,
        "start_marker_sha256": hashlib.sha256(identity.start_marker.encode("utf-8")).hexdigest(),
    }


def _observe_process_tree_best_effort(
    process: Any,
    observed: dict[tuple[int, str], ProcessIdentity],
) -> str:
    try:
        _record_process_tree(process_snapshot(), int(process.pid), observed)
    except BaseException as exc:
        return _error_code(exc)
    return ""


def _bounded_reap_process_handle(
    process: Any,
    observed: dict[tuple[int, str], ProcessIdentity],
    *,
    terminate_first: bool,
) -> tuple[int, bool, str]:
    """Bound Popen reaping without bypassing later identity-based settlement."""

    error_code = _observe_process_tree_best_effort(process, observed)
    if terminate_first:
        try:
            if process.poll() is None:
                process.terminate()
        except BaseException as exc:
            error_code = error_code or _error_code(exc)
    wait_timed_out = False
    try:
        return_code = process.wait(timeout=3.0 if terminate_first else 5.0)
    except subprocess.TimeoutExpired:
        wait_timed_out = True
    except BaseException as exc:
        wait_timed_out = True
        error_code = error_code or _error_code(exc)
    else:
        try:
            return int(return_code), wait_timed_out, error_code
        except (TypeError, ValueError):
            return -9, True, error_code or "process_return_code_invalid"

    observation_error = _observe_process_tree_best_effort(process, observed)
    error_code = error_code or observation_error
    try:
        process.kill()
    except BaseException as exc:
        error_code = error_code or _error_code(exc)
    try:
        return_code = process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        return -9, True, error_code or "process_reap_timeout"
    except BaseException as exc:
        return -9, True, error_code or _error_code(exc)
    try:
        return int(return_code), True, error_code
    except (TypeError, ValueError):
        return -9, True, error_code or "process_return_code_invalid"


def _settle_observed_processes(
    observed: dict[tuple[int, str], ProcessIdentity],
) -> tuple[list[ProcessIdentity], list[ProcessIdentity], float, float, str]:
    """Verify absence, force-clean exact identities, then verify absence again."""

    error_code = ""
    try:
        remaining, settle_seconds = await_observed_tree_absent(
            observed,
            timeout_seconds=PROCESS_EXIT_DEADLINE_SECONDS,
        )
    except BaseException as exc:
        error_code = _error_code(exc)
        remaining = list(observed.values())
        settle_seconds = 0.0
    recorded_orphans = list(remaining)
    for identity in reversed(remaining):
        try:
            _terminate_identity(identity)
        except BaseException as exc:
            error_code = error_code or _error_code(exc)
    post_cleanup: list[ProcessIdentity] = []
    cleanup_seconds = 0.0
    if recorded_orphans:
        try:
            post_cleanup, cleanup_seconds = await_observed_tree_absent(
                observed,
                timeout_seconds=3.0,
            )
        except BaseException as exc:
            error_code = error_code or _error_code(exc)
            post_cleanup = list(observed.values())
    return recorded_orphans, post_cleanup, settle_seconds, cleanup_seconds, error_code


def run_observed_command(
    executable: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    log_root: Path,
    label: str,
    timeout_seconds: float,
) -> tuple[CommandResult, dict[str, Any]]:
    """Run a command while retaining creation-bound identities for its process tree."""

    _require_regular_file(executable, "executable_unsafe")
    _require_real_directory(cwd, "runtime_cwd_unsafe")
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_path = log_root / f"{label}.stdout"
    stderr_path = log_root / f"{label}.stderr"
    started = time.monotonic()
    timed_out = False
    observation_error_code = ""
    observed: dict[tuple[int, str], ProcessIdentity] = {}
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        popen_kwargs: dict[str, Any] = {
            "cwd": cwd,
            "env": dict(env),
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": stderr,
            "shell": False,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen([os.fspath(executable), *arguments], **popen_kwargs)
        deadline = started + timeout_seconds
        try:
            while time.monotonic() < deadline:
                _record_process_tree(process_snapshot(), process.pid, observed)
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            else:
                timed_out = True
                _record_process_tree(process_snapshot(), process.pid, observed)
        except BaseException as exc:
            observation_error_code = _error_code(exc)
            timed_out = True
        return_code, wait_timed_out, reap_error_code = _bounded_reap_process_handle(
            process,
            observed,
            terminate_first=timed_out,
        )
        timed_out = timed_out or wait_timed_out
        observation_error_code = observation_error_code or reap_error_code
    duration_ms = (time.monotonic() - started) * 1000.0
    stdout_bytes, stdout_sha = _file_summary(stdout_path)
    stderr_bytes, stderr_sha = _file_summary(stderr_path)
    command = CommandResult(
        return_code=int(return_code),
        duration_ms=duration_ms,
        timed_out=timed_out,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_sha256=stdout_sha,
        stderr_sha256=stderr_sha,
    )
    (
        recorded_orphans,
        post_cleanup,
        settle_seconds,
        cleanup_seconds,
        settle_error_code,
    ) = _settle_observed_processes(observed)
    observation_error_code = observation_error_code or settle_error_code
    forced_cleanup = bool(recorded_orphans)
    root_identity_observed = any(item.pid == process.pid for item in observed.values())
    lifecycle = {
        "cleanup_seconds": cleanup_seconds,
        "forced_cleanup": forced_cleanup,
        "observed_process_count": len(observed),
        "observed_processes": [
            _identity_payload(item)
            for item in sorted(observed.values(), key=lambda value: value.pid)
        ],
        "orphan_count": len(recorded_orphans),
        "observation_error_code": observation_error_code,
        "passed": not observation_error_code and not forced_cleanup and not post_cleanup,
        "post_cleanup_survivor_count": len(post_cleanup),
        "root_identity_observed": root_identity_observed,
        "settle_seconds": settle_seconds,
    }
    lifecycle["passed"] = bool(lifecycle["passed"] and root_identity_observed)
    return _with_process_lifecycle(command, lifecycle), lifecycle


def _safe_output_from_probe(probe: Mapping[str, Any], allowed_root: Path) -> Path:
    raw = probe.get("output")
    if not isinstance(raw, str) or not raw:
        raise AuditError("probe_output_missing")
    output = _absolute(Path(raw))
    if (
        not _strictly_within_boundary(output, allowed_root)
        or _canonical(output) == _canonical(allowed_root)
    ):
        raise AuditError("probe_output_outside_isolation")
    return output


def _read_probe_if_ready(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return read_json_mapping(path, max_bytes=MAX_PROBE_BYTES)
    except AuditError:
        return None


def _probe_contract_error(
    payload: Mapping[str, Any],
    *,
    action: str,
    phase: str,
    status: str,
) -> str:
    """Return one bounded validation code without retaining probe detail."""

    try:
        validate_probe_payload(
            payload,
            action=action,
            phase=phase,
            status=status,
        )
    except Exception as exc:
        return _error_code(exc)
    return ""


def _read_probe_contract(
    path: Path,
    *,
    action: str,
    phase: str,
    status: str,
) -> tuple[dict[str, Any] | None, str]:
    """Read and validate one probe while retaining only its safe error code."""

    try:
        payload = read_json_mapping(path, max_bytes=MAX_PROBE_BYTES)
    except Exception as exc:
        return None, _error_code(exc)
    return payload, _probe_contract_error(
        payload,
        action=action,
        phase=phase,
        status=status,
    )


def _allowlisted_probe_observation(
    payload: Mapping[str, Any] | None,
    name: str,
    allowed: frozenset[str],
) -> str | None:
    """Return an explicitly allowlisted probe enum, never an arbitrary value."""

    if payload is None:
        return None
    value = payload.get(name)
    return value if isinstance(value, str) and value in allowed else None


def _probe_base_environment(
    inherited: Mapping[str, str],
    state_root: Path,
    *,
    action: str,
    probe_path: Path,
    ready_path: Path,
    request_path: Path,
    auto_quit_ms: int,
) -> tuple[dict[str, str], dict[str, Any]]:
    return scrubbed_environment(
        inherited,
        state_root,
        extra={
            "MCLAB_APP_AUTO_QUIT_MS": str(auto_quit_ms),
            "MCLAB_BATCH_PROBE_PATH": os.fspath(probe_path),
            "MCLAB_BATCH_READY_PATH": os.fspath(ready_path),
            "MCLAB_BATCH_REQUEST_PATH": os.fspath(request_path),
            "MCLAB_FAIL_ON_ERROR": "1",
            "MCLAB_SELF_TEST": "1",
            "MCLAB_SMOKE_ACTION": action,
            "MCLAB_SMOKE_ACTION_MS": "0",
        },
    )


def run_lifecycle_probe(
    executable: Path,
    *,
    cwd: Path,
    inherited_env: Mapping[str, str],
    case_root: Path,
    action: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run a ready/request cancel or close probe and observe its process tree."""

    if action not in {"cancel", "close"}:
        raise AuditError("lifecycle_action_invalid")
    case_root.mkdir(parents=True, exist_ok=False)
    probe_path = case_root / "probe.json"
    ready_path = case_root / "ready.json"
    request_path = case_root / "request.json"
    env, env_metadata = _probe_base_environment(
        inherited_env,
        case_root / "state",
        action=f"batch_probe_{action}",
        probe_path=probe_path,
        ready_path=ready_path,
        request_path=request_path,
        auto_quit_ms=90_000,
    )
    logs = case_root / "logs"
    logs.mkdir()
    stdout_path = logs / "app.stdout"
    stderr_path = logs / "app.stderr"
    started = time.monotonic()
    observed: dict[tuple[int, str], ProcessIdentity] = {}
    ready = False
    request_sent = False
    timed_out = False
    observation_error_code = ""
    direct_child_pid = 0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        popen_kwargs: dict[str, Any] = {
            "cwd": cwd,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": stderr,
            "shell": False,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(
            [os.fspath(executable), "app", "--safe-mode", "--lang", "en"],
            **popen_kwargs,
        )
        deadline = started + 90.0
        try:
            while time.monotonic() < deadline:
                snapshot = process_snapshot()
                _record_process_tree(snapshot, process.pid, observed)
                probe = _read_probe_if_ready(ready_path)
                if probe is not None and probe.get("phase") == "ready":
                    try:
                        validate_probe_payload(
                            probe,
                            action=f"batch_probe_{action}",
                            phase="ready",
                            status="running",
                        )
                        current = _integer(probe, "current")
                        direct_child_pid = _integer(probe, "child_pid")
                    except AuditError:
                        current = 0
                        direct_child_pid = 0
                    ready = current >= 1 and direct_child_pid > 0
                    if ready and not request_sent:
                        write_canonical_json(
                            request_path,
                            {"action": action, "schema": REQUEST_SCHEMA},
                            max_bytes=4096,
                        )
                        request_sent = True
                if process.poll() is not None:
                    break
                time.sleep(0.025)
            else:
                timed_out = True
        except BaseException as exc:
            observation_error_code = _error_code(exc)
            timed_out = True
        return_code, wait_timed_out, reap_error_code = _bounded_reap_process_handle(
            process,
            observed,
            terminate_first=timed_out,
        )
        timed_out = timed_out or wait_timed_out
        observation_error_code = observation_error_code or reap_error_code
    duration_ms = (time.monotonic() - started) * 1000.0
    stdout_bytes, stdout_sha = _file_summary(stdout_path)
    stderr_bytes, stderr_sha = _file_summary(stderr_path)
    command = CommandResult(
        return_code=int(return_code),
        duration_ms=duration_ms,
        timed_out=timed_out,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_sha256=stdout_sha,
        stderr_sha256=stderr_sha,
    )
    (
        recorded_orphans,
        post_cleanup,
        settle_seconds,
        cleanup_seconds,
        settle_error_code,
    ) = _settle_observed_processes(observed)
    forced_cleanup = bool(recorded_orphans)
    root_identity_observed = any(item.pid == process.pid for item in observed.values())
    command = _with_process_lifecycle(
        command,
        {
            "forced_cleanup": forced_cleanup,
            "observation_error_code": observation_error_code or settle_error_code,
            "orphan_count": len(recorded_orphans),
            "passed": not observation_error_code
            and not settle_error_code
            and not forced_cleanup
            and not post_cleanup
            and root_identity_observed,
            "post_cleanup_survivor_count": len(post_cleanup),
        },
    )

    probe_action = f"batch_probe_{action}"
    ready_probe, ready_validation_error_code = _read_probe_contract(
        ready_path,
        action=probe_action,
        phase="ready",
        status="running",
    )
    terminal_probe, terminal_validation_error_code = _read_probe_contract(
        probe_path,
        action=probe_action,
        phase="terminal",
        status="stopped",
    )
    observed_processes = [
        _identity_payload(item)
        for item in sorted(observed.values(), key=lambda value: value.pid)
    ]
    direct_observed = any(item.pid == direct_child_pid for item in observed.values())
    if ready_validation_error_code or terminal_validation_error_code:
        checks = {
            "authenticated_ready": ready
            and request_sent
            and not ready_validation_error_code,
            "direct_child_observed": direct_observed,
            "no_observed_process_alive": not recorded_orphans and not post_cleanup,
            "process_containment": command.process_lifecycle_passed,
            "process_exit": command.return_code == 0 and not command.timed_out,
            "ready_probe_contract": not ready_validation_error_code,
            "root_identity_observed": root_identity_observed,
            "terminal_probe_contract": not terminal_validation_error_code,
        }
        return {
            "checks": checks,
            "command": _command_aggregate_payload(command),
            "cleanup_seconds": cleanup_seconds,
            "direct_child_pid": direct_child_pid,
            "error_code": terminal_validation_error_code
            or ready_validation_error_code,
            "forced_cleanup": forced_cleanup,
            "observed_process_count": len(observed),
            "observed_processes": observed_processes,
            "observed_probe_error_code": _allowlisted_probe_observation(
                terminal_probe,
                "error_code",
                OBSERVABLE_PROBE_ERROR_CODES,
            ),
            "observed_terminal_status": _allowlisted_probe_observation(
                terminal_probe,
                "status",
                OBSERVABLE_PROBE_TERMINAL_STATUSES,
            ),
            "observation_error_code": observation_error_code,
            "orphan_count": len(recorded_orphans),
            "passed": False,
            "post_cleanup_survivor_count": len(post_cleanup),
            "ready_validation_error_code": ready_validation_error_code,
            "settle_error_code": settle_error_code,
            "settle_seconds": settle_seconds,
            "terminal_validation_error_code": terminal_validation_error_code,
        }, env_metadata

    assert ready_probe is not None
    assert terminal_probe is not None
    allowed_outputs = Path(env["MCLAB_DATA_DIR"]) / "outputs"
    output = _safe_output_from_probe(terminal_probe, allowed_outputs)
    integrity = verify_manifest_tree(output)
    terminal_errors = verify_terminal_batch_output(output, expected_status="stopped")
    transients = transient_batch_members(output)
    checks = {
        "authenticated_ready": ready and request_sent,
        "comparison_cleanup": not transients,
        "direct_child_observed": direct_observed,
        "manifest_integrity": integrity["passed"],
        "no_observed_process_alive": not recorded_orphans and not post_cleanup,
        "process_exit": command.return_code == 0 and not command.timed_out,
        "root_identity_observed": root_identity_observed,
        "stopped_manifest": _manifest_status(output) == "stopped",
        "strict_terminal": not terminal_errors,
        "terminal_probe": True,
    }
    payload = {
        "checks": checks,
        "command": _command_payload(command),
        "cleanup_seconds": cleanup_seconds,
        "direct_child_pid": direct_child_pid,
        "forced_cleanup": forced_cleanup,
        "hash_error_count": integrity["hash_error_count"],
        "observed_process_count": len(observed),
        "observed_processes": observed_processes,
        "orphan_count": len(recorded_orphans),
        "observation_error_code": observation_error_code,
        "passed": all(checks.values())
        and not observation_error_code
        and not settle_error_code
        and not forced_cleanup,
        "post_cleanup_survivor_count": len(post_cleanup),
        "settle_error_code": settle_error_code,
        "settle_seconds": settle_seconds,
        "strict_terminal_error_count": len(terminal_errors),
        "transient_member_count": len(transients),
    }
    return payload, env_metadata


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


class PackageE2EAudit:
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
        self.temp_root = _require_real_directory(temp_root, "temp_root_unsafe")
        self.inherited_env = dict(inherited_env)
        self.checks: dict[str, Any] = {}
        self.environment_records: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        if self.runner_os not in {"Linux", "Windows", "macOS"}:
            raise AuditError("runner_os_invalid")
        if _SHA40_RE.fullmatch(self.workflow_sha) is None:
            raise AuditError("workflow_sha_invalid")
        if _inside_boundary(self.temp_root, ROOT):
            raise AuditError("temp_root_inside_checkout")
        if not _strictly_within_boundary(
            self.bundle_root, ROOT
        ) or not _strictly_within_boundary(self.package_root, ROOT):
            raise AuditError("source_package_outside_checkout")

        with tempfile.TemporaryDirectory(prefix="mclab-e2e-", dir=self.temp_root) as temporary:
            workspace = _absolute(Path(temporary))
            copied_bundle, copied_package = self._verify_and_copy(workspace)
            executable = copied_bundle / ("MCLab.exe" if self.runner_os == "Windows" else "MCLab")
            _require_regular_file(executable, "copied_executable_missing")
            runtime_cwd = workspace / "runtime-cwd"
            runtime_cwd.mkdir()
            if _inside_boundary(runtime_cwd, copied_bundle) or _inside_boundary(
                runtime_cwd, ROOT
            ):
                raise AuditError("runtime_cwd_not_independent")

            functional_root = workspace / "functional"
            run_paths = self._functional_checks(executable, runtime_cwd, functional_root)
            self._startup_checks(executable, runtime_cwd, workspace / "startup")
            self._course_check(executable, runtime_cwd, workspace / "course")
            for action in ("cancel", "close"):
                self._lifecycle_check(
                    executable,
                    runtime_cwd,
                    workspace / f"lifecycle-{action}",
                    action,
                )

            del run_paths

        return self._evidence()

    def _lifecycle_check(
        self,
        executable: Path,
        cwd: Path,
        case_root: Path,
        action: str,
    ) -> None:
        """Retain a bounded lifecycle result, including fail-closed diagnostics."""

        try:
            payload, metadata = run_lifecycle_probe(
                executable,
                cwd=cwd,
                inherited_env=self.inherited_env,
                case_root=case_root,
                action=action,
            )
        except Exception as exc:  # evidence must survive every probe failure
            payload = {"error_code": _error_code(exc), "passed": False}
        else:
            self.environment_records.append(metadata)
        self.checks[f"batch_{action}"] = payload

    def _verify_and_copy(self, workspace: Path) -> tuple[Path, Path]:
        checkout = build_desktop.verify_package(self.bundle_root, self.package_root)
        copied_bundle, copied_package = copy_package_layout(
            self.bundle_root,
            self.package_root,
            workspace / "package-copy",
        )
        copied = build_desktop.verify_package(
            copied_bundle,
            copied_package,
            provenance_mode=build_desktop.PROVENANCE_MODE_OFFLINE,
        )
        source = checkout.get("source") if isinstance(checkout, dict) else None
        source_commit = source.get("source_commit") if isinstance(source, dict) else None
        identity_equal = checkout.get("package_identity") == copied.get("package_identity")
        archive_equal = checkout.get("archive") == copied.get("archive")
        inventory_equal = checkout.get("inventory") == copied.get("inventory")
        full_equal = canonical_json_bytes(checkout) == canonical_json_bytes(copied)
        gates = checkout.get("gates") if isinstance(checkout.get("gates"), dict) else {}
        gate_passed = all(
            isinstance(value, dict) and value.get("passed") is True
            for value in gates.values()
        ) and set(gates) == {"archive", "one_folder"}
        passed = (
            source_commit == self.workflow_sha
            and identity_equal
            and archive_equal
            and inventory_equal
            and full_equal
            and gate_passed
            and not _inside_boundary(copied_bundle, ROOT)
            and not _inside_boundary(copied_package, ROOT)
        )
        archive = checkout.get("archive") if isinstance(checkout.get("archive"), dict) else {}
        identity = (
            checkout.get("package_identity")
            if isinstance(checkout.get("package_identity"), dict)
            else {}
        )
        self.checks["package"] = {
            "archive_bytes": archive.get("size_bytes"),
            "archive_sha256": archive.get("sha256"),
            "archive_equal_after_copy": archive_equal,
            "checkout_mode": build_desktop.PROVENANCE_MODE_CHECKOUT,
            "copy_mode": build_desktop.PROVENANCE_MODE_OFFLINE,
            "copy_outside_checkout": not _inside_boundary(copied_bundle, ROOT),
            "full_evidence_equal_after_copy": full_equal,
            "identity_equal_after_copy": identity_equal,
            "inventory_equal_after_copy": inventory_equal,
            "package_identity": identity.get("value"),
            "passed": passed,
            "size_gates": gates,
            "source_commit_matches_workflow": source_commit == self.workflow_sha,
        }
        if not passed:
            raise AuditError("package_verification_failed")
        return copied_bundle, copied_package

    def _new_env(
        self,
        root: Path,
        *,
        extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        env, metadata = scrubbed_environment(self.inherited_env, root, extra=extra)
        self.environment_records.append(metadata)
        return env

    def _functional_checks(
        self,
        executable: Path,
        cwd: Path,
        root: Path,
    ) -> list[Path]:
        root.mkdir()
        logs = root / "logs"
        env = self._new_env(root / "state")

        self_test = run_command(
            executable,
            ["app", "--self-test", "--lang", "en"],
            cwd=cwd,
            env=env,
            log_root=logs,
            label="self-test",
            timeout_seconds=30.0,
        )
        self.checks["self_test"] = _command_payload(self_test)
        doctor = run_command(
            executable,
            ["doctor", "--json"],
            cwd=cwd,
            env=env,
            log_root=logs,
            label="doctor",
            timeout_seconds=30.0,
        )
        self.checks["doctor"] = _command_payload(doctor)

        run_paths: list[Path] = []
        summaries: list[dict[str, Any]] = []
        config_digests: list[str] = []
        manifest_error_counts: list[int] = []
        run_records: list[dict[str, Any]] = []
        for index in range(1, 4):
            output = root / "runs" / f"lab01-{index}"
            result = run_command(
                executable,
                [
                    "run",
                    "lab01",
                    "--config",
                    "configs/lab01_msd/default.yaml",
                    "--headless",
                    "--plot",
                    "--plots",
                    "essential",
                    "--output-dir",
                    os.fspath(output),
                    "--seed",
                    str(REPRO_SEED),
                ],
                cwd=cwd,
                env=env,
                log_root=logs,
                label=f"lab01-{index}",
                timeout_seconds=90.0,
            )
            artifact_error = False
            manifest_errors = ["command failed"] if not result.passed else []
            if not manifest_errors:
                try:
                    verify_output_artifacts(output, expect_plots=True)
                except Exception:
                    artifact_error = True
                manifest_errors = verify_manifest(output)
            manifest_error_counts.append(len(manifest_errors))
            try:
                summary = read_json_mapping(output / "summary.json")
                config_digest = _sha256_file(output / "config.yaml")
                manifest = read_json_mapping(output / "manifest.json")
                seed_matches = (
                    isinstance(manifest.get("config"), dict)
                    and manifest["config"].get("seed") == REPRO_SEED
                )
            except Exception:
                summary = {}
                config_digest = ""
                seed_matches = False
            summaries.append(summary)
            config_digests.append(config_digest)
            run_paths.append(output)
            run_passed = (
                result.passed
                and not artifact_error
                and not manifest_errors
                and _manifest_status(output) == "completed"
                and seed_matches
            )
            run_records.append(
                {
                    "artifact_contract": not artifact_error,
                    "command": _command_payload(result),
                    "config_sha256": config_digest,
                    "manifest_hash_errors": len(manifest_errors),
                    "passed": run_passed,
                    "run": index,
                    "seed_matches": seed_matches,
                }
            )
        self.checks["lab01"] = {
            "passed": len(run_records) == 3 and all(item["passed"] for item in run_records),
            "runs": run_records,
        }
        reproducibility = compare_reproducibility(
            summaries,
            config_digests,
            manifest_error_counts,
        )
        reproducibility["seed"] = REPRO_SEED
        self.checks["reproducibility"] = reproducibility

        replay_trace = root / "replay-trace.json"
        replay_env = self._new_env(
            root / "replay-state",
            extra={
                "MCLAB_APP_AUTO_QUIT_MS": "1500",
                "MCLAB_BACKEND_TRACE_PATH": os.fspath(replay_trace),
                "MCLAB_FAIL_ON_ERROR": "1",
                "MCLAB_SELF_TEST": "1",
                "MCLAB_SMOKE_ACTION": "pause,record_backend",
                "MCLAB_SMOKE_ACTION_MS": "150",
                "MCLAB_SMOKE_ACTION_INTERVAL_MS": "250",
            },
        )
        replay = run_command(
            executable,
            ["replay", os.fspath(run_paths[0]), "--lang", "en", "--safe-mode"],
            cwd=cwd,
            env=replay_env,
            log_root=logs,
            label="replay",
            timeout_seconds=30.0,
        )
        replay_frames = 0
        replay_trace_valid = False
        try:
            raw_trace = _require_regular_file(replay_trace, "replay_trace_missing").read_bytes()
            if len(raw_trace) > MAX_PROBE_BYTES:
                raise AuditError("replay_trace_too_large")
            trace = json.loads(raw_trace.decode("utf-8"), parse_constant=_reject_constant)
            if isinstance(trace, list) and trace and isinstance(trace[-1], dict):
                replay_frames = int(trace[-1].get("replay_frames", 0))
                replay_trace_valid = replay_frames > 0 and str(
                    trace[-1].get("session_state", "")
                ) in {"completed", "paused", "running"}
        except (AuditError, OSError, UnicodeError, ValueError, TypeError):
            pass
        self.checks["replay"] = {
            "command": _command_payload(replay),
            "passed": replay.passed and replay_trace_valid,
            "replay_frames": replay_frames,
            "trace_valid": replay_trace_valid,
        }

        next_preview = run_command(
            executable,
            ["next", "--preview", "--output-dir", os.fspath(root / "next-outputs")],
            cwd=cwd,
            env=env,
            log_root=logs,
            label="next-preview",
            timeout_seconds=30.0,
        )
        self.checks["next_preview"] = _command_payload(next_preview)

        cleanup_root = Path(env["MCLAB_DATA_DIR"]) / "outputs"
        cleanup_root.mkdir(parents=True, exist_ok=True)
        synthetic_run = cleanup_root / "synthetic-lab01"
        shutil.copytree(run_paths[0], synthetic_run, copy_function=shutil.copy2)
        expected_cleanup_plan = build_cleanup_plan(
            cleanup_root,
            keep=0,
            allowed_root=cleanup_root,
        ).to_dict()
        before = tree_fingerprint(cleanup_root)
        cleanup = run_command(
            executable,
            ["clean", "--output-dir", os.fspath(cleanup_root), "--keep", "0", "--json"],
            cwd=cwd,
            env=env,
            log_root=logs,
            label="cleanup-dry-run",
            timeout_seconds=30.0,
        )
        after = tree_fingerprint(cleanup_root)
        trash_absent = not (cleanup_root / ".mclab-trash").exists()
        self.checks["cleanup_dry_run"] = evaluate_cleanup_dry_run(
            cleanup,
            logs / "cleanup-dry-run.stdout",
            cleanup_root=cleanup_root,
            synthetic_run=synthetic_run,
            expected_plan=expected_cleanup_plan,
            before_fingerprint=before,
            after_fingerprint=after,
            trash_absent=trash_absent,
        )
        return run_paths

    def _startup_checks(self, executable: Path, cwd: Path, root: Path) -> None:
        root.mkdir()
        samples: list[dict[str, Any]] = []
        values: list[float] = []
        failures = 0
        for index in range(1, STARTUP_SAMPLES + 1):
            metric = root / f"startup-{index}.json"
            env = self._new_env(
                root / f"state-{index}",
                extra={
                    "MCLAB_APP_AUTO_QUIT_MS": "650",
                    "MCLAB_FAIL_ON_ERROR": "1",
                    "MCLAB_SELF_TEST": "1",
                    "MCLAB_SMOKE_ACTION": "startup_probe",
                    "MCLAB_SMOKE_ACTION_MS": "0",
                    "MCLAB_STARTUP_PATH": os.fspath(metric),
                },
            )
            env["MCLAB_STARTUP_BEGIN_NS"] = str(time.monotonic_ns())
            result = run_command(
                executable,
                ["app", "--safe-mode", "--lang", "en"],
                cwd=cwd,
                env=env,
                log_root=root / "logs",
                label=f"startup-{index}",
                timeout_seconds=20.0,
            )
            startup_ms: float | None = None
            try:
                payload = read_json_mapping(metric, max_bytes=4096)
                startup_ms = _number(payload, "startup_ms")
                if startup_ms < 0:
                    startup_ms = None
            except AuditError:
                pass
            sample_passed = (
                result.passed and startup_ms is not None
            )
            if sample_passed:
                assert startup_ms is not None
                values.append(startup_ms)
            else:
                failures += 1
            samples.append(
                {
                    "command": _command_payload(result),
                    "passed": sample_passed,
                    "sample": index,
                    "startup_ms": startup_ms,
                }
            )
        try:
            p95_ms, rank = nearest_rank_percentile(values, 0.95)
        except AuditError:
            p95_ms, rank = float("inf"), 19
        passed = (
            len(samples) == STARTUP_SAMPLES
            and len(values) == STARTUP_SAMPLES
            and failures == 0
            and p95_ms <= STARTUP_P95_LIMIT_MS
        )
        self.checks["startup"] = {
            "cold_definition": "new-process-and-fresh-settings; os-file-cache-not-flushed",
            "failure_count": failures,
            "method": "nearest-rank",
            "p95_ms": p95_ms if math.isfinite(p95_ms) else None,
            "passed": passed,
            "rank": rank,
            "sample_count": len(samples),
            "samples": samples,
        }

    def _course_check(self, executable: Path, cwd: Path, root: Path) -> None:
        root.mkdir()
        probe = root / "probe.json"
        ready = root / "ready.json"
        request = root / "unused-request.json"
        env, metadata = _probe_base_environment(
            self.inherited_env,
            root / "state",
            action="batch_probe_complete",
            probe_path=probe,
            ready_path=ready,
            request_path=request,
            auto_quit_ms=330_000,
        )
        self.environment_records.append(metadata)
        result, lifecycle = run_observed_command(
            executable,
            ["app", "--safe-mode", "--lang", "en"],
            cwd=cwd,
            env=env,
            log_root=root / "logs",
            label="course",
            timeout_seconds=COURSE_PROCESS_TIMEOUT_SECONDS,
        )
        try:
            ready_payload = read_json_mapping(ready, max_bytes=MAX_PROBE_BYTES)
            probe_payload = read_json_mapping(probe, max_bytes=MAX_PROBE_BYTES)
            validate_probe_payload(
                ready_payload,
                action="batch_probe_complete",
                phase="ready",
                status="running",
            )
            validate_probe_payload(
                probe_payload,
                action="batch_probe_complete",
                phase="terminal",
                status="completed",
            )
            allowed_outputs = Path(env["MCLAB_DATA_DIR"]) / "outputs"
            output = _safe_output_from_probe(probe_payload, allowed_outputs)
            payload = evaluate_course_output(
                output,
                probe_payload,
                result,
                allowed_root=allowed_outputs,
            )
            direct_child_pid = _integer(probe_payload, "child_pid")
            payload["checks"]["direct_child_observed"] = any(
                item.get("pid") == direct_child_pid
                for item in lifecycle["observed_processes"]
                if isinstance(item, dict)
            )
            payload["checks"]["process_containment"] = lifecycle["passed"]
            payload["passed"] = all(payload["checks"].values())
        except Exception as exc:
            payload = {
                "command": _command_payload(result),
                "error_code": _error_code(exc),
                "passed": False,
                "process_lifecycle": lifecycle,
            }
        else:
            payload["command"] = _command_payload(result)
            payload["process_lifecycle"] = lifecycle
        self.checks["full_course"] = payload

    def _evidence(self) -> dict[str, Any]:
        environment = self.environment_records[0] if self.environment_records else {
            "inherited_name_count": len(self.inherited_env),
            "passed_inherited_names": [],
            "policy": "allowlist-v1",
            "scrubbed_injection_names": [],
            "values_recorded": False,
        }
        all_scrubbed = sorted(
            {
                name
                for record in self.environment_records
                for name in record.get("scrubbed_injection_names", [])
                if isinstance(name, str)
            }
        )
        environment = {**environment, "scrubbed_injection_names": all_scrubbed}
        overall_pass = bool(self.checks) and all(
            isinstance(check, dict) and check.get("passed") is True
            for check in self.checks.values()
        )
        return {
            "artifact_class": ARTIFACT_CLASS,
            "checks": self.checks,
            "environment": environment,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_pass": overall_pass,
            "platform": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "release": platform.release(),
                "runner_os": self.runner_os,
                "system": platform.system(),
            },
            "required_check_contexts": list(REQUIRED_CHECK_CONTEXTS),
            "schema": SCHEMA,
            "subject": {
                "package_class": "unsigned-development",
                "provenance_scope": "internal-g2-development-evidence",
                "workflow_sha": self.workflow_sha,
            },
            "thresholds": {
                "archive_bytes": build_desktop.ARCHIVE_LIMIT_BYTES,
                "course_batches": 5,
                "course_comparison_plots_minimum": 5,
                "course_output_bytes": COURSE_OUTPUT_LIMIT_BYTES,
                "course_reports": 6,
                "course_scenario_runs": 54,
                "course_seconds": COURSE_TIMEOUT_SECONDS,
                "course_ui_gap_ms": COURSE_UI_GAP_LIMIT_MS,
                "one_folder_bytes": build_desktop.ONE_FOLDER_LIMIT_BYTES,
                "orphan_processes": 0,
                "reproducibility_absolute_tolerance": REPRO_ABS_TOL,
                "reproducibility_relative_tolerance": REPRO_REL_TOL,
                "startup_failure_count": 0,
                "startup_p95_ms": STARTUP_P95_LIMIT_MS,
                "startup_samples": STARTUP_SAMPLES,
            },
        }


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, AuditError):
        return exc.code
    return f"unexpected_{type(exc).__name__.casefold()}"


def _failure_evidence(
    *,
    runner_os: str,
    workflow_sha: str,
    error_code: str,
) -> dict[str, Any]:
    return {
        "artifact_class": ARTIFACT_CLASS,
        "checks": {"harness": {"error_code": error_code, "passed": False}},
        "environment": {
            "passed_inherited_names": [],
            "policy": "allowlist-v1",
            "scrubbed_injection_names": [],
            "values_recorded": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pass": False,
        "platform": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "release": platform.release(),
            "runner_os": runner_os,
            "system": platform.system(),
        },
        "required_check_contexts": list(REQUIRED_CHECK_CONTEXTS),
        "schema": SCHEMA,
        "subject": {
            "package_class": "unsigned-development",
            "provenance_scope": "internal-g2-development-evidence",
            "workflow_sha": workflow_sha,
        },
        "thresholds": {},
    }


def _resolve_checkout_input(value: Path) -> Path:
    return _absolute(value if value.is_absolute() else ROOT / value)


def _validate_output_path(output: Path, workflow_sha: str, runner_os: str) -> Path:
    if _SHA40_RE.fullmatch(workflow_sha) is None:
        raise AuditError("workflow_sha_invalid")
    if runner_os not in {"Linux", "Windows", "macOS"}:
        raise AuditError("runner_os_invalid")
    target = _absolute(output if output.is_absolute() else ROOT / output)
    expected = ROOT / "build" / "validation" / workflow_sha / f"g2-{runner_os}"
    if target != _absolute(expected / "package_e2e.json"):
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
    parser.add_argument("--runner-os", choices=("Linux", "Windows", "macOS"), required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--temp-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = _validate_output_path(args.output, args.workflow_sha, args.runner_os)
    except BaseException as exc:
        print(f"Refusing unsafe packaged E2E evidence target: {_error_code(exc)}", file=sys.stderr)
        return 2
    initial_evidence = _failure_evidence(
        runner_os=args.runner_os,
        workflow_sha=args.workflow_sha,
        error_code="audit_incomplete_or_interrupted",
    )
    try:
        _prepare_evidence_parent(output)
        _assert_no_absolute_strings(initial_evidence)
        write_canonical_json(output, initial_evidence)
    except BaseException as exc:
        print(f"Could not initialize packaged E2E evidence: {_error_code(exc)}", file=sys.stderr)
        return 2
    evidence: dict[str, Any]
    try:
        audit = PackageE2EAudit(
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
        _assert_no_absolute_strings(evidence)
        evidence_bytes = write_canonical_json(output, evidence)
    except BaseException as exc:
        print(f"Could not write packaged E2E evidence: {_error_code(exc)}", file=sys.stderr)
        return 2
    label = "PASS" if evidence.get("overall_pass") is True else "FAIL"
    print(f"{label} packaged E2E development gate; canonical evidence bytes={evidence_bytes}")
    return 0 if evidence.get("overall_pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
