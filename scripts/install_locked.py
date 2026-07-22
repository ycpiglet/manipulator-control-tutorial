"""Install or verify MCLab dependencies from reviewed, hash-locked profiles.

Third-party packages are installed separately from the local editable project so
that build isolation cannot resolve unreviewed dependencies behind the lock.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
STATE_FILE = VENV / ".mclab-lock-state.json"
PROJECT_NAME = "mujoco-manipulator-control-lab"
PROJECT_VERSION = "0.1.0"
STATE_SCHEMA = 1

BUILD_LOCK = Path("requirements/locks/build.txt")
PROFILE_LOCKS = {
    "build": BUILD_LOCK,
    "runtime": Path("requirements/locks/runtime.txt"),
    "app": Path("requirements/locks/app.txt"),
    "dev": Path("requirements/locks/dev.txt"),
    "app-dev": Path("requirements/locks/app-dev.txt"),
    "package": Path("requirements/locks/package.txt"),
}

PROFILE_CAPABILITIES = {
    "build": frozenset({"build"}),
    "runtime": frozenset({"build", "runtime"}),
    "app": frozenset({"app", "build", "runtime"}),
    "dev": frozenset({"build", "dev", "runtime"}),
    "app-dev": frozenset({"app", "build", "dev", "runtime"}),
    "package": frozenset({"app", "build", "dev", "package", "runtime"}),
}
CAPABILITIES_TO_PROFILE = {
    capabilities: profile for profile, capabilities in PROFILE_CAPABILITIES.items()
}
FRESH_VENV_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})

CAPABILITY_IMPORTS = {
    "build": ("packaging", "pip", "setuptools", "wheel"),
    "runtime": ("matplotlib", "mclab", "mujoco", "numpy", "yaml"),
    "app": ("PySide6.QtCore", "PySide6.QtQml", "PySide6.QtQuick"),
    "dev": ("axe_playwright_python", "mypy", "playwright", "pytest", "ruff"),
    "package": ("PyInstaller",),
}

_NAME_NORMALIZER = re.compile(r"[-_.]+")
_LOCK_REQUIREMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\[[A-Za-z0-9,_.-]+\])?=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
_MARKER_CONDITION_RE = re.compile(
    r"(?P<variable>python_full_version|python_version|implementation_name|"
    r"platform_machine|platform_python_implementation|sys_platform)\s*"
    r"(?P<operator><=|>=|==|!=|<|>)\s*'(?P<value>[^']+)'"
)


class LockedInstallError(RuntimeError):
    """Raised when the reviewed install contract cannot be satisfied."""


def _normalise_name(name: str) -> str:
    return _NAME_NORMALIZER.sub("-", name).lower()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _compare_version_values(left: str, operator: str, right: str) -> bool:
    if not re.fullmatch(r"\d+(?:\.\d+)*", left) or not re.fullmatch(r"\d+(?:\.\d+)*", right):
        raise LockedInstallError(
            f"Unsupported version marker comparison: {left} {operator} {right}"
        )
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


def _marker_environment() -> dict[str, str]:
    return {
        "python_full_version": platform.python_version(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "implementation_name": sys.implementation.name,
        "platform_machine": platform.machine(),
        "platform_python_implementation": platform.python_implementation(),
        "sys_platform": sys.platform,
    }


def _marker_applies(marker: str, environment: dict[str, str] | None = None) -> bool:
    """Evaluate the constrained marker grammar emitted by the reviewed generator."""

    values = _marker_environment() if environment is None else environment
    clauses = marker.split(" or ")
    if not clauses:
        raise LockedInstallError(f"Invalid empty lock marker: {marker!r}")
    clause_results: list[bool] = []
    for clause in clauses:
        if clause.startswith("(") and clause.endswith(")"):
            clause = clause[1:-1]
        elif len(clauses) != 1:
            raise LockedInstallError(f"Unsupported lock marker clause: {clause!r}")
        conditions = clause.split(" and ")
        condition_results: list[bool] = []
        for condition in conditions:
            match = _MARKER_CONDITION_RE.fullmatch(condition)
            if match is None:
                raise LockedInstallError(f"Unsupported lock marker condition: {condition!r}")
            variable = match.group("variable")
            operator = match.group("operator")
            expected = match.group("value")
            actual = values.get(variable)
            if actual is None:
                raise LockedInstallError(f"Missing lock marker environment value: {variable}")
            if variable in {"python_full_version", "python_version"}:
                condition_results.append(_compare_version_values(actual, operator, expected))
            elif operator == "==":
                condition_results.append(actual == expected)
            elif operator == "!=":
                condition_results.append(actual != expected)
            else:
                raise LockedInstallError(
                    f"Unsupported string lock marker comparison: {condition!r}"
                )
        clause_results.append(bool(condition_results) and all(condition_results))
    return any(clause_results)


def support_error(
    profile: str,
    *,
    implementation: str | None = None,
    python_version: tuple[int, int] | None = None,
    system: str | None = None,
    machine: str | None = None,
    pointer_bits: int | None = None,
    libc: tuple[str, str] | None = None,
    macos_version: str | None = None,
    windows_version: tuple[int, int, int] | None = None,
) -> str | None:
    """Return an actionable compatibility error, or ``None`` when supported."""

    if profile not in PROFILE_LOCKS:
        return f"Unknown locked dependency profile: {profile!r}."

    implementation = implementation or sys.implementation.name
    python_version = python_version or (sys.version_info.major, sys.version_info.minor)
    system = system or platform.system()
    machine = machine or platform.machine()
    pointer_bits = struct.calcsize("P") * 8 if pointer_bits is None else pointer_bits

    if implementation.lower() != "cpython" or not ((3, 10) <= python_version < (3, 13)):
        return (
            "MCLab's reviewed locks require CPython 3.10, 3.11, or 3.12; "
            f"found {implementation} {python_version[0]}.{python_version[1]}. "
            "Install a supported CPython and recreate .venv."
        )

    if pointer_bits != 64:
        return (
            "MCLab's reviewed locks require a 64-bit CPython interpreter; "
            f"found a {pointer_bits}-bit interpreter. Install 64-bit CPython and recreate .venv."
        )

    system_key = system.lower()
    supported_pair = (
        (system_key == "linux" and machine == "x86_64")
        or (system_key == "windows" and machine == "AMD64")
        or (system_key == "darwin" and machine in {"arm64", "x86_64"})
    )
    if not supported_pair:
        return (
            "No reviewed MCLab lock target exists for "
            f"{system or 'unknown OS'} {machine or 'unknown architecture'}. Supported targets are "
            "Linux x86-64, Windows AMD64, and macOS arm64/x86-64."
        )

    if system_key == "linux":
        if profile == "build":
            return None
        libc_name, libc_version = libc or platform.libc_ver()
        minimum = (2, 34) if "app" in PROFILE_CAPABILITIES[profile] else (2, 28)
        if libc_name.lower() not in {"glibc", "gnu libc"} or _version_tuple(libc_version) < minimum:
            found = f"{libc_name or 'unknown libc'} {libc_version or 'unknown version'}"
            surface = "desktop app" if minimum == (2, 34) else "runtime/dev profiles"
            return (
                f"The locked {surface} require Linux x86-64 with glibc "
                f"{minimum[0]}.{minimum[1]} or newer; "
                f"found {found}. Upgrade the host runtime or use a supported OS."
            )
    elif system_key == "darwin":
        if profile == "build":
            return None
        current_macos = macos_version if macos_version is not None else platform.mac_ver()[0]
        minimum = (13,) if "app" in PROFILE_CAPABILITIES[profile] else (11,)
        if _version_tuple(current_macos) < minimum:
            surface = "desktop app" if minimum == (13,) else "runtime/dev profiles"
            return (
                f"The locked {surface} require macOS {minimum[0]} or newer; "
                f"found {current_macos or 'an unknown macOS version'}."
            )
    elif system_key == "windows" and "app" in PROFILE_CAPABILITIES[profile]:
        current_windows = windows_version
        if current_windows is None:
            try:
                platform_version = sys.getwindowsversion().platform_version
                current_windows = tuple(int(part) for part in platform_version[:3])
            except (AttributeError, TypeError, ValueError):
                parsed = _version_tuple(platform.version())[:3]
                current_windows = parsed if len(parsed) == 3 else None
        minimum_windows = (10, 0, 17763)
        if current_windows is None or current_windows < minimum_windows:
            found = (
                ".".join(str(part) for part in current_windows)
                if current_windows is not None
                else "an unknown Windows version"
            )
            return (
                "The locked desktop app requires Windows 10 version 1809 "
                f"(build 17763) or newer; found {found}. Upgrade Windows before setup."
            )
    return None


def _platform_fingerprint() -> dict[str, str]:
    libc_name, libc_version = platform.libc_ver()
    return {
        "implementation": sys.implementation.name,
        "python": platform.python_version(),
        "cache_tag": sys.implementation.cache_tag or "",
        "system": platform.system(),
        "machine": platform.machine(),
        "pointer_bits": str(struct.calcsize("P") * 8),
        "release": platform.release(),
        "macos": platform.mac_ver()[0],
        "libc": " ".join(part for part in (libc_name, libc_version) if part),
        "executable": str(Path(sys.executable).absolute()),
        "prefix": str(Path(sys.prefix).resolve()),
    }


def _is_reparse_point(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(path_stat.st_mode) or bool(attributes & reparse_flag)


def _allowed_venv_link(path: Path, venv: Path) -> bool:
    try:
        relative = path.relative_to(venv)
    except ValueError:
        return False
    folded = tuple(part.casefold() for part in relative.parts)
    if folded == ("lib64",):
        try:
            return path.resolve(strict=True) == (venv / "lib").resolve(strict=True)
        except OSError:
            return False
    if len(folded) == 2 and folded[0] in {"bin", "scripts"}:
        return folded[1].startswith("python") and path.resolve().is_file()
    return False


def project_venv_redirect_error(venv: Path = VENV) -> str | None:
    """Reject links/junctions that can redirect installer writes outside ``venv``."""

    try:
        if not venv.exists() and not venv.is_symlink():
            return None
        root_stat = venv.lstat()
        absolute = os.path.normcase(str(venv.absolute()))
        resolved = os.path.normcase(str(venv.resolve(strict=True)))
        if _is_reparse_point(root_stat) or absolute != resolved:
            return "the .venv root or one of its ancestors redirects elsewhere"

        pending = [venv]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    entry_stat = entry.stat(follow_symlinks=False)
                    if _is_reparse_point(entry_stat):
                        if not _allowed_venv_link(path, venv):
                            return f"{path.relative_to(venv)} is a link or reparse point"
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
    except (OSError, ValueError) as exc:
        return f"the .venv structure cannot be verified: {exc}"
    return None


def _is_project_venv() -> bool:
    if _project_venv_is_linked():
        return False
    try:
        return os.path.normcase(str(Path(sys.prefix).absolute())) == os.path.normcase(
            str(VENV.absolute())
        )
    except OSError:
        return False


def _project_venv_is_linked() -> bool:
    return project_venv_redirect_error() is not None


def _environment_error(*, allow_external: bool) -> str | None:
    if allow_external:
        return None
    redirect_error = project_venv_redirect_error()
    if redirect_error:
        return (
            f"Refusing unsafe project environment {VENV}: {redirect_error}. Remove .venv, "
            "create it again from a trusted CPython, and retry."
        )
    if not _is_project_venv():
        activate = ".venv\\Scripts\\activate" if os.name == "nt" else "source .venv/bin/activate"
        return (
            f"Locked learner installs may modify only {VENV}. Activate it first with "
            f"`{activate}`, or use a repository launcher to create it."
        )
    return None


def _state_inputs(profile: str) -> dict[str, str]:
    paths = {
        "pyproject.toml": ROOT / "pyproject.toml",
        str(BUILD_LOCK): ROOT / BUILD_LOCK,
        "scripts/install_locked.py": Path(__file__).resolve(),
    }
    profile_lock = PROFILE_LOCKS[profile]
    paths[str(profile_lock)] = ROOT / profile_lock
    missing = [label for label, path in paths.items() if not path.is_file()]
    if missing:
        raise LockedInstallError("Missing dependency input(s): " + ", ".join(sorted(missing)))
    return {label: _sha256(path) for label, path in sorted(paths.items())}


def _distribution_inventory() -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        inventory.append(
            {
                "name": _normalise_name(name),
                "version": distribution.version,
            }
        )
    return sorted(inventory, key=lambda item: (item["name"], item["version"]))


def _inventory_hash(inventory: list[dict[str, str]]) -> str:
    payload = json.dumps(inventory, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_state() -> dict[str, Any] | None:
    if not STATE_FILE.is_file():
        return None
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _state_context_is_usable(state: dict[str, Any]) -> bool:
    schema = state.get("schema")
    profile = state.get("effective_profile")
    return (
        isinstance(schema, int)
        and not isinstance(schema, bool)
        and schema == STATE_SCHEMA
        and isinstance(profile, str)
        and profile in PROFILE_LOCKS
        and state.get("project_root") == str(ROOT.resolve())
        and state.get("platform") == _platform_fingerprint()
    )


def _stored_capabilities(state: dict[str, Any] | None) -> frozenset[str]:
    if state is None or not _state_context_is_usable(state):
        return frozenset()
    profile = state["effective_profile"]
    recorded = state.get("capabilities")
    expected = sorted(PROFILE_CAPABILITIES[profile])
    return PROFILE_CAPABILITIES[profile] if recorded == expected else frozenset()


def _installed_capabilities(inventory: list[dict[str, str]]) -> frozenset[str]:
    names = {item["name"] for item in inventory}
    capabilities = {"build"}
    if names & {"mujoco", _normalise_name(PROJECT_NAME)}:
        capabilities.add("runtime")
    if "pyside6-essentials" in names:
        capabilities.update(("app", "runtime"))
    if names & {"axe-playwright-python", "mypy", "playwright", "pytest", "ruff"}:
        capabilities.update(("dev", "runtime"))
    if "pyinstaller" in names:
        capabilities = set(PROFILE_CAPABILITIES["package"])
    return frozenset(capabilities)


def _effective_profile(
    requested: str,
    state: dict[str, Any] | None,
    inventory: list[dict[str, str]] | None = None,
) -> str:
    capabilities = PROFILE_CAPABILITIES[requested] | _stored_capabilities(state)
    if inventory is not None:
        capabilities |= _installed_capabilities(inventory)
    if "package" in capabilities:
        capabilities = PROFILE_CAPABILITIES["package"]
    profile = CAPABILITIES_TO_PROFILE.get(frozenset(capabilities))
    if profile is None:
        raise LockedInstallError(
            "Unsupported dependency capability combination: " + ", ".join(sorted(capabilities))
        )
    return profile


def _locked_versions(profile: str) -> dict[str, str]:
    paths = [ROOT / BUILD_LOCK]
    if profile != "build":
        paths.append(ROOT / PROFILE_LOCKS[profile])
    expected: dict[str, str] = {}
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if raw_line[:1].isspace() or not raw_line or raw_line.startswith(("#", "--")):
                continue
            requirement = raw_line.removesuffix("\\").rstrip()
            match = _LOCK_REQUIREMENT_RE.fullmatch(requirement)
            if match is None:
                raise LockedInstallError(
                    f"Unsupported requirement in {path.relative_to(ROOT)}: {raw_line}"
                )
            marker = match.group("marker")
            if marker is not None and not _marker_applies(marker):
                continue
            name = _normalise_name(match.group("name"))
            version = match.group("version")
            previous = expected.setdefault(name, version)
            if previous != version:
                raise LockedInstallError(
                    f"Conflicting locked versions for {name}: {previous} and {version}."
                )
    return expected


def _locked_version_errors(profile: str, inventory: list[dict[str, str]]) -> list[str]:
    installed: dict[str, set[str]] = {}
    for item in inventory:
        installed.setdefault(item["name"], set()).add(item["version"])
    errors: list[str] = []
    for name, expected in sorted(_locked_versions(profile).items()):
        actual = installed.get(name, set())
        if actual != {expected}:
            rendered = ", ".join(sorted(actual)) if actual else "missing"
            errors.append(f"{name}: expected {expected}, found {rendered}")
    return errors


def _unexpected_distribution_errors(profile: str, inventory: list[dict[str, str]]) -> list[str]:
    allowed = set(_locked_versions(profile))
    if profile != "build":
        allowed.add(_normalise_name(PROJECT_NAME))
    actual = {item["name"] for item in inventory}
    unexpected = sorted(actual - allowed)
    if not unexpected:
        return []
    return [
        "unexpected distribution(s) in the dedicated environment: "
        + ", ".join(unexpected)
        + "; recreate .venv before retrying"
    ]


def _record_integrity_for_versions(
    expected: dict[str, str],
) -> tuple[dict[str, object], list[str]]:
    """Verify RECORD hashes for exact distributions without importing their code."""

    distributions: dict[str, list[importlib.metadata.Distribution]] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            distributions.setdefault(_normalise_name(name), []).append(distribution)

    entries: list[dict[str, str]] = []
    errors: list[str] = []
    for name, version in sorted(expected.items()):
        matches = [
            distribution
            for distribution in distributions.get(name, ())
            if distribution.version == version
        ]
        if len(matches) != 1:
            errors.append(
                f"cannot verify RECORD for {name}=={version}: found {len(matches)} copies"
            )
            continue
        distribution = matches[0]
        files = distribution.files
        if files is None:
            errors.append(f"cannot verify RECORD for {name}=={version}: file list missing")
            continue
        hashed = 0
        for package_path in sorted(files, key=str):
            recorded_hash = package_path.hash
            # Bytecode is legitimately rewritten by the interpreter after import.
            if recorded_hash is None or package_path.suffix in {".pyc", ".pyo"}:
                continue
            if recorded_hash.mode != "sha256":
                errors.append(
                    f"unsupported RECORD hash for {name}=={version}: "
                    f"{package_path} uses {recorded_hash.mode}"
                )
                continue
            hashed += 1
            installed_path = Path(distribution.locate_file(package_path))
            digest = hashlib.sha256()
            try:
                with installed_path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
            except OSError as exc:
                errors.append(f"cannot read installed file {name}:{package_path}: {exc}")
                continue
            actual = base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")
            if actual != recorded_hash.value:
                errors.append(f"installed file hash mismatch: {name}:{package_path}")
                continue
            entries.append(
                {
                    "name": name,
                    "version": version,
                    "path": package_path.as_posix(),
                    "sha256": recorded_hash.value,
                }
            )
        if hashed == 0:
            errors.append(f"cannot verify RECORD for {name}=={version}: no sha256 files")

    payload = json.dumps(entries, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return {
        "files": len(entries),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }, errors


def _record_integrity(profile: str) -> tuple[dict[str, object], list[str]]:
    """Verify the selected lock plus editable loader metadata."""

    expected = dict(_locked_versions(profile))
    if profile != "build":
        expected[_normalise_name(PROJECT_NAME)] = PROJECT_VERSION
    return _record_integrity_for_versions(expected)


def _state_integrity_errors(state: dict[str, Any]) -> list[str]:
    """Trust-check recorded environment bytes before any installed code executes."""

    if not _state_context_is_usable(state):
        return ["lock state schema, repository, interpreter, or platform changed"]
    inventory = _distribution_inventory()
    recorded_inventory = state.get("inventory")
    if recorded_inventory != inventory or state.get("inventory_sha256") != _inventory_hash(
        inventory
    ):
        return ["installed distribution inventory changed"]

    expected: dict[str, str] = {}
    for item in inventory:
        name = item["name"]
        version = item["version"]
        previous = expected.setdefault(name, version)
        if previous != version:
            return [f"installed distribution inventory has conflicting versions for {name}"]
    fingerprint, errors = _record_integrity_for_versions(expected)
    if state.get("record_integrity") != fingerprint:
        errors.append("installed wheel RECORD fingerprint changed")
    return errors


def _required_imports(profile: str) -> tuple[str, ...]:
    capabilities = PROFILE_CAPABILITIES[profile]
    return tuple(
        module for capability in sorted(capabilities) for module in CAPABILITY_IMPORTS[capability]
    )


def _run(
    command: Sequence[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=ROOT,
        check=False,
        capture_output=capture_output,
        text=True,
    )


def _import_errors(profile: str) -> list[str]:
    errors: list[str] = []
    for module in _required_imports(profile):
        code = f"import importlib; importlib.import_module({module!r})"
        completed = _run([sys.executable, "-c", code], capture_output=True)
        if completed.returncode == 0:
            continue
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        errors.append(f"required import probe failed for {module}{suffix}")
    return errors


def _editable_error() -> str | None:
    try:
        distribution = importlib.metadata.distribution(PROJECT_NAME)
        payload = json.loads(distribution.read_text("direct_url.json") or "null")
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError, TypeError):
        return f"{PROJECT_NAME} is not installed as an editable project."
    if not isinstance(payload, dict):
        return f"{PROJECT_NAME} has invalid editable metadata."
    directory_info = payload.get("dir_info")
    if not isinstance(directory_info, dict) or directory_info.get("editable") is not True:
        return f"{PROJECT_NAME} is not an editable install."
    raw_url = payload.get("url")
    if not isinstance(raw_url, str) or urlsplit(raw_url).scheme != "file":
        return f"{PROJECT_NAME} has an invalid editable source URL."
    parsed = urlsplit(raw_url)
    source = Path(url2pathname(unquote(parsed.path)))
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", str(source)):
        source = Path(str(source)[1:])
    try:
        matches = os.path.normcase(str(source.resolve())) == os.path.normcase(str(ROOT.resolve()))
    except OSError:
        matches = False
    if not matches:
        return f"Editable source points to {source}, expected {ROOT.resolve()}."
    if distribution.version != PROJECT_VERSION:
        return f"{PROJECT_NAME} version is {distribution.version}, expected {PROJECT_VERSION}."
    return None


def _pip_check_error() -> str | None:
    completed = _run([sys.executable, "-m", "pip", "--isolated", "check"], capture_output=True)
    if completed.returncode == 0:
        return None
    detail = (completed.stdout or completed.stderr).strip()
    return "pip check failed" + (f": {detail}" if detail else "")


def _validation_errors(
    requested: str,
    state: dict[str, Any] | None = None,
    *,
    state_is_trusted: bool = False,
) -> list[str]:
    state = state if state is not None else _load_state()
    if not _is_project_venv():
        return [f"locked no-op state is available only in {VENV}"]
    if state is None:
        return [f"missing or invalid state file: {STATE_FILE}"]
    if not state_is_trusted:
        integrity_errors = _state_integrity_errors(state)
        if integrity_errors:
            return integrity_errors

    profile = state["effective_profile"]
    if not PROFILE_CAPABILITIES[requested] <= PROFILE_CAPABILITIES[profile]:
        return [f"installed profile {profile} does not satisfy requested profile {requested}"]
    if state.get("requested_profile") not in PROFILE_LOCKS:
        return ["lock state has an invalid requested profile"]
    try:
        expected_inputs = _state_inputs(profile)
    except LockedInstallError as exc:
        return [str(exc)]
    if state.get("inputs") != expected_inputs:
        return ["dependency inputs changed"]

    inventory = _distribution_inventory()
    try:
        errors = _locked_version_errors(profile, inventory)
        errors.extend(_unexpected_distribution_errors(profile, inventory))
    except (LockedInstallError, OSError, UnicodeError) as exc:
        return [str(exc)]
    if errors:
        return errors
    if profile != "build":
        editable_error = _editable_error()
        if editable_error:
            return [editable_error]
    errors.extend(_import_errors(profile))
    pip_error = _pip_check_error()
    if pip_error:
        errors.append(pip_error)
    return errors


def _pip_install_lock(lock: Path) -> None:
    command = [
        sys.executable,
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
    completed = _run(command)
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command)


def _install_project() -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--no-index",
        "--no-deps",
        "--no-build-isolation",
        "-e",
        str(ROOT),
    ]
    completed = _run(command)
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command)


def _write_state(
    requested: str,
    effective: str,
    inventory: list[dict[str, str]],
    record_integrity: dict[str, object],
) -> None:
    payload = {
        "schema": STATE_SCHEMA,
        "requested_profile": requested,
        "effective_profile": effective,
        "capabilities": sorted(PROFILE_CAPABILITIES[effective]),
        "project_root": str(ROOT.resolve()),
        "platform": _platform_fingerprint(),
        "inputs": _state_inputs(effective),
        "inventory": inventory,
        "inventory_sha256": _inventory_hash(inventory),
        "record_integrity": record_integrity,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{STATE_FILE.name}.", suffix=".tmp", dir=STATE_FILE.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        temporary.unlink(missing_ok=True)


class _EnvironmentLock(AbstractContextManager["_EnvironmentLock"]):
    def __init__(self, timeout: float = 180.0) -> None:
        # The Python environment is the mutation target. Different worktrees may
        # intentionally share one activated external venv, so ROOT must not split
        # the advisory-lock namespace.
        identity = os.path.normcase(str(Path(sys.prefix).resolve()))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        self.path = Path(tempfile.gettempdir()) / f"mclab-install-{digest}.lock"
        self.timeout = timeout
        self._stream: Any = None

    def __enter__(self) -> _EnvironmentLock:
        self._stream = self.path.open("a+b")
        self._stream.seek(0, os.SEEK_END)
        if self._stream.tell() == 0:
            self._stream.write(b"\0")
            self._stream.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._lock_nonblocking()
                return self
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    self._stream.close()
                    self._stream = None
                    raise LockedInstallError(
                        f"Timed out waiting for another dependency install: {self.path}"
                    )
                time.sleep(0.1)

    def _lock_nonblocking(self) -> None:
        assert self._stream is not None
        self._stream.seek(0)
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._stream is None:
            return None
        self._stream.seek(0)
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None
        return None


def _install(requested: str) -> None:
    error = support_error(requested)
    if error:
        raise LockedInstallError(error)

    with _EnvironmentLock():
        state = _load_state()
        project_venv = _is_project_venv()
        if project_venv and STATE_FILE.exists() and state is None:
            raise LockedInstallError(
                f"Refusing automatic repair because {STATE_FILE} is invalid. "
                "Recreate .venv before retrying."
            )
        if project_venv and state is not None:
            trust_errors = _state_integrity_errors(state)
            if trust_errors:
                raise LockedInstallError(
                    "Refusing automatic repair of an untrusted .venv:\n- "
                    + "\n- ".join(trust_errors)
                    + "\nRecreate .venv before retrying."
                )
        elif project_venv:
            initial_inventory = _distribution_inventory()
            unexpected_seed = sorted(
                {item["name"] for item in initial_inventory} - FRESH_VENV_DISTRIBUTIONS
            )
            if unexpected_seed:
                raise LockedInstallError(
                    "Refusing to bootstrap an unrecorded non-empty .venv containing: "
                    + ", ".join(unexpected_seed)
                    + ". Recreate .venv before retrying."
                )

        if not _validation_errors(
            requested,
            state,
            state_is_trusted=project_venv and state is not None,
        ):
            print(f"Locked dependencies already valid: {state['effective_profile']}")
            return

        previous_inventory = _distribution_inventory() if project_venv else None
        effective = _effective_profile(requested, state, previous_inventory)
        if project_venv:
            STATE_FILE.unlink(missing_ok=True)

        _pip_install_lock(ROOT / BUILD_LOCK)
        if effective != "build":
            _pip_install_lock(ROOT / PROFILE_LOCKS[effective])
            _install_project()

        inventory = _distribution_inventory()
        errors = _locked_version_errors(effective, inventory)
        if project_venv:
            errors.extend(_unexpected_distribution_errors(effective, inventory))
        record_integrity: dict[str, object] = {}
        if not errors:
            record_integrity, record_errors = _record_integrity(effective)
            errors.extend(record_errors)
        if errors:
            raise LockedInstallError(
                "Locked dependency validation failed:\n- " + "\n- ".join(errors)
            )
        if effective != "build":
            editable_error = _editable_error()
            if editable_error:
                raise LockedInstallError(
                    "Locked dependency validation failed:\n- " + editable_error
                )
        errors.extend(_import_errors(effective))
        pip_error = _pip_check_error()
        if pip_error:
            errors.append(pip_error)
        if errors:
            raise LockedInstallError(
                "Locked dependency validation failed:\n- " + "\n- ".join(errors)
            )

        if project_venv:
            _write_state(requested, effective, inventory, record_integrity)
        print(f"Locked dependencies installed and verified: {effective}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=tuple(PROFILE_LOCKS))
    parser.add_argument(
        "--allow-external-env",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the project .venv without installing or accessing the network.",
    )
    args = parser.parse_args(argv)

    error = support_error(args.profile)
    if error:
        print(error, file=sys.stderr)
        return 2
    environment_error = _environment_error(allow_external=args.allow_external_env)
    if environment_error:
        print(environment_error, file=sys.stderr)
        return 2
    if args.check:
        try:
            errors = _validation_errors(args.profile)
        except (LockedInstallError, OSError, UnicodeError) as exc:
            errors = [str(exc)]
        if errors:
            print("Locked dependency check failed:", file=sys.stderr)
            for item in errors:
                print(f"- {item}", file=sys.stderr)
            return 1
        state = _load_state()
        print(f"Locked dependencies valid: {state['effective_profile']}")
        return 0
    try:
        _install(args.profile)
    except (LockedInstallError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Locked dependency install failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
