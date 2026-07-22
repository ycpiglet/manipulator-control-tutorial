"""Build, archive, identify, and verify the platform-local desktop package.

The generated package is deliberately an unsigned development artifact.  Its
canonical evidence is an integrity record, not a signature or an authenticity
claim. Cooperating build and verification invocations for one checkout are
serialized, and the source/generated filesystem is assumed not to be changed
by an untrusted concurrent process. Publication is rollback-safe for caught
exceptions. A process kill or power loss can leave a dot-prefixed transaction
directory; later build/verify operations reject that state for manual
inspection rather than claiming cross-directory crash atomicity.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import zlib
from collections import deque
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIB = 1024 * 1024
ONE_FOLDER_LIMIT_BYTES = 400 * MIB
ARCHIVE_LIMIT_BYTES = 300 * MIB

BUNDLE_NAME = "MCLab"
PACKAGE_DIRECTORY_NAME = "MCLab-package"
EVIDENCE_NAME = "package-metrics.json"
UNSIGNED_MARKER_NAME = "UNSIGNED-DEVELOPMENT-BUILD.txt"
UNSIGNED_MARKER_BYTES = b"UNSIGNED DEVELOPMENT BUILD - NOT FOR PRODUCTION\n"

EVIDENCE_SCHEMA = "mclab.package-metrics.v1"
INVENTORY_SCHEMA = "mclab.bundle-inventory.v1"
IDENTITY_SCHEMA = "mclab.package-identity.v1"
ARCHIVE_FORMAT = "deterministic-tar-gzip"
MAX_EVIDENCE_BYTES = 32 * MIB
MAX_MOUNTINFO_BYTES = 8 * MIB
MAX_MEMBER_COUNT = 200_000
MAX_SYMLINK_EXPANSIONS = 128
_COPY_CHUNK_BYTES = 1024 * 1024
_REPARSE_POINT_FLAG = 0x400
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_WINDOWS_RESERVED_RE = re.compile(
    r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.IGNORECASE
)
_PLATFORM_SLUGS = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
_ARCHITECTURE_SLUGS = {
    "aarch64": "arm64",
    "amd64": "x86_64",
    "arm64": "arm64",
    "x86_64": "x86_64",
}
PROVENANCE_MODE_CHECKOUT = "checkout-bound"
PROVENANCE_MODE_OFFLINE = "offline-self-asserted"
_PYINSTALLER_COMMAND = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--clean",
    "packaging/mclab.spec",
]
_RECORDED_BUILD_COMMAND = ["python", *_PYINSTALLER_COMMAND[1:]]
_SUPPORTED_PLATFORM_MACHINES = {
    "Darwin": frozenset({"arm64", "x86_64"}),
    "Linux": frozenset({"x86_64"}),
    "Windows": frozenset({"amd64"}),
}
_PACKAGE_INPUT_PATHS = frozenset(
    {
        "pyproject.toml",
        "requirements/locks/build.txt",
        "requirements/locks/package.txt",
        "scripts/install_locked.py",
    }
)
_PACKAGE_ENVIRONMENT_SCOPE = (
    "validated-exact-python-package-profile; native-and-base-image-inputs-unbound"
)
_STALE_TRANSACTION_PREFIXES = (
    f".{PACKAGE_DIRECTORY_NAME}.backup-",
    f".{PACKAGE_DIRECTORY_NAME}.failed-",
    f".{PACKAGE_DIRECTORY_NAME}.stage-",
)
_PACKAGE_OPERATION_LOCK_NAME = ".mclab-package-operation.lock"
_PYINSTALLER_WORK_DIRECTORY = Path("build") / "mclab"


class PackageValidationError(RuntimeError):
    """Raised when a package cannot be measured or verified safely."""


class PackageBusyError(PackageValidationError):
    """Raised when another cooperating package operation owns the checkout."""


def _bundle_root() -> Path:
    return ROOT / "dist" / BUNDLE_NAME


def _package_root() -> Path:
    return ROOT / "dist" / PACKAGE_DIRECTORY_NAME


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT_FLAG)


def _require_real_directory(path: Path, *, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise PackageValidationError(f"{label} is missing: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
        raise PackageValidationError(f"{label} must not be a link or reparse point: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise PackageValidationError(f"{label} is not a directory: {path}")
    return metadata


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _decode_mountinfo_path(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def _linux_mount_points() -> frozenset[Path]:
    """Return lexical mount points, including same-device bind mounts on Linux."""

    if not sys.platform.startswith("linux"):
        return frozenset()
    mountinfo = Path("/proc/self/mountinfo")
    try:
        metadata = mountinfo.stat()
        if metadata.st_size > MAX_MOUNTINFO_BYTES:
            raise PackageValidationError("Linux mount table exceeds its safety bound")
        raw = mountinfo.read_bytes()
    except OSError as exc:
        raise PackageValidationError(f"Could not inspect Linux mount boundaries: {exc}") from exc
    if len(raw) > MAX_MOUNTINFO_BYTES:
        raise PackageValidationError("Linux mount table exceeds its safety bound")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise PackageValidationError("Linux mount table is not valid UTF-8") from exc
    points: set[Path] = set()
    for line in lines:
        fields = line.split(" ")
        if len(fields) < 7 or "-" not in fields[6:]:
            raise PackageValidationError("Linux mount table has an invalid record")
        mount_point = _decode_mountinfo_path(fields[4])
        if not mount_point.startswith("/"):
            raise PackageValidationError("Linux mount table has a non-absolute mount point")
        points.add(_absolute_path(Path(mount_point)))
    return frozenset(points)


def _path_is_mount(path: Path, mount_points: frozenset[Path]) -> bool:
    candidate = _absolute_path(path)
    # Windows volume mount points and junctions carry the reparse attribute and
    # are rejected before this helper. ``os.path.ismount`` can nevertheless
    # classify ordinary hosted-runner directories as mount points, so use the
    # fixed lexical containment and reparse checks there. Linux still needs
    # mountinfo for same-device bind mounts; POSIX ``ismount`` covers other
    # mount boundaries.
    if sys.platform.startswith("win"):
        return False
    try:
        return candidate in mount_points or os.path.ismount(candidate)
    except OSError as exc:
        raise PackageValidationError(
            f"Could not inspect mount boundary {candidate}: {exc}"
        ) from exc


def _assert_same_filesystem_member(
    path: Path,
    metadata: os.stat_result,
    *,
    boundary_device: int,
    mount_points: frozenset[Path],
    label: str,
) -> None:
    # CPython 3.11 on the GitHub Windows hosted filesystem reports different
    # st_dev values for ordinary generated descendants on the same drive. The
    # fixed lexical root plus rejection of every Windows reparse point covers
    # drive escapes, junctions, and mounted folders there. POSIX retains both
    # the device check and explicit mount detection (including Linux bind
    # mounts from mountinfo).
    if not sys.platform.startswith("win") and metadata.st_dev != boundary_device:
        raise PackageValidationError(f"{label} crosses a filesystem device boundary: {path}")
    if _path_is_mount(path, mount_points):
        raise PackageValidationError(f"{label} crosses a mount boundary: {path}")


def _require_real_directory_chain(boundary: Path, target: Path, *, label: str) -> None:
    trusted_boundary = _absolute_path(boundary)
    candidate = _absolute_path(target)
    try:
        relative = candidate.relative_to(trusted_boundary)
    except ValueError as exc:
        raise PackageValidationError(
            f"{label} escapes its trusted root {trusted_boundary}: {candidate}"
        ) from exc
    boundary_metadata = _require_real_directory(trusted_boundary, label="Trusted package root")
    mount_points = _linux_mount_points()
    current = trusted_boundary
    for component in relative.parts:
        current /= component
        metadata = _require_real_directory(current, label=label)
        _assert_same_filesystem_member(
            current,
            metadata,
            boundary_device=boundary_metadata.st_dev,
            mount_points=mount_points,
            label=label,
        )


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    identity_matches = left.st_dev == right.st_dev
    if left.st_ino or right.st_ino:
        identity_matches = identity_matches and left.st_ino == right.st_ino
    return (
        identity_matches
        and left.st_mode == right.st_mode
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _validate_component(component: str) -> None:
    if component in {"", ".", ".."}:
        raise PackageValidationError(
            f"Unsafe empty or relative package path component: {component!r}"
        )
    if any(character in component for character in ("/", "\\", "\x00", ":")):
        raise PackageValidationError(f"Unsafe package path component: {component!r}")
    if component[-1] in {" ", "."}:
        raise PackageValidationError(f"Unsafe trailing character in package path: {component!r}")
    if any(ord(character) < 32 or ord(character) == 127 for character in component):
        raise PackageValidationError(f"Unsafe control character in package path: {component!r}")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in component):
        raise PackageValidationError(f"Undecodable package path component: {component!r}")
    if _WINDOWS_RESERVED_RE.fullmatch(component):
        raise PackageValidationError(f"Reserved package path component: {component!r}")


def _validate_relative_path(relative_path: str) -> tuple[str, ...]:
    if not relative_path or "\\" in relative_path or "\x00" in relative_path:
        raise PackageValidationError(f"Unsafe package path: {relative_path!r}")
    parsed = PurePosixPath(relative_path)
    if parsed.is_absolute() or str(parsed) != relative_path:
        raise PackageValidationError(f"Non-canonical package path: {relative_path!r}")
    for component in parsed.parts:
        _validate_component(component)
    return parsed.parts


def _normalized_mode(metadata: os.stat_result, *, directory: bool = False) -> str:
    if directory:
        return "0755"
    return "0755" if metadata.st_mode & 0o111 else "0644"


def _assert_regular_metadata(
    path: Path,
    metadata: os.stat_result,
    *,
    expected_size: int | None = None,
) -> None:
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
        raise PackageValidationError(f"Regular file became a link or reparse point: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise PackageValidationError(f"Expected a regular file: {path}")
    if metadata.st_nlink != 1:
        raise PackageValidationError(f"Hard-linked package files are not allowed: {path}")
    if expected_size is not None and metadata.st_size != expected_size:
        raise PackageValidationError(f"Package file changed size while it was read: {path}")


@contextlib.contextmanager
def _open_regular_file(path: Path, *, expected_size: int | None = None) -> Iterator[BinaryIO]:
    before = path.lstat()
    _assert_regular_metadata(path, before, expected_size=expected_size)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackageValidationError(f"Could not safely open regular file: {path}: {exc}") from exc
    handle = os.fdopen(descriptor, "rb")
    try:
        opened = os.fstat(handle.fileno())
        _assert_regular_metadata(path, opened, expected_size=expected_size)
        if not _same_file_identity(before, opened):
            raise PackageValidationError(f"Package file changed before it was opened: {path}")
        yield handle
        after = os.fstat(handle.fileno())
        if not _same_file_identity(opened, after):
            raise PackageValidationError(f"Package file changed while it was read: {path}")
    finally:
        handle.close()


def _hash_stream(stream: BinaryIO, *, expected_size: int | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(_COPY_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if expected_size is not None and total > expected_size:
            raise PackageValidationError("File produced more bytes than its recorded size")
        digest.update(chunk)
    if expected_size is not None and total != expected_size:
        raise PackageValidationError(
            f"File produced {total} bytes, expected exactly {expected_size} bytes"
        )
    return digest.hexdigest(), total


def _hash_regular_file(path: Path, *, expected_size: int | None = None) -> tuple[str, int]:
    with _open_regular_file(path, expected_size=expected_size) as handle:
        return _hash_stream(handle, expected_size=expected_size)


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _canonical_values_equal(left: object, right: object) -> bool:
    return _canonical_json_bytes(left) == _canonical_json_bytes(right)


def _identity_for_members(members: list[dict[str, object]]) -> str:
    identity_input = {
        "schema": IDENTITY_SCHEMA,
        "bundle_root": BUNDLE_NAME,
        "members": members,
    }
    return hashlib.sha256(_canonical_json_bytes(identity_input)).hexdigest()


def _link_target_components(link_path: str, target: str) -> tuple[str, ...]:
    if not target or "\x00" in target or "\\" in target:
        raise PackageValidationError(f"Unsafe symlink target for {link_path}: {target!r}")
    parsed = PurePosixPath(target)
    if parsed.is_absolute():
        raise PackageValidationError(f"Absolute symlink target for {link_path}: {target!r}")
    for component in parsed.parts:
        if component != "..":
            _validate_component(component)
    return parsed.parts


def _resolve_symlink_target(
    by_path: Mapping[str, dict[str, object]], link_path: str, target: str
) -> dict[str, object]:
    """Resolve a package link with POSIX component ordering and a hard bound.

    ``..`` must be applied after any preceding symlink has been expanded.  A
    lexical normalization would let an otherwise-safe internal link change the
    meaning of later ``..`` components and can therefore conceal an escape.
    End markers keep cycle detection scoped to the symlink expansions that are
    still active while allowing a completed link to be traversed again later.
    """

    end_marker = object()
    pending: deque[object] = deque(_link_target_components(link_path, target))
    resolved = list(PurePosixPath(link_path).parent.parts)
    active_links: list[str] = [link_path]
    expansions = 0

    while pending:
        token = pending.popleft()
        if isinstance(token, tuple) and len(token) == 2 and token[0] is end_marker:
            completed = str(token[1])
            if not active_links or active_links[-1] != completed:
                raise PackageValidationError("Internal error: invalid symlink resolution state")
            active_links.pop()
            continue
        if not isinstance(token, str):
            raise PackageValidationError("Internal error: invalid symlink target component")
        if token == "..":
            if not resolved:
                raise PackageValidationError(
                    f"Symlink target escapes the bundle for {link_path}: {target!r}"
                )
            resolved.pop()
            continue

        candidate = "/".join((*resolved, token))
        member = by_path.get(candidate)
        if member is None:
            raise PackageValidationError(
                f"Symlink target does not exist for {link_path}: {candidate}"
            )
        member_type = member["type"]
        if member_type == "symlink":
            if candidate in active_links:
                chain = " -> ".join((*active_links, candidate))
                raise PackageValidationError(f"Symlink cycle in package: {chain}")
            expansions += 1
            if expansions > MAX_SYMLINK_EXPANSIONS:
                raise PackageValidationError(
                    "Symlink resolution exceeds the "
                    f"{MAX_SYMLINK_EXPANSIONS}-expansion safety bound: {link_path}"
                )
            active_links.append(candidate)
            expansion: list[object] = [
                *_link_target_components(candidate, str(member["target"])),
                (end_marker, candidate),
            ]
            pending.extendleft(reversed(expansion))
            continue

        resolved.append(token)
        has_more_components = any(isinstance(component, str) for component in pending)
        if has_more_components and member_type != "directory":
            raise PackageValidationError(
                f"Symlink target traverses a non-directory member: {candidate}"
            )

    if not resolved:
        raise PackageValidationError(f"Symlink target resolves to the bundle root: {link_path}")
    resolved_path = "/".join(resolved)
    member = by_path.get(resolved_path)
    if member is None:
        raise PackageValidationError(
            f"Symlink target does not exist for {link_path}: {resolved_path}"
        )
    return member


def _validate_symlink_graph(members: list[dict[str, object]]) -> None:
    by_path = {str(member["path"]): member for member in members}

    for member in members:
        if member["type"] != "symlink":
            continue
        link_path = str(member["path"])
        resolved = _resolve_symlink_target(by_path, link_path, str(member["target"]))
        if resolved["type"] not in {"directory", "file"}:
            raise PackageValidationError(
                f"Symlink did not resolve to a file or directory: {link_path}"
            )


def _inventory_bundle(bundle_root: Path) -> tuple[dict[str, object], str]:
    root_before = _require_real_directory(bundle_root, label="Desktop one-folder bundle")
    mount_points = _linux_mount_points()
    members: list[dict[str, object]] = []
    collision_keys: dict[str, str] = {}

    def scan(directory: Path, relative_parts: tuple[str, ...]) -> None:
        directory_before = directory.lstat()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: os.fsencode(entry.name))
        except OSError as exc:
            raise PackageValidationError(
                f"Could not enumerate package directory {directory}: {exc}"
            ) from exc
        if len(members) + len(entries) > MAX_MEMBER_COUNT:
            raise PackageValidationError(
                f"Package inventory exceeds the {MAX_MEMBER_COUNT}-member safety bound"
            )
        for entry in entries:
            _validate_component(entry.name)
            child_parts = (*relative_parts, entry.name)
            relative_path = "/".join(child_parts)
            collision_key = unicodedata.normalize("NFC", relative_path).casefold()
            previous = collision_keys.setdefault(collision_key, relative_path)
            if previous != relative_path:
                raise PackageValidationError(
                    "Package paths collide after Unicode/case normalization: "
                    f"{previous!r} and {relative_path!r}"
                )
            child = Path(entry.path)
            try:
                # On Windows, DirEntry.stat() does not populate the stable file
                # identity fields used by the hard-link and race checks below.
                # Always obtain fresh, path-based no-follow metadata instead.
                metadata = child.lstat()
            except OSError as exc:
                raise PackageValidationError(
                    f"Could not inspect package member {child}: {exc}"
                ) from exc
            if _is_reparse_point(metadata):
                raise PackageValidationError(f"Reparse points are not allowed in packages: {child}")
            _assert_same_filesystem_member(
                child,
                metadata,
                boundary_device=root_before.st_dev,
                mount_points=mount_points,
                label="Desktop bundle member",
            )
            if stat.S_ISDIR(metadata.st_mode):
                members.append(
                    {
                        "mode": _normalized_mode(metadata, directory=True),
                        "path": relative_path,
                        "type": "directory",
                    }
                )
                scan(child, child_parts)
            elif stat.S_ISREG(metadata.st_mode):
                _assert_regular_metadata(child, metadata)
                digest, size = _hash_regular_file(child, expected_size=metadata.st_size)
                members.append(
                    {
                        "mode": _normalized_mode(metadata),
                        "path": relative_path,
                        "sha256": digest,
                        "size_bytes": size,
                        "type": "file",
                    }
                )
            elif stat.S_ISLNK(metadata.st_mode):
                try:
                    target = os.readlink(child)
                except OSError as exc:
                    raise PackageValidationError(
                        f"Could not read package symlink {child}: {exc}"
                    ) from exc
                _link_target_components(relative_path, target)
                target_bytes = target.encode("utf-8")
                members.append(
                    {
                        "mode": "0777",
                        "path": relative_path,
                        "sha256": hashlib.sha256(target_bytes).hexdigest(),
                        "size_bytes": len(target_bytes),
                        "target": target,
                        "type": "symlink",
                    }
                )
            else:
                raise PackageValidationError(f"Special files are not allowed in packages: {child}")
        directory_after = directory.lstat()
        if not _same_file_identity(directory_before, directory_after):
            raise PackageValidationError(
                f"Package directory changed while inventoried: {directory}"
            )

    scan(bundle_root, ())
    root_after = bundle_root.lstat()
    if not _same_file_identity(root_before, root_after):
        raise PackageValidationError(f"Desktop bundle changed while inventoried: {bundle_root}")
    members.sort(key=lambda member: str(member["path"]).encode("utf-8"))
    _validate_symlink_graph(members)
    file_members = [member for member in members if member["type"] == "file"]
    directory_count = sum(member["type"] == "directory" for member in members)
    symlink_count = sum(member["type"] == "symlink" for member in members)
    inventory: dict[str, object] = {
        "bundle_root": BUNDLE_NAME,
        "counts": {
            "directories": directory_count,
            "files": len(file_members),
            "members": len(members),
            "symlinks": symlink_count,
        },
        "members": members,
        "one_folder_bytes": sum(int(member["size_bytes"]) for member in file_members),
        "schema": INVENTORY_SCHEMA,
    }
    return inventory, _identity_for_members(members)


def _tar_info(name: str, *, mode: int, member_type: bytes, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = member_type
    info.size = size
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _write_deterministic_archive(
    bundle_root: Path, inventory: Mapping[str, object], archive_path: Path
) -> None:
    members = inventory["members"]
    if not isinstance(members, list):
        raise PackageValidationError("Internal error: inventory members must be a list")
    with archive_path.open("xb") as raw_archive:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_archive,
            mtime=0,
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                archive.addfile(_tar_info(BUNDLE_NAME, mode=0o755, member_type=tarfile.DIRTYPE))
                for raw_member in members:
                    member = dict(raw_member)
                    relative_path = str(member["path"])
                    _validate_relative_path(relative_path)
                    archive_name = f"{BUNDLE_NAME}/{relative_path}"
                    mode = int(str(member["mode"]), 8)
                    member_type = member["type"]
                    if member_type == "directory":
                        archive.addfile(
                            _tar_info(archive_name, mode=mode, member_type=tarfile.DIRTYPE)
                        )
                    elif member_type == "symlink":
                        info = _tar_info(archive_name, mode=mode, member_type=tarfile.SYMTYPE)
                        info.linkname = str(member["target"])
                        archive.addfile(info)
                    elif member_type == "file":
                        size = int(member["size_bytes"])
                        info = _tar_info(
                            archive_name,
                            mode=mode,
                            member_type=tarfile.REGTYPE,
                            size=size,
                        )
                        with _open_regular_file(
                            bundle_root.joinpath(*PurePosixPath(relative_path).parts),
                            expected_size=size,
                        ) as source:
                            archive.addfile(info, source)
                    else:
                        raise PackageValidationError(
                            f"Internal error: unsupported inventory type {member_type!r}"
                        )
        raw_archive.flush()
        os.fsync(raw_archive.fileno())


def _expected_archive_members(inventory: Mapping[str, object]) -> list[dict[str, object]]:
    expected: list[dict[str, object]] = [{"mode": "0755", "path": BUNDLE_NAME, "type": "directory"}]
    raw_members = inventory["members"]
    if not isinstance(raw_members, list):
        raise PackageValidationError("Inventory members must be a list")
    for raw_member in raw_members:
        member = dict(raw_member)
        member["path"] = f"{BUNDLE_NAME}/{member['path']}"
        expected.append(member)
    return expected


def _verify_archive(archive_path: Path, inventory: Mapping[str, object]) -> None:
    expected_members = _expected_archive_members(inventory)
    with _open_regular_file(archive_path) as archive_stream:
        try:
            with tarfile.open(fileobj=archive_stream, mode="r:gz") as archive:
                seen = 0
                for actual in archive:
                    if seen >= len(expected_members):
                        raise PackageValidationError("Archive contains unexpected extra members")
                    expected = expected_members[seen]
                    seen += 1
                    if actual.name != expected["path"]:
                        raise PackageValidationError(
                            f"Archive member order/path mismatch: {actual.name!r} != {expected['path']!r}"
                        )
                    unexpected_pax = set(actual.pax_headers) - {"linkpath", "path"}
                    if unexpected_pax:
                        raise PackageValidationError(
                            f"Archive member has unexpected PAX metadata {sorted(unexpected_pax)}: "
                            f"{actual.name}"
                        )
                    if "path" in actual.pax_headers and actual.pax_headers["path"] != actual.name:
                        raise PackageValidationError(
                            f"Archive PAX path is inconsistent: {actual.name}"
                        )
                    if (
                        "linkpath" in actual.pax_headers
                        and actual.pax_headers["linkpath"] != actual.linkname
                    ):
                        raise PackageValidationError(
                            f"Archive PAX link target is inconsistent: {actual.name}"
                        )
                    if actual.uid != 0 or actual.gid != 0 or actual.uname or actual.gname:
                        raise PackageValidationError(
                            f"Archive ownership is not normalized: {actual.name}"
                        )
                    if actual.mtime != 0 or actual.mode != int(str(expected["mode"]), 8):
                        raise PackageValidationError(
                            f"Archive metadata is not normalized: {actual.name}"
                        )
                    expected_type = expected["type"]
                    if expected_type == "directory":
                        if not actual.isdir() or actual.size != 0:
                            raise PackageValidationError(
                                f"Invalid archive directory: {actual.name}"
                            )
                    elif expected_type == "symlink":
                        if (
                            not actual.issym()
                            or actual.linkname != expected["target"]
                            or actual.size != 0
                        ):
                            raise PackageValidationError(f"Invalid archive symlink: {actual.name}")
                    elif expected_type == "file":
                        expected_size = int(expected["size_bytes"])
                        if not actual.isfile() or actual.size != expected_size:
                            raise PackageValidationError(
                                f"Invalid archive file size/type: {actual.name}"
                            )
                        extracted = archive.extractfile(actual)
                        if extracted is None:
                            raise PackageValidationError(
                                f"Could not read archive member: {actual.name}"
                            )
                        digest, size = _hash_stream(extracted, expected_size=expected_size)
                        if size != expected_size or digest != expected["sha256"]:
                            raise PackageValidationError(
                                f"Archive member digest mismatch: {actual.name}"
                            )
                    else:
                        raise PackageValidationError(
                            f"Unsupported inventory member type: {expected_type!r}"
                        )
                if seen != len(expected_members):
                    missing = expected_members[seen]["path"]
                    raise PackageValidationError(f"Archive is missing expected member: {missing}")
        except (gzip.BadGzipFile, tarfile.TarError, EOFError, OSError) as exc:
            raise PackageValidationError(
                f"Invalid compressed package archive: {archive_path}: {exc}"
            ) from exc


def _verify_canonical_archive_bytes(
    bundle_root: Path,
    inventory: Mapping[str, object],
    *,
    actual_sha256: str,
    actual_size: int,
) -> None:
    """Rebuild the v1 archive in disposable space and require exact bytes."""

    with tempfile.TemporaryDirectory(prefix="mclab-package-verify-") as temporary:
        candidate = Path(temporary) / "canonical.tar.gz"
        _write_deterministic_archive(bundle_root, inventory, candidate)
        metadata = candidate.lstat()
        expected_sha256, expected_size = _hash_regular_file(
            candidate, expected_size=metadata.st_size
        )
    if (actual_sha256, actual_size) != (expected_sha256, expected_size):
        raise PackageValidationError(
            "Compressed archive is semantically valid but not the canonical "
            "deterministic-tar-gzip encoding"
        )


def _platform_slug(system_name: str) -> str:
    try:
        return _PLATFORM_SLUGS[system_name]
    except KeyError as exc:
        raise PackageValidationError(f"Unsupported package platform: {system_name!r}") from exc


def _architecture_slug(machine: str) -> str:
    normalized = machine.strip().lower()
    try:
        return _ARCHITECTURE_SLUGS[normalized]
    except KeyError as exc:
        raise PackageValidationError(f"Unsupported package architecture: {machine!r}") from exc


def _archive_name(system_name: str, machine: str) -> str:
    platform_slug = _platform_slug(system_name)
    architecture_slug = _architecture_slug(machine)
    supported = _SUPPORTED_PLATFORM_MACHINES[system_name]
    if machine.strip().lower() not in supported:
        raise PackageValidationError(
            f"Unsupported package platform/architecture pair: {system_name} {machine}"
        )
    return f"MCLab-{platform_slug}-{architecture_slug}-unsigned-development.tar.gz"


def _git_text(*arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PackageValidationError(
            f"Could not record exact Git provenance using: git {' '.join(arguments)}"
        ) from exc
    value = result.stdout.strip()
    return value


def _checkout_binding() -> dict[str, object]:
    commit = _git_text("rev-parse", "HEAD")
    if _COMMIT_RE.fullmatch(commit) is None:
        raise PackageValidationError(f"Git did not return an exact 40-hex commit: {commit!r}")
    dirty_status = _git_text("status", "--porcelain", "--untracked-files=normal")
    spec_path = ROOT / "packaging" / "mclab.spec"
    spec_sha256, _ = _hash_regular_file(spec_path)
    return {
        "source_commit": commit,
        "source_dirty": bool(dirty_status),
        "spec_path": "packaging/mclab.spec",
        "spec_sha256": spec_sha256,
    }


def _inventory_sha256(inventory: list[dict[str, str]]) -> str:
    payload = json.dumps(inventory, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _package_environment_record() -> dict[str, object]:
    """Validate and record the bounded, locked Python package build profile."""

    from scripts import install_locked as locked

    if _absolute_path(locked.ROOT) != _absolute_path(ROOT):
        raise PackageValidationError("Locked environment validator belongs to another checkout")
    try:
        support_error = locked.support_error("package")
        if support_error:
            raise PackageValidationError(f"Unsupported package build environment: {support_error}")
        inventory = locked._distribution_inventory()
        errors = locked._locked_version_errors("package", inventory)
        errors.extend(locked._unexpected_distribution_errors("package", inventory))
        record_integrity, record_errors = locked._record_integrity("package")
        errors.extend(record_errors)
        editable_error = locked._editable_error()
        if editable_error:
            errors.append(editable_error)
        if errors:
            raise PackageValidationError(
                "Package build environment does not match the reviewed package profile:\n- "
                + "\n- ".join(errors)
            )
        inputs = locked._state_inputs("package")
    except PackageValidationError:
        raise
    except (OSError, UnicodeError, ValueError, locked.LockedInstallError) as exc:
        raise PackageValidationError(
            f"Could not validate the locked package build environment: {exc}"
        ) from exc
    if set(inputs) != _PACKAGE_INPUT_PATHS:
        raise PackageValidationError("Package build input set drifted")
    return {
        "distribution_count": len(inventory),
        "distributions": inventory,
        "inputs": inputs,
        "inventory_sha256": _inventory_sha256(inventory),
        "profile": "package",
        "record_integrity": record_integrity,
        "scope": _PACKAGE_ENVIRONMENT_SCOPE,
    }


def _source_provenance(system_name: str) -> dict[str, object]:
    checkout = _checkout_binding()
    try:
        pyinstaller_version = importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError as exc:
        raise PackageValidationError("PyInstaller version metadata is unavailable") from exc
    machine = platform.machine()
    _archive_name(system_name, machine)
    return {
        "build_command": list(_RECORDED_BUILD_COMMAND),
        "package_environment": _package_environment_record(),
        "platform": {
            "machine": machine,
            "release": platform.release(),
            "system": system_name,
        },
        "pyinstaller_version": pyinstaller_version,
        "python": {
            "implementation": platform.python_implementation(),
            "pointer_bits": struct.calcsize("P") * 8,
            "version": platform.python_version(),
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        },
        **checkout,
    }


def _gate_payload(measured_bytes: int, limit_bytes: int, *, enforced: bool) -> dict[str, object]:
    return {
        "enforced": enforced,
        "limit_bytes": limit_bytes,
        "measured_bytes": measured_bytes,
        "passed": measured_bytes <= limit_bytes,
        "unit": "bytes",
    }


def _marker_evidence(inventory: Mapping[str, object]) -> dict[str, object]:
    members = inventory["members"]
    if not isinstance(members, list):
        raise PackageValidationError("Inventory members must be a list")
    matches = [member for member in members if member.get("path") == UNSIGNED_MARKER_NAME]
    if len(matches) != 1 or matches[0].get("type") != "file":
        raise PackageValidationError("Unsigned development marker is missing from the inventory")
    marker = matches[0]
    expected_digest = hashlib.sha256(UNSIGNED_MARKER_BYTES).hexdigest()
    if marker.get("sha256") != expected_digest or marker.get("size_bytes") != len(
        UNSIGNED_MARKER_BYTES
    ):
        raise PackageValidationError("Unsigned development marker content is invalid")
    return {
        "path": UNSIGNED_MARKER_NAME,
        "sha256": expected_digest,
        "text": UNSIGNED_MARKER_BYTES.decode("utf-8").rstrip("\n"),
    }


def _evidence_payload(
    *,
    inventory: dict[str, object],
    package_identity: str,
    archive_name: str,
    archive_size: int,
    archive_sha256: str,
    provenance: dict[str, object],
    size_gate_enforced: bool,
) -> dict[str, object]:
    one_folder_bytes = int(inventory["one_folder_bytes"])
    return {
        "archive": {
            "filename": archive_name,
            "format": ARCHIVE_FORMAT,
            "sha256": archive_sha256,
            "size_bytes": archive_size,
        },
        "artifact_class": "unsigned-development",
        "gates": {
            "archive": _gate_payload(
                archive_size, ARCHIVE_LIMIT_BYTES, enforced=size_gate_enforced
            ),
            "one_folder": _gate_payload(
                one_folder_bytes, ONE_FOLDER_LIMIT_BYTES, enforced=size_gate_enforced
            ),
        },
        "inventory": inventory,
        "package_identity": {"algorithm": "sha256", "value": package_identity},
        "schema": EVIDENCE_SCHEMA,
        "source": provenance,
        "unsigned_marker": _marker_evidence(inventory),
    }


def _check_size_gate(name: str, measured: int, limit: int, *, enforced: bool) -> None:
    print(f"MCLab {name} size: {measured / MIB:.1f} MiB ({measured} bytes)")
    if measured > limit and enforced:
        limit_mib = limit // MIB
        raise PackageValidationError(
            f"Desktop {name} exceeds {limit_mib} MiB: {measured} bytes (limit {limit} bytes)"
        )
    if measured > limit:
        print(f"WARNING: {name} size gate was explicitly skipped.")


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageValidationError(f"Duplicate key in package evidence: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise PackageValidationError(f"Non-finite number in package evidence: {value}")


def _read_evidence(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise PackageValidationError(f"Package evidence is missing: {path}") from exc
    _assert_regular_metadata(path, metadata)
    if metadata.st_size > MAX_EVIDENCE_BYTES:
        raise PackageValidationError(
            f"Package evidence exceeds the {MAX_EVIDENCE_BYTES}-byte safety bound"
        )
    with _open_regular_file(path, expected_size=metadata.st_size) as handle:
        raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=_duplicate_key_guard,
            parse_constant=_reject_json_constant,
        )
    except PackageValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PackageValidationError(f"Invalid package evidence JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageValidationError("Package evidence root must be an object")
    try:
        canonical = _canonical_json_bytes(payload)
    except (RecursionError, TypeError, ValueError) as exc:
        raise PackageValidationError(f"Package evidence cannot be canonicalized: {exc}") from exc
    if raw != canonical:
        raise PackageValidationError("Package evidence is not canonical JSON")
    return payload


def _validate_source_record(source: object) -> dict[str, object]:
    if not isinstance(source, dict) or set(source) != {
        "build_command",
        "package_environment",
        "platform",
        "pyinstaller_version",
        "python",
        "source_commit",
        "source_dirty",
        "spec_path",
        "spec_sha256",
    }:
        raise PackageValidationError("Package source provenance has an invalid shape")
    build_command = source["build_command"]
    if build_command != _RECORDED_BUILD_COMMAND:
        raise PackageValidationError("Package build command provenance is invalid")
    recorded_platform = source["platform"]
    if not isinstance(recorded_platform, dict) or set(recorded_platform) != {
        "machine",
        "release",
        "system",
    }:
        raise PackageValidationError("Package platform provenance has an invalid shape")
    system_name = recorded_platform["system"]
    if not isinstance(system_name, str):
        raise PackageValidationError("Package platform system must be a string")
    _platform_slug(system_name)
    for key in ("machine", "release"):
        if not isinstance(recorded_platform[key], str) or not recorded_platform[key]:
            raise PackageValidationError(f"Package platform {key} must be non-empty")
    _archive_name(system_name, str(recorded_platform["machine"]))
    if not isinstance(source["pyinstaller_version"], str) or not source["pyinstaller_version"]:
        raise PackageValidationError("Package provenance pyinstaller_version must be non-empty")
    python_record = source["python"]
    if not isinstance(python_record, dict) or set(python_record) != {
        "implementation",
        "pointer_bits",
        "version",
        "zlib_runtime_version",
    }:
        raise PackageValidationError("Package Python provenance has an invalid shape")
    if python_record["implementation"] != "CPython":
        raise PackageValidationError("Package Python implementation must be CPython")
    if type(python_record["pointer_bits"]) is not int or python_record["pointer_bits"] != 64:
        raise PackageValidationError("Package Python must be a 64-bit interpreter")
    python_version = python_record["version"]
    if (
        not isinstance(python_version, str)
        or re.fullmatch(r"3\.(?:10|11|12)\.\d+", python_version) is None
    ):
        raise PackageValidationError("Package Python version must be supported CPython 3.10-3.12")
    if (
        not isinstance(python_record["zlib_runtime_version"], str)
        or not python_record["zlib_runtime_version"]
    ):
        raise PackageValidationError("Package zlib runtime version must be non-empty")

    environment = source["package_environment"]
    if not isinstance(environment, dict) or set(environment) != {
        "distribution_count",
        "distributions",
        "inputs",
        "inventory_sha256",
        "profile",
        "record_integrity",
        "scope",
    }:
        raise PackageValidationError("Package environment provenance has an invalid shape")
    if environment["profile"] != "package" or environment["scope"] != _PACKAGE_ENVIRONMENT_SCOPE:
        raise PackageValidationError("Package environment profile or scope is invalid")
    distributions = environment["distributions"]
    if not isinstance(distributions, list) or not distributions:
        raise PackageValidationError("Package environment distributions must be a non-empty list")
    normalized_distributions: list[dict[str, str]] = []
    for index, distribution in enumerate(distributions):
        if not isinstance(distribution, dict) or set(distribution) != {"name", "version"}:
            raise PackageValidationError(
                f"Package environment distribution {index} has an invalid shape"
            )
        name = distribution["name"]
        version = distribution["version"]
        if (
            not isinstance(name, str)
            or not name
            or re.sub(r"[-_.]+", "-", name).lower() != name
            or not isinstance(version, str)
            or not version
        ):
            raise PackageValidationError(
                f"Package environment distribution {index} is not normalized"
            )
        normalized_distributions.append({"name": name, "version": version})
    if normalized_distributions != sorted(
        normalized_distributions, key=lambda item: (item["name"], item["version"])
    ) or len({item["name"] for item in normalized_distributions}) != len(normalized_distributions):
        raise PackageValidationError("Package environment distributions must be sorted and unique")
    distribution_count = environment["distribution_count"]
    if type(distribution_count) is not int or distribution_count != len(normalized_distributions):
        raise PackageValidationError("Package environment distribution count is invalid")
    inventory_sha256 = environment["inventory_sha256"]
    if (
        not isinstance(inventory_sha256, str)
        or _SHA256_RE.fullmatch(inventory_sha256) is None
        or inventory_sha256 != _inventory_sha256(normalized_distributions)
    ):
        raise PackageValidationError("Package environment inventory SHA-256 is invalid")
    inputs = environment["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != _PACKAGE_INPUT_PATHS:
        raise PackageValidationError("Package environment input set is invalid")
    if any(
        not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
        for value in inputs.values()
    ):
        raise PackageValidationError("Package environment input digest is invalid")
    record_integrity = environment["record_integrity"]
    if not isinstance(record_integrity, dict) or set(record_integrity) != {"files", "sha256"}:
        raise PackageValidationError("Package RECORD integrity provenance has an invalid shape")
    if type(record_integrity["files"]) is not int or record_integrity["files"] <= 0:
        raise PackageValidationError("Package RECORD integrity file count is invalid")
    if (
        not isinstance(record_integrity["sha256"], str)
        or _SHA256_RE.fullmatch(record_integrity["sha256"]) is None
    ):
        raise PackageValidationError("Package RECORD integrity digest is invalid")
    matching_pyinstaller = [
        item["version"] for item in normalized_distributions if item["name"] == "pyinstaller"
    ]
    if matching_pyinstaller != [source["pyinstaller_version"]]:
        raise PackageValidationError("PyInstaller version and package inventory disagree")
    if (
        not isinstance(source["source_commit"], str)
        or _COMMIT_RE.fullmatch(source["source_commit"]) is None
    ):
        raise PackageValidationError("Package source commit must be exact 40-hex")
    if type(source["source_dirty"]) is not bool:
        raise PackageValidationError("Package source_dirty must be a boolean")
    if source["spec_path"] != "packaging/mclab.spec":
        raise PackageValidationError("Package spec path provenance is invalid")
    if (
        not isinstance(source["spec_sha256"], str)
        or _SHA256_RE.fullmatch(source["spec_sha256"]) is None
    ):
        raise PackageValidationError("Package spec digest must be SHA-256")
    return source


def _verify_checkout_bound_provenance(source: Mapping[str, object]) -> None:
    if source["source_dirty"]:
        raise PackageValidationError(
            "Checkout-bound package provenance requires a clean recorded source tree"
        )
    current_system = platform.system()
    recorded_platform = source["platform"]
    if not isinstance(recorded_platform, Mapping):
        raise PackageValidationError("Package platform provenance has an invalid shape")
    if recorded_platform["system"] != current_system:
        raise PackageValidationError(
            "Checkout-bound package provenance was recorded on a different platform"
        )
    current = _source_provenance(current_system)
    if current["source_dirty"]:
        raise PackageValidationError(
            "Checkout-bound package verification requires a clean current source tree"
        )
    if not _canonical_values_equal(source, current):
        raise PackageValidationError(
            "Package source provenance does not match the current checkout and build environment"
        )


def _require_exact_package_files(package_root: Path, archive_name: str) -> None:
    root_before = _require_real_directory(package_root, label="Package evidence directory")
    mount_points = _linux_mount_points()
    expected = {archive_name, EVIDENCE_NAME}
    actual: set[str] = set()
    for entry in os.scandir(package_root):
        _validate_component(entry.name)
        child = Path(entry.path)
        metadata = child.lstat()
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
            raise PackageValidationError(f"Package evidence entry must not be linked: {entry.path}")
        _assert_same_filesystem_member(
            child,
            metadata,
            boundary_device=root_before.st_dev,
            mount_points=mount_points,
            label="Package evidence entry",
        )
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PackageValidationError(
                f"Package evidence entry must be a regular file: {entry.path}"
            )
        actual.add(entry.name)
    if actual != expected:
        raise PackageValidationError(
            f"Package evidence directory contents differ: expected {sorted(expected)}, got {sorted(actual)}"
        )
    if not _same_file_identity(root_before, package_root.lstat()):
        raise PackageValidationError("Package evidence directory changed during verification")


def _verify_package_unlocked(
    bundle_root: Path | None = None,
    package_root: Path | None = None,
    *,
    require_size_gates: bool = True,
    provenance_mode: str = PROVENANCE_MODE_CHECKOUT,
    _allow_staging_package: bool = False,
) -> dict[str, object]:
    """Verify saved evidence without rewriting it while the operation lock is held.

    The default binds the recorded clean checkout, supported platform tuple,
    exact locked Python package profile, installed RECORD fingerprint, and
    archive runtime to the current environment. Native/base-image inputs remain
    outside this development record. The explicit offline mode verifies only
    internal artifact consistency and always reports itself as non-gating.
    """

    if provenance_mode not in {PROVENANCE_MODE_CHECKOUT, PROVENANCE_MODE_OFFLINE}:
        raise PackageValidationError(f"Unsupported package provenance mode: {provenance_mode!r}")

    bundle = bundle_root or _bundle_root()
    package = package_root or _package_root()
    bundle = _absolute_path(bundle)
    package = _absolute_path(package)
    package_name_is_valid = package.name == PACKAGE_DIRECTORY_NAME or (
        _allow_staging_package and package.name.startswith(f".{PACKAGE_DIRECTORY_NAME}.stage-")
    )
    if (
        bundle.name != BUNDLE_NAME
        or not package_name_is_valid
        or bundle.parent != package.parent
        or bundle.parent.name != "dist"
    ):
        raise PackageValidationError("Bundle and package evidence do not use the fixed dist layout")
    repository_root = bundle.parent.parent
    if bundle_root is None and package_root is None and repository_root != _absolute_path(ROOT):
        raise PackageValidationError("Default package paths do not belong to the repository root")
    _require_real_directory_chain(repository_root, bundle.parent, label="Distribution directory")
    if not _allow_staging_package:
        _reject_stale_package_transactions(bundle.parent)
    _require_real_directory_chain(repository_root, bundle, label="Desktop one-folder bundle")
    _require_real_directory_chain(repository_root, package, label="Package evidence directory")
    evidence_path = package / EVIDENCE_NAME
    payload = _read_evidence(evidence_path)
    if set(payload) != {
        "archive",
        "artifact_class",
        "gates",
        "inventory",
        "package_identity",
        "schema",
        "source",
        "unsigned_marker",
    }:
        raise PackageValidationError("Package evidence has unknown or missing top-level fields")
    if payload["schema"] != EVIDENCE_SCHEMA or payload["artifact_class"] != "unsigned-development":
        raise PackageValidationError("Package evidence schema or artifact class is invalid")
    source = _validate_source_record(payload["source"])
    if provenance_mode == PROVENANCE_MODE_CHECKOUT:
        _verify_checkout_bound_provenance(source)
    recorded_platform = dict(source["platform"])
    system_name = str(recorded_platform["system"])
    machine = str(recorded_platform["machine"])
    archive_name = _archive_name(system_name, machine)
    _require_exact_package_files(package, archive_name)

    actual_inventory, actual_identity = _inventory_bundle(bundle)
    if not _canonical_values_equal(payload["inventory"], actual_inventory):
        raise PackageValidationError(
            "Desktop bundle inventory does not match saved package evidence"
        )
    expected_identity = {"algorithm": "sha256", "value": actual_identity}
    if not _canonical_values_equal(payload["package_identity"], expected_identity):
        raise PackageValidationError(
            "Desktop bundle identity does not match saved package evidence"
        )
    expected_marker = _marker_evidence(actual_inventory)
    if not _canonical_values_equal(payload["unsigned_marker"], expected_marker):
        raise PackageValidationError("Unsigned marker evidence does not match the bundle")

    archive_path = package / archive_name
    archive_metadata = archive_path.lstat()
    _assert_regular_metadata(archive_path, archive_metadata)
    if require_size_gates and archive_metadata.st_size > ARCHIVE_LIMIT_BYTES:
        raise PackageValidationError(
            "Compressed archive exceeds the verification safety/size bound: "
            f"{archive_metadata.st_size} bytes"
        )
    archive_sha256, archive_size = _hash_regular_file(
        archive_path, expected_size=archive_metadata.st_size
    )
    _verify_archive(archive_path, actual_inventory)
    expected_archive = {
        "filename": archive_name,
        "format": ARCHIVE_FORMAT,
        "sha256": archive_sha256,
        "size_bytes": archive_size,
    }
    if not _canonical_values_equal(payload["archive"], expected_archive):
        raise PackageValidationError("Compressed archive identity does not match saved evidence")
    _verify_canonical_archive_bytes(
        bundle,
        actual_inventory,
        actual_sha256=archive_sha256,
        actual_size=archive_size,
    )

    gates = payload["gates"]
    if not isinstance(gates, dict) or set(gates) != {"archive", "one_folder"}:
        raise PackageValidationError("Package size gates have an invalid shape")
    recorded_enforcement: bool | None = None
    for name in ("archive", "one_folder"):
        gate = gates[name]
        if not isinstance(gate, dict) or set(gate) != {
            "enforced",
            "limit_bytes",
            "measured_bytes",
            "passed",
            "unit",
        }:
            raise PackageValidationError(f"Package {name} gate has an invalid shape")
        if type(gate["enforced"]) is not bool or type(gate["passed"]) is not bool:
            raise PackageValidationError(f"Package {name} gate booleans are invalid")
        if type(gate["limit_bytes"]) is not int or type(gate["measured_bytes"]) is not int:
            raise PackageValidationError(f"Package {name} gate measurements must be exact integers")
        if gate["unit"] != "bytes":
            raise PackageValidationError(f"Package {name} gate unit must be bytes")
        if recorded_enforcement is None:
            recorded_enforcement = gate["enforced"]
        elif gate["enforced"] is not recorded_enforcement:
            raise PackageValidationError("Package size gate enforcement flags disagree")
    assert recorded_enforcement is not None
    expected_gates = {
        "archive": _gate_payload(archive_size, ARCHIVE_LIMIT_BYTES, enforced=recorded_enforcement),
        "one_folder": _gate_payload(
            int(actual_inventory["one_folder_bytes"]),
            ONE_FOLDER_LIMIT_BYTES,
            enforced=recorded_enforcement,
        ),
    }
    if not _canonical_values_equal(gates, expected_gates):
        raise PackageValidationError(
            "Package size measurements or thresholds do not match evidence"
        )
    if require_size_gates and not recorded_enforcement:
        raise PackageValidationError(
            "Package size evidence is intact, but the gates were not enforced"
        )
    if require_size_gates and not all(bool(gate["passed"]) for gate in expected_gates.values()):
        raise PackageValidationError(
            "Package evidence is intact, but one or more size gates failed"
        )
    if provenance_mode == PROVENANCE_MODE_OFFLINE:
        print(
            "NON-GATING OFFLINE CHECK ONLY: artifact contents are internally consistent, "
            "but source provenance is self-asserted and was not authenticated."
        )
    return payload


def _package_layout_roots(
    bundle_root: Path | None,
    package_root: Path | None,
) -> tuple[Path, Path, Path, Path]:
    bundle = _absolute_path(bundle_root or _bundle_root())
    package = _absolute_path(package_root or _package_root())
    if bundle.parent != package.parent or bundle.parent.name != "dist":
        raise PackageValidationError("Bundle and package evidence do not use the fixed dist layout")
    dist = bundle.parent
    return bundle, package, dist.parent, dist


def _lock_descriptor_nonblocking(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_descriptor(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextlib.contextmanager
def _package_operation_lock(repository_root: Path, dist: Path) -> Iterator[None]:
    """Serialize cooperating package operations for one physical checkout.

    The persistent lock file is ignored build state under ``dist``. It prevents
    two supported CLI invocations from racing, but deliberately does not claim
    protection from a process that ignores the advisory lock and mutates the
    checkout or generated trees.
    """

    repository = _absolute_path(repository_root)
    distribution = _absolute_path(dist)
    if distribution != repository / "dist":
        raise PackageValidationError("Package operation lock requires the fixed dist layout")
    _require_real_directory(repository, label="Repository root")
    _require_real_directory_chain(
        repository,
        distribution,
        label="Distribution directory",
    )
    lock_path = distribution / _PACKAGE_OPERATION_LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= (
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise PackageValidationError(f"Could not open package operation lock: {exc}") from exc
    locked = False
    try:
        opened = os.fstat(descriptor)
        try:
            named = lock_path.lstat()
        except OSError as exc:
            raise PackageValidationError(
                f"Could not inspect package operation lock: {exc}"
            ) from exc
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or stat.S_ISLNK(named.st_mode)
            or _is_reparse_point(named)
            or not _same_file_identity(opened, named)
        ):
            raise PackageValidationError(
                f"Package operation lock must be one stable regular file: {lock_path}"
            )
        if opened.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
            opened = os.fstat(descriptor)
            named = lock_path.lstat()
        dist_before = _require_real_directory(distribution, label="Distribution directory")
        try:
            _lock_descriptor_nonblocking(descriptor)
        except (BlockingIOError, OSError) as exc:
            raise PackageBusyError(
                "Another package build or verification operation is active for this checkout"
            ) from exc
        locked = True
        if not _same_file_identity(named, lock_path.lstat()):
            raise PackageValidationError("Package operation lock changed during acquisition")
        dist_after = _require_real_directory(distribution, label="Distribution directory")
        if not _same_file_identity(dist_before, dist_after):
            raise PackageValidationError("Distribution directory changed during lock acquisition")
        yield
    finally:
        try:
            if locked:
                _unlock_descriptor(descriptor)
        finally:
            os.close(descriptor)


def verify_package(
    bundle_root: Path | None = None,
    package_root: Path | None = None,
    *,
    require_size_gates: bool = True,
    provenance_mode: str = PROVENANCE_MODE_CHECKOUT,
    _allow_staging_package: bool = False,
) -> dict[str, object]:
    """Verify one package while excluding cooperating builds and verifiers."""

    bundle, package, repository, dist = _package_layout_roots(bundle_root, package_root)
    with _package_operation_lock(repository, dist):
        return _verify_package_unlocked(
            bundle,
            package,
            require_size_gates=require_size_gates,
            provenance_mode=provenance_mode,
            _allow_staging_package=_allow_staging_package,
        )


def _prepare_dist_directory() -> Path:
    repository = _absolute_path(ROOT)
    _require_real_directory(repository, label="Repository root")
    dist = repository / "dist"
    if dist.exists() or dist.is_symlink():
        _require_real_directory_chain(repository, dist, label="Distribution directory")
    else:
        dist.mkdir(mode=0o755)
    return dist


def _validate_owned_tree_for_removal(path: Path, *, label: str) -> None:
    root_metadata = _require_real_directory(path, label=label)
    mount_points = _linux_mount_points()
    pending = [path]
    seen = 0
    while pending:
        directory = pending.pop()
        before = _require_real_directory(directory, label=label)
        if directory != path:
            _assert_same_filesystem_member(
                directory,
                before,
                boundary_device=root_metadata.st_dev,
                mount_points=mount_points,
                label=label,
            )
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise PackageValidationError(
                f"Could not enumerate owned directory before removal {directory}: {exc}"
            ) from exc
        seen += len(entries)
        if seen > MAX_MEMBER_COUNT:
            raise PackageValidationError(
                f"Owned directory exceeds the {MAX_MEMBER_COUNT}-member removal safety bound"
            )
        for entry in entries:
            _validate_component(entry.name)
            child = Path(entry.path)
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise PackageValidationError(
                    f"Could not inspect owned member before removal {child}: {exc}"
                ) from exc
            if _is_reparse_point(metadata):
                raise PackageValidationError(
                    f"Owned directory contains a reparse point and will not be removed: {child}"
                )
            _assert_same_filesystem_member(
                child,
                metadata,
                boundary_device=root_metadata.st_dev,
                mount_points=mount_points,
                label=label,
            )
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(child)
        if not _same_file_identity(before, directory.lstat()):
            raise PackageValidationError(
                f"Owned directory changed during removal preflight: {directory}"
            )


def _validate_owned_directory_for_removal(path: Path, *, boundary: Path, label: str) -> bool:
    candidate = _absolute_path(path)
    try:
        candidate.lstat()
    except FileNotFoundError:
        return False
    try:
        _require_real_directory_chain(boundary, candidate, label=label)
        _validate_owned_tree_for_removal(candidate, label=label)
    except PackageValidationError as exc:
        raise PackageValidationError(f"Refusing to clean unsafe {label}: {candidate}") from exc
    return True


def _remove_owned_directory(path: Path, *, boundary: Path, label: str) -> None:
    if not _validate_owned_directory_for_removal(path, boundary=boundary, label=label):
        return
    if os.name != "nt" and not shutil.rmtree.avoids_symlink_attacks:
        raise PackageValidationError(
            "This platform cannot remove generated directories without symlink-attack resistance"
        )
    shutil.rmtree(_absolute_path(path))


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)


def _reject_stale_package_transactions(dist: Path) -> None:
    try:
        entries = list(os.scandir(dist))
    except OSError as exc:
        raise PackageValidationError(
            f"Could not inspect distribution transaction state: {exc}"
        ) from exc
    stale = sorted(
        entry.name
        for entry in entries
        if any(entry.name.startswith(prefix) for prefix in _STALE_TRANSACTION_PREFIXES)
    )
    if stale:
        raise PackageValidationError(
            "Stale package transaction state requires manual inspection before retry: "
            + ", ".join(stale)
        )


def _publish_staged_directory(stage: Path, destination: Path) -> None:
    parent = destination.parent
    _require_real_directory(parent, label="Distribution directory")
    backup: Path | None = None
    if destination.exists() or destination.is_symlink():
        _require_real_directory(destination, label="Existing package evidence directory")
        backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=parent))
        backup.rmdir()
        os.replace(destination, backup)
        _fsync_directory(parent)
    try:
        _fsync_directory(stage)
        os.replace(stage, destination)
        _fsync_directory(parent)
    except BaseException:
        if backup is not None:
            os.replace(backup, destination)
            _fsync_directory(parent)
        raise
    if backup is not None:
        try:
            _remove_owned_directory(
                backup,
                boundary=parent,
                label="superseded package evidence directory",
            )
            _fsync_directory(parent)
        except BaseException as cleanup_error:
            displaced = Path(tempfile.mkdtemp(prefix=f".{destination.name}.failed-", dir=parent))
            displaced.rmdir()
            os.replace(destination, displaced)
            _fsync_directory(parent)
            os.replace(backup, destination)
            _fsync_directory(parent)
            try:
                _remove_owned_directory(
                    displaced,
                    boundary=parent,
                    label="failed new package evidence directory",
                )
                _fsync_directory(parent)
            except BaseException:
                pass
            raise PackageValidationError(
                "Could not retire the previous package evidence; publication was rolled back"
            ) from cleanup_error


def _finalize_package(bundle_root: Path, *, enforce_size_gate: bool) -> Path:
    bundle_root = _absolute_path(bundle_root)
    expected_bundle = _absolute_path(_bundle_root())
    if bundle_root != expected_bundle:
        raise PackageValidationError(
            f"Desktop bundle must use the fixed build path {expected_bundle}: {bundle_root}"
        )
    _require_real_directory_chain(ROOT, bundle_root, label="Desktop one-folder bundle")
    inventory_before, package_identity = _inventory_bundle(bundle_root)
    one_folder_bytes = int(inventory_before["one_folder_bytes"])
    _check_size_gate(
        "one-folder",
        one_folder_bytes,
        ONE_FOLDER_LIMIT_BYTES,
        enforced=enforce_size_gate,
    )
    dist = _prepare_dist_directory()
    stage = Path(tempfile.mkdtemp(prefix=f".{PACKAGE_DIRECTORY_NAME}.stage-", dir=dist))
    published = False
    try:
        system_name = platform.system()
        provenance = _source_provenance(system_name)
        _validate_source_record(provenance)
        _verify_checkout_bound_provenance(provenance)
        recorded_platform = dict(provenance["platform"])
        archive_name = _archive_name(system_name, str(recorded_platform["machine"]))
        archive_path = stage / archive_name
        _write_deterministic_archive(bundle_root, inventory_before, archive_path)
        inventory_after, identity_after = _inventory_bundle(bundle_root)
        if inventory_after != inventory_before or identity_after != package_identity:
            raise PackageValidationError("Desktop bundle changed while the archive was created")
        _verify_archive(archive_path, inventory_before)
        archive_metadata = archive_path.lstat()
        archive_sha256, archive_size = _hash_regular_file(
            archive_path, expected_size=archive_metadata.st_size
        )
        _check_size_gate(
            "compressed archive",
            archive_size,
            ARCHIVE_LIMIT_BYTES,
            enforced=enforce_size_gate,
        )
        evidence = _evidence_payload(
            inventory=inventory_before,
            package_identity=package_identity,
            archive_name=archive_name,
            archive_size=archive_size,
            archive_sha256=archive_sha256,
            provenance=provenance,
            size_gate_enforced=enforce_size_gate,
        )
        _write_bytes(stage / EVIDENCE_NAME, _canonical_json_bytes(evidence))
        _verify_package_unlocked(
            bundle_root,
            stage,
            require_size_gates=enforce_size_gate,
            _allow_staging_package=True,
        )
        destination = dist / PACKAGE_DIRECTORY_NAME
        _publish_staged_directory(stage, destination)
        published = True
        return destination
    finally:
        if not published and (stage.exists() or stage.is_symlink()):
            _remove_owned_directory(
                stage,
                boundary=dist,
                label="failed package staging directory",
            )


def _capture_marker(bundle_root: Path) -> tuple[bytes, int] | None:
    marker = bundle_root / UNSIGNED_MARKER_NAME
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return None
    _assert_regular_metadata(marker, metadata)
    if metadata.st_size > 4096:
        raise PackageValidationError("Existing unsigned marker is unexpectedly large")
    with _open_regular_file(marker, expected_size=metadata.st_size) as handle:
        return handle.read(), stat.S_IMODE(metadata.st_mode)


def _atomic_replace_marker(bundle_root: Path, payload: bytes, *, mode: int = 0o644) -> None:
    _require_real_directory(bundle_root, label="Desktop one-folder bundle")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{UNSIGNED_MARKER_NAME}.", dir=bundle_root
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        destination = bundle_root / UNSIGNED_MARKER_NAME
        if destination.exists() or destination.is_symlink():
            _assert_regular_metadata(destination, destination.lstat())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _restore_marker(bundle_root: Path, previous: tuple[bytes, int] | None) -> None:
    marker = bundle_root / UNSIGNED_MARKER_NAME
    if previous is None:
        try:
            metadata = marker.lstat()
        except FileNotFoundError:
            return
        _assert_regular_metadata(marker, metadata)
        marker.unlink()
        return
    payload, mode = previous
    _atomic_replace_marker(bundle_root, payload, mode=mode)


def _verify_panda_assets() -> object:
    source_path = str(ROOT / "src")
    if source_path not in sys.path:
        sys.path.insert(0, source_path)
    from mclab.application.asset_readiness import classify_panda_asset_failure
    from mclab.application.assets import verify_assets

    try:
        verification = verify_assets(root=ROOT)
    except ValueError as exc:
        readiness = classify_panda_asset_failure(ROOT, exc)
        if readiness.code == "missing_asset":
            repair = "Run `python -m mclab assets install` before packaging."
        else:
            repair = (
                "For an invalid physical tree, run "
                "`python -m mclab assets install --force`; inspect unsafe links or reparse "
                "points manually."
            )
        raise RuntimeError(
            f"Desktop build blocked: Panda runtime asset verification failed: {exc}. {repair}"
        ) from exc
    print(
        "Panda build input verified: "
        f"{verification.file_count} files, {verification.total_bytes} bytes."
    )
    return verification


def _require_safe_distribution_directory(*, action: str) -> None:
    repository = _absolute_path(ROOT)
    _require_real_directory(repository, label="Repository root")
    dist = repository / "dist"
    try:
        dist.lstat()
    except FileNotFoundError:
        return
    try:
        _require_real_directory_chain(repository, dist, label="Distribution directory")
    except PackageValidationError as exc:
        raise PackageValidationError(
            f"Refusing to {action} through an unsafe distribution directory: {dist}"
        ) from exc


def _clean_build_outputs() -> None:
    repository = _absolute_path(ROOT)
    _require_safe_distribution_directory(action="clean generated outputs")
    targets = (
        (ROOT / "build", "PyInstaller build directory"),
        (_bundle_root(), "desktop one-folder bundle"),
        (_package_root(), "package evidence directory"),
    )
    present = [
        (path, label)
        for path, label in targets
        if _validate_owned_directory_for_removal(path, boundary=repository, label=label)
    ]
    for path, label in present:
        _remove_owned_directory(path, boundary=repository, label=label)


def _retire_pyinstaller_work_tree() -> None:
    """Retire the owned PyInstaller work tree before bundle measurement.

    This defense-in-depth cleanup removes only the freshly generated,
    mount-aware ``build/mclab`` intermediate. The package verifier still
    rejects every multiply linked deliverable, including aliases outside this
    owned path.
    """

    work_tree = _absolute_path(ROOT / _PYINSTALLER_WORK_DIRECTORY)
    _remove_owned_directory(
        work_tree,
        boundary=_absolute_path(ROOT),
        label="PyInstaller work directory",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean",
        action="store_true",
        help="compatibility flag; generated build outputs are always safely rebuilt",
    )
    parser.add_argument(
        "--skip-size-gate",
        action="store_true",
        help="record but do not enforce the two development size gates",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify the existing bundle, archive, and evidence without modifying them",
    )
    parser.add_argument(
        "--offline-self-asserted",
        action="store_true",
        help=(
            "with --verify-only, check internal artifact consistency without authenticating "
            "source provenance; this mode is explicitly non-gating"
        ),
    )
    args = parser.parse_args()
    if args.verify_only:
        if args.clean or args.skip_size_gate:
            parser.error("--verify-only cannot be combined with --clean or --skip-size-gate")
        provenance_mode = (
            PROVENANCE_MODE_OFFLINE if args.offline_self_asserted else PROVENANCE_MODE_CHECKOUT
        )
        evidence = verify_package(provenance_mode=provenance_mode)
        identity = dict(evidence["package_identity"])["value"]
        if provenance_mode == PROVENANCE_MODE_OFFLINE:
            print(f"Self-asserted unsigned development package identity: {identity}")
        else:
            print(f"Verified checkout-bound unsigned development package identity: {identity}")
        return 0
    if args.offline_self_asserted:
        parser.error("--offline-self-asserted requires --verify-only")

    dist = _prepare_dist_directory()
    with _package_operation_lock(ROOT, dist):
        _verify_panda_assets()
        _require_safe_distribution_directory(action="build desktop package")
        _reject_stale_package_transactions(dist)
        # PyInstaller never receives --noconfirm and therefore never owns recursive
        # replacement of a pre-existing live path. Validate every owned tree first,
        # then remove all of them through the mount-aware path regardless of the
        # compatibility --clean spelling.
        _clean_build_outputs()
        subprocess.run(_PYINSTALLER_COMMAND, cwd=ROOT, check=True)
        bundle = _bundle_root()
        _require_real_directory(bundle, label="PyInstaller one-folder output")
        _retire_pyinstaller_work_tree()
        previous_marker = _capture_marker(bundle)
        try:
            _atomic_replace_marker(bundle, UNSIGNED_MARKER_BYTES)
            package = _finalize_package(bundle, enforce_size_gate=not args.skip_size_gate)
        except BaseException:
            try:
                _restore_marker(bundle, previous_marker)
            except BaseException as restore_error:
                raise PackageValidationError(
                    "Package finalization failed and the unsigned marker could not be restored"
                ) from restore_error
            raise
    print(f"Package archive and canonical evidence: {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
