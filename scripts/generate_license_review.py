"""Generate the bounded LIC-01B repository evidence contract and notice artifact.

The generated records cover repository-known Python package-profile inputs and
reviewed static bundle inputs.  They are not an actual-package closure, a legal
approval, or authorization to distribute.  Generation fails closed when the
declared component set, evidence expressions, source URLs, corpus texts, or
explicit governance blockers drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ".agents/supply_chain/license-inventory.json"
INPUT_PATH = ".agents/supply_chain/license-review-inputs-v1.json"
SCHEMA_PATH = ".agents/supply_chain/license-review-v1.schema.json"
CONTRACT_PATH = ".agents/supply_chain/license-review-v1.json"
NOTICE_PATH = "THIRD_PARTY_NOTICES.md"
IMPORTER_PATH = "scripts/import_license_corpus.py"
GENERATOR_PATH = "scripts/generate_license_review.py"
PACKAGING_HOOK_PATH = "packaging/hooks/hook-mclab.py"
CORPUS_DIRECTORY = "third_party/licenses/corpus"
MAX_JSON_BYTES = 4 * 1024 * 1024
EXPECTED_PYTHON_COMPONENT_COUNT = 50
EXPECTED_STATIC_COMPONENT_COUNT = 3
EXPECTED_COMPONENT_COUNT = 53
EXPECTED_PARTIAL_COMPONENTS = frozenset(
    {"python:pyside6-essentials", "python:shiboken6"}
)
EXPECTED_GOVERNANCE = {
    "distribution_closure": "unproven",
    "external_legal_review": "not-authorized",
    "g3_license_gate": "open",
    "legal_approval": False,
    "lic_aggregate": "open",
    "native_and_base_image_closure": "unproven",
    "notice_bundle_complete": False,
    "public_distribution_authorized": False,
    "qt_pyside_lgpl_decision": "pending",
}
BLOCKERS = (
    "actual-package-content-closure-unproven",
    "copyright-attribution-review-pending",
    "external-legal-review-not-authorized",
    "native-and-base-image-transitive-closure-unproven",
    "notice-obligation-review-pending",
    "public-distribution-not-authorized",
    "qt-pyside-lgpl-compliance-decision-pending",
    "source-offer-and-relinking-obligations-pending",
)
INPUT_KEYS = {
    "captured_notice_components",
    "component_evidence_expressions",
    "contract_id",
    "declared_scope",
    "governance",
    "notice_default_status",
    "partial_license_text_components",
    "schema_version",
    "source_url_overrides",
    "supplemental_license_text_sha256",
}


class LicenseReviewError(RuntimeError):
    """Raised when the bounded reviewed evidence contract cannot be generated."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pairs(path: Path):
    def reject_duplicates(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise LicenseReviewError(f"duplicate JSON key {key!r}: {path}")
            result[key] = value
        return result

    return reject_duplicates


def _strict_json(relative: str) -> dict[str, object]:
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise LicenseReviewError(f"required regular JSON input is missing: {relative}")
    payload = path.read_bytes()
    if len(payload) > MAX_JSON_BYTES:
        raise LicenseReviewError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {relative}")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs(path),
            parse_constant=lambda token: (_ for _ in ()).throw(
                LicenseReviewError(f"non-finite JSON number {token}: {relative}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LicenseReviewError(f"malformed JSON input {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise LicenseReviewError(f"JSON input root must be an object: {relative}")
    return value


def _source_record(relative: str) -> dict[str, object]:
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise LicenseReviewError(f"required source is not a regular file: {relative}")
    payload = path.read_bytes()
    if not payload:
        raise LicenseReviewError(f"required source is empty: {relative}")
    return {"path": relative, "sha256": _sha256(payload), "size": len(payload)}


def _string_map(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise LicenseReviewError(f"{label} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not item.strip():
            raise LicenseReviewError(f"{label} must map non-empty strings to strings")
        result[key] = item
    return result


def _string_list(value: object, *, label: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise LicenseReviewError(f"{label} must be a non-empty array")
    if any(not isinstance(item, str) or not item for item in value):
        raise LicenseReviewError(f"{label} must contain non-empty strings")
    result = list(value)
    if len(result) != len(set(result)):
        raise LicenseReviewError(f"{label} must not contain duplicates")
    return result


def _corpus() -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    directory = ROOT / CORPUS_DIRECTORY
    if directory.is_symlink() or not directory.is_dir():
        raise LicenseReviewError("content-addressed license corpus directory is missing")
    files: dict[str, dict[str, object]] = {}
    observation_to_storage: dict[str, str] = {}
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if not entries:
        raise LicenseReviewError("content-addressed license corpus is empty")
    for path in entries:
        if path.is_symlink() or not path.is_file():
            raise LicenseReviewError(f"corpus contains a non-regular member: {path.name}")
        if path.suffix != ".txt" or len(path.stem) != 64:
            raise LicenseReviewError(f"corpus member name is not content-addressed: {path.name}")
        payload = path.read_bytes()
        digest = _sha256(payload)
        if path.stem != digest:
            raise LicenseReviewError(f"corpus member SHA-256 mismatch: {path.name}")
        if (
            not payload
            or not payload.endswith(b"\n")
            or payload.endswith(b"\n\n")
            or b"\r" in payload
            or b"\0" in payload
        ):
            raise LicenseReviewError(f"corpus member is not normalized UTF-8/LF: {path.name}")
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LicenseReviewError(f"corpus member is not UTF-8: {path.name}") from exc
        observation_digest = _sha256(payload[:-1])
        previous = observation_to_storage.setdefault(observation_digest, digest)
        if previous != digest:
            raise LicenseReviewError("normalized observation digest collision in corpus")
        files[digest] = {
            "path": f"{CORPUS_DIRECTORY}/{path.name}",
            "sha256": digest,
            "size": len(payload),
        }
    return files, observation_to_storage


def _observations(
    inventory: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    targets = inventory.get("observed_targets")
    if not isinstance(targets, list) or len(targets) != 3:
        raise LicenseReviewError("LIC-01A must retain exactly three observed targets")
    observations: dict[str, dict[str, object]] = {}
    for target in targets:
        if not isinstance(target, dict):
            raise LicenseReviewError("LIC-01A observed target must be an object")
        target_id = target.get("id")
        packages = target.get("package_observations")
        if not isinstance(target_id, str) or not isinstance(packages, list):
            raise LicenseReviewError("LIC-01A observed target content is invalid")
        for package in packages:
            if not isinstance(package, dict):
                raise LicenseReviewError("LIC-01A package observation must be an object")
            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                raise LicenseReviewError("LIC-01A package observation identity is invalid")
            record = observations.setdefault(
                name,
                {
                    "license_observations": set(),
                    "license_text_observations": set(),
                    "notice_text_observations": set(),
                    "target_ids": set(),
                    "url_observations": set(),
                    "version": version,
                },
            )
            if record["version"] != version:
                raise LicenseReviewError(f"cross-target package version drift: {name}")
            record["target_ids"].add(target_id)
            for field, key in (
                ("license_observation", "license_observations"),
                ("license_text_sha256", "license_text_observations"),
                ("notice_text_sha256", "notice_text_observations"),
                ("url_observation", "url_observations"),
            ):
                value = package.get(field)
                if value is not None:
                    if not isinstance(value, str) or not value:
                        raise LicenseReviewError(f"invalid {field} for {name}")
                    record[key].add(value)
    return observations


def _static_components(inventory: Mapping[str, object]) -> dict[str, dict[str, object]]:
    surfaces = inventory.get("distribution_surfaces")
    if not isinstance(surfaces, dict):
        raise LicenseReviewError("LIC-01A distribution surfaces are missing")
    fonts = surfaces.get("fonts")
    panda = surfaces.get("panda_runtime")
    if not isinstance(fonts, dict) or not isinstance(panda, dict):
        raise LicenseReviewError("LIC-01A static bundle surfaces are missing")
    font_files = fonts.get("files")
    panda_commit = panda.get("commit")
    if not isinstance(font_files, list) or len(font_files) != 2 or not isinstance(
        panda_commit, str
    ):
        raise LicenseReviewError("LIC-01A static bundle identity is invalid")
    result: dict[str, dict[str, object]] = {}
    for font in font_files:
        if not isinstance(font, dict):
            raise LicenseReviewError("LIC-01A font record must be an object")
        font_id = font.get("id")
        digest = font.get("sha256")
        if not isinstance(font_id, str) or not isinstance(digest, str):
            raise LicenseReviewError("LIC-01A font identity is invalid")
        component_id = f"static:{font_id}"
        result[component_id] = {
            "applicable_targets": ["repository-static-bundle"],
            "name": font_id,
            "version": digest,
        }
    result["static:panda-runtime"] = {
        "applicable_targets": ["repository-static-bundle"],
        "name": "MuJoCo Menagerie Franka Emika Panda runtime",
        "version": panda_commit,
    }
    if len(result) != EXPECTED_STATIC_COMPONENT_COUNT:
        raise LicenseReviewError("LIC-01A static component count drift")
    return result


def _component_inputs(
    inventory: Mapping[str, object],
    observations: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    candidates = inventory.get("candidates")
    target_cells = inventory.get("target_cells")
    if not isinstance(candidates, list) or len(candidates) != 49:
        raise LicenseReviewError("LIC-01A must retain exactly 49 lock candidates")
    if not isinstance(target_cells, list) or len(target_cells) != 12:
        raise LicenseReviewError("LIC-01A must retain exactly 12 target cells")
    result: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise LicenseReviewError("LIC-01A candidate must be an object")
        name = candidate.get("name")
        version = candidate.get("version")
        targets = candidate.get("environment_ids")
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not isinstance(targets, list)
            or any(not isinstance(item, str) for item in targets)
        ):
            raise LicenseReviewError("LIC-01A candidate identity is invalid")
        component_id = f"python:{name}"
        if component_id in result:
            raise LicenseReviewError(f"duplicate LIC-01A candidate: {name}")
        result[component_id] = {
            "applicable_targets": sorted(targets),
            "name": name,
            "version": version,
        }
    project_name = "mujoco-manipulator-control-lab"
    project_observation = observations.get(project_name)
    target_ids = [
        target.get("id")
        for target in target_cells
        if isinstance(target, dict) and isinstance(target.get("id"), str)
    ]
    if (
        project_observation is None
        or project_observation.get("version") != "0.1.0"
        or len(target_ids) != 12
    ):
        raise LicenseReviewError("LIC-01A editable project observation is missing")
    result[f"python:{project_name}"] = {
        "applicable_targets": sorted(target_ids),
        "name": project_name,
        "version": "0.1.0",
    }
    if len(result) != EXPECTED_PYTHON_COMPONENT_COUNT:
        raise LicenseReviewError("LIC-01B Python component count drift")
    result.update(_static_components(inventory))
    if len(result) != EXPECTED_COMPONENT_COUNT:
        raise LicenseReviewError("LIC-01B total component count drift")
    return result


def _ref(digest: str, corpus: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    record = corpus.get(digest)
    if record is None:
        raise LicenseReviewError(f"referenced corpus body is missing: {digest}")
    return dict(record)


def _review_inputs(
    document: Mapping[str, object],
    expected_ids: set[str],
    observations: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    if set(document) != INPUT_KEYS:
        raise LicenseReviewError("LIC-01B review input keys drift")
    if document.get("schema_version") != 1 or document.get("contract_id") != "LIC-01B":
        raise LicenseReviewError("LIC-01B review input identity drift")
    declared_scope = document.get("declared_scope")
    if not isinstance(declared_scope, str) or not declared_scope:
        raise LicenseReviewError("LIC-01B declared scope is missing")
    governance = document.get("governance")
    if governance != EXPECTED_GOVERNANCE:
        raise LicenseReviewError("LIC-01B open governance decisions drift")
    if document.get("notice_default_status") != "obligation-review-pending":
        raise LicenseReviewError("LIC-01B notice default must remain pending")

    expressions = _string_map(
        document.get("component_evidence_expressions"),
        label="component_evidence_expressions",
    )
    if set(expressions) != expected_ids:
        raise LicenseReviewError("LIC-01B expression coverage does not match component scope")
    for component_id, expression in expressions.items():
        lowered = expression.casefold()
        if "unknown" in lowered or "noassertion" in lowered:
            raise LicenseReviewError(
                f"LIC-01B expression is unresolved for {component_id}: {expression}"
            )

    partial = _string_map(
        document.get("partial_license_text_components"),
        label="partial_license_text_components",
    )
    if set(partial) != EXPECTED_PARTIAL_COMPONENTS:
        raise LicenseReviewError("LIC-01B explicit partial text blockers drift")

    captured_notice = _string_list(
        document.get("captured_notice_components"),
        label="captured_notice_components",
    )
    observed_notice = {
        f"python:{name}"
        for name, record in observations.items()
        if record["notice_text_observations"]
    }
    if set(captured_notice) != observed_notice:
        raise LicenseReviewError("LIC-01B captured notice coverage drift")

    supplements_raw = document.get("supplemental_license_text_sha256")
    if not isinstance(supplements_raw, dict):
        raise LicenseReviewError("supplemental_license_text_sha256 must be an object")
    supplements: dict[str, list[str]] = {}
    for component_id, values in supplements_raw.items():
        if not isinstance(component_id, str):
            raise LicenseReviewError("supplemental license component id is invalid")
        supplements[component_id] = sorted(
            _string_list(values, label=f"supplemental texts for {component_id}")
        )
        if any(len(value) != 64 for value in supplements[component_id]):
            raise LicenseReviewError(f"supplemental license SHA-256 is invalid: {component_id}")
    expected_supplements = {
        "python:exceptiongroup",
        "python:pyopengl",
        "python:setuptools",
        "static:noto-sans-kr-variable",
        "static:noto-sans-mono-variable",
        "static:panda-runtime",
    }
    if set(supplements) != expected_supplements:
        raise LicenseReviewError("LIC-01B supplemental text coverage drift")

    overrides = _string_map(
        document.get("source_url_overrides"), label="source_url_overrides"
    )
    required_overrides = {
        component_id
        for component_id in expected_ids
        if component_id.startswith("static:")
        or not _observed_https_url(component_id, observations)
    }
    if set(overrides) != required_overrides:
        raise LicenseReviewError("LIC-01B source URL override coverage drift")
    if any(not value.startswith("https://") for value in overrides.values()):
        raise LicenseReviewError("LIC-01B source URL overrides must use HTTPS")
    return {
        "captured_notice": set(captured_notice),
        "declared_scope": declared_scope,
        "expressions": expressions,
        "overrides": overrides,
        "partial": partial,
        "supplements": supplements,
    }


def _observed_https_url(
    component_id: str, observations: Mapping[str, Mapping[str, object]]
) -> str | None:
    if not component_id.startswith("python:"):
        return None
    name = component_id.removeprefix("python:")
    record = observations.get(name)
    if record is None:
        return None
    values = sorted(record["url_observations"])
    if len(values) == 1 and values[0].startswith("https://"):
        return values[0]
    return None


def _resolved_observation_refs(
    values: object,
    observation_to_storage: Mapping[str, str],
    corpus: Mapping[str, Mapping[str, object]],
    *,
    label: str,
) -> list[dict[str, object]]:
    if not isinstance(values, set):
        raise LicenseReviewError(f"{label} observation set is invalid")
    digests: set[str] = set()
    for observation_digest in values:
        if not isinstance(observation_digest, str):
            raise LicenseReviewError(f"{label} observation digest is invalid")
        storage_digest = observation_to_storage.get(observation_digest)
        if storage_digest is None:
            raise LicenseReviewError(
                f"{label} observation has no content-addressed corpus body: "
                f"{observation_digest}"
            )
        digests.add(storage_digest)
    return [_ref(digest, corpus) for digest in sorted(digests)]


def build_contract(root: Path = ROOT) -> dict[str, object]:
    """Build the canonical bounded LIC-01B evidence contract."""

    global ROOT
    original_root = ROOT
    ROOT = root
    try:
        inventory = _strict_json(INVENTORY_PATH)
        inputs_document = _strict_json(INPUT_PATH)
        corpus, observation_to_storage = _corpus()
        observations = _observations(inventory)
        component_inputs = _component_inputs(inventory, observations)
        expected_ids = set(component_inputs)
        reviewed = _review_inputs(inputs_document, expected_ids, observations)
        expressions = reviewed["expressions"]
        overrides = reviewed["overrides"]
        partial = reviewed["partial"]
        supplements = reviewed["supplements"]
        captured_notice = reviewed["captured_notice"]
        assert isinstance(expressions, dict)
        assert isinstance(overrides, dict)
        assert isinstance(partial, dict)
        assert isinstance(supplements, dict)
        assert isinstance(captured_notice, set)

        roles_by_digest: dict[str, set[str]] = defaultdict(set)
        components_by_digest: dict[str, set[str]] = defaultdict(set)
        components: list[dict[str, object]] = []
        for component_id in sorted(expected_ids):
            base = component_inputs[component_id]
            kind, _separator, name = component_id.partition(":")
            observation = observations.get(name)
            license_texts: list[dict[str, object]] = []
            notice_texts: list[dict[str, object]] = []
            if observation is not None:
                if observation.get("version") != base["version"]:
                    raise LicenseReviewError(f"observed component version drift: {component_id}")
                license_texts.extend(
                    _resolved_observation_refs(
                        observation["license_text_observations"],
                        observation_to_storage,
                        corpus,
                        label=f"{component_id} license",
                    )
                )
                notice_texts.extend(
                    _resolved_observation_refs(
                        observation["notice_text_observations"],
                        observation_to_storage,
                        corpus,
                        label=f"{component_id} notice",
                    )
                )
            for digest in supplements.get(component_id, []):
                license_texts.append(_ref(digest, corpus))
            license_texts = [
                value
                for _digest, value in sorted(
                    {str(value["sha256"]): value for value in license_texts}.items()
                )
            ]
            notice_texts = [
                value
                for _digest, value in sorted(
                    {str(value["sha256"]): value for value in notice_texts}.items()
                )
            ]
            if not license_texts:
                raise LicenseReviewError(f"component has no captured license text: {component_id}")
            if (component_id in captured_notice) != bool(notice_texts):
                raise LicenseReviewError(f"captured notice status drift: {component_id}")
            source_url = overrides.get(component_id) or _observed_https_url(
                component_id, observations
            )
            if not isinstance(source_url, str) or not source_url.startswith("https://"):
                raise LicenseReviewError(f"component source URL is unresolved: {component_id}")
            if component_id in partial:
                license_text_status = "partial-explicit-blocker"
                license_text_detail = partial[component_id]
            else:
                license_text_status = "complete-within-declared-evidence-scope"
                license_text_detail = (
                    "all license bodies captured by the bounded repository evidence scope"
                )
            for text in license_texts:
                digest = str(text["sha256"])
                roles_by_digest[digest].add("license")
                components_by_digest[digest].add(component_id)
            for text in notice_texts:
                digest = str(text["sha256"])
                roles_by_digest[digest].add("notice")
                components_by_digest[digest].add(component_id)
            components.append(
                {
                    "actual_distribution_status": (
                        "candidate-input-not-actual-package-closure"
                    ),
                    "applicable_targets": list(base["applicable_targets"]),
                    "evidence_expression": expressions[component_id],
                    "evidence_review_status": "repository-evidence-checked",
                    "id": component_id,
                    "kind": kind,
                    "license_text_detail": license_text_detail,
                    "license_text_status": license_text_status,
                    "license_texts": license_texts,
                    "name": str(base["name"]),
                    "notice_status": (
                        "captured-obligation-review-pending"
                        if notice_texts
                        else "no-separate-text-observed-obligation-review-pending"
                    ),
                    "notice_texts": notice_texts,
                    "role": (
                        "repository-static-bundle-input"
                        if kind == "static"
                        else (
                            "project-package-profile-input"
                            if name == "mujoco-manipulator-control-lab"
                            else "python-package-profile-input"
                        )
                    ),
                    "source_url": source_url,
                    "version": str(base["version"]),
                }
            )
        if set(roles_by_digest) != set(corpus):
            missing = sorted(set(corpus) - set(roles_by_digest))
            extra = sorted(set(roles_by_digest) - set(corpus))
            raise LicenseReviewError(
                f"corpus reference closure drift; unreferenced={missing}, missing={extra}"
            )

        corpus_files = [
            {
                "component_ids": sorted(components_by_digest[digest]),
                **corpus[digest],
                "roles": sorted(roles_by_digest[digest]),
            }
            for digest in sorted(corpus)
        ]
        complete_count = sum(
            component["license_text_status"]
            == "complete-within-declared-evidence-scope"
            for component in components
        )
        partial_count = len(components) - complete_count
        return {
            "components": components,
            "contract": {
                "blockers": list(BLOCKERS),
                "declared_scope": reviewed["declared_scope"],
                **EXPECTED_GOVERNANCE,
                "id": "LIC-01B",
                "purpose": (
                    "deterministic repository evidence corpus; not legal approval "
                    "or distribution closure"
                ),
                "status": "bounded-candidate-evidence-only",
            },
            "corpus": {
                "byte_count": sum(int(item["size"]) for item in corpus_files),
                "directory": CORPUS_DIRECTORY,
                "file_count": len(corpus_files),
                "files": corpus_files,
                "license_body_count": sum(
                    "license" in item["roles"] for item in corpus_files
                ),
                "notice_body_count": sum(
                    "notice" in item["roles"] for item in corpus_files
                ),
            },
            "coverage": {
                "component_count": len(components),
                "evidence_expression_count": sum(
                    bool(component["evidence_expression"]) for component in components
                ),
                "license_text_complete_count": complete_count,
                "license_text_partial_count": partial_count,
                "notice_text_captured_component_count": sum(
                    bool(component["notice_texts"]) for component in components
                ),
                "python_component_count": sum(
                    component["kind"] == "python" for component in components
                ),
                "source_url_count": sum(
                    bool(component["source_url"]) for component in components
                ),
                "static_component_count": sum(
                    component["kind"] == "static" for component in components
                ),
                "unknown_value_count": 0,
            },
            "notice_artifact": {
                "format": "deterministic-markdown-utf8-lf",
                "package_destination": NOTICE_PATH,
                "path": NOTICE_PATH,
            },
            "schema_version": 1,
            "sources": {
                "corpus_importer": _source_record(IMPORTER_PATH),
                "generator": _source_record(GENERATOR_PATH),
                "license_inventory": _source_record(INVENTORY_PATH),
                "packaging_hook": _source_record(PACKAGING_HOOK_PATH),
                "review_inputs": _source_record(INPUT_PATH),
                "review_schema": _source_record(SCHEMA_PATH),
            },
        }
    finally:
        ROOT = original_root


def canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_notice(contract: Mapping[str, object], root: Path = ROOT) -> bytes:
    """Render the deterministic notice artifact from a generated contract."""

    components = contract["components"]
    contract_record = contract["contract"]
    corpus = contract["corpus"]
    coverage = contract["coverage"]
    assert isinstance(components, list)
    assert isinstance(contract_record, dict)
    assert isinstance(corpus, dict)
    assert isinstance(coverage, dict)
    lines = [
        "# Third-Party Notices — bounded LIC-01B candidate",
        "",
        (
            "This deterministic artifact covers only repository-known Python "
            "package-profile inputs and reviewed static bundle inputs. It is not "
            "legal approval, actual-package/native closure, or authorization for "
            "public distribution."
        ),
        "",
        "## Open governance gates",
        "",
        "| Gate | Recorded state |",
        "| --- | --- |",
        f"| LIC aggregate | {_markdown_cell(contract_record['lic_aggregate'])} |",
        f"| G3 license gate | {_markdown_cell(contract_record['g3_license_gate'])} |",
        f"| Legal approval | {_markdown_cell(contract_record['legal_approval'])} |",
        (
            "| Public distribution authorized | "
            f"{_markdown_cell(contract_record['public_distribution_authorized'])} |"
        ),
        (
            "| Actual package distribution closure | "
            f"{_markdown_cell(contract_record['distribution_closure'])} |"
        ),
        (
            "| Native/base-image closure | "
            f"{_markdown_cell(contract_record['native_and_base_image_closure'])} |"
        ),
        (
            "| Qt/PySide LGPL decision | "
            f"{_markdown_cell(contract_record['qt_pyside_lgpl_decision'])} |"
        ),
        (
            "| External legal review | "
            f"{_markdown_cell(contract_record['external_legal_review'])} |"
        ),
        (
            "| Notice bundle complete | "
            f"{_markdown_cell(contract_record['notice_bundle_complete'])} |"
        ),
        "",
        "## Bounded coverage",
        "",
        (
            f"- Components: {coverage['component_count']} "
            f"({coverage['python_component_count']} Python inputs, "
            f"{coverage['static_component_count']} static inputs)"
        ),
        (
            f"- License text status: {coverage['license_text_complete_count']} complete "
            "within the declared evidence scope; "
            f"{coverage['license_text_partial_count']} explicit Qt partial blockers"
        ),
        (
            f"- Captured notice-text components: "
            f"{coverage['notice_text_captured_component_count']}"
        ),
        f"- Content-addressed bodies: {corpus['file_count']}",
        "- Unresolved/UNKNOWN values inside the declared component evidence: 0",
        "",
        "## Component index",
        "",
        "| Component | Version | Evidence expression | License text | Notice status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for component in components:
        assert isinstance(component, dict)
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(component[key])
                for key in (
                    "id",
                    "version",
                    "evidence_expression",
                    "license_text_status",
                    "notice_status",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Captured license and notice text corpus",
            "",
            (
                "Each body appears once by the SHA-256 of its exact stored UTF-8/LF "
                "bytes. Component mappings and text roles are generated from the "
                "versioned LIC-01B contract."
            ),
            "",
        ]
    )
    corpus_files = corpus["files"]
    assert isinstance(corpus_files, list)
    for item in corpus_files:
        assert isinstance(item, dict)
        path = root / str(item["path"])
        payload = path.read_bytes()
        if _sha256(payload) != item["sha256"] or len(payload) != item["size"]:
            raise LicenseReviewError(f"notice render corpus drift: {item['path']}")
        body = payload.decode("utf-8").rstrip("\n")
        lines.extend(
            [
                f"### SHA-256 `{item['sha256']}`",
                "",
                f"- Roles: {', '.join(item['roles'])}",
                f"- Components: {', '.join(item['component_ids'])}",
                "",
                "````text",
                body,
                "````",
                "",
            ]
        )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise LicenseReviewError(f"generated destination is not a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def check_committed(root: Path = ROOT) -> tuple[dict[str, object], list[str]]:
    """Regenerate twice and compare both committed artifacts byte-for-byte."""

    errors: list[str] = []
    first = build_contract(root)
    second = build_contract(root)
    first_contract = canonical_json_bytes(first)
    if first_contract != canonical_json_bytes(second):
        errors.append("LIC-01B contract generation is not deterministic")
    first_notice = render_notice(first, root)
    if first_notice != render_notice(second, root):
        errors.append("LIC-01B notice generation is not deterministic")
    for relative, expected in (
        (CONTRACT_PATH, first_contract),
        (NOTICE_PATH, first_notice),
    ):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"generated artifact is missing or not regular: {relative}")
        elif path.read_bytes() != expected:
            errors.append(f"generated artifact is stale: {relative}")
    return first, errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless both committed artifacts match fresh deterministic generation",
    )
    args = parser.parse_args(argv)
    try:
        contract = build_contract()
        contract_bytes = canonical_json_bytes(contract)
        notice_bytes = render_notice(contract)
        if args.check:
            _contract, errors = check_committed()
            if errors:
                raise LicenseReviewError("; ".join(errors))
        else:
            _write_atomic(ROOT / CONTRACT_PATH, contract_bytes)
            _write_atomic(ROOT / NOTICE_PATH, notice_bytes)
    except (LicenseReviewError, OSError, UnicodeError) as exc:
        print(f"LIC-01B generation failed closed: {exc}", file=os.sys.stderr)
        return 1
    coverage = contract["coverage"]
    corpus = contract["corpus"]
    assert isinstance(coverage, dict) and isinstance(corpus, dict)
    print(
        "LIC-01B repository evidence: PASS "
        f"({coverage['component_count']} components, {corpus['file_count']} corpus bodies; "
        "aggregate/G3 remain open)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
