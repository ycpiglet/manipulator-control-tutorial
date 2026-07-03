"""S-curve trajectory generator."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Target, normalized_time


@dataclass(frozen=True)
class SCurveTrajectory:
    """A smooth 7th-order S-curve profile with zero endpoint velocity/acceleration."""

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

        s = 35.0 * tau**4 - 84.0 * tau**5 + 70.0 * tau**6 - 20.0 * tau**7
        ds = (140.0 * tau**3 - 420.0 * tau**4 + 420.0 * tau**5 - 140.0 * tau**6)
        dds = (420.0 * tau**2 - 1680.0 * tau**3 + 2100.0 * tau**4 - 840.0 * tau**5)
        ddds = (840.0 * tau - 5040.0 * tau**2 + 8400.0 * tau**3 - 4200.0 * tau**4)
        return Target(
            position=self.start + delta * s,
            velocity=delta * ds / self.duration,
            acceleration=delta * dds / self.duration**2,
            jerk=delta * ddds / self.duration**3,
        )

