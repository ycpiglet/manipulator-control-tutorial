"""Persistent Qt simulation worker with thread-affine renderer cleanup."""

from __future__ import annotations

from queue import Empty, Queue
from typing import Any

from mclab.application.rendering import (
    adopt_adapter_render_resources,
    close_retained_render_resources,
    destroy_thread_mujoco_context,
    release_thread_mujoco_context,
    retain_adapter_render_resources,
)
from mclab.application.session import SessionState
from mclab.application.worker_commands import CommandQueue


def create_session_worker(qthread: Any, signal: Any) -> Any:
    """Create the worker class without importing Qt in headless installations."""

    class SessionWorker(qthread):
        state_event = signal(str)
        telemetry_event = signal("QVariantMap")
        frame_event = signal(object)
        completed_event = signal(str)
        idle_event = signal()
        error_event = signal(str)

        def __init__(
            self,
            session: Any,
            *,
            adapter: Any,
            replay: Any | None = None,
            initial_action: tuple[str, Any] | None = None,
            start_paused_step: bool = False,
            start_paused: bool = False,
        ) -> None:
            super().__init__()
            self.session = session
            self.adapter = adapter
            self.replay = replay
            self.initial_action = initial_action
            self.start_paused_step = start_paused_step
            self.start_paused = start_paused
            self.commands = CommandQueue(self._emit_command_error)
            self._jobs: Queue[tuple[Any, Any, Any, Any, bool, bool] | None] = Queue()
            self._busy = True
            self._shutdown_requested = False
            self._retained_render_resources = None
            self._bind_callbacks()

        @property
        def busy(self) -> bool:
            return self._busy

        def replace_with(self, replacement: Any) -> None:
            """Queue a replacement on this worker's renderer-owning thread."""

            self._busy = True
            self._jobs.put(replacement._job())  # noqa: SLF001

        def request_shutdown(self) -> None:
            self._shutdown_requested = True
            self._jobs.put(None)

        def run(self) -> None:
            job = self._job()
            try:
                while job is not None and not self._shutdown_requested:
                    self._activate(job)
                    self._run_current(initialize=True)
                    self._become_idle()
                    job = self._wait_for_job()
                    if job is not None:
                        self.session.close()
            finally:
                try:
                    self.session.close()
                except Exception as exc:
                    self._emit_command_error(exc)
                try:
                    close_retained_render_resources(self._retained_render_resources)
                except Exception as exc:
                    self._emit_command_error(exc)
                try:
                    destroy_thread_mujoco_context()
                except Exception as exc:
                    self._emit_command_error(exc)

        def submit(self, command: Any) -> None:
            self.commands.submit(command)

        def _job(self) -> tuple[Any, Any, Any, Any, bool, bool]:
            return (
                self.session,
                self.adapter,
                self.replay,
                self.initial_action,
                self.start_paused_step,
                self.start_paused,
            )

        def _activate(self, job: tuple[Any, Any, Any, Any, bool, bool]) -> None:
            (
                self.session,
                self.adapter,
                self.replay,
                self.initial_action,
                self.start_paused_step,
                self.start_paused,
            ) = job
            resources = self._retained_render_resources
            if resources is not None:
                if not adopt_adapter_render_resources(resources, self.adapter):
                    close_retained_render_resources(resources)
                self._retained_render_resources = None
            self._bind_callbacks()

        def _bind_callbacks(self) -> None:
            self.session.on_state = lambda state: self.state_event.emit(state.value)
            self.session.on_telemetry = lambda values: self.telemetry_event.emit(values)
            self.session.on_frame = lambda frame: self.frame_event.emit(frame)

        def _run_current(self, *, initialize: bool) -> None:
            try:
                if initialize and self.replay is not None:
                    self.session.begin_replay(self.replay)
                elif initialize:
                    self.session.start()
                    if self.start_paused:
                        self.session.pause()
                        self.session.render_current()
                    if self.initial_action is not None:
                        self.session.apply_action(*self.initial_action)
                    if self.start_paused_step:
                        if self.session.state != SessionState.PAUSED:
                            self.session.pause()
                        self.session.advance_live()
                status = self.session.run_blocking(realtime=True, command_pump=self.commands.drain)
                output = ""
                if self.replay is None:
                    # MuJoCo 3.10 EGL can crash on the next context when
                    # Matplotlib report work runs while the old one is current.
                    self._retained_render_resources = retain_adapter_render_resources(
                        self.adapter
                    )
                    self.session.close()
                    if self._retained_render_resources is not None:
                        release_thread_mujoco_context()
                    if hasattr(self.adapter, "finalize"):
                        output = str(
                            self.adapter.finalize(
                                self.session.recorder,
                                status=(
                                    "stopped"
                                    if self.session.interrupted
                                    else "completed"
                                    if status == SessionState.COMPLETED
                                    else status.value
                                ),
                            )
                        )
                self.completed_event.emit(output)
            except Exception as exc:
                self.session.fail(exc)
                self.session.close()
                self._emit_command_error(exc)

        def _become_idle(self) -> None:
            self._busy = False
            self.idle_event.emit()

        def _wait_for_job(self) -> tuple[Any, Any, Any, Any, bool] | None:
            while not self._shutdown_requested:
                try:
                    return self._jobs.get(timeout=0.01)
                except Empty:
                    self.commands.drain()
                    if self.session.state in {
                        SessionState.RUNNING,
                        SessionState.REPLAYING,
                        SessionState.PAUSED,
                    }:
                        self._busy = True
                        self._run_current(initialize=False)
                        self._become_idle()
            return None

        def _emit_command_error(self, exc: Exception) -> None:
            self.error_event.emit(f"{exc.__class__.__name__}: {exc}")

    return SessionWorker
