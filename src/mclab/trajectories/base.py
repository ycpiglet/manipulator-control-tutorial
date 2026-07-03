"""Common trajectory target interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Target:
    position: float
    velocity: float = 0.0
    acceleration: float = 0.0
    jerk: float = 0.0


class Trajectory(Protocol):
    def evaluate(self, t: float) -> Target:
        ...


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def normalized_time(t: float, start_time: float, duration: float) -> float:
    if duration <= 0.0:
        return 1.0
    return clamp((t - start_time) / duration, 0.0, 1.0)

