"""Persistence boundaries for course progress and saved run artifacts."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from mclab.application.artifacts import replay_index_reason_from_stream
from mclab.completion import CompletionEvidence, CompletionRecordKind
from mclab.config import default_outputs_root
from mclab.output_filters import is_internal_output_dir
from mclab.output_cleanup import (
    CleanupReceipt,
    quarantine_run,
)
from mclab.output_inventory import (
    CompletionRunSnapshot,
    TERMINAL_STATUSES,
    read_completion_run_snapshot_rooted,
)
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    MAX_OUTPUT_ROOT_ENTRIES,
    MAX_RUN_TREE_ENTRIES,
    CleanupSafetyError,
)


MAX_REPLAY_BYTES = 512 * 1024 * 1024
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
    cleanup_token: str
    manifest: dict[str, Any] = field(default_factory=dict)
    marker_name: str = ""
    completion_evidence: CompletionEvidence = field(
        default_factory=lambda: CompletionEvidence(CompletionRecordKind.MISSING)
    )
    interaction_events: object = None
    plot_paths: tuple[Path, ...] = ()
    worksheet_available: bool = False
    report_available: bool = False
    artifact_validation_errors: tuple[str, ...] = ()
    finished_at: str = ""
    sort_timestamp: float = 0.0
    worksheet_text: str = ""


class ArtifactRepository:
    def __init__(self, outputs_root: str | Path | None = None) -> None:
        self.outputs_root = (
            Path(outputs_root) if outputs_root is not None else default_outputs_root()
        )

    def list_runs(self, *, validate_replays: bool = False) -> tuple[ArtifactRecord, ...]:
        try:
            with pinned_output_root(
                self.outputs_root,
                allowed_root=self.outputs_root,
            ) as (root, root_exists, root_pin):
                if not root_exists or root_pin is None:
                    return ()
                records: list[tuple[float, str, ArtifactRecord]] = []
                for name in root_pin.list_names(max_entries=MAX_OUTPUT_ROOT_ENTRIES):
                    path = root / name
                    if is_internal_output_dir(path):
                        continue
                    try:
                        with root_pin.scoped_directory_pin(
                            (name,),
                            description="saved run",
                        ):
                            snapshot = read_completion_run_snapshot_rooted(
                                root_pin,
                                name,
                                allow_legacy=True,
                            )
                            size_bytes = root_pin.tree_size(
                                (name,),
                                max_entries=MAX_RUN_TREE_ENTRIES,
                            )
                            manifest = snapshot.manifest
                            summary = snapshot.summary
                            if not manifest and not summary:
                                continue
                            replay_reason = _safe_replay_reason_rooted(
                                root_pin,
                                name,
                                validate=validate_replays,
                            )
                            rerun_available = _safe_regular_file_exists_rooted(
                                root_pin,
                                (name, "config.yaml"),
                            ) or _has_resolved_config(manifest)
                            tuned_available = _safe_regular_file_exists_rooted(
                                root_pin,
                                (name, "learner_tuned_config.yaml"),
                            )
                            modified = float(root_pin.lstat((name,)).st_mtime)
                            sort_timestamp = _completion_sort_timestamp(snapshot, modified)
                            record = ArtifactRecord(
                                path=path,
                                scenario_id=snapshot.scenario_id,
                                status=snapshot.status,
                                size_bytes=size_bytes,
                                replay_available=not replay_reason,
                                rerun_available=rerun_available,
                                tuned_available=tuned_available,
                                legacy=not bool(manifest),
                                replay_reason=replay_reason,
                                summary=summary,
                                cleanup_token=snapshot.token,
                                manifest=manifest,
                                marker_name=snapshot.marker_name,
                                completion_evidence=snapshot.completion_evidence,
                                interaction_events=snapshot.interaction_events,
                                plot_paths=tuple(
                                    path.joinpath(*PurePosixPath(relative).parts)
                                    for relative in snapshot.plot_paths
                                ),
                                worksheet_available=snapshot.worksheet_available,
                                report_available=snapshot.report_available,
                                artifact_validation_errors=(
                                    snapshot.artifact_validation_errors
                                ),
                                finished_at=snapshot.finished_at,
                                sort_timestamp=sort_timestamp,
                                worksheet_text=snapshot.worksheet_text,
                            )
                    except (CleanupSafetyError, OSError):
                        continue
                    records.append((sort_timestamp, name, record))
                root_pin.assert_read_boundary()
                records.sort(key=lambda item: (-item[0], item[1]))
                return tuple(record for _timestamp, _name, record in records)
        except (CleanupSafetyError, OSError):
            return ()

    def latest(self, scenario_id: str | None = None) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.list_runs()
                if scenario_id is None or record.scenario_id == scenario_id
            ),
            None,
        )

    def delete(
        self,
        record: ArtifactRecord,
        *,
        confirm_path: str,
        cleanup_token: str,
    ) -> CleanupReceipt:
        return quarantine_run(
            self.outputs_root,
            record.path,
            confirmation=confirm_path,
            expected_token=cleanup_token,
            allowed_root=self.outputs_root,
        )

    def delete_path(
        self,
        path: str | Path,
        *,
        confirm_path: str,
        cleanup_token: str,
    ) -> CleanupReceipt:
        target = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
        root = Path(os.path.abspath(os.path.expanduser(os.fspath(self.outputs_root))))
        if not _same_existing_path(target.parent, root):
            raise ValueError("Run cleanup is limited to a direct child of outputs/.")
        record = next(
            (
                item
                for item in self.list_runs()
                if _same_direct_child_path(
                    Path(os.path.abspath(os.fspath(item.path))),
                    target,
                )
            ),
            None,
        )
        if record is None:
            raise ValueError("The saved run is no longer available.")
        return self.delete(
            record,
            confirm_path=confirm_path,
            cleanup_token=cleanup_token,
        )


def _same_existing_path(left: Path, right: Path) -> bool:
    """Compare an existing path across Windows short/long-name aliases."""

    try:
        return left.samefile(right)
    except OSError:
        return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _same_direct_child_path(left: Path, right: Path) -> bool:
    """Match one listed child name without accepting a junction alias."""

    return left.name == right.name and _same_existing_path(left.parent, right.parent)


def _completion_sort_timestamp(snapshot: CompletionRunSnapshot, fallback: float) -> float:
    if snapshot.status not in TERMINAL_STATUSES or not snapshot.finished_at:
        return fallback
    try:
        return datetime.fromisoformat(snapshot.finished_at).timestamp()
    except (OSError, OverflowError, ValueError):
        return fallback


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


def _safe_regular_file_exists_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
) -> bool:
    try:
        stat_result = root_pin.lstat(relative)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CleanupSafetyError(
            f"Could not inspect saved-run artifact {relative[-1]}: {exc}"
        ) from exc
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    if (
        stat.S_ISLNK(stat_result.st_mode)
        or attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        or not stat.S_ISREG(stat_result.st_mode)
    ):
        raise CleanupSafetyError(
            f"Saved-run artifact {relative[-1]} must be a regular, non-link file"
        )
    return True


def _safe_replay_reason_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
    *,
    validate: bool,
) -> str:
    replay_relative = (name, "replay.npz")
    if _safe_regular_file_exists_rooted(root_pin, replay_relative):
        if not validate:
            return ""
        with root_pin.open_regular_file(
            replay_relative,
            description="saved-run replay",
            max_bytes=MAX_REPLAY_BYTES,
            allow_empty=True,
        ) as stream:
            return replay_index_reason_from_stream(stream, source_label="replay.npz")
    if _safe_regular_file_exists_rooted(
        root_pin,
        (name, "states.npz"),
    ) or _safe_regular_file_exists_rooted(
        root_pin,
        (name, "log.csv"),
    ):
        return "This legacy run has metrics but no complete qpos/qvel/ctrl recording."
    return "This folder does not contain a supported MCLab recording."


def _has_resolved_config(manifest: dict[str, Any]) -> bool:
    config = manifest.get("config")
    return isinstance(config, dict) and isinstance(config.get("resolved"), dict)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}
