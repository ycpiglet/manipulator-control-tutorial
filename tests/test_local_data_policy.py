from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_local_data_policy.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("_test_local_data_policy", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _copy_repository_fixture(destination: Path) -> Path:
    source_manifest = json.loads((ROOT / checker.SOURCE_MANIFEST_PATH).read_text(encoding="utf-8"))
    source_paths = {Path(item["path"]) for item in source_manifest["sources"]}
    controlled = {
        checker.SCHEMA_PATH,
        checker.POLICY_PATH,
        checker.SOURCE_MANIFEST_PATH,
        checker.POLICY_DOC_PATH,
        *checker.REQUIRED_POLICY_LINKS,
        *checker.REQUIRED_DOCUMENT_MARKERS,
        *source_paths,
    }
    for relative in sorted(controlled, key=str):
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


@pytest.fixture(scope="session")
def baseline_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _copy_repository_fixture(tmp_path_factory.mktemp("local-data-policy-baseline"))


@pytest.fixture
def repository(tmp_path: Path, baseline_root: Path) -> Path:
    target = tmp_path / "repository"
    shutil.copytree(baseline_root, target)
    return target


def _errors(root: Path) -> list[str]:
    _policy, metrics, errors = checker.validate_repository(root)
    assert metrics
    return errors


def _policy(root: Path) -> dict[str, object]:
    return json.loads((root / checker.POLICY_PATH).read_text(encoding="utf-8"))


def _write_policy(root: Path, policy: dict[str, object]) -> None:
    (root / checker.POLICY_PATH).write_bytes(checker.canonical_json_bytes(policy))


def _replace(root: Path, relative: Path, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_current_repository_policy_passes() -> None:
    policy, metrics, errors = checker.validate_repository(ROOT)

    assert policy is not None
    assert errors == []
    assert metrics
    assert all(metric.passed for metric in metrics)


def test_temporary_repository_fixture_passes(repository: Path) -> None:
    assert _errors(repository) == []


def test_schema_closes_every_object_contract(repository: Path) -> None:
    schema = json.loads((repository / checker.SCHEMA_PATH).read_text(encoding="utf-8"))
    objects: list[dict[str, object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                objects.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)

    assert objects
    assert all(item.get("additionalProperties") is False for item in objects)


def test_unknown_contract_field_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    policy["undeclared_policy"] = True
    _write_policy(repository, policy)

    assert any("SCHEMA_ADDITIONAL_PROPERTY" in error for error in _errors(repository))


def test_duplicate_json_key_is_rejected(repository: Path) -> None:
    path = repository / checker.POLICY_PATH
    text = path.read_text(encoding="utf-8")
    marker = '  "contract_id": "mclab.local-data.v1",'
    path.write_text(text.replace(marker, f"{marker}\n{marker}", 1), encoding="utf-8")

    assert any("DUPLICATE_JSON_KEY contract_id" in error for error in _errors(repository))


def test_nonfinite_json_number_is_rejected(repository: Path) -> None:
    _replace(repository, checker.POLICY_PATH, '"schema_version": 1', '"schema_version": NaN')

    assert any("NONFINITE_JSON_NUMBER" in error for error in _errors(repository))


def test_noncanonical_contract_is_rejected(repository: Path) -> None:
    path = repository / checker.POLICY_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert "POLICY_NOT_CANONICAL_JSON" in _errors(repository)


def test_schema_change_requires_an_explicit_hash_update(repository: Path) -> None:
    path = repository / checker.SCHEMA_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert any("SCHEMA_SHA256" in error for error in _errors(repository))


def test_cyclic_local_schema_reference_is_a_controlled_diagnostic(repository: Path) -> None:
    path = repository / checker.SCHEMA_PATH
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["properties"]["contract_id"] = {"$ref": "#/$defs/localCycle"}
    schema["$defs"]["localCycle"] = {"$ref": "#/$defs/localCycle"}
    path.write_bytes(checker.canonical_json_bytes(schema))

    assert any("SCHEMA_REFERENCE_CYCLE $.contract_id" in error for error in _errors(repository))


def test_wrong_contract_version_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    policy["schema_version"] = 2
    _write_policy(repository, policy)

    assert any("SCHEMA_CONST $.schema_version" in error for error in _errors(repository))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("scope", "local_first", 1),
        ("lifecycle_controls", "automatic_deletion", 0),
        (None, "schema_version", 1.0),
    ],
)
def test_json_scalar_types_do_not_coerce(
    repository: Path,
    section: str | None,
    field: str,
    value: object,
) -> None:
    policy = _policy(repository)
    target = policy if section is None else policy[section]
    assert isinstance(target, dict)
    target[field] = value
    _write_policy(repository, policy)

    errors = _errors(repository)
    assert any(
        marker in error
        for error in errors
        for marker in ("SCHEMA_TYPE", "SCHEMA_CONST", "CONTRACT_VALUE")
    )


def test_duplicate_and_unsorted_record_ids_are_rejected(repository: Path) -> None:
    policy = _policy(repository)
    records = copy.deepcopy(policy["data_classes"])
    assert isinstance(records, list)
    records[0], records[1] = records[1], records[0]
    records[-1] = copy.deepcopy(records[0])
    policy["data_classes"] = records
    _write_policy(repository, policy)

    errors = _errors(repository)
    assert any("CONTRACT_DUPLICATE_ID" in error for error in errors)
    assert any("CONTRACT_ID_ORDER" in error for error in errors)


def test_platform_storage_location_drift_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    locations = policy["storage_locations"]
    assert isinstance(locations, list)
    windows = next(item for item in locations if item["id"] == "frozen-windows")
    windows["path_template"] = "%APPDATA%/MCLab/outputs"
    _write_policy(repository, policy)

    assert "CONTRACT_VALUE storage_locations" in _errors(repository)


def test_explicit_output_directory_boundary_is_required(repository: Path) -> None:
    policy = _policy(repository)
    locations = policy["storage_locations"]
    assert isinstance(locations, list)
    locations[:] = [item for item in locations if item["id"] != "explicit-run-output-directory"]
    _write_policy(repository, policy)

    assert any("storage_locations" in error for error in _errors(repository))


def test_explicit_output_parent_index_location_is_required(repository: Path) -> None:
    policy = _policy(repository)
    locations = policy["storage_locations"]
    assert isinstance(locations, list)
    locations[:] = [item for item in locations if item["id"] != "explicit-output-parent-index"]
    _write_policy(repository, policy)

    assert any("storage_locations" in error for error in _errors(repository))


def test_standalone_index_output_root_location_is_required(repository: Path) -> None:
    policy = _policy(repository)
    locations = policy["storage_locations"]
    assert isinstance(locations, list)
    locations[:] = [item for item in locations if item["id"] != "standalone-index-output-root"]
    _write_policy(repository, policy)

    assert any("storage_locations" in error for error in _errors(repository))


@pytest.mark.parametrize(
    "location_id",
    [
        "desktop-instance-lock-default",
        "desktop-instance-lock-override",
        "desktop-local-named-pipe-windows",
        "desktop-local-socket-filesystem",
        "desktop-output-directory-override",
        "desktop-output-parent-index",
        "desktop-qsettings-user-preferences",
    ],
)
def test_desktop_coordination_storage_location_is_required(
    repository: Path,
    location_id: str,
) -> None:
    policy = _policy(repository)
    locations = policy["storage_locations"]
    assert isinstance(locations, list)
    locations[:] = [item for item in locations if item["id"] != location_id]
    _write_policy(repository, policy)

    assert any("storage_locations" in error for error in _errors(repository))


def test_qsettings_language_and_tour_preferences_are_machine_inventory() -> None:
    policy = _policy(ROOT)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "desktop-persistent-preferences")

    assert record["artifacts"] == [
        "<Qt-QSettings-UserScope:MCLab/MCLab>:language",
        "<Qt-QSettings-UserScope:MCLab/MCLab>:tourComplete",
    ]
    assert record["status"] == "persistent"


def test_qsettings_preference_class_omission_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    records[:] = [item for item in records if item["id"] != "desktop-persistent-preferences"]
    _write_policy(repository, policy)

    assert any("data_classes" in error for error in _errors(repository))


def test_windows_named_pipe_is_a_machine_readable_transient_artifact() -> None:
    policy = _policy(ROOT)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "transient-application-controls")

    assert r"\\.\pipe\mclab-<lock-path-sha256-prefix>" in record["artifacts"]


@pytest.mark.parametrize(
    "exclusion_id",
    [
        "maintainer-audit-output-roots",
        "qt-activation-probe",
        "qt-screenshot-capture",
        "qt-self-test-traces",
    ],
)
def test_validation_only_sink_exclusion_is_required(
    repository: Path,
    exclusion_id: str,
) -> None:
    policy = _policy(repository)
    exclusions = policy["validation_only_exclusions"]
    assert isinstance(exclusions, list)
    exclusions[:] = [item for item in exclusions if item["id"] != exclusion_id]
    _write_policy(repository, policy)

    assert "CONTRACT_VALUE validation_only_exclusions" in _errors(repository)


def test_validation_only_sink_exclusions_remain_private_and_exact() -> None:
    policy = _policy(ROOT)
    exclusions = policy["validation_only_exclusions"]
    assert isinstance(exclusions, list)

    assert [item["id"] for item in exclusions] == [
        "maintainer-audit-output-roots",
        "qt-activation-probe",
        "qt-screenshot-capture",
        "qt-self-test-traces",
    ]
    assert all(item["may_contain_private_data"] is True for item in exclusions)
    self_test = next(item for item in exclusions if item["id"] == "qt-self-test-traces")
    assert self_test["artifacts"] == [
        "<MCLAB_ACCESSIBILITY_PATH>",
        "<MCLAB_BACKEND_TRACE_PATH>",
        "<MCLAB_FOCUS_TRACE_PATH>",
        "<MCLAB_STARTUP_PATH>",
    ]


def test_explicit_output_path_resolution_matches_documented_source_and_frozen_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mclab import config

    source_root = tmp_path / "source-checkout"
    frozen_parent = tmp_path / "application-data"
    absolute = tmp_path / "absolute-run"
    monkeypatch.setattr(config, "PROJECT_ROOT", source_root)
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)

    assert config.resolve_output_path(absolute) == absolute
    assert config.resolve_output_path("relative-run") == source_root / "relative-run"

    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config, "default_outputs_root", lambda: frozen_parent / "outputs")

    assert config.resolve_output_path(absolute) == absolute
    assert config.resolve_output_path("relative-run") == frozen_parent / "relative-run"


@pytest.mark.parametrize(
    ("platform", "environment_name", "relative_fallback"),
    [
        ("linux", "XDG_DATA_HOME", Path(".local/share/mclab/outputs")),
        ("win32", "LOCALAPPDATA", Path("AppData/Local/MCLab/outputs")),
    ],
)
def test_empty_platform_data_environment_uses_home_fallback(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    environment_name: str,
    relative_fallback: Path,
) -> None:
    from mclab import config

    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "platform", platform)
    monkeypatch.setenv("MCLAB_DATA_DIR", "")
    monkeypatch.setenv(environment_name, "")

    assert config.default_outputs_root() == Path.home() / relative_fallback


@pytest.mark.parametrize("frozen", [False, True])
def test_standalone_index_relative_root_uses_process_cwd_in_source_and_frozen_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frozen: bool,
) -> None:
    from mclab import cli, config

    working_directory = tmp_path / ("frozen-cwd" if frozen else "source-cwd")
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)
    monkeypatch.setattr(config.sys, "frozen", frozen, raising=False)

    assert cli.main(["index", "--output-dir", "arbitrary-review-root"]) == 0

    selected_root = working_directory / "arbitrary-review-root"
    assert {path.name for path in selected_root.iterdir()} == {"index.html"}
    assert not (working_directory / "index.html").exists()


def test_standalone_index_absolute_root_is_the_direct_write_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mclab import cli

    working_directory = tmp_path / "cwd"
    working_directory.mkdir()
    selected_root = tmp_path / "absolute-review-root"
    monkeypatch.chdir(working_directory)

    assert cli.main(["index", "--output-dir", str(selected_root)]) == 0

    assert {path.name for path in selected_root.iterdir()} == {"index.html"}
    assert not (working_directory / "index.html").exists()


def test_standalone_index_rejects_a_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mclab import cli, output_root

    protected = tmp_path / "repository-root"
    protected.mkdir()
    monkeypatch.setattr(output_root, "PROJECT_ROOT", protected)

    with pytest.raises(RuntimeError, match="terminal or unsafe"):
        cli.main(["index", "--output-dir", str(protected)])

    assert not (protected / "index.html").exists()


def test_standalone_index_rejects_a_linked_root(
    tmp_path: Path,
) -> None:
    from mclab import cli

    target = tmp_path / "physical-root"
    target.mkdir()
    selected = tmp_path / "linked-root"
    try:
        selected.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(RuntimeError, match="terminal or unsafe"):
        cli.main(["index", "--output-dir", str(selected)])

    assert not (target / "index.html").exists()


@pytest.mark.parametrize(
    ("data_class_id", "artifact"),
    [
        ("cumulative-index", "<parent-of-explicit---output-dir>/index.html"),
        ("cumulative-index", "<standalone-index---output-dir>/index.html"),
        ("learner-evidence", "<parent-of-explicit---output-dir>/index.html"),
        ("learner-evidence", "outputs/index.html"),
        ("learner-evidence", "outputs/<run>/replay.npz"),
        ("comparison-batch", "outputs/<batch>/batch_summary.json"),
        ("comparison-batch", "outputs/<batch>/comparison_plots/*.png"),
        ("comparison-batch", "outputs/<batch>/<child-run-or-batch>/"),
        ("diagnostic-provenance", "outputs/.mclab-trash/<receipt>/receipt.json"),
        ("cleanup-quarantine-and-receipts", "outputs/.mclab-trash/<receipt>/entries/<run>"),
    ],
)
def test_sensitive_or_derived_artifact_omission_is_rejected(
    repository: Path, data_class_id: str, artifact: str
) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == data_class_id)
    record["artifacts"].remove(artifact)
    _write_policy(repository, policy)

    assert any(f"data_classes.{data_class_id}.artifacts" in error for error in _errors(repository))


@pytest.mark.parametrize(
    ("data_class_id", "artifact"),
    [
        (data_class_id, artifact)
        for data_class_id in ("comparison-batch", "learner-evidence", "saved-run")
        for artifact in (
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
        )
    ],
)
def test_derived_index_copy_is_required(
    repository: Path,
    data_class_id: str,
    artifact: str,
) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == data_class_id)
    record["derived_copies"].remove(artifact)
    _write_policy(repository, policy)

    assert any(
        f"data_classes.{data_class_id}.derived_copies" in error for error in _errors(repository)
    )


def test_data_class_description_drift_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "comparison-batch")
    record["content"] = "ordinary generated files"
    _write_policy(repository, policy)

    assert any("data_classes.comparison-batch.content" in error for error in _errors(repository))


def test_qt_instance_controls_are_private_and_inventory_lock_and_socket_surfaces() -> None:
    policy = _policy(ROOT)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "transient-application-controls")

    assert record["may_contain_private_data"] is True
    assert "PID, hostname, application name, machine ID, and boot ID" in record["content"]
    assert record["artifacts"][:3] == [
        "<MCLAB_INSTANCE_LOCK>",
        "<Qt-AppLocalDataLocation>/mclab-desktop.lock",
        "<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>",
    ]


@pytest.mark.parametrize(
    "artifact",
    [
        "<MCLAB_INSTANCE_LOCK>",
        "<Qt-AppLocalDataLocation>/mclab-desktop.lock",
        "<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>",
    ],
)
def test_qt_instance_control_artifact_omission_is_rejected(
    repository: Path,
    artifact: str,
) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "transient-application-controls")
    record["artifacts"].remove(artifact)
    _write_policy(repository, policy)

    assert any(
        "data_classes.transient-application-controls.artifacts" in error
        for error in _errors(repository)
    )


def test_qt_instance_control_private_classification_drift_is_rejected(repository: Path) -> None:
    policy = _policy(repository)
    records = policy["data_classes"]
    assert isinstance(records, list)
    record = next(item for item in records if item["id"] == "transient-application-controls")
    record["may_contain_private_data"] = False
    _write_policy(repository, policy)

    assert any(
        "data_classes.transient-application-controls.may_contain_private_data" in error
        for error in _errors(repository)
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automatic_deletion", True),
        ("permanent_purge_available", True),
        ("real_output_validation", "passed"),
        ("retention_policy_status", "30-days"),
        ("rpo_rto_status", "24-hours"),
    ],
)
def test_unearned_lifecycle_claim_is_rejected(repository: Path, field: str, value: object) -> None:
    policy = _policy(repository)
    controls = policy["lifecycle_controls"]
    assert isinstance(controls, dict)
    controls[field] = value
    _write_policy(repository, policy)

    assert any(f"lifecycle_controls.{field}" in error for error in _errors(repository))


def test_unresolved_external_decision_cannot_be_silently_closed(repository: Path) -> None:
    policy = _policy(repository)
    decisions = policy["unresolved_decisions"]
    assert isinstance(decisions, list)
    decisions[0]["status"] = "decided"
    _write_policy(repository, policy)

    assert any("unresolved_decisions" in error for error in _errors(repository))


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    [
        (
            Path("src/mclab/config.py"),
            'os.environ.get("MCLAB_DATA_DIR")',
            'os.environ.get("MCLAB_DATA_HOME")',
        ),
        (
            Path("src/mclab/config.py"),
            "if candidate.is_absolute():\n        return candidate\n    if is_frozen_bundle():",
            "if False:\n        return candidate\n    if is_frozen_bundle():",
        ),
        (
            Path("src/mclab/sim/logging.py"),
            'self.output_path / "interaction_events.json"',
            'self.output_path / "private_events.json"',
        ),
        (
            Path("src/mclab/application/qt_evidence.py"),
            "PREDICTION_LIMIT = 240",
            "PREDICTION_LIMIT = 241",
        ),
        (
            Path("src/mclab/application/session.py"),
            "self.recorder.event(time=timestamp, kind=kind, name=name, value=value)",
            "self.recorder.event(time=timestamp, kind=kind, name=name, value=None)",
        ),
        (
            Path("src/mclab/sim/reporting.py"),
            'publication.write_text(("worksheet.md",), worksheet)',
            'publication.write_text(("review.md",), worksheet)',
        ),
        (
            Path("src/mclab/batch.py"),
            '(batch_output / "batch_summary.json").write_text(',
            '(batch_output / "comparison.json").write_text(',
        ),
    ],
)
def test_hash_closed_source_drift_is_rejected(
    repository: Path, relative: Path, old: str, new: str
) -> None:
    _replace(repository, relative, old, new)

    assert any(f"SOURCE_INVENTORY_SHA256 {relative}" in error for error in _errors(repository))


def test_new_python_source_is_rejected(repository: Path) -> None:
    new_source = repository / "src" / "mclab" / "new_persistence_sink.py"
    new_source.write_text(
        "from pathlib import Path\n\n"
        "def write_note(note: str) -> None:\n"
        "    Path('private-note.txt').write_text(note, encoding='utf-8')\n",
        encoding="utf-8",
    )

    assert "SOURCE_INVENTORY_UNDECLARED src/mclab/new_persistence_sink.py" in _errors(repository)


def test_missing_declared_source_is_rejected(repository: Path) -> None:
    missing = repository / "src" / "mclab" / "config.py"
    missing.unlink()

    assert "SOURCE_INVENTORY_MISSING src/mclab/config.py" in _errors(repository)


def test_source_manifest_change_requires_policy_hash_update(repository: Path) -> None:
    path = repository / checker.SOURCE_MANIFEST_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert any("SOURCE_INVENTORY_MANIFEST_SHA256" in error for error in _errors(repository))


def test_unreviewed_remote_client_is_rejected(repository: Path) -> None:
    path = repository / "src" / "mclab" / "__init__.py"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nfrom requests import get\n",
        encoding="utf-8",
    )

    assert any("UNREVIEWED_REMOTE_IMPORT" in error for error in _errors(repository))


def test_source_file_symlink_is_rejected(repository: Path, tmp_path: Path) -> None:
    source = repository / "src" / "mclab" / "config.py"
    target = tmp_path / "outside-config.py"
    shutil.copy2(source, target)
    source.unlink()
    try:
        source.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    assert "SYMLINK_SOURCE_ENTRY src/mclab/config.py" in _errors(repository)


def test_source_directory_symlink_is_rejected(repository: Path, tmp_path: Path) -> None:
    source = repository / "src" / "mclab" / "controllers"
    target = tmp_path / "outside-controllers"
    shutil.copytree(source, target)
    shutil.rmtree(source)
    try:
        source.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    assert "SYMLINK_SOURCE_ENTRY src/mclab/controllers" in _errors(repository)


def test_symlinked_contract_parent_is_rejected(repository: Path, tmp_path: Path) -> None:
    parent = repository / ".agents" / "operations"
    target = tmp_path / "outside-operations"
    shutil.copytree(parent, target)
    shutil.rmtree(parent)
    try:
        parent.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    assert any(
        "SYMLINK_REPOSITORY_DIRECTORY .agents/operations" in error for error in _errors(repository)
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_special_source_file_is_rejected(repository: Path) -> None:
    special = repository / "src" / "mclab" / "special_source.py"
    os.mkfifo(special)

    assert "SPECIAL_SOURCE_ENTRY src/mclab/special_source.py" in _errors(repository)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_special_contract_input_is_rejected_without_opening_it(repository: Path) -> None:
    policy_path = repository / checker.POLICY_PATH
    policy_path.unlink()
    os.mkfifo(policy_path)

    assert any("NON_REGULAR_REPOSITORY_INPUT" in error for error in _errors(repository))


@pytest.mark.skipif(os.name == "nt", reason="POSIX O_NOFOLLOW flag behavior")
def test_controlled_repository_read_opens_every_component_nofollow(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = checker.os.open
    flags_seen: list[int] = []

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        flags_seen.append(flags)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(checker.os, "open", recording_open)

    checker._read_regular_bytes(
        repository,
        checker.POLICY_PATH,
        max_bytes=checker.MAX_CONTRACT_BYTES,
    )

    assert flags_seen
    assert all(flags & os.O_NOFOLLOW for flags in flags_seen)


def test_windows_reparse_attribute_is_detected_independently_of_mode() -> None:
    value = SimpleNamespace(st_file_attributes=checker.WINDOWS_REPARSE_ATTRIBUTE)

    assert checker._is_windows_reparse_point(value)


def test_windows_reparse_parent_attribute_fails_closed_in_repository_walk(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_lstat = checker._entry_lstat

    def reparse_parent_lstat(parent: object, name: str) -> object:
        value = original_lstat(parent, name)
        if name != ".agents":
            return value
        return SimpleNamespace(
            st_ctime_ns=value.st_ctime_ns,
            st_dev=value.st_dev,
            st_file_attributes=checker.WINDOWS_REPARSE_ATTRIBUTE,
            st_ino=value.st_ino,
            st_mode=value.st_mode,
            st_mtime_ns=value.st_mtime_ns,
            st_reparse_tag=0xA0000003,
            st_size=value.st_size,
        )

    monkeypatch.setattr(checker, "_entry_lstat", reparse_parent_lstat)

    assert any("REPARSE_REPOSITORY_DIRECTORY .agents" in error for error in _errors(repository))


def _attempt_directory_swap_and_swap_back(directory: Path, backup: Path) -> list[str]:
    completed: list[str] = []
    try:
        directory.replace(backup)
        completed.append("swap")
        backup.replace(directory)
        completed.append("swap-back")
    except OSError:
        if backup.exists() and not directory.exists():
            backup.replace(directory)
    return completed


@pytest.mark.skipif(os.name != "nt", reason="Windows directory sharing behavior")
def test_windows_repository_ancestor_handle_blocks_swap_and_swap_back(
    repository: Path,
) -> None:
    target = repository / ".agents"
    backup = repository / ".agents-swap"

    with checker._open_directory_chain(repository, Path(".agents/operations")):
        completed = _attempt_directory_swap_and_swap_back(target, backup)

    assert completed == []
    assert target.is_dir()
    assert not backup.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows directory sharing behavior")
def test_windows_source_directory_handle_blocks_swap_and_swap_back(
    repository: Path,
) -> None:
    target = repository / "src" / "mclab" / "controllers"
    backup = repository / "src" / "mclab" / "controllers-swap"

    with checker._open_directory_chain(repository, Path("src/mclab/controllers")):
        completed = _attempt_directory_swap_and_swap_back(target, backup)

    assert completed == []
    assert target.is_dir()
    assert not backup.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_source_junction_is_rejected(repository: Path, tmp_path: Path) -> None:
    source = repository / "src" / "mclab" / "controllers"
    target = tmp_path / "junction-target"
    shutil.copytree(source, target)
    shutil.rmtree(source)
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(source), str(target)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr.strip()}")

    assert "REPARSE_SOURCE_ENTRY src/mclab/controllers" in _errors(repository)


def test_file_replacement_between_check_and_open_is_rejected(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = checker.POLICY_PATH
    candidate = repository / relative
    replacement = tmp_path / "replacement-policy.json"
    replacement.write_bytes(candidate.read_bytes() + b"\n")
    original_open = checker._open_nofollow
    swapped = False

    def racing_open(
        path: Path,
        *,
        directory: bool,
        parent_fd: int | None = None,
        name: str | None = None,
    ) -> int:
        nonlocal swapped
        if not directory and path == candidate and not swapped:
            swapped = True
            candidate.replace(tmp_path / "checked-policy.json")
            shutil.copy2(replacement, candidate)
        return original_open(
            path,
            directory=directory,
            parent_fd=parent_fd,
            name=name,
        )

    monkeypatch.setattr(checker, "_open_nofollow", racing_open)

    with pytest.raises(checker.ContractInputError, match="CHANGED_REPOSITORY_INPUT"):
        checker._read_regular_bytes(repository, relative, max_bytes=checker.MAX_CONTRACT_BYTES)


def test_file_mutation_during_bounded_read_is_rejected(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = checker.POLICY_PATH
    candidate = repository / relative
    original_read = checker.os.read
    mutated = False

    def racing_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        data = original_read(descriptor, size)
        if data and not mutated:
            mutated = True
            with candidate.open("ab") as stream:
                stream.write(b" ")
        return data

    monkeypatch.setattr(checker.os, "read", racing_read)

    with pytest.raises(checker.ContractInputError, match="CHANGED_REPOSITORY_INPUT"):
        checker._read_regular_bytes(repository, relative, max_bytes=checker.MAX_CONTRACT_BYTES)


def test_source_directory_replacement_during_walk_is_rejected(
    repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = repository / "src" / "mclab" / "controllers"
    replacement = tmp_path / "replacement-controllers"
    backup = repository / "src" / "mclab" / "controllers-before-race"
    shutil.copytree(source, replacement)
    original_list = checker._list_directory_names
    swapped = False

    def racing_list(directory: object) -> tuple[str, ...]:
        nonlocal swapped
        names = original_list(directory)
        if directory.path == source and not swapped:
            swapped = True
            source.replace(backup)
            shutil.copytree(replacement, source)
        return names

    monkeypatch.setattr(checker, "_list_directory_names", racing_list)

    assert any(
        "CHANGED_REPOSITORY_DIRECTORY src/mclab/controllers" in error
        for error in _errors(repository)
    )


def test_missing_korean_policy_section_is_rejected(repository: Path) -> None:
    _replace(repository, checker.POLICY_DOC_PATH, "### 한국어", "### Korean section missing")

    assert "POLICY_KOREAN_SECTION_COUNT" in _errors(repository)


def test_critical_policy_language_drift_is_rejected(repository: Path) -> None:
    _replace(
        repository,
        checker.POLICY_DOC_PATH,
        "recoverable quarantine, not deletion or secure erasure",
        "ordinary cleanup",
    )

    assert any("POLICY_REQUIRED_MARKER" in error for error in _errors(repository))


def test_missing_policy_link_is_rejected(repository: Path) -> None:
    path = repository / "README.en.md"
    text = path.read_text(encoding="utf-8")
    assert text.count("docs/local_data_and_privacy.md") >= 1
    path.write_text(
        text.replace("docs/local_data_and_privacy.md", "docs/missing_policy.md"),
        encoding="utf-8",
    )

    assert any("POLICY_LINK_MISSING README.en.md" in error for error in _errors(repository))


def test_support_no_sla_and_sanitization_markers_are_required(repository: Path) -> None:
    _replace(
        repository,
        Path(".github/SUPPORT.md"),
        "no response-time or platform-service SLA is promised",
        "a response-time SLA is available",
    )

    assert any(
        "DOCUMENT_REQUIRED_MARKER .github/SUPPORT.md" in error for error in _errors(repository)
    )


def test_security_policy_cannot_claim_public_release_completeness(repository: Path) -> None:
    _replace(
        repository,
        Path(".github/SECURITY.md"),
        "repository-scoped current inventory",
        "complete inventory",
    )

    assert any(
        "DOCUMENT_REQUIRED_MARKER .github/SECURITY.md" in error for error in _errors(repository)
    )


def test_symlinked_contract_input_is_rejected(repository: Path) -> None:
    policy_path = repository / checker.POLICY_PATH
    target = repository / "policy-target.json"
    shutil.copy2(policy_path, target)
    policy_path.unlink()
    try:
        policy_path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    assert any("SYMLINK_REPOSITORY_INPUT" in error for error in _errors(repository))


def test_oversized_contract_input_is_rejected(repository: Path) -> None:
    (repository / checker.POLICY_PATH).write_bytes(b" " * (checker.MAX_CONTRACT_BYTES + 1))

    assert any("OVERSIZED_REPOSITORY_INPUT" in error for error in _errors(repository))


def test_non_utf8_contract_input_is_rejected(repository: Path) -> None:
    (repository / checker.POLICY_PATH).write_bytes(b"\xff\xfe")

    assert any("NON_UTF8" in error for error in _errors(repository))


def test_checker_cli_exit_contract(capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main([]) == 0
    assert "status: PASS" in capsys.readouterr().out

    assert checker.main(["unexpected"]) == 2
    captured = capsys.readouterr()
    assert "usage: check_local_data_policy.py" in captured.err
