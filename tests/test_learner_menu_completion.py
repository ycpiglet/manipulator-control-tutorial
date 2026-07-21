from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mclab.application.catalog import (
    BATCH_TARGET_IDS,
    CONCRETE_BATCH_TARGET_IDS,
    ScenarioCatalog,
)
from mclab.application.repositories import ArtifactRecord, ArtifactRepository
from mclab.completion import (
    CompletionEvidence,
    CompletionRecordKind,
    InteractionEvidence,
    ObservationEvidence,
)
from mclab.learner_menu import (
    BATCH_ACTIONS,
    LEARNING_PATH,
    MENU_ACTIONS,
    _action_completion_assessment,
    _review_queue_items,
    action_mission_evidence_text,
    completion_target_id,
    experience_coverage_next_target,
    experience_coverage_status_text,
    experience_coverage_summary_text,
    learning_path_progress,
    learning_path_progress_items,
    learning_path_progress_text,
    learning_path_summary_text,
    learning_path_target,
    next_learning_path_step,
)


def _record(
    root: Path,
    name: str,
    scenario_id: str,
    evidence: CompletionEvidence,
    *,
    plot_names: tuple[str, ...] = (),
    worksheet: bool = False,
    report: bool = False,
) -> ArtifactRecord:
    path = root / name
    path.mkdir()
    return ArtifactRecord(
        path=path,
        scenario_id=scenario_id,
        status=evidence.status or "invalid",
        size_bytes=0,
        replay_available=False,
        rerun_available=False,
        tuned_available=False,
        legacy=evidence.record_kind == CompletionRecordKind.LEGACY_SUMMARY,
        replay_reason="not tested",
        summary={},
        cleanup_token=name,
        manifest={},
        marker_name="manifest.json",
        completion_evidence=evidence,
        interaction_events=(),
        plot_paths=tuple(path / "plots" / plot_name for plot_name in plot_names),
        worksheet_available=worksheet,
        report_available=report,
        artifact_validation_errors=(),
        finished_at="",
        sort_timestamp=0.0,
    )


def _automatic_evidence(*, status: str = "completed", plot_count: int = 1) -> CompletionEvidence:
    return CompletionEvidence(
        CompletionRecordKind.MANIFEST_V1,
        status=status,
        plot_count=plot_count,
    )


def _hands_on_evidence(
    *,
    preset_labels: tuple[str, ...] = (),
    learner_controls: int = 1,
    observations: tuple[ObservationEvidence, ...] | None = None,
) -> CompletionEvidence:
    return CompletionEvidence(
        CompletionRecordKind.MANIFEST_V1,
        status="completed",
        plot_count=1,
        interaction=InteractionEvidence(
            learner_control_count=learner_controls,
            observations=(
                observations
                if observations is not None
                else (
                    ObservationEvidence(
                        has_prediction=True,
                        has_note=True,
                        has_outcome=True,
                    ),
                )
            ),
            preset_labels=preset_labels,
        ),
    )


def _complete_evidence_for_target(target: object) -> CompletionEvidence:
    rule = target.completion  # type: ignore[attr-defined]
    observations = (
        (
            ObservationEvidence(
                has_prediction=rule.requires_prediction,
                has_note=rule.requires_note,
                has_outcome=True,
            ),
        )
        if rule.requires_observation
        else ()
    )
    return CompletionEvidence(
        CompletionRecordKind.MANIFEST_V1,
        status="completed",
        plot_count=int(rule.requires_plot),
        interaction=InteractionEvidence(
            learner_control_count=int(rule.requires_learner_control),
            observations=observations,
            preset_labels=rule.required_presets,
        ),
        artifact_keys=rule.required_artifacts,
    )


class LearnerMenuCanonicalCompletionTests(unittest.TestCase):
    def test_all_72_scenarios_and_six_batches_map_to_catalog_targets(self) -> None:
        catalog = ScenarioCatalog.default()
        scenario_ids = tuple(completion_target_id(action) for action in MENU_ACTIONS)
        batch_ids = tuple(completion_target_id(action) for action in BATCH_ACTIONS)

        self.assertEqual(len(scenario_ids), 72)
        self.assertEqual(len(set(scenario_ids)), 72)
        self.assertEqual(scenario_ids, tuple(item.id for item in catalog.all()))
        self.assertEqual(len(batch_ids), 6)
        self.assertEqual(set(batch_ids), set(BATCH_TARGET_IDS))
        self.assertEqual(batch_ids[0], "batch.all")
        self.assertTrue(all(catalog.get_target(target_id) for target_id in (*scenario_ids, *batch_ids)))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = tuple(
                _record(
                    root,
                    f"target-{index}",
                    target.id,
                    _complete_evidence_for_target(target),
                )
                for index, target in enumerate(catalog.targets())
            )
            for action in (*MENU_ACTIONS, *BATCH_ACTIONS):
                with self.subTest(action=completion_target_id(action)):
                    self.assertTrue(
                        _action_completion_assessment(action, catalog, records).complete
                    )

    def test_older_complete_credit_survives_newest_incomplete_diagnostics(self) -> None:
        first_step = LEARNING_PATH[0]
        action = learning_path_target(first_step)
        target_id = completion_target_id(action)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            newest = _record(
                root,
                "newest-stopped",
                target_id,
                _automatic_evidence(status="stopped"),
                plot_names=("position.png",),
            )
            older = _record(
                root,
                "older-complete",
                target_id,
                _automatic_evidence(),
                plot_names=("position.png",),
            )
            with patch.object(ArtifactRepository, "list_runs", return_value=(newest, older)):
                progress = learning_path_progress(first_step, root)
                items = learning_path_progress_items(root)
                text = learning_path_progress_text(first_step, progress)
                summary = learning_path_summary_text(items)

        self.assertTrue(progress.completed)
        self.assertFalse(progress.latest_complete)
        self.assertEqual(progress.latest_output, newest.path)
        self.assertEqual(progress.credited_output, older.path)
        self.assertIn("credited older-complete", text)
        self.assertIn("latest newest-stopped: Run not completed", text)
        self.assertEqual(next_learning_path_step(items), LEARNING_PATH[1])
        self.assertIn("Progress: 1/12 complete", summary)
        self.assertIn("Latest-attempt repair: 1 credited step", summary)

    def test_two_incomplete_runs_never_combine_hands_on_evidence(self) -> None:
        step = LEARNING_PATH[1]
        target_id = completion_target_id(learning_path_target(step))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation_only = _record(
                root,
                "newest-observation-only",
                target_id,
                _hands_on_evidence(learner_controls=0),
                plot_names=("position.png",),
            )
            control_only = _record(
                root,
                "older-control-only",
                target_id,
                _hands_on_evidence(observations=()),
                plot_names=("position.png",),
            )
            with patch.object(
                ArtifactRepository,
                "list_runs",
                return_value=(observation_only, control_only),
            ):
                progress = learning_path_progress(step, root)

        self.assertFalse(progress.completed)
        self.assertEqual(progress.latest_status, "Needs learner control")
        self.assertEqual(progress.observation_markers, 1)
        self.assertEqual(progress.learner_controls, 0)

    def test_wall_required_presets_are_evaluated_in_canonical_order(self) -> None:
        step = next(
            item
            for item in LEARNING_PATH
            if completion_target_id(learning_path_target(item))
            == "lab04.interactive-virtual-wall"
        )
        target_id = completion_target_id(learning_path_target(step))
        cases = (
            ((), "Close wall", False),
            (("Close wall",), "Back away", False),
            (("Close wall", "Re-enter wall"), "Back away", False),
            (("Close wall", "Back away"), "Re-enter wall", False),
            (("Close wall", "Back away", "Re-enter wall"), "", True),
        )
        for index, (labels, next_required, complete) in enumerate(cases):
            with self.subTest(labels=labels), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                record = _record(
                    root,
                    f"wall-{index}",
                    target_id,
                    _hands_on_evidence(preset_labels=labels),
                    plot_names=("wall_target.png",),
                )
                with patch.object(ArtifactRepository, "list_runs", return_value=(record,)):
                    progress = learning_path_progress(step, root)

            self.assertEqual(progress.completed, complete)
            self.assertEqual(progress.next_required_preset, next_required)

    def test_legacy_invalid_future_and_malformed_evidence_are_incomplete(self) -> None:
        step = LEARNING_PATH[0]
        action = learning_path_target(step)
        target_id = completion_target_id(action)
        cases = (
            (CompletionRecordKind.LEGACY_SUMMARY, "Legacy manifest incomplete"),
            (CompletionRecordKind.INVALID, "Invalid manifest"),
            (CompletionRecordKind.UNSUPPORTED, "Unsupported manifest schema"),
            (CompletionRecordKind.SCENARIO_MISMATCH, "Scenario mismatch"),
        )
        for index, (kind, expected_status) in enumerate(cases):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                record = _record(
                    root,
                    f"invalid-{index}",
                    target_id,
                    CompletionEvidence(kind),
                )
                with patch.object(ArtifactRepository, "list_runs", return_value=(record,)):
                    progress = learning_path_progress(step, root)
                    mission = action_mission_evidence_text(action, root)

            self.assertFalse(progress.completed)
            self.assertEqual(progress.latest_status, expected_status)
            self.assertEqual(mission, f"Mission evidence: {expected_status}")

    def test_coverage_only_counts_independently_complete_catalog_targets(self) -> None:
        intro_id = "lab01.default"
        hands_on_id = "lab01.interactive-pull"
        batch_id = "batch.lab01_msd_compare"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intro = _record(root, "intro", intro_id, _automatic_evidence())
            incomplete_hands_on = _record(
                root,
                "hands-on-control-only",
                hands_on_id,
                _hands_on_evidence(observations=()),
            )
            batch = _record(
                root,
                "compare",
                batch_id,
                CompletionEvidence(
                    CompletionRecordKind.MANIFEST_V1,
                    status="completed",
                    plot_count=1,
                    artifact_keys=("report", "worksheet", "prediction-check"),
                ),
                worksheet=True,
                report=True,
            )
            with patch.object(
                ArtifactRepository,
                "list_runs",
                return_value=(batch, incomplete_hands_on, intro),
            ):
                summary = experience_coverage_summary_text(root)
                status = experience_coverage_status_text(root)
                next_target = experience_coverage_next_target(root)

        self.assertIn("Experience coverage: 2/7 types tried", summary)
        self.assertIn("Intro basics: Done", status)
        self.assertIn("Hands-on controls: Next", status)
        self.assertIn("Comparison batch: Done", status)
        self.assertIsNotNone(next_target)
        self.assertEqual(completion_target_id(next_target), hands_on_id)  # type: ignore[arg-type]

    def test_review_queue_status_and_bucket_come_from_each_canonical_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = _record(root, "ready", "lab01.default", _automatic_evidence())
            needs_plot = _record(
                root,
                "needs-plot",
                "lab01.default",
                _automatic_evidence(plot_count=0),
            )
            wall = _record(
                root,
                "wall-needs-close",
                "lab04.interactive-virtual-wall",
                _hands_on_evidence(),
            )
            legacy = _record(
                root,
                "legacy",
                "lab01.default",
                CompletionEvidence(CompletionRecordKind.LEGACY_SUMMARY),
            )
            future = _record(
                root,
                "future",
                "lab01.default",
                CompletionEvidence(CompletionRecordKind.UNSUPPORTED),
            )
            unknown = _record(
                root,
                "unknown",
                "external.target",
                _automatic_evidence(),
            )
            with patch.object(
                ArtifactRepository,
                "list_runs",
                return_value=(ready, needs_plot, wall, legacy, future, unknown),
            ):
                items = _review_queue_items(root)

        status_buckets = {(path.name, status, bucket) for path, status, bucket, _ in items}
        self.assertIn(("ready", "Artifacts ready", "ready"), status_buckets)
        self.assertIn(("needs-plot", "Needs plot", "artifact"), status_buckets)
        self.assertIn(
            ("wall-needs-close", "Needs required preset Close wall", "preset"),
            status_buckets,
        )
        self.assertIn(("legacy", "Legacy manifest incomplete", "other"), status_buckets)
        self.assertIn(("future", "Unsupported manifest schema", "other"), status_buckets)
        self.assertIn(("unknown", "Completion rule unavailable", "other"), status_buckets)

    def test_batch_all_mission_requires_no_parent_plot_but_all_child_keys(self) -> None:
        action = BATCH_ACTIONS[0]
        target_id = completion_target_id(action)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            complete = _record(
                root,
                "all-complete",
                target_id,
                CompletionEvidence(
                    CompletionRecordKind.MANIFEST_V1,
                    status="completed",
                    plot_count=0,
                    artifact_keys=("report", "worksheet", *CONCRETE_BATCH_TARGET_IDS),
                ),
                worksheet=True,
                report=True,
            )
            with patch.object(ArtifactRepository, "list_runs", return_value=(complete,)):
                mission = action_mission_evidence_text(action, root)

        self.assertEqual(
            mission,
            "Mission evidence: Course artifacts ready; worksheet worksheet.md",
        )


if __name__ == "__main__":
    unittest.main()
