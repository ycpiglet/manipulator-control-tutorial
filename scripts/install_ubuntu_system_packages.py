#!/usr/bin/env python3
"""Install the controlled Ubuntu desktop packages from one APT snapshot.

This entry point is intentionally fail closed.  It accepts no alternate manifest or
snapshot on the command line, validates the runner and APT source configuration,
and writes evidence only after the requested candidates and installed package state
both match the controlled manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "requirements" / "system" / "ubuntu-24.04-amd64.json"
OS_RELEASE_PATH = Path("/etc/os-release")
APT_ARCHIVE_KEYRING = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
VALIDATION_ROOT = ROOT / "build" / "validation"

SCHEMA_VERSION = 1
SNAPSHOT = "20260723T000000Z"
TARGET_DISTRIBUTION = {
    "id": "ubuntu",
    "version_id": "24.04",
    "codename": "noble",
    "architecture": "amd64",
}
EXPECTED_PACKAGES = (
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

CONTROLLED_APT_SOURCES = f"""\
Types: deb
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-backports
Components: main universe
Architectures: amd64
Snapshot: {SNAPSHOT}
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: https://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main universe
Architectures: amd64
Snapshot: {SNAPSHOT}
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""

_ROOT_KEYS = {"schema_version", "ecosystem", "distribution", "snapshot", "packages"}
_DISTRIBUTION_KEYS = {"id", "version_id", "codename", "architecture"}
_PACKAGE_KEYS = {"name", "version"}
_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
_VERSION_RE = re.compile(r"^[!-~]+$")
_SNAPSHOT_OVERRIDE_FIELD_RE = re.compile(r"^\s*snapshot\s*:", re.IGNORECASE)
_SNAPSHOT_OVERRIDE_OPTION_RE = re.compile(r"(?:^|\s)snapshot\s*=", re.IGNORECASE)
_SOURCE_LINE_RE = re.compile(r"^\s*deb(?:-src)?(?:\s|$)", re.IGNORECASE)
_REPOSITORY_LINE_RE = re.compile(r"^\s*(Hit|Get|Ign|Err):\d*\s*", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_DIAGNOSTIC_RE = re.compile(r"^\s*(?:W:|Warning:|E:|Error:)", re.IGNORECASE)
_MAX_CONTROL_FILE_BYTES = 1_048_576

ARCH_TIMEOUT_SECONDS = 15
QUERY_TIMEOUT_SECONDS = 60
APT_TIMEOUT_SECONDS = 600


class PolicyError(RuntimeError):
    """A controlled-input, host, command, or verification policy failed."""


@dataclass(frozen=True)
class UbuntuManifest:
    snapshot: str
    distribution: Mapping[str, str]
    packages: tuple[tuple[str, str], ...]
    canonical_sha256: str


CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]
EvidenceWriter = Callable[[Path, Mapping[str, object]], None]


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require_exact_keys(value: object, expected: set[str], location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PolicyError(f"{location} must be a JSON object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PolicyError(f"{location} keys do not match schema; missing={missing}, extra={extra}")
    return value


def _read_control_file(path: Path, *, reject_symlink: bool) -> str:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise PolicyError(f"cannot inspect controlled file {path}: {exc}") from exc
    if reject_symlink and stat.S_ISLNK(file_stat.st_mode):
        raise PolicyError(f"controlled file must not be a symlink: {path}")
    if not (stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode)):
        raise PolicyError(f"controlled path is not a regular file: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PolicyError(f"cannot read controlled file {path}: {exc}") from exc
    if len(raw) > _MAX_CONTROL_FILE_BYTES:
        raise PolicyError(f"controlled file is too large: {path}")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PolicyError(f"controlled file is not valid UTF-8: {path}") from exc


def load_manifest(path: Path = MANIFEST_PATH) -> UbuntuManifest:
    """Load and strictly validate the sole supported Ubuntu package manifest."""

    text = _read_control_file(path, reject_symlink=True)
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except PolicyError:
        raise
    except json.JSONDecodeError as exc:
        raise PolicyError(f"invalid JSON in {path}: {exc}") from exc

    root = _require_exact_keys(document, _ROOT_KEYS, "manifest")
    schema_version = root["schema_version"]
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise PolicyError(f"manifest schema_version must be integer {SCHEMA_VERSION}")
    if root["ecosystem"] != "apt":
        raise PolicyError("manifest ecosystem must be 'apt'")

    distribution = _require_exact_keys(
        root["distribution"], _DISTRIBUTION_KEYS, "manifest.distribution"
    )
    if distribution != TARGET_DISTRIBUTION:
        raise PolicyError("manifest distribution must be exactly Ubuntu 24.04 noble on amd64")

    snapshot = root["snapshot"]
    if snapshot != SNAPSHOT:
        raise PolicyError(f"manifest snapshot must be exactly {SNAPSHOT}")

    package_records = root["packages"]
    if not isinstance(package_records, list):
        raise PolicyError("manifest.packages must be a JSON array")
    packages: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, package_record in enumerate(package_records):
        package = _require_exact_keys(package_record, _PACKAGE_KEYS, f"manifest.packages[{index}]")
        name = package["name"]
        version = package["version"]
        if not isinstance(name, str) or not _PACKAGE_NAME_RE.fullmatch(name):
            raise PolicyError(f"invalid package name at manifest.packages[{index}]")
        if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
            raise PolicyError(f"invalid package version at manifest.packages[{index}]")
        if name in seen:
            raise PolicyError(f"duplicate package in manifest: {name}")
        seen.add(name)
        packages.append((name, version))

    names = [name for name, _version in packages]
    if names != sorted(names):
        raise PolicyError("manifest packages must be sorted by package name")
    if tuple(packages) != EXPECTED_PACKAGES:
        raise PolicyError("manifest package set or version pins differ from the approved baseline")

    canonical = json.dumps(
        document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return UbuntuManifest(
        snapshot=SNAPSHOT,
        distribution=dict(TARGET_DISTRIBUTION),
        packages=tuple(packages),
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def parse_os_release(text: str) -> dict[str, str]:
    """Parse os-release assignments while rejecting malformed or duplicate keys."""

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PolicyError(f"malformed os-release line {line_number}")
        key, raw_value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise PolicyError(f"invalid os-release key on line {line_number}")
        if key in values:
            raise PolicyError(f"duplicate os-release key: {key}")
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError as exc:
            raise PolicyError(f"malformed os-release value on line {line_number}") from exc
        if len(parsed) > 1 or (not parsed and raw_value):
            raise PolicyError(f"ambiguous os-release value on line {line_number}")
        values[key] = parsed[0] if parsed else ""
    return values


def validate_host_os(os_release_text: str) -> None:
    values = parse_os_release(os_release_text)
    expected = {
        "ID": TARGET_DISTRIBUTION["id"],
        "VERSION_ID": TARGET_DISTRIBUTION["version_id"],
        "VERSION_CODENAME": TARGET_DISTRIBUTION["codename"],
    }
    observed = {key: values.get(key) for key in expected}
    if observed != expected:
        raise PolicyError(
            "host OS must be Ubuntu 24.04 noble; "
            f"observed ID={observed['ID']!r}, VERSION_ID={observed['VERSION_ID']!r}, "
            f"VERSION_CODENAME={observed['VERSION_CODENAME']!r}"
        )


def validate_no_snapshot_overrides(source_files: Mapping[str, str]) -> None:
    """Reject source-local snapshot IDs or disables that could override ``-S``."""

    for source_name in sorted(source_files):
        text = source_files[source_name]
        if not isinstance(source_name, str) or not isinstance(text, str):
            raise PolicyError("APT source file names and contents must be text")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.split("#", 1)[0]
            if not line.strip():
                continue
            if _SNAPSHOT_OVERRIDE_FIELD_RE.match(line):
                value = line.split(":", 1)[1].strip().lower()
                if value not in {"enable", SNAPSHOT.lower()}:
                    raise PolicyError(
                        f"per-repository Snapshot override in {source_name}:{line_number}"
                    )
            if _SOURCE_LINE_RE.match(line):
                option_match = re.search(r"\[([^\]]*)\]", line)
                if option_match:
                    snapshot_match = _SNAPSHOT_OVERRIDE_OPTION_RE.search(
                        option_match.group(1)
                    )
                    if snapshot_match:
                        value = snapshot_match.group(0).split("=", 1)[1].strip().lower()
                        if value not in {"enable", SNAPSHOT.lower()}:
                            raise PolicyError(
                                "per-repository snapshot option in "
                                f"{source_name}:{line_number}"
                            )


def _validate_archive_keyring(path: Path = APT_ARCHIVE_KEYRING) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PolicyError(f"cannot inspect Ubuntu archive keyring {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PolicyError(f"Ubuntu archive keyring must be a regular non-symlink file: {path}")
    if metadata.st_size <= 0:
        raise PolicyError(f"Ubuntu archive keyring must be nonempty: {path}")
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        raise PolicyError(
            "Ubuntu archive keyring must be owned by root:root: "
            f"{path} (uid={metadata.st_uid}, gid={metadata.st_gid})"
        )
    permissions = stat.S_IMODE(metadata.st_mode)
    if permissions not in {0o644, 0o664}:
        raise PolicyError(
            "Ubuntu archive keyring must have mode 0644 or 0664: "
            f"{path} (observed={permissions:#06o})"
        )
    if not os.access(path, os.R_OK):
        raise PolicyError(f"Ubuntu archive keyring is not readable: {path}")


def _prepare_isolated_apt_environment(root: Path) -> list[str]:
    """Create fixed Ubuntu-only APT inputs and return shared command options."""

    _validate_archive_keyring()
    source_file = root / "mclab-ubuntu.sources"
    source_parts = root / "sourceparts"
    lists = root / "lists"
    archives = root / "archives"
    try:
        os.chmod(root, 0o755)
        for directory in (source_parts, lists, archives):
            directory.mkdir(mode=0o755)
        partial_directories = (lists / "partial", archives / "partial")
        for directory in partial_directories:
            directory.mkdir(mode=0o700)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            try:
                import pwd  # Linux-only entry point; keep module importable elsewhere.

                apt_user = pwd.getpwnam("_apt")
            except (ImportError, KeyError) as exc:
                raise PolicyError("cannot resolve the required Ubuntu _apt account") from exc
            for directory in partial_directories:
                os.chown(directory, apt_user.pw_uid, apt_user.pw_gid)
        source_file.write_text(CONTROLLED_APT_SOURCES, encoding="utf-8", newline="\n")
        source_file.chmod(0o644)
    except OSError as exc:
        raise PolicyError(f"cannot prepare isolated APT state below {root}: {exc}") from exc

    validate_no_snapshot_overrides({str(source_file): CONTROLLED_APT_SOURCES})
    return [
        "-o",
        f"Dir::Etc::sourcelist={source_file}",
        "-o",
        f"Dir::Etc::sourceparts={source_parts}",
        "-o",
        f"Dir::State::lists={lists}",
        "-o",
        f"Dir::Cache::archives={archives}/",
        "-o",
        f"APT::Snapshot={SNAPSHOT}",
        "-o",
        "Acquire::AllowInsecureRepositories=false",
        "-o",
        "Acquire::AllowDowngradeToInsecureRepositories=false",
        "-o",
        "APT::Get::AllowUnauthenticated=false",
    ]


def _snapshot_url_is_allowed(url: str, snapshot: str) -> bool:
    cleaned = url.rstrip(".,);]")
    try:
        parsed = urlsplit(cleaned)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or parsed.hostname != "snapshot.ubuntu.com":
        return False
    if parsed.username or parsed.password or port not in (None, 443):
        return False
    if parsed.query or parsed.fragment:
        return False
    prefix = f"/ubuntu/{snapshot}"
    return parsed.path == prefix or parsed.path.startswith(f"{prefix}/")


def validate_snapshot_update_output(output: str, snapshot: str = SNAPSHOT) -> None:
    """Require warning-free repository activity exclusively from the chosen snapshot."""

    saw_snapshot_repository = False
    for line in output.splitlines():
        if _DIAGNOSTIC_RE.match(line):
            raise PolicyError(f"APT update emitted a warning or error: {line.strip()}")
        repository_match = _REPOSITORY_LINE_RE.match(line)
        if repository_match and repository_match.group(1).lower() in {"ign", "err"}:
            raise PolicyError(f"APT update emitted failed repository activity: {line.strip()}")

        urls = _URL_RE.findall(line)
        for url in urls:
            if not _snapshot_url_is_allowed(url, snapshot):
                raise PolicyError(f"APT update used a non-snapshot repository URL: {url}")

        if repository_match and repository_match.group(1).lower() in {"hit", "get"}:
            if not urls:
                raise PolicyError(
                    f"APT repository activity did not expose a verifiable URL: {line.strip()}"
                )
            saw_snapshot_repository = True

    if not saw_snapshot_repository:
        raise PolicyError("APT update output contains no verified snapshot repository activity")


def _normalize_binary_package(name: str) -> str:
    suffix = f":{TARGET_DISTRIBUTION['architecture']}"
    return name[: -len(suffix)] if name.endswith(suffix) else name


def parse_candidate_versions(output: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    sections: set[str] = set()
    current_package: str | None = None
    for line in output.splitlines():
        header = re.fullmatch(r"([^\s:]+(?::[^\s:]+)?):\s*", line)
        if header:
            current_package = _normalize_binary_package(header.group(1))
            if current_package in sections:
                raise PolicyError(f"duplicate apt-cache package section: {current_package}")
            sections.add(current_package)
            continue
        candidate = re.fullmatch(r"\s*Candidate:\s*(\S+)\s*", line)
        if candidate:
            if current_package is None:
                raise PolicyError("apt-cache Candidate appeared before a package header")
            if current_package in candidates:
                raise PolicyError(f"duplicate Candidate for package: {current_package}")
            candidates[current_package] = candidate.group(1)
    return candidates


def validate_candidate_versions(
    output: str, packages: Sequence[tuple[str, str]] = EXPECTED_PACKAGES
) -> dict[str, str]:
    candidates = parse_candidate_versions(output)
    expected = dict(packages)
    if set(candidates) != set(expected):
        missing = sorted(set(expected) - set(candidates))
        extra = sorted(set(candidates) - set(expected))
        raise PolicyError(f"APT candidate coverage drift; missing={missing}, extra={extra}")
    for name, version in packages:
        if candidates[name] != version:
            raise PolicyError(
                f"APT candidate drift for {name}: expected {version}, got {candidates[name]}"
            )
    return candidates


def validate_installed_versions(
    output: str, packages: Sequence[tuple[str, str]] = EXPECTED_PACKAGES
) -> dict[str, tuple[str, str]]:
    installed: dict[str, tuple[str, str]] = {}
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not all(fields):
            raise PolicyError(f"malformed dpkg-query output on line {line_number}")
        raw_name, version, architecture = fields
        name = _normalize_binary_package(raw_name)
        if name in installed:
            raise PolicyError(f"duplicate installed package result: {name}")
        installed[name] = (version, architecture)

    expected = dict(packages)
    if set(installed) != set(expected):
        missing = sorted(set(expected) - set(installed))
        extra = sorted(set(installed) - set(expected))
        raise PolicyError(f"installed package coverage drift; missing={missing}, extra={extra}")
    for name, version in packages:
        actual_version, architecture = installed[name]
        if actual_version != version:
            raise PolicyError(
                f"installed version drift for {name}: expected {version}, got {actual_version}"
            )
        if architecture != TARGET_DISTRIBUTION["architecture"]:
            raise PolicyError(
                f"installed architecture drift for {name}: expected amd64, got {architecture}"
            )
    return installed


def _run_command(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APT_LISTCHANGES_FRONTEND": "none",
            "DEBIAN_FRONTEND": "noninteractive",
            "LC_ALL": "C",
        }
    )
    return subprocess.run(
        list(command),
        capture_output=True,
        check=False,
        env=environment,
        errors="strict",
        text=True,
        timeout=timeout_seconds,
    )


def _invoke(
    runner: CommandRunner, command: Sequence[str], timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    command_list = list(command)
    try:
        result = runner(command_list, timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise PolicyError(
            f"command timed out after {timeout_seconds}s: {shlex.join(command_list)}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise PolicyError(f"cannot execute {shlex.join(command_list)}: {exc}") from exc
    if type(result.returncode) is not int:
        raise PolicyError(f"command returned an invalid status: {shlex.join(command_list)}")
    if not isinstance(result.stdout, str) or not isinstance(result.stderr, str):
        raise PolicyError(f"command did not return text output: {shlex.join(command_list)}")
    return result


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.rstrip("\n") for part in (result.stdout, result.stderr) if part)


def _require_success(result: subprocess.CompletedProcess[str], command: Sequence[str]) -> None:
    if result.returncode != 0:
        detail = _combined_output(result).strip().replace("\n", " | ")[-1000:]
        raise PolicyError(
            f"command failed with exit {result.returncode}: {shlex.join(list(command))}; "
            f"output={detail!r}"
        )


def _require_no_diagnostics(output: str, label: str) -> None:
    for line in output.splitlines():
        if _DIAGNOSTIC_RE.match(line):
            raise PolicyError(f"{label} emitted a warning or error: {line.strip()}")


def build_evidence(manifest: UbuntuManifest) -> dict[str, object]:
    packages = [
        {
            "architecture": TARGET_DISTRIBUTION["architecture"],
            "candidate_version": version,
            "installed_version": version,
            "name": name,
            "requested_version": version,
        }
        for name, version in manifest.packages
    ]
    return {
        "artifact": "ubuntu-system-package-installation",
        "manifest_canonical_sha256": manifest.canonical_sha256,
        "packages": packages,
        "schema_version": SCHEMA_VERSION,
        "snapshot": manifest.snapshot,
        "status": "verified",
        "target": dict(manifest.distribution),
    }


def write_evidence(output_path: Path, evidence: Mapping[str, object]) -> None:
    if output_path.suffix.lower() != ".json":
        raise PolicyError("evidence output path must end in .json")
    try:
        if output_path.is_symlink():
            raise PolicyError(f"evidence output must not be a symlink: {output_path}")
        if output_path.exists():
            raise PolicyError(f"evidence output already exists: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PolicyError(f"cannot prepare evidence output {output_path}: {exc}") from exc

    serialized = json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=output_path.parent,
            encoding="utf-8",
            delete=False,
            newline="\n",
            prefix=f".{output_path.name}.",
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(serialized)
            temporary.flush()
            os.fchmod(temporary.fileno(), 0o644)
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output_path)
        metadata = output_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o644:
            raise PolicyError(
                f"evidence output must be a regular 0644 file: {output_path}"
            )
    except OSError as exc:
        raise PolicyError(f"cannot write evidence output {output_path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _open_directory_beneath_root(root: Path, parts: Sequence[str]) -> int:
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required_flags):
        raise PolicyError("secure descriptor-relative evidence writing is unavailable")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        root_metadata = root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode) or root.is_symlink():
            raise PolicyError(f"repository root must be a non-symlink directory: {root}")
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise PolicyError(f"cannot anchor secure evidence writer at {root}: {exc}") from exc
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (root_metadata.st_dev, root_metadata.st_ino):
        os.close(descriptor)
        raise PolicyError("repository root changed while anchoring secure evidence writer")
    try:
        for part in parts:
            if part in {"", ".", ".."} or "/" in part or "\\" in part:
                raise PolicyError(f"unsafe evidence directory component: {part!r}")
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise PolicyError(f"cannot traverse secure evidence directory: {exc}") from exc
    except BaseException:
        os.close(descriptor)
        raise


def write_cli_evidence(output_path: Path, evidence: Mapping[str, object]) -> None:
    """Create root-written CLI evidence without following mutable path components."""

    destination = validated_cli_output_path(output_path)
    root = Path(os.path.abspath(ROOT))
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise PolicyError("evidence output has no lexical repository parent") from exc
    parent_descriptor = _open_directory_beneath_root(root, relative.parent.parts)
    temporary_name = f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    temporary_exists = False
    final_linked = False
    completed = False
    try:
        parent_metadata = destination.parent.lstat()
        opened_parent = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(parent_metadata.st_mode) or (
            parent_metadata.st_dev,
            parent_metadata.st_ino,
        ) != (opened_parent.st_dev, opened_parent.st_ino):
            raise PolicyError("evidence parent changed during secure descriptor traversal")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        serialized = (
            json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())

        os.link(
            temporary_name,
            destination.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        final_linked = True
        os.unlink(temporary_name, dir_fd=parent_descriptor)
        temporary_exists = False
        os.fsync(parent_descriptor)

        final_metadata = os.stat(
            destination.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        path_metadata = destination.lstat()
        if (
            not stat.S_ISREG(final_metadata.st_mode)
            or stat.S_IMODE(final_metadata.st_mode) != 0o644
            or (final_metadata.st_dev, final_metadata.st_ino)
            != (path_metadata.st_dev, path_metadata.st_ino)
        ):
            raise PolicyError("secure evidence output is not the expected regular 0644 file")
        completed = True
    except OSError as exc:
        raise PolicyError(f"cannot securely write evidence output {destination}: {exc}") from exc
    finally:
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if final_linked and not completed:
            try:
                os.unlink(destination.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        os.close(parent_descriptor)


def validated_cli_output_path(output_path: Path) -> Path:
    """Constrain privileged CLI evidence to a new file below build/validation."""

    if output_path.suffix.lower() != ".json":
        raise PolicyError("evidence output path must end in .json")
    root_lexical = Path(os.path.abspath(ROOT))
    validation_lexical = Path(os.path.abspath(VALIDATION_ROOT))
    candidate = output_path if output_path.is_absolute() else root_lexical / output_path
    try:
        lexical_relative = candidate.relative_to(validation_lexical)
        if ".." in lexical_relative.parts:
            raise ValueError("ambiguous parent component")
        resolved_root = root_lexical.resolve(strict=True)
        safe_root = validation_lexical.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
        safe_root.relative_to(resolved_root)
        resolved.relative_to(safe_root)
    except (OSError, ValueError) as exc:
        raise PolicyError("evidence output must remain below repository build/validation") from exc
    cursor = candidate
    while cursor != root_lexical:
        if cursor == cursor.parent:
            raise PolicyError("evidence output has no lexical repository parent")
        if cursor.exists() and cursor.is_symlink():
            raise PolicyError(f"evidence output must not traverse a symlink: {output_path}")
        cursor = cursor.parent
    if candidate.exists():
        raise PolicyError(f"evidence output already exists: {output_path}")
    return resolved


def install_and_verify(
    output_path: Path,
    *,
    os_release_text: str,
    source_files: Mapping[str, str],
    runner: CommandRunner = _run_command,
    manifest_path: Path = MANIFEST_PATH,
    evidence_writer: EvidenceWriter = write_evidence,
) -> dict[str, object]:
    """Perform the controlled install and return the deterministic evidence object."""

    manifest = load_manifest(manifest_path)
    validate_host_os(os_release_text)
    validate_no_snapshot_overrides(source_files)

    with tempfile.TemporaryDirectory(prefix="mclab-apt-") as temporary:
        apt_options = _prepare_isolated_apt_environment(Path(temporary))

        architecture_command = ["dpkg", "--print-architecture"]
        architecture_result = _invoke(runner, architecture_command, ARCH_TIMEOUT_SECONDS)
        _require_success(architecture_result, architecture_command)
        _require_no_diagnostics(
            _combined_output(architecture_result), "dpkg architecture query"
        )
        architecture_lines = [
            line.strip() for line in architecture_result.stdout.splitlines() if line.strip()
        ]
        if architecture_lines != [TARGET_DISTRIBUTION["architecture"]]:
            raise PolicyError(
                "host architecture must be amd64; "
                f"observed={architecture_lines if architecture_lines else '(empty)'}"
            )

        update_command = [
            "apt-get",
            *apt_options,
            "-S",
            manifest.snapshot,
            "update",
        ]
        update_result = _invoke(runner, update_command, APT_TIMEOUT_SECONDS)
        update_output = _combined_output(update_result)
        validate_snapshot_update_output(update_output, manifest.snapshot)
        _require_success(update_result, update_command)

        package_names = [name for name, _version in manifest.packages]
        candidate_command = ["apt-cache", *apt_options, "policy", *package_names]
        candidate_result = _invoke(runner, candidate_command, QUERY_TIMEOUT_SECONDS)
        _require_success(candidate_result, candidate_command)
        candidate_output = _combined_output(candidate_result)
        _require_no_diagnostics(candidate_output, "apt-cache policy")
        validate_candidate_versions(candidate_result.stdout, manifest.packages)

        requested_packages = [f"{name}={version}" for name, version in manifest.packages]
        install_command = [
            "apt-get",
            *apt_options,
            "-S",
            manifest.snapshot,
            "install",
            "--yes",
            "--no-install-recommends",
            "--no-remove",
            *requested_packages,
        ]
        install_result = _invoke(runner, install_command, APT_TIMEOUT_SECONDS)
        _require_success(install_result, install_command)
        _require_no_diagnostics(_combined_output(install_result), "apt-get install")

        installed_command = [
            "dpkg-query",
            "-W",
            "-f=${binary:Package}\t${Version}\t${Architecture}\n",
            *package_names,
        ]
        installed_result = _invoke(runner, installed_command, QUERY_TIMEOUT_SECONDS)
        _require_success(installed_result, installed_command)
        _require_no_diagnostics(_combined_output(installed_result), "dpkg-query")
        validate_installed_versions(installed_result.stdout, manifest.packages)

    evidence = build_evidence(manifest)
    evidence_writer(output_path, evidence)
    return evidence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install the controlled Ubuntu 24.04 amd64 package set from the "
            f"{SNAPSHOT} snapshot and write verified JSON evidence."
        )
    )
    parser.add_argument(
        "--install",
        action="store_true",
        required=True,
        help="explicitly authorize the controlled apt-get install operation",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="explicit .json path for deterministic verification evidence",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            raise PolicyError("the controlled Ubuntu package install must run as root")
        output_path = validated_cli_output_path(args.output)
        os_release_text = _read_control_file(OS_RELEASE_PATH, reject_symlink=False)
        install_and_verify(
            output_path,
            os_release_text=os_release_text,
            source_files={"mclab-ubuntu.sources": CONTROLLED_APT_SOURCES},
            evidence_writer=write_cli_evidence,
        )
    except PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Verified Ubuntu package evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
