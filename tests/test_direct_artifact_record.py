from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mclab import batch
from mclab.application.artifacts import write_manifest
from mclab.application.repositories import ArtifactRepository
from mclab.output_root import PinnedOutputRoot
from mclab.output_safety import MAX_OUTPUT_ROOT_ENTRIES
from mclab.sim import reporting


def _completed_run(root: Path, name: str, scenario_id: str) -> Path:
    output = root / name
    output.mkdir()
    (output / "summary.json").write_text(
        '{"lab_name":"lab01_msd","config_name":"default"}',
        encoding="utf-8",
    )
    (output / "report.html").write_text("<html></html>", encoding="utf-8")
    (output / "worksheet.md").write_text("# Worksheet\n", encoding="utf-8")
    (output / "config.yaml").write_text("sim_time: 1.0\n", encoding="utf-8")
    (output / "learner_tuned_config.yaml").write_text(
        "sim_time: 2.0\n",
        encoding="utf-8",
    )
    (output / "replay.npz").write_bytes(b"not a valid replay")
    write_manifest(
        output,
        scenario_id=scenario_id,
        status="completed",
        config={"sim_time": 1.0},
    )
    return output


def test_direct_record_matches_full_strict_inventory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        output = _completed_run(root, "run", "lab01.default")
        repository = ArtifactRepository(root)

        direct = repository.get_direct_child(output, validate_replays=True)
        listed = repository.list_runs(validate_replays=True)

    assert direct is not None
    assert listed == (direct,)
    assert not direct.replay_available
    assert direct.replay_reason
    assert direct.rerun_available
    assert direct.tuned_available


def test_direct_record_traverses_only_the_requested_run_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        target = _completed_run(root, "target", "lab01.default")
        _completed_run(root, "sibling", "lab02.default")
        calls: list[tuple[str, ...]] = []
        name_calls: list[tuple[tuple[str, ...], int | None]] = []
        original_tree_size = PinnedOutputRoot.tree_size
        original_list_names = PinnedOutputRoot.list_names

        def tree_size(
            pin: PinnedOutputRoot,
            relative: tuple[str, ...] = (),
            *,
            max_entries: int,
        ) -> int:
            calls.append(relative)
            return original_tree_size(pin, relative, max_entries=max_entries)

        def list_names(
            pin: PinnedOutputRoot,
            relative: tuple[str, ...] = (),
            *,
            max_entries: int | None = None,
        ) -> tuple[str, ...]:
            name_calls.append((relative, max_entries))
            return original_list_names(pin, relative, max_entries=max_entries)

        with (
            patch.object(
                PinnedOutputRoot,
                "tree_size",
                autospec=True,
                side_effect=tree_size,
            ),
            patch.object(
                PinnedOutputRoot,
                "list_names",
                autospec=True,
                side_effect=list_names,
            ),
        ):
            record = ArtifactRepository(root).get_direct_child(target)

    assert record is not None
    assert calls == [("target",)]
    assert name_calls == [((), MAX_OUTPUT_ROOT_ENTRIES)]


def test_direct_record_preserves_the_bounded_root_inventory_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        target = _completed_run(root, "target", "lab01.default")
        _completed_run(root, "sibling", "lab02.default")

        with patch("mclab.application.repositories.MAX_OUTPUT_ROOT_ENTRIES", 1):
            assert ArtifactRepository(root).get_direct_child(target) is None


def test_direct_record_rejects_outside_missing_and_internal_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve() / "outputs"
        root.mkdir()
        internal = _completed_run(root, "_internal", "lab01.default")
        repository = ArtifactRepository(root)

        assert repository.get_direct_child(root) is None
        assert repository.get_direct_child(root / "missing") is None
        assert repository.get_direct_child(root / "nested" / "run") is None
        assert repository.get_direct_child(root.parent / "outside") is None
        assert repository.get_direct_child(internal) is None


@pytest.mark.skipif(os.name == "nt", reason="symlink fixture is POSIX-only")
def test_direct_record_rejects_unreferenced_symlink_in_run_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        output = _completed_run(root, "run", "lab01.default")
        outside = root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (output / "unreferenced-link").symlink_to(outside)

        assert ArtifactRepository(root).get_direct_child(output) is None


@pytest.mark.skipif(os.name == "nt", reason="symlink fixture is POSIX-only")
def test_direct_record_rejects_a_direct_child_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        target = _completed_run(root, "target", "lab01.default")
        alias = root / "alias"
        alias.symlink_to(target, target_is_directory=True)

        assert ArtifactRepository(root).get_direct_child(alias) is None


def test_report_record_lookup_uses_the_strict_direct_child_api() -> None:
    output = Path("/tmp/direct-record-contract/run")
    with patch.object(
        ArtifactRepository,
        "get_direct_child",
        return_value=None,
    ) as get_direct_child:
        assert reporting._report_artifact_record(output) is None
    get_direct_child.assert_called_once_with(output)


def test_batch_record_lookup_uses_the_strict_direct_child_api() -> None:
    output = Path("/tmp/direct-batch-record-contract/run")
    with patch.object(
        ArtifactRepository,
        "get_direct_child",
        return_value=None,
    ) as get_direct_child:
        assert batch._batch_artifact_record(output) is None
    get_direct_child.assert_called_once_with(output)
