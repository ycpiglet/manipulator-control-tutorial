#!/usr/bin/env python3
"""Run the real plotted course comparison through Qt and audit responsiveness."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.application.artifacts import verify_manifest  # noqa: E402
from mclab.application.qt_batch import create_batch_controller  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _rss_kb(pid: int) -> int | None:
    """Read direct-child RSS where Linux procfs is available."""

    if pid <= 0:
        return None
    try:
        lines = (Path("/proc") / str(pid) / "status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mclab-course-comparison-audit"))
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--max-ui-gap-ms", type=float, default=500.0)
    parser.add_argument("--max-output-mb", type=float, default=150.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    runtime = args.output / f"runtime-{time.strftime('%Y%m%d-%H%M%S')}"
    os.environ["MCLAB_DATA_DIR"] = str(runtime)

    from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTimer, Signal

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    BatchController = create_batch_controller(QObject, QProcess, QTimer, Signal)
    controller = BatchController()
    started = time.perf_counter()
    last_pulse = started
    heartbeat_gaps_ms: list[float] = []
    progress: list[dict[str, Any]] = []
    rss_samples_kb: list[int] = []
    outcome = {"status": "not_started", "detail": ""}
    timed_out = False

    def pulse() -> None:
        nonlocal last_pulse
        now = time.perf_counter()
        heartbeat_gaps_ms.append((now - last_pulse) * 1000.0)
        last_pulse = now
        process = controller.process
        pid = int(process.processId()) if process is not None else 0
        rss = _rss_kb(pid)
        if rss is not None:
            rss_samples_kb.append(rss)

    def changed() -> None:
        snapshot = controller.snapshot()
        current = int(snapshot["current"])
        if current > 0 and (not progress or progress[-1]["current"] != current):
            progress.append(
                {
                    "current": current,
                    "total": int(snapshot["total"]),
                    "name": str(snapshot["name"]),
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )

    def settle(status: str, detail: str = "") -> None:
        outcome.update(status=status, detail=detail)
        QTimer.singleShot(0, app.quit)

    def timeout() -> None:
        nonlocal timed_out
        if not controller.running:
            return
        timed_out = True
        controller.cancel()

    controller.changed.connect(changed)
    controller.completed.connect(lambda _path: settle("completed"))
    controller.stopped.connect(lambda _path: settle("timeout" if timed_out else "stopped"))
    controller.failed.connect(lambda detail, _path: settle("error", detail))
    heartbeat = QTimer()
    heartbeat.setInterval(25)
    heartbeat.timeout.connect(pulse)
    heartbeat.start()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.setInterval(max(1, int(args.timeout_seconds * 1000)))
    deadline.timeout.connect(timeout)
    deadline.start()

    try:
        output = Path(controller.start())
    except Exception as exc:
        outcome.update(status="start_error", detail=str(exc))
        output = Path()
    else:
        app.exec()
    elapsed = time.perf_counter() - started
    heartbeat.stop()
    deadline.stop()

    summary = _read_json(output / "summary.json") if output else {}
    manifest = _read_json(output / "manifest.json") if output else {}
    child_reports = list(output.glob("*/report.html")) if output else []
    all_reports = list(output.rglob("report.html")) if output else []
    course_reports = ([output / "report.html"] if (output / "report.html").is_file() else [])
    course_reports.extend(child_reports)
    comparison_plots = list(output.glob("*/comparison_plots/*.png")) if output else []
    integrity_errors = verify_manifest(output) if output and output.is_dir() else ["Output missing."]
    output_bytes = _directory_size(output) if output and output.is_dir() else 0
    max_gap_ms = max(heartbeat_gaps_ms, default=float("inf"))
    output_mb = output_bytes / (1024.0 * 1024.0)
    checks = {
        "completed": outcome["status"] == "completed",
        "progress_1_through_5": [item["current"] for item in progress] == [1, 2, 3, 4, 5]
        and [item["name"] for item in progress]
        == [
            "lab01_msd_compare",
            "lab02_pid_compare",
            "lab03_2dof_compare",
            "lab04_cartesian_compare",
            "lab04_wall_compare",
        ]
        and all(item["total"] == 5 for item in progress),
        "ui_heartbeat": len(heartbeat_gaps_ms) >= 10 and max_gap_ms <= args.max_ui_gap_ms,
        "within_timeout": elapsed <= args.timeout_seconds and not timed_out,
        "five_batch_sets": int(summary.get("child_batches", 0)) == 5
        and len(child_reports) == 5,
        "fifty_four_scenarios": int(summary.get("scenario_runs", 0)) == 54,
        "six_course_reports": len(course_reports) == 6,
        "comparison_plots": len(comparison_plots) >= 5,
        "manifest_complete": manifest.get("scenario_id") == "batch.all"
        and manifest.get("status") == "completed",
        "artifact_integrity": not integrity_errors,
        "output_size": output_mb <= args.max_output_mb,
    }
    report = {
        "passed": all(checks.values()),
        "thresholds": {
            "timeout_seconds": args.timeout_seconds,
            "max_ui_gap_ms": args.max_ui_gap_ms,
            "max_output_mb": args.max_output_mb,
        },
        "checks": checks,
        "measurements": {
            "status": outcome["status"],
            "detail": outcome["detail"],
            "elapsed_seconds": elapsed,
            "max_ui_gap_ms": max_gap_ms,
            "heartbeat_count": len(heartbeat_gaps_ms),
            "peak_child_rss_kb": max(rss_samples_kb, default=0),
            "output_mb": output_mb,
            "course_reports": len(course_reports),
            "all_reports": len(all_reports),
            "comparison_plots": len(comparison_plots),
            "scenario_runs": summary.get("scenario_runs", 0),
            "progress": progress,
            "integrity_errors": integrity_errors,
        },
        "output": str(output),
    }
    report_path = args.output / "course_comparison_audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    label = "PASS" if report["passed"] else "FAIL"
    print(
        f"{label} plotted course comparison: {elapsed:.2f} s; "
        f"UI gap {max_gap_ms:.1f} ms; {output_mb:.1f} MB; "
        f"{len(comparison_plots)} comparison plots"
    )
    print("Progress: " + " -> ".join(str(item["current"]) for item in progress))
    print(f"Report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
