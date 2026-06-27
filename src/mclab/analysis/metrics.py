"""Control and trajectory metrics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def step_response_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    time_key: str = "time",
    position_key: str = "position",
    target_key: str = "target_position",
    effort_key: str = "control_force",
    tolerance_fraction: float = 0.02,
) -> dict[str, float | None]:
    """Compute simple scalar step-response metrics from logged rows."""

    if not rows:
        return {
            "rise_time": None,
            "overshoot_percent": None,
            "settling_time": None,
            "steady_state_error": None,
            "max_control_effort": None,
        }

    times = [_to_float(row.get(time_key)) for row in rows]
    positions = [_to_float(row.get(position_key)) for row in rows]
    targets = [_to_float(row.get(target_key, positions[-1])) for row in rows]
    efforts = [_to_float(row.get(effort_key, 0.0)) for row in rows]

    initial = positions[0]
    final_target = targets[-1]
    amplitude = final_target - initial
    abs_amplitude = abs(amplitude)
    if abs_amplitude < 1e-12:
        rise_time = None
        overshoot_percent = 0.0
        tolerance = tolerance_fraction
    else:
        lower = initial + 0.1 * amplitude
        upper = initial + 0.9 * amplitude
        t10 = _first_crossing(times, positions, lower, direction=amplitude)
        t90 = _first_crossing(times, positions, upper, direction=amplitude)
        rise_time = None if t10 is None or t90 is None else max(0.0, t90 - t10)

        if amplitude > 0.0:
            peak = max(positions)
            overshoot_percent = max(0.0, (peak - final_target) / abs_amplitude * 100.0)
        else:
            trough = min(positions)
            overshoot_percent = max(0.0, (final_target - trough) / abs_amplitude * 100.0)
        tolerance = tolerance_fraction * abs_amplitude

    settling_time = _settling_time(times, positions, final_target, tolerance)
    steady_state_error = final_target - positions[-1]
    max_control_effort = max(abs(value) for value in efforts) if efforts else 0.0
    return {
        "rise_time": rise_time,
        "overshoot_percent": overshoot_percent,
        "settling_time": settling_time,
        "steady_state_error": steady_state_error,
        "max_control_effort": max_control_effort,
    }


def _first_crossing(
    times: Sequence[float],
    values: Sequence[float],
    threshold: float,
    *,
    direction: float,
) -> float | None:
    for time, value in zip(times, values):
        crossed = value >= threshold if direction >= 0.0 else value <= threshold
        if crossed:
            return time
    return None


def _settling_time(
    times: Sequence[float],
    values: Sequence[float],
    target: float,
    tolerance: float,
) -> float | None:
    for index, time in enumerate(times):
        if all(abs(value - target) <= tolerance for value in values[index:]):
            return time
    return None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
