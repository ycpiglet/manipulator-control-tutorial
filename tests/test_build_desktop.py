from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_desktop.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("mclab_build_desktop_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_preflight_runs_before_pyinstaller(tmp_path: Path) -> None:
    module = _load_build_module()
    events: list[str] = []

    with (
        patch.object(module, "ROOT", tmp_path),
        patch.object(
            module,
            "_verify_panda_assets",
            side_effect=lambda: events.append("verify"),
        ),
        patch.object(
            module.subprocess,
            "run",
            side_effect=lambda *args, **kwargs: events.append("pyinstaller"),
        ),
        patch.object(sys, "argv", ["build_desktop.py", "--skip-size-gate"]),
    ):
        assert module.main() == 0

    assert events == ["verify", "pyinstaller"]


def test_build_preflight_blocks_pyinstaller_on_invalid_assets(tmp_path: Path) -> None:
    module = _load_build_module()

    with (
        patch.object(module, "ROOT", tmp_path),
        patch.object(
            module,
            "_verify_panda_assets",
            side_effect=RuntimeError("invalid Panda assets"),
        ),
        patch.object(module.subprocess, "run") as pyinstaller,
        patch.object(sys, "argv", ["build_desktop.py"]),
        pytest.raises(RuntimeError, match="invalid Panda assets"),
    ):
        module.main()

    pyinstaller.assert_not_called()


def test_build_preflight_reports_force_repair_guidance(tmp_path: Path) -> None:
    module = _load_build_module()
    panda_root = (
        tmp_path / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
    )
    panda_root.mkdir(parents=True)

    with (
        patch.object(module, "ROOT", tmp_path),
        patch(
            "mclab.application.assets.verify_assets",
            side_effect=ValueError("tampered scene.xml"),
        ),
        pytest.raises(RuntimeError, match="assets install --force"),
    ):
        module._verify_panda_assets()


def test_build_preflight_reports_non_force_guidance_for_missing_tree(tmp_path: Path) -> None:
    from mclab.application.assets import AssetVerificationError

    module = _load_build_module()
    panda_root = (
        tmp_path / "third_party" / "mujoco_menagerie" / "franka_emika_panda"
    )
    failure = AssetVerificationError(panda_root, ["runtime tree is missing"])

    with (
        patch.object(module, "ROOT", tmp_path),
        patch("mclab.application.assets.verify_assets", side_effect=failure),
        pytest.raises(RuntimeError) as raised,
    ):
        module._verify_panda_assets()

    assert "assets install`" in str(raised.value)
    assert "--force" not in str(raised.value)
