from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Sequence
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import install_ubuntu_system_packages as ubuntu_packages  # noqa: E402


VALID_OS_RELEASE = """\
NAME="Ubuntu"
ID=ubuntu
VERSION_ID="24.04"
VERSION_CODENAME=noble
PRETTY_NAME="Ubuntu 24.04 LTS"
"""
VALID_SOURCES = {
    "/etc/apt/sources.list.d/ubuntu.sources": """\
Types: deb
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-security
Components: main universe
"""
}
VALID_UPDATE_OUTPUT = """\
Get:1 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble InRelease [256 kB]
Hit:2 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble-updates InRelease
Get:3 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble-security InRelease [126 kB]
Reading package lists... Done
"""
TEST_ARCHIVE_KEYRING = b"deterministic test-only Ubuntu archive keyring bytes\n"
TEST_ARCHIVE_KEYRING_SHA256 = hashlib.sha256(TEST_ARCHIVE_KEYRING).hexdigest()
TEST_ARCHIVE_KEYRING_SPEC = ubuntu_packages.ArchiveKeyringSpec(
    package="test-only-ubuntu-keyring",
    version="1.test",
    path=Path("/usr/share/keyrings/test-only-ubuntu-archive-keyring.gpg"),
    size=len(TEST_ARCHIVE_KEYRING),
    sha256=TEST_ARCHIVE_KEYRING_SHA256,
)
_REAL_LOAD_MANIFEST = ubuntu_packages.load_manifest


def _test_verified_archive_keyring() -> ubuntu_packages.VerifiedArchiveKeyring:
    return ubuntu_packages.VerifiedArchiveKeyring(
        spec=TEST_ARCHIVE_KEYRING_SPEC,
        payload=TEST_ARCHIVE_KEYRING,
        observed_size=len(TEST_ARCHIVE_KEYRING),
        observed_sha256=TEST_ARCHIVE_KEYRING_SHA256,
    )


def _install_and_verify(*args: object, **kwargs: object) -> dict[str, object]:
    manifest_path = kwargs.get("manifest_path", ubuntu_packages.MANIFEST_PATH)
    assert isinstance(manifest_path, Path)
    manifest = replace(
        _REAL_LOAD_MANIFEST(manifest_path),
        archive_keyring=TEST_ARCHIVE_KEYRING_SPEC,
    )
    with tempfile.TemporaryDirectory() as tmp:
        source_path = Path(tmp) / "source-keyring.gpg"
        source_path.write_bytes(TEST_ARCHIVE_KEYRING)
        source_path.chmod(0o777)
        kwargs["archive_keyring_path"] = source_path
        with patch.object(ubuntu_packages, "load_manifest", return_value=manifest):
            return ubuntu_packages.install_and_verify(*args, **kwargs)


def _repository_document() -> dict[str, object]:
    return json.loads(ubuntu_packages.MANIFEST_PATH.read_text(encoding="utf-8"))


def _candidate_output(
    overrides: dict[str, str] | None = None,
    packages: Sequence[tuple[str, str]] = ubuntu_packages.EXPECTED_PACKAGES,
) -> str:
    overrides = overrides or {}
    sections: list[str] = []
    for name, version in packages:
        candidate = overrides.get(name, version)
        sections.extend(
            [
                f"{name}:",
                "  Installed: (none)",
                f"  Candidate: {candidate}",
                "  Version table:",
                f"     {candidate} 500",
            ]
        )
    return "\n".join(sections) + "\n"


def _installed_output(
    version_overrides: dict[str, str] | None = None,
    architecture_overrides: dict[str, str] | None = None,
    packages: Sequence[tuple[str, str]] = ubuntu_packages.EXPECTED_PACKAGES,
) -> str:
    version_overrides = version_overrides or {}
    architecture_overrides = architecture_overrides or {}
    lines = []
    for name, version in packages:
        architecture = architecture_overrides.get(name, "amd64")
        installed_version = version_overrides.get(name, version)
        lines.append(f"{name}:amd64\t{installed_version}\t{architecture}")
    return "\n".join(lines) + "\n"


class FakeRunner:
    """Return deterministic command results without invoking the host package manager."""

    def __init__(
        self,
        *,
        architecture: str = "amd64",
        update_output: str = VALID_UPDATE_OUTPUT,
        candidate_output: str | None = None,
        installed_output: str | None = None,
        timeout_on: str | None = None,
    ) -> None:
        self.architecture = architecture
        self.update_output = update_output
        self.candidate_output = candidate_output or _candidate_output()
        self.installed_output = installed_output or _installed_output()
        self.timeout_on = timeout_on
        self.calls: list[tuple[list[str], int]] = []

    def __call__(
        self, command: Sequence[str], timeout_seconds: int
    ) -> subprocess.CompletedProcess[str]:
        command_list = list(command)
        self.calls.append((command_list, timeout_seconds))
        if command_list == ["dpkg", "--print-architecture"]:
            key = "architecture"
            stdout = f"{self.architecture}\n"
        elif command_list[0] == "apt-get" and command_list[-1] == "update":
            key = "update"
            stdout = self.update_output
        elif command_list and command_list[0] == "apt-cache":
            key = "candidate"
            stdout = self.candidate_output
        elif command_list[0] == "apt-get" and "install" in command_list:
            key = "install"
            stdout = "Reading package lists... Done\n0 upgraded, 22 newly installed.\n"
        elif command_list and command_list[0] == "dpkg-query":
            key = "installed"
            stdout = self.installed_output
        else:
            raise AssertionError(f"unexpected command: {command_list}")
        if self.timeout_on == key:
            raise subprocess.TimeoutExpired(command_list, timeout_seconds)
        return subprocess.CompletedProcess(command_list, 0, stdout=stdout, stderr="")


class ManifestPolicyTests(unittest.TestCase):
    def _write_document(self, directory: str, document: dict[str, object]) -> Path:
        path = Path(directory) / "manifest.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_repository_manifest_has_strict_approved_schema_and_sorted_pins(self) -> None:
        manifest = ubuntu_packages.load_manifest()

        self.assertEqual(manifest.snapshot, "20260723T000000Z")
        self.assertEqual(manifest.distribution["architecture"], "amd64")
        self.assertEqual(ubuntu_packages.APT_ARCHIVE_KEYRING_PACKAGE, "ubuntu-keyring")
        self.assertEqual(ubuntu_packages.APT_ARCHIVE_KEYRING_VERSION, "2023.11.28.1")
        self.assertEqual(ubuntu_packages.APT_ARCHIVE_KEYRING_SIZE, 3607)
        self.assertEqual(
            ubuntu_packages.APT_ARCHIVE_KEYRING_SHA256,
            "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31",
        )
        self.assertEqual(
            manifest.archive_keyring,
            ubuntu_packages.ArchiveKeyringSpec(
                package="ubuntu-keyring",
                version="2023.11.28.1",
                path=Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg"),
                size=3607,
                sha256=(
                    "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31"
                ),
            ),
        )
        self.assertEqual(len(manifest.packages), 22)
        self.assertEqual(manifest.packages, ubuntu_packages.EXPECTED_PACKAGES)
        self.assertEqual(
            [name for name, _version in manifest.packages],
            sorted(name for name, _version in manifest.packages),
        )

    def test_schema_version_rejects_unknown_integer_boolean_and_extra_key(self) -> None:
        for schema_version in (2, True):
            with self.subTest(schema_version=schema_version), tempfile.TemporaryDirectory() as tmp:
                document = _repository_document()
                document["schema_version"] = schema_version
                path = self._write_document(tmp, document)
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "schema_version"):
                    ubuntu_packages.load_manifest(path)

        with tempfile.TemporaryDirectory() as tmp:
            document = _repository_document()
            document["unexpected"] = "not allowed"
            path = self._write_document(tmp, document)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "keys do not match"):
                ubuntu_packages.load_manifest(path)

    def test_duplicate_json_key_is_rejected(self) -> None:
        original = ubuntu_packages.MANIFEST_PATH.read_text(encoding="utf-8")
        duplicate = original.replace(
            '  "schema_version": 1,',
            '  "schema_version": 1,\n  "schema_version": 1,',
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "duplicate JSON key"):
                ubuntu_packages.load_manifest(path)

    def test_duplicate_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            document = _repository_document()
            packages = document["packages"]
            assert isinstance(packages, list)
            packages.append(deepcopy(packages[0]))
            path = self._write_document(tmp, document)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "duplicate package"):
                ubuntu_packages.load_manifest(path)

    def test_unsorted_packages_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            document = _repository_document()
            packages = document["packages"]
            assert isinstance(packages, list)
            packages[0], packages[1] = packages[1], packages[0]
            path = self._write_document(tmp, document)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "must be sorted"):
                ubuntu_packages.load_manifest(path)

    def test_syntactically_valid_version_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            document = _repository_document()
            packages = document["packages"]
            assert isinstance(packages, list)
            assert isinstance(packages[0], dict)
            packages[0]["version"] = "1.14.10-4ubuntu4.2"
            path = self._write_document(tmp, document)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "approved baseline"):
                ubuntu_packages.load_manifest(path)

    def test_archive_keyring_schema_and_identity_drift_are_rejected(self) -> None:
        cases: tuple[tuple[str, object, str], ...] = (
            ("version", "2023.11.28.2", "archive keyring pin"),
            ("size", 3608, "archive keyring pin"),
            ("size", 3607.0, "archive keyring pin"),
            ("sha256", "0" * 64, "archive keyring pin"),
        )
        for key, value, message in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                document = _repository_document()
                archive_keyring = document["archive_keyring"]
                assert isinstance(archive_keyring, dict)
                archive_keyring[key] = value
                path = self._write_document(tmp, document)
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, message):
                    ubuntu_packages.load_manifest(path)

        with tempfile.TemporaryDirectory() as tmp:
            document = _repository_document()
            archive_keyring = document["archive_keyring"]
            assert isinstance(archive_keyring, dict)
            archive_keyring["unexpected"] = "not allowed"
            path = self._write_document(tmp, document)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "keys do not match"):
                ubuntu_packages.load_manifest(path)


class HostAndSourcePolicyTests(unittest.TestCase):
    def test_isolated_apt_state_uses_only_fixed_ubuntu_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = ubuntu_packages._prepare_isolated_apt_environment(
                root,
                verified_archive_keyring=_test_verified_archive_keyring(),
            )
            self.assertEqual(options[::2], ["-o"] * 8)
            values = options[1::2]
            settings = dict(value.split("=", 1) for value in values)
            source = Path(settings["Dir::Etc::sourcelist"])
            source_parts = Path(settings["Dir::Etc::sourceparts"])
            lists = Path(settings["Dir::State::lists"])
            archives = Path(settings["Dir::Cache::archives"])

            trusted_keyring = root / "ubuntu-archive-keyring.gpg"
            self.assertEqual(trusted_keyring.read_bytes(), TEST_ARCHIVE_KEYRING)
            self.assertEqual(stat.S_IMODE(trusted_keyring.stat().st_mode), 0o644)
            controlled_sources = ubuntu_packages._render_controlled_apt_sources(
                trusted_keyring
            )
            self.assertEqual(source.read_text(encoding="utf-8"), controlled_sources)
            self.assertEqual(controlled_sources.count(f"Signed-By: {trusted_keyring}"), 2)
            self.assertNotIn(
                TEST_ARCHIVE_KEYRING_SPEC.path.as_posix(), controlled_sources
            )
            self.assertEqual(list(source_parts.iterdir()), [])
            self.assertTrue(lists.is_relative_to(root))
            self.assertTrue(archives.is_relative_to(root))
            self.assertEqual(settings["APT::Snapshot"], ubuntu_packages.SNAPSHOT)
            self.assertEqual(settings["Acquire::AllowInsecureRepositories"], "false")
            self.assertEqual(
                settings["Acquire::AllowDowngradeToInsecureRepositories"], "false"
            )
            self.assertEqual(settings["APT::Get::AllowUnauthenticated"], "false")
            self.assertNotIn("microsoft", source.read_text(encoding="utf-8").lower())
            self.assertNotIn("docker", source.read_text(encoding="utf-8").lower())
            self.assertEqual(
                source.read_text(encoding="utf-8").count(
                    f"Snapshot: {ubuntu_packages.SNAPSHOT}"
                ),
                2,
            )

    def test_archive_keyring_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "keyring.gpg"
            target.write_bytes(TEST_ARCHIVE_KEYRING)
            link = root / "keyring-link.gpg"
            link.symlink_to(target)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "non-symlink"):
                ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=link,
                )

    def test_archive_keyring_exact_digest_is_accepted_despite_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keyring.gpg"
            path.write_bytes(TEST_ARCHIVE_KEYRING)
            path.chmod(0o777)
            verified = ubuntu_packages._read_verified_archive_keyring(
                TEST_ARCHIVE_KEYRING_SPEC,
                path_override=path,
            )
            self.assertEqual(verified, _test_verified_archive_keyring())

    def test_archive_keyring_rejects_size_hash_and_nonregular_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "keyring.gpg"
            path.write_bytes(TEST_ARCHIVE_KEYRING)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "size drift"):
                ubuntu_packages._read_verified_archive_keyring(
                    replace(
                        TEST_ARCHIVE_KEYRING_SPEC,
                        size=len(TEST_ARCHIVE_KEYRING) + 1,
                    ),
                    path_override=path,
                )
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "SHA-256 drift"):
                ubuntu_packages._read_verified_archive_keyring(
                    replace(TEST_ARCHIVE_KEYRING_SPEC, sha256="0" * 64),
                    path_override=path,
                )
            directory = root / "directory"
            directory.mkdir()
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "regular file"):
                ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=directory,
                )

    def test_archive_keyring_open_is_nonblocking_and_fifo_is_rejected(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO fixtures are unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "keyring.gpg"
            source.write_bytes(TEST_ARCHIVE_KEYRING)
            real_open = os.open
            observed_flags: list[int] = []

            def capture_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
                observed_flags.append(flags)
                return real_open(path, flags, *args, **kwargs)

            with patch.object(ubuntu_packages.os, "open", side_effect=capture_open):
                ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=source,
                )
            self.assertEqual(len(observed_flags), 1)
            self.assertTrue(observed_flags[0] & os.O_NOFOLLOW)
            self.assertTrue(observed_flags[0] & os.O_NONBLOCK)
            self.assertTrue(observed_flags[0] & os.O_CLOEXEC)

            fifo = root / "keyring.fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "regular file"):
                ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=fifo,
                )

    def test_archive_keyring_rejects_short_oversized_and_same_size_wrong_bytes(self) -> None:
        fixtures = (
            ("short", TEST_ARCHIVE_KEYRING[:-1], "size drift"),
            ("oversized", TEST_ARCHIVE_KEYRING + b"x", "size drift"),
            (
                "wrong hash",
                b"x" * len(TEST_ARCHIVE_KEYRING),
                "SHA-256 drift",
            ),
        )
        for label, payload, message in fixtures:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "keyring.gpg"
                source.write_bytes(payload)
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, message):
                    ubuntu_packages._read_verified_archive_keyring(
                        TEST_ARCHIVE_KEYRING_SPEC,
                        path_override=source,
                    )

    def test_archive_keyring_path_replacement_after_open_cannot_replace_fd_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "keyring.gpg"
            opened_source = root / "opened-keyring.gpg"
            source.write_bytes(TEST_ARCHIVE_KEYRING)
            replacement = b"x" * len(TEST_ARCHIVE_KEYRING)
            real_open = os.open
            swapped = False

            def open_then_swap(
                path: object, flags: int, *args: object, **kwargs: object
            ) -> int:
                nonlocal swapped
                descriptor = real_open(path, flags, *args, **kwargs)
                if Path(path) == source and not swapped:
                    swapped = True
                    source.rename(opened_source)
                    source.write_bytes(replacement)
                return descriptor

            with patch.object(ubuntu_packages.os, "open", side_effect=open_then_swap):
                verified = ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=source,
                )
            self.assertEqual(verified.payload, TEST_ARCHIVE_KEYRING)
            self.assertEqual(source.read_bytes(), replacement)

    def test_archive_keyring_in_place_change_during_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "keyring.gpg"
            source.write_bytes(TEST_ARCHIVE_KEYRING)
            original_mtime_ns = source.stat().st_mtime_ns
            real_read = os.read
            changed = False

            def read_then_change_metadata(descriptor: int, size: int) -> bytes:
                nonlocal changed
                payload = real_read(descriptor, size)
                if not changed:
                    changed = True
                    os.utime(
                        source,
                        ns=(original_mtime_ns, original_mtime_ns + 1_000_000_000),
                    )
                return payload

            with (
                patch.object(
                    ubuntu_packages.os,
                    "read",
                    side_effect=read_then_change_metadata,
                ),
                self.assertRaisesRegex(ubuntu_packages.PolicyError, "changed while"),
            ):
                ubuntu_packages._read_verified_archive_keyring(
                    TEST_ARCHIVE_KEYRING_SPEC,
                    path_override=source,
                )

    def test_trusted_keyring_copy_rejects_forgery_and_existing_destinations(self) -> None:
        forged = replace(
            _test_verified_archive_keyring(),
            payload=b"x" * len(TEST_ARCHIVE_KEYRING),
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "revalidation"):
                ubuntu_packages._write_trusted_archive_keyring(Path(tmp), forged)

        for destination_type in ("file", "symlink"):
            with (
                self.subTest(destination_type=destination_type),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                destination = root / "ubuntu-archive-keyring.gpg"
                target = root / "preserved-target.gpg"
                target.write_bytes(b"preserve target\n")
                if destination_type == "file":
                    destination.write_bytes(b"preserve destination\n")
                else:
                    destination.symlink_to(target)
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "cannot publish"):
                    ubuntu_packages._write_trusted_archive_keyring(
                        root,
                        _test_verified_archive_keyring(),
                    )
                self.assertEqual(target.read_bytes(), b"preserve target\n")
                if destination_type == "file":
                    self.assertEqual(destination.read_bytes(), b"preserve destination\n")
                else:
                    self.assertTrue(destination.is_symlink())

    def test_trusted_keyring_copy_retries_short_writes_and_rejects_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_write = os.write
            first_write = True

            def short_then_normal(descriptor: int, payload: object) -> int:
                nonlocal first_write
                if first_write:
                    first_write = False
                    return real_write(descriptor, payload[:3])
                return real_write(descriptor, payload)

            with patch.object(ubuntu_packages.os, "write", side_effect=short_then_normal):
                destination = ubuntu_packages._write_trusted_archive_keyring(
                    root,
                    _test_verified_archive_keyring(),
                )
            self.assertEqual(destination.read_bytes(), TEST_ARCHIVE_KEYRING)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o644)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "ubuntu-archive-keyring.gpg"
            with (
                patch.object(ubuntu_packages.os, "write", return_value=0),
                self.assertRaisesRegex(ubuntu_packages.PolicyError, "short write"),
            ):
                ubuntu_packages._write_trusted_archive_keyring(
                    root,
                    _test_verified_archive_keyring(),
                )
            self.assertFalse(destination.exists())

    def test_bad_archive_keyring_fails_before_runner_and_evidence(self) -> None:
        runner = FakeRunner()
        manifest = replace(
            _REAL_LOAD_MANIFEST(),
            archive_keyring=TEST_ARCHIVE_KEYRING_SPEC,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "keyring.gpg"
            source.write_bytes(b"x" * len(TEST_ARCHIVE_KEYRING))
            output = root / "evidence.json"
            with (
                patch.object(ubuntu_packages, "load_manifest", return_value=manifest),
                self.assertRaisesRegex(ubuntu_packages.PolicyError, "SHA-256 drift"),
            ):
                ubuntu_packages.install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                    archive_keyring_path=source,
                )
            self.assertEqual(runner.calls, [])
            self.assertFalse(output.exists())

    def test_wrong_os_is_rejected_before_any_command(self) -> None:
        runner = FakeRunner()
        wrong_os = VALID_OS_RELEASE.replace('VERSION_ID="24.04"', 'VERSION_ID="22.04"')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "Ubuntu 24.04 noble"):
                _install_and_verify(
                    output,
                    os_release_text=wrong_os,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertEqual(runner.calls, [])
            self.assertFalse(output.exists())

    def test_wrong_architecture_is_rejected_before_apt(self) -> None:
        runner = FakeRunner(architecture="arm64")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "must be amd64"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertEqual(len(runner.calls), 1)
            self.assertFalse(output.exists())

    def test_deb822_snapshot_override_is_rejected(self) -> None:
        sources = dict(VALID_SOURCES)
        source_name = next(iter(sources))
        sources[source_name] += "Snapshot: 20260721T000000Z\n"
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "Snapshot override"):
            ubuntu_packages.validate_no_snapshot_overrides(sources)

    def test_controlled_snapshot_id_and_enable_are_not_treated_as_overrides(self) -> None:
        ubuntu_packages.validate_no_snapshot_overrides(
            {
                "exact.sources": "Snapshot: 20260723T000000Z\n",
                "enabled.sources": "Snapshot: enable\n",
            }
        )

    def test_one_line_snapshot_override_is_rejected_case_insensitively(self) -> None:
        sources = {
            "ubuntu.list": (
                "deb [arch=amd64 SNAPSHOT=20260721T000000Z] "
                "https://archive.ubuntu.com/ubuntu noble main\n"
            )
        }
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "snapshot option"):
            ubuntu_packages.validate_no_snapshot_overrides(sources)

    def test_commented_snapshot_text_is_not_an_override(self) -> None:
        ubuntu_packages.validate_no_snapshot_overrides(
            {
                "ubuntu.sources": "# Snapshot: 20260721T000000Z\nTypes: deb\n",
                "ubuntu.list": (
                    "deb [arch=amd64] https://archive.ubuntu.com/ubuntu noble main # snapshot=old\n"
                ),
            }
        )


class SnapshotOutputPolicyTests(unittest.TestCase):
    def test_snapshot_only_update_output_is_accepted(self) -> None:
        ubuntu_packages.validate_snapshot_update_output(VALID_UPDATE_OUTPUT)

    def test_live_repository_fallback_is_rejected(self) -> None:
        live_output = VALID_UPDATE_OUTPUT.replace(
            "https://snapshot.ubuntu.com/ubuntu/20260723T000000Z",
            "http://archive.ubuntu.com/ubuntu",
            1,
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "non-snapshot"):
            ubuntu_packages.validate_snapshot_update_output(live_output)

    def test_mixed_snapshot_and_live_repository_output_is_rejected(self) -> None:
        mixed_output = (
            VALID_UPDATE_OUTPUT
            + "Hit:4 http://security.ubuntu.com/ubuntu noble-security InRelease\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "non-snapshot"):
            ubuntu_packages.validate_snapshot_update_output(mixed_output)

    def test_no_repository_activity_is_rejected_as_possible_live_fallback(self) -> None:
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "no verified snapshot"):
            ubuntu_packages.validate_snapshot_update_output("Reading package lists... Done\n")

    def test_snapshot_url_outside_repository_activity_is_not_accepted(self) -> None:
        output = (
            "Checking https://snapshot.ubuntu.com/ubuntu/20260723T000000Z\n"
            "Reading package lists... Done\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "no verified snapshot"):
            ubuntu_packages.validate_snapshot_update_output(output)

    def test_malformed_snapshot_url_is_rejected_as_non_snapshot(self) -> None:
        output = (
            "Get:1 https://snapshot.ubuntu.com:invalid/ubuntu/20260723T000000Z noble InRelease\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "non-snapshot"):
            ubuntu_packages.validate_snapshot_update_output(output)

    def test_update_warnings_are_rejected_even_with_zero_exit_status(self) -> None:
        for warning in (
            "W: Some index files failed to download.",
            "Warning: snapshot metadata was ignored.",
        ):
            with self.subTest(warning=warning):
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "warning or error"):
                    ubuntu_packages.validate_snapshot_update_output(
                        f"{VALID_UPDATE_OUTPUT}{warning}\n"
                    )

    def test_ignored_or_failed_snapshot_repository_activity_is_rejected(self) -> None:
        for prefix in ("Ign:4", "Err:4"):
            with self.subTest(prefix=prefix):
                output = (
                    VALID_UPDATE_OUTPUT
                    + f"{prefix} https://snapshot.ubuntu.com/ubuntu/20260723T000000Z "
                    "noble-backports InRelease\n"
                )
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "failed repository"):
                    ubuntu_packages.validate_snapshot_update_output(output)


class CommandAndVerificationTests(unittest.TestCase):
    def test_success_uses_exact_snapshot_pins_and_writes_deterministic_schema_1_json(self) -> None:
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            first_output = Path(tmp) / "first.json"
            evidence = _install_and_verify(
                first_output,
                os_release_text=VALID_OS_RELEASE,
                source_files=VALID_SOURCES,
                runner=runner,
            )
            first_bytes = first_output.read_bytes()

            second_output = Path(tmp) / "second.json"
            _install_and_verify(
                second_output,
                os_release_text=VALID_OS_RELEASE,
                source_files=VALID_SOURCES,
                runner=FakeRunner(),
            )
            self.assertEqual(first_bytes, second_output.read_bytes())
            self.assertEqual(json.loads(first_bytes), evidence)
            self.assertEqual(stat.S_IMODE(first_output.stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE(second_output.stat().st_mode), 0o644)

        commands = [command for command, _timeout in runner.calls]
        self.assertEqual(len(commands), 5)
        self.assertEqual(commands[0], ["dpkg", "--print-architecture"])
        self.assertEqual(commands[1][0], "apt-get")
        self.assertEqual(commands[1][-3:], ["-S", "20260723T000000Z", "update"])
        expected_names = [name for name, _version in ubuntu_packages.EXPECTED_PACKAGES]
        self.assertEqual(commands[2][0], "apt-cache")
        policy_index = commands[2].index("policy")
        self.assertEqual(commands[2][policy_index + 1 :], expected_names)
        install_snapshot_index = commands[3].index("-S")
        self.assertEqual(
            commands[3][install_snapshot_index:],
            [
                "-S",
                "20260723T000000Z",
                "install",
                "--yes",
                "--no-install-recommends",
                "--no-remove",
                *[f"{name}={version}" for name, version in ubuntu_packages.EXPECTED_PACKAGES],
            ],
        )
        shared_options = commands[1][1:-3]
        self.assertEqual(commands[2][1:policy_index], shared_options)
        self.assertEqual(commands[3][1:install_snapshot_index], shared_options)
        self.assertEqual(shared_options[::2], ["-o"] * 8)
        option_values = shared_options[1::2]
        self.assertIn("APT::Snapshot=20260723T000000Z", option_values)
        self.assertIn("Acquire::AllowInsecureRepositories=false", option_values)
        self.assertIn("Acquire::AllowDowngradeToInsecureRepositories=false", option_values)
        self.assertIn("APT::Get::AllowUnauthenticated=false", option_values)
        self.assertTrue(any(value.startswith("Dir::Etc::sourcelist=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::Etc::sourceparts=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::State::lists=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::Cache::archives=") for value in option_values))
        self.assertFalse(any("microsoft" in value.lower() for value in option_values))
        self.assertEqual(
            commands[4],
            [
                "dpkg-query",
                "-W",
                "-f=${binary:Package}\t${Version}\t${Architecture}\n",
                *expected_names,
            ],
        )
        self.assertEqual(
            set(evidence),
            {
                "archive_keyring",
                "artifact",
                "manifest_canonical_sha256",
                "packages",
                "schema_version",
                "snapshot",
                "status",
                "target",
            },
        )
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(len(evidence["packages"]), 22)
        self.assertEqual(
            evidence["archive_keyring"],
            {
                "package": TEST_ARCHIVE_KEYRING_SPEC.package,
                "version": TEST_ARCHIVE_KEYRING_SPEC.version,
                "path": TEST_ARCHIVE_KEYRING_SPEC.path.as_posix(),
                "sha256": TEST_ARCHIVE_KEYRING_SHA256,
                "size": len(TEST_ARCHIVE_KEYRING),
                "trusted_copy_mode": "0644",
                "verification": "stable-fd-sha256-then-isolated-copy",
            },
        )
        self.assertNotIn(tempfile.gettempdir(), json.dumps(evidence, sort_keys=True))

    def test_evidence_rejects_keyring_record_that_does_not_match_manifest(self) -> None:
        manifest = _REAL_LOAD_MANIFEST()
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "does not match"):
            ubuntu_packages.build_evidence(
                manifest,
                _test_verified_archive_keyring(),
            )

    def test_timeouts_at_every_command_stage_fail_closed_without_evidence(self) -> None:
        for stage in ("architecture", "update", "candidate", "install", "installed"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "evidence.json"
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "timed out"):
                    _install_and_verify(
                        output,
                        os_release_text=VALID_OS_RELEASE,
                        source_files=VALID_SOURCES,
                        runner=FakeRunner(timeout_on=stage),
                    )
                self.assertFalse(output.exists())

    def test_candidate_drift_fails_before_install_and_evidence(self) -> None:
        first_name, first_version = ubuntu_packages.EXPECTED_PACKAGES[0]
        runner = FakeRunner(
            candidate_output=_candidate_output({first_name: f"{first_version}.drift"})
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "candidate drift"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertFalse(any("install" in command for command, _timeout in runner.calls))
            self.assertFalse(output.exists())

    def test_installed_version_drift_fails_without_writing_evidence(self) -> None:
        first_name, first_version = ubuntu_packages.EXPECTED_PACKAGES[0]
        runner = FakeRunner(
            installed_output=_installed_output(
                version_overrides={first_name: f"{first_version}.drift"}
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "installed version drift"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertFalse(output.exists())

    def test_installed_architecture_drift_fails_without_writing_evidence(self) -> None:
        first_name, _first_version = ubuntu_packages.EXPECTED_PACKAGES[0]
        runner = FakeRunner(
            installed_output=_installed_output(architecture_overrides={first_name: "arm64"})
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "architecture drift"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertFalse(output.exists())

    def test_update_warning_from_mocked_command_blocks_later_commands(self) -> None:
        runner = FakeRunner(update_output=f"{VALID_UPDATE_OUTPUT}W: stale metadata\n")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "warning or error"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertEqual(len(runner.calls), 2)
            self.assertFalse(output.exists())

    def test_cli_requires_explicit_install_flag_and_output_path(self) -> None:
        parser = ubuntu_packages._build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--output", "evidence.json"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--install"])

    def test_cli_output_must_be_new_json_below_validation_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            validation_root = root / "build" / "validation"
            validation_root.mkdir(parents=True)
            with (
                patch.object(ubuntu_packages, "ROOT", root),
                patch.object(ubuntu_packages, "VALIDATION_ROOT", validation_root),
            ):
                accepted = ubuntu_packages.validated_cli_output_path(
                    Path("build/validation/supply-chain/evidence.json")
                )
                self.assertEqual(
                    accepted,
                    validation_root / "supply-chain" / "evidence.json",
                )

                with self.assertRaisesRegex(
                    ubuntu_packages.PolicyError, "below repository build/validation"
                ):
                    ubuntu_packages.validated_cli_output_path(Path("outside.json"))
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "end in .json"):
                    ubuntu_packages.validated_cli_output_path(
                        Path("build/validation/evidence.txt")
                    )

                existing = validation_root / "existing.json"
                existing.write_text("preserve me\n", encoding="utf-8")
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "already exists"):
                    ubuntu_packages.validated_cli_output_path(existing)
                self.assertEqual(existing.read_text(encoding="utf-8"), "preserve me\n")

    def test_cli_output_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            validation_root = root / "build" / "validation"
            external = Path(tmp) / "external"
            validation_root.mkdir(parents=True)
            external.mkdir()
            (validation_root / "linked").symlink_to(external, target_is_directory=True)
            with (
                patch.object(ubuntu_packages, "ROOT", root),
                patch.object(ubuntu_packages, "VALIDATION_ROOT", validation_root),
                self.assertRaisesRegex(
                    ubuntu_packages.PolicyError, "below repository build/validation"
                ),
            ):
                ubuntu_packages.validated_cli_output_path(
                    Path("build/validation/linked/evidence.json")
                )

    def test_cli_output_rejects_external_lexical_alias_of_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            validation_root = root / "build" / "validation"
            validation_root.mkdir(parents=True)
            alias = Path(tmp) / "repo-alias"
            try:
                alias.symlink_to(root, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")
            with (
                patch.object(ubuntu_packages, "ROOT", root),
                patch.object(ubuntu_packages, "VALIDATION_ROOT", validation_root),
                self.assertRaisesRegex(
                    ubuntu_packages.PolicyError, "below repository build/validation"
                ),
            ):
                ubuntu_packages.validated_cli_output_path(
                    alias / "build/validation/evidence.json"
                )

    def test_secure_cli_writer_is_no_overwrite_regular_and_runner_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            validation_root = root / "build" / "validation"
            root.mkdir()
            output = validation_root / "subject" / "evidence.json"
            evidence = {"schema_version": 1, "status": "verified"}
            with (
                patch.object(ubuntu_packages, "ROOT", root),
                patch.object(ubuntu_packages, "VALIDATION_ROOT", validation_root),
            ):
                ubuntu_packages.write_cli_evidence(output, evidence)
                self.assertEqual(json.loads(output.read_text(encoding="utf-8")), evidence)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
                with self.assertRaisesRegex(ubuntu_packages.PolicyError, "already exists"):
                    ubuntu_packages.write_cli_evidence(output, {"replacement": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), evidence)

    def test_secure_cli_writer_does_not_follow_swapped_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            validation_root = root / "build" / "validation"
            parent = validation_root / "subject"
            external = Path(tmp) / "external"
            parent.mkdir(parents=True)
            external.mkdir()
            output = parent / "evidence.json"
            with (
                patch.object(ubuntu_packages, "ROOT", root),
                patch.object(ubuntu_packages, "VALIDATION_ROOT", validation_root),
            ):
                ubuntu_packages.validated_cli_output_path(output)
                parent.rename(validation_root / "original-subject")
                parent.symlink_to(external, target_is_directory=True)
                with self.assertRaises(ubuntu_packages.PolicyError):
                    ubuntu_packages.write_cli_evidence(output, {"status": "verified"})
                self.assertFalse((external / "evidence.json").exists())

                with (
                    patch.object(
                        ubuntu_packages,
                        "validated_cli_output_path",
                        return_value=output,
                    ),
                    self.assertRaisesRegex(
                        ubuntu_packages.PolicyError,
                        "secure evidence directory",
                    ),
                ):
                    ubuntu_packages.write_cli_evidence(output, {"status": "verified"})
                self.assertFalse((external / "evidence.json").exists())

    def test_cli_requires_root_before_reading_or_mutating_host_state(self) -> None:
        with patch.object(ubuntu_packages.os, "geteuid", return_value=1000):
            self.assertEqual(
                ubuntu_packages.main(["--install", "--output", "/tmp/evidence.json"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
