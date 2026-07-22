"""Fail-closed static policy gate for deterministic supply-chain inventory inputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_sbom_inputs as sbom  # noqa: E402


CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
DESKTOP_WORKFLOW_PATH = ".github/workflows/desktop.yml"
EXPECTED_SCHEMA_SHA256 = (
    "1f5ccce3c487124078777d29f8521db1e157c7eec30ea88d9804ccd8b3d9fc30"
)
TOP_LEVEL_KEYS = {
    "contract",
    "fonts",
    "github_actions",
    "packaging",
    "panda_runtime",
    "project",
    "python_lock_profiles",
    "schema_version",
    "source_commit",
    "target_environments",
    "ubuntu_system",
    "vulnerability_policy",
}
SOURCE_KEYS = {"path", "sha256", "size"}
PROFILE_KEYS = {"extras", "id", "lock", "requirements", "source"}
REQUIREMENT_KEYS = {
    "environment_ids",
    "extras",
    "hash_scope",
    "hashes",
    "marker",
    "name",
    "version",
}
ENVIRONMENT_KEYS = {
    "id",
    "implementation_name",
    "marker",
    "platform_machine",
    "platform_python_implementation",
    "python_full_version",
    "python_version",
    "sys_platform",
}
ACTION_KEYS = {
    "name",
    "release",
    "runtime",
    "sha",
    "source",
    "upstream_commit_verified",
}

SBOM_GENERATOR_COMMANDS = (
    'python scripts/generate_sbom_inputs.py --source-commit "$GITHUB_SHA" '
    "--output /tmp/mclab-sbom-inputs-1.json",
    'python scripts/generate_sbom_inputs.py --source-commit "$GITHUB_SHA" '
    "--output /tmp/mclab-sbom-inputs-2.json",
    "cmp /tmp/mclab-sbom-inputs-1.json /tmp/mclab-sbom-inputs-2.json",
)


@dataclass(frozen=True)
class WorkflowStepPolicy:
    path: str
    name: str
    expected_lines: tuple[str, ...]


WORKFLOW_STEP_POLICIES = (
    WorkflowStepPolicy(
        CI_WORKFLOW_PATH,
        "Supply-chain static policy",
        (
            "- name: Supply-chain static policy",
            "  run: python .agents/validation/check_supply_chain_policy.py",
        ),
    ),
    WorkflowStepPolicy(
        CI_WORKFLOW_PATH,
        "Generate deterministic universal SBOM inputs",
        (
            "- name: Generate deterministic universal SBOM inputs",
            "  run: |",
            *(f"    {command}" for command in SBOM_GENERATOR_COMMANDS),
        ),
    ),
    WorkflowStepPolicy(
        CI_WORKFLOW_PATH,
        "Audit reviewed Python vulnerabilities",
        (
            "- name: Audit reviewed Python vulnerabilities",
            "  run: python scripts/audit_supply_chain.py vulnerabilities "
            "--output build/validation/supply-chain/python-vulnerabilities.json",
        ),
    ),
    WorkflowStepPolicy(
        CI_WORKFLOW_PATH,
        "Upload universal supply-chain evidence",
        (
            "- name: Upload universal supply-chain evidence",
            "  if: always()",
            "  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
            "  with:",
            "    name: mclab-supply-chain-universal",
            "    path: |",
            "      /tmp/mclab-sbom-inputs-1.json",
            "      build/validation/supply-chain/python-vulnerabilities.json",
            "    if-no-files-found: error",
            "    retention-days: 14",
        ),
    ),
    WorkflowStepPolicy(
        DESKTOP_WORKFLOW_PATH,
        "Install pinned Linux Qt runtime libraries",
        (
            "- name: Install pinned Linux Qt runtime libraries",
            "  if: runner.os == 'Linux'",
            "  run: |",
            "    mkdir -p build/validation/supply-chain-Linux",
            "    sudo /usr/bin/python3 scripts/install_ubuntu_system_packages.py --install "
            "--output build/validation/supply-chain-Linux/ubuntu-system-packages.json",
        ),
    ),
    WorkflowStepPolicy(
        DESKTOP_WORKFLOW_PATH,
        "Install desktop, test, and packaging dependencies",
        (
            "- name: Install desktop, test, and packaging dependencies",
            "  run: python scripts/install_locked.py --allow-external-env package",
        ),
    ),
    WorkflowStepPolicy(
        DESKTOP_WORKFLOW_PATH,
        "Select package-profile Python",
        (
            "- name: Select package-profile Python",
            "  shell: bash",
            '  run: echo "MCLAB_PACKAGE_PYTHON=$(python -c \'import sys; print(sys.executable)\')" >> "$GITHUB_ENV"',
        ),
    ),
    WorkflowStepPolicy(
        DESKTOP_WORKFLOW_PATH,
        "Audit package-profile licenses",
        (
            "- name: Audit package-profile licenses",
            "  shell: bash",
            '  run: python scripts/audit_supply_chain.py licenses --target-python "$MCLAB_PACKAGE_PYTHON" '
            "--profile package --output "
            "build/validation/supply-chain-${RUNNER_OS}/python-licenses.json",
        ),
    ),
    WorkflowStepPolicy(
        DESKTOP_WORKFLOW_PATH,
        "Upload target supply-chain evidence",
        (
            "- name: Upload target supply-chain evidence",
            "  if: always()",
            "  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
            "  with:",
            "    name: mclab-supply-chain-${{ runner.os }}",
            "    path: build/validation/supply-chain-${{ runner.os }}",
            "    if-no-files-found: error",
            "    retention-days: 14",
        ),
    ),
)

WORKFLOW_STEP_ORDER = {
    CI_WORKFLOW_PATH: (
        "Supply-chain static policy",
        "Generate deterministic universal SBOM inputs",
        "Audit reviewed Python vulnerabilities",
        "Upload universal supply-chain evidence",
    ),
    DESKTOP_WORKFLOW_PATH: (
        "Install pinned Linux Qt runtime libraries",
        "Install desktop, test, and packaging dependencies",
        "Select package-profile Python",
        "Audit package-profile licenses",
        "Upload target supply-chain evidence",
    ),
}
WORKFLOW_REQUIRED_JOBS = {
    CI_WORKFLOW_PATH: "simulator",
    DESKTOP_WORKFLOW_PATH: "desktop",
}
WORKFLOW_JOB_HEADER_LINES = {
    CI_WORKFLOW_PATH: (
        "simulator:",
        "  name: Simulator lint and tests",
        "  runs-on: ubuntu-latest",
        "  env:",
        "    MPLBACKEND: Agg",
        "  steps:",
    ),
    DESKTOP_WORKFLOW_PATH: (
        "desktop:",
        "  name: Unsigned development build (${{ matrix.os }})",
        "  strategy:",
        "    fail-fast: false",
        "    matrix:",
        "      os: [windows-2025, ubuntu-24.04, macos-15]",
        "  runs-on: ${{ matrix.os }}",
        "  env:",
        "    QT_QPA_PLATFORM: offscreen",
        "    MPLBACKEND: Agg",
        "  steps:",
    ),
}


def _exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label}: expected object")
        return False
    if set(value) != expected:
        errors.append(f"{label}: keys must be {sorted(expected)}")
        return False
    return True


def _is_sorted_unique(values: object) -> bool:
    if not isinstance(values, list):
        return False
    try:
        return values == sorted(values) and len(values) == len(set(values))
    except (TypeError, ValueError):
        return False


def strict_json_bytes(payload: bytes, label: str = "JSON") -> dict[str, object]:
    """Parse one UTF-8 JSON object while rejecting duplicate keys and non-finite values."""

    try:
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=sbom._pairs_without_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite number {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise sbom.SupplyChainInputError(f"MALFORMED_JSON {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise sbom.SupplyChainInputError(f"MALFORMED_JSON {label}: root must be an object")
    return value


def schema_policy_errors(root: Path) -> list[str]:
    """Return errors for drift or weakening of the reviewed schema contract."""

    errors: list[str] = []
    try:
        record = sbom.source_record(root, sbom.SCHEMA_PATH)
        schema = sbom.strict_json(root, sbom.SCHEMA_PATH)
    except sbom.SupplyChainInputError as exc:
        return [str(exc)]
    if record["sha256"] != EXPECTED_SCHEMA_SHA256:
        errors.append(f"{sbom.SCHEMA_PATH}: reviewed schema SHA-256 drift")
    required = schema.get("required")
    properties = schema.get("properties")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"{sbom.SCHEMA_PATH}: draft-2020-12 declaration required")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append(f"{sbom.SCHEMA_PATH}: closed object root required")
    if not isinstance(required, list) or set(required) != TOP_LEVEL_KEYS:
        errors.append(f"{sbom.SCHEMA_PATH}: exact top-level required list drift")
    if not isinstance(properties, dict) or set(properties) != TOP_LEVEL_KEYS:
        errors.append(f"{sbom.SCHEMA_PATH}: exact top-level properties drift")
    return errors


def _source_record_errors(record: object, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return [f"{label}: expected source record"]
    if not SOURCE_KEYS.issubset(record):
        errors.append(f"{label}: missing source-record keys")
        return errors
    path = record.get("path")
    digest = record.get("sha256")
    size = record.get("size")
    if (
        not isinstance(path, str)
        or not path
        or PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        or PurePosixPath(path).as_posix() != path
    ):
        errors.append(f"{label}: unsafe source path")
    if not isinstance(digest, str) or sbom.SHA256_RE.fullmatch(digest) is None:
        errors.append(f"{label}: invalid SHA-256")
    if type(size) is not int or size < 0:
        errors.append(f"{label}: invalid byte size")
    return errors


def _closed_source_record_errors(
    record: object,
    label: str,
    *,
    extra_keys: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected = SOURCE_KEYS | (extra_keys or set())
    if not _exact_keys(record, expected, label, errors):
        return errors
    errors.extend(_source_record_errors(record, label))
    return errors


def _expected_environments() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for platform_name, machine in sbom.TARGET_PLATFORM_CELLS:
        for version in sbom.TARGET_PYTHON_VERSIONS:
            records.append(
                {
                    "id": f"cpython-{version}-{platform_name}-{machine.lower()}",
                    "implementation_name": "cpython",
                    "marker": (
                        "implementation_name == 'cpython' and "
                        f"python_version == '{version}' and "
                        f"sys_platform == '{platform_name}' and "
                        f"platform_machine == '{machine}'"
                    ),
                    "platform_machine": machine,
                    "platform_python_implementation": "CPython",
                    "python_full_version": f"{version}.0",
                    "python_version": version,
                    "sys_platform": platform_name,
                }
            )
    return sorted(records, key=lambda item: item["id"])


def _requirement_errors(
    requirement: object,
    label: str,
    environments: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(requirement, REQUIREMENT_KEYS, label, errors):
        return errors
    assert isinstance(requirement, dict)
    name = requirement.get("name")
    version = requirement.get("version")
    marker = requirement.get("marker")
    hashes = requirement.get("hashes")
    environment_ids = requirement.get("environment_ids")
    if not isinstance(name, str) or not name or sbom._normalise_name(name) != name:
        errors.append(f"{label}: normalized package name required")
    if not isinstance(version, str) or not version:
        errors.append(f"{label}: exact version required")
    if marker is not None and not isinstance(marker, str):
        errors.append(f"{label}: marker must be a string or null")
    if not _is_sorted_unique(hashes) or not hashes:
        errors.append(f"{label}: hashes must be nonempty, sorted, and unique")
    elif any(not isinstance(value, str) or sbom.SHA256_RE.fullmatch(value) is None for value in hashes):
        errors.append(f"{label}: every hash must be lowercase SHA-256")
    if requirement.get("hash_scope") != sbom.HASH_SCOPE:
        errors.append(f"{label}: wheel hashes must not claim environment mapping")
    expected_ids: list[str] = []
    if marker is None or isinstance(marker, str):
        try:
            expected_ids = [
                environment["id"]
                for environment in environments
                if marker is None
                or sbom._marker_applies(
                    marker,
                    {key: value for key, value in environment.items() if key != "id"},
                )
            ]
        except sbom.SupplyChainInputError as exc:
            errors.append(f"{label}: unsupported marker: {exc}")
    if not expected_ids:
        errors.append(f"{label}: marker applies to zero reviewed target cells")
    if environment_ids != sorted(expected_ids):
        errors.append(f"{label}: environment marker membership is inaccurate")
    extras = requirement.get("extras")
    if not _is_sorted_unique(extras):
        errors.append(f"{label}: extras must be sorted and unique")
    return errors


def document_policy_errors(document: object, expected: object | None = None) -> list[str]:
    """Validate ordering, uniqueness, exact keys, and immutable reviewed identities."""

    errors: list[str] = []
    if not _exact_keys(document, TOP_LEVEL_KEYS, "document", errors):
        return errors
    assert isinstance(document, dict)
    if document.get("schema_version") != sbom.SCHEMA_VERSION:
        errors.append("document: schema_version must equal 1")
    source_commit = document.get("source_commit")
    if not isinstance(source_commit, str) or sbom.COMMIT_RE.fullmatch(source_commit) is None:
        errors.append("document: source_commit must be lowercase 40-hex")

    contract = document.get("contract")
    if _exact_keys(contract, {"generator", "schema"}, "contract", errors):
        assert isinstance(contract, dict)
        errors.extend(_closed_source_record_errors(contract["generator"], "contract.generator"))
        errors.extend(_closed_source_record_errors(contract["schema"], "contract.schema"))

    project = document.get("project")
    project_keys = {*sbom.EXPECTED_PROJECT, "source"}
    if _exact_keys(project, project_keys, "project", errors):
        assert isinstance(project, dict)
        if {key: project[key] for key in sbom.EXPECTED_PROJECT} != sbom.EXPECTED_PROJECT:
            errors.append("project: reviewed identity drift")
        errors.extend(_closed_source_record_errors(project["source"], "project.source"))

    environments = document.get("target_environments")
    reviewed_environments = _expected_environments()
    if environments != reviewed_environments:
        errors.append("target_environments: exact sorted 12-cell contract required")
    if isinstance(environments, list):
        for index, environment in enumerate(environments):
            _exact_keys(environment, ENVIRONMENT_KEYS, f"target_environments[{index}]", errors)
    environment_values = reviewed_environments

    profiles = document.get("python_lock_profiles")
    expected_profile_ids = sorted(profile.identifier for profile in sbom.LOCK_PROFILES)
    if not isinstance(profiles, list) or len(profiles) != len(expected_profile_ids):
        errors.append("python_lock_profiles: exactly eight profiles required")
    else:
        profile_ids = [profile.get("id") if isinstance(profile, dict) else None for profile in profiles]
        if profile_ids != expected_profile_ids or not _is_sorted_unique(profile_ids):
            errors.append("python_lock_profiles: records must be sorted and unique")
        profile_contracts = {profile.identifier: profile for profile in sbom.LOCK_PROFILES}
        for profile_index, profile in enumerate(profiles):
            label = f"python_lock_profiles[{profile_index}]"
            if not _exact_keys(profile, PROFILE_KEYS, label, errors):
                continue
            assert isinstance(profile, dict)
            identifier = profile.get("id")
            contract = profile_contracts.get(identifier) if isinstance(identifier, str) else None
            if contract is None:
                errors.append(f"{label}: unknown profile")
            elif profile.get("extras") != list(contract.extras):
                errors.append(f"{label}: profile extras drift")
            errors.extend(_closed_source_record_errors(profile["source"], f"{label}.source"))
            errors.extend(_closed_source_record_errors(profile["lock"], f"{label}.lock"))
            requirements = profile.get("requirements")
            if not isinstance(requirements, list) or not requirements:
                errors.append(f"{label}: nonempty requirements required")
                continue
            names = [item.get("name") if isinstance(item, dict) else None for item in requirements]
            if not _is_sorted_unique(names):
                errors.append(f"{label}: requirements must be sorted and unique")
            for index, requirement in enumerate(requirements):
                errors.extend(
                    _requirement_errors(requirement, f"{label}.requirements[{index}]", environment_values)
                )

    actions = document.get("github_actions")
    expected_actions = [
        {"name": name, **record} for name, record in sorted(sbom.EXPECTED_ACTIONS.items())
    ]
    action_keys = {"actions", "minimum_actions_runner", "policy", "source"}
    if _exact_keys(actions, action_keys, "github_actions", errors):
        assert isinstance(actions, dict)
        action_records = actions["actions"]
        if action_records != expected_actions:
            errors.append("github_actions: reviewed immutable Action lock drift")
        if isinstance(action_records, list):
            for index, action in enumerate(action_records):
                _exact_keys(action, ACTION_KEYS, f"github_actions.actions[{index}]", errors)
        if (
            actions["minimum_actions_runner"] != "2.327.1"
            or actions["policy"] != sbom.EXPECTED_ACTION_POLICY
        ):
            errors.append("github_actions: reviewed policy metadata drift")
        errors.extend(_closed_source_record_errors(actions["source"], "github_actions.source"))

    panda = document.get("panda_runtime")
    panda_keys = {
        "archive_sha256",
        "commit",
        "files",
        "license",
        "source",
        "upstream_repository",
    }
    if _exact_keys(panda, panda_keys, "panda_runtime", errors):
        assert isinstance(panda, dict)
        files = panda.get("files")
        file_records = files if isinstance(files, list) else []
        paths = [record.get("path") if isinstance(record, dict) else None for record in file_records]
        sizes = [record.get("size") if isinstance(record, dict) else None for record in file_records]
        if (
            panda.get("commit") != sbom.EXPECTED_PANDA_COMMIT
            or panda.get("archive_sha256") != sbom.EXPECTED_PANDA_ARCHIVE_SHA256
            or not isinstance(files, list)
            or len(files) != sbom.EXPECTED_PANDA_FILE_COUNT
            or not _is_sorted_unique(paths)
            or any(type(size) is not int for size in sizes)
            or sum(sizes) != sbom.EXPECTED_PANDA_TOTAL_BYTES
        ):
            errors.append("panda_runtime: reviewed commit/archive/72-file manifest drift")
        for index, record in enumerate(file_records):
            errors.extend(_closed_source_record_errors(record, f"panda_runtime.files[{index}]"))
        expected_license = {
            "path": sbom.EXPECTED_PANDA_LICENSE[0],
            "sha256": sbom.EXPECTED_PANDA_LICENSE[2],
            "size": sbom.EXPECTED_PANDA_LICENSE[1],
            "spdx": "Apache-2.0",
        }
        if panda["license"] != expected_license:
            errors.append("panda_runtime.license: reviewed license record drift")
        _exact_keys(
            panda["license"],
            SOURCE_KEYS | {"spdx"},
            "panda_runtime.license",
            errors,
        )
        errors.extend(_closed_source_record_errors(panda["source"], "panda_runtime.source"))
        if panda["upstream_repository"] != "https://github.com/google-deepmind/mujoco_menagerie":
            errors.append("panda_runtime: upstream repository drift")

    fonts = document.get("fonts")
    expected_font_ids = sorted(value[0] for value in sbom.EXPECTED_FONT_FILES)
    font_files = fonts.get("files", []) if isinstance(fonts, dict) else []
    font_ids = [item.get("id") if isinstance(item, dict) else None for item in font_files]
    if _exact_keys(fonts, {"files", "license"}, "fonts", errors):
        assert isinstance(fonts, dict)
        if font_ids != expected_font_ids or len(font_files) != 2:
            errors.append("fonts: exact two-font inventory required")
        expected_fonts = {
            identifier: (path, digest)
            for identifier, path, digest in sbom.EXPECTED_FONT_FILES
        }
        for index, record in enumerate(font_files):
            label = f"fonts.files[{index}]"
            errors.extend(_closed_source_record_errors(record, label, extra_keys={"id"}))
            if isinstance(record, dict):
                expected_font = expected_fonts.get(record.get("id"))
                if expected_font != (record.get("path"), record.get("sha256")):
                    errors.append(f"{label}: reviewed path/hash drift")
        errors.extend(
            _closed_source_record_errors(fonts["license"], "fonts.license", extra_keys={"id", "spdx"})
        )
        expected_font_license = sbom.EXPECTED_FONT_LICENSE
        license_record = fonts["license"]
        if not isinstance(license_record, dict) or (
            license_record.get("id"),
            license_record.get("spdx"),
            license_record.get("path"),
            license_record.get("sha256"),
        ) != ("noto-ofl-1.1", "OFL-1.1", *expected_font_license):
            errors.append("fonts.license: reviewed OFL record drift")

    ubuntu = document.get("ubuntu_system")
    expected_packages = [
        {"name": name, "version": version} for name, version in sbom.EXPECTED_UBUNTU_PACKAGES
    ]
    ubuntu_keys = {"distribution", "ecosystem", "installer", "packages", "snapshot", "source"}
    if _exact_keys(ubuntu, ubuntu_keys, "ubuntu_system", errors):
        assert isinstance(ubuntu, dict)
        if (
            ubuntu["distribution"] != sbom.EXPECTED_UBUNTU_DISTRIBUTION
            or ubuntu["ecosystem"] != "apt"
            or ubuntu["snapshot"] != sbom.EXPECTED_UBUNTU_SNAPSHOT
            or ubuntu["packages"] != expected_packages
        ):
            errors.append("ubuntu_system: reviewed sorted package manifest drift")
        _exact_keys(
            ubuntu["distribution"],
            {"architecture", "codename", "id", "version_id"},
            "ubuntu_system.distribution",
            errors,
        )
        if isinstance(ubuntu["packages"], list):
            for index, package in enumerate(ubuntu["packages"]):
                _exact_keys(package, {"name", "version"}, f"ubuntu_system.packages[{index}]", errors)
        errors.extend(_closed_source_record_errors(ubuntu["installer"], "ubuntu_system.installer"))
        errors.extend(_closed_source_record_errors(ubuntu["source"], "ubuntu_system.source"))

    packaging = document.get("packaging")
    expected_groups = [
        {key: value for key, value in group.items() if key != "expression"}
        for group in sbom.EXPECTED_PACKAGING_DATA_GROUPS
    ]
    expected_groups.sort(key=lambda item: str(item["id"]))
    if _exact_keys(packaging, {"data_groups", "root_licenses", "source"}, "packaging", errors):
        assert isinstance(packaging, dict)
        if packaging["data_groups"] != expected_groups:
            errors.append("packaging: exact sorted data groups drift")
        if isinstance(packaging["data_groups"], list):
            for index, group in enumerate(packaging["data_groups"]):
                _exact_keys(
                    group,
                    {"destination", "id", "license_ids", "source"},
                    f"packaging.data_groups[{index}]",
                    errors,
                )
        root_licenses = packaging["root_licenses"]
        if not isinstance(root_licenses, list) or len(root_licenses) != 1:
            errors.append("packaging.root_licenses: exactly one root license required")
        else:
            root_license = root_licenses[0]
            errors.extend(
                _closed_source_record_errors(
                    root_license,
                    "packaging.root_licenses[0]",
                    extra_keys={"id", "spdx"},
                )
            )
            if not isinstance(root_license, dict) or (
                root_license.get("id"),
                root_license.get("spdx"),
                root_license.get("path"),
                root_license.get("sha256"),
            ) != (
                "project-apache-2.0",
                "Apache-2.0",
                sbom.PROJECT_LICENSE_PATH,
                sbom.EXPECTED_PROJECT_LICENSE_SHA256,
            ):
                errors.append("packaging.root_licenses: reviewed Apache-2.0 license drift")
        errors.extend(_closed_source_record_errors(packaging["source"], "packaging.source"))

    vulnerability = document.get("vulnerability_policy")
    vulnerability_keys = {"auditor", "waiver_source", "waivers"}
    if _exact_keys(vulnerability, vulnerability_keys, "vulnerability_policy", errors):
        assert isinstance(vulnerability, dict)
        if vulnerability["waivers"] != []:
            errors.append("vulnerability_policy: waivers must be empty")
        errors.extend(
            _closed_source_record_errors(vulnerability["auditor"], "vulnerability_policy.auditor")
        )
        errors.extend(
            _closed_source_record_errors(
                vulnerability["waiver_source"], "vulnerability_policy.waiver_source"
            )
        )
    if expected is not None and document != expected:
        errors.append("document: generated content differs from reviewed source-derived contract")
    return errors


def represented_source_errors(root: Path, document: dict[str, object]) -> list[str]:
    """Verify every represented repository source against current safe file bytes."""

    errors: list[str] = []
    try:
        records = sbom.represented_repository_records(document)
    except (KeyError, TypeError) as exc:
        return [f"represented sources: malformed document: {exc}"]
    paths: list[str] = []
    for index, record in enumerate(records):
        errors.extend(_source_record_errors(record, f"represented source {index}"))
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            continue
        path = record["path"]
        paths.append(path)
        try:
            actual = sbom.source_record(root, path)
        except sbom.SupplyChainInputError as exc:
            errors.append(str(exc))
            continue
        if {key: record.get(key) for key in SOURCE_KEYS} != actual:
            errors.append(f"represented source {path}: hash/size drift")
    if set(paths) != set(sbom.INPUT_PATHS):
        errors.append(
            "represented sources: explicit allowlist mismatch "
            f"missing={sorted(set(sbom.INPUT_PATHS) - set(paths))} "
            f"extra={sorted(set(paths) - set(sbom.INPUT_PATHS))}"
        )
    return errors


def workflow_step_blocks(text: str) -> list[str]:
    """Return every physical step block from one reviewed job."""

    lines = text.replace("\r\n", "\n").splitlines()
    steps_lines = [
        index for index, line in enumerate(lines) if re.fullmatch(r"\s{4}steps:\s*", line)
    ]
    if len(steps_lines) != 1:
        return []
    steps_line = steps_lines[0]
    step_starts: list[int] = []
    for index, line in enumerate(lines):
        if index > steps_line and re.match(r"^ {6}-\s+", line):
            step_starts.append(index)
    return [
        "\n".join(lines[start : step_starts[position + 1]])
        if position + 1 < len(step_starts)
        else "\n".join(lines[start:])
        for position, start in enumerate(step_starts)
    ]


def workflow_step_name(block: str) -> str | None:
    """Return a step name even when the YAML key or scalar is quoted."""

    for index, line in enumerate(block.splitlines()):
        pattern = (
            r"^ {6}-\s+[\"']?name[\"']?\s*:\s*(?P<name>.*?)\s*$"
            if index == 0
            else r"^ {8}[\"']?name[\"']?\s*:\s*(?P<name>.*?)\s*$"
        )
        match = re.fullmatch(pattern, line)
        if match is None:
            continue
        name = match.group("name").split("#", 1)[0].strip()
        if len(name) >= 2 and name[0] == name[-1] and name[0] in {"'", '"'}:
            name = name[1:-1].strip()
        return name or None
    return None


def named_workflow_step_blocks(text: str) -> dict[str, list[str]]:
    """Group all physical job steps by their optional name."""

    blocks: dict[str, list[str]] = {}
    for block in workflow_step_blocks(text):
        name = workflow_step_name(block)
        if name is not None:
            blocks.setdefault(name, []).append(block)
    return blocks


def workflow_job_block(text: str, job_name: str) -> str | None:
    """Return one exact two-space-indented workflow job block."""

    headers = list(
        re.finditer(
            r"(?m)^  (?P<name>[A-Za-z0-9_-]+):\s*(?:#.*)?$",
            text,
        )
    )
    matches = [header for header in headers if header.group("name") == job_name]
    if len(matches) != 1:
        return None
    start = matches[0].start()
    following = [header.start() for header in headers if header.start() > start]
    return text[start : min(following, default=len(text))]


def workflow_job_weakening(job: str, workflow: str) -> tuple[str, ...]:
    weakening = [
        key
        for key in ("if", "continue-on-error", "needs", "defaults")
        if re.search(rf"(?m)^    [\"']?{re.escape(key)}[\"']?\s*:", job)
    ]
    if re.search(r"(?m)^[\"']?defaults[\"']?\s*:", workflow):
        weakening.append("workflow defaults")
    return tuple(weakening)


def normalized_workflow_job_header_lines(job: str) -> tuple[str, ...]:
    """Return the active job header through its single steps declaration."""

    header: list[str] = []
    for line in job.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        header.append(line.rstrip())
        if re.fullmatch(r"\s{4}steps:\s*", line):
            break
    if not header or not re.fullmatch(r"\s{4}steps:\s*", header[-1]):
        return ()
    base_indent = len(header[0]) - len(header[0].lstrip())
    return tuple(line[base_indent:] for line in header)


def workflow_block_commands(block: str) -> list[str]:
    """Return active commands from a named workflow step's sole run field."""

    physical = block.splitlines()
    commands: list[str] = []
    run_fields = 0
    for index, line in enumerate(physical):
        match = re.fullmatch(r"(?P<indent>\s*)run:\s*(?P<value>.*?)\s*", line)
        if match is None:
            continue
        run_fields += 1
        value = match.group("value")
        if value not in {"|", "|-", ">", ">-"}:
            commands.append(value)
            continue
        indent = len(match.group("indent"))
        children: list[str] = []
        for child in physical[index + 1 :]:
            if child.strip() and len(child) - len(child.lstrip()) <= indent:
                break
            if child.strip() and not child.lstrip().startswith("#"):
                children.append(child.strip())
        if value.startswith(">"):
            commands.append(" ".join(children))
            continue
        continued = ""
        for child in children:
            if child.endswith("\\"):
                continued += child[:-1].rstrip() + " "
            else:
                commands.append(continued + child)
                continued = ""
        if continued:
            commands.append(continued.rstrip())
    return commands if run_fields == 1 else []


def workflow_block_has_exact_line(block: str, fragment: str) -> bool:
    """Require an active exact YAML field or run-command line, never a comment/echo."""

    active = [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if fragment.startswith(("if:", "shell:")):
        return active.count(fragment) == 1
    return workflow_block_commands(block).count(fragment) == 1


def normalized_workflow_block_lines(block: str) -> tuple[str, ...]:
    """Normalize a step's base indent while preserving its exact YAML structure."""

    active = [
        line.rstrip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not active:
        return ()
    base_indent = len(active[0]) - len(active[0].lstrip())
    if any(len(line) - len(line.lstrip()) < base_indent for line in active):
        return ()
    return tuple(line[base_indent:] for line in active)


def workflow_policy_errors(root: Path) -> list[str]:
    """Require exact fail-closed steps, including evidence uploads, in both workflows."""

    errors: list[str] = []
    by_path: dict[str, dict[str, list[str]]] = {}
    physical_by_path: dict[str, list[str]] = {}
    for path in sorted({policy.path for policy in WORKFLOW_STEP_POLICIES}):
        try:
            workflow = sbom.read_text(root, path)
        except sbom.SupplyChainInputError as exc:
            errors.append(str(exc))
            continue
        job_name = WORKFLOW_REQUIRED_JOBS[path]
        job = workflow_job_block(workflow, job_name)
        if job is None:
            errors.append(f"{path}: exactly one required job {job_name!r} must exist")
            continue
        if normalized_workflow_job_header_lines(job) != WORKFLOW_JOB_HEADER_LINES[path]:
            errors.append(
                f"{path}:{job_name}: job matrix, runner, name, environment, and steps header "
                "must exactly match the reviewed contract"
            )
        weakening = workflow_job_weakening(job, workflow)
        if weakening:
            errors.append(
                f"{path}:{job_name}: required supply-chain job is weakened by {list(weakening)}"
            )
        physical_by_path[path] = workflow_step_blocks(job)
        by_path[path] = named_workflow_step_blocks(job)
    for policy in WORKFLOW_STEP_POLICIES:
        blocks = by_path.get(policy.path, {}).get(policy.name, [])
        if len(blocks) != 1:
            errors.append(f"{policy.path}: exactly one step named {policy.name!r} required")
            continue
        block = blocks[0]
        actual_lines = normalized_workflow_block_lines(block)
        if actual_lines != policy.expected_lines:
            errors.append(
                f"{policy.path}:{policy.name}: step must exactly match reviewed fail-closed YAML"
            )
    for path, expected_order in WORKFLOW_STEP_ORDER.items():
        actual_names = [
            workflow_step_name(block) for block in physical_by_path.get(path, [])
        ]
        duplicate_names = sorted(
            {
                name
                for name in actual_names
                if name is not None and actual_names.count(name) > 1
            }
        )
        if duplicate_names:
            errors.append(f"{path}: duplicate named steps are forbidden: {duplicate_names}")
        try:
            positions = [actual_names.index(name) for name in expected_order]
        except ValueError:
            continue
        expected_positions = list(range(positions[0], positions[0] + len(positions)))
        if positions != expected_positions:
            errors.append(
                f"{path}: supply-chain steps must remain contiguous and in reviewed order "
                f"{list(expected_order)}"
            )
    return errors


def validate_repository(
    root: Path,
    source_commit: str,
    *,
    check_workflows: bool = True,
    bind_to_checkout: bool = True,
) -> tuple[dict[str, object] | None, list[str]]:
    """Generate twice, require byte identity, and verify all static policy inputs."""

    errors = schema_policy_errors(root)
    try:
        first = sbom.build_document(
            root, source_commit, bind_to_checkout=bind_to_checkout
        )
        first_bytes = sbom.canonical_json_bytes(first)
        second = sbom.build_document(
            root, source_commit, bind_to_checkout=bind_to_checkout
        )
        second_bytes = sbom.canonical_json_bytes(second)
        if first_bytes != second_bytes:
            errors.append("determinism: two generations were not byte-identical")
        parsed = strict_json_bytes(first_bytes, "generated SBOM inputs")
        if sbom.canonical_json_bytes(parsed) != first_bytes:
            errors.append("generated SBOM inputs: JSON is not canonical sorted JSON")
        errors.extend(document_policy_errors(parsed, first))
        errors.extend(represented_source_errors(root, parsed))
    except (OSError, sbom.SupplyChainInputError) as exc:
        errors.append(str(exc))
        first = None
    if check_workflows:
        errors.extend(workflow_policy_errors(root))
    return first, errors


def _git_source_commit(root: Path) -> str:
    return sbom.git_checkout_commit(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-commit",
        help="Lowercase 40-hex source SHA (defaults to the checked-out HEAD)",
    )
    args = parser.parse_args(argv)
    try:
        source_commit = args.source_commit or _git_source_commit(ROOT)
        document, errors = validate_repository(ROOT, source_commit)
    except sbom.SupplyChainInputError as exc:
        document, errors = None, [str(exc)]
    if errors:
        print("Supply-chain static policy: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    assert document is not None
    requirements = sum(len(profile["requirements"]) for profile in document["python_lock_profiles"])
    hashes = sum(
        len(requirement["hashes"])
        for profile in document["python_lock_profiles"]
        for requirement in profile["requirements"]
    )
    print(
        "Supply-chain static policy: PASS "
        f"(8 profiles, {requirements} requirements, {hashes} hashes, 12 environments)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
