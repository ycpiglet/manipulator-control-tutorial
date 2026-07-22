"""Fail-closed LIC-01A inventory and package-license evidence checker.

This checker uses only the Python standard library and reviewed repository
modules.  It proves package-lock/cell/target coverage while deliberately
retaining ``pending-lic-01``.  It does not interpret license terms, approve
Qt/PySide distribution, or turn short-lived CI observations into release
provenance.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_license_inventory as inventory  # noqa: E402
from scripts import generate_sbom_inputs as supply  # noqa: E402


EXPECTED_REGISTRY_SCHEMA_SHA256 = (
    "34df37e8de8d7bf785cca984d430f7c03270f5be56af7fbc8c6bb4f3e7be7487"
)
EXPECTED_EVIDENCE_SCHEMA_SHA256 = (
    "b247efd4aa2e12e9b704954a291ac54a5d72a8f0e16f145d8c7ac1489ffdf3f6"
)

REGISTRY_TOP_KEYS = {
    "candidates",
    "contract",
    "observation_baseline",
    "observed_targets",
    "schema_version",
    "sources",
    "target_cells",
}
CONTRACT_KEYS = {
    "blockers",
    "candidate_count",
    "compliance_status",
    "id",
    "legal_approval",
    "notice_bundle_complete",
    "observed_target_count",
    "public_distribution_authorized",
    "purpose",
    "qt_pyside_lgpl_decision",
    "target_cell_count",
}
SOURCE_KEYS = {"path", "sha256", "size"}
SOURCE_NAMES = {
    "checker",
    "evidence_schema",
    "generator",
    "package_lock",
    "project",
    "registry_schema",
    "scanner",
}
CANDIDATE_KEYS = {"environment_ids", "marker", "name", "review_status", "version"}
CELL_KEYS = {
    "candidate_count",
    "id",
    "marker",
    "platform_machine",
    "python_version",
    "sys_platform",
}
OBSERVED_KEYS = {
    "artifact",
    "cell_id",
    "id",
    "metadata_gaps",
    "package_count",
    "recorded_target",
    "runner_os",
}
ARTIFACT_KEYS = {"evidence_sha256", "expires_at", "id", "name"}
TARGET_KEYS = {
    "implementation",
    "implementation_name",
    "machine",
    "python_version",
    "sys_platform",
}
RECORDED_TARGET_KEYS = {
    "implementation",
    "implementation_name",
    "machine",
    "python_full_version",
    "sys_platform",
}
GAP_KEYS = {"license", "license_text", "notice_text", "url"}

EVIDENCE_TOP_KEYS = {
    "audit",
    "compliance_status",
    "excluded_system_packages",
    "input_lock_profiles",
    "metadata_gaps",
    "package_count",
    "packages",
    "profile",
    "purpose",
    "result",
    "schema_version",
    "target",
    "tool",
}
PACKAGE_KEYS = {"license", "license_text", "name", "notice_text", "url", "version"}

EXPECTED_CONTRACT = {
    "blockers": [
        "copyright-attribution-review-pending",
        "license-expression-review-pending",
        "license-text-coverage-pending",
        "native-and-base-image-transitive-inventory-pending",
        "notice-text-coverage-pending",
        "qt-pyside-lgpl-compliance-decision-pending",
        "source-offer-and-relinking-obligations-pending",
    ],
    "candidate_count": 49,
    "compliance_status": "pending-lic-01",
    "id": "LIC-01A",
    "legal_approval": False,
    "notice_bundle_complete": False,
    "observed_target_count": 3,
    "public_distribution_authorized": False,
    "purpose": "deterministic inventory coverage contract; not legal approval",
    "qt_pyside_lgpl_decision": "pending",
    "target_cell_count": 12,
}
EXPECTED_OBSERVATION_BASELINE = {
    "evidence_scope": "short-lived development evidence; not release provenance",
    "source_commit": "6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1",
    "workflow_run_id": 29950992873,
}
EXPECTED_OBSERVED = {
    "Linux": {
        "artifact_id": 8542125543,
        "artifact_name": "mclab-supply-chain-Linux",
        "cell_id": "cpython-3.11-linux-x86_64",
        "evidence_sha256": (
            "cea1db18977740f449f413d87e13ee2c85707f6bcbc2684b020f396c82635d83"
        ),
        "expires_at": "2026-08-05T19:27:49Z",
        "id": "github-hosted-linux-cpython-3.11",
        "machine": "x86_64",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 43,
            "url": 2,
        },
        "package_count": 44,
        "python_full_version": "3.11.15",
        "sys_platform": "linux",
    },
    "macOS": {
        "artifact_id": 8542118388,
        "artifact_name": "mclab-supply-chain-macOS",
        "cell_id": "cpython-3.11-darwin-arm64",
        "evidence_sha256": (
            "fdc73a10a3e5a9bad525604d1ff7450021182fbb78965b7407da7620d50d44de"
        ),
        "expires_at": "2026-08-05T19:27:32Z",
        "id": "github-hosted-macos-cpython-3.11",
        "machine": "arm64",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 44,
            "url": 2,
        },
        "package_count": 45,
        "python_full_version": "3.11.9",
        "sys_platform": "darwin",
    },
    "Windows": {
        "artifact_id": 8542166959,
        "artifact_name": "mclab-supply-chain-Windows",
        "cell_id": "cpython-3.11-win32-amd64",
        "evidence_sha256": (
            "bd9540d0b5a21f0772d9722b5fbf61e63902547074ac738d874da2bc9dfb987f"
        ),
        "expires_at": "2026-08-05T19:29:22Z",
        "id": "github-hosted-windows-cpython-3.11",
        "machine": "AMD64",
        "metadata_gaps": {
            "license": 1,
            "license_text": 1,
            "notice_text": 46,
            "url": 2,
        },
        "package_count": 47,
        "python_full_version": "3.11.9",
        "sys_platform": "win32",
    },
}


def _exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: expected object")
        return False
    if set(value) != expected:
        errors.append(f"{label}: keys must be {sorted(expected)}")
        return False
    return True


def _strict_json_bytes(payload: bytes, label: str) -> dict[str, object]:
    try:
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=supply._pairs_without_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite number {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise inventory.LicenseInventoryError(f"malformed {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise inventory.LicenseInventoryError(f"malformed {label}: root must be an object")
    return value


def _closed_schema_errors(
    root: Path,
    path: str,
    expected_sha256: str,
    top_level_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    try:
        record = supply.source_record(root, path)
        schema = supply.strict_json(root, path)
    except supply.SupplyChainInputError as exc:
        return [str(exc)]
    if record["sha256"] != expected_sha256:
        errors.append(f"{path}: reviewed schema SHA-256 drift")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"{path}: draft-2020-12 declaration required")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append(f"{path}: closed object root required")
    if set(schema.get("required", [])) != top_level_keys:
        errors.append(f"{path}: exact top-level required list drift")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(properties) != top_level_keys:
        errors.append(f"{path}: exact top-level properties drift")

    def visit(value: object, label: str) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                object_properties = value.get("properties")
                required = value.get("required")
                if value.get("additionalProperties") is not False:
                    errors.append(f"{path}:{label}: object schema must be closed")
                if not isinstance(object_properties, dict) or not isinstance(required, list):
                    errors.append(f"{path}:{label}: closed object fields are incomplete")
                elif set(required) != set(object_properties):
                    errors.append(f"{path}:{label}: every object property must be required")
            for key, child in value.items():
                visit(child, f"{label}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{label}[{index}]")

    visit(schema, "root")
    return errors


def schema_policy_errors(root: Path) -> list[str]:
    errors = _closed_schema_errors(
        root,
        inventory.REGISTRY_SCHEMA_PATH,
        EXPECTED_REGISTRY_SCHEMA_SHA256,
        REGISTRY_TOP_KEYS,
    )
    errors.extend(
        _closed_schema_errors(
            root,
            inventory.EVIDENCE_SCHEMA_PATH,
            EXPECTED_EVIDENCE_SCHEMA_SHA256,
            EVIDENCE_TOP_KEYS,
        )
    )
    return errors


def _source_errors(root: Path, source: object, label: str) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(source, SOURCE_KEYS, label, errors):
        return errors
    assert isinstance(source, dict)
    path = source.get("path")
    if not isinstance(path, str):
        return [f"{label}: path must be a string"]
    try:
        actual = supply.source_record(root, path)
    except supply.SupplyChainInputError as exc:
        return [str(exc)]
    if source != actual:
        errors.append(f"{label}: hash/size drift for {path}")
    return errors


def registry_policy_errors(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    try:
        registry, generation_errors = inventory.check_committed_registry(root)
    except (inventory.LicenseInventoryError, supply.SupplyChainInputError) as exc:
        return None, [str(exc)]
    errors.extend(generation_errors)
    if not _exact_keys(registry, REGISTRY_TOP_KEYS, "registry", errors):
        return registry, errors
    if registry.get("schema_version") != 1:
        errors.append("registry.schema_version: expected 1")
    if registry.get("contract") != EXPECTED_CONTRACT:
        errors.append("registry.contract: pending LIC-01A boundary drift")
    if registry.get("observation_baseline") != EXPECTED_OBSERVATION_BASELINE:
        errors.append("registry.observation_baseline: accepted SUP-01 evidence drift")

    sources = registry.get("sources")
    if _exact_keys(sources, SOURCE_NAMES, "registry.sources", errors):
        assert isinstance(sources, dict)
        for name in sorted(sources):
            errors.extend(_source_errors(root, sources[name], f"registry.sources.{name}"))

    candidates = registry.get("candidates")
    cells = registry.get("target_cells")
    if not isinstance(candidates, list) or len(candidates) != 49:
        errors.append("registry.candidates: exactly 49 records required")
        candidates = []
    if not isinstance(cells, list) or len(cells) != 12:
        errors.append("registry.target_cells: exactly 12 records required")
        cells = []
    cell_ids: set[str] = set()
    cell_counts: dict[str, int] = {}
    for index, cell in enumerate(cells):
        label = f"registry.target_cells[{index}]"
        if not _exact_keys(cell, CELL_KEYS, label, errors):
            continue
        assert isinstance(cell, dict)
        identifier = cell.get("id")
        count = cell.get("candidate_count")
        if not isinstance(identifier, str) or identifier in cell_ids:
            errors.append(f"{label}: unique string id required")
            continue
        if type(count) is not int:
            errors.append(f"{label}: integer candidate_count required")
            continue
        cell_ids.add(identifier)
        cell_counts[identifier] = count
    if cell_counts != inventory.EXPECTED_CELL_COUNTS:
        errors.append("registry.target_cells: reviewed 12-cell counts drift")

    names: list[str] = []
    measured_membership = {identifier: 0 for identifier in cell_ids}
    for index, candidate in enumerate(candidates):
        label = f"registry.candidates[{index}]"
        if not _exact_keys(candidate, CANDIDATE_KEYS, label, errors):
            continue
        assert isinstance(candidate, dict)
        name = candidate.get("name")
        version = candidate.get("version")
        environment_ids = candidate.get("environment_ids")
        if not isinstance(name, str) or supply._normalise_name(name) != name:
            errors.append(f"{label}: normalized name required")
        else:
            names.append(name)
        if not isinstance(version, str) or not version:
            errors.append(f"{label}: nonempty version required")
        if candidate.get("review_status") != "pending":
            errors.append(f"{label}: review_status must remain pending")
        if (
            not isinstance(environment_ids, list)
            or environment_ids != sorted(environment_ids)
            or len(environment_ids) != len(set(environment_ids))
            or not environment_ids
            or not set(environment_ids).issubset(cell_ids)
        ):
            errors.append(f"{label}: sorted nonempty reviewed environment_ids required")
        else:
            for identifier in environment_ids:
                measured_membership[identifier] += 1
    if names != sorted(names) or len(names) != len(set(names)):
        errors.append("registry.candidates: names must be sorted and unique")
    if measured_membership != inventory.EXPECTED_CELL_COUNTS:
        errors.append("registry.candidates: target-cell membership counts drift")

    observed = registry.get("observed_targets")
    if not isinstance(observed, list) or len(observed) != 3:
        errors.append("registry.observed_targets: exactly 3 records required")
        observed = []
    runners: set[str] = set()
    for index, target in enumerate(observed):
        label = f"registry.observed_targets[{index}]"
        if not _exact_keys(target, OBSERVED_KEYS, label, errors):
            continue
        assert isinstance(target, dict)
        runner = target.get("runner_os")
        if not isinstance(runner, str) or runner not in EXPECTED_OBSERVED or runner in runners:
            errors.append(f"{label}: unique reviewed runner_os required")
            continue
        runners.add(runner)
        expected = EXPECTED_OBSERVED[runner]
        artifact = target.get("artifact")
        recorded = target.get("recorded_target")
        _exact_keys(artifact, ARTIFACT_KEYS, f"{label}.artifact", errors)
        _exact_keys(recorded, RECORDED_TARGET_KEYS, f"{label}.recorded_target", errors)
        if not isinstance(artifact, dict) or not isinstance(recorded, dict):
            continue
        actual_summary = {
            "artifact_id": artifact.get("id"),
            "artifact_name": artifact.get("name"),
            "cell_id": target.get("cell_id"),
            "evidence_sha256": artifact.get("evidence_sha256"),
            "expires_at": artifact.get("expires_at"),
            "id": target.get("id"),
            "machine": recorded.get("machine"),
            "metadata_gaps": target.get("metadata_gaps"),
            "package_count": target.get("package_count"),
            "python_full_version": recorded.get("python_full_version"),
            "sys_platform": recorded.get("sys_platform"),
        }
        if actual_summary != expected:
            errors.append(f"{label}: accepted observed-target summary drift")
    if runners != set(EXPECTED_OBSERVED):
        errors.append("registry.observed_targets: Linux/Windows/macOS coverage required")
    return registry, errors


def _safe_evidence_bytes(root: Path, path: Path) -> bytes:
    posix = PurePosixPath(path.as_posix())
    if (
        path.is_absolute()
        or path.suffix.lower() != ".json"
        or len(posix.parts) < 3
        or posix.parts[:2] != ("build", "validation")
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise inventory.LicenseInventoryError(
            "license evidence must be a repository-relative JSON below build/validation"
        )
    return supply.read_bytes(root, posix.as_posix())


def _normalized_text(value: str) -> str:
    unix = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in unix.split("\n")).strip()


def _expected_packages(
    registry: Mapping[str, object], cell_id: str
) -> dict[str, str]:
    candidates = registry["candidates"]
    assert isinstance(candidates, list)
    packages = {
        str(candidate["name"]): str(candidate["version"])
        for candidate in candidates
        if isinstance(candidate, dict) and cell_id in candidate.get("environment_ids", [])
    }
    if packages.pop("setuptools", None) is None:
        raise inventory.LicenseInventoryError(
            f"reviewed package cell {cell_id} must contain excluded setuptools"
        )
    packages["mujoco-manipulator-control-lab"] = "0.1.0"
    return dict(sorted(packages.items()))


def evidence_policy_errors(
    root: Path,
    registry: Mapping[str, object],
    evidence_path: Path,
    runner_os: str,
) -> list[str]:
    errors: list[str] = []
    if runner_os not in EXPECTED_OBSERVED:
        return [f"unsupported runner OS {runner_os!r}"]
    try:
        payload = _safe_evidence_bytes(root, evidence_path)
        evidence = _strict_json_bytes(payload, "package-profile license evidence")
    except (inventory.LicenseInventoryError, supply.SupplyChainInputError) as exc:
        return [str(exc)]
    if inventory.canonical_json_bytes(evidence) != payload:
        errors.append("license evidence must be canonical sorted JSON")
    if not _exact_keys(evidence, EVIDENCE_TOP_KEYS, "evidence", errors):
        return errors
    expected_fixed = {
        "audit": "python-licenses",
        "compliance_status": "pending-lic-01",
        "excluded_system_packages": ["pip", "setuptools", "wheel"],
        "input_lock_profiles": ["build", "package"],
        "profile": "package",
        "purpose": "LIC-01 input only; not legal approval",
        "result": "inventory-complete",
        "schema_version": 1,
        "tool": {"name": "pip-licenses", "version": "5.5.5"},
    }
    for key, expected_value in expected_fixed.items():
        if evidence.get(key) != expected_value:
            errors.append(f"evidence.{key}: reviewed pending contract drift")

    target = evidence.get("target")
    if not _exact_keys(target, TARGET_KEYS, "evidence.target", errors):
        return errors
    assert isinstance(target, dict)
    expected_observed = EXPECTED_OBSERVED[runner_os]
    expected_target = {
        "implementation": "CPython",
        "implementation_name": "cpython",
        "machine": expected_observed["machine"],
        "sys_platform": expected_observed["sys_platform"],
    }
    if any(target.get(key) != value for key, value in expected_target.items()):
        errors.append(f"evidence.target: {runner_os} target identity drift")
    python_full_version = target.get("python_version")
    if not isinstance(python_full_version, str) or re.fullmatch(
        r"3\.11\.[0-9]+", python_full_version
    ) is None:
        errors.append("evidence.target.python_version: CPython 3.11 patch required")

    packages = evidence.get("packages")
    if not isinstance(packages, list):
        return errors + ["evidence.packages: expected list"]
    expected_packages = _expected_packages(registry, str(expected_observed["cell_id"]))
    actual_packages: dict[str, str] = {}
    calculated_gaps = {key: 0 for key in sorted(GAP_KEYS)}
    names: list[str] = []
    for index, package in enumerate(packages):
        label = f"evidence.packages[{index}]"
        if not _exact_keys(package, PACKAGE_KEYS, label, errors):
            continue
        assert isinstance(package, dict)
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or supply._normalise_name(name) != name:
            errors.append(f"{label}.name: normalized name required")
            continue
        if name in actual_packages:
            errors.append(f"{label}.name: duplicate package {name}")
            continue
        if not isinstance(version, str) or not version:
            errors.append(f"{label}.version: nonempty string required")
            continue
        names.append(name)
        actual_packages[name] = version
        for field in ("license", "license_text", "notice_text", "url"):
            value = package.get(field)
            if value is None:
                calculated_gaps[field] += 1
                continue
            if not isinstance(value, str):
                errors.append(f"{label}.{field}: string or null required")
                continue
            normalized = _normalized_text(value)
            if not normalized or normalized.casefold() == "unknown" or normalized != value:
                errors.append(f"{label}.{field}: normalized non-UNKNOWN text required")
            if len(value.encode("utf-8")) > 1024 * 1024:
                errors.append(f"{label}.{field}: bounded text limit exceeded")
        license_value = package.get("license")
        if isinstance(license_value, str):
            parts = [part.strip() for part in license_value.split(";") if part.strip()]
            normalized_license = "; ".join(
                sorted(set(parts), key=lambda item: (item.casefold(), item))
            )
            if normalized_license != license_value:
                errors.append(f"{label}.license: sorted unique identifier list required")
    if names != sorted(names):
        errors.append("evidence.packages: package names must be sorted")
    if actual_packages != expected_packages:
        missing = sorted(set(expected_packages) - set(actual_packages))
        extra = sorted(set(actual_packages) - set(expected_packages))
        mismatched = sorted(
            name
            for name in set(actual_packages) & set(expected_packages)
            if actual_packages[name] != expected_packages[name]
        )
        errors.append(
            "evidence.packages: package lock coverage drift "
            f"missing={missing}, extra={extra}, version_mismatch={mismatched}"
        )
    if evidence.get("package_count") != len(packages):
        errors.append("evidence.package_count: must equal package list length")
    if len(packages) != expected_observed["package_count"]:
        errors.append(f"evidence.package_count: {runner_os} observed count drift")
    if evidence.get("metadata_gaps") != calculated_gaps:
        errors.append("evidence.metadata_gaps: must equal calculated null counts")
    if calculated_gaps != expected_observed["metadata_gaps"]:
        errors.append(f"evidence.metadata_gaps: {runner_os} accepted gap summary drift")
    return errors


def validate_repository(
    root: Path,
    *,
    evidence_path: Path | None = None,
    runner_os: str | None = None,
) -> tuple[dict[str, object] | None, list[str]]:
    errors = schema_policy_errors(root)
    registry, registry_errors = registry_policy_errors(root)
    errors.extend(registry_errors)
    if evidence_path is not None:
        if runner_os is None:
            errors.append("runner OS is required when evidence is supplied")
        elif registry is not None:
            errors.extend(evidence_policy_errors(root, registry, evidence_path, runner_os))
    elif runner_os is not None:
        errors.append("evidence path is required when runner OS is supplied")
    return registry, errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--runner-os", choices=sorted(EXPECTED_OBSERVED))
    args = parser.parse_args(argv)
    registry, errors = validate_repository(
        ROOT,
        evidence_path=args.evidence,
        runner_os=args.runner_os,
    )
    if errors:
        print("License inventory contract: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    assert registry is not None
    suffix = ""
    if args.evidence is not None:
        suffix = f", {args.runner_os} evidence matched"
    print(
        "License inventory contract: PASS "
        f"(49 candidates, 12 cells, 3 observed targets, pending-lic-01{suffix})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
