"""Reproducible launch metadata for the desktop course-comparison batch."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mclab.config import default_outputs_root, is_frozen_bundle

ALL_COMPARE_ID = "batch.all"
BATCH_PROGRESS_PREFIX = "MCLAB_BATCH_PROGRESS "


def create_all_compare_output() -> Path:
    root = default_outputs_root()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = root / f"{stamp}_all_batches"
    output = base
    suffix = 2
    while output.exists():
        output = root / f"{base.name}_{suffix}"
        suffix += 1
    output.mkdir()
    update_batch_manifest(output, status="running")
    return output


def all_compare_command(output: str | Path) -> tuple[str, list[str]]:
    args = ["batch", "all", "--output-dir", str(Path(output).resolve())]
    if not is_frozen_bundle():
        args = ["-u", "-m", "mclab", *args]
    return sys.executable, args


def update_batch_manifest(
    output: str | Path,
    *,
    status: str,
    error: str = "",
) -> Path:
    path = Path(output) / "manifest.json"
    payload = _read_json(path)
    started_at = str(payload.get("started_at") or datetime.now().astimezone().isoformat())
    payload.update(
        {
            "schema_version": 1,
            "scenario_id": ALL_COMPARE_ID,
            "run_kind": "comparison_batch",
            "status": status,
            "config": {"resolved": {"batch_name": "all", "plot": True}},
        }
    )
    payload.setdefault("started_at", started_at)
    if status != "running":
        payload["finished_at"] = datetime.now().astimezone().isoformat()
    if error:
        payload["error"] = error[-2000:]
    else:
        payload.pop("error", None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
