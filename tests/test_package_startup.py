from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import pytest

from scripts import audit_package_startup as startup


def _runner_os() -> str:
    return {
        "Darwin": "macOS",
        "Linux": "Linux",
        "Windows": "Windows",
    }[platform.system()]


def _package_evidence(
    workflow_sha: str,
    *,
    runner_os: str | None = None,
    identity: str = "a" * 64,
) -> dict[str, object]:
    selected_os = runner_os or _runner_os()
    return {
        "archive": {
            "filename": "MCLab-test.tar.gz",
            "format": "tar.gz",
            "sha256": "b" * 64,
            "size_bytes": 1234,
        },
        "artifact_class": "unsigned-development",
        "gates": {
            "archive": {
                "enforced": True,
                "limit_bytes": startup.build_desktop.ARCHIVE_LIMIT_BYTES,
                "measured_bytes": 1234,
                "passed": True,
                "unit": "bytes",
            },
            "one_folder": {
                "enforced": True,
                "limit_bytes": startup.build_desktop.ONE_FOLDER_LIMIT_BYTES,
                "measured_bytes": 5678,
                "passed": True,
                "unit": "bytes",
            },
        },
        "inventory": {"members": [], "one_folder_bytes": 5678},
        "package_identity": {"algorithm": "sha256", "value": identity},
        "schema": "mclab.desktop-package.v1",
        "source": {
            "platform": {"system": startup._RUNNER_SYSTEM[selected_os]},
            "source_commit": workflow_sha,
            "source_dirty": False,
        },
        "unsigned_marker": {},
    }


def _passing_samples(value: float = 1000.0) -> list[dict[str, object]]:
    return [
        {
            "command": {"passed": True},
            "error_code": "",
            "passed": True,
            "sample": index,
            "startup_ms": value + index,
        }
        for index in range(1, startup.STARTUP_SAMPLES + 1)
    ]


def test_nearest_rank_p95_uses_nineteenth_sorted_sample() -> None:
    values = [float(value) for value in range(20, 0, -1)]
    p95, rank = startup.nearest_rank_percentile(values, 0.95)

    assert rank == 19
    assert p95 == 19.0


@pytest.mark.parametrize("values", ([], [1.0, float("nan")], [1.0, -1.0]))
def test_nearest_rank_rejects_incomplete_or_invalid_values(values: list[float]) -> None:
    with pytest.raises(startup.AuditError):
        startup.nearest_rank_percentile(values, 0.95)


def test_startup_gate_requires_twenty_successes_and_p95_limit() -> None:
    passing = startup.evaluate_startup_samples(_passing_samples(1000.0))
    assert passing["passed"] is True
    assert passing["sample_count"] == 20
    assert passing["rank"] == 19
    assert passing["p95_ms"] == 1019.0

    slow = _passing_samples(4990.0)
    assert startup.evaluate_startup_samples(slow)["passed"] is False
    incomplete = _passing_samples()[:-1]
    assert startup.evaluate_startup_samples(incomplete)["passed"] is False
    failed = _passing_samples()
    failed[4] = {**failed[4], "passed": False, "startup_ms": None}
    assert startup.evaluate_startup_samples(failed)["passed"] is False


def test_startup_metric_is_strict_bounded_and_finite(tmp_path: Path) -> None:
    metric = tmp_path / "metric.json"
    metric.write_text('{"startup_ms":12.5}', encoding="utf-8")
    assert startup.read_startup_metric(metric) == 12.5

    metric.write_text('{"startup_ms":1,"startup_ms":2}', encoding="utf-8")
    with pytest.raises(startup.AuditError, match="startup_metric_json_invalid"):
        startup.read_startup_metric(metric)
    metric.write_text('{"startup_ms":NaN}', encoding="utf-8")
    with pytest.raises(startup.AuditError, match="startup_metric_json_invalid"):
        startup.read_startup_metric(metric)
    metric.write_text('{"startup_ms":1,"extra":true}', encoding="utf-8")
    with pytest.raises(startup.AuditError, match="startup_metric_shape_invalid"):
        startup.read_startup_metric(metric)


def test_startup_metric_rejects_link(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"startup_ms":1}', encoding="utf-8")
    link = tmp_path / "metric.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(startup.AuditError, match="startup_metric_missing_or_unsafe"):
        startup.read_startup_metric(link)


def test_fresh_environment_isolates_state_and_scrubs_injection(tmp_path: Path) -> None:
    metric = tmp_path / "metric.json"
    env = startup.fresh_environment(
        {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "/untrusted",
            "MCLAB_OUTPUT_DIR": "/real-output",
            "MCLAB_STARTUP_SETTINGS_PATH": "/ambient/settings.ini",
            "LD_PRELOAD": "/untrusted.so",
        },
        tmp_path / "state",
        metric_path=metric,
    )
    second_env = startup.fresh_environment(
        {},
        tmp_path / "second-state",
        metric_path=tmp_path / "second-metric.json",
    )

    assert "PYTHONPATH" not in env
    assert "LD_PRELOAD" not in env
    assert env["MCLAB_OUTPUT_DIR"].startswith(os.fspath(tmp_path / "state"))
    assert env["MCLAB_STARTUP_PATH"] == os.fspath(metric)
    assert env["MCLAB_SMOKE_ACTION"] == "startup_probe"
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert env["QT_QUICK_BACKEND"] == "software"
    assert "MCLAB_STARTUP_BEGIN_NS" not in env
    assert Path(env["XDG_CONFIG_HOME"]).is_dir()
    settings_path = Path(env["MCLAB_STARTUP_SETTINGS_PATH"])
    second_settings_path = Path(second_env["MCLAB_STARTUP_SETTINGS_PATH"])
    assert settings_path.is_absolute()
    assert second_settings_path.is_absolute()
    assert settings_path != second_settings_path
    assert settings_path == tmp_path / "state/settings/mclab.ini"
    assert settings_path.parent.is_dir()
    assert second_settings_path.parent.is_dir()
    assert not settings_path.exists()
    assert not second_settings_path.exists()


def test_run_command_bounds_logs_and_stamps_process_start(tmp_path: Path) -> None:
    script = (
        "import os,sys;"
        "sys.stdout.write(os.environ['MCLAB_STARTUP_BEGIN_NS']+'\\n');"
        f"sys.stderr.write('x'*{startup.MAX_CAPTURED_LOG_BYTES + 10})"
    )
    result = startup.run_command(
        Path(sys.executable).resolve(),
        ("-c", script),
        cwd=tmp_path,
        env=os.environ,
        log_root=tmp_path / "logs",
        label="startup-1",
        stamp_startup_begin=True,
    )

    assert result.passed is True
    assert result.stdout.bytes > 0
    assert result.stderr.bytes == startup.MAX_CAPTURED_LOG_BYTES + 10
    assert result.stderr.captured_bytes == startup.MAX_CAPTURED_LOG_BYTES
    assert result.stderr.truncated is True
    stdout = (tmp_path / "logs/startup-1.stdout").read_text(encoding="utf-8").strip()
    assert int(stdout) > 0


def test_run_command_times_out_and_reaps_direct_process(tmp_path: Path) -> None:
    result = startup.run_command(
        Path(sys.executable).resolve(),
        ("-c", "import time; time.sleep(30)"),
        cwd=tmp_path,
        env=os.environ,
        log_root=tmp_path / "logs",
        label="startup-timeout",
        timeout_seconds=0.05,
    )

    assert result.passed is False
    assert result.timed_out is True
    assert result.forced_cleanup is True


def test_verified_package_comparison_binds_subject_gates_and_identity() -> None:
    workflow_sha = "c" * 40
    before = _package_evidence(workflow_sha)
    comparison = startup.compare_verified_packages(
        before,
        json.loads(json.dumps(before)),
        workflow_sha=workflow_sha,
        runner_os=_runner_os(),
    )

    assert comparison["passed"] is True
    assert comparison["package_unchanged_after_startup"] is True
    assert comparison["source_commit_matches_workflow"] is True
    assert comparison["verification_count"] == 2
    assert comparison["package_identity"] == "a" * 64


def test_verified_package_comparison_rejects_mutation_or_weak_gate() -> None:
    workflow_sha = "d" * 40
    before = _package_evidence(workflow_sha)
    after = json.loads(json.dumps(before))
    after["archive"]["size_bytes"] = 1235
    assert (
        startup.compare_verified_packages(
            before,
            after,
            workflow_sha=workflow_sha,
            runner_os=_runner_os(),
        )["passed"]
        is False
    )

    weakened = _package_evidence(workflow_sha)
    weakened["gates"]["archive"]["enforced"] = False
    with pytest.raises(
        startup.AuditError,
        match="package_size_gate_not_enforced_or_passed",
    ):
        startup.compare_verified_packages(
            weakened,
            weakened,
            workflow_sha=workflow_sha,
            runner_os=_runner_os(),
        )


def test_verified_package_comparison_rejects_wrong_workflow_subject() -> None:
    evidence = _package_evidence("e" * 40)
    with pytest.raises(startup.AuditError, match="package_subject_mismatch"):
        startup.compare_verified_packages(
            evidence,
            evidence,
            workflow_sha="f" * 40,
            runner_os=_runner_os(),
        )


def test_audit_runs_twenty_samples_between_package_verifications(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "checkout"
    bundle = checkout / "dist/MCLab"
    package = checkout / "dist/MCLab-package"
    bundle.mkdir(parents=True)
    package.mkdir()
    executable = bundle / ("MCLab.exe" if _runner_os() == "Windows" else "MCLab")
    executable.write_bytes(b"fixture")
    temp_root = tmp_path / "runner-temp"
    temp_root.mkdir()
    workflow_sha = "1" * 40
    evidence = _package_evidence(workflow_sha)
    verification_calls: list[tuple[Path, Path]] = []
    sample_calls: list[int] = []
    sample_settings_paths: list[Path] = []

    def fake_verify(bundle_root: Path, package_root: Path) -> dict[str, object]:
        verification_calls.append((bundle_root, package_root))
        return json.loads(json.dumps(evidence))

    def fake_sample(
        _executable: Path,
        *,
        cwd: Path,
        root: Path,
        index: int,
        inherited_env: dict[str, str],
    ) -> dict[str, object]:
        assert not startup._within(cwd, checkout)
        env = startup.fresh_environment(
            inherited_env,
            root / f"state-{index}",
            metric_path=root / f"startup-{index}.json",
        )
        sample_settings_paths.append(Path(env["MCLAB_STARTUP_SETTINGS_PATH"]))
        sample_calls.append(index)
        return _passing_samples(1000.0)[index - 1]

    monkeypatch.setattr(startup, "ROOT", checkout)
    monkeypatch.setattr(startup.build_desktop, "verify_package", fake_verify)
    monkeypatch.setattr(startup, "run_startup_sample", fake_sample)
    result = startup.PackageStartupAudit(
        bundle_root=bundle,
        package_root=package,
        runner_os=_runner_os(),
        workflow_sha=workflow_sha,
        temp_root=temp_root,
        inherited_env={},
    ).run()

    assert result["overall_pass"] is True
    assert result["required_check_contexts"] == list(startup.REQUIRED_CHECK_CONTEXTS)
    assert result["environment"]["fresh_settings_per_sample"] is True
    assert result["environment"]["settings_format"] == "explicit-ini"
    assert result["environment"]["settings_fallbacks_enabled"] is False
    assert (
        result["environment"]["settings_isolation_status"]
        == "verified-by-startup-processes"
    )
    assert sample_calls == list(range(1, 21))
    assert len(sample_settings_paths) == startup.STARTUP_SAMPLES
    assert len(set(sample_settings_paths)) == startup.STARTUP_SAMPLES
    assert all(path.is_absolute() for path in sample_settings_paths)
    assert verification_calls == [(bundle, package), (bundle, package)]
    assert result["checks"]["package"]["verification_count"] == 2


def test_audit_does_not_launch_an_unauthenticated_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "checkout"
    bundle = checkout / "dist/MCLab"
    package = checkout / "dist/MCLab-package"
    bundle.mkdir(parents=True)
    package.mkdir()
    temp_root = tmp_path / "runner-temp"
    temp_root.mkdir()

    monkeypatch.setattr(startup, "ROOT", checkout)
    monkeypatch.setattr(
        startup.build_desktop,
        "verify_package",
        lambda *_args: (_ for _ in ()).throw(
            startup.build_desktop.PackageValidationError("raw path must not escape")
        ),
    )
    result = startup.PackageStartupAudit(
        bundle_root=bundle,
        package_root=package,
        runner_os=_runner_os(),
        workflow_sha="2" * 40,
        temp_root=temp_root,
        inherited_env={},
    ).run()

    assert result["overall_pass"] is False
    assert result["checks"]["package"]["error_code"] == "package_pre_verification_failed"
    assert result["checks"]["startup"]["sample_count"] == 0
    assert result["environment"]["fresh_settings_per_sample"] is False
    assert result["environment"]["settings_isolation_status"] == "not-verified"
    assert result["environment"]["settings_format"] is None
    assert result["environment"]["settings_fallbacks_enabled"] is None
    assert "raw path" not in startup.canonical_json_bytes(result).decode("utf-8")


def test_main_persists_initial_fail_closed_evidence_before_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    workflow_sha = "3" * 40
    relative_output = (
        Path("build")
        / "validation"
        / workflow_sha
        / f"pkg-{_runner_os()}"
        / "package_startup.json"
    )
    observed_initial: dict[str, object] = {}

    class FailingAudit:
        def __init__(self, **_kwargs: object) -> None:
            nonlocal observed_initial
            observed_initial = json.loads(
                (checkout / relative_output).read_text(encoding="utf-8")
            )

        def run(self) -> dict[str, object]:
            raise RuntimeError("must not be copied into evidence")

    monkeypatch.setattr(startup, "ROOT", checkout)
    monkeypatch.setattr(startup, "PackageStartupAudit", FailingAudit)
    result = startup.main(
        [
            "--bundle-root",
            "dist/MCLab",
            "--package-root",
            "dist/MCLab-package",
            "--runner-os",
            _runner_os(),
            "--workflow-sha",
            workflow_sha,
            "--temp-root",
            os.fspath(runner_temp),
            "--output",
            os.fspath(relative_output),
        ]
    )

    assert result == 1
    assert (
        observed_initial["checks"]["harness"]["error_code"]
        == "audit_incomplete_or_interrupted"
    )
    final_bytes = (checkout / relative_output).read_bytes()
    final = json.loads(final_bytes)
    assert final["checks"]["harness"]["error_code"] == "unexpected_runtimeerror"
    assert final["environment"]["fresh_settings_per_sample"] is False
    assert final["environment"]["settings_isolation_status"] == "not-verified"
    assert final["environment"]["settings_format"] is None
    assert final["environment"]["settings_fallbacks_enabled"] is None
    assert "must not be copied" not in final_bytes.decode("utf-8")
    assert final_bytes == startup.canonical_json_bytes(final)
    assert len(final_bytes) <= startup.MAX_EVIDENCE_BYTES


def test_evidence_writer_rejects_absolute_strings_and_output_links(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    with pytest.raises(startup.AuditError, match="absolute_path_in_evidence"):
        startup.write_canonical_json(output, {"path": "/private/value"})

    expected = hashlib.sha256(b"safe").hexdigest()
    target = tmp_path / "target.json"
    target.write_text("safe", encoding="utf-8")
    try:
        output.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(startup.AuditError, match="evidence_target_unsafe"):
        startup.write_canonical_json(output, {"sha256": expected})
