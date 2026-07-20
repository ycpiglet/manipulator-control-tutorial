"""Lazy-loaded PySide6/Qt Quick desktop application."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mclab.application.adapters import replay_adapter_from_manifest
from mclab.application.artifacts import ReplayArchive, legacy_replay_reason
from mclab.application.catalog import ScenarioCatalog, ScenarioDefinition
from mclab.application.error_messages import localized_error, self_test_qt_errors
from mclab.application.fonts import FONT_ROOT, application_font_files
from mclab.application.i18n import TRANSLATIONS, Translator, normalize_language
from mclab.application.launcher import create_scenario_adapter
from mclab.application.platform import PlatformServices
from mclab.application.qt_batch import create_batch_backend_mixin, create_batch_controller
from mclab.application.qt_evidence import create_evidence_backend_mixin
from mclab.application.qt_fonts import configure_font_environment
from mclab.application.qt_frame import create_frame_provider
from mclab.application.qt_lifecycle import (
    consume_pending_next_scenario,
    defer_start_for_parked_session,
    has_active_experiment,
    pause_before_navigation,
    reject_running_batch,
    reject_running_experiment,
    replace_session,
    stop_active_experiment,
)
from mclab.application.qt_worker import create_session_worker
from mclab.application.presentation import (
    course_progress_payload,
    result_payloads,
    scenario_payload,
    telemetry_items,
)
from mclab.application.readiness import (
    app_readiness,
    readiness_payload,
    scenario_readiness,
    scenario_readiness_payload,
)
from mclab.application.repositories import ArtifactRepository
from mclab.application.rendering import can_reuse_adapter_render_resources
from mclab.application.saved_runs import resolve_saved_run_launch
from mclab.application.session import SessionState, SimulationSession
from mclab.application.single_instance import acquire_instance_lock, start_activation_server
from mclab.application.qt_smoke import schedule_smoke_action


SHUTDOWN_WAIT_MS = 30_000


def run_app(
    *,
    language: str | None = None,
    scenario_id: str | None = None,
    safe_mode: bool = False,
    replay_dir: str | Path | None = None,
) -> int:
    """Run the integrated app, importing Qt only after the CLI chooses it."""

    # The bundle intentionally ships one predictable, accessible Controls
    # style instead of every platform style from the Qt distribution.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    try:
        from PySide6.QtCore import (
            Property,
            QObject,
            QProcess,
            QSettings,
            QThread,
            QTimer,
            QUrl,
            Signal,
            Slot,
            qInstallMessageHandler,
        )
        from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickImageProvider
    except Exception as exc:
        translator = Translator(language)
        print(f"{translator.text('error.qt_missing')}\n{translator.text('error.qt_fix')}")
        print(f"Details: {exc.__class__.__name__}: {exc}")
        return 2

    FrameProvider = create_frame_provider(QQuickImageProvider, QImage)
    SessionWorker = create_session_worker(QThread, Signal)

    BatchController = create_batch_controller(QObject, QProcess, QTimer, Signal)
    BatchBackend = create_batch_backend_mixin(QObject, Property, Signal, Slot)
    EvidenceBackend = create_evidence_backend_mixin(BatchBackend, Property, Signal, Slot)

    class AppBackend(EvidenceBackend):
        language_changed = Signal()
        page_changed = Signal()
        selected_changed = Signal()
        state_changed = Signal()
        telemetry_changed = Signal()
        frame_changed = Signal()
        results_changed = Signal()
        error_changed = Signal()
        tour_changed = Signal()

        def __init__(self, provider: FrameProvider) -> None:
            super().__init__()
            self.provider = provider
            self.catalog = ScenarioCatalog.default()
            self._setup_issues = app_readiness(self.catalog)
            self.platform = PlatformServices()
            self.settings = QSettings("MCLab", "MCLab")
            stored = str(self.settings.value("language", "")) or None
            self._language = normalize_language(language or stored)
            self.translator = Translator(self._language)
            self._page = "home"
            self._selected: ScenarioDefinition | None = None
            self._active_config: dict[str, Any] = {}
            self._state = SessionState.READY.value
            self._speed = 1.0
            self._telemetry: dict[str, float] = {"playback_speed": self._speed}
            self._revision = 0
            self._error = self._error_detail = self._error_action = ""
            self.worker: SessionWorker | None = None
            self.session: SimulationSession | None = None
            self.adapter: Any | None = None
            self._last_output = ""
            self._safe_mode = safe_mode
            self._tour_visible = not bool(self.settings.value("tourComplete", False, type=bool))
            self._pending_restart: tuple[str | None, Any, bool] | None = None
            self._pending_next_scenario: str | None = None
            self._replay_mode = False
            self._shutting_down = False
            self._init_batch(BatchController(self))
            self._init_evidence()

        @Property(str, notify=language_changed)
        def language(self) -> str:
            return self._language
        @Property(str, notify=page_changed)
        def page(self) -> str:
            return self._page
        @Property("QVariantList", notify=results_changed)
        def scenarios(self) -> list[dict[str, Any]]:
            return [self._scenario_map(item) for item in self.catalog.all()]

        @Property("QVariantMap", notify=results_changed)
        def courseProgress(self) -> dict[str, Any]:  # noqa: N802
            return course_progress_payload(
                self.catalog.learning_path(), self.translator, ArtifactRepository().list_runs(),
                batch_readiness=readiness_payload(self._setup_issues, self.translator),
            )

        @Property("QVariantMap", notify=language_changed)
        def setupStatus(self) -> dict[str, object]:  # noqa: N802
            return readiness_payload(self._setup_issues, self.translator)
        @Property(str, notify=results_changed)
        def nextScenarioId(self) -> str:  # noqa: N802
            return str(self.courseProgress["nextId"])
        @Property("QVariantMap", notify=selected_changed)
        def selectedScenario(self) -> dict[str, Any]:  # noqa: N802
            return self._scenario_map(self._selected) if self._selected else {}
        @Property(str, notify=state_changed)
        def sessionState(self) -> str:  # noqa: N802
            return self._state

        @Property(bool, notify=state_changed)
        def hasActiveExperiment(self) -> bool:  # noqa: N802
            return has_active_experiment(self)
        @Property("QVariantMap", notify=telemetry_changed)
        def telemetry(self) -> dict[str, float]:
            return self._telemetry
        @Property("QVariantList", notify=telemetry_changed)
        def telemetryItems(self) -> list[dict[str, str]]:  # noqa: N802
            config = self._active_config or (self._selected.config if self._selected else {})
            return telemetry_items(self._selected, config, self._telemetry, self.translator)

        @Property(str, notify=frame_changed)
        def frameSource(self) -> str:  # noqa: N802
            return f"image://mclab/frame?{self._revision}"
        @Property(bool, constant=True)
        def safeMode(self) -> bool:  # noqa: N802
            return self._safe_mode

        @Property(float, notify=telemetry_changed)
        def sessionProgress(self) -> float:  # noqa: N802
            if self.session is None:
                return 0.0
            if self.session.replay_frame_count > 1:
                return self.session.replay_index / (self.session.replay_frame_count - 1)
            duration = float(self._selected.config.get("sim_time", 1.0)) if self._selected else 1.0
            return max(0.0, min(1.0, float(self._telemetry.get("time", 0.0)) / duration))

        @Property(bool, notify=state_changed)
        def hasReplay(self) -> bool:  # noqa: N802
            return self._replay_mode or (
                self.session is not None and self.session.replay_frame_count > 0
            )

        @Property("QVariantList", notify=state_changed)
        def eventMarkers(self) -> list[dict[str, Any]]:  # noqa: N802
            return list(self.session.replay_event_markers) if self.session is not None else []

        @Property(str, notify=telemetry_changed)
        def replayPosition(self) -> str:  # noqa: N802
            if self.session is None or self.session.replay_frame_count == 0:
                return ""
            return (
                f"{self.translator.text('transport.frame')} "
                f"{self.session.replay_index + 1} / {self.session.replay_frame_count}"
                f" · {self.session.replay_time:.2f} s"
            )

        @Property("QVariantList", notify=results_changed)
        def results(self) -> list[dict[str, Any]]:
            records = ArtifactRepository().list_runs(validate_replays=True)
            active = self._batch.output if self._batch.running else None
            return result_payloads(records, self.translator, self.catalog, active)

        @Property(str, notify=error_changed)
        def errorMessage(self) -> str:  # noqa: N802
            return self._error

        @Property(str, notify=error_changed)
        def errorDetail(self) -> str:  # noqa: N802
            return self._error_detail

        @Property(str, notify=error_changed)
        def errorAction(self) -> str:  # noqa: N802
            return self._error_action

        @Property(bool, notify=tour_changed)
        def tourVisible(self) -> bool:  # noqa: N802
            return self._tour_visible

        @Slot(str, result=str)
        def text(self, key: str) -> str:
            return self.translator.text(key)

        @Slot(str, str, result=str)
        def localizedText(self, _language: str, key: str) -> str:  # noqa: N802
            """Translate while making the QML language dependency explicit."""
            return self.translator.text(key)

        @Slot(str)
        def setLanguage(self, value: str) -> None:  # noqa: N802
            try:
                normalized = normalize_language(value)
            except ValueError as exc:
                self._set_error(str(exc), "Choose ko or en.")
                return
            if normalized == self._language:
                return
            self._language = normalized
            self.translator = Translator(normalized)
            self.settings.setValue("language", normalized)
            self.language_changed.emit()
            self.batch_changed.emit()
            self.selected_changed.emit()
            self.telemetry_changed.emit()
            self.results_changed.emit()

        @Slot(str)
        def navigate(self, page: str) -> None:
            if page not in {"home", "path", "explore", "results", "experiment"}:
                return
            pause_before_navigation(self, page)
            self._page = page
            self.page_changed.emit()
            if page == "results":
                self.results_changed.emit()

        @Slot()
        def returnToActiveExperiment(self) -> None:  # noqa: N802
            if self.hasActiveExperiment:
                self.navigate("experiment")

        @Slot()
        def stopActiveExperiment(self) -> None:  # noqa: N802
            stop_active_experiment(self)

        @Slot()
        def dismissTour(self) -> None:  # noqa: N802
            self._tour_visible = False
            self.settings.setValue("tourComplete", True)
            self.tour_changed.emit()

        @Slot()
        def showTour(self) -> None:  # noqa: N802
            self._tour_visible = True
            self.tour_changed.emit()

        @Slot(str)
        def selectScenario(self, scenario: str) -> None:  # noqa: N802
            try:
                self._selected = self.catalog.get(scenario)
            except KeyError as exc:
                self._set_error(str(exc), "Open Explore and choose an available scenario.")
                return
            self._active_config = {}
            self.selected_changed.emit()

        @Slot(str)
        def startScenario(self, scenario: str) -> None:  # noqa: N802
            if reject_running_batch(self):
                return
            if defer_start_for_parked_session(self, scenario):
                return
            if reject_running_experiment(self):
                return
            self.selectScenario(scenario)
            if self._selected is None:
                return
            issue = scenario_readiness(self._selected)
            if issue is not None:
                blocked = scenario_readiness_payload(issue, self.translator)
                self._error = str(blocked["readinessDetail"])
                self._error_action = str(blocked["readinessAction"])
                self.error_changed.emit()
                return
            try:
                self._start_scenario(self._selected)
            except Exception as exc:
                self._set_error(
                    f"{exc.__class__.__name__}: {exc}",
                    "Run `python -m mclab doctor`, then retry in safe mode.",
                )

        @Slot(str, bool)
        def rerunSavedRun(self, run_path: str, tuned: bool) -> None:  # noqa: N802
            if reject_running_batch(self):
                return
            if reject_running_experiment(self):
                return
            try:
                launch = resolve_saved_run_launch(run_path, self.catalog, tuned=tuned)
                self._start_scenario(launch.scenario, config_override=launch.config)
            except Exception as exc:
                self._set_error(
                    f"{exc.__class__.__name__}: {exc}",
                    "Open another saved run or create a fresh run from Explore.",
                )

        @Slot(str)
        def replayRun(self, run_path: str) -> None:  # noqa: N802
            if reject_running_batch(self):
                return
            if reject_running_experiment(self):
                return
            path = Path(run_path)
            reason = legacy_replay_reason(path)
            if reason:
                self._set_error(reason, "Use Run again with same settings for this legacy result.")
                return
            try:
                archive = ReplayArchive.load(path / "replay.npz")
                manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
                resolved = manifest.get("config", {}).get("resolved")
                scenario = str(manifest.get("scenario_id", ""))
                try:
                    selected = self.catalog.get(scenario) if scenario else None
                except KeyError:
                    selected = None
                adapter = replay_adapter_from_manifest(path, safe_mode=self._safe_mode)
                session = SimulationSession(adapter, duration=max(archive.duration, 1.0 / 60.0))
                session.set_speed(self._speed)
                self._replay_mode = True
                replace_session(self, session, adapter)
                self._reset_evidence()
                self._active_config = dict(resolved) if isinstance(resolved, dict) else {}
                self._selected = selected
                self.selected_changed.emit()
                self.state_changed.emit()
                self._launch_worker(SessionWorker(session, adapter=adapter, replay=archive))
                self.navigate("experiment")
            except Exception as exc:
                self._replay_mode = False
                self.state_changed.emit()
                self._set_error(
                    f"{exc.__class__.__name__}: {exc}",
                    "Run the scenario again to create a fresh recording.",
                )
        @Slot()
        def togglePause(self) -> None:  # noqa: N802
            if self.session is None:
                return
            if self.waitingForPrediction:
                return
            try:
                if self.session.state == SessionState.COMPLETED and self.session.replay_archive is None:
                    self._request_new_live_run()
                    return
                if self.session.state == SessionState.COMPLETED and self.session.replay_frame_count > 0:
                    self._submit_session(self.session.restart_replay)
                elif self.session.state == SessionState.PAUSED:
                    self._submit_session(self.session.resume)
                else:
                    self._submit_session(self.session.pause)
            except Exception as exc:
                self._set_error(str(exc), "Restart the experiment.")

        @Slot()
        def stepOnce(self) -> None:  # noqa: N802
            if self.session is None:
                return
            if self.waitingForPrediction:
                return
            try:
                if self.session.state == SessionState.COMPLETED and self.session.replay_archive is None:
                    self._request_new_live_run(start_paused_step=True)
                    return
                if self.session.replay_archive is not None:
                    self._submit_session(self.session.step_once)
                else:
                    self._submit_session(self.session.advance_live)
            except Exception as exc:
                self._set_error(str(exc), "Pause and try the visible-time advance again.")

        @Slot()
        def resetExperiment(self) -> None:  # noqa: N802
            if self.session is None:
                return
            if self.waitingForPrediction:
                return
            try:
                if self.session.state == SessionState.COMPLETED and self.session.replay_archive is None:
                    self._request_new_live_run()
                    return
                if self.session.replay_archive is None:
                    self._reset_evidence()
                wait_for_prediction = self._requires_evidence()
                self._submit_session(
                    lambda: self.session.restart(paused=wait_for_prediction)
                )
            except Exception as exc:
                self._set_error(str(exc), "Close and reopen the scenario.")

        @Slot(float)
        def setSpeed(self, speed: float) -> None:  # noqa: N802
            if self.session is None:
                return
            value = float(speed)
            if value not in SimulationSession.SPEEDS:
                self._set_error(f"Invalid speed: {value}", "Choose 0.25×, 0.5×, 1×, or 2×.")
                return
            self._speed = value
            self._telemetry["playback_speed"] = value
            self.telemetry_changed.emit()
            self._submit_session(lambda: self.session.set_speed(value))

        @Slot(float)
        def seekProgress(self, progress: float) -> None:  # noqa: N802
            if self.session is None or self.session.replay_frame_count == 0:
                return
            index = round(max(0.0, min(1.0, progress)) * (self.session.replay_frame_count - 1))
            try:
                self._submit_session(lambda: self.session.seek_replay(index))
            except Exception as exc:
                self._set_error(str(exc), "Pause the recording and try the timeline again.")

        @Slot(int)
        def seekEvent(self, index: int) -> None:  # noqa: N802
            markers = self.eventMarkers
            if 0 <= index < len(markers):
                self.seekProgress(float(markers[index]["position"]))

        @Slot()
        def firstFrame(self) -> None:  # noqa: N802
            self._seek_relative(absolute=0)

        @Slot()
        def previousFrame(self) -> None:  # noqa: N802
            self._seek_relative(delta=-1)

        @Slot()
        def nextFrame(self) -> None:  # noqa: N802
            self._seek_relative(delta=1)

        @Slot()
        def lastFrame(self) -> None:  # noqa: N802
            if self.session is not None:
                self._seek_relative(absolute=self.session.replay_frame_count - 1)

        @Slot(float, float, bool)
        def setReplayLoop(self, start: float, end: float, enabled: bool) -> None:  # noqa: N802
            if self.session is None:
                return
            try:
                self._submit_session(lambda: self.session.set_replay_loop(start, end, enabled=enabled))
            except Exception as exc:
                self._set_error(str(exc), "Open a valid recording and select a longer range.")

        @Slot(str, "QVariant")
        def applyControl(self, name: str, value: Any) -> None:  # noqa: N802
            if self.session is None:
                return
            try:
                experiment_control = self._is_experiment_control(name)
                if self._requires_evidence() and experiment_control and not self.hasPrediction:
                    self._evidence_error("evidence.prediction_first")
                    return
                if (
                    self._requires_evidence()
                    and experiment_control
                    and self.session.state == SessionState.COMPLETED
                ):
                    self._evidence_error("evidence.restart_first")
                    return
                if (
                    self.session.state == SessionState.COMPLETED
                    and self.session.replay_archive is None
                    and name not in SimulationSession.VIEW_ACTIONS
                ):
                    self._request_new_live_run(name, value)
                    return
                self._submit_session(lambda: self.session.apply_action(name, value))
                self._mark_learner_action(name)
            except Exception as exc:
                self._set_error(str(exc), "Return to the live experiment before changing controls.")

        @Slot(str)
        def applyAction(self, name: str) -> None:  # noqa: N802
            self.applyControl(name, None)

        @Slot(float, float, bool)
        def cameraDrag(self, dx: float, dy: float, pan: bool) -> None:  # noqa: N802
            self.applyControl("pan" if pan else "orbit", [dx, dy])

        @Slot(float)
        def cameraZoom(self, delta: float) -> None:  # noqa: N802
            self.applyControl("zoom", delta)

        @Slot(str)
        def openPath(self, path: str) -> None:  # noqa: N802
            try:
                self.platform.open_path(path)
            except Exception as exc:
                self._set_error(str(exc), "Open the path from your file manager.")

        @Slot()
        def clearError(self) -> None:  # noqa: N802
            self._error = self._error_detail = self._error_action = ""
            self.error_changed.emit()

        def shutdown(self) -> None:
            self._shutting_down = True
            self._shutdown_batch()
            self._pending_restart = None
            self._pending_next_scenario = None
            if self.session is not None:
                self.session.stop()
            if self.worker is not None and self.worker.isRunning():
                self.worker.request_shutdown()
                self.worker.wait(SHUTDOWN_WAIT_MS)
            if self.session is not None and (self.worker is None or not self.worker.isRunning()):
                self.session.close()

        def _launch_worker(self, worker: SessionWorker) -> None:
            if self.worker is not None and self.worker.isRunning():
                if can_reuse_adapter_render_resources(self.worker.adapter, worker.adapter):
                    self.worker.replace_with(worker)
                    return
                self.worker.request_shutdown()
                if not self.worker.wait(SHUTDOWN_WAIT_MS):
                    raise RuntimeError("The previous renderer did not stop before replacement.")
            self.worker = worker
            worker.state_event.connect(
                lambda state, source=worker: self._on_state(state)
                if self.worker is source
                else None
            )
            worker.telemetry_event.connect(
                lambda values, source=worker: self._on_telemetry(values)
                if self.worker is source
                else None
            )
            worker.frame_event.connect(
                lambda frame, source=worker: self._on_frame(frame)
                if self.worker is source
                else None
            )
            worker.completed_event.connect(
                lambda output, source=worker: self._on_completed(output)
                if self.worker is source
                else None
            )
            worker.idle_event.connect(lambda source=worker: self._on_worker_finished(source))
            worker.finished.connect(lambda source=worker: self._on_worker_finished(source))
            worker.error_event.connect(
                lambda detail, source=worker: self._set_error(
                    detail, "Retry with --safe-mode; if it persists, copy these details."
                )
                if self.worker is source
                else None
            )
            worker.start()

        def _start_scenario(
            self,
            scenario: ScenarioDefinition,
            *,
            config_override: dict[str, Any] | None = None,
            initial_action: tuple[str, Any] | None = None,
            start_paused_step: bool = False,
        ) -> None:
            if self.worker is not None and self.worker.busy:
                raise RuntimeError("An experiment is already running.")
            config = dict(config_override if config_override is not None else scenario.config)
            config["language"] = self._language
            output_override = os.environ.get("MCLAB_OUTPUT_DIR")
            self._replay_mode = False
            self._selected = scenario
            self._active_config = config
            self._reset_evidence()
            adapter = create_scenario_adapter(
                scenario,
                output_dir=Path(output_override) if output_override else None,
                safe_mode=self._safe_mode,
                config=config,
            )
            session = SimulationSession(adapter, duration=float(config.get("sim_time", 5.0)))
            session.set_speed(self._speed)
            application = dict(config.get("application", {}))
            start_paused = self._requires_evidence() or bool(
                application.get("start_paused", False)
            )
            replace_session(self, session, adapter)
            self.selected_changed.emit()
            self.state_changed.emit()
            self._launch_worker(
                SessionWorker(
                    session,
                    adapter=adapter,
                    initial_action=initial_action,
                    start_paused_step=start_paused_step,
                    start_paused=start_paused,
                )
            )
            if initial_action is not None:
                self._mark_learner_action(initial_action[0])
            self.navigate("experiment")

        def _request_new_live_run(
            self,
            name: str | None = None,
            value: Any = None,
            *,
            start_paused_step: bool = False,
        ) -> None:
            self._pending_restart = (name, value, start_paused_step)
            if self.worker is None or not self.worker.busy:
                self._on_worker_finished()

        def _on_worker_finished(self, source: SessionWorker | None = None) -> None:
            if source is not None and self.worker is not source:
                return
            if not self._shutting_down:
                self.state_changed.emit()
            if consume_pending_next_scenario(self):
                return
            if self._shutting_down or self._pending_restart is None or self._selected is None:
                return
            name, value, start_paused_step = self._pending_restart
            self._pending_restart = None
            action = (name, value) if name is not None else None
            try:
                self._start_scenario(
                    self._selected,
                    config_override=self._active_config,
                    initial_action=action,
                    start_paused_step=start_paused_step,
                )
            except Exception as exc:
                self._set_error(str(exc), "Open the experiment again from Explore.")

        @Slot(str)
        def _on_state(self, state: str) -> None:
            self._state = state
            self.state_changed.emit()

        @Slot("QVariantMap")
        def _on_telemetry(self, values: dict[str, float]) -> None:
            self._telemetry = {**values, "playback_speed": self._speed}
            self.telemetry_changed.emit()

        @Slot(object)
        def _on_frame(self, frame: Any) -> None:
            self.provider.update(frame)
            self._revision += 1
            self.frame_changed.emit()

        @Slot(str)
        def _on_completed(self, output: str) -> None:
            self._last_output = output
            self.results_changed.emit()

        def _scenario_map(self, scenario: ScenarioDefinition | None) -> dict[str, Any]:
            config = self._active_config if self._selected is scenario else None
            return scenario_payload(scenario, self.translator, config_override=config)

        def _submit_session(self, command: Any) -> None:
            if self.worker is not None and self.worker.isRunning():
                self.worker.submit(command)
            else:
                command()

        def _set_error(self, detail: str, action: str) -> None:
            self._error, self._error_action = localized_error(self._language, detail, action)
            self._error_detail = detail
            self.error_changed.emit()

        def _seek_relative(self, *, delta: int = 0, absolute: int | None = None) -> None:
            if self.session is None or self.session.replay_frame_count == 0:
                return
            self._submit_session(
                lambda: self.session.seek_replay(
                    absolute if absolute is not None else self.session.replay_index + delta
                )
            )

    configure_font_environment(FONT_ROOT)
    QGuiApplication.setOrganizationName("MCLab")
    QGuiApplication.setApplicationName("MCLab")
    instance_lock = acquire_instance_lock(language)
    if instance_lock is None:
        return 6
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for font_file in application_font_files():
        QFontDatabase.addApplicationFont(str(font_file))
    app_font = QFont("Noto Sans KR", 11)
    app_font.setWeight(QFont.Weight.DemiBold)
    app.setFont(app_font)
    shutting_down = [False]
    qt_messages: list[str] = []

    def qt_message_handler(_kind: Any, _context: Any, message: str) -> None:
        if shutting_down[0]:
            return
        qt_messages.append(message)
        print(message, file=sys.stderr)

    qInstallMessageHandler(qt_message_handler)
    provider = FrameProvider()
    backend = AppBackend(provider)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("mclab", provider)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("uiTranslations", TRANSLATIONS)
    engine.rootContext().setContextProperty("requestedWindowWidth", int(os.environ.get("MCLAB_WINDOW_WIDTH", "0")))
    engine.rootContext().setContextProperty("requestedWindowHeight", int(os.environ.get("MCLAB_WINDOW_HEIGHT", "0")))
    qml_path = Path(__file__).with_name("qml") / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        instance_lock.unlock()
        return 3
    backend._activation_server = start_activation_server(  # noqa: SLF001
        instance_lock, engine.rootObjects()[0]
    )
    app.aboutToQuit.connect(lambda: shutting_down.__setitem__(0, True))
    app.aboutToQuit.connect(backend.shutdown)
    if scenario_id:
        backend.startScenario(scenario_id)
    if replay_dir:
        backend.replayRun(str(replay_dir))
    schedule_smoke_action(QTimer, backend, engine.rootObjects())
    auto_quit_ms = int(os.environ.get("MCLAB_APP_AUTO_QUIT_MS", "0"))
    screenshot_path = os.environ.get("MCLAB_SCREENSHOT_PATH")
    if screenshot_path:

        def save_screenshot() -> None:
            roots = engine.rootObjects()
            if roots:
                target = Path(screenshot_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                roots[0].grabWindow().save(str(target))

        screenshot_ms = int(os.environ.get("MCLAB_SCREENSHOT_MS", max(100, auto_quit_ms // 2 if auto_quit_ms else 500)))
        QTimer.singleShot(screenshot_ms, save_screenshot)
    if auto_quit_ms > 0:
        QTimer.singleShot(auto_quit_ms, app.quit)
    exit_code = int(app.exec())
    for root in engine.rootObjects():
        root.setVisible(False)
        root.deleteLater()
    app.processEvents()
    engine.deleteLater()
    app.processEvents()
    result = exit_code
    if os.environ.get("MCLAB_SELF_TEST") == "1" and self_test_qt_errors(qt_messages):
        result = 4
    elif os.environ.get("MCLAB_FAIL_ON_ERROR") == "1" and backend.errorMessage:
        result = 5
    instance_lock.unlock()
    return result
