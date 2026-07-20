"""Reproducible launch metadata for the desktop course-comparison batch."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import secrets
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mclab.config import default_outputs_root, is_frozen_bundle
from mclab.output_inventory import terminal_manifest_entry_rooted
from mclab.output_root import pinned_output_root
from mclab.output_safety import MAX_METADATA_BYTES, CleanupSafetyError, _stat_is_link_or_reparse

ALL_COMPARE_ID = "batch.all"
BATCH_PROGRESS_PREFIX = "MCLAB_BATCH_PROGRESS "
TERMINAL_BATCH_STATUSES = frozenset({"completed", "stopped", "error"})
BATCH_HANDOFF_FILE_NAME = ".mclab-batch-handoff"
BATCH_ACTIVE_DIR_NAME = ".mclab-batch-active"


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


def all_compare_command(output: str | Path) -> tuple[str, list[str]]:
    target = Path(output).resolve()
    token = (target / BATCH_HANDOFF_FILE_NAME).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("The course-comparison handoff token is missing.")
    args = [
        "batch",
        "all",
        "--output-dir",
        str(target),
        "--handoff-token",
        token,
    ]
    if not is_frozen_bundle():
        args = ["-u", "-m", "mclab", *args]
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
    target = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    manifest = target / "manifest.json"
    handoff = target / BATCH_HANDOFF_FILE_NAME
    active = target / BATCH_ACTIVE_DIR_NAME
    if not token or len(token) > 256:
        return False
    try:
        target_stat = os.lstat(target)
        if _stat_is_link_or_reparse(target_stat) or not stat.S_ISDIR(target_stat.st_mode):
            return False
        if {item.name for item in target.iterdir()} != {
            "manifest.json",
            BATCH_HANDOFF_FILE_NAME,
        }:
            return False
        manifest_stat = os.lstat(manifest)
        handoff_stat = os.lstat(handoff)
        if any(
            _stat_is_link_or_reparse(item) or not stat.S_ISREG(item.st_mode)
            for item in (manifest_stat, handoff_stat)
        ):
            return False
        if manifest_stat.st_size > MAX_METADATA_BYTES or handoff_stat.st_size > 256:
            return False
        manifest_bytes = manifest.read_bytes()
        handoff_bytes = handoff.read_bytes()
        payload = json.loads(manifest_bytes.decode("utf-8"))
        supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not (
            isinstance(payload, dict)
            and type(payload.get("schema_version")) is int
            and payload.get("schema_version") == 1
            and payload.get("scenario_id") == ALL_COMPARE_ID
            and payload.get("status") == "running"
            and hmac.compare_digest(
                str(payload.get("handoff_token_sha256", "")),
                supplied_hash,
            )
            and hmac.compare_digest(handoff_bytes.decode("utf-8").strip(), token)
        ):
            return False
        active.mkdir(mode=0o700, exist_ok=False)
        try:
            if manifest.read_bytes() != manifest_bytes or handoff.read_bytes() != handoff_bytes:
                raise RuntimeError("Course-comparison handoff changed during claim.")
            handoff.unlink()
        except Exception:
            active.rmdir()
            raise
    except (FileExistsError, OSError, RuntimeError, UnicodeError, ValueError):
        return False
    return True


def release_all_compare_handoff(output: str | Path) -> None:
    active = Path(output) / BATCH_ACTIVE_DIR_NAME
    try:
        active_stat = os.lstat(active)
    except FileNotFoundError:
        raise RuntimeError("The course-comparison writer claim is missing.") from None
    if _stat_is_link_or_reparse(active_stat) or not stat.S_ISDIR(active_stat.st_mode):
        raise RuntimeError("The course-comparison writer claim is unsafe.")
    try:
        active.rmdir()
    except OSError as exc:
        raise RuntimeError("The course-comparison writer claim is not empty.") from exc


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
