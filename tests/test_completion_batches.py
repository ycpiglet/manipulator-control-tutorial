from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

from mclab.application.catalog import (
    ALL_BATCH_TARGET_ID,
    BATCH_TARGET_IDS,
    CONCRETE_BATCH_NAMES,
    CONCRETE_BATCH_TARGET_IDS,
    LEARNING_PATH_SCENARIO_IDS,
    LEARNING_PATH_TARGET_IDS,
    PREDICTION_CHECK_ARTIFACT_KEY,
    REPORT_ARTIFACT_KEY,
    WORKSHEET_ARTIFACT_KEY,
    ScenarioCatalog,
    stable_scenario_id,
)
from mclab.application.completion_progress import (
    assess_target_completion,
    build_completion_assessment_index,
)
from mclab.batch import BATCH_SETS
from mclab.completion import (
    COMPLETION_CONTRACT_VERSION,
    CompletionEvidence,
    CompletionReason,
    CompletionRecordKind,
    CompletionRule,
    completion_evidence_from_payloads,
    evaluate_completion,
)
from mclab.sim.logging import _scenario_id as writer_scenario_id


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "completion"
BATCH_CASES = FIXTURE_ROOT / "v1_batch_cases.json"
V1_CASES = FIXTURE_ROOT / "v1_cases.json"
V1_CASES_SHA256 = "1365e32c960af3efc2b13c32eb3029ad949743945f19e82eb0a76e5e02346951"


@dataclass(frozen=True)
class FakeCompletionRecord:
    name: str
    scenario_id: str
    completion_evidence: CompletionEvidence


class BatchCompletionFixtureTests(unittest.TestCase):
    def test_batch_cases_are_frozen_separately_from_the_v1_scenario_fixture(self) -> None:
        raw_before = BATCH_CASES.read_bytes()
        payload = json.loads(raw_before)
        payload_before = deepcopy(payload)
        catalog = ScenarioCatalog.default()

        self.assertEqual(payload["contract_version"], COMPLETION_CONTRACT_VERSION)
        for case in payload["cases"]:
            with self.subTest(case=case["id"]):
                target = catalog.get_batch(case["target_id"])
                evidence = completion_evidence_from_payloads(
                    {
                        "schema_version": 1,
                        "scenario_id": target.id,
                        "status": case["status"],
                    },
                    expected_scenario_id=target.id,
                    plot_count=case["plot_count"],
                    artifact_keys=tuple(case["artifact_keys"]),
                )
                self.assertEqual(
                    evaluate_completion(target.completion, evidence).to_dict(),
                    case["expected"],
                )

        self.assertEqual(payload, payload_before)
        self.assertEqual(BATCH_CASES.read_bytes(), raw_before)
        self.assertEqual(hashlib.sha256(V1_CASES.read_bytes()).hexdigest(), V1_CASES_SHA256)

    def test_required_artifacts_are_strict_logical_keys(self) -> None:
        rule = CompletionRule(required_artifacts=(REPORT_ARTIFACT_KEY,))
        complete = CompletionEvidence(
            CompletionRecordKind.MANIFEST_V1,
            status="completed",
            artifact_keys=(REPORT_ARTIFACT_KEY,),
        )
        missing = CompletionEvidence(
            CompletionRecordKind.MANIFEST_V1,
            status="completed",
            artifact_keys=("report.html",),
        )

        self.assertTrue(evaluate_completion(rule, complete).complete)
        self.assertEqual(
            evaluate_completion(rule, missing).primary_reason,
            CompletionReason.REQUIRED_ARTIFACT_MISSING,
        )
        invalid_rule = CompletionRule(required_artifacts=(" report",))
        self.assertEqual(
            evaluate_completion(invalid_rule, complete).primary_reason,
            CompletionReason.RULE_INVALID,
        )


class CatalogIdentityInvariantTests(unittest.TestCase):
    def test_all_scenario_and_writer_ids_use_the_public_helper(self) -> None:
        scenarios = ScenarioCatalog.default().all()

        self.assertEqual(len(scenarios), 72)
        self.assertEqual(len({item.id for item in scenarios}), 72)
        for scenario in scenarios:
            with self.subTest(scenario=scenario.id):
                self.assertEqual(
                    stable_scenario_id(scenario.lab_name, scenario.config_path),
                    scenario.id,
                )
                self.assertEqual(
                    writer_scenario_id(scenario.lab_name, Path(scenario.config_path)),
                    scenario.id,
                )

        writer_lab_names = {
            "lab01_msd": "lab01.default",
            "lab02_pid": "lab02.default",
            "lab03_trajectory": "lab03.default",
            "lab03_2dof": "lab03.joint-space-2dof",
            "lab04_panda": "lab04.neutral-hold",
        }
        config_paths = {
            "lab01_msd": "configs/lab01_msd/default.yaml",
            "lab02_pid": "configs/lab02_pid/default.yaml",
            "lab03_trajectory": "configs/lab03_trajectory/default.yaml",
            "lab03_2dof": "configs/lab03_2dof/joint_space_2dof.yaml",
            "lab04_panda": "configs/lab04_panda/neutral_hold.yaml",
        }
        for lab_name, expected in writer_lab_names.items():
            path = Path(config_paths[lab_name])
            with self.subTest(writer_lab=lab_name):
                self.assertEqual(stable_scenario_id(lab_name, path), expected)
                self.assertEqual(writer_scenario_id(lab_name, path), expected)

    def test_batch_registry_has_six_ids_and_54_resolved_scenario_children(self) -> None:
        catalog = ScenarioCatalog.default()
        batches = catalog.batches()
        concrete = batches[:-1]
        scenario_ids = {item.id for item in catalog.all()}

        self.assertEqual(tuple(item.id for item in batches), BATCH_TARGET_IDS)
        self.assertEqual(len(batches), 6)
        self.assertEqual(sum(len(item.child_target_ids) for item in concrete), 54)
        self.assertEqual(
            len({child for batch in concrete for child in batch.child_target_ids}),
            54,
        )
        self.assertTrue(
            all(child in scenario_ids for batch in concrete for child in batch.child_target_ids)
        )
        for batch_name, definition in zip(CONCRETE_BATCH_NAMES, concrete, strict=True):
            with self.subTest(batch=batch_name):
                self.assertEqual(
                    definition.child_target_ids,
                    tuple(
                        stable_scenario_id(item.lab_name, item.config_path)
                        for item in BATCH_SETS[batch_name]
                    ),
                )
        self.assertEqual(batches[-1].id, ALL_BATCH_TARGET_ID)
        self.assertEqual(batches[-1].child_target_ids, CONCRETE_BATCH_TARGET_IDS)
        self.assertEqual(catalog.integrity_errors(), [])

    def test_batch_rules_require_only_published_review_evidence(self) -> None:
        batches = ScenarioCatalog.default().batches()
        concrete_rule = CompletionRule(
            requires_plot=True,
            required_artifacts=(
                REPORT_ARTIFACT_KEY,
                WORKSHEET_ARTIFACT_KEY,
                PREDICTION_CHECK_ARTIFACT_KEY,
            ),
        )
        self.assertTrue(all(item.completion == concrete_rule for item in batches[:-1]))
        self.assertEqual(
            batches[-1].completion,
            CompletionRule(
                required_artifacts=(
                    REPORT_ARTIFACT_KEY,
                    WORKSHEET_ARTIFACT_KEY,
                    *CONCRETE_BATCH_TARGET_IDS,
                ),
            ),
        )
        self.assertFalse(batches[-1].completion.requires_plot)

    def test_course_path_has_12_stable_target_ids_without_breaking_scenario_api(self) -> None:
        catalog = ScenarioCatalog.default()

        self.assertEqual(len(LEARNING_PATH_TARGET_IDS), 12)
        self.assertEqual(len(set(LEARNING_PATH_TARGET_IDS)), 12)
        self.assertEqual(LEARNING_PATH_TARGET_IDS[-1], ALL_BATCH_TARGET_ID)
        self.assertEqual(
            tuple(item.id for item in catalog.learning_path_targets()),
            LEARNING_PATH_TARGET_IDS,
        )
        self.assertEqual(
            tuple(item.id for item in catalog.learning_path()),
            LEARNING_PATH_SCENARIO_IDS,
        )


class HistoricalCompletionAssessmentTests(unittest.TestCase):
    def test_newest_diagnostics_do_not_erase_older_independent_credit(self) -> None:
        target = ScenarioCatalog.default().get("lab01.default")
        newest = FakeCompletionRecord(
            "newest-incomplete",
            target.id,
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                plot_count=0,
            ),
        )
        older = FakeCompletionRecord(
            "older-complete",
            target.id,
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                plot_count=1,
            ),
        )

        assessment = assess_target_completion(target, (newest, older))

        self.assertTrue(assessment.complete)
        self.assertIs(assessment.latest_record, newest)
        self.assertEqual(assessment.latest_decision.primary_reason, CompletionReason.PLOT_MISSING)
        self.assertIs(assessment.credited_record, older)
        self.assertTrue(assessment.credited_decision.complete)  # type: ignore[union-attr]
        with self.assertRaises(FrozenInstanceError):
            assessment.complete = False  # type: ignore[misc]

    def test_evidence_from_different_runs_is_never_combined(self) -> None:
        target = ScenarioCatalog.default().get_batch("batch.lab01_msd_compare")
        plot_only = FakeCompletionRecord(
            "plot-only",
            target.id,
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                plot_count=1,
            ),
        )
        review_only = FakeCompletionRecord(
            "review-only",
            target.id,
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                artifact_keys=target.completion.required_artifacts,
            ),
        )

        assessment = assess_target_completion(target, (plot_only, review_only))

        self.assertFalse(assessment.complete)
        self.assertIsNone(assessment.credited_record)
        self.assertEqual(
            assessment.latest_decision.primary_reason,
            CompletionReason.REQUIRED_ARTIFACT_MISSING,
        )

    def test_index_ignores_unrelated_records_and_exposes_completed_ids(self) -> None:
        catalog = ScenarioCatalog.default()
        first, second = catalog.learning_path_targets()[:2]
        complete = FakeCompletionRecord(
            "first-complete",
            first.id,
            CompletionEvidence(
                CompletionRecordKind.MANIFEST_V1,
                status="completed",
                plot_count=1,
            ),
        )

        index = build_completion_assessment_index((first, second), (complete,))

        self.assertEqual(index.completed_target_ids, frozenset({first.id}))
        self.assertTrue(index.get(first.id).complete)
        self.assertFalse(index.get(second.id).complete)
        self.assertEqual(
            index.get(second.id).latest_decision.primary_reason,
            CompletionReason.MANIFEST_MISSING,
        )
        with self.assertRaisesRegex(KeyError, "unknown-target"):
            index.get("unknown-target")


if __name__ == "__main__":
    unittest.main()
