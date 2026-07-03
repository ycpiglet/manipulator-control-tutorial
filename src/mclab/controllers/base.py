"""Common controller protocols and command containers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlCommand:
    """A scalar control command plus useful diagnostic terms."""

    value: float
    unsaturated_value: float
    error: float
    error_rate: float
    proportional: float = 0.0
    integral: float = 0.0
    derivative: float = 0.0
    saturated: bool = False


def clip(value: float, lower: float | None, upper: float | None) -> tuple[float, bool]:
    clipped = value
    saturated = False
    if lower is not None and clipped < lower:
        clipped = lower
        saturated = True
    if upper is not None and clipped > upper:
        clipped = upper
        saturated = True
    return clipped, saturated

