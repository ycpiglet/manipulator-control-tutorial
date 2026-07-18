#!/usr/bin/env python3
"""Capture real-EGL Lab01-Lab04 scenes and score semantic state changes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application.visual_semantics import (  # noqa: E402
    SEMANTIC_COLORS,
    color_vision_separation,
    rgb,
)


@dataclass(frozen=True)
class SceneCase:
    name: str
    scenario: str
    actions: str
    screenshot_ms: int
    required_base: tuple[str, ...]
    required_changed: tuple[str, ...] = ()
    minimum_change_ratio: float = 0.002


@dataclass
class SceneResult:
    name: str
    passed: bool
    baseline: str
    changed: str
    changed_pixel_ratio: float
    mean_pixel_delta: float
    base_token_distance: dict[str, float]
    changed_token_distance: dict[str, float]
    notes: list[str]


CASES = (
    SceneCase(
        "lab01_mass_spring",
        "lab01.interactive-pull",
        "save_prediction,push",
        700,
        ("current", "target"),
        ("force",),
    ),
    SceneCase(
        "lab02_pid",
        "lab02.interactive-disturbance",
        "save_prediction,push",
        700,
        ("current", "target"),
        ("force",),
    ),
    SceneCase(
        "lab03_two_link",
        "lab03.interactive-2dof",
        "save_prediction,control_target_x=0.88,control_target_y=0.18",
        1600,
        ("current", "target", "workspace"),
    ),
    SceneCase(
        "lab04_virtual_wall",
        "lab04.interactive-virtual-wall",
        (
            "save_prediction,control_target_x=0.70,control_wall_x=0.50,"
            "control_cartesian_gain=1.05,control_wall_stiffness=320"
        ),
        3900,
        ("current", "target", "wall"),
        ("force",),
    ),
)


def _pixels(path: Path) -> np.ndarray:
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.bits(), dtype=np.uint8, count=image.sizeInBytes())
    return data.reshape(height, image.bytesPerLine())[:, : width * 3].reshape(height, width, 3).copy()


def _scene_roi(pixels: np.ndarray) -> np.ndarray:
    height, width = pixels.shape[:2]
    return pixels[int(height * 0.35) : int(height * 0.82), int(width * 0.16) : int(width * 0.59)]


def _token_distances(pixels: np.ndarray, names: tuple[str, ...]) -> dict[str, float]:
    sample = pixels.reshape(-1, 3).astype(float)
    return {
        name: float(np.linalg.norm(sample - rgb(SEMANTIC_COLORS[name]), axis=1).min())
        for name in names
    }


def _capture(
    case: SceneCase,
    output: Path,
    settings: Path,
    *,
    changed: bool,
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    suffix = "changed" if changed else "baseline"
    screenshot = output / f"{case.name}_{suffix}.png"
    env = {
        **os.environ,
        "QT_QUICK_BACKEND": "software",
        "MUJOCO_GL": "egl",
        "XDG_CONFIG_HOME": str(settings / f"{case.name}_{suffix}"),
        "MCLAB_OUTPUT_DIR": str(output / f"{case.name}_{suffix}_run"),
        "MCLAB_WINDOW_WIDTH": "1280",
        "MCLAB_WINDOW_HEIGHT": "720",
        "MCLAB_APP_AUTO_QUIT_MS": str(case.screenshot_ms + 1100),
        "MCLAB_SCREENSHOT_MS": str(case.screenshot_ms),
        "MCLAB_SCREENSHOT_PATH": str(screenshot),
        "MCLAB_FAIL_ON_ERROR": "1",
        "MCLAB_SELF_TEST": "1",
        "MCLAB_SMOKE_ACTION_MS": "350",
        "MCLAB_SMOKE_ACTION_INTERVAL_MS": "180",
    }
    if changed:
        env["MCLAB_SMOKE_ACTION"] = case.actions
    command = [sys.executable, "-m", "mclab", "app", "--lang", "ko", "--scenario", case.scenario]
    return screenshot, subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_case(case: SceneCase, output: Path, settings: Path) -> SceneResult:
    baseline_path, baseline_run = _capture(case, output, settings, changed=False)
    changed_path, changed_run = _capture(case, output, settings, changed=True)
    notes: list[str] = []
    if baseline_run.returncode:
        notes.append(f"baseline app exit {baseline_run.returncode}")
    if changed_run.returncode:
        notes.append(f"changed app exit {changed_run.returncode}")
    if not baseline_path.is_file() or not changed_path.is_file():
        notes.append("one or both screenshots are missing")
        return SceneResult(
            case.name,
            False,
            str(baseline_path),
            str(changed_path),
            0.0,
            0.0,
            {},
            {},
            notes,
        )
    baseline = _scene_roi(_pixels(baseline_path))
    changed = _scene_roi(_pixels(changed_path))
    delta = np.abs(changed.astype(np.int16) - baseline.astype(np.int16))
    changed_ratio = float(np.any(delta > 24, axis=2).mean())
    mean_delta = float(delta.mean())
    base_distances = _token_distances(baseline, case.required_base)
    changed_distances = _token_distances(changed, case.required_changed)
    if changed_ratio < case.minimum_change_ratio:
        notes.append(f"scene changed only {changed_ratio:.4%}")
    for name, distance in {**base_distances, **changed_distances}.items():
        if distance > 80.0:
            notes.append(f"{name} marker is not visibly close to its semantic token")
    passed = (
        baseline_run.returncode == 0
        and changed_run.returncode == 0
        and changed_ratio >= case.minimum_change_ratio
        and not notes
    )
    return SceneResult(
        case.name,
        passed,
        str(baseline_path),
        str(changed_path),
        changed_ratio,
        mean_delta,
        base_distances,
        changed_distances,
        notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mclab-scene-audit"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mclab-scene-settings-") as tmp:
        results = [_run_case(case, args.output, Path(tmp)) for case in CASES]
    cvd = color_vision_separation()
    cvd_passed = all(
        metrics["minimum_token_distance"] >= 24.0
        and metrics["minimum_background_distance"] >= 100.0
        for metrics in cvd.values()
    )
    report = {
        "passed": all(item.passed for item in results) and cvd_passed,
        "color_vision_passed": cvd_passed,
        "color_vision": cvd,
        "cases": [asdict(item) for item in results],
    }
    report_path = args.output / "scene_audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        state = "PASS" if item.passed else "FAIL"
        print(f"{state} {item.name}: change={item.changed_pixel_ratio:.2%}; delta={item.mean_pixel_delta:.2f}")
    print(f"{'PASS' if cvd_passed else 'FAIL'} color-vision redundancy")
    print(f"Report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
