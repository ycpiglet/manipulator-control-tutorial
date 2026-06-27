"""MuJoCo model, data, joint, actuator, and site helpers."""

from __future__ import annotations

from pathlib import Path
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


def maybe_launch_viewer(mujoco: Any, model: Any, data: Any, *, enabled: bool) -> Any | None:
    if not enabled:
        return None
    try:
        from mujoco import viewer as mujoco_viewer  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local GUI support.
        raise RuntimeError("MuJoCo viewer could not be launched in this environment.") from exc
    return mujoco_viewer.launch_passive(model, data)

