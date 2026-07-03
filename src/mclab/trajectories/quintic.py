"""Quintic polynomial trajectory generator."""

from __future__ import annotations

from .minimum_jerk import MinimumJerkTrajectory


class QuinticTrajectory(MinimumJerkTrajectory):
    """Quintic with zero velocity/acceleration boundary conditions."""

