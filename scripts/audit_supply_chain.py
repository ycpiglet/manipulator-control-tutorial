"""Fail-closed Python vulnerability and license inventory audits for SUP-01D.

The outer program is standard-library only.  Scanner packages are installed in
a disposable virtual environment exclusively from the reviewed build and
supply-chain tool locks.  Generated evidence is restricted to
``build/validation`` and never contains local interpreter or license-file paths.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = Path("build/validation")
BUILD_LOCK = Path("requirements/locks/build.txt")
SUPPLY_CHAIN_LOCK = Path("requirements/tools/supply-chain.txt")
WAIVER_REGISTRY = Path(".agents/supply_chain/vulnerability-waivers.json")

PIP_AUDIT_VERSION = "2.10.1"
PIP_LICENSES_VERSION = "5.5.5"
PROJECT_NAME = "mujoco-manipulator-control-lab"
PROJECT_VERSION = "0.1.0"
WAIVER_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1

SOCKET_TIMEOUT_SECONDS = 15
PROCESS_TIMEOUT_SECONDS = 180
INSTALL_TIMEOUT_SECONDS = 600
MAX_POLICY_BYTES = 5 * 1024 * 1024
MAX_SCANNER_STDOUT_BYTES = 16 * 1024 * 1024
MAX_SCANNER_STDERR_BYTES = 1024 * 1024

REVIEWED_LOCKS: tuple[tuple[str, Path], ...] = (
    ("uv-tool", Path("requirements/tools/uv.txt")),
    ("build", BUILD_LOCK),
    ("runtime", Path("requirements/locks/runtime.txt")),
    ("app", Path("requirements/locks/app.txt")),
    ("dev", Path("requirements/locks/dev.txt")),
    ("app-dev", Path("requirements/locks/app-dev.txt")),
    ("package", Path("requirements/locks/package.txt")),
    ("supply-chain-tool", SUPPLY_CHAIN_LOCK),
)
LICENSE_PROFILE_LOCKS = {
    "package": ("build", "package"),
}
# These bootstrap distributions are installed by the locked installer but are
# excluded from this bounded pip-licenses profile.  The exclusion does not prove
# that they are absent from a future shipped package. ``--with-system`` plus this
# explicit list avoids pip-licenses' Python-version-dependent hidden list.
LICENSE_EXCLUDED_PACKAGES = frozenset({"pip", "setuptools", "wheel"})

_NAME_NORMALIZER = re.compile(r"[-_.]+")
_REQUIREMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9,_.-]+)\])?=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
_HASH_RE = re.compile(r"(?:^|\s)--hash=sha256:(?P<digest>[0-9a-f]{64})(?=\s|$)")
_MARKER_CONDITION_RE = re.compile(
    r"(?P<variable>python_full_version|python_version|implementation_name|"
    r"platform_machine|platform_python_implementation|sys_platform)\s*"
    r"(?P<operator><=|>=|==|!=|<|>)\s*'(?P<value>[^']+)'"
)
_VERSION_RE = re.compile(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])")

Runner = Callable[..., subprocess.CompletedProcess[str]]


class SupplyChainAuditError(RuntimeError):
    """Raised when an input, scanner, or evidence contract is not satisfied."""


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    hashes: frozenset[str]
    markers: tuple[str | None, ...]
    profiles: frozenset[str]


@dataclass(frozen=True)
class ToolEnvironment:
    python: Path
    work: Path


def canonical_name(value: str) -> str:
    return _NAME_NORMALIZER.sub("-", value).lower()


def _strict_json(text: str, *, source: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SupplyChainAuditError(f"{source} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SupplyChainAuditError(f"{source} contains non-finite JSON value {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except SupplyChainAuditError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SupplyChainAuditError(f"{source} is malformed JSON: {exc}") from exc


def _read_reviewed_file(root: Path, relative: Path) -> str:
    if relative.is_absolute() or ".." in relative.parts:
        raise SupplyChainAuditError(f"reviewed path must be repository-relative: {relative}")
    try:
        root_resolved = root.resolve(strict=True)
    except OSError as exc:
        raise SupplyChainAuditError(f"repository root is unavailable: {exc}") from exc
    candidate = root / relative
    cursor = candidate
    while cursor != root:
        if cursor.exists() and cursor.is_symlink():
            raise SupplyChainAuditError(f"reviewed path must not traverse a symlink: {relative}")
        cursor = cursor.parent
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise SupplyChainAuditError(
            f"reviewed file is unavailable or escapes root: {relative}"
        ) from exc
    if not resolved.is_file():
        raise SupplyChainAuditError(f"reviewed path is not a regular file: {relative}")
    if resolved.stat().st_size > MAX_POLICY_BYTES:
        raise SupplyChainAuditError(f"reviewed file exceeds size limit: {relative}")
    try:
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SupplyChainAuditError(f"cannot read reviewed file {relative}: {exc}") from exc


def _logical_lock_lines(text: str, *, source: str) -> Iterator[str]:
    pending = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        logical = (pending + line).strip()
        pending = ""
        if logical:
            yield logical
    if pending:
        raise SupplyChainAuditError(f"{source} ends with an unterminated continuation")


def parse_lock_text(text: str, *, profile: str, source: str) -> dict[str, LockedRequirement]:
    parsed: dict[str, LockedRequirement] = {}
    saw_binary_directive = False
    for logical in _logical_lock_lines(text, source=source):
        if logical == "--only-binary :all:":
            if saw_binary_directive:
                raise SupplyChainAuditError(f"{source} repeats --only-binary :all:")
            saw_binary_directive = True
            continue
        hashes = _HASH_RE.findall(logical)
        without_hashes = _HASH_RE.sub("", logical).strip()
        if "--hash" in without_hashes or not hashes:
            raise SupplyChainAuditError(
                f"{source} requirement must have one or more lowercase SHA-256 hashes: {logical!r}"
            )
        if len(hashes) != len(set(hashes)):
            raise SupplyChainAuditError(f"{source} requirement repeats a SHA-256 hash")
        match = _REQUIREMENT_RE.fullmatch(without_hashes)
        if match is None:
            raise SupplyChainAuditError(
                f"{source} contains a non-exact or unsafe requirement: {without_hashes!r}"
            )
        name = canonical_name(match.group("name"))
        version = match.group("version")
        marker = match.group("marker")
        existing = parsed.get(name)
        if existing is not None and existing.version != version:
            raise SupplyChainAuditError(
                f"{source} pins conflicting versions for {name}: "
                f"{existing.version} and {version}"
            )
        parsed[name] = LockedRequirement(
            name=name,
            version=version,
            hashes=frozenset(hashes) | (existing.hashes if existing else frozenset()),
            markers=tuple(
                sorted(
                    set((existing.markers if existing else ())) | {marker},
                    key=lambda item: (item is not None, item or ""),
                )
            ),
            profiles=frozenset({profile}),
        )
    if not saw_binary_directive:
        raise SupplyChainAuditError(f"{source} is missing --only-binary :all:")
    if not parsed:
        raise SupplyChainAuditError(f"{source} contains no locked requirements")
    return parsed


def merge_lock_inventories(
    inventories: Mapping[str, Mapping[str, LockedRequirement]],
) -> dict[str, LockedRequirement]:
    merged: dict[str, LockedRequirement] = {}
    for profile in sorted(inventories):
        for name, requirement in inventories[profile].items():
            existing = merged.get(name)
            if existing is not None and existing.version != requirement.version:
                raise SupplyChainAuditError(
                    f"reviewed locks conflict for {name}: {existing.version} in "
                    f"{sorted(existing.profiles)} versus {requirement.version} in {profile}"
                )
            merged[name] = LockedRequirement(
                name=name,
                version=requirement.version,
                hashes=requirement.hashes | (existing.hashes if existing else frozenset()),
                markers=tuple(
                    sorted(
                        set(requirement.markers) | set(existing.markers if existing else ()),
                        key=lambda item: (item is not None, item or ""),
                    )
                ),
                profiles=requirement.profiles | (existing.profiles if existing else frozenset()),
            )
    return dict(sorted(merged.items()))


def load_reviewed_locks(
    root: Path = ROOT,
) -> tuple[dict[str, dict[str, LockedRequirement]], dict[str, LockedRequirement]]:
    profiles: dict[str, dict[str, LockedRequirement]] = {}
    for profile, relative in REVIEWED_LOCKS:
        profiles[profile] = parse_lock_text(
            _read_reviewed_file(root, relative),
            profile=profile,
            source=relative.as_posix(),
        )
    tool_inventory = profiles["supply-chain-tool"]
    expected_tools = {
        "pip-audit": PIP_AUDIT_VERSION,
        "pip-licenses": PIP_LICENSES_VERSION,
    }
    for name, expected_version in expected_tools.items():
        locked = tool_inventory.get(name)
        if locked is None or locked.version != expected_version:
            found = None if locked is None else locked.version
            raise SupplyChainAuditError(
                f"supply-chain tool lock must pin {name}=={expected_version}; found {found!r}"
            )
    return profiles, merge_lock_inventories(profiles)


def render_canonical_requirements(inventory: Mapping[str, LockedRequirement]) -> str:
    lines = ["--only-binary :all:", ""]
    for name in sorted(inventory):
        requirement = inventory[name]
        hashes = sorted(requirement.hashes)
        if not hashes:
            raise SupplyChainAuditError(f"canonical requirement {name} has no hashes")
        lines.append(f"{name}=={requirement.version} \\")
        for index, digest in enumerate(hashes):
            suffix = " \\" if index < len(hashes) - 1 else ""
            lines.append(f"    --hash=sha256:{digest}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_waiver_registry(root: Path = ROOT) -> dict[str, Any]:
    data = _strict_json(
        _read_reviewed_file(root, WAIVER_REGISTRY),
        source=WAIVER_REGISTRY.as_posix(),
    )
    if not isinstance(data, dict) or set(data) != {"schema_version", "waivers"}:
        raise SupplyChainAuditError(
            "vulnerability waiver registry must contain exactly schema_version and waivers"
        )
    if data["schema_version"] != WAIVER_SCHEMA_VERSION:
        raise SupplyChainAuditError("vulnerability waiver registry schema_version must be 1")
    waivers = data["waivers"]
    if not isinstance(waivers, list):
        raise SupplyChainAuditError("vulnerability waivers must be a list")
    if waivers:
        raise SupplyChainAuditError(
            "vulnerability waivers are not authorized; owner approval is required for any entry"
        )
    return data


def sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    for key in list(environment):
        if key.upper().startswith("PIP_AUDIT_"):
            del environment[key]
        elif key.upper() in {"PYTHONHOME", "PYTHONPATH"}:
            del environment[key]
    environment["PYTHONPATH"] = ""
    return environment


def _execute(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    environment: Mapping[str, str],
    runner: Runner | None = None,
) -> subprocess.CompletedProcess[str]:
    invoke = subprocess.run if runner is None else runner
    try:
        completed = invoke(
            list(command),
            cwd=str(cwd),
            env=dict(environment),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SupplyChainAuditError(f"command timed out after {timeout}s: {command[0]}") from exc
    except OSError as exc:
        raise SupplyChainAuditError(f"cannot execute command {command[0]}: {exc}") from exc
    if not isinstance(completed.stdout, str) or not isinstance(completed.stderr, str):
        raise SupplyChainAuditError("scanner subprocess did not return text output")
    if len(completed.stdout.encode("utf-8")) > MAX_SCANNER_STDOUT_BYTES:
        raise SupplyChainAuditError("scanner stdout exceeds the bounded evidence limit")
    if len(completed.stderr.encode("utf-8")) > MAX_SCANNER_STDERR_BYTES:
        raise SupplyChainAuditError("scanner stderr exceeds the bounded diagnostic limit")
    return completed


def _require_success(completed: subprocess.CompletedProcess[str], *, action: str) -> None:
    if completed.returncode != 0:
        raise SupplyChainAuditError(f"{action} failed with exit code {completed.returncode}")


def _tool_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def locked_install_command(python: Path, lock: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--force-reinstall",
        "--require-hashes",
        "--only-binary=:all:",
        "-r",
        str(lock),
    ]


def _verify_tool_version(
    python: Path,
    module: str,
    expected: str,
    *,
    cwd: Path,
    environment: Mapping[str, str],
    runner: Runner | None = None,
) -> None:
    completed = _execute(
        [str(python), "-m", module, "--version"],
        cwd=cwd,
        timeout=PROCESS_TIMEOUT_SECONDS,
        environment=environment,
        runner=runner,
    )
    _require_success(completed, action=f"{module} version check")
    versions = _VERSION_RE.findall(completed.stdout.strip())
    if versions != [expected]:
        reported = completed.stdout.strip()
        raise SupplyChainAuditError(
            f"{module} version must be exactly {expected}; scanner reported {reported!r}"
        )


@contextmanager
def disposable_tool_environment(
    root: Path = ROOT,
    *,
    runner: Runner | None = None,
) -> Iterator[ToolEnvironment]:
    environment = sanitized_environment()
    with tempfile.TemporaryDirectory(prefix="mclab-supply-chain-") as temporary:
        work = Path(temporary)
        venv = work / "venv"
        created = _execute(
            [sys.executable, "-m", "venv", str(venv)],
            cwd=root,
            timeout=PROCESS_TIMEOUT_SECONDS,
            environment=environment,
            runner=runner,
        )
        _require_success(created, action="disposable scanner venv creation")
        python = _tool_python(venv)
        for relative in (BUILD_LOCK, SUPPLY_CHAIN_LOCK):
            installed = _execute(
                locked_install_command(python, root / relative),
                cwd=root,
                timeout=INSTALL_TIMEOUT_SECONDS,
                environment=environment,
                runner=runner,
            )
            _require_success(installed, action=f"locked tool install from {relative.as_posix()}")
        _verify_tool_version(
            python,
            "pip_audit",
            PIP_AUDIT_VERSION,
            cwd=work,
            environment=environment,
            runner=runner,
        )
        _verify_tool_version(
            python,
            "piplicenses",
            PIP_LICENSES_VERSION,
            cwd=work,
            environment=environment,
            runner=runner,
        )
        yield ToolEnvironment(python=python, work=work)


def vulnerability_command(python: Path, requirements: Path, cache: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "pip_audit",
        "--strict",
        "--no-deps",
        "--require-hashes",
        "--disable-pip",
        "--format",
        "json",
        "--vulnerability-service",
        "pypi",
        "--timeout",
        str(SOCKET_TIMEOUT_SECONDS),
        "--cache-dir",
        str(cache),
        "--progress-spinner",
        "off",
        "--aliases",
        "on",
        "--desc",
        "off",
        "--requirement",
        str(requirements),
    ]


def _nonempty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SupplyChainAuditError(f"scanner field {field} must be a non-empty string")
    return value.strip()


def _normal_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SupplyChainAuditError(f"scanner field {field} must be a list")
    normalized = [_nonempty_string(item, field=field) for item in value]
    return sorted(set(normalized), key=lambda item: (item.casefold(), item))


def normalize_vulnerability_output(
    stdout: str,
    *,
    returncode: int,
    inventory: Mapping[str, LockedRequirement],
) -> dict[str, Any]:
    if returncode not in {0, 1}:
        raise SupplyChainAuditError(
            f"pip-audit returned unsupported exit code {returncode}; only 0 and 1 are valid"
        )
    raw = _strict_json(stdout, source="pip-audit stdout")
    if not isinstance(raw, dict) or set(raw) != {"dependencies", "fixes"}:
        raise SupplyChainAuditError("pip-audit JSON must contain exactly dependencies and fixes")
    if raw["fixes"] != []:
        raise SupplyChainAuditError("pip-audit reported fixes even though fix mode is disabled")
    dependencies = raw["dependencies"]
    if not isinstance(dependencies, list):
        raise SupplyChainAuditError("pip-audit dependencies must be a list")
    normalized: dict[str, dict[str, Any]] = {}
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise SupplyChainAuditError("pip-audit dependency must be an object")
        if "skip_reason" in dependency:
            raise SupplyChainAuditError("pip-audit skipped a locked dependency")
        if set(dependency) != {"name", "version", "vulns"}:
            raise SupplyChainAuditError("pip-audit dependency has unexpected or missing fields")
        name = canonical_name(_nonempty_string(dependency["name"], field="dependency.name"))
        version = _nonempty_string(dependency["version"], field="dependency.version")
        if name in normalized:
            raise SupplyChainAuditError(f"pip-audit returned duplicate dependency {name}")
        vulns = dependency["vulns"]
        if not isinstance(vulns, list):
            raise SupplyChainAuditError(f"pip-audit vulns for {name} must be a list")
        normalized_vulns: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for vuln in vulns:
            if not isinstance(vuln, dict) or set(vuln) != {
                "id",
                "fix_versions",
                "aliases",
            }:
                raise SupplyChainAuditError(
                    f"pip-audit vulnerability for {name} has invalid fields"
                )
            identifier = _nonempty_string(vuln["id"], field="vulnerability.id")
            if identifier in seen_ids:
                raise SupplyChainAuditError(
                    f"pip-audit repeated vulnerability {identifier} for {name}"
                )
            seen_ids.add(identifier)
            normalized_vulns.append(
                {
                    "id": identifier,
                    "aliases": _normal_string_list(vuln["aliases"], field="aliases"),
                    "fix_versions": _normal_string_list(
                        vuln["fix_versions"], field="fix_versions"
                    ),
                }
            )
        normalized[name] = {
            "name": name,
            "version": version,
            "vulnerabilities": sorted(
                normalized_vulns,
                key=lambda item: (item["id"].casefold(), item["id"]),
            ),
        }
    expected_names = set(inventory)
    actual_names = set(normalized)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise SupplyChainAuditError(
            f"pip-audit dependency coverage drift: missing={missing}, extra={extra}"
        )
    for name, requirement in inventory.items():
        if normalized[name]["version"] != requirement.version:
            raise SupplyChainAuditError(
                f"pip-audit version drift for {name}: {normalized[name]['version']} "
                f"!= {requirement.version}"
            )
    finding_count = sum(len(item["vulnerabilities"]) for item in normalized.values())
    if (returncode == 0) != (finding_count == 0):
        raise SupplyChainAuditError(
            f"pip-audit exit/result inconsistency: exit={returncode}, findings={finding_count}"
        )
    output_dependencies = []
    for name in sorted(normalized):
        requirement = inventory[name]
        output_dependencies.append(
            normalized[name]
            | {
                "hashes": [f"sha256:{digest}" for digest in sorted(requirement.hashes)],
                "profiles": sorted(requirement.profiles),
            }
        )
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "audit": "python-vulnerabilities",
        "scope": "all-reviewed-python-locks",
        "lock_profiles": [profile for profile, _ in REVIEWED_LOCKS],
        "tool": {
            "name": "pip-audit",
            "version": PIP_AUDIT_VERSION,
            "service": "pypi",
            "strict": True,
            "dependency_resolution": False,
            "hashes_required": True,
        },
        "waiver_policy": {
            "schema_version": WAIVER_SCHEMA_VERSION,
            "authorized_waivers": 0,
            "applied_waivers": 0,
        },
        "dependencies": output_dependencies,
        "dependency_count": len(output_dependencies),
        "finding_count": finding_count,
        "result": "pass" if finding_count == 0 else "fail",
    }


_TARGET_PROBE_CODE = (
    "import importlib.metadata as m,json,platform,sys;"
    "d=[{'name':x.metadata.get('Name'),'version':x.version} for x in m.distributions()];"
    "e={'implementation_name':sys.implementation.name,"
    "'python_full_version':platform.python_version(),"
    "'python_version':f'{sys.version_info.major}.{sys.version_info.minor}',"
    "'platform_machine':platform.machine(),"
    "'platform_python_implementation':platform.python_implementation(),"
    "'sys_platform':sys.platform};"
    "print(json.dumps({'environment':e,'distributions':d},sort_keys=True))"
)


def probe_target_command(target_python: Path) -> list[str]:
    return [str(target_python), "-c", _TARGET_PROBE_CODE]


def normalize_target_probe(stdout: str) -> tuple[dict[str, str], dict[str, str]]:
    raw = _strict_json(stdout, source="target Python inventory")
    if not isinstance(raw, dict) or set(raw) != {"environment", "distributions"}:
        raise SupplyChainAuditError(
            "target Python inventory must contain exactly environment and distributions"
        )
    environment = raw["environment"]
    expected_environment_keys = {
        "implementation_name",
        "python_full_version",
        "python_version",
        "platform_machine",
        "platform_python_implementation",
        "sys_platform",
    }
    if not isinstance(environment, dict) or set(environment) != expected_environment_keys:
        raise SupplyChainAuditError("target Python environment fields are invalid")
    normalized_environment = {
        key: _nonempty_string(value, field=f"environment.{key}")
        for key, value in environment.items()
    }
    distributions = raw["distributions"]
    if not isinstance(distributions, list):
        raise SupplyChainAuditError("target Python distributions must be a list")
    inventory: dict[str, str] = {}
    for distribution in distributions:
        if not isinstance(distribution, dict) or set(distribution) != {"name", "version"}:
            raise SupplyChainAuditError("target Python distribution entry is invalid")
        name = canonical_name(_nonempty_string(distribution["name"], field="distribution.name"))
        version = _nonempty_string(distribution["version"], field="distribution.version")
        if name in inventory:
            raise SupplyChainAuditError(f"target Python has duplicate distribution {name}")
        inventory[name] = version
    return normalized_environment, dict(sorted(inventory.items()))


def _version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
        raise SupplyChainAuditError(f"unsupported marker version value: {value!r}")
    return tuple(int(part) for part in value.split("."))


def _compare_marker_values(actual: str, operator: str, expected: str, *, numeric: bool) -> bool:
    if numeric:
        left = _version_tuple(actual)
        right = _version_tuple(expected)
        width = max(len(left), len(right))
        left += (0,) * (width - len(left))
        right += (0,) * (width - len(right))
    else:
        left = actual
        right = expected
    comparisons = {
        "==": left == right,
        "!=": left != right,
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
    }
    if not numeric and operator not in {"==", "!="}:
        raise SupplyChainAuditError(f"unsupported string marker operator: {operator}")
    return comparisons[operator]


def marker_applies(marker: str | None, environment: Mapping[str, str]) -> bool:
    if marker is None:
        return True
    clauses = marker.split(" or ")
    clause_results: list[bool] = []
    for clause in clauses:
        if clause.startswith("(") and clause.endswith(")"):
            clause = clause[1:-1]
        elif len(clauses) > 1:
            raise SupplyChainAuditError(f"unsupported marker clause: {clause!r}")
        results: list[bool] = []
        for condition in clause.split(" and "):
            match = _MARKER_CONDITION_RE.fullmatch(condition)
            if match is None:
                raise SupplyChainAuditError(f"unsupported lock marker condition: {condition!r}")
            variable = match.group("variable")
            if variable not in environment:
                raise SupplyChainAuditError(f"target environment lacks marker field {variable}")
            results.append(
                _compare_marker_values(
                    environment[variable],
                    match.group("operator"),
                    match.group("value"),
                    numeric=variable in {"python_full_version", "python_version"},
                )
            )
        clause_results.append(bool(results) and all(results))
    return any(clause_results)


def expected_license_inventory(
    lock_profiles: Mapping[str, Mapping[str, LockedRequirement]],
    *,
    profile: str,
    environment: Mapping[str, str],
) -> dict[str, str]:
    if profile not in LICENSE_PROFILE_LOCKS:
        raise SupplyChainAuditError(f"unsupported license profile: {profile}")
    expected: dict[str, str] = {}
    for lock_profile in LICENSE_PROFILE_LOCKS[profile]:
        for name, requirement in lock_profiles[lock_profile].items():
            if not any(marker_applies(marker, environment) for marker in requirement.markers):
                continue
            previous = expected.get(name)
            if previous is not None and previous != requirement.version:
                raise SupplyChainAuditError(
                    f"license profile conflicts for {name}: {previous} and {requirement.version}"
                )
            expected[name] = requirement.version
    for excluded in LICENSE_EXCLUDED_PACKAGES:
        expected.pop(excluded, None)
    expected[canonical_name(PROJECT_NAME)] = PROJECT_VERSION
    return dict(sorted(expected.items()))


def validate_target_inventory(actual: Mapping[str, str], expected: Mapping[str, str]) -> None:
    filtered_actual = {
        name: version for name, version in actual.items() if name not in LICENSE_EXCLUDED_PACKAGES
    }
    missing = sorted(set(expected) - set(filtered_actual))
    mismatched = sorted(
        name
        for name in set(expected) & set(filtered_actual)
        if expected[name] != filtered_actual[name]
    )
    if missing or mismatched:
        raise SupplyChainAuditError(
            "target Python package-profile drift: "
            f"missing={missing}, version_mismatch={mismatched}"
        )


def license_command(
    python: Path,
    target_python: Path,
    expected: Mapping[str, str],
) -> list[str]:
    return [
        str(python),
        "-m",
        "piplicenses",
        "--python",
        str(target_python),
        "--from",
        "mixed",
        "--format",
        "json",
        "--with-urls",
        "--with-system",
        "--with-license-file",
        "--with-notice-file",
        "--no-license-path",
        "--ignore-packages",
        *sorted(LICENSE_EXCLUDED_PACKAGES),
        "--packages",
        *sorted(expected),
    ]


def _normalize_text(value: Any, *, field: str, allow_absent: bool = False) -> str | None:
    if not isinstance(value, str):
        raise SupplyChainAuditError(f"pip-licenses field {field} must be a string")
    unix_text = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in unix_text.split("\n")).strip()
    if not normalized or normalized.casefold() == "unknown":
        if allow_absent:
            return None
        raise SupplyChainAuditError(f"pip-licenses field {field} must not be empty or UNKNOWN")
    return normalized


def normalize_license_output(
    stdout: str,
    *,
    expected: Mapping[str, str],
    environment: Mapping[str, str],
    profile: str,
) -> dict[str, Any]:
    raw = _strict_json(stdout, source="pip-licenses stdout")
    if not isinstance(raw, list):
        raise SupplyChainAuditError("pip-licenses JSON must be a list")
    required_fields = {"Name", "Version", "License", "URL", "LicenseText", "NoticeText"}
    packages: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) != required_fields:
            raise SupplyChainAuditError(
                "pip-licenses entry must contain exactly Name, Version, License, URL, "
                "LicenseText, and NoticeText (no paths)"
            )
        name = canonical_name(_nonempty_string(item["Name"], field="license.Name"))
        if name in packages:
            raise SupplyChainAuditError(f"pip-licenses returned duplicate package {name}")
        version = _nonempty_string(item["Version"], field="license.Version")
        license_value = _normalize_text(
            item["License"], field=f"{name}.License", allow_absent=True
        )
        normalized_license: str | None = None
        if license_value is not None:
            licenses = sorted(
                {part.strip() for part in license_value.split(";") if part.strip()},
                key=lambda value: (value.casefold(), value),
            )
            normalized_license = "; ".join(licenses) or None
        license_text = _normalize_text(
            item["LicenseText"], field=f"{name}.LicenseText", allow_absent=True
        )
        packages[name] = {
            "name": name,
            "version": version,
            "license": normalized_license,
            "url": _normalize_text(item["URL"], field=f"{name}.URL", allow_absent=True),
            "license_text": license_text,
            "notice_text": _normalize_text(
                item["NoticeText"], field=f"{name}.NoticeText", allow_absent=True
            ),
        }
    if set(packages) != set(expected):
        missing = sorted(set(expected) - set(packages))
        extra = sorted(set(packages) - set(expected))
        raise SupplyChainAuditError(
            f"pip-licenses package coverage drift: missing={missing}, extra={extra}"
        )
    for name, expected_version in expected.items():
        if packages[name]["version"] != expected_version:
            raise SupplyChainAuditError(
                f"pip-licenses version drift for {name}: {packages[name]['version']} "
                f"!= {expected_version}"
            )
    normalized_packages = [packages[name] for name in sorted(packages)]
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "audit": "python-licenses",
        "purpose": "LIC-01 input only; not legal approval",
        "profile": profile,
        "input_lock_profiles": list(LICENSE_PROFILE_LOCKS[profile]),
        "tool": {"name": "pip-licenses", "version": PIP_LICENSES_VERSION},
        "target": {
            "implementation": environment["platform_python_implementation"],
            "implementation_name": environment["implementation_name"],
            "python_version": environment["python_full_version"],
            "sys_platform": environment["sys_platform"],
            "machine": environment["platform_machine"],
        },
        "excluded_system_packages": sorted(LICENSE_EXCLUDED_PACKAGES),
        "packages": normalized_packages,
        "package_count": len(normalized_packages),
        "metadata_gaps": {
            "license": sum(package["license"] is None for package in normalized_packages),
            "license_text": sum(
                package["license_text"] is None for package in normalized_packages
            ),
            "url": sum(package["url"] is None for package in normalized_packages),
            "notice_text": sum(
                package["notice_text"] is None for package in normalized_packages
            ),
        },
        "result": "inventory-complete",
        "compliance_status": "pending-lic-01",
    }


def validated_output_path(output: Path, *, root: Path = ROOT) -> Path:
    if output.suffix.lower() != ".json":
        raise SupplyChainAuditError("audit output must use a .json filename")
    root_lexical = Path(os.path.abspath(root))
    candidate = output if output.is_absolute() else root_lexical / output
    safe_root = root_lexical / VALIDATION_ROOT
    try:
        lexical_relative = candidate.relative_to(safe_root)
        if ".." in lexical_relative.parts:
            raise ValueError("ambiguous parent component")
        root_resolved = root_lexical.resolve(strict=True)
        safe_resolved = safe_root.resolve(strict=False)
        candidate_resolved = candidate.resolve(strict=False)
        safe_resolved.relative_to(root_resolved)
        candidate_resolved.relative_to(safe_resolved)
    except (OSError, ValueError) as exc:
        raise SupplyChainAuditError(
            "audit output must remain under build/validation"
        ) from exc
    cursor = candidate
    while cursor != root_lexical:
        if cursor == cursor.parent:
            raise SupplyChainAuditError("audit output has no lexical repository parent")
        if cursor.exists() and cursor.is_symlink():
            raise SupplyChainAuditError("audit output must not traverse or replace a symlink")
        cursor = cursor.parent
    if candidate.exists():
        raise SupplyChainAuditError("audit output already exists; evidence is not overwritten")
    return candidate_resolved


def validated_target_python_path(target_python: Path, *, root: Path = ROOT) -> Path:
    """Validate a target interpreter without dereferencing a venv Python symlink."""

    candidate = target_python if target_python.is_absolute() else root / target_python
    candidate = Path(os.path.abspath(candidate))
    if not candidate.exists() or not candidate.is_file():
        raise SupplyChainAuditError("target Python is unavailable or is not a file")
    return candidate


def write_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        raise SupplyChainAuditError(f"cannot write audit evidence: {exc}") from exc


def run_vulnerability_audit(
    output: Path,
    *,
    root: Path = ROOT,
    runner: Runner | None = None,
) -> int:
    destination = validated_output_path(output, root=root)
    load_waiver_registry(root)
    _, inventory = load_reviewed_locks(root)
    with disposable_tool_environment(root, runner=runner) as tools:
        canonical = tools.work / "canonical-reviewed-requirements.txt"
        canonical.write_text(render_canonical_requirements(inventory), encoding="utf-8")
        completed = _execute(
            vulnerability_command(tools.python, canonical, tools.work / "cache"),
            cwd=tools.work,
            timeout=PROCESS_TIMEOUT_SECONDS,
            environment=sanitized_environment(),
            runner=runner,
        )
        evidence = normalize_vulnerability_output(
            completed.stdout,
            returncode=completed.returncode,
            inventory=inventory,
        )
    write_evidence(destination, evidence)
    return 0 if evidence["result"] == "pass" else 1


def run_license_audit(
    output: Path,
    *,
    target_python: Path,
    profile: str,
    root: Path = ROOT,
    runner: Runner | None = None,
) -> int:
    destination = validated_output_path(output, root=root)
    target = validated_target_python_path(target_python, root=root)
    lock_profiles, _ = load_reviewed_locks(root)
    with disposable_tool_environment(root, runner=runner) as tools:
        probed = _execute(
            probe_target_command(target),
            cwd=tools.work,
            timeout=PROCESS_TIMEOUT_SECONDS,
            environment=sanitized_environment(),
            runner=runner,
        )
        _require_success(probed, action="target Python inventory probe")
        environment, actual_inventory = normalize_target_probe(probed.stdout)
        expected = expected_license_inventory(
            lock_profiles,
            profile=profile,
            environment=environment,
        )
        validate_target_inventory(actual_inventory, expected)
        scanned = _execute(
            license_command(tools.python, target, expected),
            cwd=tools.work,
            timeout=PROCESS_TIMEOUT_SECONDS,
            environment=sanitized_environment(),
            runner=runner,
        )
        _require_success(scanned, action="pip-licenses scan")
        evidence = normalize_license_output(
            scanned.stdout,
            expected=expected,
            environment=environment,
            profile=profile,
        )
    write_evidence(destination, evidence)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    vulnerabilities = subparsers.add_parser(
        "vulnerabilities", help="Audit all reviewed Python locks with pip-audit."
    )
    vulnerabilities.add_argument("--output", type=Path, required=True)
    licenses = subparsers.add_parser(
        "licenses", help="Create a deterministic LIC-01 input with pip-licenses."
    )
    licenses.add_argument("--output", type=Path, required=True)
    licenses.add_argument("--target-python", type=Path, required=True)
    licenses.add_argument("--profile", choices=sorted(LICENSE_PROFILE_LOCKS), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.implementation.name != "cpython" or not ((3, 10) <= sys.version_info[:2] < (3, 13)):
        print("Supply-chain audits require CPython 3.10, 3.11, or 3.12.", file=sys.stderr)
        return 2
    try:
        if args.mode == "vulnerabilities":
            return run_vulnerability_audit(args.output)
        return run_license_audit(
            args.output,
            target_python=args.target_python,
            profile=args.profile,
        )
    except SupplyChainAuditError as exc:
        print(f"Supply-chain audit failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
