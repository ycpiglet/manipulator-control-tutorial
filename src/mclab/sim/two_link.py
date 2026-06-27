"""Planar 2-link arm kinematics used by Lab03."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TwoLinkGeometry:
    link1: float = 0.6
    link2: float = 0.45


def forward_kinematics(q: list[float] | tuple[float, float], geometry: TwoLinkGeometry) -> tuple[float, float]:
    q1, q2 = float(q[0]), float(q[1])
    q12 = q1 + q2
    x = geometry.link1 * math.cos(q1) + geometry.link2 * math.cos(q12)
    y = geometry.link1 * math.sin(q1) + geometry.link2 * math.sin(q12)
    return x, y


def jacobian(q: list[float] | tuple[float, float], geometry: TwoLinkGeometry) -> tuple[tuple[float, float], tuple[float, float]]:
    q1, q2 = float(q[0]), float(q[1])
    q12 = q1 + q2
    return (
        (
            -geometry.link1 * math.sin(q1) - geometry.link2 * math.sin(q12),
            -geometry.link2 * math.sin(q12),
        ),
        (
            geometry.link1 * math.cos(q1) + geometry.link2 * math.cos(q12),
            geometry.link2 * math.cos(q12),
        ),
    )


def end_effector_velocity(
    q: list[float] | tuple[float, float],
    qdot: list[float] | tuple[float, float],
    geometry: TwoLinkGeometry,
) -> tuple[float, float]:
    j = jacobian(q, geometry)
    return (
        j[0][0] * qdot[0] + j[0][1] * qdot[1],
        j[1][0] * qdot[0] + j[1][1] * qdot[1],
    )


def inverse_kinematics(
    target_xy: list[float] | tuple[float, float],
    geometry: TwoLinkGeometry,
    *,
    elbow: str = "down",
) -> tuple[float, float]:
    x, y = float(target_xy[0]), float(target_xy[1])
    radius_sq = x * x + y * y
    link1_sq = geometry.link1 * geometry.link1
    link2_sq = geometry.link2 * geometry.link2
    cos_q2 = (radius_sq - link1_sq - link2_sq) / (2.0 * geometry.link1 * geometry.link2)
    cos_q2 = max(-1.0, min(1.0, cos_q2))
    sign = -1.0 if elbow == "up" else 1.0
    sin_q2 = sign * math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))
    q2 = math.atan2(sin_q2, cos_q2)
    k1 = geometry.link1 + geometry.link2 * cos_q2
    k2 = geometry.link2 * sin_q2
    q1 = math.atan2(y, x) - math.atan2(k2, k1)
    return q1, q2
