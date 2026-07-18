#!/usr/bin/env python3
"""Measure five fresh-settings desktop starts against the 5-second p95 gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _sample(index: int, output: Path, settings: Path) -> dict[str, object]:
    metric = output / f"startup_{index}.json"
    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
        "XDG_CONFIG_HOME": str(settings / f"settings_{index}"),
        "XDG_DATA_HOME": str(settings / f"share_{index}"),
        "MCLAB_DATA_DIR": str(settings / f"data_{index}"),
        "MCLAB_OUTPUT_DIR": str(output / f"run_{index}"),
        "MCLAB_APP_AUTO_QUIT_MS": "650",
        "MCLAB_SELF_TEST": "1",
        "MCLAB_FAIL_ON_ERROR": "1",
        "MCLAB_SMOKE_ACTION": "startup_probe",
        "MCLAB_SMOKE_ACTION_MS": "0",
        "MCLAB_STARTUP_PATH": str(metric),
        "MCLAB_STARTUP_BEGIN_NS": str(time.monotonic_ns()),
    }
    completed = subprocess.run(
        [sys.executable, "-m", "mclab", "app", "--safe-mode", "--lang", "ko"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    value = None
    if metric.is_file():
        value = float(json.loads(metric.read_text(encoding="utf-8"))["startup_ms"])
    return {
        "sample": index,
        "startup_ms": value,
        "return_code": completed.returncode,
        "stderr": completed.stderr.strip()[-300:],
    }


def _duplicate_instance_probe(output: Path, settings: Path) -> dict[str, object]:
    ready = output / "duplicate_first_ready.json"
    activation = output / "duplicate_activation.json"
    activation.unlink(missing_ok=True)
    base_env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
        "XDG_CONFIG_HOME": str(settings / "duplicate_config"),
        "XDG_DATA_HOME": str(settings / "duplicate_share"),
        "MCLAB_DATA_DIR": str(settings / "duplicate_data"),
        "MCLAB_OUTPUT_DIR": str(output / "duplicate_output"),
        "MCLAB_ACTIVATION_PATH": str(activation),
        "MCLAB_SELF_TEST": "1",
    }
    first_env = {
        **base_env,
        "MCLAB_APP_AUTO_QUIT_MS": "2500",
        "MCLAB_SMOKE_ACTION": "startup_probe",
        "MCLAB_SMOKE_ACTION_MS": "0",
        "MCLAB_STARTUP_PATH": str(ready),
        "MCLAB_STARTUP_BEGIN_NS": str(time.monotonic_ns()),
    }
    command = [sys.executable, "-m", "mclab", "app", "--safe-mode", "--lang", "ko"]
    first = subprocess.Popen(
        command,
        cwd=ROOT,
        env=first_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 5.0
    while not ready.is_file() and first.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    first_ready = ready.is_file()
    second_started = time.perf_counter()
    second = subprocess.run(
        command,
        cwd=ROOT,
        env={**base_env, "MCLAB_APP_AUTO_QUIT_MS": "650"},
        text=True,
        capture_output=True,
        check=False,
    )
    second_ms = (time.perf_counter() - second_started) * 1000.0
    activation_deadline = time.monotonic() + 1.0
    while not activation.is_file() and time.monotonic() < activation_deadline:
        time.sleep(0.02)
    activation_count = 0
    if activation.is_file():
        activation_count = int(
            json.loads(activation.read_text(encoding="utf-8")).get("activation_count", 0)
        )
    try:
        first_stdout, first_stderr = first.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        first.terminate()
        first_stdout, first_stderr = first.communicate(timeout=2.0)
    restart = subprocess.run(
        command,
        cwd=ROOT,
        env={**base_env, "MCLAB_APP_AUTO_QUIT_MS": "650"},
        text=True,
        capture_output=True,
        check=False,
    )
    message = "MCLab이 이미 실행 중입니다."
    passed = (
        first_ready
        and first.returncode == 0
        and second.returncode == 6
        and second_ms <= 1000.0
        and message in second.stderr
        and activation_count == 1
        and restart.returncode == 0
    )
    return {
        "passed": passed,
        "first_ready": first_ready,
        "first_return_code": first.returncode,
        "first_stderr": first_stderr.strip()[-300:],
        "first_stdout": first_stdout.strip()[-300:],
        "second_return_code": second.returncode,
        "second_ms": second_ms,
        "second_stderr": second.stderr.strip()[-300:],
        "activation_count": activation_count,
        "restart_return_code": restart.returncode,
        "restart_stderr": restart.stderr.strip()[-300:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mclab-startup-audit"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mclab-startup-settings-") as tmp:
        settings = Path(tmp)
        samples = [_sample(index, args.output, settings) for index in range(1, 6)]
        duplicate = _duplicate_instance_probe(args.output, settings)
    values = [float(item["startup_ms"]) for item in samples if item["startup_ms"] is not None]
    p95_ms = float(np.percentile(values, 95)) if values else float("inf")
    passed = (
        len(values) == 5
        and all(item["return_code"] == 0 for item in samples)
        and p95_ms <= 5000.0
        and bool(duplicate["passed"])
    )
    report = {
        "passed": passed,
        "threshold_ms": 5000.0,
        "p95_ms": p95_ms,
        "samples": samples,
        "duplicate_instance": duplicate,
    }
    report_path = args.output / "startup_audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'PASS' if passed else 'FAIL'} cold start p95: {p95_ms:.1f} ms (limit 5000 ms)")
    print("Samples: " + ", ".join(f"{value:.1f}" for value in values) + " ms")
    print(
        f"{'PASS' if duplicate['passed'] else 'FAIL'} duplicate instance: "
        f"second rc={duplicate['second_return_code']} in {float(duplicate['second_ms']):.1f} ms; "
        f"restart rc={duplicate['restart_return_code']}"
    )
    print(f"Report: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
