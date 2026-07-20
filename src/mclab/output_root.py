"""Pinned, root-relative filesystem access for MCLab saved outputs."""

from __future__ import annotations

import os
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from mclab.config import PROJECT_ROOT, default_outputs_root
from mclab.output_safety import (
    CleanupOperationError,
    CleanupSafetyError,
    FilesystemIdentity,
    _absolute_path,
    _is_mount_point,
    _lexists,
    _posix_directory_identity,
    _same_file_identity,
    _same_open_file_state,
    _stat_is_link_or_reparse,
    _verified_posix_directory_rename_noreplace,
)
from mclab.output_windows import (
    close_windows_handles as _close_windows_handles,
    exclusive_windows_operation_mutex as _exclusive_windows_operation_mutex,
    open_windows_directory as _open_windows_directory,
    pin_windows_lexical_chain as _pin_windows_lexical_chain,
    rename_windows_directory_noreplace as _rename_windows_directory_noreplace,
    windows_file_id as _windows_file_id,
)


class PinnedOutputRoot:
    """Keep one validated outputs directory anchored for a complete operation."""

    def __init__(
        self,
        root: Path,
        initial_stat: os.stat_result,
        *,
        descriptor: int = -1,
        windows_handles: tuple[int, ...] = (),
        windows_root_id: tuple[int, int] | None = None,
    ) -> None:
        self.root = root
        self._initial_stat = initial_stat
        self._descriptor = descriptor
        self._windows_handles = windows_handles
        self._windows_root_id = windows_root_id
        self._mutation_started = False
        self._directory_descriptors: dict[tuple[str, ...], int] = {}
        self._directory_handles: dict[tuple[str, ...], int] = {}
        self._directory_stats: dict[tuple[str, ...], os.stat_result] = {}
        self._directory_windows_ids: dict[tuple[str, ...], tuple[int, int]] = {}

    def __enter__(self) -> PinnedOutputRoot:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        for descriptor in self._directory_descriptors.values():
            os.close(descriptor)
        self._directory_descriptors.clear()
        if self._directory_handles:
            _close_windows_handles(tuple(self._directory_handles.values()))
            self._directory_handles.clear()
        self._directory_stats.clear()
        self._directory_windows_ids.clear()
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1
        if self._windows_handles:
            _close_windows_handles(self._windows_handles)
            self._windows_handles = ()

    def assert_current(self) -> None:
        """Fail if the configured path no longer names the pinned directory."""

        if os.name != "nt":
            try:
                descriptor, exists = _open_posix_lexical_directory(self.root)
            except CleanupSafetyError as exc:
                raise CleanupSafetyError(
                    "The configured outputs root changed during the operation"
                ) from exc
            if not exists:
                raise CleanupSafetyError("The configured outputs root changed during the operation")
            try:
                current = os.fstat(descriptor)
            finally:
                os.close(descriptor)
        else:
            try:
                current = os.lstat(self.root)
            except OSError as exc:
                raise CleanupSafetyError(f"The configured outputs root changed: {exc}") from exc
        if (
            _stat_is_link_or_reparse(current)
            or not stat.S_ISDIR(current.st_mode)
            or not _same_file_identity(self._initial_stat, current)
        ):
            raise CleanupSafetyError(
                "The configured outputs root changed during the operation; no result is valid."
            )
        if os.name == "nt" and self._windows_root_id is not None:
            handle = _open_windows_directory(self.root, delete_access=False)
            try:
                if _windows_file_id(handle) != self._windows_root_id:
                    raise CleanupSafetyError(
                        "The configured Windows outputs root changed during the operation."
                    )
            finally:
                _close_windows_handles((handle,))

    def begin_mutation(self) -> None:
        """Check attachment once, then keep recovery anchored to held descriptors."""

        if not self._mutation_started:
            self.assert_current()
            self._mutation_started = True

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Serialize cleanup and restore for this physical output root."""

        self.assert_current()
        if os.name == "nt":
            if self._windows_root_id is None:
                raise CleanupOperationError("The Windows output-root identity is unavailable")
            volume_id, file_id = self._windows_root_id
            name = f"Global\\MCLabOutputCleanup-{volume_id:016x}-{file_id:032x}"
            with _exclusive_windows_operation_mutex(name):
                yield
            return

        if self._descriptor < 0:
            raise CleanupOperationError("The outputs root descriptor is unavailable")
        import fcntl

        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CleanupOperationError(
                "Another saved-output cleanup or restore operation is active"
            ) from exc
        except OSError as exc:
            raise CleanupOperationError(f"Could not lock saved-output operations: {exc}") from exc
        try:
            yield
        finally:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)

    def operation_is_active(self) -> bool:
        """Probe the cross-process lock without retaining it."""

        try:
            with self.operation_lock():
                return False
        except CleanupOperationError:
            return True

    def assert_read_boundary(self) -> None:
        if not self._mutation_started:
            self.assert_current()

    def pin_directory(self, relative: tuple[str, ...], *, description: str) -> None:
        """Keep one rooted subdirectory open until the output-root lease closes."""

        parts = _validated_parts(relative)
        if not parts or parts in self._directory_stats:
            return
        self.validate_directory(parts, description=description)
        if os.name == "nt":
            handle = _open_windows_directory(self.display_path(parts), delete_access=False)
            self._directory_handles[parts] = handle
            self._directory_windows_ids[parts] = _windows_file_id(handle)
            self._directory_stats[parts] = self.lstat(parts)
            return
        with self._open_directory_fd(parts) as descriptor:
            retained = os.dup(descriptor)
            opened = os.fstat(retained)
        self._directory_descriptors[parts] = retained
        self._directory_stats[parts] = opened

    def assert_pinned_directories_current(self) -> None:
        """Verify that every pinned subdirectory still has its canonical rooted name."""

        for relative, initial in self._directory_stats.items():
            try:
                current = self.lstat(relative)
            except OSError as exc:
                raise CleanupSafetyError(
                    f"Pinned output directory changed at {'/'.join(relative)}: {exc}"
                ) from exc
            if (
                _stat_is_link_or_reparse(current)
                or not stat.S_ISDIR(current.st_mode)
                or not _same_file_identity(initial, current)
            ):
                raise CleanupSafetyError(
                    f"Pinned output directory changed at {'/'.join(relative)}"
                )
            if os.name == "nt":
                handle = _open_windows_directory(
                    self.display_path(relative),
                    delete_access=False,
                )
                try:
                    if _windows_file_id(handle) != self._directory_windows_ids[relative]:
                        raise CleanupSafetyError(
                            f"Pinned Windows output directory changed at {'/'.join(relative)}"
                        )
                finally:
                    _close_windows_handles((handle,))

    def assert_transaction_boundaries(self) -> None:
        self.assert_current()
        self.assert_pinned_directories_current()

    def display_path(self, relative: tuple[str, ...] = ()) -> Path:
        return self.root.joinpath(*_validated_parts(relative))

    def identity_payload(self, *, include_mtime: bool) -> dict[str, int | str]:
        if self._windows_root_id is not None:
            volume_id, file_id = self._windows_root_id
            payload: dict[str, int | str] = {
                "scheme": "windows-file-id",
                "volume_id": volume_id,
                "file_id": file_id,
            }
        else:
            payload = {
                "scheme": "posix-stat",
                "device": int(self._initial_stat.st_dev),
                "inode": int(self._initial_stat.st_ino),
                "file_type": int(stat.S_IFMT(self._initial_stat.st_mode)),
            }
        if include_mtime:
            payload["mtime_ns"] = int(self.lstat(()).st_mtime_ns)
            payload["mode"] = int(self.lstat(()).st_mode)
        return payload

    def directory_identity(self, relative: tuple[str, ...]) -> FilesystemIdentity:
        """Return one handle-derived physical directory identity."""

        parts = _validated_parts(relative)
        if os.name == "nt":
            handle = _open_windows_directory(self.display_path(parts), delete_access=False)
            try:
                volume_id, file_id = _windows_file_id(handle)
                return "windows-file-id", volume_id, file_id
            finally:
                _close_windows_handles((handle,))
        with self._open_directory_fd(parts) as descriptor:
            return _posix_directory_identity(os.fstat(descriptor))

    def list_names(self, relative: tuple[str, ...] = ()) -> tuple[str, ...]:
        """List one physical directory through the pinned boundary."""

        parts = _validated_parts(relative)
        if os.name == "nt":
            with self._pinned_windows_directory(parts):
                try:
                    names = tuple(entry.name for entry in os.scandir(self.display_path(parts)))
                except OSError as exc:
                    raise CleanupSafetyError(f"Could not inventory outputs safely: {exc}") from exc
        else:
            with self._open_directory_fd(parts) as descriptor:
                try:
                    names = tuple(entry.name for entry in os.scandir(descriptor))
                except OSError as exc:
                    raise CleanupSafetyError(f"Could not inventory outputs safely: {exc}") from exc
        self.assert_read_boundary()
        return names

    def lstat(self, relative: tuple[str, ...]) -> os.stat_result:
        parts = _validated_parts(relative)
        if not parts:
            return self._initial_stat
        if os.name == "nt":
            with self._pinned_windows_directory(parts[:-1]):
                result = os.lstat(self.display_path(parts))
        else:
            with self._open_directory_fd(parts[:-1]) as parent_fd:
                result = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        return result

    def lexists(self, relative: tuple[str, ...]) -> bool:
        try:
            self.lstat(relative)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise CleanupSafetyError(f"Could not inspect rooted output path: {exc}") from exc
        return True

    def validate_directory(self, relative: tuple[str, ...], *, description: str) -> None:
        parts = _validated_parts(relative)
        try:
            result = self.lstat(parts)
        except OSError as exc:
            raise CleanupSafetyError(f"Could not inspect {description}: {exc}") from exc
        if _stat_is_link_or_reparse(result):
            raise CleanupSafetyError(f"{description.capitalize()} is a link or reparse point")
        if not stat.S_ISDIR(result.st_mode):
            raise CleanupSafetyError(f"{description.capitalize()} is not a directory")
        if self.is_mount_point(parts):
            raise CleanupSafetyError(f"{description.capitalize()} is a mount point")

    def is_mount_point(self, relative: tuple[str, ...]) -> bool:
        """Check a directory mount boundary through its physical rooted parent."""

        parts = _validated_parts(relative)
        if os.name == "nt" or not parts:
            return _is_mount_point(self.display_path(parts))
        with self._open_directory_fd(parts[:-1]) as parent_fd:
            parent = os.fstat(parent_fd)
            child_fd = os.open(parts[-1], _directory_flags(), dir_fd=parent_fd)
            try:
                child = os.fstat(child_fd)
            finally:
                os.close(child_fd)
        return int(parent.st_dev) != int(child.st_dev) or (
            int(parent.st_dev),
            int(parent.st_ino),
        ) == (
            int(child.st_dev),
            int(child.st_ino),
        )

    def read_regular_file(
        self,
        relative: tuple[str, ...],
        *,
        description: str,
        max_bytes: int,
        allow_empty: bool = True,
    ) -> bytes:
        """Read a bounded regular file relative to a pinned physical parent."""

        parts = _validated_parts(relative)
        if not parts:
            raise CleanupSafetyError(f"{description} must name a file")
        with self.open_regular_file(
            parts,
            description=description,
            max_bytes=max_bytes,
            allow_empty=allow_empty,
        ) as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise CleanupSafetyError(f"{description} exceeded its safe size while read")
        self.assert_read_boundary()
        return data

    @contextmanager
    def open_regular_file(
        self,
        relative: tuple[str, ...],
        *,
        description: str,
        max_bytes: int,
        allow_empty: bool = True,
    ) -> Iterator[BinaryIO]:
        """Yield one stable regular file while its rooted parent stays pinned."""

        parts = _validated_parts(relative)
        if not parts:
            raise CleanupSafetyError(f"{description} must name a file")
        descriptor = -1
        try:
            if os.name == "nt":
                with self._pinned_windows_directory(parts[:-1]):
                    path_stat = os.lstat(self.display_path(parts))
                    descriptor = os.open(self.display_path(parts), _read_flags())
                    with _validated_stream(
                        descriptor,
                        path_stat=path_stat,
                        description=description,
                        max_bytes=max_bytes,
                        allow_empty=allow_empty,
                    ) as stream:
                        descriptor = -1
                        yield stream
            else:
                with self._open_directory_fd(parts[:-1]) as parent_fd:
                    path_stat = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
                    descriptor = os.open(parts[-1], _read_flags(), dir_fd=parent_fd)
                    with _validated_stream(
                        descriptor,
                        path_stat=path_stat,
                        description=description,
                        max_bytes=max_bytes,
                        allow_empty=allow_empty,
                    ) as stream:
                        descriptor = -1
                        yield stream
        except CleanupSafetyError:
            raise
        except OSError as exc:
            raise CleanupSafetyError(f"{description} is missing or unreadable: {exc}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        self.assert_read_boundary()

    def tree_size(self, relative: tuple[str, ...], *, max_entries: int) -> int:
        """Return a bounded physical tree size without recursive Python calls."""

        start = _validated_parts(relative)
        self.validate_directory(start, description="saved run")
        total = 0
        count = 0
        stack = [start]
        before: dict[tuple[str, ...], os.stat_result] = {}
        while stack:
            directory = stack.pop()
            initial = self.lstat(directory)
            before[directory] = initial
            for name in self.list_names(directory):
                count += 1
                if count > max_entries:
                    raise CleanupSafetyError(
                        f"Saved run contains more than {max_entries} entries"
                    )
                child = (*directory, name)
                child_stat = self.lstat(child)
                if _stat_is_link_or_reparse(child_stat):
                    raise CleanupSafetyError(
                        f"Saved-run contents include a link or reparse point: {name}"
                    )
                if stat.S_ISREG(child_stat.st_mode):
                    total += int(child_stat.st_size)
                elif stat.S_ISDIR(child_stat.st_mode):
                    if self.is_mount_point(child):
                        raise CleanupSafetyError("Saved-run contents include a mount point")
                    stack.append(child)
                else:
                    raise CleanupSafetyError(
                        f"Saved-run contents include a special filesystem entry: {name}"
                    )
        for directory, initial in before.items():
            final = self.lstat(directory)
            if _stat_is_link_or_reparse(final) or not _same_open_file_state(initial, final):
                raise CleanupSafetyError("Saved-run contents changed while sizing")
        self.assert_read_boundary()
        return total

    def mkdir(self, relative: tuple[str, ...], *, mode: int) -> None:
        parts = _validated_parts(relative)
        if not parts:
            raise CleanupSafetyError("The outputs root cannot be created as a child of itself")
        self.begin_mutation()
        if os.name == "nt":
            with self._pinned_windows_directory(parts[:-1]):
                os.mkdir(self.display_path(parts), mode=mode)
        else:
            with self._open_directory_fd(parts[:-1]) as parent_fd:
                os.mkdir(parts[-1], mode=mode, dir_fd=parent_fd)
                os.fsync(parent_fd)

    def rmdir(self, relative: tuple[str, ...]) -> None:
        parts = _validated_parts(relative)
        if not parts:
            raise CleanupSafetyError("The outputs root cannot be removed")
        self.begin_mutation()
        if os.name == "nt":
            with self._pinned_windows_directory(parts[:-1]):
                os.rmdir(self.display_path(parts))
        else:
            with self._open_directory_fd(parts[:-1]) as parent_fd:
                os.rmdir(parts[-1], dir_fd=parent_fd)
                os.fsync(parent_fd)

    def replace_regular_file(
        self,
        relative: tuple[str, ...],
        data: bytes,
        *,
        mode: int = 0o600,
    ) -> None:
        """Durably replace one rooted metadata file using a unique sibling."""

        parts = _validated_parts(relative)
        if not parts:
            raise CleanupSafetyError("A rooted metadata write must name a file")
        temporary_name = f".{parts[-1]}.{uuid.uuid4().hex}.tmp"
        temporary = (*parts[:-1], temporary_name)
        self.begin_mutation()
        descriptor = -1
        try:
            if os.name == "nt":
                with self._pinned_windows_directory(parts[:-1]):
                    descriptor = os.open(
                        self.display_path(temporary),
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(getattr(os, "O_BINARY", 0)),
                        mode,
                    )
                    owned_descriptor = descriptor
                    descriptor = -1
                    _write_and_sync(owned_descriptor, data)
                    os.replace(self.display_path(temporary), self.display_path(parts))
            else:
                with self._open_directory_fd(parts[:-1]) as parent_fd:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(
                        getattr(os, "O_CLOEXEC", 0)
                    )
                    descriptor = os.open(temporary_name, flags, mode, dir_fd=parent_fd)
                    owned_descriptor = descriptor
                    descriptor = -1
                    _write_and_sync(owned_descriptor, data)
                    os.replace(
                        temporary_name,
                        parts[-1],
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    os.fsync(parent_fd)
        except OSError as exc:
            try:
                if self.lexists(temporary):
                    if os.name == "nt":
                        os.unlink(self.display_path(temporary))
                    else:
                        with self._open_directory_fd(parts[:-1]) as parent_fd:
                            os.unlink(temporary_name, dir_fd=parent_fd)
            except (CleanupSafetyError, OSError):
                pass
            raise CleanupOperationError(f"Could not write cleanup receipt: {exc}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def rename_noreplace(
        self,
        source: tuple[str, ...],
        destination: tuple[str, ...],
        *,
        expected_source_identity: FilesystemIdentity,
    ) -> None:
        """Move a directory between pinned parents without replacing a destination."""

        source_parts = _validated_parts(source)
        destination_parts = _validated_parts(destination)
        if not source_parts or not destination_parts:
            raise CleanupSafetyError("A rooted rename cannot target the outputs root")
        self.begin_mutation()
        if os.name == "nt":
            if expected_source_identity[0] != "windows-file-id":
                raise CleanupSafetyError("Move source has an incompatible Windows identity")
            _rename_windows_directory_noreplace(
                self.display_path(source_parts),
                self.display_path(destination_parts),
                expected_source_id=(
                    expected_source_identity[1],
                    expected_source_identity[2],
                ),
            )
        else:
            if expected_source_identity[0] != "posix-stat":
                raise CleanupSafetyError("Move source has an incompatible POSIX identity")
            with self._open_directory_fd(source_parts[:-1]) as source_fd:
                with self._open_directory_fd(destination_parts[:-1]) as destination_fd:
                    _verified_posix_directory_rename_noreplace(
                        Path(source_parts[-1]),
                        Path(destination_parts[-1]),
                        source_parent_fd=source_fd,
                        destination_parent_fd=destination_fd,
                        expected_source_identity=expected_source_identity,
                    )

    @contextmanager
    def _open_directory_fd(self, relative: tuple[str, ...]) -> Iterator[int]:
        if self._descriptor < 0:
            raise CleanupOperationError("The outputs root descriptor is unavailable")
        pinned_prefix: tuple[str, ...] = ()
        for candidate in self._directory_descriptors:
            if len(candidate) > len(pinned_prefix) and relative[: len(candidate)] == candidate:
                pinned_prefix = candidate
        base_descriptor = (
            self._directory_descriptors[pinned_prefix]
            if pinned_prefix
            else self._descriptor
        )
        descriptor = os.dup(base_descriptor)
        try:
            for name in relative[len(pinned_prefix) :]:
                next_descriptor = os.open(name, _directory_flags(), dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
                opened = os.fstat(descriptor)
                if _stat_is_link_or_reparse(opened) or not stat.S_ISDIR(opened.st_mode):
                    raise CleanupSafetyError("A rooted path component became unsafe")
            yield descriptor
        finally:
            os.close(descriptor)

    @contextmanager
    def _pinned_windows_directory(self, relative: tuple[str, ...]) -> Iterator[None]:
        if os.name != "nt":
            yield
            return
        handle = _open_windows_directory(self.display_path(relative), delete_access=False)
        try:
            yield
        finally:
            _close_windows_handles((handle,))


@contextmanager
def pinned_output_root(
    output_root: str | Path,
    *,
    allowed_root: str | Path | None,
) -> Iterator[tuple[Path, bool, PinnedOutputRoot | None]]:
    """Validate and immediately pin the exact configured outputs root."""

    candidate = _absolute_path(output_root)
    configured = _absolute_path(allowed_root or default_outputs_root())
    if os.path.normcase(str(candidate)) != os.path.normcase(str(configured)):
        raise CleanupSafetyError(
            f"Cleanup is limited to the configured outputs root: {configured}"
        )
    _reject_link_components(candidate)
    _reject_protected_root(candidate)

    descriptor = -1
    windows_handles: tuple[int, ...] = ()
    windows_root_id: tuple[int, int] | None = None
    try:
        if os.name == "nt":
            windows_handles, root_exists = _pin_windows_lexical_chain(candidate)
            if not root_exists:
                _close_windows_handles(windows_handles)
                windows_handles = ()
                yield candidate, False, None
                return
            resolved = candidate.resolve(strict=True)
            initial = os.lstat(resolved)
            windows_root_id = _windows_file_id(windows_handles[-1])
        else:
            descriptor, root_exists = _open_posix_lexical_directory(candidate)
            if not root_exists:
                yield candidate, False, None
                return
            resolved = candidate
            initial = os.fstat(descriptor)
        if _stat_is_link_or_reparse(initial) or not stat.S_ISDIR(initial.st_mode):
            raise CleanupSafetyError("The configured outputs root is not a physical directory")
        if _is_mount_point(resolved):
            raise CleanupSafetyError("The configured outputs root must not be a mount point.")
        _reject_protected_root(resolved)
        pin = PinnedOutputRoot(
            resolved,
            initial,
            descriptor=descriptor,
            windows_handles=windows_handles,
            windows_root_id=windows_root_id,
        )
        descriptor = -1
        windows_handles = ()
        with pin:
            pin.assert_current()
            yield resolved, True, pin
            pin.assert_read_boundary()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if windows_handles:
            _close_windows_handles(windows_handles)


def _open_posix_lexical_directory(root: Path) -> tuple[int, bool]:
    """Open an absolute directory component-by-component without following links."""

    anchor = Path(root.anchor)
    descriptor = os.open(anchor, _directory_flags())
    try:
        for name in root.relative_to(anchor).parts:
            try:
                next_descriptor = os.open(name, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                os.close(descriptor)
                return -1, False
            except OSError as exc:
                raise CleanupSafetyError(
                    "The outputs root contains a link or reparse-point component, "
                    "or is not a directory"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, True
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _validated_parts(relative: tuple[str, ...]) -> tuple[str, ...]:
    parts = tuple(relative)
    if any(not part or part in {".", ".."} or Path(part).name != part for part in parts):
        raise CleanupSafetyError("A rooted output path contains an unsafe component")
    return parts


def _reject_link_components(path: Path) -> None:
    for component in [*reversed(path.parents), path]:
        if not _lexists(component):
            continue
        try:
            if _stat_is_link_or_reparse(os.lstat(component)):
                raise CleanupSafetyError(
                    "The outputs root contains a link or reparse-point component."
                )
        except CleanupSafetyError:
            raise
        except OSError as exc:
            raise CleanupSafetyError(f"Could not inspect outputs root component: {exc}") from exc


def _reject_protected_root(root: Path) -> None:
    anchor = Path(root.anchor)
    if root == anchor:
        raise CleanupSafetyError("Filesystem, drive, and share roots cannot be cleaned.")
    protected = (
        Path.home().resolve(strict=False),
        PROJECT_ROOT.resolve(strict=False),
        Path(tempfile.gettempdir()).resolve(strict=False),
    )
    for item in protected:
        if root == item or item.is_relative_to(root):
            raise CleanupSafetyError(
                f"Protected home, repository, workspace, or temporary roots cannot be cleaned: {root}"
            )


def _directory_flags() -> int:
    flags = os.O_RDONLY
    flags |= int(getattr(os, "O_DIRECTORY", 0))
    flags |= int(getattr(os, "O_CLOEXEC", 0))
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    return flags


def _read_flags() -> int:
    flags = os.O_RDONLY
    flags |= int(getattr(os, "O_BINARY", 0))
    flags |= int(getattr(os, "O_CLOEXEC", 0))
    flags |= int(getattr(os, "O_NOFOLLOW", 0))
    flags |= int(getattr(os, "O_NONBLOCK", 0))
    return flags


@contextmanager
def _validated_stream(
    descriptor: int,
    *,
    path_stat: os.stat_result,
    description: str,
    max_bytes: int,
    allow_empty: bool,
) -> Iterator[BinaryIO]:
    opened = os.fstat(descriptor)
    if (
        _stat_is_link_or_reparse(path_stat)
        or not stat.S_ISREG(path_stat.st_mode)
        or not _same_file_identity(path_stat, opened)
        or opened.st_size < 0
        or opened.st_size > max_bytes
        or (not allow_empty and opened.st_size == 0)
    ):
        raise CleanupSafetyError(f"{description} changed or has an unsafe type or size")
    with os.fdopen(descriptor, "rb", closefd=True) as stream:
        yield stream
        final = os.fstat(stream.fileno())
    if not _same_open_file_state(opened, final):
        raise CleanupSafetyError(f"{description} changed while read")


def _write_and_sync(descriptor: int, data: bytes) -> None:
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
