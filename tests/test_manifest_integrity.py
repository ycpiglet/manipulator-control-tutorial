from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mclab.application.artifacts import verify_manifest, write_manifest
from mclab.output_safety import CleanupOperationError, MAX_METADATA_BYTES


def _write_crafted_manifest(output: Path, artifacts: dict[str, str]) -> None:
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenario_id": "lab01.default",
                "status": "completed",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )


def test_verify_manifest_rejects_windows_drive_qualified_artifact_paths(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run"
    output.mkdir()
    digest = hashlib.sha256(b"outside").hexdigest()
    _write_crafted_manifest(
        output,
        {
            "C:/outside.txt": digest,
            "D:drive-relative.txt": digest,
        },
    )

    errors = verify_manifest(output)

    assert "Unsafe artifact path: C:/outside.txt" in errors
    assert "Unsafe artifact path: D:drive-relative.txt" in errors


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not reliable on Windows CI")
def test_verify_manifest_rejects_artifact_beneath_linked_ancestor(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence = outside / "evidence.png"
    evidence.write_bytes(b"outside evidence")
    output = tmp_path / "run"
    output.mkdir()
    (output / "plots").symlink_to(outside, target_is_directory=True)
    _write_crafted_manifest(
        output,
        {"plots/evidence.png": hashlib.sha256(evidence.read_bytes()).hexdigest()},
    )

    errors = verify_manifest(output)

    assert "Missing artifact: plots/evidence.png" in errors


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not reliable on Windows CI")
def test_write_manifest_does_not_inventory_linked_ancestor(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.png").write_bytes(b"outside evidence")
    output = tmp_path / "run"
    output.mkdir()
    (output / "plots").symlink_to(outside, target_is_directory=True)

    manifest = write_manifest(
        output,
        scenario_id="lab01.default",
        status="completed",
        config={},
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert "plots/evidence.png" not in payload["artifacts"]
    assert verify_manifest(output) == []


def test_terminal_manifest_cannot_be_reopened(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    manifest = write_manifest(
        output,
        scenario_id="lab01.default",
        status="completed",
        config={},
    )
    terminal_bytes = manifest.read_bytes()

    with pytest.raises(RuntimeError, match="terminal manifest is immutable"):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="running",
            config={},
        )
    with pytest.raises(RuntimeError, match="terminal manifest is immutable"):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config={},
        )
    with pytest.raises(RuntimeError, match="terminal manifest is immutable"):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="error",
            config={},
        )

    assert manifest.read_bytes() == terminal_bytes


def test_manifest_rejects_unknown_status_without_publication(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()

    with pytest.raises(RuntimeError, match="Unsupported manifest status"):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="finished",
            config={},
        )

    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("fixture_name", ["valid_replay", "dense_replay"])
def test_desktop_replay_fixture_publishes_terminal_manifest_once(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    pytest.importorskip("PySide6")
    from scripts.audit_desktop_ui import _prepare_fixture

    _prepare_fixture(fixture_name, tmp_path)

    output = tmp_path / "outputs" / fixture_name
    payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["scenario_id"] == "lab01.interactive-pull"
    assert "replay.npz" in payload["artifacts"]
    assert verify_manifest(output) == []


def test_manifest_rejects_payload_larger_than_reader_limit(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()

    with pytest.raises(RuntimeError, match="metadata read limit"):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="running",
            config={"oversized": "x" * MAX_METADATA_BYTES},
        )

    assert not (output / "manifest.json").exists()


def test_manifest_valid_running_to_terminal_lifecycle(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    artifact = output / "log.csv"
    artifact.write_text("time\n0\n", encoding="utf-8")
    started_at = "2026-07-22T00:00:00+00:00"

    first = write_manifest(
        output,
        scenario_id="lab01.default",
        status="running",
        config={"sim_time": 1.0},
        started_at=started_at,
    )
    assert json.loads(first.read_text(encoding="utf-8"))["status"] == "running"

    artifact.write_text("time\n0\n1\n", encoding="utf-8")
    second = write_manifest(
        output,
        scenario_id="lab01.default",
        status="running",
        config={"sim_time": 1.0},
        started_at=started_at,
    )
    assert json.loads(second.read_text(encoding="utf-8"))["status"] == "running"

    terminal = write_manifest(
        output,
        scenario_id="lab01.default",
        status="completed",
        config={"sim_time": 1.0},
        started_at=started_at,
    )
    payload = json.loads(terminal.read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["started_at"] == started_at
    assert payload["artifacts"]["log.csv"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert verify_manifest(output) == []


def test_running_manifest_can_defer_only_report_documents_until_terminal(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "log.csv").write_text("time\n0\n", encoding="utf-8")
    report = output / "report.html"
    worksheet = output / "worksheet.md"
    report.write_text("running report", encoding="utf-8")
    worksheet.write_text("running worksheet", encoding="utf-8")

    manifest = write_manifest(
        output,
        scenario_id="lab01.default",
        status="running",
        config={},
        untrusted_artifacts=("report.html", "worksheet.md"),
    )
    running = json.loads(manifest.read_text(encoding="utf-8"))

    assert "log.csv" in running["artifacts"]
    assert "report.html" not in running["artifacts"]
    assert "worksheet.md" not in running["artifacts"]
    report.write_text("prospective terminal report", encoding="utf-8")
    worksheet.write_text("prospective terminal worksheet", encoding="utf-8")
    assert verify_manifest(output) == []

    terminal = write_manifest(
        output,
        scenario_id="lab01.default",
        status="completed",
        config={},
    )
    completed = json.loads(terminal.read_text(encoding="utf-8"))

    assert {"report.html", "worksheet.md"} <= set(completed["artifacts"])
    assert verify_manifest(output) == []


@pytest.mark.parametrize(
    ("status", "untrusted_artifacts", "message"),
    [
        (
            "completed",
            ("report.html",),
            "Artifact trust may be deferred only by a running manifest",
        ),
        (
            "running",
            ("log.csv",),
            "must defer report.html and worksheet.md together",
        ),
        (
            "running",
            ("report.html",),
            "must defer report.html and worksheet.md together",
        ),
    ],
)
def test_manifest_rejects_unsafe_artifact_trust_deferral(
    tmp_path: Path,
    status: str,
    untrusted_artifacts: tuple[str, ...],
    message: str,
) -> None:
    output = tmp_path / status
    output.mkdir()
    (output / "log.csv").write_text("time\n0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status=status,
            config={},
            untrusted_artifacts=untrusted_artifacts,
        )

    assert not (output / "manifest.json").exists()


def test_manifest_refuses_terminal_marker_published_during_inventory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run"
    output.mkdir()
    manifest = write_manifest(
        output,
        scenario_id="lab01.default",
        status="running",
        config={"sim_time": 1.0},
    )

    def publish_terminal(_root_pin: object) -> dict[str, str]:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["status"] = "completed"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        return {}

    with (
        patch(
            "mclab.application.artifacts._inventory_artifacts_rooted",
            side_effect=publish_terminal,
        ),
        pytest.raises(RuntimeError, match="Manifest changed during publication"),
    ):
        write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
        )

    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "completed"


def test_manifest_reconciles_exact_marker_visible_after_post_commit_error(
    tmp_path: Path,
) -> None:
    output = tmp_path / "run"
    output.mkdir()

    with (
        patch(
            "mclab.application.artifacts.PinnedOutputRoot.assert_transaction_boundaries",
            side_effect=CleanupOperationError("directory sync failed after replace"),
        ),
        patch("mclab.application.artifacts.LOGGER.warning") as warning,
    ):
        manifest = write_manifest(
            output,
            scenario_id="lab01.default",
            status="completed",
            config={"sim_time": 1.0},
        )

    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "completed"
    warning.assert_called_once()
