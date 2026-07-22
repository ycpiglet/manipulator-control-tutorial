"""Shared, bounded-cost Panda asset readiness helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from mclab.application.assets import (
    AssetSafetyError,
    AssetVerificationError,
    verify_assets,
)
from mclab.application.panda_runtime_manifest import PANDA_RUNTIME_MANIFEST
from mclab.config import PROJECT_ROOT

PANDA_ASSET_ROOT = Path("third_party/mujoco_menagerie/franka_emika_panda")
PANDA_MODEL_MEMBERS = frozenset(
    relative
    for relative, _size, _digest in PANDA_RUNTIME_MANIFEST
    if PurePosixPath(relative).suffix.casefold() == ".xml"
)


@dataclass(frozen=True)
class PandaAssetReadiness:
    """One classified result suitable for learner-facing readiness surfaces."""

    code: str
    detail: str
    file_count: int = 0
    total_bytes: int = 0

    @property
    def ready(self) -> bool:
        return self.code == "ready"


def is_panda_model_path(
    model_path: str | Path,
    *,
    root: str | Path = PROJECT_ROOT,
) -> bool:
    """Return whether a model path lexically belongs to the managed Panda tree."""

    project_root = Path(root)
    candidate = Path(model_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = Path(os.path.abspath(candidate))
    panda_root = Path(os.path.abspath(project_root / PANDA_ASSET_ROOT))
    try:
        candidate.relative_to(panda_root)
    except ValueError:
        return False
    return True


def resolve_panda_model_member(
    model_path: str | Path,
    *,
    root: str | Path = PROJECT_ROOT,
) -> Path:
    """Resolve one configured Panda path only when it is a tracked XML model."""

    project_root = Path(root)
    candidate = Path(model_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = Path(os.path.abspath(candidate))
    panda_root = Path(os.path.abspath(project_root / PANDA_ASSET_ROOT))
    try:
        relative = candidate.relative_to(panda_root)
    except ValueError as exc:
        raise ValueError(f"Panda model path is outside the managed runtime tree: {model_path}") from exc
    relative_posix = relative.as_posix()
    if relative_posix not in PANDA_MODEL_MEMBERS:
        allowed = ", ".join(sorted(PANDA_MODEL_MEMBERS))
        raise ValueError(
            "Panda model_path must name a tracked XML model "
            f"({allowed}): {model_path}"
        )
    return relative


def panda_asset_readiness(root: str | Path = PROJECT_ROOT) -> PandaAssetReadiness:
    """Return a cached verification result for high-fan-out readiness views."""

    normalized_root = os.path.normcase(os.path.abspath(Path(root)))
    return _cached_panda_asset_readiness(normalized_root)


@lru_cache(maxsize=8)
def _cached_panda_asset_readiness(root: str) -> PandaAssetReadiness:
    return check_panda_asset_readiness(root)


def check_panda_asset_readiness(root: str | Path = PROJECT_ROOT) -> PandaAssetReadiness:
    """Verify and classify the Panda tree without using the UI readiness cache."""

    try:
        verification = verify_assets(root=Path(root))
    except ValueError as exc:
        return classify_panda_asset_failure(root, exc)
    return PandaAssetReadiness(
        "ready",
        verification.target.as_posix(),
        file_count=verification.file_count,
        total_bytes=verification.total_bytes,
    )


def classify_panda_asset_failure(
    root: str | Path,
    error: ValueError,
) -> PandaAssetReadiness:
    """Classify one verifier failure without running the expensive check again."""

    target = Path(os.path.abspath(Path(root) / PANDA_ASSET_ROOT))
    missing_tree_error = (
        isinstance(error, AssetVerificationError)
        and not isinstance(error, AssetSafetyError)
        and error.target == target
        and error.issues == ("runtime tree is missing",)
    )
    if missing_tree_error:
        try:
            os.lstat(target)
        except FileNotFoundError:
            return PandaAssetReadiness("missing_asset", target.as_posix())
        except OSError as inspection_error:
            return PandaAssetReadiness(
                "invalid_asset",
                f"Could not inspect {target}: {inspection_error}",
            )
    return PandaAssetReadiness("invalid_asset", str(error))


def clear_panda_asset_readiness_cache() -> None:
    """Clear cached UI readiness after an in-process asset repair."""

    _cached_panda_asset_readiness.cache_clear()
