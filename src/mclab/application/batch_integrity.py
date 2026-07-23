"""Pinned filesystem integrity checks for authenticated desktop batch state."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mclab.application.batch_progress import (
    ALL_COMPARE_ID,
    BATCH_ACTIVE_DIR_NAME,
    BATCH_HANDOFF_FILE_NAME,
    BATCH_PROGRESS_FILE_NAME,
    MAX_BATCH_PROGRESS_BYTES,
    BatchProgressEvent,
    decode_handoff_bytes,
    decode_progress_payload,
)
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    MAX_METADATA_BYTES,
    CleanupBusyError,
    CleanupOperationError,
    CleanupSafetyError,
    _same_file_identity,
    _stat_is_link_or_reparse,
)

TERMINAL_BATCH_STATUSES = frozenset({"completed", "stopped", "error"})
_BATCH_LOCK_RETRY_SECONDS = 2.0
_BATCH_LOCK_RETRY_INTERVAL_SECONDS = 0.01
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RUNNING_MANIFEST_BASE_KEYS = {
    "schema_version",
    "scenario_id",
    "run_kind",
    "status",
    "config",
    "handoff_token_sha256",
    "started_at",
}
_RUNNING_MANIFEST_FULL_KEYS = {
    *_RUNNING_MANIFEST_BASE_KEYS,
    "finished_at",
    "runtime",
    "model",
    "artifacts",
    "replay",
}


@contextmanager
def retrying_batch_operation_lock(root_pin: PinnedOutputRoot) -> Iterator[None]:
    """Acquire the batch protocol lock without failing on a brief peer read."""

    deadline = time.monotonic() + _BATCH_LOCK_RETRY_SECONDS
    while True:
        manager = root_pin.operation_lock()
        try:
            manager.__enter__()
        except CleanupBusyError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_BATCH_LOCK_RETRY_INTERVAL_SECONDS)
            continue
        break
    try:
        yield
    finally:
        manager.__exit__(None, None, None)


def read_authenticated_running_state_rooted(
    root_pin: PinnedOutputRoot,
    token: str,
    key: bytes,
) -> tuple[str, tuple[BatchProgressEvent, ...], bytes, dict[str, Any]]:
    manifest_bytes, payload = read_running_manifest_rooted(root_pin)
    validate_manifest_token_hash(payload, token)
    root_names = set(root_pin.list_names((), max_entries=256))
    unknown_markers = {
        name
        for name in root_names
        if name.startswith(".mclab-batch-")
        and name not in {BATCH_HANDOFF_FILE_NAME, BATCH_ACTIVE_DIR_NAME}
    }
    if unknown_markers or BATCH_PROGRESS_FILE_NAME in root_names:
        raise CleanupSafetyError(
            "Course-comparison output contains an unknown or misplaced transient marker"
        )
    has_handoff = BATCH_HANDOFF_FILE_NAME in root_names
    has_active = BATCH_ACTIVE_DIR_NAME in root_names
    if has_handoff and has_active:
        raise CleanupSafetyError("Course-comparison output contains conflicting handoff markers")
    if has_handoff:
        if root_names != {"manifest.json", BATCH_HANDOFF_FILE_NAME}:
            raise CleanupSafetyError(
                "Course-comparison preclaim output contains unexpected entries"
            )
        encoded = root_pin.read_regular_file(
            (BATCH_HANDOFF_FILE_NAME,),
            description="course-comparison handoff token",
            max_bytes=64,
            allow_empty=False,
        )
        if not hmac.compare_digest(decode_handoff_bytes(encoded), token):
            raise CleanupSafetyError("Course-comparison handoff token does not match")
        return "preclaim", (), manifest_bytes, payload
    if has_active:
        root_pin.validate_directory(
            (BATCH_ACTIVE_DIR_NAME,), description="course-comparison writer claim"
        )
        with root_pin.scoped_directory_pin(
            (BATCH_ACTIVE_DIR_NAME,), description="course-comparison writer claim"
        ):
            names = set(root_pin.list_names((BATCH_ACTIVE_DIR_NAME,), max_entries=2))
            if not names.issubset({BATCH_PROGRESS_FILE_NAME}):
                raise CleanupSafetyError(
                    "Course-comparison writer claim contains an unknown marker"
                )
            events: tuple[BatchProgressEvent, ...] = ()
            if BATCH_PROGRESS_FILE_NAME in names:
                encoded = root_pin.read_regular_file(
                    (BATCH_ACTIVE_DIR_NAME, BATCH_PROGRESS_FILE_NAME),
                    description="course-comparison progress sidecar",
                    max_bytes=MAX_BATCH_PROGRESS_BYTES,
                    allow_empty=False,
                )
                events = decode_progress_payload(encoded, key)
            return "postclaim", events, manifest_bytes, payload
    return "cleanup-gap", (), manifest_bytes, payload


def read_running_manifest_rooted(
    root_pin: PinnedOutputRoot,
) -> tuple[bytes, dict[str, Any]]:
    encoded = root_pin.read_regular_file(
        ("manifest.json",),
        description="course-comparison manifest",
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=False,
    )
    payload = json.loads(encoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise CleanupSafetyError("Course-comparison manifest must contain an object")
    keys = set(payload)
    if keys != _RUNNING_MANIFEST_BASE_KEYS and keys != _RUNNING_MANIFEST_FULL_KEYS:
        raise CleanupSafetyError(
            "Course-comparison running manifest contains missing or extra fields"
        )
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise CleanupSafetyError("Course-comparison manifest schema is invalid")
    if payload.get("scenario_id") != ALL_COMPARE_ID:
        raise CleanupSafetyError("Course-comparison manifest identity is invalid")
    if payload.get("run_kind") != "comparison_batch":
        raise CleanupSafetyError("Course-comparison manifest run kind is invalid")
    if payload.get("status") != "running":
        raise CleanupSafetyError("Course-comparison manifest is not running")
    if not isinstance(payload.get("started_at"), str) or not payload["started_at"]:
        raise CleanupSafetyError("Course-comparison manifest start time is invalid")
    digest = payload.get("handoff_token_sha256")
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise CleanupSafetyError("Course-comparison handoff digest is invalid")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise CleanupSafetyError("Course-comparison manifest config is invalid")
    expected_config = (
        {"resolved"}
        if keys == _RUNNING_MANIFEST_BASE_KEYS
        else {"path", "seed", "resolved"}
    )
    if set(config) != expected_config:
        raise CleanupSafetyError("Course-comparison manifest config shape is invalid")
    resolved = config.get("resolved")
    if not isinstance(resolved, dict) or set(resolved) != {"batch_name", "plot"}:
        raise CleanupSafetyError("Course-comparison resolved config is invalid")
    if resolved.get("batch_name") != "all" or type(resolved.get("plot")) is not bool:
        raise CleanupSafetyError("Course-comparison resolved identity is invalid")
    if keys == _RUNNING_MANIFEST_FULL_KEYS:
        from mclab.completion import CompletionRecordKind
        from mclab.output_inventory import validate_completion_manifest_v1

        validation = validate_completion_manifest_v1(payload)
        if validation.record_kind != CompletionRecordKind.MANIFEST_V1:
            raise CleanupSafetyError(
                f"Course-comparison running manifest is invalid: {validation.reason}"
            )
    return encoded, payload


def validate_manifest_token_hash(payload: dict[str, Any], token: str) -> None:
    supplied_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    if not hmac.compare_digest(payload["handoff_token_sha256"], supplied_hash):
        raise CleanupSafetyError("Course-comparison handoff digest does not match")


def unlink_regular_file_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    expected: bytes,
    description: str,
) -> None:
    current_bytes = root_pin.read_regular_file(
        relative,
        description=description,
        max_bytes=max(len(expected), 1),
        allow_empty=not expected,
    )
    if not hmac.compare_digest(current_bytes, expected):
        raise CleanupSafetyError(f"{description.capitalize()} changed before removal")
    initial = root_pin.lstat(relative)
    if _stat_is_link_or_reparse(initial) or not stat.S_ISREG(initial.st_mode):
        raise CleanupSafetyError(f"{description.capitalize()} has an unsafe type")
    root_pin.begin_mutation()
    if os.name == "nt":
        with root_pin._pinned_windows_directory(relative[:-1]):
            current = os.lstat(root_pin.display_path(relative))
            if not _same_file_identity(initial, current):
                raise CleanupSafetyError(f"{description.capitalize()} changed before removal")
            os.unlink(root_pin.display_path(relative))
    else:
        with root_pin._open_directory_fd(relative[:-1]) as parent_fd:
            current = os.stat(relative[-1], dir_fd=parent_fd, follow_symlinks=False)
            if (
                _stat_is_link_or_reparse(current)
                or not stat.S_ISREG(current.st_mode)
                or not _same_file_identity(initial, current)
            ):
                raise CleanupSafetyError(f"{description.capitalize()} changed before removal")
            os.unlink(relative[-1], dir_fd=parent_fd)
            os.fsync(parent_fd)
    if root_pin.lexists(relative):
        raise CleanupSafetyError(f"{description.capitalize()} is still present")


def verify_terminal_batch_output(
    output_path: str | Path, *, expected_status: str
) -> list[str]:
    if expected_status not in TERMINAL_BATCH_STATUSES:
        return [f"Unsupported terminal batch status: {expected_status!r}"]
    output = Path(output_path)
    try:
        with pinned_output_root(output, allowed_root=output) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Terminal batch output directory is missing")
            root_pin.validate_directory((), description="terminal batch output")
            with root_pin.operation_lock():
                errors = verify_terminal_batch_output_rooted(
                    root_pin,
                    expected_status=expected_status,
                )
                root_pin.assert_read_boundary()
                return errors
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        return [f"Could not read terminal batch manifest: {exc}"]


def verify_terminal_batch_output_rooted(
    root_pin: PinnedOutputRoot,
    *,
    expected_status: str,
) -> list[str]:
    """Verify a terminal batch while the caller holds the operation lock."""

    encoded = root_pin.read_regular_file(
        ("manifest.json",),
        description="terminal batch manifest",
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=False,
    )
    payload = json.loads(encoded.decode("utf-8"))
    errors = _validate_terminal_batch_payload(payload, expected_status)
    from mclab.application.artifacts import _inventory_artifacts_rooted

    try:
        actual = _inventory_artifacts_rooted(root_pin, strict=True)
    except CleanupSafetyError as exc:
        errors.append(str(exc))
        actual = {}
    expected = payload.get("artifacts") if isinstance(payload, dict) else None
    if isinstance(expected, dict):
        for relative in sorted(set(expected) - set(actual)):
            errors.append(f"Missing artifact: {relative}")
        for relative in sorted(set(actual) - set(expected)):
            errors.append(f"Unlisted artifact: {relative}")
        for relative in sorted(set(expected) & set(actual)):
            if expected[relative] != actual[relative]:
                errors.append(f"Artifact hash mismatch: {relative}")
    final = root_pin.read_regular_file(
        ("manifest.json",),
        description="terminal batch manifest",
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=False,
    )
    if final != encoded:
        errors.append("Manifest changed during verification.")
    return errors


def _validate_terminal_batch_payload(payload: object, expected_status: str) -> list[str]:
    if not isinstance(payload, dict):
        return ["Invalid terminal batch manifest payload."]
    from mclab.completion import CompletionRecordKind
    from mclab.output_inventory import validate_completion_manifest_v1

    errors: list[str] = []
    validation = validate_completion_manifest_v1(payload)
    if validation.record_kind != CompletionRecordKind.MANIFEST_V1:
        errors.append(f"Invalid terminal batch manifest: {validation.reason}")
    if payload.get("status") != expected_status:
        errors.append(
            f"Terminal batch status mismatch: expected {expected_status!r}, "
            f"found {payload.get('status')!r}"
        )
    scenario_id = payload.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.startswith("batch."):
        errors.append("Terminal batch manifest has an invalid scenario identity.")
    if payload.get("run_kind") != "comparison_batch":
        errors.append("Terminal batch manifest has an invalid run kind.")
    required = {
        "schema_version",
        "scenario_id",
        "status",
        "started_at",
        "finished_at",
        "config",
        "runtime",
        "model",
        "artifacts",
        "replay",
        "run_kind",
    }
    allowed = set(required)
    if expected_status == "error":
        allowed.add("error")
        if not isinstance(payload.get("error"), str) or not payload["error"]:
            errors.append("Terminal error batch manifest is missing its error detail.")
    if set(payload) != allowed:
        errors.append("Terminal batch manifest contains missing or extra fields.")
    if "handoff_token_sha256" in payload:
        errors.append("Terminal batch manifest retained live handoff metadata.")
    return errors
