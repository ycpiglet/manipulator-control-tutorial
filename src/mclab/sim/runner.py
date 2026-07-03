"""Shared MuJoCo simulation loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mclab.sim.mujoco_utils import hide_viewer_side_panels


def run_fixed_step_loop(
    *,
    mujoco: Any,
    model: Any,
    data: Any,
    sim_time: float,
    step_callback: Callable[[float], None],
    viewer: Any | None = None,
) -> None:
    """Run a straightforward MuJoCo loop with an optional passive viewer."""

    while data.time < sim_time:
        step_callback(float(data.time))
        mujoco.mj_step(model, data)
        if viewer is not None:
            hide_viewer_side_panels(viewer)
            viewer.sync()
            hide_viewer_side_panels(viewer)
