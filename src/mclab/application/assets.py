"""Install pinned third-party runtime assets with checksum verification."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from mclab.config import PROJECT_ROOT

MENAGERIE_COMMIT = "71f066ad0be9cd271f7ed58c030243ef157af9f4"
MENAGERIE_ARCHIVE_URL = (
    f"https://github.com/google-deepmind/mujoco_menagerie/archive/{MENAGERIE_COMMIT}.tar.gz"
)
MENAGERIE_ARCHIVE_SHA256 = "000b9f51abb404efb1de2b88b3c738674c472a85b6c4143168859abc4c98d423"
PANDA_PREFIX = f"mujoco_menagerie-{MENAGERIE_COMMIT}/franka_emika_panda/"


def install_assets(
    root: str | Path = PROJECT_ROOT,
    *,
    force: bool = False,
    archive_path: str | Path | None = None,
) -> Path:
    """Install only the pinned Panda model from the verified Menagerie archive."""

    project_root = Path(root)
    target = project_root / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
    if (target / "scene.xml").is_file() and not force:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mclab-assets-") as temp_dir:
        temp = Path(temp_dir)
        archive = Path(archive_path) if archive_path else temp / "menagerie.tar.gz"
        if archive_path is None:
            _download(MENAGERIE_ARCHIVE_URL, archive)
        actual_hash = _sha256(archive)
        if actual_hash != MENAGERIE_ARCHIVE_SHA256:
            raise ValueError(
                "MuJoCo Menagerie archive checksum mismatch: "
                f"expected {MENAGERIE_ARCHIVE_SHA256}, got {actual_hash}."
            )
        staging = temp / "franka_emika_panda"
        _extract_panda(archive, staging)
        if not (staging / "scene.xml").is_file() or not (staging / "LICENSE").is_file():
            raise ValueError("Verified archive did not contain the Panda scene and license.")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staging, target)
    return target


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "MCLab-assets/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download MCLab assets from {url}: {exc}") from exc


def _extract_panda(archive: Path, staging: Path) -> None:
    staging.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.name.startswith(PANDA_PREFIX) or not member.isfile():
                continue
            relative = Path(member.name.removeprefix(PANDA_PREFIX))
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe asset archive member: {member.name}")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                continue
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
