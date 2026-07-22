from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import generate_license_inventory as generator


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents/validation/check_license_inventory.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("_test_license_inventory_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


@pytest.fixture
def contract_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    paths = {generator.REGISTRY_PATH, *generator.SOURCE_PATHS.values()}
    for relative in sorted(paths):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _registry() -> dict[str, object]:
    return json.loads((ROOT / generator.REGISTRY_PATH).read_text(encoding="utf-8"))


def _evidence_document(registry: dict[str, object], runner_os: str) -> dict[str, Any]:
    observed = checker.EXPECTED_OBSERVED[runner_os]
    expected_packages = checker._expected_packages(registry, observed["cell_id"])
    packages = [
        {
            "license": "present",
            "license_text": "present",
            "name": name,
            "notice_text": "present",
            "url": "https://example.invalid",
            "version": version,
        }
        for name, version in expected_packages.items()
    ]
    for field, count in observed["metadata_gaps"].items():
        for package in packages[:count]:
            package[field] = None
    return {
        "audit": "python-licenses",
        "compliance_status": "pending-lic-01",
        "excluded_system_packages": ["pip", "setuptools", "wheel"],
        "input_lock_profiles": ["build", "package"],
        "metadata_gaps": dict(observed["metadata_gaps"]),
        "package_count": len(packages),
        "packages": packages,
        "profile": "package",
        "purpose": "LIC-01 input only; not legal approval",
        "result": "inventory-complete",
        "schema_version": 1,
        "target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": observed["machine"],
            "python_version": observed["python_full_version"],
            "sys_platform": observed["sys_platform"],
        },
        "tool": {"name": "pip-licenses", "version": "5.5.5"},
    }


def _registry_with_evidence_observations(
    registry: dict[str, object],
    runner_os: str,
    evidence: dict[str, Any],
) -> dict[str, object]:
    updated = copy.deepcopy(registry)
    target = next(item for item in updated["observed_targets"] if item["runner_os"] == runner_os)
    target["package_observations"] = [
        {
            "license_observation": package["license"],
            "license_text_sha256": (
                hashlib.sha256(package["license_text"].encode("utf-8")).hexdigest()
                if package["license_text"] is not None
                else None
            ),
            "name": package["name"],
            "notice_text_sha256": (
                hashlib.sha256(package["notice_text"].encode("utf-8")).hexdigest()
                if package["notice_text"] is not None
                else None
            ),
            "url_observation": package["url"],
            "version": package["version"],
        }
        for package in evidence["packages"]
    ]
    return updated


def _write_evidence(
    root: Path,
    document: dict[str, Any],
    *,
    payload: bytes | None = None,
) -> Path:
    relative = Path("build/validation/license-test/python-licenses.json")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(generator.canonical_json_bytes(document) if payload is None else payload)
    return relative


def test_committed_inventory_is_deterministic_closed_and_pending() -> None:
    registry, errors = checker.validate_repository(ROOT)

    assert errors == []
    assert registry is not None
    assert len(registry["candidates"]) == 49
    assert len(registry["target_cells"]) == 12
    assert len(registry["observed_targets"]) == 3
    assert registry["contract"] == checker.EXPECTED_CONTRACT
    assert registry["contract"]["compliance_status"] == "pending-lic-01"
    assert registry["contract"]["legal_approval"] is False
    assert registry["contract"]["notice_bundle_complete"] is False
    assert registry["contract"]["public_distribution_authorized"] is False
    assert registry["contract"]["qt_pyside_lgpl_decision"] == "pending"
    assert registry["coverage"] == checker.EXPECTED_COVERAGE
    assert registry["coverage"]["applicable_lock_candidate_union_count"] == 48
    assert registry["coverage"]["observed_locked_candidate_union_count"] == 47
    assert registry["coverage"]["observation_row_union_count"] == 48
    assert registry["coverage"]["not_applicable_to_observed_targets"][0]["name"] == "exceptiongroup"
    assert registry["coverage"]["excluded_applicable_lock_candidates"][0] == {
        "name": "setuptools",
        "reason": "explicit-target-scoped-scanner-exclusion",
        "target_ids": registry["coverage"]["observed_target_ids"],
        "version": "83.0.0",
    }
    assert registry["coverage"]["added_observation_rows"][0] == {
        "name": "mujoco-manipulator-control-lab",
        "reason": "editable-project-target-addition",
        "target_ids": registry["coverage"]["observed_target_ids"],
        "version": "0.1.0",
    }
    assert registry["coverage"]["distribution_closure"] == "unproven"
    assert len(registry["coverage"]["observed_target_ids"]) == 3
    assert len(registry["coverage"]["unobserved_target_ids"]) == 9
    assert [len(target["package_observations"]) for target in registry["observed_targets"]] == [
        44,
        45,
        47,
    ]
    assert [
        target["applicable_lock_candidate_count"] for target in registry["observed_targets"]
    ] == [44, 45, 47]
    assert [
        target["observed_locked_candidate_count"] for target in registry["observed_targets"]
    ] == [43, 44, 46]
    assert [target["observation_row_count"] for target in registry["observed_targets"]] == [
        44,
        45,
        47,
    ]
    assert all(
        target["excluded_applicable_lock_candidates"] == checker.EXPECTED_TARGET_EXCLUSION
        and target["added_observation_rows"] == checker.EXPECTED_TARGET_ADDITION
        for target in registry["observed_targets"]
    )
    assert all(
        set(package) == checker.OBSERVED_PACKAGE_KEYS
        for target in registry["observed_targets"]
        for package in target["package_observations"]
    )
    candidate_names = {candidate["name"] for candidate in registry["candidates"]}
    observed_row_names = {
        package["name"]
        for target in registry["observed_targets"]
        for package in target["package_observations"]
    }
    assert len(candidate_names - {"exceptiongroup", "setuptools"}) == 47
    assert len(observed_row_names & candidate_names) == 47
    assert len(observed_row_names) == 48
    assert "setuptools" not in observed_row_names
    assert "exceptiongroup" not in observed_row_names
    assert "mujoco-manipulator-control-lab" in observed_row_names
    assert set(registry["sources"]) == set(generator.SOURCE_PATHS)
    assert {
        name: source["path"] for name, source in registry["sources"].items()
    } == generator.SOURCE_PATHS
    artifacts = {target["runner_os"]: target["artifact"] for target in registry["observed_targets"]}
    assert all(
        artifact["normalization_algorithm"] == generator.EVIDENCE_NORMALIZATION_ALGORITHM
        and artifact["normalization_version"] == generator.EVIDENCE_NORMALIZATION_VERSION
        for artifact in artifacts.values()
    )
    assert (
        artifacts["Linux"]["raw_evidence_sha256"] == artifacts["Linux"]["canonical_evidence_sha256"]
    )
    assert (
        artifacts["macOS"]["raw_evidence_sha256"] == artifacts["macOS"]["canonical_evidence_sha256"]
    )
    assert (
        artifacts["Windows"]["raw_evidence_sha256"]
        != artifacts["Windows"]["canonical_evidence_sha256"]
    )
    surfaces = registry["distribution_surfaces"]
    assert surfaces == generator._distribution_surfaces(ROOT)
    assert surfaces["ubuntu_system"]["package_count"] == 22
    assert surfaces["panda_runtime"]["file_count"] == 72
    assert surfaces["fonts"]["file_count"] == 2
    assert surfaces["packaging"]["data_group_count"] == 6
    assert all(candidate["review_status"] == "pending" for candidate in registry["candidates"])
    assert (
        generator.canonical_json_bytes(generator.build_registry(ROOT))
        == (ROOT / generator.REGISTRY_PATH).read_bytes()
    )
    assert generator.canonical_json_bytes(generator.build_registry(ROOT)) == (
        generator.canonical_json_bytes(generator.build_registry(ROOT))
    )


def test_schemas_close_every_object_and_exact_inventory_lengths() -> None:
    assert checker.schema_policy_errors(ROOT) == []
    registry_schema = json.loads(
        (ROOT / generator.REGISTRY_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    evidence_schema = json.loads(
        (ROOT / generator.EVIDENCE_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    assert registry_schema["properties"]["candidates"]["minItems"] == 49
    assert registry_schema["properties"]["candidates"]["maxItems"] == 49
    assert registry_schema["properties"]["target_cells"]["minItems"] == 12
    assert registry_schema["properties"]["target_cells"]["maxItems"] == 12
    assert registry_schema["properties"]["observed_targets"]["minItems"] == 3
    assert registry_schema["properties"]["observed_targets"]["maxItems"] == 3

    for schema in (registry_schema, evidence_schema):
        pending = [schema]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if value.get("type") == "object":
                    assert value["additionalProperties"] is False
                    assert set(value["required"]) == set(value["properties"])
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)


@pytest.mark.parametrize(
    "tamper",
    (
        "candidate-status",
        "legal-approval",
        "notice-complete",
        "public-distribution",
        "qt-decision",
        "missing-candidate",
        "extra-key",
        "cell-count",
        "observed-summary",
        "observed-license",
        "observed-url",
        "observed-license-hash",
        "observed-notice-hash",
        "coverage",
        "distribution-surface",
    ),
)
def test_registry_tampering_fails_closed(contract_repository: Path, tamper: str) -> None:
    path = contract_repository / generator.REGISTRY_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "candidate-status":
        document["candidates"][0]["review_status"] = "approved"
    elif tamper == "legal-approval":
        document["contract"]["legal_approval"] = True
    elif tamper == "notice-complete":
        document["contract"]["notice_bundle_complete"] = True
    elif tamper == "public-distribution":
        document["contract"]["public_distribution_authorized"] = True
    elif tamper == "qt-decision":
        document["contract"]["qt_pyside_lgpl_decision"] = "approved"
    elif tamper == "missing-candidate":
        document["candidates"].pop()
    elif tamper == "extra-key":
        document["unexpected"] = True
    elif tamper == "cell-count":
        document["target_cells"][0]["candidate_count"] += 1
    elif tamper == "observed-summary":
        document["observed_targets"][0]["package_count"] += 1
    elif tamper == "observed-license":
        document["observed_targets"][0]["package_observations"][1]["license_observation"] = (
            "changed observation"
        )
    elif tamper == "observed-url":
        document["observed_targets"][0]["package_observations"][2]["url_observation"] = (
            "https://changed.invalid"
        )
    elif tamper == "observed-license-hash":
        document["observed_targets"][0]["package_observations"][3]["license_text_sha256"] = "0" * 64
    elif tamper == "observed-notice-hash":
        document["observed_targets"][0]["package_observations"][-1]["notice_text_sha256"] = "0" * 64
    elif tamper == "coverage":
        document["coverage"]["distribution_closure"] = "proven"
    else:
        document["distribution_surfaces"]["packaging"]["data_group_count"] = 5
    path.write_bytes(generator.canonical_json_bytes(document))

    _registry, errors = checker.registry_policy_errors(contract_repository)

    assert errors


def test_registry_exact_integer_fields_reject_bool_and_float(
    contract_repository: Path,
) -> None:
    path = contract_repository / generator.REGISTRY_PATH
    baseline = json.loads(path.read_text(encoding="utf-8"))
    field_paths: list[tuple[object, ...]] = [("schema_version",)]
    for target_index in range(len(baseline["observed_targets"])):
        field_paths.append(("observed_targets", target_index, "package_count"))
        field_paths.extend(
            ("observed_targets", target_index, "metadata_gaps", field)
            for field in sorted(checker.GAP_KEYS)
        )
    for field_path in field_paths:
        original: Any = baseline
        for part in field_path:
            original = original[part]
        for invalid in (True, float(original)):
            document = copy.deepcopy(baseline)
            parent: Any = document
            for part in field_path[:-1]:
                parent = parent[part]
            parent[field_path[-1]] = invalid
            path.write_bytes(generator.canonical_json_bytes(document))

            _registry_value, errors = checker.registry_policy_errors(contract_repository)

            label = ".".join(str(part) for part in field_path)
            assert any(
                "exact integer required" in error and label.split(".")[-1] in error
                for error in errors
            ), (field_path, invalid, errors)
    path.write_bytes(generator.canonical_json_bytes(baseline))


def test_every_direct_producer_input_missing_and_drift_fails_closed(
    contract_repository: Path,
) -> None:
    scanner_locks = {relative.as_posix() for _profile, relative in generator.audit.REVIEWED_LOCKS}
    declared_scanner_locks = {
        generator.SOURCE_PATHS[f"{profile.replace('-', '_')}_lock"]
        for profile, _relative in generator.audit.REVIEWED_LOCKS
    }
    assert declared_scanner_locks == scanner_locks

    for source_name, relative in sorted(generator.SOURCE_PATHS.items()):
        source = contract_repository / relative
        baseline = source.read_bytes()

        source.unlink()
        _registry_value, missing_errors = checker.registry_policy_errors(contract_repository)
        assert missing_errors, source_name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(baseline)

        source.write_bytes(baseline + b"\n")
        _registry_value, drift_errors = checker.registry_policy_errors(contract_repository)
        assert drift_errors, source_name
        source.write_bytes(baseline)


def test_source_and_schema_drift_fail_closed(contract_repository: Path) -> None:
    lock = contract_repository / generator.PACKAGE_LOCK_PATH
    lock.write_text(
        lock.read_text(encoding="utf-8").replace("mujoco==3.10.0", "mujoco==3.10.1", 1),
        encoding="utf-8",
    )
    schema = contract_repository / generator.REGISTRY_SCHEMA_PATH
    schema.write_text(schema.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    _registry_value, registry_errors = checker.registry_policy_errors(contract_repository)

    assert registry_errors
    assert any(
        "schema SHA-256 drift" in error
        for error in checker.schema_policy_errors(contract_repository)
    )


def test_generator_refuses_to_overwrite_committed_registry() -> None:
    with pytest.raises(generator.LicenseInventoryError, match="will not overwrite"):
        generator._write_output(
            ROOT / generator.REGISTRY_PATH,
            generator.canonical_json_bytes(generator.build_registry(ROOT)),
        )


@pytest.mark.parametrize("runner_os", ("Linux", "Windows", "macOS"))
def test_package_profile_evidence_matches_each_observed_target(
    tmp_path: Path, runner_os: str
) -> None:
    registry = _registry()
    evidence = _evidence_document(registry, runner_os)
    registry = _registry_with_evidence_observations(registry, runner_os, evidence)
    relative = _write_evidence(tmp_path, evidence)

    assert checker.evidence_policy_errors(tmp_path, registry, relative, runner_os) == []


def test_evidence_exact_integer_fields_reject_bool_and_float(tmp_path: Path) -> None:
    registry = _registry()
    baseline = _evidence_document(registry, "Linux")
    registry = _registry_with_evidence_observations(registry, "Linux", baseline)
    field_paths: list[tuple[str, ...]] = [
        ("schema_version",),
        ("package_count",),
        *(("metadata_gaps", field) for field in sorted(checker.GAP_KEYS)),
    ]
    for field_path in field_paths:
        original: Any = baseline
        for part in field_path:
            original = original[part]
        for invalid in (True, float(original)):
            document = copy.deepcopy(baseline)
            parent: Any = document
            for part in field_path[:-1]:
                parent = parent[part]
            parent[field_path[-1]] = invalid
            relative = _write_evidence(tmp_path, document)

            errors = checker.evidence_policy_errors(tmp_path, registry, relative, "Linux")

            assert any(
                "exact integer required" in error and field_path[-1] in error for error in errors
            )


def test_historical_noncanonical_evidence_requires_both_provenance_hashes(
    tmp_path: Path,
) -> None:
    registry = _registry()
    evidence = _evidence_document(registry, "Linux")
    registry = _registry_with_evidence_observations(registry, "Linux", evidence)
    canonical = generator.canonical_json_bytes(evidence)
    historical_raw = canonical.replace(b"\n", b"\r\n")
    target = next(item for item in registry["observed_targets"] if item["runner_os"] == "Linux")
    target["artifact"].update(
        {
            "canonical_evidence_sha256": hashlib.sha256(canonical).hexdigest(),
            "normalization_algorithm": generator.EVIDENCE_NORMALIZATION_ALGORITHM,
            "normalization_version": generator.EVIDENCE_NORMALIZATION_VERSION,
            "raw_evidence_sha256": hashlib.sha256(historical_raw).hexdigest(),
        }
    )
    relative = _write_evidence(tmp_path, evidence, payload=historical_raw)

    assert checker.evidence_policy_errors(tmp_path, registry, relative, "Linux") == []

    target["artifact"]["raw_evidence_sha256"] = "0" * 64
    assert any(
        "canonical sorted JSON" in error
        for error in checker.evidence_policy_errors(tmp_path, registry, relative, "Linux")
    )


@pytest.mark.parametrize(
    "tamper",
    (
        "status",
        "extra-key",
        "wrong-target",
        "wrong-version",
        "extra-package",
        "gap-summary",
        "license-observation",
        "url-observation",
        "license-text-observation",
        "notice-text-observation",
        "crlf",
    ),
)
def test_package_profile_evidence_tampering_fails_closed(tmp_path: Path, tamper: str) -> None:
    registry = _registry()
    document = _evidence_document(registry, "Linux")
    registry = _registry_with_evidence_observations(registry, "Linux", document)
    payload = None
    if tamper == "status":
        document["compliance_status"] = "complete"
    elif tamper == "extra-key":
        document["unexpected"] = True
    elif tamper == "wrong-target":
        document["target"]["machine"] = "arm64"
    elif tamper == "wrong-version":
        document["packages"][0]["version"] = "0"
    elif tamper == "extra-package":
        document["packages"].append(
            {
                "license": "present",
                "license_text": "present",
                "name": "zz-extra",
                "notice_text": "present",
                "url": "https://example.invalid",
                "version": "1",
            }
        )
        document["package_count"] += 1
    elif tamper == "gap-summary":
        document["metadata_gaps"]["url"] += 1
    elif tamper == "license-observation":
        document["packages"][1]["license"] = "changed observation"
    elif tamper == "url-observation":
        document["packages"][2]["url"] = "https://changed.invalid"
    elif tamper == "license-text-observation":
        document["packages"][3]["license_text"] = "changed observation"
    elif tamper == "notice-text-observation":
        document["packages"][-1]["notice_text"] = "changed observation"
    else:
        payload = generator.canonical_json_bytes(document).replace(b"\n", b"\r\n")
    relative = _write_evidence(tmp_path, document, payload=payload)

    errors = checker.evidence_policy_errors(tmp_path, registry, relative, "Linux")

    assert errors
    observation_fields = {
        "license-observation": "license_observation",
        "url-observation": "url_observation",
        "license-text-observation": "license_text_sha256",
        "notice-text-observation": "notice_text_sha256",
    }
    if tamper in observation_fields:
        assert any(
            "accepted normalized metadata observation drift" in error
            and observation_fields[tamper] in error
            for error in errors
        )


@pytest.mark.parametrize(
    "payload",
    (
        b'{"schema_version":1,"schema_version":1}\n',
        b'{"schema_version":NaN}\n',
        b"[]\n",
    ),
)
def test_evidence_parser_rejects_ambiguous_json(payload: bytes) -> None:
    with pytest.raises(generator.LicenseInventoryError, match="malformed"):
        checker._strict_json_bytes(payload, "test evidence")


@pytest.mark.parametrize(
    "path",
    (
        Path("outputs/python-licenses.json"),
        Path("build/python-licenses.json"),
        Path("build/validation/../python-licenses.json"),
        Path("build/validation/python-licenses.txt"),
    ),
)
def test_evidence_path_is_bounded_to_validation_json(tmp_path: Path, path: Path) -> None:
    with pytest.raises(generator.LicenseInventoryError, match="build/validation"):
        checker._safe_evidence_bytes(tmp_path, path)
