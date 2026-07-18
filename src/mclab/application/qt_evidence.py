"""Qt-free factory for the guided prediction and observation workflow."""

from __future__ import annotations

from typing import Any

from mclab.application.session import SessionState

PREDICTION_LIMIT = 240
OBSERVATION_LIMIT = 300
PREDICTION_OUTCOMES = frozenset({"Matched", "Partly matched", "Surprised"})


def create_evidence_backend_mixin(
    base: type,
    Property: Any,
    Signal: Any,
    Slot: Any,
) -> type:
    """Build a QObject mixin after PySide6 is selected by the CLI."""

    class EvidenceBackendMixin(base):
        evidence_changed = Signal()

        def _init_evidence(self) -> None:
            self._prediction = ""
            self._learner_action_count = 0
            self._observation = {}

        @Property(bool, notify=evidence_changed)
        def hasPrediction(self) -> bool:  # noqa: N802
            return bool(self._prediction)

        @Property(bool, notify=evidence_changed)
        def hasLearnerAction(self) -> bool:  # noqa: N802
            return self._learner_action_count > 0

        @Property(bool, notify=evidence_changed)
        def hasObservation(self) -> bool:  # noqa: N802
            return bool(self._observation)

        @Property(int, notify=evidence_changed)
        def learnerActionCount(self) -> int:  # noqa: N802
            return self._learner_action_count

        @Property(str, notify=evidence_changed)
        def predictionText(self) -> str:  # noqa: N802
            return self._prediction

        @Property(bool, notify=evidence_changed)
        def waitingForPrediction(self) -> bool:  # noqa: N802
            return (
                self._requires_evidence()
                and not bool(getattr(self, "_replay_mode", False))
                and not self._prediction
            )

        @Slot(str)
        def savePrediction(self, text: str) -> None:  # noqa: N802
            prediction = _clean_text(text, PREDICTION_LIMIT)
            if len(prediction) < 3:
                self._evidence_error("evidence.prediction_short")
                return
            if not self._evidence_editable():
                self._evidence_error("evidence.live_only")
                return
            self._prediction = prediction
            self._observation = {}
            self._queue_evidence(
                "prediction",
                "prediction",
                prediction,
                "Prediction",
                resume=True,
            )
            self.evidence_changed.emit()

        @Slot(str, str)
        def saveObservation(self, note: str, outcome: str) -> None:  # noqa: N802
            observation = _clean_text(note, OBSERVATION_LIMIT)
            canonical_outcome = str(outcome).strip()
            if not self._prediction:
                self._evidence_error("evidence.prediction_first")
                return
            if self._learner_action_count <= 0:
                self._evidence_error("evidence.control_first")
                return
            if canonical_outcome not in PREDICTION_OUTCOMES:
                self._evidence_error("evidence.outcome_required")
                return
            if len(observation) < 3:
                self._evidence_error("evidence.observation_short")
                return
            if not self._evidence_editable():
                self._evidence_error("evidence.live_only")
                return
            value = {
                "prediction": self._prediction,
                "outcome": canonical_outcome,
                "note": observation,
                "status": dict(self._telemetry),
            }
            self._observation = value
            self._queue_evidence("marker", "observation", value, "Mark observation")
            self.evidence_changed.emit()

        def _reset_evidence(self) -> None:
            self._prediction = ""
            self._learner_action_count = 0
            self._observation = {}
            self.evidence_changed.emit()

        def _mark_learner_action(self, name: str) -> None:
            if not self._requires_evidence() or not self._is_experiment_control(name):
                return
            self._learner_action_count += 1
            self.evidence_changed.emit()

        def _requires_evidence(self) -> bool:
            selected = getattr(self, "_selected", None)
            completion = getattr(selected, "completion", None)
            return bool(
                completion
                and (
                    completion.requires_learner_control
                    or completion.requires_observation
                )
            )

        def _is_experiment_control(self, name: str) -> bool:
            if str(name) in {"orbit", "pan", "zoom", "reset_camera"}:
                return False
            if getattr(self, "_selected", None) is None:
                return False
            payload = self._scenario_map(self._selected)
            ids = {
                str(item.get("id", ""))
                for item in (*payload.get("actions", ()), *payload.get("controls", ()))
            }
            return str(name) in ids

        def _evidence_editable(self) -> bool:
            session = getattr(self, "session", None)
            return bool(
                self._requires_evidence()
                and session is not None
                and session.replay_archive is None
                and session.state
                in {SessionState.READY, SessionState.RUNNING, SessionState.PAUSED}
            )

        def _queue_evidence(
            self,
            kind: str,
            name: str,
            value: Any,
            label: str,
            *,
            resume: bool = False,
        ) -> None:
            session = self.session

            def record() -> None:
                session.record_evidence(kind, name, value, label=label)
                if resume and session.state == SessionState.PAUSED:
                    session.resume()

            self._submit_session(record)

        def _evidence_error(self, key: str) -> None:
            self._set_error(
                self.translator.text(key),
                self.translator.text("evidence.recovery"),
            )

    return EvidenceBackendMixin


def _clean_text(value: str, limit: int) -> str:
    return " ".join(str(value).split())[:limit].strip()
