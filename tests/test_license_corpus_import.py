from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import import_license_corpus as importer


def _canonical_json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def test_hosted_package_evidence_is_hash_bound_normalized_and_deduplicated(
    tmp_path: Path,
) -> None:
    license_text = "Example license  \r\nsecond line\r\n"
    normalized = importer._normalized_text(license_text)
    observation_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    targets: list[dict[str, object]] = []
    for runner_os in ("Linux", "Windows", "macOS"):
        artifact_name = f"licenses-{runner_os.lower()}"
        artifact = tmp_path / artifact_name
        artifact.mkdir()
        evidence = {
            "packages": [
                {
                    "license_text": license_text,
                    "name": "demo",
                    "notice_text": None,
                    "version": "1.0",
                }
            ]
        }
        raw = _canonical_json_bytes(evidence)
        (artifact / "python-licenses.json").write_bytes(raw)
        targets.append(
            {
                "artifact": {
                    "name": artifact_name,
                    "raw_evidence_sha256": hashlib.sha256(raw).hexdigest(),
                },
                "package_observations": [
                    {
                        "license_text_sha256": observation_digest,
                        "name": "demo",
                        "notice_text_sha256": None,
                        "version": "1.0",
                    }
                ],
                "runner_os": runner_os,
            }
        )

    texts = importer._evidence_texts(
        tmp_path,
        {"observed_targets": targets},
    )

    expected_payload = (normalized + "\n").encode("utf-8")
    assert texts == {hashlib.sha256(expected_payload).hexdigest(): expected_payload}

    evidence_path = tmp_path / "licenses-linux" / "python-licenses.json"
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
    with pytest.raises(importer.CorpusImportError, match="SHA-256"):
        importer._evidence_texts(tmp_path, {"observed_targets": targets})


def test_sdist_and_wheel_extractors_require_exact_archive_and_member_identity(
    tmp_path: Path,
) -> None:
    text = b"Example license\r\n"
    sdist = tmp_path / "demo.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        member = tarfile.TarInfo("demo-1.0/LICENSE.txt")
        member.size = len(text)
        archive.addfile(member, io.BytesIO(text))
    sdist_digest = hashlib.sha256(sdist.read_bytes()).hexdigest()

    assert importer._pyopengl_text(
        sdist,
        expected_sha256=sdist_digest,
        expected_member="demo-1.0/LICENSE.txt",
    ) == b"Example license\n"
    with pytest.raises(importer.CorpusImportError, match="must contain one"):
        importer._pyopengl_text(
            sdist,
            expected_sha256=sdist_digest,
            expected_member="demo-1.0/MISSING.txt",
        )

    wheel = tmp_path / "demo.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo-1.0.dist-info/licenses/LICENSE", text)
        archive.writestr("demo/__init__.py", b"")
    wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert importer._wheel_texts(
        wheel,
        expected_sha256=wheel_digest,
        expected_members=frozenset({"demo-1.0.dist-info/licenses/LICENSE"}),
        label="demo",
    ) == [b"Example license\n"]
    with pytest.raises(importer.CorpusImportError, match="package lock"):
        importer._wheel_texts(
            wheel,
            expected_sha256="0" * 64,
            expected_members=frozenset({"demo-1.0.dist-info/licenses/LICENSE"}),
            label="demo",
        )
