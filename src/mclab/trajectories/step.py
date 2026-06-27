"""Step trajectory generator."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Target


@dataclass(frozen=True)
class StepTrajectory:
    start: float
    end: float
    start_time: float = 0.0

    def evaluate(self, t: float) -> Target:
        position = self.start if t < self.start_time else self.end
        return Target(position=position)

