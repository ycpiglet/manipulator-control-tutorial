from __future__ import annotations

import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mclab.config import PROJECT_ROOT
from mclab.output_cleanup import (
    CleanupOperationError,
    CleanupSafetyError,
    build_cleanup_plan,
    list_cleanup_receipts,
    quarantine_cleanup_plan,
    quarantine_run,
    restore_cleanup_receipt,
    run_identity_token,
)


UTC = timezone.utc


def _manifest_payload(
    *,
    scenario_id: str = "lab01.default",
    status: str = "completed",
    finished_at: str = "2026-07-20T12:00:00+00:00",
    schema_version: int = 1,
    artifacts: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "scenario_id": scenario_id,
        "status": status,
        "started_at": "2026-07-20T11:59:00+00:00",
        "finished_at": finished_at,
        "config": {"resolved": {"sim_time": 1.0}},
        "artifacts": artifacts or {},
    }


def _make_run(
    root: Path,
    name: str,
    *,
    scenario_id: str = "lab01.default",
    status: str = "completed",
    finished_at: str = "2026-07-20T12:00:00+00:00",
    schema_version: int = 1,
    artifacts: dict[str, str] | None = None,
) -> Path:
    run = root / name
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps(
            _manifest_payload(
                scenario_id=scenario_id,
                status=status,
                finished_at=finished_at,
                schema_version=schema_version,
                artifacts=artifacts,
            )
        ),
        encoding="utf-8",
    )
    return run


class CleanupRootGuardTests(unittest.TestCase):
    def test_only_the_configured_root_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configured = Path(tmp).resolve() / "data" / "outputs"
            configured.mkdir(parents=True)
            other = Path(tmp).resolve() / "other" / "outputs"
            other.mkdir(parents=True)

            self.assertEqual(
                build_cleanup_plan(configured, keep=0, allowed_root=configured).root,
                configured.resolve(),
            )
            with self.assertRaisesRegex(CleanupSafetyError, "configured outputs root"):
                build_cleanup_plan(other, keep=0, allowed_root=configured)

    def test_missing_configured_root_is_a_safe_empty_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "data" / "outputs"
            plan = build_cleanup_plan(root, keep=20, allowed_root=root)
            self.assertFalse(plan.root_exists)
            self.assertEqual(plan.selected, ())
            self.assertEqual(plan.retained, ())

    def test_negative_keep_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            with self.assertRaisesRegex(CleanupSafetyError, "non-negative"):
                build_cleanup_plan(root, keep=-1, allowed_root=root)

    def test_file_and_protected_roots_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file_root = Path(tmp).resolve() / "outputs"
            file_root.write_text("not a directory", encoding="utf-8")
            with self.assertRaisesRegex(CleanupSafetyError, "directory"):
                build_cleanup_plan(file_root, keep=0, allowed_root=file_root)

        filesystem_root = Path(Path.cwd().anchor)
        protected_roots = (
            Path.home(),
            filesystem_root,
            PROJECT_ROOT,
            PROJECT_ROOT.parent,
            Path(tempfile.gettempdir()),
        )
        for protected in protected_roots:
            with self.subTest(root=protected):
                with self.assertRaises(CleanupSafetyError):
                    build_cleanup_plan(protected, keep=0, allowed_root=protected)
        self.assertTrue(filesystem_root.anchor)

    def test_symlink_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp).resolve() / "real" / "outputs"
            real.mkdir(parents=True)
            link = Path(tmp).resolve() / "linked-outputs"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                build_cleanup_plan(link, keep=0, allowed_root=link)

    def test_symlink_parent_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real_parent = Path(tmp).resolve() / "real-parent"
            root = real_parent / "outputs"
            root.mkdir(parents=True)
            linked_parent = Path(tmp).resolve() / "linked-parent"
            try:
                linked_parent.symlink_to(real_parent, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")
            linked_root = linked_parent / "outputs"
            with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                build_cleanup_plan(linked_root, keep=0, allowed_root=linked_root)

    def test_mount_root_is_rejected_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            with patch("mclab.output_root._is_mount_point", return_value=True):
                with self.assertRaisesRegex(CleanupSafetyError, "mount point"):
                    build_cleanup_plan(root, keep=0, allowed_root=root)

    def test_unsupported_mount_api_does_not_break_python_310_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            with patch.object(Path, "is_mount", side_effect=NotImplementedError):
                plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertTrue(plan.root_exists)
            self.assertEqual(plan.selected, ())

    def test_replaced_root_inventory_fails_without_returning_external_runs(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows root replacement is covered by the handle-sharing test")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            _make_run(root, "original-run")
            outside = base / "outside"
            outside.mkdir()
            _make_run(outside, "external-secret")
            detached = base / "detached-outputs"

            from mclab.output_root import PinnedOutputRoot

            original_list = PinnedOutputRoot.list_names
            swapped = False

            def swap_before_inventory(
                root_pin: PinnedOutputRoot,
                relative: tuple[str, ...] = (),
            ) -> tuple[str, ...]:
                nonlocal swapped
                if not swapped and not relative:
                    root.rename(detached)
                    root.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return original_list(root_pin, relative)

            try:
                with patch.object(
                    PinnedOutputRoot,
                    "list_names",
                    swap_before_inventory,
                ):
                    with self.assertRaisesRegex(CleanupSafetyError, "root changed"):
                        build_cleanup_plan(root, keep=0, allowed_root=root)
            finally:
                if root.is_symlink():
                    root.unlink()
                if detached.exists():
                    detached.rename(root)
            self.assertTrue(swapped)
            self.assertTrue((outside / "external-secret").is_dir())
            self.assertFalse((outside / ".mclab-trash").exists())

    @unittest.skipIf(os.name == "nt", "POSIX component opening race fixture")
    def test_parent_link_swap_before_root_pin_cannot_inventory_external_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            trusted_parent = base / "trusted-parent"
            root = trusted_parent / "outputs"
            root.mkdir(parents=True)
            _make_run(root, "trusted-run")
            external_parent = base / "external-parent"
            outside = external_parent / "outputs"
            outside.mkdir(parents=True)
            _make_run(outside, "external-secret")
            detached = base / "detached-trusted-parent"
            from mclab import output_root as output_root_module

            original_guard = output_root_module._reject_link_components

            def swap_after_guard(path: Path) -> None:
                original_guard(path)
                trusted_parent.rename(detached)
                trusted_parent.symlink_to(external_parent, target_is_directory=True)

            try:
                with patch(
                    "mclab.output_root._reject_link_components",
                    side_effect=swap_after_guard,
                ):
                    with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                        build_cleanup_plan(root, keep=0, allowed_root=root)
            finally:
                if trusted_parent.is_symlink():
                    trusted_parent.unlink()
                if detached.exists():
                    detached.rename(trusted_parent)
            self.assertTrue((outside / "external-secret").is_dir())
            self.assertFalse((outside / ".mclab-trash").exists())

    @unittest.skipIf(os.name == "nt", "POSIX component opening race fixture")
    def test_parent_link_swap_before_root_pin_cannot_quarantine_external_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            trusted_parent = base / "trusted-parent"
            root = trusted_parent / "outputs"
            root.mkdir(parents=True)
            _make_run(root, "trusted-run")
            external_parent = base / "external-parent"
            outside = external_parent / "outputs"
            outside.mkdir(parents=True)
            external_run = _make_run(outside, "external-run")
            external_token = run_identity_token(external_run)
            detached = base / "detached-trusted-parent"
            from mclab import output_root as output_root_module

            original_guard = output_root_module._reject_link_components

            def swap_after_guard(path: Path) -> None:
                original_guard(path)
                trusted_parent.rename(detached)
                trusted_parent.symlink_to(external_parent, target_is_directory=True)

            try:
                with patch(
                    "mclab.output_root._reject_link_components",
                    side_effect=swap_after_guard,
                ):
                    with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                        quarantine_run(
                            root,
                            root / "external-run",
                            confirmation="external-run",
                            expected_token=external_token,
                            allowed_root=root,
                        )
            finally:
                if trusted_parent.is_symlink():
                    trusted_parent.unlink()
                if detached.exists():
                    detached.rename(trusted_parent)
            self.assertTrue(external_run.is_dir())
            self.assertFalse((outside / ".mclab-trash").exists())

    def test_apply_rejects_same_manifest_clone_at_the_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original = base / "original-outputs"
            root.rename(original)
            shutil.copytree(original, root)

            with self.assertRaisesRegex(CleanupSafetyError, "inventory changed"):
                quarantine_cleanup_plan(
                    plan,
                    expected_plan_id=plan.plan_id,
                    allowed_root=root,
                )
            self.assertTrue((root / "run").is_dir())
            self.assertFalse((root / ".mclab-trash").exists())
            self.assertTrue((original / "run").is_dir())

    @unittest.skipUnless(os.sys.platform == "darwin", "macOS /var alias fixture")
    def test_macos_temp_alias_is_rejected_but_canonical_path_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alias_base = Path(tmp)
            canonical_base = alias_base.resolve(strict=True)
            if alias_base == canonical_base:
                self.skipTest("TMPDIR does not use a lexical symlink alias")
            alias_root = alias_base / "outputs"
            canonical_root = canonical_base / "outputs"
            canonical_root.mkdir()
            with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                build_cleanup_plan(alias_root, keep=0, allowed_root=alias_root)
            self.assertTrue(
                build_cleanup_plan(
                    canonical_root,
                    keep=0,
                    allowed_root=canonical_root,
                ).root_exists
            )

    @unittest.skipUnless(os.name == "nt", "Windows junction root fixture")
    def test_windows_junction_root_and_parent_component_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            real_parent = base / "real-parent"
            root = real_parent / "outputs"
            root.mkdir(parents=True)
            junction = base / "junction-parent"
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(real_parent)],
                check=True,
                capture_output=True,
                text=True,
            )
            for candidate in (junction, junction / "outputs"):
                with self.subTest(candidate=candidate):
                    with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                        build_cleanup_plan(candidate, keep=0, allowed_root=candidate)

    @unittest.skipUnless(os.name == "nt", "Windows root handle sharing fixture")
    def test_windows_pinned_root_blocks_replacement_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            moved = base / "moved-outputs"
            root.mkdir()
            from mclab.output_root import pinned_output_root

            with pinned_output_root(root, allowed_root=root):
                attempted = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import os,sys; os.rename(sys.argv[1], sys.argv[2])",
                        str(root),
                        str(moved),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(attempted.returncode, 0)
                self.assertTrue(root.is_dir())
            root.rename(moved)
            self.assertTrue(moved.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows ancestor handle sharing fixture")
    def test_windows_pinned_ancestor_blocks_replacement_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            parent = base / "parent"
            root = parent / "outputs"
            root.mkdir(parents=True)
            moved_parent = base / "moved-parent"
            from mclab.output_root import pinned_output_root

            with pinned_output_root(root, allowed_root=root):
                attempted = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import os,sys; os.rename(sys.argv[1], sys.argv[2])",
                        str(parent),
                        str(moved_parent),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(attempted.returncode, 0)
                self.assertTrue(root.is_dir())
            parent.rename(moved_parent)
            self.assertTrue((moved_parent / "outputs").is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows handle-rename fixture")
    def test_windows_handle_rename_uses_the_exact_nested_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            source_name = "source-끝-Z9"
            source = root / source_name
            entries = root / ".mclab-trash" / "receipt" / "entries"
            source.mkdir(parents=True)
            entries.mkdir(parents=True)
            (source / "canary.txt").write_text("preserve", encoding="utf-8")
            destination = entries / source_name
            collision_source = root / "collision-source"
            collision_destination = entries / "collision-existing"
            collision_source.mkdir()
            collision_destination.mkdir()
            (collision_source / "source.txt").write_text("source", encoding="utf-8")
            (collision_destination / "destination.txt").write_text(
                "destination",
                encoding="utf-8",
            )

            from mclab.output_root import pinned_output_root

            with pinned_output_root(root, allowed_root=root) as (
                _resolved,
                root_exists,
                root_pin,
            ):
                self.assertTrue(root_exists)
                self.assertIsNotNone(root_pin)
                assert root_pin is not None
                root_pin.pin_directory((".mclab-trash",), description="quarantine")
                root_pin.pin_directory(
                    (".mclab-trash", "receipt"),
                    description="cleanup receipt",
                )
                root_pin.pin_directory(
                    (".mclab-trash", "receipt", "entries"),
                    description="quarantine entries",
                )
                source_identity = root_pin.directory_identity((source_name,))
                root_pin.rename_noreplace(
                    (source_name,),
                    (".mclab-trash", "receipt", "entries", destination.name),
                    expected_source_identity=source_identity,
                )
                self.assertEqual(
                    root_pin.directory_identity(
                        (".mclab-trash", "receipt", "entries", destination.name)
                    ),
                    source_identity,
                )
                collision_identity = root_pin.directory_identity((collision_source.name,))
                with self.assertRaises(FileExistsError):
                    root_pin.rename_noreplace(
                        (collision_source.name,),
                        (
                            ".mclab-trash",
                            "receipt",
                            "entries",
                            collision_destination.name,
                        ),
                        expected_source_identity=collision_identity,
                    )

            self.assertFalse(source.exists())
            self.assertEqual(
                (destination / "canary.txt").read_text(encoding="utf-8"),
                "preserve",
            )
            self.assertEqual(
                {path.name for path in entries.iterdir()},
                {destination.name, collision_destination.name},
            )
            self.assertEqual(
                (collision_source / "source.txt").read_text(encoding="utf-8"),
                "source",
            )
            self.assertEqual(
                (collision_destination / "destination.txt").read_text(encoding="utf-8"),
                "destination",
            )


class CleanupCandidateTests(unittest.TestCase):
    def test_mixed_inventory_selects_only_strict_terminal_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            valid_names = {
                "completed-run",
                "stopped-run",
                "error-run",
                "odd learner name !",
            }
            _make_run(root, "completed-run", status="completed")
            _make_run(root, "stopped-run", status="stopped")
            _make_run(root, "error-run", status="error")
            _make_run(root, "odd learner name !", status="completed")

            for name in (
                "_internal",
                "_QT_probe",
                "codex_probe",
                "CODEX_upper_probe",
                "verify_probe",
                "VERIFY_upper_probe",
                ".mclab-trash",
            ):
                _make_run(root, name)
            _make_run(root, "running-run", status="running")
            _make_run(root, "unknown-status", status="mystery")
            _make_run(root, "old-schema", schema_version=0)
            _make_run(root, "future-schema", schema_version=2)
            _make_run(root, "blank-scenario", scenario_id="   ")
            _make_run(root, "bad-time", finished_at="yesterday")
            _make_run(root, "naive-time", finished_at="2026-07-20T12:00:00")
            _make_run(root, "absolute-artifact", artifacts={"/outside": "abc"})
            _make_run(root, "traversal-artifact", artifacts={"../outside": "abc"})
            preserved = _make_run(root, "preserved-run")
            (preserved / ".mclab-preserve").write_text("hold", encoding="utf-8")

            (root / "missing-manifest").mkdir()
            malformed = root / "malformed-manifest"
            malformed.mkdir()
            (malformed / "manifest.json").write_text("{", encoding="utf-8")
            non_object = root / "non-object-manifest"
            non_object.mkdir()
            (non_object / "manifest.json").write_text("[]", encoding="utf-8")
            summary_only = root / "summary-only-legacy"
            summary_only.mkdir()
            (summary_only / "summary.json").write_text(
                json.dumps({"lab_name": "lab01_msd"}), encoding="utf-8"
            )
            timestamp_only = root / "20260720_120000_lab01_msd"
            timestamp_only.mkdir()
            (root / "top-level-file").write_text("keep", encoding="utf-8")

            nested_parent = root / "nested-parent"
            nested_parent.mkdir()
            _make_run(nested_parent, "valid-but-nested")

            external = Path(tmp).resolve() / "external-run"
            _make_run(Path(tmp).resolve(), "external-run")
            for name, target in (
                ("external-link", external),
                ("sibling-link", root / "completed-run"),
            ):
                try:
                    (root / name).symlink_to(target, target_is_directory=True)
                except (NotImplementedError, OSError):
                    pass

            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual({entry.name for entry in plan.eligible}, valid_names)
            self.assertEqual({entry.name for entry in plan.selected}, valid_names)
            self.assertGreaterEqual(len(plan.skipped), 23)
            self.assertTrue(all(entry.path.parent == root for entry in plan.selected))

    def test_manifest_symlink_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            outside = Path(tmp).resolve() / "outside.json"
            outside.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
            run = root / "manifest-link"
            run.mkdir()
            try:
                (run / "manifest.json").symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("file symlinks are unavailable")

            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(plan.eligible, ())
            self.assertIn("manifest", plan.skipped[0].reason)

    def test_strict_manifest_mutation_table_rejects_every_invalid_shape(self) -> None:
        def missing(key: str):
            return lambda payload: payload.pop(key)

        mutations = {
            "schema-bool": lambda payload: payload.update(schema_version=True),
            "missing-started": missing("started_at"),
            "naive-started": lambda payload: payload.update(
                started_at="2026-07-20T11:59:00"
            ),
            "invalid-started": lambda payload: payload.update(started_at="earlier"),
            "missing-finished": missing("finished_at"),
            "finished-before-started": lambda payload: payload.update(
                started_at="2026-07-20T12:01:00+00:00",
                finished_at="2026-07-20T12:00:00+00:00",
            ),
            "config-list": lambda payload: payload.update(config=[]),
            "resolved-list": lambda payload: payload.update(config={"resolved": []}),
            "artifacts-list": lambda payload: payload.update(artifacts=[]),
            "artifact-drive": lambda payload: payload.update(artifacts={"C:/outside": "x"}),
            "artifact-backslash": lambda payload: payload.update(
                artifacts={"plots\\outside.png": "x"}
            ),
            "artifact-dot": lambda payload: payload.update(artifacts={".": "x"}),
            "artifact-empty": lambda payload: payload.update(artifacts={"": "x"}),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            for name, mutate in mutations.items():
                run = root / name
                run.mkdir()
                payload = _manifest_payload()
                mutate(payload)
                (run / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

            for name, content in (
                ("empty-manifest", b""),
                ("invalid-utf8", b"\xff"),
                ("oversized-manifest", b" " * (2 * 1024 * 1024 + 1)),
            ):
                run = root / name
                run.mkdir()
                (run / "manifest.json").write_bytes(content)

            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(plan.eligible, ())
            self.assertEqual(
                {item.name for item in plan.skipped},
                set(mutations) | {"empty-manifest", "invalid-utf8", "oversized-manifest"},
            )

    def test_manifest_replaced_by_symlink_during_open_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "raced-run")
            manifest = run / "manifest.json"
            original_manifest = run / "original-manifest.json"
            outside = Path(tmp).resolve() / "outside.json"
            outside.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
            try:
                probe = Path(tmp).resolve() / "symlink-probe"
                probe.symlink_to(outside)
                probe.unlink()
            except (NotImplementedError, OSError):
                self.skipTest("file symlinks are unavailable")

            original_open = os.open
            swapped = False

            def swap_before_open(
                path: str | os.PathLike[str],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal swapped
                if Path(path).name == manifest.name and not swapped:
                    swapped = True
                    manifest.replace(original_manifest)
                    manifest.symlink_to(outside)
                return original_open(path, flags, *args, **kwargs)

            with patch("mclab.output_root.os.open", side_effect=swap_before_open):
                plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(plan.eligible, ())
            self.assertTrue(outside.is_file())
            self.assertTrue(original_manifest.is_file())

    @unittest.skipUnless(os.name == "nt", "Windows junction fixture")
    def test_windows_junction_candidate_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            real = _make_run(Path(tmp).resolve(), "junction-target")
            junction = root / "junction-run"
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(real)],
                check=True,
                capture_output=True,
                text=True,
            )
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(plan.eligible, ())
            self.assertTrue(real.exists())

    def test_seeded_mixed_inventory_selects_only_expected_strict_runs(self) -> None:
        randomizer = random.Random(20260720)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            expected: set[str] = set()
            statuses = ("completed", "stopped", "error", "running", "unknown")
            for index in range(48):
                name = f"seeded-{index:02d}"
                status = randomizer.choice(statuses)
                schema = randomizer.choice((1, 1, 1, 0, 2))
                _make_run(
                    root,
                    name,
                    status=status,
                    schema_version=schema,
                    finished_at=f"2026-07-20T12:{index:02d}:00+00:00",
                )
                if status in {"completed", "stopped", "error"} and schema == 1:
                    expected.add(name)
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            selected = {entry.name for entry in plan.selected}
            self.assertEqual(selected, expected)
            self.assertTrue(selected <= {path.name for path in root.iterdir()})

    def test_casefold_collisions_have_a_deterministic_plan_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            upper = root / "A"
            lower = root / "a"
            upper.write_text("upper", encoding="utf-8")
            lower.write_text("lower", encoding="utf-8")
            if upper.samefile(lower):
                self.skipTest("fixture filesystem is case-insensitive")
            from mclab.output_root import PinnedOutputRoot

            with patch.object(PinnedOutputRoot, "list_names", return_value=("a", "A")):
                first = build_cleanup_plan(root, keep=0, allowed_root=root)
            with patch.object(PinnedOutputRoot, "list_names", return_value=("A", "a")):
                second = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual([entry.name for entry in first.skipped], ["A", "a"])
            self.assertEqual(first.plan_id, second.plan_id)

    def test_retention_uses_finished_at_not_name_or_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            base = datetime(2026, 7, 20, 12, tzinfo=UTC)
            oldest = _make_run(root, "zzz-old", finished_at=base.isoformat())
            _make_run(
                root,
                "mmm-middle",
                finished_at=(base + timedelta(minutes=1)).isoformat(),
            )
            newest = _make_run(
                root,
                "aaa-new",
                finished_at=(base + timedelta(minutes=2)).isoformat(),
            )
            os.utime(oldest, (newest.stat().st_mtime + 1000,) * 2)
            os.utime(newest, (oldest.stat().st_mtime - 2000,) * 2)

            plan = build_cleanup_plan(root, keep=2, allowed_root=root)
            self.assertEqual([entry.name for entry in plan.retained], ["aaa-new", "mmm-middle"])
            self.assertEqual([entry.name for entry in plan.selected], ["zzz-old"])

    def test_plan_id_is_deterministic_and_changes_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            first = build_cleanup_plan(root, keep=0, allowed_root=root)
            second = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(first.plan_id, second.plan_id)
            payload = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            payload["scenario_id"] = "lab02.default"
            (run / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            changed = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertNotEqual(first.plan_id, changed.plan_id)

    def test_plan_json_partitions_eligible_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "new", finished_at="2026-07-20T12:01:00+00:00")
            _make_run(root, "old", finished_at="2026-07-20T12:00:00+00:00")
            (root / "unknown").mkdir()
            plan = build_cleanup_plan(root, keep=1, allowed_root=root)
            payload = plan.to_dict()
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["plan_id"], plan.plan_id)
            self.assertEqual(
                {item["name"] for item in payload["eligible"]},
                {item["name"] for item in payload["retained"]}
                | {item["name"] for item in payload["selected"]},
            )
            self.assertEqual(
                {item["name"] for item in payload["retained"]}
                & {item["name"] for item in payload["selected"]},
                set(),
            )

    def test_lone_surrogate_metadata_is_hashed_without_raw_encoding_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "run", scenario_id="lab01.\ud800")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            self.assertEqual(len(plan.selected), 1)
            self.assertRegex(plan.plan_id, r"[0-9a-f]{64}")

    def test_legacy_recursive_sizer_translates_recursion_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp).resolve() / "run"
            run.mkdir()
            from mclab.output_safety import saved_run_size_bytes

            with patch(
                "mclab.output_safety._physical_tree_size",
                side_effect=RecursionError("injected deep tree"),
            ):
                with self.assertRaisesRegex(CleanupSafetyError, "nested too deeply"):
                    saved_run_size_bytes(run)


class CleanupQuarantineTests(unittest.TestCase):
    def test_mixed_plan_moves_exactly_selected_runs_and_preserves_every_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            oldest = _make_run(root, "oldest", finished_at="2026-07-20T12:00:00+00:00")
            middle = _make_run(root, "middle", finished_at="2026-07-20T12:01:00+00:00")
            newest = _make_run(root, "newest", finished_at="2026-07-20T12:02:00+00:00")
            internal = _make_run(root, "_internal")
            invalid = root / "invalid"
            invalid.mkdir()
            (invalid / "canary.txt").write_text("preserve", encoding="utf-8")
            preserved = _make_run(root, "preserved")
            (preserved / ".mclab-preserve").write_text("hold", encoding="utf-8")

            plan = build_cleanup_plan(root, keep=1, allowed_root=root)
            selected_names = tuple(entry.name for entry in plan.selected)
            self.assertEqual(set(selected_names), {"oldest", "middle"})
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )

            self.assertEqual(receipt.names, selected_names)
            self.assertFalse(oldest.exists())
            self.assertFalse(middle.exists())
            self.assertTrue(newest.is_dir())
            self.assertTrue(internal.is_dir())
            self.assertEqual((invalid / "canary.txt").read_text(encoding="utf-8"), "preserve")
            self.assertTrue(preserved.is_dir())

    def test_wrong_or_stale_plan_id_never_moves_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            with self.assertRaisesRegex(CleanupSafetyError, "plan ID"):
                quarantine_cleanup_plan(
                    plan,
                    expected_plan_id="0" * 64,
                    allowed_root=root,
                )
            self.assertTrue(run.exists())
            self.assertFalse((root / ".mclab-trash").exists())

            payload = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            payload["status"] = "stopped"
            (run / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(CleanupSafetyError, "changed"):
                quarantine_cleanup_plan(
                    plan,
                    expected_plan_id=plan.plan_id,
                    allowed_root=root,
                )
            self.assertTrue(run.exists())

    def test_root_replacement_before_first_write_moves_nothing(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows root handles block the replacement itself")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            outside = base / "outside"
            outside.mkdir()
            (outside / "canary.txt").write_text("preserve", encoding="utf-8")
            detached = base / "detached-outputs"

            import mclab.output_cleanup as cleanup

            original_ensure = cleanup._ensure_trash_root_rooted

            def replace_before_first_write(root_pin: object) -> tuple[str, ...]:
                root.rename(detached)
                root.symlink_to(outside, target_is_directory=True)
                return original_ensure(root_pin)

            try:
                with patch(
                    "mclab.output_cleanup._ensure_trash_root_rooted",
                    side_effect=replace_before_first_write,
                ):
                    with self.assertRaisesRegex(CleanupOperationError, "quarantine"):
                        quarantine_cleanup_plan(
                            plan,
                            expected_plan_id=plan.plan_id,
                            allowed_root=root,
                        )
            finally:
                if root.is_symlink():
                    root.unlink()
                if detached.exists():
                    detached.rename(root)
            self.assertTrue(run.is_dir())
            self.assertFalse((root / ".mclab-trash").exists())
            self.assertEqual((outside / "canary.txt").read_text(encoding="utf-8"), "preserve")
            self.assertFalse((outside / ".mclab-trash").exists())

    def test_source_swap_before_rename_is_reversed_without_parsing_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original_backup = root / "original-run-backup"

            from mclab.output_root import PinnedOutputRoot

            original_rename = PinnedOutputRoot.rename_noreplace
            swapped = False

            def swap_source_before_rename(
                root_pin: PinnedOutputRoot,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_source_identity: tuple[str, int, int],
            ) -> object:
                nonlocal swapped
                if not swapped and source == ("run",):
                    run.rename(original_backup)
                    run.mkdir()
                    (run / "attacker-canary.txt").write_text("preserve", encoding="utf-8")
                    swapped = True
                return original_rename(
                    root_pin,
                    source,
                    destination,
                    expected_source_identity=expected_source_identity,
                )

            with patch.object(
                PinnedOutputRoot,
                "rename_noreplace",
                new=swap_source_before_rename,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(swapped)
            self.assertTrue(original_backup.is_dir())
            self.assertTrue((run / "attacker-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_complete")
            self.assertEqual(list((receipt.path / "entries").iterdir()), [])

    @unittest.skipIf(os.name == "nt", "POSIX syscall-boundary replacement fixture")
    def test_source_swap_at_rename_syscall_is_detected_and_reversed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original_backup = root / "original-run-backup"

            from mclab import output_safety

            original_rename = output_safety._rename_directory_noreplace
            swapped = False

            def swap_at_syscall(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                if not swapped:
                    run.rename(original_backup)
                    run.mkdir()
                    (run / "attacker-canary.txt").write_text(
                        "preserve",
                        encoding="utf-8",
                    )
                    swapped = True
                original_rename(*args, **kwargs)  # type: ignore[arg-type]

            with patch(
                "mclab.output_safety._rename_directory_noreplace",
                side_effect=swap_at_syscall,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(swapped)
            self.assertTrue(original_backup.is_dir())
            self.assertTrue((run / "attacker-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_complete")
            self.assertEqual(list((receipt.path / "entries").iterdir()), [])

    @unittest.skipIf(os.name == "nt", "POSIX occupied-source recovery fixture")
    def test_raced_move_with_occupied_source_records_both_preserved_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original_backup = root / "original-run-backup"

            from mclab import output_safety

            original_rename = output_safety._rename_directory_noreplace
            swapped = False

            def swap_and_occupy_source(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                if not swapped:
                    run.rename(original_backup)
                    run.mkdir()
                    (run / "replacement-canary.txt").write_text(
                        "replacement",
                        encoding="utf-8",
                    )
                    original_rename(*args, **kwargs)  # type: ignore[arg-type]
                    run.mkdir()
                    (run / "occupant-canary.txt").write_text("occupant", encoding="utf-8")
                    swapped = True
                    return
                original_rename(*args, **kwargs)  # type: ignore[arg-type]

            with patch(
                "mclab.output_safety._rename_directory_noreplace",
                side_effect=swap_and_occupy_source,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(swapped)
            self.assertTrue((original_backup / "manifest.json").is_file())
            self.assertTrue((run / "occupant-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            staged = receipt.path / "entries" / "run"
            self.assertTrue((staged / "replacement-canary.txt").is_file())
            self.assertEqual(receipt.status, "rollback_failed")
            payload = json.loads((receipt.path / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["staged"], ["run"])

    @unittest.skipIf(os.name == "nt", "POSIX post-commit error fixture")
    def test_postcommit_error_with_recreated_source_remains_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            (run / "original-canary.txt").write_text("original", encoding="utf-8")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            from mclab import output_safety

            original_rename = output_safety._rename_directory_noreplace
            injected = False

            def commit_recreate_and_report_error(*args: object, **kwargs: object) -> None:
                nonlocal injected
                original_rename(*args, **kwargs)  # type: ignore[arg-type]
                if not injected:
                    run.mkdir()
                    (run / "new-canary.txt").write_text("new", encoding="utf-8")
                    injected = True
                    raise OSError("injected post-commit rename error")

            with patch(
                "mclab.output_safety._rename_directory_noreplace",
                side_effect=commit_recreate_and_report_error,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(injected)
            self.assertTrue((run / "new-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            staged = receipt.path / "entries" / "run"
            self.assertTrue((staged / "original-canary.txt").is_file())
            self.assertEqual(receipt.status, "rollback_failed")
            self.assertTrue(receipt.to_dict()["recoverable"])
            payload = json.loads((receipt.path / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["staged"], ["run"])

    @unittest.skipIf(os.name == "nt", "POSIX wrong-destination error fixture")
    def test_wrong_postcommit_destination_with_occupied_source_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            (run / "original-canary.txt").write_text("original", encoding="utf-8")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original_backup = root / "original-run-backup"

            from mclab import output_safety

            original_rename = output_safety._rename_directory_noreplace
            injected = False

            def move_replacement_recreate_and_error(*args: object, **kwargs: object) -> None:
                nonlocal injected
                if not injected:
                    run.rename(original_backup)
                    replacement = _make_run(root, "run")
                    (replacement / "replacement-canary.txt").write_text(
                        "replacement",
                        encoding="utf-8",
                    )
                    original_rename(*args, **kwargs)  # type: ignore[arg-type]
                    run.mkdir()
                    (run / "occupant-canary.txt").write_text("occupant", encoding="utf-8")
                    injected = True
                    raise OSError("injected wrong-destination post-commit error")
                original_rename(*args, **kwargs)  # type: ignore[arg-type]

            with patch(
                "mclab.output_safety._rename_directory_noreplace",
                side_effect=move_replacement_recreate_and_error,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(injected)
            self.assertTrue((original_backup / "original-canary.txt").is_file())
            self.assertTrue((run / "occupant-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            staged = receipt.path / "entries" / "run"
            self.assertTrue((staged / "replacement-canary.txt").is_file())
            self.assertEqual(receipt.status, "rollback_failed")
            self.assertTrue(receipt.to_dict()["recoverable"])
            payload = json.loads((receipt.path / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["staged"], ["run"])

    @unittest.skipIf(os.name == "nt", "POSIX post-commit reconciliation fixture")
    def test_postcommit_probe_failures_preserve_recoverable_receipt(self) -> None:
        for failure_point in (
            "source-presence",
            "destination-presence",
            "destination-open",
            "destination-fstat",
            "source-handle-close",
            "destination-parent-close",
            "source-parent-close",
        ):
            with self.subTest(failure_point=failure_point), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve() / "outputs"
                root.mkdir()
                run = _make_run(root, "run")
                (run / "original-canary.txt").write_text("original", encoding="utf-8")
                plan = build_cleanup_plan(root, keep=0, allowed_root=root)

                from mclab import output_safety

                original_rename = output_safety._rename_directory_noreplace
                original_exists = output_safety._relative_entry_exists
                original_open = output_safety.os.open
                original_fstat = output_safety.os.fstat
                original_close = output_safety.os.close
                committed = False
                injected = False
                presence_probes = 0
                postcommit_closes = 0

                def commit_and_recreate_source(*args: object, **kwargs: object) -> None:
                    nonlocal committed
                    original_rename(*args, **kwargs)  # type: ignore[arg-type]
                    if not committed:
                        run.mkdir()
                        (run / "new-canary.txt").write_text("new", encoding="utf-8")
                        committed = True

                def fail_presence_probe(
                    path: Path,
                    *,
                    parent_fd: int,
                ) -> bool:
                    nonlocal injected, presence_probes
                    if committed:
                        presence_probes += 1
                        target_probe = 1 if failure_point == "source-presence" else 2
                        if not injected and presence_probes == target_probe:
                            injected = True
                            raise OSError(f"injected {failure_point} failure")
                    return original_exists(path, parent_fd=parent_fd)

                def fail_destination_open(
                    path: object,
                    flags: int,
                    mode: int = 0o777,
                    *,
                    dir_fd: int | None = None,
                ) -> int:
                    nonlocal injected
                    if committed and not injected:
                        injected = True
                        raise OSError("injected destination-open failure")
                    if dir_fd is None:
                        return original_open(path, flags, mode)  # type: ignore[arg-type]
                    return original_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

                def fail_destination_fstat(descriptor: int) -> os.stat_result:
                    nonlocal injected
                    if committed and not injected:
                        injected = True
                        raise OSError("injected destination-fstat failure")
                    return original_fstat(descriptor)

                def fail_source_close(descriptor: int) -> None:
                    nonlocal injected, postcommit_closes
                    if committed:
                        postcommit_closes += 1
                        close_target = {
                            "source-handle-close": 2,
                            "destination-parent-close": 3,
                            "source-parent-close": 4,
                        }[failure_point]
                        if not injected and postcommit_closes == close_target:
                            injected = True
                            raise OSError(f"injected {failure_point} failure")
                    original_close(descriptor)

                probe_target = (
                    "mclab.output_safety._relative_entry_exists"
                    if failure_point.endswith("presence")
                    else (
                        "mclab.output_safety.os.open"
                        if failure_point == "destination-open"
                        else (
                            "mclab.output_safety.os.fstat"
                            if failure_point == "destination-fstat"
                            else "mclab.output_safety.os.close"
                        )
                    )
                )
                probe_effect = (
                    fail_presence_probe
                    if failure_point.endswith("presence")
                    else (
                        fail_destination_open
                        if failure_point == "destination-open"
                        else (
                            fail_destination_fstat
                            if failure_point == "destination-fstat"
                            else fail_source_close
                        )
                    )
                )
                with (
                    patch(
                        "mclab.output_safety._rename_directory_noreplace",
                        side_effect=commit_and_recreate_source,
                    ),
                    patch(probe_target, side_effect=probe_effect),
                ):
                    with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                        quarantine_cleanup_plan(
                            plan,
                            expected_plan_id=plan.plan_id,
                            allowed_root=root,
                        )

                self.assertTrue(committed)
                self.assertTrue(injected)
                self.assertTrue((run / "new-canary.txt").is_file())
                receipt = list_cleanup_receipts(root, allowed_root=root)[0]
                staged = receipt.path / "entries" / "run"
                self.assertTrue((staged / "original-canary.txt").is_file())
                self.assertEqual(receipt.status, "rollback_failed")
                self.assertTrue(receipt.to_dict()["recoverable"])
                payload = json.loads((receipt.path / "receipt.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["staged"], ["run"])

    @unittest.skipIf(os.name == "nt", "POSIX wrong-destination close fixture")
    def test_wrong_destination_with_restored_source_and_parent_close_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            (run / "original-canary.txt").write_text("original", encoding="utf-8")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            original_backup = root / "original-run-backup"

            from mclab import output_safety

            original_rename = output_safety._rename_directory_noreplace
            original_close = output_safety.os.close
            committed = False
            injected = False
            postcommit_closes = 0

            def move_replacement_and_restore_expected(*args: object, **kwargs: object) -> None:
                nonlocal committed
                run.rename(original_backup)
                replacement = _make_run(root, "run")
                (replacement / "replacement-canary.txt").write_text(
                    "replacement",
                    encoding="utf-8",
                )
                original_rename(*args, **kwargs)  # type: ignore[arg-type]
                original_backup.rename(run)
                committed = True

            def fail_destination_parent_close(descriptor: int) -> None:
                nonlocal injected, postcommit_closes
                if committed:
                    postcommit_closes += 1
                    if not injected and postcommit_closes == 3:
                        injected = True
                        raise OSError("injected destination-parent close failure")
                original_close(descriptor)

            with (
                patch(
                    "mclab.output_safety._rename_directory_noreplace",
                    side_effect=move_replacement_and_restore_expected,
                ),
                patch(
                    "mclab.output_safety.os.close",
                    side_effect=fail_destination_parent_close,
                ),
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(committed)
            self.assertTrue(injected)
            self.assertTrue((run / "original-canary.txt").is_file())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            staged = receipt.path / "entries" / "run"
            self.assertTrue((staged / "replacement-canary.txt").is_file())
            self.assertEqual(receipt.status, "rollback_failed")
            self.assertTrue(receipt.to_dict()["recoverable"])
            payload = json.loads((receipt.path / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["staged"], ["run"])

    def test_root_detach_after_move_is_detected_and_rolled_back_anchored(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows root handles block the replacement itself")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            detached = base / "detached-outputs"
            outside = base / "outside"
            outside.mkdir()
            (outside / "canary.txt").write_text("preserve", encoding="utf-8")

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            swapped = False

            def detach_after_move(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal swapped
                result = original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )
                if not swapped and source == ("run",):
                    root.rename(detached)
                    root.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return result

            try:
                with patch(
                    "mclab.output_cleanup._move_directory_rooted",
                    side_effect=detach_after_move,
                ):
                    with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                        quarantine_cleanup_plan(
                            plan,
                            expected_plan_id=plan.plan_id,
                            allowed_root=root,
                        )
            finally:
                if root.is_symlink():
                    root.unlink()
                if detached.exists():
                    detached.rename(root)
            self.assertTrue(swapped)
            self.assertTrue(run.is_dir())
            self.assertEqual((outside / "canary.txt").read_text(encoding="utf-8"), "preserve")
            self.assertFalse((outside / ".mclab-trash").exists())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_complete")

    def test_entries_directory_replacement_after_move_uses_pinned_rollback(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows directory handles block the replacement itself")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            replaced = False
            entries_backup: Path | None = None
            replacement_entries: Path | None = None

            def replace_entries_after_move(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal replaced, entries_backup, replacement_entries
                result = original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )
                if not replaced and source == ("run",):
                    entries = root.joinpath(*destination[:-1])
                    entries_backup = entries.with_name("entries-backup")
                    entries.rename(entries_backup)
                    entries.mkdir()
                    replacement_entries = entries
                    replaced = True
                return result

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=replace_entries_after_move,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(replaced)
            self.assertTrue(run.is_dir())
            self.assertIsNotNone(entries_backup)
            self.assertIsNotNone(replacement_entries)
            self.assertEqual(list(entries_backup.iterdir()), [])  # type: ignore[union-attr]
            self.assertEqual(list(replacement_entries.iterdir()), [])  # type: ignore[union-attr]
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_complete")

    def test_quarantine_and_restore_are_receipted_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            selected = _make_run(root, "old", finished_at="2026-07-20T12:00:00+00:00")
            retained = _make_run(root, "new", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=1, allowed_root=root)

            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            self.assertEqual(receipt.status, "quarantined")
            self.assertFalse(selected.exists())
            self.assertTrue(retained.exists())
            self.assertTrue((receipt.path / "entries" / "old").is_dir())
            self.assertEqual(
                [item.receipt_id for item in list_cleanup_receipts(root, allowed_root=root)],
                [receipt.receipt_id],
            )

            restored = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(restored.status, "restored")
            self.assertTrue(selected.exists())
            self.assertTrue(retained.exists())

    @unittest.skipIf(os.name == "nt", "POSIX permission-bit identity fixture")
    def test_root_permission_change_does_not_orphan_a_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            original_mode = stat.S_IMODE(root.stat().st_mode)
            root.chmod(original_mode ^ stat.S_IWGRP)
            try:
                listed = list_cleanup_receipts(root, allowed_root=root)
                self.assertEqual([item.receipt_id for item in listed], [receipt.receipt_id])
                restored = restore_cleanup_receipt(
                    root,
                    receipt.receipt_id,
                    allowed_root=root,
                )
            finally:
                root.chmod(original_mode)
            self.assertEqual(restored.status, "restored")
            self.assertTrue(run.is_dir())

    def test_operation_lock_blocks_restore_and_marks_receipts_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            from mclab.output_root import pinned_output_root

            with pinned_output_root(root, allowed_root=root) as (_root, _exists, root_pin):
                assert root_pin is not None
                with root_pin.operation_lock():
                    with self.assertRaisesRegex(CleanupOperationError, "Another saved-output"):
                        restore_cleanup_receipt(
                            root,
                            receipt.receipt_id,
                            allowed_root=root,
                        )
                    listed = list_cleanup_receipts(root, allowed_root=root)
                    self.assertTrue(listed[0].operation_active)
                    self.assertFalse(listed[0].to_dict()["recoverable"])
            self.assertFalse(run.exists())
            restored = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(restored.status, "restored")
            self.assertTrue(run.is_dir())

    def test_operation_lock_is_enforced_across_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            sentinel = base / "lock-ready"
            script = """
import sys
import time
from pathlib import Path
from mclab.output_root import pinned_output_root

root = Path(sys.argv[1])
sentinel = Path(sys.argv[2])
with pinned_output_root(root, allowed_root=root) as (_root, _exists, root_pin):
    assert root_pin is not None
    with root_pin.operation_lock():
        sentinel.write_text("ready", encoding="utf-8")
        time.sleep(30)
"""
            environment = os.environ.copy()
            source_root = str(Path(__file__).resolve().parents[1] / "src")
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, (source_root, environment.get("PYTHONPATH", "")))
            )
            process = subprocess.Popen(
                [sys.executable, "-c", script, str(root), str(sentinel)],
                env=environment,
            )
            try:
                for _attempt in range(250):
                    if sentinel.is_file() or process.poll() is not None:
                        break
                    time.sleep(0.02)
                self.assertTrue(sentinel.is_file(), "child process did not acquire the lock")
                with self.assertRaisesRegex(CleanupOperationError, "Another saved-output"):
                    restore_cleanup_receipt(
                        root,
                        receipt.receipt_id,
                        allowed_root=root,
                    )
                self.assertFalse(run.exists())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            restored = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(restored.status, "restored")
            self.assertTrue(run.is_dir())

    def test_receipt_size_is_preflighted_before_any_run_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            first = _make_run(root, "first")
            second = _make_run(root, "second")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            with patch("mclab.output_receipts.MAX_RECEIPT_BYTES", 512):
                with self.assertRaisesRegex(CleanupOperationError, "safety limit"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertFalse((root / ".mclab-trash").exists())

    def test_restore_final_receipt_size_is_preflighted_before_any_move(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            receipt_file = receipt.path / "receipt.json"
            constrained_limit = receipt_file.stat().st_size + 1
            with patch(
                "mclab.output_receipts.MAX_RECEIPT_BYTES",
                constrained_limit,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "safety limit"):
                    restore_cleanup_receipt(
                        root,
                        receipt.receipt_id,
                        allowed_root=root,
                    )
            self.assertFalse(run.exists())
            self.assertTrue((receipt.path / "entries" / "run").is_dir())
            current = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(current.status, "quarantined")

    def test_copied_receipt_cannot_restore_into_a_replacement_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            original = base / "original-outputs"
            root.rename(original)
            shutil.copytree(original, root)

            with self.assertRaisesRegex(CleanupSafetyError, "replaced outputs root"):
                list_cleanup_receipts(root, allowed_root=root)
            with self.assertRaisesRegex(CleanupSafetyError, "replaced outputs root"):
                restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertFalse((root / "run").exists())
            self.assertTrue(
                (root / ".mclab-trash" / receipt.receipt_id / "entries" / "run").is_dir()
            )
            self.assertTrue(
                (original / ".mclab-trash" / receipt.receipt_id / "entries" / "run").is_dir()
            )

    def test_restore_collision_preserves_both_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            replacement = root / "run"
            replacement.mkdir()
            (replacement / "canary.txt").write_text("new", encoding="utf-8")

            with self.assertRaisesRegex(CleanupSafetyError, "already exists"):
                restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertEqual((replacement / "canary.txt").read_text(encoding="utf-8"), "new")
            self.assertTrue((receipt.path / "entries" / "run").is_dir())

    def test_restore_source_swap_is_reversed_and_never_reported_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            staged = receipt.path / "entries" / "run"
            original_backup = receipt.path / "original-run-backup"

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            swapped = False

            def swap_staged_source_before_restore(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal swapped
                if not swapped and "entries" in source[:-1] and destination == ("run",):
                    staged.rename(original_backup)
                    staged.mkdir()
                    (staged / "replacement-canary.txt").write_text(
                        "preserve",
                        encoding="utf-8",
                    )
                    swapped = True
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=swap_staged_source_before_restore,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)

            self.assertTrue(swapped)
            self.assertFalse((root / "run").exists())
            self.assertTrue(original_backup.is_dir())
            self.assertTrue((staged / "replacement-canary.txt").is_file())
            current = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(current.status, "quarantined")

    def test_move_refuses_a_destination_created_after_the_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "source-canary.txt").write_text("source", encoding="utf-8")
            (destination / "destination-canary.txt").write_text(
                "destination",
                encoding="utf-8",
            )

            from mclab.output_safety import _rename_directory_noreplace

            with self.assertRaises(OSError):
                _rename_directory_noreplace(source, destination)

            self.assertEqual(
                (source / "source-canary.txt").read_text(encoding="utf-8"),
                "source",
            )
            self.assertEqual(
                (destination / "destination-canary.txt").read_text(encoding="utf-8"),
                "destination",
            )

    def test_restore_move_failure_rolls_back_every_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            restore_calls = 0

            def fail_second_restore(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal restore_calls
                if "entries" in source[:-1]:
                    restore_calls += 1
                    if restore_calls == 2:
                        raise OSError("injected restore failure")
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=fail_second_restore,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertFalse((root / "first").exists())
            self.assertFalse((root / "second").exists())
            self.assertEqual(
                {path.name for path in (receipt.path / "entries").iterdir()},
                {"first", "second"},
            )

    def test_partial_restore_rollback_can_converge_on_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            restore_calls = 0
            rollback_failed = False

            def fail_restore_and_first_rollback(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal restore_calls, rollback_failed
                if "entries" in source[:-1]:
                    restore_calls += 1
                    if restore_calls == 2:
                        raise OSError("injected restore failure")
                elif "entries" in destination[:-1] and not rollback_failed:
                    rollback_failed = True
                    raise OSError("injected restore rollback failure")
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=fail_restore_and_first_rollback,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)

            partial = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(partial.status, "restore_rollback_failed")
            recovered = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(recovered.status, "restored")
            self.assertTrue((root / "first").is_dir())
            self.assertTrue((root / "second").is_dir())

    def test_stage_failure_rolls_back_every_moved_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            calls = 0

            def fail_second_source(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal calls
                if len(source) == 1:
                    calls += 1
                    if calls == 2:
                        raise OSError("injected stage failure")
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=fail_second_source,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )
            self.assertTrue((root / "first").is_dir())
            self.assertTrue((root / "second").is_dir())

    def test_partial_rollback_receipt_can_converge_to_a_full_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            stage_calls = 0
            rollback_failed = False

            def fail_stage_and_first_rollback(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal stage_calls, rollback_failed
                if len(source) == 1:
                    stage_calls += 1
                    if stage_calls == 2:
                        raise OSError("injected stage failure")
                elif not rollback_failed:
                    rollback_failed = True
                    raise OSError("injected rollback failure")
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=fail_stage_and_first_rollback,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_failed")
            self.assertEqual(
                sum((root / name).exists() for name in ("first", "second")),
                1,
            )
            recovered = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(recovered.status, "restored")
            self.assertTrue((root / "first").is_dir())
            self.assertTrue((root / "second").is_dir())

    def test_rollback_refuses_a_swapped_staged_source_and_stays_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            first_staged_name = plan.selected[0].name

            import mclab.output_cleanup as cleanup

            original_move = cleanup._move_directory_rooted
            stage_calls = 0
            detached_original: Path | None = None
            replacement: Path | None = None

            def swap_first_staged_before_rollback(
                root_pin: object,
                source: tuple[str, ...],
                destination: tuple[str, ...],
                *,
                expected_token: str,
            ) -> object:
                nonlocal stage_calls, detached_original, replacement
                if len(source) == 1:
                    stage_calls += 1
                    if stage_calls == 2:
                        entries = root.joinpath(*destination[:-1])
                        staged = entries / first_staged_name
                        detached_original = entries / "detached-original"
                        staged.rename(detached_original)
                        replacement = _make_run(entries, first_staged_name)
                        (replacement / "replacement-canary.txt").write_text(
                            "preserve",
                            encoding="utf-8",
                        )
                        raise OSError("injected second-stage failure")
                return original_move(
                    root_pin,
                    source,
                    destination,
                    expected_token=expected_token,
                )

            with patch(
                "mclab.output_cleanup._move_directory_rooted",
                side_effect=swap_first_staged_before_rollback,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rollback was incomplete"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertIsNotNone(detached_original)
            self.assertIsNotNone(replacement)
            self.assertTrue(detached_original.is_dir())  # type: ignore[union-attr]
            self.assertTrue(
                (replacement / "replacement-canary.txt").is_file()  # type: ignore[operator]
            )
            self.assertFalse((root / first_staged_name).exists())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_failed")
            self.assertTrue(receipt.to_dict()["recoverable"])

    def test_interrupted_staging_receipt_can_converge_to_a_full_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "first", finished_at="2026-07-20T12:00:00+00:00")
            _make_run(root, "second", finished_at="2026-07-20T12:01:00+00:00")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            import mclab.output_cleanup as cleanup

            original_write = cleanup._write_receipt_payload_rooted
            def interrupt_after_first_move(
                root_pin: object,
                receipt_relative: tuple[str, ...],
                payload: dict[str, object],
            ) -> None:
                if payload.get("status") == "staging" and payload.get("staged"):
                    raise KeyboardInterrupt("injected process interruption")
                original_write(root_pin, receipt_relative, payload)

            with patch(
                "mclab.output_cleanup._write_receipt_payload_rooted",
                side_effect=interrupt_after_first_move,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "staging")
            recovered = restore_cleanup_receipt(
                root,
                receipt.receipt_id,
                allowed_root=root,
            )
            self.assertEqual(recovered.status, "restored")
            self.assertTrue((root / "first").is_dir())
            self.assertTrue((root / "second").is_dir())

    def test_corrupt_matching_receipt_is_reported_instead_of_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            trash = root / ".mclab-trash"
            receipt = trash / "20260720T120000Z_aaaaaaaaaaaa_bbbbbbbb"
            receipt.mkdir(parents=True)
            (receipt / "receipt.json").write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(CleanupSafetyError, "unreadable or unsafe"):
                list_cleanup_receipts(root, allowed_root=root)

    def test_tampered_receipt_root_and_entry_name_are_rejected(self) -> None:
        for mutation, message in (
            (
                lambda payload: payload.update(schema_version=True),
                "Unsupported cleanup receipt schema",
            ),
            (lambda payload: payload.update(root="/outside"), "different outputs root"),
            (
                lambda payload: payload.update(root_token="0" * 64),
                "replaced outputs root",
            ),
            (
                lambda payload: payload["entries"].__setitem__(
                    0,
                    {"name": "../escape", "token": payload["entries"][0]["token"]},
                ),
                "unsafe entry name",
            ),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve() / "outputs"
                root.mkdir()
                _make_run(root, "run")
                plan = build_cleanup_plan(root, keep=0, allowed_root=root)
                receipt = quarantine_cleanup_plan(
                    plan,
                    expected_plan_id=plan.plan_id,
                    allowed_root=root,
                )
                receipt_file = receipt.path / "receipt.json"
                payload = json.loads(receipt_file.read_text(encoding="utf-8"))
                mutation(payload)
                receipt_file.write_text(json.dumps(payload), encoding="utf-8")

                with self.assertRaisesRegex(CleanupSafetyError, message):
                    restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
                self.assertFalse((root / "run").exists())
                self.assertTrue((receipt.path / "entries" / "run").is_dir())

    def test_tampered_receipt_token_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            receipt_file = receipt.path / "receipt.json"
            payload = json.loads(receipt_file.read_text(encoding="utf-8"))
            payload["entries"][0]["token"] = "0" * 64
            receipt_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(CleanupSafetyError, "changed"):
                restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertFalse((root / "run").exists())

    def test_staged_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )
            staged = receipt.path / "entries" / "run"
            backup = receipt.path / "original-run-backup"
            staged.replace(backup)
            outside = Path(tmp).resolve() / "outside"
            outside.mkdir()
            try:
                staged.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertTrue(outside.is_dir())
            self.assertTrue(backup.is_dir())

    def test_initial_receipt_failure_removes_only_the_empty_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            with patch(
                "mclab.output_cleanup._write_receipt_payload_rooted",
                side_effect=CleanupOperationError("injected initial receipt failure"),
            ):
                with self.assertRaisesRegex(CleanupOperationError, "initial receipt"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )

            self.assertTrue(run.is_dir())
            self.assertEqual(list_cleanup_receipts(root, allowed_root=root), ())
            trash = root / ".mclab-trash"
            self.assertTrue(trash.is_dir())
            self.assertEqual(list(trash.iterdir()), [])

    def test_final_quarantine_receipt_failure_rolls_back_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)

            import mclab.output_cleanup as cleanup

            original_write = cleanup._write_receipt_payload_rooted
            def fail_final_status(
                root_pin: object,
                receipt_relative: tuple[str, ...],
                payload: dict[str, object],
            ) -> None:
                if payload.get("status") == "quarantined":
                    raise CleanupOperationError("injected final receipt failure")
                original_write(root_pin, receipt_relative, payload)

            with patch(
                "mclab.output_cleanup._write_receipt_payload_rooted",
                side_effect=fail_final_status,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    quarantine_cleanup_plan(
                        plan,
                        expected_plan_id=plan.plan_id,
                        allowed_root=root,
                    )
            self.assertTrue(run.is_dir())
            receipt = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(receipt.status, "rollback_complete")

    def test_final_restore_receipt_failure_rolls_back_the_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            plan = build_cleanup_plan(root, keep=0, allowed_root=root)
            receipt = quarantine_cleanup_plan(
                plan,
                expected_plan_id=plan.plan_id,
                allowed_root=root,
            )

            import mclab.output_cleanup as cleanup

            original_write = cleanup._write_receipt_payload_rooted
            def fail_final_status(
                root_pin: object,
                receipt_relative: tuple[str, ...],
                payload: dict[str, object],
            ) -> None:
                if payload.get("status") == "restored":
                    raise CleanupOperationError("injected restore receipt failure")
                original_write(root_pin, receipt_relative, payload)

            with patch(
                "mclab.output_cleanup._write_receipt_payload_rooted",
                side_effect=fail_final_status,
            ):
                with self.assertRaisesRegex(CleanupOperationError, "rolled back"):
                    restore_cleanup_receipt(root, receipt.receipt_id, allowed_root=root)
            self.assertFalse(run.exists())
            self.assertTrue((receipt.path / "entries" / "run").is_dir())
            current = list_cleanup_receipts(root, allowed_root=root)[0]
            self.assertEqual(current.status, "quarantined")

    def test_single_run_quarantine_requires_name_and_fresh_identity_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = _make_run(root, "run")
            token = run_identity_token(run, allow_legacy=True)

            with self.assertRaisesRegex(CleanupSafetyError, "exact folder name"):
                quarantine_run(
                    root,
                    run,
                    confirmation="wrong",
                    expected_token=token,
                    allowed_root=root,
                )
            self.assertTrue(run.exists())

            manifest = run / "manifest.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(CleanupSafetyError, "changed"):
                quarantine_run(
                    root,
                    run,
                    confirmation="run",
                    expected_token=token,
                    allowed_root=root,
                )
            self.assertTrue(run.exists())

    def test_single_run_rejects_internal_sibling_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            real = _make_run(root, "real")
            alias = root / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")

            with self.assertRaisesRegex(CleanupSafetyError, "link or reparse"):
                run_identity_token(alias, allow_legacy=True)
            self.assertTrue(real.exists())

    def test_invalid_manifest_cannot_fall_back_to_a_legacy_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            run = root / "partial-run"
            run.mkdir()
            (run / "manifest.json").write_text("{", encoding="utf-8")
            (run / "summary.json").write_text(
                json.dumps({"lab_name": "lab01_msd"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CleanupSafetyError, "metadata"):
                run_identity_token(run, allow_legacy=True)
            self.assertTrue(run.is_dir())

    def test_single_run_rejects_running_and_preserved_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "outputs"
            root.mkdir()
            running = _make_run(root, "running", status="running")
            running_token = run_identity_token(running, allow_legacy=True)
            with self.assertRaisesRegex(CleanupSafetyError, "Running or unknown-status"):
                quarantine_run(
                    root,
                    running,
                    confirmation=running.name,
                    expected_token=running_token,
                    allowed_root=root,
                )

            preserved = _make_run(root, "preserved")
            (preserved / ".mclab-preserve").write_text("hold", encoding="utf-8")
            preserved_token = run_identity_token(preserved, allow_legacy=True)
            with self.assertRaisesRegex(CleanupSafetyError, "preserve"):
                quarantine_run(
                    root,
                    preserved,
                    confirmation=preserved.name,
                    expected_token=preserved_token,
                    allowed_root=root,
                )

            legacy = root / "legacy"
            legacy.mkdir()
            (legacy / "summary.json").write_text(
                json.dumps({"lab_name": "lab01_msd"}),
                encoding="utf-8",
            )
            legacy_token = run_identity_token(legacy, allow_legacy=True)
            with self.assertRaisesRegex(CleanupSafetyError, "Legacy saved runs"):
                quarantine_run(
                    root,
                    legacy,
                    confirmation=legacy.name,
                    expected_token=legacy_token,
                    allowed_root=root,
                )

            incomplete = root / "incomplete-modern"
            incomplete.mkdir()
            (incomplete / "manifest.json").write_text(
                json.dumps({"scenario_id": "lab01.default", "status": "completed"}),
                encoding="utf-8",
            )
            incomplete_token = run_identity_token(incomplete, allow_legacy=True)
            with self.assertRaisesRegex(CleanupSafetyError, "strict terminal"):
                quarantine_run(
                    root,
                    incomplete,
                    confirmation=incomplete.name,
                    expected_token=incomplete_token,
                    allowed_root=root,
                )
            self.assertTrue(running.is_dir())
            self.assertTrue(preserved.is_dir())
            self.assertTrue(legacy.is_dir())
            self.assertTrue(incomplete.is_dir())


if __name__ == "__main__":
    unittest.main()
