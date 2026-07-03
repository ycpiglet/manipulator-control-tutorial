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


def jacobian_determinant(q: list[float] | tuple[float, float], geometry: TwoLinkGeometry) -> float:
    matrix = jacobian(q, geometry)
    return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]


def manipulability(q: list[float] | tuple[float, float], geometry: TwoLinkGeometry) -> float:
    return abs(jacobian_determinant(q, geometry))


def jacobian_condition_number(
    q: list[float] | tuple[float, float],
    geometry: TwoLinkGeometry,
    *,
    singular_value_floor: float = 1e-9,
) -> float:
    matrix = jacobian(q, geometry)
    a, b = matrix[0]
    c, d = matrix[1]
    trace = a * a + b * b + c * c + d * d
    determinant = (a * d - b * c) ** 2
    discriminant = max(0.0, trace * trace - 4.0 * determinant)
    lambda_max = 0.5 * (trace + math.sqrt(discriminant))
    lambda_min = 0.5 * (trace - math.sqrt(discriminant))
    if lambda_min <= singular_value_floor * singular_value_floor:
        return float("inf")
    return math.sqrt(lambda_max / lambda_min)


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


def damped_least_squares_inverse(
    q: list[float] | tuple[float, float],
    geometry: TwoLinkGeometry,
    *,
    damping: float = 0.08,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return J^T (J J^T + lambda^2 I)^-1 for the planar arm."""

    matrix = jacobian(q, geometry)
    a, b = matrix[0]
    c, d = matrix[1]
    lambda_sq = max(0.0, float(damping)) ** 2

    jj_00 = a * a + b * b + lambda_sq
    jj_01 = a * c + b * d
    jj_11 = c * c + d * d + lambda_sq
    determinant = jj_00 * jj_11 - jj_01 * jj_01
    if abs(determinant) < 1.0e-12:
        determinant = 1.0e-12 if determinant >= 0.0 else -1.0e-12

    inv_00 = jj_11 / determinant
    inv_01 = -jj_01 / determinant
    inv_11 = jj_00 / determinant

    return (
        (a * inv_00 + c * inv_01, a * inv_01 + c * inv_11),
        (b * inv_00 + d * inv_01, b * inv_01 + d * inv_11),
    )


def damped_least_squares_joint_velocity(
    q: list[float] | tuple[float, float],
    task_velocity: list[float] | tuple[float, float],
    geometry: TwoLinkGeometry,
    *,
    damping: float = 0.08,
) -> tuple[float, float]:
    inverse = damped_least_squares_inverse(q, geometry, damping=damping)
    vx, vy = float(task_velocity[0]), float(task_velocity[1])
    return (
        inverse[0][0] * vx + inverse[0][1] * vy,
        inverse[1][0] * vx + inverse[1][1] * vy,
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
