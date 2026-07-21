from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_readme_contract.py"
SPEC = importlib.util.spec_from_file_location("mclab_readme_contract", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def _copy_contract_fixture(destination: Path) -> Path:
    """Create the smallest current-state tree that the contract checker needs."""

    for relative_path in CHECKER.LINK_DOCUMENTS:
        source = ROOT / relative_path
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    linked_targets: set[str] = set()
    for relative_path in CHECKER.LINK_DOCUMENTS:
        linked_targets.update(CHECKER.markdown_local_targets(ROOT, relative_path))
    for linked_target in linked_targets:
        source = ROOT / linked_target
        target = destination / linked_target
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            target.mkdir(exist_ok=True)
        else:
            shutil.copy2(source, target)

    for row in CHECKER.REPOSITORY_MAP_CONTRACT:
        for relative_path in row:
            (destination / relative_path).mkdir(parents=True, exist_ok=True)
    for row in CHECKER.STRUCTURE_LAYOUT_CONTRACT:
        for relative_path in row:
            (destination / relative_path).mkdir(parents=True, exist_ok=True)

    for launcher in (*CHECKER.PUBLIC_LAUNCHERS, *CHECKER.ROOT_LAUNCHER_INVENTORY):
        shutil.copy2(ROOT / launcher, destination / launcher)

    for relative_path in CHECKER.PUBLIC_FILES:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, target)

    cli_target = destination / "src" / "mclab" / "cli.py"
    cli_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src" / "mclab" / "cli.py", cli_target)
    return destination


@pytest.fixture
def contract_root(tmp_path: Path) -> Path:
    return _copy_contract_fixture(tmp_path)


def _errors(root: Path) -> list[str]:
    metrics, errors = CHECKER.validate(root)
    assert metrics
    return errors


def test_current_repository_readme_contract_passes() -> None:
    metrics, errors = CHECKER.validate(ROOT)

    assert errors == []
    assert metrics
    assert all(metric.passed for metric in metrics)


def test_fixture_matches_current_contract(contract_root: Path) -> None:
    assert _errors(contract_root) == []


def test_documented_cli_invocations_parse_with_installed_runtime() -> None:
    assert CHECKER.runtime_cli_invocation_errors() == ()


def test_runtime_cli_gate_converts_parser_system_exit_to_error() -> None:
    with patch("mclab.cli.build_parser", side_effect=SystemExit(0)):
        errors = CHECKER._runtime_cli_invocation_errors_in_process()

    assert errors == ("runtime parser build exited with 0",)


def test_runtime_cli_gate_converts_import_system_exit_to_error() -> None:
    with patch("builtins.__import__", side_effect=SystemExit(0)):
        errors = CHECKER._runtime_cli_invocation_errors_in_process()

    assert errors == ("runtime CLI import exited with 0",)


def test_runtime_cli_gate_rejects_silent_worker_exit_zero() -> None:
    completed = CHECKER.subprocess.CompletedProcess(
        args=("python", "worker"),
        returncode=0,
        stdout="",
        stderr="",
    )
    with patch.object(CHECKER.subprocess, "run", return_value=completed):
        errors = CHECKER.runtime_cli_invocation_errors()

    assert errors == (
        "runtime CLI worker exited with 0 without exactly one authenticated result",
    )


def test_runtime_cli_gate_survives_hard_worker_exit(
    contract_root: Path,
) -> None:
    package_root = contract_root / "src" / "mclab"
    shutil.copytree(ROOT / "src" / "mclab", package_root, dirs_exist_ok=True)
    cli_path = package_root / "cli.py"
    cli_path.write_text(
        cli_path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            '    getattr(os, "_exit")(0)\n',
            1,
        ),
        encoding="utf-8",
    )
    checker_path = contract_root / ".agents" / "validation" / CHECKER_PATH.name
    checker_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKER_PATH, checker_path)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(contract_root / "src")

    completed = subprocess.run(
        [sys.executable, str(checker_path), "--runtime-cli"],
        cwd=contract_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "without exactly one authenticated result" in completed.stdout
    assert "status: FAIL" in completed.stdout


def test_broken_local_link_fails(contract_root: Path) -> None:
    (contract_root / "docs" / "learner_guide.md").unlink()

    assert any("BROKEN_LINK" in error for error in _errors(contract_root))


def test_missing_anchor_fails(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "installation.md#source-setup", "installation.md#missing-source-setup"
        ),
        encoding="utf-8",
    )

    assert any("MISSING_ANCHOR" in error for error in _errors(contract_root))


def test_reference_style_link_is_explicitly_rejected(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n[broken reference][missing-doc]\n"
        + "[missing-doc]: missing.md\n",
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_REFERENCE_LINK" in error for error in _errors(contract_root))


def test_multiline_link_label_is_explicitly_rejected(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(
        "[broken\nlink](missing.md)\n",
        encoding="utf-8",
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert any("UNSUPPORTED_MULTILINE_LINK" in error for error in errors)


def test_nested_multiline_link_label_is_explicitly_rejected() -> None:
    _links, errors = CHECKER.inline_link_destinations(
        "[foo [bar]\nbaz](missing.md)\n"
    )

    assert errors == [(1, "UNSUPPORTED_MULTILINE_LINK")]


def test_bare_cr_multiline_link_label_is_explicitly_rejected() -> None:
    _links, errors = CHECKER.inline_link_destinations(
        "[broken\rlink](missing.md)\r"
    )

    assert errors == [(1, "UNSUPPORTED_MULTILINE_LINK")]


def test_multiline_link_syntax_inside_html_block_is_not_markdown() -> None:
    errors = CHECKER.multiline_inline_link_errors(
        "<div>\n[foo\nbar](missing.md)\n</div>\n\n"
    )

    assert errors == []


def test_multiline_link_scan_has_bounded_backslash_runtime() -> None:
    probe = """
import importlib.util
import sys
from pathlib import Path

path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("readme_contract_probe", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.multiline_inline_link_errors(
    "[" + chr(92) * 30 + chr(10) + "x" * 30
)
"""

    completed = subprocess.run(
        [sys.executable, "-c", probe, str(CHECKER_PATH)],
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )

    assert completed.returncode == 0, completed.stderr


def test_multiline_link_title_cannot_supply_required_prose(
    contract_root: Path,
) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace(
        marker,
        "The structural decision remains pending.",
        1,
    )
    path.write_text(
        text
        + '\n[compatibility\nboundary](https://example.invalid "'
        + marker
        + '")\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_MULTILINE_LINK" in error for error in _errors(contract_root))


def test_raw_html_link_is_explicitly_rejected(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + '\n<a href="missing.md">hidden</a>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_raw_html_backticks_cannot_mask_link_attribute(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<a title="`" href="missing.md" data-note="`">broken</a>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_fence_markers_inside_html_block_cannot_mask_link_attribute(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<div>\n```\n<a href="missing.md">broken</a>\n```\n</div>\n\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_raw_html_srcset_is_explicitly_rejected(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<picture><source srcset="missing.webp 1x"></picture>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "html",
    (
        '<a title=">" href="missing.md">hidden</a>',
        '<img alt=">" src="missing.png">',
        '<meta http-equiv="refresh" content="0; url=missing.md">',
    ),
)
def test_raw_html_url_attributes_with_complex_values_are_rejected(
    contract_root: Path, html: str
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n{html}\n",
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_raw_html_non_url_attribute_does_not_false_positive(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<div title="example src=not-a-url">safe</div>\n',
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_html_template_is_rejected_as_hidden_contract_content(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n<template>hidden prose</template>\n",
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "html",
    (
        "<canvas>hidden prose</canvas>",
        "<dialog>hidden prose</dialog>",
        "<iframe>hidden prose</iframe>",
        "<noframes>hidden prose</noframes>",
        "<noscript>hidden prose</noscript>",
        "<title>hidden prose</title>",
        "<div popover>hidden prose</div>",
    ),
)
def test_other_hidden_html_containers_are_rejected(
    contract_root: Path,
    html: str,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n{html}\n",
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "style_value",
    ("color: red", r"background:u\72l(missing.png)"),
)
def test_raw_html_style_is_explicitly_rejected(
    contract_root: Path, style_value: str
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f'\n<div style="{style_value}">unsupported</div>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_STYLE" in error for error in _errors(contract_root))


def test_language_switch_hidden_in_comment_does_not_count(contract_root: Path) -> None:
    path = contract_root / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "[English](README.en.md)", "<!-- [English](README.en.md) -->", 1
        ),
        encoding="utf-8",
    )

    assert any("LANGUAGE_SWITCH" in error for error in _errors(contract_root))


def test_language_switch_hidden_in_indented_code_does_not_count(contract_root: Path) -> None:
    path = contract_root / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "[English](README.en.md)", "    [English](README.en.md)", 1
        ),
        encoding="utf-8",
    )

    errors = _errors(contract_root)
    assert any("UNSUPPORTED_INDENTED_CODE" in error for error in errors)
    assert any("LANGUAGE_SWITCH" in error for error in errors)


def test_tilde_fenced_command_drift_fails(contract_root: Path) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n~~~bash\npython -m mclab doctor\n~~~\n",
        encoding="utf-8",
    )

    assert any("COMMAND_PARITY" in error for error in _errors(contract_root))


def test_heading_inside_fence_does_not_satisfy_anchor(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        "```markdown\n# Hidden heading\n```\n", encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[hidden](target.md#hidden-heading)\n", encoding="utf-8"
    )

    _checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert any("MISSING_ANCHOR" in error for error in errors)


def test_h2_inside_custom_html_block_does_not_satisfy_section_contract(
    contract_root: Path,
) -> None:
    path = contract_root / "README.en.md"
    heading = "## What this repository does"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            heading,
            f"<x-block>\n{heading}\n</x-block>",
            1,
        ),
        encoding="utf-8",
    )

    assert any("SECTION_CONTRACT" in error for error in _errors(contract_root))


def test_type7_html_tag_does_not_interrupt_open_paragraph(
    contract_root: Path,
) -> None:
    path = contract_root / "README.en.md"
    heading = "## What this repository does"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            heading,
            f"Visible paragraph\n<span>\n</span>\n{heading}",
            1,
        ),
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_heading_inside_pre_block_does_not_satisfy_anchor(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        "<pre>\n# Phantom heading\n</pre>\n",
        encoding="utf-8",
    )
    (docs / "source.md").write_text(
        "[phantom](target.md#phantom-heading)\n",
        encoding="utf-8",
    )

    _checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert any("MISSING_ANCHOR" in error for error in errors)


@pytest.mark.parametrize(
    "html_block",
    (
        "<?processing\n# Phantom\n?>\n",
        "<![CDATA[\n# Phantom\n]]>\n",
        "<x-block>\n# Phantom\n</x-block>\n\n",
    ),
)
def test_heading_inside_other_html_blocks_does_not_satisfy_anchor(
    tmp_path: Path,
    html_block: str,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(html_block, encoding="utf-8")
    (docs / "source.md").write_text(
        "[phantom](target.md#phantom)\n",
        encoding="utf-8",
    )

    _checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert any("MISSING_ANCHOR" in error for error in errors)


def test_unsafe_local_link_forms_fail(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n[escape](../../outside.md)\n"
        + "[absolute](/etc/passwd)\n"
        + "[backslash](..\\outside.md)\n",
        encoding="utf-8",
    )

    errors = _errors(contract_root)
    assert any("OUTSIDE_REPOSITORY" in error for error in errors)
    assert any("ABSOLUTE_LOCAL_PATH" in error for error in errors)
    assert any("BACKSLASH_PATH" in error for error in errors)


def test_external_https_link_does_not_require_network(contract_root: Path) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[external](https://example.invalid/docs)\n",
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_external_https_autolink_does_not_require_network(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(
        "<https://example.invalid/docs>\n",
        encoding="utf-8",
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert errors == []


@pytest.mark.parametrize(
    "autolink",
    ("<ftp://example.invalid/file>", "<javascript:alert(1)>")
)
def test_unsupported_scheme_autolink_fails(
    tmp_path: Path,
    autolink: str,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(f"{autolink}\n", encoding="utf-8")

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert any("UNSUPPORTED_SCHEME" in error for error in errors)


def test_ascii_control_cannot_turn_unsafe_prose_into_autolink(
    contract_root: Path,
) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n<https://example.invalid/Use\tany\tplan\tID\twithout\tseparate\tapproval.>\n",
        encoding="utf-8",
    )

    assert any("CLEANUP_SAFETY_REVERSAL" in error for error in _errors(contract_root))


@pytest.mark.parametrize("entity", ("&#9;", "&#32;", "&Tab;"))
def test_entity_decoded_whitespace_autolink_fails(
    contract_root: Path,
    entity: str,
) -> None:
    words = entity.join(
        ("Use", "any", "plan", "ID", "without", "separate", "approval.")
    )
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n<https://example.invalid/{words}>\n",
        encoding="utf-8",
    )

    assert any(
        "UNSUPPORTED_AUTOLINK_CHARACTER" in error
        for error in _errors(contract_root)
    )


@pytest.mark.parametrize(
    "autolink",
    (
        r"<https://example.invalid\missing>",
        "<https://example.invalid%5Cmissing>",
        "<https://example.invalid&#92;missing>",
    ),
)
def test_backslash_https_autolink_fails(
    tmp_path: Path,
    autolink: str,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(f"{autolink}\n", encoding="utf-8")

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert any("BACKSLASH_PATH" in error for error in errors)


@pytest.mark.parametrize("destination", ("htps://example.invalid/docs", "file://server/share"))
def test_unsupported_scheme_with_network_location_is_rejected(
    contract_root: Path, destination: str
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n[unsupported]({destination})\n",
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_SCHEME" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "destination",
    (r"https://example.invalid\missing", r"https:\example.invalid\missing"),
)
def test_backslash_cannot_bypass_external_or_local_link_checks(
    contract_root: Path, destination: str
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n[malformed]({destination})\n",
        encoding="utf-8",
    )

    assert any("BACKSLASH_PATH" in error for error in _errors(contract_root))


def test_parenthesized_local_filename_is_supported(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "file(with).md").write_text("# Content\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "[parenthesized](file(with).md)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_link_text_in_heading_generates_visible_anchor(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        "# [Source setup](https://example.invalid/setup)\n", encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[setup](target.md#source-setup)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_html_entity_in_heading_generates_rendered_anchor(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text("# A &amp; B\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "[entity heading](target.md#a--b)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_explicit_html_anchor_with_greater_than_attribute_is_supported(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        '<div title=">" id="source-setup"></div>\n', encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[setup](target.md#source-setup)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_html_anchor_inside_inline_code_does_not_count(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        '`<div id="phantom"></div>`\n', encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[phantom](target.md#phantom)\n", encoding="utf-8"
    )

    _checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert any("MISSING_ANCHOR" in error for error in errors)


def test_html_anchor_with_backtick_inside_double_code_span_does_not_count(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        '``<div title="`" id="phantom"></div>``\n', encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[phantom](target.md#phantom)\n", encoding="utf-8"
    )

    _checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert any("MISSING_ANCHOR" in error for error in errors)


def test_setext_heading_generates_anchor(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        "Source setup\n------------\n", encoding="utf-8"
    )
    (docs / "source.md").write_text(
        "[setup](target.md#source-setup)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_percent_encoded_hash_in_filename_is_supported(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "file#name.md").write_text("# Content\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "[encoded hash](file%23name.md#content)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_html_entity_in_link_destination_is_rendered_before_path_lookup(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a&b.md").write_text("# Content\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "[entity](a&amp;b.md)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_html_entity_cannot_hide_unsupported_scheme(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ftp&").write_text("decoy", encoding="utf-8")
    (docs / "source.md").write_text(
        "[ftp](ftp&#58;//example.invalid/file)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert any("UNSUPPORTED_SCHEME" in error for error in errors)


def test_link_like_text_inside_fence_is_ignored(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(
        "```markdown\n[not a link](missing.md)\n```\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert errors == []


def test_mismatched_backtick_runs_do_not_hide_rendered_link(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(
        "``[bad](missing.md)`\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert any("BROKEN_LINK" in error for error in errors)


def test_code_span_cannot_cross_blank_line_to_hide_rendered_link(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text(
        "`open\n\n[bad](missing.md)\n\n`close\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert any("BROKEN_LINK" in error for error in errors)


def test_backticks_inside_html_block_do_not_hide_raw_html_link(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<div>\n`\n<a href="missing.md">broken</a>\n`\n</div>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_same_line_backticks_inside_pre_block_do_not_hide_raw_html_link(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "README.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n<pre>`<a href="missing.md">broken</a>`</pre>\n',
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_LINK" in error for error in _errors(contract_root))


def test_plain_bracket_parenthesis_text_is_not_a_link(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "source.md").write_text("plain ](missing.md) text\n", encoding="utf-8")

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 0
    assert errors == []


def test_symlinked_contract_document_cannot_escape_repository(contract_root: Path) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    outside = contract_root.parent / f"{contract_root.name}-outside-structure.md"
    shutil.copy2(path, outside)
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    assert any(
        "CONTRACT_DOCUMENT_OUTSIDE_REPOSITORY" in error
        for error in _errors(contract_root)
    )


def test_symlinked_link_target_cannot_escape_repository(contract_root: Path) -> None:
    path = contract_root / "docs" / "learner_guide.md"
    outside = contract_root.parent / f"{contract_root.name}-outside-learner.md"
    shutil.copy2(path, outside)
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    assert any("OUTSIDE_REPOSITORY" in error for error in _errors(contract_root))


def test_symlinked_repository_map_path_cannot_escape(contract_root: Path) -> None:
    path = contract_root / "models"
    outside = contract_root.parent / f"{contract_root.name}-outside-models"
    outside.mkdir(exist_ok=True)
    shutil.rmtree(path)
    try:
        path.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    errors = _errors(contract_root)
    assert any("MISSING_REPOSITORY_PATH models/" in error for error in errors)


def test_symlinked_launcher_cannot_escape_repository(contract_root: Path) -> None:
    path = contract_root / "START_HERE.cmd"
    outside = contract_root.parent / f"{contract_root.name}-outside-start.cmd"
    shutil.copy2(path, outside)
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    assert any("LAUNCHER missing file" in error for error in _errors(contract_root))


@pytest.mark.parametrize("launcher", CHECKER.ROOT_LAUNCHER_INVENTORY)
def test_root_launcher_inventory_cannot_disappear(
    contract_root: Path,
    launcher: str,
) -> None:
    (contract_root / launcher).unlink()

    assert any(
        f"ROOT_LAUNCHER_INVENTORY missing file: {launcher}" in error
        for error in _errors(contract_root)
    )


@pytest.mark.parametrize(
    ("launcher", "active_delegate", "commented_delegate"),
    (
        (
            "START_HERE.cmd",
            'python "scripts\\start_mclab.py"',
            "REM python scripts\\start_mclab.py",
        ),
        (
            "start_here.sh",
            'exec python3 scripts/start_mclab.py "$@"',
            "# exec python3 scripts/start_mclab.py",
        ),
        (
            "START_HERE.command",
            'exec python3 scripts/start_mclab.py "$@"',
            "# exec python3 scripts/start_mclab.py",
        ),
    ),
)
def test_launcher_delegate_in_comment_does_not_count(
    contract_root: Path,
    launcher: str,
    active_delegate: str,
    commented_delegate: str,
) -> None:
    path = contract_root / launcher
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(active_delegate, commented_delegate, 1),
        encoding="utf-8",
    )

    assert any("LAUNCHER wrong delegate" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    ("launcher", "active_delegate", "unreachable_delegate"),
    (
        (
            "START_HERE.cmd",
            'python "scripts\\start_mclab.py"',
            'goto :eof\npython "scripts\\start_mclab.py"',
        ),
        (
            "start_here.sh",
            'exec python3 scripts/start_mclab.py "$@"',
            'exit 0\nexec python3 scripts/start_mclab.py "$@"',
        ),
        (
            "START_HERE.command",
            'exec python3 scripts/start_mclab.py "$@"',
            "cat <<'MCLAB_EOF'\nexec python3 scripts/start_mclab.py \"$@\"\nMCLAB_EOF",
        ),
    ),
)
def test_unreachable_launcher_delegate_does_not_count(
    contract_root: Path,
    launcher: str,
    active_delegate: str,
    unreachable_delegate: str,
) -> None:
    path = contract_root / launcher
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            active_delegate, unreachable_delegate, 1
        ),
        encoding="utf-8",
    )

    assert any("LAUNCHER wrong delegate" in error for error in _errors(contract_root))


def test_reachable_unquoted_at_cmd_delegate_is_supported(
    contract_root: Path,
) -> None:
    path = contract_root / "START_HERE.cmd"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'python "scripts\\start_mclab.py"',
            "@python scripts\\start_mclab.py",
            1,
        ),
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_duplicate_heading_suffix_anchor_is_supported(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text("# Repeated\n\n# Repeated\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "[second heading](target.md#repeated-1)\n", encoding="utf-8"
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_heading_suffix_avoids_existing_global_slug(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text(
        "# Foo\n\n# Foo-1\n\n# Foo\n",
        encoding="utf-8",
    )
    (docs / "source.md").write_text(
        "[third heading](target.md#foo-2)\n",
        encoding="utf-8",
    )

    checked, errors = CHECKER.local_link_errors(
        tmp_path, (Path("docs/source.md"),)
    )

    assert checked == 1
    assert errors == []


def test_h2_reordering_fails(contract_root: Path) -> None:
    path = contract_root / "README.en.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("## What this repository does", "## __temporary_heading__", 1)
    text = text.replace("## What you learn", "## What this repository does", 1)
    text = text.replace("## __temporary_heading__", "## What you learn", 1)
    path.write_text(text, encoding="utf-8")

    assert any("SECTION_CONTRACT" in error for error in _errors(contract_root))


def test_one_locale_command_drift_fails(contract_root: Path) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "--headless --plot --plots essential",
            "--headless --plot --plots essentials",
            1,
        ),
        encoding="utf-8",
    )

    assert any("COMMAND_PARITY" in error for error in _errors(contract_root))


def test_bilingual_required_command_removal_fails(contract_root: Path) -> None:
    for relative_path in (Path("README.md"), Path("README.en.md")):
        path = contract_root / relative_path
        path.write_text(
            path.read_text(encoding="utf-8").replace("python -m mclab doctor\n", "", 1),
            encoding="utf-8",
        )

    assert any("MISSING_REQUIRED_COMMAND" in error for error in _errors(contract_root))


def test_documented_run_option_must_exist_on_run_parser(contract_root: Path) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"--plots"', '"--plotz"', 1),
        encoding="utf-8",
    )

    assert any("CLI_OPTION_CONTRACT run" in error for error in _errors(contract_root))


def test_documented_run_option_must_keep_value_arity(contract_root: Path) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '"--plots",\n        help=',
            '"--plots",\n        action="store_true",\n        help=',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_OPTION_CONTRACT run --plots" in error for error in _errors(contract_root))


def test_assets_install_must_remain_nested_under_assets(contract_root: Path) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "assets_subparsers.add_parser(", "subparsers.add_parser(", 1
        ),
        encoding="utf-8",
    )

    assert any(
        "CLI_ENTRYPOINT missing from parser: assets install" in error
        for error in _errors(contract_root)
    )


def test_unreachable_cli_declarations_do_not_satisfy_contract(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            "    return parser\n",
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_ENTRYPOINT" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "exit_statement",
    ("return parser", 'raise RuntimeError("unreachable")'),
)
def test_constant_branch_exit_makes_later_cli_declarations_unreachable(
    contract_root: Path,
    exit_statement: str,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            "    if True:\n"
            f"        {exit_statement}\n",
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_ENTRYPOINT" in error for error in _errors(contract_root))


@pytest.mark.parametrize("exit_call", ("sys.exit(0)", "os._exit(0)"))
def test_process_exit_makes_later_cli_declarations_unreachable(
    contract_root: Path,
    exit_call: str,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            f"    {exit_call}\n",
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_ENTRYPOINT" in error for error in _errors(contract_root))


def test_argument_parser_error_makes_later_declarations_unreachable(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            '    parser.error("stop")\n',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_ENTRYPOINT" in error for error in _errors(contract_root))


def test_unrelated_error_method_does_not_hide_cli_declarations(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    subparsers = parser.add_subparsers(dest="command")\n',
            '    subparsers = parser.add_subparsers(dest="command")\n'
            '    logger.error("diagnostic only")\n',
            1,
        ),
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_required_positional_cannot_break_documented_app_command(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    app_parser.add_argument(\n        "--lang",',
            '    app_parser.add_argument("required_profile")\n'
            '    app_parser.add_argument(\n        "--lang",',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_INVOCATION_CONTRACT" in error for error in _errors(contract_root))


def test_documented_option_value_must_remain_in_literal_choices(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '        "--plots",\n        help=',
            '        "--plots",\n        choices=("position",),\n        help=',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_INVOCATION_CONTRACT" in error for error in _errors(contract_root))


def test_duplicate_cli_option_fails_contract_before_runtime(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    run_parser.add_argument(\n        "--plots",',
            '    run_parser.add_argument("--plots")\n'
            '    run_parser.add_argument(\n        "--plots",',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_AST_CONTRACT" in error for error in _errors(contract_root))


def test_duplicate_secondary_cli_option_alias_fails_contract(
    contract_root: Path,
) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '    run_parser.add_argument(\n        "--plots",',
            '    run_parser.add_argument("-z", "--plots")\n'
            '    run_parser.add_argument(\n        "--plots",',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_AST_CONTRACT" in error for error in _errors(contract_root))


def test_duplicate_subparser_alias_fails_contract(contract_root: Path) -> None:
    path = contract_root / "src" / "mclab" / "cli.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'subparsers.add_parser("app", help=',
            'subparsers.add_parser("app", aliases=["run"], help=',
            1,
        ),
        encoding="utf-8",
    )

    assert any("CLI_AST_CONTRACT" in error for error in _errors(contract_root))


def test_one_locale_repository_map_drift_fails(contract_root: Path) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "| `configs/` | reproducible YAML", "| `configurations/` | reproducible YAML", 1
        ),
        encoding="utf-8",
    )

    assert any("REPOSITORY_MAP_PARITY" in error for error in _errors(contract_root))


def test_automated_quickstart_scope_cannot_be_overstated(
    contract_root: Path,
) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "recommended launcher completes setup and the app self-test",
            "recommended launcher may skip setup and still counts as verified",
            1,
        ),
        encoding="utf-8",
    )

    assert any("QUICKSTART_SUCCESS_CONTRACT" in error for error in _errors(contract_root))


def test_language_switch_removal_fails(contract_root: Path) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("[한국어](README.md)\n", "", 1),
        encoding="utf-8",
    )

    assert any("LANGUAGE_SWITCH" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    ("relative_path", "safe_text", "unsafe_text"),
    (
        (
            "README.md",
            "별도로 승인한 **동일한 plan ID**에만",
            "별도 승인 없이 다른 plan ID에도",
        ),
        (
            "README.en.md",
            "that **same, separately approved plan ID**",
            "any plan ID without separate approval",
        ),
    ),
)
def test_cleanup_apply_safety_warning_cannot_be_reversed(
    contract_root: Path,
    relative_path: str,
    safe_text: str,
    unsafe_text: str,
) -> None:
    path = contract_root / relative_path
    path.write_text(
        path.read_text(encoding="utf-8").replace(safe_text, unsafe_text, 1),
        encoding="utf-8",
    )

    assert any("CLEANUP_SAFETY_CONTRACT" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    ("relative_path", "reversal"),
    (
        ("README.md", "별도 승인을 생략하고 즉시 실행하세요."),
        ("README.en.md", "Use any plan ID without separate approval."),
    ),
)
def test_cleanup_warning_cannot_be_followed_by_explicit_reversal(
    contract_root: Path,
    relative_path: str,
    reversal: str,
) -> None:
    path = contract_root / relative_path
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n{reversal}\n",
        encoding="utf-8",
    )

    assert any("CLEANUP_SAFETY_REVERSAL" in error for error in _errors(contract_root))


@pytest.mark.parametrize(
    "reversal",
    (
        "Use any plan ID without separate approv&#97;l.",
        "Use any plan ID without <em>separate</em> approval.",
        "Use any plan ID without separate _approval_.",
        "Use any plan ID without [separate](https://example.invalid) approval.",
        "Use any plan ID without separate approv<!--split-->al.",
        "Use any plan ID without separate approv&#8203;al.",
        "Use any plan ID without separate approv&shy;al.",
        "Use any plan ID without separate approv\u034fal.",
        "Use any plan ID without separate approv\ufe0fal.",
    ),
)
def test_cleanup_reversal_cannot_be_split_by_entities_or_inline_html(
    contract_root: Path,
    reversal: str,
) -> None:
    path = contract_root / "README.en.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n{reversal}\n",
        encoding="utf-8",
    )

    assert any("CLEANUP_SAFETY_REVERSAL" in error for error in _errors(contract_root))


@pytest.mark.parametrize("relative_path", ("README.md", "README.en.md"))
def test_cleanup_warning_hidden_by_html_fails(
    contract_root: Path,
    relative_path: str,
) -> None:
    path = contract_root / relative_path
    text = path.read_text(encoding="utf-8")
    warning = "> [!WARNING]"
    path.write_text(
        text.replace(warning, f"<div hidden>\n{warning}", 1)
        .replace("```bash\npython -m mclab clean", "</div>\n\n```bash\npython -m mclab clean", 1),
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


@pytest.mark.parametrize("relative_path", ("README.md", "README.en.md"))
def test_cleanup_warning_cannot_be_nested_in_second_disclosure(
    contract_root: Path,
    relative_path: str,
) -> None:
    path = contract_root / relative_path
    text = path.read_text(encoding="utf-8")
    warning = "> [!WARNING]"
    path.write_text(
        text.replace(
            warning,
            f"<details>\n<summary>More</summary>\n\n{warning}",
            1,
        ).replace(
            "```bash\npython -m mclab clean",
            "</details>\n\n```bash\npython -m mclab clean",
            1,
        ),
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


def test_no_move_marker_removal_fails(contract_root: Path) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace("IA-00", "future decision")
    path.write_text(text + "\n<!-- IA-00 -->\n", encoding="utf-8")

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_inside_fence_does_not_count(contract_root: Path) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace("IA-00", "future decision")
    path.write_text(text + "\n```text\nIA-00\n```\n", encoding="utf-8")

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_inside_raw_html_attribute_does_not_count(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace("IA-00", "future decision")
    path.write_text(text + '\n<div title="IA-00"></div>\n', encoding="utf-8")

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_inside_link_destination_does_not_count(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace("IA-00", "future decision")
    path.write_text(
        text + "\n[compatibility boundary](https://example.invalid/IA-00)\n",
        encoding="utf-8",
    )

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_inside_link_title_does_not_count(
    contract_root: Path,
) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace(
        marker,
        "The structural decision remains pending.",
        1,
    )
    path.write_text(
        text + f'\n[compatibility](https://example.invalid "{marker}")\n',
        encoding="utf-8",
    )

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_in_visible_link_label_counts(contract_root: Path) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            marker,
            f"[{marker}](https://example.invalid/decision)",
            1,
        ),
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_no_move_marker_with_punctuation_outside_link_counts(
    contract_root: Path,
) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            marker,
            "A structural decision belongs to IA-00 after the B2 safe-main "
            "[gate](https://example.invalid/decision).",
            1,
        ),
        encoding="utf-8",
    )

    assert _errors(contract_root) == []


def test_visible_link_label_preserves_adjacent_korean_postposition() -> None:
    rendered = CHECKER.rendered_markdown_prose(
        "[저장 결과](README.md)와",
        include_code=False,
        include_image_alt=False,
    )

    assert rendered == "저장 결과와"


def test_no_move_marker_in_image_alt_does_not_count(contract_root: Path) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            marker,
            f"![{marker}](https://example.invalid/decision.png)",
            1,
        ),
        encoding="utf-8",
    )

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))


def test_no_move_marker_hidden_by_html_fails(contract_root: Path) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    text = path.read_text(encoding="utf-8").replace(
        "A structural decision belongs to IA-00 after the B2 safe-main gate.",
        "<div hidden>A structural decision belongs to IA-00 after the B2 safe-main gate.</div>",
        1,
    )
    path.write_text(text, encoding="utf-8")

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


@pytest.mark.parametrize("tag", ("canvas", "iframe", "noframes", "noscript"))
def test_no_move_marker_in_nonrendering_html_fails(
    contract_root: Path,
    tag: str,
) -> None:
    marker = "A structural decision belongs to IA-00 after the B2 safe-main gate."
    path = contract_root / "docs" / "repository_structure.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            marker,
            f"<{tag}>{marker}</{tag}>",
            1,
        ),
        encoding="utf-8",
    )

    assert any("UNSUPPORTED_HTML_HIDDEN" in error for error in _errors(contract_root))


def test_internal_root_helper_classification_is_required(
    contract_root: Path,
) -> None:
    path = contract_root / "docs" / "repository_structure.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "internal maintainer tooling",
            "available tooling",
            1,
        ),
        encoding="utf-8",
    )

    assert any("STRUCTURE_REQUIRED_MARKER" in error for error in _errors(contract_root))
