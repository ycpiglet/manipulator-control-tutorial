"""Receipt schema and durable metadata helpers for output quarantine."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mclab.output_safety import (
    MAX_METADATA_BYTES,
    CleanupOperationError,
    CleanupSafetyError,
    _parse_aware_datetime,
)
from mclab.output_root import PinnedOutputRoot


RECEIPT_SCHEMA_VERSION = 1
RECEIPT_FILE_NAME = "receipt.json"
MAX_RECEIPT_BYTES = MAX_METADATA_BYTES
RECEIPT_ID_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}_[0-9a-f]{8}")
RECOVERABLE_RECEIPT_STATUSES = frozenset(
    {"staging", "quarantined", "rollback_failed", "restore_rollback_failed"}
)


@dataclass(frozen=True)
class CleanupReceipt:
    receipt_id: str
    path: Path
    root: Path
    root_token: str
    plan_id: str
    status: str
    names: tuple[str, ...]
    created_at: str
    operation_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_id": self.receipt_id,
            "path": str(self.path),
            "root": str(self.root),
            "root_token": self.root_token,
            "plan_id": self.plan_id,
            "status": self.status,
            "recoverable": (
                self.status in RECOVERABLE_RECEIPT_STATUSES and not self.operation_active
            ),
            "operation_active": self.operation_active,
            "names": list(self.names),
            "created_at": self.created_at,
        }


def _write_receipt_payload_rooted(
    root_pin: PinnedOutputRoot,
    receipt_relative: tuple[str, ...],
    payload: dict[str, Any],
) -> None:
    root_pin.replace_regular_file(
        (*receipt_relative, RECEIPT_FILE_NAME),
        _encode_receipt_payload(payload),
    )


def _write_receipt_payload_rooted_best_effort(
    root_pin: PinnedOutputRoot,
    receipt_relative: tuple[str, ...],
    payload: dict[str, Any],
) -> str:
    try:
        _write_receipt_payload_rooted(root_pin, receipt_relative, payload)
    except (CleanupOperationError, CleanupSafetyError) as exc:
        return str(exc)
    return ""


def _read_receipt_payload_rooted(
    root_pin: PinnedOutputRoot,
    receipt_relative: tuple[str, ...],
) -> dict[str, Any]:
    data = root_pin.read_regular_file(
        (*receipt_relative, RECEIPT_FILE_NAME),
        description="cleanup receipt metadata",
        max_bytes=MAX_RECEIPT_BYTES,
        allow_empty=False,
    )
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CleanupSafetyError(f"cleanup receipt metadata is malformed: {exc}") from exc
    if not isinstance(payload, dict) or not payload:
        raise CleanupSafetyError(
            "cleanup receipt metadata must contain a non-empty JSON object"
        )
    return payload


def _encode_receipt_payload(payload: dict[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CleanupOperationError(f"Could not encode cleanup receipt: {exc}") from exc
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise CleanupOperationError(
            f"Cleanup receipt exceeds the {MAX_RECEIPT_BYTES}-byte safety limit"
        )
    return encoded


def _receipt_from_payload(
    receipt_path: Path,
    payload: dict[str, Any],
    *,
    expected_root: Path,
    expected_root_token: str | None = None,
    operation_active: bool = False,
) -> CleanupReceipt:
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != RECEIPT_SCHEMA_VERSION:
        raise CleanupSafetyError("Unsupported cleanup receipt schema.")
    receipt_id = payload.get("receipt_id")
    if not isinstance(receipt_id, str) or receipt_id != receipt_path.name:
        raise CleanupSafetyError("Cleanup receipt ID does not match its directory.")
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise CleanupSafetyError("Invalid cleanup receipt ID.")
    if payload.get("root") != str(expected_root):
        raise CleanupSafetyError("Cleanup receipt belongs to a different outputs root.")
    root_token = payload.get("root_token")
    if not isinstance(root_token, str) or re.fullmatch(r"[0-9a-f]{64}", root_token) is None:
        raise CleanupSafetyError("Cleanup receipt has an invalid root identity token.")
    if expected_root_token is not None and root_token != expected_root_token:
        raise CleanupSafetyError("Cleanup receipt belongs to a replaced outputs root.")
    plan_id = payload.get("plan_id")
    status_value = payload.get("status")
    created_at = payload.get("created_at")
    if not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_id):
        raise CleanupSafetyError("Cleanup receipt has an invalid plan ID.")
    if not isinstance(status_value, str) or not status_value:
        raise CleanupSafetyError("Cleanup receipt has an invalid status.")
    if not isinstance(created_at, str):
        raise CleanupSafetyError("Cleanup receipt has an invalid timestamp.")
    _parse_aware_datetime(created_at)
    mappings = _receipt_mappings(payload)
    return CleanupReceipt(
        receipt_id=receipt_id,
        path=receipt_path,
        root=expected_root,
        root_token=root_token,
        plan_id=plan_id,
        status=status_value,
        names=tuple(name for name, _token in mappings),
        created_at=created_at,
        operation_active=operation_active,
    )


def _receipt_mappings(payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise CleanupSafetyError("Cleanup receipt has no entry mappings.")
    mappings: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise CleanupSafetyError("Cleanup receipt contains an invalid entry mapping.")
        name = raw.get("name")
        token = raw.get("token")
        if (
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            or name in {".", ".."}
            or name in seen
        ):
            raise CleanupSafetyError("Cleanup receipt contains an unsafe entry name.")
        if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise CleanupSafetyError("Cleanup receipt contains an invalid entry token.")
        seen.add(name)
        mappings.append((name, token))
    return tuple(mappings)


def _new_receipt_id(plan_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{plan_id[:12]}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
