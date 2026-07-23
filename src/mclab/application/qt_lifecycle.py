"""Small lifecycle boundary for replacing Qt-owned simulation sessions."""

from __future__ import annotations

from typing import Any

from mclab.application.session import SessionState


def create_shutdown_event_filter(QObject: Any, QEvent: Any) -> type:
    """Create an application-level veto for quit paths that bypass window close."""

    class ShutdownEventFilter(QObject):
        def __init__(self, backend: Any, parent: Any = None) -> None:
            super().__init__(parent)
            self.backend = backend

        def eventFilter(self, _watched: Any, event: Any) -> bool:  # noqa: N802
            if event.type() != QEvent.Type.Quit:
                return False
            try:
                return not bool(self.backend.shutdown())
            except BaseException:
                return True

    return ShutdownEventFilter


def has_active_experiment(owner: Any) -> bool:
    """Return whether the persistent worker still owns unfinished session work."""

    worker = owner.worker
    return bool(
        owner.session is not None
        and worker is not None
        and worker.isRunning()
        and worker.busy
    )


def pause_before_navigation(owner: Any, target: str) -> None:
    """Freeze live/replay time before the learner leaves the experiment page."""

    session = owner.session
    if (
        owner._page == "experiment"  # noqa: SLF001
        and target != "experiment"
        and session is not None
        and session.state in {SessionState.RUNNING, SessionState.REPLAYING}
    ):
        owner._submit_session(session.pause)  # noqa: SLF001


def stop_active_experiment(owner: Any) -> None:
    """End an active session while preserving the evidence recorded so far."""

    session = owner.session
    if session is None or not has_active_experiment(owner):
        return
    if session.state in {
        SessionState.READY,
        SessionState.RUNNING,
        SessionState.PAUSED,
        SessionState.REPLAYING,
    }:
        owner._submit_session(session.stop)  # noqa: SLF001


def defer_start_for_parked_session(owner: Any, scenario: str) -> bool:
    """Stop a paused/idle session and remember the scenario to start once it ends.

    A completed-but-restarted (or paused replay) session keeps the worker busy
    forever, which used to dead-end every "start next" entry point. Instead of
    rejecting the launch, end the parked session (evidence is preserved by
    stop_active_experiment) and let the idle handler start the requested one.
    """

    if not has_active_experiment(owner) or owner.session is None:
        return False
    if owner.session.state not in {
        SessionState.READY,
        SessionState.PAUSED,
        SessionState.REPLAYING,
    }:
        return False
    owner._pending_next_scenario = scenario  # noqa: SLF001
    stop_active_experiment(owner)
    worker = owner.worker
    if worker is None or not worker.busy:
        owner._on_worker_finished()  # noqa: SLF001
    return True


def consume_pending_next_scenario(owner: Any) -> bool:
    """Start the deferred next scenario once the worker has gone idle."""

    pending = getattr(owner, "_pending_next_scenario", None)
    if pending is None or owner._shutting_down:  # noqa: SLF001
        return False
    worker = owner.worker
    if worker is not None and worker.busy:
        return False
    owner._pending_next_scenario = None  # noqa: SLF001
    owner.startScenario(pending)
    return True


def reject_running_experiment(owner: Any) -> bool:
    """Reject a second launch while the current worker still owns a session."""

    worker = owner.worker
    if worker is None or not worker.isRunning() or not getattr(worker, "busy", True):
        return False
    owner._set_error(  # noqa: SLF001
        "An experiment is already running.",
        "Return to the active experiment, or end and save it before starting another.",
    )
    return True


def reject_running_batch(owner: Any) -> bool:
    """Reject work that would compete with the course-comparison process."""

    batch = getattr(owner, "_batch", None)
    if batch is None or not batch.running:
        return False
    owner._set_error(  # noqa: SLF001
        "The course comparison is already running.",
        "Use Cancel comparison or wait for the five sets to finish.",
    )
    return True


def shutdown_application(owner: Any, wait_ms: int) -> bool:
    """Stop owned process trees and workers before allowing the window to close."""

    if getattr(owner, "_shutdown_complete", False):
        return True
    if owner._shutting_down:  # noqa: SLF001
        return False
    owner._shutting_down = True  # noqa: SLF001
    try:
        batch_stopped = owner._shutdown_batch()  # noqa: SLF001
    except BaseException as exc:
        return _shutdown_rejected(
            owner,
            str(exc) or "The course comparison shutdown failed.",
            _batch_recovery_action(owner),
        )
    if not batch_stopped:
        return _shutdown_rejected(
            owner,
            "The course comparison process tree could not be stopped safely.",
            _batch_recovery_action(owner),
        )
    try:
        owner._pending_restart = None  # noqa: SLF001
        owner._pending_next_scenario = None  # noqa: SLF001
        if owner.session is not None:
            owner.session.stop()
        if owner.worker is not None and owner.worker.isRunning():
            owner.worker.request_shutdown()
            if not owner.worker.wait(wait_ms):
                return _shutdown_rejected(
                    owner,
                    "The renderer worker could not be stopped safely.",
                    "Wait for it to stop, then close the application again.",
                )
        if owner.session is not None:
            owner.session.close()
    except BaseException as exc:
        return _shutdown_rejected(
            owner,
            str(exc) or "Application-owned resources could not be stopped safely.",
            "Wait for them to stop, then close the application again.",
        )
    owner._shutdown_complete = True  # noqa: SLF001
    return True


def _shutdown_rejected(owner: Any, detail: str, action: str) -> bool:
    """Return a retryable veto even when user-facing error reporting fails."""

    owner._shutting_down = False  # noqa: SLF001
    try:
        owner._set_error(detail, action)  # noqa: SLF001
    except BaseException:
        pass
    return False


def _batch_recovery_action(owner: Any) -> str:
    try:
        return str(owner.translator.text("path.batch_recovery"))
    except BaseException:
        return "Wait for the comparison to stop, then close the application again."


def replace_session(owner: Any, replacement: Any, adapter: Any) -> None:
    """Close the previous session before publishing its replacement."""

    previous = owner.session
    worker = getattr(owner, "worker", None)
    worker_owns_previous = (
        worker is not None
        and worker.isRunning()
        and getattr(worker, "session", None) is previous
    )
    try:
        if previous is not None and previous is not replacement and not worker_owns_previous:
            previous.close()
    except Exception:
        replacement.close()
        raise
    owner.session = replacement
    owner.adapter = adapter
