"""Trapezoidal velocity trajectory generator."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .base import Target


@dataclass(frozen=True)
class TrapezoidalTrajectory:
    start: float
    end: float
    max_velocity: float
    max_acceleration: float
    start_time: float = 0.0

    def __post_init__(self) -> None:
        if self.max_velocity <= 0.0:
            raise ValueError("max_velocity must be positive")
        if self.max_acceleration <= 0.0:
            raise ValueError("max_acceleration must be positive")

    @property
    def duration(self) -> float:
        return self._profile()[3]

    def evaluate(self, t: float) -> Target:
        distance, direction, t_acc, total_time, cruise_time, peak_velocity = self._profile()
        elapsed = t - self.start_time
        if elapsed <= 0.0 or distance == 0.0:
            return Target(position=self.start)
        if elapsed >= total_time:
            return Target(position=self.end)

        accel = self.max_acceleration
        if elapsed < t_acc:
            pos = 0.5 * accel * elapsed**2
            vel = accel * elapsed
            acc = accel
        elif elapsed < t_acc + cruise_time:
            cruise_elapsed = elapsed - t_acc
            pos = 0.5 * accel * t_acc**2 + peak_velocity * cruise_elapsed
            vel = peak_velocity
            acc = 0.0
        else:
            decel_elapsed = elapsed - t_acc - cruise_time
            decel_start = 0.5 * accel * t_acc**2 + peak_velocity * cruise_time
            pos = decel_start + peak_velocity * decel_elapsed - 0.5 * accel * decel_elapsed**2
            vel = peak_velocity - accel * decel_elapsed
            acc = -accel

        return Target(
            position=self.start + direction * pos,
            velocity=direction * vel,
            acceleration=direction * acc,
            jerk=0.0,
        )

    def _profile(self) -> tuple[float, float, float, float, float, float]:
        distance = abs(self.end - self.start)
        direction = 1.0 if self.end >= self.start else -1.0
        if distance == 0.0:
            return 0.0, direction, 0.0, 0.0, 0.0, 0.0

        t_acc = self.max_velocity / self.max_acceleration
        d_acc = 0.5 * self.max_acceleration * t_acc**2
        if 2.0 * d_acc > distance:
            t_acc = sqrt(distance / self.max_acceleration)
            peak_velocity = self.max_acceleration * t_acc
            cruise_time = 0.0
        else:
            peak_velocity = self.max_velocity
            cruise_time = (distance - 2.0 * d_acc) / peak_velocity
        total_time = 2.0 * t_acc + cruise_time
        return distance, direction, t_acc, total_time, cruise_time, peak_velocity

