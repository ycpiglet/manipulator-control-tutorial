from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import generate_sbom_inputs as generator


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "a" * 40
CHECKER_PATH = ROOT / ".agents/validation/check_supply_chain_policy.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("_test_supply_chain_policy", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _workflow_text(path: str) -> str:
    policies = [policy for policy in checker.WORKFLOW_STEP_POLICIES if policy.path == path]
    blocks = [
        "\n".join(f"      {line}" for line in policy.expected_lines)
        for policy in policies
    ]
    if path == checker.CI_WORKFLOW_PATH:
        blocks.insert(
            0,
            "      - name: README contract and local links\n"
            "        run: echo fixture",
        )
    return (
        "name: test\njobs:\n"
        + "\n".join(f"  {line}" for line in checker.WORKFLOW_JOB_HEADER_LINES[path])
        + "\n"
        + "\n".join(blocks)
        + "\n"
    )


def _workflow_policy_block(path: str, name: str) -> str:
    policy = next(
        candidate
        for candidate in checker.WORKFLOW_STEP_POLICIES
        if candidate.path == path and candidate.name == name
    )
    return "\n".join(f"      {line}" for line in policy.expected_lines) + "\n"


def _build_document(root: Path, source_commit: str = SOURCE_COMMIT) -> dict[str, object]:
    return generator.build_document(root, source_commit, bind_to_checkout=False)


def _commit_fixture_repository(repository: Path) -> str:
    subprocess.run(["git", "init", "--quiet", os.fspath(repository)], check=True)
    subprocess.run(["git", "-C", os.fspath(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(repository),
            "-c",
            "user.name=Supply Chain Test",
            "-c",
            "user.email=supply-chain@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", os.fspath(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="session")
def baseline_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("supply-chain-baseline")
    for relative in generator.INPUT_PATHS:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            shutil.copy2(source, target)
        elif relative == generator.AUDITOR_PATH:
            target.write_text('"""Fixture scanner interface."""\n', encoding="utf-8")
        else:
            raise AssertionError(f"missing fixture source: {relative}")
    for workflow_path in (checker.CI_WORKFLOW_PATH, checker.DESKTOP_WORKFLOW_PATH):
        target = root / workflow_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_workflow_text(workflow_path), encoding="utf-8")
    return root


@pytest.fixture
def repository(tmp_path: Path, baseline_root: Path) -> Path:
    target = tmp_path / "repository"
    shutil.copytree(baseline_root, target)
    return target


@pytest.fixture(scope="session")
def baseline_document(baseline_root: Path) -> dict[str, object]:
    return _build_document(baseline_root)


def _rewrite_first_lock_marker(path: Path, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = rf"\1{marker} \\"
    changed, count = re.subn(r"(?m)^(uv==[^;]+;\s*).+?\\\s*$", replacement, text, count=1)
    assert count == 1
    path.write_text(changed, encoding="utf-8")


def test_generator_is_canonical_deterministic_and_complete(baseline_root: Path) -> None:
    first = _build_document(baseline_root)
    second = _build_document(baseline_root)
    first_bytes = generator.canonical_json_bytes(first)
    assert first_bytes == generator.canonical_json_bytes(second)
    assert checker.strict_json_bytes(first_bytes) == first
    assert b"timestamp" not in first_bytes and b"generated_at" not in first_bytes
    assert first["source_commit"] == SOURCE_COMMIT
    assert len(first["target_environments"]) == 12
    assert [profile["id"] for profile in first["python_lock_profiles"]] == [
        "app",
        "app-dev",
        "build",
        "dev",
        "package",
        "runtime",
        "supply-chain-tool",
        "uv-tool",
    ]
    requirements = [
        requirement
        for profile in first["python_lock_profiles"]
        for requirement in profile["requirements"]
    ]
    assert len(requirements) == 213
    assert sum(len(requirement["hashes"]) for requirement in requirements) == 4465
    assert all(requirement["hash_scope"] == generator.HASH_SCOPE for requirement in requirements)
    assert (
        first["ubuntu_system"]["archive_keyring"]
        == generator.EXPECTED_UBUNTU_ARCHIVE_KEYRING
    )
    assert set(generator.represented_repository_paths(first)) == set(generator.INPUT_PATHS)


def test_marker_membership_is_honest(baseline_document: dict[str, object]) -> None:
    environments = baseline_document["target_environments"]
    for profile in baseline_document["python_lock_profiles"]:
        for requirement in profile["requirements"]:
            marker = requirement["marker"]
            expected = sorted(
                environment["id"]
                for environment in environments
                if marker is None
                or generator._marker_applies(
                    marker,
                    {key: value for key, value in environment.items() if key != "id"},
                )
            )
            assert requirement["environment_ids"] == expected


def test_static_validator_passes_fixture(baseline_root: Path) -> None:
    document, errors = checker.validate_repository(
        baseline_root, SOURCE_COMMIT, bind_to_checkout=False
    )
    assert document is not None
    assert errors == []


def test_schema_closes_every_fixed_inventory(baseline_root: Path) -> None:
    schema = json.loads((baseline_root / generator.SCHEMA_PATH).read_text(encoding="utf-8"))
    properties = schema["properties"]
    inventories = (
        (properties["github_actions"]["properties"]["actions"], 4),
        (properties["fonts"]["properties"]["files"], 2),
        (properties["packaging"]["properties"]["data_groups"], 6),
        (properties["panda_runtime"]["properties"]["files"], 72),
        (properties["python_lock_profiles"], 8),
        (properties["target_environments"], 12),
        (properties["ubuntu_system"]["properties"]["packages"], 22),
    )
    for inventory, cardinality in inventories:
        assert inventory["minItems"] == cardinality
        assert inventory["maxItems"] == cardinality
        assert inventory["uniqueItems"] is True


def test_schema_requires_exact_ubuntu_archive_keyring_contract(
    baseline_root: Path,
) -> None:
    schema = json.loads((baseline_root / generator.SCHEMA_PATH).read_text(encoding="utf-8"))
    archive_keyring = schema["properties"]["ubuntu_system"]["properties"][
        "archive_keyring"
    ]
    assert archive_keyring == {
        "additionalProperties": False,
        "properties": {
            key: {"const": value}
            for key, value in generator.EXPECTED_UBUNTU_ARCHIVE_KEYRING.items()
        },
        "required": sorted(generator.EXPECTED_UBUNTU_ARCHIVE_KEYRING),
        "type": "object",
    }
    assert "archive_keyring" in schema["properties"]["ubuntu_system"]["required"]


@pytest.mark.parametrize("source_commit", ["", "A" * 40, "0" * 39, "g" * 40])
def test_source_commit_must_be_explicit_lowercase_40_hex(
    baseline_root: Path, source_commit: str
) -> None:
    with pytest.raises(generator.SupplyChainInputError, match="SOURCE_COMMIT_INVALID"):
        _build_document(baseline_root, source_commit)


def test_source_commit_is_bound_to_clean_checked_out_head(repository: Path) -> None:
    head = _commit_fixture_repository(repository)

    assert generator.build_document(repository, head)["source_commit"] == head
    with pytest.raises(generator.SupplyChainInputError, match="SOURCE_COMMIT_MISMATCH"):
        generator.build_document(repository, "0" * 40)
    document, errors = checker.validate_repository(
        repository,
        "0" * 40,
        check_workflows=False,
    )
    assert document is None
    assert any("SOURCE_COMMIT_MISMATCH" in error for error in errors)

    (repository / generator.PROJECT_LICENSE_PATH).write_bytes(
        (repository / generator.PROJECT_LICENSE_PATH).read_bytes() + b"\n"
    )
    with pytest.raises(generator.SupplyChainInputError, match="SOURCE_CHECKOUT_DIRTY"):
        generator.build_document(repository, head)


def test_generator_cli_requires_source_commit_and_output() -> None:
    with pytest.raises(SystemExit):
        generator.main([])


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(generator.SupplyChainInputError, match="MALFORMED_JSON"):
        checker.strict_json_bytes(b'{"schema_version":1,"schema_version":1}')


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "nested-extra", "duplicate", "unsorted"]
)
def test_document_records_fail_closed(
    baseline_document: dict[str, object], mutation: str
) -> None:
    document = copy.deepcopy(baseline_document)
    if mutation == "missing":
        del document["fonts"]
    elif mutation == "extra":
        document["unexpected"] = True
    elif mutation == "nested-extra":
        document["python_lock_profiles"][0]["requirements"][0]["unexpected"] = True
    elif mutation == "duplicate":
        document["python_lock_profiles"].append(
            copy.deepcopy(document["python_lock_profiles"][0])
        )
    else:
        document["python_lock_profiles"].reverse()
    assert checker.document_policy_errors(document)


@pytest.mark.parametrize(
    ("marker", "message"),
    [
        ("python_version == '9.9'", "LOCK_MARKER_ZERO_CELL"),
        ("os_name == 'posix'", "LOCK_MARKER_UNSUPPORTED"),
    ],
)
def test_lock_markers_reject_zero_cell_and_unsupported_grammar(
    repository: Path, marker: str, message: str
) -> None:
    _rewrite_first_lock_marker(repository / "requirements/tools/uv.txt", marker)
    with pytest.raises(generator.SupplyChainInputError, match=message):
        _build_document(repository)


def test_stale_document_detects_lock_hash_drift(repository: Path) -> None:
    document = _build_document(repository)
    path = repository / "requirements/tools/uv.txt"
    text = path.read_text(encoding="utf-8")
    changed, count = generator.HASH_TOKEN_RE.subn(
        "--hash=sha256:" + "0" * 64,
        text,
        count=1,
    )
    assert count == 1
    path.write_text(changed, encoding="utf-8")
    assert any("hash/size drift" in error for error in checker.represented_source_errors(repository, document))


def test_action_lock_drift_is_rejected(repository: Path) -> None:
    path = repository / generator.ACTIONS_LOCK_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"]["actions/checkout"]["sha"] = "0" * 40
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError, match="ACTION_LOCK_RECORD_DRIFT"):
        _build_document(repository)


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        (generator.PANDA_MANIFEST_PATH, "PANDA_MANIFEST_SOURCE_DRIFT"),
        (generator.EXPECTED_FONT_FILES[0][1], "FONT_HASH_DRIFT"),
        (generator.EXPECTED_FONT_LICENSE[0], "FONT_LICENSE_DRIFT"),
        (generator.PROJECT_LICENSE_PATH, "PROJECT_LICENSE_DRIFT"),
    ],
)
def test_reviewed_hash_and_license_drift_is_rejected(
    repository: Path, relative: str, message: str
) -> None:
    path = repository / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.SupplyChainInputError, match=message):
        _build_document(repository)


def test_ubuntu_package_drift_and_order_are_rejected(repository: Path) -> None:
    path = repository / generator.UBUNTU_MANIFEST_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["packages"][0]["version"] = "0"
    payload["packages"].reverse()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError, match="UBUNTU_PACKAGE_DRIFT_OR_ORDER"):
        _build_document(repository)


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [
        ("package", "drifted-keyring"),
        ("version", "0"),
        ("path", "/tmp/drifted-keyring.gpg"),
        ("size", 3608),
        ("size", 3607.0),
        ("sha256", "0" * 64),
    ],
)
def test_ubuntu_archive_keyring_value_drift_is_rejected(
    repository: Path,
    field: str,
    drifted_value: object,
) -> None:
    path = repository / generator.UBUNTU_MANIFEST_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["archive_keyring"][field] = drifted_value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError, match="UBUNTU_ARCHIVE_KEYRING_DRIFT"):
        _build_document(repository)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_ubuntu_archive_keyring_keys_are_closed(repository: Path, mutation: str) -> None:
    path = repository / generator.UBUNTU_MANIFEST_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "missing":
        del payload["archive_keyring"]["sha256"]
    else:
        payload["archive_keyring"]["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError, match="UNEXPECTED_KEYS"):
        _build_document(repository)


@pytest.mark.parametrize("mutation", ["missing", "extra", "value"])
def test_static_policy_rejects_ubuntu_archive_keyring_drift(
    baseline_document: dict[str, object],
    mutation: str,
) -> None:
    document = copy.deepcopy(baseline_document)
    archive_keyring = document["ubuntu_system"]["archive_keyring"]
    if mutation == "missing":
        del archive_keyring["sha256"]
    elif mutation == "extra":
        archive_keyring["unexpected"] = True
    else:
        archive_keyring["version"] = "0"
    errors = checker.document_policy_errors(document)
    assert any("ubuntu_system.archive_keyring" in error for error in errors)


def test_packaging_data_group_drift_is_rejected(repository: Path) -> None:
    path = repository / generator.PACKAGING_SPEC_PATH
    text = path.read_text(encoding="utf-8").replace(
        '(str(ROOT / "configs"), "configs")',
        '(str(ROOT / "configs"), "changed")',
        1,
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError, match="PACKAGING_DATA_GROUP_DRIFT"):
        _build_document(repository)


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":1,"schema_version":1,"waivers":[]}',
        '{"schema_version":1,"waivers":[],"unexpected":true}',
        '{"schema_version":1,"waivers":[{"id":"not-approved"}]}',
    ],
)
def test_vulnerability_waivers_fail_closed(repository: Path, payload: str) -> None:
    (repository / generator.WAIVER_PATH).write_text(payload, encoding="utf-8")
    with pytest.raises(generator.SupplyChainInputError):
        _build_document(repository)


def test_missing_symlink_out_of_tree_and_oversized_inputs_are_rejected(
    repository: Path, tmp_path: Path
) -> None:
    (repository / generator.PROJECT_PATH).unlink()
    with pytest.raises(generator.SupplyChainInputError, match="MISSING_INPUT"):
        _build_document(repository)
    with pytest.raises(generator.SupplyChainInputError, match="UNSAFE_PATH"):
        generator.read_bytes(repository, "../outside")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    waiver = repository / generator.WAIVER_PATH
    waiver.unlink()
    waiver.symlink_to(outside)
    with pytest.raises(generator.SupplyChainInputError, match="symlink"):
        generator.read_bytes(repository, generator.WAIVER_PATH)
    huge = repository / "huge"
    with huge.open("wb") as stream:
        stream.truncate(generator.MAX_INPUT_BYTES + 1)
    with pytest.raises(generator.SupplyChainInputError, match="OVERSIZED_INPUT"):
        generator.read_bytes(repository, "huge")


def test_output_symlinks_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "result.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(generator.SupplyChainInputError, match="UNSAFE_OUTPUT"):
        generator.write_document(link, b"{}\n")


def test_schema_rejects_extra_and_duplicate_keys(repository: Path) -> None:
    path = repository / generator.SCHEMA_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert checker.schema_policy_errors(repository)
    path.write_text('{"type":"object","type":"object"}', encoding="utf-8")
    assert any("MALFORMED_JSON" in error for error in checker.schema_policy_errors(repository))


def test_workflow_contract_binds_exact_github_sha_and_is_fail_closed(
    repository: Path,
) -> None:
    assert checker.workflow_policy_errors(repository) == []
    ci = repository / checker.CI_WORKFLOW_PATH
    text = ci.read_text(encoding="utf-8").replace('"$GITHUB_SHA"', '"' + "b" * 40 + '"', 1)
    ci.write_text(text, encoding="utf-8")
    errors = checker.workflow_policy_errors(repository)
    assert any("Generate deterministic universal SBOM inputs" in error for error in errors)
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    desktop.write_text(desktop.read_text(encoding="utf-8") + "        continue-on-error: true\n")
    assert checker.workflow_policy_errors(repository)


@pytest.mark.parametrize(
    ("reviewed", "mutation"),
    (
        (
            "    MCLAB_EVIDENCE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            "    MCLAB_EVIDENCE_SHA: ${{ github.sha }}",
        ),
        (
            "    ref: ${{ env.MCLAB_EVIDENCE_SHA }}",
            "    ref: ${{ github.event.pull_request.head.sha || github.sha }}",
        ),
        (
            '    if [[ ! "$MCLAB_EVIDENCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then',
            '    if [[ -z "$MCLAB_EVIDENCE_SHA" ]]; then',
        ),
        (
            '    head_sha="$(git rev-parse --verify \'HEAD^{commit}\')" || exit 1',
            '    head_sha="$(git rev-parse HEAD)"',
        ),
        (
            '    checkout_status="$(git status --porcelain=v1 --untracked-files=all)" || exit 1',
            '    checkout_status="$(git status --porcelain=v1 --untracked-files=no)"',
        ),
        (
            "    printf 'MCLAB_E2E_EVIDENCE=build/validation/%s/g2-%s/package_e2e.json\\n' \\",
            "    printf 'MCLAB_E2E_EVIDENCE=build/validation/g2-%s/package_e2e.json\\n' \\",
        ),
        (
            '    --output "$MCLAB_E2E_EVIDENCE"',
            '    --output "build/validation/$MCLAB_EVIDENCE_SHA/package_e2e.json"',
        ),
        (
            "    name: mclab-g2-${{ runner.os }}-${{ env.MCLAB_EVIDENCE_SHA }}",
            "    name: mclab-g2-${{ runner.os }}-${{ github.sha }}",
        ),
        (
            "    path: ${{ env.MCLAB_E2E_EVIDENCE }}",
            "    path: build/validation/${{ github.sha }}/package_e2e.json",
        ),
    ),
)
def test_desktop_package_evidence_contract_rejects_provenance_mutation(
    repository: Path,
    reviewed: str,
    mutation: str,
) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    text = desktop.read_text(encoding="utf-8")
    assert text.count(reviewed) == 1
    desktop.write_text(text.replace(reviewed, mutation, 1), encoding="utf-8")

    assert checker.workflow_policy_errors(repository)


@pytest.mark.parametrize(
    "extra",
    (
        (
            "      - name: Re-evaluate package evidence subject\n"
            "        run: echo '${{ github.event.pull_request.head.sha || github.sha }}'\n"
        ),
        (
            "      - name: Rebind package evidence path\n"
            "        run: echo 'MCLAB_E2E_EVIDENCE=alternate.json' >> \"$GITHUB_ENV\"\n"
        ),
    ),
)
def test_desktop_package_evidence_contract_rejects_extra_binding(
    repository: Path,
    extra: str,
) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    run = _workflow_policy_block(
        checker.DESKTOP_WORKFLOW_PATH,
        "Run packaged E2E readiness gate",
    )
    text = desktop.read_text(encoding="utf-8")
    assert run in text
    desktop.write_text(text.replace(run, extra + run, 1), encoding="utf-8")

    errors = checker.workflow_policy_errors(repository)
    assert any("controlled provenance token" in error for error in errors)


@pytest.mark.parametrize(
    "names",
    (
        (
            "Checkout exact package evidence subject",
            "Verify exact package evidence subject",
            "Bind packaged E2E evidence path",
        ),
        (
            "Run packaged E2E readiness gate",
            "Upload packaged E2E readiness evidence",
        ),
    ),
)
def test_desktop_package_evidence_contract_requires_reviewed_order(
    repository: Path,
    names: tuple[str, ...],
) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    blocks = [
        _workflow_policy_block(checker.DESKTOP_WORKFLOW_PATH, name)
        for name in names
    ]
    sequence = "".join(blocks)
    text = desktop.read_text(encoding="utf-8")
    assert sequence in text
    desktop.write_text(
        text.replace(sequence, blocks[1] + blocks[0] + "".join(blocks[2:]), 1),
        encoding="utf-8",
    )

    errors = checker.workflow_policy_errors(repository)
    assert any("reviewed order" in error for error in errors)


def test_desktop_package_evidence_contract_binds_path_before_audit(
    repository: Path,
) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    checkout = _workflow_policy_block(
        checker.DESKTOP_WORKFLOW_PATH,
        "Checkout exact package evidence subject",
    )
    run_and_upload = "".join(
        _workflow_policy_block(checker.DESKTOP_WORKFLOW_PATH, name)
        for name in (
            "Run packaged E2E readiness gate",
            "Upload packaged E2E readiness evidence",
        )
    )
    text = desktop.read_text(encoding="utf-8")
    assert checkout in text and run_and_upload in text
    text = text.replace(run_and_upload, "", 1)
    desktop.write_text(
        text.replace(checkout, run_and_upload + checkout, 1),
        encoding="utf-8",
    )

    errors = checker.workflow_policy_errors(repository)
    assert any("reviewed order" in error for error in errors)


@pytest.mark.parametrize(
    "mutation",
    (
        "prepend-exit",
        "expression-continue",
        "false-expression",
        "quoted-continue",
        "quoted-false",
    ),
)
def test_workflow_contract_rejects_neutralized_or_skipped_steps(
    repository: Path,
    mutation: str,
) -> None:
    ci = repository / checker.CI_WORKFLOW_PATH
    text = ci.read_text(encoding="utf-8")
    step = "      - name: Audit reviewed Python vulnerabilities\n"
    if mutation == "prepend-exit":
        text = text.replace(step, step + "        run: |\n          exit 0\n", 1).replace(
            "        run: |\n          python scripts/audit_supply_chain.py vulnerabilities",
            "          python scripts/audit_supply_chain.py vulnerabilities",
            1,
        )
    elif mutation == "expression-continue":
        text = text.replace(step, step + "        continue-on-error: ${{ true }}\n", 1)
    elif mutation == "false-expression":
        text = text.replace(step, step + "        if: ${{ false && always() }}\n", 1)
    elif mutation == "quoted-continue":
        text = text.replace(step, step + '        "continue-on-error": true\n', 1)
    else:
        text = text.replace(step, step + "        'if': false\n", 1)
    ci.write_text(text, encoding="utf-8")

    assert checker.workflow_policy_errors(repository)


@pytest.mark.parametrize(
    ("workflow_path", "step_name"),
    (
        (checker.CI_WORKFLOW_PATH, "Upload universal supply-chain evidence"),
        (checker.DESKTOP_WORKFLOW_PATH, "Upload target supply-chain evidence"),
    ),
)
def test_workflow_contract_requires_evidence_upload_step(
    repository: Path,
    workflow_path: str,
    step_name: str,
) -> None:
    policy = next(
        candidate
        for candidate in checker.WORKFLOW_STEP_POLICIES
        if candidate.path == workflow_path and candidate.name == step_name
    )
    block = "\n".join(f"      {line}" for line in policy.expected_lines) + "\n"
    path = repository / workflow_path
    text = path.read_text(encoding="utf-8")
    assert block in text
    path.write_text(text.replace(block, "", 1), encoding="utf-8")

    assert any(step_name in error for error in checker.workflow_policy_errors(repository))


def test_workflow_contract_requires_audit_before_upload(repository: Path) -> None:
    ci = repository / checker.CI_WORKFLOW_PATH
    audit_policy = next(
        policy
        for policy in checker.WORKFLOW_STEP_POLICIES
        if policy.path == checker.CI_WORKFLOW_PATH
        and policy.name == "Audit reviewed Python vulnerabilities"
    )
    upload_policy = next(
        policy
        for policy in checker.WORKFLOW_STEP_POLICIES
        if policy.path == checker.CI_WORKFLOW_PATH
        and policy.name == "Upload universal supply-chain evidence"
    )
    audit = "\n".join(f"      {line}" for line in audit_policy.expected_lines) + "\n"
    upload = "\n".join(f"      {line}" for line in upload_policy.expected_lines) + "\n"
    text = ci.read_text(encoding="utf-8")
    assert audit in text and upload in text
    assert audit + upload in text
    ci.write_text(text.replace(audit + upload, upload + audit, 1), encoding="utf-8")

    assert any("reviewed order" in error for error in checker.workflow_policy_errors(repository))


def test_desktop_workflow_validates_license_inventory_before_upload(
    repository: Path,
) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    names = (
        "Audit package-profile licenses",
        "Validate package-profile license inventory",
        "Upload target supply-chain evidence",
    )
    blocks = []
    for name in names:
        policy = next(
            candidate
            for candidate in checker.WORKFLOW_STEP_POLICIES
            if candidate.path == checker.DESKTOP_WORKFLOW_PATH
            and candidate.name == name
        )
        blocks.append(
            "\n".join(f"      {line}" for line in policy.expected_lines) + "\n"
        )
    sequence = "".join(blocks)
    text = desktop.read_text(encoding="utf-8")
    assert sequence in text
    desktop.write_text(
        text.replace(sequence, blocks[0] + blocks[2] + blocks[1], 1),
        encoding="utf-8",
    )

    assert any("reviewed order" in error for error in checker.workflow_policy_errors(repository))


@pytest.mark.parametrize(
    "tamper",
    (
        "      - name: Replace audited evidence\n"
        "        run: echo '{}' > build/validation/supply-chain/python-vulnerabilities.json\n",
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
        "      - name: README contract and local links\n"
        "        run: rm -f build/validation/supply-chain/python-vulnerabilities.json\n",
    ),
)
def test_workflow_contract_rejects_step_between_audit_and_upload(
    repository: Path,
    tamper: str,
) -> None:
    ci = repository / checker.CI_WORKFLOW_PATH
    upload_policy = next(
        policy
        for policy in checker.WORKFLOW_STEP_POLICIES
        if policy.path == checker.CI_WORKFLOW_PATH
        and policy.name == "Upload universal supply-chain evidence"
    )
    upload = "\n".join(f"      {line}" for line in upload_policy.expected_lines) + "\n"
    text = ci.read_text(encoding="utf-8")
    assert upload in text
    ci.write_text(text.replace(upload, tamper + upload, 1), encoding="utf-8")

    assert any("contiguous" in error for error in checker.workflow_policy_errors(repository))


def test_workflow_contract_rejects_steps_moved_to_another_job(repository: Path) -> None:
    ci = repository / checker.CI_WORKFLOW_PATH
    text = ci.read_text(encoding="utf-8")
    blocks = [
        "\n".join(f"      {line}" for line in policy.expected_lines) + "\n"
        for policy in checker.WORKFLOW_STEP_POLICIES
        if policy.path == checker.CI_WORKFLOW_PATH
    ]
    for block in blocks:
        assert block in text
        text = text.replace(block, "", 1)
    text += (
        "  nonrequired-supply-chain:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        + "".join(blocks)
    )
    ci.write_text(text, encoding="utf-8")

    errors = checker.workflow_policy_errors(repository)
    assert any("simulator" in error or "exactly one step" in error for error in errors)


def test_workflow_contract_requires_complete_desktop_matrix(repository: Path) -> None:
    desktop = repository / checker.DESKTOP_WORKFLOW_PATH
    text = desktop.read_text(encoding="utf-8")
    required = "      os: [windows-2025, ubuntu-24.04, macos-15]"
    assert required in text
    desktop.write_text(
        text.replace(required, "      os: [windows-2025, macos-15]", 1),
        encoding="utf-8",
    )

    errors = checker.workflow_policy_errors(repository)
    assert any("job matrix" in error for error in errors)


def test_generator_writes_byte_identical_files(
    repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _commit_fixture_repository(repository)
    monkeypatch.setattr(generator, "ROOT", repository)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert generator.main(["--source-commit", head, "--output", os.fspath(first)]) == 0
    assert generator.main(["--source-commit", head, "--output", os.fspath(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
