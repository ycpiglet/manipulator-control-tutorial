"""Minimum-jerk trajectory generator."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Target, normalized_time


@dataclass(frozen=True)
class MinimumJerkTrajectory:
    start: float
    end: float
    duration: float
    start_time: float = 0.0

    def evaluate(self, t: float) -> Target:
        tau = normalized_time(t, self.start_time, self.duration)
        delta = self.end - self.start
        if tau <= 0.0:
            return Target(position=self.start)
        if tau >= 1.0:
            return Target(position=self.end)

        s = 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5
        ds = (30.0 * tau**2 - 60.0 * tau**3 + 30.0 * tau**4) / self.duration
        dds = (60.0 * tau - 180.0 * tau**2 + 120.0 * tau**3) / self.duration**2
        ddds = (60.0 - 360.0 * tau + 360.0 * tau**2) / self.duration**3
        return Target(
            position=self.start + delta * s,
            velocity=delta * ds,
            acceleration=delta * dds,
            jerk=delta * ddds,
        )

