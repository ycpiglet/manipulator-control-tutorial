"""Persistence boundaries for course progress and saved run artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mclab.application.artifacts import replay_index_reason
from mclab.config import default_outputs_root
from mclab.output_filters import is_internal_output_dir


@dataclass(frozen=True)
class ArtifactRecord:
    path: Path
    scenario_id: str
    status: str
    size_bytes: int
    replay_available: bool
    rerun_available: bool
    tuned_available: bool
    legacy: bool
    replay_reason: str
    summary: dict[str, Any]


class ArtifactRepository:
    def __init__(self, outputs_root: str | Path | None = None) -> None:
        self.outputs_root = (
            Path(outputs_root) if outputs_root is not None else default_outputs_root()
        )

    def list_runs(self, *, validate_replays: bool = False) -> tuple[ArtifactRecord, ...]:
        if not self.outputs_root.exists():
            return ()
        records: list[ArtifactRecord] = []
        for path in self.outputs_root.iterdir():
            if not path.is_dir() or is_internal_output_dir(path):
                continue
            manifest = _read_json(path / "manifest.json")
            summary = _read_json(path / "summary.json")
            if not manifest and not summary:
                continue
            replay_path = path / "replay.npz"
            replay_reason = (
                replay_index_reason(path)
                if validate_replays or not replay_path.exists()
                else ""
            )
            records.append(
                ArtifactRecord(
                    path=path,
                    scenario_id=str(
                        manifest.get("scenario_id") or summary.get("config_name") or "legacy"
                    ),
                    status=str(manifest.get("status") or "completed"),
                    size_bytes=_directory_size(path),
                    replay_available=not replay_reason,
                    rerun_available=(path / "config.yaml").exists()
                    or _has_resolved_config(manifest),
                    tuned_available=(path / "learner_tuned_config.yaml").exists(),
                    legacy=not bool(manifest),
                    replay_reason=replay_reason,
                    summary=summary,
                )
            )
        records.sort(key=lambda item: _modified_time(item.path), reverse=True)
        return tuple(records)

    def latest(self, scenario_id: str | None = None) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.list_runs()
                if scenario_id is None or record.scenario_id == scenario_id
            ),
            None,
        )

    def delete(self, record: ArtifactRecord, *, confirm_path: str) -> None:
        resolved = record.path.resolve()
        root = self.outputs_root.resolve()
        if resolved.parent != root or confirm_path != record.path.name:
            raise ValueError(
                "Run deletion requires the exact folder name and a direct child of outputs/."
            )
        shutil.rmtree(resolved)

    def delete_path(self, path: str | Path, *, confirm_path: str) -> None:
        target = Path(path).resolve()
        record = next(
            (item for item in self.list_runs() if item.path.resolve() == target),
            None,
        )
        if record is None:
            raise ValueError("The saved run is no longer available.")
        self.delete(record, confirm_path=confirm_path)


class ProgressRepository:
    """Store lightweight app preferences without changing legacy evidence files."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = (
            Path(path) if path is not None else default_outputs_root() / ".mclab_progress.json"
        )

    def load(self) -> dict[str, Any]:
        return _read_json(self.path)

    def update(self, **values: Any) -> dict[str, Any]:
        state = self.load()
        state.update(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state


def _directory_size(path: Path) -> int:
    total = 0
    try:
        items = path.rglob("*")
        for item in items:
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _modified_time(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _has_resolved_config(manifest: dict[str, Any]) -> bool:
    config = manifest.get("config")
    return isinstance(config, dict) and isinstance(config.get("resolved"), dict)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}
