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
