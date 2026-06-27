"""PID controller implementation."""

from __future__ import annotations

from dataclasses import dataclass

from .base import ControlCommand, clip


@dataclass
class PIDController:
    """Readable scalar PID controller with optional saturation and anti-windup."""

    kp: float
    ki: float
    kd: float
    dt: float
    output_min: float | None = None
    output_max: float | None = None
    integral_min: float | None = None
    integral_max: float | None = None
    anti_windup: bool = True

    integral_error: float = 0.0
    previous_error: float | None = None

    def reset(self) -> None:
        self.integral_error = 0.0
        self.previous_error = None

    def compute(
        self,
        *,
        setpoint: float,
        measurement: float,
        measurement_rate: float | None = None,
    ) -> ControlCommand:
        error = setpoint - measurement
        if measurement_rate is not None:
            error_rate = -measurement_rate
        elif self.previous_error is None:
            error_rate = 0.0
        else:
            error_rate = (error - self.previous_error) / self.dt

        candidate_integral = self.integral_error + error * self.dt
        candidate_integral, _ = clip(
            candidate_integral,
            self.integral_min,
            self.integral_max,
        )

        p_term = self.kp * error
        i_term = self.ki * candidate_integral
        d_term = self.kd * error_rate
        unsaturated = p_term + i_term + d_term
        value, saturated = clip(unsaturated, self.output_min, self.output_max)

        if not saturated or not self.anti_windup:
            self.integral_error = candidate_integral
        else:
            # Keep the integral when it would push the saturated output farther
            # into the limit. This is intentionally simple and inspectable.
            output_high = self.output_max is not None and unsaturated > self.output_max
            output_low = self.output_min is not None and unsaturated < self.output_min
            if (output_high and error < 0.0) or (output_low and error > 0.0):
                self.integral_error = candidate_integral

        self.previous_error = error
        return ControlCommand(
            value=value,
            unsaturated_value=unsaturated,
            error=error,
            error_rate=error_rate,
            proportional=p_term,
            integral=self.ki * self.integral_error,
            derivative=d_term,
            saturated=saturated,
        )

