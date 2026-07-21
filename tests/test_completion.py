from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

from mclab.application.catalog import (
    CompletionRule as CatalogCompletionRule,
    ScenarioCatalog,
)
from mclab.completion import (
    COMPLETION_CONTRACT_VERSION,
    CompletionDecision,
    CompletionEvidence,
    CompletionReason,
    CompletionRecordKind,
    CompletionRule,
    InteractionEvidence,
    ObservationEvidence,
    completion_evidence_from_payloads,
    evaluate_completion,
    summarize_interaction_events,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "completion"
GOLDEN_CASES = FIXTURE_ROOT / "v1_cases.json"


def _fixture_inventory() -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(FIXTURE_ROOT).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(FIXTURE_ROOT.rglob("*"))
        if path.is_file()
    )


def _rule_from_case(payload: object) -> CompletionRule | None:
    if payload is None:
        return None
    assert isinstance(payload, dict)
    values = dict(payload)
    if "required_presets" in values:
        values["required_presets"] = tuple(values["required_presets"])
    return CompletionRule(**values)


class CompletionContractGoldenTests(unittest.TestCase):
    def test_v1_golden_cases_and_fixture_tree_are_immutable(self) -> None:
        inventory_before = _fixture_inventory()
        raw_before = GOLDEN_CASES.read_bytes()
        payload = json.loads(raw_before)
        payload_before = deepcopy(payload)

        self.assertEqual(payload["contract_version"], COMPLETION_CONTRACT_VERSION)
        for case in payload["cases"]:
            with self.subTest(case=case["id"]):
                evidence = completion_evidence_from_payloads(
                    case.get("manifest"),
                    expected_scenario_id="lab01.default",
                    plot_count=case.get("plot_count", 0),
                    interaction_events=case.get("events"),
                    legacy_summary=case.get("legacy_summary"),
                )
                decision = evaluate_completion(_rule_from_case(case.get("rule")), evidence)
                self.assertEqual(decision.to_dict(), case["expected"])

        self.assertEqual(payload, payload_before)
        self.assertEqual(GOLDEN_CASES.read_bytes(), raw_before)
        self.assertEqual(_fixture_inventory(), inventory_before)

    def test_required_and_available_truth_table_is_exhaustive(self) -> None:
        rule_cases = tuple(itertools.product((False, True), repeat=5))
        evidence_cases = tuple(itertools.product((False, True), repeat=5))
        evaluated = 0
        for required in rule_cases:
            rule = CompletionRule(
                requires_run=required[0],
                requires_plot=required[1],
                requires_learner_control=required[2],
                requires_observation=required[3],
                requires_prediction=required[4],
            )
            for available in evidence_cases:
                observations = (
                    (ObservationEvidence(has_prediction=available[4]),)
                    if available[3]
                    else ()
                )
                evidence = CompletionEvidence(
                    CompletionRecordKind.MANIFEST_V1,
                    status="completed" if available[0] else "stopped",
                    plot_count=int(available[1]),
                    interaction=InteractionEvidence(
                        learner_control_count=int(available[2]),
                        observations=observations,
                    ),
                )
                expected = all(
                    not needed or present
                    for needed, present in zip(
                        required,
                        (
                            available[0],
                            available[1],
                            available[2],
                            available[3],
                            available[3] and available[4],
                        ),
                        strict=True,
                    )
                )
                with self.subTest(required=required, available=available):
                    self.assertEqual(evaluate_completion(rule, evidence).complete, expected)
                evaluated += 1
        self.assertEqual(evaluated, 1024)

    def test_note_requires_prediction_and_note_on_the_same_marker(self) -> None:
        rule = CompletionRule(
            requires_observation=True,
            requires_prediction=True,
            requires_note=True,
        )
        cases = (
            ((), False),
            ((ObservationEvidence(has_prediction=True),), False),
            ((ObservationEvidence(has_note=True),), False),
            (
                (
                    ObservationEvidence(has_prediction=True),
                    ObservationEvidence(has_note=True),
                ),
                False,
            ),
            ((ObservationEvidence(has_prediction=True, has_note=True),), True),
        )
        for observations, expected in cases:
            evidence = CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=InteractionEvidence(observations=observations),
            )
            with self.subTest(observations=observations):
                self.assertEqual(evaluate_completion(rule, evidence).complete, expected)

    def test_note_only_rule_honors_its_independent_flag(self) -> None:
        decision = evaluate_completion(
            CompletionRule(requires_observation=True, requires_note=True),
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=InteractionEvidence(
                    observations=(ObservationEvidence(has_note=True),),
                ),
            ),
        )
        self.assertTrue(decision.complete)

    def test_each_qualifying_observation_needs_outcome_review(self) -> None:
        decision = evaluate_completion(
            CompletionRule(
                requires_observation=True,
                requires_prediction=True,
                requires_note=True,
            ),
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=InteractionEvidence(
                    observations=(
                        ObservationEvidence(
                            has_prediction=True,
                            has_note=True,
                            has_outcome=True,
                        ),
                        ObservationEvidence(has_prediction=True, has_note=True),
                    ),
                ),
            ),
        )
        self.assertTrue(decision.complete)
        self.assertTrue(decision.outcome_review_pending)

    def test_only_exact_completed_status_satisfies_a_run_requirement(self) -> None:
        rule = CompletionRule()
        for status in (None, "", "running", "stopped", "error", "unknown", "Completed", "completed "):
            evidence = CompletionEvidence(CompletionRecordKind.MANIFEST_V1, status=status)
            with self.subTest(status=status):
                decision = evaluate_completion(rule, evidence)
                self.assertFalse(decision.complete)
                self.assertEqual(decision.primary_reason, CompletionReason.RUN_NOT_COMPLETED)
        self.assertTrue(
            evaluate_completion(
                rule,
                CompletionEvidence(CompletionRecordKind.MANIFEST_V1, status="completed"),
            ).complete
        )

    def test_invalid_required_counts_fail_closed(self) -> None:
        plot_rule = CompletionRule(requires_plot=True)
        for count in (-1, True):
            evidence = CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                plot_count=count,
            )
            with self.subTest(count=count):
                self.assertEqual(
                    evaluate_completion(plot_rule, evidence).primary_reason,
                    CompletionReason.PLOT_MISSING,
                )

        invalid_interaction = InteractionEvidence(learner_control_count=-1)
        decision = evaluate_completion(
            CompletionRule(requires_learner_control=True),
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=invalid_interaction,
            ),
        )
        self.assertEqual(
            decision.primary_reason,
            CompletionReason.INTERACTION_EVIDENCE_INVALID,
        )

        malformed = CompletionEvidence(
            CompletionRecordKind.MANIFEST_V1,
            status="completed",
            interaction=None,  # type: ignore[arg-type]
        )
        self.assertTrue(evaluate_completion(CompletionRule(), malformed).complete)
        self.assertEqual(
            evaluate_completion(
                CompletionRule(requires_observation=True),
                malformed,
            ).primary_reason,
            CompletionReason.INTERACTION_EVIDENCE_INVALID,
        )

    def test_rule_and_decision_serialization_are_frozen_and_versioned(self) -> None:
        rule = CompletionRule()
        decision = evaluate_completion(
            rule,
            CompletionEvidence(CompletionRecordKind.MANIFEST_V1, status="completed"),
        )
        with self.assertRaises(FrozenInstanceError):
            rule.requires_run = False  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            decision.complete = False  # type: ignore[misc]
        self.assertIsInstance(decision, CompletionDecision)
        self.assertTrue(
            all(reason.value.startswith("completion.v1.") for reason in CompletionReason)
        )
        self.assertEqual(decision.to_dict()["contract_version"], 1)

    def test_invalid_rule_fails_closed(self) -> None:
        invalid_rule = CompletionRule(requires_run="yes")  # type: ignore[arg-type]
        decision = evaluate_completion(
            invalid_rule,
            CompletionEvidence(CompletionRecordKind.MANIFEST_V1, status="completed"),
        )
        self.assertEqual(decision.primary_reason, CompletionReason.RULE_INVALID)


class CompletionEvidenceNormalizationTests(unittest.TestCase):
    def test_manifest_shape_and_scenario_states_are_deterministic(self) -> None:
        cases = (
            (None, CompletionRecordKind.MISSING),
            ([], CompletionRecordKind.INVALID),
            ({}, CompletionRecordKind.UNSUPPORTED),
            (
                {"schema_version": True, "scenario_id": "lab01.default", "status": "completed"},
                CompletionRecordKind.UNSUPPORTED,
            ),
            (
                {"schema_version": 2, "scenario_id": "lab01.default", "status": "completed"},
                CompletionRecordKind.UNSUPPORTED,
            ),
            (
                {"schema_version": 1, "scenario_id": "", "status": "completed"},
                CompletionRecordKind.INVALID,
            ),
            (
                {"schema_version": 1, "scenario_id": "lab01.default", "status": None},
                CompletionRecordKind.INVALID,
            ),
            (
                {"schema_version": 1, "scenario_id": "lab02.default", "status": "completed"},
                CompletionRecordKind.SCENARIO_MISMATCH,
            ),
            (
                {"schema_version": 1, "scenario_id": "lab01.default", "status": "completed"},
                CompletionRecordKind.MANIFEST_V1,
            ),
        )
        for manifest, expected in cases:
            original = deepcopy(manifest)
            evidence = completion_evidence_from_payloads(
                manifest,
                expected_scenario_id="lab01.default",
            )
            with self.subTest(manifest=manifest):
                self.assertEqual(evidence.record_kind, expected)
                self.assertEqual(manifest, original)

    def test_legacy_summary_is_recognized_but_never_upgraded_or_rewritten(self) -> None:
        path = FIXTURE_ROOT / "legacy_summary.json"
        raw_before = path.read_bytes()
        summary = json.loads(raw_before)
        evidence = completion_evidence_from_payloads(
            None,
            expected_scenario_id="lab01.default",
            legacy_summary=summary,
        )
        decision = evaluate_completion(CompletionRule(), evidence)

        self.assertEqual(evidence.record_kind, CompletionRecordKind.LEGACY_SUMMARY)
        self.assertFalse(decision.complete)
        self.assertEqual(
            decision.primary_reason,
            CompletionReason.LEGACY_MANIFEST_MISSING,
        )
        self.assertEqual(path.read_bytes(), raw_before)

    def test_event_normalizer_counts_only_learner_controls(self) -> None:
        counted = (
            {"kind": "button", "name": "pull_mass"},
            {"kind": "slider", "name": "damping"},
            {"kind": "preset", "name": "soft_wall", "label": "Soft wall"},
        )
        ignored = (
            {"kind": "button", "name": "clear_observation_note"},
            {"kind": "button", "name": "pause_simulation"},
            {"kind": "button", "name": "resume_simulation"},
            {"kind": "button", "name": "step_simulation"},
            {"kind": "button", "name": "use_changed_values_note"},
            {"kind": "button", "name": "use_live_status_note"},
            {"kind": "slider", "name": "playback_speed"},
        )
        for event in counted:
            with self.subTest(event=event):
                self.assertEqual(summarize_interaction_events([event]).learner_control_count, 1)
        for event in ignored:
            with self.subTest(event=event):
                self.assertEqual(summarize_interaction_events([event]).learner_control_count, 0)

    def test_event_normalizer_preserves_marker_correlation_and_text_rules(self) -> None:
        events = [
            {
                "kind": "MARKER",
                "name": "Observation",
                "value": {"prediction": "  faster  ", "note": "  ", "outcome": "Matched"},
            },
            {
                "kind": "marker",
                "name": "observation",
                "value": {"prediction": " ", "note": "visible"},
            },
        ]
        evidence = summarize_interaction_events(events)

        self.assertTrue(evidence.valid)
        self.assertEqual(
            evidence.observations,
            (
                ObservationEvidence(has_prediction=True, has_note=False, has_outcome=True),
                ObservationEvidence(has_prediction=False, has_note=True, has_outcome=False),
            ),
        )
        self.assertFalse(summarize_interaction_events({}).valid)
        self.assertFalse(summarize_interaction_events([None]).valid)

    def test_malformed_observation_value_cannot_satisfy_observation_rule(self) -> None:
        interaction = summarize_interaction_events(
            [{"kind": "marker", "name": "observation", "value": []}]
        )
        decision = evaluate_completion(
            CompletionRule(requires_observation=True),
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=interaction,
            ),
        )
        self.assertFalse(interaction.valid)
        self.assertFalse(decision.complete)
        self.assertEqual(
            decision.primary_reason,
            CompletionReason.INTERACTION_EVIDENCE_INVALID,
        )

    def test_unknown_outcome_does_not_clear_review_pending(self) -> None:
        interaction = summarize_interaction_events(
            [
                {
                    "kind": "marker",
                    "name": "observation",
                    "value": {
                        "prediction": "Faster",
                        "note": "Visible",
                        "outcome": "arbitrary",
                    },
                }
            ]
        )
        decision = evaluate_completion(
            CompletionRule(
                requires_observation=True,
                requires_prediction=True,
                requires_note=True,
            ),
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                interaction=interaction,
            ),
        )
        self.assertTrue(decision.complete)
        self.assertTrue(decision.outcome_review_pending)


class CompletionCatalogContractTests(unittest.TestCase):
    def test_catalog_reexports_the_canonical_rule_without_consumer_wiring(self) -> None:
        self.assertIs(CatalogCompletionRule, CompletionRule)

    def test_current_catalog_declares_all_completion_requirements(self) -> None:
        scenarios = ScenarioCatalog.default().all()
        hands_on = tuple(
            scenario
            for scenario in scenarios
            if scenario.completion.requires_learner_control
            or scenario.completion.requires_observation
        )

        self.assertEqual(len(scenarios), 72)
        self.assertEqual(len(hands_on), 9)
        self.assertTrue(all(item.completion.requires_run for item in scenarios))
        self.assertTrue(all(item.completion.requires_plot for item in scenarios))
        self.assertTrue(all(item.completion.requires_prediction for item in hands_on))
        self.assertTrue(all(item.completion.requires_note for item in hands_on))
        self.assertTrue(
            all(
                not item.completion.requires_prediction and not item.completion.requires_note
                for item in scenarios
                if item not in hands_on
            )
        )
        wall = next(item for item in scenarios if item.id == "lab04.interactive-virtual-wall")
        self.assertEqual(
            wall.completion.required_presets,
            ("Close wall", "Back away", "Re-enter wall"),
        )


if __name__ == "__main__":
    unittest.main()
