from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import install_locked  # noqa: E402


class InstallLockedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._environment_lock_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._environment_lock_temp.cleanup)
        self._environment_lock_temp_patch = patch.object(
            install_locked.tempfile,
            "gettempdir",
            return_value=self._environment_lock_temp.name,
        )
        self._environment_lock_temp_patch.start()
        self.addCleanup(self._environment_lock_temp_patch.stop)

    def test_profiles_form_the_expected_capability_lattice(self) -> None:
        self.assertEqual(
            set(install_locked.PROFILE_LOCKS),
            {"build", "runtime", "app", "dev", "app-dev", "package"},
        )
        app_state = self._state("app")
        package_state = self._state("package")

        with patch.object(install_locked, "_state_context_is_usable", return_value=True):
            self.assertEqual(install_locked._effective_profile("dev", app_state), "app-dev")
            self.assertEqual(install_locked._effective_profile("runtime", package_state), "package")

    def test_unknown_profile_is_rejected_by_argparse(self) -> None:
        with self.assertRaises(SystemExit):
            install_locked.main(["unknown"])

    def test_third_party_install_is_hash_locked_and_binary_only(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(install_locked, "_run", return_value=completed) as runner:
            install_locked._pip_install_lock(ROOT / "requirements/locks/runtime.txt")

        command = runner.call_args.args[0]
        self.assertEqual(command[:5], [sys.executable, "-m", "pip", "--isolated", "install"])
        self.assertIn("--require-hashes", command)
        self.assertIn("--only-binary=:all:", command)
        self.assertIn("--force-reinstall", command)
        self.assertIn("--no-input", command)
        self.assertNotIn("-e", command)

    def test_editable_install_cannot_resolve_or_build_dependencies(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(install_locked, "_run", return_value=completed) as runner:
            install_locked._install_project()

        command = runner.call_args.args[0]
        self.assertIn("--no-index", command)
        self.assertIn("--no-deps", command)
        self.assertIn("--no-build-isolation", command)
        self.assertEqual(command[-2:], ["-e", str(ROOT)])
        self.assertNotIn("--require-hashes", command)

    def test_build_profile_does_not_install_the_editable_project(self) -> None:
        completed_inventory = [{"name": "pip", "version": "26.1.2"}]
        with (
            patch.object(install_locked, "support_error", return_value=None),
            patch.object(install_locked, "_EnvironmentLock", _NoOpLock),
            patch.object(install_locked, "_load_state", return_value=None),
            patch.object(install_locked, "_validation_errors", return_value=["missing"]),
            patch.object(install_locked, "_is_project_venv", return_value=False),
            patch.object(install_locked, "_pip_install_lock") as install_lock,
            patch.object(install_locked, "_install_project") as install_project,
            patch.object(
                install_locked, "_distribution_inventory", return_value=completed_inventory
            ),
            patch.object(install_locked, "_locked_version_errors", return_value=[]),
            patch.object(
                install_locked,
                "_record_integrity",
                return_value=({"files": 1, "sha256": "digest"}, []),
            ),
            patch.object(install_locked, "_import_errors", return_value=[]),
            patch.object(install_locked, "_pip_check_error", return_value=None),
        ):
            install_locked._install("build")

        install_lock.assert_called_once_with(ROOT / install_locked.BUILD_LOCK)
        install_project.assert_not_called()

    def test_failed_install_removes_a_previous_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{}\n", encoding="utf-8")
            state = self._state("runtime")
            with (
                patch.object(install_locked, "STATE_FILE", state_file),
                patch.object(install_locked, "support_error", return_value=None),
                patch.object(install_locked, "_EnvironmentLock", _NoOpLock),
                patch.object(install_locked, "_load_state", return_value=state),
                patch.object(install_locked, "_state_integrity_errors", return_value=[]),
                patch.object(install_locked, "_validation_errors", return_value=["stale"]),
                patch.object(install_locked, "_is_project_venv", return_value=True),
                patch.object(install_locked, "_distribution_inventory", return_value=[]),
                patch.object(
                    install_locked,
                    "_pip_install_lock",
                    side_effect=subprocess.CalledProcessError(1, ["pip"]),
                ),
            ):
                self.assertEqual(install_locked.main(["runtime"]), 2)

            self.assertFalse(state_file.exists())

    def test_untrusted_state_is_preserved_without_executing_repair_pip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{}\n", encoding="utf-8")
            state = self._state("runtime")
            with (
                patch.object(install_locked, "STATE_FILE", state_file),
                patch.object(install_locked, "support_error", return_value=None),
                patch.object(install_locked, "_EnvironmentLock", _NoOpLock),
                patch.object(install_locked, "_load_state", return_value=state),
                patch.object(
                    install_locked,
                    "_state_integrity_errors",
                    return_value=["installed file hash mismatch"],
                ),
                patch.object(install_locked, "_is_project_venv", return_value=True),
                patch.object(install_locked, "_pip_install_lock") as install_lock,
            ):
                self.assertEqual(install_locked.main(["runtime"]), 2)

            self.assertTrue(state_file.exists())
            install_lock.assert_not_called()

    def test_check_mode_never_calls_install(self) -> None:
        with (
            patch.object(install_locked, "support_error", return_value=None),
            patch.object(install_locked, "_validation_errors", return_value=["drift"]),
            patch.object(install_locked, "_install") as install,
        ):
            self.assertEqual(install_locked.main(["--allow-external-env", "--check", "app"]), 1)

        install.assert_not_called()

    def test_default_external_environment_is_rejected_before_install(self) -> None:
        with (
            patch.object(install_locked, "support_error", return_value=None),
            patch.object(
                install_locked,
                "_environment_error",
                return_value="external environment refused",
            ),
            patch.object(install_locked, "_install") as install,
        ):
            self.assertEqual(install_locked.main(["runtime"]), 2)

        install.assert_not_called()

    def test_external_environment_requires_explicit_opt_in(self) -> None:
        with (
            patch.object(install_locked, "support_error", return_value=None),
            patch.object(install_locked, "_environment_error", return_value=None) as guard,
            patch.object(install_locked, "_install") as install,
        ):
            self.assertEqual(install_locked.main(["--allow-external-env", "runtime"]), 0)

        guard.assert_called_once_with(allow_external=True)
        install.assert_called_once_with("runtime")

    def test_linked_project_venv_is_rejected(self) -> None:
        with patch.object(
            install_locked,
            "project_venv_redirect_error",
            return_value="lib is a link or reparse point",
        ):
            error = install_locked._environment_error(allow_external=False)

        self.assertIn("Refusing unsafe project environment", error or "")

    def test_nested_venv_directory_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv = root / ".venv"
            external = root / "external"
            venv.mkdir()
            external.mkdir()
            (venv / "lib").symlink_to(external, target_is_directory=True)

            error = install_locked.project_venv_redirect_error(venv)

        self.assertIn("lib is a link or reparse point", error or "")

    def test_internal_lib64_alias_is_allowed(self) -> None:
        if os.name == "nt":
            self.skipTest("lib64 aliases are POSIX-only")
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            (venv / "lib").mkdir(parents=True)
            (venv / "lib64").symlink_to("lib", target_is_directory=True)

            self.assertIsNone(install_locked.project_venv_redirect_error(venv))

    def test_fingerprint_input_change_invalidates_noop(self) -> None:
        state = self._state("runtime")
        state["inputs"] = {"pyproject.toml": "old"}
        with (
            patch.object(install_locked, "_is_project_venv", return_value=True),
            patch.object(install_locked, "_state_integrity_errors", return_value=[]),
            patch.object(install_locked, "_state_inputs", return_value={"pyproject.toml": "new"}),
        ):
            self.assertEqual(
                install_locked._validation_errors("runtime", state),
                ["dependency inputs changed"],
            )

    def test_fingerprint_rejects_a_different_virtual_environment(self) -> None:
        state = self._state("runtime")
        for field in ("executable", "prefix"):
            with self.subTest(field=field):
                changed = dict(state)
                changed["platform"] = dict(state["platform"])
                changed["platform"][field] = "/different/environment"
                self.assertFalse(install_locked._state_context_is_usable(changed))

    def test_inventory_change_invalidates_noop_before_import_probe(self) -> None:
        state = self._state("runtime")
        state["inputs"] = {"input": "same"}
        state["inventory"] = []
        state["inventory_sha256"] = install_locked._inventory_hash([])
        changed = [{"name": "numpy", "version": "0"}]
        with (
            patch.object(install_locked, "_is_project_venv", return_value=True),
            patch.object(install_locked, "_state_context_is_usable", return_value=True),
            patch.object(install_locked, "_state_inputs", return_value={"input": "same"}),
            patch.object(install_locked, "_distribution_inventory", return_value=changed),
            patch.object(install_locked, "_import_errors") as imports,
        ):
            self.assertEqual(
                install_locked._validation_errors("runtime", state),
                ["installed distribution inventory changed"],
            )

        imports.assert_not_called()

    def test_record_failure_stops_before_any_import_or_pip_execution(self) -> None:
        state = self._state("runtime")
        state["inputs"] = {"input": "same"}
        state["inventory"] = []
        state["inventory_sha256"] = install_locked._inventory_hash([])
        state["record_integrity"] = {"files": 1, "sha256": "old"}
        cases = (
            ({"files": 1, "sha256": "old"}, ["installed file hash mismatch"]),
            ({"files": 1, "sha256": "new"}, []),
        )
        for fingerprint, record_errors in cases:
            with self.subTest(fingerprint=fingerprint, record_errors=record_errors):
                with (
                    patch.object(install_locked, "_is_project_venv", return_value=True),
                    patch.object(install_locked, "_state_context_is_usable", return_value=True),
                    patch.object(install_locked, "_state_inputs", return_value={"input": "same"}),
                    patch.object(install_locked, "_distribution_inventory", return_value=[]),
                    patch.object(install_locked, "_locked_version_errors", return_value=[]),
                    patch.object(
                        install_locked, "_unexpected_distribution_errors", return_value=[]
                    ),
                    patch.object(
                        install_locked,
                        "_record_integrity_for_versions",
                        return_value=(fingerprint, record_errors),
                    ),
                    patch.object(install_locked, "_import_errors") as imports,
                    patch.object(install_locked, "_pip_check_error") as pip_check,
                ):
                    errors = install_locked._validation_errors("runtime", state)

                self.assertTrue(errors)
                imports.assert_not_called()
                pip_check.assert_not_called()

    def test_post_install_record_failure_stops_before_import_execution(self) -> None:
        with (
            patch.object(install_locked, "support_error", return_value=None),
            patch.object(install_locked, "_EnvironmentLock", _NoOpLock),
            patch.object(install_locked, "_load_state", return_value=None),
            patch.object(install_locked, "_validation_errors", return_value=["stale"]),
            patch.object(install_locked, "_is_project_venv", return_value=False),
            patch.object(install_locked, "_pip_install_lock"),
            patch.object(install_locked, "_distribution_inventory", return_value=[]),
            patch.object(install_locked, "_locked_version_errors", return_value=[]),
            patch.object(
                install_locked,
                "_record_integrity",
                return_value=({}, ["installed file hash mismatch"]),
            ),
            patch.object(install_locked, "_import_errors") as imports,
            patch.object(install_locked, "_pip_check_error") as pip_check,
        ):
            with self.assertRaisesRegex(
                install_locked.LockedInstallError, "installed file hash mismatch"
            ):
                install_locked._install("build")

        imports.assert_not_called()
        pip_check.assert_not_called()

    def test_editable_source_must_point_to_this_repository(self) -> None:
        direct_url = json.dumps(
            {"url": Path("/somewhere/else").as_uri(), "dir_info": {"editable": True}}
        )
        distribution = SimpleNamespace(
            version=install_locked.PROJECT_VERSION,
            read_text=lambda name: direct_url if name == "direct_url.json" else None,
        )
        with patch.object(
            install_locked.importlib.metadata, "distribution", return_value=distribution
        ):
            self.assertIn("expected", install_locked._editable_error() or "")

    def test_record_integrity_detects_installed_file_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            module = site / "demo.py"
            module.write_bytes(b"safe\n")
            info = site / "demo-1.0.dist-info"
            info.mkdir()
            (info / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n", encoding="utf-8"
            )
            digest = base64.urlsafe_b64encode(hashlib.sha256(module.read_bytes()).digest()).rstrip(
                b"="
            )
            (info / "RECORD").write_text(
                f"demo.py,sha256={digest.decode('ascii')},{module.stat().st_size}\n"
                "demo-1.0.dist-info/METADATA,,\n"
                "demo-1.0.dist-info/RECORD,,\n",
                encoding="utf-8",
            )
            distribution = install_locked.importlib.metadata.PathDistribution(info)
            with (
                patch.object(
                    install_locked.importlib.metadata,
                    "distributions",
                    return_value=[distribution],
                ),
                patch.object(install_locked, "_locked_versions", return_value={"demo": "1.0"}),
            ):
                fingerprint, errors = install_locked._record_integrity("build")
                self.assertEqual(errors, [])
                self.assertEqual(fingerprint["files"], 1)

                module.write_bytes(b"tampered\n")
                _fingerprint, errors = install_locked._record_integrity("build")

            self.assertEqual(errors, ["installed file hash mismatch: demo:demo.py"])

    def test_non_build_record_integrity_includes_editable_loader_metadata(self) -> None:
        with (
            patch.object(install_locked, "_locked_versions", return_value={}),
            patch.object(
                install_locked.importlib.metadata,
                "distributions",
                return_value=[],
            ),
        ):
            _fingerprint, errors = install_locked._record_integrity("runtime")

        self.assertEqual(
            errors,
            [
                "cannot verify RECORD for "
                f"{install_locked._normalise_name(install_locked.PROJECT_NAME)}=="
                f"{install_locked.PROJECT_VERSION}: found 0 copies"
            ],
        )

    def test_editable_mapping_is_validated_before_import_probe(self) -> None:
        state = self._state("runtime")
        state["inputs"] = {"input": "same"}
        state["inventory"] = []
        state["inventory_sha256"] = install_locked._inventory_hash([])
        state["record_integrity"] = {"files": 1, "sha256": "same"}
        with (
            patch.object(install_locked, "_is_project_venv", return_value=True),
            patch.object(install_locked, "_state_context_is_usable", return_value=True),
            patch.object(install_locked, "_state_inputs", return_value={"input": "same"}),
            patch.object(install_locked, "_distribution_inventory", return_value=[]),
            patch.object(install_locked, "_locked_version_errors", return_value=[]),
            patch.object(install_locked, "_unexpected_distribution_errors", return_value=[]),
            patch.object(
                install_locked,
                "_record_integrity_for_versions",
                return_value=({"files": 1, "sha256": "same"}, []),
            ),
            patch.object(install_locked, "_editable_error", return_value="bad mapping"),
            patch.object(install_locked, "_import_errors") as imports,
            patch.object(install_locked, "_pip_check_error") as pip_check,
        ):
            errors = install_locked._validation_errors("runtime", state)

        self.assertEqual(errors, ["bad mapping"])
        imports.assert_not_called()
        pip_check.assert_not_called()

    def test_supported_python_and_platform_envelope(self) -> None:
        self.assertIsNone(
            install_locked.support_error(
                "app",
                implementation="cpython",
                python_version=(3, 12),
                system="Linux",
                machine="x86_64",
                libc=("glibc", "2.34"),
            )
        )
        too_new = install_locked.support_error(
            "runtime",
            implementation="cpython",
            python_version=(3, 13),
            system="Linux",
            machine="x86_64",
        )
        self.assertIn("3.10, 3.11, or 3.12", too_new or "")
        old_glibc = install_locked.support_error(
            "app",
            implementation="cpython",
            python_version=(3, 11),
            system="Linux",
            machine="x86_64",
            libc=("glibc", "2.31"),
        )
        self.assertIn("glibc 2.34", old_glibc or "")
        old_macos = install_locked.support_error(
            "app",
            implementation="cpython",
            python_version=(3, 11),
            system="Darwin",
            machine="arm64",
            macos_version="12.7",
        )
        self.assertIn("macOS 13", old_macos or "")
        headless_macos_too_old = install_locked.support_error(
            "runtime",
            implementation="cpython",
            python_version=(3, 11),
            system="Darwin",
            machine="x86_64",
            macos_version="10.15",
        )
        self.assertIn("macOS 11", headless_macos_too_old or "")
        self.assertIsNone(
            install_locked.support_error(
                "runtime",
                implementation="cpython",
                python_version=(3, 11),
                system="Darwin",
                machine="x86_64",
                macos_version="11.0",
            )
        )
        headless_linux_too_old = install_locked.support_error(
            "dev",
            implementation="cpython",
            python_version=(3, 11),
            system="Linux",
            machine="x86_64",
            libc=("glibc", "2.27"),
        )
        self.assertIn("glibc 2.28", headless_linux_too_old or "")
        self.assertIsNone(
            install_locked.support_error(
                "runtime",
                implementation="cpython",
                python_version=(3, 11),
                system="Linux",
                machine="x86_64",
                libc=("glibc", "2.28"),
            )
        )
        unsupported_arch = install_locked.support_error(
            "runtime",
            implementation="cpython",
            python_version=(3, 11),
            system="Linux",
            machine="aarch64",
        )
        self.assertIn("No reviewed", unsupported_arch or "")

        for system, machine in (("Linux", "AMD64"), ("Windows", "x86_64")):
            with self.subTest(system=system, machine=machine):
                marker_alias = install_locked.support_error(
                    "runtime",
                    implementation="cpython",
                    python_version=(3, 11),
                    system=system,
                    machine=machine,
                )
                self.assertIn("No reviewed", marker_alias or "")

        wrong_bitness = install_locked.support_error(
            "runtime",
            implementation="cpython",
            python_version=(3, 11),
            system="Linux",
            machine="x86_64",
            pointer_bits=32,
        )
        self.assertIn("64-bit CPython", wrong_bitness or "")

        for profile in ("app", "app-dev", "package"):
            with self.subTest(profile=profile, windows_version=(10, 0, 17762)):
                old_windows = install_locked.support_error(
                    profile,
                    implementation="cpython",
                    python_version=(3, 11),
                    system="Windows",
                    machine="AMD64",
                    windows_version=(10, 0, 17762),
                )
                self.assertIn("build 17763", old_windows or "")
        for version in ((10, 0, 17763), (10, 0, 26100)):
            with self.subTest(windows_version=version):
                self.assertIsNone(
                    install_locked.support_error(
                        "app",
                        implementation="cpython",
                        python_version=(3, 11),
                        system="Windows",
                        machine="AMD64",
                        windows_version=version,
                    )
                )
        self.assertIsNone(
            install_locked.support_error(
                "runtime",
                implementation="cpython",
                python_version=(3, 11),
                system="Windows",
                machine="AMD64",
                windows_version=(6, 3, 9600),
            )
        )

    def test_every_admitted_platform_name_matches_the_lock_marker(self) -> None:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement

        requirement = next(
            Requirement(line.removesuffix("\\").rstrip())
            for line in (ROOT / install_locked.BUILD_LOCK).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith(("#", "--")) and not line[:1].isspace()
        )
        targets = (
            ("Linux", "x86_64", "linux"),
            ("Windows", "AMD64", "win32"),
            ("Darwin", "arm64", "darwin"),
            ("Darwin", "x86_64", "darwin"),
        )
        for system, machine, sys_platform in targets:
            with self.subTest(system=system, machine=machine):
                self.assertIsNone(
                    install_locked.support_error(
                        "runtime",
                        implementation="cpython",
                        python_version=(3, 11),
                        system=system,
                        machine=machine,
                        pointer_bits=64,
                        macos_version="13.0" if system == "Darwin" else None,
                    )
                )
                environment = default_environment()
                environment.update(
                    {
                        "implementation_name": "cpython",
                        "platform_machine": machine,
                        "python_full_version": "3.11.0",
                        "python_version": "3.11",
                        "sys_platform": sys_platform,
                    }
                )
                self.assertIsNotNone(requirement.marker)
                self.assertTrue(requirement.marker.evaluate(environment))

        if install_locked.support_error("runtime") is None:
            self.assertIn(platform.machine(), {target[1] for target in targets})

    def test_locked_files_resolve_to_exact_versions_for_this_platform(self) -> None:
        for profile in install_locked.PROFILE_LOCKS:
            with self.subTest(profile=profile):
                versions = install_locked._locked_versions(profile)
                self.assertIn("pip", versions)
                self.assertTrue(
                    all(version and "*" not in version for version in versions.values())
                )
        self.assertNotIn("uv", install_locked._locked_versions("package"))

    def test_locked_parser_does_not_import_third_party_marker_code(self) -> None:
        original_import = __import__

        def guarded_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "packaging" or name.startswith("packaging."):
                raise AssertionError("third-party packaging imported before RECORD trust")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            versions = install_locked._locked_versions("runtime")

        self.assertIn("packaging", versions)
        self.assertIn("mujoco", versions)

    def test_constrained_marker_evaluator_handles_python_and_platform_cells(self) -> None:
        marker = (
            "(python_full_version < '3.11' and implementation_name == 'cpython' "
            "and platform_machine == 'x86_64' and sys_platform == 'linux')"
        )
        environment = {
            "python_full_version": "3.10.14",
            "python_version": "3.10",
            "implementation_name": "cpython",
            "platform_machine": "x86_64",
            "sys_platform": "linux",
        }
        self.assertTrue(install_locked._marker_applies(marker, environment))
        environment["python_full_version"] = "3.11.0"
        environment["python_version"] = "3.11"
        self.assertFalse(install_locked._marker_applies(marker, environment))
        with self.assertRaisesRegex(install_locked.LockedInstallError, "Unsupported"):
            install_locked._marker_applies("os_name == 'posix'", environment)

    def test_constrained_markers_match_packaging_across_all_twelve_lock_cells(self) -> None:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement

        targets = (
            ("linux", "x86_64"),
            ("win32", "AMD64"),
            ("darwin", "arm64"),
            ("darwin", "x86_64"),
        )
        versions = ("3.10.14", "3.11.9", "3.12.13")
        markers: set[str] = set()
        for lock in install_locked.PROFILE_LOCKS.values():
            for line in (ROOT / lock).read_text(encoding="utf-8").splitlines():
                if not line or line[:1].isspace() or line.startswith(("#", "--")):
                    continue
                requirement_text = line.removesuffix("\\").rstrip()
                parsed = install_locked._LOCK_REQUIREMENT_RE.fullmatch(requirement_text)
                self.assertIsNotNone(parsed)
                marker = parsed.group("marker")
                if marker is not None:
                    markers.add(marker)

        for sys_platform, machine in targets:
            for full_version in versions:
                environment = default_environment()
                environment.update(
                    {
                        "implementation_name": "cpython",
                        "platform_machine": machine,
                        "platform_python_implementation": "CPython",
                        "python_full_version": full_version,
                        "python_version": ".".join(full_version.split(".")[:2]),
                        "sys_platform": sys_platform,
                    }
                )
                constrained_environment = {
                    key: environment[key]
                    for key in (
                        "python_full_version",
                        "python_version",
                        "implementation_name",
                        "platform_machine",
                        "platform_python_implementation",
                        "sys_platform",
                    )
                }
                for marker in markers:
                    with self.subTest(
                        sys_platform=sys_platform,
                        machine=machine,
                        full_version=full_version,
                        marker=marker,
                    ):
                        self.assertEqual(
                            install_locked._marker_applies(marker, constrained_environment),
                            Requirement(f"demo==1 ; {marker}").marker.evaluate(environment),
                        )

    def test_environment_lock_excludes_a_second_writer(self) -> None:
        first = install_locked._EnvironmentLock(timeout=0.1)
        second = install_locked._EnvironmentLock(timeout=0.01)
        with first:
            with self.assertRaisesRegex(install_locked.LockedInstallError, "Timed out"):
                second.__enter__()

    def test_environment_lock_path_uses_effective_temp_and_environment_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            environment = base / "environment"
            environment.mkdir()
            effective_temp = base / "effective-temp"
            effective_temp.mkdir()
            identity = os.path.normcase(str(environment.resolve()))
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

            with (
                patch.object(install_locked.sys, "prefix", os.fspath(environment)),
                patch.object(
                    install_locked.tempfile,
                    "gettempdir",
                    return_value=os.fspath(effective_temp),
                ),
            ):
                lock = install_locked._EnvironmentLock()

            self.assertEqual(lock.path, effective_temp / f"mclab-install-{digest}.lock")

    def test_environment_lock_persists_with_nul_marker_after_normal_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            environment = base / "environment"
            environment.mkdir()
            effective_temp = base / "effective-temp"
            effective_temp.mkdir()

            with (
                patch.object(install_locked.sys, "prefix", os.fspath(environment)),
                patch.object(
                    install_locked.tempfile,
                    "gettempdir",
                    return_value=os.fspath(effective_temp),
                ),
            ):
                lock = install_locked._EnvironmentLock()
                with lock:
                    pass

            self.assertTrue(lock.path.is_file())
            self.assertEqual(lock.path.read_bytes(), b"\0")

    def test_environment_lock_marks_existing_empty_file(self) -> None:
        lock = install_locked._EnvironmentLock()
        lock.path.write_bytes(b"")

        with lock:
            pass

        self.assertEqual(lock.path.read_bytes(), b"\0")

    def test_environment_lock_preserves_existing_nonempty_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            environment = base / "environment"
            environment.mkdir()
            effective_temp = base / "effective-temp"
            effective_temp.mkdir()

            with (
                patch.object(install_locked.sys, "prefix", os.fspath(environment)),
                patch.object(
                    install_locked.tempfile,
                    "gettempdir",
                    return_value=os.fspath(effective_temp),
                ),
            ):
                lock = install_locked._EnvironmentLock()
                original = b"pre-existing-marker\n"
                lock.path.write_bytes(original)
                with lock:
                    pass

            self.assertEqual(lock.path.read_bytes(), original)

    @unittest.skipIf(
        os.name == "nt" or not hasattr(os, "fchmod"),
        "POSIX descriptor permission narrowing is unavailable",
    )
    def test_environment_lock_narrows_legacy_permissions_without_truncating(self) -> None:
        lock = install_locked._EnvironmentLock()
        original = b"legacy-marker\n"
        lock.path.write_bytes(original)
        lock.path.chmod(0o666)

        with lock:
            self.assertEqual(lock.path.stat().st_mode & 0o077, 0)

        self.assertEqual(lock.path.read_bytes(), original)
        self.assertEqual(lock.path.stat().st_mode & 0o077, 0)

    def test_environment_lock_rejects_symlink_before_writing_without_nofollow(self) -> None:
        lock = install_locked._EnvironmentLock()
        foreign = Path(self._environment_lock_temp.name) / "foreign-target"
        foreign.write_bytes(b"")
        try:
            lock.path.symlink_to(foreign)
        except OSError as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")

        with (
            patch.object(install_locked.os, "O_NOFOLLOW", 0, create=True),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            with lock:
                self.fail("unsafe dependency lock path was acquired")

        self.assertEqual(foreign.read_bytes(), b"")

    def test_environment_lock_rejects_synthetic_windows_reparse_metadata(self) -> None:
        reparse_flag = 0x0400
        metadata = SimpleNamespace(
            st_dev=1,
            st_file_attributes=reparse_flag,
            st_ino=2,
            st_mode=stat.S_IFREG | 0o600,
            st_nlink=1,
            st_uid=0,
        )

        with (
            patch.object(
                install_locked.stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                reparse_flag,
                create=True,
            ),
            patch.object(install_locked.os, "fstat", return_value=metadata),
            patch.object(install_locked.os, "lstat", return_value=metadata),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            install_locked._validate_owned_environment_lock_file(
                123,
                Path("synthetic.lock"),
                phase="validate synthetic reparse",
            )

    def test_environment_lock_rejects_synthetic_windows_file_id_mismatch(self) -> None:
        opened = SimpleNamespace(
            st_dev=1,
            st_file_attributes=0,
            st_ino=2,
            st_mode=stat.S_IFREG | 0o600,
            st_nlink=1,
            st_uid=0,
        )
        attached = SimpleNamespace(
            st_dev=1,
            st_file_attributes=0,
            st_ino=3,
            st_mode=stat.S_IFREG | 0o600,
            st_nlink=1,
            st_uid=0,
        )

        with (
            patch.object(install_locked.os, "fstat", return_value=opened),
            patch.object(install_locked.os, "lstat", return_value=attached),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            install_locked._validate_owned_environment_lock_file(
                123,
                Path("synthetic.lock"),
                phase="validate synthetic identity",
            )

    @unittest.skipIf(
        os.name == "nt" or not hasattr(os, "fchmod"),
        "POSIX fallback permission regression",
    )
    def test_environment_lock_validates_swapped_identity_before_fchmod(self) -> None:
        lock = install_locked._EnvironmentLock()
        lock.path.write_bytes(b"")
        lock.path.chmod(0o600)
        foreign = Path(self._environment_lock_temp.name) / "foreign-target"
        foreign.write_bytes(b"")
        foreign.chmod(0o666)
        real_open = os.open
        calls = 0

        def swap_before_existing_open(
            path: str | os.PathLike[str],
            flags: int,
            mode: int = 0o777,
        ) -> int:
            nonlocal calls
            calls += 1
            if calls == 2:
                lock.path.unlink()
                lock.path.symlink_to(foreign)
            return real_open(path, flags, mode)

        with (
            patch.object(install_locked.os, "O_NOFOLLOW", 0, create=True),
            patch.object(
                install_locked.os,
                "open",
                side_effect=swap_before_existing_open,
            ),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            with lock:
                self.fail("swapped dependency lock path was acquired")

        self.assertEqual(foreign.read_bytes(), b"")
        self.assertEqual(foreign.stat().st_mode & 0o777, 0o666)

    def test_environment_lock_does_not_create_dangling_symlink_referent(self) -> None:
        lock = install_locked._EnvironmentLock()
        foreign = Path(self._environment_lock_temp.name) / "missing-foreign-target"
        try:
            lock.path.symlink_to(foreign)
        except OSError as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")

        with (
            patch.object(install_locked.os, "O_NOFOLLOW", 0, create=True),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            with lock:
                self.fail("unsafe dependency lock path was acquired")

        self.assertFalse(foreign.exists())

    def test_environment_lock_rejects_hardlink_before_writing(self) -> None:
        lock = install_locked._EnvironmentLock()
        foreign = Path(self._environment_lock_temp.name) / "foreign-target"
        foreign.write_bytes(b"")
        try:
            os.link(foreign, lock.path)
        except OSError as exc:
            self.skipTest(f"hard links are unavailable: {exc}")

        with self.assertRaisesRegex(
            install_locked.LockedInstallError,
            "private current-user physical file",
        ):
            with lock:
                self.fail("unsafe dependency lock path was acquired")

        self.assertEqual(foreign.read_bytes(), b"")

    def test_environment_lock_rejects_nonregular_path_before_writing(self) -> None:
        lock = install_locked._EnvironmentLock()
        lock.path.mkdir()

        with self.assertRaisesRegex(
            install_locked.LockedInstallError,
            "private current-user physical file",
        ):
            with lock:
                self.fail("nonregular dependency lock path was acquired")

    @unittest.skipUnless(hasattr(os, "geteuid"), "POSIX ownership metadata is unavailable")
    def test_environment_lock_rejects_foreign_owner_before_writing(self) -> None:
        lock = install_locked._EnvironmentLock()
        lock.path.write_bytes(b"")
        foreign_uid = os.geteuid() + 1

        with (
            patch.object(install_locked.os, "geteuid", return_value=foreign_uid),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "private current-user physical file",
            ),
        ):
            with lock:
                self.fail("foreign-owned dependency lock path was acquired")

        self.assertEqual(lock.path.read_bytes(), b"")

    def test_environment_lock_reports_noncontention_error_without_timeout(self) -> None:
        lock = install_locked._EnvironmentLock(timeout=60.0)

        with (
            patch.object(
                lock,
                "_lock_nonblocking",
                side_effect=OSError(errno.EIO, "fixture I/O failure"),
            ),
            self.assertRaisesRegex(
                install_locked.LockedInstallError,
                "Could not acquire dependency install lock",
            ),
        ):
            with lock:
                self.fail("non-contention failure was treated as an acquired lock")

        self.assertIsNone(lock._stream)

    @unittest.skipIf(os.name == "nt", "open lock files cannot be unlinked on Windows")
    def test_environment_lock_detects_stable_path_violation_on_release(self) -> None:
        first = install_locked._EnvironmentLock()

        with self.assertRaisesRegex(
            install_locked.LockedInstallError,
            "private current-user physical file",
        ):
            with first:
                assert first._stream is not None
                first_inode = os.fstat(first._stream.fileno()).st_ino
                first.path.unlink()
                second = install_locked._EnvironmentLock()
                with second:
                    assert second._stream is not None
                    second_inode = os.fstat(second._stream.fileno()).st_ino
                    self.assertNotEqual(first_inode, second_inode)

        self.assertIsNone(first._stream)

    def test_environment_lock_is_shared_across_worktrees_for_one_venv(self) -> None:
        first = install_locked._EnvironmentLock()
        with patch.object(install_locked, "ROOT", Path("/a/different/worktree")):
            second = install_locked._EnvironmentLock()

        self.assertEqual(first.path, second.path)

    def test_write_state_uses_atomic_sibling_and_records_private_path_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            state_file = root / ".venv" / ".mclab-lock-state.json"
            calls: list[tuple[str, str, Path]] = []
            real_mkstemp = tempfile.mkstemp

            def capture_mkstemp(
                *,
                prefix: str,
                suffix: str,
                dir: str | os.PathLike[str],
            ) -> tuple[int, str]:
                calls.append((prefix, suffix, Path(dir)))
                return real_mkstemp(prefix=prefix, suffix=suffix, dir=dir)

            inventory = [{"name": "example", "version": "1.0"}]
            integrity = {"example": {"sha256": "0" * 64}}
            with (
                patch.object(install_locked, "ROOT", root),
                patch.object(install_locked, "STATE_FILE", state_file),
                patch.object(
                    install_locked,
                    "_platform_fingerprint",
                    return_value={"system": "fixture"},
                ),
                patch.object(
                    install_locked,
                    "_state_inputs",
                    return_value={"runtime": {"sha256": "1" * 64}},
                ),
                patch.object(
                    install_locked.tempfile,
                    "mkstemp",
                    side_effect=capture_mkstemp,
                ),
            ):
                install_locked._write_state(
                    "runtime",
                    "runtime",
                    inventory,
                    integrity,
                )

            self.assertEqual(
                calls,
                [
                    (
                        "..mclab-lock-state.json.",
                        ".tmp",
                        state_file.parent,
                    )
                ],
            )
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], install_locked.STATE_SCHEMA)
            self.assertEqual(payload["project_root"], str(root.resolve()))
            self.assertEqual(payload["requested_profile"], "runtime")
            self.assertEqual(payload["effective_profile"], "runtime")
            self.assertEqual(
                payload["capabilities"],
                sorted(install_locked.PROFILE_CAPABILITIES["runtime"]),
            )
            self.assertEqual(payload["platform"], {"system": "fixture"})
            self.assertEqual(payload["inputs"], {"runtime": {"sha256": "1" * 64}})
            self.assertEqual(payload["inventory"], inventory)
            self.assertEqual(
                payload["inventory_sha256"],
                install_locked._inventory_hash(inventory),
            )
            self.assertEqual(payload["record_integrity"], integrity)
            self.assertFalse(list(state_file.parent.glob("..mclab-lock-state.json.*.tmp")))

    @staticmethod
    def _state(profile: str) -> dict[str, object]:
        return {
            "schema": install_locked.STATE_SCHEMA,
            "requested_profile": profile,
            "effective_profile": profile,
            "capabilities": sorted(install_locked.PROFILE_CAPABILITIES[profile]),
            "project_root": str(ROOT.resolve()),
            "platform": install_locked._platform_fingerprint(),
        }


class _NoOpLock:
    def __enter__(self) -> _NoOpLock:
        return self

    def __exit__(self, *args: object) -> None:
        return None
