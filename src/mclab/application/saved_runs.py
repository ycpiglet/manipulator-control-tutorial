"""Resolve saved and legacy runs into reproducible desktop launches."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mclab.application.catalog import ScenarioCatalog, ScenarioDefinition
from mclab.config import PROJECT_ROOT, load_config


@dataclass(frozen=True)
class SavedRunLaunch:
    scenario: ScenarioDefinition
    config: dict[str, Any]
    source: Path


def resolve_saved_run_launch(
    run_path: str | Path,
    catalog: ScenarioCatalog,
    *,
    tuned: bool = False,
) -> SavedRunLaunch:
    """Load the exact resolved config or the optional final learner tuning."""

    run = Path(run_path)
    if not run.is_dir():
        raise FileNotFoundError(f"Saved run folder does not exist: {run}")
    manifest = _read_json(run / "manifest.json")
    summary = _read_json(run / "summary.json")
    scenario = _find_scenario(catalog, manifest, summary)
    if scenario is None:
        raise ValueError("This saved run does not identify a scenario in the current catalog.")

    if tuned:
        source = run / "learner_tuned_config.yaml"
        if not source.is_file():
            raise FileNotFoundError("This run does not contain learner_tuned_config.yaml.")
        config = load_config(source)
    else:
        source = run / "config.yaml"
        resolved = manifest.get("config", {}).get("resolved")
        if isinstance(resolved, dict) and resolved:
            config = deepcopy(resolved)
        elif source.is_file():
            config = load_config(source)
        else:
            raise FileNotFoundError("This run does not contain a reusable resolved config.")
    return SavedRunLaunch(scenario=scenario, config=config, source=source)


def _find_scenario(
    catalog: ScenarioCatalog,
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> ScenarioDefinition | None:
    scenario_id = str(manifest.get("scenario_id") or "")
    if scenario_id:
        try:
            return catalog.get(scenario_id)
        except KeyError:
            pass
    raw_config_path = str(
        summary.get("config_path")
        or manifest.get("config", {}).get("path")
        or ""
    )
    if not raw_config_path:
        return None
    config_path = Path(raw_config_path)
    if config_path.is_absolute():
        try:
            config_path = config_path.relative_to(PROJECT_ROOT)
        except ValueError:
            return None
    return catalog.find_by_config(config_path.as_posix())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}
