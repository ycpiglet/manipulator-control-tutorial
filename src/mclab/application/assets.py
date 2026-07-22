"""Install and verify the pinned third-party Panda runtime assets."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mclab.application._atomic_publish import rename_directory_no_replace
from mclab.application._asset_verification import (
    AssetSafetyError,
    AssetVerification,
    AssetVerificationError,
    _is_link_or_reparse,
    _same_path_identity,
    _validate_private_lock_file,
    _validate_private_lock_path,
    sanitize_asset_diagnostic,
    verify_runtime_tree as _verify_runtime_tree_impl,
)
from mclab.application.panda_runtime_manifest import (
    PANDA_RUNTIME_ARCHIVE_SHA256,
    PANDA_RUNTIME_FILE_COUNT,
    PANDA_RUNTIME_MANIFEST,
    PANDA_RUNTIME_MANIFEST_SCHEMA,
    PANDA_RUNTIME_MENAGERIE_COMMIT,
    PANDA_RUNTIME_TOTAL_BYTES,
)
from mclab.config import PROJECT_ROOT


# Keep these public names stable for callers that already import or patch them.
MENAGERIE_COMMIT = PANDA_RUNTIME_MENAGERIE_COMMIT
MENAGERIE_ARCHIVE_URL = (
    f"https://github.com/google-deepmind/mujoco_menagerie/archive/{MENAGERIE_COMMIT}.tar.gz"
)
MENAGERIE_ARCHIVE_SHA256 = PANDA_RUNTIME_ARCHIVE_SHA256
PANDA_PREFIX = f"mujoco_menagerie-{MENAGERIE_COMMIT}/franka_emika_panda/"

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_LOCK_RETRY_SECONDS = 0.05


class _AssetRollbackError(RuntimeError):
    """Internal signal that transaction recovery data must be preserved."""


@dataclass(frozen=True)
class _ProjectPathLease:
    """Physical project-to-asset-parent identities held during installation."""

    entries: tuple[tuple[Path, os.stat_result], ...]


def verify_assets(root: str | Path = PROJECT_ROOT) -> AssetVerification:
    """Read and strictly verify the installed Panda runtime tree."""

    project_root = _absolute_path(root)
    target = _asset_target(project_root)
    _check_project_path(project_root, create_parents=False)
    if not _path_exists(target):
        result = _verify_runtime_tree(target)
        path_lease = _capture_project_path_lease(project_root)
        _assert_project_path_lease(path_lease)
        return result
    path_lease = _capture_project_path_lease(project_root)
    result = _verify_runtime_tree(target)
    _assert_project_path_lease(path_lease)
    return result


def install_assets(
    root: str | Path = PROJECT_ROOT,
    *,
    force: bool = False,
    archive_path: str | Path | None = None,
) -> Path:
    """Install only the canonical Panda runtime subset from the pinned archive.

    A valid existing tree is reused without network access. An invalid but
    physical tree requires ``force=True``; unsafe trees are never replaced.
    Publication uses same-filesystem renames and restores the previous tree if
    candidate publication or post-publication verification fails.
    """

    project_root = _absolute_path(root)
    with _exclusive_asset_install_lock(project_root):
        return _install_assets_locked(
            project_root,
            force=force,
            archive_path=archive_path,
        )


def _install_assets_locked(
    project_root: Path,
    *,
    force: bool,
    archive_path: str | Path | None,
) -> Path:
    """Install assets while the per-project cross-process lease is held."""

    target = _asset_target(project_root)
    _check_project_path(project_root, create_parents=True)
    path_lease = _capture_project_path_lease(project_root)

    target_present = _path_exists(target)
    previous_identity = (
        _require_owned_directory(target, expected=None, label="existing runtime tree")
        if target_present
        else None
    )
    if target_present:
        assert previous_identity is not None
        try:
            _verify_runtime_tree(target)
        except AssetSafetyError:
            raise
        except AssetVerificationError as exc:
            if not force:
                raise AssetVerificationError(
                    target,
                    ["rerun with --force to replace this physical tree", *exc.issues],
                ) from exc
        else:
            if not force:
                _assert_owned_path(target, previous_identity, label="verified runtime tree")
                _assert_project_path_lease(path_lease)
                return target
        _assert_owned_path(target, previous_identity, label="existing runtime tree")

    _assert_project_path_lease(path_lease)
    transaction = Path(tempfile.mkdtemp(prefix=".mclab-assets-", dir=os.fspath(target.parent)))
    transaction_identity = _require_owned_directory(
        transaction,
        expected=None,
        label="asset transaction",
    )
    _assert_project_path_lease(path_lease)
    preserve_transaction = False
    try:
        archive = (
            _absolute_path(archive_path)
            if archive_path is not None
            else transaction / "menagerie.tar.gz"
        )
        if archive_path is None:
            _download(MENAGERIE_ARCHIVE_URL, archive)
        actual_hash = _sha256(archive)
        if actual_hash != MENAGERIE_ARCHIVE_SHA256:
            raise AssetVerificationError(
                archive,
                [
                    "MuJoCo Menagerie archive checksum mismatch "
                    f"(expected {MENAGERIE_ARCHIVE_SHA256}, got {actual_hash})"
                ],
            )

        candidate = transaction / "candidate"
        _extract_panda(archive, candidate)
        _verify_runtime_tree(candidate)
        _assert_owned_path(transaction, transaction_identity, label="asset transaction")
        _assert_project_path_lease(path_lease)
        _publish_candidate(
            candidate,
            target,
            transaction,
            path_lease,
            transaction_identity,
            previous_identity,
        )
    except _AssetRollbackError:
        preserve_transaction = True
        raise
    finally:
        if not preserve_transaction:
            _remove_transaction(transaction, transaction_identity, path_lease)
    return target


def _asset_target(project_root: Path) -> Path:
    return project_root / "third_party" / "mujoco_menagerie" / "franka_emika_panda"


def _absolute_path(path: str | Path) -> Path:
    """Return an absolute lexical path without resolving links."""

    return Path(os.path.abspath(os.fspath(path)))


def _asset_install_lock_path(
    project_root: Path,
    *,
    identity: os.stat_result | None = None,
) -> Path:
    physical = identity or _require_physical_directory(project_root, label="project root")
    lock_key = f"{physical.st_dev}:{physical.st_ino}"
    digest = hashlib.sha256(lock_key.encode("ascii")).hexdigest()
    return Path(tempfile.gettempdir()) / f"mclab-assets-{digest}.lock"


@contextmanager
def _exclusive_asset_install_lock(project_root: Path) -> Iterator[None]:
    """Serialize one physical project root across processes until cleanup finishes."""

    project_identity = _require_physical_directory(project_root, label="project root")
    lock_path = _asset_install_lock_path(project_root, identity=project_identity)
    descriptor = _open_asset_install_lock(lock_path)

    locked = False
    try:
        opened = _validate_private_lock_file(
            descriptor,
            lock_path,
            phase="validate",
        )
        if opened.st_size == 0:
            os.write(descriptor, b"\0")
        _lock_descriptor(descriptor)
        locked = True
        _validate_private_lock_file(descriptor, lock_path, phase="revalidate")
        current_project = _require_physical_directory(project_root, label="project root")
        if not _same_path_identity(project_identity, current_project):
            raise AssetSafetyError(
                project_root,
                ["project root changed while acquiring the asset install lock"],
            )
        yield
    finally:
        if locked:
            _unlock_descriptor(descriptor)
        os.close(descriptor)


def _open_asset_install_lock(lock_path: Path) -> int:
    flags = (
        os.O_RDWR
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        return os.open(lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _validate_private_lock_path(lock_path, phase="inspect existing")
        try:
            return os.open(lock_path, flags)
        except OSError as exc:
            raise AssetSafetyError(
                lock_path,
                [f"could not open existing asset install lock: {exc}"],
            ) from exc
    except OSError as exc:
        raise AssetSafetyError(lock_path, [f"could not open asset install lock: {exc}"]) from exc


def _lock_descriptor(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        import msvcrt

        busy_errors = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        while True:
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in busy_errors and getattr(exc, "winerror", None) not in {33, 36}:
                    raise RuntimeError(f"Could not lock Panda asset installation: {exc}") from exc
                time.sleep(_LOCK_RETRY_SECONDS)

    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        raise RuntimeError(f"Could not lock Panda asset installation: {exc}") from exc


def _unlock_descriptor(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _check_project_path(project_root: Path, *, create_parents: bool) -> None:
    """Reject link/reparse parents and optionally create the install parents."""

    target_parent = _asset_target(project_root).parent
    current = project_root
    if not _path_exists(current):
        raise AssetVerificationError(current, ["project root is missing"])
    _require_physical_directory(current, label="project root")

    for part in target_parent.relative_to(project_root).parts:
        current = current / part
        if _path_exists(current):
            _require_physical_directory(current, label="asset parent")
            continue
        if not create_parents:
            return
        current.mkdir()
        _require_physical_directory(current, label="created asset parent")


def _capture_project_path_lease(project_root: Path) -> _ProjectPathLease:
    target_parent = _asset_target(project_root).parent
    paths = [project_root]
    current = project_root
    for part in target_parent.relative_to(project_root).parts:
        current = current / part
        paths.append(current)
    return _ProjectPathLease(
        tuple(
            (path, _require_physical_directory(path, label="asset install parent"))
            for path in paths
        )
    )


def _assert_project_path_lease(lease: _ProjectPathLease) -> None:
    for path, expected in lease.entries:
        current = _require_physical_directory(path, label="asset install parent")
        if not _same_path_identity(expected, current):
            raise AssetSafetyError(
                path,
                ["asset install parent changed during installation"],
            )


def _require_physical_directory(path: Path, *, label: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise AssetSafetyError(path, [f"could not inspect {label}: {exc}"]) from exc
    if _is_link_or_reparse(metadata):
        raise AssetSafetyError(path, [f"{label} is a link or reparse point"])
    if not stat.S_ISDIR(metadata.st_mode):
        raise AssetSafetyError(path, [f"{label} is not a physical directory"])
    return metadata


def _verify_runtime_tree(target: Path) -> AssetVerification:
    manifest, expected_directories = _validated_manifest()
    return _verify_runtime_tree_impl(
        target,
        manifest=manifest,
        expected_directories=expected_directories,
        file_count=PANDA_RUNTIME_FILE_COUNT,
        total_bytes=PANDA_RUNTIME_TOTAL_BYTES,
    )


def _validated_manifest() -> tuple[tuple[tuple[str, int, str], ...], set[str]]:
    issues: list[str] = []
    if PANDA_RUNTIME_MANIFEST_SCHEMA != 1:
        issues.append(f"unsupported runtime manifest schema: {PANDA_RUNTIME_MANIFEST_SCHEMA!r}")
    raw_manifest: tuple[object, ...] = tuple(PANDA_RUNTIME_MANIFEST)
    manifest: list[tuple[str, int, str]] = []
    expected_directories: set[str] = set()
    for index, entry in enumerate(raw_manifest):
        if not isinstance(entry, tuple) or len(entry) != 3:
            issues.append(f"invalid runtime manifest entry at index {index}: {entry!r}")
            continue
        relative, size, digest = entry
        if not isinstance(relative, str):
            issues.append(f"invalid runtime path at index {index}: {relative!r}")
            continue
        posix = PurePosixPath(relative)
        if (
            not relative
            or posix == PurePosixPath(".")
            or relative != posix.as_posix()
            or posix.is_absolute()
            or any(part in {"", ".", ".."} for part in posix.parts)
            or "\\" in relative
            or "\x00" in relative
        ):
            issues.append(f"unsafe runtime manifest path: {relative!r}")
            continue
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            issues.append(f"invalid runtime size for {relative}: {size!r}")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            issues.append(f"invalid runtime SHA-256 for {relative}: {digest!r}")
        if isinstance(size, int) and not isinstance(size, bool) and isinstance(digest, str):
            manifest.append((relative, size, digest))
        parent = posix.parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent

    paths = [entry[0] for entry in manifest]
    if paths != sorted(paths):
        issues.append("runtime manifest paths are not sorted")
    if len(paths) != len(set(paths)):
        issues.append("runtime manifest contains duplicate paths")
    if len({path.casefold() for path in paths}) != len(paths):
        issues.append("runtime manifest contains case-insensitive path collisions")
    if set(paths) & expected_directories:
        issues.append("runtime manifest uses the same path as a file and directory")
    if len(raw_manifest) != PANDA_RUNTIME_FILE_COUNT:
        issues.append(
            "runtime manifest file count mismatch "
            f"(expected {PANDA_RUNTIME_FILE_COUNT}, got {len(raw_manifest)})"
        )
    manifest_bytes = sum(entry[1] for entry in manifest)
    if manifest_bytes != PANDA_RUNTIME_TOTAL_BYTES:
        issues.append(
            "runtime manifest byte total mismatch "
            f"(expected {PANDA_RUNTIME_TOTAL_BYTES}, got {manifest_bytes})"
        )
    if issues:
        raise AssetVerificationError(Path("<embedded Panda runtime manifest>"), issues)
    return tuple(manifest), expected_directories


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "MCLab-assets/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download MCLab assets from {url}: {exc}") from exc


def _extract_panda(archive: Path, staging: Path) -> None:
    manifest, _ = _validated_manifest()
    expected = {relative: size for relative, size, _digest in manifest}
    seen: set[str] = set()
    staging.mkdir()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.name.startswith(PANDA_PREFIX):
                continue
            relative = member.name.removeprefix(PANDA_PREFIX)
            if relative not in expected:
                continue
            if relative in seen:
                raise AssetVerificationError(
                    archive, [f"duplicate runtime archive member: {relative}"]
                )
            seen.add(relative)
            if not member.isfile():
                raise AssetSafetyError(
                    archive, [f"runtime archive member is not a regular file: {relative}"]
                )
            if member.size != expected[relative]:
                raise AssetVerificationError(
                    archive,
                    [
                        f"archive size mismatch for {relative} "
                        f"(expected {expected[relative]}, got {member.size})"
                    ],
                )
            destination = staging.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise AssetVerificationError(
                    archive, [f"could not read runtime archive member: {relative}"]
                )
            with source, destination.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _publish_candidate(
    candidate: Path,
    target: Path,
    transaction: Path,
    path_lease: _ProjectPathLease,
    transaction_identity: os.stat_result,
    previous_identity: os.stat_result | None,
) -> None:
    """Publish one owned candidate without ever moving an unowned target."""

    candidate_identity = _require_owned_directory(
        candidate,
        expected=None,
        label="verified asset candidate",
    )
    backup = transaction / "previous"
    failed_candidate = transaction / "failed-candidate"
    _assert_project_path_lease(path_lease)
    _assert_owned_path(transaction, transaction_identity, label="asset transaction")

    if previous_identity is None:
        if _path_metadata(target) is not None:
            raise AssetSafetyError(
                target,
                ["runtime target appeared after verification; refusing to replace it"],
            )
    else:
        _assert_owned_path(target, previous_identity, label="verified previous runtime tree")
        try:
            _move_owned_directory(
                target,
                backup,
                previous_identity,
                path_lease,
                transaction,
                transaction_identity,
            )
        except BaseException as move_error:
            try:
                target_state = _path_metadata(target)
                backup_state = _path_metadata(backup)
                previous_remains = (
                    target_state is not None
                    and _same_path_identity(target_state, previous_identity)
                    and backup_state is None
                )
            except BaseException as probe_error:
                _raise_preserved_recovery_error(backup, move_error, probe_error)
            if previous_remains:
                _raise_install_error_or_base_exception(
                    move_error,
                    f"Could not begin Panda asset replacement at {target}; "
                    "the previous tree remains.",
                )
            _rollback_previous_tree(
                target=target,
                backup=backup,
                failed_candidate=failed_candidate,
                candidate_identity=candidate_identity,
                previous_identity=previous_identity,
                transaction=transaction,
                transaction_identity=transaction_identity,
                path_lease=path_lease,
                publish_error=move_error,
            )

    try:
        _move_owned_directory(
            candidate,
            target,
            candidate_identity,
            path_lease,
            transaction,
            transaction_identity,
        )
        _verify_runtime_tree(target)
        _assert_owned_path(target, candidate_identity, label="published runtime tree")
        _assert_project_path_lease(path_lease)
    except BaseException as publish_error:
        if previous_identity is not None:
            _rollback_previous_tree(
                target=target,
                backup=backup,
                failed_candidate=failed_candidate,
                candidate_identity=candidate_identity,
                previous_identity=previous_identity,
                transaction=transaction,
                transaction_identity=transaction_identity,
                path_lease=path_lease,
                publish_error=publish_error,
            )
        try:
            _recover_failed_initial_publish(
                candidate=candidate,
                target=target,
                failed_candidate=failed_candidate,
                candidate_identity=candidate_identity,
                transaction=transaction,
                transaction_identity=transaction_identity,
                path_lease=path_lease,
            )
        except BaseException as recovery_error:
            _raise_preserved_recovery_error(transaction, publish_error, recovery_error)
        _raise_install_error_or_base_exception(
            publish_error,
            f"Could not publish verified Panda assets to {target}; no previous tree existed.",
        )


def _rollback_previous_tree(
    *,
    target: Path,
    backup: Path,
    failed_candidate: Path,
    candidate_identity: os.stat_result,
    previous_identity: os.stat_result,
    transaction: Path,
    transaction_identity: os.stat_result,
    path_lease: _ProjectPathLease,
    publish_error: BaseException,
) -> None:
    """Restore an owned backup or preserve the whole transaction on uncertainty."""

    try:
        target_state = _path_metadata(target)
        if target_state is not None:
            if not _same_path_identity(target_state, candidate_identity):
                raise AssetSafetyError(
                    target,
                    ["runtime target is not owned by this transaction; refusing to move it"],
                )
            _move_owned_directory(
                target,
                failed_candidate,
                candidate_identity,
                path_lease,
                transaction,
                transaction_identity,
            )
        _assert_owned_path(backup, previous_identity, label="previous runtime recovery tree")
        _move_owned_directory(
            backup,
            target,
            previous_identity,
            path_lease,
            transaction,
            transaction_identity,
        )
        _assert_owned_path(target, previous_identity, label="restored previous runtime tree")
    except BaseException as rollback_error:
        _raise_preserved_recovery_error(backup, publish_error, rollback_error)

    _raise_install_error_or_base_exception(
        publish_error,
        f"Could not publish verified Panda assets to {target}; the previous tree was restored.",
    )


def _recover_failed_initial_publish(
    *,
    candidate: Path,
    target: Path,
    failed_candidate: Path,
    candidate_identity: os.stat_result,
    transaction: Path,
    transaction_identity: os.stat_result,
    path_lease: _ProjectPathLease,
) -> None:
    target_state = _path_metadata(target)
    if target_state is not None:
        if not _same_path_identity(target_state, candidate_identity):
            raise AssetSafetyError(
                target,
                ["runtime target is not owned by this transaction; refusing to move it"],
            )
        _move_owned_directory(
            target,
            failed_candidate,
            candidate_identity,
            path_lease,
            transaction,
            transaction_identity,
        )
        return

    candidate_state = _path_metadata(candidate)
    if candidate_state is None or not _same_path_identity(candidate_state, candidate_identity):
        raise AssetSafetyError(
            transaction,
            ["verified candidate location is uncertain after publication failure"],
        )


def _move_owned_directory(
    source: Path,
    destination: Path,
    source_identity: os.stat_result,
    path_lease: _ProjectPathLease,
    transaction: Path,
    transaction_identity: os.stat_result,
) -> None:
    _assert_project_path_lease(path_lease)
    _assert_owned_path(transaction, transaction_identity, label="asset transaction")
    _assert_owned_path(source, source_identity, label="transaction-owned directory")
    if _path_metadata(destination) is not None:
        raise AssetSafetyError(
            destination,
            ["publication destination already exists; refusing to replace it"],
        )
    _replace_path(source, destination)
    _assert_project_path_lease(path_lease)
    _assert_owned_path(transaction, transaction_identity, label="asset transaction")
    _assert_owned_path(destination, source_identity, label="moved transaction-owned directory")


def _raise_preserved_recovery_error(
    recovery_path: Path,
    publication_error: BaseException,
    recovery_error: BaseException,
) -> None:
    raise _AssetRollbackError(
        "Could not publish verified Panda assets and automatic recovery was uncertain; "
        f"recovery data was preserved at {recovery_path}. "
        f"Publication error: {sanitize_asset_diagnostic(publication_error)}"
    ) from recovery_error


def _raise_install_error_or_base_exception(error: BaseException, message: str) -> None:
    if not isinstance(error, Exception):
        raise error
    raise RuntimeError(message) from error


def _replace_path(source: Path, destination: Path) -> None:
    rename_directory_no_replace(source, destination)


def _remove_transaction(
    transaction: Path,
    transaction_identity: os.stat_result,
    path_lease: _ProjectPathLease,
) -> None:
    _assert_project_path_lease(path_lease)
    _assert_owned_path(transaction, transaction_identity, label="asset transaction")
    try:
        shutil.rmtree(transaction)
    except OSError as exc:
        raise RuntimeError(
            f"Could not remove Panda asset transaction {sanitize_asset_diagnostic(transaction)}: "
            f"{sanitize_asset_diagnostic(exc)}"
        ) from exc
    _assert_project_path_lease(path_lease)


def _require_owned_directory(
    path: Path,
    *,
    expected: os.stat_result | None,
    label: str,
) -> os.stat_result:
    metadata = _path_metadata(path)
    if metadata is None:
        raise AssetSafetyError(path, [f"{label} is missing"])
    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise AssetSafetyError(path, [f"{label} is not a physical directory"])
    if expected is not None and not _same_path_identity(metadata, expected):
        raise AssetSafetyError(path, [f"{label} changed identity"])
    return metadata


def _assert_owned_path(path: Path, expected: os.stat_result, *, label: str) -> None:
    _require_owned_directory(path, expected=expected, label=label)


def _path_metadata(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AssetSafetyError(path, [f"could not inspect path: {exc}"]) from exc


def _path_exists(path: Path) -> bool:
    return _path_metadata(path) is not None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
