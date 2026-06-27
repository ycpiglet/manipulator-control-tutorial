"""Simulation logging utilities."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from mclab.config import PROJECT_ROOT, resolve_project_path


def create_output_path(lab_name: str, output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        path = resolve_project_path(output_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = PROJECT_ROOT / "outputs" / f"{stamp}_{lab_name}"
    path.mkdir(parents=True, exist_ok=True)
    (path / "plots").mkdir(exist_ok=True)
    return path


class RunLogger:
    """Collect rows and save the standard lab output files."""

    def __init__(
        self,
        lab_name: str,
        config: Mapping[str, Any],
        *,
        config_path: str | Path | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.lab_name = lab_name
        self.config = dict(config)
        self.config_path = Path(config_path) if config_path else None
        self.output_path = create_output_path(lab_name, output_dir)
        self.rows: list[dict[str, Any]] = []

    def record(self, **row: Any) -> None:
        self.rows.append(_flatten_mapping(row))

    def save(self, summary: Mapping[str, Any] | None = None, notes: str = "") -> Path:
        self._save_config_snapshot()
        self._save_csv()
        self._save_states()
        self._save_summary(summary or {})
        self._save_notes(notes)
        return self.output_path

    def _save_config_snapshot(self) -> None:
        target = self.output_path / "config.yaml"
        if self.config_path:
            source = resolve_project_path(self.config_path)
            if source.exists():
                shutil.copyfile(source, target)
                return
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
        np.savez(self.output_path / "states.npz", **arrays)

    def _save_summary(self, summary: Mapping[str, Any]) -> None:
        payload = {
            "lab_name": self.lab_name,
            "samples": len(self.rows),
            "duration": self.rows[-1].get("time", 0.0) if self.rows else 0.0,
            **dict(summary),
        }
        (self.output_path / "summary.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _save_notes(self, notes: str) -> None:
        content = notes.strip() + "\n" if notes.strip() else f"# {self.lab_name}\n"
        (self.output_path / "notes.md").write_text(content, encoding="utf-8")


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

