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
) -> Any | None:
    if not enabled:
        return None
    try:
        from mujoco import viewer as mujoco_viewer  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        raise RuntimeError("MuJoCo viewer could not be launched in this environment.") from exc
    viewer_handle = mujoco_viewer.launch_passive(
        model,
        data,
        key_callback=key_callback,
        show_left_ui=False,
        show_right_ui=False,
    )
    hide_viewer_side_panels(viewer_handle)
    return viewer_handle


def hide_viewer_side_panels(viewer_handle: Any | None) -> None:
    """Keep MuJoCo's built-in side panels out of learner-facing demos."""

    sim = _viewer_sim(viewer_handle)
    if sim is None:
        return
    for attr in ("ui0_enable", "ui1_enable"):
        if hasattr(sim, attr):
            try:
                setattr(sim, attr, False)
            except Exception:
                pass


def _viewer_sim(viewer_handle: Any | None) -> Any | None:
    if viewer_handle is None:
        return None

    get_sim = getattr(viewer_handle, "_get_sim", None)
    if callable(get_sim):
        try:
            return get_sim()
        except Exception:
            return None

    sim_ref = getattr(viewer_handle, "_sim", None)
    if callable(sim_ref):
        try:
            return sim_ref()
        except Exception:
            return None
    return None


def viewer_clock() -> float:
    return perf_counter()


def sync_viewer(
    viewer_handle: Any | None,
    data: Any,
    *,
    realtime: bool = False,
    wall_start: float | None = None,
    sim_start: float = 0.0,
    speed_scale: float = 1.0,
) -> None:
    if viewer_handle is None:
        return
    hide_viewer_side_panels(viewer_handle)
    viewer_handle.sync()
    hide_viewer_side_panels(viewer_handle)
    if realtime and wall_start is not None:
        speed = max(0.05, float(speed_scale))
        target_wall_time = wall_start + max(0.0, float(data.time) - sim_start) / speed
        delay = target_wall_time - perf_counter()
        if delay > 0.0:
            sleep(min(delay, 0.05))


def realtime_wall_start(data_time: float, sim_start: float, speed_scale: float = 1.0) -> float:
    speed = max(0.05, float(speed_scale))
    return perf_counter() - max(0.0, float(data_time) - float(sim_start)) / speed


def sync_paused_viewer(viewer_handle: Any | None, *, interval: float = 1.0 / 30.0) -> None:
    if viewer_handle is not None:
        hide_viewer_side_panels(viewer_handle)
        viewer_handle.sync()
        hide_viewer_side_panels(viewer_handle)
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
            hide_viewer_side_panels(viewer_handle)
            viewer_handle.sync()
            hide_viewer_side_panels(viewer_handle)
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
