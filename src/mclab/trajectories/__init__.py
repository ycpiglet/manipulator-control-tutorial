"""Trajectory generators."""

from __future__ import annotations

from typing import Any

from .base import Target, Trajectory
from .minimum_jerk import MinimumJerkTrajectory
from .quintic import QuinticTrajectory
from .s_curve import SCurveTrajectory
from .step import StepTrajectory
from .trapezoidal import TrapezoidalTrajectory

__all__ = [
    "MinimumJerkTrajectory",
    "QuinticTrajectory",
    "SCurveTrajectory",
    "StepTrajectory",
    "Target",
    "Trajectory",
    "TrapezoidalTrajectory",
    "build_trajectory",
]


def build_trajectory(config: dict[str, Any]) -> Trajectory:
    kind = str(config.get("type", "minimum_jerk")).lower().replace("-", "_")
    start = float(config.get("start", config.get("start_position", 0.0)))
    end = float(config.get("end", config.get("goal_position", 1.0)))
    start_time = float(config.get("start_time", 0.0))

    if kind == "step":
        return StepTrajectory(start=start, end=end, start_time=start_time)
    if kind in {"minimum_jerk", "min_jerk"}:
        return MinimumJerkTrajectory(
            start=start,
            end=end,
            duration=float(config.get("duration", 1.0)),
            start_time=start_time,
        )
    if kind == "quintic":
        return QuinticTrajectory(
            start=start,
            end=end,
            duration=float(config.get("duration", 1.0)),
            start_time=start_time,
        )
    if kind in {"s_curve", "scurve"}:
        return SCurveTrajectory(
            start=start,
            end=end,
            duration=float(config.get("duration", 1.0)),
            start_time=start_time,
        )
    if kind == "trapezoidal":
        return TrapezoidalTrajectory(
            start=start,
            end=end,
            max_velocity=float(config.get("max_velocity", 0.5)),
            max_acceleration=float(config.get("max_acceleration", 1.0)),
            start_time=start_time,
        )
    raise ValueError(f"Unknown trajectory type: {config.get('type')}")

