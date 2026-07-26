"""Import exact reviewed license evidence into a content-addressed text corpus.

This is a bounded provenance importer for LIC-01B.  It accepts only the three
SUP-01 package-license artifacts already pinned by LIC-01A, repository-local
project/font texts, the pinned Panda license, and exact locked supplemental
Python distributions.  It does not fetch network content, interpret license
terms, or make a distribution decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / ".agents/supply_chain/license-inventory.json"
IMPORT_MANIFEST_PATH = ROOT / ".agents/supply_chain/license-corpus-import-v1.json"
CORPUS_DIRECTORY = ROOT / "third_party/licenses/corpus"
MAX_INPUT_BYTES = 2 * 1024 * 1024
EXPECTED_REPLAY_COMMAND = [
    "python",
    "scripts/import_license_corpus.py",
    "--evidence-root",
    "<directory-containing-the-three-SUP-01-artifacts>",
    "--panda-license",
    "<pinned-panda-license>",
    "--pyopengl-sdist",
    "<locked-pyopengl-sdist>",
    "--exceptiongroup-wheel",
    "<locked-exceptiongroup-wheel>",
    "--setuptools-wheel",
    "<locked-setuptools-wheel>",
]
EXPECTED_SUPPLEMENTAL_KINDS = {
    "exceptiongroup": "wheel",
    "panda-runtime": "file",
    "pyopengl": "sdist-tar-gz",
    "setuptools": "wheel",
}


class CorpusImportError(RuntimeError):
    """Raised when provisional evidence cannot be imported exactly."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if len(payload) > MAX_INPUT_BYTES:
        raise CorpusImportError(f"JSON evidence exceeds {MAX_INPUT_BYTES} bytes: {path}")

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise CorpusImportError(f"duplicate JSON key {key!r}: {path}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CorpusImportError(f"non-finite JSON number {token}: {path}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusImportError(f"malformed JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CorpusImportError(f"JSON evidence root must be an object: {path}")
    return value


def _import_manifest() -> dict[str, dict[str, object]]:
    document = _strict_json(IMPORT_MANIFEST_PATH)
    if set(document) != {
        "contract_id",
        "package_evidence_inventory",
        "raw_evidence_retention",
        "replay_command",
        "schema_version",
        "supplemental_inputs",
    }:
        raise CorpusImportError("license corpus import manifest keys drift")
    if document.get("schema_version") != 1 or document.get("contract_id") != "LIC-01B":
        raise CorpusImportError("license corpus import manifest identity drift")
    if document.get("package_evidence_inventory") != (
        ".agents/supply_chain/license-inventory.json"
    ):
        raise CorpusImportError("license corpus package-evidence provenance drift")
    if document.get("raw_evidence_retention") != "open-owner-decision-required":
        raise CorpusImportError("raw evidence retention must remain an explicit open decision")
    if document.get("replay_command") != EXPECTED_REPLAY_COMMAND:
        raise CorpusImportError("license corpus replay command drift")
    supplements = document.get("supplemental_inputs")
    if not isinstance(supplements, dict) or set(supplements) != set(
        EXPECTED_SUPPLEMENTAL_KINDS
    ):
        raise CorpusImportError("license corpus supplemental input coverage drift")
    normalized: dict[str, dict[str, object]] = {}
    for label, expected_kind in EXPECTED_SUPPLEMENTAL_KINDS.items():
        record = supplements.get(label)
        if not isinstance(record, dict) or set(record) != {
            "archive_sha256",
            "kind",
            "license_members",
        }:
            raise CorpusImportError(f"{label} import manifest record is malformed")
        digest = record.get("archive_sha256")
        members = record.get("license_members")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise CorpusImportError(f"{label} import manifest SHA-256 is invalid")
        if record.get("kind") != expected_kind:
            raise CorpusImportError(f"{label} import manifest kind drift")
        if (
            not isinstance(members, list)
            or not members
            or any(not isinstance(member, str) or not member for member in members)
            or len(members) != len(set(members))
        ):
            raise CorpusImportError(f"{label} import manifest members are invalid")
        normalized[label] = {
            "archive_sha256": digest,
            "kind": expected_kind,
            "license_members": frozenset(members),
        }
    return normalized


def _normalized_text(value: str) -> str:
    unix = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in unix.split("\n")).strip()
    if not normalized:
        raise CorpusImportError("license corpus text must not be empty")
    if "\x00" in normalized:
        raise CorpusImportError("license corpus text must not contain NUL")
    return normalized


def _storage_payload(value: str) -> bytes:
    return (_normalized_text(value) + "\n").encode("utf-8")


def _expected_targets(inventory: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    targets = inventory.get("observed_targets")
    if not isinstance(targets, list) or len(targets) != 3:
        raise CorpusImportError("LIC-01A must contain exactly three observed targets")
    result: dict[str, Mapping[str, object]] = {}
    for target in targets:
        if not isinstance(target, dict):
            raise CorpusImportError("LIC-01A observed target must be an object")
        runner_os = target.get("runner_os")
        if not isinstance(runner_os, str) or runner_os in result:
            raise CorpusImportError("LIC-01A observed runner identity is invalid")
        result[runner_os] = target
    if set(result) != {"Linux", "Windows", "macOS"}:
        raise CorpusImportError("LIC-01A Linux/Windows/macOS observations are required")
    return result


def _accepted_observations(target: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    packages = target.get("package_observations")
    if not isinstance(packages, list):
        raise CorpusImportError("LIC-01A package observations are missing")
    result: dict[str, Mapping[str, object]] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise CorpusImportError("LIC-01A package observation must be an object")
        name = package.get("name")
        if not isinstance(name, str) or name in result:
            raise CorpusImportError("LIC-01A package observation identity is invalid")
        result[name] = package
    return result


def _evidence_texts(
    evidence_root: Path, inventory: Mapping[str, object]
) -> dict[str, bytes]:
    texts: dict[str, bytes] = {}
    for runner_os, target in sorted(_expected_targets(inventory).items()):
        artifact = target.get("artifact")
        if not isinstance(artifact, dict):
            raise CorpusImportError(f"LIC-01A {runner_os} artifact provenance is missing")
        artifact_name = artifact.get("name")
        raw_sha256 = artifact.get("raw_evidence_sha256")
        if not isinstance(artifact_name, str) or not isinstance(raw_sha256, str):
            raise CorpusImportError(f"LIC-01A {runner_os} artifact provenance is invalid")
        evidence_path = evidence_root / artifact_name / "python-licenses.json"
        raw = evidence_path.read_bytes()
        if _sha256(raw) != raw_sha256:
            raise CorpusImportError(f"{runner_os} evidence SHA-256 does not match LIC-01A")
        document = _strict_json(evidence_path)
        packages = document.get("packages")
        if not isinstance(packages, list):
            raise CorpusImportError(f"{runner_os} evidence packages are missing")
        accepted = _accepted_observations(target)
        if len(packages) != len(accepted):
            raise CorpusImportError(f"{runner_os} evidence package count drift")
        seen: set[str] = set()
        for package in packages:
            if not isinstance(package, dict):
                raise CorpusImportError(f"{runner_os} evidence package must be an object")
            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not isinstance(version, str) or name in seen:
                raise CorpusImportError(f"{runner_os} evidence package identity is invalid")
            seen.add(name)
            expected = accepted.get(name)
            if expected is None or expected.get("version") != version:
                raise CorpusImportError(f"{runner_os} package coverage drift for {name}")
            for field, digest_field in (
                ("license_text", "license_text_sha256"),
                ("notice_text", "notice_text_sha256"),
            ):
                value = package.get(field)
                expected_digest = expected.get(digest_field)
                if value is None:
                    if expected_digest is not None:
                        raise CorpusImportError(
                            f"{runner_os} missing accepted {field} for {name}"
                        )
                    continue
                if not isinstance(value, str):
                    raise CorpusImportError(f"{runner_os} invalid {field} for {name}")
                normalized = _normalized_text(value)
                observation_digest = _sha256(normalized.encode("utf-8"))
                if observation_digest != expected_digest:
                    raise CorpusImportError(
                        f"{runner_os} accepted {field} digest drift for {name}"
                    )
                payload = _storage_payload(normalized)
                texts.setdefault(_sha256(payload), payload)
    return texts


def _panda_text(path: Path, *, expected_sha256: str) -> bytes:
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise CorpusImportError("Panda license does not match the pinned runtime manifest")
    return _storage_payload(raw.decode("utf-8"))


def _local_text(path: str, expected: Mapping[str, object]) -> bytes:
    source = ROOT / path
    raw = source.read_bytes()
    if expected.get("path") != path or expected.get("sha256") != _sha256(raw):
        raise CorpusImportError(f"repository-local license provenance drift: {path}")
    return _storage_payload(raw.decode("utf-8"))


def _pyopengl_text(
    path: Path,
    *,
    expected_sha256: str,
    expected_member: str,
) -> bytes:
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise CorpusImportError("PyOpenGL sdist does not match the package lock")
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = [member for member in archive if member.name == expected_member]
            if len(members) != 1 or not members[0].isfile():
                raise CorpusImportError("PyOpenGL sdist must contain one regular license.txt")
            if members[0].size > MAX_INPUT_BYTES:
                raise CorpusImportError("PyOpenGL license exceeds the bounded text size")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise CorpusImportError("PyOpenGL license could not be read")
            payload = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, tarfile.TarError) as exc:
        raise CorpusImportError(f"invalid PyOpenGL sdist: {exc}") from exc
    if len(payload) > MAX_INPUT_BYTES:
        raise CorpusImportError("PyOpenGL license exceeds the bounded text size")
    return _storage_payload(payload.decode("utf-8"))


def _wheel_texts(
    path: Path,
    *,
    expected_sha256: str,
    expected_members: frozenset[str],
    label: str,
) -> list[bytes]:
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise CorpusImportError(f"{label} wheel does not match the package lock")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise CorpusImportError(f"{label} wheel has duplicate member names")
            actual = {name for name in names if name in expected_members}
            if actual != expected_members:
                raise CorpusImportError(f"{label} wheel license member coverage drift")
            payloads: list[bytes] = []
            for member_name in sorted(expected_members):
                member = archive.getinfo(member_name)
                if member.is_dir() or member.file_size > MAX_INPUT_BYTES:
                    raise CorpusImportError(
                        f"{label} wheel license member is invalid: {member_name}"
                    )
                payload = archive.read(member)
                if len(payload) > MAX_INPUT_BYTES:
                    raise CorpusImportError(
                        f"{label} wheel license exceeds bounded text size: {member_name}"
                    )
                payloads.append(_storage_payload(payload.decode("utf-8")))
    except (OSError, zipfile.BadZipFile) as exc:
        raise CorpusImportError(f"invalid {label} wheel: {exc}") from exc
    return payloads


def _write_exact(path: Path, payload: bytes) -> None:
    expected_name = f"{_sha256(payload)}.txt"
    if path.name != expected_name:
        raise CorpusImportError(f"content-addressed corpus name mismatch: {path}")
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise CorpusImportError(f"existing corpus member differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def import_corpus(
    evidence_root: Path,
    panda_license: Path,
    pyopengl_sdist: Path,
    exceptiongroup_wheel: Path,
    setuptools_wheel: Path,
) -> tuple[int, int]:
    inventory = _strict_json(INVENTORY_PATH)
    manifest = _import_manifest()
    texts = _evidence_texts(evidence_root, inventory)
    surfaces = inventory.get("distribution_surfaces")
    if not isinstance(surfaces, dict):
        raise CorpusImportError("LIC-01A distribution surfaces are missing")
    fonts = surfaces.get("fonts")
    packaging = surfaces.get("packaging")
    if not isinstance(fonts, dict) or not isinstance(packaging, dict):
        raise CorpusImportError("LIC-01A reviewed static license records are missing")
    font_license = fonts.get("license")
    root_licenses = packaging.get("root_licenses")
    if (
        not isinstance(font_license, dict)
        or not isinstance(root_licenses, list)
        or len(root_licenses) != 1
        or not isinstance(root_licenses[0], dict)
    ):
        raise CorpusImportError("LIC-01A reviewed repository license records are invalid")
    panda = manifest["panda-runtime"]
    pyopengl = manifest["pyopengl"]
    exceptiongroup = manifest["exceptiongroup"]
    setuptools = manifest["setuptools"]
    panda_members = panda["license_members"]
    pyopengl_members = pyopengl["license_members"]
    exceptiongroup_members = exceptiongroup["license_members"]
    setuptools_members = setuptools["license_members"]
    assert isinstance(panda_members, frozenset)
    assert isinstance(pyopengl_members, frozenset)
    assert isinstance(exceptiongroup_members, frozenset)
    assert isinstance(setuptools_members, frozenset)
    if panda_members != {"<whole-file>"} or len(pyopengl_members) != 1:
        raise CorpusImportError("file/sdist import manifest member coverage drift")
    supplemental = [
        _local_text("LICENSE", root_licenses[0]),
        _local_text("third_party/fonts/noto/OFL.txt", font_license),
        _panda_text(
            panda_license,
            expected_sha256=str(panda["archive_sha256"]),
        ),
        _pyopengl_text(
            pyopengl_sdist,
            expected_sha256=str(pyopengl["archive_sha256"]),
            expected_member=next(iter(pyopengl_members)),
        ),
        *_wheel_texts(
            exceptiongroup_wheel,
            expected_sha256=str(exceptiongroup["archive_sha256"]),
            expected_members=exceptiongroup_members,
            label="exceptiongroup",
        ),
        *_wheel_texts(
            setuptools_wheel,
            expected_sha256=str(setuptools["archive_sha256"]),
            expected_members=setuptools_members,
            label="setuptools",
        ),
    ]
    for payload in supplemental:
        texts.setdefault(_sha256(payload), payload)
    for digest, payload in sorted(texts.items()):
        _write_exact(CORPUS_DIRECTORY / f"{digest}.txt", payload)
    actual = sorted(CORPUS_DIRECTORY.glob("*.txt"))
    expected_names = {f"{digest}.txt" for digest in texts}
    if {path.name for path in actual} != expected_names:
        raise CorpusImportError("corpus directory contains an unexpected or missing text")
    return len(texts), sum(len(payload) for payload in texts.values())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--panda-license", type=Path, required=True)
    parser.add_argument("--pyopengl-sdist", type=Path, required=True)
    parser.add_argument("--exceptiongroup-wheel", type=Path, required=True)
    parser.add_argument("--setuptools-wheel", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        count, size = import_corpus(
            args.evidence_root.resolve(),
            args.panda_license.resolve(),
            args.pyopengl_sdist.resolve(),
            args.exceptiongroup_wheel.resolve(),
            args.setuptools_wheel.resolve(),
        )
    except (CorpusImportError, OSError, UnicodeError) as exc:
        print(f"License corpus import failed closed: {exc}", file=os.sys.stderr)
        return 1
    print(f"License corpus import: PASS ({count} texts, {size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
