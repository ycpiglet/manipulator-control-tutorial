"""Small lifecycle boundary for replacing Qt-owned simulation sessions."""

from __future__ import annotations

from typing import Any

from mclab.application.session import SessionState


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
