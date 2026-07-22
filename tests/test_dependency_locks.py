from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_dependency_locks.py"
SPEC = importlib.util.spec_from_file_location("check_dependency_locks", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)

POLICY_FILES = (
    "pyproject.toml",
    "README.md",
    "README.en.md",
    "docs/installation.md",
    "docs/troubleshooting.md",
    ".github/workflows/ci.yml",
    ".github/workflows/desktop.yml",
    CHECKER.PAPER_LOCK,
    "requirements/build.in",
    "requirements/tools/uv.in",
    "requirements/tools/supply-chain.in",
    "scripts/install_locked.py",
    "scripts/lock_requirements.py",
    "scripts/manage_dependency_locks.py",
    "scripts/start_mclab.py",
    "scripts/bootstrap_and_run.py",
    *CHECKER.EXPECTED_CMD_LAUNCHERS,
    *(profile.output for profile in CHECKER.EXPECTED_PROFILES),
)


@pytest.fixture
def lock_root(tmp_path: Path) -> Path:
    for relative in POLICY_FILES:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def _errors(root: Path) -> list[str]:
    _metrics, errors = CHECKER.validate(root)
    return errors


def _replace(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= count, old
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def _inject_lock_line(path: Path, line: str) -> None:
    _replace(path, "--only-binary :all:\n", f"--only-binary :all:\n{line}\n")


def test_current_repository_dependency_lock_policy_passes() -> None:
    metrics, errors = CHECKER.validate(ROOT)

    assert errors == []
    assert len(metrics) == 5
    assert all(metric.passed for metric in metrics)
    lock_metric = next(metric for metric in metrics if metric.name == "hashed lock profiles")
    assert "8/8 profiles" in lock_metric.measured
    assert "requirements" in lock_metric.measured
    assert "hashes" in lock_metric.measured
    install_metric = next(metric for metric in metrics if metric.name == "install surface policy")
    assert "19/19 launchers" in install_metric.measured


def test_checker_cli_reports_measured_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert CHECKER.main([]) == 0
    output = capsys.readouterr().out
    assert "PASS hashed lock profiles" in output
    assert "status: PASS" in output


def test_python_policy_and_every_direct_project_pin_are_exact(lock_root: Path) -> None:
    pyproject = lock_root / "pyproject.toml"
    _replace(pyproject, 'requires-python = ">=3.10,<3.13"', 'requires-python = ">=3.10"')
    _replace(pyproject, '"numpy==2.2.6"', '"numpy>=2.2.6"')
    _replace(pyproject, '"pytest==9.1.1"', '"pytest==9.1.0"')

    errors = _errors(lock_root)

    assert any(error.startswith("PYTHON_POLICY_MISMATCH") for error in errors)
    assert any("PYPROJECT_PIN_FORMAT project.dependencies" in error for error in errors)
    assert any("DIRECT_PINS_MISMATCH optional-dependencies.dev" in error for error in errors)


def test_build_uv_and_scanner_inputs_remain_exact_and_separate(lock_root: Path) -> None:
    build_input = lock_root / "requirements" / "build.in"
    uv_input = lock_root / "requirements" / "tools" / "uv.in"
    scanner_input = lock_root / "requirements" / "tools" / "supply-chain.in"
    build_input.write_text(build_input.read_text(encoding="utf-8") + "uv==0.11.31\n")
    uv_input.write_text("uv>=0.11.31\n", encoding="utf-8")
    scanner_input.write_text("pip-audit>=2.10.1\npip-licenses==5.5.5\n", encoding="utf-8")

    errors = _errors(lock_root)

    assert any("DIRECT_PINS_MISMATCH requirements/build.in" in error for error in errors)
    assert any("INPUT_PIN_FORMAT requirements/tools/uv.in" in error for error in errors)
    assert any(
        "INPUT_PIN_FORMAT requirements/tools/supply-chain.in" in error for error in errors
    )


def test_uv_cannot_enter_a_learner_or_build_lock(lock_root: Path) -> None:
    build_lock = lock_root / "requirements" / "locks" / "build.txt"
    digest = "0" * 64
    _inject_lock_line(build_lock, f"uv==0.11.31 --hash=sha256:{digest}")

    errors = _errors(lock_root)

    assert any(
        error == "BUILD_TOOL_SEPARATION build: uv must remain generator-only" for error in errors
    )


def test_scanners_cannot_enter_a_learner_or_build_lock(lock_root: Path) -> None:
    build_lock = lock_root / "requirements" / "locks" / "build.txt"
    digest = "0" * 64
    _inject_lock_line(build_lock, f"pip-audit==2.10.1 --hash=sha256:{digest}")

    errors = _errors(lock_root)

    assert any(
        error
        == "BUILD_TOOL_SEPARATION build: pip-audit must remain supply-chain-tool-only"
        for error in errors
    )


def test_lock_inventory_requires_exactly_the_eight_reviewed_profiles(lock_root: Path) -> None:
    (lock_root / "requirements" / "locks" / "runtime.txt").unlink()
    (lock_root / "requirements" / "locks" / "unreviewed.txt").write_text(
        "--only-binary :all:\n", encoding="utf-8"
    )

    errors = _errors(lock_root)

    assert "LOCK_INVENTORY_MISSING requirements/locks/runtime.txt" in errors
    assert "LOCK_INVENTORY_UNEXPECTED requirements/locks/unreviewed.txt" in errors
    assert any(
        error.startswith("POLICY_FILE_MISSING requirements/locks/runtime.txt") for error in errors
    )


@pytest.mark.parametrize(
    "line, expected_code",
    (
        ("--extra-index-url https://example.invalid/simple", "LOCK_UNSAFE_DIRECTIVE"),
        ("--find-links ../wheelhouse", "LOCK_UNSAFE_DIRECTIVE"),
        ("-e ../editable-project", "LOCK_UNSAFE_DIRECTIVE"),
        (
            f"demo @ git+https://example.invalid/demo.git --hash=sha256:{'1' * 64}",
            "LOCK_UNSAFE_SOURCE",
        ),
        (
            f"demo @ file:///tmp/demo.whl --hash=sha256:{'2' * 64}",
            "LOCK_UNSAFE_SOURCE",
        ),
    ),
)
def test_lock_rejects_index_local_editable_and_direct_sources(
    lock_root: Path,
    line: str,
    expected_code: str,
) -> None:
    tool_lock = lock_root / "requirements" / "tools" / "uv.txt"
    _inject_lock_line(tool_lock, line)

    errors = _errors(lock_root)

    assert any(error.startswith(expected_code) for error in errors)


def test_lock_rejects_an_option_hidden_inside_a_requirement(lock_root: Path) -> None:
    tool_lock = lock_root / "requirements" / "tools" / "uv.txt"
    _replace(
        tool_lock,
        " \\\n    --hash=sha256:",
        " --index-url=example.invalid/simple \\\n    --hash=sha256:",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("LOCK_UNSAFE_DIRECTIVE") for error in errors)


def test_every_locked_requirement_needs_a_lowercase_sha256_hash(lock_root: Path) -> None:
    tool_lock = lock_root / "requirements" / "tools" / "uv.txt"
    text = tool_lock.read_text(encoding="utf-8")
    text = re.sub(
        r"--hash=sha256:[0-9a-f]{64}",
        f"--hash=sha512:{'A' * 64}",
        text,
        count=1,
    )
    tool_lock.write_text(text, encoding="utf-8")

    errors = _errors(lock_root)

    assert any(error.startswith("LOCK_HASH_FORMAT") for error in errors)


def test_unhashed_and_unterminated_requirements_fail_closed(lock_root: Path) -> None:
    tool_lock = lock_root / "requirements" / "tools" / "uv.txt"
    header = tool_lock.read_text(encoding="utf-8").splitlines()[:2]
    tool_lock.write_text(
        "\n".join((*header, "--only-binary :all:", "", "uv==0.11.31 \\")) + "\n",
        encoding="utf-8",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("LOCK_UNTERMINATED_CONTINUATION") for error in errors)
    assert any(error.startswith("LOCK_EMPTY") for error in errors)


def test_profile_lock_contains_exact_direct_pin_surface(lock_root: Path) -> None:
    app_lock = lock_root / "requirements" / "locks" / "app.txt"
    _replace(app_lock, "pyside6-essentials==6.11.1", "pyside6-essentials==6.11.0")

    errors = _errors(lock_root)

    assert any(error.startswith("LOCK_PROFILE_DIRECT_MISMATCH app:") for error in errors)


def test_both_uv_environment_lists_contain_the_same_reviewed_twelve_cells(
    lock_root: Path,
) -> None:
    pyproject = lock_root / "pyproject.toml"
    marker = CHECKER.EXPECTED_ENVIRONMENTS[-1]
    _replace(pyproject, f'  "{marker}",\n', "", count=1)

    errors = _errors(lock_root)

    environment_errors = [error for error in errors if error.startswith("UV_ENVIRONMENTS_MISMATCH")]
    assert len(environment_errors) >= 2


@pytest.mark.parametrize(
    "old, new, expected_code",
    (
        ('UV_VERSION = "0.11.31"', 'UV_VERSION = "0.11.30"', "LOCK_GENERATOR_UV"),
        (
            'EXCLUDE_NEWER = "2026-07-22T07:45:00Z"',
            'EXCLUDE_NEWER = "2026-07-22T08:00:00Z"',
            "LOCK_GENERATOR_CUTOFF",
        ),
        ('            "--generate-hashes",', '            "--no-deps",', "LOCK_GENERATOR_FLAGS"),
        (
            'LockProfile("dev", "pyproject.toml", "requirements/locks/dev.txt", ("dev",))',
            'LockProfile("dev", "pyproject.toml", "requirements/locks/dev.txt", ("app",))',
            "LOCK_GENERATOR_PROFILES",
        ),
        ("        check=True,", "        check=False,", "LOCK_GENERATOR_UV_GUARD"),
        (
            "    if actual_uv != UV_VERSION:",
            "    if False:",
            "LOCK_GENERATOR_UV_GUARD",
        ),
    ),
)
def test_generator_constants_profiles_and_safety_flags_are_static_contracts(
    lock_root: Path,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    generator = lock_root / "scripts" / "lock_requirements.py"
    _replace(generator, old, new)

    errors = _errors(lock_root)

    assert any(error.startswith(expected_code) for error in errors)


def test_malformed_policy_files_report_errors_instead_of_escaping(lock_root: Path) -> None:
    (lock_root / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    (lock_root / "scripts" / "lock_requirements.py").write_text("def broken(:\n", encoding="utf-8")

    metrics, errors = CHECKER.validate(lock_root)

    assert any(error.startswith("PYPROJECT_INVALID") for error in errors)
    assert any(error.startswith("LOCK_GENERATOR_INVALID") for error in errors)
    assert any(not metric.passed for metric in metrics)


def test_out_of_tree_symlink_policy_file_is_rejected(lock_root: Path, tmp_path: Path) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external-build.in"
    external.write_text("pip==26.1.2\n", encoding="utf-8")
    build_input = lock_root / "requirements" / "build.in"
    build_input.unlink()
    build_input.symlink_to(external)

    errors = _errors(lock_root)

    assert any(error.startswith("POLICY_FILE_UNSAFE requirements/build.in") for error in errors)


def test_auxiliary_paper_lock_version_and_hash_are_reviewed(lock_root: Path) -> None:
    paper_lock = lock_root / CHECKER.PAPER_LOCK
    _replace(paper_lock, "PyYAML==6.0.3", "PyYAML==6.0.2")
    _replace(paper_lock, CHECKER.PAPER_LOCK_HASH, "0" * 64)

    errors = _errors(lock_root)

    assert any(error.startswith("PAPER_LOCK_MISMATCH") for error in errors)


@pytest.mark.parametrize(
    "old, new, expected_code",
    (
        ('        "--force-reinstall",', '        "--upgrade",', "INSTALLER_THIRD_PARTY"),
        (
            "        help=argparse.SUPPRESS,",
            '        help="external installs",',
            "INSTALLER_ENV_GUARD",
        ),
    ),
)
def test_installer_hash_and_external_environment_guards_are_static_contracts(
    lock_root: Path,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    installer = lock_root / "scripts" / "install_locked.py"
    _replace(installer, old, new)

    errors = _errors(lock_root)

    assert any(error.startswith(expected_code) for error in errors)


def test_installer_record_trust_must_cover_the_editable_loader(lock_root: Path) -> None:
    installer = lock_root / "scripts" / "install_locked.py"
    _replace(
        installer,
        "        expected[_normalise_name(PROJECT_NAME)] = PROJECT_VERSION",
        '        expected["local-project"] = PROJECT_VERSION',
    )

    errors = _errors(lock_root)

    assert any(error.startswith("INSTALLER_TRUST_ORDER") for error in errors)


def test_bootstrap_redirect_guard_is_a_static_contract(lock_root: Path) -> None:
    bootstrap = lock_root / "scripts" / "bootstrap_and_run.py"
    _replace(
        bootstrap,
        "    redirect_error = project_venv_redirect_error(VENV)\n",
        "    redirect_error = None\n",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("BOOTSTRAP_VENV_GUARD") for error in errors)


def test_windows_desktop_floor_is_a_static_contract(lock_root: Path) -> None:
    installer = lock_root / "scripts" / "install_locked.py"
    _replace(installer, "minimum_windows = (10, 0, 17763)", "minimum_windows = (10, 0, 17762)")

    errors = _errors(lock_root)

    assert any(error.startswith("INSTALLER_SUPPORT_ENVELOPE") for error in errors)


def test_disposable_manager_force_and_external_opt_in_are_static_contracts(
    lock_root: Path,
) -> None:
    manager = lock_root / "scripts" / "manage_dependency_locks.py"
    _replace(manager, '                    "--allow-external-env",\n', "")
    _replace(manager, '                    "--force-reinstall",\n', "")

    errors = _errors(lock_root)

    assert any(error.startswith("LOCK_MANAGER_POLICY") for error in errors)


def test_paper_workflow_install_must_force_hash_verification(lock_root: Path) -> None:
    workflow = lock_root / ".github" / "workflows" / "ci.yml"
    _replace(workflow, "          --force-reinstall\n", "")

    errors = _errors(lock_root)

    assert any(error.startswith("WORKFLOW_INSTALL_POLICY") for error in errors)


def test_new_raw_workflow_install_is_rejected(lock_root: Path) -> None:
    workflow = lock_root / ".github" / "workflows" / "desktop.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8")
        + "\n# forbidden mutation\n# python -m pip install demo\n",
        encoding="utf-8",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("WORKFLOW_INSTALL_POLICY") for error in errors)


def test_isolated_package_environment_install_is_a_static_contract(lock_root: Path) -> None:
    workflow = lock_root / ".github" / "workflows" / "desktop.yml"
    _replace(
        workflow,
        '          "$package_python" scripts/install_locked.py --allow-external-env package\n',
        "",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("WORKFLOW_INSTALL_POLICY") for error in errors)


def test_launcher_lock_probe_cannot_be_removed(lock_root: Path) -> None:
    launcher = lock_root / "run_lab01.cmd"
    _replace(launcher, "--check runtime", "--check app")

    errors = _errors(lock_root)

    assert any(error.startswith("LAUNCHER_INSTALL_POLICY run_lab01.cmd") for error in errors)


def test_public_guidance_cannot_expose_raw_or_external_install_bypass(
    lock_root: Path,
) -> None:
    installation = lock_root / "docs" / "installation.md"
    installation.write_text(
        installation.read_text(encoding="utf-8") + "\npip install unreviewed\n",
        encoding="utf-8",
    )

    errors = _errors(lock_root)

    assert any(error.startswith("PUBLIC_INSTALL_BYPASS docs/installation.md") for error in errors)


def test_new_script_level_pip_install_is_rejected(lock_root: Path) -> None:
    bootstrap = lock_root / "scripts" / "bootstrap_and_run.py"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8")
        + '\nFORBIDDEN_INSTALL = ["python", "-m", "pip", "install", "demo"]\n',
        encoding="utf-8",
    )

    errors = _errors(lock_root)

    assert any(
        error.startswith("SCRIPT_INSTALL_INVENTORY scripts/bootstrap_and_run.py")
        for error in errors
    )
