"""Application services for the MCLab desktop experience.

The package deliberately has no Qt imports at module import time.  Headless
users can keep using the simulator, reports, and CLI without installing the
optional desktop dependency.
"""

from .catalog import ScenarioCatalog, ScenarioDefinition
from .session import LabAdapter, SessionState, SimulationSession

__all__ = [
    "LabAdapter",
    "ScenarioCatalog",
    "ScenarioDefinition",
    "SessionState",
    "SimulationSession",
]
