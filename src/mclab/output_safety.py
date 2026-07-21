"""Low-level filesystem guards shared by saved-run listing and cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator

MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_ROOT_ENTRIES = 10_000
MAX_RUN_TREE_ENTRIES = 100_000


class CleanupSafetyError(ValueError):
    """Reject an unsafe root, target, plan, token, or restore request."""


class CleanupOperationError(RuntimeError):
    """Report an I/O failure without claiming that cleanup succeeded."""


class CleanupBusyError(CleanupOperationError):
    """A fail-fast saved-output lease is already held by another operation."""


class CleanupMoveCommittedError(OSError):
    """Report that a rename committed but could not be safely reconciled."""


FilesystemIdentity = tuple[str, int, int]


def reconcile_directory_move_error(
    error: OSError,
    *,
    expected_identity: FilesystemIdentity,
    source_identity: Callable[[], FilesystemIdentity],
    destination_identity: Callable[[], FilesystemIdentity],
) -> OSError:
    """Classify an error escaping a rename boundary without losing a move."""

    if isinstance(error, CleanupMoveCommittedError):
        return error

    destination_state: FilesystemIdentity | None = None
    destination_uncertain = False
    try:
        destination_state = destination_identity()
    except FileNotFoundError:
        pass
    except (CleanupSafetyError, OSError):
        destination_uncertain = True
    if destination_state == expected_identity:
        return CleanupMoveCommittedError(
            f"Expected move committed but the rooted rename boundary reported an error: {error}"
        )

    source_state: FilesystemIdentity | None = None
    source_uncertain = False
    try:
        source_state = source_identity()
    except FileNotFoundError:
        pass
    except (CleanupSafetyError, OSError):
        source_uncertain = True
    if (
        source_state == expected_identity
        and destination_state is None
        and not destination_uncertain
    ):
        return error

    uncertainty = "identity inspection was inconclusive" if (
        source_uncertain or destination_uncertain
    ) else "the expected source identity was no longer at its original name"
    return CleanupMoveCommittedError(
        f"Rename outcome must be treated as committed because {uncertainty}: {error}"
    )


def saved_run_size_bytes(path: str | Path) -> int:
    """Return a bounded physical-tree size without following links or special entries."""

    target = _absolute_path(path)
    _validate_physical_directory(target, description="saved run")
    try:
        initial_stat = os.lstat(target)
        total, _count = _physical_tree_size(target, count=0)
        final_stat = os.lstat(target)
    except CleanupSafetyError:
        raise
    except RecursionError as exc:
        raise CleanupSafetyError("Saved run is nested too deeply to size safely") from exc
    except OSError as exc:
        raise CleanupSafetyError(f"Could not size saved run safely: {exc}") from exc
    if _stat_is_link_or_reparse(final_stat) or not _same_open_file_state(
        initial_stat,
        final_stat,
    ):
        raise CleanupSafetyError("Saved run changed while it was sized")
    return total


@contextmanager
def open_bounded_regular_file(
    path: str | Path,
    *,
    description: str,
    max_bytes: int,
    allow_empty: bool = True,
) -> Iterator[BinaryIO]:
    """Open one stable regular file without following a final link or blocking on a FIFO."""

    target = _absolute_path(path)
    try:
        path_stat = os.lstat(target)
    except OSError as exc:
        raise CleanupSafetyError(f"{description} is missing or unreadable: {exc}") from exc
    if _stat_is_link_or_reparse(path_stat) or not stat.S_ISREG(path_stat.st_mode):
        raise CleanupSafetyError(f"{description} must be a regular, non-link file")
    if path_stat.st_size < 0 or path_stat.st_size > max_bytes:
        raise CleanupSafetyError(f"{description} has an unsafe size")
    if not allow_empty and path_stat.st_size == 0:
        raise CleanupSafetyError(f"{description} has an unsafe size")

    flags = os.O_RDONLY
    flags |= int(getattr(os, "O_BINARY", 0))
    flags |= int(getattr(os, "O_CLOEXEC", 0))
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    flags |= int(getattr(os, "O_NONBLOCK", 0))
    descriptor = -1
    try:
        descriptor = os.open(target, flags)
        opened_stat = os.fstat(descriptor)
        if (
            _stat_is_link_or_reparse(opened_stat)
            or not stat.S_ISREG(opened_stat.st_mode)
            or not _same_file_identity(path_stat, opened_stat)
            or opened_stat.st_size < 0
            or opened_stat.st_size > max_bytes
            or (not allow_empty and opened_stat.st_size == 0)
        ):
            raise CleanupSafetyError(
                f"{description} changed or became unsafe while it was opened"
            )
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            yield stream
            final_stat = os.fstat(stream.fileno())
            if not _same_open_file_state(opened_stat, final_stat):
                raise CleanupSafetyError(f"{description} changed while it was read")
    except CleanupSafetyError:
        raise
    except OSError as exc:
        raise CleanupSafetyError(f"{description} is unreadable: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_physical_directory(path: Path, *, description: str) -> None:
    try:
        stat_result = os.lstat(path)
    except OSError as exc:
        raise CleanupSafetyError(f"Could not inspect {description}: {exc}") from exc
    if _stat_is_link_or_reparse(stat_result):
        raise CleanupSafetyError(f"{description.capitalize()} is a link or reparse point")
    if not stat.S_ISDIR(stat_result.st_mode):
        raise CleanupSafetyError(f"{description.capitalize()} is not a directory")
    if _is_mount_point(path):
        raise CleanupSafetyError(f"{description.capitalize()} is a mount point")


def _stat_is_link_or_reparse(stat_result: os.stat_result) -> bool:
    if stat.S_ISLNK(stat_result.st_mode):
        return True
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse_flag)


def _is_mount_point(path: Path) -> bool:
    """Return mount status without relying on unsupported WindowsPath APIs."""

    try:
        return path.is_mount()
    except NotImplementedError:
        # Python 3.10/3.11 may not implement WindowsPath.is_mount(). Windows
        # junctions and volume mount points are still rejected as reparse points.
        return False
    except OSError as exc:
        raise CleanupSafetyError(f"Could not inspect mount status for {path}: {exc}") from exc


def _read_json_mapping(
    path: Path,
    *,
    description: str,
    allow_empty: bool = False,
) -> tuple[dict[str, Any], str]:
    try:
        with open_bounded_regular_file(
            path,
            description=description,
            max_bytes=MAX_METADATA_BYTES,
            allow_empty=False,
        ) as stream:
            data = stream.read(MAX_METADATA_BYTES + 1)
        if len(data) > MAX_METADATA_BYTES:
            raise CleanupSafetyError(f"{description} exceeded its safe size while read")
        payload = json.loads(data.decode("utf-8"))
    except CleanupSafetyError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise CleanupSafetyError(f"{description} is malformed or unreadable: {exc}") from exc
    if not isinstance(payload, dict) or (not payload and not allow_empty):
        qualifier = "a JSON object" if allow_empty else "a non-empty JSON object"
        raise CleanupSafetyError(f"{description} must contain {qualifier}")
    return payload, hashlib.sha256(data).hexdigest()


def _physical_tree_size(path: Path, *, count: int) -> tuple[int, int]:
    """Size a stable physical directory tree without following nested aliases."""

    try:
        before = os.lstat(path)
    except OSError as exc:
        raise CleanupSafetyError(f"Could not inspect saved-run contents: {exc}") from exc
    if _stat_is_link_or_reparse(before) or not stat.S_ISDIR(before.st_mode):
        raise CleanupSafetyError("Saved-run contents include a link or special directory")
    if _is_mount_point(path):
        raise CleanupSafetyError("Saved-run contents include a mount point")

    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                count += 1
                if count > MAX_RUN_TREE_ENTRIES:
                    raise CleanupSafetyError(
                        f"Saved run contains more than {MAX_RUN_TREE_ENTRIES} entries"
                    )
                entry_stat = entry.stat(follow_symlinks=False)
                if _stat_is_link_or_reparse(entry_stat):
                    raise CleanupSafetyError(
                        f"Saved-run contents include a link or reparse point: {entry.name}"
                    )
                entry_path = Path(entry.path)
                if stat.S_ISREG(entry_stat.st_mode):
                    total += int(entry_stat.st_size)
                elif stat.S_ISDIR(entry_stat.st_mode):
                    child_total, count = _physical_tree_size(entry_path, count=count)
                    total += child_total
                else:
                    raise CleanupSafetyError(
                        f"Saved-run contents include a special filesystem entry: {entry.name}"
                    )
    except CleanupSafetyError:
        raise
    except OSError as exc:
        raise CleanupSafetyError(f"Could not size saved-run contents safely: {exc}") from exc

    try:
        after = os.lstat(path)
    except OSError as exc:
        raise CleanupSafetyError(f"Saved-run contents changed while sizing: {exc}") from exc
    if _stat_is_link_or_reparse(after) or not _same_open_file_state(before, after):
        raise CleanupSafetyError("Saved-run contents changed while sizing")
    return total, count


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        int(first.st_dev),
        int(first.st_ino),
        int(first.st_mode),
    ) == (
        int(second.st_dev),
        int(second.st_ino),
        int(second.st_mode),
    )


def _same_open_file_state(first: os.stat_result, second: os.stat_result) -> bool:
    return _same_file_identity(first, second) and (
        int(first.st_size),
        int(first.st_mtime_ns),
    ) == (
        int(second.st_size),
        int(second.st_mtime_ns),
    )


def _parse_aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CleanupSafetyError("manifest finished_at is missing or invalid")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CleanupSafetyError("manifest finished_at is missing or invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CleanupSafetyError("manifest finished_at must include a timezone")
    return parsed


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _absolute_path(path: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _rename_directory_noreplace(
    source: Path,
    destination: Path,
    *,
    source_dir_fd: int | None = None,
    destination_dir_fd: int | None = None,
) -> None:
    """Rename a directory atomically while refusing to replace any destination."""

    if os.name == "nt":
        if source_dir_fd is not None or destination_dir_fd is not None:
            raise CleanupOperationError("Windows no-replace rename does not accept POSIX dir_fds")
        # MoveFileEx without MOVEFILE_REPLACE_EXISTING is the behavior exposed
        # by os.rename on Windows.
        os.rename(source, destination)
        return

    import ctypes

    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    source_at = -100 if source_dir_fd is None else source_dir_fd
    destination_at = -100 if destination_dir_fd is None else destination_dir_fd
    if sys.platform.startswith("linux"):
        try:
            rename = library.renameat2
        except AttributeError as exc:
            raise CleanupOperationError(
                "Atomic no-replace rename is unavailable on this Linux runtime"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(source_at, source_bytes, destination_at, destination_bytes, 1)
    elif sys.platform == "darwin":
        try:
            rename = library.renameatx_np
        except AttributeError as exc:
            raise CleanupOperationError(
                "Atomic no-replace rename is unavailable on this macOS runtime"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        # RENAME_EXCL refuses replacement; RENAME_NOFOLLOW_ANY rejects a
        # symlink in any component on supported macOS volumes.
        result = rename(
            source_at,
            source_bytes,
            destination_at,
            destination_bytes,
            0x00000004 | 0x00000010,
        )
    else:
        raise CleanupOperationError(
            f"Atomic no-replace rename is unsupported on {sys.platform}"
        )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(destination))


def _posix_directory_identity(stat_result: os.stat_result) -> FilesystemIdentity:
    return "posix-stat", int(stat_result.st_dev), int(stat_result.st_ino)


def _verified_posix_directory_rename_noreplace(
    source: Path,
    destination: Path,
    *,
    source_parent_fd: int,
    destination_parent_fd: int,
    expected_source_identity: FilesystemIdentity,
) -> None:
    """Rename the exact opened directory, reversing a raced replacement."""

    flags = os.O_RDONLY
    flags |= int(getattr(os, "O_DIRECTORY", 0))
    flags |= int(getattr(os, "O_CLOEXEC", 0))
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    source_descriptor = os.open(source, flags, dir_fd=source_parent_fd)
    try:
        opened = os.fstat(source_descriptor)
        if (
            _stat_is_link_or_reparse(opened)
            or not stat.S_ISDIR(opened.st_mode)
            or _posix_directory_identity(opened) != expected_source_identity
        ):
            raise CleanupSafetyError("Move source changed before the atomic rename")

        rename_error: OSError | None = None
        try:
            _rename_directory_noreplace(
                source,
                destination,
                source_dir_fd=source_parent_fd,
                destination_dir_fd=destination_parent_fd,
            )
        except OSError as exc:
            rename_error = exc

        try:
            source_present = _relative_entry_exists(source, parent_fd=source_parent_fd)
            destination_present = _relative_entry_exists(
                destination,
                parent_fd=destination_parent_fd,
            )
        except OSError as exc:
            raise CleanupMoveCommittedError(
                f"Rename outcome could not be reconciled after the syscall: {exc}"
            ) from exc
        if not destination_present:
            if rename_error is not None:
                raise rename_error
            raise CleanupOperationError("Atomic rename returned without a destination")

        try:
            destination_descriptor = os.open(
                destination,
                flags,
                dir_fd=destination_parent_fd,
            )
            try:
                moved_identity = _posix_directory_identity(os.fstat(destination_descriptor))
            finally:
                os.close(destination_descriptor)
        except OSError as exc:
            raise CleanupMoveCommittedError(
                f"Destination identity could not be reconciled after the rename: {exc}"
            ) from exc
        if moved_identity == expected_source_identity:
            try:
                _sync_directory_pair(source_parent_fd, destination_parent_fd)
            except OSError as exc:
                raise CleanupMoveCommittedError(
                    f"Expected move committed but directory sync failed: {exc}"
                ) from exc
            if rename_error is not None:
                raise CleanupMoveCommittedError(
                    f"Expected move committed but rename reported an error: {rename_error}"
                ) from rename_error
            if source_present:
                raise CleanupMoveCommittedError(
                    "Expected move committed but the source name was recreated"
                )
            return

        if moved_identity != expected_source_identity:
            if rename_error is not None and source_present:
                raise CleanupMoveCommittedError(
                    "An unexpected destination and a recreated source remained after "
                    f"rename reported an error: {rename_error}"
                ) from rename_error
            if source_present:
                raise CleanupMoveCommittedError(
                    "Move source changed during rename; both names were preserved"
                )
            try:
                _rename_directory_noreplace(
                    destination,
                    source,
                    source_dir_fd=destination_parent_fd,
                    destination_dir_fd=source_parent_fd,
                )
            except OSError as exc:
                raise CleanupMoveCommittedError(
                    f"Move source changed during rename and reversal failed: {exc}"
                ) from exc
            try:
                _sync_directory_pair(source_parent_fd, destination_parent_fd)
            except OSError as exc:
                raise CleanupOperationError(
                    f"Unexpected move source was returned but directory sync failed: {exc}"
                ) from exc
            raise CleanupSafetyError(
                "Move source changed during rename; the unexpected directory was returned"
            )
    finally:
        body_exception_active = sys.exc_info()[0] is not None
        try:
            os.close(source_descriptor)
        except OSError as exc:
            # Preserve any more precise reconciliation or reversal exception.
            # If the body otherwise returned, the expected move committed and
            # the caller must still record the entry as staged.
            if not body_exception_active:
                raise CleanupMoveCommittedError(
                    f"Expected move committed but the source handle did not close cleanly: {exc}"
                ) from exc


def _relative_entry_exists(path: Path, *, parent_fd: int) -> bool:
    try:
        os.stat(path, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _sync_directory_pair(first_fd: int, second_fd: int) -> None:
    os.fsync(first_fd)
    if _posix_directory_identity(os.fstat(first_fd)) != _posix_directory_identity(
        os.fstat(second_fd)
    ):
        os.fsync(second_fd)
