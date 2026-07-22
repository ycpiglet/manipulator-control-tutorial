from __future__ import annotations

import importlib.util
import gzip
import json
import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_desktop.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("mclab_build_desktop_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build_module():
    return _load_build_module()


def _make_bundle(module, repository: Path, *, payload: bytes = b"payload\n") -> Path:
    bundle = repository / "dist" / module.BUNDLE_NAME
    bundle.mkdir(parents=True)
    executable = bundle / "MCLab"
    executable.write_bytes(payload)
    executable.chmod(0o755)
    (bundle / "data").mkdir()
    (bundle / "data" / "lesson.txt").write_bytes(b"lesson\n")
    (bundle / module.UNSIGNED_MARKER_NAME).write_bytes(module.UNSIGNED_MARKER_BYTES)
    return bundle


def _provenance(module, system_name: str = "Linux") -> dict[str, object]:
    distributions = [
        {"name": "mujoco-manipulator-control-lab", "version": "0.1.0"},
        {"name": "pyinstaller", "version": "6.0.0"},
    ]
    machine = "AMD64" if system_name == "Windows" else "x86_64"
    return {
        "build_command": list(module._RECORDED_BUILD_COMMAND),
        "package_environment": {
            "distribution_count": len(distributions),
            "distributions": distributions,
            "inputs": {path: "c" * 64 for path in module._PACKAGE_INPUT_PATHS},
            "inventory_sha256": module._inventory_sha256(distributions),
            "profile": "package",
            "record_integrity": {"files": 2, "sha256": "d" * 64},
            "scope": module._PACKAGE_ENVIRONMENT_SCOPE,
        },
        "platform": {"machine": machine, "release": "test-release", "system": system_name},
        "pyinstaller_version": "6.0.0",
        "python": {
            "implementation": "CPython",
            "pointer_bits": 64,
            "version": "3.10.0",
            "zlib_runtime_version": "1.2.13",
        },
        "source_commit": "a" * 40,
        "source_dirty": False,
        "spec_path": "packaging/mclab.spec",
        "spec_sha256": "b" * 64,
    }


def _finalize(
    module,
    repository: Path,
    bundle: Path,
    *,
    enforce_size_gate: bool = True,
) -> Path:
    with (
        patch.object(module, "ROOT", repository),
        patch.object(module.platform, "system", return_value="Linux"),
        patch.object(
            module, "_source_provenance", side_effect=lambda system: _provenance(module, system)
        ),
    ):
        return module._finalize_package(bundle, enforce_size_gate=enforce_size_gate)


def _load_evidence(module, package: Path) -> dict[str, object]:
    return json.loads((package / module.EVIDENCE_NAME).read_text(encoding="utf-8"))


def _verify(module, bundle: Path, package: Path, **kwargs):
    with (
        patch.object(module.platform, "system", return_value="Linux"),
        patch.object(module, "_source_provenance", return_value=_provenance(module)),
    ):
        return module.verify_package(bundle, package, **kwargs)


def test_size_limits_are_exact_binary_mib_and_independent(build_module) -> None:
    assert build_module.ONE_FOLDER_LIMIT_BYTES == 400 * 1024 * 1024
    assert build_module.ARCHIVE_LIMIT_BYTES == 300 * 1024 * 1024


def test_archive_names_are_architecture_specific_and_normalized(build_module) -> None:
    arm = build_module._archive_name("Darwin", "arm64")
    intel = build_module._archive_name("Darwin", "x86_64")

    assert arm == "MCLab-macos-arm64-unsigned-development.tar.gz"
    assert intel == "MCLab-macos-x86_64-unsigned-development.tar.gz"
    assert arm != intel
    assert (
        build_module._archive_name("Windows", "AMD64")
        == "MCLab-windows-x86_64-unsigned-development.tar.gz"
    )
    with pytest.raises(build_module.PackageValidationError, match="architecture"):
        build_module._archive_name("Linux", "unsupported-test-architecture")
    with pytest.raises(build_module.PackageValidationError, match="platform/architecture"):
        build_module._archive_name("Linux", "arm64")
    with pytest.raises(build_module.PackageValidationError, match="platform/architecture"):
        build_module._archive_name("Windows", "ARM64")


@pytest.mark.parametrize(
    ("name", "limit", "limit_mib"),
    [("one-folder", 400 * 1024 * 1024, 400), ("compressed archive", 300 * 1024 * 1024, 300)],
)
def test_size_gate_accepts_exact_boundary_and_rejects_next_byte(
    build_module, name: str, limit: int, limit_mib: int
) -> None:
    build_module._check_size_gate(name, limit, limit, enforced=True)
    with pytest.raises(
        build_module.PackageValidationError,
        match=rf"exceeds {limit_mib} MiB: {limit + 1} bytes",
    ):
        build_module._check_size_gate(name, limit + 1, limit, enforced=True)


def test_build_preflight_and_marker_run_before_package_inventory(
    build_module, tmp_path: Path
) -> None:
    events: list[str] = []
    previous_package = tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME
    previous_package.mkdir(parents=True)
    (previous_package / "stale.txt").write_bytes(b"stale evidence")
    previous_build = tmp_path / "build"
    previous_build.mkdir()
    (previous_build / "stale.txt").write_bytes(b"stale build")
    previous_bundle = tmp_path / "dist" / build_module.BUNDLE_NAME
    previous_bundle.mkdir()
    (previous_bundle / "stale.txt").write_bytes(b"stale bundle")

    def fake_pyinstaller(*args, **kwargs) -> None:
        assert not previous_package.exists()
        assert not previous_build.exists()
        assert not previous_bundle.exists()
        events.append("pyinstaller")
        bundle = tmp_path / "dist" / build_module.BUNDLE_NAME
        bundle.mkdir(parents=True)
        (bundle / "MCLab").write_bytes(b"app")

    def fake_finalize(bundle: Path, *, enforce_size_gate: bool) -> Path:
        assert enforce_size_gate is False
        assert (bundle / build_module.UNSIGNED_MARKER_NAME).read_bytes() == (
            build_module.UNSIGNED_MARKER_BYTES
        )
        events.append("inventory")
        return tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(
            build_module,
            "_verify_panda_assets",
            side_effect=lambda: events.append("verify"),
        ),
        patch.object(build_module.subprocess, "run", side_effect=fake_pyinstaller),
        patch.object(build_module, "_finalize_package", side_effect=fake_finalize),
        patch.object(sys, "argv", ["build_desktop.py", "--skip-size-gate"]),
    ):
        assert build_module.main() == 0

    assert events == ["verify", "pyinstaller", "inventory"]
    assert "--noconfirm" not in build_module._PYINSTALLER_COMMAND
    assert "--clean" in build_module._PYINSTALLER_COMMAND


def test_build_preflight_blocks_pyinstaller_on_invalid_assets(build_module, tmp_path: Path) -> None:
    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(
            build_module,
            "_verify_panda_assets",
            side_effect=RuntimeError("invalid Panda assets"),
        ),
        patch.object(build_module.subprocess, "run") as pyinstaller,
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(RuntimeError, match="invalid Panda assets"),
    ):
        build_module.main()

    pyinstaller.assert_not_called()


def test_failed_rebuild_cannot_leave_previous_package_evidence_canonical(
    build_module, tmp_path: Path
) -> None:
    previous_package = tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME
    previous_package.mkdir(parents=True)
    (previous_package / "stale.txt").write_bytes(b"stale evidence")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets"),
        patch.object(
            build_module.subprocess,
            "run",
            side_effect=RuntimeError("pyinstaller failed"),
        ),
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(RuntimeError, match="pyinstaller failed"),
    ):
        build_module.main()

    assert not previous_package.exists()


def test_build_preflight_reports_force_repair_guidance(build_module, tmp_path: Path) -> None:
    panda_root = tmp_path / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
    panda_root.mkdir(parents=True)

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch(
            "mclab.application.assets.verify_assets",
            side_effect=ValueError("tampered scene.xml"),
        ),
        pytest.raises(RuntimeError, match="assets install --force"),
    ):
        build_module._verify_panda_assets()


def test_build_preflight_reports_non_force_guidance_for_missing_tree(
    build_module, tmp_path: Path
) -> None:
    from mclab.application.assets import AssetVerificationError

    panda_root = tmp_path / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
    failure = AssetVerificationError(panda_root, ["runtime tree is missing"])

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch("mclab.application.assets.verify_assets", side_effect=failure),
        pytest.raises(RuntimeError) as raised,
    ):
        build_module._verify_panda_assets()

    assert "assets install`" in str(raised.value)
    assert "--force" not in str(raised.value)


def test_inventory_is_sorted_deterministic_and_identity_covers_marker(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    (bundle / "z.txt").write_bytes(b"z")
    (bundle / "a.txt").write_bytes(b"a")

    first_inventory, first_identity = build_module._inventory_bundle(bundle)
    second_inventory, second_identity = build_module._inventory_bundle(bundle)

    assert first_inventory == second_inventory
    assert first_identity == second_identity
    members = first_inventory["members"]
    assert [member["path"] for member in members] == sorted(member["path"] for member in members)
    marker = next(
        member for member in members if member["path"] == build_module.UNSIGNED_MARKER_NAME
    )
    assert (
        marker["sha256"]
        == build_module.hashlib.sha256(build_module.UNSIGNED_MARKER_BYTES).hexdigest()
    )
    assert first_inventory["one_folder_bytes"] == sum(
        path.stat().st_size for path in bundle.rglob("*") if path.is_file()
    )


def test_archive_is_byte_deterministic_and_has_normalized_metadata(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    inventory, _ = build_module._inventory_bundle(bundle)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    build_module._write_deterministic_archive(bundle, inventory, first)
    build_module._write_deterministic_archive(bundle, inventory, second)

    assert first.read_bytes() == second.read_bytes()
    build_module._verify_archive(first, inventory)
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
    assert members[0].name == build_module.BUNDLE_NAME
    assert all(member.mtime == 0 and member.uid == 0 and member.gid == 0 for member in members)


def test_finalize_records_distinct_measured_sizes_identity_and_unsigned_status(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path, payload=b"0" * (1024 * 1024))
    package = _finalize(build_module, tmp_path, bundle)
    evidence = _load_evidence(build_module, package)

    one_folder = evidence["gates"]["one_folder"]
    archive = evidence["gates"]["archive"]
    assert one_folder["limit_bytes"] == 400 * 1024 * 1024
    assert archive["limit_bytes"] == 300 * 1024 * 1024
    assert archive["measured_bytes"] < one_folder["measured_bytes"]
    assert one_folder["passed"] is True and archive["passed"] is True
    assert evidence["artifact_class"] == "unsigned-development"
    assert evidence["unsigned_marker"]["path"] == build_module.UNSIGNED_MARKER_NAME
    assert len(evidence["package_identity"]["value"]) == 64
    assert {path.name for path in package.iterdir()} == {
        build_module.EVIDENCE_NAME,
        "MCLab-linux-x86_64-unsigned-development.tar.gz",
    }
    _verify(build_module, bundle, package)


def test_skipped_gate_is_explicit_in_evidence(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle, enforce_size_gate=False)
    evidence = _load_evidence(build_module, package)

    assert evidence["gates"]["one_folder"]["enforced"] is False
    assert evidence["gates"]["archive"]["enforced"] is False
    with pytest.raises(build_module.PackageValidationError, match="were not enforced"):
        _verify(build_module, bundle, package)
    _verify(build_module, bundle, package, require_size_gates=False)


def test_finalize_rejects_dirty_source_for_checkout_bound_evidence(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    dirty = _provenance(build_module)
    dirty["source_dirty"] = True

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module.platform, "system", return_value="Linux"),
        patch.object(build_module, "_source_provenance", return_value=dirty),
        pytest.raises(build_module.PackageValidationError, match="clean recorded source tree"),
    ):
        build_module._finalize_package(bundle, enforce_size_gate=True)

    assert not (tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME).exists()
    assert not list((tmp_path / "dist").glob(".MCLab-package.stage-*"))


def test_verification_only_is_read_only_and_skips_build_preflight(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    observed = [
        bundle / build_module.UNSIGNED_MARKER_NAME,
        bundle / "MCLab",
        package / build_module.EVIDENCE_NAME,
        next(path for path in package.iterdir() if path.name.endswith(".tar.gz")),
    ]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in observed}

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets") as preflight,
        patch.object(build_module.platform, "system", return_value="Linux"),
        patch.object(
            build_module,
            "_source_provenance",
            return_value=_provenance(build_module),
        ),
        patch.object(build_module.subprocess, "run") as command,
        patch.object(sys, "argv", ["build_desktop.py", "--verify-only"]),
    ):
        assert build_module.main() == 0

    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in observed} == before
    preflight.assert_not_called()
    command.assert_not_called()


def test_verification_detects_bundle_tamper_without_repairing_it(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    marker = bundle / build_module.UNSIGNED_MARKER_NAME
    marker.write_bytes(b"tampered unsigned marker\n")
    evidence_before = (package / build_module.EVIDENCE_NAME).read_bytes()
    archive = next(path for path in package.iterdir() if path.name.endswith(".tar.gz"))
    archive_before = archive.read_bytes()

    with pytest.raises(build_module.PackageValidationError, match="inventory"):
        _verify(build_module, bundle, package)

    assert marker.read_bytes() == b"tampered unsigned marker\n"
    assert (package / build_module.EVIDENCE_NAME).read_bytes() == evidence_before
    assert archive.read_bytes() == archive_before


def test_verification_detects_archive_tamper_without_rewriting_archive(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    archive = next(path for path in package.iterdir() if path.name.endswith(".tar.gz"))
    archive.write_bytes(archive.read_bytes() + b"tamper")
    tampered = archive.read_bytes()

    with pytest.raises(build_module.PackageValidationError, match="archive identity"):
        _verify(build_module, bundle, package)

    assert archive.read_bytes() == tampered


def test_verification_rejects_noncanonical_gzip_with_matching_semantic_tar_and_evidence(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    archive = next(path for path in package.iterdir() if path.name.endswith(".tar.gz"))
    tar_payload = gzip.decompress(archive.read_bytes())
    with archive.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=1,
            fileobj=raw,
            mtime=7,
        ) as compressed:
            compressed.write(tar_payload)
    evidence_path = package / build_module.EVIDENCE_NAME
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    archive_bytes = archive.read_bytes()
    archive_size = len(archive_bytes)
    evidence["archive"]["sha256"] = build_module.hashlib.sha256(archive_bytes).hexdigest()
    evidence["archive"]["size_bytes"] = archive_size
    evidence["gates"]["archive"]["measured_bytes"] = archive_size
    evidence_path.write_bytes(build_module._canonical_json_bytes(evidence))

    with pytest.raises(build_module.PackageValidationError, match="canonical"):
        _verify(build_module, bundle, package)


@pytest.mark.parametrize("suffix", [b"trailing-data", gzip.compress(b"", mtime=0)])
def test_verification_rejects_noncanonical_archive_suffix_even_when_evidence_matches(
    build_module, tmp_path: Path, suffix: bytes
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    archive = next(path for path in package.iterdir() if path.name.endswith(".tar.gz"))
    archive.write_bytes(archive.read_bytes() + suffix)
    evidence_path = package / build_module.EVIDENCE_NAME
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    archive_bytes = archive.read_bytes()
    archive_size = len(archive_bytes)
    evidence["archive"]["sha256"] = build_module.hashlib.sha256(archive_bytes).hexdigest()
    evidence["archive"]["size_bytes"] = archive_size
    evidence["gates"]["archive"]["measured_bytes"] = archive_size
    evidence_path.write_bytes(build_module._canonical_json_bytes(evidence))

    with pytest.raises(build_module.PackageValidationError):
        _verify(build_module, bundle, package)


def test_verification_rejects_canonical_evidence_tamper_without_rewriting_it(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    evidence_path = package / build_module.EVIDENCE_NAME
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["package_identity"]["value"] = "0" * 64
    evidence_path.write_bytes(build_module._canonical_json_bytes(payload))
    tampered = evidence_path.read_bytes()

    with pytest.raises(build_module.PackageValidationError, match="identity"):
        _verify(build_module, bundle, package)

    assert evidence_path.read_bytes() == tampered


def test_checkout_bound_verification_rejects_valid_provenance_tamper(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    evidence_path = package / build_module.EVIDENCE_NAME
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["source"]["source_commit"] = "c" * 40
    payload["source"]["spec_sha256"] = "d" * 64
    evidence_path.write_bytes(build_module._canonical_json_bytes(payload))

    with pytest.raises(build_module.PackageValidationError, match="provenance"):
        _verify(build_module, bundle, package)


@pytest.mark.parametrize(
    ("system_name", "machine"),
    [("Linux", "arm64"), ("Windows", "ARM64")],
)
def test_source_record_rejects_unreviewed_platform_pair(
    build_module, system_name: str, machine: str
) -> None:
    source = _provenance(build_module, system_name)
    source["platform"]["machine"] = machine

    with pytest.raises(build_module.PackageValidationError, match="platform/architecture"):
        build_module._validate_source_record(source)


@pytest.mark.parametrize("invalid_count", [True, 2.0, -1])
def test_source_record_requires_exact_package_environment_inventory(
    build_module, invalid_count: object
) -> None:
    source = _provenance(build_module)
    source["package_environment"]["distribution_count"] = invalid_count

    with pytest.raises(build_module.PackageValidationError, match="distribution count"):
        build_module._validate_source_record(source)


def test_source_record_binds_lock_inputs_and_pyinstaller_inventory(build_module) -> None:
    source = _provenance(build_module)
    assert build_module._validate_source_record(source) is source

    source["package_environment"]["inputs"].pop("requirements/locks/package.txt")
    with pytest.raises(build_module.PackageValidationError, match="input set"):
        build_module._validate_source_record(source)

    source = _provenance(build_module)
    source["pyinstaller_version"] = "6.0.1"
    with pytest.raises(build_module.PackageValidationError, match="PyInstaller version"):
        build_module._validate_source_record(source)


def test_package_environment_record_invokes_locked_profile_and_record_validation(
    build_module, tmp_path: Path
) -> None:
    from scripts import install_locked

    inventory = [
        {"name": "mujoco-manipulator-control-lab", "version": "0.1.0"},
        {"name": "pyinstaller", "version": "6.0.0"},
    ]
    inputs = {path: "a" * 64 for path in build_module._PACKAGE_INPUT_PATHS}
    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(install_locked, "ROOT", tmp_path),
        patch.object(install_locked, "support_error", return_value=None) as support,
        patch.object(install_locked, "_distribution_inventory", return_value=inventory),
        patch.object(install_locked, "_locked_version_errors", return_value=[]) as versions,
        patch.object(
            install_locked,
            "_unexpected_distribution_errors",
            return_value=[],
        ) as unexpected,
        patch.object(
            install_locked,
            "_record_integrity",
            return_value=({"files": 2, "sha256": "b" * 64}, []),
        ) as record,
        patch.object(install_locked, "_editable_error", return_value=None) as editable,
        patch.object(install_locked, "_state_inputs", return_value=inputs) as state_inputs,
    ):
        result = build_module._package_environment_record()

    assert result["inventory_sha256"] == build_module._inventory_sha256(inventory)
    assert result["inputs"] == inputs
    support.assert_called_once_with("package")
    versions.assert_called_once_with("package", inventory)
    unexpected.assert_called_once_with("package", inventory)
    record.assert_called_once_with("package")
    editable.assert_called_once_with()
    state_inputs.assert_called_once_with("package")


def test_offline_self_asserted_verification_is_unmistakably_non_gating(
    build_module, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    evidence_path = package / build_module.EVIDENCE_NAME
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["source"]["source_commit"] = "c" * 40
    evidence_path.write_bytes(build_module._canonical_json_bytes(payload))

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(
            build_module,
            "_source_provenance",
            side_effect=AssertionError("offline mode must not claim checkout provenance"),
        ),
        patch.object(sys, "argv", ["build_desktop.py", "--verify-only", "--offline-self-asserted"]),
    ):
        assert build_module.main() == 0

    output = capsys.readouterr().out
    assert "NON-GATING OFFLINE CHECK ONLY" in output
    assert "source provenance is self-asserted" in output
    assert "Verified checkout-bound" not in output


def test_evidence_reader_rejects_noncanonical_json_and_duplicate_keys(
    build_module, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{\n  "schema": "x"\n}\n', encoding="utf-8")
    with pytest.raises(build_module.PackageValidationError, match="not canonical"):
        build_module._read_evidence(evidence)

    evidence.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
    with pytest.raises(build_module.PackageValidationError, match="Duplicate key"):
        build_module._read_evidence(evidence)

    evidence.write_text('{"measurement":NaN}\n', encoding="utf-8")
    with pytest.raises(build_module.PackageValidationError, match="Non-finite"):
        build_module._read_evidence(evidence)


@pytest.mark.parametrize(
    "payload",
    [
        b"[" * 1200 + b"0" + b"]" * 1200,
        b'{"value":' + b"9" * 100_000 + b"}\n",
    ],
)
def test_evidence_reader_bounds_deep_or_oversized_integer_json(
    build_module, tmp_path: Path, payload: bytes
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(payload)

    with pytest.raises(build_module.PackageValidationError, match="Invalid package evidence"):
        build_module._read_evidence(evidence)


def test_verification_rejects_numeric_type_substitution_in_evidence(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    package = _finalize(build_module, tmp_path, bundle)
    evidence_path = package / build_module.EVIDENCE_NAME
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["gates"]["one_folder"]["measured_bytes"] = float(
        payload["gates"]["one_folder"]["measured_bytes"]
    )
    evidence_path.write_bytes(build_module._canonical_json_bytes(payload))

    with pytest.raises(build_module.PackageValidationError, match="exact integers"):
        _verify(build_module, bundle, package)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_safe_internal_symlink_is_inventoried_and_preserved(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.symlink("data/lesson.txt", bundle / "lesson-link")

    inventory, _ = build_module._inventory_bundle(bundle)
    link = next(member for member in inventory["members"] if member["path"] == "lesson-link")
    assert link["type"] == "symlink"
    assert link["target"] == "data/lesson.txt"
    archive = tmp_path / "links.tar.gz"
    build_module._write_deterministic_archive(bundle, inventory, archive)
    build_module._verify_archive(archive, inventory)
    with tarfile.open(archive, "r:gz") as package:
        archived_link = package.getmember("MCLab/lesson-link")
    assert archived_link.issym() and archived_link.linkname == "data/lesson.txt"


def test_long_archive_path_has_only_deterministic_pax_metadata(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    long_directory = bundle / ("d" * 90)
    long_directory.mkdir()
    (long_directory / ("f" * 80)).write_bytes(b"long path")
    inventory, _ = build_module._inventory_bundle(bundle)
    archive = tmp_path / "long-path.tar.gz"

    build_module._write_deterministic_archive(bundle, inventory, archive)
    build_module._verify_archive(archive, inventory)

    with tarfile.open(archive, "r:gz") as package:
        long_member = package.getmember(f"MCLab/{'d' * 90}/{'f' * 80}")
    assert set(long_member.pax_headers) <= {"path"}


def test_archive_verifier_rejects_redundant_pax_metadata(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    inventory, _ = build_module._inventory_bundle(bundle)
    archive_path = tmp_path / "redundant-pax.tar.gz"
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
                pax_headers={"comment": "redundant"},
            ) as archive:
                archive.addfile(
                    build_module._tar_info(
                        build_module.BUNDLE_NAME,
                        mode=0o755,
                        member_type=tarfile.DIRTYPE,
                    )
                )

    with pytest.raises(build_module.PackageValidationError, match="unexpected PAX"):
        build_module._verify_archive(archive_path, inventory)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
@pytest.mark.parametrize(
    "target",
    ["../../outside", "missing.txt", "missing/../data/lesson.txt", "/absolute/path"],
)
def test_unsafe_or_broken_symlink_fails_closed(build_module, tmp_path: Path, target: str) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.symlink(target, bundle / "unsafe-link")

    with pytest.raises(build_module.PackageValidationError, match="Symlink|symlink"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_componentwise_symlink_resolution_rejects_intermediate_link_escape(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    (bundle / "a").mkdir()
    (bundle / "dir").mkdir()
    (bundle / "outside").write_bytes(b"internal decoy")
    external = bundle.parent / "outside"
    external.write_bytes(b"external target")
    os.symlink("../dir", bundle / "a" / "inside")
    os.symlink("a/inside/../../outside", bundle / "escape")
    assert (bundle / "escape").resolve(strict=True) == external.resolve(strict=True)

    with pytest.raises(build_module.PackageValidationError, match="escapes the bundle"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_componentwise_symlink_resolution_rejects_non_directory_traversal(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.symlink("data/lesson.txt/../lesson.txt", bundle / "invalid-traversal")

    with pytest.raises(build_module.PackageValidationError, match="non-directory"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_componentwise_symlink_resolution_rejects_cycles(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.symlink("cycle-b", bundle / "cycle-a")
    os.symlink("cycle-a", bundle / "cycle-b")

    with pytest.raises(build_module.PackageValidationError, match="cycle"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_componentwise_symlink_resolution_has_a_hard_expansion_bound(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    link_count = build_module.MAX_SYMLINK_EXPANSIONS + 2
    for index in range(link_count):
        target = f"chain-{index + 1}" if index + 1 < link_count else "data/lesson.txt"
        os.symlink(target, bundle / f"chain-{index}")

    with pytest.raises(build_module.PackageValidationError, match="expansion safety bound"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="hardlink semantics differ on Windows CI")
def test_hardlinked_regular_file_fails_closed(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.link(bundle / "data" / "lesson.txt", bundle / "lesson-hardlink")

    with pytest.raises(build_module.PackageValidationError, match="Hard-linked"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is POSIX-only")
def test_special_file_fails_closed(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    os.mkfifo(bundle / "unsafe-fifo")

    with pytest.raises(build_module.PackageValidationError, match="Special files"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="colon is not a legal Windows filename")
def test_cross_platform_unsafe_member_name_fails_closed(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    (bundle / "drive:name").write_bytes(b"unsafe")

    with pytest.raises(build_module.PackageValidationError, match="Unsafe package path"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="surrogateescape filename fixture is POSIX-only")
def test_undecodable_member_name_fails_closed(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    bad_path = os.fsencode(bundle) + b"/bad-\xff"
    descriptor = os.open(bad_path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        os.write(descriptor, b"unsafe")
    finally:
        os.close(descriptor)

    with pytest.raises(build_module.PackageValidationError, match="Undecodable"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="case-distinct fixtures are not portable on Windows")
def test_case_colliding_member_names_fail_closed(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    (bundle / "Case.txt").write_bytes(b"upper")
    (bundle / "case.txt").write_bytes(b"lower")

    with pytest.raises(build_module.PackageValidationError, match="collide"):
        build_module._inventory_bundle(bundle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_linked_bundle_root_fails_closed(build_module, tmp_path: Path) -> None:
    real_bundle = _make_bundle(build_module, tmp_path / "real")
    linked_bundle = tmp_path / "linked-bundle"
    os.symlink(real_bundle, linked_bundle)

    with pytest.raises(build_module.PackageValidationError, match="link or reparse"):
        build_module._inventory_bundle(linked_bundle)


def test_inventory_rejects_nested_same_device_mount_boundary(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    mounted = bundle / "mounted"
    mounted.mkdir()
    (mounted / "external.txt").write_bytes(b"must not be archived")

    with (
        patch.object(
            build_module,
            "_linux_mount_points",
            return_value=frozenset({build_module._absolute_path(mounted)}),
        ),
        pytest.raises(build_module.PackageValidationError, match="mount boundary"),
    ):
        build_module._inventory_bundle(bundle)


def test_filesystem_identity_check_rejects_cross_device_member(
    build_module, tmp_path: Path
) -> None:
    path = tmp_path / "member"
    path.write_bytes(b"content")
    metadata = path.lstat()
    different_device = type(
        "Metadata",
        (),
        {"st_dev": metadata.st_dev + 1},
    )()

    with pytest.raises(build_module.PackageValidationError, match="filesystem or mount"):
        build_module._assert_same_filesystem_member(
            path,
            different_device,
            boundary_device=metadata.st_dev,
            mount_points=frozenset(),
            label="test member",
        )


def test_one_folder_gate_failure_prevents_archive_work(build_module, tmp_path: Path) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "ONE_FOLDER_LIMIT_BYTES", 1),
        patch.object(build_module, "_write_deterministic_archive") as archive_writer,
        pytest.raises(build_module.PackageValidationError, match="one-folder exceeds"),
    ):
        build_module._finalize_package(bundle, enforce_size_gate=True)

    archive_writer.assert_not_called()
    assert not (tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME).exists()


def test_archive_failure_cleans_owned_stage_and_preserves_previous_package(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    previous = tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME
    previous.mkdir()
    (previous / "previous.txt").write_bytes(b"preserve me")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module.platform, "system", return_value="Linux"),
        patch.object(
            build_module,
            "_source_provenance",
            return_value=_provenance(build_module),
        ),
        patch.object(
            build_module,
            "_write_deterministic_archive",
            side_effect=OSError("archive fault"),
        ),
        pytest.raises(OSError, match="archive fault"),
    ):
        build_module._finalize_package(bundle, enforce_size_gate=True)

    assert (previous / "previous.txt").read_bytes() == b"preserve me"
    assert not list((tmp_path / "dist").glob(".MCLab-package.stage-*"))


def test_archive_gate_failure_cleans_stage_and_preserves_previous_package(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    previous = tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME
    previous.mkdir()
    (previous / "previous.txt").write_bytes(b"preserve me")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "ARCHIVE_LIMIT_BYTES", 1),
        patch.object(build_module.platform, "system", return_value="Linux"),
        patch.object(
            build_module,
            "_source_provenance",
            return_value=_provenance(build_module),
        ),
        pytest.raises(build_module.PackageValidationError, match="compressed archive exceeds"),
    ):
        build_module._finalize_package(bundle, enforce_size_gate=True)

    assert (previous / "previous.txt").read_bytes() == b"preserve me"
    assert not list((tmp_path / "dist").glob(".MCLab-package.stage-*"))


def test_atomic_publish_restores_previous_directory_when_rename_fails(
    build_module, tmp_path: Path
) -> None:
    destination = tmp_path / build_module.PACKAGE_DIRECTORY_NAME
    destination.mkdir()
    (destination / "previous.txt").write_bytes(b"previous")
    stage = tmp_path / ".MCLab-package.stage-test"
    stage.mkdir()
    (stage / "new.txt").write_bytes(b"new")
    real_replace = os.replace

    def injected_replace(source, target) -> None:
        if Path(source) == stage and Path(target) == destination:
            raise OSError("publish rename fault")
        real_replace(source, target)

    with (
        patch.object(build_module.os, "replace", side_effect=injected_replace),
        pytest.raises(OSError, match="publish rename fault"),
    ):
        build_module._publish_staged_directory(stage, destination)

    assert (destination / "previous.txt").read_bytes() == b"previous"
    assert (stage / "new.txt").read_bytes() == b"new"
    assert not list(tmp_path.glob(".MCLab-package.backup-*"))


def test_main_finalization_failure_restores_preexisting_marker(
    build_module, tmp_path: Path
) -> None:
    original_marker = b"previous marker\n"

    def fake_pyinstaller(*args, **kwargs) -> None:
        bundle = tmp_path / "dist" / build_module.BUNDLE_NAME
        bundle.mkdir(parents=True)
        (bundle / "MCLab").write_bytes(b"app")
        (bundle / build_module.UNSIGNED_MARKER_NAME).write_bytes(original_marker)

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets"),
        patch.object(build_module.subprocess, "run", side_effect=fake_pyinstaller),
        patch.object(
            build_module,
            "_finalize_package",
            side_effect=RuntimeError("finalization fault"),
        ),
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(RuntimeError, match="finalization fault"),
    ):
        build_module.main()

    marker = tmp_path / "dist" / build_module.BUNDLE_NAME / build_module.UNSIGNED_MARKER_NAME
    assert marker.read_bytes() == original_marker


def test_main_finalization_failure_removes_new_marker(build_module, tmp_path: Path) -> None:
    def fake_pyinstaller(*args, **kwargs) -> None:
        bundle = tmp_path / "dist" / build_module.BUNDLE_NAME
        bundle.mkdir(parents=True)
        (bundle / "MCLab").write_bytes(b"app")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets"),
        patch.object(build_module.subprocess, "run", side_effect=fake_pyinstaller),
        patch.object(
            build_module,
            "_finalize_package",
            side_effect=RuntimeError("finalization fault"),
        ),
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(RuntimeError, match="finalization fault"),
    ):
        build_module.main()

    marker = tmp_path / "dist" / build_module.BUNDLE_NAME / build_module.UNSIGNED_MARKER_NAME
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_clean_rejects_linked_owned_target(build_module, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    os.symlink(outside, tmp_path / "build")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        pytest.raises(build_module.PackageValidationError, match=r"Refusing to clean.*unsafe"),
    ):
        build_module._clean_build_outputs()

    assert (outside / "keep.txt").read_bytes() == b"keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_clean_rejects_linked_dist_ancestor_before_any_deletion(
    build_module, tmp_path: Path
) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "preserve-build.txt").write_bytes(b"preserve build")
    outside = tmp_path / "outside"
    victim = outside / build_module.BUNDLE_NAME
    victim.mkdir(parents=True)
    keep = victim / "keep.txt"
    keep.write_bytes(b"must survive")
    os.symlink(outside, tmp_path / "dist")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        pytest.raises(build_module.PackageValidationError, match=r"Refusing to clean.*unsafe"),
    ):
        build_module._clean_build_outputs()

    assert keep.read_bytes() == b"must survive"
    assert (build / "preserve-build.txt").read_bytes() == b"preserve build"


def test_clean_directory_chain_uses_windows_reparse_flag_abstraction(
    build_module, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    bundle = dist / build_module.BUNDLE_NAME
    bundle.mkdir(parents=True)
    keep = bundle / "keep.txt"
    keep.write_bytes(b"must survive")
    dist_identity = (dist.stat().st_dev, dist.stat().st_ino)
    real_is_reparse = build_module._is_reparse_point

    def simulated_windows_reparse(metadata) -> bool:
        if (metadata.st_dev, metadata.st_ino) == dist_identity:
            return True
        return real_is_reparse(metadata)

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(
            build_module,
            "_is_reparse_point",
            side_effect=simulated_windows_reparse,
        ),
        pytest.raises(build_module.PackageValidationError, match=r"Refusing to clean.*unsafe"),
    ):
        build_module._clean_build_outputs()

    assert keep.read_bytes() == b"must survive"


def test_nested_mount_preflight_blocks_all_deletion_and_pyinstaller(
    build_module, tmp_path: Path
) -> None:
    build = tmp_path / "build"
    mounted = build / "mounted"
    mounted.mkdir(parents=True)
    canary = mounted / "external-canary.txt"
    canary.write_bytes(b"preserve")
    package = tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME
    package.mkdir(parents=True)
    package_canary = package / "previous.txt"
    package_canary.write_bytes(b"preserve package")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets"),
        patch.object(
            build_module,
            "_linux_mount_points",
            return_value=frozenset({build_module._absolute_path(mounted)}),
        ),
        patch.object(build_module.subprocess, "run") as pyinstaller,
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(build_module.PackageValidationError, match="Refusing to clean unsafe"),
    ):
        build_module.main()

    pyinstaller.assert_not_called()
    assert canary.read_bytes() == b"preserve"
    assert package_canary.read_bytes() == b"preserve package"


def test_stale_transaction_state_blocks_build_and_verify_without_mutation(
    build_module, tmp_path: Path
) -> None:
    bundle = _make_bundle(build_module, tmp_path)
    stale = tmp_path / "dist" / f".{build_module.PACKAGE_DIRECTORY_NAME}.backup-crash"
    stale.mkdir()
    canary = stale / "previous.txt"
    canary.write_bytes(b"preserve")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        patch.object(build_module, "_verify_panda_assets"),
        patch.object(build_module.subprocess, "run") as pyinstaller,
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(build_module.PackageValidationError, match="Stale package transaction"),
    ):
        build_module.main()
    pyinstaller.assert_not_called()
    assert canary.read_bytes() == b"preserve"

    with pytest.raises(build_module.PackageValidationError, match="Stale package transaction"):
        build_module.verify_package(bundle, tmp_path / "dist" / build_module.PACKAGE_DIRECTORY_NAME)
    assert canary.read_bytes() == b"preserve"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_finalize_rejects_linked_dist_ancestor(build_module, tmp_path: Path) -> None:
    real_dist = tmp_path / "real-dist"
    real_dist.mkdir()
    bundle = real_dist / build_module.BUNDLE_NAME
    bundle.mkdir()
    (bundle / "MCLab").write_bytes(b"app")
    (bundle / build_module.UNSIGNED_MARKER_NAME).write_bytes(build_module.UNSIGNED_MARKER_BYTES)
    os.symlink(real_dist, tmp_path / "dist")

    with (
        patch.object(build_module, "ROOT", tmp_path),
        pytest.raises(build_module.PackageValidationError, match="link or reparse"),
    ):
        build_module._finalize_package(tmp_path / "dist" / "MCLab", enforce_size_gate=True)


@pytest.mark.parametrize("option", ["--clean", "--skip-size-gate"])
def test_verify_only_rejects_mutating_option_combinations(build_module, option: str) -> None:
    with (
        patch.object(sys, "argv", ["build_desktop.py", "--verify-only", option]),
        pytest.raises(SystemExit) as raised,
    ):
        build_module.main()
    assert raised.value.code == 2


def test_offline_self_asserted_requires_verify_only(build_module) -> None:
    with (
        patch.object(sys, "argv", ["build_desktop.py", "--offline-self-asserted"]),
        pytest.raises(SystemExit) as raised,
    ):
        build_module.main()
    assert raised.value.code == 2
