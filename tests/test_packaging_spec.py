from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "packaging" / "mclab.spec"


def _analysis_exclusions() -> tuple[str, ...]:
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"), filename=str(SPEC_PATH))
    analysis_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Analysis"
    ]
    assert len(analysis_calls) == 1, "mclab.spec must define exactly one Analysis call"

    exclusion_keywords = [
        keyword for keyword in analysis_calls[0].keywords if keyword.arg == "excludes"
    ]
    assert len(exclusion_keywords) == 1, "Analysis must define exactly one excludes keyword"

    value = exclusion_keywords[0].value
    assert isinstance(
        value, (ast.List, ast.Tuple)
    ), "Analysis excludes must be a literal list or tuple"
    assert all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ), "Analysis excludes must contain only string literals"
    return tuple(element.value for element in value.elts)


def test_production_bundle_excludes_source_audit_qt_modules() -> None:
    exclusions = _analysis_exclusions()

    assert {"PySide6.QtTest", "PySide6.QtWidgets"} <= set(exclusions)


def test_production_bundle_exclusions_do_not_repeat_modules() -> None:
    exclusions = _analysis_exclusions()

    assert len(exclusions) == len(set(exclusions))


def test_spec_verifies_and_bundles_only_the_canonical_panda_runtime_tree() -> None:
    source = SPEC_PATH.read_text(encoding="utf-8")

    assert source.index("verify_assets(root=ROOT)") < source.index("Analysis(")
    assert (
        '(str(PANDA_ASSETS.target), "third_party/mujoco_menagerie/franka_emika_panda")'
        in source
    )
    assert "franka_emika_panda/assets" not in source
    assert "franka_emika_panda/panda.xml" not in source
    assert "assets install --force" in source
