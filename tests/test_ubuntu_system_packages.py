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
SNAPSHOT_ENDPOINT_UPDATE_OUTPUT = """\
Get:1 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble InRelease [256 kB]
Hit:2 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble-updates InRelease
Get:3 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z noble-security InRelease [126 kB]
Reading package lists... Done
"""
VALID_UPDATE_OUTPUT = """\
Get:1 https://archive.ubuntu.com/ubuntu noble InRelease [256 kB]
Hit:2 https://archive.ubuntu.com/ubuntu noble-updates InRelease
Hit:3 https://archive.ubuntu.com/ubuntu noble-backports InRelease
Get:4 https://security.ubuntu.com/ubuntu noble-security InRelease [126 kB]
Reading package lists... Done
"""
VALID_PREFLIGHT_OUTPUT = (
    "'https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble/InRelease' "
    "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble_InRelease 0 \n"
    "'https://archive.ubuntu.com/ubuntu/dists/noble/InRelease' "
    "archive.ubuntu.com_ubuntu_dists_noble_InRelease 0 \n"
    "'https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble-updates/InRelease' "
    "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble-updates_InRelease 0 \n"
    "'https://archive.ubuntu.com/ubuntu/dists/noble-updates/InRelease' "
    "archive.ubuntu.com_ubuntu_dists_noble-updates_InRelease 0 \n"
    "'https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble-backports/InRelease' "
    "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble-backports_InRelease 0 \n"
    "'https://archive.ubuntu.com/ubuntu/dists/noble-backports/InRelease' "
    "archive.ubuntu.com_ubuntu_dists_noble-backports_InRelease 0 \n"
    "'https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble-security/InRelease' "
    "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble-security_InRelease 0 \n"
    "'https://security.ubuntu.com/ubuntu/dists/noble-security/InRelease' "
    "security.ubuntu.com_ubuntu_dists_noble-security_InRelease 0 \n"
    "'https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble/main/"
    "binary-amd64/Packages.xz' "
    "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble_main_binary-amd64_Packages "
    "0 \n"
    "'https://archive.ubuntu.com/ubuntu/dists/noble/main/binary-amd64/Packages.xz' "
    "archive.ubuntu.com_ubuntu_dists_noble_main_binary-amd64_Packages 0 \n"
)
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
        preflight_output: str = VALID_PREFLIGHT_OUTPUT,
        preflight_stderr: str = "",
        preflight_returncode: int = 0,
        update_output: str = VALID_UPDATE_OUTPUT,
        candidate_output: str | None = None,
        installed_output: str | None = None,
        timeout_on: str | None = None,
    ) -> None:
        self.architecture = architecture
        self.preflight_output = preflight_output
        self.preflight_stderr = preflight_stderr
        self.preflight_returncode = preflight_returncode
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
        executable = Path(command_list[0]).name if command_list else ""
        if command_list == [ubuntu_packages.DPKG, "--print-architecture"]:
            key = "architecture"
            stdout = f"{self.architecture}\n"
        elif executable == "apt-get" and "--print-uris" in command_list:
            key = "preflight"
            stdout = self.preflight_output
        elif executable == "apt-get" and command_list[-1] == "update":
            key = "update"
            stdout = self.update_output
        elif executable == "apt-cache":
            key = "candidate"
            stdout = self.candidate_output
        elif executable == "apt-get" and "install" in command_list:
            key = "install"
            stdout = "Reading package lists... Done\n0 upgraded, 22 newly installed.\n"
        elif executable == "dpkg-query":
            key = "installed"
            stdout = self.installed_output
        else:
            raise AssertionError(f"unexpected command: {command_list}")
        if self.timeout_on == key:
            raise subprocess.TimeoutExpired(command_list, timeout_seconds)
        return subprocess.CompletedProcess(
            command_list,
            self.preflight_returncode if key == "preflight" else 0,
            stdout=stdout,
            stderr=self.preflight_stderr if key == "preflight" else "",
        )


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
            self.assertEqual(options[::2], ["-o"] * 26)
            values = options[1::2]
            settings = dict(value.split("=", 1) for value in values)
            source = Path(settings["Dir::Etc::sourcelist"])
            source_parts = Path(settings["Dir::Etc::sourceparts"])
            apt_config = Path(settings["Dir::Etc::main"])
            apt_config_parts = Path(settings["Dir::Etc::parts"])
            preferences = Path(settings["Dir::Etc::preferences"])
            preferences_parts = Path(settings["Dir::Etc::preferencesparts"])
            trusted = Path(settings["Dir::Etc::trusted"])
            trusted_parts = Path(settings["Dir::Etc::trustedparts"])
            auth = Path(settings["Dir::Etc::netrc"])
            auth_parts = Path(settings["Dir::Etc::netrcparts"])
            lists = Path(settings["Dir::State::lists"])
            cache = Path(settings["Dir::Cache"])
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
            self.assertEqual(list(apt_config_parts.iterdir()), [])
            self.assertEqual(list(preferences_parts.iterdir()), [])
            self.assertEqual(list(trusted_parts.iterdir()), [])
            self.assertEqual(list(auth_parts.iterdir()), [])
            self.assertEqual(preferences.read_bytes(), b"")
            self.assertEqual(trusted.read_bytes(), TEST_ARCHIVE_KEYRING)
            self.assertEqual(auth.read_bytes(), b"")
            self.assertEqual(stat.S_IMODE(auth.stat().st_mode), 0o600)
            self.assertTrue(lists.is_relative_to(root))
            self.assertTrue(cache.is_relative_to(root))
            self.assertTrue(archives.is_relative_to(root))
            self.assertEqual(settings["APT::Snapshot"], ubuntu_packages.SNAPSHOT)
            self.assertEqual(settings["Acquire::AllowInsecureRepositories"], "false")
            self.assertEqual(settings["Acquire::AllowWeakRepositories"], "false")
            self.assertEqual(
                settings["Acquire::AllowDowngradeToInsecureRepositories"], "false"
            )
            self.assertEqual(settings["APT::Get::AllowUnauthenticated"], "false")
            self.assertEqual(settings["Acquire::Check-Date"], "true")
            self.assertEqual(settings["Acquire::Check-Valid-Until"], "true")
            self.assertEqual(settings["Acquire::http::Proxy"], "false")
            self.assertEqual(settings["Acquire::https::Proxy"], "false")
            self.assertEqual(settings["Acquire::http::AllowRedirect"], "false")
            self.assertEqual(settings["Acquire::https::AllowRedirect"], "false")
            self.assertEqual(settings["Acquire::https::Verify-Peer"], "true")
            self.assertEqual(settings["Acquire::https::Verify-Host"], "true")
            controlled_config = ubuntu_packages._render_controlled_apt_config(root)
            self.assertEqual(apt_config.read_text(encoding="utf-8"), controlled_config)
            self.assertIn("#clear DPkg::Pre-Install-Pkgs;", controlled_config)
            self.assertIn("#clear APT::Update::Post-Invoke;", controlled_config)
            self.assertNotIn("/etc/apt", controlled_config)
            self.assertNotIn("microsoft", source.read_text(encoding="utf-8").lower())
            self.assertNotIn("docker", source.read_text(encoding="utf-8").lower())
            self.assertEqual(
                source.read_text(encoding="utf-8").count(
                    f"Snapshot: {ubuntu_packages.SNAPSHOT}"
                ),
                2,
            )

    def test_real_runner_uses_only_controlled_environment_and_early_apt_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            options = ubuntu_packages._prepare_isolated_apt_environment(
                root,
                verified_archive_keyring=_test_verified_archive_keyring(),
            )
            command = [ubuntu_packages.APT_GET, *options, "update"]
            completed = subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            hostile_environment = {
                "APT_CONFIG": "/tmp/hostile.conf",
                "LD_PRELOAD": "/tmp/hostile.so",
                "PATH": "/tmp/hostile-bin",
                "http_proxy": "http://proxy.example",
                "https_proxy": "http://proxy.example",
            }
            with (
                patch.dict(os.environ, hostile_environment, clear=True),
                patch.object(
                    ubuntu_packages.subprocess,
                    "run",
                    return_value=completed,
                ) as run,
            ):
                self.assertIs(
                    ubuntu_packages._run_command(command, 17),
                    completed,
                )
            environment = run.call_args.kwargs["env"]
            self.assertEqual(
                environment,
                {
                    "APT_CONFIG": (root / "apt.conf").as_posix(),
                    "APT_LISTCHANGES_FRONTEND": "none",
                    "DEBIAN_FRONTEND": "noninteractive",
                    "LC_ALL": "C",
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                },
            )
            self.assertEqual(run.call_args.kwargs["timeout"], 17)

            with self.assertRaisesRegex(OSError, "exactly one Dir::Etc::main"):
                ubuntu_packages._run_command([ubuntu_packages.APT_GET, "update"], 17)

    def test_controlled_apt_config_rejects_relative_root(self) -> None:
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "path is unsafe"):
            ubuntu_packages._render_controlled_apt_config(Path("relative"))

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


class SnapshotPreflightPolicyTests(unittest.TestCase):
    def test_exact_snapshot_and_logical_shadow_routes_are_accepted(self) -> None:
        ubuntu_packages.validate_snapshot_preflight_output(VALID_PREFLIGHT_OUTPUT)
        reversed_output = "\n".join(reversed(VALID_PREFLIGHT_OUTPUT.splitlines())) + "\n"
        ubuntu_packages.validate_snapshot_preflight_output(reversed_output)

    def test_explicit_default_https_port_is_accepted(self) -> None:
        output = VALID_PREFLIGHT_OUTPUT.replace(
            "https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble/InRelease",
            "https://snapshot.ubuntu.com:443/ubuntu/20260723T000000Z/dists/noble/InRelease",
            1,
        )
        ubuntu_packages.validate_snapshot_preflight_output(output)

    def test_every_physical_and_logical_inrelease_route_is_required(self) -> None:
        physical_line = VALID_PREFLIGHT_OUTPUT.splitlines()[0]
        logical_line = VALID_PREFLIGHT_OUTPUT.splitlines()[1]
        for label, removed, message in (
            ("physical", physical_line, "physical InRelease"),
            ("logical", logical_line, "logical InRelease"),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                message,
            ):
                ubuntu_packages.validate_snapshot_preflight_output(
                    VALID_PREFLIGHT_OUTPUT.replace(f"{removed}\n", "", 1)
                )

    def test_every_optional_target_requires_physical_logical_parity(self) -> None:
        physical_packages = next(
            line
            for line in VALID_PREFLIGHT_OUTPUT.splitlines()
            if "snapshot.ubuntu.com" in line and "Packages.xz" in line
        )
        logical_packages = next(
            line
            for line in VALID_PREFLIGHT_OUTPUT.splitlines()
            if "archive.ubuntu.com" in line and "Packages.xz" in line
        )
        for label, removed in (
            ("physical", physical_packages),
            ("logical", logical_packages),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "target parity failed",
            ):
                ubuntu_packages.validate_snapshot_preflight_output(
                    VALID_PREFLIGHT_OUTPUT.replace(f"{removed}\n", "", 1)
                )

    def test_unapproved_or_ambiguous_preflight_routes_are_rejected(self) -> None:
        approved = (
            "https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/"
            "dists/noble/InRelease"
        )
        rejected = (
            approved.replace("https://", "http://"),
            approved.replace("snapshot.ubuntu.com", "snapshot.ubuntu.com.evil.example"),
            approved.replace("snapshot.ubuntu.com", "user@snapshot.ubuntu.com"),
            approved.replace("snapshot.ubuntu.com", "snapshot.ubuntu.com:444"),
            approved.replace("snapshot.ubuntu.com", "snapshot.ubuntu.com:invalid"),
            f"{approved}?mirror=live",
            f"{approved}#fragment",
            approved.replace("20260723T000000Z", "20260722T000000Z"),
            approved.replace("20260723T000000Z", "20260723T000000Zsuffix"),
            approved.replace("20260723T000000Z", "prefix20260723T000000Z"),
            approved.replace("/dists/noble/", "/dists/noble/../"),
            approved.replace("/dists/noble/", "/dists/noble/%2e%2e/"),
            approved.replace("/dists/noble/", "/dists//noble/"),
            approved.replace("/dists/noble/", "/dists/oracular/"),
            approved.replace("/ubuntu/20260723T000000Z", "/ubuntu2/20260723T000000Z"),
        )
        original_line = VALID_PREFLIGHT_OUTPUT.splitlines()[0]
        for url in rejected:
            replacement = f"'{url}' rejected_destination 0 "
            output = VALID_PREFLIGHT_OUTPUT.replace(original_line, replacement, 1)
            with self.subTest(url=url), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "unapproved",
            ):
                ubuntu_packages.validate_snapshot_preflight_output(output)

    def test_logical_suite_must_use_its_exact_controlled_host(self) -> None:
        output = VALID_PREFLIGHT_OUTPUT.replace(
            "https://security.ubuntu.com/ubuntu/dists/noble-security/InRelease",
            "https://archive.ubuntu.com/ubuntu/dists/noble-security/InRelease",
            1,
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
            ubuntu_packages.validate_snapshot_preflight_output(output)

    def test_malformed_duplicate_and_oversized_preflight_output_is_rejected(self) -> None:
        first_line = VALID_PREFLIGHT_OUTPUT.splitlines()[0]
        malformed = (
            first_line.removeprefix("'"),
            f"{first_line} extra",
            first_line.replace(
                "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble_InRelease",
                "unsafe/destination",
            ),
            f"{VALID_PREFLIGHT_OUTPUT}\n",
        )
        for output in malformed:
            with self.subTest(output=output[:80]), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "malformed",
            ):
                ubuntu_packages.validate_snapshot_preflight_output(output)

        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "duplicate"):
            ubuntu_packages.validate_snapshot_preflight_output(
                f"{VALID_PREFLIGHT_OUTPUT}{first_line}\n"
            )
        lines = VALID_PREFLIGHT_OUTPUT.splitlines()
        duplicate_destination = f"{lines[1].split()[0]} {lines[0].split()[1]} 0 "
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "destination"):
            ubuntu_packages.validate_snapshot_preflight_output(
                VALID_PREFLIGHT_OUTPUT.replace(lines[1], duplicate_destination, 1)
            )
        explicit_port_line = first_line.replace(
            "snapshot.ubuntu.com/",
            "snapshot.ubuntu.com:443/",
        ).replace(
            "snapshot.ubuntu.com_ubuntu_20260723T000000Z_dists_noble_InRelease",
            "snapshot.ubuntu.com:443_ubuntu_20260723T000000Z_dists_noble_InRelease",
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "normalized"):
            ubuntu_packages.validate_snapshot_preflight_output(
                f"{VALID_PREFLIGHT_OUTPUT}{explicit_port_line}\n"
            )
        with (
            patch.object(ubuntu_packages, "_MAX_PREFLIGHT_OUTPUT_BYTES", 10),
            self.assertRaisesRegex(ubuntu_packages.PolicyError, "safety limit"),
        ):
            ubuntu_packages.validate_snapshot_preflight_output(VALID_PREFLIGHT_OUTPUT)
        with (
            patch.object(ubuntu_packages, "_MAX_PREFLIGHT_RECORDS", 1),
            self.assertRaisesRegex(ubuntu_packages.PolicyError, "too many"),
        ):
            ubuntu_packages.validate_snapshot_preflight_output(VALID_PREFLIGHT_OUTPUT)


class SnapshotOutputPolicyTests(unittest.TestCase):
    def test_snapshot_only_update_output_is_accepted(self) -> None:
        ubuntu_packages.validate_snapshot_update_output(SNAPSHOT_ENDPOINT_UPDATE_OUTPUT)

    def test_snapshot_selected_logical_ubuntu_output_is_accepted(self) -> None:
        ubuntu_packages.validate_snapshot_update_output(VALID_UPDATE_OUTPUT)

    def test_mixed_approved_representations_and_default_port_are_accepted(self) -> None:
        output = (
            "Get:1 https://archive.ubuntu.com:443/ubuntu/ noble InRelease [256 kB]\n"
            "Hit:2 https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/ "
            "noble-security InRelease\n"
        )
        ubuntu_packages.validate_snapshot_update_output(output)

    def test_insecure_logical_repository_is_rejected(self) -> None:
        live_output = VALID_UPDATE_OUTPUT.replace(
            "https://archive.ubuntu.com/ubuntu",
            "http://archive.ubuntu.com/ubuntu",
            1,
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
            ubuntu_packages.validate_snapshot_update_output(live_output)

    def test_mixed_approved_and_insecure_repository_output_is_rejected(self) -> None:
        mixed_output = (
            VALID_UPDATE_OUTPUT
            + "Hit:4 http://security.ubuntu.com/ubuntu noble-security InRelease\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
            ubuntu_packages.validate_snapshot_update_output(mixed_output)

    def test_no_repository_activity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "no verified controlled"):
            ubuntu_packages.validate_snapshot_update_output("Reading package lists... Done\n")

    def test_snapshot_url_outside_repository_activity_is_not_accepted(self) -> None:
        output = (
            "Checking https://snapshot.ubuntu.com/ubuntu/20260723T000000Z\n"
            "Reading package lists... Done\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "no verified controlled"):
            ubuntu_packages.validate_snapshot_update_output(output)

    def test_malformed_snapshot_url_is_rejected_as_unapproved(self) -> None:
        output = (
            "Get:1 https://snapshot.ubuntu.com:invalid/ubuntu/20260723T000000Z noble InRelease\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
            ubuntu_packages.validate_snapshot_update_output(output)

    def test_wrong_snapshot_and_unapproved_https_repository_are_rejected(self) -> None:
        wrong_snapshot = SNAPSHOT_ENDPOINT_UPDATE_OUTPUT.replace(
            "20260723T000000Z",
            "20260722T000000Z",
        )
        unapproved = (
            VALID_UPDATE_OUTPUT
            + "Hit:5 https://packages.microsoft.com/ubuntu/24.04 noble InRelease\n"
        )
        for label, output in (("wrong snapshot", wrong_snapshot), ("unapproved", unapproved)):
            with self.subTest(label=label), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "unapproved",
            ):
                ubuntu_packages.validate_snapshot_update_output(output)

    def test_repository_identity_rejects_nonexact_url_variants(self) -> None:
        rejected = (
            "http://archive.ubuntu.com/ubuntu",
            "https://archive.ubuntu.com.evil.example/ubuntu",
            "https://user@archive.ubuntu.com/ubuntu",
            "https://archive.ubuntu.com:444/ubuntu",
            "https://archive.ubuntu.com:/ubuntu",
            "https://archive.ubuntu.com/ubuntu?snapshot=latest",
            "https://archive.ubuntu.com/ubuntu#snapshot",
            "https://security.ubuntu.com/not-ubuntu",
            "https://archive.ubuntu.com/ubuntu2",
            "https://archive.ubuntu.com/ubuntu/evil",
            "https://archive.ubuntu.com/ubuntu/../evil",
            "https://archive.ubuntu.com/ubuntu/%2e%2e/evil",
            "https://archive.ubuntu.com/ubuntu.",
            (
                "https://snapshot.ubuntu.com/ubuntu/"
                f"{ubuntu_packages.SNAPSHOT}/../other"
            ),
        )
        for url in rejected:
            with self.subTest(url=url):
                self.assertFalse(
                    ubuntu_packages._repository_output_url_is_allowed(
                        url,
                        ubuntu_packages.SNAPSHOT,
                    )
                )

        accepted = (
            "https://archive.ubuntu.com:443/ubuntu",
            "https://archive.ubuntu.com/ubuntu/",
            "https://security.ubuntu.com/ubuntu/",
            f"https://snapshot.ubuntu.com/ubuntu/{ubuntu_packages.SNAPSHOT}/",
        )
        for url in accepted:
            with self.subTest(url=url):
                self.assertTrue(
                    ubuntu_packages._repository_output_url_is_allowed(
                        url,
                        ubuntu_packages.SNAPSHOT,
                    )
                )

    def test_one_activity_line_with_approved_and_foreign_urls_is_rejected(self) -> None:
        output = (
            "Get:1 https://archive.ubuntu.com/ubuntu "
            "https://evil.example/ubuntu noble InRelease\n"
        )
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "secondary URI"):
            ubuntu_packages.validate_snapshot_update_output(output)

    def test_repository_activity_without_an_approved_primary_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved primary"):
            ubuntu_packages.validate_snapshot_update_output("Get:1 noble InRelease\n")

    def test_embedded_allowed_url_cannot_hide_an_invalid_primary_token(self) -> None:
        rejected = (
            "Get:1 xhttps://archive.ubuntu.com/ubuntu noble InRelease\n",
            (
                "Get:1 ftp://evil.example/https://archive.ubuntu.com/ubuntu "
                "noble InRelease\n"
            ),
            "Get:1 file:///https://archive.ubuntu.com/ubuntu noble InRelease\n",
            (
                "Get:1 ftp://evil.example/ubuntu "
                "https://archive.ubuntu.com/ubuntu noble InRelease\n"
            ),
            "Get:1 garbage https://archive.ubuntu.com/ubuntu noble InRelease\n",
        )
        for output in rejected:
            with self.subTest(output=output), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "unapproved primary",
            ):
                ubuntu_packages.validate_snapshot_update_output(output)

    def test_malformed_repository_activity_prefix_is_rejected(self) -> None:
        for output in (
            "Get:\n",
            "Get:1x https://archive.ubuntu.com/ubuntu noble InRelease\n",
            "Hit https://archive.ubuntu.com/ubuntu noble InRelease\n",
        ):
            with self.subTest(output=output), self.assertRaisesRegex(
                ubuntu_packages.PolicyError,
                "malformed",
            ):
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
                    + f"{prefix} https://security.ubuntu.com/ubuntu "
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
        self.assertEqual(len(commands), 6)
        self.assertEqual(commands[0], [ubuntu_packages.DPKG, "--print-architecture"])
        self.assertEqual(commands[1][0], ubuntu_packages.APT_GET)
        preflight_index = commands[1].index("--print-uris")
        self.assertEqual(
            commands[1][preflight_index:],
            ["--print-uris", "-S", "20260723T000000Z", "update"],
        )
        self.assertEqual(commands[2][0], ubuntu_packages.APT_GET)
        self.assertEqual(commands[2][-3:], ["-S", "20260723T000000Z", "update"])
        expected_names = [name for name, _version in ubuntu_packages.EXPECTED_PACKAGES]
        self.assertEqual(commands[3][0], ubuntu_packages.APT_CACHE)
        policy_index = commands[3].index("policy")
        self.assertEqual(commands[3][policy_index + 1 :], expected_names)
        install_snapshot_index = commands[4].index("-S")
        self.assertEqual(
            commands[4][install_snapshot_index:],
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
        shared_options = commands[2][1:-3]
        self.assertEqual(commands[1][1:preflight_index], shared_options)
        self.assertEqual(commands[3][1:policy_index], shared_options)
        self.assertEqual(commands[4][1:install_snapshot_index], shared_options)
        self.assertEqual(shared_options[::2], ["-o"] * 26)
        option_values = shared_options[1::2]
        self.assertIn("APT::Snapshot=20260723T000000Z", option_values)
        self.assertIn("Acquire::AllowInsecureRepositories=false", option_values)
        self.assertIn("Acquire::AllowWeakRepositories=false", option_values)
        self.assertIn("Acquire::AllowDowngradeToInsecureRepositories=false", option_values)
        self.assertIn("APT::Get::AllowUnauthenticated=false", option_values)
        self.assertIn("Acquire::Check-Date=true", option_values)
        self.assertIn("Acquire::Check-Valid-Until=true", option_values)
        self.assertIn("Acquire::https::Verify-Peer=true", option_values)
        self.assertIn("Acquire::https::Verify-Host=true", option_values)
        self.assertTrue(any(value.startswith("Dir::Etc::sourcelist=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::Etc::sourceparts=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::State::lists=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::Cache=") for value in option_values))
        self.assertTrue(any(value.startswith("Dir::Cache::archives=") for value in option_values))
        self.assertFalse(any("microsoft" in value.lower() for value in option_values))
        self.assertEqual(
            commands[5],
            [
                ubuntu_packages.DPKG_QUERY,
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
        for stage in (
            "architecture",
            "preflight",
            "update",
            "candidate",
            "install",
            "installed",
        ):
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
            self.assertEqual(len(runner.calls), 3)
            self.assertFalse(output.exists())

    def test_unapproved_real_update_url_blocks_candidate_install_and_evidence(self) -> None:
        runner = FakeRunner(
            update_output=VALID_UPDATE_OUTPUT.replace(
                "https://archive.ubuntu.com/ubuntu",
                "https://mirror.example/ubuntu",
                1,
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertEqual(len(runner.calls), 3)
            self.assertFalse(any("install" in command for command, _ in runner.calls))
            self.assertFalse(output.exists())

    def test_unapproved_preflight_route_blocks_update_install_and_evidence(self) -> None:
        bad_output = VALID_PREFLIGHT_OUTPUT.replace(
            "https://snapshot.ubuntu.com/ubuntu/20260723T000000Z/dists/noble/InRelease",
            "https://mirror.example/ubuntu/20260723T000000Z/dists/noble/InRelease",
            1,
        )
        runner = FakeRunner(preflight_output=bad_output)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ubuntu_packages.PolicyError, "unapproved"):
                _install_and_verify(
                    output,
                    os_release_text=VALID_OS_RELEASE,
                    source_files=VALID_SOURCES,
                    runner=runner,
                )
            self.assertEqual(len(runner.calls), 2)
            self.assertFalse(any("install" in command for command, _ in runner.calls))
            self.assertFalse(output.exists())

    def test_preflight_nonzero_or_stderr_blocks_update_and_evidence(self) -> None:
        runners = (
            FakeRunner(preflight_returncode=100),
            FakeRunner(preflight_stderr="unexpected apt notice\n"),
        )
        for runner in runners:
            with self.subTest(runner=runner), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "evidence.json"
                with self.assertRaises(ubuntu_packages.PolicyError):
                    _install_and_verify(
                        output,
                        os_release_text=VALID_OS_RELEASE,
                        source_files=VALID_SOURCES,
                        runner=runner,
                    )
                self.assertEqual(len(runner.calls), 2)
                self.assertFalse(output.exists())

    def test_preflight_state_or_control_mutation_blocks_update_and_evidence(self) -> None:
        for mutation in (
            "state",
            "source",
            "keyring",
            "cache_mode",
            "sourceparts_symlink",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                fake = FakeRunner()

                def mutating_runner(
                    command: Sequence[str], timeout_seconds: int
                ) -> subprocess.CompletedProcess[str]:
                    result = fake(command, timeout_seconds)
                    command_list = list(command)
                    if "--print-uris" not in command_list:
                        return result
                    option_values = command_list[2::2]
                    if mutation == "state":
                        lists_value = next(
                            value
                            for value in option_values
                            if value.startswith("Dir::State::lists=")
                        )
                        (Path(lists_value.split("=", 1)[1]) / "unexpected").write_text(
                            "mutation\n",
                            encoding="utf-8",
                        )
                    elif mutation == "source":
                        source_value = next(
                            value
                            for value in option_values
                            if value.startswith("Dir::Etc::sourcelist=")
                        )
                        Path(source_value.split("=", 1)[1]).write_text(
                            "Types: deb\n",
                            encoding="utf-8",
                        )
                    elif mutation == "keyring":
                        source_value = next(
                            value
                            for value in option_values
                            if value.startswith("Dir::Etc::sourcelist=")
                        )
                        keyring = (
                            Path(source_value.split("=", 1)[1]).parent
                            / "ubuntu-archive-keyring.gpg"
                        )
                        keyring.chmod(0o777)
                    elif mutation == "cache_mode":
                        cache_value = next(
                            value
                            for value in option_values
                            if value.startswith("Dir::Cache=")
                        )
                        Path(cache_value.split("=", 1)[1]).chmod(0o777)
                    else:
                        parts_value = next(
                            value
                            for value in option_values
                            if value.startswith("Dir::Etc::sourceparts=")
                        )
                        sourceparts = Path(parts_value.split("=", 1)[1])
                        replacement = sourceparts.parent / "replacement-empty"
                        replacement.mkdir()
                        sourceparts.rmdir()
                        sourceparts.symlink_to(replacement, target_is_directory=True)
                    return result

                output = Path(tmp) / "evidence.json"
                with self.assertRaisesRegex(
                    ubuntu_packages.PolicyError,
                    "changed controlled metadata|wrong type|mutated isolated state|source drifted|keyring metadata drifted",
                ):
                    _install_and_verify(
                        output,
                        os_release_text=VALID_OS_RELEASE,
                        source_files=VALID_SOURCES,
                        runner=mutating_runner,
                    )
                self.assertEqual(len(fake.calls), 2)
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
