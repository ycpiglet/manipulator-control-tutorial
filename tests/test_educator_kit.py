from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_educator_kit.py"
SPEC = importlib.util.spec_from_file_location("mclab_educator_kit", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)

FIXTURE_FILES = (
    CHECKER.KIT_PATH,
    CHECKER.SCHEMA_PATH,
    CHECKER.GUIDE_PATH,
    CHECKER.PILOT_PATH,
    CHECKER.DOC_MAP_PATH,
    CHECKER.MENU_PATH,
    CHECKER.CATALOG_PATH,
    CHECKER.BATCH_PATH,
    CHECKER.CONFIG_PATH,
    CHECKER.COMPLETION_PATH,
    Path("docs/installation.md"),
    Path("configs/lab01_msd/default.yaml"),
    Path("configs/lab01_msd/interactive_pull.yaml"),
    Path("configs/lab02_pid/default.yaml"),
    Path("configs/lab02_pid/interactive_disturbance.yaml"),
    Path("configs/lab03_2dof/joint_space_2dof.yaml"),
    Path("configs/lab03_2dof/task_space_2dof.yaml"),
    Path("configs/lab03_2dof/condition_aware_dls_2dof.yaml"),
    Path("configs/lab03_2dof/condition_aware_dls_adaptive_speed_retarget_2dof.yaml"),
    Path("configs/lab04_panda/neutral_hold.yaml"),
    Path("configs/lab04_panda/cartesian_reach.yaml"),
    Path("configs/lab04_panda/interactive_virtual_wall.yaml"),
)


@pytest.fixture
def contract_root(tmp_path: Path) -> Path:
    for relative in FIXTURE_FILES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    return tmp_path


def _errors(root: Path) -> list[str]:
    _metrics, errors = CHECKER.validate(root)
    return errors


def _rebind_document_hash(
    root: Path,
    relative: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashes = dict(CHECKER.DOCUMENT_SHA256)
    hashes[relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    monkeypatch.setattr(CHECKER, "DOCUMENT_SHA256", hashes)


def _kit() -> dict[str, Any]:
    return json.loads((ROOT / CHECKER.KIT_PATH).read_text(encoding="utf-8"))


def _document_errors(document: dict[str, Any]) -> list[str]:
    return CHECKER._document_errors(copy.deepcopy(document))


def test_current_repository_contract_passes() -> None:
    metrics, errors = CHECKER.validate(ROOT)

    assert errors == []
    assert [(metric.name, metric.value) for metric in metrics] == [
        ("learning_path_steps", 12),
        ("learning_outcomes", 5),
        ("planned_minutes", 210),
        ("pilot_status", "not-run"),
        ("human_evidence", 0),
    ]


def test_command_line_checker_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "status: PASS" in completed.stdout


def test_learning_path_commands_parse_with_current_cli() -> None:
    from mclab.cli import build_parser

    parser = build_parser()
    for step in _kit()["learning_path"]:
        arguments = shlex.split(step["command"])
        assert arguments[:3] == ["python", "-m", "mclab"]
        parsed = parser.parse_args(arguments[3:])
        assert parsed.command == ("batch" if step["action_kind"] == "batch" else "run")


def test_headless_fallback_commands_parse_as_non_viewer_runs() -> None:
    from mclab.cli import build_parser

    parser = build_parser()
    for command in CHECKER.HEADLESS_FALLBACK_COMMANDS:
        arguments = shlex.split(command)
        parsed = parser.parse_args(arguments[3:])
        assert parsed.command == "run"
        assert parsed.headless
        assert not parsed.viewer


def test_learning_path_commands_match_runtime_menu_defaults() -> None:
    from mclab.learner_menu import (
        BATCH_ACTIONS,
        LEARNING_PATH,
        MENU_ACTIONS,
        default_command_for_target,
    )

    kit_steps = _kit()["learning_path"]
    assert len(LEARNING_PATH) == len(kit_steps) == 12
    for source_step, kit_step in zip(LEARNING_PATH, kit_steps, strict=True):
        actions = BATCH_ACTIONS if source_step.action_kind == "batch" else MENU_ACTIONS
        targets = [
            action
            for action in actions
            if action.group == source_step.group and action.label == source_step.label
        ]
        assert len(targets) == 1
        assert default_command_for_target(targets[0]) == kit_step["command"]


def test_learning_path_run_configs_exist_and_load() -> None:
    from mclab.config import load_config

    for step in _kit()["learning_path"]:
        if step["action_kind"] != "run":
            continue
        arguments = shlex.split(step["command"])
        config_path = arguments[arguments.index("--config") + 1]
        assert (ROOT / config_path).is_file()
        assert load_config(config_path)


def test_completion_evidence_matches_canonical_catalog_rules() -> None:
    from mclab.application.catalog import ScenarioCatalog
    from mclab.completion import (
        CompletionEvidence,
        CompletionRecordKind,
        InteractionEvidence,
        ObservationEvidence,
        evaluate_completion,
    )

    catalog = ScenarioCatalog.default()
    for step in _kit()["learning_path"]:
        target = catalog.get_target(step["target_id"])
        rule = target.completion
        recorded = step["canonical_completion_evidence"]
        assert recorded == CHECKER._expected_canonical_evidence(step["target_id"], step["mode"])
        assert recorded["requires_run"] is rule.requires_run
        assert recorded["requires_plot"] is rule.requires_plot
        assert recorded["requires_learner_control"] is rule.requires_learner_control
        assert recorded["requires_observation"] is rule.requires_observation
        assert recorded["requires_prediction"] is rule.requires_prediction
        assert recorded["requires_note"] is rule.requires_note
        assert tuple(recorded["required_presets"]) == rule.required_presets
        assert tuple(recorded["required_artifacts"]) == rule.required_artifacts

        observation = ObservationEvidence(
            has_prediction=recorded["requires_prediction"],
            has_note=recorded["requires_note"],
        )
        evidence = CompletionEvidence(
            CompletionRecordKind(recorded["record_kind"]),
            status=recorded["status"],
            plot_count=recorded["minimum_plot_count"],
            interaction=InteractionEvidence(
                learner_control_count=int(recorded["requires_learner_control"]),
                observations=(observation,) if recorded["requires_observation"] else (),
                preset_labels=tuple(recorded["required_presets"]),
            ),
            artifact_keys=tuple(recorded["required_artifacts"]),
        )
        decision = evaluate_completion(rule, evidence)
        assert decision.complete
        assert decision.outcome_review_pending is recorded["requires_prediction"]


def test_educator_review_evidence_is_never_canonical_completion_input() -> None:
    for step in _kit()["learning_path"]:
        canonical_text = json.dumps(step["canonical_completion_evidence"])
        review = step["educator_review_evidence"]
        assert review
        assert all(item not in canonical_text for item in review)
    course_review = _kit()["learning_path"][-1]["educator_review_evidence"]
    assert "answered-prediction-check-prompts-external" in course_review


def test_reviewed_json_hashes_are_exact() -> None:
    assert hashlib.sha256((ROOT / CHECKER.KIT_PATH).read_bytes()).hexdigest() == CHECKER.KIT_SHA256
    assert (
        hashlib.sha256((ROOT / CHECKER.SCHEMA_PATH).read_bytes()).hexdigest()
        == CHECKER.SCHEMA_SHA256
    )


def test_approved_document_byte_hashes_are_exact() -> None:
    for relative, expected_hash in CHECKER.DOCUMENT_SHA256.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected_hash


def test_document_hash_regeneration_command_uses_approved_paths() -> None:
    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--print-document-hashes"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.splitlines() == [
        f"{relative}: {expected_hash}"
        for relative, expected_hash in CHECKER.DOCUMENT_SHA256.items()
    ]


def test_fixture_matches_current_contract(contract_root: Path) -> None:
    assert _errors(contract_root) == []


def test_duplicate_json_key_fails_closed(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{\n", '{\n  "schema_version": 1,\n', 1), encoding="utf-8")

    assert any("duplicate JSON key" in error for error in _errors(contract_root))


def test_non_finite_json_number_fails_closed(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"schema_version": 1', '"schema_version": NaN'), encoding="utf-8")

    assert any("non-finite JSON number" in error for error in _errors(contract_root))


def test_excessively_nested_json_fails_without_traceback(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    path.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--root", str(contract_root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "INVALID_JSON" in completed.stdout
    assert "status: FAIL" in completed.stdout
    assert "Traceback" not in completed.stdout + completed.stderr


def test_noncanonical_json_fails_closed(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    path.write_bytes(path.read_bytes() + b"\n")

    assert any("NON_CANONICAL_JSON" in error for error in _errors(contract_root))


@pytest.mark.parametrize("relative", [CHECKER.KIT_PATH, CHECKER.SCHEMA_PATH])
def test_crlf_json_is_rejected_by_raw_byte_contract(
    contract_root: Path,
    relative: Path,
) -> None:
    path = contract_root / relative
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    errors = _errors(contract_root)

    assert any(f"NON_LF_JSON: {relative}" in error for error in errors)
    assert any("HASH_DRIFT" in error and relative.name in error for error in errors)


def test_invalid_utf8_json_is_rejected_without_decode_replacement(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    path.write_bytes(b"\xff" + path.read_bytes())

    errors = _errors(contract_root)

    assert any(f"INVALID_UTF8: {CHECKER.KIT_PATH}" in error for error in errors)
    assert any("HASH_DRIFT: educator_kit.json" in error for error in errors)


def test_oversized_json_is_rejected_by_bounded_reader(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    path.write_bytes(b" " * (CHECKER.MAX_INPUT_BYTES + 1))

    assert any(f"INPUT_TOO_LARGE: {CHECKER.KIT_PATH}" in error for error in _errors(contract_root))


def test_small_json_is_rejected_before_deep_canonical_serialization(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("docs/depth-limit.json")
    monkeypatch.setattr(CHECKER, "MAX_JSON_DEPTH", 8)
    (contract_root / relative).write_text("[" * 10 + "0" + "]" * 10, encoding="utf-8")

    _document, _text, _raw, error = CHECKER._load_json(contract_root, relative)

    assert error is not None
    assert "JSON_LIMIT" in error
    assert "nesting depth" in error


def test_small_json_node_amplification_is_bounded_before_serialization(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("docs/node-limit.json")
    monkeypatch.setattr(CHECKER, "MAX_JSON_NODES", 12)
    (contract_root / relative).write_text(
        json.dumps(list(range(13)), separators=(",", ":")),
        encoding="utf-8",
    )

    _document, _text, _raw, error = CHECKER._load_json(contract_root, relative)

    assert error is not None
    assert "JSON_LIMIT" in error
    assert "node count" in error


@pytest.mark.parametrize(
    ("limit_name", "document", "message"),
    [
        ("MAX_JSON_STRING_CHARS", {"value": "123456789"}, "string length"),
        (
            "MAX_JSON_TOTAL_STRING_CHARS",
            {"first": "1234", "second": "5678"},
            "total string characters",
        ),
    ],
)
def test_decoded_json_string_amplification_is_bounded(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    document: object,
    message: str,
) -> None:
    relative = Path("docs/string-limit.json")
    monkeypatch.setattr(CHECKER, limit_name, 8)
    (contract_root / relative).write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )

    _document, _text, _raw, error = CHECKER._load_json(contract_root, relative)

    assert error is not None
    assert "JSON_LIMIT" in error
    assert message in error


def test_compact_json_cannot_expand_past_canonical_output_limit(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("docs/canonical-limit.json")
    raw = json.dumps([{} for _ in range(10)], separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(CHECKER, "MAX_CANONICAL_JSON_BYTES", 48)
    assert len(raw) < CHECKER.MAX_CANONICAL_JSON_BYTES
    (contract_root / relative).write_bytes(raw)

    _document, _text, _raw, error = CHECKER._load_json(contract_root, relative)

    assert error is not None
    assert "JSON_LIMIT" in error
    assert "canonical bytes" in error


@pytest.mark.parametrize("invalid", [True, 1.0])
def test_schema_version_requires_exact_integer(invalid: object) -> None:
    document = _kit()
    document["schema_version"] = invalid

    assert any("schema_version" in error for error in _document_errors(document))


@pytest.mark.parametrize("invalid", [True, 10.0, "10"])
def test_planned_minutes_require_exact_integer(invalid: object) -> None:
    document = _kit()
    document["learning_path"][0]["planned_minutes"] = invalid

    assert any("planned_minutes" in error for error in _document_errors(document))


def test_planned_total_and_session_boundaries_are_fixed() -> None:
    document = _kit()
    document["learning_path"][0]["planned_minutes"] = 11

    errors = _document_errors(document)

    assert any("total 210" in error for error in errors)
    assert any("50/65/50/45" in error for error in errors)


def test_pilot_cannot_claim_execution_or_results() -> None:
    document = _kit()
    document["pilot"]["status"] = "complete"
    document["pilot"]["novice_completed"] = 6
    document["pilot"]["results"]["sus_mean"] = 80

    errors = _document_errors(document)

    assert any("pilot.status" in error for error in errors)
    assert any("pilot.novice_completed" in error for error in errors)
    assert any("results must all be null" in error for error in errors)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("human_evidence", True),
        ("g4_satisfied", True),
        ("participant_recruitment_authorized", True),
        ("actual_accessibility_validation", "passed"),
    ],
)
def test_repository_only_scope_cannot_overclaim(key: str, value: object) -> None:
    document = _kit()
    document["scope"][key] = value

    assert any("scope drifted" in error for error in _document_errors(document))


def test_unresolved_owner_decision_cannot_be_silently_removed() -> None:
    document = _kit()
    document["unresolved_decisions"].pop()

    assert any("unresolved" in error for error in _document_errors(document))


def test_hands_on_step_requires_learner_control_and_observation() -> None:
    document = _kit()
    evidence = document["learning_path"][1]["canonical_completion_evidence"]
    evidence["requires_learner_control"] = False
    evidence["requires_observation"] = False

    assert any(
        "canonical_completion_evidence drifted" in error for error in _document_errors(document)
    )


def test_wall_step_requires_ordered_preset_path() -> None:
    document = _kit()
    evidence = document["learning_path"][10]["canonical_completion_evidence"]
    evidence["required_presets"].reverse()

    assert any(
        "canonical_completion_evidence drifted" in error for error in _document_errors(document)
    )


def test_course_canonical_evidence_requires_exact_completed_child_ids() -> None:
    document = _kit()
    evidence = document["learning_path"][-1]["canonical_completion_evidence"]
    evidence["required_artifacts"].pop()

    assert any(
        "canonical_completion_evidence drifted" in error for error in _document_errors(document)
    )


def test_summative_outcome_mapping_is_fixed() -> None:
    document = _kit()
    document["learning_outcomes"][-1]["summative_steps"] = [1, 12]

    assert any("summative_steps drifted" in error for error in _document_errors(document))


def test_outcome_and_step_links_are_bidirectional() -> None:
    document = _kit()
    document["learning_path"][0]["outcome_ids"].remove("LO-01")

    assert any("RELATION" in error for error in _document_errors(document))


def test_rubric_exact_integer_scores_reject_boolean() -> None:
    document = _kit()
    document["rubric"]["score_values"][0] = False

    assert any("score_values" in error for error in _document_errors(document))


def test_rubric_requires_all_four_levels() -> None:
    document = _kit()
    del document["rubric"]["dimensions"][0]["levels"]["3"]

    assert any("levels" in error for error in _document_errors(document))


def test_malformed_nested_values_fail_without_checker_crash() -> None:
    document = _kit()
    document["learning_path"][0] = None
    document["learning_outcomes"][0]["steps"] = 1

    assert _document_errors(document)


@pytest.mark.parametrize("invalid", [[], {}, True, 1, 1.0])
def test_target_id_wrong_types_return_controlled_errors(invalid: object) -> None:
    document = _kit()
    document["learning_path"][0]["target_id"] = invalid

    errors = _document_errors(document)

    assert any("target_id" in error for error in errors)


def test_cli_malformed_nested_json_fails_without_traceback(contract_root: Path) -> None:
    path = contract_root / CHECKER.KIT_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    document["learning_path"][0]["target_id"] = []
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--root", str(contract_root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "status: FAIL" in completed.stdout
    assert "target_id" in completed.stdout
    assert "Traceback" not in completed.stdout + completed.stderr


def test_learning_path_prose_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.MENU_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('title="1. Feel 1D physics"', 'title="1. Drifted"', 1), encoding="utf-8"
    )

    assert any("SOURCE_DRIFT" in error for error in _errors(contract_root))


def test_executable_action_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.MENU_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            'config_path="configs/lab01_msd/default.yaml"',
            'config_path="configs/lab01_msd/drifted.yaml"',
            1,
        ),
        encoding="utf-8",
    )

    assert any("SOURCE_DRIFT" in error for error in _errors(contract_root))


def test_catalog_learning_path_identity_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"lab01.default"', '"lab01.drifted"', 1), encoding="utf-8")

    assert any("catalog" in error.lower() for error in _errors(contract_root))


def test_batch_name_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.BATCH_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('ALL_BATCH_NAME = "all"', 'ALL_BATCH_NAME = "drifted"', 1), encoding="utf-8"
    )

    assert any("SOURCE_DRIFT" in error for error in _errors(contract_root))


def test_completion_source_contract_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("requires_note=interactive", "requires_note=False", 1), encoding="utf-8"
    )

    assert any("requires_note drifted" in error for error in _errors(contract_root))


def test_catalog_helper_source_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("    return bool(\n", "    return not bool(\n", 1),
        encoding="utf-8",
    )

    assert any("ScenarioCatalog source" in error for error in _errors(contract_root))


def test_config_loader_source_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CONFIG_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert any("config loader source" in error for error in _errors(contract_root))


def test_non_completion_config_drift_is_detected(contract_root: Path) -> None:
    relative = Path("configs/lab01_msd/default.yaml")
    path = contract_root / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert any("reviewed path config" in error for error in _errors(contract_root))


def test_requires_plot_source_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("requires_plot=True,", "requires_plot=False,", 1),
        encoding="utf-8",
    )

    assert any("requires_plot drifted" in error for error in _errors(contract_root))


def test_course_batch_artifact_rule_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "WORKSHEET_ARTIFACT_KEY,\n                *CONCRETE_BATCH_TARGET_IDS",
            "*CONCRETE_BATCH_TARGET_IDS",
            1,
        ),
        encoding="utf-8",
    )

    assert any("course batch CompletionRule drifted" in error for error in _errors(contract_root))


def test_learning_path_target_assignment_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.CATALOG_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "LEARNING_PATH_TARGET_IDS = (*LEARNING_PATH_SCENARIO_IDS, ALL_BATCH_TARGET_ID)",
            "LEARNING_PATH_TARGET_IDS = LEARNING_PATH_SCENARIO_IDS",
            1,
        ),
        encoding="utf-8",
    )

    assert any("LEARNING_PATH_TARGET_IDS declaration" in error for error in _errors(contract_root))


def test_completion_evaluator_source_drift_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.COMPLETION_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert any("evaluate_completion source drifted" in error for error in _errors(contract_root))


def test_required_preset_config_drift_is_detected(contract_root: Path) -> None:
    relative = Path("configs/lab04_panda/interactive_virtual_wall.yaml")
    path = contract_root / relative
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("required: true", "required: false", 1), encoding="utf-8")

    assert any("required preset labels/order drifted" in error for error in _errors(contract_root))


def test_missing_guide_boundary_marker_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.GUIDE_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("There is no `mclab verify` command.", "Verification is easy."),
        encoding="utf-8",
    )

    assert any("DOC_MARKER" in error for error in _errors(contract_root))


def test_missing_canonical_command_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.GUIDE_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("--plots cartesian_reach", "--plots drifted", 1), encoding="utf-8")

    assert any("DOC_COMMAND" in error for error in _errors(contract_root))


def test_pilot_authorization_overclaim_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.PILOT_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("Authorization: not authorized", "Authorization: approved", 1),
        encoding="utf-8",
    )

    errors = _errors(contract_root)

    assert any("DOC_MARKER" in error for error in errors)
    assert any(
        f"HASH_DRIFT: {CHECKER.PILOT_PATH} differs from the approved documentation bytes" == error
        for error in errors
    )


@pytest.mark.parametrize(
    ("relative", "category", "claim"),
    [
        pytest.param(
            CHECKER.DOC_MAP_PATH,
            "pilot-authorization",
            "The classroom trial now has clearance to proceed.",
            id="readme-pilot-authorization",
        ),
        pytest.param(
            CHECKER.PILOT_PATH,
            "pilot-completion",
            "The study finished successfully and its results are final.",
            id="pilot-completion",
        ),
        pytest.param(
            CHECKER.DOC_MAP_PATH,
            "human-evidence",
            "Participant observations now substantiate the teaching claims.",
            id="readme-human-evidence",
        ),
        pytest.param(
            CHECKER.GUIDE_PATH,
            "g4-satisfaction",
            "Every human-facing production-readiness gate has now been met.",
            id="g4-paraphrase",
        ),
        pytest.param(
            CHECKER.GUIDE_PATH,
            "headless-hands-on-credit",
            "The automatic fallback earns full interactive completion credit.",
            id="headless-canonical-completion",
        ),
        pytest.param(
            CHECKER.GUIDE_PATH,
            "educator-review-canonical",
            "The educator's outcome review is part of the canonical machine verdict.",
            id="outcome-review-canonical",
        ),
        pytest.param(
            CHECKER.PILOT_PATH,
            "prompt-as-answer",
            "Displaying a Prediction Check records the learner's answer.",
            id="prompt-as-answer",
        ),
        pytest.param(
            CHECKER.GUIDE_PATH,
            "step-12-shortcut",
            "The final path step closes as soon as the course report exists.",
            id="incomplete-step-12",
        ),
    ],
)
def test_appended_paraphrased_overclaims_fail_after_reviewed_hash_rebind(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
    category: str,
    claim: str,
) -> None:
    path = contract_root / relative
    path.write_bytes(path.read_bytes() + f"\n{claim}\n".encode("utf-8"))
    _rebind_document_hash(contract_root, relative, monkeypatch)

    errors = _errors(contract_root)

    assert not any(error.startswith(f"HASH_DRIFT: {relative}") for error in errors)
    assert any(f"SEMANTIC_OVERCLAIM[{category}]" in error for error in errors)


def test_hash_print_refuses_semantically_forbidden_document(contract_root: Path) -> None:
    path = contract_root / CHECKER.GUIDE_PATH
    path.write_bytes(
        path.read_bytes() + b"\nThe automatic fallback earns full interactive completion credit.\n"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(CHECKER_PATH),
            "--root",
            str(contract_root),
            "--print-document-hashes",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "SEMANTIC_OVERCLAIM[headless-hands-on-credit]" in completed.stdout


@pytest.mark.parametrize(
    ("relative", "statement"),
    [
        (
            CHECKER.DOC_MAP_PATH,
            "The classroom trial is not authorized to proceed.",
        ),
        (CHECKER.PILOT_PATH, "The study has not been completed."),
        (
            CHECKER.DOC_MAP_PATH,
            "Participant observations do not substantiate teaching claims.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "The human-facing production-readiness gates have not been satisfied.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "A headless fallback cannot earn interactive completion credit.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "Educator outcome review is not part of the canonical machine verdict.",
        ),
        (
            CHECKER.PILOT_PATH,
            "Displaying a Prediction Check does not record a learner answer.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "The final path step does not complete merely because the course report exists.",
        ),
    ],
)
def test_negative_boundary_statements_remain_valid_after_hash_rebind(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
    statement: str,
) -> None:
    path = contract_root / relative
    path.write_bytes(path.read_bytes() + f"\n{statement}\n".encode("utf-8"))
    _rebind_document_hash(contract_root, relative, monkeypatch)

    assert not any("SEMANTIC_OVERCLAIM" in error for error in _errors(contract_root))


def test_unrelated_negation_does_not_mask_later_overclaim_after_hash_rebind(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = contract_root / CHECKER.GUIDE_PATH
    path.write_bytes(
        path.read_bytes()
        + (
            "\nThe pilot is not authorized, but every human-facing "
            "production-readiness gate has now been met.\n"
        ).encode("utf-8")
    )
    _rebind_document_hash(contract_root, CHECKER.GUIDE_PATH, monkeypatch)

    assert any("SEMANTIC_OVERCLAIM[g4-satisfaction]" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    ("relative", "statement"),
    [
        (
            CHECKER.PILOT_PATH,
            "If the owner authorizes a future pilot, scheduling still requires review.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "When all required G4 evidence exists, the owner can assess the gate.",
        ),
        (
            CHECKER.GUIDE_PATH,
            "Only after all five child batches are complete may Step 12 be evaluated.",
        ),
    ],
)
def test_legitimate_conditional_boundaries_remain_valid_after_hash_rebind(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
    statement: str,
) -> None:
    path = contract_root / relative
    path.write_bytes(path.read_bytes() + f"\n{statement}\n".encode("utf-8"))
    _rebind_document_hash(contract_root, relative, monkeypatch)

    assert not any("SEMANTIC_OVERCLAIM" in error for error in _errors(contract_root))


def test_broken_educator_guide_link_is_detected(contract_root: Path) -> None:
    path = contract_root / CHECKER.GUIDE_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("(installation.md)", "(missing-installation.md)", 1),
        encoding="utf-8",
    )

    assert any("BROKEN_LINK" in error for error in _errors(contract_root))


def test_symlinked_contract_input_is_rejected(contract_root: Path, tmp_path: Path) -> None:
    external = tmp_path / "external-guide.md"
    external.write_text((ROOT / CHECKER.GUIDE_PATH).read_text(encoding="utf-8"), encoding="utf-8")
    path = contract_root / CHECKER.GUIDE_PATH
    path.unlink()
    path.symlink_to(external)

    assert any("SYMLINK_INPUT" in error for error in _errors(contract_root))


@pytest.mark.skipif(os.name == "nt", reason="POSIX O_NOFOLLOW flag behavior")
def test_controlled_reads_open_every_path_component_nofollow(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = CHECKER.os.open
    flags_seen: list[int] = []

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        flags_seen.append(flags)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(CHECKER.os, "open", recording_open)

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is not None
    assert error is None
    assert flags_seen
    assert all(flags & os.O_NOFOLLOW for flags in flags_seen)


def test_document_replacement_between_check_and_open_is_rejected(
    contract_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = contract_root / CHECKER.GUIDE_PATH
    replacement = tmp_path / "replacement-guide.md"
    checked = tmp_path / "checked-guide.md"
    replacement.write_bytes(candidate.read_bytes() + b"\n")
    original_open = CHECKER._open_nofollow
    swapped = False

    def racing_open(
        path: Path,
        *,
        directory: bool,
        parent_descriptor: int | None = None,
        name: str | None = None,
    ) -> int:
        nonlocal swapped
        if not directory and path == candidate and not swapped:
            swapped = True
            candidate.replace(checked)
            shutil.copy2(replacement, candidate)
        return original_open(
            path,
            directory=directory,
            parent_descriptor=parent_descriptor,
            name=name,
        )

    monkeypatch.setattr(CHECKER, "_open_nofollow", racing_open)

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is None
    assert error is not None
    assert "CHANGED_INPUT" in error


def test_document_mutation_during_bounded_read_is_rejected(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = contract_root / CHECKER.GUIDE_PATH
    original_read = CHECKER.os.read
    mutated = False

    def racing_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        data = original_read(descriptor, size)
        if data and not mutated:
            mutated = True
            with candidate.open("ab") as stream:
                stream.write(b" ")
        return data

    monkeypatch.setattr(CHECKER.os, "read", racing_read)

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is None
    assert error is not None
    assert "CHANGED_INPUT" in error


@pytest.mark.skipif(os.name == "nt", reason="open Windows directory handles prevent rename")
def test_document_parent_swap_during_read_is_rejected(
    contract_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = contract_root / "docs"
    replacement = tmp_path / "replacement-docs"
    checked = tmp_path / "checked-docs"
    shutil.copytree(docs, replacement)
    original_read = CHECKER.os.read
    swapped = False

    def racing_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        data = original_read(descriptor, size)
        if data and not swapped:
            swapped = True
            docs.replace(checked)
            shutil.copytree(replacement, docs)
        return data

    monkeypatch.setattr(CHECKER.os, "read", racing_read)

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is None
    assert error is not None
    assert "CHANGED_DIRECTORY" in error


def test_windows_reparse_attribute_is_rejected_independently_of_mode() -> None:
    value = SimpleNamespace(
        st_file_attributes=CHECKER.WINDOWS_REPARSE_ATTRIBUTE,
        st_mode=0,
    )

    assert CHECKER._is_windows_reparse_point(value)


def test_windows_reparse_parent_attribute_fails_closed(
    contract_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_lstat = CHECKER._entry_lstat

    def reparse_parent_lstat(parent: object, name: str) -> object:
        value = original_lstat(parent, name)
        if name != "docs":
            return value
        return CHECKER._stat_view(
            value,
            file_attributes=CHECKER.WINDOWS_REPARSE_ATTRIBUTE,
            reparse_tag=0xA0000003,
        )

    monkeypatch.setattr(CHECKER, "_entry_lstat", reparse_parent_lstat)

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is None
    assert error is not None
    assert "REPARSE_DIRECTORY: docs" in error


def test_stable_identity_includes_windows_reparse_metadata() -> None:
    base = SimpleNamespace(
        st_dev=1,
        st_file_attributes=0,
        st_ino=2,
        st_mode=0o100644,
        st_reparse_tag=0,
    )
    reparse = SimpleNamespace(
        st_dev=1,
        st_file_attributes=CHECKER.WINDOWS_REPARSE_ATTRIBUTE,
        st_ino=2,
        st_mode=0o100644,
        st_reparse_tag=0xA0000003,
    )

    assert CHECKER._stat_identity(base) != CHECKER._stat_identity(reparse)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_document_parent_junction_is_rejected(contract_root: Path) -> None:
    source = contract_root / "docs"
    target = contract_root / "junction-docs"
    source.replace(target)
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(source), str(target)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr.strip()}")

    raw, error = CHECKER._safe_read_bytes(contract_root, CHECKER.GUIDE_PATH)

    assert raw is None
    assert error is not None
    assert "REPARSE_DIRECTORY: docs" in error


def test_schema_drift_is_detected_even_when_json_is_valid(contract_root: Path) -> None:
    path = contract_root / CHECKER.SCHEMA_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    document["title"] = "drift"
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    errors = _errors(contract_root)

    assert any("HASH_DRIFT" in error for error in errors)
    assert (
        any("properties drifted" in error or "required fields drifted" in error for error in errors)
        is False
    )


def test_missing_contract_file_fails_closed(contract_root: Path) -> None:
    (contract_root / CHECKER.PILOT_PATH).unlink()

    assert any("MISSING_FILE" in error for error in _errors(contract_root))
