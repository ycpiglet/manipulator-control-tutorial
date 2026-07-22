"""Validate MCLab's reviewed dependency-lock policy without network access."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]
PYTHON_POLICY = ">=3.10,<3.13"
UV_VERSION = "0.11.31"
EXCLUDE_NEWER = "2026-07-22T07:45:00Z"
MAX_POLICY_FILE_BYTES = 5 * 1024 * 1024
PAPER_LOCK = ".agents/validation/workflow-check-requirements.txt"
PAPER_LOCK_HASH = "b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d"

DIRECT_PIN_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
)
LOCK_REQUIREMENT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9,_.-]+)\])?=="
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
HASH_TOKEN_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}")
UNSAFE_SOURCE_RE = re.compile(
    r"(?:^|\s)(?:-e|--editable)(?:\s|=)|"
    r"(?:git|hg|svn|bzr)\+|(?:https?|file)://|"
    r"(?:^|\s)(?:\.{0,2}/|~[/\\])"
)


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


@dataclass(frozen=True)
class Metric:
    name: str
    threshold: str
    measured: str
    passed: bool


@dataclass(frozen=True)
class LockProfile:
    name: str
    source: str
    output: str
    extras: tuple[str, ...] = ()


@dataclass(frozen=True)
class LockData:
    packages: dict[str, str]
    requirements: int
    hashes: int


EXPECTED_RUNTIME_PINS = {
    "matplotlib": "3.10.9",
    "mujoco": "3.10.0",
    "numpy": "2.2.6",
    "pyyaml": "6.0.3",
}
EXPECTED_OPTIONAL_PINS = {
    "app": {"pyside6-essentials": "6.11.1"},
    "dev": {
        "axe-playwright-python": "0.1.7",
        "mypy": "2.3.0",
        "playwright": "1.61.0",
        "pytest": "9.1.1",
        "pytest-cov": "7.1.0",
        "ruff": "0.15.22",
    },
    "package": {"pyinstaller": "6.21.0"},
}
EXPECTED_BUILD_SYSTEM_PINS = {
    "setuptools": "83.0.0",
    "wheel": "0.47.0",
}
EXPECTED_BUILD_INPUT_PINS = {
    "pip": "26.1.2",
    "setuptools": "83.0.0",
    "tomli": "2.4.1",
    "wheel": "0.47.0",
}
EXPECTED_UV_INPUT_PINS = {"uv": UV_VERSION}
EXPECTED_SUPPLY_CHAIN_INPUT_PINS = {
    "pip-audit": "2.10.1",
    "pip-licenses": "5.5.5",
}

EXPECTED_PROFILES = (
    LockProfile("uv-tool", "requirements/tools/uv.in", "requirements/tools/uv.txt"),
    LockProfile(
        "supply-chain-tool",
        "requirements/tools/supply-chain.in",
        "requirements/tools/supply-chain.txt",
    ),
    LockProfile("build", "requirements/build.in", "requirements/locks/build.txt"),
    LockProfile("runtime", "pyproject.toml", "requirements/locks/runtime.txt"),
    LockProfile("app", "pyproject.toml", "requirements/locks/app.txt", ("app",)),
    LockProfile("dev", "pyproject.toml", "requirements/locks/dev.txt", ("dev",)),
    LockProfile(
        "app-dev",
        "pyproject.toml",
        "requirements/locks/app-dev.txt",
        ("app", "dev"),
    ),
    LockProfile(
        "package",
        "pyproject.toml",
        "requirements/locks/package.txt",
        ("app", "dev", "package"),
    ),
)

EXPECTED_PROFILE_DIRECT_PINS = {
    "runtime": EXPECTED_RUNTIME_PINS,
    "app": EXPECTED_RUNTIME_PINS | EXPECTED_OPTIONAL_PINS["app"],
    "dev": EXPECTED_RUNTIME_PINS | EXPECTED_OPTIONAL_PINS["dev"],
    "app-dev": (
        EXPECTED_RUNTIME_PINS | EXPECTED_OPTIONAL_PINS["app"] | EXPECTED_OPTIONAL_PINS["dev"]
    ),
    "package": (
        EXPECTED_RUNTIME_PINS
        | EXPECTED_OPTIONAL_PINS["app"]
        | EXPECTED_OPTIONAL_PINS["dev"]
        | EXPECTED_OPTIONAL_PINS["package"]
    ),
}
ALL_PROJECT_DIRECT_NAMES = frozenset(
    EXPECTED_RUNTIME_PINS
    | EXPECTED_OPTIONAL_PINS["app"]
    | EXPECTED_OPTIONAL_PINS["dev"]
    | EXPECTED_OPTIONAL_PINS["package"]
)

_PLATFORM_ENVIRONMENTS = (
    ("linux", "x86_64"),
    ("win32", "AMD64"),
    ("darwin", "arm64"),
    ("darwin", "x86_64"),
)
EXPECTED_ENVIRONMENTS = tuple(
    "implementation_name == 'cpython' and "
    f"python_version == '{version}' and "
    f"sys_platform == '{platform}' and platform_machine == '{machine}'"
    for platform, machine in _PLATFORM_ENVIRONMENTS
    for version in ("3.10", "3.11", "3.12")
)

COMPILE_PREFIX = (
    "<sys.executable>",
    "-m",
    "uv",
    "pip",
    "compile",
    "<profile.source>",
)
COMPILE_SUFFIX = (
    "--universal",
    "--python-version",
    "3.10",
    "--only-binary",
    ":all:",
    "--emit-build-options",
    "--generate-hashes",
    "--no-sources",
    "--exclude-newer",
    "<EXCLUDE_NEWER>",
    "--no-python-downloads",
    "--output-file",
    "<profile.output>",
)
INSTALL_LOCK_COMMAND = (
    "<sys.executable>",
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
    "<lock>",
)
EDITABLE_INSTALL_COMMAND = (
    "<sys.executable>",
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
    "<ROOT>",
)
EXPECTED_INSTALLER_PROFILES = {
    "build": "requirements/locks/build.txt",
    "runtime": "requirements/locks/runtime.txt",
    "app": "requirements/locks/app.txt",
    "dev": "requirements/locks/dev.txt",
    "app-dev": "requirements/locks/app-dev.txt",
    "package": "requirements/locks/package.txt",
}
EXPECTED_CMD_LAUNCHERS = (
    "run_all_batches.cmd",
    "run_batch_lab01.cmd",
    "run_batch_lab02.cmd",
    "run_batch_lab03.cmd",
    "run_batch_lab04.cmd",
    "run_batch_lab04_cartesian.cmd",
    "run_lab01.cmd",
    "run_lab01_interactive.cmd",
    "run_lab02.cmd",
    "run_lab02_interactive.cmd",
    "run_lab03.cmd",
    "run_lab03_condition_dls_interactive.cmd",
    "run_lab03_dls_interactive.cmd",
    "run_lab03_interactive.cmd",
    "run_lab04.cmd",
    "run_lab04_cartesian_interactive.cmd",
    "run_lab04_interactive.cmd",
    "run_lab04_wall_interactive.cmd",
    "run_mclab.cmd",
)
UV_QUERY_FUNCTION_AST = ast.dump(
    ast.parse(
        """def _installed_uv_version() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "uv", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    fields = completed.stdout.strip().split()
    return fields[1] if len(fields) >= 2 else ""
"""
    ).body[0],
    include_attributes=False,
)


def _read_policy_file(root: Path, relative: str, errors: list[str]) -> str | None:
    path = root / relative
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        errors.append(f"POLICY_ROOT_INVALID {root}: {exc}")
        return None
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        errors.append(f"POLICY_FILE_MISSING {relative}: {exc}")
        return None
    if path.is_symlink() or not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        errors.append(f"POLICY_FILE_UNSAFE {relative}: expected an in-tree regular file")
        return None
    try:
        size = resolved.stat().st_size
        if size > MAX_POLICY_FILE_BYTES:
            errors.append(
                f"POLICY_FILE_TOO_LARGE {relative}: {size} > {MAX_POLICY_FILE_BYTES} bytes"
            )
            return None
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"POLICY_FILE_UNREADABLE {relative}: {exc}")
        return None


def _parse_pin_values(value: object, label: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, list):
        errors.append(f"PYPROJECT_PIN_FORMAT {label}: expected a TOML array")
        return {}
    pins: dict[str, str] = {}
    for index, requirement in enumerate(value):
        if not isinstance(requirement, str):
            errors.append(f"PYPROJECT_PIN_FORMAT {label}[{index}]: expected a string")
            continue
        match = DIRECT_PIN_RE.fullmatch(requirement)
        if match is None:
            errors.append(
                f"PYPROJECT_PIN_FORMAT {label}[{index}]: expected name==version, got {requirement!r}"
            )
            continue
        name = _canonical_name(match.group("name"))
        if name in pins:
            errors.append(f"PYPROJECT_PIN_DUPLICATE {label}: {name}")
            continue
        pins[name] = match.group("version")
    return pins


def _check_expected_pins(
    actual: dict[str, str],
    expected: dict[str, str],
    label: str,
    errors: list[str],
) -> None:
    if actual != expected:
        errors.append(f"DIRECT_PINS_MISMATCH {label}: expected {expected}, got {actual}")


def _validate_pyproject(root: Path, errors: list[str]) -> None:
    text = _read_policy_file(root, "pyproject.toml", errors)
    if text is None:
        return
    try:
        payload = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        errors.append(f"PYPROJECT_INVALID pyproject.toml: {exc}")
        return
    if not isinstance(payload, dict):
        errors.append("PYPROJECT_INVALID pyproject.toml: root must be a table")
        return

    project = payload.get("project")
    if not isinstance(project, dict):
        errors.append("PYPROJECT_INVALID [project] table missing")
        project = {}
    if project.get("requires-python") != PYTHON_POLICY:
        errors.append(
            "PYTHON_POLICY_MISMATCH [project].requires-python: "
            f"expected {PYTHON_POLICY!r}, got {project.get('requires-python')!r}"
        )
    _check_expected_pins(
        _parse_pin_values(project.get("dependencies"), "project.dependencies", errors),
        EXPECTED_RUNTIME_PINS,
        "project.dependencies",
        errors,
    )

    optional = project.get("optional-dependencies")
    if not isinstance(optional, dict):
        errors.append("PYPROJECT_INVALID [project.optional-dependencies] table missing")
        optional = {}
    if set(optional) != set(EXPECTED_OPTIONAL_PINS):
        errors.append(
            "OPTIONAL_PROFILES_MISMATCH project.optional-dependencies: "
            f"expected {sorted(EXPECTED_OPTIONAL_PINS)}, got {sorted(optional)}"
        )
    for profile, expected in EXPECTED_OPTIONAL_PINS.items():
        _check_expected_pins(
            _parse_pin_values(optional.get(profile), f"optional-dependencies.{profile}", errors),
            expected,
            f"optional-dependencies.{profile}",
            errors,
        )

    build_system = payload.get("build-system")
    if not isinstance(build_system, dict):
        errors.append("PYPROJECT_INVALID [build-system] table missing")
        build_system = {}
    _check_expected_pins(
        _parse_pin_values(build_system.get("requires"), "build-system.requires", errors),
        EXPECTED_BUILD_SYSTEM_PINS,
        "build-system.requires",
        errors,
    )
    if build_system.get("build-backend") != "setuptools.build_meta":
        errors.append(
            "BUILD_BACKEND_MISMATCH expected 'setuptools.build_meta', got "
            f"{build_system.get('build-backend')!r}"
        )

    tool = payload.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    if not isinstance(uv, dict):
        errors.append("UV_ENVIRONMENTS_MISSING [tool.uv] table missing")
        return
    for key in ("environments", "required-environments"):
        value = uv.get(key)
        actual = (
            tuple(value)
            if isinstance(value, list) and all(isinstance(item, str) for item in value)
            else ()
        )
        if actual != EXPECTED_ENVIRONMENTS:
            errors.append(
                f"UV_ENVIRONMENTS_MISMATCH [tool.uv].{key}: "
                f"expected {len(EXPECTED_ENVIRONMENTS)} reviewed markers, got {len(actual)}"
            )
    if uv.get("environments") != uv.get("required-environments"):
        errors.append("UV_ENVIRONMENTS_MISMATCH environments and required-environments differ")


def _parse_input_pins(text: str, relative: str, errors: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = DIRECT_PIN_RE.fullmatch(stripped)
        if match is None:
            errors.append(
                f"INPUT_PIN_FORMAT {relative}:{line_number}: expected exact name==version"
            )
            continue
        name = _canonical_name(match.group("name"))
        if name in pins:
            errors.append(f"INPUT_PIN_DUPLICATE {relative}:{line_number}: {name}")
            continue
        pins[name] = match.group("version")
    return pins


def _validate_inputs(root: Path, errors: list[str]) -> None:
    for relative, expected in (
        ("requirements/build.in", EXPECTED_BUILD_INPUT_PINS),
        ("requirements/tools/uv.in", EXPECTED_UV_INPUT_PINS),
        ("requirements/tools/supply-chain.in", EXPECTED_SUPPLY_CHAIN_INPUT_PINS),
    ):
        text = _read_policy_file(root, relative, errors)
        if text is None:
            continue
        _check_expected_pins(_parse_input_pins(text, relative, errors), expected, relative, errors)


def _expected_header(profile: LockProfile) -> str:
    tokens = ["uv", "pip", "compile", profile.source]
    for extra in profile.extras:
        tokens.extend(("--extra", extra))
    tokens.extend(
        (
            "--universal",
            "--python-version",
            "3.10",
            "--only-binary",
            ":all:",
            "--emit-build-options",
            "--generate-hashes",
            "--no-sources",
            "--exclude-newer",
            EXCLUDE_NEWER,
            "--no-python-downloads",
            "--output-file",
            profile.output,
        )
    )
    return "#    " + " ".join(tokens)


def _logical_lock_lines(text: str, relative: str, errors: list[str]) -> list[tuple[int, str]]:
    logical: list[tuple[int, str]] = []
    parts: list[str] = []
    start_line = 0
    for line_number, physical in enumerate(text.splitlines(), start=1):
        stripped = physical.strip()
        if not stripped or stripped.startswith("#"):
            if parts:
                errors.append(
                    f"LOCK_STRUCTURE {relative}:{line_number}: comment/blank in continuation"
                )
                parts = []
            continue
        if not parts:
            start_line = line_number
        continued = stripped.endswith("\\")
        parts.append(stripped[:-1].rstrip() if continued else stripped)
        if not continued:
            logical.append((start_line, " ".join(parts)))
            parts = []
    if parts:
        errors.append(f"LOCK_UNTERMINATED_CONTINUATION {relative}:{start_line}")
    return logical


def _parse_lock(
    profile: LockProfile,
    text: str,
    errors: list[str],
) -> LockData:
    relative = profile.output
    lines = text.splitlines()
    expected_first = "# This file was autogenerated by uv via the following command:"
    if len(lines) < 2 or lines[0] != expected_first or lines[1] != _expected_header(profile):
        errors.append(f"LOCK_HEADER_MISMATCH {relative}: generator command is not reviewed")

    logical = _logical_lock_lines(text, relative, errors)
    global_option = "--only-binary :all:"
    option_positions = [
        index for index, (_line, value) in enumerate(logical) if value == global_option
    ]
    if option_positions != [0]:
        errors.append(
            f"LOCK_BINARY_POLICY {relative}: expected one leading {global_option!r} directive"
        )

    packages: dict[str, str] = {}
    requirement_count = 0
    hash_count = 0
    for line_number, value in logical:
        if value == global_option:
            continue
        if value.startswith("-"):
            errors.append(f"LOCK_UNSAFE_DIRECTIVE {relative}:{line_number}: {value}")
            continue
        if UNSAFE_SOURCE_RE.search(value) or " @ " in value:
            errors.append(f"LOCK_UNSAFE_SOURCE {relative}:{line_number}: direct/local source")
            continue
        tokens = value.split()
        try:
            first_hash = next(
                index for index, token in enumerate(tokens) if token.startswith("--hash=")
            )
        except StopIteration:
            errors.append(f"LOCK_HASH_MISSING {relative}:{line_number}")
            continue
        unexpected_options = [token for token in tokens[:first_hash] if token.startswith("-")]
        if unexpected_options:
            errors.append(f"LOCK_UNSAFE_DIRECTIVE {relative}:{line_number}: {unexpected_options}")
            continue
        hash_tokens = tokens[first_hash:]
        if not hash_tokens or any(HASH_TOKEN_RE.fullmatch(token) is None for token in hash_tokens):
            errors.append(
                f"LOCK_HASH_FORMAT {relative}:{line_number}: only lowercase sha256 hashes allowed"
            )
            continue
        if len(hash_tokens) != len(set(hash_tokens)):
            errors.append(f"LOCK_HASH_DUPLICATE {relative}:{line_number}")
            continue
        requirement = " ".join(tokens[:first_hash])
        match = LOCK_REQUIREMENT_RE.fullmatch(requirement)
        if match is None:
            errors.append(
                f"LOCK_REQUIREMENT_FORMAT {relative}:{line_number}: expected hashed name==version"
            )
            continue
        name = _canonical_name(match.group("name"))
        if name in packages:
            errors.append(f"LOCK_PACKAGE_DUPLICATE {relative}:{line_number}: {name}")
            continue
        packages[name] = match.group("version")
        requirement_count += 1
        hash_count += len(hash_tokens)
    if not packages:
        errors.append(f"LOCK_EMPTY {relative}: no valid hashed requirements")
    return LockData(packages, requirement_count, hash_count)


def _lock_inventory_errors(root: Path) -> list[str]:
    expected = {profile.output for profile in EXPECTED_PROFILES}
    actual: set[str] = set()
    for relative_directory in ("requirements/locks", "requirements/tools"):
        directory = root / relative_directory
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.glob("*.txt"):
            actual.add(path.relative_to(root).as_posix())
    errors: list[str] = []
    for missing in sorted(expected - actual):
        errors.append(f"LOCK_INVENTORY_MISSING {missing}")
    for unexpected in sorted(actual - expected):
        errors.append(f"LOCK_INVENTORY_UNEXPECTED {unexpected}")
    return errors


def _validate_locks(root: Path, errors: list[str]) -> dict[str, LockData]:
    errors.extend(_lock_inventory_errors(root))
    locks: dict[str, LockData] = {}
    for profile in EXPECTED_PROFILES:
        text = _read_policy_file(root, profile.output, errors)
        if text is not None:
            locks[profile.name] = _parse_lock(profile, text, errors)

    uv_tool = locks.get("uv-tool")
    if uv_tool is not None and uv_tool.packages != EXPECTED_UV_INPUT_PINS:
        errors.append(
            f"UV_TOOL_LOCK_MISMATCH expected {EXPECTED_UV_INPUT_PINS}, got {uv_tool.packages}"
        )
    supply_chain_tool = locks.get("supply-chain-tool")
    if supply_chain_tool is not None:
        actual_supply_chain_direct = {
            name: supply_chain_tool.packages[name]
            for name in EXPECTED_SUPPLY_CHAIN_INPUT_PINS
            if name in supply_chain_tool.packages
        }
        if actual_supply_chain_direct != EXPECTED_SUPPLY_CHAIN_INPUT_PINS:
            errors.append(
                "SUPPLY_CHAIN_TOOL_LOCK_MISMATCH "
                f"expected {EXPECTED_SUPPLY_CHAIN_INPUT_PINS}, "
                f"got {actual_supply_chain_direct}"
            )
    build = locks.get("build")
    if build is not None:
        actual_build_direct = {
            name: build.packages[name]
            for name in EXPECTED_BUILD_INPUT_PINS
            if name in build.packages
        }
        if actual_build_direct != EXPECTED_BUILD_INPUT_PINS:
            errors.append(
                "BUILD_LOCK_DIRECT_PINS_MISMATCH "
                f"expected {EXPECTED_BUILD_INPUT_PINS}, got {actual_build_direct}"
            )

    for profile, expected in EXPECTED_PROFILE_DIRECT_PINS.items():
        lock = locks.get(profile)
        if lock is None:
            continue
        actual = {
            name: version
            for name, version in lock.packages.items()
            if name in ALL_PROJECT_DIRECT_NAMES
        }
        if actual != expected:
            errors.append(
                f"LOCK_PROFILE_DIRECT_MISMATCH {profile}: expected {expected}, got {actual}"
            )

    tool_owners = {
        "uv": "uv-tool",
        "pip-audit": "supply-chain-tool",
        "pip-licenses": "supply-chain-tool",
    }
    for profile, lock in locks.items():
        for package, owner in tool_owners.items():
            if profile != owner and package in lock.packages:
                separation = (
                    "generator-only" if package == "uv" else "supply-chain-tool-only"
                )
                errors.append(
                    f"BUILD_TOOL_SEPARATION {profile}: {package} must remain {separation}"
                )
    return locks


def _assignment_value(module: ast.Module, name: str) -> ast.expr | None:
    matches: list[ast.expr] = []
    for statement in module.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            matches.append(statement.value)
    return matches[0] if len(matches) == 1 else None


def _named_function(module: ast.Module, name: str) -> ast.FunctionDef | None:
    matches = [
        statement
        for statement in module.body
        if isinstance(statement, ast.FunctionDef) and statement.name == name
    ]
    return matches[0] if len(matches) == 1 else None


def _string_constant(value: ast.expr) -> str | None:
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _integer_constant(value: ast.expr) -> int | None:
    return (
        value.value
        if isinstance(value, ast.Constant)
        and isinstance(value.value, int)
        and not isinstance(value.value, bool)
        else None
    )


def _parse_generator_profiles(value: ast.expr | None) -> tuple[LockProfile, ...] | None:
    if not isinstance(value, (ast.Tuple, ast.List)):
        return None
    profiles: list[LockProfile] = []
    for item in value.elts:
        if (
            not isinstance(item, ast.Call)
            or not isinstance(item.func, ast.Name)
            or item.func.id != "LockProfile"
            or item.keywords
            or len(item.args) not in (3, 4)
        ):
            return None
        required = tuple(_string_constant(argument) for argument in item.args[:3])
        if any(part is None for part in required):
            return None
        extras: tuple[str, ...] = ()
        if len(item.args) == 4:
            extras_node = item.args[3]
            if not isinstance(extras_node, (ast.Tuple, ast.List)):
                return None
            parsed_extras = tuple(_string_constant(extra) for extra in extras_node.elts)
            if any(extra is None for extra in parsed_extras):
                return None
            extras = tuple(extra for extra in parsed_extras if extra is not None)
        name, source, output = required
        if name is None or source is None or output is None:
            return None
        profiles.append(LockProfile(name, source, output, extras))
    return tuple(profiles)


def _expr_key(value: ast.expr) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
        and value.attr == "executable"
    ):
        return "<sys.executable>"
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "profile"
        and value.attr in {"source", "output", "extras"}
    ):
        return f"<profile.{value.attr}>"
    if isinstance(value, ast.Name) and value.id == "EXCLUDE_NEWER":
        return "<EXCLUDE_NEWER>"
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "str"
        and len(value.args) == 1
        and not value.keywords
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id in {"lock", "ROOT"}
    ):
        return f"<{value.args[0].id}>"
    if isinstance(value, ast.Name):
        return f"<{value.id}>"
    return None


def _sequence_keys(value: ast.expr) -> tuple[str | None, ...] | None:
    if not isinstance(value, (ast.List, ast.Tuple)):
        return None
    return tuple(_expr_key(item) for item in value.elts)


def _extend_keys(statement: ast.stmt) -> tuple[str | None, ...] | None:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    call = statement.value
    if (
        not isinstance(call.func, ast.Attribute)
        or not isinstance(call.func.value, ast.Name)
        or call.func.value.id != "command"
        or call.func.attr != "extend"
        or len(call.args) != 1
        or call.keywords
    ):
        return None
    return _sequence_keys(call.args[0])


def _compile_function_matches(module: ast.Module) -> bool:
    function = _named_function(module, "compile_command")
    if function is None:
        return False
    if (
        function.decorator_list
        or len(function.args.args) != 1
        or function.args.args[0].arg != "profile"
        or len(function.body) != 4
    ):
        return False
    assignment, loop, extension, returned = function.body
    if (
        not isinstance(assignment, ast.Assign)
        or len(assignment.targets) != 1
        or not isinstance(assignment.targets[0], ast.Name)
        or assignment.targets[0].id != "command"
        or _sequence_keys(assignment.value) != COMPILE_PREFIX
    ):
        return False
    if (
        not isinstance(loop, ast.For)
        or not isinstance(loop.target, ast.Name)
        or loop.target.id != "extra"
        or _expr_key(loop.iter) != "<profile.extras>"
        or len(loop.body) != 1
        or loop.orelse
        or _extend_keys(loop.body[0]) != ("--extra", "<extra>")
    ):
        return False
    if _extend_keys(extension) != COMPILE_SUFFIX:
        return False
    return (
        isinstance(returned, ast.Return)
        and isinstance(returned.value, ast.Name)
        and returned.value.id == "command"
    )


def _uv_query_function_matches(module: ast.Module) -> bool:
    function = _named_function(module, "_installed_uv_version")
    return (
        function is not None
        and ast.dump(function, include_attributes=False) == UV_QUERY_FUNCTION_AST
    )


def _is_uv_guard(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.If) or statement.orelse:
        return False
    test = statement.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "actual_uv"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.NotEq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Name)
        and test.comparators[0].id == "UV_VERSION"
        and bool(statement.body)
        and isinstance(statement.body[-1], ast.Return)
        and isinstance(statement.body[-1].value, ast.Constant)
        and statement.body[-1].value.value == 2
    )


def _assigns_installed_uv(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Try) or len(statement.body) != 1:
        return False
    assignment = statement.body[0]
    return (
        isinstance(assignment, ast.Assign)
        and len(assignment.targets) == 1
        and isinstance(assignment.targets[0], ast.Name)
        and assignment.targets[0].id == "actual_uv"
        and isinstance(assignment.value, ast.Call)
        and isinstance(assignment.value.func, ast.Name)
        and assignment.value.func.id == "_installed_uv_version"
        and not assignment.value.args
        and not assignment.value.keywords
    )


def _called_names(statement: ast.stmt) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(statement)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _main_uv_guard_precedes_generation(module: ast.Module) -> bool:
    function = _named_function(module, "main")
    if function is None:
        return False
    assignment_indices = [
        index for index, statement in enumerate(function.body) if _assigns_installed_uv(statement)
    ]
    guard_indices = [
        index for index, statement in enumerate(function.body) if _is_uv_guard(statement)
    ]
    generation_indices = [
        index
        for index, statement in enumerate(function.body)
        if _called_names(statement) & {"_generate", "_check"}
    ]
    return (
        len(assignment_indices) == 1
        and len(guard_indices) == 1
        and bool(generation_indices)
        and assignment_indices[0] < guard_indices[0] < min(generation_indices)
    )


def _validate_generator(root: Path, errors: list[str]) -> None:
    relative = "scripts/lock_requirements.py"
    text = _read_policy_file(root, relative, errors)
    if text is None:
        return
    try:
        module = ast.parse(text, filename=relative)
    except (SyntaxError, ValueError) as exc:
        errors.append(f"LOCK_GENERATOR_INVALID {relative}: {exc}")
        return

    uv_value = _assignment_value(module, "UV_VERSION")
    if uv_value is None or _string_constant(uv_value) != UV_VERSION:
        errors.append(f"LOCK_GENERATOR_UV expected UV_VERSION={UV_VERSION!r}")
    cutoff_value = _assignment_value(module, "EXCLUDE_NEWER")
    if cutoff_value is None or _string_constant(cutoff_value) != EXCLUDE_NEWER:
        errors.append(f"LOCK_GENERATOR_CUTOFF expected EXCLUDE_NEWER={EXCLUDE_NEWER!r}")
    profiles = _parse_generator_profiles(_assignment_value(module, "LOCK_PROFILES"))
    if profiles != EXPECTED_PROFILES:
        errors.append(f"LOCK_GENERATOR_PROFILES expected {EXPECTED_PROFILES!r}, got {profiles!r}")
    if not _compile_function_matches(module):
        errors.append(
            "LOCK_GENERATOR_FLAGS compile_command must preserve universal Python 3.10, "
            "binary-only, hash, no-sources, cutoff, and output policy"
        )
    if not _uv_query_function_matches(module) or not _main_uv_guard_precedes_generation(module):
        errors.append(
            "LOCK_GENERATOR_UV_GUARD generator must query uv --version and reject != UV_VERSION"
        )


def _path_call_value(value: ast.expr) -> str | None:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "Path"
        and len(value.args) == 1
        and not value.keywords
    ):
        return _string_constant(value.args[0])
    return None


def _installer_profile_mapping(module: ast.Module) -> dict[str, str] | None:
    build_lock = _path_call_value(_assignment_value(module, "BUILD_LOCK") or ast.Constant())
    value = _assignment_value(module, "PROFILE_LOCKS")
    if build_lock is None or not isinstance(value, ast.Dict):
        return None
    mapping: dict[str, str] = {}
    for key_node, value_node in zip(value.keys, value.values, strict=True):
        key = _string_constant(key_node) if key_node is not None else None
        if isinstance(value_node, ast.Name) and value_node.id == "BUILD_LOCK":
            path = build_lock
        else:
            path = _path_call_value(value_node)
        if key is None or path is None or key in mapping:
            return None
        mapping[key] = path
    return mapping


def _function_command(module: ast.Module, function_name: str) -> tuple[str | None, ...] | None:
    function = _named_function(module, function_name)
    if function is None:
        return None
    assignments = [
        statement
        for statement in function.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "command"
    ]
    return _sequence_keys(assignments[0].value) if len(assignments) == 1 else None


def _external_environment_guard_matches(module: ast.Module) -> bool:
    main = _named_function(module, "main")
    environment_guard = _named_function(module, "_environment_error")
    project_check = _named_function(module, "_is_project_venv")
    linked_check = _named_function(module, "_project_venv_is_linked")
    redirect_check = _named_function(module, "project_venv_redirect_error")
    if any(item is None for item in (main, environment_guard, project_check, linked_check, redirect_check)):
        return False

    option_calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and _string_constant(node.args[0]) == "--allow-external-env"
    ]
    if len(option_calls) != 1:
        return False
    keywords = {keyword.arg: keyword.value for keyword in option_calls[0].keywords}
    hidden = (
        _string_constant(keywords.get("action", ast.Constant())) == "store_true"
        and isinstance(keywords.get("help"), ast.Attribute)
        and isinstance(keywords["help"].value, ast.Name)
        and keywords["help"].value.id == "argparse"
        and keywords["help"].attr == "SUPPRESS"
    )

    guard_calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_environment_error"
    ]
    install_calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_install"
    ]
    if len(guard_calls) != 1 or len(install_calls) != 1:
        return False
    guard_keywords = {keyword.arg: keyword.value for keyword in guard_calls[0].keywords}
    external_value = guard_keywords.get("allow_external")
    forwards_flag = (
        isinstance(external_value, ast.Attribute)
        and isinstance(external_value.value, ast.Name)
        and external_value.value.id == "args"
        and external_value.attr == "allow_external_env"
    )
    if not (hidden and forwards_flag and guard_calls[0].lineno < install_calls[0].lineno):
        return False

    if (
        len(environment_guard.args.kwonlyargs) != 1
        or environment_guard.args.kwonlyargs[0].arg != "allow_external"
        or not environment_guard.body
        or not isinstance(environment_guard.body[0], ast.If)
        or not isinstance(environment_guard.body[0].test, ast.Name)
        or environment_guard.body[0].test.id != "allow_external"
    ):
        return False
    guard_names = _called_names(environment_guard)
    project_names = _called_names(project_check)
    linked_names = _called_names(linked_check)
    redirect_names = _called_names(redirect_check)
    redirect_attributes = {
        node.attr for node in ast.walk(redirect_check) if isinstance(node, ast.Attribute)
    }
    return {"project_venv_redirect_error", "_is_project_venv"} <= guard_names and (
        "_project_venv_is_linked" in project_names
        and "project_venv_redirect_error" in linked_names
        and {"_is_reparse_point", "_allowed_venv_link"} <= redirect_names
        and "scandir" in redirect_attributes
    )


def _bootstrap_venv_guard_matches(module: ast.Module, function_name: str) -> bool:
    function = _named_function(module, function_name)
    if function is None:
        return False
    redirect_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "project_venv_redirect_error"
    ]
    support_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "support_error"
    ]
    venv_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and any(_string_constant(item) == "venv" for item in ast.walk(node))
    ]
    return (
        len(redirect_calls) == 1
        and len(support_calls) == 1
        and bool(venv_calls)
        and redirect_calls[0].lineno < min(node.lineno for node in venv_calls)
        and support_calls[0].lineno < min(node.lineno for node in venv_calls)
    )


def _support_envelope_matches(module: ast.Module) -> bool:
    support = _named_function(module, "support_error")
    if support is None:
        return False
    tuples = {
        tuple(_integer_constant(item) for item in node.elts)
        for node in ast.walk(support)
        if isinstance(node, ast.Tuple)
        and node.elts
        and all(_integer_constant(item) is not None for item in node.elts)
    }
    names = {node.id for node in ast.walk(support) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(support) if isinstance(node, ast.Attribute)}
    return (
        (10, 0, 17763) in tuples
        and "PROFILE_CAPABILITIES" in names
        and {"getwindowsversion", "platform_version"} <= attributes
    )


def _record_trust_order_matches(module: ast.Module) -> bool:
    record = _named_function(module, "_record_integrity")
    state_integrity = _named_function(module, "_state_integrity_errors")
    locked = _named_function(module, "_locked_versions")
    validation = _named_function(module, "_validation_errors")
    install = _named_function(module, "_install")
    if (
        record is None
        or state_integrity is None
        or locked is None
        or validation is None
        or install is None
    ):
        return False
    record_names = {node.id for node in ast.walk(record) if isinstance(node, ast.Name)}
    if not {"PROJECT_NAME", "PROJECT_VERSION"} <= record_names:
        return False
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(locked)):
        return False
    state_calls = _called_names(state_integrity)
    if "_record_integrity_for_versions" not in state_calls:
        return False

    def call_lines(function: ast.FunctionDef, name: str) -> list[int]:
        return [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]

    validation_lines = {
        name: call_lines(validation, name)
        for name in (
            "_state_integrity_errors",
            "_editable_error",
            "_import_errors",
            "_pip_check_error",
        )
    }
    if any(len(found) != 1 for found in validation_lines.values()) or not (
        validation_lines["_state_integrity_errors"][0]
        < validation_lines["_editable_error"][0]
        < validation_lines["_import_errors"][0]
        < validation_lines["_pip_check_error"][0]
    ):
        return False

    install_lines = {
        name: call_lines(install, name)
        for name in (
            "_state_integrity_errors",
            "_pip_install_lock",
            "_record_integrity",
            "_editable_error",
            "_import_errors",
            "_pip_check_error",
        )
    }
    if any(
        len(found) != (2 if name == "_pip_install_lock" else 1)
        for name, found in install_lines.items()
    ):
        return False
    return (
        install_lines["_state_integrity_errors"][0]
        < min(install_lines["_pip_install_lock"])
        <= max(install_lines["_pip_install_lock"])
        < install_lines["_record_integrity"][0]
        < install_lines["_editable_error"][0]
        < install_lines["_import_errors"][0]
        < install_lines["_pip_check_error"][0]
    )


def _validate_auxiliary_paper_lock(root: Path, errors: list[str]) -> None:
    text = _read_policy_file(root, PAPER_LOCK, errors)
    if text is None:
        return
    logical = [value for _line, value in _logical_lock_lines(text, PAPER_LOCK, errors)]
    expected = f"PyYAML==6.0.3 --hash=sha256:{PAPER_LOCK_HASH}"
    if logical != [expected]:
        errors.append(
            "PAPER_LOCK_MISMATCH expected one CPython 3.11 Linux wheel pin "
            "PyYAML==6.0.3 with its reviewed sha256"
        )


def _validate_installer(root: Path, errors: list[str]) -> None:
    relative = "scripts/install_locked.py"
    text = _read_policy_file(root, relative, errors)
    if text is None:
        return
    try:
        module = ast.parse(text, filename=relative)
    except (SyntaxError, ValueError) as exc:
        errors.append(f"INSTALLER_INVALID {relative}: {exc}")
        return
    if _installer_profile_mapping(module) != EXPECTED_INSTALLER_PROFILES:
        errors.append(
            "INSTALLER_PROFILES profile mapping must match the six reviewed build/runtime/"
            "app/dev/app-dev/package locks"
        )
    if _function_command(module, "_pip_install_lock") != INSTALL_LOCK_COMMAND:
        errors.append(
            "INSTALLER_THIRD_PARTY third-party pip must preserve isolated, forced, "
            "hash-required, binary-only installation"
        )
    if _function_command(module, "_install_project") != EDITABLE_INSTALL_COMMAND:
        errors.append(
            "INSTALLER_EDITABLE local editable install must preserve no-index, no-deps, "
            "and no-build-isolation"
        )
    if not _external_environment_guard_matches(module):
        errors.append(
            "INSTALLER_ENV_GUARD external environments require the hidden explicit opt-in; "
            "default installs must reject linked/non-project .venv targets"
        )
    if not _support_envelope_matches(module):
        errors.append(
            "INSTALLER_SUPPORT_ENVELOPE app-capable Windows installs must require "
            "Windows 10 1809/build 17763 or newer before download"
        )
    if not _record_trust_order_matches(module):
        errors.append(
            "INSTALLER_TRUST_ORDER stdlib lock parsing and third-party/editable RECORD trust "
            "must precede editable validation, imports, and pip check"
        )


def _validate_manager(root: Path, errors: list[str]) -> None:
    relative = "scripts/manage_dependency_locks.py"
    text = _read_policy_file(root, relative, errors)
    if text is None:
        return
    try:
        module = ast.parse(text, filename=relative)
    except (SyntaxError, ValueError) as exc:
        errors.append(f"LOCK_MANAGER_INVALID {relative}: {exc}")
        return
    temporary_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "tempfile"
        and node.func.attr == "TemporaryDirectory"
    ]
    required_once = (
        '"--allow-external-env"',
        '"--force-reinstall"',
        '"--require-hashes"',
        '"--only-binary=:all:"',
        '"requirements" / "tools" / "uv.txt"',
    )
    if len(temporary_calls) != 1 or any(text.count(token) != 1 for token in required_once):
        errors.append(
            "LOCK_MANAGER_POLICY manager must use one disposable venv, an explicit external "
            "build install, and one forced hash/binary-only uv install"
        )


def _validate_workflows(root: Path, errors: list[str]) -> None:
    workflow_directory = root / ".github" / "workflows"
    try:
        workflow_paths = sorted(
            (*workflow_directory.glob("*.yml"), *workflow_directory.glob("*.yaml"))
        )
    except OSError as exc:
        errors.append(f"WORKFLOW_INSTALL_POLICY cannot enumerate workflows: {exc}")
        return
    texts: dict[str, str] = {}
    for path in workflow_paths:
        relative = path.relative_to(root).as_posix()
        text = _read_policy_file(root, relative, errors)
        if text is not None:
            texts[relative] = text

    raw_pip_installs = sum(
        len(re.findall(r"-m\s+pip\s+install\b", text)) for text in texts.values()
    )
    ci = texts.get(".github/workflows/ci.yml", "")
    desktop = texts.get(".github/workflows/desktop.yml", "")
    paper_start = ci.find("- name: Install workflow checker parser")
    paper_end = ci.find("\n      - name:", paper_start + 1) if paper_start >= 0 else -1
    paper = ci[paper_start : paper_end if paper_end >= 0 else len(ci)]
    paper_flags = (
        "--isolated",
        "--no-input",
        "--no-deps",
        "--force-reinstall",
        "--only-binary=:all:",
        "--require-hashes",
        f"-r {PAPER_LOCK}",
    )
    valid = (
        raw_pip_installs == 1
        and paper_start >= 0
        and all(flag in paper for flag in paper_flags)
        and ci.count("python scripts/install_locked.py --allow-external-env dev") == 3
        and ci.count("python scripts/manage_dependency_locks.py --check") == 1
        and desktop.count("python scripts/install_locked.py --allow-external-env package") == 1
        and desktop.count("& $venvPython scripts/install_locked.py dev") == 1
        and sum(text.count("--allow-external-env") for text in texts.values()) == 4
        and not any("uv pip install" in text for text in texts.values())
    )
    if not valid:
        errors.append(
            "WORKFLOW_INSTALL_POLICY workflows must use four reviewed external-profile "
            "installs and the one exact forced/hash-locked paper-parser exception"
        )


def _validate_bootstraps_and_launchers(root: Path, errors: list[str]) -> None:
    source_expectations = {
        "scripts/start_mclab.py": ('"install_locked.py"), "app"', "_ensure_venv"),
        "scripts/bootstrap_and_run.py": ('"install_locked.py"), profile', "ensure_venv"),
    }
    public_texts: list[tuple[str, str]] = []
    for relative, (expected, guard_function) in source_expectations.items():
        text = _read_policy_file(root, relative, errors)
        if text is None:
            continue
        public_texts.append((relative, text))
        if expected not in text or re.search(r"-m[\"']?\s*,?\s*[\"']pip[\"']?.*install", text):
            errors.append(
                f"BOOTSTRAP_INSTALL_POLICY {relative}: must route through install_locked.py"
            )
        try:
            module = ast.parse(text, filename=relative)
        except (SyntaxError, ValueError):
            continue
        if not _bootstrap_venv_guard_matches(module, guard_function):
            errors.append(
                f"BOOTSTRAP_VENV_GUARD {relative}: redirect checks must precede venv creation"
            )
    for relative in (
        "README.md",
        "README.en.md",
        "docs/installation.md",
        "docs/troubleshooting.md",
    ):
        text = _read_policy_file(root, relative, errors)
        if text is not None:
            public_texts.append((relative, text))
    for relative, text in public_texts:
        if "pip install" in text or "--allow-external-env" in text:
            errors.append(
                f"PUBLIC_INSTALL_BYPASS {relative}: raw pip or external-env opt-in is not public"
            )

    actual_launchers = tuple(path.name for path in sorted(root.glob("run_*.cmd")))
    if actual_launchers != EXPECTED_CMD_LAUNCHERS:
        errors.append(
            f"LAUNCHER_INSTALL_INVENTORY expected {len(EXPECTED_CMD_LAUNCHERS)}, "
            f"got {len(actual_launchers)}"
        )
    for relative in EXPECTED_CMD_LAUNCHERS:
        text = _read_policy_file(root, relative, errors)
        if text is None:
            continue
        profile = "app" if relative == "run_mclab.cmd" else "runtime"
        probe = (
            f'".venv\\Scripts\\python.exe" "scripts\\install_locked.py" --check {profile} >nul 2>&1'
        )
        fallback = f"{probe}\nif errorlevel 1 goto setup"
        if (
            fallback not in text
            or "-m mclab" not in text
            or text.index(probe) > text.index("-m mclab")
        ):
            errors.append(
                f"LAUNCHER_INSTALL_POLICY {relative}: locked check/fallback must precede workload"
            )


def _pip_install_list_count(module: ast.Module) -> int:
    count = 0
    for node in ast.walk(module):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        tokens = tuple(_string_constant(item) for item in node.elts)
        try:
            pip_index = tokens.index("pip")
            install_index = tokens.index("install")
        except ValueError:
            continue
        if pip_index < install_index:
            count += 1
    return count


def _validate_script_install_inventory(root: Path, errors: list[str]) -> None:
    expected_pip_installs = {
        "scripts/audit_supply_chain.py": 1,
        "scripts/install_locked.py": 2,
        "scripts/manage_dependency_locks.py": 1,
    }
    expected_external_flags = {
        "scripts/install_locked.py": 1,
        "scripts/manage_dependency_locks.py": 1,
    }
    for path in sorted((root / "scripts").glob("*.py")):
        relative = path.relative_to(root).as_posix()
        text = _read_policy_file(root, relative, errors)
        if text is None:
            continue
        try:
            module = ast.parse(text, filename=relative)
        except (SyntaxError, ValueError) as exc:
            errors.append(f"SCRIPT_INSTALL_INVENTORY {relative}: cannot parse: {exc}")
            continue
        pip_count = _pip_install_list_count(module)
        external_count = text.count('"--allow-external-env"')
        if pip_count != expected_pip_installs.get(relative, 0):
            errors.append(
                f"SCRIPT_INSTALL_INVENTORY {relative}: expected "
                f"{expected_pip_installs.get(relative, 0)} pip install command(s), got {pip_count}"
            )
        if external_count != expected_external_flags.get(relative, 0):
            errors.append(
                f"SCRIPT_EXTERNAL_ENV_INVENTORY {relative}: expected "
                f"{expected_external_flags.get(relative, 0)} opt-in occurrence(s), "
                f"got {external_count}"
            )


def _validate_install_surfaces(root: Path, errors: list[str]) -> None:
    _validate_auxiliary_paper_lock(root, errors)
    _validate_installer(root, errors)
    _validate_manager(root, errors)
    _validate_workflows(root, errors)
    _validate_bootstraps_and_launchers(root, errors)
    _validate_script_install_inventory(root, errors)
    generator = _read_policy_file(root, "scripts/lock_requirements.py", errors)
    if generator is not None and "python -m pip" in generator:
        errors.append(
            "LOCK_GENERATOR_GUIDANCE raw pip guidance must not bypass the disposable manager"
        )


def _stage_metric(
    name: str,
    threshold: str,
    errors: list[str],
    start: int,
    measured: str,
) -> Metric:
    issue_count = len(errors) - start
    return Metric(
        name, threshold, measured if not issue_count else f"{issue_count} issues", not issue_count
    )


def validate(root: Path = ROOT) -> tuple[list[Metric], list[str]]:
    """Return measurable static lock-policy results and all discovered errors."""

    root = Path(root)
    metrics: list[Metric] = []
    errors: list[str] = []

    start = len(errors)
    _validate_pyproject(root, errors)
    metrics.append(
        _stage_metric(
            "project dependency policy",
            "Python >=3.10,<3.13; exact runtime/app/dev/package/build pins; 12 environments",
            errors,
            start,
            "12 direct project pins; 2 build pins; 12/12 environments",
        )
    )

    start = len(errors)
    _validate_inputs(root, errors)
    metrics.append(
        _stage_metric(
            "generator input separation",
            "build, uv, and supply-chain tools exact and profile-separated",
            errors,
            start,
            "4 build pins; 1 generator pin; 2 scanner pins",
        )
    )

    start = len(errors)
    locks = _validate_locks(root, errors)
    metrics.append(
        _stage_metric(
            "hashed lock profiles",
            "8/8 reviewed profiles; every requirement exact+sha256; unsafe sources 0",
            errors,
            start,
            f"{len(locks)}/8 profiles; "
            f"{sum(lock.requirements for lock in locks.values())} requirements; "
            f"{sum(lock.hashes for lock in locks.values())} hashes",
        )
    )

    start = len(errors)
    _validate_generator(root, errors)
    metrics.append(
        _stage_metric(
            "lock generator policy",
            "uv 0.11.31; cutoff 2026-07-22T07:45:00Z; 8 profiles; reviewed flags",
            errors,
            start,
            "8 profiles; universal/binary/hash/no-sources flags",
        )
    )

    start = len(errors)
    _validate_install_surfaces(root, errors)
    metrics.append(
        _stage_metric(
            "install surface policy",
            "canonical installer/manager; 4 external CI calls; 1 auxiliary lock; 19/19 launchers",
            errors,
            start,
            "2 installer commands; 1 disposable manager; 4 external CI calls; "
            "1 auxiliary lock; 19/19 launchers",
        )
    )
    return metrics, errors


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("usage: check_dependency_locks.py", file=sys.stderr)
        return 2
    try:
        metrics, errors = validate()
    except Exception as exc:  # pragma: no cover - last-resort fail-closed boundary
        print(f"ERROR VALIDATOR_INTERNAL_ERROR {type(exc).__name__}: {exc}")
        print("status: FAIL")
        return 1
    for metric in metrics:
        status = "PASS" if metric.passed else "FAIL"
        print(f"{status} {metric.name}: threshold={metric.threshold}; measured={metric.measured}")
    for error in errors:
        print(f"ERROR {error}")
    failed = bool(errors) or any(not metric.passed for metric in metrics)
    print("status:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
