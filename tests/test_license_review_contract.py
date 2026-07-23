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
        generator.IMPORTER_PATH,
        generator.INPUT_PATH,
        generator.INVENTORY_PATH,
        generator.NOTICE_PATH,
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
    with pytest.raises(generator.LicenseReviewError, match="unresolved"):
        generator.build_contract(contract_repository)

    document = _inputs(ROOT)
    governance = document["governance"]
    assert isinstance(governance, dict)
    governance["public_distribution_authorized"] = True
    _write_inputs(contract_repository, document)
    with pytest.raises(generator.LicenseReviewError, match="governance"):
        generator.build_contract(contract_repository)


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


def test_packaging_hook_bundles_the_notice_at_bundle_root() -> None:
    namespace = runpy.run_path(str(ROOT / generator.PACKAGING_HOOK_PATH))

    assert namespace["datas"] == [(str(ROOT / generator.NOTICE_PATH), ".")]
    spec = (ROOT / "packaging/mclab.spec").read_text(encoding="utf-8")
    assert 'hookspath=[str(ROOT / "packaging/hooks")]' in spec
