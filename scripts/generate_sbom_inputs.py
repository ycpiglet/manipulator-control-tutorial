"""Generate deterministic, reviewed inputs for downstream SBOM tooling.

This module intentionally reads only the files named in ``INPUT_PATHS``.  It
does not walk the repository, resolve dependencies, download metadata, or
claim that a wheel hash belongs to a particular target environment.  The
environment lists attached to locked requirements are marker-membership only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 16 * 1024 * 1024
HASH_SCOPE = "candidate-artifacts-not-mapped-to-environments"
GIT_TIMEOUT_SECONDS = 15

SCHEMA_PATH = ".agents/supply_chain/sbom-inputs.schema.json"
GENERATOR_PATH = "scripts/generate_sbom_inputs.py"
WAIVER_PATH = ".agents/supply_chain/vulnerability-waivers.json"
AUDITOR_PATH = "scripts/audit_supply_chain.py"
UBUNTU_MANIFEST_PATH = "requirements/system/ubuntu-24.04-amd64.json"
UBUNTU_INSTALLER_PATH = "scripts/install_ubuntu_system_packages.py"
ACTIONS_LOCK_PATH = ".github/actions-lock.json"
PANDA_MANIFEST_PATH = "src/mclab/application/panda_runtime_manifest.py"
PACKAGING_SPEC_PATH = "packaging/mclab.spec"
PROJECT_PATH = "pyproject.toml"
PROJECT_LICENSE_PATH = "LICENSE"

SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
REQUIREMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9,_.-]+)\])?=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
HASH_TOKEN_RE = re.compile(r"--hash=sha256:(?P<digest>[0-9a-f]{64})")
MARKER_CONDITION_RE = re.compile(
    r"(?P<variable>python_full_version|python_version|implementation_name|"
    r"platform_machine|platform_python_implementation|sys_platform)\s*"
    r"(?P<operator><=|>=|==|!=|<|>)\s*'(?P<value>[^']+)'"
)


class SupplyChainInputError(RuntimeError):
    """Raised when a reviewed source input cannot be represented safely."""


class DuplicateJsonKeyError(ValueError):
    """Raised when JSON repeats an object key."""


@dataclass(frozen=True)
class LockProfile:
    identifier: str
    source_path: str
    lock_path: str
    extras: tuple[str, ...] = ()


LOCK_PROFILES = (
    LockProfile("uv-tool", "requirements/tools/uv.in", "requirements/tools/uv.txt"),
    LockProfile("build", "requirements/build.in", "requirements/locks/build.txt"),
    LockProfile("runtime", PROJECT_PATH, "requirements/locks/runtime.txt"),
    LockProfile("app", PROJECT_PATH, "requirements/locks/app.txt", ("app",)),
    LockProfile("dev", PROJECT_PATH, "requirements/locks/dev.txt", ("dev",)),
    LockProfile("app-dev", PROJECT_PATH, "requirements/locks/app-dev.txt", ("app", "dev")),
    LockProfile(
        "package",
        PROJECT_PATH,
        "requirements/locks/package.txt",
        ("app", "dev", "package"),
    ),
    LockProfile(
        "supply-chain-tool",
        "requirements/tools/supply-chain.in",
        "requirements/tools/supply-chain.txt",
    ),
)

TARGET_PLATFORM_CELLS = (
    ("linux", "x86_64"),
    ("win32", "AMD64"),
    ("darwin", "arm64"),
    ("darwin", "x86_64"),
)
TARGET_PYTHON_VERSIONS = ("3.10", "3.11", "3.12")
EXPECTED_TARGET_MARKERS = tuple(
    "implementation_name == 'cpython' and "
    f"python_version == '{version}' and "
    f"sys_platform == '{platform}' and platform_machine == '{machine}'"
    for platform, machine in TARGET_PLATFORM_CELLS
    for version in TARGET_PYTHON_VERSIONS
)

EXPECTED_PROJECT = {
    "license": "Apache-2.0",
    "name": "mujoco-manipulator-control-lab",
    "requires_python": ">=3.10,<3.13",
    "version": "0.1.0",
}
EXPECTED_ACTION_POLICY = {
    "require_full_commit_sha": True,
    "require_release_comment": True,
    "required_runtime": "node24",
}
EXPECTED_ACTIONS = {
    "WtfJoke/setup-tectonic": {
        "release": "v4.0.5",
        "runtime": "node24",
        "sha": "eb29fd68b7d3f76011906b6e45ea4320c8de5d2f",
        "source": "https://github.com/WtfJoke/setup-tectonic/releases/tag/v4.0.5",
        "upstream_commit_verified": True,
    },
    "actions/checkout": {
        "release": "v7.0.1",
        "runtime": "node24",
        "sha": "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "source": "https://github.com/actions/checkout/releases/tag/v7.0.1",
        "upstream_commit_verified": True,
    },
    "actions/setup-python": {
        "release": "v7.0.0",
        "runtime": "node24",
        "sha": "5fda3b95a4ea91299a34e894583c3862153e4b97",
        "source": "https://github.com/actions/setup-python/releases/tag/v7.0.0",
        "upstream_commit_verified": True,
    },
    "actions/upload-artifact": {
        "release": "v7.0.1",
        "runtime": "node24",
        "sha": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "source": "https://github.com/actions/upload-artifact/releases/tag/v7.0.1",
        "upstream_commit_verified": True,
    },
}

EXPECTED_PANDA_SOURCE_SHA256 = (
    "41d476063ef9c5aab6d86ee915b2b907ede5743b7c067b3a0aea34c9c978eb36"
)
EXPECTED_PANDA_COMMIT = "71f066ad0be9cd271f7ed58c030243ef157af9f4"
EXPECTED_PANDA_ARCHIVE_SHA256 = (
    "000b9f51abb404efb1de2b88b3c738674c472a85b6c4143168859abc4c98d423"
)
EXPECTED_PANDA_FILE_COUNT = 72
EXPECTED_PANDA_TOTAL_BYTES = 34_333_936
EXPECTED_PANDA_LICENSE = (
    "LICENSE",
    10_173,
    "a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9",
)

EXPECTED_FONT_FILES = (
    (
        "noto-sans-kr-variable",
        "third_party/fonts/noto/NotoSansKR[wght].ttf",
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
    ),
    (
        "noto-sans-mono-variable",
        "third_party/fonts/noto/NotoSansMono[wdth,wght].ttf",
        "2cb2adb378a8f574213e23df697050b83c54c27df465a2015552740b2769a081",
    ),
)
EXPECTED_FONT_LICENSE = (
    "third_party/fonts/noto/OFL.txt",
    "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
)
EXPECTED_PROJECT_LICENSE_SHA256 = (
    "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
)

EXPECTED_UBUNTU_DISTRIBUTION = {
    "architecture": "amd64",
    "codename": "noble",
    "id": "ubuntu",
    "version_id": "24.04",
}
EXPECTED_UBUNTU_SNAPSHOT = "20260723T000000Z"
EXPECTED_UBUNTU_PACKAGES = (
    ("libdbus-1-3", "1.14.10-4ubuntu4.1"),
    ("libegl1", "1.7.0-1build1"),
    ("libfontconfig1", "2.15.0-1.1ubuntu2"),
    ("libgl1", "1.7.0-1build1"),
    ("libglib2.0-0t64", "2.80.0-6ubuntu3.8"),
    ("libgssapi-krb5-2", "1.20.1-6ubuntu2.7"),
    ("libx11-xcb1", "2:1.8.7-1build1"),
    ("libxcb-cursor0", "0.1.4-1build1"),
    ("libxcb-icccm4", "0.4.1-1.1build3"),
    ("libxcb-image0", "0.4.0-2build1"),
    ("libxcb-keysyms1", "0.4.0-1build4"),
    ("libxcb-randr0", "1.15-1ubuntu2"),
    ("libxcb-render-util0", "0.3.9-1build4"),
    ("libxcb-shape0", "1.15-1ubuntu2"),
    ("libxcb-shm0", "1.15-1ubuntu2"),
    ("libxcb-sync1", "1.15-1ubuntu2"),
    ("libxcb-xfixes0", "1.15-1ubuntu2"),
    ("libxcb-xinerama0", "1.15-1ubuntu2"),
    ("libxcb-xkb1", "1.15-1ubuntu2"),
    ("libxkbcommon-x11-0", "1.6.0-1build1"),
    ("xauth", "1:1.1.2-1build1"),
    ("xvfb", "2:21.1.12-1ubuntu1.6"),
)

EXPECTED_PACKAGING_DATA_GROUPS = (
    {
        "destination": "configs",
        "expression": 'str(ROOT / "configs")',
        "id": "configs",
        "license_ids": ["project-apache-2.0"],
        "source": "configs",
    },
    {
        "destination": "models",
        "expression": 'str(ROOT / "models")',
        "id": "models",
        "license_ids": ["project-apache-2.0"],
        "source": "models",
    },
    {
        "destination": "mclab/application/qml",
        "expression": 'str(ROOT / "src/mclab/application/qml")',
        "id": "qml",
        "license_ids": ["project-apache-2.0"],
        "source": "src/mclab/application/qml",
    },
    {
        "destination": "third_party/mujoco_menagerie/franka_emika_panda",
        "expression": "str(PANDA_ASSETS.target)",
        "id": "panda-runtime",
        "license_ids": ["panda-apache-2.0"],
        "source": "managed-panda-runtime",
    },
    {
        "destination": "third_party/fonts/noto",
        "expression": 'str(ROOT / "third_party/fonts/noto")',
        "id": "noto-fonts",
        "license_ids": ["noto-ofl-1.1"],
        "source": "third_party/fonts/noto",
    },
    {
        "destination": ".",
        "expression": 'str(ROOT / "LICENSE")',
        "id": "project-license",
        "license_ids": ["project-apache-2.0"],
        "source": "LICENSE",
    },
)


def _input_paths() -> tuple[str, ...]:
    paths = {
        ACTIONS_LOCK_PATH,
        AUDITOR_PATH,
        GENERATOR_PATH,
        PACKAGING_SPEC_PATH,
        PANDA_MANIFEST_PATH,
        PROJECT_LICENSE_PATH,
        PROJECT_PATH,
        SCHEMA_PATH,
        UBUNTU_INSTALLER_PATH,
        UBUNTU_MANIFEST_PATH,
        WAIVER_PATH,
        EXPECTED_FONT_LICENSE[0],
        *(path for _identifier, path, _digest in EXPECTED_FONT_FILES),
        *(profile.source_path for profile in LOCK_PROFILES),
        *(profile.lock_path for profile in LOCK_PROFILES),
    }
    return tuple(sorted(paths))


INPUT_PATHS = _input_paths()


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _safe_file(root: Path, relative: str) -> Path:
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or not candidate_relative.parts:
        raise SupplyChainInputError(f"UNSAFE_PATH {relative!r}: expected repository-relative path")
    if any(part in {"", ".", ".."} for part in candidate_relative.parts):
        raise SupplyChainInputError(f"UNSAFE_PATH {relative!r}: ambiguous path component")
    if root.is_symlink():
        raise SupplyChainInputError(f"UNSAFE_ROOT {root}: repository root must not be a symlink")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise SupplyChainInputError(f"MISSING_ROOT {root}: {exc}") from exc
    cursor = root
    for part in candidate_relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SupplyChainInputError(f"UNSAFE_PATH {relative}: symlink component")
    try:
        resolved = cursor.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise SupplyChainInputError(f"MISSING_INPUT {relative}: {exc}") from exc
    if not resolved.is_relative_to(resolved_root) or not stat.S_ISREG(metadata.st_mode):
        raise SupplyChainInputError(f"UNSAFE_PATH {relative}: expected in-tree regular file")
    if metadata.st_size > MAX_INPUT_BYTES:
        raise SupplyChainInputError(
            f"OVERSIZED_INPUT {relative}: {metadata.st_size} > {MAX_INPUT_BYTES}"
        )
    return resolved


def read_bytes(root: Path, relative: str) -> bytes:
    path = _safe_file(root, relative)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SupplyChainInputError(f"UNREADABLE_INPUT {relative}: {exc}") from exc


def read_text(root: Path, relative: str) -> str:
    try:
        return read_bytes(root, relative).decode("utf-8")
    except UnicodeError as exc:
        raise SupplyChainInputError(f"NON_UTF8_INPUT {relative}: {exc}") from exc


def source_record(root: Path, relative: str) -> dict[str, object]:
    payload = read_bytes(root, relative)
    return {
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(key)
        result[key] = value
    return result


def strict_json(root: Path, relative: str) -> dict[str, object]:
    text = read_text(root, relative)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite number {token}")
            ),
        )
    except (json.JSONDecodeError, DuplicateJsonKeyError, ValueError) as exc:
        raise SupplyChainInputError(f"MALFORMED_JSON {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise SupplyChainInputError(f"MALFORMED_JSON {relative}: root must be an object")
    return value


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise SupplyChainInputError(
            f"UNEXPECTED_KEYS {label}: expected {sorted(expected)}, got {sorted(actual)}"
        )


def _section(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*\n(?P<body>.*?)(?=^\[|\Z)", text
    )
    if match is None:
        raise SupplyChainInputError(f"PYPROJECT_SECTION_MISSING [{name}]")
    return match.group("body")


def _toml_string(section: str, key: str) -> str:
    match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"(?P<value>[^"\n]+)"\s*$', section)
    if match is None:
        raise SupplyChainInputError(f"PYPROJECT_VALUE_INVALID {key}")
    return match.group("value")


def _toml_string_array(section: str, key: str) -> tuple[str, ...]:
    match = re.search(
        rf"(?ms)^{re.escape(key)}\s*=\s*\[(?P<value>.*?)^\]\s*$", section
    )
    if match is None:
        raise SupplyChainInputError(f"PYPROJECT_ARRAY_INVALID {key}")
    try:
        value = ast.literal_eval("[" + match.group("value") + "]")
    except (SyntaxError, ValueError) as exc:
        raise SupplyChainInputError(f"PYPROJECT_ARRAY_INVALID {key}: {exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SupplyChainInputError(f"PYPROJECT_ARRAY_INVALID {key}: strings required")
    return tuple(value)


def _project_and_environments(root: Path) -> tuple[dict[str, object], list[dict[str, str]]]:
    text = read_text(root, PROJECT_PATH)
    project_section = _section(text, "project")
    license_match = re.search(
        r'(?m)^license\s*=\s*\{\s*text\s*=\s*"(?P<value>[^"\n]+)"\s*\}\s*$',
        project_section,
    )
    if license_match is None:
        raise SupplyChainInputError("PYPROJECT_VALUE_INVALID project.license.text")
    actual_project = {
        "license": license_match.group("value"),
        "name": _toml_string(project_section, "name"),
        "requires_python": _toml_string(project_section, "requires-python"),
        "version": _toml_string(project_section, "version"),
    }
    if actual_project != EXPECTED_PROJECT:
        raise SupplyChainInputError(
            f"PROJECT_IDENTITY_DRIFT expected {EXPECTED_PROJECT}, got {actual_project}"
        )

    uv_section = _section(text, "tool.uv")
    environments = _toml_string_array(uv_section, "environments")
    required = _toml_string_array(uv_section, "required-environments")
    if environments != EXPECTED_TARGET_MARKERS or required != EXPECTED_TARGET_MARKERS:
        raise SupplyChainInputError(
            "TARGET_ENVIRONMENT_DRIFT expected both reviewed 12-cell marker lists"
        )

    records: list[dict[str, str]] = []
    for platform_name, machine in TARGET_PLATFORM_CELLS:
        for version in TARGET_PYTHON_VERSIONS:
            marker = (
                "implementation_name == 'cpython' and "
                f"python_version == '{version}' and "
                f"sys_platform == '{platform_name}' and "
                f"platform_machine == '{machine}'"
            )
            records.append(
                {
                    "id": f"cpython-{version}-{platform_name}-{machine.lower()}",
                    "implementation_name": "cpython",
                    "marker": marker,
                    "platform_machine": machine,
                    "platform_python_implementation": "CPython",
                    "python_full_version": f"{version}.0",
                    "python_version": version,
                    "sys_platform": platform_name,
                }
            )
    records.sort(key=lambda item: item["id"])
    project = dict(actual_project)
    project["source"] = source_record(root, PROJECT_PATH)
    return project, records


def _version_parts(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"\d+(?:\.\d+)*", value) is None:
        raise SupplyChainInputError(f"LOCK_MARKER_VERSION_INVALID {value!r}")
    return tuple(int(part) for part in value.split("."))


def _compare_marker(left: str, operator: str, right: str, *, version: bool) -> bool:
    if version:
        left_parts = _version_parts(left)
        right_parts = _version_parts(right)
        width = max(len(left_parts), len(right_parts))
        left_value: object = left_parts + (0,) * (width - len(left_parts))
        right_value: object = right_parts + (0,) * (width - len(right_parts))
    else:
        if operator not in {"==", "!="}:
            raise SupplyChainInputError(
                f"LOCK_MARKER_STRING_OPERATOR_UNSUPPORTED {left} {operator} {right}"
            )
        left_value = left
        right_value = right
    comparisons = {
        "<": left_value < right_value,
        "<=": left_value <= right_value,
        "==": left_value == right_value,
        "!=": left_value != right_value,
        ">=": left_value >= right_value,
        ">": left_value > right_value,
    }
    return comparisons[operator]


def _marker_applies(marker: str, environment: dict[str, str]) -> bool:
    clauses = marker.split(" or ")
    results: list[bool] = []
    for clause in clauses:
        if clause.startswith("(") and clause.endswith(")"):
            clause = clause[1:-1]
        elif len(clauses) != 1:
            raise SupplyChainInputError(f"LOCK_MARKER_CLAUSE_UNSUPPORTED {clause!r}")
        conditions = clause.split(" and ")
        condition_results: list[bool] = []
        for condition in conditions:
            match = MARKER_CONDITION_RE.fullmatch(condition)
            if match is None:
                raise SupplyChainInputError(
                    f"LOCK_MARKER_CONDITION_UNSUPPORTED {condition!r}"
                )
            variable = match.group("variable")
            actual = environment.get(variable)
            if actual is None:
                raise SupplyChainInputError(f"LOCK_MARKER_VALUE_MISSING {variable}")
            condition_results.append(
                _compare_marker(
                    actual,
                    match.group("operator"),
                    match.group("value"),
                    version=variable in {"python_full_version", "python_version"},
                )
            )
        results.append(bool(condition_results) and all(condition_results))
    return bool(results) and any(results)


def _logical_lock_lines(text: str, relative: str) -> list[str]:
    logical: list[str] = []
    parts: list[str] = []
    for line_number, physical in enumerate(text.splitlines(), start=1):
        stripped = physical.strip()
        if not stripped or stripped.startswith("#"):
            if parts:
                raise SupplyChainInputError(
                    f"LOCK_STRUCTURE {relative}:{line_number}: comment/blank in continuation"
                )
            continue
        continued = stripped.endswith("\\")
        parts.append(stripped[:-1].rstrip() if continued else stripped)
        if not continued:
            logical.append(" ".join(parts))
            parts = []
    if parts:
        raise SupplyChainInputError(f"LOCK_STRUCTURE {relative}: unterminated continuation")
    return logical


def _parse_lock(
    root: Path,
    profile: LockProfile,
    environments: list[dict[str, str]],
) -> dict[str, object]:
    text = read_text(root, profile.lock_path)
    logical = _logical_lock_lines(text, profile.lock_path)
    if not logical or logical[0] != "--only-binary :all:":
        raise SupplyChainInputError(
            f"LOCK_POLICY {profile.lock_path}: one leading --only-binary :all: required"
        )
    if logical.count("--only-binary :all:") != 1:
        raise SupplyChainInputError(f"LOCK_POLICY {profile.lock_path}: duplicate directive")

    requirements: list[dict[str, object]] = []
    seen: set[str] = set()
    for line_number, value in enumerate(logical[1:], start=1):
        tokens = value.split()
        try:
            hash_index = next(index for index, token in enumerate(tokens) if token.startswith("--"))
        except StopIteration as exc:
            raise SupplyChainInputError(
                f"LOCK_HASH_MISSING {profile.lock_path}:{line_number}"
            ) from exc
        if any(token.startswith("-") for token in tokens[:hash_index]):
            raise SupplyChainInputError(
                f"LOCK_DIRECTIVE_UNSAFE {profile.lock_path}:{line_number}"
            )
        hash_tokens = tokens[hash_index:]
        hashes: list[str] = []
        for token in hash_tokens:
            match = HASH_TOKEN_RE.fullmatch(token)
            if match is None:
                raise SupplyChainInputError(
                    f"LOCK_HASH_INVALID {profile.lock_path}:{line_number}: {token!r}"
                )
            hashes.append(match.group("digest"))
        if not hashes or len(hashes) != len(set(hashes)):
            raise SupplyChainInputError(
                f"LOCK_HASH_INVALID {profile.lock_path}:{line_number}: empty/duplicate"
            )
        requirement_text = " ".join(tokens[:hash_index])
        match = REQUIREMENT_RE.fullmatch(requirement_text)
        if match is None:
            raise SupplyChainInputError(
                f"LOCK_REQUIREMENT_INVALID {profile.lock_path}:{line_number}"
            )
        name = _normalise_name(match.group("name"))
        if name in seen:
            raise SupplyChainInputError(
                f"LOCK_REQUIREMENT_DUPLICATE {profile.lock_path}:{line_number}: {name}"
            )
        seen.add(name)
        marker = match.group("marker")
        environment_ids: list[str] = []
        for environment in environments:
            values = {key: value for key, value in environment.items() if key != "id"}
            try:
                applies = marker is None or _marker_applies(marker, values)
            except SupplyChainInputError as exc:
                raise SupplyChainInputError(
                    f"LOCK_MARKER_UNSUPPORTED {profile.lock_path}:{line_number}: {exc}"
                ) from exc
            if applies:
                environment_ids.append(environment["id"])
        if not environment_ids:
            raise SupplyChainInputError(
                f"LOCK_MARKER_ZERO_CELL {profile.lock_path}:{line_number}: {marker!r}"
            )
        extras = match.group("extras")
        requirements.append(
            {
                "environment_ids": sorted(environment_ids),
                "extras": sorted(extras.split(",")) if extras else [],
                "hash_scope": HASH_SCOPE,
                "hashes": sorted(hashes),
                "marker": marker,
                "name": name,
                "version": match.group("version"),
            }
        )
    if not requirements:
        raise SupplyChainInputError(f"LOCK_EMPTY {profile.lock_path}")
    names = [item["name"] for item in requirements]
    if names != sorted(names):
        raise SupplyChainInputError(f"LOCK_RECORDS_UNSORTED {profile.lock_path}")
    return {
        "extras": list(profile.extras),
        "id": profile.identifier,
        "lock": source_record(root, profile.lock_path),
        "requirements": requirements,
        "source": source_record(root, profile.source_path),
    }


def _actions(root: Path) -> dict[str, object]:
    payload = strict_json(root, ACTIONS_LOCK_PATH)
    _expect_keys(payload, {"actions", "minimum_actions_runner", "policy", "schema_version"}, ACTIONS_LOCK_PATH)
    if payload.get("schema_version") != 1 or payload.get("minimum_actions_runner") != "2.327.1":
        raise SupplyChainInputError("ACTION_LOCK_METADATA_DRIFT")
    if payload.get("policy") != EXPECTED_ACTION_POLICY:
        raise SupplyChainInputError("ACTION_LOCK_POLICY_DRIFT")
    if payload.get("actions") != EXPECTED_ACTIONS:
        raise SupplyChainInputError("ACTION_LOCK_RECORD_DRIFT")
    actions = [
        {"name": name, **record}
        for name, record in sorted(EXPECTED_ACTIONS.items())
    ]
    return {
        "actions": actions,
        "minimum_actions_runner": "2.327.1",
        "policy": dict(EXPECTED_ACTION_POLICY),
        "source": source_record(root, ACTIONS_LOCK_PATH),
    }


def _literal_assignment(tree: ast.Module, name: str, path: str) -> object:
    matches: list[ast.expr] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id == name:
                matches.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == name
            and statement.value is not None
        ):
            matches.append(statement.value)
    if len(matches) != 1:
        raise SupplyChainInputError(f"PYTHON_CONSTANT_INVALID {path}:{name}")
    try:
        return ast.literal_eval(matches[0])
    except (ValueError, TypeError) as exc:
        raise SupplyChainInputError(f"PYTHON_CONSTANT_INVALID {path}:{name}") from exc


def _panda(root: Path) -> dict[str, object]:
    source = source_record(root, PANDA_MANIFEST_PATH)
    if source["sha256"] != EXPECTED_PANDA_SOURCE_SHA256:
        raise SupplyChainInputError("PANDA_MANIFEST_SOURCE_DRIFT")
    text = read_text(root, PANDA_MANIFEST_PATH)
    try:
        tree = ast.parse(text, filename=PANDA_MANIFEST_PATH)
    except SyntaxError as exc:
        raise SupplyChainInputError(f"PANDA_MANIFEST_INVALID: {exc}") from exc
    schema = _literal_assignment(tree, "PANDA_RUNTIME_MANIFEST_SCHEMA", PANDA_MANIFEST_PATH)
    commit = _literal_assignment(tree, "PANDA_RUNTIME_MENAGERIE_COMMIT", PANDA_MANIFEST_PATH)
    archive = _literal_assignment(tree, "PANDA_RUNTIME_ARCHIVE_SHA256", PANDA_MANIFEST_PATH)
    manifest = _literal_assignment(tree, "PANDA_RUNTIME_MANIFEST", PANDA_MANIFEST_PATH)
    if schema != 1 or commit != EXPECTED_PANDA_COMMIT or archive != EXPECTED_PANDA_ARCHIVE_SHA256:
        raise SupplyChainInputError("PANDA_IDENTITY_DRIFT")
    if not isinstance(manifest, tuple) or len(manifest) != EXPECTED_PANDA_FILE_COUNT:
        raise SupplyChainInputError("PANDA_MANIFEST_COUNT_DRIFT")
    records: list[dict[str, object]] = []
    for index, entry in enumerate(manifest):
        if (
            not isinstance(entry, tuple)
            or len(entry) != 3
            or not isinstance(entry[0], str)
            or type(entry[1]) is not int
            or not isinstance(entry[2], str)
            or entry[1] <= 0
            or SHA256_RE.fullmatch(entry[2]) is None
        ):
            raise SupplyChainInputError(f"PANDA_MANIFEST_ENTRY_INVALID {index}")
        records.append({"path": entry[0], "sha256": entry[2], "size": entry[1]})
    paths = [record["path"] for record in records]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise SupplyChainInputError("PANDA_MANIFEST_ORDER_OR_DUPLICATE")
    if sum(int(record["size"]) for record in records) != EXPECTED_PANDA_TOTAL_BYTES:
        raise SupplyChainInputError("PANDA_MANIFEST_SIZE_DRIFT")
    license_entry = next((entry for entry in manifest if entry[0] == "LICENSE"), None)
    if license_entry != EXPECTED_PANDA_LICENSE:
        raise SupplyChainInputError("PANDA_LICENSE_DRIFT")
    return {
        "archive_sha256": archive,
        "commit": commit,
        "files": records,
        "license": {
            "path": license_entry[0],
            "sha256": license_entry[2],
            "size": license_entry[1],
            "spdx": "Apache-2.0",
        },
        "source": source,
        "upstream_repository": "https://github.com/google-deepmind/mujoco_menagerie",
    }


def _fonts(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for identifier, path, expected_digest in EXPECTED_FONT_FILES:
        record = source_record(root, path)
        if record["sha256"] != expected_digest:
            raise SupplyChainInputError(f"FONT_HASH_DRIFT {path}")
        files.append({"id": identifier, **record})
    license_path, expected_license_digest = EXPECTED_FONT_LICENSE
    license_record = source_record(root, license_path)
    if license_record["sha256"] != expected_license_digest:
        raise SupplyChainInputError("FONT_LICENSE_DRIFT")
    return {
        "files": sorted(files, key=lambda item: str(item["id"])),
        "license": {"id": "noto-ofl-1.1", "spdx": "OFL-1.1", **license_record},
    }


def _ubuntu(root: Path) -> dict[str, object]:
    payload = strict_json(root, UBUNTU_MANIFEST_PATH)
    _expect_keys(
        payload,
        {"distribution", "ecosystem", "packages", "schema_version", "snapshot"},
        UBUNTU_MANIFEST_PATH,
    )
    if payload.get("schema_version") != 1 or payload.get("ecosystem") != "apt":
        raise SupplyChainInputError("UBUNTU_MANIFEST_METADATA_DRIFT")
    distribution = payload.get("distribution")
    if not isinstance(distribution, dict):
        raise SupplyChainInputError("UBUNTU_DISTRIBUTION_INVALID")
    _expect_keys(
        distribution,
        {"architecture", "codename", "id", "version_id"},
        f"{UBUNTU_MANIFEST_PATH}:distribution",
    )
    if distribution != EXPECTED_UBUNTU_DISTRIBUTION:
        raise SupplyChainInputError("UBUNTU_DISTRIBUTION_DRIFT")
    if payload.get("snapshot") != EXPECTED_UBUNTU_SNAPSHOT:
        raise SupplyChainInputError("UBUNTU_SNAPSHOT_DRIFT")
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise SupplyChainInputError("UBUNTU_PACKAGES_INVALID")
    actual: list[tuple[str, str]] = []
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            raise SupplyChainInputError(f"UBUNTU_PACKAGE_INVALID {index}")
        _expect_keys(package, {"name", "version"}, f"ubuntu package {index}")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or not name or not version:
            raise SupplyChainInputError(f"UBUNTU_PACKAGE_INVALID {index}")
        actual.append((name, version))
    if tuple(actual) != EXPECTED_UBUNTU_PACKAGES:
        raise SupplyChainInputError("UBUNTU_PACKAGE_DRIFT_OR_ORDER")
    return {
        "distribution": dict(EXPECTED_UBUNTU_DISTRIBUTION),
        "ecosystem": "apt",
        "installer": source_record(root, UBUNTU_INSTALLER_PATH),
        "packages": [{"name": name, "version": version} for name, version in actual],
        "snapshot": EXPECTED_UBUNTU_SNAPSHOT,
        "source": source_record(root, UBUNTU_MANIFEST_PATH),
    }


def _expression_dump(expression: str) -> str:
    return ast.dump(ast.parse(expression, mode="eval").body, include_attributes=False)


def _packaging(root: Path) -> dict[str, object]:
    text = read_text(root, PACKAGING_SPEC_PATH)
    try:
        tree = ast.parse(text, filename=PACKAGING_SPEC_PATH)
    except SyntaxError as exc:
        raise SupplyChainInputError(f"PACKAGING_SPEC_INVALID: {exc}") from exc
    assignments = [
        statement.value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "datas"
    ]
    if len(assignments) != 1 or not isinstance(assignments[0], (ast.List, ast.Tuple)):
        raise SupplyChainInputError("PACKAGING_DATA_GROUPS_INVALID")
    actual: list[tuple[str, str]] = []
    for item in assignments[0].elts:
        if not isinstance(item, (ast.Tuple, ast.List)) or len(item.elts) != 2:
            raise SupplyChainInputError("PACKAGING_DATA_GROUP_INVALID")
        destination = item.elts[1]
        if not isinstance(destination, ast.Constant) or not isinstance(destination.value, str):
            raise SupplyChainInputError("PACKAGING_DESTINATION_INVALID")
        actual.append((ast.dump(item.elts[0], include_attributes=False), destination.value))
    expected = [
        (_expression_dump(str(group["expression"])), str(group["destination"]))
        for group in EXPECTED_PACKAGING_DATA_GROUPS
    ]
    if actual != expected:
        raise SupplyChainInputError("PACKAGING_DATA_GROUP_DRIFT")
    license_record = source_record(root, PROJECT_LICENSE_PATH)
    if license_record["sha256"] != EXPECTED_PROJECT_LICENSE_SHA256:
        raise SupplyChainInputError("PROJECT_LICENSE_DRIFT")
    groups = [
        {key: value for key, value in group.items() if key != "expression"}
        for group in EXPECTED_PACKAGING_DATA_GROUPS
    ]
    groups.sort(key=lambda item: str(item["id"]))
    return {
        "data_groups": groups,
        "root_licenses": [
            {"id": "project-apache-2.0", "spdx": "Apache-2.0", **license_record}
        ],
        "source": source_record(root, PACKAGING_SPEC_PATH),
    }


def _vulnerability_policy(root: Path) -> dict[str, object]:
    waivers = strict_json(root, WAIVER_PATH)
    _expect_keys(waivers, {"schema_version", "waivers"}, WAIVER_PATH)
    if waivers.get("schema_version") != 1 or waivers.get("waivers") != []:
        raise SupplyChainInputError("VULNERABILITY_WAIVERS_MUST_BE_EMPTY")
    return {
        "auditor": source_record(root, AUDITOR_PATH),
        "waiver_source": source_record(root, WAIVER_PATH),
        "waivers": [],
    }


def validate_source_commit(source_commit: str) -> None:
    if COMMIT_RE.fullmatch(source_commit) is None:
        raise SupplyChainInputError("SOURCE_COMMIT_INVALID: expected lowercase 40-hex SHA")


def _git_command(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SupplyChainInputError(f"SOURCE_CHECKOUT_UNAVAILABLE: {exc}") from exc


def git_checkout_commit(root: Path) -> str:
    """Return HEAD only when *root* is the exact top level of a Git worktree."""

    top_level = _git_command(root, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        raise SupplyChainInputError(
            f"SOURCE_CHECKOUT_UNAVAILABLE: {top_level.stderr.strip() or 'not a Git worktree'}"
        )
    try:
        expected_root = root.resolve(strict=True)
        actual_root = Path(top_level.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise SupplyChainInputError(f"SOURCE_CHECKOUT_UNAVAILABLE: {exc}") from exc
    if actual_root != expected_root:
        raise SupplyChainInputError(
            f"SOURCE_CHECKOUT_ROOT_MISMATCH: expected {expected_root}, got {actual_root}"
        )

    head = _git_command(root, "rev-parse", "--verify", "HEAD^{commit}")
    if head.returncode != 0:
        raise SupplyChainInputError(
            f"SOURCE_COMMIT_UNAVAILABLE: {head.stderr.strip() or 'HEAD is unavailable'}"
        )
    commit = head.stdout.strip()
    validate_source_commit(commit)
    return commit


def validate_source_checkout(root: Path, source_commit: str) -> None:
    """Bind generated evidence to a clean, exact checked-out Git commit."""

    validate_source_commit(source_commit)
    actual_commit = git_checkout_commit(root)
    if actual_commit != source_commit:
        raise SupplyChainInputError(
            f"SOURCE_COMMIT_MISMATCH: requested {source_commit}, checked out {actual_commit}"
        )
    status = _git_command(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        raise SupplyChainInputError(
            f"SOURCE_CHECKOUT_UNAVAILABLE: {status.stderr.strip() or 'git status failed'}"
        )
    if status.stdout.strip():
        raise SupplyChainInputError(
            "SOURCE_CHECKOUT_DIRTY: source_commit may describe only a clean checkout"
        )


def build_document(
    root: Path,
    source_commit: str,
    *,
    bind_to_checkout: bool = True,
) -> dict[str, object]:
    """Build one schema-1 document from the explicit reviewed allowlist."""

    validate_source_commit(source_commit)
    if bind_to_checkout:
        validate_source_checkout(root, source_commit)
    project, environments = _project_and_environments(root)
    profiles = [
        _parse_lock(root, profile, environments)
        for profile in sorted(LOCK_PROFILES, key=lambda item: item.identifier)
    ]
    document = {
        "contract": {
            "generator": source_record(root, GENERATOR_PATH),
            "schema": source_record(root, SCHEMA_PATH),
        },
        "fonts": _fonts(root),
        "github_actions": _actions(root),
        "packaging": _packaging(root),
        "panda_runtime": _panda(root),
        "project": project,
        "python_lock_profiles": profiles,
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "target_environments": environments,
        "ubuntu_system": _ubuntu(root),
        "vulnerability_policy": _vulnerability_policy(root),
    }
    represented = set(represented_repository_paths(document))
    expected = set(INPUT_PATHS)
    if represented != expected:
        raise SupplyChainInputError(
            "SOURCE_ALLOWLIST_MISMATCH "
            f"missing={sorted(expected - represented)} extra={sorted(represented - expected)}"
        )
    return document


def represented_repository_records(document: dict[str, object]) -> list[dict[str, object]]:
    """Return repository-backed source records represented by the document."""

    records: list[dict[str, object]] = []
    contract = document["contract"]
    records.extend((contract["generator"], contract["schema"]))
    records.append(document["project"]["source"])
    for profile in document["python_lock_profiles"]:
        records.extend((profile["source"], profile["lock"]))
    records.append(document["github_actions"]["source"])
    records.append(document["panda_runtime"]["source"])
    records.extend(document["fonts"]["files"])
    records.append(document["fonts"]["license"])
    records.extend(
        (document["ubuntu_system"]["source"], document["ubuntu_system"]["installer"])
    )
    records.append(document["packaging"]["source"])
    records.extend(document["packaging"]["root_licenses"])
    records.extend(
        (
            document["vulnerability_policy"]["auditor"],
            document["vulnerability_policy"]["waiver_source"],
        )
    )
    return records


def represented_repository_paths(document: dict[str, object]) -> tuple[str, ...]:
    return tuple(sorted({str(record["path"]) for record in represented_repository_records(document)}))


def canonical_json_bytes(document: dict[str, object]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _safe_output_path(path: Path) -> Path:
    if not path.name or path.name in {".", ".."}:
        raise SupplyChainInputError(f"UNSAFE_OUTPUT {path}: filename required")
    absolute = path.absolute()
    existing = absolute
    while not existing.exists():
        if existing.is_symlink():
            raise SupplyChainInputError(f"UNSAFE_OUTPUT {path}: symlink component")
        if existing == existing.parent:
            break
        existing = existing.parent
    cursor = existing
    while cursor != absolute:
        if cursor.is_symlink():
            raise SupplyChainInputError(f"UNSAFE_OUTPUT {path}: symlink component")
        cursor = cursor / absolute.relative_to(cursor).parts[0]
    if absolute.exists() and absolute.is_symlink():
        raise SupplyChainInputError(f"UNSAFE_OUTPUT {path}: symlink")
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = parent.resolve(strict=True)
    resolved = resolved_parent / path.name
    if resolved.exists():
        metadata = resolved.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise SupplyChainInputError(f"UNSAFE_OUTPUT {path}: expected regular file")
    return resolved


def write_document(path: Path, payload: bytes) -> None:
    target = _safe_output_path(path)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Exact lowercase 40-hex source SHA")
    parser.add_argument("--output", required=True, type=Path, help="Required JSON output path")
    args = parser.parse_args(argv)
    try:
        document = build_document(ROOT, args.source_commit)
        payload = canonical_json_bytes(document)
        write_document(args.output, payload)
    except (OSError, SupplyChainInputError) as exc:
        print(f"SBOM input generation failed: {exc}", file=sys.stderr)
        return 1
    requirements = sum(
        len(profile["requirements"]) for profile in document["python_lock_profiles"]
    )
    hashes = sum(
        len(requirement["hashes"])
        for profile in document["python_lock_profiles"]
        for requirement in profile["requirements"]
    )
    print(
        f"SBOM inputs written: {args.output} "
        f"(8 profiles, {requirements} requirements, {hashes} hashes, 12 environments)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
