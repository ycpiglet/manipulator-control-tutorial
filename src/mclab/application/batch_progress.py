"""Canonical authenticated progress records for the desktop all-batch worker."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from mclab.output_safety import CleanupSafetyError

ALL_COMPARE_ID = "batch.all"
BATCH_HANDOFF_FILE_NAME = ".mclab-batch-handoff"
BATCH_ACTIVE_DIR_NAME = ".mclab-batch-active"
BATCH_PROGRESS_FILE_NAME = "progress.json"
BATCH_PROGRESS_SCHEMA = "mclab.batch-progress.v1"
MAX_BATCH_PROGRESS_BYTES = 4 * 1024
ALL_COMPARE_BATCH_NAMES = (
    "lab01_msd_compare",
    "lab02_pid_compare",
    "lab03_2dof_compare",
    "lab04_cartesian_compare",
    "lab04_wall_compare",
)
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class BatchProgressEvent:
    sequence: int
    current: int
    total: int
    name: str


def validated_progress_event(
    *, sequence: object, current: object, total: object, name: object, expected_index: int
) -> BatchProgressEvent:
    if (
        type(sequence) is not int
        or type(current) is not int
        or type(total) is not int
        or not isinstance(name, str)
    ):
        raise CleanupSafetyError("Batch progress fields have invalid types")
    if not 1 <= expected_index <= len(ALL_COMPARE_BATCH_NAMES):
        raise CleanupSafetyError("Batch progress contains too many events")
    if (
        sequence != expected_index
        or current != expected_index
        or total != len(ALL_COMPARE_BATCH_NAMES)
        or name != ALL_COMPARE_BATCH_NAMES[expected_index - 1]
    ):
        raise CleanupSafetyError(
            "Batch progress is not an exact prefix of the ordered course comparison"
        )
    return BatchProgressEvent(sequence=sequence, current=current, total=total, name=name)


def encode_progress_payload(events: tuple[BatchProgressEvent, ...], key: bytes) -> bytes:
    unsigned = {
        "schema": BATCH_PROGRESS_SCHEMA,
        "events": [
            {
                "sequence": event.sequence,
                "current": event.current,
                "total": event.total,
                "name": event.name,
            }
            for event in events
        ],
    }
    signature = hmac.new(key, canonical_json(unsigned), hashlib.sha256).hexdigest()
    encoded = canonical_json({**unsigned, "hmac_sha256": signature})
    if len(encoded) > MAX_BATCH_PROGRESS_BYTES:
        raise CleanupSafetyError("Batch progress sidecar exceeds its safe size")
    return encoded


def decode_progress_payload(
    encoded: bytes, key: bytes
) -> tuple[BatchProgressEvent, ...]:
    if not encoded or len(encoded) > MAX_BATCH_PROGRESS_BYTES:
        raise CleanupSafetyError("Batch progress sidecar has an invalid size")
    payload = json.loads(encoded.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "events",
        "hmac_sha256",
    }:
        raise CleanupSafetyError("Batch progress sidecar has missing or extra fields")
    if (
        not isinstance(payload.get("schema"), str)
        or payload["schema"] != BATCH_PROGRESS_SCHEMA
        or type(payload.get("events")) is not list
    ):
        raise CleanupSafetyError("Batch progress sidecar schema is invalid")
    signature = payload.get("hmac_sha256")
    if not isinstance(signature, str) or _SHA256_PATTERN.fullmatch(signature) is None:
        raise CleanupSafetyError("Batch progress sidecar signature is invalid")
    unsigned = {"schema": payload["schema"], "events": payload["events"]}
    expected = hmac.new(key, canonical_json(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise CleanupSafetyError("Batch progress sidecar authentication failed")
    if encoded != canonical_json({**unsigned, "hmac_sha256": signature}):
        raise CleanupSafetyError("Batch progress sidecar is not canonical")
    if len(payload["events"]) > len(ALL_COMPARE_BATCH_NAMES):
        raise CleanupSafetyError("Batch progress sidecar contains too many events")
    events: list[BatchProgressEvent] = []
    for index, raw_event in enumerate(payload["events"], start=1):
        if not isinstance(raw_event, dict) or set(raw_event) != {
            "sequence",
            "current",
            "total",
            "name",
        }:
            raise CleanupSafetyError("Batch progress event has missing or extra fields")
        events.append(
            validated_progress_event(
                sequence=raw_event["sequence"],
                current=raw_event["current"],
                total=raw_event["total"],
                name=raw_event["name"],
                expected_index=index,
            )
        )
    return tuple(events)


def canonical_json(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CleanupSafetyError("Batch progress sidecar is not canonical JSON") from exc


def decode_token(token: object) -> bytes:
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise CleanupSafetyError(
            "Course-comparison handoff token must be 32 canonical bytes"
        )
    decoded = bytes.fromhex(token)
    if len(decoded) != 32:
        raise CleanupSafetyError("Course-comparison handoff token has an invalid length")
    return decoded


def decode_handoff_bytes(encoded: bytes) -> str:
    try:
        token = encoded.decode("ascii")
    except UnicodeError as exc:
        raise CleanupSafetyError("Course-comparison handoff token is not ASCII") from exc
    decode_token(token)
    if token.encode("ascii") != encoded:
        raise CleanupSafetyError("Course-comparison handoff token is not canonical")
    return token
