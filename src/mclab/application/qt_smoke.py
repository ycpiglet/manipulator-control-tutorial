"""Optional runtime probes used by packaged Qt smoke tests."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mclab.application.qt_batch_probe import BATCH_PROBE_ACTIONS, schedule_batch_lifecycle_probe
from mclab.application.qt_smoke_input import (
    activate_object as _activate_object,
    type_into as _type_into,
)


def schedule_smoke_action(timer: Any, backend: Any, roots: list[Any] | None = None) -> None:
    """Configure a deterministic window and schedule a small beta-task sequence."""

    # These hooks can drive controls and mutate saved evidence. They must never
    # be enabled in a normal learner process merely by inheriting environment
    # variables from a shell or launcher.
    if os.environ.get("MCLAB_SELF_TEST") != "1":
        return

    width = int(os.environ.get("MCLAB_WINDOW_WIDTH", "0"))
    height = int(os.environ.get("MCLAB_WINDOW_HEIGHT", "0"))
    if roots and (width > 0 or height > 0):
        def apply_window_size() -> None:
            root = roots[0]
            current_width = root.width() if callable(root.width) else root.width
            current_height = root.height() if callable(root.height) else root.height
            needs_resize = (width > 0 and current_width != width) or (
                height > 0 and current_height != height
            )
            show_normal = getattr(root, "showNormal", None)
            if needs_resize and callable(show_normal):
                show_normal()
            if width > 0 and current_width != width:
                root.setWidth(width)
            if height > 0 and current_height != height:
                root.setHeight(height)
            raise_window = getattr(root, "raise_", None)
            if callable(raise_window):
                raise_window()
            request_activate = getattr(root, "requestActivate", None)
            if callable(request_activate):
                request_activate()

        apply_window_size()
        # Window managers may apply the QML startup geometry after the first
        # event-loop turn. Reassert the audit viewport before captures/actions.
        for resize_delay in (100, 500, 1000):
            timer.singleShot(resize_delay, apply_window_size)
    actions = [
        item.strip()
        for item in os.environ.get("MCLAB_SMOKE_ACTION", "").split(",")
        if item.strip()
    ]
    delay_ms = max(0, int(os.environ.get("MCLAB_SMOKE_ACTION_MS", "1000")))
    interval_ms = max(50, int(os.environ.get("MCLAB_SMOKE_ACTION_INTERVAL_MS", "250")))
    root = roots[0] if roots else None
    selected_batch_probes = [item for item in actions if item in BATCH_PROBE_ACTIONS]
    if selected_batch_probes:
        if len(actions) != 1 or len(selected_batch_probes) != 1:
            raise RuntimeError("A batch lifecycle probe must be the only smoke action.")
        schedule_batch_lifecycle_probe(
            timer,
            backend,
            root,
            selected_batch_probes[0],
            delay_ms,
        )
        return
    if actions:
        def run_sequence(index: int) -> None:
            _run_action(backend, actions[index], root)
            if index + 1 < len(actions):
                timer.singleShot(interval_ms, lambda: run_sequence(index + 1))

        # Chain actions so text-entry event processing cannot re-enter the next
        # beta step when a busy CI host fires several absolute timers at once.
        timer.singleShot(delay_ms, lambda: run_sequence(0))


def _run_action(backend: Any, action: str, root: Any = None) -> None:
    if action == "press_enter" and root is not None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        QTest.keyClick(root, Qt.Key.Key_Return)
    elif action.startswith("key_") and root is not None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        keys = {
            "key_tab": Qt.Key.Key_Tab,
            "key_backtab": Qt.Key.Key_Backtab,
            "key_enter": Qt.Key.Key_Return,
            "key_space": Qt.Key.Key_Space,
            "key_left": Qt.Key.Key_Left,
            "key_right": Qt.Key.Key_Right,
            "key_up": Qt.Key.Key_Up,
            "key_down": Qt.Key.Key_Down,
            "key_escape": Qt.Key.Key_Escape,
            "key_plus": Qt.Key.Key_Plus,
            "key_minus": Qt.Key.Key_Minus,
            "key_zero": Qt.Key.Key_0,
            "key_shift_up": Qt.Key.Key_Up,
        }
        modifier = (
            Qt.KeyboardModifier.ShiftModifier
            if action.startswith("key_shift_")
            else Qt.KeyboardModifier.NoModifier
        )
        QTest.keyClick(root, keys[action], modifier)
        _record_focus(action)
    elif action == "record_focus":
        _record_focus(action)
    elif action == "record_backend":
        _record_backend(backend, root)
    elif action == "focus_experiment" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "experimentPage")
        focused = page is not None and QMetaObject.invokeMethod(
            page, "focusExperiment", Qt.ConnectionType.DirectConnection
        )
        if not focused:
            raise RuntimeError("Experiment focus target was not found.")
    elif action == "focus_tour_skip" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "homePage")
        focused = page is not None and QMetaObject.invokeMethod(
            page, "focusTourSkip", Qt.ConnectionType.DirectConnection
        )
        if not focused:
            raise RuntimeError("First-run tour skip control was not found.")
        _record_focus(action)
    elif action == "focus_tour_again" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "homePage")
        focused = page is not None and QMetaObject.invokeMethod(
            page, "focusTourAgain", Qt.ConnectionType.DirectConnection
        )
        if not focused:
            raise RuntimeError("Show tour again control was not found.")
        _record_focus(action)
    elif action == "focus_scenario_search" and root is not None:
        _focus_object(root, "scenarioSearch", "Scenario search")
        _record_focus(action)
    elif action == "focus_explore_clear" and root is not None:
        _focus_object(root, "clearExploreFilters", "Explore filter reset")
        _record_focus(action)
    elif action == "focus_reset_camera" and root is not None:
        _focus_object(root, "sceneCameraReset", "Scene camera reset")
    elif action == "focus_advanced_toggle" and root is not None:
        _focus_object(root, "advancedToggle", "Advanced settings")
    elif action == "focus_scene" and root is not None:
        _focus_object(root, "sceneCameraArea", "Scene camera area")
    elif action == "hover_scene" and root is not None:
        _hover_object(root, "sceneCameraArea", "Scene camera area")
    elif action == "hover_reset_camera" and root is not None:
        _hover_object(root, "sceneCameraReset", "Scene camera reset")
    elif action == "orbit_scene" and root is not None:
        _drag_object(root, "sceneCameraArea", "Scene camera area", pan=False)
    elif action == "pan_scene" and root is not None:
        _drag_object(root, "sceneCameraArea", "Scene camera area", pan=True)
    elif action == "zoom_scene" and root is not None:
        _wheel_object(root, "sceneCameraArea", "Scene camera area")
    elif action == "focus_result_primary" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "resultsPage")
        focused = page is not None and QMetaObject.invokeMethod(
            page, "focusFirstPrimary", Qt.ConnectionType.DirectConnection
        )
        if not focused:
            raise RuntimeError("Result primary action control was not found.")
        _record_focus(action)
    elif action == "focus_results_load_more" and root is not None:
        _focus_object(root, "loadMoreResultsButton", "Results load-more action")
        _record_focus(action)
    elif action == "explore_filter_hands_on" and root is not None:
        _set_object_property(root, "scenarioModeFilter", "currentIndex", 1)
    elif action == "explore_filter_build" and root is not None:
        _set_object_property(root, "scenarioLevelFilter", "currentIndex", 2)
    elif action == "explore_search_none" and root is not None:
        _set_object_property(root, "scenarioSearch", "text", "zzzz-no-scenario")
    elif action == "type_explore_lab04_wall" and root is not None:
        _type_into(root, "scenarioSearch", "lab04 wall")
        _record_focus(action)
    elif action == "type_prediction" and root is not None:
        _type_into(root, "predictionInput", "More damping will reduce oscillation.")
        _record_focus(action)
    elif action == "type_prediction_limit" and root is not None:
        prediction = (
            "More damping should reduce every oscillation, lower each peak, and help "
            "the mass settle closer to equilibrium while I compare position, velocity, "
            "and force with this prediction before starting the experiment. "
        )
        _type_into(root, "predictionInput", (prediction * 2)[:240])
        _record_focus(action)
    elif action == "type_prediction_limit_ko" and root is not None:
        prediction = (
            "감쇠를 높이면 진동의 각 봉우리가 작아지고 질량 블록이 평형점에 더 빨리 "
            "가까워질 것이다. 실험을 시작하기 전에 이 예측을 위치, 속도, 힘의 변화와 "
            "비교해서 어떤 근거가 예상과 일치하는지 확인하겠다. "
        )
        value = (prediction * 3)[:240]
        if value[-1].isspace():
            value = value[:-1] + "끝"
        _type_into(root, "predictionInput", value)
        _record_focus(action)
    elif action == "prediction_cursor_end" and root is not None:
        from PySide6.QtCore import QObject

        prediction = root.findChild(QObject, "predictionInput")
        if prediction is None:
            raise RuntimeError("Prediction input was not found.")
        prediction.setProperty("cursorPosition", len(str(prediction.property("text"))))
        prediction.setProperty("focus", True)
    elif action == "prediction_cursor_start" and root is not None:
        from PySide6.QtCore import QObject

        prediction = root.findChild(QObject, "predictionInput")
        if prediction is None:
            raise RuntimeError("Prediction input was not found.")
        prediction.setProperty("cursorPosition", 0)
        prediction.setProperty("focus", True)
    elif action == "type_observation" and root is not None:
        _type_into(root, "observationInput", "The peaks became smaller after the change.")
        _record_focus(action)
    elif action == "type_observation_limit" and root is not None:
        observation = (
            "The first peak became smaller after the damping change, the later peaks "
            "decayed sooner, and the mass settled closer to equilibrium while the "
            "position, velocity, and force traces stayed consistent with my prediction. "
        )
        value = (observation * 2)[:300]
        if value[-1].isspace():
            value = value[:-1] + "x"
        _type_into(root, "observationInput", value)
        _record_focus(action)
    elif action == "type_observation_limit_ko" and root is not None:
        observation = (
            "감쇠 값을 바꾼 뒤 첫 번째 봉우리가 작아졌고 이후 진동도 더 빨리 줄었다. "
            "질량 블록은 평형점 가까이에서 안정되었으며 위치, 속도, 힘의 변화가 내가 "
            "기록한 예측과 어떤 부분에서 일치하고 달랐는지 확인했다. "
        )
        value = (observation * 4)[:300]
        if value[-1].isspace():
            value = value[:-1] + "끝"
        _type_into(root, "observationInput", value)
        _record_focus(action)
    elif action in {"observation_cursor_end", "observation_cursor_start"} and root is not None:
        from PySide6.QtCore import QObject

        observation = root.findChild(QObject, "observationInput")
        if observation is None:
            raise RuntimeError("Observation input was not found.")
        position = (
            len(str(observation.property("text")))
            if action == "observation_cursor_end"
            else 0
        )
        observation.setProperty("cursorPosition", position)
        observation.setProperty("focus", True)
    elif action == "select_outcome_matched" and root is not None:
        _set_object_property(root, "outcomeSelector", "currentIndex", 1)
    elif action == "save_prediction":
        backend.savePrediction("More damping will reduce oscillation.")
    elif action == "save_observation_matched":
        backend.saveObservation("The peaks became smaller after the change.", "Matched")
    elif action == "remember_session":
        if os.environ.get("MCLAB_SELF_TEST") != "1":
            raise RuntimeError("Session tracking is available only during MCLAB_SELF_TEST.")
        backend._smoke_previous_session = backend.session  # noqa: SLF001
    elif action == "speed_0_5" and root is not None:
        from PySide6.QtCore import QObject

        control = root.findChild(QObject, "playbackSpeedSelector")
        if control is None:
            raise RuntimeError("Playback speed selector was not found.")
        control.setProperty("currentIndex", 1)
        backend.setSpeed(0.5)
    elif action == "finish_session":
        if backend.session is None:
            raise RuntimeError("No session is available to finish.")
        backend.session.stop()
    elif action == "wait_worker":
        worker = backend.worker
        deadline = time.monotonic() + 10.0
        if worker is not None:
            from PySide6.QtCore import QCoreApplication

            while worker.busy and time.monotonic() < deadline:
                QCoreApplication.processEvents()
                time.sleep(0.01)
            if worker.busy:
                raise RuntimeError("The simulation worker did not become idle within 10 seconds.")
    elif action == "wait_session_completed":
        if backend.session is None:
            raise RuntimeError("No session is available to complete.")
        from PySide6.QtCore import QCoreApplication

        deadline = time.monotonic() + 12.0
        while backend.session.state.value not in {"completed", "error"}:
            if time.monotonic() >= deadline:
                raise RuntimeError("The simulation did not complete within 12 seconds.")
            QCoreApplication.processEvents()
            time.sleep(0.01)
        if backend.session.state.value == "error":
            raise RuntimeError("The simulation entered the error state before completion.")
    elif action == "wait_restart":
        previous = getattr(backend, "_smoke_previous_session", None)
        if previous is None:
            raise RuntimeError("Remember the previous session before waiting for a restart.")
        from PySide6.QtCore import QCoreApplication

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            session = backend.session
            if (
                session is not None
                and session is not previous
                and session.state.value == "paused"
                and float(session.adapter.time) == 0.0
            ):
                break
            QCoreApplication.processEvents()
            time.sleep(0.01)
        else:
            raise RuntimeError("A paused zero-time replacement did not appear within 10 seconds.")
    elif action == "pause":
        backend.togglePause()
    elif action == "step":
        backend.stepOnce()
    elif action == "reset_experiment":
        backend.resetExperiment()
    elif action == "return_experiment":
        backend.returnToActiveExperiment()
    elif action == "stop_active":
        backend.stopActiveExperiment()
    elif action == "start_next":
        backend.startCourseNext()
    elif action == "skip_tour":
        backend.dismissTour()
    elif action.startswith("language_"):
        backend.setLanguage(action.removeprefix("language_"))
    elif action.startswith("navigate_"):
        backend.navigate(action.removeprefix("navigate_"))
    elif action.startswith("control_") and "=" in action:
        name, raw_value = action.removeprefix("control_").split("=", 1)
        backend.applyControl(name, float(raw_value))
    elif action == "accessibility_snapshot" and root is not None:
        _write_accessibility_snapshot(root)
    elif action == "inject_missing_next_asset":
        _inject_missing_next_asset(backend)
    elif action == "inject_batch_running":
        _inject_batch_running(backend)
    elif action == "inject_batch_cancelling":
        _inject_batch_running(backend)
        backend._batch.cancel_requested = True  # noqa: SLF001
        backend.batch_changed.emit()
    elif action == "inject_batch_start_probe":
        if os.environ.get("MCLAB_SELF_TEST") != "1":
            raise RuntimeError("Batch launch probing is available only during MCLAB_SELF_TEST.")
        controller = backend._batch  # noqa: SLF001
        controller._smoke_start_called = False  # noqa: SLF001

        def record_start() -> str:
            controller._smoke_start_called = True  # noqa: SLF001
            return ""

        controller.start = record_start
    elif action == "start_all_compare":
        backend.startAllCompare()
    elif action == "inject_live_completed":
        if os.environ.get("MCLAB_SELF_TEST") != "1":
            raise RuntimeError("Completion injection is available only during MCLAB_SELF_TEST.")
        backend._state = "completed"  # noqa: SLF001
        backend.state_changed.emit()
    elif action == "delete_active_batch":
        active = Path(backend._batch.output)  # noqa: SLF001
        backend.deleteRun(str(active), active.name, "")
    elif action == "startup_probe":
        _write_startup_probe()
    elif action == "replay_fixture":
        backend.replayRun(os.environ["MCLAB_FIXTURE_RUN_PATH"])
    elif action == "replay_last_output":
        if not backend._last_output:  # noqa: SLF001
            raise RuntimeError("The completed run output is not available for replay.")
        backend.replayRun(backend._last_output)  # noqa: SLF001
    elif action == "rerun_fixture":
        backend.rerunSavedRun(os.environ["MCLAB_FIXTURE_RUN_PATH"], False)
    elif action == "restart_replay_trace":
        if os.environ.get("MCLAB_SELF_TEST") != "1":
            raise RuntimeError("Replay tracing is available only during MCLAB_SELF_TEST.")
        from PySide6.QtCore import QTimer

        backend._submit_session(backend.session.restart_replay)  # noqa: SLF001
        QTimer.singleShot(100, lambda: _record_backend(backend, root))
    elif action == "first_frame":
        backend.firstFrame()
    elif action == "previous_frame":
        backend.previousFrame()
    elif action == "next_frame":
        backend.nextFrame()
    elif action == "last_frame":
        backend.lastFrame()
    elif action == "seek_50":
        backend.seekProgress(0.5)
    elif action == "toggle_loop" and root is not None:
        from PySide6.QtCore import QObject

        control = root.findChild(QObject, "replayLoopToggle")
        if control is None:
            raise RuntimeError("Replay loop toggle was not found.")
        control.setProperty("checked", not bool(control.property("checked")))
    elif action == "open_result_manager" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "resultsPage")
        opened = page is not None and QMetaObject.invokeMethod(
            page, "openFirstManager", Qt.ConnectionType.DirectConnection
        )
        if not opened:
            raise RuntimeError("Saved run manager was not found.")
    elif action == "begin_result_quarantine" and root is not None:
        _activate_object(root, "beginQuarantineButton", "Saved-run quarantine action")
    elif action == "type_wrong_result_confirmation" and root is not None:
        _type_into(root, "deleteConfirmationInput", "wrong-name")
        _record_focus(action)
    elif action == "type_result_confirmation" and root is not None:
        from mclab.application.repositories import ArtifactRepository

        records = ArtifactRepository().list_runs()
        if not records:
            raise RuntimeError("Managed saved run was not found.")
        _type_into(root, "deleteConfirmationInput", records[0].path.name)
        _record_focus(action)
    elif action == "confirm_result_quarantine" and root is not None:
        _activate_object(root, "confirmQuarantineButton", "Confirm quarantine action")
    elif action == "delete_managed_result" and root is not None:
        _activate_object(root, "beginQuarantineButton", "Saved-run quarantine action")
        from mclab.application.repositories import ArtifactRepository

        records = ArtifactRepository().list_runs()
        if not records:
            raise RuntimeError("Managed saved run was not found.")
        _type_into(root, "deleteConfirmationInput", records[0].path.name)
        _activate_object(root, "confirmQuarantineButton", "Confirm quarantine action")
    elif action == "probe_managed_result_backend_guard":
        from mclab.application.repositories import ArtifactRepository

        records = ArtifactRepository().list_runs()
        if not records:
            raise RuntimeError("Managed saved run was not found.")
        record = records[0]
        backend.deleteRun(str(record.path), record.path.name, record.cleanup_token)
    elif action == "load_more_results" and root is not None:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        page = root.findChild(QObject, "resultsPage")
        loaded = page is not None and QMetaObject.invokeMethod(
            page, "loadMoreResults", Qt.ConnectionType.DirectConnection
        )
        if not loaded:
            raise RuntimeError("More saved runs could not be shown.")
    elif action.startswith("activate_event_"):
        index = int(action.removeprefix("activate_event_"))
        backend.seekEvent(index)
    else:
        backend.applyAction(action)


def _write_accessibility_snapshot(root: Any) -> None:
    """Write the live Qt accessibility tree for deterministic beta-task audits."""

    from PySide6.QtGui import QAccessible

    destination = os.environ.get("MCLAB_ACCESSIBILITY_PATH", "")
    if not destination:
        raise RuntimeError("MCLAB_ACCESSIBILITY_PATH is required for accessibility_snapshot.")
    interface = QAccessible.queryAccessibleInterface(root)
    if interface is None or not interface.isValid():
        raise RuntimeError("The application window has no valid accessibility interface.")
    items: list[dict[str, Any]] = []

    def visit(node: Any, depth: int) -> None:
        if node is None or not node.isValid() or depth > 40 or len(items) >= 5000:
            return
        state = node.state()
        rect = node.rect()
        accessible_object = node.object()
        items.append(
            {
                "depth": depth,
                "role": node.role().name,
                "name": node.text(QAccessible.Text.Name),
                "objectClass": (
                    accessible_object.metaObject().className()
                    if accessible_object is not None
                    else ""
                ),
                "objectName": (
                    accessible_object.objectName() if accessible_object is not None else ""
                ),
                "description": node.text(QAccessible.Text.Description),
                "value": node.text(QAccessible.Text.Value),
                "focusable": bool(state.focusable),
                "focused": bool(state.focused),
                "disabled": bool(state.disabled),
                "invisible": bool(state.invisible),
                "checked": bool(state.checked),
                "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
            }
        )
        for index in range(node.childCount()):
            visit(node.child(index), depth + 1)

    visit(interface, 0)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def _focus_object(root: Any, object_name: str, label: str) -> None:
    from PySide6.QtCore import QObject

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"{label} control was not found.")
    control.forceActiveFocus()


def _hover_object(root: Any, object_name: str, label: str) -> None:
    from PySide6.QtCore import QPoint, QPointF, QObject
    from PySide6.QtTest import QTest

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"{label} control was not found.")
    center = control.mapToScene(
        QPointF(float(control.property("width")) / 2, float(control.property("height")) / 2)
    )
    QTest.mouseMove(root, QPoint(round(center.x()), round(center.y())))


def _drag_object(root: Any, object_name: str, label: str, *, pan: bool) -> None:
    from PySide6.QtCore import QPoint, QPointF, QObject, Qt
    from PySide6.QtTest import QTest

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"{label} control was not found.")
    center = control.mapToScene(
        QPointF(float(control.property("width")) / 2, float(control.property("height")) / 2)
    )
    start = QPoint(round(center.x()), round(center.y()))
    end = start + QPoint(48, 24)
    button = Qt.MouseButton.RightButton if pan else Qt.MouseButton.LeftButton
    QTest.mousePress(root, button, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(root, end, 80)
    QTest.mouseRelease(root, button, Qt.KeyboardModifier.NoModifier, end)


def _wheel_object(root: Any, object_name: str, label: str) -> None:
    from PySide6.QtCore import QPoint, QPointF, QObject
    from PySide6.QtTest import QTest

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"{label} control was not found.")
    center = control.mapToScene(
        QPointF(float(control.property("width")) / 2, float(control.property("height")) / 2)
    )
    QTest.wheelEvent(root, center, QPoint(0, 120))


def _set_object_property(root: Any, object_name: str, name: str, value: Any) -> None:
    from PySide6.QtCore import QObject

    control = root.findChild(QObject, object_name)
    if control is None:
        raise RuntimeError(f"QML control was not found: {object_name}")
    if not control.setProperty(name, value):
        raise RuntimeError(f"Could not set {object_name}.{name}")


def _record_focus(action: str) -> None:
    """Append the accessible focus target reached after one smoke action."""

    from PySide6.QtGui import QAccessible, QGuiApplication

    destination = os.environ.get("MCLAB_FOCUS_TRACE_PATH", "")
    if not destination:
        return
    target = QGuiApplication.focusObject()
    interface = None
    while target is not None:
        candidate = QAccessible.queryAccessibleInterface(target)
        if candidate is not None and candidate.isValid():
            name = candidate.text(QAccessible.Text.Name).strip()
            if name or candidate.role().name in {"Button", "Slider", "CheckBox", "ComboBox"}:
                interface = candidate
                break
        target = target.parent()
    window = QGuiApplication.focusWindow()
    window_rect = (
        [window.x(), window.y(), window.width(), window.height()]
        if window is not None
        else [0, 0, 0, 0]
    )
    item: dict[str, Any] = {
        "action": action,
        "role": "",
        "name": "",
        "rect": [0, 0, 0, 0],
        "window_rect": window_rect,
    }
    if interface is not None:
        rect = interface.rect()
        item.update(
            {
                "role": interface.role().name,
                "name": interface.text(QAccessible.Text.Name),
                "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
            }
        )
    path = Path(destination)
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        trace = []
    trace.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_backend(backend: Any, root: Any) -> None:
    """Append paired UI/backend transport state for transition audits."""

    destination = os.environ.get("MCLAB_BACKEND_TRACE_PATH", "")
    if not destination:
        return
    from PySide6.QtCore import QObject

    from mclab.application.qt_smoke_metrics import evidence_text_metrics

    control = root.findChild(QObject, "playbackSpeedSelector") if root is not None else None
    now_prompt = root.findChild(QObject, "nowPrompt") if root is not None else None
    experiment = root.findChild(QObject, "experimentPage") if root is not None else None

    session = backend.session
    previous = getattr(backend, "_smoke_previous_session", None)
    previous_adapter = previous.adapter if previous is not None else None
    adapter = session.adapter if session is not None else None
    camera = getattr(adapter, "camera", None)
    trace_item = {
        "backend_state": str(getattr(backend, "_state", "")),
        "page": str(getattr(backend, "_page", "")),
        "session_state": session.state.value if session is not None else "",
        "session_speed": session.speed if session is not None else None,
        "session_time": float(session.adapter.time) if session is not None else None,
        "session_id": id(session) if session is not None else None,
        "replay_frames": session.replay_frame_count if session is not None else 0,
        "replay_index": session.replay_index if session is not None else 0,
        "ui_speed_index": int(control.property("currentIndex")) if control is not None else None,
        "ui_speed_text": str(control.property("currentText")) if control is not None else "",
        "now_prompt": str(now_prompt.property("text")) if now_prompt is not None else "",
        "now_prompt_truncated": bool(now_prompt.property("truncated")) if now_prompt is not None else None,
        "now_prompt_line_count": int(now_prompt.property("lineCount")) if now_prompt is not None else None,
        "active_stage": int(experiment.property("activeStage")) if experiment is not None else None,
        "prediction_saved_length": len(str(backend.predictionText)),
        "observation_saved_length": len(
            str(getattr(backend, "_observation", {}).get("note", ""))
        ),
        "has_prediction": bool(backend.hasPrediction),
        "has_learner_action": bool(backend.hasLearnerAction),
        "has_observation": bool(backend.hasObservation),
        "learner_action_count": int(backend.learnerActionCount),
        "worker_busy": bool(backend.worker is not None and backend.worker.busy),
        "has_active_experiment": bool(backend.hasActiveExperiment),
        "batch_probe_started": bool(
            getattr(getattr(backend, "_batch", None), "_smoke_start_called", False)
        ),
        "previous_session_closed": getattr(previous, "_closed", None),
        "previous_session_id": id(previous) if previous is not None else None,
        "previous_adapter_closed": getattr(previous_adapter, "_closed", None),
        "rss_kb": _process_rss_kb(),
        "camera_azimuth": float(camera.azimuth) if camera is not None else None,
        "camera_elevation": float(camera.elevation) if camera is not None else None,
        "camera_distance": float(camera.distance) if camera is not None else None,
        "camera_lookat": [float(value) for value in camera.lookat] if camera is not None else None,
    }
    trace_item.update(evidence_text_metrics(root, "prediction", QObject))
    trace_item.update(evidence_text_metrics(root, "observation", QObject))
    path = Path(destination)
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        trace = []
    trace.append(trace_item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


def _process_rss_kb() -> int | None:
    """Return Linux resident memory for hostile lifecycle audits."""

    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _inject_missing_next_asset(backend: Any) -> None:
    """Inject a missing next-scenario model only during packaged/UI self-tests."""

    if os.environ.get("MCLAB_SELF_TEST") != "1":
        raise RuntimeError("Readiness injection is available only during MCLAB_SELF_TEST.")
    from dataclasses import replace

    from mclab.application.catalog import ScenarioCatalog
    from mclab.application.readiness import app_readiness

    next_id = backend.nextScenarioId
    scenarios = []
    for scenario in backend.catalog.all():
        if scenario.id == next_id:
            scenario = replace(
                scenario,
                config_data={
                    **scenario.config,
                    "model_path": "third_party/mujoco_menagerie/injected-model.xml",
                },
            )
        scenarios.append(scenario)
    backend.catalog = ScenarioCatalog(tuple(scenarios))
    backend._setup_issues = app_readiness(backend.catalog)  # noqa: SLF001
    backend.results_changed.emit()
    backend.language_changed.emit()


def _inject_batch_running(backend: Any) -> None:
    if os.environ.get("MCLAB_SELF_TEST") != "1":
        raise RuntimeError("Batch-state injection is available only during MCLAB_SELF_TEST.")
    from PySide6.QtCore import QProcess

    class SmokeProcess:
        def __init__(self) -> None:
            self.active = True

        def state(self) -> Any:
            return QProcess.Running if self.active else QProcess.NotRunning

        def terminate(self) -> None:
            self.active = False

        def waitForFinished(self, _milliseconds: int) -> bool:  # noqa: N802
            return True

        def kill(self) -> None:
            self.active = False

    from mclab.application.batch_runs import ALL_COMPARE_ID
    from mclab.application.repositories import ArtifactRepository

    active = next(
        (
            record
            for record in ArtifactRepository().list_runs()
            if record.scenario_id == ALL_COMPARE_ID and record.status == "running"
        ),
        None,
    )
    backend._batch._smoke_inject_active(  # noqa: SLF001
        SmokeProcess(),
        str(active.path) if active is not None else "",
    )
    backend.batch_changed.emit()
    backend.results_changed.emit()


def _write_startup_probe() -> None:
    destination = os.environ.get("MCLAB_STARTUP_PATH", "")
    started = int(os.environ.get("MCLAB_STARTUP_BEGIN_NS", "0"))
    if not destination or started <= 0:
        raise RuntimeError("Startup probe path and monotonic start time are required.")
    elapsed_ms = (time.monotonic_ns() - started) / 1_000_000.0
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text(json.dumps({"startup_ms": elapsed_ms}, indent=2), encoding="utf-8")
