"""Validate the repository-only local-data and privacy contract.

OPS-01A deliberately validates repository sources and temporary test fixtures only.
The checker never opens the configured MCLab outputs root and never performs cleanup.
It uses only the Python standard library so the contract can run before installation.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(".agents/operations/local-data-policy.schema.json")
POLICY_PATH = Path(".agents/operations/local-data-policy.json")
SOURCE_MANIFEST_PATH = Path(".agents/operations/local-data-policy.sources.json")
POLICY_DOC_PATH = Path("docs/local_data_and_privacy.md")
MAX_CONTRACT_BYTES = 256 * 1024
MAX_DOCUMENT_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_REFERENCE_DEPTH = 64
READ_CHUNK_BYTES = 64 * 1024
WINDOWS_REPARSE_ATTRIBUTE = 0x400
OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
STAT_SUPPORTS_NOFOLLOW = os.stat in os.supports_follow_symlinks
LISTDIR_SUPPORTS_FD = os.listdir in os.supports_fd
SCHEMA_SHA256 = "3e880cd7d80ae1168c8ae205a0deddd6f30e2702a9283e34f91aa727e08aa3bb"

POLICY_HEADINGS = (
    "Scope / 범위",
    "Storage locations / 저장 위치",
    "Data inventory / 저장 데이터 목록",
    "Network behavior / 네트워크 동작",
    "Export and copying / 내보내기와 복사",
    "Cleanup, deletion, and restore / 정리·삭제·복원",
    "Shared PCs / 공용 PC",
    "Sharing, support, and security / 공유·지원·보안",
    "Backup, retention, and external decisions / 백업·보존·외부 결정",
    "Validation status and limits / 검증 상태와 한계",
)

EXPECTED_SCOPE = {
    "account_required": False,
    "automatic_learner_data_upload": False,
    "distribution_scope": "supervised-source-development-only",
    "local_first": True,
    "ordinary_run_network_required": False,
    "remote_usage_analytics": False,
    "repository_only": True,
}

EXPECTED_STORAGE_LOCATIONS = (
    {
        "applies_when": "the desktop starts without MCLAB_INSTANCE_LOCK",
        "code_reference": "src/mclab/application/single_instance.py:acquire_instance_lock",
        "id": "desktop-instance-lock-default",
        "parent_source": "Qt AppLocalDataLocation",
        "path_template": "<Qt-AppLocalDataLocation>/mclab-desktop.lock",
        "relative_child": "mclab-desktop.lock",
    },
    {
        "applies_when": "the desktop starts with MCLAB_INSTANCE_LOCK",
        "code_reference": "src/mclab/application/single_instance.py:acquire_instance_lock",
        "id": "desktop-instance-lock-override",
        "parent_source": (
            "the exact override path, with a relative value interpreted from the "
            "process current working directory"
        ),
        "path_template": "<MCLAB_INSTANCE_LOCK>",
        "relative_child": "not-appended",
    },
    {
        "applies_when": "the desktop activation server listens on Windows",
        "code_reference": "src/mclab/application/single_instance.py:start_activation_server",
        "id": "desktop-local-named-pipe-windows",
        "parent_source": "the local Windows named-pipe namespace",
        "path_template": r"\\.\pipe\mclab-<lock-path-sha256-prefix>",
        "relative_child": "derived-local-named-pipe-endpoint",
    },
    {
        "applies_when": (
            "Qt maps the derived QLocalServer name to a filesystem socket entry on a "
            "Unix-like platform"
        ),
        "code_reference": "src/mclab/application/single_instance.py:start_activation_server",
        "id": "desktop-local-socket-filesystem",
        "parent_source": "the Qt local-server runtime or temporary directory",
        "path_template": ("<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>"),
        "relative_child": "derived-local-socket-entry",
    },
    {
        "applies_when": (
            "the desktop starts its first live scenario with a non-empty MCLAB_OUTPUT_DIR"
        ),
        "code_reference": "src/mclab/application/qt_app.py:AppBackend._start_scenario",
        "id": "desktop-output-directory-override",
        "parent_source": (
            "an absolute override selects that exact directory; a relative override resolves "
            "through src/mclab/config.py:resolve_output_path"
        ),
        "path_template": "<MCLAB_OUTPUT_DIR-selected-first-run-directory>",
        "relative_child": "not-appended",
    },
    {
        "applies_when": (
            "that first desktop run reaches terminal publication and its best-effort parent "
            "index refresh succeeds"
        ),
        "code_reference": "src/mclab/sim/reporting.py:write_outputs_index",
        "id": "desktop-output-parent-index",
        "parent_source": "parent directory of the MCLAB_OUTPUT_DIR-selected first run",
        "path_template": ("<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html"),
        "relative_child": "index.html-in-parent",
    },
    {
        "applies_when": (
            "the desktop reads language and tourComplete or writes a changed language or "
            "dismissed-tour value"
        ),
        "code_reference": "src/mclab/application/qt_app.py:AppBackend",
        "id": "desktop-qsettings-user-preferences",
        "parent_source": (
            "Qt native UserScope settings for organization MCLab and application MCLab"
        ),
        "path_template": "<Qt-QSettings-UserScope:MCLab/MCLab>",
        "relative_child": "native-settings-store",
    },
    {
        "applies_when": "MCLAB_DATA_DIR is set for source or frozen execution",
        "code_reference": "src/mclab/config.py:default_outputs_root",
        "id": "environment-override",
        "parent_source": "MCLAB_DATA_DIR",
        "path_template": "<MCLAB_DATA_DIR>/outputs",
        "relative_child": "outputs",
    },
    {
        "applies_when": (
            "a CLI run or batch with --output-dir reaches terminal publication and its "
            "best-effort parent index refresh succeeds"
        ),
        "code_reference": "src/mclab/sim/reporting.py:write_outputs_index",
        "id": "explicit-output-parent-index",
        "parent_source": "parent directory of the user-selected exact output directory",
        "path_template": "<parent-of-explicit---output-dir>/index.html",
        "relative_child": "index.html-in-parent",
    },
    {
        "applies_when": "CLI run or batch receives --output-dir",
        "code_reference": "src/mclab/config.py:resolve_output_path",
        "id": "explicit-run-output-directory",
        "parent_source": (
            "absolute user path, PROJECT_ROOT for a relative source path, or frozen "
            "application-data parent for a relative frozen path"
        ),
        "path_template": "<user-selected-exact-output-directory>",
        "relative_child": "not-appended",
    },
    {
        "applies_when": "running a frozen bundle on Linux without MCLAB_DATA_DIR",
        "code_reference": "src/mclab/config.py:default_outputs_root",
        "id": "frozen-linux",
        "parent_source": "XDG_DATA_HOME or user-home fallback",
        "path_template": "${XDG_DATA_HOME:-$HOME/.local/share}/mclab/outputs",
        "relative_child": "outputs",
    },
    {
        "applies_when": "running a frozen bundle on macOS without MCLAB_DATA_DIR",
        "code_reference": "src/mclab/config.py:default_outputs_root",
        "id": "frozen-macos",
        "parent_source": "user home",
        "path_template": "$HOME/Library/Application Support/MCLab/outputs",
        "relative_child": "outputs",
    },
    {
        "applies_when": "running a frozen bundle on Windows without MCLAB_DATA_DIR",
        "code_reference": "src/mclab/config.py:default_outputs_root",
        "id": "frozen-windows",
        "parent_source": "LOCALAPPDATA or user-home fallback",
        "path_template": "%LOCALAPPDATA%/MCLab/outputs",
        "relative_child": "outputs",
    },
    {
        "applies_when": "running from source without MCLAB_DATA_DIR",
        "code_reference": "src/mclab/config.py:default_outputs_root",
        "id": "source-default",
        "parent_source": "PROJECT_ROOT",
        "path_template": "<repository>/outputs",
        "relative_child": "outputs",
    },
    {
        "applies_when": "python -m mclab index receives --output-dir",
        "code_reference": "src/mclab/cli.py:index",
        "id": "standalone-index-output-root",
        "parent_source": (
            "an absolute or process-current-working-directory-relative caller root that "
            "passes physical-directory, protected-root, mount, and publication safety checks"
        ),
        "path_template": "<standalone-index---output-dir>/index.html",
        "relative_child": "index.html-in-selected-root",
    },
)

EXPECTED_DATA_CLASSES = {
    "cleanup-quarantine-and-receipts": {
        "artifacts": (
            "outputs/.mclab-trash/<receipt>/entries/<run>",
            "outputs/.mclab-trash/<receipt>/receipt.json",
        ),
        "content": (
            "Recoverable copies of complete saved runs plus cleanup root, run-name, "
            "plan, status, and identity metadata."
        ),
        "derived_copies": (),
        "learner_authored": True,
        "may_contain_private_data": True,
        "sharing": "do-not-share-raw",
        "status": "quarantined-recoverable",
    },
    "comparison-batch": {
        "artifacts": (
            "outputs/<batch>/<child-run-or-batch>/",
            "outputs/<batch>/batch_summary.json",
            "outputs/<batch>/comparison_plots/*.png",
            "outputs/<batch>/index.html",
            "outputs/<batch>/manifest.json",
            "outputs/<batch>/report.html",
            "outputs/<batch>/summary.json",
            "outputs/<batch>/worksheet.md",
        ),
        "content": (
            "Comparison metadata and child output paths, complete child run or batch "
            "trees, generated comparison plots, report, worksheet, manifest, summary, "
            "and nested browser index."
        ),
        "derived_copies": (
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
            "outputs/index.html",
        ),
        "learner_authored": True,
        "may_contain_private_data": True,
        "sharing": "sanitize-before-sharing",
        "status": "persistent",
    },
    "cumulative-index": {
        "artifacts": (
            "<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html",
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
            "outputs/index.html",
        ),
        "content": (
            "A regenerated cross-run browser index written at the configured outputs "
            "root, after a successful best-effort refresh in the parent of an explicit "
            "CLI or MCLAB_OUTPUT_DIR run, or directly under a safety-validated "
            "standalone-index root; it can summarize learner evidence and link saved "
            "artifacts."
        ),
        "derived_copies": (),
        "learner_authored": True,
        "may_contain_private_data": True,
        "sharing": "sanitize-before-sharing",
        "status": "derived",
    },
    "desktop-persistent-preferences": {
        "artifacts": (
            "<Qt-QSettings-UserScope:MCLab/MCLab>:language",
            "<Qt-QSettings-UserScope:MCLab/MCLab>:tourComplete",
        ),
        "content": (
            "The selected ko/en interface language and whether the introductory tour was "
            "dismissed, stored by Qt in the current user's native settings backend."
        ),
        "derived_copies": (),
        "learner_authored": False,
        "may_contain_private_data": False,
        "sharing": "sanitize-before-sharing",
        "status": "persistent",
    },
    "diagnostic-provenance": {
        "artifacts": (
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/manifest.json",
            "outputs/.mclab-trash/<receipt>/receipt.json",
            "outputs/<run>/manifest.json",
        ),
        "content": (
            "Runtime, operating-system, config/model path, hash, bounded error, "
            "output-root, run-name, and cleanup identity metadata."
        ),
        "derived_copies": (),
        "learner_authored": False,
        "may_contain_private_data": True,
        "sharing": "sanitize-before-sharing",
        "status": "persistent",
    },
    "learner-evidence": {
        "artifacts": (
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/<learner-evidence-artifact>",
            "<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html",
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
            "outputs/<run>/interaction_events.json",
            "outputs/<run>/replay.npz",
            "outputs/<run>/report.html",
            "outputs/<run>/worksheet.md",
            "outputs/index.html",
        ),
        "content": (
            "Learner prediction, selected outcome, observation note, learner-control "
            "events, and captured live-status evidence."
        ),
        "derived_copies": (
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/replay.npz:events_json",
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/report.html",
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/worksheet.md",
            "<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html",
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
            "outputs/<run>/replay.npz:events_json",
            "outputs/<run>/report.html",
            "outputs/<run>/worksheet.md",
            "outputs/index.html",
        ),
        "learner_authored": True,
        "may_contain_private_data": True,
        "sharing": "do-not-share-raw",
        "status": "persistent",
    },
    "optional-progress-preferences": {
        "artifacts": ("outputs/.mclab_progress.json",),
        "content": (
            "A defined lightweight app-preference storage surface; no current "
            "production writer is connected to it."
        ),
        "derived_copies": (),
        "learner_authored": False,
        "may_contain_private_data": False,
        "sharing": "sanitize-before-sharing",
        "status": "defined-storage-surface-no-current-writer",
    },
    "saved-run": {
        "artifacts": (
            "<MCLAB_OUTPUT_DIR-selected-first-run-directory>/",
            "outputs/<run>/config.yaml",
            "outputs/<run>/interaction_events.json",
            "outputs/<run>/learner_snapshot.json",
            "outputs/<run>/learner_tuned_config.yaml",
            "outputs/<run>/log.csv",
            "outputs/<run>/manifest.json",
            "outputs/<run>/notes.md",
            "outputs/<run>/plots/*.png",
            "outputs/<run>/replay.npz",
            "outputs/<run>/report.html",
            "outputs/<run>/states.json",
            "outputs/<run>/states.npz",
            "outputs/<run>/summary.json",
            "outputs/<run>/worksheet.md",
        ),
        "content": (
            "Resolved configuration, simulation signals and states, generated lesson "
            "notes, plots, replay, provenance, learner interaction evidence, report, "
            "and worksheet."
        ),
        "derived_copies": (
            "<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html",
            "<parent-of-explicit---output-dir>/index.html",
            "<standalone-index---output-dir>/index.html",
            "outputs/index.html",
        ),
        "learner_authored": True,
        "may_contain_private_data": True,
        "sharing": "sanitize-before-sharing",
        "status": "persistent",
    },
    "transient-application-controls": {
        "artifacts": (
            "<MCLAB_INSTANCE_LOCK>",
            "<Qt-AppLocalDataLocation>/mclab-desktop.lock",
            "<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>",
            r"\\.\pipe\mclab-<lock-path-sha256-prefix>",
            "outputs/<batch>/.mclab-batch-active",
            "outputs/<batch>/.mclab-batch-handoff",
        ),
        "content": (
            "Desktop QLockFile metadata can include PID, hostname, application name, "
            "machine ID, and boot ID; the path-derived Unix socket or Windows named-pipe "
            "endpoint and course-comparison controls are normally short-lived, but lock "
            "or Unix socket entries can remain after abnormal termination, and the batch "
            "handoff contains a one-time token."
        ),
        "derived_copies": (),
        "learner_authored": False,
        "may_contain_private_data": True,
        "sharing": "never-share-live-control-token",
        "status": "transient",
    },
}

EXPECTED_NETWORK_ACTIONS = (
    {
        "command": "python -m mclab assets install",
        "id": "asset-install",
        "purpose": "Download the pinned and hash-verified MuJoCo Menagerie Panda asset.",
        "source_reference": "src/mclab/application/assets.py",
    },
    {
        "command": "python scripts/install_locked.py <profile>",
        "id": "locked-dependency-install",
        "purpose": "Install the selected hash-locked Python dependency profile.",
        "source_reference": "scripts/install_locked.py",
    },
    {
        "command": (
            "python scripts/install_ubuntu_system_packages.py --install "
            "--output <temporary-json-path>"
        ),
        "id": "ubuntu-ci-system-install",
        "purpose": (
            "Install and verify the controlled Ubuntu package set in the maintainer CI job."
        ),
        "source_reference": "scripts/install_ubuntu_system_packages.py",
    },
)

EXPECTED_LIFECYCLE_CONTROLS = {
    "automatic_deletion": False,
    "backup_policy_status": "not-defined",
    "cleanup_apply_authorized_by_this_contract": False,
    "cleanup_default": "read-only-plan",
    "cleanup_effect": "recoverable-quarantine-not-erasure",
    "derived_index_may_persist_until_regenerated": True,
    "hold_marker": ".mclab-preserve",
    "network_filesystem_support": "unsupported",
    "permanent_purge_available": False,
    "real_output_validation": "not-run-not-authorized",
    "restore_scope": "source-or-venv-cli-on-local-filesystem",
    "retention_policy_status": "not-defined",
    "rpo_rto_status": "not-defined",
    "secure_erasure_status": "not-provided-by-mclab",
}

EXPECTED_SHARING_RULES = {
    "minimum_necessary_only": True,
    "private_security_channel": ".github/SECURITY.md",
    "public_support_channel": ".github/SUPPORT.md",
    "remove_before_sharing": [
        "credentials-and-tokens",
        "learner-predictions-and-notes",
        "live-batch-handoff-secrets",
        "private-output-content",
        "unsanitized-absolute-paths",
    ],
    "support_submission_is_user_initiated": True,
}

EXPECTED_DOCUMENTATION = {
    "bilingual_policy": "docs/local_data_and_privacy.md",
    "documentation_map": "docs/README.md",
    "english_readme": "README.en.md",
    "korean_readme": "README.md",
    "learner_guide": "docs/learner_guide.md",
    "security_policy": ".github/SECURITY.md",
    "support_policy": ".github/SUPPORT.md",
}

EXPECTED_SOURCE_INVENTORY = {
    "inventory_version": 1,
    "manifest_path": str(SOURCE_MANIFEST_PATH),
    "manifest_sha256": "92f6d220f7905904fc60fc4afba5f0c03bcda5d998904bbd2faaf97933bc0b02",
    "scope": "all-python-sources-under-packaging-scripts-and-src-mclab",
}

EXPECTED_SOURCE_ROOTS = (
    {"extensions": [".py"], "path": "packaging"},
    {"extensions": [".py"], "path": "scripts"},
    {"extensions": [".py"], "path": "src/mclab"},
)

EXPECTED_VALIDATION_ONLY_EXCLUSIONS = (
    {
        "activation": "explicit maintainer invocation of one of the listed audit scripts",
        "artifacts": [
            "<audit-app-startup---output>/**",
            "<audit-course-comparison---output>/**",
            "<audit-desktop-ui---output>/**",
            "<audit-report-ui---output>/**",
            "<audit-scene-semantics---output>/**",
            "<audit-supply-chain---output>",
        ],
        "exclusion_scope": "not-created-by-an-ordinary-learner-run",
        "id": "maintainer-audit-output-roots",
        "may_contain_private_data": True,
        "source_references": [
            "scripts/audit_app_startup.py",
            "scripts/audit_course_comparison.py",
            "scripts/audit_desktop_ui.py",
            "scripts/audit_report_ui.py",
            "scripts/audit_scene_semantics.py",
            "scripts/audit_supply_chain.py",
        ],
    },
    {
        "activation": (
            "an explicit MCLAB_ACTIVATION_PATH plus a successful local duplicate-instance "
            "activation"
        ),
        "artifacts": ["<MCLAB_ACTIVATION_PATH>"],
        "exclusion_scope": "validation-probe-not-ordinary-learner-storage",
        "id": "qt-activation-probe",
        "may_contain_private_data": True,
        "source_references": ["src/mclab/application/single_instance.py:_record_activation"],
    },
    {
        "activation": "an explicit MCLAB_SCREENSHOT_PATH diagnostic override",
        "artifacts": ["<MCLAB_SCREENSHOT_PATH>"],
        "exclusion_scope": "validation-capture-not-ordinary-learner-storage",
        "id": "qt-screenshot-capture",
        "may_contain_private_data": True,
        "source_references": ["src/mclab/application/qt_app.py:run_app"],
    },
    {
        "activation": (
            "MCLAB_SELF_TEST=1, a matching scheduled smoke action, and the corresponding "
            "explicit destination variable"
        ),
        "artifacts": [
            "<MCLAB_ACCESSIBILITY_PATH>",
            "<MCLAB_BACKEND_TRACE_PATH>",
            "<MCLAB_FOCUS_TRACE_PATH>",
            "<MCLAB_STARTUP_PATH>",
        ],
        "exclusion_scope": "self-test-evidence-not-ordinary-learner-storage",
        "id": "qt-self-test-traces",
        "may_contain_private_data": True,
        "source_references": ["src/mclab/application/qt_smoke.py"],
    },
)

EXPECTED_UNRESOLVED_IDS = (
    "backup-owner-location-cadence",
    "institution-retention-period",
    "release-evidence-retention",
    "rpo-rto",
    "secure-erasure-method",
    "shared-pc-account-admin-policy",
)

REQUIRED_POLICY_MARKERS = (
    "no automatic learner-data upload or remote usage analytics",
    "recoverable quarantine, not deletion or secure erasure",
    "No real learner output was read, dry-run, moved, restored, or erased",
    "학습자 데이터를 자동 업로드하거나 원격 사용량 분석을 수행하지 않습니다",
    "복구 가능한 격리이며 삭제 또는 안전한 영구 삭제가 아니고",
    "실제 학습자 output을 읽거나,",
    "support SLA, RPO, or RTO",
    "지원 SLA, RPO 또는 RTO",
    "<parent-of-explicit---output-dir>/index.html",
    "<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html",
    "<standalone-index---output-dir>/index.html",
    "process current working directory in both source and frozen execution",
    "best-effort parent-index refresh",
    "Qt-QSettings-UserScope:MCLab/MCLab",
    r"\\.\pipe\mclab-<lock-path-sha256-prefix>",
    "validation-only exclusions",
    "검증 전용 제외",
    "PID, hostname, application name, machine ID, and boot ID",
    "<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>",
    "canonical version-1 source manifest pins the exact path set and SHA-256 bytes",
    "canonical version-1 source manifest는",
    "Controlled repository reads use no-follow file descriptors",
    "Windows reparse points",
    "FILE_LIST_DIRECTORY handles without FILE_SHARE_DELETE",
    "통제된 저장소 읽기는 no-follow file descriptor를 사용하고",
    "mclab.local-data.v1",
)

REQUIRED_POLICY_LINKS = {
    Path("README.md"): "docs/local_data_and_privacy.md",
    Path("README.en.md"): "docs/local_data_and_privacy.md",
    Path("docs/README.md"): "local_data_and_privacy.md",
    Path("docs/learner_guide.md"): "local_data_and_privacy.md",
    Path(".github/SECURITY.md"): "../docs/local_data_and_privacy.md",
    Path(".github/SUPPORT.md"): "../docs/local_data_and_privacy.md",
    POLICY_DOC_PATH: "../.agents/operations/local-data-policy.json",
}

REQUIRED_DOCUMENT_MARKERS = {
    Path(".github/SECURITY.md"): (
        "Do not attach credentials, tokens, learner predictions or notes, private outputs, "
        "or unsanitized absolute paths.",
        "The maintainer handles reports on a best-effort basis and does not promise a "
        "fixed response SLA.",
        "repository-scoped current inventory",
        "not a public-release completeness or institutional-policy claim",
    ),
    Path(".github/SUPPORT.md"): (
        "Support is best effort; no response-time or platform-service SLA is promised.",
        "MCLab keeps runs and notes locally and does not upload them automatically; sharing "
        "them in an issue is the reporter's explicit action.",
        "사용자명, 홈 경로, 비밀정보, 학습자 예측·메모를 제거한 뒤 필요한 부분만 공유해 주세요.",
    ),
}

REMOTE_IMPORTS = frozenset(
    {
        "aiohttp",
        "boto3",
        "botocore",
        "ftplib",
        "httpx",
        "paramiko",
        "requests",
        "smtplib",
        "urllib.request",
    }
)
ALLOWED_REMOTE_IMPORTS = {
    (Path("src/mclab/application/assets.py"), "urllib.request"),
}


@dataclass(frozen=True)
class Metric:
    name: str
    threshold: str
    measured: str
    passed: bool


class ContractInputError(ValueError):
    """Raised when a controlled repository input is not safely readable."""


def _duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractInputError(f"DUPLICATE_JSON_KEY {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractInputError(f"NONFINITE_JSON_NUMBER {value}")


def strict_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractInputError(f"NON_UTF8 {label}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_duplicate_object,
            parse_constant=_reject_constant,
        )
    except ContractInputError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractInputError(f"MALFORMED_JSON {label}: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _json_values_equal(left: Any, right: Any) -> bool:
    """Compare parsed JSON values without Python's bool/int coercion."""

    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)


@dataclass
class _OpenedDirectory:
    path: Path
    fd: int
    identity: tuple[int, int, int, int, int]
    label: str
    parent: _OpenedDirectory | None = None
    name: str | None = None


@dataclass
class _DirectoryChain:
    entries: list[_OpenedDirectory]

    @property
    def leaf(self) -> _OpenedDirectory:
        return self.entries[-1]

    def assert_current(self) -> None:
        for entry in self.entries:
            _assert_directory_current(entry)


@dataclass(frozen=True)
class _StatView:
    st_ctime_ns: int
    st_dev: int
    st_file_attributes: int
    st_ino: int
    st_mode: int
    st_mtime_ns: int
    st_reparse_tag: int
    st_size: int


def _windows_path_attributes(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_attributes = kernel32.GetFileAttributesW
    get_attributes.argtypes = (wintypes.LPCWSTR,)
    get_attributes.restype = wintypes.DWORD
    attributes = int(get_attributes(str(path)))
    if attributes == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    return attributes


def _windows_descriptor_metadata(descriptor: int) -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    information = FileAttributeTagInfo()
    handle = msvcrt.get_osfhandle(descriptor)
    if not get_information(
        handle,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(information.file_attributes), int(information.reparse_tag)


def _stat_view(
    value: os.stat_result,
    *,
    file_attributes: int | None = None,
    reparse_tag: int | None = None,
) -> os.stat_result | _StatView:
    if file_attributes is None and reparse_tag is None:
        return value
    return _StatView(
        st_ctime_ns=int(value.st_ctime_ns),
        st_dev=int(value.st_dev),
        st_file_attributes=int(
            getattr(value, "st_file_attributes", 0) if file_attributes is None else file_attributes
        ),
        st_ino=int(value.st_ino),
        st_mode=int(value.st_mode),
        st_mtime_ns=int(value.st_mtime_ns),
        st_reparse_tag=int(
            getattr(value, "st_reparse_tag", 0) if reparse_tag is None else reparse_tag
        ),
        st_size=int(value.st_size),
    )


def _descriptor_stat(descriptor: int) -> os.stat_result | _StatView:
    value = os.fstat(descriptor)
    if os.name != "nt":
        return value
    attributes, reparse_tag = _windows_descriptor_metadata(descriptor)
    return _stat_view(
        value,
        file_attributes=attributes,
        reparse_tag=reparse_tag,
    )


def _is_windows_reparse_point(value: Any) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0)) & WINDOWS_REPARSE_ATTRIBUTE)


def _stat_identity(value: Any) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        stat.S_IFMT(value.st_mode),
        int(getattr(value, "st_file_attributes", 0)),
        int(getattr(value, "st_reparse_tag", 0)),
    )


def _file_snapshot(value: Any) -> tuple[int, int, int]:
    return (
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _validate_stat_kind(
    value: Any,
    *,
    label: str,
    context: str,
    directory: bool,
) -> None:
    if stat.S_ISLNK(value.st_mode):
        raise ContractInputError(f"SYMLINK_{context} {label}")
    if _is_windows_reparse_point(value):
        raise ContractInputError(f"REPARSE_{context} {label}")
    if directory and not stat.S_ISDIR(value.st_mode):
        raise ContractInputError(f"NON_DIRECTORY_{context} {label}")
    if not directory and not stat.S_ISREG(value.st_mode):
        raise ContractInputError(f"NON_REGULAR_{context} {label}")


def _open_windows_nofollow(path: Path, *, directory: bool) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    # FILE_LIST_DIRECTORY makes a retained directory handle participate in
    # ordinary directory sharing checks.  Omitting FILE_SHARE_DELETE pins the
    # lexical name while the handle is held, so an ancestor cannot be renamed
    # away and swapped back around a path-based Windows inspection.  This is
    # the same anchoring pattern used by src/mclab/output_windows.py.
    desired_access = (0x00000001 | 0x00000080) if directory else 0x80000000
    share_mode = 0x00000001 | 0x00000002
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = create_file(str(path), desired_access, share_mode, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)
    descriptor_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    try:
        return msvcrt.open_osfhandle(int(handle), descriptor_flags)
    except OSError:
        close_handle(handle)
        raise


def _open_nofollow(
    path: Path,
    *,
    directory: bool,
    parent_fd: int | None = None,
    name: str | None = None,
) -> int:
    if os.name == "nt":
        if parent_fd is not None:
            if name is None or Path(path).name != name:
                raise ContractInputError("MISSING_RELATIVE_OPEN_NAME")
            # Win32 CreateFileW has no dir_fd form.  The caller therefore
            # retains every lexical parent with rename-denying share flags;
            # validate that anchor handle before opening the checked full path.
            parent_value = _descriptor_stat(parent_fd)
            _validate_stat_kind(
                parent_value,
                label=str(Path(path).parent),
                context="REPOSITORY_DIRECTORY",
                directory=True,
            )
        return _open_windows_nofollow(path, directory=directory)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ContractInputError("NOFOLLOW_FILE_DESCRIPTOR_UNAVAILABLE")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            raise ContractInputError("DIRECTORY_FILE_DESCRIPTOR_UNAVAILABLE")
        flags |= directory_flag
    if parent_fd is None:
        return os.open(path, flags)
    if name is None:
        raise ContractInputError("MISSING_RELATIVE_OPEN_NAME")
    if not OPEN_SUPPORTS_DIR_FD:
        raise ContractInputError("RELATIVE_NOFOLLOW_OPEN_UNAVAILABLE")
    return os.open(name, flags, dir_fd=parent_fd)


def _entry_lstat(parent: _OpenedDirectory, name: str) -> os.stat_result | _StatView:
    if os.name != "nt":
        if not STAT_SUPPORTS_DIR_FD or not STAT_SUPPORTS_NOFOLLOW:
            raise ContractInputError("RELATIVE_NOFOLLOW_STAT_UNAVAILABLE")
        return os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
    path = parent.path / name
    value = os.lstat(path)
    return _stat_view(value, file_attributes=_windows_path_attributes(path))


def _path_lstat(path: Path) -> os.stat_result | _StatView:
    value = os.lstat(path)
    if os.name != "nt":
        return value
    return _stat_view(value, file_attributes=_windows_path_attributes(path))


def _open_directory(
    path: Path,
    *,
    label: str,
    parent: _OpenedDirectory | None = None,
    name: str | None = None,
    expected_identity: tuple[int, int, int, int, int] | None = None,
) -> _OpenedDirectory:
    descriptor: int | None = None
    try:
        before = _path_lstat(path) if parent is None else _entry_lstat(parent, str(name))
        _validate_stat_kind(
            before,
            label=label,
            context="REPOSITORY_DIRECTORY",
            directory=True,
        )
        before_identity = _stat_identity(before)
        if expected_identity is not None and before_identity != expected_identity:
            raise ContractInputError(f"CHANGED_REPOSITORY_DIRECTORY {label}")
        descriptor = _open_nofollow(
            path,
            directory=True,
            parent_fd=parent.fd if parent is not None else None,
            name=name,
        )
        opened = _descriptor_stat(descriptor)
        after = _path_lstat(path) if parent is None else _entry_lstat(parent, str(name))
        for value in (opened, after):
            _validate_stat_kind(
                value,
                label=label,
                context="REPOSITORY_DIRECTORY",
                directory=True,
            )
        if not (before_identity == _stat_identity(opened) == _stat_identity(after)):
            raise ContractInputError(f"CHANGED_REPOSITORY_DIRECTORY {label}")
        return _OpenedDirectory(
            path=path,
            fd=descriptor,
            identity=before_identity,
            label=label,
            parent=parent,
            name=name,
        )
    except ContractInputError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ContractInputError(f"UNREADABLE_REPOSITORY_DIRECTORY {label}: {exc}") from exc


def _assert_directory_current(directory: _OpenedDirectory) -> None:
    try:
        descriptor_stat = _descriptor_stat(directory.fd)
        path_stat = (
            _path_lstat(directory.path)
            if directory.parent is None
            else _entry_lstat(directory.parent, str(directory.name))
        )
        for value in (descriptor_stat, path_stat):
            _validate_stat_kind(
                value,
                label=directory.label,
                context="REPOSITORY_DIRECTORY",
                directory=True,
            )
        if not (directory.identity == _stat_identity(descriptor_stat) == _stat_identity(path_stat)):
            raise ContractInputError(f"CHANGED_REPOSITORY_DIRECTORY {directory.label}")
    except ContractInputError:
        raise
    except OSError as exc:
        raise ContractInputError(f"CHANGED_REPOSITORY_DIRECTORY {directory.label}: {exc}") from exc


def _safe_relative_path(relative: Path, *, context: str) -> tuple[str, ...]:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ContractInputError(f"UNSAFE_{context} {relative}")
    parts = tuple(part for part in relative.parts if part != ".")
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ContractInputError(f"UNSAFE_{context} {relative}")
    return parts


@contextmanager
def _open_directory_chain(
    root: Path,
    relative_directory: Path | None = None,
) -> Iterator[_DirectoryChain]:
    root_path = Path(os.path.abspath(os.fspath(root)))
    if not root_path.is_absolute() or not root_path.anchor:
        raise ContractInputError("INVALID_REPOSITORY_ROOT")
    relative_parts: tuple[str, ...] = ()
    if relative_directory is not None and relative_directory.parts:
        relative_parts = _safe_relative_path(
            relative_directory,
            context="REPOSITORY_DIRECTORY",
        )
    entries: list[_OpenedDirectory] = []
    try:
        anchor = Path(root_path.anchor)
        current = _open_directory(anchor, label="<repository-root-ancestor>")
        entries.append(current)
        for part in root_path.parts[1:]:
            current = _open_directory(
                current.path / part,
                label="<repository-root-ancestor>",
                parent=current,
                name=part,
            )
            entries.append(current)
        for index, part in enumerate(relative_parts):
            relative_label = Path(*relative_parts[: index + 1]).as_posix()
            current = _open_directory(
                current.path / part,
                label=relative_label,
                parent=current,
                name=part,
            )
            entries.append(current)
        chain = _DirectoryChain(entries)
        chain.assert_current()
        yield chain
        chain.assert_current()
    finally:
        for entry in reversed(entries):
            try:
                os.close(entry.fd)
            except OSError:
                pass


def _read_regular_bytes(root: Path, relative: Path, *, max_bytes: int) -> bytes:
    parts = _safe_relative_path(relative, context="REPOSITORY_PATH")
    normalized = Path(*parts)
    parent_relative = normalized.parent if len(parts) > 1 else None
    label = normalized.as_posix()
    descriptor: int | None = None
    try:
        with _open_directory_chain(root, parent_relative) as chain:
            parent = chain.leaf
            name = parts[-1]
            before = _entry_lstat(parent, name)
            _validate_stat_kind(
                before,
                label=label,
                context="REPOSITORY_INPUT",
                directory=False,
            )
            if before.st_size > max_bytes:
                raise ContractInputError(
                    f"OVERSIZED_REPOSITORY_INPUT {label}: {before.st_size}>{max_bytes}"
                )
            descriptor = _open_nofollow(
                parent.path / name,
                directory=False,
                parent_fd=parent.fd,
                name=name,
            )
            opened = _descriptor_stat(descriptor)
            after_open = _entry_lstat(parent, name)
            for value in (opened, after_open):
                _validate_stat_kind(
                    value,
                    label=label,
                    context="REPOSITORY_INPUT",
                    directory=False,
                )
            if not (_stat_identity(before) == _stat_identity(opened) == _stat_identity(after_open)):
                raise ContractInputError(f"CHANGED_REPOSITORY_INPUT {label}")

            data = bytearray()
            while True:
                remaining = max_bytes + 1 - len(data)
                if remaining <= 0:
                    raise ContractInputError(f"OVERSIZED_REPOSITORY_INPUT {label}: >{max_bytes}")
                chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ContractInputError(f"OVERSIZED_REPOSITORY_INPUT {label}: >{max_bytes}")

            after_read = _descriptor_stat(descriptor)
            final_path = _entry_lstat(parent, name)
            chain.assert_current()
            for value in (after_read, final_path):
                _validate_stat_kind(
                    value,
                    label=label,
                    context="REPOSITORY_INPUT",
                    directory=False,
                )
            if not (
                _stat_identity(before) == _stat_identity(after_read) == _stat_identity(final_path)
            ) or not (
                _file_snapshot(before)
                == _file_snapshot(opened)
                == _file_snapshot(after_open)
                == _file_snapshot(after_read)
                == _file_snapshot(final_path)
            ):
                raise ContractInputError(f"CHANGED_REPOSITORY_INPUT {label}")
            if len(data) != after_read.st_size:
                raise ContractInputError(f"CHANGED_REPOSITORY_INPUT {label}")
            return bytes(data)
    except ContractInputError:
        raise
    except OSError as exc:
        raise ContractInputError(f"UNREADABLE_REPOSITORY_INPUT {label}: {exc}") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_text(root: Path, relative: Path, *, max_bytes: int) -> str:
    data = _read_regular_bytes(root, relative, max_bytes=max_bytes)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractInputError(f"NON_UTF8 {relative}: {exc}") from exc


def _resolve_json_pointer(schema_root: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ContractInputError(f"UNSUPPORTED_SCHEMA_REFERENCE {reference}")
    value: Any = schema_root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise ContractInputError(f"MISSING_SCHEMA_REFERENCE {reference}")
        value = value[part]
    return value


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "boolean":
        return type(value) is bool
    return False


def _schema_errors(
    value: Any,
    schema: dict[str, Any],
    schema_root: dict[str, Any],
    *,
    path: str = "$",
    reference_stack: tuple[str, ...] = (),
) -> list[str]:
    if "$ref" in schema:
        reference = str(schema["$ref"])
        if reference in reference_stack:
            return [f"SCHEMA_REFERENCE_CYCLE {path}: {reference}"]
        if len(reference_stack) >= MAX_SCHEMA_REFERENCE_DEPTH:
            return [f"SCHEMA_REFERENCE_DEPTH {path}: >{MAX_SCHEMA_REFERENCE_DEPTH}"]
        referenced = _resolve_json_pointer(schema_root, reference)
        if not isinstance(referenced, dict):
            return [f"SCHEMA_REFERENCE_NOT_OBJECT {path}"]
        return _schema_errors(
            value,
            referenced,
            schema_root,
            path=path,
            reference_stack=(*reference_stack, reference),
        )

    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _matches_type(value, expected_type):
        return [f"SCHEMA_TYPE {path}: expected {expected_type}"]
    if "const" in schema and not _json_values_equal(value, schema["const"]):
        errors.append(f"SCHEMA_CONST {path}: expected {schema['const']!r}")
    choices = schema.get("enum")
    if isinstance(choices, list) and not any(
        _json_values_equal(value, choice) for choice in choices
    ):
        errors.append(f"SCHEMA_ENUM {path}: unsupported value {value!r}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            return [f"INVALID_SCHEMA_OBJECT_RULES {path}"]
        for key in required:
            if key not in value:
                errors.append(f"SCHEMA_REQUIRED {path}.{key}")
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                errors.append(f"SCHEMA_ADDITIONAL_PROPERTY {path}.{key}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(
                    _schema_errors(
                        child,
                        child_schema,
                        schema_root,
                        path=f"{path}.{key}",
                        reference_stack=reference_stack,
                    )
                )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if type(minimum) is int and len(value) < minimum:
            errors.append(f"SCHEMA_MIN_ITEMS {path}: {len(value)}<{minimum}")
        if type(maximum) is int and len(value) > maximum:
            errors.append(f"SCHEMA_MAX_ITEMS {path}: {len(value)}>{maximum}")
        if schema.get("uniqueItems") is True:
            keys = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(keys) != len(set(keys)):
                errors.append(f"SCHEMA_UNIQUE_ITEMS {path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    _schema_errors(
                        item,
                        item_schema,
                        schema_root,
                        path=f"{path}[{index}]",
                        reference_stack=reference_stack,
                    )
                )

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if type(minimum_length) is int and len(value) < minimum_length:
            errors.append(f"SCHEMA_MIN_LENGTH {path}: {len(value)}<{minimum_length}")
        maximum_length = schema.get("maxLength")
        if type(maximum_length) is int and len(value) > maximum_length:
            errors.append(f"SCHEMA_MAX_LENGTH {path}: {len(value)}>{maximum_length}")
    return errors


def _record_map(value: Any, *, field: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        return {}, [f"CONTRACT_RECORDS {field}: expected list"]
    records: dict[str, dict[str, Any]] = {}
    ids: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append(f"CONTRACT_RECORD_ID {field}[{index}]")
            continue
        item_id = item["id"]
        ids.append(item_id)
        if item_id in records:
            errors.append(f"CONTRACT_DUPLICATE_ID {field}.{item_id}")
        records[item_id] = item
    if ids != sorted(ids):
        errors.append(f"CONTRACT_ID_ORDER {field}: {ids!r}")
    return records, errors


def _contract_semantic_errors(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    exact_fields = {
        "scope": EXPECTED_SCOPE,
        "lifecycle_controls": EXPECTED_LIFECYCLE_CONTROLS,
        "sharing_rules": EXPECTED_SHARING_RULES,
        "documentation": EXPECTED_DOCUMENTATION,
        "source_inventory": EXPECTED_SOURCE_INVENTORY,
    }
    for field, expected in exact_fields.items():
        if not _json_values_equal(policy.get(field), expected):
            errors.append(f"CONTRACT_VALUE {field}")

    if not _json_values_equal(
        tuple(policy.get("storage_locations", ())), EXPECTED_STORAGE_LOCATIONS
    ):
        errors.append("CONTRACT_VALUE storage_locations")
    if not _json_values_equal(
        tuple(policy.get("validation_only_exclusions", ())),
        EXPECTED_VALIDATION_ONLY_EXCLUSIONS,
    ):
        errors.append("CONTRACT_VALUE validation_only_exclusions")
    network = policy.get("network_behavior")
    if not isinstance(network, dict):
        errors.append("CONTRACT_VALUE network_behavior")
    else:
        expected_network_scalars = {
            "automatic_learner_data_transfer": False,
            "local_socket_is_remote_network": False,
            "ordinary_run_network_required": False,
            "support_sharing": "user-initiated-sanitized-only",
            "telemetry_is_remote_analytics": False,
        }
        for field, expected in expected_network_scalars.items():
            if not _json_values_equal(network.get(field), expected):
                errors.append(f"CONTRACT_VALUE network_behavior.{field}")
        if not _json_values_equal(
            tuple(network.get("explicit_network_actions", ())), EXPECTED_NETWORK_ACTIONS
        ):
            errors.append("CONTRACT_VALUE network_behavior.explicit_network_actions")

    records, record_errors = _record_map(policy.get("data_classes"), field="data_classes")
    errors.extend(record_errors)
    if tuple(records) != tuple(EXPECTED_DATA_CLASSES):
        errors.append(f"CONTRACT_IDS data_classes: {tuple(records)!r}")
    for item_id, expected in EXPECTED_DATA_CLASSES.items():
        actual = records.get(item_id)
        if actual is None:
            continue
        for field, expected_value in expected.items():
            actual_value = actual.get(field)
            if field in {"artifacts", "derived_copies"} and isinstance(actual_value, list):
                actual_value = tuple(actual_value)
            if not _json_values_equal(actual_value, expected_value):
                errors.append(f"CONTRACT_VALUE data_classes.{item_id}.{field}")

    unresolved, unresolved_errors = _record_map(
        policy.get("unresolved_decisions"), field="unresolved_decisions"
    )
    errors.extend(unresolved_errors)
    if tuple(unresolved) != EXPECTED_UNRESOLVED_IDS:
        errors.append(f"CONTRACT_IDS unresolved_decisions: {tuple(unresolved)!r}")
    for item_id, record in unresolved.items():
        if not _json_values_equal(
            record,
            {"id": item_id, "status": "unresolved-external-policy"},
        ):
            errors.append(f"CONTRACT_VALUE unresolved_decisions.{item_id}")
    return errors


def _list_directory_names(directory: _OpenedDirectory) -> tuple[str, ...]:
    try:
        before = _descriptor_stat(directory.fd)
        _assert_directory_current(directory)
        if os.name != "nt" and not LISTDIR_SUPPORTS_FD:
            raise ContractInputError("DIRECTORY_DESCRIPTOR_LIST_UNAVAILABLE")
        raw_names = os.listdir(directory.path if os.name == "nt" else directory.fd)
        after = _descriptor_stat(directory.fd)
        _assert_directory_current(directory)
    except ContractInputError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ContractInputError(f"UNREADABLE_SOURCE_DIRECTORY {directory.label}: {exc}") from exc
    if _stat_identity(before) != _stat_identity(after):
        raise ContractInputError(f"CHANGED_SOURCE_DIRECTORY {directory.label}")
    if not all(isinstance(name, str) and name not in {"", ".", ".."} for name in raw_names):
        raise ContractInputError(f"INVALID_SOURCE_DIRECTORY_ENTRY {directory.label}")
    return tuple(sorted(raw_names))


def _source_entry_error(value: os.stat_result, relative: Path) -> str | None:
    label = relative.as_posix()
    if stat.S_ISLNK(value.st_mode):
        return f"SYMLINK_SOURCE_ENTRY {label}"
    if _is_windows_reparse_point(value):
        return f"REPARSE_SOURCE_ENTRY {label}"
    if stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode):
        return None
    return f"SPECIAL_SOURCE_ENTRY {label}"


def _walk_source_directory(
    directory: _OpenedDirectory,
    relative_directory: Path,
    extensions: tuple[str, ...],
    discovered: set[str],
    errors: list[str],
) -> None:
    try:
        names = _list_directory_names(directory)
    except ContractInputError as exc:
        errors.append(str(exc))
        return
    entry_identities: dict[str, tuple[int, int, int, int, int]] = {}
    for name in names:
        relative = relative_directory / name
        try:
            before = _entry_lstat(directory, name)
        except OSError as exc:
            errors.append(f"UNREADABLE_SOURCE_ENTRY {relative.as_posix()}: {exc}")
            continue
        unsafe = _source_entry_error(before, relative)
        if unsafe is not None:
            errors.append(unsafe)
            continue
        identity = _stat_identity(before)
        entry_identities[name] = identity
        if stat.S_ISREG(before.st_mode):
            if relative.suffix in extensions:
                discovered.add(relative.as_posix())
            continue
        child: _OpenedDirectory | None = None
        try:
            child = _open_directory(
                directory.path / name,
                label=relative.as_posix(),
                parent=directory,
                name=name,
                expected_identity=identity,
            )
            _walk_source_directory(child, relative, extensions, discovered, errors)
            _assert_directory_current(child)
            _assert_directory_current(directory)
        except ContractInputError as exc:
            errors.append(str(exc))
        finally:
            if child is not None:
                try:
                    os.close(child.fd)
                except OSError:
                    pass

    try:
        final_names = _list_directory_names(directory)
    except ContractInputError as exc:
        errors.append(str(exc))
        return
    if names != final_names:
        errors.append(f"CHANGED_SOURCE_DIRECTORY {relative_directory.as_posix()}")
        return
    for name, identity in entry_identities.items():
        relative = relative_directory / name
        try:
            current = _entry_lstat(directory, name)
        except OSError as exc:
            errors.append(f"CHANGED_SOURCE_ENTRY {relative.as_posix()}: {exc}")
            continue
        unsafe = _source_entry_error(current, relative)
        if unsafe is not None:
            errors.append(unsafe)
        elif _stat_identity(current) != identity:
            errors.append(f"CHANGED_SOURCE_ENTRY {relative.as_posix()}")


def _discover_source_paths(
    root: Path,
    roots: tuple[dict[str, Any], ...],
) -> tuple[set[str], list[str]]:
    discovered: set[str] = set()
    errors: list[str] = []
    for record in roots:
        relative_root = Path(str(record.get("path", "")))
        extensions = record.get("extensions")
        if not isinstance(extensions, list) or not all(
            isinstance(item, str) and item.startswith(".") for item in extensions
        ):
            errors.append(f"SOURCE_INVENTORY_EXTENSIONS {relative_root}")
            continue
        try:
            _safe_relative_path(relative_root, context="SOURCE_ROOT")
            with _open_directory_chain(root, relative_root) as chain:
                _walk_source_directory(
                    chain.leaf,
                    relative_root,
                    tuple(extensions),
                    discovered,
                    errors,
                )
        except ContractInputError as exc:
            errors.append(str(exc))
    return discovered, errors


def _source_inventory_errors(
    root: Path,
    policy: dict[str, Any],
    schema: dict[str, Any],
    manifest_bytes: bytes,
    manifest: Any,
) -> tuple[int, list[str]]:
    errors: list[str] = []
    reference = policy.get("source_inventory")
    if not isinstance(reference, dict):
        return 0, ["SOURCE_INVENTORY_REFERENCE"]
    expected_manifest_hash = reference.get("manifest_sha256")
    if (
        not isinstance(expected_manifest_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_hash) is None
    ):
        errors.append("SOURCE_INVENTORY_MANIFEST_SHA256_FORMAT")
    else:
        measured_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if measured_manifest_hash != expected_manifest_hash:
            errors.append(
                "SOURCE_INVENTORY_MANIFEST_SHA256 "
                f"{measured_manifest_hash}; expected {expected_manifest_hash}"
            )
    if not isinstance(manifest, dict):
        return 0, [*errors, "SOURCE_INVENTORY_ROOT_NOT_OBJECT"]
    manifest_schema = schema.get("$defs", {}).get("sourceInventoryManifest")
    if not isinstance(manifest_schema, dict):
        errors.append("SOURCE_INVENTORY_SCHEMA_MISSING")
    else:
        errors.extend(_schema_errors(manifest, manifest_schema, schema, path="$source"))
    if canonical_json_bytes(manifest) != manifest_bytes:
        errors.append("SOURCE_INVENTORY_NOT_CANONICAL_JSON")

    roots_value = manifest.get("roots")
    roots = tuple(roots_value) if isinstance(roots_value, list) else ()
    if not _json_values_equal(roots, EXPECTED_SOURCE_ROOTS):
        errors.append("SOURCE_INVENTORY_ROOTS")

    sources_value = manifest.get("sources")
    if not isinstance(sources_value, list):
        return 0, [*errors, "SOURCE_INVENTORY_SOURCES"]
    declared: dict[str, str] = {}
    ordered_paths: list[str] = []
    for index, record in enumerate(sources_value):
        if not isinstance(record, dict):
            errors.append(f"SOURCE_INVENTORY_RECORD [{index}]")
            continue
        path_value = record.get("path")
        digest = record.get("sha256")
        if not isinstance(path_value, str):
            errors.append(f"SOURCE_INVENTORY_PATH [{index}]")
            continue
        relative = Path(path_value)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.as_posix() != path_value
        ):
            errors.append(f"SOURCE_INVENTORY_UNSAFE_PATH {path_value!r}")
            continue
        if path_value in declared:
            errors.append(f"SOURCE_INVENTORY_DUPLICATE_PATH {path_value}")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append(f"SOURCE_INVENTORY_DIGEST {path_value}")
            continue
        declared[path_value] = digest
        ordered_paths.append(path_value)
    if ordered_paths != sorted(ordered_paths):
        errors.append("SOURCE_INVENTORY_PATH_ORDER")

    discovered, discovery_errors = _discover_source_paths(root, roots)
    errors.extend(discovery_errors)
    declared_paths = set(declared)
    for path_value in sorted(declared_paths - discovered):
        errors.append(f"SOURCE_INVENTORY_MISSING {path_value}")
    for path_value in sorted(discovered - declared_paths):
        errors.append(f"SOURCE_INVENTORY_UNDECLARED {path_value}")
    for path_value in sorted(declared_paths & discovered):
        try:
            source = _read_regular_bytes(root, Path(path_value), max_bytes=MAX_SOURCE_BYTES)
        except ContractInputError as exc:
            errors.append(str(exc))
            continue
        measured = hashlib.sha256(source).hexdigest()
        if measured != declared[path_value]:
            errors.append(
                f"SOURCE_INVENTORY_SHA256 {path_value}: {measured}; expected {declared[path_value]}"
            )
    return len(declared), errors


def _import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                names.add(f"{module}.{alias.name}" if module else alias.name)
    return names


def _network_boundary_errors(root: Path) -> list[str]:
    source_paths, errors = _discover_source_paths(
        root,
        ({"extensions": [".py"], "path": "src/mclab"},),
    )
    for path_value in sorted(source_paths):
        relative = Path(path_value)
        try:
            source = _read_text(root, relative, max_bytes=MAX_SOURCE_BYTES)
            tree = ast.parse(source, filename=str(relative))
        except (ContractInputError, SyntaxError) as exc:
            errors.append(f"NETWORK_SCAN_INPUT {relative}: {exc}")
            continue
        reviewed_imports = _import_names(tree)
        for remote_name in sorted(REMOTE_IMPORTS):
            if not any(
                name == remote_name or name.startswith(f"{remote_name}.")
                for name in reviewed_imports
            ):
                continue
            if (relative, remote_name) not in ALLOWED_REMOTE_IMPORTS:
                errors.append(f"UNREVIEWED_REMOTE_IMPORT {relative}: {remote_name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "open_url":
                    errors.append(f"UNREVIEWED_OPEN_URL_CALL {relative}:{node.lineno}")
    return errors


def _policy_document_errors(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = _read_text(root, POLICY_DOC_PATH, max_bytes=MAX_DOCUMENT_BYTES)
    except ContractInputError as exc:
        return [str(exc)]
    headings = tuple(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if headings != POLICY_HEADINGS:
        errors.append(f"POLICY_HEADING_PARITY {headings!r}")
    if len(re.findall(r"^### English\s*$", text, flags=re.MULTILINE)) != len(POLICY_HEADINGS):
        errors.append("POLICY_ENGLISH_SECTION_COUNT")
    if len(re.findall(r"^### 한국어\s*$", text, flags=re.MULTILINE)) != len(POLICY_HEADINGS):
        errors.append("POLICY_KOREAN_SECTION_COUNT")
    normalized = " ".join(text.split())
    for marker in REQUIRED_POLICY_MARKERS:
        if " ".join(marker.split()) not in normalized:
            errors.append(f"POLICY_REQUIRED_MARKER {marker!r}")
    return errors


def _documentation_link_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, target in REQUIRED_POLICY_LINKS.items():
        try:
            text = _read_text(root, relative, max_bytes=MAX_DOCUMENT_BYTES)
        except ContractInputError as exc:
            errors.append(str(exc))
            continue
        if target not in text:
            errors.append(f"POLICY_LINK_MISSING {relative}: {target}")
    for relative, markers in REQUIRED_DOCUMENT_MARKERS.items():
        try:
            text = _read_text(root, relative, max_bytes=MAX_DOCUMENT_BYTES)
        except ContractInputError as exc:
            if str(exc) not in errors:
                errors.append(str(exc))
            continue
        normalized = " ".join(text.split())
        for marker in markers:
            if " ".join(marker.split()) not in normalized:
                errors.append(f"DOCUMENT_REQUIRED_MARKER {relative}: {marker!r}")
    return errors


def validate_repository(
    root: Path = ROOT,
) -> tuple[dict[str, Any] | None, list[Metric], list[str]]:
    metrics: list[Metric] = []
    errors: list[str] = []
    root = Path(root)

    try:
        schema_bytes = _read_regular_bytes(root, SCHEMA_PATH, max_bytes=MAX_CONTRACT_BYTES)
        policy_bytes = _read_regular_bytes(root, POLICY_PATH, max_bytes=MAX_CONTRACT_BYTES)
        source_manifest_bytes = _read_regular_bytes(
            root,
            SOURCE_MANIFEST_PATH,
            max_bytes=MAX_CONTRACT_BYTES,
        )
        schema = strict_json_bytes(schema_bytes, label=str(SCHEMA_PATH))
        policy = strict_json_bytes(policy_bytes, label=str(POLICY_PATH))
        source_manifest = strict_json_bytes(
            source_manifest_bytes,
            label=str(SOURCE_MANIFEST_PATH),
        )
    except ContractInputError as exc:
        metrics.append(Metric("machine contract inputs", "3 safely readable", "failed", False))
        return None, metrics, [str(exc)]

    schema_errors: list[str] = []
    measured_schema_hash = hashlib.sha256(schema_bytes).hexdigest()
    if measured_schema_hash != SCHEMA_SHA256:
        schema_errors.append(f"SCHEMA_SHA256 {measured_schema_hash}; expected {SCHEMA_SHA256}")
    if not isinstance(schema, dict):
        schema_errors.append("SCHEMA_ROOT_NOT_OBJECT")
    elif schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        schema_errors.append("SCHEMA_DIALECT")
    if not isinstance(policy, dict):
        schema_errors.append("POLICY_ROOT_NOT_OBJECT")
    elif isinstance(schema, dict):
        try:
            schema_errors.extend(_schema_errors(policy, schema, schema))
        except ContractInputError as exc:
            schema_errors.append(str(exc))
    if isinstance(policy, dict) and canonical_json_bytes(policy) != policy_bytes:
        schema_errors.append("POLICY_NOT_CANONICAL_JSON")
    metrics.append(
        Metric(
            "machine contract schema",
            "pinned schema; closed canonical version-1 policy; 0 errors",
            f"{len(schema_errors)} errors",
            not schema_errors,
        )
    )
    errors.extend(schema_errors)

    semantic_errors = _contract_semantic_errors(policy) if isinstance(policy, dict) else []
    metrics.append(
        Metric(
            "local-data contract semantics",
            (
                "all storage, data, network, lifecycle, sharing, validation-exclusion, "
                "and open-decision records exact"
            ),
            f"{len(semantic_errors)} errors",
            not semantic_errors,
        )
    )
    errors.extend(semantic_errors)

    source_count = 0
    if isinstance(policy, dict) and isinstance(schema, dict):
        source_count, source_errors = _source_inventory_errors(
            root,
            policy,
            schema,
            source_manifest_bytes,
            source_manifest,
        )
    else:
        source_errors = ["SOURCE_INVENTORY_PREREQUISITE"]
    metrics.append(
        Metric(
            "closed repository source inventory",
            (
                "canonical version-1 manifest; no-follow, stable-identity, bounded "
                "repository reads; exact Python path set and SHA-256 bytes under "
                "packaging, scripts, and src/mclab; real outputs accessed 0"
            ),
            (
                f"{source_count} declared sources; {len(source_errors)} errors; "
                "real outputs accessed 0"
            ),
            not source_errors,
        )
    )
    errors.extend(source_errors)

    network_errors = _network_boundary_errors(root)
    metrics.append(
        Metric(
            "ordinary-run network boundary",
            (
                "within the hash-closed src/mclab Python set, the static remote-client "
                "import scan allows only the explicit asset installer"
            ),
            f"{len(network_errors)} errors",
            not network_errors,
        )
    )
    errors.extend(network_errors)

    policy_doc_errors = _policy_document_errors(root)
    metrics.append(
        Metric(
            "paired English/Korean policy",
            f"{len(POLICY_HEADINGS)}/{len(POLICY_HEADINGS)} paired sections; 0 missing markers",
            f"{len(policy_doc_errors)} errors",
            not policy_doc_errors,
        )
    )
    errors.extend(policy_doc_errors)

    link_errors = _documentation_link_errors(root)
    metrics.append(
        Metric(
            "policy documentation links",
            (
                f"{len(REQUIRED_POLICY_LINKS)}/{len(REQUIRED_POLICY_LINKS)} required "
                "surfaces; required sanitization/SLA markers present"
            ),
            f"{len(link_errors)} errors",
            not link_errors,
        )
    )
    errors.extend(link_errors)
    return policy if isinstance(policy, dict) else None, metrics, errors


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("usage: check_local_data_policy.py", file=sys.stderr)
        return 2
    _policy, metrics, errors = validate_repository(ROOT)
    for metric in metrics:
        status = "PASS" if metric.passed else "FAIL"
        print(f"{status} {metric.name}: threshold={metric.threshold}; measured={metric.measured}")
    for error in errors:
        print(f"ERROR {error}")
    failed = bool(errors) or any(not metric.passed for metric in metrics)
    print("status:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
