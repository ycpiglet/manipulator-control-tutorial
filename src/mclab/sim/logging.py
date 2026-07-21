"""Simulation logging utilities."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mclab.application.artifacts import ReplayRecorder, write_manifest
from mclab.application.catalog import stable_scenario_id
from mclab.config import default_outputs_root, resolve_output_path
from mclab.sim.reporting import write_outputs_index, write_run_report

LOGGER = logging.getLogger(__name__)


def create_output_path(lab_name: str, output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        path = resolve_output_path(output_dir)
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            if not path.is_dir() or any(path.iterdir()):
                raise RuntimeError(
                    f"Refusing to reuse a non-empty output directory: {path}"
                ) from None
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Course progress and readiness read default_outputs_root(); runs must
        # be written under the same root or completions never advance the path
        # (MCLAB_DATA_DIR overrides and frozen bundles diverged here before).
        path = _create_unique_output_directory(default_outputs_root() / f"{stamp}_{lab_name}")
    try:
        (path / "plots").mkdir(exist_ok=False)
    except FileExistsError:
        raise RuntimeError(f"Output directory is already in use: {path}") from None
    return path


def _create_unique_output_directory(base_path: Path) -> Path:
    for index in range(1000):
        path = base_path if index == 0 else base_path.with_name(f"{base_path.name}_{index:03d}")
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not create a unique output directory for {base_path}")


class RunLogger:
    """Collect rows and save the standard lab output files."""

    def __init__(
        self,
        lab_name: str,
        config: Mapping[str, Any],
        *,
        config_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        seed: int | None = None,
    ) -> None:
        self.lab_name = lab_name
        self.config = dict(config)
        self.config_path = Path(config_path) if config_path else None
        self.seed = seed
        self.output_path = create_output_path(lab_name, output_dir)
        self.rows: list[dict[str, Any]] = []
        self.log_sample_hz = float(self.config.get("log_sample_hz", 100.0))
        self._next_log_time = 0.0
        self._last_seen_time: float | None = None
        self.replay = ReplayRecorder(float(self.config.get("replay_sample_hz", 60.0)))
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.run_status = "completed"
        self._finalized = False
        self._running_marker_established = False
        self._running_report_repair_required = False

    def record(self, **row: Any) -> None:
        flattened = _flatten_mapping(row)
        try:
            timestamp = float(flattened.get("time", self._next_log_time))
        except (TypeError, ValueError):
            timestamp = self._next_log_time
        rewound = self._last_seen_time is not None and timestamp + 1e-12 < self._last_seen_time
        self._last_seen_time = timestamp
        if rewound:
            self._next_log_time = timestamp
        if (
            self.rows
            and not rewound
            and self.log_sample_hz > 0
            and timestamp + 1e-12 < self._next_log_time
        ):
            return
        self.rows.append(flattened)
        if self.log_sample_hz > 0:
            self._next_log_time = timestamp + 1.0 / self.log_sample_hz

    def record_physics_state(
        self,
        data: Any,
        *,
        semantic: Mapping[str, float] | None = None,
    ) -> bool:
        """Record a compact MuJoCo state without changing physics stepping."""

        return self.replay.record(
            time=float(data.time),
            qpos=data.qpos,
            qvel=data.qvel,
            ctrl=data.ctrl,
            semantic=dict(semantic or {}),
        )

    def save(self, summary: Mapping[str, Any] | None = None, notes: str = "") -> Path:
        return self.save_with_artifacts(summary=summary, notes=notes)

    def save_with_artifacts(
        self,
        summary: Mapping[str, Any] | None = None,
        notes: str = "",
        *,
        interaction_events: list[Mapping[str, Any]] | None = None,
        learner_snapshot: Mapping[str, Any] | None = None,
        learner_tuned_config: Mapping[str, Any] | None = None,
        run_status: str = "completed",
        finalize: bool = True,
    ) -> Path:
        self._require_unfinalized()
        self.run_status = run_status
        if not self._running_marker_established:
            # Establish the empty/initial running boundary once.  On a retry,
            # the prior marker must continue to make changed producer bytes or
            # stale prospective verdicts fail closed until finalization repairs
            # the documents and refreshes the manifest in that order.
            self._write_manifest(status="running")
            self._running_marker_established = True
        self._save_config_snapshot()
        self._save_csv()
        self._save_states()
        self._save_replay()
        self._save_summary(summary or {})
        self._save_notes(notes)
        self._save_interaction_events(interaction_events)
        self._save_learner_snapshot(learner_snapshot)
        self._save_learner_tuned_config(learner_tuned_config)
        if finalize:
            self.finalize_artifacts()
        else:
            if self._running_report_repair_required:
                write_run_report(
                    self.output_path,
                    update_index=False,
                    completion_status="running",
                )
            self._write_manifest(status="running")
            self._running_report_repair_required = False
        return self.output_path

    def finalize_artifacts(self) -> Path:
        """Write reports while cleanup is blocked, then publish terminal state last."""

        self._require_unfinalized()
        try:
            # A prior terminal-publication attempt may have left prospective
            # Complete documents whose bytes no longer match the last running
            # manifest.  Repair those documents before refreshing that
            # manifest so a retry can never digest-publish a stale verdict.
            write_run_report(
                self.output_path,
                update_index=False,
                completion_status="running",
            )
            self._write_manifest(status="running")
            self._running_report_repair_required = False
            write_run_report(
                self.output_path,
                update_index=False,
                completion_status=self.run_status,
            )
            manifest = self._write_manifest(status=self.run_status)
        except Exception:
            self._repair_failed_finalization()
            raise
        self._finalized = True
        # Keep the terminal manifest last inside the run directory.  The
        # cumulative parent index is outside that immutable artifact boundary
        # and must observe the published terminal state.
        try:
            write_outputs_index(self.output_path.parent)
        except Exception as exc:
            LOGGER.warning(
                "Saved run is complete, but the cumulative outputs index could not "
                "be refreshed: %s",
                exc,
            )
        return manifest

    def _repair_failed_finalization(self) -> None:
        """Best-effort repair of a prospective verdict while keeping retry open."""

        self._running_report_repair_required = True
        try:
            write_run_report(
                self.output_path,
                update_index=False,
                completion_status="running",
            )
        except Exception as exc:
            LOGGER.warning("Could not repair learner report after finalization failure: %s", exc)
            return
        try:
            # Seal only successfully repaired running documents.  Until this
            # refresh, the prior marker keeps any prospective terminal files
            # untrusted by digest.
            self._write_manifest(status="running")
            self._running_report_repair_required = False
        except Exception as exc:
            LOGGER.warning("Could not seal repaired running artifacts: %s", exc)

    def _require_unfinalized(self) -> None:
        if self._finalized:
            raise RuntimeError("This saved run is already finalized and cannot be rewritten.")

    def _write_manifest(self, *, status: str) -> Path:
        return write_manifest(
            self.output_path,
            scenario_id=_scenario_id(self.lab_name, self.config_path),
            status=status,
            config=self.config,
            config_path=self.config_path,
            seed=self.seed,
            started_at=self.started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    def _save_config_snapshot(self) -> None:
        target = self.output_path / "config.yaml"
        target.write_text(_dump_basic_yaml(self.config), encoding="utf-8")

    def _save_csv(self) -> None:
        csv_path = self.output_path / "log.csv"
        if not self.rows:
            csv_path.write_text("", encoding="utf-8")
            return

        fieldnames: list[str] = []
        seen: set[str] = set()
        for row in self.rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)

        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)

    def _save_states(self) -> None:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            state_path = self.output_path / "states.json"
            state_path.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")
            return

        columns: dict[str, list[float]] = {}
        for row in self.rows:
            for key, value in row.items():
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                columns.setdefault(key, []).append(number)

        arrays = {key: np.asarray(values, dtype=float) for key, values in columns.items()}
        np.savez_compressed(self.output_path / "states.npz", **arrays)

    def _save_replay(self) -> None:
        archive = self.replay.archive()
        if archive.frame_count:
            archive.save(self.output_path / "replay.npz")

    def _save_summary(self, summary: Mapping[str, Any]) -> None:
        payload = {
            "lab_name": self.lab_name,
            "samples": len(self.rows),
            "duration": self.rows[-1].get("time", 0.0) if self.rows else 0.0,
            **dict(summary),
            **self._config_metadata(),
        }
        (self.output_path / "summary.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _config_metadata(self) -> dict[str, str]:
        if self.config_path is None:
            return {}
        return {
            "config_path": self.config_path.as_posix(),
            "config_name": self.config_path.stem,
        }

    def _save_notes(self, notes: str) -> None:
        content = notes.strip() + "\n" if notes.strip() else f"# {self.lab_name}\n"
        (self.output_path / "notes.md").write_text(content, encoding="utf-8")

    def _save_interaction_events(self, events: list[Mapping[str, Any]] | None) -> None:
        if events is None:
            return
        (self.output_path / "interaction_events.json").write_text(
            json.dumps(list(events), indent=2),
            encoding="utf-8",
        )

    def _save_learner_snapshot(self, snapshot: Mapping[str, Any] | None) -> None:
        if not snapshot:
            return
        (self.output_path / "learner_snapshot.json").write_text(
            json.dumps(dict(snapshot), indent=2),
            encoding="utf-8",
        )

    def _save_learner_tuned_config(self, config: Mapping[str, Any] | None) -> None:
        if not config:
            return
        (self.output_path / "learner_tuned_config.yaml").write_text(
            _dump_basic_yaml(config),
            encoding="utf-8",
        )


def _flatten_mapping(row: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                flat[f"{key}_{index}"] = item
        elif isinstance(value, Mapping):
            for child_key, child_value in value.items():
                flat[f"{key}_{child_key}"] = child_value
        else:
            flat[key] = value
    return flat


def _dump_basic_yaml(data: Mapping[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, Mapping):
            lines.append(f"{prefix}{key}:")
            lines.append(_dump_basic_yaml(value, indent + 2).rstrip())
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines) + "\n"


def _scenario_id(lab_name: str, config_path: Path | None) -> str:
    return stable_scenario_id(lab_name, config_path)
