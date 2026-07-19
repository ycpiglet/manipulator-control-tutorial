"""Small factory boundary between the Qt shell and lab adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mclab.application.adapters import Lab01Adapter, Lab02Adapter
from mclab.application.catalog import ScenarioDefinition
from mclab.application.lab03_adapter import Lab03Adapter
from mclab.application.lab04_adapter import Lab04Adapter


def create_scenario_adapter(
    scenario: ScenarioDefinition,
    config: dict[str, Any],
    *,
    output_dir: str | Path | None,
    safe_mode: bool,
) -> Any:
    adapter_class = {
        "lab01": Lab01Adapter,
        "lab02": Lab02Adapter,
        "lab03": Lab03Adapter,
        "lab04": Lab04Adapter,
    }[scenario.lab_name]
    return adapter_class(
        scenario,
        output_dir=output_dir,
        safe_mode=safe_mode,
        config_override=config,
    )
