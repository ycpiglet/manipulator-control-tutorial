"""Simulation logging utilities."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mclab.application.artifacts import ReplayRecorder, write_manifest
from mclab.config import (
    PROJECT_ROOT,
    default_outputs_root,
    is_frozen_bundle,
    resolve_output_path,
)
from mclab.sim.reporting import write_run_report


def create_output_path(lab_name: str, output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        path = resolve_output_path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = default_outputs_root() if is_frozen_bundle() else PROJECT_ROOT / "outputs"
        path = _create_unique_output_directory(root / f"{stamp}_{lab_name}")
    (path / "plots").mkdir(exist_ok=True)
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
    ) -> Path:
        self.run_status = run_status
        self._save_config_snapshot()
        self._save_csv()
        self._save_states()
        self._save_replay()
        self._save_summary(summary or {})
        self._save_notes(notes)
        self._save_interaction_events(interaction_events)
        self._save_learner_snapshot(learner_snapshot)
        self._save_learner_tuned_config(learner_tuned_config)
        self.finalize_artifacts()
        return self.output_path

    def finalize_artifacts(self) -> Path:
        """Refresh manifest hashes after optional plots have been written."""

        write_manifest(
            self.output_path,
            scenario_id=_scenario_id(self.lab_name, self.config_path),
            status=self.run_status,
            config=self.config,
            config_path=self.config_path,
            seed=self.seed,
            started_at=self.started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        write_run_report(self.output_path)
        return write_manifest(
            self.output_path,
            scenario_id=_scenario_id(self.lab_name, self.config_path),
            status=self.run_status,
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
    prefix = {
        "lab01_msd": "lab01",
        "lab02_pid": "lab02",
        "lab03_trajectory": "lab03",
        "lab03_2dof": "lab03",
        "lab04_panda": "lab04",
    }.get(lab_name, lab_name)
    suffix = config_path.stem if config_path else "custom"
    return f"{prefix}.{suffix.replace('_', '-')}"
