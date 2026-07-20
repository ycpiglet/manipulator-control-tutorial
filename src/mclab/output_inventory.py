"""Strict saved-run inventory and identity checks under a pinned output root."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path, PurePosixPath
from typing import Any

from mclab.application.artifacts import MANIFEST_SCHEMA_VERSION
from mclab.output_filters import is_internal_output_dir
from mclab.output_root import PinnedOutputRoot
from mclab.output_safety import (
    MAX_METADATA_BYTES,
    CleanupSafetyError,
    _hash_payload,
    _parse_aware_datetime,
    _same_open_file_state,
    _stat_is_link_or_reparse,
)


TRASH_DIR_NAME = ".mclab-trash"
TERMINAL_STATUSES = frozenset({"completed", "stopped", "error"})


@dataclass(frozen=True)
class CleanupEntry:
    path: Path
    name: str
    scenario_id: str
    status: str
    finished_at: str
    token: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": str(self.path),
            "scenario_id": self.scenario_id,
            "status": self.status,
            "finished_at": self.finished_at,
            "token": self.token,
        }


@dataclass(frozen=True)
class SavedRunSnapshot:
    """Bounded metadata snapshot used by Results and cleanup guards."""

    token: str
    scenario_id: str
    status: str
    marker_name: str
    manifest: dict[str, Any]
    summary: dict[str, Any]


@dataclass(frozen=True)
class RunIdentity:
    token: str
    scenario_id: str
    status: str
    marker_name: str
    payload: dict[str, Any]
    path_stat: os.stat_result


def strict_cleanup_entry_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
) -> tuple[CleanupEntry | None, str]:
    path = root_pin.display_path((name,))
    if is_internal_output_dir(path) or name == TRASH_DIR_NAME:
        return None, "internal or reserved output"
    entry, reason = terminal_manifest_entry_rooted(root_pin, name)
    if entry is None:
        return None, reason
    if root_pin.lexists((name, ".mclab-preserve")):
        return None, "run has a .mclab-preserve hold marker"
    return entry, ""


def terminal_manifest_entry_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
) -> tuple[CleanupEntry | None, str]:
    """Validate terminal manifest structure independently of cleanup policy holds."""

    path = root_pin.display_path((name,))
    try:
        root_pin.validate_directory((name,), description="run candidate")
    except CleanupSafetyError as exc:
        return None, str(exc)
    try:
        payload, manifest_digest = read_json_mapping_rooted(
            root_pin,
            (name, "manifest.json"),
            description="run manifest",
        )
    except CleanupSafetyError as exc:
        return None, str(exc)
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        return None, "unsupported manifest schema"
    scenario_id = payload.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        return None, "manifest scenario_id is blank or invalid"
    status_value = payload.get("status")
    if not isinstance(status_value, str) or status_value not in TERMINAL_STATUSES:
        return None, "manifest status is not a terminal cleanup status"
    try:
        finished = _parse_aware_datetime(payload.get("finished_at"))
    except CleanupSafetyError as exc:
        return None, str(exc)
    config = payload.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("resolved"), dict):
        return None, "manifest config is invalid"
    try:
        started = _parse_aware_datetime(payload.get("started_at"))
    except CleanupSafetyError as exc:
        return None, str(exc).replace("finished_at", "started_at")
    if finished < started:
        return None, "manifest finished_at precedes started_at"
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return None, "manifest artifacts are invalid"
    if any(not _safe_manifest_relative_path(value) for value in artifacts):
        return None, "manifest contains an unsafe artifact path"
    try:
        stat_result = root_pin.lstat((name,))
    except OSError as exc:
        return None, f"could not stat run candidate: {exc}"
    token = _identity_token(
        name=name,
        stat_result=stat_result,
        marker_name="manifest.json",
        marker_digest=manifest_digest,
    )
    return (
        CleanupEntry(
            path=path,
            name=name,
            scenario_id=scenario_id.strip(),
            status=status_value,
            finished_at=finished.astimezone(timezone.utc).isoformat(),
            token=token,
        ),
        "",
    )


def run_identity_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    allow_legacy: bool,
) -> RunIdentity:
    root_pin.validate_directory(relative, description="saved run")
    initial_stat = root_pin.lstat(relative)
    manifest = (*relative, "manifest.json")
    marker_candidates = (
        [manifest]
        if root_pin.lexists(manifest) or not allow_legacy
        else [(*relative, "summary.json")]
    )
    errors: list[str] = []
    for marker in marker_candidates:
        try:
            payload, digest = read_json_mapping_rooted(
                root_pin,
                marker,
                description="saved-run metadata",
            )
        except CleanupSafetyError as exc:
            errors.append(str(exc))
            continue
        marker_name = marker[-1]
        if marker_name == "manifest.json":
            scenario = payload.get("scenario_id")
            status = payload.get("status")
            if not isinstance(scenario, str) or not scenario.strip():
                errors.append("manifest scenario_id is blank or invalid")
                continue
            if not isinstance(status, str) or not status.strip():
                errors.append("manifest status is blank or invalid")
                continue
        else:
            scenario = payload.get("config_name") or payload.get("lab_name")
            status = "legacy"
            if not isinstance(scenario, str) or not scenario.strip():
                errors.append("legacy summary does not identify an MCLab run")
                continue
        stat_result = root_pin.lstat(relative)
        if _stat_is_link_or_reparse(stat_result) or not _same_open_file_state(
            initial_stat,
            stat_result,
        ):
            raise CleanupSafetyError("Saved run changed while metadata was read")
        return RunIdentity(
            token=_identity_token(
                name=relative[-1],
                stat_result=stat_result,
                marker_name=marker_name,
                marker_digest=digest,
            ),
            scenario_id=scenario.strip(),
            status=status.strip(),
            marker_name=marker_name,
            payload=payload,
            path_stat=stat_result,
        )
    reason = errors[-1] if errors else "saved-run metadata is missing"
    raise CleanupSafetyError(f"The selected folder is not a validated saved run: {reason}.")


def read_json_mapping_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    description: str,
    allow_empty: bool = False,
) -> tuple[dict[str, Any], str]:
    data = root_pin.read_regular_file(
        relative,
        description=description,
        max_bytes=MAX_METADATA_BYTES,
        allow_empty=False,
    )
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CleanupSafetyError(f"{description} is malformed or unreadable: {exc}") from exc
    if not isinstance(payload, dict) or (not payload and not allow_empty):
        qualifier = "a JSON object" if allow_empty else "a non-empty JSON object"
        raise CleanupSafetyError(f"{description} must contain {qualifier}")
    return payload, hashlib.sha256(data).hexdigest()


def _safe_manifest_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or value in {".", ".."} or "\\" in value:
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _identity_token(
    *,
    name: str,
    stat_result: os.stat_result,
    marker_name: str,
    marker_digest: str,
) -> str:
    return _hash_payload(
        {
            "name": name,
            "device": int(stat_result.st_dev),
            "inode": int(stat_result.st_ino),
            "mtime_ns": int(stat_result.st_mtime_ns),
            "marker": marker_name,
            "marker_sha256": marker_digest,
        }
    )
