"""Enforce the reviewed MAINT-01A exact mypy-debt and migration contracts."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import threading
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_BASELINE_RELATIVE = Path(".agents/baselines/MAINT-01A-mypy-debt-v1.json")
BASELINE_RELATIVE = Path(".agents/baselines/MAINT-01A-mypy-debt-v2.json")
PREVIOUS_CONFIG_RELATIVE = Path(".agents/baselines/MAINT-01A-mypy.ini")
CONFIG_RELATIVE = Path(".agents/baselines/MAINT-01A-mypy-v2.ini")
PYPROJECT_RELATIVE = Path("pyproject.toml")
BUILD_LOCK_RELATIVE = Path("requirements/locks/build.txt")
DEV_LOCK_RELATIVE = Path("requirements/locks/dev.txt")
PREVIOUS_BASELINE_SHA256 = "3c27e9e88da45954529443f8d9c3439dfe2c66362fd8f65e8b2b3df41f4bc612"
BASELINE_SHA256 = "998b05c41c590fbdeca58ff94f6c3995e86a6e5af83c36f19adb31c9f78c783b"
PREVIOUS_CONFIG_SHA256 = "e96b3933c1194a7a75b0bfa014b8f663c0739cc06fa33ab40777aae3c132d6a8"
CONFIG_SHA256 = "22c94d4c69c83f0f219a5c13535f255f28107784e3f74e6c69dc2810e5f736d8"
PYPROJECT_SHA256 = "3e778ccd63a0d42e799f95681fa9bb1fccc5846b89b6aaa0ba5ba1e06e75c7c8"
BUILD_LOCK_SHA256 = "a5665dc6290d9cdc25bb20a984fa4e40197697194e834d422baa71db3326b6e1"
DEV_LOCK_SHA256 = "e5e6237f17b9b8abcc1ace2603edbece97c636244a2d23d96190bb9b758fcdde"
PREVIOUS_BASELINE_ID = "MAINT-01A-mypy-debt-v1"
BASELINE_ID = "MAINT-01A-mypy-debt-v2"
BASELINE_PURPOSE = "Exact current mypy-debt baseline; improvements require monotonic migration."
EXPLICIT_ANY_RESIDUAL = (
    "disallow_any_explicit remains disabled: 781 inherited explicit-Any diagnostics are a "
    "named residual and are not absorbed into the 264-diagnostic baseline."
)
SOURCE_ROOT = "src/mclab"
MYPY_IMPORT_ROOTS = ("src",)
MYPY_VERSION = "2.3.0"
PROJECT_DISTRIBUTION = ("mujoco-manipulator-control-lab", "0.1.0")
# Deliberately empty: pip, setuptools, and wheel are pinned by the build lock.
BOOTSTRAP_DISTRIBUTION_ALLOWLIST: tuple[tuple[str, str], ...] = ()
SUPPORTED_PYTHON_VERSIONS = ("3.10", "3.11", "3.12")
MAX_BASELINE_BYTES = 2 * 1024 * 1024
MAX_POLICY_INPUT_BYTES = 4 * 1024 * 1024
MAX_MYPY_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_JSON_LINE_BYTES = 256 * 1024
MAX_PROBE_OUTPUT_BYTES = 512 * 1024
MAX_VERSION_OUTPUT_BYTES = 64 * 1024
MAX_STDERR_BYTES = 512 * 1024
DEFAULT_TIMEOUT_SECONDS = 180
GIT_OBJECT_RE = re.compile(r"[0-9a-f]{40}\Z")
VERSION_RE = re.compile(r"mypy (?P<version>[0-9]+(?:\.[0-9]+){2})(?: \(compiled: (?:yes|no)\))?\Z")
NAME_NORMALIZER_RE = re.compile(r"[-_.]+")
LOCK_REQUIREMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\[[A-Za-z0-9,_.-]+\])?=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
MARKER_CONDITION_RE = re.compile(
    r"(?P<variable>python_full_version|python_version|implementation_name|"
    r"platform_machine|platform_python_implementation|sys_platform)\s*"
    r"(?P<operator><=|>=|==|!=|<|>)\s*'(?P<value>[^']+)'"
)
TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\s*\[(?P<codes>[^\]\r\n]+)\])?(?![\w-])")
MYPY_DIRECTIVE_RE = re.compile(r"#\s*mypy:\s*(?P<directive>.+)\Z")
SUPPRESSION_KINDS = (
    "file-mypy-directive",
    "inline-type-ignore",
    "no-type-check",
    "stub-file",
)
PORTABLE_AST_IGNORED_FIELDS = frozenset({"type_params"})
TOOL_PROBE_SCRIPT = """\
import importlib.metadata as metadata
import importlib.util
import json
import platform
import struct
import sys
from pathlib import Path

spec = importlib.util.find_spec("mypy")
if spec is None or spec.origin is None:
    raise SystemExit("mypy import origin is unavailable")
distribution = metadata.distribution("mypy")
inventory = []
for item in metadata.distributions():
    name = item.metadata.get("Name")
    if name:
        origins = {
            str(Path(item.locate_file(entry.parts[0])).resolve())
            for entry in (item.files or ())
            if entry.parts and entry.parts[0].endswith((".dist-info", ".egg-info"))
        }
        if len(origins) != 1:
            raise SystemExit(
                f"distribution metadata origin is ambiguous or unavailable: {name}"
            )
        inventory.append({
            "name": name,
            "version": item.version,
            "root": str(Path(item.locate_file("")).resolve()),
            "origin": origins.pop(),
        })
payload = {
    "implementation_name": sys.implementation.name,
    "platform_python_implementation": platform.python_implementation(),
    "python_full_version": platform.python_version(),
    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
    "sys_platform": sys.platform,
    "platform_machine": platform.machine(),
    "pointer_bits": struct.calcsize("P") * 8,
    "prefix": str(Path(sys.prefix).resolve()),
    "base_prefix": str(Path(sys.base_prefix).resolve()),
    "mypy_origin": str(Path(spec.origin).resolve()),
    "mypy_distribution_root": str(Path(distribution.locate_file("")).resolve()),
    "inventory": sorted(
        inventory,
        key=lambda row: (
            row["name"].lower(),
            row["version"],
            row["root"],
            row["origin"],
        ),
    ),
}
print(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
"""

Fingerprint = tuple[str, str, str]
LegacySuppressionFingerprint = tuple[str, str, str]
SuppressionFingerprint = tuple[str, str, str, str]


class ContractError(ValueError):
    """Raised when baseline or tool output violates the closed contract."""


@dataclass(frozen=True)
class Baseline:
    error_count: int
    error_file_count: int
    source_file_count: int
    by_code: Mapping[str, int]
    by_file: Mapping[str, int]
    diagnostics: Counter[Fingerprint]
    suppressions: Counter[SuppressionFingerprint]


@dataclass(frozen=True)
class PreviousBaseline:
    diagnostics: Counter[Fingerprint]
    suppressions: Counter[LegacySuppressionFingerprint]


@dataclass(frozen=True)
class EnvironmentAttestation:
    implementation_name: str
    platform_python_implementation: str
    python_full_version: str
    python_version: str
    sys_platform: str
    platform_machine: str
    pointer_bits: int
    prefix: str
    base_prefix: str
    mypy_origin: str
    mypy_distribution_root: str
    inventory: tuple[DistributionAttestation, ...]


@dataclass(frozen=True)
class DistributionAttestation:
    name: str
    version: str
    root: str
    origin: str


@dataclass(frozen=True)
class AliasBinding:
    kind: str
    module: str | None = None
    name: str | None = None
    expression: ast.expr | None = None


@dataclass(frozen=True)
class MypyExecution:
    version: str
    returncode: int
    stdout: str
    stderr: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class BoundedProcess:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RepositoryMeasurement:
    attestation: EnvironmentAttestation
    source_file_count: int
    diagnostics: Counter[Fingerprint]
    suppressions: Counter[SuppressionFingerprint]


@dataclass(frozen=True)
class ValidationResult:
    native_python_version: str
    target_python_version: str
    interpreter_prefix_mode: str
    source_file_count: int
    error_count: int
    error_file_count: int
    baseline_error_count: int
    baseline_error_file_count: int
    removed_diagnostic_count: int
    suppression_count: int
    baseline_suppression_count: int
    removed_suppression_count: int
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant is forbidden: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{location} must be an object")
    return value


def _require_list(value: Any, location: str) -> list[Any]:
    if type(value) is not list:
        raise ContractError(f"{location} must be an array")
    return value


def _require_string(value: Any, location: str) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{location} must be a non-empty string")
    return value


def _require_int(value: Any, location: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{location} must be an integer >= {minimum}")
    return value


def _require_bool(value: Any, location: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{location} must be a boolean")
    return value


def _require_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ContractError(f"{location} keys mismatch: missing={missing}, extra={extra}")


def _canonical_message(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _canonical_file(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ContractError(f"unsafe diagnostic path: {value!r}")
    if not any(
        normalized.startswith(f"{root}/") for root in MYPY_IMPORT_ROOTS
    ) or not normalized.endswith(".py"):
        raise ContractError(f"diagnostic path is outside repository mypy import roots: {value!r}")
    return normalized


def _canonical_suppression_file(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ContractError(f"unsafe suppression path: {value!r}")
    is_import_root_python = any(
        normalized.startswith(f"{root}/") for root in MYPY_IMPORT_ROOTS
    ) and normalized.endswith(".py")
    is_import_root_stub = any(
        normalized.startswith(f"{root}/") for root in MYPY_IMPORT_ROOTS
    ) and normalized.endswith(".pyi")
    if not (is_import_root_python or is_import_root_stub):
        raise ContractError(f"suppression path is outside repository mypy import roots: {value!r}")
    return normalized


def _read_regular_file(path: Path, *, maximum: int) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ContractError(f"cannot stat {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ContractError(f"policy input must be a regular non-symlink file: {path}")
    if metadata.st_size > maximum:
        raise ContractError(f"policy input is too large: {path} ({metadata.st_size} bytes)")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc


def _normalise_distribution_name(name: str) -> str:
    return NAME_NORMALIZER_RE.sub("-", name).lower()


def _compare_version_values(left: str, operator: str, right: str) -> bool:
    if not re.fullmatch(r"\d+(?:\.\d+)*", left) or not re.fullmatch(r"\d+(?:\.\d+)*", right):
        raise ContractError(f"unsupported lock version comparison: {left} {operator} {right}")
    left_parts = tuple(int(part) for part in left.split("."))
    right_parts = tuple(int(part) for part in right.split("."))
    width = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (width - len(left_parts))
    right_parts += (0,) * (width - len(right_parts))
    comparisons = {
        "<": left_parts < right_parts,
        "<=": left_parts <= right_parts,
        "==": left_parts == right_parts,
        "!=": left_parts != right_parts,
        ">=": left_parts >= right_parts,
        ">": left_parts > right_parts,
    }
    return comparisons[operator]


def _marker_applies(marker: str, environment: Mapping[str, str]) -> bool:
    clauses = marker.split(" or ")
    if not clauses:
        raise ContractError(f"invalid empty lock marker: {marker!r}")
    clause_results: list[bool] = []
    for clause in clauses:
        if clause.startswith("(") and clause.endswith(")"):
            clause = clause[1:-1]
        elif len(clauses) != 1:
            raise ContractError(f"unsupported lock marker clause: {clause!r}")
        condition_results: list[bool] = []
        for condition in clause.split(" and "):
            match = MARKER_CONDITION_RE.fullmatch(condition)
            if match is None:
                raise ContractError(f"unsupported lock marker condition: {condition!r}")
            variable = match.group("variable")
            operator = match.group("operator")
            expected = match.group("value")
            actual = environment.get(variable)
            if actual is None:
                raise ContractError(f"missing lock marker environment value: {variable}")
            if variable in {"python_full_version", "python_version"}:
                result = _compare_version_values(actual, operator, expected)
            elif operator == "==":
                result = actual == expected
            elif operator == "!=":
                result = actual != expected
            else:
                raise ContractError(f"unsupported string lock comparison: {condition!r}")
            condition_results.append(result)
        clause_results.append(bool(condition_results) and all(condition_results))
    return any(clause_results)


def _locked_versions(
    raw: bytes,
    *,
    label: str,
    environment: Mapping[str, str],
) -> dict[str, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ContractError(f"{label} must be UTF-8: {exc}") from exc
    expected: dict[str, str] = {}
    for raw_line in text.splitlines():
        if raw_line[:1].isspace() or not raw_line or raw_line.startswith(("#", "--")):
            continue
        requirement = raw_line.removesuffix("\\").rstrip()
        match = LOCK_REQUIREMENT_RE.fullmatch(requirement)
        if match is None:
            raise ContractError(f"unsupported requirement in {label}: {raw_line}")
        marker = match.group("marker")
        if marker is not None and not _marker_applies(marker, environment):
            continue
        name = _normalise_distribution_name(match.group("name"))
        version = match.group("version")
        previous = expected.setdefault(name, version)
        if previous != version:
            raise ContractError(f"conflicting locked versions for {name}: {previous} and {version}")
    return expected


def _validate_policy_inputs(root: Path) -> dict[Path, bytes]:
    expected = {
        PREVIOUS_CONFIG_RELATIVE: (PREVIOUS_CONFIG_SHA256, 1024),
        CONFIG_RELATIVE: (CONFIG_SHA256, 1024),
        PYPROJECT_RELATIVE: (PYPROJECT_SHA256, MAX_POLICY_INPUT_BYTES),
        BUILD_LOCK_RELATIVE: (BUILD_LOCK_SHA256, MAX_POLICY_INPUT_BYTES),
        DEV_LOCK_RELATIVE: (DEV_LOCK_SHA256, MAX_POLICY_INPUT_BYTES),
    }
    inputs: dict[Path, bytes] = {}
    for relative, (digest, maximum) in expected.items():
        raw = _read_regular_file(root / relative, maximum=maximum)
        measured = hashlib.sha256(raw).hexdigest()
        if measured != digest:
            raise ContractError(
                f"immutable policy input drifted: {relative.as_posix()}: "
                f"expected {digest}, measured {measured}"
            )
        inputs[relative] = raw
    if inputs[PREVIOUS_CONFIG_RELATIVE] != b"[mypy]\n":
        raise ContractError("immutable previous mypy config bytes drifted")
    if inputs[CONFIG_RELATIVE] != (
        b"[mypy]\n"
        b"check_untyped_defs = True\n"
        b"disallow_untyped_defs = True\n"
        b"disallow_incomplete_defs = True\n"
    ):
        raise ContractError("immutable active mypy config bytes drifted")
    return inputs


def _sanitised_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("MYPY") or key in {
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONSTARTUP",
            "PYTHONUSERBASE",
        }:
            environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _parse_environment_probe(text: str) -> EnvironmentAttestation:
    if len(text.encode("utf-8")) > MAX_PROBE_OUTPUT_BYTES:
        raise ContractError(f"environment probe output exceeds {MAX_PROBE_OUTPUT_BYTES} bytes")
    if not text.endswith("\n") or text.count("\n") != 1:
        raise ContractError("environment probe must emit exactly one JSON line")
    value = _require_object(_strict_json(text), "environment probe")
    _require_keys(
        value,
        {
            "implementation_name",
            "platform_python_implementation",
            "python_full_version",
            "python_version",
            "sys_platform",
            "platform_machine",
            "pointer_bits",
            "prefix",
            "base_prefix",
            "mypy_origin",
            "mypy_distribution_root",
            "inventory",
        },
        "environment probe",
    )
    inventory_rows = _require_list(value["inventory"], "environment probe.inventory")
    inventory: list[DistributionAttestation] = []
    seen: set[str] = set()
    for index, raw in enumerate(inventory_rows):
        row = _require_object(raw, f"environment probe.inventory[{index}]")
        _require_keys(
            row,
            {"name", "version", "root", "origin"},
            f"environment probe.inventory[{index}]",
        )
        name = _normalise_distribution_name(
            _require_string(row["name"], f"environment probe.inventory[{index}].name")
        )
        version = _require_string(row["version"], f"environment probe.inventory[{index}].version")
        if name in seen:
            raise ContractError(
                f"DEPENDENCY_PROFILE_MISMATCH duplicate installed distribution: {name}"
            )
        seen.add(name)
        inventory.append(
            DistributionAttestation(
                name=name,
                version=version,
                root=_require_string(row["root"], f"environment probe.inventory[{index}].root"),
                origin=_require_string(
                    row["origin"], f"environment probe.inventory[{index}].origin"
                ),
            )
        )
    inventory.sort(key=lambda item: (item.name, item.version, item.root, item.origin))
    return EnvironmentAttestation(
        implementation_name=_require_string(
            value["implementation_name"], "environment probe.implementation_name"
        ),
        platform_python_implementation=_require_string(
            value["platform_python_implementation"],
            "environment probe.platform_python_implementation",
        ),
        python_full_version=_require_string(
            value["python_full_version"], "environment probe.python_full_version"
        ),
        python_version=_require_string(value["python_version"], "environment probe.python_version"),
        sys_platform=_require_string(value["sys_platform"], "environment probe.sys_platform"),
        platform_machine=_require_string(
            value["platform_machine"], "environment probe.platform_machine"
        ),
        pointer_bits=_require_int(value["pointer_bits"], "environment probe.pointer_bits"),
        prefix=_require_string(value["prefix"], "environment probe.prefix"),
        base_prefix=_require_string(value["base_prefix"], "environment probe.base_prefix"),
        mypy_origin=_require_string(value["mypy_origin"], "environment probe.mypy_origin"),
        mypy_distribution_root=_require_string(
            value["mypy_distribution_root"], "environment probe.mypy_distribution_root"
        ),
        inventory=tuple(inventory),
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _attestation_marker_environment(attestation: EnvironmentAttestation) -> dict[str, str]:
    return {
        "python_full_version": attestation.python_full_version,
        "python_version": attestation.python_version,
        "implementation_name": attestation.implementation_name,
        "platform_machine": attestation.platform_machine,
        "platform_python_implementation": attestation.platform_python_implementation,
        "sys_platform": attestation.sys_platform,
    }


def _validate_environment_attestation(
    attestation: EnvironmentAttestation,
    *,
    policy_inputs: Mapping[Path, bytes],
) -> None:
    if attestation.implementation_name != "cpython":
        raise ContractError("environment must use CPython")
    if attestation.platform_python_implementation != "CPython":
        raise ContractError("environment Python implementation label must be CPython")
    if attestation.python_version not in SUPPORTED_PYTHON_VERSIONS:
        raise ContractError(
            "environment runtime must be CPython 3.10, 3.11, or 3.12; "
            f"measured {attestation.python_full_version}"
        )
    if attestation.sys_platform != "linux" or attestation.platform_machine != "x86_64":
        raise ContractError(
            "environment must be the reviewed Linux x86_64 dev profile; "
            f"measured {attestation.sys_platform} {attestation.platform_machine}"
        )
    if attestation.pointer_bits != 64:
        raise ContractError(f"environment must be 64-bit; measured {attestation.pointer_bits}-bit")

    prefix = Path(attestation.prefix)
    base_prefix = Path(attestation.base_prefix)
    distribution_root = Path(attestation.mypy_distribution_root)
    origin = Path(attestation.mypy_origin)
    if not all(path.is_absolute() for path in (prefix, base_prefix, distribution_root, origin)):
        raise ContractError("mypy origin attestation paths must be absolute")
    if not _is_relative_to(distribution_root, prefix):
        raise ContractError("mypy distribution root is outside the selected interpreter prefix")
    if not _is_relative_to(origin, distribution_root / "mypy"):
        raise ContractError("mypy import origin is outside its installed distribution package")

    for distribution in attestation.inventory:
        distribution_root_path = Path(distribution.root)
        distribution_origin_path = Path(distribution.origin)
        if not distribution_root_path.is_absolute() or not distribution_origin_path.is_absolute():
            raise ContractError(
                "DEPENDENCY_ORIGIN_OUTSIDE_PREFIX distribution provenance must be absolute: "
                f"{distribution.name}"
            )
        if (
            distribution_root_path != distribution_root_path.resolve()
            or distribution_origin_path != distribution_origin_path.resolve()
        ):
            raise ContractError(
                "DEPENDENCY_ORIGIN_OUTSIDE_PREFIX distribution provenance must be resolved: "
                f"{distribution.name}"
            )
        if not _is_relative_to(distribution_root_path, prefix) or not _is_relative_to(
            distribution_origin_path, prefix
        ):
            raise ContractError(
                "DEPENDENCY_ORIGIN_OUTSIDE_PREFIX expected every distribution under the "
                f"selected interpreter prefix: name={distribution.name!r}, "
                f"root={distribution.root!r}, origin={distribution.origin!r}, "
                f"prefix={attestation.prefix!r}"
            )

    marker_environment = _attestation_marker_environment(attestation)
    expected: dict[str, str] = {}
    for relative in (BUILD_LOCK_RELATIVE, DEV_LOCK_RELATIVE):
        for name, version in _locked_versions(
            policy_inputs[relative],
            label=relative.as_posix(),
            environment=marker_environment,
        ).items():
            previous = expected.setdefault(name, version)
            if previous != version:
                raise ContractError(
                    f"conflicting build/dev lock versions for {name}: {previous} and {version}"
                )
    for name, version in (PROJECT_DISTRIBUTION, *BOOTSTRAP_DISTRIBUTION_ALLOWLIST):
        normalised = _normalise_distribution_name(name)
        previous = expected.setdefault(normalised, version)
        if previous != version:
            raise ContractError(
                f"conflicting explicit distribution versions for {normalised}: "
                f"{previous} and {version}"
            )

    actual = {item.name: item.version for item in attestation.inventory}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        changed = sorted(
            f"{name}: expected {expected[name]}, measured {actual[name]}"
            for name in set(expected) & set(actual)
            if expected[name] != actual[name]
        )
        raise ContractError(
            "DEPENDENCY_PROFILE_MISMATCH expected exact dev-only inventory; "
            f"missing={missing}; unexpected={unexpected}; changed={changed}"
        )
    if actual.get("mypy") != MYPY_VERSION:
        raise ContractError(
            f"mypy distribution must be {MYPY_VERSION}, measured {actual.get('mypy', 'missing')}"
        )


def _run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
) -> BoundedProcess:
    """Drain both pipes concurrently and kill the child as soon as either cap is exceeded."""

    if stdout_limit < 1 or stderr_limit < 1:
        raise ContractError("subprocess output limits must be positive")
    process = subprocess.Popen(
        tuple(argv),
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    overflows: list[str] = []
    reader_errors: list[str] = []
    lock = threading.Lock()

    def terminate() -> None:
        try:
            process.kill()
        except OSError:
            pass

    def drain(label: str, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                with lock:
                    remaining = limits[label] - len(buffers[label])
                    if remaining > 0:
                        buffers[label].extend(chunk[:remaining])
                    if len(chunk) > remaining and label not in overflows:
                        overflows.append(label)
                        terminate()
        except (OSError, ValueError) as exc:
            with lock:
                reader_errors.append(f"{label}: {type(exc).__name__}: {exc}")
            terminate()

    threads = (
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    )
    for thread in threads:
        thread.start()
    timeout_error: subprocess.TimeoutExpired | None = None
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        timeout_error = exc
        terminate()
        returncode = process.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=10)
    if any(thread.is_alive() for thread in threads):
        terminate()
        raise ContractError("subprocess pipe reader did not terminate after child exit")
    if timeout_error is not None:
        raise timeout_error
    if reader_errors:
        raise ContractError(f"subprocess pipe read failed: {reader_errors[0]}")
    if overflows:
        label = overflows[0]
        raise ContractError(
            f"subprocess {label} exceeded its {limits[label]}-byte cap; child terminated"
        )
    try:
        stdout = bytes(buffers["stdout"]).decode("utf-8", errors="strict")
        stderr = bytes(buffers["stderr"]).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"subprocess output must be strict UTF-8: {exc}") from exc
    return BoundedProcess(returncode=returncode, stdout=stdout, stderr=stderr)


def attest_environment(
    root: Path,
    *,
    policy_inputs: Mapping[Path, bytes],
) -> EnvironmentAttestation:
    process = _run_bounded(
        (sys.executable, "-I", "-c", TOOL_PROBE_SCRIPT),
        cwd=root,
        env=_sanitised_environment(),
        timeout_seconds=30,
        stdout_limit=MAX_PROBE_OUTPUT_BYTES,
        stderr_limit=MAX_PROBE_OUTPUT_BYTES,
    )
    if process.returncode != 0 or process.stderr:
        raise ContractError(
            "isolated environment probe failed: "
            f"status={process.returncode}, stderr={process.stderr!r}"
        )
    attestation = _parse_environment_probe(process.stdout)
    _validate_environment_attestation(attestation, policy_inputs=policy_inputs)
    return attestation


def _parse_count_rows(
    value: Any,
    *,
    key_name: str,
    location: str,
    normalize_key: Callable[[str], str] | None = None,
) -> dict[str, int]:
    rows = _require_list(value, location)
    parsed: dict[str, int] = {}
    previous: str | None = None
    for index, raw in enumerate(rows):
        row = _require_object(raw, f"{location}[{index}]")
        _require_keys(row, {key_name, "count"}, f"{location}[{index}]")
        key = _require_string(row[key_name], f"{location}[{index}].{key_name}")
        if normalize_key is not None:
            key = normalize_key(key)
        count = _require_int(row["count"], f"{location}[{index}].count", minimum=1)
        if previous is not None and key <= previous:
            raise ContractError(f"{location} must be unique and sorted by {key_name}")
        previous = key
        parsed[key] = count
    return parsed


def _parse_suppression_rows(value: Any) -> Counter[SuppressionFingerprint]:
    rows = _require_list(value, "suppressions.entries")
    parsed: Counter[SuppressionFingerprint] = Counter()
    previous: SuppressionFingerprint | None = None
    for index, raw in enumerate(rows):
        row = _require_object(raw, f"suppressions.entries[{index}]")
        _require_keys(
            row,
            {"file", "kind", "directive", "context", "count"},
            f"suppressions.entries[{index}]",
        )
        kind = _require_string(row["kind"], f"suppressions.entries[{index}].kind")
        if kind not in SUPPRESSION_KINDS:
            raise ContractError(f"unsupported suppression kind: {kind!r}")
        fingerprint = (
            _canonical_suppression_file(
                _require_string(row["file"], f"suppressions.entries[{index}].file")
            ),
            kind,
            _require_string(row["directive"], f"suppressions.entries[{index}].directive"),
            _require_string(row["context"], f"suppressions.entries[{index}].context"),
        )
        if previous is not None and fingerprint <= previous:
            raise ContractError("suppressions.entries must be unique and sorted")
        previous = fingerprint
        parsed[fingerprint] = _require_int(
            row["count"], f"suppressions.entries[{index}].count", minimum=1
        )
    return parsed


def _parse_legacy_suppression_rows(value: Any) -> Counter[LegacySuppressionFingerprint]:
    rows = _require_list(value, "previous suppressions.entries")
    parsed: Counter[LegacySuppressionFingerprint] = Counter()
    previous: LegacySuppressionFingerprint | None = None
    for index, raw in enumerate(rows):
        row = _require_object(raw, f"previous suppressions.entries[{index}]")
        _require_keys(
            row,
            {"file", "kind", "directive", "count"},
            f"previous suppressions.entries[{index}]",
        )
        fingerprint = (
            _canonical_suppression_file(
                _require_string(row["file"], f"previous suppressions.entries[{index}].file")
            ),
            _require_string(row["kind"], f"previous suppressions.entries[{index}].kind"),
            _require_string(row["directive"], f"previous suppressions.entries[{index}].directive"),
        )
        if previous is not None and fingerprint <= previous:
            raise ContractError("previous suppressions.entries must be unique and sorted")
        previous = fingerprint
        parsed[fingerprint] = _require_int(
            row["count"], f"previous suppressions.entries[{index}].count", minimum=1
        )
    return parsed


def _parse_diagnostic_rows(value: Any, *, location: str) -> Counter[Fingerprint]:
    rows = _require_list(value, location)
    diagnostics: Counter[Fingerprint] = Counter()
    previous: Fingerprint | None = None
    for index, raw in enumerate(rows):
        row = _require_object(raw, f"{location}[{index}]")
        _require_keys(row, {"file", "code", "message", "count"}, f"{location}[{index}]")
        fingerprint = (
            _canonical_file(_require_string(row["file"], f"{location}[{index}].file")),
            _require_string(row["code"], f"{location}[{index}].code"),
            _canonical_message(_require_string(row["message"], f"{location}[{index}].message")),
        )
        if previous is not None and fingerprint <= previous:
            raise ContractError(f"{location} must be unique and sorted")
        previous = fingerprint
        diagnostics[fingerprint] = _require_int(
            row["count"], f"{location}[{index}].count", minimum=1
        )
    return diagnostics


def validate_baseline_document(document: Any) -> Baseline:
    root = _require_object(document, "baseline document")
    _require_keys(
        root,
        {
            "schema_version",
            "baseline_id",
            "purpose",
            "history",
            "subject",
            "environment",
            "tool",
            "baseline",
            "suppressions",
            "policy",
        },
        "baseline document",
    )
    if root["schema_version"] != 2 or type(root["schema_version"]) is not int:
        raise ContractError("schema_version must be integer 2")
    if root["baseline_id"] != BASELINE_ID:
        raise ContractError(f"baseline_id must be {BASELINE_ID}")
    if root["purpose"] != BASELINE_PURPOSE:
        raise ContractError("baseline purpose drifted")

    history = _require_list(root["history"], "history")
    if history != [
        {
            "baseline_id": PREVIOUS_BASELINE_ID,
            "path": PREVIOUS_BASELINE_RELATIVE.as_posix(),
            "sha256": PREVIOUS_BASELINE_SHA256,
            "relationship": (
                "diagnostics and context-projected suppressions are multisets contained in "
                "the immutable previous baseline"
            ),
        }
    ]:
        raise ContractError("baseline history drifted from immutable v1 ancestry")

    subject = _require_object(root["subject"], "subject")
    _require_keys(subject, {"commit", "tree"}, "subject")
    for key in ("commit", "tree"):
        value = _require_string(subject[key], f"subject.{key}")
        if GIT_OBJECT_RE.fullmatch(value) is None:
            raise ContractError(f"subject.{key} must be a lowercase 40-hex Git identifier")

    environment = _require_object(root["environment"], "environment")
    _require_keys(
        environment,
        {
            "profile",
            "runtime",
            "inputs",
            "local_project_distribution",
            "bootstrap_distribution_allowlist",
        },
        "environment",
    )
    if environment["profile"] != "exact-dev-interpreter-prefix":
        raise ContractError("environment.profile must be 'exact-dev-interpreter-prefix'")
    runtime = _require_object(environment["runtime"], "environment.runtime")
    expected_runtime = {
        "implementation": "cpython",
        "platform": "linux",
        "machine": "x86_64",
        "pointer_bits": 64,
        "python_versions": list(SUPPORTED_PYTHON_VERSIONS),
        "prefix_scope": "selected interpreter prefix; not necessarily a virtual environment",
        "distribution_scope": (
            "every expected distribution root and metadata origin resolves under sys.prefix"
        ),
    }
    if runtime != expected_runtime:
        raise ContractError(f"environment.runtime must be {expected_runtime!r}")
    expected_inputs = [
        {
            "path": CONFIG_RELATIVE.as_posix(),
            "sha256": CONFIG_SHA256,
            "purpose": "standalone strict-definition mypy configuration",
        },
        {
            "path": PYPROJECT_RELATIVE.as_posix(),
            "sha256": PYPROJECT_SHA256,
            "purpose": "project metadata and dev-extra semantics",
        },
        {
            "path": BUILD_LOCK_RELATIVE.as_posix(),
            "sha256": BUILD_LOCK_SHA256,
            "purpose": "pinned bootstrap and build distributions",
        },
        {
            "path": DEV_LOCK_RELATIVE.as_posix(),
            "sha256": DEV_LOCK_SHA256,
            "purpose": "pinned runtime and dev distributions",
        },
    ]
    if environment["inputs"] != expected_inputs:
        raise ContractError("environment.inputs drifted from exact project/build/dev inputs")
    expected_project_distribution = {
        "name": PROJECT_DISTRIBUTION[0],
        "version": PROJECT_DISTRIBUTION[1],
    }
    if environment["local_project_distribution"] != expected_project_distribution:
        raise ContractError("environment.local_project_distribution drifted")
    expected_bootstrap = [
        {"name": name, "version": version} for name, version in BOOTSTRAP_DISTRIBUTION_ALLOWLIST
    ]
    if environment["bootstrap_distribution_allowlist"] != expected_bootstrap:
        raise ContractError("environment.bootstrap_distribution_allowlist drifted")

    tool = _require_object(root["tool"], "tool")
    _require_keys(
        tool,
        {
            "name",
            "version",
            "dependency_profile",
            "platform",
            "source_root",
            "controlled_import_roots",
            "canonical_python_version",
            "supported_python_versions",
            "canonical_argv",
        },
        "tool",
    )
    exact_tool_values = {
        "name": "mypy",
        "version": MYPY_VERSION,
        "dependency_profile": (
            "exact dev inventory with resolved distribution provenance under the selected "
            "interpreter prefix"
        ),
        "platform": "linux",
        "source_root": SOURCE_ROOT,
        "canonical_python_version": "3.11",
    }
    for key, expected in exact_tool_values.items():
        if tool[key] != expected:
            raise ContractError(f"tool.{key} must be {expected!r}")
    if tool["controlled_import_roots"] != list(MYPY_IMPORT_ROOTS):
        raise ContractError("tool.controlled_import_roots drifted")
    supported = _require_list(tool["supported_python_versions"], "tool.supported_python_versions")
    if supported != list(SUPPORTED_PYTHON_VERSIONS):
        raise ContractError("supported Python versions must remain ordered 3.10/3.11/3.12")
    argv = _require_list(tool["canonical_argv"], "tool.canonical_argv")
    expected_argv = [
        "<python>",
        "-I",
        "-m",
        "mypy",
        "--no-incremental",
        "--config-file",
        CONFIG_RELATIVE.as_posix(),
        "--python-version",
        "<3.10|3.11|3.12>",
        "--platform",
        "linux",
        "--output",
        "json",
        SOURCE_ROOT,
    ]
    if argv != expected_argv:
        raise ContractError("tool.canonical_argv drifted")

    values = _require_object(root["baseline"], "baseline")
    _require_keys(
        values,
        {
            "source_file_count",
            "error_count",
            "error_file_count",
            "by_code",
            "by_file",
            "diagnostics",
        },
        "baseline",
    )
    source_file_count = _require_int(
        values["source_file_count"], "baseline.source_file_count", minimum=1
    )
    error_count = _require_int(values["error_count"], "baseline.error_count")
    error_file_count = _require_int(values["error_file_count"], "baseline.error_file_count")
    by_code = _parse_count_rows(values["by_code"], key_name="code", location="baseline.by_code")
    by_file = _parse_count_rows(
        values["by_file"],
        key_name="file",
        location="baseline.by_file",
        normalize_key=_canonical_file,
    )

    diagnostics = _parse_diagnostic_rows(values["diagnostics"], location="baseline.diagnostics")

    derived_by_code: Counter[str] = Counter()
    derived_by_file: Counter[str] = Counter()
    for (file_name, code, _message), count in diagnostics.items():
        derived_by_file[file_name] += count
        derived_by_code[code] += count
    if sum(diagnostics.values()) != error_count:
        raise ContractError("baseline error_count does not reconcile with diagnostics")
    if len(derived_by_file) != error_file_count:
        raise ContractError("baseline error_file_count does not reconcile with diagnostics")
    if dict(sorted(derived_by_code.items())) != by_code:
        raise ContractError("baseline.by_code does not reconcile with diagnostics")
    if dict(sorted(derived_by_file.items())) != by_file:
        raise ContractError("baseline.by_file does not reconcile with diagnostics")

    suppressions = _require_object(root["suppressions"], "suppressions")
    _require_keys(
        suppressions,
        {
            "comparison",
            "migration_comparison",
            "fingerprint_fields",
            "context_definition",
            "kinds",
            "line_and_column_ignored",
            "removals_require_migration",
            "additions_are_forbidden",
            "entries",
        },
        "suppressions",
    )
    if suppressions["comparison"] != (
        "normal validation requires the exact active typing-suppression multiset"
    ):
        raise ContractError("suppressions.comparison drifted")
    if suppressions["migration_comparison"] != (
        "a deliberate next suppression multiset must be a subset of the active baseline"
    ):
        raise ContractError("suppressions.migration_comparison drifted")
    if suppressions["fingerprint_fields"] != ["file", "kind", "directive", "context"]:
        raise ContractError("suppressions.fingerprint_fields drifted")
    if suppressions["context_definition"] != (
        "normalized AST plus line-insensitive parent/field/index path for ignores/decorators; "
        "module AST hash for file directives; raw-byte hash for stubs"
    ):
        raise ContractError("suppressions.context_definition drifted")
    if suppressions["kinds"] != list(SUPPRESSION_KINDS):
        raise ContractError("suppressions.kinds drifted")
    for key in (
        "line_and_column_ignored",
        "removals_require_migration",
        "additions_are_forbidden",
    ):
        if not _require_bool(suppressions[key], f"suppressions.{key}"):
            raise ContractError(f"suppressions.{key} must remain true")
    suppression_entries = _parse_suppression_rows(suppressions["entries"])

    policy = _require_object(root["policy"], "policy")
    _require_keys(
        policy,
        {
            "comparison",
            "migration_comparison",
            "fingerprint_fields",
            "line_and_column_ignored",
            "removals_are_improvements",
            "additions_are_forbidden",
            "per_file_increases_are_forbidden",
            "explicit_any_residual",
        },
        "policy",
    )
    if policy["comparison"] != "normal validation requires exact baseline multisets":
        raise ContractError("policy.comparison drifted")
    if policy["migration_comparison"] != (
        "a deliberate next baseline may record debt removal or a source-file inventory "
        "change and may not increase the active diagnostic or suppression multiset"
    ):
        raise ContractError("policy.migration_comparison drifted")
    if policy["fingerprint_fields"] != ["file", "code", "message"]:
        raise ContractError("policy.fingerprint_fields drifted")
    for key in (
        "line_and_column_ignored",
        "removals_are_improvements",
        "additions_are_forbidden",
        "per_file_increases_are_forbidden",
    ):
        if not _require_bool(policy[key], f"policy.{key}"):
            raise ContractError(f"policy.{key} must remain true")
    if policy["explicit_any_residual"] != EXPLICIT_ANY_RESIDUAL:
        raise ContractError("policy.explicit_any_residual drifted")

    return Baseline(
        error_count=error_count,
        error_file_count=error_file_count,
        source_file_count=source_file_count,
        by_code=by_code,
        by_file=by_file,
        diagnostics=diagnostics,
        suppressions=suppression_entries,
    )


def load_baseline_document(path: Path, *, enforce_digest: bool = True) -> dict[str, Any]:
    raw = _read_regular_file(path, maximum=MAX_BASELINE_BYTES)
    if enforce_digest:
        measured = hashlib.sha256(raw).hexdigest()
        if measured != BASELINE_SHA256:
            raise ContractError(
                f"baseline digest mismatch: expected {BASELINE_SHA256}, measured {measured}"
            )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"baseline must be UTF-8: {exc}") from exc
    if not text.endswith("\n"):
        raise ContractError("baseline must end with one newline")
    document = _require_object(_strict_json(text), "baseline document")
    canonical = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if text != canonical:
        raise ContractError("baseline JSON is not canonical indent-2 UTF-8")
    validate_baseline_document(document)
    return document


def load_baseline(path: Path, *, enforce_digest: bool = True) -> Baseline:
    return validate_baseline_document(load_baseline_document(path, enforce_digest=enforce_digest))


def load_previous_baseline(path: Path) -> PreviousBaseline:
    raw = _read_regular_file(path, maximum=MAX_BASELINE_BYTES)
    measured = hashlib.sha256(raw).hexdigest()
    if measured != PREVIOUS_BASELINE_SHA256:
        raise ContractError(
            "previous baseline digest mismatch: "
            f"expected {PREVIOUS_BASELINE_SHA256}, measured {measured}"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"previous baseline must be UTF-8: {exc}") from exc
    document = _require_object(_strict_json(text), "previous baseline document")
    canonical = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if text != canonical:
        raise ContractError("previous baseline JSON is not canonical indent-2 UTF-8")
    if document.get("baseline_id") != PREVIOUS_BASELINE_ID:
        raise ContractError("previous baseline ID drifted")
    values = _require_object(document.get("baseline"), "previous baseline")
    suppressions = _require_object(document.get("suppressions"), "previous suppressions")
    return PreviousBaseline(
        diagnostics=_parse_diagnostic_rows(
            values.get("diagnostics"), location="previous baseline.diagnostics"
        ),
        suppressions=_parse_legacy_suppression_rows(suppressions.get("entries")),
    )


def _project_suppressions(
    suppressions: Counter[SuppressionFingerprint],
) -> Counter[LegacySuppressionFingerprint]:
    projected: Counter[LegacySuppressionFingerprint] = Counter()
    for (file_name, kind, directive, _context), count in suppressions.items():
        projected[(file_name, kind, directive)] += count
    return projected


def validate_baseline_ancestry(active: Baseline, previous: PreviousBaseline) -> None:
    diagnostic_additions = active.diagnostics - previous.diagnostics
    suppression_additions = _project_suppressions(active.suppressions) - previous.suppressions
    if diagnostic_additions:
        raise ContractError(
            "active baseline reintroduces diagnostics outside immutable v1: "
            f"count={sum(diagnostic_additions.values())}"
        )
    if suppression_additions:
        raise ContractError(
            "active baseline reintroduces suppressions outside immutable v1: "
            f"count={sum(suppression_additions.values())}"
        )


def parse_mypy_jsonl(text: str, *, returncode: int) -> Counter[Fingerprint]:
    encoded_size = len(text.encode("utf-8"))
    if encoded_size > MAX_MYPY_OUTPUT_BYTES:
        raise ContractError(f"mypy output exceeds {MAX_MYPY_OUTPUT_BYTES} bytes")
    if returncode not in (0, 1):
        raise ContractError(f"mypy returned unexpected status {returncode}")
    if text in {"", "\n"}:
        if returncode == 0:
            return Counter()
        raise ContractError("mypy returned status 1 with empty diagnostic output")
    if not text.endswith("\n"):
        raise ContractError("mypy JSONL output must end with a newline")

    diagnostics: Counter[Fingerprint] = Counter()
    for number, line in enumerate(text.splitlines(), start=1):
        if len(line.encode("utf-8")) > MAX_JSON_LINE_BYTES:
            raise ContractError(f"mypy JSONL line {number} is too large")
        row = _require_object(_strict_json(line), f"mypy line {number}")
        _require_keys(
            row,
            {
                "file",
                "line",
                "column",
                "end_line",
                "end_column",
                "message",
                "hint",
                "code",
                "severity",
            },
            f"mypy line {number}",
        )
        for key in ("line", "column", "end_line", "end_column"):
            _require_int(row[key], f"mypy line {number}.{key}")
        if row["hint"] is not None and type(row["hint"]) is not str:
            raise ContractError(f"mypy line {number}.hint must be a string or null")
        if row["severity"] != "error":
            raise ContractError(f"mypy line {number}.severity must be 'error'")
        fingerprint = (
            _canonical_file(_require_string(row["file"], f"mypy line {number}.file")),
            _require_string(row["code"], f"mypy line {number}.code"),
            _canonical_message(_require_string(row["message"], f"mypy line {number}.message")),
        )
        diagnostics[fingerprint] += 1
    if returncode == 0 and diagnostics:
        raise ContractError("mypy returned status 0 while emitting error diagnostics")
    return diagnostics


def mypy_argv(python_version: str) -> tuple[str, ...]:
    if python_version not in SUPPORTED_PYTHON_VERSIONS:
        raise ContractError(f"unsupported Python target: {python_version}")
    return (
        sys.executable,
        "-I",
        "-m",
        "mypy",
        "--no-incremental",
        "--config-file",
        CONFIG_RELATIVE.as_posix(),
        "--python-version",
        python_version,
        "--platform",
        "linux",
        "--output",
        "json",
        SOURCE_ROOT,
    )


def execute_mypy(
    root: Path,
    python_version: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> MypyExecution:
    environment = _sanitised_environment()
    version_process = _run_bounded(
        (sys.executable, "-I", "-m", "mypy", "--version"),
        cwd=root,
        env=environment,
        timeout_seconds=30,
        stdout_limit=MAX_VERSION_OUTPUT_BYTES,
        stderr_limit=MAX_VERSION_OUTPUT_BYTES,
    )
    if version_process.returncode != 0 or version_process.stderr:
        raise ContractError(
            "mypy version probe failed: "
            f"status={version_process.returncode}, stderr={version_process.stderr!r}"
        )
    match = VERSION_RE.fullmatch(version_process.stdout.strip())
    if match is None:
        raise ContractError(f"unrecognized mypy version output: {version_process.stdout!r}")
    version = match.group("version")
    if version != MYPY_VERSION:
        raise ContractError(f"mypy version must be {MYPY_VERSION}, measured {version}")

    argv = mypy_argv(python_version)
    process = _run_bounded(
        argv,
        cwd=root,
        env=environment,
        timeout_seconds=timeout_seconds,
        stdout_limit=MAX_MYPY_OUTPUT_BYTES,
        stderr_limit=MAX_STDERR_BYTES,
    )
    return MypyExecution(
        version=version,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
        argv=argv,
    )


def compare_diagnostics(
    baseline: Baseline,
    current: Counter[Fingerprint],
    *,
    python_version: str,
    native_python_version: str = "unknown",
    interpreter_prefix_mode: str = "unknown",
    source_file_count: int,
    current_suppressions: Counter[SuppressionFingerprint],
) -> ValidationResult:
    errors: list[str] = []
    current_by_file: Counter[str] = Counter()
    current_by_code: Counter[str] = Counter()
    for (file_name, code, _message), count in current.items():
        current_by_file[file_name] += count
        current_by_code[code] += count

    additions = current - baseline.diagnostics
    for (file_name, code, message), count in sorted(additions.items()):
        errors.append(
            f"NEW_DIAGNOSTIC count={count} file={file_name} code={code} message={message!r}"
        )
    for file_name in sorted(set(current_by_file) - set(baseline.by_file)):
        errors.append(f"NEW_ERROR_FILE {file_name}: {current_by_file[file_name]} errors")
    for code in sorted(set(current_by_code) - set(baseline.by_code)):
        errors.append(f"NEW_ERROR_CODE {code}: {current_by_code[code]} errors")
    for file_name, count in sorted(current_by_file.items()):
        budget = baseline.by_file.get(file_name, 0)
        if count > budget:
            errors.append(f"FILE_BUDGET_EXCEEDED {file_name}: {count} > {budget}")
    current_count = sum(current.values())
    if current_count > baseline.error_count:
        errors.append(f"TOTAL_BUDGET_EXCEEDED {current_count} > {baseline.error_count}")

    removed = baseline.diagnostics - current
    for (file_name, code, message), count in sorted(removed.items()):
        errors.append(
            "BASELINE_DIAGNOSTIC_REMOVED_REQUIRES_MIGRATION "
            f"count={count} file={file_name} code={code} message={message!r}"
        )
    if source_file_count != baseline.source_file_count:
        errors.append(
            "SOURCE_FILE_COUNT_REQUIRES_MIGRATION "
            f"{source_file_count} != {baseline.source_file_count}"
        )

    suppression_additions = current_suppressions - baseline.suppressions
    for (file_name, kind, directive, context), count in sorted(suppression_additions.items()):
        errors.append(
            "NEW_TYPING_SUPPRESSION "
            f"count={count} file={file_name} kind={kind} directive={directive!r} "
            f"context={context}"
        )

    removed_suppressions = baseline.suppressions - current_suppressions
    for (file_name, kind, directive, context), count in sorted(removed_suppressions.items()):
        errors.append(
            "BASELINE_SUPPRESSION_REMOVED_REQUIRES_MIGRATION "
            f"count={count} file={file_name} kind={kind} directive={directive!r} "
            f"context={context}"
        )
    return ValidationResult(
        native_python_version=native_python_version,
        target_python_version=python_version,
        interpreter_prefix_mode=interpreter_prefix_mode,
        source_file_count=source_file_count,
        error_count=current_count,
        error_file_count=len(current_by_file),
        baseline_error_count=baseline.error_count,
        baseline_error_file_count=baseline.error_file_count,
        removed_diagnostic_count=sum(removed.values()),
        suppression_count=sum(current_suppressions.values()),
        baseline_suppression_count=sum(baseline.suppressions.values()),
        removed_suppression_count=sum(removed_suppressions.values()),
        errors=tuple(errors),
    )


def validate_monotonic_migration(
    baseline: Baseline,
    diagnostics: Counter[Fingerprint],
    suppressions: Counter[SuppressionFingerprint],
    *,
    source_file_count: int,
) -> None:
    if type(source_file_count) is not int or source_file_count < 1:
        raise ContractError("migration source_file_count must be an integer >= 1")
    diagnostic_additions = diagnostics - baseline.diagnostics
    suppression_additions = suppressions - baseline.suppressions
    if diagnostic_additions:
        raise ContractError(
            "migration reintroduces or increases diagnostic fingerprints: "
            f"count={sum(diagnostic_additions.values())}"
        )
    if suppression_additions:
        raise ContractError(
            "migration reintroduces or increases typing suppressions: "
            f"count={sum(suppression_additions.values())}"
        )
    if (
        diagnostics == baseline.diagnostics
        and suppressions == baseline.suppressions
        and source_file_count == baseline.source_file_count
    ):
        raise ContractError(
            "migration requires at least one diagnostic or suppression removal "
            "or a source-file inventory change"
        )


def build_migration_candidate(
    active_document: Mapping[str, Any],
    baseline: Baseline,
    *,
    diagnostics: Counter[Fingerprint],
    suppressions: Counter[SuppressionFingerprint],
    source_file_count: int,
    subject_commit: str,
    subject_tree: str,
) -> dict[str, Any]:
    """Build a v3 candidate after non-increasing debt and a reviewed inventory change."""

    for label, value in (("subject commit", subject_commit), ("subject tree", subject_tree)):
        if GIT_OBJECT_RE.fullmatch(value) is None:
            raise ContractError(f"migration {label} must be a lowercase 40-hex identifier")
    validate_monotonic_migration(
        baseline,
        diagnostics,
        suppressions,
        source_file_count=source_file_count,
    )
    candidate = copy.deepcopy(dict(active_document))
    candidate["baseline_id"] = "MAINT-01A-mypy-debt-v3"
    candidate["subject"] = {"commit": subject_commit, "tree": subject_tree}
    history = _require_list(candidate.get("history"), "migration history")
    history.append(
        {
            "baseline_id": BASELINE_ID,
            "path": BASELINE_RELATIVE.as_posix(),
            "sha256": BASELINE_SHA256,
            "relationship": (
                "diagnostics and contextual suppressions are multisets contained in the "
                "immutable previous baseline"
            ),
        }
    )

    by_code: Counter[str] = Counter()
    by_file: Counter[str] = Counter()
    diagnostic_rows: list[dict[str, Any]] = []
    for (file_name, code, message), count in sorted(diagnostics.items()):
        diagnostic_rows.append(
            {"file": file_name, "code": code, "message": message, "count": count}
        )
        by_code[code] += count
        by_file[file_name] += count
    candidate["baseline"] = {
        "source_file_count": source_file_count,
        "error_count": sum(diagnostics.values()),
        "error_file_count": len(by_file),
        "by_code": [{"code": code, "count": count} for code, count in sorted(by_code.items())],
        "by_file": [
            {"file": file_name, "count": count} for file_name, count in sorted(by_file.items())
        ],
        "diagnostics": diagnostic_rows,
    }
    candidate_suppressions = _require_object(
        candidate.get("suppressions"), "migration suppressions"
    )
    candidate_suppressions["entries"] = [
        {
            "file": file_name,
            "kind": kind,
            "directive": directive,
            "context": context,
            "count": count,
        }
        for (file_name, kind, directive, context), count in sorted(suppressions.items())
    ]
    return candidate


def _source_python_files(root: Path) -> tuple[Path, ...]:
    discovered: set[Path] = set()
    for import_root in MYPY_IMPORT_ROOTS:
        source = root / import_root
        if not source.is_dir() or source.is_symlink():
            raise ContractError(f"mypy import root must be a non-symlink directory: {import_root}")
        try:
            for directory, directory_names, file_names in os.walk(source, followlinks=False):
                directory_names.sort()
                file_names.sort()
                current = Path(directory)
                for name in directory_names:
                    child = current / name
                    if child.is_symlink():
                        raise ContractError(
                            f"source directory must not be a symlink: {child.relative_to(root)}"
                        )
                for name in file_names:
                    if not name.endswith((".py", ".pyi")):
                        continue
                    path = current / name
                    metadata = path.lstat()
                    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                        raise ContractError(
                            "source Python input must be a regular non-symlink file: "
                            f"{path.relative_to(root)}"
                        )
                    discovered.add(path)
        except OSError as exc:
            raise ContractError(f"cannot inventory mypy import root {import_root}: {exc}") from exc
    return tuple(sorted(discovered, key=lambda path: path.relative_to(root).as_posix()))


def _repository_stub_files(root: Path) -> tuple[Path, ...]:
    discovered: set[Path] = set()
    for import_root in MYPY_IMPORT_ROOTS:
        source = root / import_root
        if not source.is_dir() or source.is_symlink():
            raise ContractError(f"mypy import root must be a non-symlink directory: {import_root}")
        try:
            for directory, directory_names, file_names in os.walk(source, followlinks=False):
                directory_names.sort()
                file_names.sort()
                current = Path(directory)
                for name in directory_names:
                    child = current / name
                    if child.is_symlink():
                        raise ContractError(
                            "mypy import-root directory must not be a symlink: "
                            f"{child.relative_to(root)}"
                        )
                for name in file_names:
                    if not name.endswith(".pyi"):
                        continue
                    path = current / name
                    metadata = path.lstat()
                    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                        raise ContractError(
                            "stub input must be a regular non-symlink file: "
                            f"{path.relative_to(root)}"
                        )
                    discovered.add(path)
        except OSError as exc:
            raise ContractError(f"cannot inventory mypy import root {import_root}: {exc}") from exc
    return tuple(sorted(discovered, key=lambda path: path.relative_to(root).as_posix()))


def _canonical_type_ignore(match: re.Match[str]) -> str:
    codes = match.group("codes")
    if codes is None:
        return "# type: ignore"
    canonical_codes = ",".join(part.strip() for part in codes.split(","))
    return f"# type: ignore[{canonical_codes}]"


def _portable_ast_dump(node: ast.AST) -> str:
    """Serialize the common CPython 3.10-3.12 AST without version-only fields."""

    def normalize(value: Any) -> Any:
        if isinstance(value, ast.AST):
            return {
                "node": type(value).__name__,
                "fields": [
                    [field, normalize(child)]
                    for field, child in ast.iter_fields(value)
                    if field not in PORTABLE_AST_IGNORED_FIELDS
                ],
            }
        if isinstance(value, list):
            return [normalize(child) for child in value]
        if value is None or type(value) in {bool, int, str}:
            return value
        if type(value) is float:
            return {"float-hex": value.hex()}
        if type(value) is bytes:
            return {"bytes-hex": value.hex()}
        if type(value) is complex:
            return {"complex-hex": [value.real.hex(), value.imag.hex()]}
        if value is Ellipsis:
            return {"singleton": "Ellipsis"}
        raise ContractError(
            f"unsupported AST fingerprint value: {type(value).__name__}"
        )

    return json.dumps(
        normalize(node),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _ast_hash(node: ast.AST, *, label: str) -> str:
    normalized = _portable_ast_dump(node)
    return f"{label}-sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _ast_structural_paths(tree: ast.Module) -> dict[int, str]:
    """Return line-insensitive parent/field/index paths for every AST node."""

    paths = {id(tree): "Module"}

    def visit(parent: ast.AST) -> None:
        parent_path = paths[id(parent)]
        for field, value in ast.iter_fields(parent):
            if isinstance(value, ast.AST):
                paths[id(value)] = f"{parent_path}/{type(parent).__name__}.{field}"
                visit(value)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    if not isinstance(child, ast.AST):
                        continue
                    paths[id(child)] = f"{parent_path}/{type(parent).__name__}.{field}[{index}]"
                    visit(child)

    visit(tree)
    return paths


def _structural_context_hash(node: ast.AST, path: str, *, label: str) -> str:
    normalized = json.dumps(
        {
            "ast": _portable_ast_dump(node),
            "path": path,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{label}-sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _statement_context(
    tree: ast.Module,
    token: tokenize.TokenInfo,
    structural_paths: Mapping[int, str],
) -> str:
    row, column = token.start
    candidates: list[ast.stmt] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt) or not hasattr(node, "lineno"):
            continue
        end_row = getattr(node, "end_lineno", node.lineno)
        if node.lineno <= row <= end_row and (
            row != node.lineno or column >= getattr(node, "col_offset", 0)
        ):
            candidates.append(node)
    if not candidates:
        raise ContractError(f"typing ignore at line {row} is not attached to a Python statement")
    statement = min(
        candidates,
        key=lambda node: (
            getattr(node, "end_lineno", node.lineno) - node.lineno,
            -getattr(node, "col_offset", 0),
        ),
    )
    return _structural_context_hash(
        statement,
        structural_paths[id(statement)],
        label="statement-context",
    )


def _module_identity(
    root: Path,
    path: Path,
) -> tuple[str, bool]:
    relative = path.relative_to(root)
    for import_root in sorted(MYPY_IMPORT_ROOTS, key=len, reverse=True):
        try:
            module_relative = relative.relative_to(import_root)
        except ValueError:
            continue
        parts = list(module_relative.parts)
        is_package = parts[-1] in {"__init__.py", "__init__.pyi"}
        if is_package:
            parts = parts[:-1]
        else:
            parts[-1] = Path(parts[-1]).stem
        if parts and all(part.isidentifier() for part in parts):
            return ".".join(parts), is_package
        break
    return f"<file:{relative.as_posix()}>", False


def _absolute_import_module(
    current_module: str,
    *,
    is_package: bool,
    imported_module: str | None,
    level: int,
) -> str:
    if level == 0:
        return imported_module or ""
    if current_module.startswith("<file:"):
        return ""
    package_parts = current_module.split(".") if is_package else current_module.split(".")[:-1]
    ascents = level - 1
    if ascents > len(package_parts):
        return ""
    resolved = package_parts[: len(package_parts) - ascents]
    if imported_module:
        resolved.extend(imported_module.split("."))
    return ".".join(resolved)


def _alias_bindings(
    tree: ast.Module,
    *,
    module: str,
    is_package: bool,
) -> tuple[dict[str, tuple[AliasBinding, ...]], tuple[str, ...]]:
    """Collect conservative aliases across scopes so suppression routes cannot hide."""

    collected: dict[str, list[AliasBinding]] = {}
    star_modules: set[str] = set()

    def add(name: str, binding: AliasBinding) -> None:
        collected.setdefault(name, []).append(binding)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    add(alias.asname, AliasBinding(kind="module", module=alias.name))
                else:
                    root_name = alias.name.split(".", 1)[0]
                    add(root_name, AliasBinding(kind="module", module=root_name))
        elif isinstance(node, ast.ImportFrom):
            imported = _absolute_import_module(
                module,
                is_package=is_package,
                imported_module=node.module,
                level=node.level,
            )
            for alias in node.names:
                if alias.name == "*":
                    if imported:
                        star_modules.add(imported)
                    continue
                add(
                    alias.asname or alias.name,
                    AliasBinding(kind="symbol", module=imported, name=alias.name),
                )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    add(target.id, AliasBinding(kind="expression", expression=node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                add(
                    node.target.id,
                    AliasBinding(kind="expression", expression=node.value),
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            add(node.name, AliasBinding(kind="definition"))

    return (
        {name: tuple(bindings) for name, bindings in collected.items()},
        tuple(sorted(star_modules)),
    )


def _expression_module_path(
    module: str,
    expression: ast.expr,
    *,
    bindings_by_module: Mapping[str, Mapping[str, tuple[AliasBinding, ...]]],
    local_modules: frozenset[str],
    seen: frozenset[tuple[str, str]],
) -> str | None:
    if isinstance(expression, ast.Name):
        marker = (module, f"module:{expression.id}")
        if marker in seen:
            return None
        next_seen = seen | {marker}
        for binding in bindings_by_module.get(module, {}).get(expression.id, ()):
            if binding.kind == "module":
                return binding.module
            if binding.kind == "symbol" and binding.module and binding.name:
                candidate = f"{binding.module}.{binding.name}" if binding.module else binding.name
                if candidate in local_modules:
                    return candidate
            if binding.kind == "expression" and binding.expression is not None:
                candidate = _expression_module_path(
                    module,
                    binding.expression,
                    bindings_by_module=bindings_by_module,
                    local_modules=local_modules,
                    seen=next_seen,
                )
                if candidate is not None:
                    return candidate
        return None
    if isinstance(expression, ast.Attribute):
        parent = _expression_module_path(
            module,
            expression.value,
            bindings_by_module=bindings_by_module,
            local_modules=local_modules,
            seen=seen,
        )
        if parent is None:
            return None
        candidate = f"{parent}.{expression.attr}"
        if candidate in local_modules or parent in {"typing", "typing_extensions"}:
            return candidate
    return None


def _name_resolves_no_type_check(
    module: str,
    name: str,
    *,
    bindings_by_module: Mapping[str, Mapping[str, tuple[AliasBinding, ...]]],
    star_modules_by_module: Mapping[str, tuple[str, ...]],
    local_modules: frozenset[str],
    seen: frozenset[tuple[str, str]],
) -> bool:
    marker = (module, name)
    if marker in seen:
        return False
    next_seen = seen | {marker}
    for binding in bindings_by_module.get(module, {}).get(name, ()):
        if binding.kind == "symbol" and binding.module and binding.name:
            if (
                binding.module in {"typing", "typing_extensions"}
                and binding.name == "no_type_check"
            ):
                return True
            if binding.module in local_modules and _name_resolves_no_type_check(
                binding.module,
                binding.name,
                bindings_by_module=bindings_by_module,
                star_modules_by_module=star_modules_by_module,
                local_modules=local_modules,
                seen=next_seen,
            ):
                return True
        elif binding.kind == "expression" and binding.expression is not None:
            if _expression_resolves_no_type_check(
                module,
                binding.expression,
                bindings_by_module=bindings_by_module,
                star_modules_by_module=star_modules_by_module,
                local_modules=local_modules,
                seen=next_seen,
            ):
                return True
    for star_module in star_modules_by_module.get(module, ()):
        if star_module in {"typing", "typing_extensions"} and name == "no_type_check":
            return True
        if star_module in local_modules and _name_resolves_no_type_check(
            star_module,
            name,
            bindings_by_module=bindings_by_module,
            star_modules_by_module=star_modules_by_module,
            local_modules=local_modules,
            seen=next_seen,
        ):
            return True
    return False


def _expression_resolves_no_type_check(
    module: str,
    expression: ast.expr,
    *,
    bindings_by_module: Mapping[str, Mapping[str, tuple[AliasBinding, ...]]],
    star_modules_by_module: Mapping[str, tuple[str, ...]],
    local_modules: frozenset[str],
    seen: frozenset[tuple[str, str]],
) -> bool:
    if isinstance(expression, ast.Name):
        return _name_resolves_no_type_check(
            module,
            expression.id,
            bindings_by_module=bindings_by_module,
            star_modules_by_module=star_modules_by_module,
            local_modules=local_modules,
            seen=seen,
        )
    if isinstance(expression, ast.Attribute):
        module_path = _expression_module_path(
            module,
            expression.value,
            bindings_by_module=bindings_by_module,
            local_modules=local_modules,
            seen=seen,
        )
        if module_path in {"typing", "typing_extensions"} and expression.attr == "no_type_check":
            return True
        if module_path in local_modules:
            return _name_resolves_no_type_check(
                module_path,
                expression.attr,
                bindings_by_module=bindings_by_module,
                star_modules_by_module=star_modules_by_module,
                local_modules=local_modules,
                seen=seen,
            )
    return False


def _is_no_type_check_decorator(
    node: ast.expr,
    *,
    module: str,
    bindings_by_module: Mapping[str, Mapping[str, tuple[AliasBinding, ...]]],
    star_modules_by_module: Mapping[str, tuple[str, ...]],
    local_modules: frozenset[str],
) -> bool:
    return (
        (isinstance(node, ast.Name) and node.id == "no_type_check")
        or (isinstance(node, ast.Attribute) and node.attr == "no_type_check")
        or _expression_resolves_no_type_check(
            module,
            node,
            bindings_by_module=bindings_by_module,
            star_modules_by_module=star_modules_by_module,
            local_modules=local_modules,
            seen=frozenset(),
        )
    )


def scan_typing_suppressions(
    root: Path,
    source_files: Sequence[Path] | None = None,
) -> Counter[SuppressionFingerprint]:
    source_paths = _source_python_files(root) if source_files is None else tuple(source_files)
    paths = tuple(
        sorted(
            {*source_paths, *_repository_stub_files(root)},
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )
    parsed: dict[Path, tuple[str, bytes, ast.Module, str, bool]] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        raw = _read_regular_file(path, maximum=MAX_POLICY_INPUT_BYTES)
        try:
            encoding, _unused = tokenize.detect_encoding(io.BytesIO(raw).readline)
            source_text = raw.decode(encoding, errors="strict")
            tree = ast.parse(source_text, filename=relative)
        except (IndentationError, SyntaxError, tokenize.TokenError, UnicodeError) as exc:
            raise ContractError(
                f"cannot tokenize typing-suppression surface {relative}: {exc}"
            ) from exc
        module, is_package = _module_identity(root, path)
        parsed[path] = (relative, raw, tree, module, is_package)

    local_modules = frozenset(
        module
        for _relative, _raw, _tree, module, _is_package in parsed.values()
        if not module.startswith("<file:")
    )
    mutable_bindings: dict[str, dict[str, list[AliasBinding]]] = {}
    mutable_stars: dict[str, set[str]] = {}
    for _relative, _raw, tree, module, is_package in parsed.values():
        file_bindings, star_modules = _alias_bindings(
            tree,
            module=module,
            is_package=is_package,
        )
        module_bindings = mutable_bindings.setdefault(module, {})
        for name, bindings in file_bindings.items():
            module_bindings.setdefault(name, []).extend(bindings)
        mutable_stars.setdefault(module, set()).update(star_modules)
    bindings_by_module = {
        module: {name: tuple(bindings) for name, bindings in names.items()}
        for module, names in mutable_bindings.items()
    }
    star_modules_by_module = {
        module: tuple(sorted(stars)) for module, stars in mutable_stars.items()
    }

    suppressions: Counter[SuppressionFingerprint] = Counter()
    for path in paths:
        relative, raw, tree, module, _is_package = parsed[path]
        if path.suffix == ".pyi":
            suppressions[
                (
                    relative,
                    "stub-file",
                    "present",
                    f"raw-sha256:{hashlib.sha256(raw).hexdigest()}",
                )
            ] += 1
        try:
            module_context = _ast_hash(tree, label="module-ast")
            structural_paths = _ast_structural_paths(tree)
            tokens = tokenize.tokenize(io.BytesIO(raw).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                for match in TYPE_IGNORE_RE.finditer(token.string):
                    suppressions[
                        (
                            relative,
                            "inline-type-ignore",
                            _canonical_type_ignore(match),
                            _statement_context(tree, token, structural_paths),
                        )
                    ] += 1
                mypy_match = MYPY_DIRECTIVE_RE.fullmatch(token.string.strip())
                if mypy_match is not None:
                    directive = " ".join(mypy_match.group("directive").split())
                    suppressions[
                        (
                            relative,
                            "file-mypy-directive",
                            f"# mypy: {directive}",
                            module_context,
                        )
                    ] += 1
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for decorator in node.decorator_list:
                    if _is_no_type_check_decorator(
                        decorator,
                        module=module,
                        bindings_by_module=bindings_by_module,
                        star_modules_by_module=star_modules_by_module,
                        local_modules=local_modules,
                    ):
                        suppressions[
                            (
                                relative,
                                "no-type-check",
                                "@no_type_check",
                                _structural_context_hash(
                                    node,
                                    structural_paths[id(node)],
                                    label="definition-context",
                                ),
                            )
                        ] += 1
        except (IndentationError, SyntaxError, tokenize.TokenError, UnicodeError) as exc:
            raise ContractError(
                f"cannot tokenize typing-suppression surface {relative}: {exc}"
            ) from exc
    return suppressions


def measure_repository(
    root: Path = ROOT,
    *,
    python_version: str = "3.11",
    executor: Callable[[Path, str], MypyExecution] = execute_mypy,
) -> RepositoryMeasurement:
    root = Path(root)
    policy_inputs = _validate_policy_inputs(root)
    source_files = _source_python_files(root)
    source_file_count = sum(path.suffix == ".py" for path in source_files)
    current_suppressions = scan_typing_suppressions(root, source_files)
    try:
        attestation = attest_environment(root, policy_inputs=policy_inputs)
        execution = executor(root, python_version)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ContractError(
            f"sanitized mypy validation failed: {type(exc).__name__}: {exc}"
        ) from exc
    if attestation.python_version != python_version:
        raise ContractError(
            "native interpreter and mypy target must match; "
            f"native={attestation.python_version}, target={python_version}"
        )
    if execution.version != MYPY_VERSION:
        raise ContractError(
            f"mypy executor version must be {MYPY_VERSION}, measured {execution.version}"
        )
    if execution.stderr:
        raise ContractError(f"mypy stderr must be empty: {execution.stderr!r}")
    if tuple(execution.argv) != mypy_argv(python_version):
        raise ContractError("mypy executor argv drifted from the canonical command")
    current = parse_mypy_jsonl(execution.stdout, returncode=execution.returncode)
    return RepositoryMeasurement(
        attestation=attestation,
        source_file_count=source_file_count,
        diagnostics=current,
        suppressions=current_suppressions,
    )


def validate_repository(
    root: Path = ROOT,
    *,
    python_version: str = "3.11",
    executor: Callable[[Path, str], MypyExecution] = execute_mypy,
) -> ValidationResult:
    root = Path(root)
    baseline = load_baseline(root / BASELINE_RELATIVE)
    previous = load_previous_baseline(root / PREVIOUS_BASELINE_RELATIVE)
    validate_baseline_ancestry(baseline, previous)
    measurement = measure_repository(root, python_version=python_version, executor=executor)
    return compare_diagnostics(
        baseline,
        measurement.diagnostics,
        python_version=python_version,
        native_python_version=measurement.attestation.python_full_version,
        interpreter_prefix_mode=(
            "venv"
            if Path(measurement.attestation.prefix) != Path(measurement.attestation.base_prefix)
            else "interpreter-prefix"
        ),
        source_file_count=measurement.source_file_count,
        current_suppressions=measurement.suppressions,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Require an exact MAINT-01A mypy baseline match or print a separately requested "
            "monotonic migration candidate."
        )
    )
    parser.add_argument(
        "--python-version",
        choices=SUPPORTED_PYTHON_VERSIONS,
        default="3.11",
        help="Mypy target semantics to validate (default: 3.11).",
    )
    parser.add_argument(
        "--print-migration-candidate",
        action="store_true",
        help=(
            "Print a canonical v3 baseline candidate only when current diagnostics and "
            "suppressions are a strict monotonic improvement."
        ),
    )
    parser.add_argument("--subject-commit", help="Exact 40-hex commit for a migration candidate.")
    parser.add_argument("--subject-tree", help="Exact 40-hex tree for a migration candidate.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if arguments.print_migration_candidate:
            if arguments.subject_commit is None or arguments.subject_tree is None:
                raise ContractError(
                    "--print-migration-candidate requires --subject-commit and --subject-tree"
                )
            active_document = load_baseline_document(ROOT / BASELINE_RELATIVE)
            baseline = validate_baseline_document(active_document)
            previous = load_previous_baseline(ROOT / PREVIOUS_BASELINE_RELATIVE)
            validate_baseline_ancestry(baseline, previous)
            measurement = measure_repository(
                ROOT,
                python_version=arguments.python_version,
            )
            candidate = build_migration_candidate(
                active_document,
                baseline,
                diagnostics=measurement.diagnostics,
                suppressions=measurement.suppressions,
                source_file_count=measurement.source_file_count,
                subject_commit=arguments.subject_commit,
                subject_tree=arguments.subject_tree,
            )
            print(json.dumps(candidate, indent=2, ensure_ascii=False))
            return 0
        if arguments.subject_commit is not None or arguments.subject_tree is not None:
            raise ContractError(
                "--subject-commit/--subject-tree are only valid with --print-migration-candidate"
            )
        result = validate_repository(python_version=arguments.python_version)
    except Exception as exc:  # pragma: no cover - last-resort fail-closed boundary
        print(f"ERROR VALIDATOR_INTERNAL_ERROR {type(exc).__name__}: {exc}")
        print("status: FAIL")
        return 1
    print(
        "PASS" if result.passed else "FAIL",
        "mypy exact-debt baseline:",
        f"native={result.native_python_version}; target={result.target_python_version};",
        f"prefix_mode={result.interpreter_prefix_mode}; source_files={result.source_file_count};",
        f"errors={result.error_count}/{result.baseline_error_count};",
        f"error_files={result.error_file_count}/{result.baseline_error_file_count};",
        f"removed={result.removed_diagnostic_count};",
        f"suppressions={result.suppression_count}/{result.baseline_suppression_count};",
        f"removed_suppressions={result.removed_suppression_count};",
        f"new_issues={len(result.errors)}",
    )
    for error in result.errors:
        print(f"ERROR {error}")
    print("status:", "PASS" if result.passed else "FAIL")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
