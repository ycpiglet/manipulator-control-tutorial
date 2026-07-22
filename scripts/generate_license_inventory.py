"""Generate the bounded LIC-01A package-license inventory contract.

The registry is deliberately an inventory-coverage contract, not a notice
bundle or legal conclusion.  It reads only the reviewed package lock,
12-target policy, closed schemas, scanner, and its own checker/generator
sources.  Accepted SUP-01 target observations are represented only by their
bounded summary and evidence hash; license and NOTICE bodies are never copied
into the committed registry.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_sbom_inputs as supply  # noqa: E402


SCHEMA_VERSION = 1
CANDIDATE_COUNT = 49
TARGET_CELL_COUNT = 12
OBSERVED_TARGET_COUNT = 3

REGISTRY_PATH = ".agents/supply_chain/license-inventory.json"
REGISTRY_SCHEMA_PATH = ".agents/supply_chain/license-inventory.schema.json"
EVIDENCE_SCHEMA_PATH = ".agents/supply_chain/python-license-evidence.schema.json"
GENERATOR_PATH = "scripts/generate_license_inventory.py"
CHECKER_PATH = ".agents/validation/check_license_inventory.py"
SCANNER_PATH = "scripts/audit_supply_chain.py"
PACKAGE_LOCK_PATH = "requirements/locks/package.txt"
PROJECT_PATH = "pyproject.toml"

BLOCKERS = (
    "copyright-attribution-review-pending",
    "license-expression-review-pending",
    "license-text-coverage-pending",
    "native-and-base-image-transitive-inventory-pending",
    "notice-text-coverage-pending",
    "qt-pyside-lgpl-compliance-decision-pending",
    "source-offer-and-relinking-obligations-pending",
)

EXPECTED_CELL_COUNTS = {
    "cpython-3.10-darwin-arm64": 46,
    "cpython-3.10-darwin-x86_64": 46,
    "cpython-3.10-linux-x86_64": 45,
    "cpython-3.10-win32-amd64": 48,
    "cpython-3.11-darwin-arm64": 45,
    "cpython-3.11-darwin-x86_64": 45,
    "cpython-3.11-linux-x86_64": 44,
    "cpython-3.11-win32-amd64": 47,
    "cpython-3.12-darwin-arm64": 44,
    "cpython-3.12-darwin-x86_64": 44,
    "cpython-3.12-linux-x86_64": 43,
    "cpython-3.12-win32-amd64": 46,
}

OBSERVATION_BASELINE = {
    "evidence_scope": "short-lived development evidence; not release provenance",
    "source_commit": "6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1",
    "workflow_run_id": 29950992873,
}

OBSERVED_TARGETS = (
    {
        "artifact": {
            "evidence_sha256": (
                "cea1db18977740f449f413d87e13ee2c85707f6bcbc2684b020f396c82635d83"
            ),
            "expires_at": "2026-08-05T19:27:49Z",
            "id": 8542125543,
            "name": "mclab-supply-chain-Linux",
        },
        "cell_id": "cpython-3.11-linux-x86_64",
        "id": "github-hosted-linux-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 43,
            "url": 2,
        },
        "package_count": 44,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "x86_64",
            "python_full_version": "3.11.15",
            "sys_platform": "linux",
        },
        "runner_os": "Linux",
    },
    {
        "artifact": {
            "evidence_sha256": (
                "fdc73a10a3e5a9bad525604d1ff7450021182fbb78965b7407da7620d50d44de"
            ),
            "expires_at": "2026-08-05T19:27:32Z",
            "id": 8542118388,
            "name": "mclab-supply-chain-macOS",
        },
        "cell_id": "cpython-3.11-darwin-arm64",
        "id": "github-hosted-macos-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 44,
            "url": 2,
        },
        "package_count": 45,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "arm64",
            "python_full_version": "3.11.9",
            "sys_platform": "darwin",
        },
        "runner_os": "macOS",
    },
    {
        "artifact": {
            "evidence_sha256": (
                "bd9540d0b5a21f0772d9722b5fbf61e63902547074ac738d874da2bc9dfb987f"
            ),
            "expires_at": "2026-08-05T19:29:22Z",
            "id": 8542166959,
            "name": "mclab-supply-chain-Windows",
        },
        "cell_id": "cpython-3.11-win32-amd64",
        "id": "github-hosted-windows-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 1,
            "notice_text": 46,
            "url": 2,
        },
        "package_count": 47,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "AMD64",
            "python_full_version": "3.11.9",
            "sys_platform": "win32",
        },
        "runner_os": "Windows",
    },
)


class LicenseInventoryError(RuntimeError):
    """Raised when the bounded LIC-01A contract cannot be generated safely."""


def _package_profile() -> supply.LockProfile:
    matches = [profile for profile in supply.LOCK_PROFILES if profile.identifier == "package"]
    if len(matches) != 1 or matches[0].lock_path != PACKAGE_LOCK_PATH:
        raise LicenseInventoryError("package lock profile identity drift")
    return matches[0]


def _candidate_records(
    root: Path, environments: list[dict[str, str]]
) -> list[dict[str, object]]:
    parsed = supply._parse_lock(root, _package_profile(), environments)
    requirements = parsed.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != CANDIDATE_COUNT:
        actual = None if not isinstance(requirements, list) else len(requirements)
        raise LicenseInventoryError(
            f"package lock candidate count drift: {actual} != {CANDIDATE_COUNT}"
        )
    candidates: list[dict[str, object]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise LicenseInventoryError("package lock candidate is not an object")
        candidates.append(
            {
                "environment_ids": requirement["environment_ids"],
                "marker": requirement["marker"],
                "name": requirement["name"],
                "review_status": "pending",
                "version": requirement["version"],
            }
        )
    names = [str(candidate["name"]) for candidate in candidates]
    if names != sorted(names) or len(names) != len(set(names)):
        raise LicenseInventoryError("package lock candidates must be sorted and unique")
    return candidates


def _target_cells(
    environments: list[dict[str, str]], candidates: list[dict[str, object]]
) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for environment in environments:
        identifier = environment["id"]
        candidate_count = sum(
            identifier in candidate["environment_ids"] for candidate in candidates
        )
        cells.append(
            {
                "candidate_count": candidate_count,
                "id": identifier,
                "marker": environment["marker"],
                "platform_machine": environment["platform_machine"],
                "python_version": environment["python_version"],
                "sys_platform": environment["sys_platform"],
            }
        )
    cells.sort(key=lambda item: str(item["id"]))
    measured = {str(cell["id"]): int(cell["candidate_count"]) for cell in cells}
    if measured != EXPECTED_CELL_COUNTS:
        raise LicenseInventoryError(
            f"package lock target-cell coverage drift: {measured}"
        )
    return cells


def _source_records(root: Path) -> dict[str, dict[str, object]]:
    paths = {
        "checker": CHECKER_PATH,
        "evidence_schema": EVIDENCE_SCHEMA_PATH,
        "generator": GENERATOR_PATH,
        "package_lock": PACKAGE_LOCK_PATH,
        "project": PROJECT_PATH,
        "registry_schema": REGISTRY_SCHEMA_PATH,
        "scanner": SCANNER_PATH,
    }
    return {name: supply.source_record(root, path) for name, path in paths.items()}


def build_registry(root: Path = ROOT) -> dict[str, object]:
    """Build one canonical pending LIC-01A registry from reviewed sources."""

    _project, environments = supply._project_and_environments(root)
    if len(environments) != TARGET_CELL_COUNT:
        raise LicenseInventoryError(
            f"target cell count drift: {len(environments)} != {TARGET_CELL_COUNT}"
        )
    candidates = _candidate_records(root, environments)
    target_cells = _target_cells(environments, candidates)
    cell_counts = {str(cell["id"]): int(cell["candidate_count"]) for cell in target_cells}
    if len(OBSERVED_TARGETS) != OBSERVED_TARGET_COUNT:
        raise LicenseInventoryError("observed target count drift")
    for observed in OBSERVED_TARGETS:
        if cell_counts.get(str(observed["cell_id"])) != observed["package_count"]:
            raise LicenseInventoryError(
                f"observed target coverage drift for {observed['id']}"
            )
    return {
        "candidates": candidates,
        "contract": {
            "blockers": list(BLOCKERS),
            "candidate_count": CANDIDATE_COUNT,
            "compliance_status": "pending-lic-01",
            "id": "LIC-01A",
            "legal_approval": False,
            "notice_bundle_complete": False,
            "observed_target_count": OBSERVED_TARGET_COUNT,
            "public_distribution_authorized": False,
            "purpose": "deterministic inventory coverage contract; not legal approval",
            "qt_pyside_lgpl_decision": "pending",
            "target_cell_count": TARGET_CELL_COUNT,
        },
        "observation_baseline": dict(OBSERVATION_BASELINE),
        "observed_targets": [dict(target) for target in OBSERVED_TARGETS],
        "schema_version": SCHEMA_VERSION,
        "sources": _source_records(root),
        "target_cells": target_cells,
    }


def canonical_json_bytes(document: dict[str, object]) -> bytes:
    return supply.canonical_json_bytes(document)


def check_committed_registry(root: Path = ROOT) -> tuple[dict[str, object], list[str]]:
    """Compare the committed registry byte-for-byte with two fresh generations."""

    errors: list[str] = []
    first = build_registry(root)
    second = build_registry(root)
    first_bytes = canonical_json_bytes(first)
    if first_bytes != canonical_json_bytes(second):
        errors.append("license inventory generation is not byte-deterministic")
    try:
        committed = supply.strict_json(root, REGISTRY_PATH)
        committed_bytes = supply.read_bytes(root, REGISTRY_PATH)
    except supply.SupplyChainInputError as exc:
        return first, [str(exc)]
    if canonical_json_bytes(committed) != committed_bytes:
        errors.append("committed license inventory is not canonical sorted JSON")
    if committed_bytes != first_bytes:
        errors.append("committed license inventory does not match reviewed sources")
    return committed, errors


def _write_output(path: Path, payload: bytes) -> None:
    if path.suffix.lower() != ".json":
        raise LicenseInventoryError("license inventory output must use a .json filename")
    candidate = Path(os.path.abspath(path))
    committed = Path(os.path.abspath(ROOT / REGISTRY_PATH))
    if candidate == committed:
        raise LicenseInventoryError(
            "generator will not overwrite the committed registry; generate elsewhere and review"
        )
    supply.write_document(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Check the committed registry")
    mode.add_argument("--output", type=Path, help="Write a reviewed candidate JSON elsewhere")
    args = parser.parse_args(argv)
    try:
        if args.check:
            registry, errors = check_committed_registry(ROOT)
            if errors:
                raise LicenseInventoryError("; ".join(errors))
            print(
                "License inventory generation: PASS "
                f"({len(registry['candidates'])} candidates, "
                f"{len(registry['target_cells'])} cells, "
                f"{len(registry['observed_targets'])} observed targets, pending-lic-01)"
            )
            return 0
        document = build_registry(ROOT)
        assert args.output is not None
        _write_output(args.output, canonical_json_bytes(document))
        print(
            f"License inventory candidate written: {args.output} "
            f"({CANDIDATE_COUNT} candidates, {TARGET_CELL_COUNT} cells, "
            f"{OBSERVED_TARGET_COUNT} observed targets, pending-lic-01)"
        )
        return 0
    except (OSError, LicenseInventoryError, supply.SupplyChainInputError) as exc:
        print(f"License inventory generation failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
