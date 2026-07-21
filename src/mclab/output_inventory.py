"""Strict saved-run inventory and identity checks under a pinned output root."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path, PurePosixPath
from typing import Any

from mclab.application.artifacts import MANIFEST_SCHEMA_VERSION, REPLAY_SCHEMA_VERSION
from mclab.completion import (
    CompletionEvidence,
    CompletionRecordKind,
    CompletionRule,
    completion_evidence_from_payloads,
)
from mclab.output_filters import is_internal_output_dir
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    MAX_METADATA_BYTES,
    MAX_RUN_TREE_ENTRIES,
    CleanupSafetyError,
    _hash_payload,
    _parse_aware_datetime,
    _same_open_file_state,
    _stat_is_link_or_reparse,
)


TRASH_DIR_NAME = ".mclab-trash"
TERMINAL_STATUSES = frozenset({"completed", "stopped", "error"})
COMPLETION_MANIFEST_STATUSES = frozenset({"running", *TERMINAL_STATUSES})
MAX_COMPLETION_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_COMPLETION_SNAPSHOT_BYTES = 256 * 1024 * 1024
MAX_COMPLETION_PLOT_FILES = 256
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPORT_ARTIFACT_KEY = "report"
_WORKSHEET_ARTIFACT_KEY = "worksheet"
_PREDICTION_CHECK_ARTIFACT_KEY = "prediction-check"
_ALL_BATCH_TARGET_ID = "batch.all"


@dataclass(frozen=True)
class CleanupEntry:
    path: Path
    name: str
    scenario_id: str
    status: str
    finished_at: str
    token: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": str(self.path),
            "scenario_id": self.scenario_id,
            "status": self.status,
            "finished_at": self.finished_at,
            "token": self.token,
        }


@dataclass(frozen=True)
class SavedRunSnapshot:
    """Bounded metadata snapshot used by Results and cleanup guards."""

    token: str
    scenario_id: str
    status: str
    marker_name: str
    manifest: dict[str, Any]
    summary: dict[str, Any]


@dataclass(frozen=True)
class InvalidInteractionEvents:
    """A present interaction artifact that could not be trusted as a JSON list."""

    reason: str


@dataclass(frozen=True)
class CompletionManifestValidation:
    """Typed result of validating one manifest against the complete v1 shape."""

    record_kind: CompletionRecordKind
    scenario_id: str
    status: str
    finished_at: str
    artifacts: dict[str, str]
    reason: str = ""


@dataclass(frozen=True)
class CompletionRunSnapshot:
    """One coherent read of completion inputs and manifest-published artifacts."""

    token: str
    scenario_id: str
    status: str
    marker_name: str
    manifest: dict[str, Any]
    summary: dict[str, Any]
    completion_evidence: CompletionEvidence
    interaction_events: object
    plot_paths: tuple[str, ...]
    worksheet_available: bool
    report_available: bool
    artifact_validation_errors: tuple[str, ...]
    finished_at: str = ""
    worksheet_text: str = ""


@dataclass(frozen=True)
class RunIdentity:
    token: str
    scenario_id: str
    status: str
    marker_name: str
    marker_digest: str
    payload: dict[str, Any]
    path_stat: os.stat_result


@dataclass
class _CompletionReadBudget:
    """Bound cumulative completion content and retain commit-time digests."""

    max_bytes: int
    total_bytes: int = 0
    sizes: dict[tuple[str, ...], int] = field(default_factory=dict)
    trusted_digests: dict[tuple[str, ...], str] = field(default_factory=dict)

    def max_bytes_for(self, relative: tuple[str, ...], per_file_limit: int) -> int:
        previous = self.sizes.get(relative)
        if previous is not None:
            return min(per_file_limit, previous)
        return min(per_file_limit, max(0, self.max_bytes - self.total_bytes))

    def account(self, relative: tuple[str, ...], size: int) -> None:
        previous = self.sizes.get(relative)
        if previous is not None:
            if previous != size:
                raise CleanupSafetyError(
                    f"Saved-run artifact {'/'.join(relative)} changed size while read"
                )
            return
        if size < 0 or size > self.max_bytes - self.total_bytes:
            raise _CompletionSnapshotBudgetExceeded(
                "Saved-run completion content exceeds the cumulative "
                f"{self.max_bytes}-byte read budget"
            )
        self.sizes[relative] = size
        self.total_bytes += size

    def trust(self, relative: tuple[str, ...], digest: str) -> None:
        previous = self.trusted_digests.get(relative)
        if previous is not None and not hmac.compare_digest(previous, digest):
            raise CleanupSafetyError(
                f"Saved-run artifact {'/'.join(relative)} changed digest while read"
            )
        self.trusted_digests[relative] = digest

    def discard_trusted_prefix(self, prefix: tuple[str, ...]) -> None:
        for relative in tuple(self.trusted_digests):
            if relative[: len(prefix)] == prefix:
                self.trusted_digests.pop(relative, None)


_ACTIVE_COMPLETION_READ_BUDGET: ContextVar[_CompletionReadBudget | None] = ContextVar(
    "mclab_completion_read_budget",
    default=None,
)


class _CompletionSnapshotBudgetExceeded(CleanupSafetyError):
    """Stop one run snapshot when its unique trusted inputs exceed the cap."""


def assert_output_tree_mutable(output_path: str | Path) -> None:
    """Fail closed unless a direct output tree is safe and non-terminal."""

    output = Path(os.path.abspath(os.path.expanduser(os.fspath(output_path))))
    try:
        with pinned_output_root(output, allowed_root=output) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                return
            assert_output_tree_mutable_rooted(root_pin)
    except (CleanupSafetyError, OSError) as exc:
        raise RuntimeError(
            "Refusing to rewrite artifacts because the output tree is terminal or unsafe."
        ) from exc


def assert_output_tree_mutable_rooted(root_pin: PinnedOutputRoot) -> None:
    """Validate one already pinned output tree without releasing its lease."""

    relative: tuple[str, ...] = ()
    root_pin.validate_directory(relative, description="report output")
    if root_pin.lexists(("manifest.json",)):
        payload, _digest = read_json_mapping_rooted(
            root_pin,
            ("manifest.json",),
            description="report output manifest",
        )
        validation = validate_completion_manifest_v1(payload)
        if validation.record_kind != CompletionRecordKind.MANIFEST_V1:
            raise CleanupSafetyError("Report output manifest is not valid schema 1")
        if validation.status in TERMINAL_STATUSES:
            raise CleanupSafetyError("Report output already has a terminal manifest")
        if validation.status != "running":
            raise CleanupSafetyError(
                "Report output manifest status is not safely mutable"
            )
    elif root_pin.list_names(relative, max_entries=MAX_RUN_TREE_ENTRIES):
        raise CleanupSafetyError("Existing manifest-less output artifacts are read-only")
    root_pin.tree_size(
        relative,
        max_entries=MAX_RUN_TREE_ENTRIES,
    )
    root_pin.assert_read_boundary()


def strict_cleanup_entry_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
) -> tuple[CleanupEntry | None, str]:
    path = root_pin.display_path((name,))
    if is_internal_output_dir(path) or name == TRASH_DIR_NAME:
        return None, "internal or reserved output"
    entry, reason = terminal_manifest_entry_rooted(root_pin, name)
    if entry is None:
        return None, reason
    if root_pin.lexists((name, ".mclab-preserve")):
        return None, "run has a .mclab-preserve hold marker"
    return entry, ""


def terminal_manifest_entry_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
) -> tuple[CleanupEntry | None, str]:
    """Validate terminal manifest structure independently of cleanup policy holds."""

    path = root_pin.display_path((name,))
    try:
        root_pin.validate_directory((name,), description="run candidate")
    except CleanupSafetyError as exc:
        return None, str(exc)
    try:
        payload, manifest_digest = read_json_mapping_rooted(
            root_pin,
            (name, "manifest.json"),
            description="run manifest",
        )
    except CleanupSafetyError as exc:
        return None, str(exc)
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        return None, "unsupported manifest schema"
    scenario_id = payload.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        return None, "manifest scenario_id is blank or invalid"
    status_value = payload.get("status")
    if not isinstance(status_value, str) or status_value not in TERMINAL_STATUSES:
        return None, "manifest status is not a terminal cleanup status"
    try:
        finished = _parse_aware_datetime(payload.get("finished_at"))
    except CleanupSafetyError as exc:
        return None, str(exc)
    config = payload.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("resolved"), dict):
        return None, "manifest config is invalid"
    try:
        started = _parse_aware_datetime(payload.get("started_at"))
    except CleanupSafetyError as exc:
        return None, str(exc).replace("finished_at", "started_at")
    if finished < started:
        return None, "manifest finished_at precedes started_at"
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return None, "manifest artifacts are invalid"
    if any(not _safe_manifest_relative_path(value) for value in artifacts):
        return None, "manifest contains an unsafe artifact path"
    try:
        stat_result = root_pin.lstat((name,))
    except OSError as exc:
        return None, f"could not stat run candidate: {exc}"
    token = _identity_token(
        name=name,
        stat_result=stat_result,
        marker_name="manifest.json",
        marker_digest=manifest_digest,
    )
    return (
        CleanupEntry(
            path=path,
            name=name,
            scenario_id=scenario_id.strip(),
            status=status_value,
            finished_at=finished.astimezone(timezone.utc).isoformat(),
            token=token,
        ),
        "",
    )


def run_identity_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    allow_legacy: bool,
    pinned_stat: os.stat_result | None = None,
) -> RunIdentity:
    root_pin.validate_directory(relative, description="saved run")
    initial_stat = pinned_stat if pinned_stat is not None else root_pin.lstat(relative)
    manifest = (*relative, "manifest.json")
    marker_candidates = (
        [manifest]
        if root_pin.lexists(manifest) or not allow_legacy
        else [(*relative, "summary.json")]
    )
    errors: list[str] = []
    for marker in marker_candidates:
        try:
            payload, digest = read_json_mapping_rooted(
                root_pin,
                marker,
                description="saved-run metadata",
            )
        except CleanupSafetyError as exc:
            errors.append(str(exc))
            continue
        marker_name = marker[-1]
        if marker_name == "manifest.json":
            scenario = payload.get("scenario_id")
            status = payload.get("status")
            if not isinstance(scenario, str) or not scenario.strip():
                errors.append("manifest scenario_id is blank or invalid")
                continue
            if not isinstance(status, str) or not status.strip():
                errors.append("manifest status is blank or invalid")
                continue
        else:
            scenario = payload.get("config_name") or payload.get("lab_name")
            status = "legacy"
            if not isinstance(scenario, str) or not scenario.strip():
                errors.append("legacy summary does not identify an MCLab run")
                continue
        stat_result = root_pin.lstat(relative)
        if _stat_is_link_or_reparse(stat_result) or not _same_open_file_state(
            initial_stat,
            stat_result,
        ):
            raise CleanupSafetyError("Saved run changed while metadata was read")
        _trust_completion_digest(marker, digest)
        return RunIdentity(
            token=_identity_token(
                name=relative[-1],
                stat_result=stat_result,
                marker_name=marker_name,
                marker_digest=digest,
            ),
            scenario_id=scenario.strip(),
            status=status.strip(),
            marker_name=marker_name,
            marker_digest=digest,
            payload=payload,
            path_stat=stat_result,
        )
    reason = errors[-1] if errors else "saved-run metadata is missing"
    raise CleanupSafetyError(f"The selected folder is not a validated saved run: {reason}.")


def validate_completion_manifest_v1(payload: object) -> CompletionManifestValidation:
    """Validate the complete manifest shape used to award saved-run completion.

    The pure completion contract intentionally accepts small synthetic payloads.
    Filesystem consumers use this stricter boundary first so only manifests
    emitted by the schema-v1 writer can contribute trusted completion facts.
    """

    if not isinstance(payload, dict):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            reason="manifest must contain a JSON object",
        )
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        return _manifest_validation(
            CompletionRecordKind.UNSUPPORTED,
            scenario_id=_clean_manifest_text(payload.get("scenario_id")),
            status=_clean_manifest_text(payload.get("status")),
            reason="unsupported manifest schema",
        )

    scenario_id = _clean_manifest_text(payload.get("scenario_id"))
    status = _clean_manifest_text(payload.get("status"))
    if not scenario_id or scenario_id != payload.get("scenario_id"):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest scenario_id is blank or invalid",
        )
    if status not in COMPLETION_MANIFEST_STATUSES or status != payload.get("status"):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest status is invalid",
        )

    try:
        started = _parse_aware_datetime(payload.get("started_at"))
    except CleanupSafetyError as exc:
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason=str(exc).replace("finished_at", "started_at"),
        )
    try:
        finished = _parse_aware_datetime(payload.get("finished_at"))
    except CleanupSafetyError as exc:
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason=str(exc),
        )
    if finished < started:
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest finished_at precedes started_at",
        )

    config = payload.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("resolved"), dict):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest config is invalid",
        )
    if not isinstance(config.get("path"), str):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest config path is invalid",
        )
    seed = config.get("seed")
    if seed is not None and type(seed) is not int:
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest config seed is invalid",
        )

    runtime = payload.get("runtime")
    if not isinstance(runtime, dict) or any(
        not isinstance(runtime.get(key), str)
        for key in ("mclab", "mujoco", "python", "os")
    ):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest runtime is invalid",
        )

    model = payload.get("model")
    if not isinstance(model, dict) or any(
        not isinstance(model.get(key), str)
        for key in ("path", "sha256", "license", "license_sha256")
    ):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest model provenance is invalid",
        )
    if not _optional_sha256(model["sha256"]) or not _optional_sha256(
        model["license_sha256"]
    ):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest model digest is invalid",
        )

    artifacts_value = payload.get("artifacts")
    if not isinstance(artifacts_value, dict):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest artifacts are invalid",
        )
    artifacts: dict[str, str] = {}
    for relative, expected_digest in artifacts_value.items():
        if (
            not _canonical_manifest_relative_path(relative)
            or relative == "manifest.json"
        ):
            return _manifest_validation(
                CompletionRecordKind.INVALID,
                scenario_id=scenario_id,
                status=status,
                reason="manifest contains an unsafe artifact path",
            )
        if not isinstance(expected_digest, str) or _SHA256_RE.fullmatch(
            expected_digest
        ) is None:
            return _manifest_validation(
                CompletionRecordKind.INVALID,
                scenario_id=scenario_id,
                status=status,
                reason="manifest contains an invalid artifact digest",
            )
        artifacts[relative] = expected_digest

    replay = payload.get("replay")
    if (
        not isinstance(replay, dict)
        or type(replay.get("schema_version")) is not int
        or replay.get("schema_version") != REPLAY_SCHEMA_VERSION
        or type(replay.get("available")) is not bool
    ):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest replay metadata is invalid",
        )
    if "run_kind" in payload and not isinstance(payload["run_kind"], str):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest run_kind is invalid",
        )
    if "error" in payload and not isinstance(payload["error"], str):
        return _manifest_validation(
            CompletionRecordKind.INVALID,
            scenario_id=scenario_id,
            status=status,
            reason="manifest error is invalid",
        )

    return CompletionManifestValidation(
        record_kind=CompletionRecordKind.MANIFEST_V1,
        scenario_id=scenario_id,
        status=status,
        finished_at=finished.astimezone(timezone.utc).isoformat(),
        artifacts=artifacts,
    )


def read_completion_run_snapshot_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
    *,
    allow_legacy: bool = True,
) -> CompletionRunSnapshot:
    """Read one completion snapshot through an already pinned outputs root."""

    relative = (name,)
    with root_pin.scoped_directory_pin(relative, description="saved run"):
        return _read_completion_run_snapshot_pinned(
            root_pin,
            name,
            allow_legacy=allow_legacy,
        )


def _read_completion_run_snapshot_pinned(
    root_pin: PinnedOutputRoot,
    name: str,
    *,
    allow_legacy: bool,
) -> CompletionRunSnapshot:
    """Read a completion snapshot while the physical run directory is held."""

    budget = _CompletionReadBudget(MAX_COMPLETION_SNAPSHOT_BYTES)
    budget_token = _ACTIVE_COMPLETION_READ_BUDGET.set(budget)
    try:
        return _read_completion_run_snapshot_with_budget(
            root_pin,
            name,
            allow_legacy=allow_legacy,
            budget=budget,
        )
    finally:
        _ACTIVE_COMPLETION_READ_BUDGET.reset(budget_token)


def _read_completion_run_snapshot_with_budget(
    root_pin: PinnedOutputRoot,
    name: str,
    *,
    allow_legacy: bool,
    budget: _CompletionReadBudget,
) -> CompletionRunSnapshot:
    """Build and commit a snapshot under one cumulative content budget."""

    relative = (name,)
    identity = run_identity_rooted(
        root_pin,
        relative,
        allow_legacy=allow_legacy,
        pinned_stat=root_pin.pinned_directory_stat(relative),
    )
    manifest = identity.payload if identity.marker_name == "manifest.json" else {}
    summary = identity.payload if identity.marker_name == "summary.json" else {}

    interaction_events: object = None
    plot_paths: tuple[str, ...] = ()
    worksheet_available = False
    worksheet_text = ""
    report_available = False
    artifact_errors: list[str] = []
    finished_at = ""
    if manifest:
        validation = validate_completion_manifest_v1(manifest)
        finished_at = validation.finished_at
        if validation.record_kind == CompletionRecordKind.MANIFEST_V1:
            summary, summary_error = _read_trusted_summary_rooted(
                root_pin,
                relative,
                validation.artifacts,
            )
            if summary_error:
                artifact_errors.append(summary_error)
            artifact_keys: list[str] = []
            interaction_events, interaction_error = _read_interaction_events_rooted(
                root_pin,
                relative,
                validation.artifacts,
            )
            if interaction_error:
                artifact_errors.append(interaction_error)
            plot_paths, plot_errors = _trusted_plot_paths_rooted(
                root_pin,
                relative,
                validation.artifacts,
            )
            artifact_errors.extend(plot_errors)
            worksheet_available, worksheet_data, worksheet_error = (
                _read_trusted_artifact_bytes_rooted(
                    root_pin,
                    relative,
                    validation.artifacts,
                    "worksheet.md",
                )
            )
            if worksheet_available:
                prediction_check_available = _contains_prediction_check(worksheet_data)
                worksheet_text = worksheet_data.decode("utf-8", errors="replace")
            else:
                prediction_check_available = False
            if worksheet_error:
                artifact_errors.append(worksheet_error)
            report_available, report_error = _trusted_artifact_available_rooted(
                root_pin,
                relative,
                validation.artifacts,
                "report.html",
            )
            if report_error:
                artifact_errors.append(report_error)
            child_keys: tuple[str, ...] = ()
            if validation.scenario_id == _ALL_BATCH_TARGET_ID:
                child_keys, child_errors = _trusted_child_batch_keys_rooted(
                    root_pin,
                    name,
                    validation.artifacts,
                )
                artifact_errors.extend(child_errors)
            if artifact_errors:
                # A report embeds the publication-time verdict.  If any
                # manifest-published evidence no longer validates, hide both
                # review documents rather than advertising a stale verdict.
                report_available = False
                worksheet_available = False
                prediction_check_available = False
                worksheet_text = ""
            else:
                if report_available:
                    artifact_keys.append(_REPORT_ARTIFACT_KEY)
                if worksheet_available:
                    artifact_keys.append(_WORKSHEET_ARTIFACT_KEY)
                if prediction_check_available:
                    artifact_keys.append(_PREDICTION_CHECK_ARTIFACT_KEY)
            artifact_keys.extend(child_keys)
            completion_evidence = completion_evidence_from_payloads(
                manifest,
                expected_scenario_id=validation.scenario_id,
                plot_count=len(plot_paths),
                interaction_events=interaction_events,
                artifact_keys=tuple(artifact_keys),
            )
        else:
            completion_evidence = CompletionEvidence(validation.record_kind)
            if validation.reason:
                artifact_errors.append(validation.reason)
    else:
        completion_evidence = completion_evidence_from_payloads(
            None,
            expected_scenario_id=identity.scenario_id,
            legacy_summary=summary,
        )

    marker_relative = (*relative, identity.marker_name)
    _marker_payload, final_marker_digest = read_json_mapping_rooted(
        root_pin,
        marker_relative,
        description="saved-run metadata",
        allow_empty=identity.marker_name == "summary.json",
    )
    if not hmac.compare_digest(identity.marker_digest, final_marker_digest):
        raise CleanupSafetyError("Saved-run metadata changed while evidence was read")
    _revalidate_trusted_completion_files_rooted(
        root_pin,
        budget,
        marker_relative=marker_relative,
    )
    final_stat = root_pin.lstat(relative)
    if _stat_is_link_or_reparse(final_stat) or not _same_open_file_state(
        identity.path_stat,
        final_stat,
    ):
        raise CleanupSafetyError("Saved run changed while evidence was read")

    return CompletionRunSnapshot(
        token=identity.token,
        scenario_id=identity.scenario_id,
        status=identity.status,
        marker_name=identity.marker_name,
        manifest=manifest,
        summary=summary,
        completion_evidence=completion_evidence,
        interaction_events=interaction_events,
        plot_paths=plot_paths,
        worksheet_available=worksheet_available,
        report_available=report_available,
        artifact_validation_errors=tuple(artifact_errors),
        finished_at=finished_at,
        worksheet_text=worksheet_text,
    )


def _manifest_validation(
    record_kind: CompletionRecordKind,
    *,
    scenario_id: str = "",
    status: str = "",
    reason: str,
) -> CompletionManifestValidation:
    return CompletionManifestValidation(
        record_kind=record_kind,
        scenario_id=scenario_id,
        status=status,
        finished_at="",
        artifacts={},
        reason=reason,
    )


def _clean_manifest_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_sha256(value: str) -> bool:
    return not value or _SHA256_RE.fullmatch(value) is not None


def _canonical_manifest_relative_path(value: object) -> bool:
    if not _safe_manifest_relative_path(value):
        return False
    assert isinstance(value, str)
    return PurePosixPath(value).as_posix() == value


def _read_trusted_summary_rooted(
    root_pin: PinnedOutputRoot,
    relative_root: tuple[str, ...],
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], str]:
    relative = "summary.json"
    expected_digest = artifacts.get(relative)
    rooted = (*relative_root, relative)
    if expected_digest is None:
        if root_pin.lexists(rooted):
            return {}, "summary.json is not published by the manifest"
        return {}, ""
    try:
        payload, actual_digest = read_json_mapping_rooted(
            root_pin,
            rooted,
            description="saved-run summary",
            allow_empty=True,
        )
    except _CompletionSnapshotBudgetExceeded:
        raise
    except CleanupSafetyError as exc:
        return {}, f"summary.json is not a trusted published artifact: {exc}"
    if not hmac.compare_digest(actual_digest, expected_digest):
        return {}, "summary.json does not match its manifest digest"
    _trust_completion_digest(rooted, expected_digest)
    return payload, ""


def _read_interaction_events_rooted(
    root_pin: PinnedOutputRoot,
    relative_root: tuple[str, ...],
    artifacts: dict[str, str],
) -> tuple[object, str]:
    relative = "interaction_events.json"
    expected_digest = artifacts.get(relative)
    if expected_digest is None:
        return None, ""
    rooted = (*relative_root, relative)
    try:
        max_bytes = _completion_read_limit(
            root_pin,
            rooted,
            MAX_METADATA_BYTES,
        )
        data = root_pin.read_regular_file(
            rooted,
            description="saved-run interaction events",
            max_bytes=max_bytes,
            allow_empty=False,
        )
        _account_completion_bytes(rooted, len(data))
    except _CompletionSnapshotBudgetExceeded:
        raise
    except CleanupSafetyError as exc:
        reason = f"interaction_events.json is not a trusted published artifact: {exc}"
        return InvalidInteractionEvents(reason), reason
    actual_digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        reason = "interaction_events.json does not match its manifest digest"
        return InvalidInteractionEvents(reason), reason
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        reason = f"interaction_events.json is malformed or unreadable: {exc}"
        return InvalidInteractionEvents(reason), reason
    if not isinstance(payload, list):
        reason = "interaction_events.json must contain a JSON list"
        return InvalidInteractionEvents(reason), reason
    _trust_completion_digest(rooted, expected_digest)
    return payload, ""


def _trusted_plot_paths_rooted(
    root_pin: PinnedOutputRoot,
    relative_root: tuple[str, ...],
    artifacts: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    candidates = sorted(
        relative
        for relative in artifacts
        if _is_completion_plot_path(relative)
    )
    if len(candidates) > MAX_COMPLETION_PLOT_FILES:
        return (), (
            f"manifest publishes more than {MAX_COMPLETION_PLOT_FILES} plot artifacts",
        )
    trusted: list[str] = []
    errors: list[str] = []
    for relative in candidates:
        available, error = _trusted_artifact_available_rooted(
            root_pin,
            relative_root,
            artifacts,
            relative,
        )
        if available:
            trusted.append(relative)
        elif error:
            errors.append(error)
    return tuple(trusted), tuple(errors)


def _is_completion_plot_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        len(path.parts) == 2
        and path.parts[0] in {"plots", "comparison_plots"}
        and path.suffix.casefold() == ".png"
    )


def _trusted_artifact_available_rooted(
    root_pin: PinnedOutputRoot,
    relative_root: tuple[str, ...],
    artifacts: dict[str, str],
    relative: str,
) -> tuple[bool, str]:
    expected_digest = artifacts.get(relative)
    if expected_digest is None:
        return False, ""
    try:
        actual_digest = _sha256_regular_file_rooted(
            root_pin,
            (*relative_root, *PurePosixPath(relative).parts),
            description=f"saved-run artifact {relative}",
        )
    except _CompletionSnapshotBudgetExceeded:
        raise
    except CleanupSafetyError as exc:
        return False, f"{relative} is not a trusted published artifact: {exc}"
    if not hmac.compare_digest(actual_digest, expected_digest):
        return False, f"{relative} does not match its manifest digest"
    _trust_completion_digest(
        (*relative_root, *PurePosixPath(relative).parts),
        expected_digest,
    )
    return True, ""


def _read_trusted_artifact_bytes_rooted(
    root_pin: PinnedOutputRoot,
    relative_root: tuple[str, ...],
    artifacts: dict[str, str],
    relative: str,
) -> tuple[bool, bytes, str]:
    expected_digest = artifacts.get(relative)
    if expected_digest is None:
        return False, b"", ""
    rooted = (*relative_root, *PurePosixPath(relative).parts)
    try:
        max_bytes = _completion_read_limit(
            root_pin,
            rooted,
            MAX_COMPLETION_ARTIFACT_BYTES,
        )
        data = root_pin.read_regular_file(
            rooted,
            description=f"saved-run artifact {relative}",
            max_bytes=max_bytes,
            allow_empty=True,
        )
        _account_completion_bytes(rooted, len(data))
    except _CompletionSnapshotBudgetExceeded:
        raise
    except CleanupSafetyError as exc:
        return False, b"", f"{relative} is not a trusted published artifact: {exc}"
    actual_digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        return False, b"", f"{relative} does not match its manifest digest"
    _trust_completion_digest(rooted, expected_digest)
    return True, data, ""


def _contains_prediction_check(worksheet: bytes) -> bool:
    return any(
        line.strip() == b"## Prediction Check"
        for line in worksheet.splitlines()
    )


def _trusted_child_batch_keys_rooted(
    root_pin: PinnedOutputRoot,
    name: str,
    artifacts: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    # Keep catalog/evaluator imports local: catalog construction imports the
    # batch runner, while this module is also used by persistence boundaries.
    from mclab.application.catalog import (
        CONCRETE_BATCH_NAMES,
        CONCRETE_BATCH_TARGET_IDS,
        ScenarioCatalog,
    )

    trusted: list[str] = []
    errors: list[str] = []
    catalog = ScenarioCatalog.default()
    for batch_name, target_id in zip(
        CONCRETE_BATCH_NAMES,
        CONCRETE_BATCH_TARGET_IDS,
        strict=True,
    ):
        relative = f"{batch_name}/manifest.json"
        expected_digest = artifacts.get(relative)
        if expected_digest is None:
            errors.append(f"{relative} is not published by the course manifest")
            continue
        try:
            with root_pin.scoped_directory_pin(
                (name, batch_name),
                description=f"saved child batch {batch_name}",
            ):
                complete, child_errors = _trusted_child_batch_rooted(
                    root_pin,
                    name=name,
                    batch_name=batch_name,
                    target_id=target_id,
                    expected_manifest_digest=expected_digest,
                    completion_rule=catalog.get_batch(target_id).completion,
                )
        except _CompletionSnapshotBudgetExceeded:
            raise
        except CleanupSafetyError as exc:
            _discard_trusted_completion_prefix((name, batch_name))
            errors.append(f"{relative} is not a trusted published artifact: {exc}")
            continue
        errors.extend(child_errors)
        if complete:
            trusted.append(target_id)
        else:
            _discard_trusted_completion_prefix((name, batch_name))
    return tuple(trusted), tuple(errors)


def _trusted_child_batch_rooted(
    root_pin: PinnedOutputRoot,
    *,
    name: str,
    batch_name: str,
    target_id: str,
    expected_manifest_digest: str,
    completion_rule: CompletionRule,
) -> tuple[bool, tuple[str, ...]]:
    from mclab.completion import evaluate_completion

    relative = f"{batch_name}/manifest.json"
    errors: list[str] = []
    payload, actual_digest = read_json_mapping_rooted(
        root_pin,
        (name, batch_name, "manifest.json"),
        description=f"saved child-batch manifest {batch_name}",
    )
    if not hmac.compare_digest(actual_digest, expected_manifest_digest):
        return False, (f"{relative} does not match its course-manifest digest",)
    _trust_completion_digest(
        (name, batch_name, "manifest.json"),
        expected_manifest_digest,
    )
    validation = validate_completion_manifest_v1(payload)
    if validation.record_kind != CompletionRecordKind.MANIFEST_V1:
        return False, (f"{relative} is not a valid schema-1 child-batch manifest",)
    if validation.scenario_id != target_id:
        return False, (f"{relative} does not identify expected child batch {target_id}",)
    if validation.status != "completed":
        return False, (f"{relative} child batch is not completed",)

    child_root = (name, batch_name)
    child_published_plot_paths, child_plot_errors = _trusted_plot_paths_rooted(
        root_pin,
        child_root,
        validation.artifacts,
    )
    child_plot_paths = tuple(
        path
        for path in child_published_plot_paths
        if PurePosixPath(path).parts[0] == "comparison_plots"
    )
    errors.extend(f"{relative}: {error}" for error in child_plot_errors)
    worksheet_available, worksheet_data, worksheet_error = (
        _read_trusted_artifact_bytes_rooted(
            root_pin,
            child_root,
            validation.artifacts,
            "worksheet.md",
        )
    )
    if worksheet_error:
        errors.append(f"{relative}: {worksheet_error}")
    report_available, report_error = _trusted_artifact_available_rooted(
        root_pin,
        child_root,
        validation.artifacts,
        "report.html",
    )
    if report_error:
        errors.append(f"{relative}: {report_error}")
    child_artifact_keys: list[str] = []
    if report_available:
        child_artifact_keys.append(_REPORT_ARTIFACT_KEY)
    if worksheet_available:
        child_artifact_keys.append(_WORKSHEET_ARTIFACT_KEY)
        if _contains_prediction_check(worksheet_data):
            child_artifact_keys.append(_PREDICTION_CHECK_ARTIFACT_KEY)
    child_evidence = completion_evidence_from_payloads(
        payload,
        expected_scenario_id=target_id,
        plot_count=len(child_plot_paths),
        artifact_keys=tuple(child_artifact_keys),
    )
    decision = evaluate_completion(completion_rule, child_evidence)
    try:
        _final_payload, final_manifest_digest = read_json_mapping_rooted(
            root_pin,
            (name, batch_name, "manifest.json"),
            description=f"saved child-batch manifest {batch_name}",
        )
    except _CompletionSnapshotBudgetExceeded:
        raise
    except CleanupSafetyError as exc:
        errors.append(f"{relative} changed while child evidence was read: {exc}")
        return False, tuple(errors)
    if not (
        hmac.compare_digest(final_manifest_digest, actual_digest)
        and hmac.compare_digest(final_manifest_digest, expected_manifest_digest)
    ):
        errors.append(f"{relative} changed while child evidence was read")
        return False, tuple(errors)
    if not decision.complete:
        errors.append(f"{relative} child batch fails {decision.primary_reason.value}")
        return False, tuple(errors)
    return True, tuple(errors)


def _sha256_regular_file_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    description: str,
) -> str:
    digest = hashlib.sha256()
    max_bytes = _completion_read_limit(
        root_pin,
        relative,
        MAX_COMPLETION_ARTIFACT_BYTES,
    )
    remaining = max_bytes
    size = 0
    with root_pin.open_regular_file(
        relative,
        description=description,
        max_bytes=max_bytes,
        allow_empty=True,
    ) as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, remaining + 1))
            if not chunk:
                break
            if len(chunk) > remaining:
                raise CleanupSafetyError(
                    f"{description} exceeded its safe size while read"
                )
            digest.update(chunk)
            remaining -= len(chunk)
            size += len(chunk)
    _account_completion_bytes(relative, size)
    return digest.hexdigest()


def read_json_mapping_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    description: str,
    allow_empty: bool = False,
) -> tuple[dict[str, Any], str]:
    max_bytes = _completion_read_limit(root_pin, relative, MAX_METADATA_BYTES)
    data = root_pin.read_regular_file(
        relative,
        description=description,
        max_bytes=max_bytes,
        allow_empty=False,
    )
    _account_completion_bytes(relative, len(data))
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CleanupSafetyError(f"{description} is malformed or unreadable: {exc}") from exc
    if not isinstance(payload, dict) or (not payload and not allow_empty):
        qualifier = "a JSON object" if allow_empty else "a non-empty JSON object"
        raise CleanupSafetyError(f"{description} must contain {qualifier}")
    return payload, hashlib.sha256(data).hexdigest()


def _completion_read_limit(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    per_file_limit: int,
) -> int:
    budget = _ACTIVE_COMPLETION_READ_BUDGET.get()
    if budget is None:
        return per_file_limit
    if relative not in budget.sizes:
        try:
            candidate_size = int(root_pin.lstat(relative).st_size)
        except OSError:
            candidate_size = 0
        if candidate_size > budget.max_bytes - budget.total_bytes:
            raise _CompletionSnapshotBudgetExceeded(
                "Saved-run completion content exceeds the cumulative "
                f"{budget.max_bytes}-byte read budget"
            )
    return budget.max_bytes_for(relative, per_file_limit)


def _account_completion_bytes(relative: tuple[str, ...], size: int) -> None:
    budget = _ACTIVE_COMPLETION_READ_BUDGET.get()
    if budget is not None:
        budget.account(relative, size)


def _trust_completion_digest(relative: tuple[str, ...], digest: str) -> None:
    budget = _ACTIVE_COMPLETION_READ_BUDGET.get()
    if budget is not None:
        budget.trust(relative, digest)


def _discard_trusted_completion_prefix(prefix: tuple[str, ...]) -> None:
    budget = _ACTIVE_COMPLETION_READ_BUDGET.get()
    if budget is not None:
        budget.discard_trusted_prefix(prefix)


def _revalidate_trusted_completion_files_rooted(
    root_pin: PinnedOutputRoot,
    budget: _CompletionReadBudget,
    *,
    marker_relative: tuple[str, ...],
) -> None:
    """Rehash every trusted input, with the governing marker checked last."""

    trusted = budget.trusted_digests
    ordered = [
        relative
        for relative in sorted(trusted)
        if relative != marker_relative
    ]
    if marker_relative in trusted:
        ordered.append(marker_relative)
    for relative in ordered:
        expected_digest = trusted[relative]
        actual_digest = _sha256_regular_file_rooted(
            root_pin,
            relative,
            description=f"saved-run snapshot input {'/'.join(relative)}",
        )
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise CleanupSafetyError(
                f"Saved-run artifact {'/'.join(relative)} changed before snapshot commit"
            )


def _safe_manifest_relative_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _identity_token(
    *,
    name: str,
    stat_result: os.stat_result,
    marker_name: str,
    marker_digest: str,
) -> str:
    return _hash_payload(
        {
            "name": name,
            "device": int(stat_result.st_dev),
            "inode": int(stat_result.st_ino),
            "mtime_ns": int(stat_result.st_mtime_ns),
            "marker": marker_name,
            "marker_sha256": marker_digest,
        }
    )
