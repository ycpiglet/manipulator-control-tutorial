from __future__ import annotations

import hashlib
import io
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mclab.application import assets
from mclab.cli import build_parser, main


RUNTIME_RELATIVE = Path("third_party/mujoco_menagerie/franka_emika_panda")


class AssetContractTests(unittest.TestCase):
    def test_valid_existing_tree_is_verified_without_network_access(self) -> None:
        files = {"LICENSE": b"license", "scene.xml": b"<mujoco/>"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            with patch.object(assets, "_download") as download:
                installed = assets.install_assets(root)

            self.assertEqual(installed, target)
            download.assert_not_called()
            result = assets.verify_assets(root)
            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.total_bytes, 16)

    def test_missing_parent_that_becomes_a_symlink_cannot_verify(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            base = Path(tmp)
            root = base / "project"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            outside_target = outside / "mujoco_menagerie" / "franka_emika_panda"
            outside_target.mkdir(parents=True)
            (outside_target / "scene.xml").write_bytes(b"trusted")
            original_verify = assets._verify_runtime_tree
            swapped = False

            def swap_missing_parent(path: Path) -> assets.AssetVerification:
                nonlocal swapped
                if path == root / RUNTIME_RELATIVE and not swapped:
                    swapped = True
                    try:
                        (root / "third_party").symlink_to(outside, target_is_directory=True)
                    except OSError as exc:
                        self.skipTest(f"directory symlinks are unavailable: {exc}")
                return original_verify(path)

            with patch.object(
                assets,
                "_verify_runtime_tree",
                side_effect=swap_missing_parent,
            ):
                with self.assertRaisesRegex(assets.AssetSafetyError, "link or reparse point"):
                    assets.verify_assets(root)

            self.assertTrue(swapped)

    def test_valid_existing_target_identity_is_rechecked_before_early_return(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            original_verify = assets._verify_runtime_tree

            def replace_after_verification(path: Path) -> assets.AssetVerification:
                result = original_verify(path)
                if path == target:
                    target.rename(root / "verified-original")
                    target.mkdir()
                    (target / "owner.txt").write_bytes(b"foreign")
                return result

            with (
                patch.object(
                    assets, "_verify_runtime_tree", side_effect=replace_after_verification
                ),
                patch.object(assets, "_download") as download,
            ):
                with self.assertRaisesRegex(assets.AssetSafetyError, "changed identity"):
                    assets.install_assets(root)

            download.assert_not_called()
            self.assertEqual((target / "owner.txt").read_bytes(), b"foreign")

    def test_install_lock_blocks_another_process_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempted = root / "child-lock-attempted"
            acquired = root / "child-acquired"
            source_root = Path(__file__).resolve().parents[1] / "src"
            environment = os.environ.copy()
            previous_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                value for value in (os.fspath(source_root), previous_pythonpath) if value
            )
            child_code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from mclab.application import assets\n"
                "root, attempted, acquired = map(Path, sys.argv[1:])\n"
                "original_lock = assets._lock_descriptor\n"
                "def tracked_lock(descriptor):\n"
                "    attempted.write_text('attempted', encoding='utf-8')\n"
                "    original_lock(descriptor)\n"
                "assets._lock_descriptor = tracked_lock\n"
                "with assets._exclusive_asset_install_lock(assets._absolute_path(root)):\n"
                "    acquired.write_text('acquired', encoding='utf-8')\n"
            )
            process: subprocess.Popen[str] | None = None
            try:
                with assets._exclusive_asset_install_lock(assets._absolute_path(root)):
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            child_code,
                            os.fspath(root),
                            os.fspath(attempted),
                            os.fspath(acquired),
                        ],
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    deadline = time.monotonic() + 5.0
                    while not attempted.exists() and process.poll() is None:
                        if time.monotonic() >= deadline:
                            break
                        time.sleep(0.01)
                    self.assertTrue(attempted.exists())
                    self.assertFalse(acquired.exists())

                stdout, stderr = process.communicate(timeout=5.0)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertTrue(acquired.exists())
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5.0)

    def test_install_lock_serializes_physical_project_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            physical_parent = base / "physical-parent"
            physical_parent.mkdir()
            root = physical_parent / "project"
            root.mkdir()
            alias_parent = base / "alias-parent"
            try:
                alias_parent.symlink_to(physical_parent, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")
            alias = alias_parent / "project"
            physical_root = assets._absolute_path(root)
            alias_root = assets._absolute_path(alias)
            self.assertEqual(
                assets._asset_install_lock_path(physical_root),
                assets._asset_install_lock_path(alias_root),
            )

            attempted = base / "alias-lock-attempted"
            acquired = base / "alias-lock-acquired"
            source_root = Path(__file__).resolve().parents[1] / "src"
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                value for value in (os.fspath(source_root), environment.get("PYTHONPATH")) if value
            )
            child_code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from mclab.application import assets\n"
                "root, attempted, acquired = map(Path, sys.argv[1:])\n"
                "original_lock = assets._lock_descriptor\n"
                "def tracked_lock(descriptor):\n"
                "    attempted.write_text('attempted', encoding='utf-8')\n"
                "    original_lock(descriptor)\n"
                "assets._lock_descriptor = tracked_lock\n"
                "with assets._exclusive_asset_install_lock(assets._absolute_path(root)):\n"
                "    acquired.write_text('acquired', encoding='utf-8')\n"
            )
            process: subprocess.Popen[str] | None = None
            try:
                with assets._exclusive_asset_install_lock(physical_root):
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            child_code,
                            os.fspath(alias_root),
                            os.fspath(attempted),
                            os.fspath(acquired),
                        ],
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    deadline = time.monotonic() + 5.0
                    while not attempted.exists() and process.poll() is None:
                        if time.monotonic() >= deadline:
                            break
                        time.sleep(0.01)
                    self.assertTrue(attempted.exists())
                    self.assertFalse(acquired.exists())
                stdout, stderr = process.communicate(timeout=5.0)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertTrue(acquired.exists())
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5.0)

    def test_install_lock_rejects_symlink_before_writing_without_nofollow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = assets._absolute_path(Path(tmp))
            foreign = root / "foreign-lock-target"
            foreign.write_bytes(b"")
            lock_path = assets._asset_install_lock_path(root)
            lock_path.unlink(missing_ok=True)
            self.assertFalse(os.path.lexists(lock_path))
            try:
                lock_path.symlink_to(foreign)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")
            try:
                with (
                    patch.object(assets.os, "O_NOFOLLOW", 0, create=True),
                    self.assertRaisesRegex(
                        assets.AssetSafetyError,
                        "private current-user physical file",
                    ),
                ):
                    with assets._exclusive_asset_install_lock(root):
                        self.fail("unsafe lock path was acquired")
                self.assertEqual(foreign.read_bytes(), b"")
            finally:
                lock_path.unlink(missing_ok=True)

    def test_install_lock_does_not_create_dangling_symlink_referent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = assets._absolute_path(Path(tmp))
            foreign = root / "missing-foreign-lock-target"
            lock_path = assets._asset_install_lock_path(root)
            lock_path.unlink(missing_ok=True)
            self.assertFalse(os.path.lexists(lock_path))
            try:
                lock_path.symlink_to(foreign)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")
            try:
                with (
                    patch.object(assets.os, "O_NOFOLLOW", 0, create=True),
                    self.assertRaisesRegex(
                        assets.AssetSafetyError,
                        "private current-user physical file",
                    ),
                ):
                    with assets._exclusive_asset_install_lock(root):
                        self.fail("unsafe lock path was acquired")
                self.assertFalse(foreign.exists())
            finally:
                lock_path.unlink(missing_ok=True)

    def test_install_lock_rejects_hardlink_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = assets._absolute_path(Path(tmp))
            foreign = root / "foreign-lock-target"
            foreign.write_bytes(b"")
            lock_path = assets._asset_install_lock_path(root)
            lock_path.unlink(missing_ok=True)
            self.assertFalse(os.path.lexists(lock_path))
            try:
                os.link(foreign, lock_path)
            except OSError as exc:
                self.skipTest(f"hard links are unavailable: {exc}")
            try:
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "private current-user physical file",
                ):
                    with assets._exclusive_asset_install_lock(root):
                        self.fail("unsafe lock path was acquired")
                self.assertEqual(foreign.read_bytes(), b"")
            finally:
                lock_path.unlink(missing_ok=True)

    @unittest.skipUnless(hasattr(os, "geteuid"), "POSIX ownership metadata is unavailable")
    def test_install_lock_rejects_foreign_owner_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = assets._absolute_path(Path(tmp))
            lock_path = assets._asset_install_lock_path(root)
            lock_path.unlink(missing_ok=True)
            self.assertFalse(os.path.lexists(lock_path))
            try:
                with (
                    patch.object(assets.os, "geteuid", return_value=os.geteuid() + 1),
                    self.assertRaisesRegex(
                        assets.AssetSafetyError,
                        "private current-user physical file",
                    ),
                ):
                    with assets._exclusive_asset_install_lock(root):
                        self.fail("foreign-owned lock path was acquired")
                self.assertEqual(lock_path.read_bytes(), b"")
            finally:
                lock_path.unlink(missing_ok=True)

    def test_concurrent_initial_installs_serialize_and_keep_valid_target(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            original_lock = assets._lock_descriptor
            original_extract = assets._extract_panda
            second_lock_attempt = threading.Event()
            attempt_guard = threading.Lock()
            result_guard = threading.Lock()
            start = threading.Barrier(3)
            attempts = 0
            extraction_count = 0
            results: list[Path] = []
            errors: list[BaseException] = []

            def tracked_lock(descriptor: int) -> None:
                nonlocal attempts
                with attempt_guard:
                    attempts += 1
                    if attempts == 2:
                        second_lock_attempt.set()
                original_lock(descriptor)

            def synchronized_extract(source: Path, staging: Path) -> None:
                nonlocal extraction_count
                original_extract(source, staging)
                extraction_count += 1
                if not second_lock_attempt.wait(timeout=5.0):
                    raise AssertionError("second installer never attempted the shared lock")

            def install_worker() -> None:
                start.wait()
                try:
                    result = assets.install_assets(root, archive_path=archive)
                except BaseException as exc:
                    with result_guard:
                        errors.append(exc)
                else:
                    with result_guard:
                        results.append(result)

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_lock_descriptor", side_effect=tracked_lock),
                patch.object(assets, "_extract_panda", side_effect=synchronized_extract),
            ):
                workers = [threading.Thread(target=install_worker) for _ in range(2)]
                for worker in workers:
                    worker.start()
                start.wait()
                for worker in workers:
                    worker.join(timeout=10.0)

            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(extraction_count, 1)
            target = root / RUNTIME_RELATIVE
            self.assertEqual((target / "scene.xml").read_bytes(), b"trusted")
            assets.verify_assets(root)

    def test_target_not_owned_by_transaction_is_never_moved_or_deleted(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = root / RUNTIME_RELATIVE
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            original_extract = assets._extract_panda

            def create_foreign_target(source: Path, staging: Path) -> None:
                original_extract(source, staging)
                target.mkdir()
                (target / "owner.txt").write_bytes(b"foreign")

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_extract_panda", side_effect=create_foreign_target),
            ):
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "refusing to replace it",
                ):
                    assets.install_assets(root, archive_path=archive)

            self.assertEqual((target / "owner.txt").read_bytes(), b"foreign")
            self.assertEqual(list(target.parent.glob(".mclab-assets-*")), [])

    def test_invalid_existing_tree_is_rejected_without_network_access(self) -> None:
        files = {"scene.xml": b"expected"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"altered!"})
            with patch.object(assets, "_download") as download:
                with self.assertRaisesRegex(assets.AssetVerificationError, "SHA-256 mismatch"):
                    assets.install_assets(root)

            download.assert_not_called()
            self.assertEqual((target / "scene.xml").read_bytes(), b"altered!")

    def test_scene_only_tree_does_not_satisfy_a_multi_file_contract(self) -> None:
        files = {"LICENSE": b"license", "scene.xml": b"scene"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            _write_runtime_tree(root, {"scene.xml": b"scene"})

            with self.assertRaisesRegex(
                assets.AssetVerificationError, "missing runtime file: LICENSE"
            ):
                assets.verify_assets(root)
            with patch.object(assets, "_download") as download:
                with self.assertRaisesRegex(
                    assets.AssetVerificationError, "missing runtime file: LICENSE"
                ):
                    assets.install_assets(root)
            download.assert_not_called()

    def test_tampered_same_size_file_is_rejected_by_digest(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            _write_runtime_tree(root, {"scene.xml": b"changed"})

            with self.assertRaisesRegex(assets.AssetVerificationError, "SHA-256 mismatch"):
                assets.verify_assets(root)

    def test_missing_and_unknown_runtime_paths_are_rejected(self) -> None:
        files = {"assets/link.obj": b"mesh", "scene.xml": b"scene"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"scene"})
            (target / "surprise.txt").write_bytes(b"unknown")

            with self.assertRaises(assets.AssetVerificationError) as raised:
                assets.verify_assets(root)

            self.assertIn("missing runtime file: assets/link.obj", raised.exception.issues)
            self.assertIn("missing runtime directory: assets", raised.exception.issues)
            self.assertIn("unknown runtime file: surprise.txt", raised.exception.issues)

    def test_runtime_symlink_is_unsafe_even_with_force(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = root / RUNTIME_RELATIVE
            target.mkdir(parents=True)
            source = root / "outside.xml"
            source.write_bytes(b"trusted")
            try:
                (target / "scene.xml").symlink_to(source)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")

            with self.assertRaisesRegex(assets.AssetSafetyError, "link or reparse point"):
                assets.verify_assets(root)
            with patch.object(assets, "_download") as download:
                with self.assertRaises(assets.AssetSafetyError):
                    assets.install_assets(root, force=True)
            download.assert_not_called()

    def test_linked_asset_parent_and_target_root_are_rejected_before_download(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            base = Path(tmp)
            for linked_part in ("parent", "target"):
                with self.subTest(linked_part=linked_part):
                    root = base / linked_part
                    outside = base / f"outside-{linked_part}"
                    outside.mkdir()
                    try:
                        if linked_part == "parent":
                            link = root / "third_party" / "mujoco_menagerie"
                        else:
                            link = root / RUNTIME_RELATIVE
                        link.parent.mkdir(parents=True)
                        link.symlink_to(outside, target_is_directory=True)
                    except (NotImplementedError, OSError) as exc:
                        self.skipTest(f"directory symlinks are unavailable: {exc}")

                    with self.assertRaisesRegex(assets.AssetSafetyError, "link or reparse point"):
                        assets.verify_assets(root)
                    with patch.object(assets, "_download") as download:
                        with self.assertRaises(assets.AssetSafetyError):
                            assets.install_assets(root, force=True)
                    download.assert_not_called()

    def test_parent_swap_after_lock_revalidation_cannot_reach_outside_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_bytes(b"outside")
            original_check = assets._check_project_path

            def swap_parent(project_root: Path, *, create_parents: bool) -> None:
                original_check(project_root, create_parents=create_parents)
                parent = project_root / RUNTIME_RELATIVE.parent
                physical_parent = project_root / "physical-menagerie-parent"
                parent.rename(physical_parent)
                try:
                    parent.symlink_to(outside, target_is_directory=True)
                except (NotImplementedError, OSError) as exc:
                    physical_parent.rename(parent)
                    self.skipTest(f"directory symlinks are unavailable: {exc}")

            with patch.object(assets, "_check_project_path", side_effect=swap_parent):
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "link or reparse point",
                ):
                    assets.install_assets(root, archive_path=root / "unused.tar.gz")

            self.assertEqual(sentinel.read_bytes(), b"outside")
            self.assertFalse((outside / "franka_emika_panda").exists())

    def test_child_directory_swap_during_scan_is_rejected(self) -> None:
        files = {"assets/link.obj": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            outside = root / "outside-assets"
            outside.mkdir()
            (outside / "link.obj").write_bytes(b"trusted")
            original_scandir = os.scandir
            swapped = False

            def swap_before_scan(path: str | os.PathLike[str]):
                nonlocal swapped
                scanned_path = Path(path)
                child = target / "assets"
                if scanned_path == child and not swapped:
                    swapped = True
                    child.rename(root / "original-assets")
                    try:
                        child.symlink_to(outside, target_is_directory=True)
                    except (NotImplementedError, OSError) as exc:
                        (root / "original-assets").rename(child)
                        self.skipTest(f"directory symlinks are unavailable: {exc}")
                return original_scandir(path)

            with patch.object(assets.os, "scandir", side_effect=swap_before_scan):
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "runtime directory changed type after scanning",
                ):
                    assets.verify_assets(root)

            self.assertTrue(swapped)

    def test_verifier_does_not_depend_on_incomplete_direntry_stat_metadata(self) -> None:
        files = {"assets/link.obj": b"trusted", "scene.xml": b"scene"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            _write_runtime_tree(root, files)
            original_scandir = os.scandir

            class WindowsLikeDirEntry:
                """Expose names and paths but reject cached DirEntry metadata."""

                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self.name = entry.name
                    self.path = entry.path

                def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
                    del follow_symlinks
                    raise AssertionError(
                        "verification must use lstat instead of incomplete DirEntry.stat data"
                    )

            @contextmanager
            def windows_like_scandir(path: str | os.PathLike[str]):
                with original_scandir(path) as scanned:
                    entries = [WindowsLikeDirEntry(entry) for entry in scanned]
                yield entries

            with patch.object(assets.os, "scandir", side_effect=windows_like_scandir):
                result = assets.verify_assets(root)

            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.total_bytes, 12)

    def test_reparse_attribute_is_rejected_without_platform_privileges(self) -> None:
        metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=assets._REPARSE_POINT,
        )

        self.assertTrue(assets._is_link_or_reparse(metadata))

    def test_archive_checksum_mismatch_preserves_existing_tree(self) -> None:
        files = {"scene.xml": b"new!"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"old!"})
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)

            with patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", "0" * 64):
                with self.assertRaisesRegex(
                    assets.AssetVerificationError, "archive checksum mismatch"
                ):
                    assets.install_assets(root, force=True, archive_path=archive)

            self.assertEqual((target / "scene.xml").read_bytes(), b"old!")
            self.assertEqual(list(target.parent.glob(".mclab-assets-*")), [])

    def test_scene_only_archive_cannot_publish_a_partial_tree(self) -> None:
        files = {"LICENSE": b"license", "scene.xml": b"scene"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            archive = root / "scene-only.tar.gz"
            _write_archive(archive, {"scene.xml": b"scene"})
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            with patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest):
                with self.assertRaisesRegex(
                    assets.AssetVerificationError, "missing runtime file: LICENSE"
                ):
                    assets.install_assets(root, archive_path=archive)

            self.assertFalse((root / RUNTIME_RELATIVE).exists())
            self.assertEqual(
                list((root / RUNTIME_RELATIVE.parent).glob(".mclab-assets-*")),
                [],
            )

    def test_installer_extracts_only_manifest_runtime_files(self) -> None:
        files = {"LICENSE": b"license", "scene.xml": b"scene"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            archive = root / "panda.tar.gz"
            _write_archive(
                archive,
                files,
                extras={
                    assets.PANDA_PREFIX + "README.md": b"not runtime",
                    "unrelated/large.bin": b"not Panda",
                },
            )
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            with patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest):
                target = assets.install_assets(root, archive_path=archive)

            actual = {
                path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()
            }
            self.assertEqual(actual, set(files))
            assets.verify_assets(root)

    def test_publication_does_not_clobber_destination_created_at_syscall_boundary(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = root / RUNTIME_RELATIVE
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            original_replace = assets._replace_path
            injected = False

            def inject_foreign_destination(source: Path, destination: Path) -> None:
                nonlocal injected
                if destination == target and not injected:
                    injected = True
                    destination.mkdir()
                    (destination / "owner.txt").write_bytes(b"foreign")
                original_replace(source, destination)

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_replace_path", side_effect=inject_foreign_destination),
            ):
                with self.assertRaisesRegex(RuntimeError, "recovery data was preserved"):
                    assets.install_assets(root, archive_path=archive)

            self.assertTrue(injected)
            self.assertEqual((target / "owner.txt").read_bytes(), b"foreign")

    def test_failed_candidate_replacement_restores_previous_tree(self) -> None:
        files = {"scene.xml": b"new!"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"old!"})
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            calls: list[tuple[Path, Path]] = []
            original_replace = assets._replace_path

            def fail_publication(source: Path, destination: Path) -> None:
                calls.append((source, destination))
                if len(calls) == 2:
                    raise OSError("simulated publication failure")
                original_replace(source, destination)

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_replace_path", side_effect=fail_publication),
            ):
                with self.assertRaisesRegex(RuntimeError, "previous tree was restored"):
                    assets.install_assets(root, force=True, archive_path=archive)

            self.assertEqual(len(calls), 3)
            self.assertEqual((target / "scene.xml").read_bytes(), b"old!")
            self.assertEqual(list(target.parent.glob(".mclab-assets-*")), [])

    def test_failed_rollback_preserves_recovery_tree(self) -> None:
        files = {"scene.xml": b"new!"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            _write_runtime_tree(root, {"scene.xml": b"old!"})
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            call_count = 0
            original_replace = assets._replace_path

            def fail_publication_and_rollback(source: Path, destination: Path) -> None:
                nonlocal call_count
                call_count += 1
                if call_count in {2, 3}:
                    raise OSError(f"simulated replace failure {call_count}")
                original_replace(source, destination)

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(
                    assets,
                    "_replace_path",
                    side_effect=fail_publication_and_rollback,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "recovery data was preserved") as raised:
                    assets.install_assets(root, force=True, archive_path=archive)

            transactions = list((root / RUNTIME_RELATIVE.parent).glob(".mclab-assets-*"))
            self.assertEqual(len(transactions), 1)
            backup = transactions[0] / "previous" / "scene.xml"
            self.assertEqual(backup.read_bytes(), b"old!")
            self.assertIn(os.fspath(transactions[0] / "previous"), str(raised.exception))

    def test_backup_probe_failure_preserves_previous_tree_transaction(self) -> None:
        files = {"scene.xml": b"new!"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"old!"})
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            original_lstat = os.lstat
            original_replace = assets._replace_path
            replace_count = 0
            successful_backup_probes = 0

            def fail_candidate_publication(source: Path, destination: Path) -> None:
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("simulated candidate publication failure")
                original_replace(source, destination)

            def fail_second_existing_backup_probe(path: str | os.PathLike[str]):
                nonlocal successful_backup_probes
                try:
                    metadata = original_lstat(path)
                except OSError:
                    raise
                if Path(path).name == "previous":
                    successful_backup_probes += 1
                    if successful_backup_probes == 2:
                        raise OSError("simulated backup probe failure")
                return metadata

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_replace_path", side_effect=fail_candidate_publication),
                patch.object(assets.os, "lstat", side_effect=fail_second_existing_backup_probe),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "recovery data was preserved",
                ):
                    assets.install_assets(root, force=True, archive_path=archive)

            transactions = list(target.parent.glob(".mclab-assets-*"))
            self.assertEqual(len(transactions), 1)
            self.assertFalse(target.exists())
            self.assertEqual((transactions[0] / "previous" / "scene.xml").read_bytes(), b"old!")

    def test_keyboard_interrupt_during_publication_restores_previous_tree(self) -> None:
        files = {"scene.xml": b"new!"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, {"scene.xml": b"old!"})
            archive = root / "panda.tar.gz"
            _write_archive(archive, files)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            call_count = 0
            original_replace = assets._replace_path

            def interrupt_publication(source: Path, destination: Path) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise KeyboardInterrupt
                original_replace(source, destination)

            with (
                patch.object(assets, "MENAGERIE_ARCHIVE_SHA256", digest),
                patch.object(assets, "_replace_path", side_effect=interrupt_publication),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    assets.install_assets(root, force=True, archive_path=archive)

            self.assertEqual(call_count, 3)
            self.assertEqual((target / "scene.xml").read_bytes(), b"old!")
            self.assertEqual(list(target.parent.glob(".mclab-assets-*")), [])

    def test_same_size_mutation_with_restored_mtime_is_rejected(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            runtime_file = target / "scene.xml"
            original_metadata = os.lstat(runtime_file)
            original_fstat = os.fstat
            matching_fstat_calls = 0

            def mutate_before_final_fstat(descriptor: int):
                nonlocal matching_fstat_calls
                metadata = original_fstat(descriptor)
                if (
                    metadata.st_dev == original_metadata.st_dev
                    and metadata.st_ino == original_metadata.st_ino
                ):
                    matching_fstat_calls += 1
                    if matching_fstat_calls == 2:
                        time.sleep(0.01)
                        with runtime_file.open("r+b") as stream:
                            stream.write(b"changed")
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.utime(
                            runtime_file,
                            ns=(original_metadata.st_atime_ns, original_metadata.st_mtime_ns),
                            follow_symlinks=False,
                        )
                        metadata = original_fstat(descriptor)
                return metadata

            with patch.object(assets.os, "fstat", side_effect=mutate_before_final_fstat):
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "runtime file changed while hashing",
                ):
                    assets.verify_assets(root)

            self.assertEqual(runtime_file.read_bytes(), b"changed")
            self.assertEqual(os.lstat(runtime_file).st_mtime_ns, original_metadata.st_mtime_ns)

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "POSIX FIFO only")
    def test_fifo_swap_before_open_is_nonblocking_and_rejected(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            runtime_file = target / "scene.xml"
            original_open = os.open
            swapped = False

            def swap_to_fifo(path: str | os.PathLike[str], flags: int, *args: int) -> int:
                nonlocal swapped
                opened_path = Path(path)
                if opened_path == runtime_file and not swapped:
                    if not flags & os.O_NONBLOCK:
                        raise AssertionError("runtime files must be opened with O_NONBLOCK")
                    swapped = True
                    runtime_file.rename(target / "original-scene.xml")
                    os.mkfifo(runtime_file)
                return original_open(path, flags, *args)

            with patch.object(assets.os, "open", side_effect=swap_to_fifo):
                with self.assertRaisesRegex(
                    assets.AssetSafetyError,
                    "runtime file changed type while opening",
                ):
                    assets.verify_assets(root)

            self.assertTrue(swapped)

    def test_diagnostics_are_deterministic_and_bounded(self) -> None:
        files = {f"assets/file-{index:02d}.bin": bytes([index]) for index in range(12)}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            (root / RUNTIME_RELATIVE).mkdir(parents=True)

            with self.assertRaises(assets.AssetVerificationError) as first:
                assets.verify_assets(root)
            with self.assertRaises(assets.AssetVerificationError) as second:
                assets.verify_assets(root)

            self.assertEqual(first.exception.issues, second.exception.issues)
            self.assertEqual(str(first.exception), str(second.exception))
            self.assertEqual(len(first.exception.issues), 13)
            self.assertIn("... (+8 more issues)", str(first.exception))
            self.assertNotIn("file-11.bin", str(first.exception))

    def test_diagnostics_escape_control_characters_to_one_line(self) -> None:
        files = {"scene.xml": b"trusted"}
        with tempfile.TemporaryDirectory() as tmp, _runtime_contract(files):
            root = Path(tmp)
            target = _write_runtime_tree(root, files)
            (target / "forged\nAsset verified: yes\x1b[31m").write_bytes(b"unknown")

            with self.assertRaises(assets.AssetVerificationError) as raised:
                assets.verify_assets(root)

            diagnostic = str(raised.exception)
            self.assertEqual(len(diagnostic.splitlines()), 1)
            self.assertIn(r"forged\nAsset verified: yes\x1b[31m", diagnostic)

    def test_malformed_manifest_fails_as_a_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / RUNTIME_RELATIVE).mkdir(parents=True)
            with (
                patch.object(assets, "PANDA_RUNTIME_MANIFEST", (("broken",),)),
                patch.object(assets, "PANDA_RUNTIME_FILE_COUNT", 1),
                patch.object(assets, "PANDA_RUNTIME_TOTAL_BYTES", 0),
            ):
                with self.assertRaisesRegex(
                    assets.AssetVerificationError, "invalid runtime manifest entry"
                ):
                    assets.verify_assets(root)


class AssetCliTests(unittest.TestCase):
    def test_assets_verify_parser_and_success_output(self) -> None:
        parsed = build_parser().parse_args(["assets", "verify"])
        self.assertEqual(parsed.assets_command, "verify")
        result = assets.AssetVerification(Path("/verified/panda"), 72, 34_333_936)
        output = io.StringIO()

        with patch.object(assets, "verify_assets", return_value=result), redirect_stdout(output):
            self.assertEqual(main(["assets", "verify"]), 0)

        self.assertEqual(
            output.getvalue().strip(),
            "Assets verified: /verified/panda (72 files, 34333936 bytes)",
        )

    def test_assets_verify_failure_is_concise_and_nonzero(self) -> None:
        error = assets.AssetVerificationError(Path("/bad/panda"), ["tampered"])
        output = io.StringIO()

        with patch.object(assets, "verify_assets", side_effect=error), redirect_stderr(output):
            self.assertEqual(main(["assets", "verify"]), 1)

        self.assertEqual(
            output.getvalue().strip(),
            "Asset error: Asset verification failed for /bad/panda: tampered.",
        )

    def test_assets_install_failure_is_concise_and_nonzero(self) -> None:
        error = assets.AssetVerificationError(Path("/bad/archive"), ["checksum mismatch"])
        output = io.StringIO()

        with patch.object(assets, "install_assets", side_effect=error), redirect_stderr(output):
            self.assertEqual(main(["assets", "install"]), 1)

        self.assertEqual(
            output.getvalue().strip(),
            "Asset error: Asset verification failed for /bad/archive: checksum mismatch.",
        )

    def test_assets_install_runtime_failure_is_concise_and_nonzero(self) -> None:
        output = io.StringIO()

        with (
            patch.object(
                assets,
                "install_assets",
                side_effect=RuntimeError("download failed\nforged success\x1b[31m"),
            ),
            redirect_stderr(output),
        ):
            self.assertEqual(main(["assets", "install"]), 1)

        self.assertEqual(
            output.getvalue().strip(),
            r"Asset error: download failed\nforged success\x1b[31m",
        )


@contextmanager
def _runtime_contract(files: dict[str, bytes]):
    manifest = tuple(
        sorted(
            (
                relative,
                len(content),
                hashlib.sha256(content).hexdigest(),
            )
            for relative, content in files.items()
        )
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(assets, "PANDA_RUNTIME_MANIFEST", manifest))
        stack.enter_context(patch.object(assets, "PANDA_RUNTIME_FILE_COUNT", len(manifest)))
        stack.enter_context(
            patch.object(
                assets,
                "PANDA_RUNTIME_TOTAL_BYTES",
                sum(len(content) for content in files.values()),
            )
        )
        yield


def _write_runtime_tree(root: Path, files: dict[str, bytes]) -> Path:
    target = root / RUNTIME_RELATIVE
    target.mkdir(parents=True)
    for relative, content in files.items():
        destination = target.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return target


def _write_archive(
    archive: Path,
    files: dict[str, bytes],
    *,
    extras: dict[str, bytes] | None = None,
) -> None:
    members = {assets.PANDA_PREFIX + relative: content for relative, content in files.items()}
    members.update(extras or {})
    with tarfile.open(archive, "w:gz") as bundle:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
