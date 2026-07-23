from __future__ import annotations

import ctypes
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audit_package_e2e.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "desktop.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("mclab_package_e2e_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def e2e_module():
    return _load_module()


def test_canonical_json_is_compact_sorted_utf8_and_bounded(e2e_module, tmp_path: Path) -> None:
    payload = {"z": "한글", "a": [2, 1]}
    expected = b'{"a":[2,1],"z":"\xed\x95\x9c\xea\xb8\x80"}\n'

    assert e2e_module.canonical_json_bytes(payload) == expected
    output = tmp_path / "evidence.json"
    assert e2e_module.write_canonical_json(output, payload, max_bytes=len(expected)) == len(expected)
    assert output.read_bytes() == expected
    with pytest.raises(e2e_module.AuditError, match="evidence_size_invalid"):
        e2e_module.write_canonical_json(output, payload, max_bytes=len(expected) - 1)
    with pytest.raises(ValueError, match="Out of range float"):
        e2e_module.canonical_json_bytes({"value": math.inf})


def test_absolute_path_guard_checks_mapping_keys_as_well_as_values(e2e_module) -> None:
    with pytest.raises(e2e_module.AuditError, match="absolute_path_in_evidence"):
        e2e_module._assert_no_absolute_strings({"nested": {"/tmp/private": True}})
    with pytest.raises(e2e_module.AuditError, match="absolute_path_in_evidence"):
        e2e_module._assert_no_absolute_strings({"error": "failed at /tmp/private"})
    with pytest.raises(e2e_module.AuditError, match="absolute_path_in_evidence"):
        e2e_module._assert_no_absolute_strings({"nested": {r"C:\private": True}})


@pytest.mark.parametrize(
    "raw",
    [
        b'{"same":1,"same":2}',
        b'{"value":NaN}',
        b"[]",
    ],
)
def test_strict_json_reader_rejects_duplicate_nonfinite_and_nonobject(
    e2e_module, tmp_path: Path, raw: bytes
) -> None:
    path = tmp_path / "probe.json"
    path.write_bytes(raw)

    with pytest.raises(e2e_module.AuditError):
        e2e_module.read_json_mapping(path)


def _cleanup_plan_payload(e2e_module, root: Path, synthetic_run: Path) -> dict[str, object]:
    synthetic_run.mkdir(parents=True, exist_ok=True)
    (synthetic_run / "manifest.json").write_text(
        json.dumps(
            {
                "artifacts": {},
                "config": {"resolved": {}},
                "finished_at": "2026-07-23T01:02:03+00:00",
                "scenario_id": "lab01.default",
                "schema_version": 1,
                "started_at": "2026-07-23T01:02:02+00:00",
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    return e2e_module.build_cleanup_plan(
        root,
        keep=0,
        allowed_root=root,
    ).to_dict()


def test_cleanup_dry_run_requires_exact_plan_and_retains_only_safe_aggregates(
    e2e_module, tmp_path: Path
) -> None:
    cleanup_root = tmp_path / "isolated" / "outputs"
    synthetic_run = cleanup_root / "synthetic-lab01"
    expected_plan = _cleanup_plan_payload(e2e_module, cleanup_root, synthetic_run)
    stdout = tmp_path / "cleanup.stdout"
    stdout.write_text(
        json.dumps(expected_plan),
        encoding="utf-8",
    )

    evidence = e2e_module.evaluate_cleanup_dry_run(
        _successful_command(e2e_module),
        stdout,
        cleanup_root=cleanup_root,
        synthetic_run=synthetic_run,
        expected_plan=expected_plan,
        before_fingerprint="before",
        after_fingerprint="before",
        trash_absent=True,
    )

    assert evidence["passed"] is True
    assert evidence["plan"] == {
        "contract_error_code": "",
        "eligible_count": 1,
        "exact_synthetic_selection": True,
        "retained_count": 0,
        "schema_version": 1,
        "selected_count": 1,
        "skipped_count": 0,
    }
    durable = json.dumps(evidence, sort_keys=True)
    assert str(cleanup_root) not in durable
    private_tokens = {
        expected_plan["plan_id"],
        expected_plan["root_token"],
        expected_plan["eligible"][0]["token"],
    }
    assert all(token not in durable for token in private_tokens)
    assert "stdout_sha256" not in evidence["command"]
    assert "stderr_sha256" not in evidence["command"]
    e2e_module._assert_no_absolute_strings(evidence)


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("empty", "json_size_invalid"),
        ("no-op", "cleanup_plan_selection_invalid"),
    ],
)
def test_cleanup_dry_run_rejects_exit_zero_empty_or_noop_stdout(
    e2e_module,
    tmp_path: Path,
    case: str,
    expected_error: str,
) -> None:
    cleanup_root = tmp_path / "isolated" / "outputs"
    synthetic_run = cleanup_root / "synthetic-lab01"
    expected_plan = _cleanup_plan_payload(e2e_module, cleanup_root, synthetic_run)
    stdout = tmp_path / "cleanup.stdout"
    if case == "empty":
        stdout.write_bytes(b"")
    else:
        payload = json.loads(json.dumps(expected_plan))
        payload["eligible"] = []
        payload["selected"] = []
        stdout.write_text(json.dumps(payload), encoding="utf-8")

    evidence = e2e_module.evaluate_cleanup_dry_run(
        _successful_command(e2e_module),
        stdout,
        cleanup_root=cleanup_root,
        synthetic_run=synthetic_run,
        expected_plan=expected_plan,
        before_fingerprint="unchanged",
        after_fingerprint="unchanged",
        trash_absent=True,
    )

    assert evidence["passed"] is False
    assert evidence["plan"]["contract_error_code"] == expected_error
    assert evidence["tree_unchanged"] is True
    assert evidence["trash_absent"] is True


def test_cleanup_dry_run_rejects_shape_valid_plan_not_bound_to_filesystem(
    e2e_module, tmp_path: Path
) -> None:
    cleanup_root = tmp_path / "isolated" / "outputs"
    synthetic_run = cleanup_root / "synthetic-lab01"
    expected_plan = _cleanup_plan_payload(e2e_module, cleanup_root, synthetic_run)
    fabricated = json.loads(json.dumps(expected_plan))
    fabricated["plan_id"] = "c" * 64
    fabricated["root_token"] = "d" * 64
    fabricated["eligible"][0]["token"] = "e" * 64
    fabricated["selected"][0]["token"] = "e" * 64
    stdout = tmp_path / "cleanup.stdout"
    stdout.write_text(json.dumps(fabricated), encoding="utf-8")

    evidence = e2e_module.evaluate_cleanup_dry_run(
        _successful_command(e2e_module),
        stdout,
        cleanup_root=cleanup_root,
        synthetic_run=synthetic_run,
        expected_plan=expected_plan,
        before_fingerprint="unchanged",
        after_fingerprint="unchanged",
        trash_absent=True,
    )

    assert evidence["passed"] is False
    assert evidence["plan"]["contract_error_code"] == "cleanup_plan_binding_invalid"


def test_scrubbed_environment_is_allowlisted_and_never_records_values(
    e2e_module, tmp_path: Path
) -> None:
    inherited = {
        "PATH": "/trusted/bin",
        "SystemRoot": "C:\\Windows",
        "MCLAB_DATA_DIR": "/real/learner/output",
        "PYTHONPATH": "/injected/source",
        "DYLD_INSERT_LIBRARIES": "/tmp/inject.dylib",
        "SECRET_SENTINEL": "do-not-copy",
    }

    env, evidence = e2e_module.scrubbed_environment(
        inherited,
        tmp_path / "case",
        extra={"MCLAB_SELF_TEST": "1"},
    )

    assert env["PATH"] == "/trusted/bin"
    assert env["SystemRoot"] == "C:\\Windows"
    assert env["MCLAB_SELF_TEST"] == "1"
    assert env["MCLAB_DATA_DIR"] != inherited["MCLAB_DATA_DIR"]
    assert "PYTHONPATH" not in env
    assert "DYLD_INSERT_LIBRARIES" not in env
    assert "SECRET_SENTINEL" not in env
    assert evidence["values_recorded"] is False
    assert evidence["scrubbed_injection_names"] == [
        "DYLD_INSERT_LIBRARIES",
        "MCLAB_DATA_DIR",
        "PYTHONPATH",
    ]
    assert "do-not-copy" not in json.dumps(evidence)
    assert "/real/learner/output" not in json.dumps(evidence)


def _make_source_package(e2e_module, checkout: Path) -> tuple[Path, Path]:
    bundle = checkout / "dist" / e2e_module.build_desktop.BUNDLE_NAME
    package = checkout / "dist" / e2e_module.build_desktop.PACKAGE_DIRECTORY_NAME
    bundle.mkdir(parents=True)
    package.mkdir()
    executable = bundle / "MCLab"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    (bundle / "asset.txt").write_bytes(b"asset")
    (package / "package-metrics.json").write_bytes(b"{}")
    (package / "archive.tar.gz").write_bytes(b"archive")
    return bundle, package


def test_package_copy_uses_exact_dist_layout_and_no_hardlinks(
    e2e_module, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    outside = tmp_path / "outside"
    checkout.mkdir()
    bundle, package = _make_source_package(e2e_module, checkout)

    copied_bundle, copied_package = e2e_module.copy_package_layout(
        bundle,
        package,
        outside,
        checkout_root=checkout,
    )

    assert copied_bundle == outside / "dist" / "MCLab"
    assert copied_package == outside / "dist" / "MCLab-package"
    assert copied_bundle.joinpath("asset.txt").read_bytes() == b"asset"
    assert copied_package.joinpath("archive.tar.gz").read_bytes() == b"archive"
    assert not os.path.samefile(bundle / "asset.txt", copied_bundle / "asset.txt")
    assert not os.path.samefile(package / "archive.tar.gz", copied_package / "archive.tar.gz")


def test_package_copy_rejects_destination_inside_checkout(e2e_module, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    bundle, package = _make_source_package(e2e_module, checkout)

    with pytest.raises(e2e_module.AuditError, match="package_copy_inside_checkout"):
        e2e_module.copy_package_layout(
            bundle,
            package,
            checkout / "copy",
            checkout_root=checkout,
        )


def _directory_symlink(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlink unavailable: {type(exc).__name__}")


def test_package_copy_rejects_lexically_outside_symlink_ancestor_into_checkout(
    e2e_module, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    physical_parent = checkout / "physical-parent"
    physical_parent.mkdir(parents=True)
    bundle, package = _make_source_package(e2e_module, checkout)
    alias = tmp_path / "outside-alias"
    _directory_symlink(physical_parent, alias)

    with pytest.raises(e2e_module.AuditError, match="package_copy_inside_checkout"):
        e2e_module.copy_package_layout(
            bundle,
            package,
            alias / "copy",
            checkout_root=checkout,
        )
    assert not (physical_parent / "copy").exists()


def test_audit_rejects_temp_root_with_symlinked_ancestor_into_checkout(
    e2e_module, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    bundle, package = _make_source_package(e2e_module, checkout)
    physical_temp = checkout / "physical-temp"
    physical_temp.mkdir()
    alias = tmp_path / "outside-alias"
    _directory_symlink(checkout, alias)

    with patch.object(e2e_module, "ROOT", checkout):
        audit = e2e_module.PackageE2EAudit(
            bundle_root=bundle,
            package_root=package,
            runner_os="Linux",
            workflow_sha="a" * 40,
            temp_root=alias / physical_temp.name,
            inherited_env={},
        )
        with pytest.raises(e2e_module.AuditError, match="temp_root_inside_checkout"):
            audit.run()


def test_nearest_rank_p95_for_twenty_samples_is_nineteenth_sorted_value(e2e_module) -> None:
    values = [float(value) for value in range(20, 0, -1)]

    value, rank = e2e_module.nearest_rank_percentile(values, 0.95)

    assert rank == 19
    assert value == 19.0
    with pytest.raises(e2e_module.AuditError, match="percentile_nonfinite"):
        e2e_module.nearest_rank_percentile([1.0, math.nan], 0.95)


def _summary(offset: float = 0.0) -> dict[str, float]:
    return {
        "max_abs_position": 0.1 + offset,
        "final_position": 0.01 + offset,
        "final_velocity": 0.001 + offset,
        "final_total_energy": 0.0001 + offset,
    }


def test_reproducibility_requires_three_equal_configs_metrics_and_zero_hash_errors(
    e2e_module,
) -> None:
    within = 0.5 * e2e_module.REPRO_ABS_TOL
    result = e2e_module.compare_reproducibility(
        [_summary(), _summary(within), _summary(-within)],
        ["a" * 64] * 3,
        [0, 0, 0],
    )

    assert result["passed"] is True
    assert len(result["comparisons"]) == 8
    assert result["hash_error_count"] == 0

    outside = e2e_module.compare_reproducibility(
        [_summary(), _summary(1e-6), _summary()],
        ["a" * 64, "b" * 64, "a" * 64],
        [0, 1, 0],
    )
    assert outside["passed"] is False
    assert outside["config_digest_count"] == 2
    assert outside["hash_error_count"] == 1


def test_descendant_graph_and_creation_marker_prevent_pid_reuse_false_positive(
    e2e_module,
) -> None:
    identity = e2e_module.ProcessIdentity
    snapshot = {
        10: identity(10, 1, "root-start"),
        11: identity(11, 10, "child-start"),
        12: identity(12, 11, "grandchild-start"),
        20: identity(20, 1, "unrelated"),
    }

    descendants = e2e_module.descendant_identities(snapshot, 10)

    assert set(descendants) == {11, 12}
    assert not e2e_module._identity_still_alive(
        identity(11, 10, "child-start"),
        {11: identity(11, 1, "reused-pid")},
    )
    assert e2e_module._identity_still_alive(
        identity(11, 10, "unknown"),
        {11: identity(11, 1, "anything")},
    )
    assert e2e_module._identity_still_alive(
        identity(11, 10, "known-original"),
        {11: identity(11, 1, "unknown")},
    )


def test_process_absence_poll_finishes_when_exact_identity_disappears(e2e_module) -> None:
    identity = e2e_module.ProcessIdentity(41, 1, "start")
    snapshots = [
        {41: identity},
        {41: e2e_module.ProcessIdentity(41, 1, "reused")},
    ]

    with patch.object(e2e_module, "process_snapshot", side_effect=snapshots):
        remaining, elapsed = e2e_module.await_identities_absent(
            {41: identity}, timeout_seconds=1.0
        )

    assert remaining == []
    assert elapsed < 1.0


def test_process_snapshot_acquisition_failures_raise_instead_of_proving_absence(
    e2e_module,
) -> None:
    with patch.object(Path, "iterdir", side_effect=OSError("injected")):
        with pytest.raises(e2e_module.AuditError, match="process_snapshot_failed"):
            e2e_module._linux_process_snapshot()

    failed_ps = subprocess.CompletedProcess([], 1, stdout="", stderr="injected")
    with patch.object(e2e_module.subprocess, "run", return_value=failed_ps):
        with pytest.raises(e2e_module.AuditError, match="process_snapshot_failed"):
            e2e_module._darwin_process_snapshot()


def test_snapshot_failure_makes_observed_settlement_fail_closed(e2e_module) -> None:
    identity = e2e_module.ProcessIdentity(41, 1, "start")
    observed = {(identity.pid, identity.start_marker): identity}
    with (
        patch.object(
            e2e_module,
            "process_snapshot",
            side_effect=e2e_module.AuditError("process_snapshot_failed"),
        ),
        patch.object(e2e_module, "_terminate_identity"),
    ):
        recorded, survivors, _settle, _cleanup, error = (
            e2e_module._settle_observed_processes(observed)
        )

    assert recorded == [identity]
    assert survivors == [identity]
    assert error == "process_snapshot_failed"


def test_process_settlement_continues_discovering_descendants(e2e_module) -> None:
    identity = e2e_module.ProcessIdentity
    observed = {(10, "root"): identity(10, 1, "root")}
    snapshots = [
        {
            10: identity(10, 1, "root"),
            11: identity(11, 10, "child"),
        },
        {
            10: identity(10, 1, "reused"),
            11: identity(11, 1, "reused"),
        },
    ]

    with patch.object(e2e_module, "process_snapshot", side_effect=snapshots):
        remaining, elapsed = e2e_module.await_observed_tree_absent(
            observed,
            timeout_seconds=1.0,
        )

    assert remaining == []
    assert (11, "child") in observed
    assert elapsed < 1.0


class _StuckPopen:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.kill_calls = 0
        self.terminate_calls = 0
        self.wait_calls = 0

    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout: float) -> int:
        self.wait_calls += 1
        raise subprocess.TimeoutExpired(cmd="stuck", timeout=timeout)


def test_observed_command_settles_tree_after_repeated_popen_wait_timeouts(
    e2e_module, tmp_path: Path
) -> None:
    executable = tmp_path / "MCLab"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    process = _StuckPopen(321)
    identity = e2e_module.ProcessIdentity(321, 1, "root-start")
    settle = patch.object(
        e2e_module,
        "await_observed_tree_absent",
        side_effect=[([identity], 0.01), ([], 0.02)],
    )
    terminate_identity = patch.object(e2e_module, "_terminate_identity")

    with (
        patch.object(e2e_module.subprocess, "Popen", return_value=process),
        patch.object(e2e_module, "process_snapshot", return_value={321: identity}),
        settle as settle_mock,
        terminate_identity as terminate_mock,
    ):
        command, lifecycle = e2e_module.run_observed_command(
            executable,
            ["app"],
            cwd=tmp_path,
            env={},
            log_root=tmp_path / "logs",
            label="stuck",
            timeout_seconds=1.0,
        )

    assert command.return_code == -9
    assert command.timed_out is True
    assert command.process_lifecycle_passed is False
    assert command.process_forced_cleanup is True
    assert process.wait_calls == 2
    assert process.kill_calls == 1
    assert settle_mock.call_count == 2
    terminate_mock.assert_called_once_with(identity)
    assert lifecycle["observation_error_code"] == "process_reap_timeout"
    assert lifecycle["forced_cleanup"] is True
    assert lifecycle["post_cleanup_survivor_count"] == 0
    assert lifecycle["passed"] is False


def test_standard_command_fails_when_reaping_requires_forced_identity_cleanup(
    e2e_module, tmp_path: Path
) -> None:
    executable = tmp_path / "MCLab"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    process = _StuckPopen(432)
    identity = e2e_module.ProcessIdentity(432, 1, "root-start")

    with (
        patch.object(e2e_module.subprocess, "Popen", return_value=process),
        patch.object(e2e_module, "process_snapshot", return_value={432: identity}),
        patch.object(
            e2e_module,
            "await_observed_tree_absent",
            side_effect=[([identity], 0.01), ([], 0.02)],
        ),
        patch.object(e2e_module, "_terminate_identity"),
    ):
        command = e2e_module.run_command(
            executable,
            ["doctor", "--json"],
            cwd=tmp_path,
            env={},
            log_root=tmp_path / "logs",
            label="stuck-standard",
            timeout_seconds=1.0,
        )

    assert command.passed is False
    assert command.process_lifecycle_passed is False
    assert command.process_forced_cleanup is True
    assert command.process_orphan_count == 1
    assert command.process_post_cleanup_survivor_count == 0
    assert command.process_observation_error_code == "process_reap_timeout"


def test_lifecycle_probe_settles_tree_after_repeated_popen_wait_timeouts(
    e2e_module, tmp_path: Path
) -> None:
    executable = tmp_path / "MCLab"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    output = tmp_path / "synthetic-course"
    output.mkdir()
    process = _StuckPopen(654)
    identity = e2e_module.ProcessIdentity(654, 1, "root-start")
    integrity = {
        "hash_error_count": 0,
        "manifest_count": 1,
        "passed": True,
        "status_counts": {"stopped": 1},
    }

    with (
        patch.object(e2e_module.subprocess, "Popen", return_value=process),
        patch.object(e2e_module, "process_snapshot", return_value={654: identity}),
        patch.object(
            e2e_module,
            "await_observed_tree_absent",
            side_effect=[([identity], 0.01), ([], 0.02)],
        ) as settle_mock,
        patch.object(e2e_module, "_terminate_identity") as terminate_mock,
        patch.object(e2e_module, "_read_probe_if_ready", return_value=None),
        patch.object(e2e_module, "read_json_mapping", return_value={}),
        patch.object(e2e_module, "validate_probe_payload", return_value=[]),
        patch.object(
            e2e_module,
            "validate_worker_safe_point_payload",
            return_value=None,
        ),
        patch.object(e2e_module, "_safe_output_from_probe", return_value=output),
        patch.object(e2e_module, "verify_manifest_tree", return_value=integrity),
        patch.object(e2e_module, "verify_terminal_batch_output", return_value=[]),
        patch.object(e2e_module, "transient_batch_members", return_value=[]),
        patch.object(e2e_module, "_manifest_status", return_value="stopped"),
    ):
        payload, _metadata = e2e_module.run_lifecycle_probe(
            executable,
            cwd=tmp_path,
            inherited_env={},
            case_root=tmp_path / "lifecycle",
            action="cancel",
        )

    assert process.wait_calls == 2
    assert process.kill_calls == 1
    assert settle_mock.call_count == 2
    terminate_mock.assert_called_once_with(identity)
    assert payload["command"]["return_code"] == -9
    assert payload["command"]["timed_out"] is True
    assert payload["command"]["process_lifecycle_passed"] is False
    assert payload["command"]["process_forced_cleanup"] is True
    assert payload["command"]["passed"] is False
    assert payload["observation_error_code"] == "process_reap_timeout"
    assert payload["forced_cleanup"] is True
    assert payload["post_cleanup_survivor_count"] == 0
    assert payload["passed"] is False


class _ExitedPopen:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    @staticmethod
    def poll() -> int:
        return 0


def _lifecycle_probe_payload(
    e2e_module,
    output: Path,
    *,
    action: str,
    phase: str,
    status: str,
    error_code: str = "",
) -> dict[str, object]:
    return {
        "schema": e2e_module.PROBE_SCHEMA,
        "action": f"batch_probe_{action}",
        "phase": phase,
        "status": status,
        "output": str(output),
        "child_pid": 987,
        "current": 1,
        "total": 5,
        "name": e2e_module.EXPECTED_PROGRESS_NAMES[0],
        "progress": [
            {
                "current": 1,
                "total": 5,
                "name": e2e_module.EXPECTED_PROGRESS_NAMES[0],
                "elapsed_ms": 1.0,
            }
        ],
        "heartbeat_count": 1,
        "max_ui_gap_ms": 100.0,
        "elapsed_seconds": 0.1,
        "cancel_requested": phase == "terminal",
        "settled": phase == "terminal",
        "error_code": error_code,
    }


def _run_lifecycle_failure_fixture(
    e2e_module,
    tmp_path: Path,
    *,
    action: str,
    ready: dict[str, object],
    terminal: dict[str, object],
    ready_during_run: bool = True,
    worker_safe_point_action: str | None = None,
    worker_safe_point_final_action: str | None = None,
    worker_safe_point_present: bool = True,
    settlement: tuple[list[object], list[object], float, float, str] = (
        [],
        [],
        0.1,
        0.0,
        "",
    ),
):
    executable = tmp_path / "MCLab"
    executable.write_bytes(b"executable")
    executable.chmod(0o755)
    root = e2e_module.ProcessIdentity(654, 1, "root-start")
    worker_safe_point = {
        "action": worker_safe_point_action or action,
        "schema": e2e_module.WORKER_SAFE_POINT_SCHEMA,
    }
    worker_safe_point_reads = 0

    def read_probe(path, **_kwargs):
        nonlocal worker_safe_point_reads
        if path.name == "ready.json":
            return ready
        if path.name == ".mclab-worker-safe-point.json":
            if not worker_safe_point_present:
                raise e2e_module.AuditError("json_not_regular")
            worker_safe_point_reads += 1
            if worker_safe_point_reads > 1 and worker_safe_point_final_action:
                return {
                    **worker_safe_point,
                    "action": worker_safe_point_final_action,
                }
            return worker_safe_point
        return terminal

    with (
        patch.object(e2e_module.subprocess, "Popen", return_value=_ExitedPopen(654)),
        patch.object(e2e_module, "process_snapshot", return_value={654: root}),
        patch.object(
            e2e_module,
            "_read_probe_if_ready",
            return_value=ready if ready_during_run else None,
        ),
        patch.object(
            e2e_module,
            "_bounded_reap_process_handle",
            return_value=(0, False, ""),
        ),
        patch.object(
            e2e_module,
            "_settle_observed_processes",
            return_value=settlement,
        ),
        patch.object(e2e_module, "read_json_mapping", side_effect=read_probe),
        patch.object(e2e_module, "_safe_output_from_probe") as safe_output,
        patch.object(e2e_module, "verify_manifest_tree") as verify_integrity,
        patch.object(e2e_module, "verify_terminal_batch_output") as verify_terminal,
    ):
        payload, _metadata = e2e_module.run_lifecycle_probe(
            executable,
            cwd=tmp_path,
            inherited_env={},
            case_root=tmp_path / f"lifecycle-invalid-{action}",
            action=action,
        )
    return payload, safe_output, verify_integrity, verify_terminal


def test_lifecycle_terminal_contract_failure_preserves_only_bounded_diagnostics(
    e2e_module, tmp_path: Path
) -> None:
    output = tmp_path / "private-state" / "outputs" / "course"
    ready = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="ready",
        status="running",
    )
    terminal = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="terminal",
        status="error",
        error_code="batch_failed",
    )
    orphan = e2e_module.ProcessIdentity(987, 654, "child-start")
    payload, safe_output, verify_integrity, verify_terminal = (
        _run_lifecycle_failure_fixture(
            e2e_module,
            tmp_path,
            action="cancel",
            ready=ready,
            terminal=terminal,
            settlement=([orphan], [orphan], 0.1, 0.2, "process_survivor"),
        )
    )

    assert payload["passed"] is False
    assert payload["error_code"] == "probe_status_invalid"
    assert payload["ready_validation_error_code"] == ""
    assert payload["terminal_validation_error_code"] == "probe_status_invalid"
    assert payload["observed_terminal_status"] == "error"
    assert payload["observed_probe_error_code"] == "batch_failed"
    assert payload["checks"]["terminal_probe_contract"] is False
    assert payload["checks"]["worker_safe_point"] is True
    assert payload["worker_safe_point_validation_error_code"] == ""
    assert payload["checks"]["process_containment"] is False
    assert payload["command"]["process_lifecycle_passed"] is False
    assert payload["command"]["process_orphan_count"] == 1
    assert payload["command"]["process_post_cleanup_survivor_count"] == 1
    assert "stdout_sha256" not in payload["command"]
    assert "stderr_sha256" not in payload["command"]
    assert payload["orphan_count"] == 1
    assert payload["post_cleanup_survivor_count"] == 1
    assert payload["observed_process_count"] == 1
    safe_output.assert_not_called()
    verify_integrity.assert_not_called()
    verify_terminal.assert_not_called()
    assert str(output) not in json.dumps(payload, sort_keys=True)
    e2e_module._assert_no_absolute_strings(payload)


def test_lifecycle_ready_contract_failure_is_distinguished_and_skips_outputs(
    e2e_module, tmp_path: Path
) -> None:
    output = tmp_path / "private-state" / "outputs" / "course"
    ready = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="close",
        phase="terminal",
        status="running",
    )
    terminal = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="close",
        phase="terminal",
        status="stopped",
    )
    payload, safe_output, verify_integrity, _verify_terminal = (
        _run_lifecycle_failure_fixture(
            e2e_module,
            tmp_path,
            action="close",
            ready=ready,
            terminal=terminal,
            ready_during_run=False,
        )
    )

    assert payload["passed"] is False
    assert payload["error_code"] == "probe_phase_invalid"
    assert payload["ready_validation_error_code"] == "probe_phase_invalid"
    assert payload["terminal_validation_error_code"] == ""
    assert payload["observed_terminal_status"] == "stopped"
    assert payload["observed_probe_error_code"] == ""
    assert payload["checks"]["ready_probe_contract"] is False
    assert payload["checks"]["terminal_probe_contract"] is True
    assert payload["checks"]["worker_safe_point"] is False
    assert payload["worker_safe_point_validation_error_code"] == ""
    assert payload["checks"]["process_containment"] is True
    assert payload["orphan_count"] == 0
    assert payload["post_cleanup_survivor_count"] == 0
    safe_output.assert_not_called()
    verify_integrity.assert_not_called()
    e2e_module._assert_no_absolute_strings(payload)


@pytest.mark.parametrize(
    ("worker_safe_point_present", "worker_safe_point_action", "expected_error"),
    [
        (False, None, "worker_safe_point_read_invalid"),
        (True, "close", "worker_safe_point_action_invalid"),
    ],
)
def test_lifecycle_ready_without_exact_worker_safe_point_never_sends_request(
    e2e_module,
    tmp_path: Path,
    worker_safe_point_present: bool,
    worker_safe_point_action: str | None,
    expected_error: str,
) -> None:
    output = tmp_path / "private-state" / "outputs" / "course"
    ready = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="ready",
        status="running",
    )
    terminal = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="terminal",
        status="stopped",
    )
    payload, safe_output, verify_integrity, verify_terminal = (
        _run_lifecycle_failure_fixture(
            e2e_module,
            tmp_path,
            action="cancel",
            ready=ready,
            terminal=terminal,
            worker_safe_point_action=worker_safe_point_action,
            worker_safe_point_present=worker_safe_point_present,
        )
    )

    request = tmp_path / "lifecycle-invalid-cancel" / "request.json"
    assert not request.exists()
    assert payload["passed"] is False
    assert payload["error_code"] == expected_error
    assert payload["worker_safe_point_validation_error_code"] == expected_error
    assert payload["checks"]["authenticated_ready"] is False
    assert payload["checks"]["worker_safe_point"] is False
    safe_output.assert_not_called()
    verify_integrity.assert_not_called()
    verify_terminal.assert_not_called()
    e2e_module._assert_no_absolute_strings(payload)


def test_lifecycle_worker_safe_point_final_reread_fails_closed(
    e2e_module,
    tmp_path: Path,
) -> None:
    output = tmp_path / "private-state" / "outputs" / "course"
    ready = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="ready",
        status="running",
    )
    terminal = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="terminal",
        status="stopped",
    )
    payload, safe_output, verify_integrity, verify_terminal = (
        _run_lifecycle_failure_fixture(
            e2e_module,
            tmp_path,
            action="cancel",
            ready=ready,
            terminal=terminal,
            worker_safe_point_final_action="close",
        )
    )

    request = tmp_path / "lifecycle-invalid-cancel" / "request.json"
    assert json.loads(request.read_text(encoding="utf-8")) == {
        "action": "cancel",
        "schema": e2e_module.REQUEST_SCHEMA,
    }
    assert payload["passed"] is False
    assert payload["error_code"] == "worker_safe_point_action_invalid"
    assert (
        payload["worker_safe_point_validation_error_code"]
        == "worker_safe_point_action_invalid"
    )
    assert payload["checks"]["authenticated_ready"] is False
    assert payload["checks"]["worker_safe_point"] is False
    safe_output.assert_not_called()
    verify_integrity.assert_not_called()
    verify_terminal.assert_not_called()
    e2e_module._assert_no_absolute_strings(payload)


def test_lifecycle_failure_does_not_echo_unrecognized_probe_enums(
    e2e_module, tmp_path: Path
) -> None:
    output = tmp_path / "private-state" / "outputs" / "course"
    ready = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="ready",
        status="running",
    )
    terminal = _lifecycle_probe_payload(
        e2e_module,
        output,
        action="cancel",
        phase="terminal",
        status="/private/status",
        error_code=r"C:\private\detail",
    )
    payload, *_mocks = _run_lifecycle_failure_fixture(
        e2e_module,
        tmp_path,
        action="cancel",
        ready=ready,
        terminal=terminal,
    )

    assert payload["observed_terminal_status"] is None
    assert payload["observed_probe_error_code"] is None
    durable = json.dumps(payload, sort_keys=True)
    assert "/private/status" not in durable
    assert r"C:\private\detail" not in durable
    e2e_module._assert_no_absolute_strings(payload)


def test_package_audit_retains_bounded_lifecycle_failure_payload(
    e2e_module, tmp_path: Path
) -> None:
    payload = {
        "command": {"process_lifecycle_passed": True},
        "error_code": "probe_status_invalid",
        "observed_probe_error_code": "batch_failed",
        "observed_terminal_status": "error",
        "orphan_count": 0,
        "passed": False,
        "post_cleanup_survivor_count": 0,
        "ready_validation_error_code": "",
        "terminal_validation_error_code": "probe_status_invalid",
        "worker_safe_point_validation_error_code": "",
    }
    metadata = {
        "passed_inherited_names": [],
        "policy": "allowlist-v1",
        "scrubbed_injection_names": [],
        "values_recorded": False,
    }
    audit = e2e_module.PackageE2EAudit(
        bundle_root=tmp_path / "bundle",
        package_root=tmp_path / "package",
        runner_os="Linux",
        workflow_sha="a" * 40,
        temp_root=tmp_path,
        inherited_env={},
    )

    with patch.object(
        e2e_module,
        "run_lifecycle_probe",
        return_value=(payload, metadata),
    ):
        audit._lifecycle_check(
            tmp_path / "MCLab",
            tmp_path,
            tmp_path / "case",
            "cancel",
        )

    assert audit.checks["batch_cancel"] == payload
    assert audit.environment_records == [metadata]
    e2e_module._assert_no_absolute_strings(audit.checks["batch_cancel"])


def _course_fixture(e2e_module, tmp_path: Path) -> tuple[Path, dict[str, object]]:
    allowed = tmp_path / "state" / "data" / "outputs"
    output = allowed / "course"
    output.mkdir(parents=True)
    (output / "summary.json").write_text(
        json.dumps({"child_batches": 5, "scenario_runs": 54}), encoding="utf-8"
    )
    (output / "manifest.json").write_text(
        json.dumps({"scenario_id": "batch.all", "status": "completed"}), encoding="utf-8"
    )
    (output / "report.html").write_text("course", encoding="utf-8")
    pngs: list[Path] = []
    for index in range(5):
        child = output / f"batch-{index}"
        plots = child / "comparison_plots"
        plots.mkdir(parents=True)
        (child / "report.html").write_text("batch", encoding="utf-8")
        png = plots / f"plot-{index}.png"
        png.write_bytes(b"png")
        pngs.append(png)
    probe: dict[str, object] = {
        "action": "batch_probe_complete",
        "cancel_requested": False,
        "child_pid": 4321,
        "current": 5,
        "elapsed_seconds": 299.0,
        "error_code": "",
        "heartbeat_count": 10,
        "max_ui_gap_ms": 500.0,
        "name": e2e_module.EXPECTED_PROGRESS_NAMES[-1],
        "output": str(output),
        "phase": "terminal",
        "progress": [
            {
                "current": index,
                "elapsed_ms": float(index),
                "total": 5,
                "name": name,
            }
            for index, name in enumerate(e2e_module.EXPECTED_PROGRESS_NAMES, start=1)
        ],
        "schema": e2e_module.PROBE_SCHEMA,
        "settled": True,
        "status": "completed",
        "total": 5,
    }
    return output, probe


def _successful_command(e2e_module):
    return e2e_module.CommandResult(
        return_code=0,
        duration_ms=1.0,
        timed_out=False,
        stdout_bytes=0,
        stderr_bytes=0,
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
    )


def test_course_evaluator_enforces_exact_counts_progress_time_ui_size_and_integrity(
    e2e_module, tmp_path: Path
) -> None:
    output, probe = _course_fixture(e2e_module, tmp_path)
    real_tree_members = e2e_module._tree_members

    def bounded_tree(path: Path):
        files, _size = real_tree_members(path)
        return files, 150 * e2e_module.MIB

    with (
        patch.object(e2e_module, "_tree_members", side_effect=bounded_tree),
        patch.object(
            e2e_module,
            "verify_manifest_tree",
            return_value={
                "hash_error_count": 0,
                "manifest_count": 60,
                "passed": True,
                "status_counts": {"completed": 60},
            },
        ),
        patch.object(e2e_module, "verify_terminal_batch_output", return_value=[]),
        patch.object(e2e_module, "transient_batch_members", return_value=[]),
    ):
        result = e2e_module.evaluate_course_output(
            output,
            probe,
            _successful_command(e2e_module),
            allowed_root=output.parent,
        )

    assert result["passed"] is True
    assert result["course_report_count"] == 6
    assert result["comparison_plot_count"] == 5
    assert result["manifest_count"] == 60
    assert result["output_bytes"] == 150 * e2e_module.MIB
    assert result["checks"]["strict_terminal"] is True


def test_course_evaluator_does_not_relax_thresholds(e2e_module, tmp_path: Path) -> None:
    output, probe = _course_fixture(e2e_module, tmp_path)
    probe["elapsed_seconds"] = 300.000001
    probe["max_ui_gap_ms"] = 500.000001
    with (
        patch.object(
            e2e_module,
            "_tree_members",
            return_value=(list(output.rglob("*.png")), 150 * e2e_module.MIB + 1),
        ),
        patch.object(
            e2e_module,
            "verify_manifest_tree",
            return_value={
                "hash_error_count": 0,
                "manifest_count": 59,
                "passed": True,
                "status_counts": {"completed": 58, "running": 1},
            },
        ),
        patch.object(
            e2e_module,
            "verify_terminal_batch_output",
            return_value=["Unlisted artifact: late.txt"],
        ),
        patch.object(e2e_module, "transient_batch_members", return_value=["active"]),
    ):
        result = e2e_module.evaluate_course_output(
            output,
            probe,
            _successful_command(e2e_module),
            allowed_root=output.parent,
        )

    assert result["passed"] is False
    assert result["checks"]["within_timeout"] is False
    assert result["checks"]["ui_heartbeat"] is False
    assert result["checks"]["output_size"] is False
    assert result["checks"]["artifact_integrity"] is False
    assert result["checks"]["strict_terminal"] is False
    assert result["checks"]["transient_cleanup"] is False


def test_course_evaluator_rejects_any_noncompleted_manifest_status(
    e2e_module, tmp_path: Path
) -> None:
    output, probe = _course_fixture(e2e_module, tmp_path)
    with (
        patch.object(
            e2e_module,
            "verify_manifest_tree",
            return_value={
                "hash_error_count": 0,
                "manifest_count": 60,
                "passed": True,
                "status_counts": {"completed": 59, "running": 1},
            },
        ),
        patch.object(e2e_module, "verify_terminal_batch_output", return_value=[]),
        patch.object(e2e_module, "transient_batch_members", return_value=[]),
    ):
        result = e2e_module.evaluate_course_output(
            output,
            probe,
            _successful_command(e2e_module),
            allowed_root=output.parent,
        )

    assert result["checks"]["artifact_integrity"] is False
    assert result["status_counts"] == {"completed": 59, "running": 1}


def test_empty_batch_active_directory_is_detected_as_terminal_transient(
    e2e_module, tmp_path: Path
) -> None:
    output = tmp_path / "course"
    (output / ".mclab-batch-active").mkdir(parents=True)

    assert e2e_module.transient_batch_members(output) == [".mclab-batch-active"]


def test_evidence_rejects_absolute_posix_and_windows_paths(e2e_module) -> None:
    with pytest.raises(e2e_module.AuditError, match="absolute_path_in_evidence"):
        e2e_module._assert_no_absolute_strings({"path": "/tmp/private"})
    with pytest.raises(e2e_module.AuditError, match="absolute_path_in_evidence"):
        e2e_module._assert_no_absolute_strings({"path": "C:\\Users\\name"})


def test_failure_evidence_has_closed_top_level_shape_and_no_raw_error(e2e_module) -> None:
    evidence = e2e_module._failure_evidence(
        runner_os="Linux",
        workflow_sha="a" * 40,
        error_code="package_verification_failed",
    )

    assert set(evidence) == {
        "artifact_class",
        "checks",
        "environment",
        "generated_at",
        "overall_pass",
        "platform",
        "required_check_contexts",
        "schema",
        "subject",
        "thresholds",
    }
    assert evidence["schema"] == "mclab.package-e2e.v1"
    assert evidence["overall_pass"] is False
    assert evidence["checks"]["harness"] == {
        "error_code": "package_verification_failed",
        "passed": False,
    }
    e2e_module._assert_no_absolute_strings(evidence)


def test_evidence_output_is_fixed_below_commit_and_runner_os(e2e_module, tmp_path: Path) -> None:
    commit = "b" * 40
    valid = tmp_path / "build" / "validation" / commit / "g2-Linux" / "package_e2e.json"
    with patch.object(e2e_module, "ROOT", tmp_path):
        assert e2e_module._validate_output_path(valid, commit, "Linux") == valid
        with pytest.raises(e2e_module.AuditError, match="evidence_output_path_invalid"):
            e2e_module._validate_output_path(tmp_path / "elsewhere.json", commit, "Linux")


def test_invalid_workflow_sha_is_rejected_before_any_evidence_write(
    e2e_module, tmp_path: Path
) -> None:
    invalid_sha = "../../outside"
    target = (
        tmp_path
        / "build"
        / "validation"
        / invalid_sha
        / "g2-Linux"
        / "package_e2e.json"
    )
    with (
        patch.object(e2e_module, "ROOT", tmp_path),
        pytest.raises(e2e_module.AuditError, match="workflow_sha_invalid"),
    ):
        e2e_module._validate_output_path(target, invalid_sha, "Linux")

    with patch.object(e2e_module, "ROOT", tmp_path):
        result = e2e_module.main(
            [
                "--bundle-root",
                "dist/MCLab",
                "--package-root",
                "dist/MCLab-package",
                "--runner-os",
                "Linux",
                "--workflow-sha",
                invalid_sha,
                "--temp-root",
                str(tmp_path),
                "--output",
                str(target),
            ]
        )
    assert result == 2
    assert not target.exists()


def test_invalid_output_path_is_rejected_without_writing_failure_evidence(
    e2e_module, tmp_path: Path
) -> None:
    target = tmp_path / "attacker-selected" / "package_e2e.json"
    with patch.object(e2e_module, "ROOT", tmp_path):
        result = e2e_module.main(
            [
                "--bundle-root",
                "dist/MCLab",
                "--package-root",
                "dist/MCLab-package",
                "--runner-os",
                "Linux",
                "--workflow-sha",
                "a" * 40,
                "--temp-root",
                str(tmp_path),
                "--output",
                str(target),
            ]
        )

    assert result == 2
    assert not target.exists()


def test_probe_environment_and_contract_require_separate_authenticated_ready_file(
    e2e_module, tmp_path: Path
) -> None:
    probe = tmp_path / "probe.json"
    ready = tmp_path / "ready.json"
    request = tmp_path / "request.json"
    env, _metadata = e2e_module._probe_base_environment(
        {"PATH": os.environ.get("PATH", "")},
        tmp_path / "state",
        action="batch_probe_cancel",
        probe_path=probe,
        ready_path=ready,
        request_path=request,
        auto_quit_ms=90_000,
    )

    assert env["MCLAB_BATCH_PROBE_PATH"] == str(probe)
    assert env["MCLAB_BATCH_READY_PATH"] == str(ready)
    assert env["MCLAB_BATCH_REQUEST_PATH"] == str(request)

    output = tmp_path / "state" / "data" / "outputs" / "course"
    payload = {
        "schema": e2e_module.PROBE_SCHEMA,
        "action": "batch_probe_cancel",
        "phase": "ready",
        "status": "running",
        "output": str(output),
        "child_pid": 123,
        "current": 1,
        "total": 5,
        "name": e2e_module.EXPECTED_PROGRESS_NAMES[0],
        "progress": [
            {
                "current": 1,
                "total": 5,
                "name": e2e_module.EXPECTED_PROGRESS_NAMES[0],
                "elapsed_ms": 1.0,
            }
        ],
        "heartbeat_count": 1,
        "max_ui_gap_ms": 100.0,
        "elapsed_seconds": 0.1,
        "cancel_requested": False,
        "settled": False,
        "error_code": "",
    }
    assert e2e_module.validate_probe_payload(
        payload,
        action="batch_probe_cancel",
        phase="ready",
        status="running",
    )[0]["current"] == 1
    with pytest.raises(e2e_module.AuditError, match="probe_keys_invalid"):
        e2e_module.validate_probe_payload(
            {**payload, "unexpected": True},
            action="batch_probe_cancel",
            phase="ready",
            status="running",
        )
    for field, code in (
        ("schema", "probe_schema_invalid"),
        ("action", "probe_action_invalid"),
        ("phase", "probe_phase_invalid"),
        ("status", "probe_status_invalid"),
    ):
        with pytest.raises(e2e_module.AuditError, match=code):
            e2e_module.validate_probe_payload(
                {**payload, field: "mismatch"},
                action="batch_probe_cancel",
                phase="ready",
                status="running",
            )

    worker_safe_point = {
        "action": "cancel",
        "schema": e2e_module.WORKER_SAFE_POINT_SCHEMA,
    }
    e2e_module.validate_worker_safe_point_payload(
        worker_safe_point,
        action="cancel",
    )
    for invalid, code in (
        (
            {**worker_safe_point, "unexpected": True},
            "worker_safe_point_keys_invalid",
        ),
        (
            {**worker_safe_point, "schema": "mismatch"},
            "worker_safe_point_schema_invalid",
        ),
        (
            {**worker_safe_point, "action": "close"},
            "worker_safe_point_action_invalid",
        ),
    ):
        with pytest.raises(e2e_module.AuditError, match=code):
            e2e_module.validate_worker_safe_point_payload(
                invalid,
                action="cancel",
            )


def test_windows_process_api_declares_pointer_safe_signatures(e2e_module) -> None:
    class FakeFunction:
        def __init__(self) -> None:
            self.argtypes = None
            self.restype = None

        def __call__(self, *_args):
            return 0

    class FakeKernel32:
        CreateToolhelp32Snapshot = FakeFunction()
        OpenProcess = FakeFunction()
        GetProcessTimes = FakeFunction()
        TerminateProcess = FakeFunction()
        CloseHandle = FakeFunction()
        Process32FirstW = FakeFunction()
        Process32NextW = FakeFunction()

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("pid", ctypes.c_ulong)]

    kernel32 = FakeKernel32()
    e2e_module._configure_windows_process_api(kernel32, ProcessEntry)

    assert kernel32.CreateToolhelp32Snapshot.argtypes is not None
    assert kernel32.CreateToolhelp32Snapshot.restype is not None
    assert kernel32.OpenProcess.argtypes is not None
    assert kernel32.OpenProcess.restype is not None
    assert kernel32.GetProcessTimes.argtypes is not None
    assert kernel32.GetProcessTimes.restype is not None
    assert kernel32.TerminateProcess.argtypes is not None
    assert kernel32.TerminateProcess.restype is not None
    assert kernel32.CloseHandle.argtypes is not None
    assert kernel32.CloseHandle.restype is not None
    assert kernel32.Process32FirstW.argtypes is not None
    assert kernel32.Process32NextW.argtypes is not None
    assert not e2e_module._windows_handle_valid(None)
    assert not e2e_module._windows_handle_valid(0)
    assert not e2e_module._windows_handle_valid(ctypes.c_void_p(-1))
    assert e2e_module._windows_handle_valid(ctypes.c_void_p(123))


def test_windows_partial_process_enumeration_fails_closed(e2e_module) -> None:
    class FakeFunction:
        def __init__(self, callback) -> None:
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel32:
        def __init__(self) -> None:
            self.CreateToolhelp32Snapshot = FakeFunction(
                lambda *_args: ctypes.c_void_p(123)
            )
            self.OpenProcess = FakeFunction(lambda *_args: 0)
            self.GetProcessTimes = FakeFunction(lambda *_args: 0)
            self.TerminateProcess = FakeFunction(lambda *_args: 0)
            self.CloseHandle = FakeFunction(lambda *_args: 1)
            self.Process32FirstW = FakeFunction(self.first)
            self.Process32NextW = FakeFunction(lambda *_args: 0)

        @staticmethod
        def first(_snapshot, entry_pointer) -> int:
            entry = entry_pointer._obj
            entry.th32ProcessID = 101
            entry.th32ParentProcessID = 1
            return 1

    kernel32 = FakeKernel32()
    with (
        patch.object(e2e_module, "_windows_process_start_marker", return_value="known"),
        patch.object(e2e_module.ctypes, "set_last_error", create=True),
        patch.object(e2e_module.ctypes, "get_last_error", return_value=5, create=True),
    ):
        with pytest.raises(e2e_module.AuditError, match="process_snapshot_failed"):
            e2e_module._windows_process_snapshot(kernel32)


def test_desktop_workflow_keeps_six_job_names_and_uploads_g2_evidence_for_90_days() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    exact = workflow.index("- name: Verify exact package evidence subject")
    verify = workflow.index("- name: Verify package identity and size evidence")
    e2e = workflow.index("- name: Run packaged E2E readiness gate")
    evidence = workflow.index("- name: Upload packaged E2E readiness evidence")
    package = workflow.index("- name: Upload unsigned development package")

    assert exact < verify < e2e < evidence < package
    assert "name: Unsigned development build (${{ matrix.os }})" in workflow
    assert "os: [windows-2025, ubuntu-24.04, macos-15]" in workflow
    assert "tests/test_batch_lifecycle.py" in workflow
    assert "tests/test_package_e2e.py" in workflow
    assert '"$MCLAB_BUILD_PYTHON" scripts/audit_package_e2e.py' in workflow
    assert (
        "MCLAB_EVIDENCE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}"
        in workflow
    )
    assert "ref: ${{ env.MCLAB_EVIDENCE_SHA }}" in workflow
    assert 'head_sha="$(git rev-parse --verify \'HEAD^{commit}\')"' in workflow
    assert '[[ "$head_sha" != "$MCLAB_EVIDENCE_SHA" ]]' in workflow
    assert '--workflow-sha "$MCLAB_EVIDENCE_SHA"' in workflow[e2e:evidence]
    assert '--output "$MCLAB_E2E_EVIDENCE"' in workflow[e2e:evidence]
    assert (
        "name: mclab-g2-${{ runner.os }}-${{ env.MCLAB_EVIDENCE_SHA }}"
        in workflow[evidence:package]
    )
    assert (
        "path: ${{ env.MCLAB_E2E_EVIDENCE }}"
        in workflow[evidence:package]
    )
    assert '--workflow-sha "$GITHUB_SHA"' not in workflow[e2e:evidence]
    assert "${{ github.sha }}" not in workflow[evidence:package]
    assert "timeout-minutes: 20" in workflow[e2e:evidence]
    assert "retention-days: 90" in workflow[evidence:package]
    assert "retention-days: 7" in workflow[package:]
    assert "if-no-files-found: error" in workflow[evidence:package]
    assert "if: always() && steps.package_e2e.outcome != 'skipped'" in workflow[evidence:package]
    assert (
        "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        in workflow[evidence:package]
    )
