"""Reproducible launch metadata for the desktop course-comparison batch."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from mclab.application.batch_integrity import (
    read_authenticated_running_state_rooted as _read_authenticated_running_state_rooted,
    read_running_manifest_rooted as _read_running_manifest_rooted,
    retrying_batch_operation_lock as _retrying_batch_operation_lock,
    unlink_regular_file_rooted as _unlink_regular_file_rooted,
    validate_manifest_token_hash as _validate_manifest_token_hash,
    verify_terminal_batch_output_rooted as _verify_terminal_batch_output_rooted,
)
from mclab.application.batch_progress import (
    ALL_COMPARE_BATCH_NAMES,
    ALL_COMPARE_ID,
    BATCH_ACTIVE_DIR_NAME,
    BATCH_HANDOFF_FILE_NAME,
    BATCH_PROGRESS_FILE_NAME,
    BATCH_PROGRESS_SCHEMA,
    MAX_BATCH_PROGRESS_BYTES,
    BatchProgressEvent,
    decode_handoff_bytes as _decode_handoff_bytes,
    decode_progress_payload as _decode_progress_payload,
    decode_token as _decode_token,
    encode_progress_payload as _encode_progress_payload,
    validated_progress_event as _validated_progress_event,
)
from mclab.application.batch_settlement import prune_interrupted_batch_directories
from mclab.config import default_outputs_root, is_frozen_bundle
from mclab.output_inventory import terminal_manifest_entry_rooted
from mclab.output_root import pinned_output_root
from mclab.output_safety import (
    MAX_METADATA_BYTES,
    CleanupBusyError,
    CleanupOperationError,
    CleanupSafetyError,
)

BATCH_PROGRESS_PREFIX = "MCLAB_BATCH_PROGRESS "
TERMINAL_BATCH_STATUSES = frozenset({"completed", "stopped", "error"})


class BatchProgressBusy(RuntimeError):
    """A normal peer mutation briefly owns the authenticated progress lock."""


__all__ = [
    "ALL_COMPARE_BATCH_NAMES",
    "ALL_COMPARE_ID",
    "BATCH_ACTIVE_DIR_NAME",
    "BATCH_HANDOFF_FILE_NAME",
    "BATCH_PROGRESS_FILE_NAME",
    "BATCH_PROGRESS_PREFIX",
    "BATCH_PROGRESS_SCHEMA",
    "BatchProgressBusy",
    "BatchProgressEvent",
    "all_compare_command",
    "batch_manifest_status",
    "claim_all_compare_handoff",
    "clear_all_compare_progress",
    "create_all_compare_output",
    "parse_batch_progress",
    "read_all_compare_handoff",
    "read_batch_progress",
    "release_all_compare_handoff",
    "settle_all_compare_output",
    "update_batch_manifest",
    "write_batch_progress",
]


def create_all_compare_output() -> Path:
    root = default_outputs_root()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = root / f"{stamp}_all_batches"
    for suffix in range(1, 1001):
        output = base if suffix == 1 else root / f"{base.name}_{suffix}"
        try:
            output.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError(f"Could not create a unique batch output directory for {base}")
    token = secrets.token_hex(32)
    handoff = output / BATCH_HANDOFF_FILE_NAME
    handoff.write_text(token, encoding="utf-8")
    try:
        handoff.chmod(0o600)
    except OSError:
        pass
    update_batch_manifest(
        output,
        status="running",
        handoff_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )
    return output


def read_all_compare_handoff(output: str | Path) -> str:
    """Read a pristine one-shot handoff through a pinned physical root."""

    target = _absolute_output_path(output)
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                manifest_bytes, _payload = _read_running_manifest_rooted(root_pin)
                names = set(root_pin.list_names((), max_entries=3))
                if names != {"manifest.json", BATCH_HANDOFF_FILE_NAME}:
                    raise CleanupSafetyError(
                        "Course-comparison handoff is not in its pristine preclaim state"
                    )
                token_bytes = root_pin.read_regular_file(
                    (BATCH_HANDOFF_FILE_NAME,),
                    description="course-comparison handoff token",
                    max_bytes=64,
                    allow_empty=False,
                )
                token = _decode_handoff_bytes(token_bytes)
                _validate_manifest_token_hash(_payload, token)
                if root_pin.read_regular_file(
                    ("manifest.json",),
                    description="course-comparison manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                ) != manifest_bytes:
                    raise CleanupSafetyError(
                        "Course-comparison manifest changed while the handoff was read"
                    )
                root_pin.assert_read_boundary()
                return token
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not read the course-comparison handoff: {exc}") from exc


def all_compare_command(
    output: str | Path,
    worker_arguments: Sequence[str] = (),
) -> tuple[str, list[str]]:
    target = _absolute_output_path(output)
    token = read_all_compare_handoff(target)
    forwarded = [
        "batch",
        "all",
        "--output-dir",
        str(target),
        "--handoff-token",
        token,
    ]
    if isinstance(worker_arguments, (str, bytes)):
        raise RuntimeError("Batch worker arguments must be a sequence of individual values.")
    worker = [str(item) for item in worker_arguments]
    if any(not item for item in worker):
        raise RuntimeError("The batch worker arguments contain an empty value.")
    if is_frozen_bundle():
        args = ["__batch-worker", *worker, *forwarded]
    else:
        args = ["-u", "-m", "mclab.application.batch_worker", *worker, *forwarded]
    return sys.executable, args


def update_batch_manifest(
    output: str | Path,
    *,
    status: str,
    error: str = "",
    handoff_token_hash: str = "",
) -> Path:
    path = Path(output) / "manifest.json"
    payload = _read_json(path)
    if batch_manifest_status(output) in TERMINAL_BATCH_STATUSES:
        return path
    started_at = str(payload.get("started_at") or datetime.now().astimezone().isoformat())
    if status in TERMINAL_BATCH_STATUSES:
        from mclab.application.artifacts import write_manifest

        return write_manifest(
            output,
            scenario_id=ALL_COMPARE_ID,
            status=status,
            config={"batch_name": "all", "plot": True},
            started_at=started_at,
            run_kind="comparison_batch",
            error=error,
        )
    payload.update(
        {
            "schema_version": 1,
            "scenario_id": ALL_COMPARE_ID,
            "run_kind": "comparison_batch",
            "status": status,
            "config": {"resolved": {"batch_name": "all", "plot": True}},
        }
    )
    if handoff_token_hash:
        payload["handoff_token_sha256"] = handoff_token_hash
    payload.setdefault("started_at", started_at)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def batch_manifest_status(output: str | Path) -> str:
    target = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    try:
        with pinned_output_root(target.parent, allowed_root=target.parent) as (
            _root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                return ""
            entry, _reason = terminal_manifest_entry_rooted(root_pin, target.name)
    except (CleanupSafetyError, OSError):
        return ""
    if entry is None or entry.scenario_id != ALL_COMPARE_ID:
        return ""
    return entry.status


def claim_all_compare_handoff(output: str | Path, token: str) -> bool:
    target = _absolute_output_path(output)
    try:
        _decode_token(token)
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                return False
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                manifest_bytes, payload = _read_running_manifest_rooted(root_pin)
                _validate_manifest_token_hash(payload, token)
                if set(root_pin.list_names((), max_entries=3)) != {
                    "manifest.json",
                    BATCH_HANDOFF_FILE_NAME,
                }:
                    return False
                handoff_bytes = root_pin.read_regular_file(
                    (BATCH_HANDOFF_FILE_NAME,),
                    description="course-comparison handoff token",
                    max_bytes=64,
                    allow_empty=False,
                )
                if not hmac.compare_digest(_decode_handoff_bytes(handoff_bytes), token):
                    return False
                root_pin.mkdir((BATCH_ACTIVE_DIR_NAME,), mode=0o700)
                try:
                    if root_pin.read_regular_file(
                        ("manifest.json",),
                        description="course-comparison manifest",
                        max_bytes=MAX_METADATA_BYTES,
                        allow_empty=False,
                    ) != manifest_bytes:
                        raise CleanupSafetyError(
                            "Course-comparison manifest changed during claim"
                        )
                    _unlink_regular_file_rooted(
                        root_pin,
                        (BATCH_HANDOFF_FILE_NAME,),
                        expected=handoff_bytes,
                        description="course-comparison handoff token",
                    )
                    root_pin.assert_transaction_boundaries()
                except Exception:
                    root_pin.rmdir((BATCH_ACTIVE_DIR_NAME,))
                    raise
    except (
        CleanupOperationError,
        CleanupSafetyError,
        FileExistsError,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        TypeError,
    ):
        return False
    return True


def release_all_compare_handoff(output: str | Path) -> None:
    target = _absolute_output_path(output)
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                root_pin.validate_directory(
                    (BATCH_ACTIVE_DIR_NAME,),
                    description="course-comparison writer claim",
                )
                if root_pin.list_names((BATCH_ACTIVE_DIR_NAME,), max_entries=1):
                    raise CleanupSafetyError(
                        "Course-comparison writer claim is not empty"
                    )
                root_pin.rmdir((BATCH_ACTIVE_DIR_NAME,))
                root_pin.assert_transaction_boundaries()
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not release the course-comparison writer claim: {exc}") from exc


def write_batch_progress(
    output: str | Path,
    token: str,
    *,
    sequence: int,
    current: int,
    total: int,
    name: str,
) -> BatchProgressEvent:
    """Append one authenticated, ordered progress event to the active claim."""

    key = _decode_token_runtime(token)
    event = _validated_progress_event(
        sequence=sequence,
        current=current,
        total=total,
        name=name,
        expected_index=sequence,
    )
    target = _absolute_output_path(output)
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                _manifest_bytes, manifest = _read_running_manifest_rooted(root_pin)
                _validate_manifest_token_hash(manifest, token)
                if root_pin.lexists((BATCH_HANDOFF_FILE_NAME,)):
                    raise CleanupSafetyError(
                        "Course-comparison progress cannot precede the writer claim"
                    )
                root_pin.validate_directory(
                    (BATCH_ACTIVE_DIR_NAME,),
                    description="course-comparison writer claim",
                )
                with root_pin.scoped_directory_pin(
                    (BATCH_ACTIVE_DIR_NAME,),
                    description="course-comparison writer claim",
                ):
                    names = set(
                        root_pin.list_names((BATCH_ACTIVE_DIR_NAME,), max_entries=2)
                    )
                    if not names.issubset({BATCH_PROGRESS_FILE_NAME}):
                        raise CleanupSafetyError(
                            "Course-comparison writer claim contains an unknown marker"
                        )
                    events: tuple[BatchProgressEvent, ...] = ()
                    progress_path = (BATCH_ACTIVE_DIR_NAME, BATCH_PROGRESS_FILE_NAME)
                    if BATCH_PROGRESS_FILE_NAME in names:
                        progress_bytes = root_pin.read_regular_file(
                            progress_path,
                            description="course-comparison progress sidecar",
                            max_bytes=MAX_BATCH_PROGRESS_BYTES,
                            allow_empty=False,
                        )
                        events = _decode_progress_payload(progress_bytes, key)
                    if sequence != len(events) + 1:
                        raise CleanupSafetyError(
                            "Course-comparison progress sequence is replayed or out of order"
                        )
                    encoded = _encode_progress_payload((*events, event), key)
                    root_pin.replace_regular_file(progress_path, encoded, mode=0o600)
                    root_pin.assert_transaction_boundaries()
                    return event
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not publish authenticated batch progress: {exc}") from exc


def read_batch_progress(
    output: str | Path,
    token: str,
) -> tuple[BatchProgressEvent, ...]:
    """Return the authenticated history for a valid handoff lifecycle state."""

    key = _decode_token_runtime(token)
    target = _absolute_output_path(output)
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with root_pin.operation_lock():
                manifest_bytes = root_pin.read_regular_file(
                    ("manifest.json",),
                    description="course-comparison manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                )
                payload = json.loads(manifest_bytes.decode("utf-8"))
                status = payload.get("status") if isinstance(payload, dict) else None
                if status in TERMINAL_BATCH_STATUSES:
                    if payload.get("scenario_id") != ALL_COMPARE_ID:
                        raise CleanupSafetyError(
                            "Terminal batch manifest identity is invalid"
                        )
                    errors = _verify_terminal_batch_output_rooted(
                        root_pin,
                        expected_status=str(status),
                    )
                    if errors:
                        raise CleanupSafetyError(
                            "Terminal course-comparison output is invalid: "
                            + "; ".join(errors)
                        )
                    events: tuple[BatchProgressEvent, ...] = ()
                else:
                    _state, events, _manifest_bytes, _payload = (
                        _read_authenticated_running_state_rooted(root_pin, token, key)
                    )
                root_pin.assert_read_boundary()
                return events
    except CleanupBusyError as exc:
        raise BatchProgressBusy("Authenticated batch progress is being updated") from exc
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not read authenticated batch progress: {exc}") from exc


def clear_all_compare_progress(output: str | Path, token: str) -> None:
    """Remove a valid progress sidecar while leaving the active claim in place."""

    key = _decode_token_runtime(token)
    target = _absolute_output_path(output)
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                state, _events, _manifest_bytes, _payload = (
                    _read_authenticated_running_state_rooted(root_pin, token, key)
                )
                if state != "postclaim":
                    raise CleanupSafetyError(
                        "Course-comparison progress cleanup requires an active writer claim"
                    )
                progress_path = (BATCH_ACTIVE_DIR_NAME, BATCH_PROGRESS_FILE_NAME)
                if root_pin.lexists(progress_path):
                    progress_bytes = root_pin.read_regular_file(
                        progress_path,
                        description="course-comparison progress sidecar",
                        max_bytes=MAX_BATCH_PROGRESS_BYTES,
                        allow_empty=False,
                    )
                    _decode_progress_payload(progress_bytes, key)
                    _unlink_regular_file_rooted(
                        root_pin,
                        progress_path,
                        expected=progress_bytes,
                        description="course-comparison progress sidecar",
                    )
                    root_pin.assert_transaction_boundaries()
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not clear authenticated batch progress: {exc}") from exc


def settle_all_compare_output(
    output: str | Path,
    token: str,
    requested_status: str,
    error: str = "",
) -> str:
    """Recover a quiescent desktop batch without ever synthesizing success.

    The caller owns the process-tree quiescence proof.  This function owns the
    authenticated filesystem transition once no child can write again.
    """

    if requested_status not in TERMINAL_BATCH_STATUSES:
        raise RuntimeError(f"Unsupported course-comparison settlement: {requested_status!r}")
    target = _absolute_output_path(output)
    terminal = _strict_terminal_status(target)
    if terminal:
        return terminal
    if requested_status == "completed":
        raise RuntimeError(
            "A completed course comparison must be published by the child and cannot be recovered."
        )
    key = _decode_token_runtime(token)
    started_at = ""
    plot = True
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Course-comparison output is missing")
            root_pin.validate_directory((), description="course-comparison output")
            with _retrying_batch_operation_lock(root_pin):
                state, _events, manifest_bytes, payload = (
                    _read_authenticated_running_state_rooted(root_pin, token, key)
                )
                started_at = str(payload["started_at"])
                resolved = payload["config"]["resolved"]
                plot = bool(resolved["plot"])
                if state == "preclaim":
                    handoff_bytes = root_pin.read_regular_file(
                        (BATCH_HANDOFF_FILE_NAME,),
                        description="course-comparison handoff token",
                        max_bytes=64,
                        allow_empty=False,
                    )
                    _unlink_regular_file_rooted(
                        root_pin,
                        (BATCH_HANDOFF_FILE_NAME,),
                        expected=handoff_bytes,
                        description="course-comparison handoff token",
                    )
                elif state == "postclaim":
                    progress_path = (BATCH_ACTIVE_DIR_NAME, BATCH_PROGRESS_FILE_NAME)
                    if root_pin.lexists(progress_path):
                        progress_bytes = root_pin.read_regular_file(
                            progress_path,
                            description="course-comparison progress sidecar",
                            max_bytes=MAX_BATCH_PROGRESS_BYTES,
                            allow_empty=False,
                        )
                        _decode_progress_payload(progress_bytes, key)
                        _unlink_regular_file_rooted(
                            root_pin,
                            progress_path,
                            expected=progress_bytes,
                            description="course-comparison progress sidecar",
                        )
                    if root_pin.list_names((BATCH_ACTIVE_DIR_NAME,), max_entries=1):
                        raise CleanupSafetyError(
                            "Course-comparison writer claim did not become empty"
                        )
                    root_pin.rmdir((BATCH_ACTIVE_DIR_NAME,))
                prune_interrupted_batch_directories(root_pin)
                current_manifest = root_pin.read_regular_file(
                    ("manifest.json",),
                    description="course-comparison manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                )
                if current_manifest != manifest_bytes:
                    raise CleanupSafetyError(
                        "Course-comparison manifest changed during settlement"
                    )
                root_pin.assert_transaction_boundaries()
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not settle the course-comparison output: {exc}") from exc

    from mclab.application.artifacts import write_manifest

    terminal_error = error or "The course comparison ended before authenticated completion."
    write_manifest(
        target,
        scenario_id=ALL_COMPARE_ID,
        status=requested_status,
        config={"batch_name": "all", "plot": plot},
        started_at=started_at,
        run_kind="comparison_batch",
        error=terminal_error if requested_status == "error" else "",
    )
    errors = _terminal_batch_errors(target, requested_status)
    if errors:
        raise RuntimeError("Terminal course-comparison verification failed: " + "; ".join(errors))
    return requested_status


def _decode_token_runtime(token: object) -> bytes:
    try:
        return _decode_token(token)
    except CleanupSafetyError as exc:
        raise RuntimeError(f"Invalid course-comparison handoff token: {exc}") from exc


def _strict_terminal_status(target: Path) -> str:
    try:
        with pinned_output_root(target, allowed_root=target) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None or not root_pin.lexists(("manifest.json",)):
                return ""
            with _retrying_batch_operation_lock(root_pin):
                manifest_bytes = root_pin.read_regular_file(
                    ("manifest.json",),
                    description="course-comparison manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                )
                payload = json.loads(manifest_bytes.decode("utf-8"))
                if not isinstance(payload, dict):
                    root_pin.assert_read_boundary()
                    return ""
                status = payload.get("status")
                if status not in TERMINAL_BATCH_STATUSES:
                    root_pin.assert_read_boundary()
                    return ""
                if payload.get("scenario_id") != ALL_COMPARE_ID:
                    raise CleanupSafetyError("Terminal batch manifest identity is invalid")
                errors = _verify_terminal_batch_output_rooted(
                    root_pin,
                    expected_status=str(status),
                )
                if errors:
                    raise CleanupSafetyError(
                        "Terminal course-comparison output is invalid: " + "; ".join(errors)
                    )
                root_pin.assert_read_boundary()
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise RuntimeError(f"Could not inspect terminal batch state: {exc}") from exc
    return str(status)


def _terminal_batch_errors(target: Path, status: str) -> list[str]:
    from mclab.application.artifacts import verify_terminal_batch_output

    return verify_terminal_batch_output(target, expected_status=status)


def _absolute_output_path(output: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(output))))


def parse_batch_progress(line: str) -> tuple[int, int, str] | None:
    if not line.startswith(BATCH_PROGRESS_PREFIX):
        return None
    parts = line.removeprefix(BATCH_PROGRESS_PREFIX).split(maxsplit=1)
    fraction = parts[0]
    try:
        current, total = (int(item) for item in fraction.split("/", 1))
    except (TypeError, ValueError):
        return None
    if current < 1 or total < 1 or current > total:
        return None
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return None
    return current, total, name


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}
