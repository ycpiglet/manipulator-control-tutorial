"""Fail-closed planning and recoverable quarantine for saved MCLab runs."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mclab.output_inventory import (
    TRASH_DIR_NAME,
    CleanupEntry,
    SavedRunSnapshot,
    read_json_mapping_rooted as _read_json_mapping_rooted,
    run_identity_rooted as _run_identity_rooted,
    strict_cleanup_entry_rooted as _strict_cleanup_entry_rooted,
)
from mclab.output_receipts import (
    RECOVERABLE_RECEIPT_STATUSES,
    RECEIPT_FILE_NAME,
    RECEIPT_ID_RE,
    RECEIPT_SCHEMA_VERSION,
    CleanupReceipt,
    _encode_receipt_payload,
    _new_receipt_id,
    _read_receipt_payload_rooted,
    _receipt_from_payload,
    _receipt_mappings,
    _utc_now,
    _write_receipt_payload_rooted,
    _write_receipt_payload_rooted_best_effort,
)
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    CleanupMoveCommittedError,
    CleanupOperationError,
    CleanupSafetyError,
    _absolute_path,
    _hash_payload,
    reconcile_directory_move_error,
    _same_open_file_state,
    _stat_is_link_or_reparse,
)


PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SkippedEntry:
    path: Path
    name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": str(self.path), "reason": self.reason}


@dataclass(frozen=True)
class CleanupPlan:
    root: Path
    root_exists: bool
    keep: int
    eligible: tuple[CleanupEntry, ...]
    retained: tuple[CleanupEntry, ...]
    selected: tuple[CleanupEntry, ...]
    skipped: tuple[SkippedEntry, ...]
    root_token: str
    plan_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "root": str(self.root),
            "root_exists": self.root_exists,
            "root_token": self.root_token,
            "keep": self.keep,
            "eligible": [entry.to_dict() for entry in self.eligible],
            "retained": [entry.to_dict() for entry in self.retained],
            "selected": [entry.to_dict() for entry in self.selected],
            "skipped": [entry.to_dict() for entry in self.skipped],
        }


def validate_output_root(
    output_root: str | Path,
    *,
    allowed_root: str | Path | None = None,
) -> tuple[Path, bool]:
    """Validate a configured outputs root without inventorying or changing it."""

    with pinned_output_root(output_root, allowed_root=allowed_root) as (
        root,
        root_exists,
        _root_pin,
    ):
        return root, root_exists


def build_cleanup_plan(
    output_root: str | Path,
    *,
    keep: int,
    allowed_root: str | Path | None = None,
) -> CleanupPlan:
    """Return a deterministic, read-only plan for strict modern run manifests."""

    if keep < 0:
        raise CleanupSafetyError("Cleanup --keep must be a non-negative integer.")
    with (
        pinned_output_root(output_root, allowed_root=allowed_root) as (
            root,
            root_exists,
            root_pin,
        ),
        root_pin.operation_lock() if root_pin is not None else nullcontext(),
    ):
        return _build_cleanup_plan_pinned(
            root,
            root_exists=root_exists,
            root_pin=root_pin,
            keep=keep,
        )


def _build_cleanup_plan_pinned(
    root: Path,
    *,
    root_exists: bool,
    root_pin: PinnedOutputRoot | None,
    keep: int,
) -> CleanupPlan:
    if not root_exists or root_pin is None:
        return _assemble_plan(
            root,
            root_exists=False,
            root_pin=None,
            keep=keep,
            eligible=(),
            skipped=(),
        )
    eligible: list[CleanupEntry] = []
    skipped: list[SkippedEntry] = []
    children = sorted(root_pin.list_names(), key=lambda name: (name.casefold(), name))
    for name in children:
        path = root_pin.display_path((name,))
        entry, reason = _strict_cleanup_entry_rooted(root_pin, name)
        if entry is None:
            skipped.append(SkippedEntry(path=path, name=name, reason=reason))
        else:
            eligible.append(entry)
    root_pin.assert_read_boundary()
    eligible.sort(key=lambda entry: (entry.finished_at, entry.name), reverse=True)
    return _assemble_plan(
        root,
        root_exists=True,
        root_pin=root_pin,
        keep=keep,
        eligible=tuple(eligible),
        skipped=tuple(skipped),
    )


def quarantine_cleanup_plan(
    plan: CleanupPlan,
    *,
    expected_plan_id: str,
    allowed_root: str | Path | None = None,
) -> CleanupReceipt:
    """Move an unchanged plan into quarantine with rollback and receipt recovery."""

    if expected_plan_id != plan.plan_id:
        raise CleanupSafetyError("The supplied cleanup plan ID does not match this plan.")
    with pinned_output_root(plan.root, allowed_root=allowed_root) as (
        root,
        root_exists,
        root_pin,
    ):
        if not root_exists or root_pin is None:
            raise CleanupSafetyError("The configured outputs root no longer exists.")
        with root_pin.operation_lock():
            fresh = _build_cleanup_plan_pinned(
                root,
                root_exists=True,
                root_pin=root_pin,
                keep=plan.keep,
            )
            if fresh.plan_id != plan.plan_id:
                raise CleanupSafetyError(
                    "The outputs inventory changed after the dry-run; no run was moved. "
                    "Create a new plan."
                )
            if not fresh.selected:
                raise CleanupSafetyError("The cleanup plan has no selected runs to quarantine.")
            return _quarantine_entries_locked(
                root_pin=root_pin,
                entries=fresh.selected,
                plan_id=fresh.plan_id,
                keep=fresh.keep,
                mode="bulk",
            )


def run_identity_token(path: str | Path, *, allow_legacy: bool = False) -> str:
    """Return a stale-operation token for a physical saved-run directory."""

    target = _absolute_path(path)
    with pinned_output_root(target.parent, allowed_root=target.parent) as (
        _root,
        root_exists,
        root_pin,
    ):
        if not root_exists or root_pin is None:
            raise CleanupSafetyError("The saved-run parent does not exist.")
        return _run_identity_rooted(root_pin, (target.name,), allow_legacy=allow_legacy).token


def read_saved_run_snapshot(
    path: str | Path,
    *,
    allow_legacy: bool = False,
) -> SavedRunSnapshot:
    """Read one coherent, bounded saved-run metadata snapshot without following links."""

    target = _absolute_path(path)
    with pinned_output_root(target.parent, allowed_root=target.parent) as (
        _root,
        root_exists,
        root_pin,
    ):
        if not root_exists or root_pin is None:
            raise CleanupSafetyError("The saved-run parent does not exist.")
        return read_saved_run_snapshot_rooted(
            root_pin,
            target.name,
            allow_legacy=allow_legacy,
        )


def read_saved_run_snapshot_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
    *,
    allow_legacy: bool = False,
) -> SavedRunSnapshot:
    """Read one snapshot through an already pinned outputs boundary."""

    relative = (name,)
    identity = _run_identity_rooted(root_pin, relative, allow_legacy=allow_legacy)
    manifest = identity.payload if identity.marker_name == "manifest.json" else {}
    summary = identity.payload if identity.marker_name == "summary.json" else {}
    summary_relative = (*relative, "summary.json")
    if identity.marker_name == "manifest.json" and root_pin.lexists(summary_relative):
        summary, _digest = _read_json_mapping_rooted(
            root_pin,
            summary_relative,
            description="saved-run summary",
            allow_empty=True,
        )
    final_stat = root_pin.lstat(relative)
    if _stat_is_link_or_reparse(final_stat) or not _same_open_file_state(
        identity.path_stat,
        final_stat,
    ):
        raise CleanupSafetyError("Saved run changed while metadata was read")
    return SavedRunSnapshot(
        token=identity.token,
        scenario_id=identity.scenario_id,
        status=identity.status,
        marker_name=identity.marker_name,
        manifest=manifest,
        summary=summary,
    )


def quarantine_run(
    output_root: str | Path,
    run_path: str | Path,
    *,
    confirmation: str,
    expected_token: str,
    allowed_root: str | Path | None = None,
) -> CleanupReceipt:
    """Move one explicitly confirmed, unchanged saved run into quarantine."""

    with pinned_output_root(output_root, allowed_root=allowed_root) as (
        root,
        root_exists,
        root_pin,
    ):
        if not root_exists or root_pin is None:
            raise CleanupSafetyError("The configured outputs root does not exist.")
        target = _absolute_path(run_path)
        if target.parent != root:
            raise CleanupSafetyError("Run cleanup is limited to a direct child of outputs/.")
        if confirmation != target.name:
            raise CleanupSafetyError("Run cleanup requires the exact folder name as confirmation.")
        identity = _run_identity_rooted(root_pin, (target.name,), allow_legacy=True)
        if identity.marker_name != "manifest.json":
            raise CleanupSafetyError(
                "Legacy saved runs cannot be quarantined without a strict terminal manifest."
            )
        if identity.status not in {"completed", "stopped", "error"}:
            raise CleanupSafetyError(
                "Running or unknown-status saved runs cannot be quarantined. "
                "Finish or repair the run first."
            )
        if root_pin.lexists((target.name, ".mclab-preserve")):
            raise CleanupSafetyError("The saved run has a .mclab-preserve hold marker.")
        entry, reason = _strict_cleanup_entry_rooted(root_pin, target.name)
        if entry is None:
            raise CleanupSafetyError(
                "The selected folder is not a strict terminal cleanup candidate: "
                f"{reason}."
            )
        if not expected_token or entry.token != expected_token:
            raise CleanupSafetyError(
                "The saved run changed after it was listed; no run was moved. "
                "Refresh Results and retry."
            )
        plan_id = _hash_payload(
            {
                "schema_version": PLAN_SCHEMA_VERSION,
                "mode": "single",
                "root": str(root),
                "name": target.name,
                "token": entry.token,
            }
        )
        return _quarantine_entries(
            root_pin=root_pin,
            entries=(entry,),
            plan_id=plan_id,
            keep=0,
            mode="single",
        )


def list_cleanup_receipts(
    output_root: str | Path,
    *,
    allowed_root: str | Path | None = None,
) -> tuple[CleanupReceipt, ...]:
    """List readable quarantine receipts without following links."""

    with pinned_output_root(output_root, allowed_root=allowed_root) as (
        root,
        root_exists,
        root_pin,
    ):
        if not root_exists or root_pin is None:
            return ()
        trash_relative = (TRASH_DIR_NAME,)
        if not root_pin.lexists(trash_relative):
            return ()
        root_pin.validate_directory(trash_relative, description="cleanup quarantine")
        operation_active = root_pin.operation_is_active()
        receipts: list[CleanupReceipt] = []
        for receipt_id in sorted(root_pin.list_names(trash_relative), reverse=True):
            if not RECEIPT_ID_RE.fullmatch(receipt_id):
                continue
            receipt_relative = (*trash_relative, receipt_id)
            try:
                root_pin.validate_directory(receipt_relative, description="cleanup receipt")
                payload = _read_receipt_payload_rooted(root_pin, receipt_relative)
                receipts.append(
                    _receipt_from_payload(
                        root_pin.display_path(receipt_relative),
                        payload,
                        expected_root=root,
                        expected_root_token=_stable_root_identity_token(root_pin),
                        operation_active=operation_active,
                    )
                )
            except CleanupSafetyError as exc:
                raise CleanupSafetyError(
                    f"Cleanup receipt {receipt_id!r} is unreadable or unsafe: {exc}"
                ) from exc
        root_pin.assert_read_boundary()
        receipts.sort(key=lambda item: (item.created_at, item.receipt_id), reverse=True)
        return tuple(receipts)


def restore_cleanup_receipt(
    output_root: str | Path,
    receipt_id: str,
    *,
    allowed_root: str | Path | None = None,
) -> CleanupReceipt:
    """Restore a receipt, rolling back on failure and recording any partial state."""

    with (
        pinned_output_root(output_root, allowed_root=allowed_root) as (
            root,
            root_exists,
            root_pin,
        ),
        root_pin.operation_lock() if root_pin is not None else nullcontext(),
    ):
        if not root_exists or root_pin is None:
            raise CleanupSafetyError("The configured outputs root does not exist.")
        if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
            raise CleanupSafetyError("Invalid cleanup receipt ID.")
        trash_relative = (TRASH_DIR_NAME,)
        receipt_relative = (*trash_relative, receipt_id)
        entries_relative = (*receipt_relative, "entries")
        root_pin.validate_directory(trash_relative, description="cleanup quarantine")
        root_pin.pin_directory(trash_relative, description="cleanup quarantine")
        root_pin.validate_directory(receipt_relative, description="cleanup receipt")
        root_pin.pin_directory(receipt_relative, description="cleanup receipt")
        payload = _read_receipt_payload_rooted(root_pin, receipt_relative)
        receipt_path = root_pin.display_path(receipt_relative)
        receipt = _receipt_from_payload(
            receipt_path,
            payload,
            expected_root=root,
            expected_root_token=_stable_root_identity_token(root_pin),
        )
        if receipt.status not in RECOVERABLE_RECEIPT_STATUSES:
            raise CleanupSafetyError(
                f"Cleanup receipt {receipt_id} is {receipt.status!r}, not a recoverable state."
            )

        mappings = _receipt_mappings(payload)
        root_pin.validate_directory(entries_relative, description="receipt entries")
        root_pin.pin_directory(entries_relative, description="receipt entries")
        pending: list[tuple[tuple[str, ...], tuple[str, ...], str]] = []
        for name, token in mappings:
            source = (name,)
            staged = (*entries_relative, name)
            source_present = root_pin.lexists(source)
            staged_present = root_pin.lexists(staged)
            if source_present and staged_present:
                raise CleanupSafetyError(
                    f"Cannot restore {name!r}: the original path already exists while the "
                    "quarantined path also exists. Both copies were preserved."
                )
            if not source_present and not staged_present:
                raise CleanupSafetyError(
                    f"Cannot restore {name!r}: both original and quarantined paths are missing."
                )
            current = source if source_present else staged
            identity = _run_identity_rooted(root_pin, current, allow_legacy=True)
            if identity.token != token:
                raise CleanupSafetyError(
                    f"Cannot restore {name!r}: the saved run changed. No run was restored."
                )
            if staged_present:
                pending.append((staged, source, token))

        previous_status = receipt.status
        restored_at = _utc_now()
        _encode_receipt_payload(
            {
                **payload,
                "status": "restored",
                "restored_at": restored_at,
            }
        )
        restored: list[tuple[tuple[str, ...], tuple[str, ...], str]] = []
        try:
            for staged, source, token in pending:
                reported_error = _move_directory_rooted(
                    root_pin,
                    staged,
                    source,
                    expected_token=token,
                )
                restored.append((source, staged, token))
                if reported_error is not None:
                    raise CleanupOperationError(
                        f"Restore rename completed but reported an error: {reported_error}"
                    )
                restored_identity = _run_identity_rooted(
                    root_pin,
                    source,
                    allow_legacy=True,
                )
                if restored_identity.token != token:
                    raise CleanupSafetyError(
                        f"Restored run {source[-1]!r} changed during movement."
                    )
            root_pin.assert_transaction_boundaries()
            payload["status"] = "restored"
            payload["restored_at"] = restored_at
            _write_receipt_payload_rooted(root_pin, receipt_relative, payload)
            root_pin.assert_transaction_boundaries()
        except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
            rollback_errors = _rollback_moves_rooted(root_pin, restored)
            payload["status"] = (
                "restore_rollback_failed" if rollback_errors else previous_status
            )
            payload["restore_error"] = str(exc)
            if rollback_errors:
                payload["rollback_errors"] = rollback_errors
            receipt_error = _write_receipt_payload_rooted_best_effort(
                root_pin,
                receipt_relative,
                payload,
            )
            detail = (
                "rollback was incomplete"
                if rollback_errors
                else "all restored entries were rolled back"
            )
            if receipt_error:
                detail = f"{detail}; receipt update also failed: {receipt_error}"
            raise CleanupOperationError(
                f"Restore failed; {detail}. Receipt: {receipt_id}"
            ) from exc
        return _receipt_from_payload(
            receipt_path,
            payload,
            expected_root=root,
            expected_root_token=_stable_root_identity_token(root_pin),
        )


def _assemble_plan(
    root: Path,
    *,
    root_exists: bool,
    root_pin: PinnedOutputRoot | None,
    keep: int,
    eligible: tuple[CleanupEntry, ...],
    skipped: tuple[SkippedEntry, ...],
) -> CleanupPlan:
    retained = eligible[:keep]
    selected = eligible[keep:]
    root_token = (
        _hash_payload(root_pin.identity_payload(include_mtime=True))
        if root_exists and root_pin is not None
        else "missing"
    )
    plan_payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "root": str(root),
        "root_exists": root_exists,
        "root_token": root_token,
        "keep": keep,
        "eligible": [entry.to_dict() for entry in eligible],
        "skipped": [entry.to_dict() for entry in skipped],
        "retained": [entry.name for entry in retained],
        "selected": [entry.name for entry in selected],
    }
    return CleanupPlan(
        root=root,
        root_exists=root_exists,
        keep=keep,
        eligible=eligible,
        retained=retained,
        selected=selected,
        skipped=skipped,
        root_token=root_token,
        plan_id=_hash_payload(plan_payload),
    )


def _quarantine_entries(
    *,
    root_pin: PinnedOutputRoot,
    entries: tuple[CleanupEntry, ...],
    plan_id: str,
    keep: int,
    mode: str,
) -> CleanupReceipt:
    with root_pin.operation_lock():
        return _quarantine_entries_locked(
            root_pin=root_pin,
            entries=entries,
            plan_id=plan_id,
            keep=keep,
            mode=mode,
        )


def _quarantine_entries_locked(
    *,
    root_pin: PinnedOutputRoot,
    entries: tuple[CleanupEntry, ...],
    plan_id: str,
    keep: int,
    mode: str,
) -> CleanupReceipt:
    for entry in entries:
        current, reason = _strict_cleanup_entry_rooted(root_pin, entry.name)
        if current is None:
            raise CleanupSafetyError(
                f"Saved run {entry.name!r} is no longer a strict terminal cleanup "
                f"candidate: {reason}."
            )
        if current.token != entry.token:
            raise CleanupSafetyError(
                f"Saved run {entry.name!r} changed before quarantine; no run was moved."
            )
    root = root_pin.root
    trash_relative = (TRASH_DIR_NAME,)
    receipt_id = _new_receipt_id(plan_id)
    receipt_relative = (*trash_relative, receipt_id)
    entries_relative = (*receipt_relative, "entries")
    receipt_path = root_pin.display_path(receipt_relative)
    created_at = _utc_now()
    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "root": str(root),
        "root_token": _stable_root_identity_token(root_pin),
        "plan_id": plan_id,
        "mode": mode,
        "keep": keep,
        "created_at": created_at,
        "status": "staging",
        "entries": [{"name": entry.name, "token": entry.token} for entry in entries],
        "staged": [],
    }
    _encode_receipt_payload(
        {
            **payload,
            "status": "quarantined",
            "quarantined_at": created_at,
            "restored_at": created_at,
            "staged": [entry.name for entry in entries],
        }
    )
    _ensure_trash_root_rooted(root_pin)
    try:
        root_pin.mkdir(receipt_relative, mode=0o700)
        root_pin.mkdir(entries_relative, mode=0o700)
    except (CleanupSafetyError, OSError) as exc:
        raise CleanupOperationError(f"Could not create cleanup receipt {receipt_id}: {exc}") from exc
    try:
        _write_receipt_payload_rooted(root_pin, receipt_relative, payload)
    except CleanupOperationError:
        # No run has moved yet. Remove only the exact empty scaffold we just
        # created; preserve it if a receipt file or any unexpected entry exists.
        if not root_pin.lexists((*receipt_relative, RECEIPT_FILE_NAME)):
            try:
                root_pin.rmdir(entries_relative)
                root_pin.rmdir(receipt_relative)
            except (CleanupSafetyError, OSError):
                pass
        raise

    root_pin.pin_directory(receipt_relative, description="cleanup receipt")
    root_pin.pin_directory(entries_relative, description="receipt entries")

    moved: list[tuple[tuple[str, ...], tuple[str, ...], str]] = []
    try:
        for entry in entries:
            source = (entry.name,)
            destination = (*entries_relative, entry.name)
            current = _run_identity_rooted(root_pin, source, allow_legacy=True)
            if current.token != entry.token:
                raise CleanupSafetyError(
                    f"Saved run {entry.name!r} changed during staging; quarantine stopped."
                )
            reported_error = _move_directory_rooted(
                root_pin,
                source,
                destination,
                expected_token=entry.token,
            )
            moved.append((destination, source, entry.token))
            payload["staged"] = [current_path[-1] for current_path, _, _ in moved]
            if reported_error is not None:
                raise CleanupOperationError(
                    f"Quarantine rename completed but reported an error: {reported_error}"
                )
            staged_identity = _run_identity_rooted(
                root_pin,
                destination,
                allow_legacy=True,
            )
            if staged_identity.token != entry.token:
                raise CleanupSafetyError(
                    f"Saved run {entry.name!r} changed during staging; quarantine stopped."
                )
            _write_receipt_payload_rooted(root_pin, receipt_relative, payload)
        root_pin.assert_transaction_boundaries()
        payload["status"] = "quarantined"
        payload["quarantined_at"] = _utc_now()
        _write_receipt_payload_rooted(root_pin, receipt_relative, payload)
        root_pin.assert_transaction_boundaries()
    except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
        rollback_errors = _rollback_moves_rooted(root_pin, moved)
        payload["status"] = "rollback_failed" if rollback_errors else "rollback_complete"
        payload["stage_error"] = str(exc)
        if rollback_errors:
            payload["rollback_errors"] = rollback_errors
        receipt_error = _write_receipt_payload_rooted_best_effort(
            root_pin,
            receipt_relative,
            payload,
        )
        detail = "rollback was incomplete" if rollback_errors else "all staged runs were rolled back"
        if receipt_error:
            detail = f"{detail}; receipt update also failed: {receipt_error}"
        raise CleanupOperationError(
            f"Quarantine staging failed; {detail}. Receipt: {receipt_id}"
        ) from exc
    return _receipt_from_payload(
        receipt_path,
        payload,
        expected_root=root,
        expected_root_token=_stable_root_identity_token(root_pin),
    )


def _rollback_moves_rooted(
    root_pin: PinnedOutputRoot,
    moves: list[tuple[tuple[str, ...], tuple[str, ...], str]],
) -> list[str]:
    errors: list[str] = []
    for current, original, token in reversed(moves):
        try:
            if root_pin.lexists(original):
                raise FileExistsError(
                    f"restore target already exists: {root_pin.display_path(original)}"
                )
            _move_directory_rooted(
                root_pin,
                current,
                original,
                expected_token=token,
            )
            restored_identity = _run_identity_rooted(
                root_pin,
                original,
                allow_legacy=True,
            )
            if restored_identity.token != token:
                raise CleanupSafetyError(
                    f"Rollback target {original[-1]!r} changed during movement"
                )
        except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
            errors.append(
                f"{root_pin.display_path(current)} -> "
                f"{root_pin.display_path(original)}: {exc}"
            )
    return errors


def _move_directory_rooted(
    root_pin: PinnedOutputRoot,
    source: tuple[str, ...],
    destination: tuple[str, ...],
    *,
    expected_token: str,
) -> OSError | None:
    """Move through pinned parents and reconcile a reported post-commit error."""

    source_filesystem_identity = root_pin.directory_identity(source)
    if expected_token:
        source_identity = _run_identity_rooted(root_pin, source, allow_legacy=True)
        if source_identity.token != expected_token:
            raise CleanupSafetyError(f"Move source {source[-1]!r} changed before movement")
    if root_pin.lexists(destination):
        raise FileExistsError(
            f"destination already exists: {root_pin.display_path(destination)}"
        )
    try:
        root_pin.rename_noreplace(
            source,
            destination,
            expected_source_identity=source_filesystem_identity,
        )
    except OSError as exc:
        reported = reconcile_directory_move_error(
            exc,
            expected_identity=source_filesystem_identity,
            source_identity=lambda: root_pin.directory_identity(source),
            destination_identity=lambda: root_pin.directory_identity(destination),
        )
        if isinstance(reported, CleanupMoveCommittedError):
            return reported
        raise reported
    return None


def _stable_root_identity_token(root_pin: PinnedOutputRoot) -> str:
    return _hash_payload(root_pin.identity_payload(include_mtime=False))


def _ensure_trash_root_rooted(root_pin: PinnedOutputRoot) -> tuple[str, ...]:
    trash = (TRASH_DIR_NAME,)
    if root_pin.lexists(trash):
        root_pin.validate_directory(trash, description="cleanup quarantine")
        root_pin.pin_directory(trash, description="cleanup quarantine")
        return trash
    try:
        root_pin.mkdir(trash, mode=0o700)
    except FileExistsError:
        root_pin.validate_directory(trash, description="cleanup quarantine")
    except (CleanupSafetyError, OSError) as exc:
        raise CleanupOperationError(f"Could not create cleanup quarantine: {exc}") from exc
    root_pin.pin_directory(trash, description="cleanup quarantine")
    return trash
