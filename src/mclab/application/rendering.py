"""Shared MuJoCo renderer and semantic overlay helpers for Qt sessions."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

_RENDER_CONTEXT = threading.local()
_RENDERER_FACTORY_LOCK = threading.Lock()


@dataclass
class RetainedRenderResources:
    """Live MuJoCo objects retained by their renderer-owning worker thread."""

    donor: Any
    mujoco: Any
    model: Any
    data: Any
    renderer: Any
    camera: Any


class _BorrowedContext:
    """Make a worker-owned GL context current without letting Renderer free it."""

    def __init__(self, context: Any) -> None:
        self._context = context

    def make_current(self) -> None:
        self._context.make_current()

    def free(self) -> None:
        """The persistent worker owns this context and frees it at thread shutdown."""


def create_mujoco_renderer(
    mujoco: Any,
    model: Any,
    *,
    height: int,
    width: int,
) -> Any:
    """Create a renderer while reusing one EGL context per simulation thread."""

    if os.environ.get("MUJOCO_GL", "").strip().lower() != "egl":
        return mujoco.Renderer(model, height=height, width=width)
    from mujoco.rendering.classic import gl_context

    context = getattr(_RENDER_CONTEXT, "context", None)
    if context is None:
        context_class = gl_context.GLContext
        if context_class is None:
            return mujoco.Renderer(model, height=height, width=width)
        context = context_class(width, height)
        _RENDER_CONTEXT.context = context
    context.make_current()
    with _RENDERER_FACTORY_LOCK:
        context_class = gl_context.GLContext
        gl_context.GLContext = None
        try:
            renderer = mujoco.Renderer(model, height=height, width=width)
        finally:
            gl_context.GLContext = context_class
    renderer._gl_context = _BorrowedContext(context)  # noqa: SLF001
    return renderer


def release_thread_mujoco_context() -> None:
    """Detach the retained EGL context before report or other graphics work."""

    if getattr(_RENDER_CONTEXT, "context", None) is None:
        return
    import mujoco.egl as mujoco_egl

    released = mujoco_egl.EGL.eglMakeCurrent(
        mujoco_egl.EGL_DISPLAY,
        mujoco_egl.EGL.EGL_NO_SURFACE,
        mujoco_egl.EGL.EGL_NO_SURFACE,
        mujoco_egl.EGL.EGL_NO_CONTEXT,
    )
    if not released:
        raise RuntimeError("Failed to release the worker EGL context.")


def destroy_thread_mujoco_context() -> None:
    """Free the persistent EGL context on the thread that created it."""

    context = getattr(_RENDER_CONTEXT, "context", None)
    if context is None:
        return
    try:
        context.free()
    finally:
        _RENDER_CONTEXT.context = None


def can_reuse_adapter_render_resources(donor: Any, recipient: Any) -> bool:
    """Return whether a restart can safely keep the exact native render objects."""

    donor_scenario = getattr(getattr(donor, "scenario", None), "id", None)
    recipient_scenario = getattr(getattr(recipient, "scenario", None), "id", None)
    return bool(
        os.environ.get("MUJOCO_GL", "").strip().lower() == "egl"
        and type(donor) is type(recipient)
        and donor_scenario
        and donor_scenario == recipient_scenario
        and getattr(donor, "safe_mode", False) == getattr(recipient, "safe_mode", False)
        and getattr(donor, "config", None) == getattr(recipient, "config", None)
    )


def retain_adapter_render_resources(adapter: Any) -> RetainedRenderResources | None:
    """Detach native render state before a completed adapter is finalized."""

    renderer = getattr(adapter, "renderer", None)
    if renderer is None or os.environ.get("MUJOCO_GL", "").strip().lower() != "egl":
        return None
    resources = RetainedRenderResources(
        adapter,
        getattr(adapter, "mujoco", None),
        getattr(adapter, "model", None),
        getattr(adapter, "data", None),
        renderer,
        getattr(adapter, "camera", None),
    )
    adapter.renderer = None
    return resources


def adopt_adapter_render_resources(
    resources: RetainedRenderResources,
    adapter: Any,
) -> bool:
    """Give a same-scenario restart the previous model, data, camera, and renderer."""

    if not can_reuse_adapter_render_resources(resources.donor, adapter):
        return False
    adapter.prepare()
    adapter.mujoco = resources.mujoco
    adapter.model = resources.model
    adapter.data = resources.data
    adapter.renderer = resources.renderer
    adapter.camera = resources.camera
    adapter.reset()
    return True


def close_retained_render_resources(resources: RetainedRenderResources | None) -> None:
    """Close a retained renderer when it cannot be adopted or its worker exits."""

    if resources is not None:
        close_mujoco_renderer(resources.renderer)


def close_mujoco_renderer(renderer: Any) -> None:
    """Finish queued GPU work before destroying an offscreen context."""

    try:
        context = getattr(renderer, "_gl_context", None)
        if context is not None:
            context.make_current()
        from OpenGL.GL import glFinish

        glFinish()
    except Exception:
        pass
    renderer.close()
    release_thread_mujoco_context()


class MujocoRenderMixin:
    """Provide camera input, replay state restore, and 30 fps frame rendering."""

    mujoco: Any
    model: Any
    data: Any
    renderer: Any
    camera: Any
    safe_mode: bool

    def setup_camera(self) -> None:
        self.camera = self.mujoco.MjvCamera()
        self.mujoco.mjv_defaultFreeCamera(self.model, self.camera)

    def reset_camera(self) -> None:
        self.mujoco.mjv_defaultFreeCamera(self.model, self.camera)

    def orbit(self, dx: float, dy: float) -> None:
        self.camera.azimuth += float(dx) * 0.35
        self.camera.elevation = max(-89.0, min(45.0, self.camera.elevation + float(dy) * 0.25))

    def pan(self, dx: float, dy: float) -> None:
        scale = max(0.0005, float(self.camera.distance) * 0.0015)
        self.camera.lookat[0] -= float(dx) * scale
        self.camera.lookat[2] += float(dy) * scale

    def zoom(self, delta: float) -> None:
        factor = 1.0 - float(delta) * 0.001
        self.camera.distance = max(0.35, min(12.0, self.camera.distance * factor))

    def state_vectors(self) -> tuple[Any, Any, Any]:
        return self.data.qpos, self.data.qvel, self.data.ctrl

    def restore_frame(self, frame: Any) -> None:
        _copy_vector(self.data.qpos, frame.qpos)
        _copy_vector(self.data.qvel, frame.qvel)
        _copy_vector(self.data.ctrl, frame.ctrl)
        self.data.time = frame.time
        self.mujoco.mj_forward(self.model, self.data)

    def render(self, width: int, height: int) -> np.ndarray:
        if self.safe_mode:
            return _safe_frame(width, height)
        framebuffer = self.model.vis.global_
        width = min(int(width), int(framebuffer.offwidth))
        height = min(int(height), int(framebuffer.offheight))
        if self.renderer is None or self.renderer.width != width or self.renderer.height != height:
            if self.renderer is not None:
                close_mujoco_renderer(self.renderer)
            self.renderer = create_mujoco_renderer(
                self.mujoco,
                self.model,
                height=height,
                width=width,
            )
        self.renderer.update_scene(self.data, camera=self.camera)
        self.add_semantic_overlays(self.renderer.scene)
        return np.asarray(self.renderer.render()).copy()

    def add_semantic_overlays(self, scene: Any) -> None:
        del scene

    def close_renderer(self) -> None:
        if self.renderer is not None:
            close_mujoco_renderer(self.renderer)
            self.renderer = None


def add_sphere(
    mujoco: Any,
    scene: Any,
    position: Sequence[float],
    *,
    radius: float,
    rgba: Sequence[float],
) -> bool:
    return _add_geom(
        mujoco,
        scene,
        mujoco.mjtGeom.mjGEOM_SPHERE,
        position,
        [radius, radius, radius],
        rgba,
    )


def add_box(
    mujoco: Any,
    scene: Any,
    position: Sequence[float],
    *,
    half_size: Sequence[float],
    rgba: Sequence[float],
    rotation: Sequence[float] | None = None,
) -> bool:
    return _add_geom(
        mujoco,
        scene,
        mujoco.mjtGeom.mjGEOM_BOX,
        position,
        half_size,
        rgba,
        rotation=rotation,
    )


def add_arrow(
    mujoco: Any,
    scene: Any,
    start: Sequence[float],
    end: Sequence[float],
    *,
    width: float,
    rgba: Sequence[float],
) -> bool:
    geom = _next_geom(scene)
    if geom is None:
        return False
    mujoco.mjv_connector(
        geom,
        mujoco.mjtGeom.mjGEOM_ARROW,
        float(width),
        np.asarray(start, dtype=float),
        np.asarray(end, dtype=float),
    )
    geom.rgba[:] = np.asarray(rgba, dtype=float)
    scene.ngeom += 1
    return True


def add_segment(
    mujoco: Any,
    scene: Any,
    start: Sequence[float],
    end: Sequence[float],
    *,
    width: float,
    rgba: Sequence[float],
) -> bool:
    """Add a plain capsule segment for dynamic mechanisms and trails."""

    geom = _next_geom(scene)
    if geom is None:
        return False
    mujoco.mjv_connector(
        geom,
        mujoco.mjtGeom.mjGEOM_CAPSULE,
        float(width),
        np.asarray(start, dtype=float),
        np.asarray(end, dtype=float),
    )
    geom.rgba[:] = np.asarray(rgba, dtype=float)
    scene.ngeom += 1
    return True


def add_dashed_segment(
    mujoco: Any,
    scene: Any,
    start: Sequence[float],
    end: Sequence[float],
    *,
    width: float,
    rgba: Sequence[float],
    segments: int = 9,
) -> None:
    first = np.asarray(start, dtype=float)
    last = np.asarray(end, dtype=float)
    count = max(3, int(segments))
    for index in range(0, count, 2):
        low = first + (last - first) * (index / count)
        high = first + (last - first) * (min(count, index + 1) / count)
        add_segment(mujoco, scene, low, high, width=width, rgba=rgba)


def add_circle(
    mujoco: Any,
    scene: Any,
    center: Sequence[float],
    *,
    radius: float,
    width: float,
    rgba: Sequence[float],
    segments: int = 36,
    axes: tuple[Sequence[float], Sequence[float]] = ((1, 0, 0), (0, 1, 0)),
) -> None:
    origin = np.asarray(center, dtype=float)
    first_axis = np.asarray(axes[0], dtype=float)
    second_axis = np.asarray(axes[1], dtype=float)
    points = [
        origin
        + float(radius)
        * (np.cos(2.0 * np.pi * index / segments) * first_axis
           + np.sin(2.0 * np.pi * index / segments) * second_axis)
        for index in range(segments)
    ]
    for start, end in zip(points, points[1:] + points[:1]):
        add_segment(mujoco, scene, start, end, width=width, rgba=rgba)


def add_digit_marker(
    mujoco: Any,
    scene: Any,
    center: Sequence[float],
    digit: int,
    *,
    scale: float = 0.045,
    rgba: Sequence[float] = (0.96, 0.97, 0.98, 0.98),
) -> None:
    x, y, z = (float(value) for value in center)
    strokes = (
        [
            ((-0.25, 0.65), (0.05, 1.0)),
            ((0.05, 1.0), (0.05, -1.0)),
            ((-0.35, -1.0), (0.45, -1.0)),
        ]
        if digit == 1
        else [
            ((-0.7, 0.8), (0.0, 1.0)),
            ((0.0, 1.0), (0.7, 0.7)),
            ((0.7, 0.7), (-0.7, -0.8)),
            ((-0.7, -0.8), (0.7, -0.8)),
        ]
    )
    for start, end in strokes:
        add_segment(
            mujoco,
            scene,
            [x + scale * start[0], y + scale * start[1], z],
            [x + scale * end[0], y + scale * end[1], z],
            width=0.009,
            rgba=rgba,
        )


def add_wall_grid(
    mujoco: Any,
    scene: Any,
    x: float,
    *,
    y_extent: float,
    z_min: float,
    z_max: float,
    rgba: Sequence[float],
) -> None:
    for y in np.linspace(-y_extent, y_extent, 9):
        add_segment(
            mujoco,
            scene,
            [x, float(y), z_min],
            [x, float(y), z_max],
            width=0.0035,
            rgba=rgba,
        )
    for z in np.linspace(z_min, z_max, 8):
        add_segment(
            mujoco,
            scene,
            [x, -y_extent, float(z)],
            [x, y_extent, float(z)],
            width=0.0035,
            rgba=rgba,
        )


def spring_polyline(
    start: Sequence[float],
    end: Sequence[float],
    *,
    coils: int = 8,
    amplitude: float = 0.075,
) -> tuple[tuple[float, float, float], ...]:
    """Return a visibly deforming zig-zag between an anchor and a moving mass."""

    first = np.asarray(start, dtype=float)
    last = np.asarray(end, dtype=float)
    points = [first]
    count = max(2, int(coils) * 2)
    for index in range(1, count):
        point = first + (last - first) * (index / count)
        point[2] += amplitude if index % 2 else -amplitude
        points.append(point)
    points.append(last)
    return tuple(tuple(float(value) for value in point) for point in points)


def _add_geom(
    mujoco: Any,
    scene: Any,
    geom_type: Any,
    position: Sequence[float],
    size: Sequence[float],
    rgba: Sequence[float],
    *,
    rotation: Sequence[float] | None = None,
) -> bool:
    geom = _next_geom(scene)
    if geom is None:
        return False
    matrix = np.eye(3, dtype=float).reshape(-1)
    if rotation is not None:
        matrix = np.asarray(rotation, dtype=float).reshape(-1)
    mujoco.mjv_initGeom(
        geom,
        geom_type,
        np.asarray(size, dtype=float),
        np.asarray(position, dtype=float),
        matrix,
        np.asarray(rgba, dtype=float),
    )
    category = getattr(getattr(mujoco, "mjtCatBit", None), "mjCAT_DECOR", None)
    if category is not None:
        geom.category = category
    scene.ngeom += 1
    return True


def _next_geom(scene: Any) -> Any | None:
    index = int(scene.ngeom)
    return None if index >= len(scene.geoms) else scene.geoms[index]


def _copy_vector(target: Any, source: Any) -> None:
    count = min(len(target), len(source))
    target[:count] = source[:count]
    if len(target) > count:
        target[count:] = 0.0


def _safe_frame(width: int, height: int) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, :] = (17, 24, 39)
    frame[height // 2 - 1 : height // 2 + 1, :, :] = (55, 65, 81)
    frame[:, width // 2 - 1 : width // 2 + 1, :] = (55, 65, 81)
    return frame
