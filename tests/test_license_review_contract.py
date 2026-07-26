from __future__ import annotations

import importlib.util
import hashlib
import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest

from scripts import generate_license_review as generator
from scripts import import_license_corpus as corpus_importer


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents/validation/check_license_review.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("_test_license_review_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


@pytest.fixture
def contract_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    files = {
        generator.CONTRACT_PATH,
        generator.GENERATOR_PATH,
        generator.IMPORT_MANIFEST_PATH,
        generator.IMPORTER_PATH,
        generator.INPUT_PATH,
        generator.INVENTORY_PATH,
        generator.NOTICE_PATH,
        generator.PACKAGE_BUILDER_PATH,
        generator.PACKAGING_HOOK_PATH,
        generator.SCHEMA_PATH,
        "packaging/mclab.spec",
    }
    for relative in sorted(files):
        source = ROOT / relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copytree(
        ROOT / generator.CORPUS_DIRECTORY,
        repository / generator.CORPUS_DIRECTORY,
    )
    return repository


def _inputs(repository: Path) -> dict[str, object]:
    return json.loads((repository / generator.INPUT_PATH).read_text(encoding="utf-8"))


def _write_inputs(repository: Path, document: dict[str, object]) -> None:
    (repository / generator.INPUT_PATH).write_text(
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_committed_review_contract_notice_schema_and_packaging_are_current() -> None:
    contract, generation_errors = generator.check_committed(ROOT)
    metrics, policy_errors = checker.validate(ROOT)

    assert not generation_errors
    assert not policy_errors
    assert metrics == contract["coverage"]
    assert metrics == {
        "component_count": 53,
        "evidence_expression_count": 53,
        "license_text_complete_count": 51,
        "license_text_partial_count": 2,
        "notice_text_captured_component_count": 1,
        "python_component_count": 50,
        "source_url_count": 53,
        "static_component_count": 3,
        "unknown_value_count": 0,
    }


def test_declared_scope_has_no_missing_or_unknown_component_evidence() -> None:
    contract = json.loads((ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8"))
    components = contract["components"]

    assert len(components) == 53
    assert len({component["id"] for component in components}) == 53
    assert all(component["evidence_expression"] for component in components)
    assert all(component["source_url"].startswith("https://") for component in components)
    assert all(component["license_texts"] for component in components)
    assert not checker._unresolved_values(contract)


def test_corpus_import_manifest_is_explicit_hash_anchored_and_retention_open() -> None:
    manifest = json.loads(
        (ROOT / generator.IMPORT_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert manifest["raw_evidence_retention"] == "open-owner-decision-required"
    assert manifest["replay_command"] == corpus_importer.EXPECTED_REPLAY_COMMAND
    supplements = manifest["supplemental_inputs"]
    assert corpus_importer._import_manifest() == {
        label: {
            "archive_sha256": record["archive_sha256"],
            "kind": record["kind"],
            "license_members": frozenset(record["license_members"]),
        }
        for label, record in supplements.items()
    }
    package_lock = (ROOT / "requirements/locks/package.txt").read_text(encoding="utf-8")
    build_lock = (ROOT / "requirements/locks/build.txt").read_text(encoding="utf-8")
    assert supplements["exceptiongroup"]["archive_sha256"] in package_lock
    assert supplements["pyopengl"]["archive_sha256"] in package_lock
    assert supplements["setuptools"]["archive_sha256"] in build_lock
    inventory = (ROOT / generator.INVENTORY_PATH).read_text(encoding="utf-8")
    assert supplements["panda-runtime"]["archive_sha256"] in inventory


def test_corpus_import_manifest_retention_decision_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    document = json.loads(
        (ROOT / generator.IMPORT_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    document["raw_evidence_retention"] = "complete"
    manifest_path.write_text(
        json.dumps(document, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(corpus_importer, "IMPORT_MANIFEST_PATH", manifest_path)

    with pytest.raises(corpus_importer.CorpusImportError, match="remain.*open"):
        corpus_importer._import_manifest()


def test_qt_rows_are_explicit_partial_blockers_and_governance_stays_open() -> None:
    contract = json.loads((ROOT / generator.CONTRACT_PATH).read_text(encoding="utf-8"))
    components = {component["id"]: component for component in contract["components"]}

    partial_ids = {
        component_id
        for component_id, component in components.items()
        if component["license_text_status"] == "partial-explicit-blocker"
    }
    assert partial_ids == generator.EXPECTED_PARTIAL_COMPONENTS
    assert all("commercial-terms-only" in components[item]["license_text_detail"] for item in partial_ids)
    assert contract["contract"]["qt_pyside_lgpl_decision"] == "pending"
    assert contract["contract"]["legal_approval"] is False
    assert contract["contract"]["public_distribution_authorized"] is False
    assert contract["contract"]["notice_bundle_complete"] is False
    assert contract["contract"]["lic_aggregate"] == "open"
    assert contract["contract"]["g3_license_gate"] == "open"


def test_review_input_fails_closed_when_one_component_expression_is_missing(
    contract_repository: Path,
) -> None:
    document = _inputs(contract_repository)
    expressions = document["component_evidence_expressions"]
    assert isinstance(expressions, dict)
    del expressions["python:numpy"]
    _write_inputs(contract_repository, document)

    with pytest.raises(generator.LicenseReviewError, match="expression coverage"):
        generator.build_contract(contract_repository)


def test_review_input_fails_closed_on_unknown_or_governance_promotion(
    contract_repository: Path,
) -> None:
    document = _inputs(contract_repository)
    expressions = document["component_evidence_expressions"]
    assert isinstance(expressions, dict)
    expressions["python:numpy"] = "UNKNOWN"
    _write_inputs(contract_repository, document)
    with pytest.raises(generator.LicenseReviewError, match="SPDX"):
        generator.build_contract(contract_repository)

    document = _inputs(ROOT)
    governance = document["governance"]
    assert isinstance(governance, dict)
    governance["public_distribution_authorized"] = True
    _write_inputs(contract_repository, document)
    with pytest.raises(generator.LicenseReviewError, match="governance"):
        generator.build_contract(contract_repository)


@pytest.mark.parametrize(
    "expression",
    [
        "TBD",
        "NONE",
        "foo",
        "MIT XOR BSD-3-Clause",
        "MIT AND",
        "MIT OR OR BSD-3-Clause",
        "MIT or BSD-3-Clause",
        "LicenseRef-Undefined",
        "(MIT)",
        "MIT  AND PSF-2.0",
    ],
)
def test_review_input_rejects_unresolved_or_malformed_spdx_expressions(
    contract_repository: Path,
    expression: str,
) -> None:
    document = _inputs(contract_repository)
    expressions = document["component_evidence_expressions"]
    assert isinstance(expressions, dict)
    expressions["python:numpy"] = expression
    _write_inputs(contract_repository, document)

    with pytest.raises(generator.LicenseReviewError, match="SPDX"):
        generator.build_contract(contract_repository)


def test_review_input_requires_exact_licenseref_definition_coverage(
    contract_repository: Path,
) -> None:
    document = _inputs(contract_repository)
    definitions = document["license_ref_components"]
    assert isinstance(definitions, dict)
    definitions.pop("LicenseRef-NumPy-2.2.6")
    _write_inputs(contract_repository, document)
    with pytest.raises(generator.LicenseReviewError, match="undefined LicenseRef"):
        generator.build_contract(contract_repository)

    document = _inputs(ROOT)
    definitions = document["license_ref_components"]
    assert isinstance(definitions, dict)
    definitions["LicenseRef-Unused-1.0"] = "python:numpy"
    _write_inputs(contract_repository, document)
    with pytest.raises(generator.LicenseReviewError, match="definition coverage"):
        generator.build_contract(contract_repository)


def test_checker_recognizes_broader_exact_unresolved_sentinels() -> None:
    for value in ("TBD", "NONE", "N/A", "NOASSERTION", "UNKNOWN"):
        assert checker._unresolved_values({"evidence_expression": value}) == [
            "$.evidence_expression: unresolved sentinel is not allowed: "
            f"{value!r}"
        ]


def test_contract_generation_for_an_explicit_root_does_not_mutate_module_root(
    contract_repository: Path,
) -> None:
    original_root = generator.ROOT

    generator.build_contract(contract_repository)

    assert generator.ROOT == original_root


def test_corpus_tamper_and_unreferenced_file_fail_closed(
    contract_repository: Path,
) -> None:
    corpus = contract_repository / generator.CORPUS_DIRECTORY
    member = next(iter(sorted(corpus.glob("*.txt"))))
    member.write_bytes(member.read_bytes() + b"tamper\n")
    with pytest.raises(generator.LicenseReviewError, match="SHA-256 mismatch"):
        generator.build_contract(contract_repository)

    shutil.rmtree(corpus)
    shutil.copytree(ROOT / generator.CORPUS_DIRECTORY, corpus)
    payload = b"extra\n"
    unexpected = corpus / f"{hashlib.sha256(payload).hexdigest()}.txt"
    unexpected.write_bytes(payload)
    with pytest.raises(generator.LicenseReviewError, match="corpus reference closure"):
        generator.build_contract(contract_repository)


def test_stale_notice_is_rejected_even_when_contract_is_current(
    contract_repository: Path,
) -> None:
    notice = contract_repository / generator.NOTICE_PATH
    notice.write_bytes(notice.read_bytes() + b"stale\n")

    _contract, errors = generator.check_committed(contract_repository)

    assert errors == [f"generated artifact is stale: {generator.NOTICE_PATH}"]


def test_packaging_hook_and_builder_attest_the_notice_at_bundle_root() -> None:
    namespace = runpy.run_path(str(ROOT / generator.PACKAGING_HOOK_PATH))

    assert namespace["datas"] == [(str(ROOT / generator.NOTICE_PATH), ".")]
    spec = (ROOT / "packaging/mclab.spec").read_text(encoding="utf-8")
    assert 'hookspath=[str(ROOT / "packaging/hooks")]' in spec
    builder = runpy.run_path(str(ROOT / generator.PACKAGE_BUILDER_PATH))
    assert builder["THIRD_PARTY_NOTICES_NAME"] == generator.NOTICE_PATH
    assert builder["EVIDENCE_SCHEMA"] == "mclab.package-metrics.v2"
    assert callable(builder["_atomic_replace_third_party_notices"])
    assert callable(builder["_third_party_notices_evidence"])
