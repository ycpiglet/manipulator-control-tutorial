from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audit_supply_chain.py"
SPEC = importlib.util.spec_from_file_location("audit_supply_chain", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)

HASH_A = "a" * 64


def _lock(*requirements: str) -> str:
    return "--only-binary :all:\n\n" + "\n".join(requirements) + "\n"


def _requirement(
    name: str,
    version: str = "1.0",
    *,
    marker: str | None = None,
    digest: str = HASH_A,
) -> str:
    marker_text = f" ; {marker}" if marker else ""
    return (
        f"{name}=={version}{marker_text} \\"
        + f"\n    --hash=sha256:{digest}"
    )


def _inventory(*items: tuple[str, str]) -> dict[str, Any]:
    return {
        name: AUDIT.LockedRequirement(
            name=name,
            version=version,
            hashes=frozenset({HASH_A}),
            markers=(None,),
            profiles=frozenset({"runtime"}),
        )
        for name, version in items
    }


def _audit_json(
    *items: tuple[str, str, list[dict[str, Any]]],
    fixes: list[dict[str, Any]] | None = None,
) -> str:
    return json.dumps(
        {
            "dependencies": [
                {"name": name, "version": version, "vulns": vulns}
                for name, version, vulns in items
            ],
            "fixes": [] if fixes is None else fixes,
        }
    )


def _target_environment(**updates: str) -> dict[str, str]:
    environment = {
        "implementation_name": "cpython",
        "python_full_version": "3.12.4",
        "python_version": "3.12",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "sys_platform": "linux",
    }
    environment.update(updates)
    return environment


def _license_item(
    name: str,
    version: str,
    *,
    license_value: str = "MIT License",
    url: str = "https://example.invalid/project",
    license_text: str = "Permission is hereby granted.\n",
    notice_text: str = "UNKNOWN",
) -> dict[str, str]:
    return {
        "Name": name,
        "Version": version,
        "License": license_value,
        "URL": url,
        "LicenseText": license_text,
        "NoticeText": notice_text,
    }


def test_committed_tool_input_and_empty_waiver_contract() -> None:
    assert (ROOT / "requirements/tools/supply-chain.in").read_text(encoding="utf-8") == (
        "pip-audit==2.10.1\npip-licenses==5.5.5\n"
    )
    assert json.loads(
        (ROOT / ".agents/supply_chain/vulnerability-waivers.json").read_text(
            encoding="utf-8"
        )
    ) == {"schema_version": 1, "waivers": []}


def test_repository_locks_form_one_marker_free_canonical_inventory() -> None:
    profiles, inventory = AUDIT.load_reviewed_locks(ROOT)
    rendered = AUDIT.render_canonical_requirements(inventory)

    assert list(profiles) == [profile for profile, _ in AUDIT.REVIEWED_LOCKS]
    assert [profile for profile, _ in AUDIT.REVIEWED_LOCKS][-1] == "supply-chain-tool"
    assert ";" not in rendered
    assert "--only-binary :all:" in rendered
    assert "pip-audit==2.10.1" in rendered
    assert "pip-licenses==5.5.5" in rendered
    for platform_only in ("colorama", "macholib", "pefile", "pywin32-ctypes"):
        assert f"{platform_only}==" in rendered


def test_lock_parser_strips_markers_but_keeps_platform_only_dependency() -> None:
    marker = "python_full_version < '3.13' and sys_platform == 'win32'"
    parsed = AUDIT.parse_lock_text(
        _lock(_requirement("Colorama", marker=marker)),
        profile="package",
        source="fixture.txt",
    )

    assert parsed["colorama"].markers == (marker,)
    canonical = AUDIT.render_canonical_requirements(parsed)
    assert "colorama==1.0" in canonical
    assert "win32" not in canonical


@pytest.mark.parametrize(
    "requirement",
    [
        "demo==1.0",
        "demo==1.0 --hash=sha256:" + "a" * 63,
        "demo==1.0 --hash=sha256:" + "A" * 64,
        "demo==1.0 --hash=sha512:" + "a" * 64,
        "demo>=1.0 --hash=sha256:" + HASH_A,
        "demo @ https://example.invalid/demo.whl --hash=sha256:" + HASH_A,
    ],
)
def test_lock_parser_rejects_missing_bad_or_unsafe_hash_contract(requirement: str) -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError):
        AUDIT.parse_lock_text(
            _lock(requirement),
            profile="fixture",
            source="fixture.txt",
        )


def test_lock_merge_rejects_conflicting_versions() -> None:
    first = AUDIT.parse_lock_text(
        _lock(_requirement("demo", "1.0")), profile="one", source="one.txt"
    )
    second = AUDIT.parse_lock_text(
        _lock(_requirement("demo", "2.0")), profile="two", source="two.txt"
    )

    with pytest.raises(AUDIT.SupplyChainAuditError, match="conflict"):
        AUDIT.merge_lock_inventories({"one": first, "two": second})


def test_any_nonempty_vulnerability_waiver_is_rejected(tmp_path: Path) -> None:
    waiver = tmp_path / AUDIT.WAIVER_REGISTRY
    waiver.parent.mkdir(parents=True)
    waiver.write_text(
        json.dumps({"schema_version": 1, "waivers": [{"id": "CVE-2099-0001"}]}),
        encoding="utf-8",
    )

    with pytest.raises(AUDIT.SupplyChainAuditError, match="not authorized"):
        AUDIT.load_waiver_registry(tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":1,"schema_version":1,"waivers":[]}',
        '{"schema_version":1,"waivers":[],"extra":true}',
        '{"schema_version":2,"waivers":[]}',
        '{"schema_version":1,"waivers":{}}',
    ],
)
def test_waiver_registry_rejects_duplicate_extra_or_invalid_schema(
    tmp_path: Path, payload: str
) -> None:
    waiver = tmp_path / AUDIT.WAIVER_REGISTRY
    waiver.parent.mkdir(parents=True)
    waiver.write_text(payload, encoding="utf-8")

    with pytest.raises(AUDIT.SupplyChainAuditError):
        AUDIT.load_waiver_registry(tmp_path)


def test_vulnerability_output_has_exact_coverage_and_normalized_findings() -> None:
    inventory = _inventory(("alpha", "1.0"), ("beta", "2.0"))
    vulnerability = {
        "id": "PYSEC-2099-1",
        "aliases": ["GHSA-z", "CVE-2099-1", "GHSA-z"],
        "fix_versions": ["1.2", "1.1", "1.2"],
    }
    stdout = _audit_json(("beta", "2.0", []), ("Alpha", "1.0", [vulnerability]))

    result = AUDIT.normalize_vulnerability_output(
        stdout, returncode=1, inventory=inventory
    )

    assert result["result"] == "fail"
    assert result["finding_count"] == 1
    assert result["lock_profiles"][-1] == "supply-chain-tool"
    assert [item["name"] for item in result["dependencies"]] == ["alpha", "beta"]
    finding = result["dependencies"][0]["vulnerabilities"][0]
    assert finding["aliases"] == ["CVE-2099-1", "GHSA-z"]
    assert finding["fix_versions"] == ["1.1", "1.2"]


@pytest.mark.parametrize(
    ("stdout", "returncode", "message"),
    [
        (_audit_json(("alpha", "1.0", [])), 0, "coverage drift"),
        (
            _audit_json(
                ("alpha", "1.0", []),
                ("beta", "2.0", []),
                ("extra", "3.0", []),
            ),
            0,
            "coverage drift",
        ),
        (
            _audit_json(
                ("alpha", "1.0", []),
                ("Alpha", "1.0", []),
                ("beta", "2.0", []),
            ),
            0,
            "duplicate dependency",
        ),
        (_audit_json(("alpha", "9.0", []), ("beta", "2.0", [])), 0, "version drift"),
    ],
)
def test_vulnerability_output_rejects_missing_extra_duplicate_or_wrong_version(
    stdout: str, returncode: int, message: str
) -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError, match=message):
        AUDIT.normalize_vulnerability_output(
            stdout,
            returncode=returncode,
            inventory=_inventory(("alpha", "1.0"), ("beta", "2.0")),
        )


@pytest.mark.parametrize(
    "stdout",
    [
        "not-json",
        '{"dependencies":[],"dependencies":[],"fixes":[]}',
        '{"dependencies":[],"fixes":[],"extra":true}',
        '[{"dependencies":[],"fixes":[]}]',
    ],
)
def test_vulnerability_output_rejects_malformed_or_ambiguous_json(stdout: str) -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError):
        AUDIT.normalize_vulnerability_output(stdout, returncode=0, inventory={})


def test_vulnerability_output_rejects_skips_and_fix_mode_output() -> None:
    skipped = json.dumps(
        {"dependencies": [{"name": "alpha", "skip_reason": "bad"}], "fixes": []}
    )
    with pytest.raises(AUDIT.SupplyChainAuditError, match="skipped"):
        AUDIT.normalize_vulnerability_output(
            skipped, returncode=0, inventory=_inventory(("alpha", "1.0"))
        )
    with pytest.raises(AUDIT.SupplyChainAuditError, match="fixes"):
        AUDIT.normalize_vulnerability_output(
            _audit_json(("alpha", "1.0", []), fixes=[{"name": "alpha"}]),
            returncode=0,
            inventory=_inventory(("alpha", "1.0")),
        )


@pytest.mark.parametrize(
    ("returncode", "vulns"),
    [
        (1, []),
        (
            0,
            [{"id": "CVE-1", "aliases": [], "fix_versions": []}],
        ),
    ],
)
def test_vulnerability_output_rejects_exit_result_inconsistency(
    returncode: int, vulns: list[dict[str, Any]]
) -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError, match="inconsistency"):
        AUDIT.normalize_vulnerability_output(
            _audit_json(("alpha", "1.0", vulns)),
            returncode=returncode,
            inventory=_inventory(("alpha", "1.0")),
        )


def test_vulnerability_output_rejects_non_contract_exit_code() -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError, match="unsupported exit code"):
        AUDIT.normalize_vulnerability_output("{}", returncode=2, inventory={})


def test_vulnerability_command_is_strict_hash_only_pypi_and_bounded() -> None:
    command = AUDIT.vulnerability_command(
        Path("tool-python"), Path("canonical.txt"), Path("disposable/cache")
    )
    expected_flags = {
        "--strict",
        "--no-deps",
        "--require-hashes",
        "--disable-pip",
        "--timeout",
        "--cache-dir",
        "--progress-spinner",
        "--aliases",
        "--desc",
        "--vulnerability-service",
    }
    assert expected_flags <= set(command)
    assert "pypi" in command
    assert "--ignore-vuln" not in command
    assert str(AUDIT.SOCKET_TIMEOUT_SECONDS) in command
    assert command[command.index("--cache-dir") + 1] == "disposable/cache"


def test_vulnerability_run_uses_its_disposable_cache_and_scrubbed_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "tool-work"
    work.mkdir()
    destination = tmp_path / "evidence.json"
    inventory = _inventory(("alpha", "1.0"))
    captured: dict[str, Any] = {}

    @contextmanager
    def fake_tools(*_: Any, **__: Any) -> Any:
        yield AUDIT.ToolEnvironment(python=Path("tool-python"), work=work)

    def fake_execute(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["environment"] = kwargs["environment"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=_audit_json(("alpha", "1.0", [])),
            stderr="",
        )

    monkeypatch.setattr(AUDIT, "validated_output_path", lambda *_args, **_kwargs: destination)
    monkeypatch.setattr(AUDIT, "load_waiver_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(AUDIT, "load_reviewed_locks", lambda *_args, **_kwargs: ({}, inventory))
    monkeypatch.setattr(AUDIT, "disposable_tool_environment", fake_tools)
    monkeypatch.setattr(AUDIT, "_execute", fake_execute)
    monkeypatch.setattr(AUDIT, "write_evidence", lambda path, evidence: None)
    monkeypatch.setenv("PIP_AUDIT_OUTPUT", "unsafe.json")

    assert AUDIT.run_vulnerability_audit(destination, root=tmp_path) == 0
    command = captured["command"]
    assert command[command.index("--cache-dir") + 1] == str(work / "cache")
    assert all(
        not key.upper().startswith("PIP_AUDIT_") for key in captured["environment"]
    )


def test_environment_scrubs_all_case_variants_of_pip_audit_overrides() -> None:
    cleaned = AUDIT.sanitized_environment(
        {
            "PIP_AUDIT_FORMAT": "markdown",
            "pip_audit_output": "outside.json",
            "PiP_AuDiT_Desc": "on",
            "PYTHONHOME": "/unsafe",
            "PYTHONPATH": "/unsafe",
            "KEEP": "yes",
        }
    )
    assert all(not key.upper().startswith("PIP_AUDIT_") for key in cleaned)
    assert "PYTHONHOME" not in cleaned
    assert cleaned["PYTHONPATH"] == ""
    assert cleaned["KEEP"] == "yes"


def test_disposable_tool_environment_installs_only_two_hash_locked_locks() -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        stdout = ""
        if command[-2:] == ["pip_audit", "--version"]:
            stdout = "pip-audit 2.10.1\n"
        elif command[-2:] == ["piplicenses", "--version"]:
            stdout = "piplicenses.py 5.5.5\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with AUDIT.disposable_tool_environment(ROOT, runner=fake_runner):
        pass

    installs = [command for command in calls if command[1:3] == ["-m", "pip"]]
    assert len(installs) == 2
    assert [Path(command[-1]).name for command in installs] == ["build.txt", "supply-chain.txt"]
    for command in installs:
        assert "--isolated" in command
        assert "--require-hashes" in command
        assert "--only-binary=:all:" in command


def test_tool_version_mismatch_and_command_timeout_fail_closed(tmp_path: Path) -> None:
    def wrong_version(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="pip-audit 2.9.0\n", stderr="")

    with pytest.raises(AUDIT.SupplyChainAuditError, match="exactly 2.10.1"):
        AUDIT._verify_tool_version(
            Path("python"),
            "pip_audit",
            "2.10.1",
            cwd=tmp_path,
            environment={},
            runner=wrong_version,
        )

    def timeout(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 1)

    with pytest.raises(AUDIT.SupplyChainAuditError, match="timed out"):
        AUDIT._execute(
            ["scanner"], cwd=tmp_path, timeout=1, environment={}, runner=timeout
        )


def test_tool_nonzero_exit_fails_closed() -> None:
    completed = subprocess.CompletedProcess(["tool"], 7, stdout="", stderr="error")
    with pytest.raises(AUDIT.SupplyChainAuditError, match="exit code 7"):
        AUDIT._require_success(completed, action="scanner")


def test_marker_evaluation_selects_only_target_platform() -> None:
    windows = "python_full_version < '3.13' and sys_platform == 'win32'"
    assert not AUDIT.marker_applies(windows, _target_environment())
    assert AUDIT.marker_applies(windows, _target_environment(sys_platform="win32"))


def test_target_probe_rejects_duplicate_distribution_and_malformed_json() -> None:
    duplicate = json.dumps(
        {
            "environment": _target_environment(),
            "distributions": [
                {"name": "Demo", "version": "1.0"},
                {"name": "demo", "version": "1.0"},
            ],
        }
    )
    with pytest.raises(AUDIT.SupplyChainAuditError, match="duplicate distribution"):
        AUDIT.normalize_target_probe(duplicate)
    with pytest.raises(AUDIT.SupplyChainAuditError):
        AUDIT.normalize_target_probe("not-json")


def test_target_inventory_requires_expected_name_and_version_coverage() -> None:
    expected = {"demo": "1.0", "mujoco-manipulator-control-lab": "0.1.0"}
    actual = expected | {"pip": "26.1.2", "setuptools": "83.0.0", "wheel": "0.47.0"}
    AUDIT.validate_target_inventory(actual, expected)
    AUDIT.validate_target_inventory(actual | {"certifi": "2026.1.4"}, expected)
    with pytest.raises(AUDIT.SupplyChainAuditError, match="missing"):
        AUDIT.validate_target_inventory(
            {name: version for name, version in actual.items() if name != "demo"},
            expected,
        )
    with pytest.raises(AUDIT.SupplyChainAuditError, match="version_mismatch"):
        AUDIT.validate_target_inventory(actual | {"demo": "2.0"}, expected)


def test_license_command_uses_explicit_target_mixed_json_texts_and_no_paths() -> None:
    expected = {"zeta-package": "2.0", "alpha-package": "1.0"}
    command = AUDIT.license_command(
        Path("tool-python"),
        Path("target-python"),
        expected,
    )
    for token in (
        "--python",
        "target-python",
        "--from",
        "mixed",
        "--format",
        "json",
        "--with-urls",
        "--with-system",
        "--with-license-file",
        "--with-notice-file",
        "--no-license-path",
        "--ignore-packages",
        "--packages",
    ):
        assert token in command
    for excluded in AUDIT.LICENSE_EXCLUDED_PACKAGES:
        assert excluded in command
    packages_index = command.index("--packages")
    assert command[packages_index + 1 :] == sorted(expected)
    assert "certifi" not in command[packages_index + 1 :]
    assert "--output-file" not in command


def test_license_output_is_deterministic_and_labels_lic01_input() -> None:
    expected = {"alpha": "1.0", "beta": "2.0"}
    raw = json.dumps(
        [
            _license_item(
                "Beta",
                "2.0",
                license_value="Zlib; MIT; Zlib",
                url="UNKNOWN",
                license_text="line one  \r\nline two\r\n",
                notice_text="UNKNOWN",
            ),
            _license_item("alpha", "1.0", notice_text="Copyright notice\r\n"),
        ]
    )

    result = AUDIT.normalize_license_output(
        raw,
        expected=expected,
        environment=_target_environment(),
        profile="package",
    )

    assert result["purpose"] == "LIC-01 input only; not legal approval"
    assert result["result"] == "inventory-complete"
    assert result["compliance_status"] == "pending-lic-01"
    assert [package["name"] for package in result["packages"]] == ["alpha", "beta"]
    beta = result["packages"][1]
    assert beta["license"] == "MIT; Zlib"
    assert beta["license_text"] == "line one\nline two"
    assert beta["url"] is None
    assert beta["notice_text"] is None
    assert result["metadata_gaps"] == {
        "license": 0,
        "license_text": 0,
        "notice_text": 1,
        "url": 1,
    }
    assert "path" not in json.dumps(result).casefold()


@pytest.mark.parametrize("license_value", ["", "   ", "UNKNOWN", "unknown"])
def test_license_output_records_empty_or_unknown_license_gap(license_value: str) -> None:
    result = AUDIT.normalize_license_output(
        json.dumps([_license_item("demo", "1.0", license_value=license_value)]),
        expected={"demo": "1.0"},
        environment=_target_environment(),
        profile="package",
    )

    assert result["packages"][0]["license"] is None
    assert result["metadata_gaps"]["license"] == 1


@pytest.mark.parametrize("license_text", ["", "UNKNOWN"])
def test_license_output_records_missing_license_text_gap(license_text: str) -> None:
    result = AUDIT.normalize_license_output(
        json.dumps([_license_item("demo", "1.0", license_text=license_text)]),
        expected={"demo": "1.0"},
        environment=_target_environment(),
        profile="package",
    )

    assert result["packages"][0]["license_text"] is None
    assert result["metadata_gaps"]["license_text"] == 1


def test_license_output_records_known_package_profile_gap_shape() -> None:
    expected = {
        "axe-playwright-python": "0.1.7",
        "pyopengl": "3.1.10",
        "pyside6-essentials": "6.11.1",
        "shiboken6": "6.11.1",
    }
    raw = json.dumps(
        [
            _license_item("axe-playwright-python", "0.1.7", license_value="UNKNOWN"),
            _license_item("PyOpenGL", "3.1.10", license_text="UNKNOWN"),
            _license_item("PySide6_Essentials", "6.11.1", license_text="UNKNOWN"),
            _license_item("shiboken6", "6.11.1", license_text="UNKNOWN"),
        ]
    )

    result = AUDIT.normalize_license_output(
        raw,
        expected=expected,
        environment=_target_environment(),
        profile="package",
    )

    assert result["metadata_gaps"]["license"] == 1
    assert result["metadata_gaps"]["license_text"] == 3
    assert result["result"] == "inventory-complete"
    assert result["compliance_status"] == "pending-lic-01"


@pytest.mark.parametrize(
    "items",
    [
        [],
        [_license_item("demo", "1.0"), _license_item("extra", "1.0")],
        [_license_item("Demo", "1.0"), _license_item("demo", "1.0")],
        [_license_item("demo", "2.0")],
    ],
)
def test_license_output_rejects_missing_extra_duplicate_or_wrong_version(
    items: list[dict[str, str]],
) -> None:
    with pytest.raises(AUDIT.SupplyChainAuditError):
        AUDIT.normalize_license_output(
            json.dumps(items),
            expected={"demo": "1.0"},
            environment=_target_environment(),
            profile="package",
        )


def test_license_output_rejects_path_fields_and_duplicate_json_keys() -> None:
    item = _license_item("demo", "1.0") | {"LicenseFile": "/secret/LICENSE"}
    with pytest.raises(AUDIT.SupplyChainAuditError, match="no paths"):
        AUDIT.normalize_license_output(
            json.dumps([item]),
            expected={"demo": "1.0"},
            environment=_target_environment(),
            profile="package",
        )
    duplicate = (
        '[{"Name":"demo","Name":"other","Version":"1.0",'
        '"License":"MIT","URL":"UNKNOWN","LicenseText":"text",'
        '"NoticeText":"UNKNOWN"}]'
    )
    with pytest.raises(AUDIT.SupplyChainAuditError, match="duplicate JSON key"):
        AUDIT.normalize_license_output(
            duplicate,
            expected={"demo": "1.0"},
            environment=_target_environment(),
            profile="package",
        )


def test_output_path_is_restricted_to_new_json_under_validation(tmp_path: Path) -> None:
    safe = AUDIT.validated_output_path(
        Path("build/validation/subject/python-vulnerabilities.json"), root=tmp_path
    )
    assert safe == tmp_path / "build/validation/subject/python-vulnerabilities.json"

    for unsafe in (
        Path("outputs/audit.json"),
        Path("build/audit.json"),
        Path("../audit.json"),
        tmp_path.parent / "outside.json",
        Path("build/validation/audit.txt"),
    ):
        with pytest.raises(AUDIT.SupplyChainAuditError):
            AUDIT.validated_output_path(unsafe, root=tmp_path)


def test_output_path_rejects_existing_file_and_symlink_parent(tmp_path: Path) -> None:
    existing = tmp_path / "build/validation/audit.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(AUDIT.SupplyChainAuditError, match="already exists"):
        AUDIT.validated_output_path(existing, root=tmp_path)

    if hasattr(os, "symlink"):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = tmp_path / "build/validation/link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are unavailable")
        with pytest.raises(AUDIT.SupplyChainAuditError):
            AUDIT.validated_output_path(link / "audit.json", root=tmp_path)


def test_output_path_rejects_external_lexical_alias_of_repository(tmp_path: Path) -> None:
    (tmp_path / "build/validation").mkdir(parents=True)
    alias = tmp_path.parent / f"{tmp_path.name}-alias"
    try:
        alias.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    try:
        with pytest.raises(AUDIT.SupplyChainAuditError, match="remain under"):
            AUDIT.validated_output_path(
                alias / "build/validation/audit.json",
                root=tmp_path,
            )
    finally:
        alias.unlink(missing_ok=True)


def test_evidence_writer_emits_canonical_utf8_lf_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "build/validation/evidence.json"
    evidence = {"z": "한글", "a": {"value": "line one\nline two"}}

    AUDIT.write_evidence(destination, evidence)

    payload = destination.read_bytes()
    assert payload == (
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    assert b"\r" not in payload


def test_target_python_validation_preserves_venv_symlink_invocation(tmp_path: Path) -> None:
    interpreter = tmp_path / "system-python"
    interpreter.write_text("placeholder", encoding="utf-8")
    venv_python = tmp_path / ".venv/bin/python"
    venv_python.parent.mkdir(parents=True)
    try:
        venv_python.symlink_to(interpreter)
    except OSError:
        pytest.skip("file symlinks are unavailable")

    validated = AUDIT.validated_target_python_path(Path(".venv/bin/python"), root=tmp_path)

    assert validated == venv_python
    assert validated != interpreter
    assert validated.resolve() == interpreter


def test_cli_requires_explicit_mode_outputs_target_and_profile() -> None:
    parser = AUDIT.build_parser()
    vulnerabilities = parser.parse_args(
        ["vulnerabilities", "--output", "build/validation/vulns.json"]
    )
    licenses = parser.parse_args(
        [
            "licenses",
            "--target-python",
            ".venv/bin/python",
            "--profile",
            "package",
            "--output",
            "build/validation/licenses.json",
        ]
    )
    assert vulnerabilities.mode == "vulnerabilities"
    assert licenses.mode == "licenses"
    assert licenses.profile == "package"
