"""Application services for the MCLab desktop experience.

The package deliberately has no runtime or Qt imports at module import time.
Headless setup diagnostics must remain available before NumPy, MuJoCo, and the
optional desktop dependency are installed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .catalog import ScenarioCatalog, ScenarioDefinition
    from .session import LabAdapter, SessionState, SimulationSession

__all__ = [
    "LabAdapter",
    "ScenarioCatalog",
    "ScenarioDefinition",
    "SessionState",
    "SimulationSession",
]

_EXPORT_MODULES = {
    "LabAdapter": ".session",
    "ScenarioCatalog": ".catalog",
    "ScenarioDefinition": ".catalog",
    "SessionState": ".session",
    "SimulationSession": ".session",
}


def __getattr__(name: str) -> Any:
    """Import public application services only when a caller requests one."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
