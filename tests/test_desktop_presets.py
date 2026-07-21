from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mclab.application.artifacts import ReplayRecorder, verify_manifest
from mclab.application.catalog import ScenarioCatalog
from mclab.application.i18n import Translator
from mclab.application.presentation import result_payloads, scenario_payload
from mclab.application.qt_evidence import (
    apply_desktop_preset,
    config_with_desktop_preset,
    create_evidence_backend_mixin,
)
from mclab.application.repositories import ArtifactRepository
from mclab.application.session import SessionState
from mclab.application.session import SimulationSession
from mclab.cli import _print_output_summary, main
from mclab.completion import CompletionReason, evaluate_completion
from mclab.labs import lab04_panda
from mclab.learner_menu import (
    MENU_ACTIONS,
    _action_completion_assessment,
    completion_target_id,
)
from mclab.sim.interaction import InteractionLog, LiveTuning, SliderSpec, TuningPreset
from mclab.sim.logging import RunLogger
from mclab.sim.reporting import _discover_runs


EXPECTED_PRESET_LABELS = {
    "lab01.interactive-pull": ["Lightly damped", "Heavy damping", "Stiff spring"],
    "lab02.interactive-disturbance": ["Gentle P", "Damped PD", "Aggressive PID"],
    "lab03.dls-singularity-2dof": [
        "Low DLS damping",
        "Balanced DLS",
        "High DLS damping",
    ],
    "lab03.condition-aware-dls-2dof": [
        "Early damping",
        "Balanced schedule",
        "Late damping",
    ],
    "lab03.interactive-2dof": ["Soft reach", "Default reach", "Near edge"],
    "lab03.interactive-tracking": ["Soft tracking", "Fast tracking"],
    "lab04.interactive-cartesian-reach": ["Soft reach", "Default reach", "Far target"],
    "lab04.interactive-virtual-wall": [
        "Soft wall",
        "Stiff wall",
        "Close wall",
        "Back away",
        "Re-enter wall",
    ],
}


def _preset(payload: dict[str, Any], label: str) -> dict[str, Any]:
    return next(item for item in payload["presets"] if item["canonicalLabel"] == label)


def test_all_eight_yaml_preset_groups_keep_yaml_order_and_values() -> None:
    catalog = ScenarioCatalog.default()
    actual: dict[str, list[str]] = {}

    for scenario in catalog.all():
        raw_presets = scenario.config.get("interaction", {}).get("tuning_presets", [])
        if not raw_presets:
            continue
        payload = scenario_payload(scenario, Translator("en"))
        actual[scenario.id] = [item["canonicalLabel"] for item in payload["presets"]]
        assert actual[scenario.id] == [item["label"] for item in raw_presets]
        assert [item["label"] for item in payload["presets"]] == actual[scenario.id]
        assert [item["values"] for item in payload["presets"]] == [
            {name: float(value) for name, value in item["values"].items()}
            for item in raw_presets
        ]

    assert actual == EXPECTED_PRESET_LABELS


def test_required_wall_preset_order_is_visible_and_complete_in_both_languages() -> None:
    scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
    english = scenario_payload(scenario, Translator("en"))
    korean = scenario_payload(scenario, Translator("ko"))
    required = [item for item in english["presets"] if item["required"]]

    assert english["requiredPresetGuide"] == (
        "Required order: Close wall → Back away → Re-enter wall"
    )
    assert korean["requiredPresetGuide"] == (
        "필수 순서: Close wall → Back away → Re-enter wall"
    )
    assert [item["canonicalLabel"] for item in required] == [
        "Close wall",
        "Back away",
        "Re-enter wall",
    ]
    assert [item["requiredOrder"] for item in required] == [1, 2, 3]
    assert {item["requiredTotal"] for item in english["presets"]} == {3}
    assert all(len(item["values"]) == 9 for item in english["presets"])


def test_preset_control_override_refreshes_the_visible_slider_model() -> None:
    scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
    payload = scenario_payload(
        scenario,
        Translator("en"),
        control_values_override={"target_x": 0.64, "wall_x": 0.53},
    )
    controls = {item["id"]: item["value"] for item in payload["controls"]}

    assert controls["target_x"] == pytest.approx(0.64)
    assert controls["wall_x"] == pytest.approx(0.53)
    assert controls["wall_stiffness"] == pytest.approx(260.0)


def test_manual_adapter_preset_is_atomic_and_records_the_canonical_event() -> None:
    adapter = SimpleNamespace(
        time=1.25,
        parameters={"mass": 2.0, "damping": 2.0, "stiffness": 20.0},
        events=[],
    )
    preset = {
        "id": "stiff_spring",
        "label": "Stiff spring",
        "canonicalLabel": "Stiff spring",
        "purpose": "Higher restoring force and frequency.",
        "required": False,
        "values": {"mass": 1.0, "damping": 1.0, "stiffness": 90.0},
    }

    assert apply_desktop_preset(adapter, preset) == preset["values"]
    assert adapter.parameters == preset["values"]
    assert adapter.events == [
        {
            "time": 1.25,
            "kind": "preset",
            "name": "stiff_spring",
            "label": "Stiff spring",
            "value": {
                "values": preset["values"],
                "purpose": "Higher restoring force and frequency.",
            },
        }
    ]

    unchanged = SimpleNamespace(parameters={"mass": 2.0}, events=[], time=0.0)
    before = dict(unchanged.parameters)
    with pytest.raises(ValueError, match="cannot apply values"):
        apply_desktop_preset(unchanged, preset)
    assert unchanged.parameters == before
    assert unchanged.events == []


def test_live_tuning_preset_applies_hidden_values_and_records_one_exact_event() -> None:
    values = {"visible_gain": 2.5, "hidden_limit": 42.0}
    event_log = InteractionLog()
    event_log.set_time(2.5)
    tuning = LiveTuning(
        [
            SliderSpec("visible_gain", "Visible gain", 0.0, 5.0, 1.0, 0.1),
            SliderSpec("hidden_limit", "Hidden limit", 0.0, 80.0, 20.0, 1.0),
        ],
        event_log=event_log,
        presets=[
            TuningPreset(
                "balanced",
                "Balanced YAML label",
                values,
                purpose="Apply both fields.",
                required=True,
            )
        ],
    )
    adapter = SimpleNamespace(time=2.5, live_tuning=tuning)
    preset = {
        "id": "balanced",
        "canonicalLabel": "Balanced YAML label",
        "purpose": "Apply both fields.",
        "required": True,
        "values": values,
    }

    assert apply_desktop_preset(adapter, preset) == values
    assert tuning.snapshot() == values
    assert event_log.events() == [
        {
            "time": 2.5,
            "kind": "preset",
            "name": "balanced",
            "label": "Balanced YAML label",
            "value": {
                "values": values,
                "purpose": "Apply both fields.",
                "required": True,
            },
        }
    ]


def test_wall_preset_materializes_all_hidden_and_visible_values_in_active_config() -> None:
    scenario = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
    payload = scenario_payload(scenario, Translator("en"))
    preset = _preset(payload, "Close wall")
    base = deepcopy(scenario.config)
    active = deepcopy(base)

    updated = config_with_desktop_preset(scenario, base, active, preset)

    assert active == base
    assert updated["cartesian_target"]["position"] == pytest.approx([0.64, 0.0, 0.57])
    assert updated["cartesian_target"]["gain"] == pytest.approx(1.05)
    assert updated["trajectory"]["start"] == pytest.approx(base["trajectory"]["start"] + 0.08)
    assert updated["trajectory"]["end"] == pytest.approx(base["trajectory"]["end"] + 0.08)
    assert updated["virtual_wall"] == {
        **base["virtual_wall"],
        "wall_x": 0.53,
        "stiffness": 320.0,
        "damping": 14.0,
        "cartesian_retreat_gain": 0.55,
    }


class _BoundSignal:
    def __init__(self) -> None:
        self.emissions = 0

    def emit(self, *_args: Any) -> None:
        self.emissions += 1


def _signal(*_args: Any) -> _BoundSignal:
    return _BoundSignal()


def _property(_kind: Any, getter: Any = None, **_kwargs: Any) -> Any:
    if getter is not None:
        return property(getter)
    return lambda function: property(function)


def _slot(*_args: Any, **_kwargs: Any) -> Any:
    return lambda function: function


class _BackendBase:
    def __init__(self) -> None:
        self.translator = Translator("en")
        self.selected_changed = _BoundSignal()
        self.errors: list[tuple[str, str]] = []
        self._telemetry: dict[str, float] = {}
        self._replay_mode = False

    def _scenario_map(self, scenario: Any) -> dict[str, Any]:
        config = self._active_config if self._selected is scenario else None
        return self._preset_scenario_payload(scenario, self.translator, config)

    def _submit_session(self, command: Any) -> None:
        command()

    def _set_error(self, detail: str, action: str) -> None:
        self.errors.append((detail, action))


def _backend_for_lab01() -> Any:
    backend_class = create_evidence_backend_mixin(
        _BackendBase,
        _property,
        _signal,
        _slot,
    )
    backend = backend_class()
    backend._init_evidence()
    backend._selected = ScenarioCatalog.default().get("lab01.interactive-pull")
    backend._set_preset_config(deepcopy(backend._selected.config), base=True)
    backend.adapter = SimpleNamespace(
        time=3.0,
        parameters={"mass": 1.0, "damping": 1.0, "stiffness": 35.0},
        events=[],
    )
    backend.session = SimpleNamespace(
        state=SessionState.PAUSED,
        replay_archive=None,
        recorder=ReplayRecorder(),
    )
    backend._prediction = "I predict a visible response."
    return backend


def _backend_for_wall() -> Any:
    backend_class = create_evidence_backend_mixin(
        _BackendBase,
        _property,
        _signal,
        _slot,
    )
    backend = backend_class()
    backend._init_evidence()
    backend._selected = ScenarioCatalog.default().get("lab04.interactive-virtual-wall")
    backend._set_preset_config(deepcopy(backend._selected.config), base=True)
    events = InteractionLog()
    backend.adapter = SimpleNamespace(
        time=0.0,
        live_tuning=lab04_panda._live_tuning(backend._selected.config, events),
        events=events,
    )
    backend.session = SimulationSession(backend.adapter, duration=1.0)
    return backend


def _apply_wall_evidence_path(labels: tuple[str, ...]) -> tuple[Any, list[dict[str, Any]]]:
    backend = _backend_for_wall()
    payload = scenario_payload(backend._selected, backend.translator)
    backend.savePrediction("Contact force will change across the wall presets.")
    applied_labels = labels or ("Soft wall",)
    for index, label in enumerate(applied_labels, start=1):
        backend.adapter.time = index * 0.25
        backend.adapter.events.set_time(backend.adapter.time)
        backend.applyPreset(_preset(payload, label)["id"])
    backend.adapter.time = (len(applied_labels) + 1) * 0.25
    backend.saveObservation("The wall response changed after the target moved.", "Matched")

    assert backend.errors == []
    assert backend.learnerActionCount == len(applied_labels)
    events = backend.adapter.events.events()
    assert [
        event["label"] for event in events if event.get("kind") == "preset"
    ] == list(applied_labels)
    return backend, events


def _persist_wall_run(outputs_root: Path, labels: tuple[str, ...]) -> Path:
    backend, events = _apply_wall_evidence_path(labels)
    scenario = backend._selected
    run = outputs_root / "wall-run"
    logger = RunLogger(
        scenario.lab_name,
        scenario.config,
        config_path=scenario.config_path,
        output_dir=run,
    )
    logger.record(
        time=0.0,
        hand_x=0.55,
        target_x=0.64,
        wall_x=0.57,
        wall_force_x=-12.0,
        wall_penetration=0.01,
    )
    output = logger.save_with_artifacts(
        summary={"max_wall_force": 12.0, "max_wall_penetration": 0.01},
        notes="Persisted desktop wall-preset evidence.",
        interaction_events=events,
        run_status="completed",
        finalize=False,
    )
    (output / "plots" / "wall_target.png").write_bytes(b"trusted wall plot")
    logger.finalize_artifacts()
    return output


def _assert_rendered_completion_surface(
    text: str,
    *,
    complete: bool,
    reason: CompletionReason,
    next_required: str,
    explicit_verdict: bool,
) -> None:
    verdict = "Complete" if complete else "Incomplete"
    if explicit_verdict:
        assert (
            f"Completion verdict:</strong> {verdict}" in text
            or f"Completion verdict: {verdict}" in text
        )
    assert reason.value in text
    if next_required:
        assert f"Needs required preset {next_required}" in text
    else:
        assert "Ready for review" in text


def test_backend_preset_counts_as_control_resets_and_rejects_noneditable_use() -> None:
    backend = _backend_for_lab01()

    backend.applyPreset("heavy_damping")

    assert backend.learnerActionCount == 1
    assert backend.hasLearnerAction
    assert backend.adapter.parameters == {"mass": 1.0, "damping": 6.0, "stiffness": 35.0}
    assert backend.adapter.events[0]["kind"] == "preset"
    assert backend.adapter.events[0]["label"] == "Heavy damping"
    assert backend.session.recorder.archive().events == (
        {
            "time": 3.0,
            "kind": "preset",
            "name": "heavy_damping",
            "value": {
                "values": {"mass": 1.0, "damping": 6.0, "stiffness": 35.0},
                "purpose": "Faster decay with less overshoot.",
            },
        },
    )
    visible = {
        item["id"]: item["value"]
        for item in backend._scenario_map(backend._selected)["controls"]
    }
    assert visible == {"mass": 1.0, "damping": 6.0, "stiffness": 35.0}

    backend._reset_evidence()
    assert backend.learnerActionCount == 0
    assert not backend.hasLearnerAction

    before = dict(backend.adapter.parameters)
    event_count = len(backend.adapter.events)
    backend._prediction = "A new prediction."
    backend._replay_mode = True
    backend.applyPreset("stiff_spring")
    assert backend.adapter.parameters == before
    assert len(backend.adapter.events) == event_count
    assert backend.learnerActionCount == 0
    assert backend.errors

    backend._replay_mode = False
    backend.session.state = SessionState.COMPLETED
    backend.applyPreset("stiff_spring")
    assert backend.adapter.parameters == before
    assert len(backend.adapter.events) == event_count
    assert backend.learnerActionCount == 0


@pytest.mark.parametrize(
    ("case_name", "labels", "next_required", "complete"),
    (
        ("none", (), "Close wall", False),
        ("partial", ("Close wall",), "Back away", False),
        (
            "out-of-order",
            ("Close wall", "Re-enter wall", "Back away"),
            "Re-enter wall",
            False,
        ),
        (
            "complete",
            ("Close wall", "Back away", "Re-enter wall"),
            "",
            True,
        ),
    ),
)
def test_persisted_wall_preset_path_keeps_every_completion_surface_in_parity(
    tmp_path: Path,
    case_name: str,
    labels: tuple[str, ...],
    next_required: str,
    complete: bool,
) -> None:
    outputs_root = tmp_path / case_name / "outputs"
    outputs_root.mkdir(parents=True)
    run = _persist_wall_run(outputs_root, labels)

    interaction_path = run / "interaction_events.json"
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    interaction_digest = hashlib.sha256(interaction_path.read_bytes()).hexdigest()
    assert manifest["status"] == "completed"
    assert manifest["artifacts"]["interaction_events.json"] == interaction_digest
    assert manifest["artifacts"]["report.html"]
    assert manifest["artifacts"]["worksheet.md"]
    assert verify_manifest(run) == []

    records = ArtifactRepository(outputs_root).list_runs()
    assert len(records) == 1
    record = records[0]
    assert record.path == run
    assert record.marker_name == "manifest.json"
    assert record.status == "completed"
    assert record.artifact_validation_errors == ()
    assert record.report_available
    assert record.worksheet_available
    assert record.completion_evidence.interaction.preset_labels == (
        labels if labels else ("Soft wall",)
    )

    catalog = ScenarioCatalog.default()
    target = catalog.get("lab04.interactive-virtual-wall")
    action = next(
        item for item in MENU_ACTIONS if completion_target_id(item) == target.id
    )
    canonical = evaluate_completion(target.completion, record.completion_evidence)
    expected_reason = (
        CompletionReason.COMPLETE
        if complete
        else CompletionReason.REQUIRED_PRESET_MISSING
    )
    assert canonical.complete is complete
    assert canonical.primary_reason == expected_reason
    assert canonical.next_required_preset == next_required

    desktop = result_payloads((record,), Translator("en"), catalog)[0]
    assert desktop["completionDecision"] == canonical.to_dict()
    assert desktop["completed"] is complete
    assert desktop["completionReason"] == expected_reason.value

    menu = _action_completion_assessment(action, catalog, records).latest_decision
    assert menu.to_dict() == canonical.to_dict()

    index_runs = _discover_runs(outputs_root)
    assert len(index_runs) == 1
    index_decision = index_runs[0]["completion_decision"]
    assert index_decision.to_dict() == canonical.to_dict()

    with redirect_stdout(StringIO()) as summary_stdout:
        _print_output_summary("Run", run)
    cli_summary = summary_stdout.getvalue()
    cli_verdict = "Complete" if complete else "Incomplete"
    assert (
        f"Completion: {cli_verdict} - {expected_reason.value} "
        f"({canonical.contract_version})"
    ) in cli_summary

    with redirect_stdout(StringIO()) as path_stdout:
        assert main(["path", "--output-dir", str(outputs_root), "--all"]) == 0
    cli_path = path_stdout.getvalue()
    wall_path_line = next(
        line for line in cli_path.splitlines() if "11. Touch virtual wall:" in line
    )
    if next_required:
        assert f"Needs required preset {next_required}" in wall_path_line
    else:
        assert "Done - latest wall-run" in wall_path_line

    index_html = (outputs_root / "index.html").read_text(encoding="utf-8")
    report_html = (run / "report.html").read_text(encoding="utf-8")
    worksheet = (run / "worksheet.md").read_text(encoding="utf-8")
    _assert_rendered_completion_surface(
        index_html,
        complete=complete,
        reason=expected_reason,
        next_required=next_required,
        explicit_verdict=False,
    )
    for rendered in (report_html, worksheet):
        _assert_rendered_completion_surface(
            rendered,
            complete=complete,
            reason=expected_reason,
            next_required=next_required,
            explicit_verdict=True,
        )


def test_qml_exposes_keyboard_accessible_preset_buttons_and_required_guide() -> None:
    root = Path(__file__).parents[1] / "src/mclab/application/qml"
    controls = (root / "ExperimentControls.qml").read_text(encoding="utf-8")
    button = (root / "MButton.qml").read_text(encoding="utf-8")

    for contract in (
        "id: presetRepeater",
        "model: scenario.presets || []",
        'objectName: "quickPreset_" + modelData.id',
        "scenario.requiredPresetGuide",
        "accessibleName:",
        "accessibleDescription:",
        "onClicked: backend.applyPreset(modelData.id)",
    ):
        assert contract in controls
    for contract in (
        "focusPolicy: Qt.StrongFocus",
        "Keys.onReturnPressed",
        "Keys.onEnterPressed",
        "Accessible.role: Accessible.Button",
    ):
        assert contract in button
    assert len(controls.splitlines()) <= 400
