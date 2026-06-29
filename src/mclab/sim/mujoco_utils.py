"""MuJoCo model, data, joint, actuator, and site helpers."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter, sleep
from collections.abc import Sequence
from typing import Any

from mclab.config import resolve_project_path


def import_mujoco() -> Any:
    try:
        import mujoco  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MuJoCo is required to run this lab. Install the project with "
            "`pip install -e .` or install the `mujoco` package."
        ) from exc
    return mujoco


def load_model_and_data(model_path: str | Path) -> tuple[Any, Any, Any]:
    mujoco = import_mujoco()
    resolved = resolve_project_path(model_path)
    model = mujoco.MjModel.from_xml_path(str(resolved))
    data = mujoco.MjData(model)
    return mujoco, model, data


def maybe_launch_viewer(
    mujoco: Any,
    model: Any,
    data: Any,
    *,
    enabled: bool,
    key_callback: Any | None = None,
    show_ui: bool = False,
) -> Any | None:
    if not enabled:
        return None
    try:
        from mujoco import viewer as mujoco_viewer  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        raise RuntimeError("MuJoCo viewer could not be launched in this environment.") from exc
    return mujoco_viewer.launch_passive(
        model,
        data,
        key_callback=key_callback,
        show_left_ui=show_ui,
        show_right_ui=show_ui,
    )


def viewer_clock() -> float:
    return perf_counter()


def sync_viewer(
    viewer_handle: Any | None,
    data: Any,
    *,
    realtime: bool = False,
    wall_start: float | None = None,
    sim_start: float = 0.0,
) -> None:
    if viewer_handle is None:
        return
    viewer_handle.sync()
    if realtime and wall_start is not None:
        target_wall_time = wall_start + max(0.0, float(data.time) - sim_start)
        delay = target_wall_time - perf_counter()
        if delay > 0.0:
            sleep(min(delay, 0.05))


def sync_paused_viewer(viewer_handle: Any | None, *, interval: float = 1.0 / 30.0) -> None:
    if viewer_handle is not None:
        viewer_handle.sync()
    sleep(max(0.0, float(interval)))


def viewer_is_running(viewer_handle: Any | None) -> bool:
    if viewer_handle is None:
        return True
    is_running = getattr(viewer_handle, "is_running", None)
    if not callable(is_running):
        return True
    return bool(is_running())


def pause_viewer_at_end(viewer_handle: Any | None, *, enabled: bool) -> None:
    if viewer_handle is None or not enabled:
        return

    if not viewer_is_running(viewer_handle):
        return

    if not callable(getattr(viewer_handle, "is_running", None)):
        input("Simulation complete. Press Enter to close the MuJoCo viewer...")
        return

    print("Simulation complete. Close the MuJoCo viewer window to exit.")
    try:
        while viewer_is_running(viewer_handle):
            viewer_handle.sync()
            sleep(1.0 / 30.0)
    except KeyboardInterrupt:
        pass


def reset_viewer_overlays(viewer_handle: Any | None) -> None:
    """Clear per-frame learner guide geoms from a passive viewer."""

    scene = getattr(viewer_handle, "user_scn", None)
    if scene is not None and hasattr(scene, "ngeom"):
        scene.ngeom = 0


def add_viewer_sphere(
    mujoco: Any,
    viewer_handle: Any | None,
    position: Sequence[float],
    *,
    radius: float,
    rgba: Sequence[float],
) -> bool:
    """Add a sphere to the passive viewer's user scene."""

    geom_type = mujoco.mjtGeom.mjGEOM_SPHERE
    return _add_viewer_geom(mujoco, viewer_handle, geom_type, position, [radius, radius, radius], rgba)


def add_viewer_box(
    mujoco: Any,
    viewer_handle: Any | None,
    position: Sequence[float],
    *,
    half_size: Sequence[float],
    rgba: Sequence[float],
) -> bool:
    """Add an axis-aligned box to the passive viewer's user scene."""

    geom_type = mujoco.mjtGeom.mjGEOM_BOX
    return _add_viewer_geom(mujoco, viewer_handle, geom_type, position, half_size, rgba)


def _add_viewer_geom(
    mujoco: Any,
    viewer_handle: Any | None,
    geom_type: Any,
    position: Sequence[float],
    size: Sequence[float],
    rgba: Sequence[float],
) -> bool:
    scene = getattr(viewer_handle, "user_scn", None)
    geoms = getattr(scene, "geoms", None)
    if scene is None or geoms is None or not hasattr(scene, "ngeom"):
        return False

    geom_index = int(scene.ngeom)
    if geom_index >= len(geoms):
        return False

    import numpy as np

    geom = geoms[geom_index]
    mujoco.mjv_initGeom(
        geom,
        geom_type,
        np.asarray(size, dtype=float),
        np.asarray(position, dtype=float),
        np.eye(3, dtype=float).reshape(-1),
        np.asarray(rgba, dtype=float),
    )
    category = getattr(getattr(mujoco, "mjtCatBit", None), "mjCAT_DECOR", None)
    if category is not None and hasattr(geom, "category"):
        geom.category = category
    if hasattr(geom, "transparent") and len(rgba) >= 4:
        geom.transparent = 1 if float(rgba[3]) < 1.0 else 0
    scene.ngeom = geom_index + 1
    return True
