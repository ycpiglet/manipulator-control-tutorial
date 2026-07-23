from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import TypeVar

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_mypy_baseline.py"
SPEC = importlib.util.spec_from_file_location("check_mypy_baseline", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)
T = TypeVar("T")


def _baseline_document() -> dict[str, object]:
    return json.loads((ROOT / CHECKER.BASELINE_RELATIVE).read_text(encoding="utf-8"))


def _row(
    *,
    file: str = "src/mclab/completion.py",
    code: str = "call-overload",
    message: str = (
        'No overload variant of "get" of "dict" matches argument types "object", "CompletionReason"'
    ),
    line: int = 1,
) -> dict[str, object]:
    return {
        "file": file,
        "line": line,
        "column": 0,
        "end_line": line,
        "end_column": 1,
        "message": message,
        "hint": None,
        "code": code,
        "severity": "error",
    }


def _jsonl(*rows: dict[str, object]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


def _native_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _live_mypy(path: Path) -> tuple[int, Counter[tuple[str, str, str]]]:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "mypy",
            "--no-incremental",
            "--config-file",
            str(ROOT / CHECKER.CONFIG_RELATIVE),
            "--output",
            "json",
            str(path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
    )
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line]
    diagnostics = Counter((Path(row["file"]).name, row["code"], row["message"]) for row in rows)
    return completed.returncode, diagnostics


def _remove_one(items: Counter[T]) -> Counter[T]:
    reduced = items.copy()
    fingerprint = next(iter(reduced))
    reduced[fingerprint] -= 1
    if reduced[fingerprint] == 0:
        del reduced[fingerprint]
    return reduced


def test_committed_baseline_is_canonical_and_self_consistent() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    previous = CHECKER.load_previous_baseline(ROOT / CHECKER.PREVIOUS_BASELINE_RELATIVE)
    document = _baseline_document()

    assert baseline.error_count == 264
    assert baseline.error_file_count == 29
    assert baseline.source_file_count == 87
    assert sum(baseline.by_code.values()) == 264
    assert sum(baseline.by_file.values()) == 264
    assert sum(baseline.diagnostics.values()) == 264
    assert len(baseline.diagnostics) == 150
    assert sum(baseline.suppressions.values()) == 8
    assert len(baseline.suppressions) == 8
    assert document["schema_version"] == 2
    assert document["history"][0]["sha256"] == CHECKER.PREVIOUS_BASELINE_SHA256  # type: ignore[index]
    CHECKER.validate_baseline_ancestry(baseline, previous)
    assert "raw_jsonl_sha256" not in document["tool"]  # type: ignore[operator]
    assert document["tool"]["controlled_import_roots"] == ["src"]  # type: ignore[index]
    assert document["environment"]["bootstrap_distribution_allowlist"] == []  # type: ignore[index]


def test_current_repository_has_no_new_mypy_debt() -> None:
    native = _native_python_version()
    result = CHECKER.validate_repository(ROOT, python_version=native)

    assert result.passed
    assert result.errors == ()
    assert result.error_count == result.baseline_error_count == 264
    assert result.error_file_count == result.baseline_error_file_count
    assert result.suppression_count == result.baseline_suppression_count
    assert result.native_python_version.startswith(f"{native}.")
    assert result.target_python_version == native


def test_normal_validation_is_exact_and_improvements_require_migration() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    equal = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions.copy(),
    )
    reduced_diagnostics = _remove_one(baseline.diagnostics)
    reduced = CHECKER.compare_diagnostics(
        baseline,
        reduced_diagnostics,
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions.copy(),
    )
    removed_file = next(iter(baseline.by_file))
    without_error_file = Counter(
        {
            fingerprint: count
            for fingerprint, count in baseline.diagnostics.items()
            if fingerprint[0] != removed_file
        }
    )
    eliminated = CHECKER.compare_diagnostics(
        baseline,
        without_error_file,
        python_version="3.11",
        source_file_count=baseline.source_file_count + 1,
        current_suppressions=baseline.suppressions.copy(),
    )
    clean_module_added = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count + 1,
        current_suppressions=baseline.suppressions.copy(),
    )

    assert equal.passed
    assert equal.removed_diagnostic_count == 0
    assert not reduced.passed
    assert reduced.removed_diagnostic_count == 1
    assert any("REQUIRES_MIGRATION" in error for error in reduced.errors)
    assert not eliminated.passed
    assert eliminated.error_file_count == baseline.error_file_count - 1
    assert not clean_module_added.passed
    assert clean_module_added.source_file_count == baseline.source_file_count + 1
    assert any(
        "SOURCE_FILE_COUNT_REQUIRES_MIGRATION" in error for error in clean_module_added.errors
    )


@pytest.mark.parametrize(
    "fingerprint, expected_codes",
    (
        (
            ("src/mclab/completion.py", "new-code", "new diagnostic"),
            ("NEW_DIAGNOSTIC", "NEW_ERROR_CODE", "FILE_BUDGET_EXCEEDED"),
        ),
        (
            ("src/mclab/new_module.py", "arg-type", "new diagnostic"),
            ("NEW_DIAGNOSTIC", "NEW_ERROR_FILE", "FILE_BUDGET_EXCEEDED"),
        ),
    ),
)
def test_new_diagnostic_file_or_code_fails(
    fingerprint: tuple[str, str, str], expected_codes: tuple[str, ...]
) -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    current = baseline.diagnostics.copy()
    current[fingerprint] += 1

    result = CHECKER.compare_diagnostics(
        baseline,
        current,
        python_version="3.11",
        source_file_count=baseline.source_file_count + 1,
        current_suppressions=baseline.suppressions.copy(),
    )

    assert not result.passed
    assert all(any(error.startswith(code) for error in result.errors) for code in expected_codes)
    assert any(error.startswith("TOTAL_BUDGET_EXCEEDED") for error in result.errors)


def test_increased_duplicate_multiplicity_fails_even_if_another_error_is_removed() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    current = baseline.diagnostics.copy()
    fingerprints = list(current)
    added = fingerprints[0]
    removed = fingerprints[-1]
    current[added] += 1
    current[removed] -= 1
    if current[removed] == 0:
        del current[removed]

    result = CHECKER.compare_diagnostics(
        baseline,
        current,
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions.copy(),
    )

    assert result.error_count == baseline.error_count
    assert any(error.startswith("NEW_DIAGNOSTIC") for error in result.errors)


def test_current_typing_suppression_surface_matches_immutable_baseline() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)

    assert CHECKER.scan_typing_suppressions(ROOT) == baseline.suppressions


@pytest.mark.parametrize(
    "fingerprint",
    (
        (
            "src/mclab/completion.py",
            "inline-type-ignore",
            "# type: ignore[assignment]",
            "statement-context-sha256:" + "0" * 64,
        ),
        (
            "src/mclab/completion.py",
            "file-mypy-directive",
            "# mypy: ignore-errors",
            "module-ast-sha256:" + "0" * 64,
        ),
        (
            "src/mclab/completion.py",
            "no-type-check",
            "@no_type_check",
            "definition-context-sha256:" + "0" * 64,
        ),
        (
            "src/dependency.pyi",
            "stub-file",
            "present",
            "raw-sha256:" + "0" * 64,
        ),
    ),
)
def test_new_typing_suppression_or_stub_surface_fails(
    fingerprint: tuple[str, str, str, str],
) -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    current_suppressions = baseline.suppressions.copy()
    current_suppressions[fingerprint] += 1

    result = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=current_suppressions,
    )

    assert not result.passed
    assert any(error.startswith("NEW_TYPING_SUPPRESSION") for error in result.errors)


def test_suppression_removal_requires_migration_and_duplicate_addition_fails() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    fingerprint = next(iter(baseline.suppressions))
    reduced = baseline.suppressions.copy()
    reduced[fingerprint] -= 1
    if reduced[fingerprint] == 0:
        del reduced[fingerprint]
    increased = baseline.suppressions.copy()
    increased[fingerprint] += 1

    removal = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=reduced,
    )
    addition = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=increased,
    )

    assert not removal.passed
    assert removal.removed_suppression_count == 1
    assert any(
        "BASELINE_SUPPRESSION_REMOVED_REQUIRES_MIGRATION" in error for error in removal.errors
    )
    assert not addition.passed


def test_monotonic_migration_accepts_improvement_and_appends_immutable_history() -> None:
    document = _baseline_document()
    original = copy.deepcopy(document)
    baseline = CHECKER.validate_baseline_document(document)
    diagnostics = _remove_one(baseline.diagnostics)
    subject_commit = "a" * 40
    subject_tree = "b" * 40

    CHECKER.validate_monotonic_migration(
        baseline,
        diagnostics,
        baseline.suppressions.copy(),
        source_file_count=baseline.source_file_count,
    )
    candidate = CHECKER.build_migration_candidate(
        document,
        baseline,
        diagnostics=diagnostics,
        suppressions=baseline.suppressions.copy(),
        source_file_count=baseline.source_file_count,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
    )

    assert document == original
    assert candidate["baseline_id"] == "MAINT-01A-mypy-debt-v3"
    assert candidate["subject"] == {"commit": subject_commit, "tree": subject_tree}
    assert candidate["baseline"]["error_count"] == baseline.error_count - 1  # type: ignore[index]
    assert candidate["history"][-1] == {  # type: ignore[index]
        "baseline_id": CHECKER.BASELINE_ID,
        "path": CHECKER.BASELINE_RELATIVE.as_posix(),
        "sha256": CHECKER.BASELINE_SHA256,
        "relationship": (
            "diagnostics and contextual suppressions are multisets contained in the "
            "immutable previous baseline"
        ),
    }
    assert json.dumps(candidate, indent=2, ensure_ascii=False).endswith("}")


def test_monotonic_migration_accepts_new_clean_source_file_without_recapturing_debt() -> None:
    document = _baseline_document()
    baseline = CHECKER.validate_baseline_document(document)
    source_file_count = baseline.source_file_count + 1

    CHECKER.validate_monotonic_migration(
        baseline,
        baseline.diagnostics.copy(),
        baseline.suppressions.copy(),
        source_file_count=source_file_count,
    )
    candidate = CHECKER.build_migration_candidate(
        document,
        baseline,
        diagnostics=baseline.diagnostics.copy(),
        suppressions=baseline.suppressions.copy(),
        source_file_count=source_file_count,
        subject_commit="a" * 40,
        subject_tree="b" * 40,
    )

    assert candidate["baseline"]["source_file_count"] == source_file_count  # type: ignore[index]
    assert candidate["baseline"]["error_count"] == baseline.error_count  # type: ignore[index]
    assert candidate["suppressions"]["entries"] == document["suppressions"]["entries"]  # type: ignore[index]


def test_monotonic_migration_rejects_reintroduction_and_unchanged_regeneration() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    reintroduced_diagnostics = _remove_one(baseline.diagnostics)
    reintroduced_diagnostics[("src/mclab/new.py", "misc", "new debt")] += 1
    reintroduced_suppressions = _remove_one(baseline.suppressions)
    reintroduced_suppressions[
        (
            "src/mclab/new.py",
            "no-type-check",
            "@no_type_check",
            "definition-context-sha256:" + "0" * 64,
        )
    ] += 1

    with pytest.raises(CHECKER.ContractError, match="reintroduces or increases diagnostic"):
        CHECKER.validate_monotonic_migration(
            baseline,
            reintroduced_diagnostics,
            baseline.suppressions.copy(),
            source_file_count=baseline.source_file_count,
        )
    with pytest.raises(CHECKER.ContractError, match="reintroduces or increases typing"):
        CHECKER.validate_monotonic_migration(
            baseline,
            baseline.diagnostics.copy(),
            reintroduced_suppressions,
            source_file_count=baseline.source_file_count,
        )
    with pytest.raises(CHECKER.ContractError, match="at least one"):
        CHECKER.validate_monotonic_migration(
            baseline,
            baseline.diagnostics.copy(),
            baseline.suppressions.copy(),
            source_file_count=baseline.source_file_count,
        )
    with pytest.raises(CHECKER.ContractError, match="source_file_count"):
        CHECKER.validate_monotonic_migration(
            baseline,
            baseline.diagnostics.copy(),
            baseline.suppressions.copy(),
            source_file_count=True,
        )


def test_monotonic_migration_rejects_multiplicity_increase_despite_removal() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    diagnostics = baseline.diagnostics.copy()
    added, removed = list(diagnostics)[:2]
    diagnostics[added] += 1
    diagnostics[removed] -= 1
    if diagnostics[removed] == 0:
        del diagnostics[removed]

    with pytest.raises(CHECKER.ContractError, match="reintroduces or increases diagnostic"):
        CHECKER.validate_monotonic_migration(
            baseline,
            diagnostics,
            baseline.suppressions.copy(),
            source_file_count=baseline.source_file_count,
        )


def test_suppression_scanner_uses_comment_tokens_and_tracks_stubs(tmp_path: Path) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    (source / "module.py").write_text(
        'literal = "# type: ignore[assignment]"\n'
        "value = object()  # type: ignore [ assignment, attr-defined ]\n"
        "# mypy: ignore-errors\n",
        encoding="utf-8",
    )
    (source / "module.pyi").write_text("value: object\n", encoding="utf-8")

    scanned = CHECKER.scan_typing_suppressions(tmp_path)

    assert sum(scanned.values()) == 3
    by_kind = {fingerprint[1]: fingerprint for fingerprint in scanned}
    assert by_kind["inline-type-ignore"][:3] == (
        "src/mclab/module.py",
        "inline-type-ignore",
        "# type: ignore[assignment,attr-defined]",
    )
    assert by_kind["inline-type-ignore"][3].startswith("statement-context-sha256:")
    assert by_kind["file-mypy-directive"][:3] == (
        "src/mclab/module.py",
        "file-mypy-directive",
        "# mypy: ignore-errors",
    )
    assert by_kind["file-mypy-directive"][3].startswith("module-ast-sha256:")
    assert by_kind["stub-file"][:3] == (
        "src/mclab/module.pyi",
        "stub-file",
        "present",
    )
    assert by_kind["stub-file"][3].startswith("raw-sha256:")


def test_sibling_import_root_stub_is_inventoried_and_rejected(tmp_path: Path) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    (source / "module.py").write_text("value: int = 1\n", encoding="utf-8")
    sibling = tmp_path / "src" / "dependency.pyi"
    sibling.write_text("value: object\n", encoding="utf-8")

    scanned = CHECKER.scan_typing_suppressions(tmp_path)

    fingerprint = next(item for item in scanned if item[1] == "stub-file")
    assert fingerprint[0] == "src/dependency.pyi"
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    result = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions + scanned,
    )
    assert any(error.startswith("NEW_TYPING_SUPPRESSION") for error in result.errors)


def test_sibling_package_python_is_controlled_and_diagnostics_are_canonical(tmp_path: Path) -> None:
    mclab = tmp_path / "src" / "mclab"
    sibling = tmp_path / "src" / "sibling"
    mclab.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (mclab / "__init__.py").write_text("", encoding="utf-8")
    (sibling / "__init__.py").write_text("", encoding="utf-8")
    module = sibling / "module.py"
    module.write_text("import yaml  # type: ignore\n", encoding="utf-8")

    source_files = CHECKER._source_python_files(tmp_path)
    scanned = CHECKER.scan_typing_suppressions(tmp_path, source_files)
    diagnostic = CHECKER.parse_mypy_jsonl(
        _jsonl(_row(file="src/sibling/module.py", code="assignment", message="sibling debt")),
        returncode=1,
    )

    assert {path.relative_to(tmp_path).as_posix() for path in source_files} == {
        "src/mclab/__init__.py",
        "src/sibling/__init__.py",
        "src/sibling/module.py",
    }
    assert any(fingerprint[0] == "src/sibling/module.py" for fingerprint in scanned)
    assert CHECKER._canonical_suppression_file("src/sibling/module.py") == ("src/sibling/module.py")
    assert diagnostic == Counter({("src/sibling/module.py", "assignment", "sibling debt"): 1})


def test_type_ignore_context_mutation_cannot_repurpose_suppression(tmp_path: Path) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    module = source / "module.py"
    module.write_text("import yaml  # type: ignore\n", encoding="utf-8")
    before = CHECKER.scan_typing_suppressions(tmp_path)
    module.write_text("import json  # type: ignore\n", encoding="utf-8")
    after = CHECKER.scan_typing_suppressions(tmp_path)

    assert before != after
    assert next(iter(before))[:3] == next(iter(after))[:3]
    assert next(iter(before))[3] != next(iter(after))[3]
    baseline = CHECKER.Baseline(
        error_count=0,
        error_file_count=0,
        source_file_count=1,
        by_code={},
        by_file={},
        diagnostics=Counter(),
        suppressions=before,
    )
    result = CHECKER.compare_diagnostics(
        baseline,
        Counter(),
        python_version="3.11",
        source_file_count=1,
        current_suppressions=after,
    )
    assert any(error.startswith("NEW_TYPING_SUPPRESSION") for error in result.errors)


def test_duplicate_statement_ignore_cannot_move_between_structural_paths(tmp_path: Path) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    module = source / "module.py"
    first_branch = "if enabled:\n    value = load()  # type: ignore\nelse:\n    value = load()\n"
    module.write_text(first_branch, encoding="utf-8")
    before = CHECKER.scan_typing_suppressions(tmp_path)
    module.write_text("\n\n" + first_branch, encoding="utf-8")
    line_moved = CHECKER.scan_typing_suppressions(tmp_path)
    module.write_text(
        "if enabled:\n    value = load()\nelse:\n    value = load()  # type: ignore\n",
        encoding="utf-8",
    )
    branch_moved = CHECKER.scan_typing_suppressions(tmp_path)

    assert before == line_moved
    assert next(iter(before))[:3] == next(iter(branch_moved))[:3]
    assert next(iter(before))[3] != next(iter(branch_moved))[3]


def test_ast_fingerprint_ignores_python_312_type_params_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function = ast.parse("def identity(value):\n    return value\n").body[0]
    node_type = type(function)
    original_fields = node_type._fields
    if "type_params" not in original_fields:
        monkeypatch.setattr(node_type, "_fields", (*original_fields, "type_params"))

    function.type_params = []
    without_type_params = CHECKER._portable_ast_dump(function)
    function.type_params = [ast.Name(id="T", ctx=ast.Load())]
    with_type_params = CHECKER._portable_ast_dump(function)

    assert with_type_params == without_type_params
    assert "type_params" not in with_type_params


def test_no_type_check_has_zero_baseline_and_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    (source / "module.py").write_text(
        "from typing import no_type_check\n\n"
        "@no_type_check\n"
        "def unsafe(value):\n"
        "    return value.missing\n",
        encoding="utf-8",
    )

    scanned = CHECKER.scan_typing_suppressions(tmp_path)

    assert (
        sum(count for fingerprint, count in scanned.items() if fingerprint[1] == "no-type-check")
        == 1
    )
    committed = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    assert all(fingerprint[1] != "no-type-check" for fingerprint in committed.suppressions)
    result = CHECKER.compare_diagnostics(
        committed,
        committed.diagnostics.copy(),
        python_version="3.11",
        source_file_count=committed.source_file_count,
        current_suppressions=committed.suppressions + scanned,
    )
    assert any("kind=no-type-check" in error for error in result.errors)


@pytest.mark.parametrize(
    "source_text",
    (
        (
            "from typing import no_type_check as unchecked\n\n"
            "@unchecked\n"
            "def unsafe(value):\n"
            "    return value\n"
        ),
        (
            "import typing_extensions as typing_tools\n\n"
            "unchecked = typing_tools.no_type_check\n\n"
            "@unchecked\n"
            "def unsafe(value):\n"
            "    return value\n"
        ),
        (
            "from typing_extensions import no_type_check as unchecked\n\n"
            "@unchecked\n"
            "def unsafe(value):\n"
            "    return value\n"
        ),
    ),
)
def test_no_type_check_aliases_are_resolved_and_rejected(
    tmp_path: Path,
    source_text: str,
) -> None:
    source = tmp_path / "src" / "mclab"
    source.mkdir(parents=True)
    (source / "module.py").write_text(source_text, encoding="utf-8")

    scanned = CHECKER.scan_typing_suppressions(tmp_path)

    matches = [fingerprint for fingerprint in scanned if fingerprint[1] == "no-type-check"]
    assert len(matches) == 1
    assert matches[0][0] == "src/mclab/module.py"
    assert matches[0][3].startswith("definition-context-sha256:")


def test_local_no_type_check_reexport_chain_is_resolved_and_rejected(tmp_path: Path) -> None:
    package = tmp_path / "src" / "mclab"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "typing_bridge.py").write_text(
        "from typing import no_type_check as unchecked\n",
        encoding="utf-8",
    )
    (package / "project_aliases.py").write_text(
        "from .typing_bridge import unchecked as skip_validation\n",
        encoding="utf-8",
    )
    (package / "module.py").write_text(
        "from .project_aliases import skip_validation as hidden\n\n"
        "@hidden\n"
        "def unsafe(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    scanned = CHECKER.scan_typing_suppressions(tmp_path)

    matches = [fingerprint for fingerprint in scanned if fingerprint[1] == "no-type-check"]
    assert len(matches) == 1
    assert matches[0][0] == "src/mclab/module.py"


def test_line_and_column_movement_does_not_change_the_fingerprint() -> None:
    first = CHECKER.parse_mypy_jsonl(_jsonl(_row(line=10)), returncode=1)
    moved = CHECKER.parse_mypy_jsonl(_jsonl(_row(line=999)), returncode=1)

    assert first == moved


def test_mypy_jsonl_accepts_zero_errors_only_with_success_status() -> None:
    assert CHECKER.parse_mypy_jsonl("", returncode=0) == Counter()
    assert CHECKER.parse_mypy_jsonl("\n", returncode=0) == Counter()
    with pytest.raises(CHECKER.ContractError, match="status 1 with empty diagnostic output"):
        CHECKER.parse_mypy_jsonl("", returncode=1)
    with pytest.raises(CHECKER.ContractError, match="unexpected status 2"):
        CHECKER.parse_mypy_jsonl("", returncode=2)


@pytest.mark.parametrize(
    "mutation, match",
    (
        (lambda row: row.update(extra=True), "keys mismatch"),
        (lambda row: row.update(file="/tmp/outside.py"), "unsafe diagnostic path"),
        (lambda row: row.update(severity="note"), "severity must be 'error'"),
        (lambda row: row.update(line=True), "must be an integer"),
        (lambda row: row.update(hint=3), "string or null"),
    ),
)
def test_mypy_jsonl_is_closed_and_fail_closed(mutation: object, match: str) -> None:
    row = _row()
    mutation(row)  # type: ignore[operator]

    with pytest.raises(CHECKER.ContractError, match=match):
        CHECKER.parse_mypy_jsonl(_jsonl(row), returncode=1)


def test_mypy_jsonl_rejects_duplicate_keys_non_finite_and_missing_newline() -> None:
    duplicate = '{"file":"src/mclab/a.py","file":"src/mclab/b.py"}\n'
    with pytest.raises(CHECKER.ContractError, match="duplicate JSON key"):
        CHECKER.parse_mypy_jsonl(duplicate, returncode=1)
    with pytest.raises(CHECKER.ContractError, match="non-finite"):
        CHECKER._strict_json('{"value": NaN}')
    with pytest.raises(CHECKER.ContractError, match="end with a newline"):
        CHECKER.parse_mypy_jsonl(json.dumps(_row()), returncode=1)


@pytest.mark.parametrize(
    "mutate, match",
    (
        (lambda doc: doc.update(extra=True), "keys mismatch"),
        (lambda doc: doc.update(schema_version=True), "schema_version"),
        (
            lambda doc: doc["baseline"]["by_code"].reverse(),  # type: ignore[index]
            "unique and sorted",
        ),
        (
            lambda doc: doc["baseline"].update(error_count=263),  # type: ignore[index]
            "does not reconcile",
        ),
        (
            lambda doc: doc["policy"].update(additions_are_forbidden=1),  # type: ignore[index]
            "must be a boolean",
        ),
        (
            lambda doc: doc["environment"].update(profile="app-dev"),  # type: ignore[index]
            "environment.profile",
        ),
        (
            lambda doc: doc["tool"].update(controlled_import_roots=[]),  # type: ignore[index]
            "controlled_import_roots",
        ),
        (
            lambda doc: doc["environment"].update(  # type: ignore[index]
                bootstrap_distribution_allowlist=[
                    {"name": "pyside6-essentials", "version": "6.11.1"}
                ]
            ),
            "bootstrap_distribution_allowlist",
        ),
        (
            lambda doc: doc["suppressions"].update(kinds=[]),  # type: ignore[index]
            "suppressions.kinds",
        ),
    ),
)
def test_baseline_schema_rejects_unknown_unsorted_or_inconsistent_data(
    mutate: object, match: str
) -> None:
    document = copy.deepcopy(_baseline_document())
    mutate(document)  # type: ignore[operator]

    with pytest.raises(CHECKER.ContractError, match=match):
        CHECKER.validate_baseline_document(document)


def test_baseline_digest_and_config_are_immutable(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_bytes((ROOT / CHECKER.BASELINE_RELATIVE).read_bytes() + b" ")
    with pytest.raises(CHECKER.ContractError, match="digest mismatch"):
        CHECKER.load_baseline(baseline_path)

    previous_config_path = ROOT / CHECKER.PREVIOUS_CONFIG_RELATIVE
    assert previous_config_path.read_bytes() == b"[mypy]\n"
    assert (
        CHECKER.hashlib.sha256(previous_config_path.read_bytes()).hexdigest()
        == CHECKER.PREVIOUS_CONFIG_SHA256
    )
    config_path = ROOT / CHECKER.CONFIG_RELATIVE
    assert config_path.read_bytes() == (
        b"[mypy]\n"
        b"check_untyped_defs = True\n"
        b"disallow_untyped_defs = True\n"
        b"disallow_incomplete_defs = True\n"
    )
    assert CHECKER.hashlib.sha256(config_path.read_bytes()).hexdigest() == CHECKER.CONFIG_SHA256


def test_live_fully_untyped_bad_module_is_rejected(tmp_path: Path) -> None:
    module = tmp_path / "untyped_bad.py"
    module.write_text(
        'def broken():\n    return 1 + "bad"\n',
        encoding="utf-8",
    )

    returncode, diagnostics = _live_mypy(module)

    assert returncode == 1
    assert any(code == "no-untyped-def" for _file, code, _message in diagnostics)
    assert any(code == "operator" for _file, code, _message in diagnostics)


def test_live_annotation_removal_changes_clean_module_to_failure(tmp_path: Path) -> None:
    module = tmp_path / "annotation_regression.py"
    module.write_text("def identity(value: int) -> int:\n    return value\n", encoding="utf-8")
    clean_returncode, clean = _live_mypy(module)
    module.write_text("def identity(value: int):\n    return value\n", encoding="utf-8")
    bad_returncode, bad = _live_mypy(module)

    assert clean_returncode == 0
    assert clean == Counter()
    assert bad_returncode == 1
    assert any(code == "no-untyped-def" for _file, code, _message in bad)


def test_explicit_any_remains_named_unabsorbed_781_diagnostic_residual() -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    document = _baseline_document()
    argv = [*CHECKER.mypy_argv(_native_python_version())]
    argv.insert(-1, "--disallow-any-explicit")

    process = CHECKER._run_bounded(
        argv,
        cwd=ROOT,
        env=CHECKER._sanitised_environment(),
        timeout_seconds=CHECKER.DEFAULT_TIMEOUT_SECONDS,
        stdout_limit=CHECKER.MAX_MYPY_OUTPUT_BYTES,
        stderr_limit=CHECKER.MAX_STDERR_BYTES,
    )
    diagnostic_count = len(process.stdout.splitlines())

    assert process.returncode == 1
    assert process.stderr == ""
    assert diagnostic_count - baseline.error_count == 781
    assert document["policy"]["explicit_any_residual"] == CHECKER.EXPLICIT_ANY_RESIDUAL  # type: ignore[index]


def test_project_and_lock_inputs_match_the_immutable_environment_contract() -> None:
    inputs = CHECKER._validate_policy_inputs(ROOT)

    assert CHECKER.hashlib.sha256(inputs[CHECKER.PYPROJECT_RELATIVE]).hexdigest() == (
        CHECKER.PYPROJECT_SHA256
    )
    assert CHECKER.hashlib.sha256(inputs[CHECKER.BUILD_LOCK_RELATIVE]).hexdigest() == (
        CHECKER.BUILD_LOCK_SHA256
    )
    assert CHECKER.hashlib.sha256(inputs[CHECKER.DEV_LOCK_RELATIVE]).hexdigest() == (
        CHECKER.DEV_LOCK_SHA256
    )


@pytest.mark.parametrize("constant", ("PYPROJECT_SHA256", "BUILD_LOCK_SHA256", "DEV_LOCK_SHA256"))
def test_project_or_lock_digest_drift_fails_closed(
    constant: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CHECKER, constant, "0" * 64)

    with pytest.raises(CHECKER.ContractError, match="immutable policy input drifted"):
        CHECKER._validate_policy_inputs(ROOT)


def test_canonical_argv_pins_config_platform_and_source() -> None:
    argv = CHECKER.mypy_argv("3.12")

    assert argv[:4] == (sys.executable, "-I", "-m", "mypy")
    assert "--no-incremental" in argv
    assert argv[argv.index("--config-file") + 1] == CHECKER.CONFIG_RELATIVE.as_posix()
    assert argv[argv.index("--python-version") + 1] == "3.12"
    assert argv[argv.index("--platform") + 1] == "linux"
    assert argv[-1] == "src/mclab"
    with pytest.raises(CHECKER.ContractError, match="unsupported Python target"):
        CHECKER.mypy_argv("3.13")


def test_environment_attestation_accepts_exact_dev_inventory_and_mypy_origin() -> None:
    inputs = CHECKER._validate_policy_inputs(ROOT)
    attestation = CHECKER.attest_environment(ROOT, policy_inputs=inputs)

    assert attestation.sys_platform == "linux"
    assert attestation.platform_machine == "x86_64"
    assert attestation.python_version in CHECKER.SUPPORTED_PYTHON_VERSIONS
    assert Path(attestation.prefix).is_absolute()
    assert Path(attestation.base_prefix).is_absolute()
    inventory = {item.name: item for item in attestation.inventory}
    assert inventory["mypy"].version == CHECKER.MYPY_VERSION
    assert all(Path(item.root).is_relative_to(attestation.prefix) for item in inventory.values())
    assert all(Path(item.origin).is_relative_to(attestation.prefix) for item in inventory.values())
    assert Path(attestation.mypy_origin).is_relative_to(
        Path(attestation.mypy_distribution_root) / "mypy"
    )


def test_environment_attestation_rejects_app_dev_contamination_and_bad_origin() -> None:
    inputs = CHECKER._validate_policy_inputs(ROOT)
    attestation = CHECKER.attest_environment(ROOT, policy_inputs=inputs)
    prefix = Path(attestation.prefix)
    contaminated = replace(
        attestation,
        inventory=tuple(
            sorted(
                (
                    *attestation.inventory,
                    CHECKER.DistributionAttestation(
                        name="pyside6-essentials",
                        version="6.11.1",
                        root=str(prefix),
                        origin=str(prefix / "pyside6_essentials-6.11.1.dist-info"),
                    ),
                ),
                key=lambda item: (item.name, item.version, item.root, item.origin),
            )
        ),
    )
    bad_origin = replace(attestation, mypy_origin=str(ROOT / "mypy.py"))

    with pytest.raises(CHECKER.ContractError, match="DEPENDENCY_PROFILE_MISMATCH"):
        CHECKER._validate_environment_attestation(contaminated, policy_inputs=inputs)
    with pytest.raises(CHECKER.ContractError, match="mypy import origin"):
        CHECKER._validate_environment_attestation(bad_origin, policy_inputs=inputs)


def test_environment_attestation_rejects_distribution_outside_selected_prefix() -> None:
    inputs = CHECKER._validate_policy_inputs(ROOT)
    attestation = CHECKER.attest_environment(ROOT, policy_inputs=inputs)
    selected = next(item for item in attestation.inventory if item.name == "pytest")
    outside = replace(
        selected,
        root="/usr/lib/python3/dist-packages",
        origin="/usr/lib/python3/dist-packages/pytest-9.1.1.dist-info",
    )
    outside_inventory = tuple(
        outside if item.name == selected.name else item for item in attestation.inventory
    )

    with pytest.raises(CHECKER.ContractError, match="DEPENDENCY_ORIGIN_OUTSIDE_PREFIX"):
        CHECKER._validate_environment_attestation(
            replace(attestation, inventory=outside_inventory),
            policy_inputs=inputs,
        )


def test_environment_sanitization_removes_python_and_mypy_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/tmp/injected")
    monkeypatch.setenv("PYTHONHOME", "/tmp/injected")
    monkeypatch.setenv("MYPYPATH", "/tmp/injected")
    monkeypatch.setenv("MYPY_FORCE_COLOR", "1")

    environment = CHECKER._sanitised_environment()

    assert "PYTHONPATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "MYPYPATH" not in environment
    assert "MYPY_FORCE_COLOR" not in environment
    assert environment["PYTHONNOUSERSITE"] == "1"


@pytest.mark.parametrize(
    "output, match",
    (
        ("mypy 2.2.0\n", "must be 2.3.0"),
        ("mypy 2.3.0 forged-suffix\n", "unrecognized mypy version output"),
    ),
)
def test_execute_mypy_rejects_tool_version_drift_or_suffix(
    output: str,
    match: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> object:
        return CHECKER.BoundedProcess(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(CHECKER, "_run_bounded", fake_run)

    with pytest.raises(CHECKER.ContractError, match=match):
        CHECKER.execute_mypy(ROOT, "3.11")


def test_validate_repository_fails_on_executor_stderr_or_argv_drift() -> None:
    native = _native_python_version()
    canonical = CHECKER.mypy_argv(native)

    def stderr_executor(_root: Path, _version: str) -> object:
        return CHECKER.MypyExecution("2.3.0", 1, _jsonl(_row()), "warning\n", canonical)

    with pytest.raises(CHECKER.ContractError, match="stderr must be empty"):
        CHECKER.validate_repository(ROOT, python_version=native, executor=stderr_executor)

    def argv_executor(_root: Path, _version: str) -> object:
        return CHECKER.MypyExecution("2.3.0", 1, _jsonl(_row()), "", canonical[:-1])

    with pytest.raises(CHECKER.ContractError, match="argv drifted"):
        CHECKER.validate_repository(ROOT, python_version=native, executor=argv_executor)


def test_run_bounded_drains_large_stdout_and_stderr_without_deadlock() -> None:
    size = 256 * 1024
    script = f"import os\nos.write(1, b'o' * {size})\nos.write(2, b'e' * {size})\n"

    result = CHECKER._run_bounded(
        (sys.executable, "-I", "-c", script),
        cwd=ROOT,
        env=CHECKER._sanitised_environment(),
        timeout_seconds=10,
        stdout_limit=size + 1,
        stderr_limit=size + 1,
    )

    assert result.returncode == 0
    assert result.stdout == "o" * size
    assert result.stderr == "e" * size


@pytest.mark.parametrize(("file_descriptor", "label"), ((1, "stdout"), (2, "stderr")))
def test_run_bounded_terminates_on_either_output_cap(
    file_descriptor: int,
    label: str,
) -> None:
    script = f"import os, time\nos.write({file_descriptor}, b'x' * (1024 * 1024))\ntime.sleep(30)\n"
    started = time.monotonic()

    with pytest.raises(CHECKER.ContractError, match=rf"{label} exceeded") as caught:
        CHECKER._run_bounded(
            (sys.executable, "-I", "-c", script),
            cwd=ROOT,
            env=CHECKER._sanitised_environment(),
            timeout_seconds=10,
            stdout_limit=1024,
            stderr_limit=1024,
        )

    assert time.monotonic() - started < 5
    assert len(str(caught.value)) < 160
    assert "child terminated" in str(caught.value)


def test_execute_mypy_timeout_is_wrapped_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="mypy", timeout=1)

    monkeypatch.setattr(CHECKER, "_run_bounded", timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        CHECKER.execute_mypy(ROOT, "3.11")


def test_main_reports_exact_pass_and_migration_required_failure(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = CHECKER.load_baseline(ROOT / CHECKER.BASELINE_RELATIVE)
    exact = CHECKER.compare_diagnostics(
        baseline,
        baseline.diagnostics.copy(),
        python_version="3.11",
        native_python_version="3.11.9",
        interpreter_prefix_mode="interpreter-prefix",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions.copy(),
    )
    monkeypatch.setattr(CHECKER, "validate_repository", lambda **_kwargs: exact)

    assert CHECKER.main(["--python-version", "3.11"]) == 0
    output = capsys.readouterr().out
    assert f"errors={exact.error_count}/{baseline.error_count}" in output
    assert f"source_files={baseline.source_file_count}" in output
    assert "native=3.11.9; target=3.11" in output
    assert "prefix_mode=interpreter-prefix" in output
    assert "status: PASS" in output

    reduced = CHECKER.compare_diagnostics(
        baseline,
        _remove_one(baseline.diagnostics),
        python_version="3.11",
        source_file_count=baseline.source_file_count,
        current_suppressions=baseline.suppressions.copy(),
    )
    monkeypatch.setattr(CHECKER, "validate_repository", lambda **_kwargs: reduced)
    assert CHECKER.main(["--python-version", "3.11"]) == 1
    output = capsys.readouterr().out
    assert "REQUIRES_MIGRATION" in output
    assert "status: FAIL" in output

    assert CHECKER.main(["--unknown"]) == 2


def test_ci_preserves_six_job_names_and_separates_native_mypy_from_pytest() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    jobs = workflow["jobs"]
    desktop = yaml.safe_load((ROOT / ".github" / "workflows" / "desktop.yml").read_text())

    assert workflow["name"] == "CI"
    assert {job["name"] for job in jobs.values()} == {
        "Simulator lint and tests",
        "Paper citation and formula gates",
        "Paper LaTeX build",
    }
    assert desktop["name"] == "Desktop app smoke and unsigned builds"
    assert desktop["jobs"]["desktop"]["name"] == "Unsigned development build (${{ matrix.os }})"
    assert desktop["jobs"]["desktop"]["strategy"]["matrix"]["os"] == [
        "windows-2025",
        "ubuntu-24.04",
        "macos-15",
    ]
    assert len(jobs) + len(desktop["jobs"]["desktop"]["strategy"]["matrix"]["os"]) == 6
    simulator_steps = jobs["simulator"]["steps"]
    named_steps = {step.get("name"): step for step in simulator_steps if "name" in step}
    for version in CHECKER.SUPPORTED_PYTHON_VERSIONS:
        name = f"Python {version} mypy exact-debt checker"
        assert named_steps[name]["run"] == (
            f"python .agents/validation/check_mypy_baseline.py --python-version {version}"
        )
        assert "pytest" not in named_steps[name]["run"]
    pytest_steps = [step for step in simulator_steps if "pytest" in step.get("run", "")]
    assert pytest_steps
    assert all("check_mypy_baseline.py" not in step["run"] for step in pytest_steps)
