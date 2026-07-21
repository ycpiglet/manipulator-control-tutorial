from __future__ import annotations

import json
import hashlib
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import mclab.output_inventory as output_inventory
from mclab.application.artifacts import verify_manifest, write_manifest
from mclab.application.catalog import (
    CONCRETE_BATCH_NAMES,
    CONCRETE_BATCH_TARGET_IDS,
)
from mclab.application.repositories import ArtifactRecord, ArtifactRepository
from mclab.completion import CompletionRecordKind, CompletionRule
from mclab.output_inventory import (
    InvalidInteractionEvents,
    read_completion_run_snapshot_rooted,
    validate_completion_manifest_v1,
)
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import MAX_METADATA_BYTES, CleanupSafetyError


class CompletionInventoryTests(unittest.TestCase):
    def test_artifact_record_preserves_the_pre_completion_constructor(self) -> None:
        record = ArtifactRecord(
            Path("legacy-constructor"),
            "lab01.default",
            "completed",
            1,
            False,
            True,
            False,
            False,
            "",
            {},
            "token",
        )

        self.assertEqual(
            record.completion_evidence.record_kind,
            CompletionRecordKind.MISSING,
        )
        self.assertEqual(record.plot_paths, ())
        self.assertFalse(record.report_available)

    def test_repository_exposes_one_trusted_completion_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            events = [
                {"kind": "preset", "name": "soft", "label": "Soft"},
                {
                    "kind": "marker",
                    "name": "observation",
                    "value": {"prediction": "less overshoot", "note": "settled"},
                },
            ]
            run = self._write_run(
                root,
                "valid-run",
                events=json.dumps(events).encode(),
                plot=b"published plot",
                worksheet=b"# Worksheet\n\n## Prediction Check\n",
                report=b"<html>report</html>",
                started_at="2026-07-21T09:00:00+09:00",
                finished_at="2026-07-21T09:30:00+09:00",
            )

            record = ArtifactRepository(root).list_runs()[0]

        self.assertEqual(record.path, run)
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.marker_name, "manifest.json")
        self.assertEqual(record.finished_at, "2026-07-21T00:30:00+00:00")
        self.assertEqual(record.completion_evidence.record_kind, CompletionRecordKind.MANIFEST_V1)
        self.assertEqual(record.completion_evidence.plot_count, 1)
        self.assertTrue(record.completion_evidence.interaction.valid)
        self.assertEqual(record.completion_evidence.interaction.learner_control_count, 1)
        self.assertEqual(record.interaction_events, events)
        self.assertEqual(record.plot_paths, (run / "plots" / "position.png",))
        self.assertTrue(record.worksheet_available)
        self.assertTrue(record.report_available)
        self.assertEqual(
            record.completion_evidence.artifact_keys,
            ("report", "worksheet", "prediction-check"),
        )
        self.assertEqual(record.artifact_validation_errors, ())

    def test_repository_bounds_root_entries_before_materializing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("one", "two", "three"):
                (root / name).mkdir()

            with patch(
                "mclab.application.repositories.MAX_OUTPUT_ROOT_ENTRIES",
                2,
            ):
                records = ArtifactRepository(root).list_runs()

        self.assertEqual(records, ())

    def test_bounded_name_listing_consumes_only_the_limit_plus_one(self) -> None:
        class FakeEntry:
            def __init__(self, name: str) -> None:
                self.name = name

        class FakeScandir:
            def __init__(self) -> None:
                self.consumed = 0

            def __enter__(self) -> FakeScandir:
                return self

            def __exit__(self, *_exc_info: object) -> None:
                return None

            def __iter__(self):
                for index in range(100):
                    self.consumed += 1
                    yield FakeEntry(f"entry-{index}")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fake_scandir = FakeScandir()
            with pinned_output_root(root, allowed_root=root) as (
                _display_root,
                _root_exists,
                root_pin,
            ):
                assert root_pin is not None
                with (
                    patch("mclab.output_root.os.scandir", return_value=fake_scandir),
                    self.assertRaises(CleanupSafetyError),
                ):
                    root_pin.list_names(max_entries=2)

        self.assertEqual(fake_scandir.consumed, 3)

    def test_repository_streams_run_tree_instead_of_materializing_each_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._write_run(root, "streamed", plot=b"plot")
            real_list_names = PinnedOutputRoot.list_names
            calls: list[tuple[tuple[str, ...], int | None]] = []

            def bounded_root_only(
                root_pin: PinnedOutputRoot,
                relative: tuple[str, ...] = (),
                *,
                max_entries: int | None = None,
            ) -> tuple[str, ...]:
                calls.append((relative, max_entries))
                if relative:
                    raise AssertionError("run tree was materialized through list_names")
                return real_list_names(
                    root_pin,
                    relative,
                    max_entries=max_entries,
                )

            with patch.object(PinnedOutputRoot, "list_names", bounded_root_only):
                records = ArtifactRepository(root).list_runs()

        self.assertEqual([record.path.name for record in records], ["streamed"])
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(calls[0][1])

    def test_completion_snapshot_has_a_cumulative_content_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = self._write_run(root, "budgeted", plot=b"plot")
            trusted_files = (
                run / "manifest.json",
                run / "summary.json",
                run / "plots" / "position.png",
            )
            aggregate_size = sum(path.stat().st_size for path in trusted_files)
            self.assertGreater(
                aggregate_size - 1,
                max(path.stat().st_size for path in trusted_files),
            )

            with patch.object(
                output_inventory,
                "MAX_COMPLETION_SNAPSHOT_BYTES",
                aggregate_size - 1,
            ):
                records = ArtifactRepository(root).list_runs()

        self.assertEqual(records, ())

    def test_same_length_in_place_overwrite_cannot_survive_snapshot_commit(self) -> None:
        artifact_names = (
            "summary.json",
            "interaction_events.json",
            "plots/position.png",
            "worksheet.md",
            "report.html",
        )
        for artifact_name in artifact_names:
            with self.subTest(artifact=artifact_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                run = self._write_run(
                    root,
                    "victim",
                    events=b'[{"kind":"button","name":"pull"}]',
                    plot=b"published plot",
                    worksheet=b"# Worksheet\n\n## Prediction Check\n",
                    report=b"<html>report</html>",
                )
                target = run.joinpath(*PurePosixPath(artifact_name).parts)
                original_size = target.stat().st_size
                real_reader = output_inventory.read_json_mapping_rooted
                manifest_reads = 0
                overwritten = False

                def overwrite_after_final_marker(
                    *args: object,
                    **kwargs: object,
                ) -> object:
                    nonlocal manifest_reads, overwritten
                    result = real_reader(*args, **kwargs)
                    relative = tuple(args[1])
                    if relative == (run.name, "manifest.json"):
                        manifest_reads += 1
                        if manifest_reads == 2:
                            target.write_bytes(b"X" * original_size)
                            overwritten = True
                    return result

                with patch.object(
                    output_inventory,
                    "read_json_mapping_rooted",
                    overwrite_after_final_marker,
                ):
                    records = ArtifactRepository(root).list_runs()

                self.assertTrue(overwritten)
                self.assertEqual(target.stat().st_size, original_size)
                self.assertEqual(records, ())

    def test_manifest_shape_is_fully_validated_before_evidence_is_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            invalid = self._write_run(root, "invalid", plot=b"plot")
            invalid_manifest = json.loads((invalid / "manifest.json").read_text(encoding="utf-8"))
            invalid_manifest.pop("runtime")
            (invalid / "manifest.json").write_text(
                json.dumps(invalid_manifest), encoding="utf-8"
            )

            future = self._write_run(root, "future", plot=b"plot")
            future_manifest = json.loads((future / "manifest.json").read_text(encoding="utf-8"))
            future_manifest["schema_version"] = 2
            (future / "manifest.json").write_text(json.dumps(future_manifest), encoding="utf-8")

            records = {item.path.name: item for item in ArtifactRepository(root).list_runs()}

        self.assertEqual(
            records["invalid"].completion_evidence.record_kind,
            CompletionRecordKind.INVALID,
        )
        self.assertEqual(records["invalid"].completion_evidence.plot_count, 0)
        self.assertFalse(records["invalid"].worksheet_available)
        self.assertIn("manifest runtime is invalid", records["invalid"].artifact_validation_errors)
        self.assertEqual(
            records["future"].completion_evidence.record_kind,
            CompletionRecordKind.UNSUPPORTED,
        )
        self.assertEqual(records["future"].completion_evidence.plot_count, 0)

    def test_schema_one_validator_rejects_every_invalid_required_section(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = self._write_run(root, "source", plot=b"plot")
            valid = json.loads((run / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(
            validate_completion_manifest_v1(valid).record_kind,
            CompletionRecordKind.MANIFEST_V1,
        )
        mutations = {
            "unknown status": lambda item: item.__setitem__("status", "unknown"),
            "missing start": lambda item: item.pop("started_at"),
            "naive finish": lambda item: item.__setitem__(
                "finished_at", "2026-07-21T00:01:00"
            ),
            "backward time": lambda item: item.__setitem__(
                "finished_at", "2026-07-20T00:01:00+00:00"
            ),
            "missing config path": lambda item: item["config"].pop("path"),
            "boolean seed": lambda item: item["config"].__setitem__("seed", True),
            "missing runtime": lambda item: item.pop("runtime"),
            "bad model digest": lambda item: item["model"].__setitem__("sha256", "bad"),
            "unsafe artifact path": lambda item: item.__setitem__(
                "artifacts", {"../plot.png": "0" * 64}
            ),
            "bad artifact digest": lambda item: item.__setitem__(
                "artifacts", {"plots/plot.png": "bad"}
            ),
            "bad replay": lambda item: item["replay"].__setitem__("available", 1),
            "bad run kind": lambda item: item.__setitem__("run_kind", 1),
            "bad error": lambda item: item.__setitem__("error", []),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                payload = deepcopy(valid)
                mutate(payload)
                self.assertEqual(
                    validate_completion_manifest_v1(payload).record_kind,
                    CompletionRecordKind.INVALID,
                )

        future = deepcopy(valid)
        future["schema_version"] = 2
        self.assertEqual(
            validate_completion_manifest_v1(future).record_kind,
            CompletionRecordKind.UNSUPPORTED,
        )

    def test_absent_and_malformed_interaction_artifacts_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._write_run(root, "absent")
            self._write_run(root, "malformed", events=b"{")
            self._write_run(root, "wrong-shape", events=json.dumps({"kind": "button"}).encode())
            mixed_events = [{"kind": "button", "name": "pull"}, "not-an-object"]
            self._write_run(root, "mixed", events=json.dumps(mixed_events).encode())
            changed = self._write_run(
                root,
                "digest-mismatch",
                events=json.dumps([{"kind": "button", "name": "pull"}]).encode(),
            )
            (changed / "interaction_events.json").write_text("[]", encoding="utf-8")
            self._write_run(
                root,
                "oversized",
                events=b"[" + (b" " * MAX_METADATA_BYTES) + b"]",
            )

            records = {item.path.name: item for item in ArtifactRepository(root).list_runs()}

        self.assertIsNone(records["absent"].interaction_events)
        self.assertTrue(records["absent"].completion_evidence.interaction.valid)
        for name in ("malformed", "wrong-shape", "digest-mismatch", "oversized"):
            with self.subTest(name=name):
                self.assertIsInstance(records[name].interaction_events, InvalidInteractionEvents)
                self.assertFalse(records[name].completion_evidence.interaction.valid)
        self.assertEqual(records["mixed"].interaction_events, mixed_events)
        self.assertFalse(records["mixed"].completion_evidence.interaction.valid)

    def test_deeply_nested_json_fails_closed_without_crashing_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            nested_manifest = self._write_run(root, "nested-manifest")
            manifest_text = (nested_manifest / "manifest.json").read_text(encoding="utf-8")
            (nested_manifest / "manifest.json").write_text(
                manifest_text.rstrip()[:-1]
                + ', "nested": '
                + "[" * 1_200
                + "0"
                + "]" * 1_200
                + "}",
                encoding="utf-8",
            )
            nested_events = b"[" * 1_200 + b"0" + b"]" * 1_200
            self._write_run(root, "nested-events", events=nested_events)

            records = ArtifactRepository(root).list_runs()

        self.assertEqual([record.path.name for record in records], ["nested-events"])
        self.assertIsInstance(records[0].interaction_events, InvalidInteractionEvents)
        self.assertFalse(records[0].completion_evidence.interaction.valid)

    def test_schema_one_summary_requires_its_published_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = self._write_run(root, "tampered-summary")
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "lab_name": "batch_group",
                        "duration": 999_999,
                        "child_batches": 999,
                    }
                ),
                encoding="utf-8",
            )

            record = ArtifactRepository(root).list_runs()[0]

        self.assertEqual(record.summary, {})
        self.assertIn(
            "summary.json does not match its manifest digest",
            record.artifact_validation_errors,
        )

    @unittest.skipIf(os.name == "nt", "Windows directory leases prevent this POSIX rename probe")
    def test_run_directory_swap_cannot_inject_interaction_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / "run"
            replacement = root / "replacement"
            original.mkdir()
            replacement.mkdir()
            events = [{"kind": "button", "name": "pull"}]
            (replacement / "interaction_events.json").write_text(
                json.dumps(events),
                encoding="utf-8",
            )
            manifest = write_manifest(
                replacement,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
            )
            shutil.copy2(manifest, original / "manifest.json")
            real_reader = output_inventory._read_interaction_events_rooted

            def swapped_reader(
                root_pin: PinnedOutputRoot,
                relative_root: tuple[str, ...],
                artifacts: dict[str, str],
            ) -> tuple[object, str]:
                hold = root / "hold"
                original.rename(hold)
                replacement.rename(original)
                try:
                    return real_reader(root_pin, relative_root, artifacts)
                finally:
                    original.rename(replacement)
                    hold.rename(original)

            with pinned_output_root(root, allowed_root=root) as (
                _display_root,
                root_exists,
                root_pin,
            ):
                self.assertTrue(root_exists)
                assert root_pin is not None
                with patch.object(
                    output_inventory,
                    "_read_interaction_events_rooted",
                    swapped_reader,
                ):
                    snapshot = read_completion_run_snapshot_rooted(root_pin, original.name)

        self.assertIsInstance(snapshot.interaction_events, InvalidInteractionEvents)
        self.assertEqual(snapshot.completion_evidence.interaction.learner_control_count, 0)
        self.assertFalse((original / "interaction_events.json").exists())

    def test_interaction_reader_rejects_a_manifest_published_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            external = root / "external-events.json"
            external.write_text("[]", encoding="utf-8")
            run = root / "linked-events"
            run.mkdir()
            try:
                (run / "interaction_events.json").symlink_to(external)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem symlink fixture is unavailable")
            manifest = write_manifest(
                run,
                scenario_id="lab01.default",
                status="completed",
                config={"sim_time": 1.0},
            )
            # The producer now refuses to publish links.  Craft the malicious
            # manifest entry explicitly so this remains a reader-side probe.
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertNotIn("interaction_events.json", payload["artifacts"])
            payload["artifacts"]["interaction_events.json"] = hashlib.sha256(
                external.read_bytes()
            ).hexdigest()
            manifest.write_text(json.dumps(payload), encoding="utf-8")

            with pinned_output_root(root, allowed_root=root) as (
                _display_root,
                root_exists,
                root_pin,
            ):
                self.assertTrue(root_exists)
                assert root_pin is not None
                snapshot = read_completion_run_snapshot_rooted(root_pin, run.name)

        self.assertIsInstance(snapshot.interaction_events, InvalidInteractionEvents)
        self.assertFalse(snapshot.completion_evidence.interaction.valid)
        self.assertTrue(snapshot.artifact_validation_errors)

    def test_only_published_regular_digest_matching_plots_are_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            valid = self._write_run(root, "valid", plot=b"valid")

            unpublished = self._write_run(root, "unpublished")
            (unpublished / "plots").mkdir()
            (unpublished / "plots" / "position.png").write_bytes(b"late")

            missing = self._write_run(root, "missing", plot=b"published")
            (missing / "plots" / "position.png").unlink()

            mismatch = self._write_run(root, "mismatch", plot=b"before")
            (mismatch / "plots" / "position.png").write_bytes(b"after")

            records = {item.path.name: item for item in ArtifactRepository(root).list_runs()}

        self.assertEqual(records["valid"].completion_evidence.plot_count, 1)
        self.assertEqual(records["valid"].plot_paths, (valid / "plots" / "position.png",))
        for name in ("unpublished", "missing", "mismatch"):
            with self.subTest(name=name):
                self.assertEqual(records[name].completion_evidence.plot_count, 0)
                self.assertEqual(records[name].plot_paths, ())
        self.assertTrue(records["missing"].artifact_validation_errors)
        self.assertTrue(records["mismatch"].artifact_validation_errors)

    def test_worksheet_and_report_require_published_digest_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._write_run(
                root,
                "valid",
                worksheet=b"worksheet",
                report=b"report",
            )
            damaged = self._write_run(
                root,
                "damaged",
                worksheet=b"worksheet",
                report=b"report",
            )
            (damaged / "worksheet.md").unlink()
            (damaged / "report.html").write_bytes(b"changed")

            records = {item.path.name: item for item in ArtifactRepository(root).list_runs()}

        self.assertTrue(records["valid"].worksheet_available)
        self.assertTrue(records["valid"].report_available)
        self.assertEqual(
            records["valid"].completion_evidence.artifact_keys,
            ("report", "worksheet"),
        )
        self.assertFalse(records["damaged"].worksheet_available)
        self.assertFalse(records["damaged"].report_available)
        self.assertEqual(records["damaged"].completion_evidence.artifact_keys, ())
        self.assertEqual(len(records["damaged"].artifact_validation_errors), 2)

    def test_legacy_status_and_reason_are_preserved_without_synthetic_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            older = root / "legacy-older"
            older.mkdir()
            (older / "summary.json").write_text(
                json.dumps({"config_name": "lab01.default", "duration": 1.0}),
                encoding="utf-8",
            )
            newer = root / "legacy-newer"
            newer.mkdir()
            (newer / "summary.json").write_text(
                json.dumps({"config_name": "lab01.default", "duration": 2.0}),
                encoding="utf-8",
            )
            os.utime(older, (1_000_000_000, 1_000_000_000))
            os.utime(newer, (2_000_000_000, 2_000_000_000))

            records = ArtifactRepository(root).list_runs()
            record = records[0]

        self.assertEqual([item.path.name for item in records], ["legacy-newer", "legacy-older"])
        self.assertEqual(record.status, "legacy")
        self.assertTrue(record.legacy)
        self.assertEqual(record.marker_name, "summary.json")
        self.assertEqual(
            record.completion_evidence.record_kind,
            CompletionRecordKind.LEGACY_SUMMARY,
        )
        self.assertEqual(record.completion_evidence.status, None)
        self.assertEqual(record.finished_at, "")

    def test_terminal_runs_sort_by_manifest_finish_time_then_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            old = self._write_run(
                root,
                "old",
                finished_at="2026-07-21T01:00:00+00:00",
            )
            new = self._write_run(
                root,
                "new",
                finished_at="2026-07-21T02:00:00+00:00",
            )
            self._write_run(
                root,
                "tie-b",
                finished_at="2026-07-21T03:00:00+00:00",
            )
            self._write_run(
                root,
                "tie-a",
                finished_at="2026-07-21T03:00:00+00:00",
            )
            os.utime(old, (2_000_000_000, 2_000_000_000))
            os.utime(new, (1_000_000_000, 1_000_000_000))

            names = [item.path.name for item in ArtifactRepository(root).list_runs()]

        self.assertEqual(names, ["tie-a", "tie-b", "new", "old"])

    def test_course_child_keys_require_published_strict_completed_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            course = root / "course"
            course.mkdir()
            for index, (batch_name, target_id) in enumerate(
                zip(CONCRETE_BATCH_NAMES, CONCRETE_BATCH_TARGET_IDS, strict=True)
            ):
                child = course / batch_name
                child.mkdir()
                (child / "comparison_plots").mkdir()
                (child / "comparison_plots" / "comparison.png").write_bytes(b"plot")
                (child / "worksheet.md").write_text(
                    "# Batch worksheet\n\n## Prediction Check\n",
                    encoding="utf-8",
                )
                (child / "report.html").write_text(
                    "<html>batch report</html>",
                    encoding="utf-8",
                )
                child_scenario = "batch.wrong" if index == 0 else target_id
                child_status = "stopped" if index == 1 else "completed"
                manifest = write_manifest(
                    child,
                    scenario_id=child_scenario,
                    status=child_status,
                    config={"batch_name": batch_name, "plot": True},
                )
                if index == 2:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                    payload.pop("runtime")
                    manifest.write_text(json.dumps(payload), encoding="utf-8")
            (course / "worksheet.md").write_text("# Course worksheet\n", encoding="utf-8")
            (course / "report.html").write_text("<html>course</html>", encoding="utf-8")
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )

            record = ArtifactRepository(root).list_runs()[0]

        self.assertEqual(
            record.completion_evidence.artifact_keys,
            CONCRETE_BATCH_TARGET_IDS[3:],
            record.artifact_validation_errors,
        )
        self.assertEqual(len(record.artifact_validation_errors), 3)
        self.assertTrue(
            any("expected child batch" in error for error in record.artifact_validation_errors)
        )
        self.assertTrue(
            any("not completed" in error for error in record.artifact_validation_errors)
        )
        self.assertTrue(
            any("not a valid schema-1" in error for error in record.artifact_validation_errors)
        )

    def test_course_child_key_requires_full_child_completion_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            course = root / "course"
            course.mkdir()
            damaged_target = CONCRETE_BATCH_TARGET_IDS[2]
            for batch_name, target_id in zip(
                CONCRETE_BATCH_NAMES,
                CONCRETE_BATCH_TARGET_IDS,
                strict=True,
            ):
                child = course / batch_name
                child.mkdir()
                (child / "comparison_plots").mkdir()
                (child / "comparison_plots" / "comparison.png").write_bytes(b"plot")
                (child / "worksheet.md").write_text(
                    "# Batch worksheet\n\n## Prediction Check\n",
                    encoding="utf-8",
                )
                (child / "report.html").write_text(
                    "<html>batch report</html>",
                    encoding="utf-8",
                )
                write_manifest(
                    child,
                    scenario_id=target_id,
                    status="completed",
                    config={"batch_name": batch_name, "plot": True},
                )
                if target_id == damaged_target:
                    (child / "report.html").write_text(
                        "<html>corrupted after publication</html>",
                        encoding="utf-8",
                    )
            (course / "worksheet.md").write_text("# Course worksheet\n", encoding="utf-8")
            (course / "report.html").write_text("<html>course</html>", encoding="utf-8")
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )

            record = ArtifactRepository(root).list_runs()[0]

        self.assertNotIn(damaged_target, record.completion_evidence.artifact_keys)
        self.assertEqual(
            set(record.completion_evidence.artifact_keys),
            set(CONCRETE_BATCH_TARGET_IDS) - {damaged_target},
        )
        self.assertFalse(record.report_available)
        self.assertFalse(record.worksheet_available)
        self.assertTrue(
            any(
                "report.html does not match its manifest digest" in error
                and "required_artifact_missing" in record.artifact_validation_errors[-1]
                for error in record.artifact_validation_errors
            ),
            record.artifact_validation_errors,
        )

    def test_child_manifest_mutation_during_evidence_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            course = root / "course"
            course.mkdir()
            batch_name = CONCRETE_BATCH_NAMES[0]
            target_id = CONCRETE_BATCH_TARGET_IDS[0]
            child = course / batch_name
            child.mkdir()
            (child / "comparison_plots").mkdir()
            (child / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            (child / "worksheet.md").write_text(
                "# Batch worksheet\n\n## Prediction Check\n",
                encoding="utf-8",
            )
            (child / "report.html").write_text("<html>report</html>", encoding="utf-8")
            child_manifest = write_manifest(
                child,
                scenario_id=target_id,
                status="completed",
                config={"batch_name": batch_name, "plot": True},
            )
            (course / "worksheet.md").write_text("# Course worksheet\n", encoding="utf-8")
            (course / "report.html").write_text("<html>course</html>", encoding="utf-8")
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )
            real_plot_reader = output_inventory._trusted_plot_paths_rooted
            mutated = False

            def mutate_child_manifest(
                root_pin: PinnedOutputRoot,
                relative_root: tuple[str, ...],
                artifacts: dict[str, str],
            ) -> tuple[tuple[str, ...], tuple[str, ...]]:
                nonlocal mutated
                result = real_plot_reader(root_pin, relative_root, artifacts)
                if relative_root == (course.name, batch_name) and not mutated:
                    payload = json.loads(child_manifest.read_text(encoding="utf-8"))
                    payload["status"] = "stopped"
                    child_manifest.write_text(json.dumps(payload), encoding="utf-8")
                    mutated = True
                return result

            with patch.object(
                output_inventory,
                "_trusted_plot_paths_rooted",
                mutate_child_manifest,
            ):
                record = ArtifactRepository(root).list_runs()[0]

        self.assertNotIn(target_id, record.completion_evidence.artifact_keys)
        self.assertTrue(
            any("changed while child evidence was read" in error for error in record.artifact_validation_errors),
            record.artifact_validation_errors,
        )

    def test_same_length_child_artifact_overwrite_is_revalidated_before_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            course = root / "course"
            course.mkdir()
            target_plot: Path | None = None
            for batch_name, target_id in zip(
                CONCRETE_BATCH_NAMES,
                CONCRETE_BATCH_TARGET_IDS,
                strict=True,
            ):
                child = course / batch_name
                child.mkdir()
                (child / "comparison_plots").mkdir()
                plot = child / "comparison_plots" / "comparison.png"
                plot.write_bytes(b"trusted child plot")
                if target_plot is None:
                    target_plot = plot
                (child / "worksheet.md").write_text(
                    "# Batch worksheet\n\n## Prediction Check\n",
                    encoding="utf-8",
                )
                (child / "report.html").write_text(
                    "<html>batch report</html>",
                    encoding="utf-8",
                )
                write_manifest(
                    child,
                    scenario_id=target_id,
                    status="completed",
                    config={"batch_name": batch_name, "plot": True},
                )
            (course / "worksheet.md").write_text(
                "# Course worksheet\n",
                encoding="utf-8",
            )
            (course / "report.html").write_text(
                "<html>course report</html>",
                encoding="utf-8",
            )
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )
            assert target_plot is not None
            original_size = target_plot.stat().st_size
            real_reader = output_inventory.read_json_mapping_rooted
            manifest_reads = 0
            overwritten = False

            def overwrite_child_after_final_parent_marker(
                *args: object,
                **kwargs: object,
            ) -> object:
                nonlocal manifest_reads, overwritten
                result = real_reader(*args, **kwargs)
                relative = tuple(args[1])
                if relative == (course.name, "manifest.json"):
                    manifest_reads += 1
                    if manifest_reads == 2:
                        target_plot.write_bytes(b"X" * original_size)
                        overwritten = True
                return result

            with patch.object(
                output_inventory,
                "read_json_mapping_rooted",
                overwrite_child_after_final_parent_marker,
            ):
                records = ArtifactRepository(root).list_runs()

        self.assertTrue(overwritten)
        self.assertEqual(records, ())

    def test_hash_reader_rejects_file_growth_after_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = self._write_run(root, "growing", plot=b"12345678")
            real_open = PinnedOutputRoot.open_regular_file

            @contextmanager
            def growing_open(
                root_pin: PinnedOutputRoot,
                relative: tuple[str, ...],
                *,
                description: str,
                max_bytes: int,
                allow_empty: bool = True,
            ):
                with real_open(
                    root_pin,
                    relative,
                    description=description,
                    max_bytes=max_bytes,
                    allow_empty=allow_empty,
                ) as stream:
                    if relative[-1] == "position.png":
                        with root_pin.display_path(relative).open("ab") as writer:
                            writer.write(b"9")
                    yield stream

            with pinned_output_root(root, allowed_root=root) as (
                _display_root,
                _root_exists,
                root_pin,
            ):
                assert root_pin is not None
                with (
                    patch.object(PinnedOutputRoot, "open_regular_file", growing_open),
                    patch.object(output_inventory, "MAX_COMPLETION_ARTIFACT_BYTES", 8),
                    self.assertRaises(CleanupSafetyError),
                ):
                    output_inventory._sha256_regular_file_rooted(
                        root_pin,
                        (run.name, "plots", "position.png"),
                        description="growing plot",
                    )

    @unittest.skipIf(os.name == "nt", "Windows directory leases prevent this POSIX rename probe")
    def test_repository_rejects_run_swap_after_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = self._write_run(root, "victim", plot=b"trusted")
            replacement = self._write_run(root, "replacement", plot=b"injected")
            held = root / "held-victim"
            real_snapshot = output_inventory.read_completion_run_snapshot_rooted
            swapped = False

            def swap_after_snapshot(
                root_pin: PinnedOutputRoot,
                name: str,
                *,
                allow_legacy: bool = True,
            ):
                nonlocal swapped
                snapshot = real_snapshot(
                    root_pin,
                    name,
                    allow_legacy=allow_legacy,
                )
                if name == original.name and not swapped:
                    original.rename(held)
                    replacement.rename(original)
                    swapped = True
                return snapshot

            try:
                with patch(
                    "mclab.application.repositories.read_completion_run_snapshot_rooted",
                    swap_after_snapshot,
                ):
                    records = ArtifactRepository(root).list_runs()
            finally:
                if swapped:
                    original.rename(replacement)
                    held.rename(original)

        self.assertNotIn("victim", {record.path.name for record in records})

    def test_verify_manifest_rejects_escape_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            run = root / "run"
            run.mkdir()
            manifest = write_manifest(
                run,
                scenario_id="lab01.default",
                status="completed",
                config={},
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["artifacts"]["../outside.txt"] = hashlib.sha256(
                outside.read_bytes()
            ).hexdigest()
            payload["artifacts"]["bad\x00name"] = hashlib.sha256(b"").hexdigest()
            manifest.write_text(json.dumps(payload), encoding="utf-8")

            errors = verify_manifest(run)
            validation = validate_completion_manifest_v1(payload)

        self.assertIn("Unsafe artifact path: ../outside.txt", errors)
        self.assertIn("Unsafe artifact path: bad\x00name", errors)
        self.assertEqual(validation.record_kind, CompletionRecordKind.INVALID)

    @unittest.skipIf(os.name == "nt", "Windows directory leases prevent this POSIX rename probe")
    def test_child_batch_directory_swap_cannot_inject_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            course = root / "course"
            course.mkdir()
            batch_name = CONCRETE_BATCH_NAMES[0]
            target_id = CONCRETE_BATCH_TARGET_IDS[0]
            original = course / batch_name
            replacement = root / "replacement-child"
            original.mkdir()
            replacement.mkdir()
            (replacement / "comparison_plots").mkdir()
            (replacement / "comparison_plots" / "comparison.png").write_bytes(b"plot")
            (replacement / "worksheet.md").write_text(
                "# Batch worksheet\n\n## Prediction Check\n",
                encoding="utf-8",
            )
            (replacement / "report.html").write_text("<html>report</html>", encoding="utf-8")
            replacement_manifest = write_manifest(
                replacement,
                scenario_id=target_id,
                status="completed",
                config={"batch_name": batch_name, "plot": True},
            )
            shutil.copy2(replacement_manifest, original / "manifest.json")
            (course / "worksheet.md").write_text("# Course worksheet\n", encoding="utf-8")
            (course / "report.html").write_text("<html>course</html>", encoding="utf-8")
            write_manifest(
                course,
                scenario_id="batch.all",
                status="completed",
                config={"batch_name": "all", "plot": True},
            )
            course_stat = course.stat()
            real_reader = output_inventory._trusted_child_batch_rooted

            def swapped_reader(
                root_pin: PinnedOutputRoot,
                *,
                name: str,
                batch_name: str,
                target_id: str,
                expected_manifest_digest: str,
                completion_rule: CompletionRule,
            ) -> tuple[bool, tuple[str, ...]]:
                hold = root / "held-child"
                original.rename(hold)
                replacement.rename(original)
                try:
                    return real_reader(
                        root_pin,
                        name=name,
                        batch_name=batch_name,
                        target_id=target_id,
                        expected_manifest_digest=expected_manifest_digest,
                        completion_rule=completion_rule,
                    )
                finally:
                    original.rename(replacement)
                    hold.rename(original)
                    os.utime(
                        course,
                        ns=(course_stat.st_atime_ns, course_stat.st_mtime_ns),
                    )

            with patch.object(
                output_inventory,
                "_trusted_child_batch_rooted",
                swapped_reader,
            ):
                record = next(
                    item
                    for item in ArtifactRepository(root).list_runs()
                    if item.path.name == course.name
                )

        self.assertNotIn(target_id, record.completion_evidence.artifact_keys)
        self.assertTrue(
            any("comparison.png" in error for error in record.artifact_validation_errors),
            record.artifact_validation_errors,
        )

    @staticmethod
    def _write_run(
        root: Path,
        name: str,
        *,
        events: bytes | None = None,
        plot: bytes | None = None,
        worksheet: bytes | None = None,
        report: bytes | None = None,
        started_at: str = "2026-07-21T00:00:00+00:00",
        finished_at: str = "2026-07-21T00:01:00+00:00",
    ) -> Path:
        run = root / name
        run.mkdir()
        (run / "summary.json").write_text(
            json.dumps({"config_name": "default", "lab_name": "lab01_msd"}),
            encoding="utf-8",
        )
        if events is not None:
            (run / "interaction_events.json").write_bytes(events)
        if plot is not None:
            (run / "plots").mkdir()
            (run / "plots" / "position.png").write_bytes(plot)
        if worksheet is not None:
            (run / "worksheet.md").write_bytes(worksheet)
        if report is not None:
            (run / "report.html").write_bytes(report)
        write_manifest(
            run,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
            config_path="configs/lab01_msd/default.yaml",
            started_at=started_at,
            finished_at=finished_at,
        )
        return run


if __name__ == "__main__":
    unittest.main()
