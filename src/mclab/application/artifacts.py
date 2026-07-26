"""Replay and provenance artifacts shared by CLI and desktop runs."""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO, Iterator

import numpy as np

from mclab import __version__
from mclab.application.batch_integrity import retrying_batch_operation_lock
from mclab.application import manifest_trust
from mclab.config import PROJECT_ROOT, resolve_project_path
from mclab.output_root import PinnedOutputRoot, pinned_output_root
from mclab.output_safety import (
    MAX_METADATA_BYTES,
    MAX_RUN_TREE_ENTRIES,
    CleanupOperationError,
    CleanupSafetyError,
    _stat_is_link_or_reparse,
)

MANIFEST_SCHEMA_VERSION = 1
REPLAY_SCHEMA_VERSION = 1
_TERMINAL_MANIFEST_STATUSES = frozenset({"completed", "stopped", "error"})
_MANIFEST_STATUSES = frozenset({"running", *_TERMINAL_MANIFEST_STATUSES})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_BATCH_TRANSIENT_PREFIX = ".mclab-batch-"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayFrame:
    time: float
    qpos: np.ndarray
    qvel: np.ndarray
    ctrl: np.ndarray
    semantic: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayArchive:
    time: np.ndarray
    qpos: np.ndarray
    qvel: np.ndarray
    ctrl: np.ndarray
    semantic: dict[str, np.ndarray]
    events: tuple[dict[str, Any], ...] = ()
    schema_version: int = REPLAY_SCHEMA_VERSION

    @property
    def frame_count(self) -> int:
        return int(self.time.shape[0])

    @property
    def duration(self) -> float:
        if self.frame_count < 2:
            return 0.0
        return float(self.time[-1] - self.time[0])

    def frame(self, index: int) -> ReplayFrame:
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        semantic = {key: float(values[index]) for key, values in self.semantic.items()}
        return ReplayFrame(
            time=float(self.time[index]),
            qpos=np.array(self.qpos[index], copy=True),
            qvel=np.array(self.qvel[index], copy=True),
            ctrl=np.array(self.ctrl[index], copy=True),
            semantic=semantic,
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": np.asarray([self.schema_version], dtype=np.int16),
            "time": np.asarray(self.time, dtype=np.float64),
            "qpos": np.asarray(self.qpos, dtype=np.float32),
            "qvel": np.asarray(self.qvel, dtype=np.float32),
            "ctrl": np.asarray(self.ctrl, dtype=np.float32),
            "semantic_keys": np.asarray(sorted(self.semantic), dtype=str),
            "events_json": np.asarray([json.dumps(self.events, ensure_ascii=False)], dtype=str),
        }
        for key, values in self.semantic.items():
            payload[f"semantic__{key}"] = np.asarray(values, dtype=np.float32)
        np.savez_compressed(target, **payload)
        return target

    @classmethod
    def load(cls, path: str | Path) -> "ReplayArchive":
        source = Path(path)
        try:
            with np.load(source, allow_pickle=False) as data:
                required = {"schema_version", "time", "qpos", "qvel", "ctrl"}
                missing = required - set(data.files)
                if missing:
                    raise ValueError(f"Replay is missing fields: {', '.join(sorted(missing))}")
                version = int(np.asarray(data["schema_version"]).reshape(-1)[0])
                if version != REPLAY_SCHEMA_VERSION:
                    raise ValueError(
                        f"Unsupported replay schema {version}; expected {REPLAY_SCHEMA_VERSION}."
                    )
                time = np.asarray(data["time"], dtype=np.float64)
                qpos = np.asarray(data["qpos"], dtype=np.float32)
                qvel = np.asarray(data["qvel"], dtype=np.float32)
                ctrl = np.asarray(data["ctrl"], dtype=np.float32)
                _validate_replay_shapes(time, qpos, qvel, ctrl)
                keys = [str(key) for key in data.get("semantic_keys", np.asarray([], dtype=str))]
                semantic = {
                    key: np.asarray(data[f"semantic__{key}"], dtype=np.float32) for key in keys
                }
                for key, values in semantic.items():
                    if values.shape != time.shape:
                        raise ValueError(f"Semantic replay field {key!r} has a mismatched length.")
                raw_events = str(np.asarray(data.get("events_json", ["[]"])).reshape(-1)[0])
                parsed_events = json.loads(raw_events)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read replay {source}: {exc}") from exc
        events = tuple(item for item in parsed_events if isinstance(item, dict))
        return cls(time=time, qpos=qpos, qvel=qvel, ctrl=ctrl, semantic=semantic, events=events)


class ReplayRecorder:
    """Downsample physics states to a compact fixed-rate replay."""

    def __init__(self, sample_hz: float = 60.0) -> None:
        if sample_hz <= 0:
            raise ValueError("Replay sample rate must be positive.")
        self.sample_hz = float(sample_hz)
        self._frames: list[ReplayFrame] = []
        self._events: list[dict[str, Any]] = []
        self._next_sample_time = 0.0
        self._last_seen_time: float | None = None

    def record(
        self,
        *,
        time: float,
        qpos: Any,
        qvel: Any,
        ctrl: Any,
        semantic: dict[str, float] | None = None,
    ) -> bool:
        timestamp = float(time)
        rewound = self._last_seen_time is not None and timestamp + 1e-12 < self._last_seen_time
        self._last_seen_time = timestamp
        if rewound:
            self._next_sample_time = timestamp
        if self._frames and not rewound and timestamp + 1e-12 < self._next_sample_time:
            return False
        self._frames.append(
            ReplayFrame(
                time=timestamp,
                qpos=np.asarray(qpos, dtype=np.float32).reshape(-1).copy(),
                qvel=np.asarray(qvel, dtype=np.float32).reshape(-1).copy(),
                ctrl=np.asarray(ctrl, dtype=np.float32).reshape(-1).copy(),
                semantic={key: float(value) for key, value in (semantic or {}).items()},
            )
        )
        interval = 1.0 / self.sample_hz
        self._next_sample_time += interval
        while self._next_sample_time <= timestamp + 1e-12:
            self._next_sample_time += interval
        return True

    def event(self, *, time: float, kind: str, name: str, value: Any = None) -> None:
        self._events.append({"time": float(time), "kind": kind, "name": name, "value": value})

    def clear(self) -> None:
        self._frames.clear()
        self._events.clear()
        self._next_sample_time = 0.0
        self._last_seen_time = None

    def archive(self) -> ReplayArchive:
        if not self._frames:
            return ReplayArchive(
                time=np.empty((0,), dtype=np.float64),
                qpos=np.empty((0, 0), dtype=np.float32),
                qvel=np.empty((0, 0), dtype=np.float32),
                ctrl=np.empty((0, 0), dtype=np.float32),
                semantic={},
                events=tuple(self._events),
            )
        qpos_size = self._frames[0].qpos.size
        qvel_size = self._frames[0].qvel.size
        ctrl_size = self._frames[0].ctrl.size
        if any(
            frame.qpos.size != qpos_size
            or frame.qvel.size != qvel_size
            or frame.ctrl.size != ctrl_size
            for frame in self._frames
        ):
            raise ValueError("Replay state vector sizes changed during the run.")
        semantic_keys = sorted(set().union(*(frame.semantic.keys() for frame in self._frames)))
        semantic = {
            key: np.asarray(
                [frame.semantic.get(key, np.nan) for frame in self._frames], dtype=np.float32
            )
            for key in semantic_keys
        }
        return ReplayArchive(
            time=np.asarray([frame.time for frame in self._frames], dtype=np.float64),
            qpos=np.stack([frame.qpos for frame in self._frames]),
            qvel=np.stack([frame.qvel for frame in self._frames]),
            ctrl=np.stack([frame.ctrl for frame in self._frames]),
            semantic=semantic,
            events=tuple(self._events),
        )


def write_manifest(
    output_path: str | Path,
    *,
    scenario_id: str,
    status: str,
    config: dict[str, Any],
    config_path: str | Path | None = None,
    seed: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    run_kind: str = "",
    error: str = "",
    handoff_token_sha256: str = "",
    untrusted_artifacts: tuple[str, ...] = (),
    expected_root_identity: dict[str, int | str] | None = None,
) -> Path:
    output = Path(output_path)
    try:
        with pinned_output_root(output, allowed_root=output) as (
            display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Manifest output directory is missing")
            root_pin.validate_directory((), description="manifest output")
            manifest_trust.validate_expected_root_identity(root_pin, expected_root_identity)
            operation_lock = (
                retrying_batch_operation_lock(root_pin)
                if scenario_id == "batch.all"
                else root_pin.operation_lock()
            )
            with operation_lock:
                expected_manifest = _assert_manifest_transition_allowed(
                    root_pin, requested_status=status
                )
                omitted_artifacts = manifest_trust.validate_running_document_deferral(
                    untrusted_artifacts, status=status
                )
                strict_batch_terminal = (
                    status in _TERMINAL_MANIFEST_STATUSES
                    and scenario_id.startswith("batch.")
                )
                if strict_batch_terminal and status != "error" and error:
                    raise CleanupSafetyError(
                        "Batch error detail is only valid for terminal error status"
                    )
                artifacts = (
                    _inventory_artifacts_rooted(root_pin, strict=True)
                    if strict_batch_terminal
                    else _inventory_artifacts_rooted(root_pin)
                )
                for relative in omitted_artifacts:
                    artifacts.pop(relative, None)
                model_path_value = config.get("model_path")
                model_path = resolve_project_path(model_path_value) if model_path_value else None
                license_path = _find_model_license(model_path)
                payload = {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "scenario_id": scenario_id,
                    "status": status,
                    "started_at": started_at or _utc_now(),
                    "finished_at": finished_at or _utc_now(),
                    "config": {
                        "path": Path(config_path).as_posix() if config_path else "",
                        "seed": seed,
                        "resolved": config,
                    },
                    "runtime": {
                        "mclab": __version__,
                        "mujoco": _module_version("mujoco"),
                        "python": platform.python_version(),
                        "os": platform.platform(),
                    },
                    "model": {
                        "path": _relative_or_absolute(model_path),
                        "sha256": (
                            _sha256(model_path) if model_path and model_path.is_file() else ""
                        ),
                        "license": _relative_or_absolute(license_path),
                        "license_sha256": _sha256(license_path) if license_path else "",
                    },
                    "artifacts": artifacts,
                    "replay": {
                        "schema_version": REPLAY_SCHEMA_VERSION,
                        "available": "replay.npz" in artifacts,
                    },
                }
                if run_kind:
                    payload["run_kind"] = run_kind
                if error or (status == "error" and scenario_id.startswith("batch.")):
                    payload["error"] = (
                        error or "The comparison batch failed without an error detail."
                    )[-2000:]
                preserved_handoff_hash = _preserved_running_handoff_hash(
                    expected_manifest,
                    scenario_id=scenario_id,
                    status=status,
                    supplied=handoff_token_sha256,
                )
                if preserved_handoff_hash:
                    payload["handoff_token_sha256"] = preserved_handoff_hash
                encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
                if len(encoded) > MAX_METADATA_BYTES:
                    raise CleanupSafetyError(
                        "Manifest exceeds the schema-1 metadata read limit"
                    )
                _assert_manifest_unchanged(root_pin, expected_manifest)
                try:
                    root_pin.replace_regular_file(("manifest.json",), encoded)
                    root_pin.assert_transaction_boundaries()
                except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
                    if not _desired_manifest_is_visible(root_pin, encoded):
                        raise
                    LOGGER.warning(
                        "Manifest replacement reached the requested state before a "
                        "post-commit check failed; preserving the visible publication: %s",
                        exc,
                    )
                return display_root / "manifest.json"
    except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
        raise RuntimeError(f"Could not publish manifest safely: {exc}") from exc


def verify_manifest(output_path: str | Path) -> list[str]:
    output = Path(output_path)
    try:
        with pinned_output_root(output, allowed_root=output) as (
            _display_root,
            root_exists,
            root_pin,
        ):
            if not root_exists or root_pin is None:
                raise CleanupSafetyError("Manifest output directory is missing")
            root_pin.validate_directory((), description="manifest output")
            with root_pin.operation_lock():
                manifest_bytes = root_pin.read_regular_file(
                    ("manifest.json",),
                    description="manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                )
                payload = json.loads(manifest_bytes.decode("utf-8"))
                errors = _verify_manifest_payload_rooted(root_pin, payload)
                final_manifest = root_pin.read_regular_file(
                    ("manifest.json",),
                    description="manifest",
                    max_bytes=MAX_METADATA_BYTES,
                    allow_empty=False,
                )
                if final_manifest != manifest_bytes:
                    errors.append("Manifest changed during verification.")
                root_pin.assert_read_boundary()
                return errors
    except (
        CleanupOperationError,
        CleanupSafetyError,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        return [f"Could not read manifest: {exc}"]


def verify_terminal_batch_output(
    output_path: str | Path,
    *,
    expected_status: str,
) -> list[str]:
    """Strictly verify one immutable batch tree and its exact artifact set."""

    from mclab.application.batch_integrity import verify_terminal_batch_output as verify

    return verify(output_path, expected_status=expected_status)


def _verify_manifest_payload_rooted(
    root_pin: PinnedOutputRoot,
    payload: object,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["Invalid manifest payload."]
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        errors.append("Unsupported manifest schema.")
    raw_artifacts = payload.get("artifacts", {})
    if not isinstance(raw_artifacts, dict):
        return ["Invalid manifest artifacts."]
    for relative, expected in raw_artifacts.items():
        if not _safe_artifact_relative(relative):
            errors.append(f"Unsafe artifact path: {relative}")
            continue
        parts = tuple(PurePosixPath(relative).parts)
        try:
            artifact_stat = root_pin.lstat(parts)
        except (CleanupOperationError, CleanupSafetyError, OSError):
            errors.append(f"Missing artifact: {relative}")
            continue
        if _stat_is_link_or_reparse(artifact_stat) or not stat.S_ISREG(artifact_stat.st_mode):
            errors.append(f"Missing artifact: {relative}")
            continue
        try:
            actual = _sha256_rooted(
                root_pin,
                parts,
                description=f"artifact {relative}",
                expected_size=int(artifact_stat.st_size),
            )
        except (CleanupOperationError, CleanupSafetyError, OSError):
            errors.append(f"Missing artifact: {relative}")
            continue
        if actual != expected:
            errors.append(f"Artifact hash mismatch: {relative}")
    return errors


def _assert_manifest_transition_allowed(
    root_pin: PinnedOutputRoot,
    *,
    requested_status: str,
) -> bytes | None:
    if requested_status not in _MANIFEST_STATUSES:
        raise CleanupSafetyError(f"Unsupported manifest status: {requested_status!r}")
    if not root_pin.lexists(("manifest.json",)):
        return None
    try:
        existing_bytes = root_pin.read_regular_file(
            ("manifest.json",),
            description="existing manifest",
            max_bytes=MAX_METADATA_BYTES,
            allow_empty=False,
        )
        existing = json.loads(existing_bytes.decode("utf-8"))
    except (CleanupOperationError, CleanupSafetyError, OSError, UnicodeError, ValueError) as exc:
        raise CleanupSafetyError("Existing manifest is not safely readable") from exc
    if not isinstance(existing, dict):
        raise CleanupSafetyError("Existing manifest payload is invalid")
    if existing.get("status") in _TERMINAL_MANIFEST_STATUSES:
        raise CleanupSafetyError(
            f"A terminal manifest is immutable and cannot be reopened as {requested_status!r}"
        )
    if (
        type(existing.get("schema_version")) is not int
        or existing.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or existing.get("status") != "running"
    ):
        raise CleanupSafetyError(
            "Only an existing schema-1 running manifest may be advanced or refreshed"
        )
    return existing_bytes


def _assert_manifest_unchanged(
    root_pin: PinnedOutputRoot,
    expected_manifest: bytes | None,
) -> None:
    """Refuse to overwrite a marker changed after the transition check."""

    if expected_manifest is None:
        if root_pin.lexists(("manifest.json",)):
            raise CleanupSafetyError("Manifest appeared during publication")
        return
    try:
        current = root_pin.read_regular_file(
            ("manifest.json",),
            description="existing manifest",
            max_bytes=MAX_METADATA_BYTES,
            allow_empty=False,
        )
    except (CleanupOperationError, CleanupSafetyError, OSError) as exc:
        raise CleanupSafetyError("Manifest changed during publication") from exc
    if current != expected_manifest:
        raise CleanupSafetyError("Manifest changed during publication")


def _desired_manifest_is_visible(
    root_pin: PinnedOutputRoot,
    expected: bytes,
) -> bool:
    """Reconcile an exception only when the exact marker is still attached."""

    try:
        root_pin.assert_current()
        current = root_pin.read_regular_file(
            ("manifest.json",),
            description="committed manifest",
            max_bytes=MAX_METADATA_BYTES,
            allow_empty=False,
        )
    except (CleanupOperationError, CleanupSafetyError, OSError):
        return False
    return current == expected


def _preserved_running_handoff_hash(
    existing_manifest: bytes | None,
    *,
    scenario_id: str,
    status: str,
    supplied: str,
) -> str:
    """Carry authenticated desktop ownership through every running refresh."""

    if supplied and _SHA256_PATTERN.fullmatch(supplied) is None:
        raise CleanupSafetyError("The batch handoff digest is invalid")
    if status != "running" or scenario_id != "batch.all":
        if supplied:
            raise CleanupSafetyError(
                "Batch handoff metadata is valid only on a running batch.all manifest"
            )
        return ""
    existing = ""
    if existing_manifest is not None:
        try:
            payload = json.loads(existing_manifest.decode("utf-8"))
        except (UnicodeError, ValueError, TypeError) as exc:
            raise CleanupSafetyError("Existing batch handoff metadata is invalid") from exc
        if isinstance(payload, dict) and "handoff_token_sha256" in payload:
            value = payload["handoff_token_sha256"]
            if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
                raise CleanupSafetyError("Existing batch handoff digest is invalid")
            existing = value
    if supplied and existing and supplied != existing:
        raise CleanupSafetyError("The batch handoff digest cannot be changed")
    return supplied or existing


def _inventory_artifacts_rooted(
    root_pin: PinnedOutputRoot,
    *,
    strict: bool = False,
) -> dict[str, str]:
    regular_files: list[tuple[str, tuple[str, ...], int]] = []
    directories: list[tuple[str, ...]] = [()]
    discovered_directories: list[str] = []
    entries_seen = 0
    while directories:
        directory = directories.pop()
        with _pinned_directory_chain(root_pin, directory):
            remaining_entries = MAX_RUN_TREE_ENTRIES - entries_seen
            names = root_pin.list_names(directory, max_entries=remaining_entries)
            for name in sorted(names):
                entries_seen += 1
                if entries_seen > MAX_RUN_TREE_ENTRIES:
                    raise CleanupSafetyError(
                        f"Manifest output contains more than {MAX_RUN_TREE_ENTRIES} entries"
                    )
                child = (*directory, name)
                relative = PurePosixPath(*child).as_posix()
                if relative == "manifest.json":
                    continue
                child_stat = root_pin.lstat(child)
                if _stat_is_link_or_reparse(child_stat):
                    if strict:
                        raise CleanupSafetyError(
                            f"Terminal batch contains a link or reparse point: {relative}"
                        )
                    continue
                if strict and any(
                    part.startswith(_BATCH_TRANSIENT_PREFIX) for part in child
                ):
                    raise CleanupSafetyError(
                        f"Terminal batch contains a live transient marker: {relative}"
                    )
                if stat.S_ISREG(child_stat.st_mode):
                    if _safe_artifact_relative(relative):
                        regular_files.append((relative, child, int(child_stat.st_size)))
                    elif strict:
                        raise CleanupSafetyError(
                            f"Terminal batch contains an unsafe artifact path: {relative}"
                        )
                    continue
                if stat.S_ISDIR(child_stat.st_mode):
                    if strict and not _safe_artifact_relative(relative):
                        raise CleanupSafetyError(
                            f"Terminal batch contains an unsafe directory path: {relative}"
                        )
                    if root_pin.is_mount_point(child):
                        if strict:
                            raise CleanupSafetyError(
                                f"Terminal batch contains a mount point: {relative}"
                            )
                        continue
                    discovered_directories.append(relative)
                    directories.append(child)
                    continue
                if strict:
                    raise CleanupSafetyError(
                        f"Terminal batch contains a special filesystem entry: {relative}"
                    )

    artifacts: dict[str, str] = {}
    for relative, parts, expected_size in sorted(regular_files):
        artifacts[relative] = _sha256_rooted(
            root_pin,
            parts,
            description=f"artifact {relative}",
            expected_size=expected_size,
        )
    if strict:
        for relative in discovered_directories:
            prefix = f"{relative}/"
            if not any(artifact.startswith(prefix) for artifact in artifacts):
                raise CleanupSafetyError(
                    f"Terminal batch contains an unlisted empty directory: {relative}"
                )
    return artifacts


def _sha256_rooted(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
    *,
    description: str,
    expected_size: int,
) -> str:
    if expected_size < 0:
        raise CleanupSafetyError(f"{description} has an invalid size")
    digest = hashlib.sha256()
    bytes_read = 0
    with _pinned_directory_chain(root_pin, relative[:-1]):
        file_stat = root_pin.lstat(relative)
        if (
            _stat_is_link_or_reparse(file_stat)
            or not stat.S_ISREG(file_stat.st_mode)
            or int(file_stat.st_size) != expected_size
        ):
            raise CleanupSafetyError(f"{description} changed or has an unsafe type")
        with root_pin.open_regular_file(
            relative,
            description=description,
            max_bytes=expected_size,
        ) as stream:
            while bytes_read <= expected_size:
                remaining = expected_size + 1 - bytes_read
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                bytes_read += len(chunk)
    if bytes_read != expected_size:
        raise CleanupSafetyError(f"{description} changed size while hashed")
    return digest.hexdigest()


@contextmanager
def _pinned_directory_chain(
    root_pin: PinnedOutputRoot,
    relative: tuple[str, ...],
) -> Iterator[None]:
    """Retain every ancestor so no Windows reparse point can enter mid-read."""

    with ExitStack() as stack:
        for index in range(1, len(relative) + 1):
            prefix = relative[:index]
            stack.enter_context(
                root_pin.scoped_directory_pin(
                    prefix,
                    description=f"artifact directory {'/'.join(prefix)}",
                )
            )
        yield


def _safe_artifact_relative(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    if PureWindowsPath(value).drive:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def legacy_replay_reason(output_path: str | Path) -> str:
    output = Path(output_path)
    if (output / "replay.npz").exists():
        try:
            ReplayArchive.load(output / "replay.npz")
        except (EOFError, KeyError, OSError, ValueError) as exc:
            return str(exc)
        return ""
    if (output / "states.npz").exists() or (output / "log.csv").exists():
        return "This legacy run has metrics but no complete qpos/qvel/ctrl recording."
    return "This folder does not contain a supported MCLab recording."


def replay_index_reason(output_path: str | Path) -> str:
    """Validate an NPZ index and schema without decompressing every recorded frame."""

    source = Path(output_path) / "replay.npz"
    if not source.is_file():
        return legacy_replay_reason(output_path)
    return replay_index_reason_from_stream(source, source_label=str(source))


def replay_index_reason_from_stream(
    source: str | Path | BinaryIO,
    *,
    source_label: str = "replay.npz",
) -> str:
    """Validate a replay index from a caller-owned safe stream."""

    try:
        with np.load(source, allow_pickle=False) as data:
            required = {"schema_version", "time", "qpos", "qvel", "ctrl"}
            missing = required - set(data.files)
            if missing:
                return f"Replay is missing fields: {', '.join(sorted(missing))}"
            version = int(np.asarray(data["schema_version"]).reshape(-1)[0])
            if version != REPLAY_SCHEMA_VERSION:
                return f"Unsupported replay schema {version}; expected {REPLAY_SCHEMA_VERSION}."
    except (EOFError, KeyError, OSError, TypeError, ValueError) as exc:
        return f"Could not read replay {source_label}: {exc}"
    return ""


def _validate_replay_shapes(
    time: np.ndarray, qpos: np.ndarray, qvel: np.ndarray, ctrl: np.ndarray
) -> None:
    if time.ndim != 1:
        raise ValueError("Replay time must be one-dimensional.")
    frame_count = time.shape[0]
    for name, values in (("qpos", qpos), ("qvel", qvel), ("ctrl", ctrl)):
        if values.ndim != 2 or values.shape[0] != frame_count:
            raise ValueError(f"Replay {name} must be a frame-by-value matrix.")
    if frame_count > 1 and np.any(np.diff(time) < 0):
        raise ValueError("Replay timestamps are not monotonic.")


def _find_model_license(model_path: Path | None) -> Path | None:
    if model_path is None:
        return None
    for parent in (model_path.parent, *model_path.parents):
        for name in ("LICENSE", "LICENSE.txt", "COPYING"):
            candidate = parent / name
            if candidate.is_file():
                return candidate
        if parent == PROJECT_ROOT:
            break
    return None


def _module_version(module_name: str) -> str:
    try:
        module = __import__(module_name)
    except Exception:
        return "unavailable"
    return str(getattr(module, "__version__", "unknown"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_or_absolute(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
