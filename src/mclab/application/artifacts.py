"""Replay and provenance artifacts shared by CLI and desktop runs."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from mclab import __version__
from mclab.config import PROJECT_ROOT, resolve_project_path

MANIFEST_SCHEMA_VERSION = 1
REPLAY_SCHEMA_VERSION = 1


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
) -> Path:
    output = Path(output_path)
    model_path_value = config.get("model_path")
    model_path = resolve_project_path(model_path_value) if model_path_value else None
    license_path = _find_model_license(model_path)
    artifacts = {
        item.relative_to(output).as_posix(): _sha256(item)
        for item in sorted(output.rglob("*"))
        if item.is_file() and item.name != "manifest.json"
    }
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
            "sha256": _sha256(model_path) if model_path and model_path.is_file() else "",
            "license": _relative_or_absolute(license_path),
            "license_sha256": _sha256(license_path) if license_path else "",
        },
        "artifacts": artifacts,
        "replay": {
            "schema_version": REPLAY_SCHEMA_VERSION,
            "available": (output / "replay.npz").exists(),
        },
    }
    if run_kind:
        payload["run_kind"] = run_kind
    if error:
        payload["error"] = error[-2000:]
    target = output / "manifest.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def verify_manifest(output_path: str | Path) -> list[str]:
    output = Path(output_path)
    manifest_path = output / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"Could not read manifest: {exc}"]
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        errors.append("Unsupported manifest schema.")
    for relative, expected in dict(payload.get("artifacts", {})).items():
        path = output / relative
        if not path.is_file():
            errors.append(f"Missing artifact: {relative}")
        elif _sha256(path) != expected:
            errors.append(f"Artifact hash mismatch: {relative}")
    return errors


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
