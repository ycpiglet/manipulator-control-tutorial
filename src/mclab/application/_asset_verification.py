"""Strict physical-tree verification primitives for pinned runtime assets."""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DISPLAY_ISSUE_LIMIT = 5
_DISPLAY_TEXT_LIMIT = 320


@dataclass(frozen=True)
class AssetVerification:
    """Successful verification result for one canonical runtime tree."""

    target: Path
    file_count: int
    total_bytes: int


class AssetVerificationError(ValueError):
    """Raised when an asset tree does not match the tracked runtime contract."""

    def __init__(self, target: Path, issues: list[str] | tuple[str, ...]) -> None:
        self.target = target
        self.issues = tuple(sanitize_asset_diagnostic(issue) for issue in issues)
        visible = self.issues[:_DISPLAY_ISSUE_LIMIT]
        detail = "; ".join(visible)
        remaining = len(self.issues) - len(visible)
        if remaining:
            detail += f"; ... (+{remaining} more issues)"
        safe_target = sanitize_asset_diagnostic(os.fspath(target))
        super().__init__(f"Asset verification failed for {safe_target}: {detail}.")


class AssetSafetyError(AssetVerificationError):
    """Raised when links, reparse points, or special files make a tree unsafe."""


def sanitize_asset_diagnostic(value: object) -> str:
    """Escape control characters and bound one learner-facing diagnostic field."""

    escaped: list[str] = []
    for character in str(value):
        if character == "\n":
            escaped.append(r"\n")
        elif character == "\r":
            escaped.append(r"\r")
        elif character == "\t":
            escaped.append(r"\t")
        elif unicodedata.category(character).startswith("C"):
            codepoint = ord(character)
            if codepoint <= 0xFF:
                escaped.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                escaped.append(f"\\U{codepoint:08x}")
        else:
            escaped.append(character)
    text = "".join(escaped)
    if len(text) > _DISPLAY_TEXT_LIMIT:
        return text[: _DISPLAY_TEXT_LIMIT - 3] + "..."
    return text


def verify_runtime_tree(
    target: Path,
    *,
    manifest: tuple[tuple[str, int, str], ...],
    expected_directories: set[str],
    file_count: int,
    total_bytes: int,
) -> AssetVerification:
    """Verify one runtime tree against an already validated manifest."""

    expected = {relative: (size, digest) for relative, size, digest in manifest}
    if not _path_exists(target):
        raise AssetVerificationError(target, ["runtime tree is missing"])
    try:
        root_metadata = os.lstat(target)
    except OSError as exc:
        raise AssetSafetyError(target, [f"could not inspect runtime tree: {exc}"]) from exc
    if _is_link_or_reparse(root_metadata):
        raise AssetSafetyError(target, ["runtime tree is a link or reparse point"])
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise AssetSafetyError(target, ["runtime tree is not a physical directory"])

    actual_files: dict[str, tuple[Path, os.stat_result]] = {}
    actual_directories: set[str] = set()
    directory_states: dict[str, tuple[Path, os.stat_result]] = {"": (target, root_metadata)}
    verified_digests: dict[str, str] = {}
    safety_issues: list[str] = []
    scan_issues: list[str] = []
    stack: list[tuple[Path, str, os.stat_result]] = [(target, "", root_metadata)]

    while stack:
        directory, relative_parent, expected_directory_state = stack.pop()
        try:
            _assert_directory_state(
                directory,
                expected_directory_state,
                relative_parent,
                phase="before scanning",
            )
            with os.scandir(directory) as scanned:
                entries = sorted(scanned, key=lambda entry: entry.name)
            _assert_directory_state(
                directory,
                expected_directory_state,
                relative_parent,
                phase="after scanning",
            )
        except AssetSafetyError as exc:
            safety_issues.extend(exc.issues)
            continue
        except OSError as exc:
            safety_issues.append(f"could not scan {relative_parent or '.'}: {exc}")
            continue
        for entry in entries:
            relative = f"{relative_parent}/{entry.name}" if relative_parent else entry.name
            path = Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                safety_issues.append(f"could not inspect {relative}: {exc}")
                continue
            if _is_link_or_reparse(metadata):
                safety_issues.append(f"link or reparse point is not allowed: {relative}")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                actual_directories.add(relative)
                directory_states[relative] = (path, metadata)
                stack.append((path, relative, metadata))
            elif stat.S_ISREG(metadata.st_mode):
                actual_files[relative] = (path, metadata)
            else:
                safety_issues.append(f"special file is not allowed: {relative}")

    expected_paths = set(expected)
    actual_paths = set(actual_files)
    for relative in sorted(expected_paths - actual_paths):
        scan_issues.append(f"missing runtime file: {relative}")
    for relative in sorted(actual_paths - expected_paths):
        scan_issues.append(f"unknown runtime file: {relative}")
    for relative in sorted(actual_directories - expected_directories):
        scan_issues.append(f"unknown runtime directory: {relative}")
    for relative in sorted(expected_directories - actual_directories):
        scan_issues.append(f"missing runtime directory: {relative}")

    for relative in sorted(expected_paths & actual_paths):
        path, metadata = actual_files[relative]
        expected_size, expected_digest = expected[relative]
        if metadata.st_size != expected_size:
            scan_issues.append(
                f"size mismatch for {relative} (expected {expected_size}, got {metadata.st_size})"
            )
            continue
        try:
            parent_relative = PurePosixPath(relative).parent.as_posix()
            if parent_relative == ".":
                parent_relative = ""
            parent_path, parent_state = directory_states[parent_relative]
            _assert_directory_state(
                parent_path,
                parent_state,
                parent_relative,
                phase=f"before hashing {relative}",
            )
            actual_digest = _sha256_physical_file(path, metadata)
        except AssetSafetyError as exc:
            safety_issues.extend(exc.issues)
            continue
        verified_digests[relative] = actual_digest
        if actual_digest != expected_digest:
            scan_issues.append(
                f"SHA-256 mismatch for {relative} (expected {expected_digest}, got {actual_digest})"
            )

    for relative in sorted(expected_paths & actual_paths):
        path, metadata = actual_files[relative]
        try:
            first_digest = verified_digests.get(relative)
            if first_digest is None:
                _assert_file_state(path, metadata, relative, phase="at final verification")
                continue
            final_digest = _sha256_physical_file(path, metadata)
            if final_digest != first_digest:
                safety_issues.append(f"runtime file changed while hashing: {relative}")
        except AssetSafetyError as exc:
            safety_issues.extend(exc.issues)

    final_directories = sorted(
        directory_states.items(),
        key=lambda item: (item[0].count("/"), item[0]),
        reverse=True,
    )
    for relative, (path, metadata) in final_directories:
        try:
            _assert_directory_state(
                path,
                metadata,
                relative,
                phase="at final verification",
            )
        except AssetSafetyError as exc:
            safety_issues.extend(exc.issues)

    if safety_issues:
        raise AssetSafetyError(target, sorted(set(safety_issues + scan_issues)))
    if scan_issues:
        raise AssetVerificationError(target, sorted(set(scan_issues)))
    return AssetVerification(target=target, file_count=file_count, total_bytes=total_bytes)


def _assert_directory_state(
    path: Path,
    expected: os.stat_result,
    relative: str,
    *,
    phase: str,
) -> None:
    display = relative or "."
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(
            path,
            [f"runtime directory disappeared {phase}: {display}: {exc}"],
        ) from exc
    if _is_link_or_reparse(current) or not stat.S_ISDIR(current.st_mode):
        raise AssetSafetyError(
            path,
            [f"runtime directory changed type {phase}: {display}"],
        )
    if not _same_file_state(expected, current):
        raise AssetSafetyError(path, [f"runtime directory changed {phase}: {display}"])


def _assert_file_state(
    path: Path,
    expected: os.stat_result,
    relative: str,
    *,
    phase: str,
) -> None:
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(
            path,
            [f"runtime file disappeared {phase}: {relative}: {exc}"],
        ) from exc
    if _is_link_or_reparse(current) or not stat.S_ISREG(current.st_mode):
        raise AssetSafetyError(path, [f"runtime file changed type {phase}: {relative}"])
    if not _same_file_state(expected, current):
        raise AssetSafetyError(path, [f"runtime file changed {phase}: {relative}"])


def _sha256_physical_file(path: Path, initial: os.stat_result) -> str:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AssetSafetyError(
            path, [f"could not open physical runtime file: {path.name}: {exc}"]
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if _is_link_or_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise AssetSafetyError(path, [f"runtime file changed type while opening: {path.name}"])
        if not _same_file_state(initial, opened):
            raise AssetSafetyError(path, [f"runtime file changed while opening: {path.name}"])
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        final = os.fstat(descriptor)
        if not _same_file_state(opened, final):
            raise AssetSafetyError(path, [f"runtime file changed while hashing: {path.name}"])
    finally:
        os.close(descriptor)
    try:
        after = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(
            path, [f"runtime file disappeared after hashing: {path.name}: {exc}"]
        ) from exc
    if _is_link_or_reparse(after) or not _same_file_state(final, after):
        raise AssetSafetyError(path, [f"runtime file changed after hashing: {path.name}"])
    return digest.hexdigest()


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _same_path_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat.S_IFMT(left.st_mode),
        getattr(left, "st_file_attributes", 0) & _REPARSE_POINT,
    ) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
        getattr(right, "st_file_attributes", 0) & _REPARSE_POINT,
    )


def _validate_private_lock_file(
    descriptor: int,
    path: Path,
    *,
    phase: str,
) -> os.stat_result:
    """Require one current-user physical name for an opened lock file."""

    try:
        opened = os.fstat(descriptor)
        attached = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(path, [f"could not {phase} asset install lock: {exc}"]) from exc
    unsafe = not _is_private_lock_metadata(opened) or not _is_private_lock_metadata(attached)
    unsafe = unsafe or not _same_path_identity(opened, attached)
    if unsafe:
        raise AssetSafetyError(
            path,
            ["asset install lock is not a private current-user physical file"],
        )
    return opened


def _validate_private_lock_path(path: Path, *, phase: str) -> os.stat_result:
    """Reject an unsafe existing lock path before opening it."""

    try:
        attached = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(path, [f"could not {phase} asset install lock: {exc}"]) from exc
    if not _is_private_lock_metadata(attached):
        raise AssetSafetyError(
            path,
            ["asset install lock is not a private current-user physical file"],
        )
    return attached


def _is_private_lock_metadata(metadata: os.stat_result) -> bool:
    current_user = getattr(os, "geteuid", None)
    expected_user = current_user() if current_user is not None else None
    return (
        not _is_link_or_reparse(metadata)
        and stat.S_ISREG(metadata.st_mode)
        and metadata.st_nlink == 1
        and (expected_user is None or metadata.st_uid == expected_user)
    )


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _path_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AssetSafetyError(path, [f"could not inspect path: {exc}"]) from exc
    return True
