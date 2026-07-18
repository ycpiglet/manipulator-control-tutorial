"""Deterministic simulation and replay session state machine."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .artifacts import ReplayArchive, ReplayFrame, ReplayRecorder


class SessionState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    REPLAYING = "replaying"
    COMPLETED = "completed"
    ERROR = "error"


@runtime_checkable
class LabAdapter(Protocol):
    """Small lab boundary consumed by SimulationSession."""

    @property
    def time(self) -> float: ...

    @property
    def timestep(self) -> float: ...

    def prepare(self) -> None: ...

    def step(self) -> Mapping[str, float]: ...

    def reset(self) -> None: ...

    def apply_action(self, name: str, value: Any = None) -> None: ...

    def state_vectors(self) -> tuple[Any, Any, Any]: ...

    def restore_frame(self, frame: ReplayFrame) -> None: ...

    def render(self, width: int, height: int) -> Any: ...

    def close(self) -> None: ...


StateCallback = Callable[[SessionState], None]
TelemetryCallback = Callable[[dict[str, float]], None]
FrameCallback = Callable[[Any], None]


class SimulationSession:
    """Own physics lifecycle, controls, replay, cleanup, and state changes."""

    SPEEDS = (0.25, 0.5, 1.0, 2.0)
    VIEW_ACTIONS = frozenset({"orbit", "pan", "zoom", "reset_camera"})
    MARKER_MERGE_SECONDS = 0.2

    def __init__(
        self,
        adapter: LabAdapter,
        *,
        duration: float,
        replay_hz: float = 60.0,
        render_hz: float = 30.0,
        status_hz: float = 10.0,
        on_state: StateCallback | None = None,
        on_telemetry: TelemetryCallback | None = None,
        on_frame: FrameCallback | None = None,
    ) -> None:
        if duration <= 0:
            raise ValueError("Simulation duration must be positive.")
        self.adapter = adapter
        self.duration = float(duration)
        self.render_hz = float(render_hz)
        self.status_hz = float(status_hz)
        self.on_state = on_state
        self.on_telemetry = on_telemetry
        self.on_frame = on_frame
        self.recorder = ReplayRecorder(replay_hz)
        self._state = SessionState.READY
        self._speed = 1.0
        self._prepared = False
        self._closed = False
        self._stop_requested = False
        self._interrupted = False
        self._replay: ReplayArchive | None = None
        self._replay_index = 0
        self._replay_loop: tuple[int, int] | None = None
        self._error: Exception | None = None
        self._lock = threading.RLock()
        self._last_render_time = -float("inf")
        self._last_status_time = -float("inf")

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def replay_index(self) -> int:
        return self._replay_index

    @property
    def replay_frame_count(self) -> int:
        return self._replay.frame_count if self._replay else 0

    @property
    def replay_time(self) -> float:
        if self._replay is None or self._replay.frame_count == 0:
            return 0.0
        return float(self._replay.time[self._replay_index] - self._replay.time[0])

    @property
    def replay_event_positions(self) -> tuple[float, ...]:
        return tuple(float(marker["position"]) for marker in self.replay_event_markers)

    @property
    def replay_event_markers(self) -> tuple[dict[str, Any], ...]:
        archive = self._replay
        if archive is None or archive.duration <= 0.0:
            return ()
        start = float(archive.time[0])
        return tuple(
            {
                "position": max(
                    0.0,
                    min(
                        1.0,
                        (float(group["end_time"]) - start) / archive.duration,
                    ),
                ),
                "time": min(
                    archive.duration,
                    max(0.0, float(group["end_time"]) - start),
                ),
                "name": group["name"],
                "kind": group["kind"],
                "count": group["count"],
            }
            for group in self._grouped_replay_events()
        )

    def _grouped_replay_events(self) -> list[dict[str, Any]]:
        archive = self._replay
        if archive is None or archive.frame_count == 0:
            return []
        groups: list[dict[str, Any]] = []
        default_time = float(archive.time[0])
        for event in archive.events:
            name = str(event.get("name", "event"))
            if name in self.VIEW_ACTIONS:
                continue
            kind = str(event.get("kind", "event"))
            event_time = float(event.get("time", default_time))
            previous = groups[-1] if groups else None
            gap = event_time - float(previous["end_time"]) if previous else float("inf")
            if (
                previous is not None
                and previous["name"] == name
                and previous["kind"] == kind
                and 0.0 <= gap <= self.MARKER_MERGE_SECONDS
            ):
                previous["end_time"] = event_time
                previous["count"] += 1
            else:
                groups.append(
                    {
                        "name": name,
                        "kind": kind,
                        "start_time": event_time,
                        "end_time": event_time,
                        "count": 1,
                    }
                )
        return groups

    @property
    def replay_archive(self) -> ReplayArchive | None:
        return self._replay

    @property
    def interrupted(self) -> bool:
        return self._interrupted

    def start(self) -> None:
        with self._lock:
            self._ensure_open()
            if self._state not in {SessionState.READY, SessionState.PAUSED}:
                raise RuntimeError(f"Cannot start from {self._state.value}.")
            if not self._prepared:
                self.adapter.prepare()
                self._prepared = True
                self._record_current_state({})
            self._stop_requested = False
            self._interrupted = False
            self._set_state(SessionState.RUNNING)

    def pause(self) -> None:
        with self._lock:
            if self._state not in {SessionState.RUNNING, SessionState.REPLAYING}:
                return
            self._set_state(SessionState.PAUSED)

    def resume(self) -> None:
        with self._lock:
            if self._state != SessionState.PAUSED:
                raise RuntimeError(f"Cannot resume from {self._state.value}.")
            state = SessionState.REPLAYING if self._replay is not None else SessionState.RUNNING
            self._set_state(state)

    def step_once(self) -> dict[str, float]:
        with self._lock:
            self._ensure_open()
            if self._state == SessionState.READY:
                self.start()
                self.pause()
            if self._state != SessionState.PAUSED:
                raise RuntimeError("Step once requires a ready or paused session.")
            if self._replay is not None:
                self._advance_replay(1)
                return self._replay.frame(self._replay_index).semantic
            return self._physics_tick(force_callbacks=True)

    def advance_live(self, seconds: float = 0.1) -> dict[str, float]:
        """Advance live physics by a visible time interval and remain paused."""

        with self._lock:
            self._ensure_open()
            interval = float(seconds)
            if interval <= 0.0:
                raise ValueError("Live advance interval must be positive.")
            if self._replay is not None:
                raise RuntimeError("Use next frame while replaying a recording.")
            if self._state == SessionState.READY:
                self.start()
                self.pause()
            elif self._state == SessionState.RUNNING:
                self.pause()
            if self._state != SessionState.PAUSED:
                raise RuntimeError("Live advance requires a ready, running, or paused session.")
            tick_count = max(1, round(interval / self.adapter.timestep))
            telemetry: dict[str, float] = {}
            for index in range(tick_count):
                telemetry = self._physics_tick(force_callbacks=index == tick_count - 1)
                if self._state == SessionState.COMPLETED:
                    break
            return telemetry

    def tick(self) -> dict[str, float]:
        with self._lock:
            if self._state == SessionState.RUNNING:
                return self._physics_tick()
            if self._state == SessionState.REPLAYING:
                self._advance_replay(1)
                if self._replay is None:
                    return {}
                return self._replay.frame(self._replay_index).semantic
            return {}

    def run_blocking(
        self,
        *,
        realtime: bool = True,
        command_pump: Callable[[], None] | None = None,
    ) -> SessionState:
        if self._state == SessionState.READY:
            self.start()
        try:
            while self._state in {
                SessionState.RUNNING,
                SessionState.REPLAYING,
                SessionState.PAUSED,
            }:
                start = time.perf_counter()
                if command_pump is not None:
                    command_pump()
                if self._stop_requested:
                    self._set_state(SessionState.COMPLETED)
                    break
                if self._state != SessionState.PAUSED:
                    self.tick()
                if realtime and self._state in {
                    SessionState.RUNNING,
                    SessionState.REPLAYING,
                }:
                    elapsed = time.perf_counter() - start
                    interval = self._pacing_interval() / self._speed
                    if elapsed < interval:
                        time.sleep(interval - elapsed)
                elif self._state == SessionState.PAUSED:
                    time.sleep(0.01)
        except Exception as exc:
            self.fail(exc)
        return self._state

    def reset(self) -> None:
        with self._lock:
            self._ensure_open()
            self.adapter.reset()
            self.recorder.clear()
            self._clear_adapter_events()
            self._replay = None
            self._replay_index = 0
            self._replay_loop = None
            self._error = None
            self._interrupted = False
            self._last_render_time = -float("inf")
            self._last_status_time = -float("inf")
            self._record_current_state({})
            self._set_state(SessionState.READY)

    def restart(self, *, paused: bool = False) -> None:
        """Reset a live experiment and continue it in the same worker."""

        with self._lock:
            self._ensure_open()
            if self._replay is not None:
                raise RuntimeError("Use the replay timeline to return to the first frame.")
            self.adapter.reset()
            self.recorder.clear()
            self._clear_adapter_events()
            self._error = None
            self._interrupted = False
            self._stop_requested = False
            self._last_render_time = -float("inf")
            self._last_status_time = -float("inf")
            self._record_current_state({})
            self._set_state(SessionState.PAUSED if paused else SessionState.RUNNING)

    def render_current(self) -> None:
        """Publish the prepared state without consuming one physics step."""

        with self._lock:
            self._ensure_open()
            if not self._prepared:
                raise RuntimeError("Start the session before rendering its current state.")
            if self.on_frame:
                self.on_frame(self.adapter.render(1200, 540))
            self._last_render_time = float(self.adapter.time)

    def stop(self) -> None:
        with self._lock:
            self._interrupted = True
            self._stop_requested = True
            if self._state in {SessionState.READY, SessionState.PAUSED}:
                self._set_state(SessionState.COMPLETED)

    def set_speed(self, speed: float) -> None:
        value = float(speed)
        if value not in self.SPEEDS:
            raise ValueError(f"Speed must be one of {self.SPEEDS}.")
        self._speed = value

    def apply_action(self, name: str, value: Any = None) -> None:
        with self._lock:
            if name in self.VIEW_ACTIONS:
                self.adapter.apply_action(name, value)
                if self._prepared and self.on_frame:
                    self.on_frame(self.adapter.render(1200, 540))
                    self._last_render_time = float(self.adapter.time)
                return
            if self._state in {SessionState.COMPLETED, SessionState.ERROR, SessionState.REPLAYING}:
                raise RuntimeError(f"Cannot apply an action while {self._state.value}.")
            self.adapter.apply_action(name, value)
            self.recorder.event(time=self.adapter.time, kind="learner", name=name, value=value)

    def record_evidence(
        self,
        kind: str,
        name: str,
        value: Any,
        *,
        label: str = "",
    ) -> None:
        """Persist learner evidence in both run artifacts and the replay timeline."""

        with self._lock:
            self._ensure_open()
            if self._replay is not None or self._state not in {
                SessionState.READY,
                SessionState.RUNNING,
                SessionState.PAUSED,
            }:
                raise RuntimeError(f"Cannot save evidence while {self._state.value}.")
            timestamp = float(self.adapter.time)
            events = getattr(self.adapter, "events", None)
            if hasattr(events, "set_time") and hasattr(events, "record"):
                events.set_time(timestamp)
                events.record(kind, name, value, label=label)
            elif isinstance(events, list):
                events.append(
                    {
                        "time": timestamp,
                        "kind": str(kind),
                        "name": str(name),
                        "label": str(label or name),
                        "value": value,
                    }
                )
            self.recorder.event(time=timestamp, kind=kind, name=name, value=value)

    def begin_replay(self, archive: ReplayArchive | None = None) -> None:
        with self._lock:
            self._ensure_open()
            if not self._prepared:
                self.adapter.prepare()
                self._prepared = True
            self._replay = archive or self.recorder.archive()
            if self._replay.frame_count == 0:
                raise ValueError("The recording has no replay frames.")
            self._replay_index = 0
            self._replay_loop = None
            self.adapter.restore_frame(self._replay.frame(0))
            self._set_state(SessionState.REPLAYING)
            self._emit_replay_callbacks()

    def seek_replay(self, index: int) -> None:
        with self._lock:
            if self._replay is None:
                raise RuntimeError("No replay is loaded.")
            self._replay_index = max(0, min(int(index), self._replay.frame_count - 1))
            self.adapter.restore_frame(self._replay.frame(self._replay_index))
            self._set_state(SessionState.PAUSED)
            self._emit_replay_callbacks()

    def restart_replay(self) -> None:
        """Replay the loaded archive again without recomputing physics."""

        with self._lock:
            if self._replay is None or self._replay.frame_count == 0:
                raise RuntimeError("No replay is loaded.")
            self._replay_index = 0
            self.adapter.restore_frame(self._replay.frame(0))
            self._stop_requested = False
            self._set_state(SessionState.REPLAYING)
            self._emit_replay_callbacks()

    def set_replay_loop(self, start: float, end: float, *, enabled: bool) -> None:
        """Set an inclusive replay loop using normalized timeline positions."""

        with self._lock:
            if not enabled:
                self._replay_loop = None
                return
            if self._replay is None or self._replay.frame_count < 2:
                raise RuntimeError("No replay is loaded.")
            low = max(0.0, min(1.0, float(start)))
            high = max(low, min(1.0, float(end)))
            last = self._replay.frame_count - 1
            first_index = min(last - 1, round(low * last))
            last_index = max(first_index + 1, round(high * last))
            self._replay_loop = (first_index, min(last, last_index))

    def fail(self, error: Exception) -> None:
        with self._lock:
            self._error = error
            self._set_state(SessionState.ERROR)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.adapter.close()
            finally:
                self._stop_requested = True

    def _physics_tick(self, *, force_callbacks: bool = False) -> dict[str, float]:
        telemetry = dict(self.adapter.step())
        timestamp = self.adapter.time
        self._record_current_state(telemetry)
        status_due = timestamp - self._last_status_time >= 1.0 / self.status_hz
        render_due = timestamp - self._last_render_time >= 1.0 / self.render_hz
        if self.on_telemetry and (force_callbacks or status_due):
            self.on_telemetry(telemetry)
            self._last_status_time = timestamp
        if self.on_frame and (force_callbacks or render_due):
            self.on_frame(self.adapter.render(1200, 540))
            self._last_render_time = timestamp
        if timestamp >= self.duration:
            self._set_state(SessionState.COMPLETED)
        return telemetry

    def _record_current_state(self, telemetry: Mapping[str, float]) -> None:
        qpos, qvel, ctrl = self.adapter.state_vectors()
        self.recorder.record(
            time=self.adapter.time,
            qpos=qpos,
            qvel=qvel,
            ctrl=ctrl,
            semantic={key: float(value) for key, value in telemetry.items()},
        )

    def _clear_adapter_events(self) -> None:
        events = getattr(self.adapter, "events", None)
        if hasattr(events, "clear"):
            events.clear()

    def _advance_replay(self, delta: int) -> None:
        if self._replay is None:
            raise RuntimeError("No replay is loaded.")
        next_index = self._replay_index + delta
        if self._replay_loop is not None and delta > 0:
            loop_start, loop_end = self._replay_loop
            if next_index > loop_end:
                next_index = loop_start
        if next_index >= self._replay.frame_count:
            self._replay_index = self._replay.frame_count - 1
            self.adapter.restore_frame(self._replay.frame(self._replay_index))
            self._emit_replay_callbacks()
            self._set_state(SessionState.COMPLETED)
            return
        self._replay_index = max(0, next_index)
        self.adapter.restore_frame(self._replay.frame(self._replay_index))
        self._emit_replay_callbacks()

    def _emit_replay_callbacks(self) -> None:
        if self._replay is None:
            return
        frame = self._replay.frame(self._replay_index)
        if self.on_telemetry:
            self.on_telemetry(frame.semantic)
        if self.on_frame:
            self.on_frame(self.adapter.render(960, 540))

    def _pacing_interval(self) -> float:
        if self._replay is None or self._replay.frame_count < 2:
            return self.adapter.timestep
        index = max(1, self._replay_index)
        interval = float(self._replay.time[index] - self._replay.time[index - 1])
        return interval if interval > 0.0 else 1.0 / 60.0

    def _set_state(self, state: SessionState) -> None:
        if self._state == state:
            return
        self._state = state
        if self.on_state:
            self.on_state(state)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Simulation session is closed.")

    def __enter__(self) -> "SimulationSession":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
