#!/usr/bin/env python3
"""Fail-closed protected-main integration transactions.

The command surface is intentionally narrow: validate-policy, preflight,
attest-refresh, mark-ready, and merge. It never reads build/package/output
artifacts and has no release, tag, cleanup, external-contact, or
ruleset-bypass operation.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import errno
import fnmatch
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Protocol, Sequence


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_MARKER = re.compile(
    r"^<!-- protected-integration:v1:pr-(?P<number>[1-9][0-9]*):"
    r"(?P<head>[0-9a-f]{40}):(?P<stage>premerge|postmerge):"
    r"(?P<fingerprint>[0-9a-f]{64}) -->$"
)
INDEPENDENT_REVIEWER_ID = re.compile(r"^/root/[a-z0-9][a-z0-9_]{0,63}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
REVIEWED_RESULT_ENTRY = re.compile(
    r"^100644 blob [0-9a-f]{40}$"
)
MAX_REVIEW_RECEIPT_BYTES = 16 * 1024
REVIEW_CLOCK_SKEW = dt.timedelta(minutes=5)
SUBJECT_REFRESH_NOT_BEFORE = dt.datetime(
    2026, 7, 27, tzinfo=dt.timezone.utc
)
SEMANTIC_INDEX_LINE = re.compile(
    rb"^index [0-9a-f]{4,64}\.\.[0-9a-f]{4,64}(?: [0-7]{6})?\r?\n?$"
)
SEMANTIC_HUNK_LINE = re.compile(
    rb"^@@ -[0-9]+(?:,[0-9]+)? \+[0-9]+(?:,[0-9]+)? @@.*\r?\n?$"
)
FULL_INDEX_LINE = re.compile(
    rb"^index (?P<old>[0-9a-f]{40}|[0-9a-f]{64})"
    rb"\.\.(?P<new>[0-9a-f]{40}|[0-9a-f]{64})"
    rb"(?P<mode> [0-7]{6})?(?P<ending>\r?\n?)$"
)
REPOSITORY_KEYS = {
    "schema_version",
    "policy_id",
    "repository",
    "base_branch",
    "standing_owner_delegation",
    "review_topology",
    "ruleset",
    "queue",
    "denied_paths",
    "denied_capabilities",
}
POLICY_RELATIVE = Path(".agents/integration/protected-main-v1.json")
SCRIPT_RELATIVE = Path("scripts/protected_integration.py")
CANONICAL_POLICY_SHA256 = (
    "424865e9dea0568f98ac5f4f9cf3bde55e01901530945c0ad13dd1da7705d235"
)
STATE_SCHEMA = 1
STATE_DIR = Path("codex/protected-integration/v1")
LOCK_FILE = Path("codex/protected-integration/v1.lock")
COMMAND_TIMEOUT_SECONDS = 120.0
EVIDENCE_PREFIX = "<!-- protected-integration:v1:"
PINNED_OWNER_ID = 68498184
PINNED_OWNER_LOGIN = "ycpiglet"
REQUIRED_DENIED_CAPABILITIES = {
    "release-or-tag",
    "artifact-content-or-download",
    "learner-output-access",
    "cleanup-dry-run-or-apply",
    "external-contact",
    "ruleset-bypass",
    "signing-or-notarization",
    "doi-or-publication",
    "public-beta-or-promotion",
    "participant-recruitment",
    "ruleset-or-security-setting-modification",
    "repository-move-or-layout-change",
    "signing-or-release-credential-acquisition-or-use",
    "signed-or-package-distribution",
}
EXPECTED_REQUIRED_CHECKS = (
    "Simulator lint and tests",
    "Paper citation and formula gates",
    "Paper LaTeX build",
    "Unsigned development build (windows-2025)",
    "Unsigned development build (ubuntu-24.04)",
    "Unsigned development build (macos-15)",
)
SELF_DENIED_PATHS = {
    ".agents/integration/**",
    ".agents/OPERATING_SYSTEM.md",
    ".agents/CURRENT_STATE.md",
    ".agents/READINESS_EXECUTION_PLAN.md",
    "AGENTS.md",
    "scripts/protected_integration.py",
    "tests/test_protected_integration.py",
}


class HarnessError(RuntimeError):
    """A fail-closed policy or transaction error."""


class PendingChecks(HarnessError):
    """Required checks have not all registered or completed yet."""


class CommandError(HarnessError):
    """A local or GitHub CLI command failed."""


@dataclasses.dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str = ""
    returncode: int = 0


@dataclasses.dataclass(frozen=True)
class CommandBytesResult:
    stdout: bytes
    stderr: bytes = b""
    returncode: int = 0


class Runner(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        """Run one command without a shell."""

    def run_bytes(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
    ) -> CommandBytesResult:
        """Run one command without text decoding or newline conversion."""


class SubprocessRunner:
    @staticmethod
    def _environment() -> dict[str, str]:
        environment = os.environ.copy()
        exact_names = {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_CONFIG",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_SYSTEM",
            "GIT_DIFF_OPTS",
            "GIT_DIR",
            "GIT_DISCOVERY_ACROSS_FILESYSTEM",
            "GIT_INDEX_FILE",
            "GIT_NAMESPACE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_QUARANTINE_PATH",
            "GIT_REPLACE_REF_BASE",
            "GIT_SHALLOW_FILE",
            "GIT_WORK_TREE",
        }
        for name in tuple(environment):
            if (
                name in exact_names
                or name.startswith("GIT_CONFIG_KEY_")
                or name.startswith("GIT_CONFIG_VALUE_")
            ):
                environment.pop(name, None)
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        return environment

    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(arguments),
                cwd=cwd,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
                env=self._environment(),
            )
        except subprocess.TimeoutExpired as exc:
            rendered = " ".join(arguments)
            raise CommandError(
                f"command timed out after {COMMAND_TIMEOUT_SECONDS}s: {rendered}"
            ) from exc
        result = CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
        if result.returncode:
            rendered = " ".join(arguments)
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise CommandError(f"command failed ({result.returncode}): {rendered}: {detail}")
        return result

    def run_bytes(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
    ) -> CommandBytesResult:
        try:
            completed = subprocess.run(
                list(arguments),
                cwd=cwd,
                input=input_bytes,
                text=False,
                capture_output=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
                env=self._environment(),
            )
        except subprocess.TimeoutExpired as exc:
            rendered = " ".join(arguments)
            raise CommandError(
                f"command timed out after {COMMAND_TIMEOUT_SECONDS}s: {rendered}"
            ) from exc
        result = CommandBytesResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
        if result.returncode:
            rendered = " ".join(arguments)
            detail = (
                result.stderr.decode("utf-8", errors="replace").strip()
                or result.stdout.decode("utf-8", errors="replace").strip()
                or "no output"
            )
            raise CommandError(f"command failed ({result.returncode}): {rendered}: {detail}")
        return result


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise HarnessError(
            f"{label} keys must be exact; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def _exact_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise HarnessError(f"{label} must be an exact integer")
    return value


def _require_exact_value(value: object, expected: object, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise HarnessError(f"{label} drift: {value!r} != {expected!r}")


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessError(f"{label} must be a non-empty string")
    return value


def exact_sha(value: str) -> str:
    if not HEX40.fullmatch(value):
        raise argparse.ArgumentTypeError("expected a lowercase 40-hex Git SHA")
    return value


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise HarnessError(f"{label} must be an exact UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HarnessError(f"{label} is not a real calendar timestamp") from exc
    if parsed.tzinfo != dt.timezone.utc:
        raise HarnessError(f"{label} is not UTC")
    return parsed


def parse_canonical_review_receipt(value: object) -> Mapping[str, Any]:
    if not isinstance(value, str):
        raise HarnessError("review receipt must be canonical JSON text")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise HarnessError("review receipt is not valid UTF-8") from exc
    if not encoded or len(encoded) > MAX_REVIEW_RECEIPT_BYTES:
        raise HarnessError(
            "review receipt must be non-empty and at most "
            f"{MAX_REVIEW_RECEIPT_BYTES} UTF-8 bytes"
        )
    try:
        document = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HarnessError("review receipt is malformed JSON") from exc
    if not isinstance(document, dict) or canonical_json(document) != value:
        raise HarnessError("review receipt must be a canonical JSON object")
    return document


def _diff_file_sections(raw_diff: bytes) -> list[tuple[bytes, bytes]]:
    sections: list[tuple[bytes, bytes]] = []
    current: list[bytes] = []
    for line in raw_diff.splitlines(keepends=True):
        if line.startswith(b"diff --git "):
            if current:
                header = current[0].removesuffix(b"\n").removesuffix(b"\r")
                sections.append((header, b"".join(current)))
            current = [line]
            continue
        if not current:
            raise HarnessError("semantic patch has data before its first file header")
        current.append(line)
    if current:
        header = current[0].removesuffix(b"\n").removesuffix(b"\r")
        sections.append((header, b"".join(current)))
    if not sections:
        raise HarnessError("semantic patch has no file sections")
    headers = [header for header, _section in sections]
    if len(headers) != len(set(headers)):
        raise HarnessError("patch has duplicate file headers")
    return sections


def sorted_diff_file_sections(raw_diff: bytes) -> bytes:
    return b"".join(
        section for _header, section in sorted(_diff_file_sections(raw_diff))
    )


def reviewed_exact_diff_sha256(raw_diff: bytes) -> str:
    normalized_sections: list[tuple[bytes, bytes]] = []
    for header, section in _diff_file_sections(raw_diff):
        normalized_lines = []
        for line in section.splitlines(keepends=True):
            if not line.startswith(b"index "):
                normalized_lines.append(line)
                continue
            match = FULL_INDEX_LINE.fullmatch(line)
            if match is None or len(match.group("old")) != len(match.group("new")):
                raise HarnessError("canonical exact patch has a malformed index line")
            normalized_lines.append(
                b"index "
                + match.group("old")[:7]
                + b".."
                + match.group("new")[:7]
                + (match.group("mode") or b"")
                + match.group("ending")
            )
        normalized_sections.append((header, b"".join(normalized_lines)))
    normalized = b"".join(
        section for _header, section in sorted(normalized_sections)
    )
    return hashlib.sha256(normalized).hexdigest()


def semantic_patch_sha256(raw_diff: bytes) -> str:
    """Hash a whitespace-preserving patch after rebase-location normalization."""

    normalized_sections = []
    for header, section in _diff_file_sections(raw_diff):
        lines = section.splitlines(keepends=True)
        if not lines or lines[0].removesuffix(b"\n").removesuffix(b"\r") != header:
            raise HarnessError("semantic patch file section is malformed")
        if any(
            line.rstrip(b"\r\n") == b"GIT binary patch"
            or (
                line.startswith(b"Binary files ")
                and line.rstrip(b"\r\n").endswith(b" differ")
            )
            for line in lines
        ):
            raise HarnessError(
                "binary semantic rebases are outside the protected queue contract"
            )
        normalized_sections.append(
            (
                header,
                b"".join(
                    line
                    for line in lines
                    if not SEMANTIC_INDEX_LINE.fullmatch(line)
                    and not SEMANTIC_HUNK_LINE.fullmatch(line)
                ),
            )
        )
    normalized = b"".join(
        section for _header, section in sorted(normalized_sections)
    )
    return hashlib.sha256(normalized).hexdigest()


def owner_attestation_marker(number: int, head: str) -> str:
    return (
        "<!-- protected-integration:v1:owner-attestation:"
        f"pr-{number}:{head} -->"
    )


def owner_attestation_body(
    policy: "Policy",
    item: "QueueItem",
    base: str,
    head: str,
    head_tree: str,
    current_exact_diff_sha256: str,
) -> str:
    topology = policy.review_topology
    marker = owner_attestation_marker(item.number, head)
    return (
        f"{marker}\n"
        "Protected integration v1 owner attestation\n\n"
        f"- Pull request: `#{item.number}`\n"
        f"- Work item: `{item.work_id}`\n"
        f"- Exact base: `{base}`\n"
        f"- Exact head: `{head}`\n"
        f"- Exact head tree: `{head_tree}`\n"
        f"- Reviewed subject base: `{item.reviewed_subject_base}`\n"
        f"- Reviewed subject head: `{item.reviewed_subject_head}`\n"
        f"- Stable patch ID: `{item.stable_patch_id}`\n"
        f"- Semantic patch SHA-256: `{item.semantic_patch_sha256}`\n"
        f"- Current exact diff SHA-256: `{current_exact_diff_sha256}`\n"
        f"- Sorted-NUL changed-path SHA-256: `{item.changed_paths_sha256}`\n"
        f"- Name-status SHA-256: `{item.name_status_sha256}`\n"
        "- Independent read-only agent exact-candidate review: `PASS`\n"
        "- Formal independent human approval: `absent`\n"
        "- Required approvals under the single-collaborator exception: `0`\n"
        "- Standing owner risk acceptance: "
        f"`accepted {topology['owner_risk_acceptance_date']}`\n"
        "- Delegated scope: `fixed protected-main integration queue only`\n\n"
        "This attestation does not authorize public beta or promotion, participant "
        "recruitment, release/tag/DOI, signed or package distribution, signing "
        "or release credential acquisition/use, artifact/package content access, "
        "learner-output access, cleanup "
        "dry-run/apply, repository moves, external contact, or repository "
        "ruleset/security-setting changes."
    )


def subject_refresh_marker(number: int, head: str) -> str:
    return (
        "<!-- protected-integration:v1:subject-refresh:"
        f"pr-{number}:{head} -->"
    )


@dataclasses.dataclass(frozen=True)
class IndependentReviewReceipt:
    payload: Mapping[str, Any]
    sha256: str
    reviewer_id: str
    reviewed_at: str


def subject_refresh_body(
    policy: "Policy",
    item: "QueueItem",
    binding: "ContentBinding",
    head_tree: str,
    receipt: IndependentReviewReceipt,
) -> str:
    marker = subject_refresh_marker(item.number, binding.head_sha)
    payload = {
        "accessed": {
            "artifact_or_package_content": False,
            "credentials": False,
            "learner_outputs": False,
        },
        "binding_mode": binding.binding_mode,
        "changed_paths_sha256": binding.changed_paths_sha256,
        "exact_base": binding.base_sha,
        "exact_diff_sha256": binding.exact_diff_sha256,
        "exact_head": binding.head_sha,
        "exact_head_tree": head_tree,
        "external_contact_performed": False,
        "formal_independent_human_approval": "absent",
        "independent_read_only_agent_review": "PASS",
        "name_status_sha256": binding.name_status_sha256,
        "policy_id": policy.policy_id,
        "policy_reviewed_subject_base": item.reviewed_subject_base,
        "policy_reviewed_subject_head": item.reviewed_subject_head,
        "pull_request": item.number,
        "refresh_generation": 1,
        "refresh_reason": "serial-integration-reconciliation",
        "refreshed_paths": list(binding.refreshed_paths),
        "removed_reviewed_paths": list(binding.removed_reviewed_paths),
        "repository": policy.repository,
        "review_receipt": dict(receipt.payload),
        "review_receipt_sha256": receipt.sha256,
        "semantic_patch_sha256": binding.semantic_patch_sha256,
        "stable_patch_id": binding.stable_patch_id,
        "subject_refresh_accepted_date": policy.delegation[
            "subject_refresh_accepted_date"
        ],
        "work_id": item.work_id,
    }
    return (
        f"{marker}\n"
        "Protected integration v1 subject refresh certificate\n\n"
        f"{canonical_json(payload)}"
    )


def refreshed_owner_attestation_body(
    policy: "Policy",
    item: "QueueItem",
    binding: "ContentBinding",
    head_tree: str,
    refresh: "RefreshCertificate",
) -> str:
    topology = policy.review_topology
    marker = owner_attestation_marker(item.number, binding.head_sha)
    return (
        f"{marker}\n"
        "Protected integration v1 owner attestation\n\n"
        f"- Pull request: `#{item.number}`\n"
        f"- Work item: `{item.work_id}`\n"
        f"- Exact base: `{binding.base_sha}`\n"
        f"- Exact head: `{binding.head_sha}`\n"
        f"- Exact head tree: `{head_tree}`\n"
        f"- Reviewed subject base: `{item.reviewed_subject_base}`\n"
        f"- Reviewed subject head: `{item.reviewed_subject_head}`\n"
        f"- Binding mode: `{binding.binding_mode}`\n"
        f"- Stable patch ID: `{binding.stable_patch_id}`\n"
        f"- Semantic patch SHA-256: `{binding.semantic_patch_sha256}`\n"
        f"- Current exact diff SHA-256: `{binding.exact_diff_sha256}`\n"
        f"- Sorted-NUL changed-path SHA-256: `{binding.changed_paths_sha256}`\n"
        f"- Name-status SHA-256: `{binding.name_status_sha256}`\n"
        f"- Subject refresh comment ID: `{refresh.comment_id}`\n"
        f"- Subject refresh body SHA-256: `{refresh.body_sha256}`\n"
        f"- Independent review receipt SHA-256: `{refresh.review_receipt_sha256}`\n"
        "- Subject-refresh authority: "
        f"`accepted {policy.delegation['subject_refresh_accepted_date']}; "
        f"generation {policy.delegation['subject_refresh_generation']}`\n"
        "- Independent read-only agent exact-candidate review: `PASS`\n"
        "- Formal independent human approval: `absent`\n"
        "- Required approvals under the single-collaborator exception: `0`\n"
        "- Standing owner risk acceptance: "
        f"`accepted {topology['owner_risk_acceptance_date']}`\n"
        "- Delegated scope: `fixed protected-main integration queue only`\n\n"
        "This attestation does not authorize public beta or promotion, participant "
        "recruitment, release/tag/DOI, signed or package distribution, signing "
        "or release credential acquisition/use, artifact/package content access, "
        "learner-output access, cleanup dry-run/apply, repository moves, external "
        "contact, or repository ruleset/security-setting changes."
    )


@dataclasses.dataclass(frozen=True)
class QueueItem:
    number: int
    work_id: str
    branch: str
    reviewed_subject_base: str
    reviewed_subject_head: str
    stable_patch_id: str
    semantic_patch_sha256: str
    changed_paths_sha256: str
    reviewed_exact_diff_sha256: str
    name_status_sha256: str
    accepted_integration: Mapping[str, Any] | None
    allowed_paths: tuple[str, ...]
    reviewed_changed_paths: tuple[str, ...]
    reviewed_result_entries: Mapping[str, str | None]
    refreshable_paths: tuple[str, ...]
    locked_paths: tuple[str, ...]
    locked_semantic_patch_sha256: str
    locked_name_status_sha256: str
    completion_claim: str


@dataclasses.dataclass(frozen=True)
class Policy:
    policy_id: str
    repository: str
    base_branch: str
    ruleset_id: int
    ruleset_name: str
    actions_app_id: int
    required_checks: tuple[str, ...]
    queue: tuple[QueueItem, ...]
    denied_paths: tuple[str, ...]
    denied_capabilities: tuple[str, ...]
    delegation: Mapping[str, Any]
    review_topology: Mapping[str, Any]

    @classmethod
    def load(
        cls, path: Path, *, enforce_canonical_fingerprint: bool = True
    ) -> "Policy":
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise HarnessError(f"cannot read policy {path}: {exc}") from exc
        if len(raw) > 256 * 1024:
            raise HarnessError("policy exceeds the 256 KiB limit")
        if (
            enforce_canonical_fingerprint
            and hashlib.sha256(raw).hexdigest() != CANONICAL_POLICY_SHA256
        ):
            raise HarnessError(
                "policy fingerprint differs from the authority pinned in the harness"
            )
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HarnessError(f"policy is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise HarnessError("policy root must be an object")
        _exact_keys(document, REPOSITORY_KEYS, "policy")
        if _exact_int(document["schema_version"], "schema_version") != 1:
            raise HarnessError("unsupported policy schema_version")
        if document["policy_id"] != "protected-main-v1":
            raise HarnessError("policy_id must be protected-main-v1")

        repository = _nonempty_string(document["repository"], "repository")
        if repository != "ycpiglet/manipulator-control-tutorial":
            raise HarnessError("repository identity drift")
        base_branch = _nonempty_string(document["base_branch"], "base_branch")
        if base_branch != "main":
            raise HarnessError("base_branch must be main")

        delegation = document["standing_owner_delegation"]
        if not isinstance(delegation, dict):
            raise HarnessError("standing_owner_delegation must be an object")
        _exact_keys(
            delegation,
            {
                "accepted_date",
                "scope",
                "activation",
                "already_integrated_prefix_allowed",
                "self_amendment_authority",
                "subject_refresh_accepted_date",
                "subject_refresh_generation",
                "subject_refresh_human_reprompt_required",
            },
            "standing_owner_delegation",
        )
        if delegation["accepted_date"] != "2026-07-26":
            raise HarnessError("standing delegation date drift")
        if delegation["scope"] != "fixed protected-main integration queue only":
            raise HarnessError("standing delegation scope drift")
        if (
            delegation["activation"]
            != "only after this policy and harness are accepted on protected main"
        ):
            raise HarnessError("standing delegation activation drift")
        if delegation["already_integrated_prefix_allowed"] is not True:
            raise HarnessError("already-integrated queue prefix must remain allowed")
        if delegation["self_amendment_authority"] is not False:
            raise HarnessError("the harness cannot authorize its own amendment")
        if delegation["subject_refresh_accepted_date"] != "2026-07-27":
            raise HarnessError("subject-refresh delegation date drift")
        if (
            _exact_int(
                delegation["subject_refresh_generation"],
                "standing_owner_delegation.subject_refresh_generation",
            )
            != 1
        ):
            raise HarnessError("only subject-refresh generation 1 is authorized")
        if delegation["subject_refresh_human_reprompt_required"] is not False:
            raise HarnessError(
                "fixed-queue subject refresh must not require another human prompt"
            )

        review_topology = document["review_topology"]
        if not isinstance(review_topology, dict):
            raise HarnessError("review_topology must be an object")
        _exact_keys(
            review_topology,
            {
                "direct_collaborators",
                "required_approvals",
                "formal_independent_human_approval",
                "owner_id",
                "owner_login",
                "owner_risk_acceptance_date",
                "exact_head_independent_agent_attestation_required",
            },
            "review_topology",
        )
        if _exact_int(
            review_topology["direct_collaborators"],
            "review_topology.direct_collaborators",
        ) != 1:
            raise HarnessError("direct collaborator topology drift")
        if _exact_int(
            review_topology["required_approvals"],
            "review_topology.required_approvals",
        ) != 0:
            raise HarnessError("required approvals must remain zero for this topology")
        if review_topology["formal_independent_human_approval"] is not False:
            raise HarnessError("formal independent human approval must remain false")
        if (
            _exact_int(review_topology["owner_id"], "review_topology.owner_id")
            != PINNED_OWNER_ID
        ):
            raise HarnessError("owner account ID drift")
        if review_topology["owner_login"] != PINNED_OWNER_LOGIN:
            raise HarnessError("owner login drift")
        if review_topology["owner_risk_acceptance_date"] != "2026-07-26":
            raise HarnessError("owner risk-acceptance date drift")
        if (
            review_topology["exact_head_independent_agent_attestation_required"]
            is not True
        ):
            raise HarnessError("exact-head independent-agent attestation is mandatory")

        ruleset = document["ruleset"]
        if not isinstance(ruleset, dict):
            raise HarnessError("ruleset must be an object")
        _exact_keys(
            ruleset,
            {"id", "name", "github_actions_app_id", "required_checks"},
            "ruleset",
        )
        ruleset_id = _exact_int(ruleset["id"], "ruleset.id")
        actions_app_id = _exact_int(
            ruleset["github_actions_app_id"], "ruleset.github_actions_app_id"
        )
        if ruleset_id != 19209773 or actions_app_id != 15368:
            raise HarnessError("ruleset identity or GitHub Actions app drift")
        ruleset_name = _nonempty_string(ruleset["name"], "ruleset.name")
        checks = ruleset["required_checks"]
        if not isinstance(checks, list) or not checks:
            raise HarnessError("required_checks must be a non-empty array")
        required_checks = tuple(
            _nonempty_string(item, "required_checks item") for item in checks
        )
        if required_checks != EXPECTED_REQUIRED_CHECKS:
            raise HarnessError("required_checks must equal the six governed contexts")

        queue_raw = document["queue"]
        if not isinstance(queue_raw, list) or not queue_raw:
            raise HarnessError("queue must be a non-empty array")
        queue: list[QueueItem] = []
        for index, raw_item in enumerate(queue_raw):
            if not isinstance(raw_item, dict):
                raise HarnessError(f"queue[{index}] must be an object")
            _exact_keys(
                raw_item,
                {
                    "number",
                    "work_id",
                    "branch",
                    "reviewed_subject_base",
                    "reviewed_subject_head",
                    "stable_patch_id",
                    "semantic_patch_sha256",
                    "changed_paths_sha256",
                    "reviewed_exact_diff_sha256",
                    "name_status_sha256",
                    "accepted_integration",
                    "allowed_paths",
                    "reviewed_changed_paths",
                    "reviewed_result_entries",
                    "refreshable_paths",
                    "locked_paths",
                    "locked_semantic_patch_sha256",
                    "locked_name_status_sha256",
                    "completion_claim",
                },
                f"queue[{index}]",
            )
            allowed = raw_item["allowed_paths"]
            if not isinstance(allowed, list) or not allowed:
                raise HarnessError(f"queue[{index}].allowed_paths must be non-empty")
            reviewed_paths_raw = raw_item["reviewed_changed_paths"]
            reviewed_result_entries_raw = raw_item["reviewed_result_entries"]
            refreshable_raw = raw_item["refreshable_paths"]
            locked_raw = raw_item["locked_paths"]
            if not isinstance(reviewed_paths_raw, list) or not reviewed_paths_raw:
                raise HarnessError(
                    f"queue[{index}].reviewed_changed_paths must be non-empty"
                )
            if (
                not isinstance(reviewed_result_entries_raw, dict)
                or not isinstance(refreshable_raw, list)
                or not isinstance(locked_raw, list)
            ):
                raise HarnessError(
                    f"queue[{index}] reviewed_result_entries must be an object "
                    "and refreshable_paths/locked_paths must be arrays"
                )
            number = _exact_int(raw_item["number"], f"queue[{index}].number")
            reviewed_subject_base = _nonempty_string(
                raw_item["reviewed_subject_base"],
                f"queue[{index}].reviewed_subject_base",
            )
            reviewed_subject_head = _nonempty_string(
                raw_item["reviewed_subject_head"],
                f"queue[{index}].reviewed_subject_head",
            )
            stable_patch_id = _nonempty_string(
                raw_item["stable_patch_id"], f"queue[{index}].stable_patch_id"
            )
            semantic_patch_digest = _nonempty_string(
                raw_item["semantic_patch_sha256"],
                f"queue[{index}].semantic_patch_sha256",
            )
            changed_paths_sha256 = _nonempty_string(
                raw_item["changed_paths_sha256"],
                f"queue[{index}].changed_paths_sha256",
            )
            reviewed_exact_diff_sha256 = _nonempty_string(
                raw_item["reviewed_exact_diff_sha256"],
                f"queue[{index}].reviewed_exact_diff_sha256",
            )
            name_status_sha256 = _nonempty_string(
                raw_item["name_status_sha256"],
                f"queue[{index}].name_status_sha256",
            )
            locked_semantic_patch_sha256 = _nonempty_string(
                raw_item["locked_semantic_patch_sha256"],
                f"queue[{index}].locked_semantic_patch_sha256",
            )
            locked_name_status_sha256 = _nonempty_string(
                raw_item["locked_name_status_sha256"],
                f"queue[{index}].locked_name_status_sha256",
            )
            if not HEX40.fullmatch(reviewed_subject_base):
                raise HarnessError(
                    f"queue[{index}] reviewed subject base must be 40-hex"
                )
            if not HEX40.fullmatch(reviewed_subject_head):
                raise HarnessError(
                    f"queue[{index}] reviewed subject head must be 40-hex"
                )
            if not HEX40.fullmatch(stable_patch_id):
                raise HarnessError(f"queue[{index}] stable patch ID must be 40-hex")
            if not HEX64.fullmatch(semantic_patch_digest):
                raise HarnessError(
                    f"queue[{index}] semantic patch digest must be 64-hex"
                )
            if not HEX64.fullmatch(changed_paths_sha256):
                raise HarnessError(f"queue[{index}] path digest must be 64-hex")
            if not HEX64.fullmatch(reviewed_exact_diff_sha256):
                raise HarnessError(
                    f"queue[{index}] reviewed exact diff digest must be 64-hex"
                )
            if not HEX64.fullmatch(name_status_sha256):
                raise HarnessError(
                    f"queue[{index}] name-status digest must be 64-hex"
                )
            if not HEX64.fullmatch(locked_semantic_patch_sha256):
                raise HarnessError(
                    f"queue[{index}] locked semantic digest must be 64-hex"
                )
            if not HEX64.fullmatch(locked_name_status_sha256):
                raise HarnessError(
                    f"queue[{index}] locked name-status digest must be 64-hex"
                )
            reviewed_changed_paths = tuple(
                _validated_exact_path(
                    value, f"queue[{index}].reviewed_changed_paths"
                )
                for value in reviewed_paths_raw
            )
            refreshable_paths = tuple(
                _validated_exact_path(value, f"queue[{index}].refreshable_paths")
                for value in refreshable_raw
            )
            locked_paths = tuple(
                _validated_exact_path(value, f"queue[{index}].locked_paths")
                for value in locked_raw
            )
            reviewed_result_entries: dict[str, str | None] = {}
            if list(reviewed_result_entries_raw) != sorted(
                reviewed_result_entries_raw
            ):
                raise HarnessError(
                    f"queue[{index}].reviewed_result_entries keys must be sorted"
                )
            for raw_path, raw_entry in reviewed_result_entries_raw.items():
                path = _validated_exact_path(
                    raw_path,
                    f"queue[{index}].reviewed_result_entries",
                )
                if raw_entry is not None and (
                    not isinstance(raw_entry, str)
                    or REVIEWED_RESULT_ENTRY.fullmatch(raw_entry) is None
                ):
                    raise HarnessError(
                        f"queue[{index}].reviewed_result_entries[{path!r}] "
                        "must be null or an exact non-executable blob identity"
                    )
                reviewed_result_entries[path] = raw_entry
            for label, values in (
                ("reviewed_changed_paths", reviewed_changed_paths),
                ("refreshable_paths", refreshable_paths),
                ("locked_paths", locked_paths),
            ):
                if len(values) != len(set(values)) or tuple(sorted(values)) != values:
                    raise HarnessError(
                        f"queue[{index}].{label} must be sorted and unique"
                    )
            if set(locked_paths) & set(refreshable_paths):
                raise HarnessError(
                    f"queue[{index}] locked and refreshable paths overlap"
                )
            if set(reviewed_changed_paths) != (
                set(locked_paths) | (set(reviewed_changed_paths) & set(refreshable_paths))
            ):
                raise HarnessError(
                    f"queue[{index}] reviewed paths are not partitioned by "
                    "locked/refreshable paths"
                )
            expected_result_paths = set(reviewed_changed_paths) & set(
                refreshable_paths
            )
            if set(reviewed_result_entries) != expected_result_paths:
                raise HarnessError(
                    f"queue[{index}] reviewed result entries do not equal the "
                    "refreshable reviewed-path set"
                )
            accepted_raw = raw_item["accepted_integration"]
            accepted: Mapping[str, Any] | None
            if accepted_raw is None:
                accepted = None
            else:
                if not isinstance(accepted_raw, dict):
                    raise HarnessError(
                        f"queue[{index}].accepted_integration must be object or null"
                    )
                _exact_keys(
                    accepted_raw,
                    {
                        "source_base",
                        "source_head",
                        "merge_sha",
                        "tree",
                        "owner_completion_comment",
                    },
                    f"queue[{index}].accepted_integration",
                )
                for key in ("source_base", "source_head", "merge_sha", "tree"):
                    value = accepted_raw[key]
                    if not isinstance(value, str) or not HEX40.fullmatch(value):
                        raise HarnessError(
                            f"queue[{index}].accepted_integration.{key} "
                            "must be lowercase 40-hex"
                        )
                completion = accepted_raw["owner_completion_comment"]
                if not isinstance(completion, dict):
                    raise HarnessError(
                        f"queue[{index}].accepted_integration."
                        "owner_completion_comment must be an object"
                    )
                _exact_keys(
                    completion,
                    {
                        "id",
                        "marker",
                        "body_sha256",
                        "author_id",
                        "author_login",
                        "created_at",
                        "updated_at",
                    },
                    f"queue[{index}].accepted_integration.owner_completion_comment",
                )
                if _exact_int(
                    completion["id"],
                    f"queue[{index}] owner completion comment id",
                ) <= 0:
                    raise HarnessError("owner completion comment ID must be positive")
                if _exact_int(
                    completion["author_id"],
                    f"queue[{index}] owner completion comment author_id",
                ) <= 0:
                    raise HarnessError(
                        "owner completion comment author ID must be positive"
                    )
                _nonempty_string(
                    completion["marker"],
                    f"queue[{index}] owner completion comment marker",
                )
                body_digest = _nonempty_string(
                    completion["body_sha256"],
                    f"queue[{index}] owner completion comment body_sha256",
                )
                if not HEX64.fullmatch(body_digest):
                    raise HarnessError(
                        "owner completion comment body digest must be 64-hex"
                    )
                for key in ("author_login", "created_at", "updated_at"):
                    _nonempty_string(
                        completion[key],
                        f"queue[{index}] owner completion comment {key}",
                    )
                accepted = {
                    **{
                        key: accepted_raw[key]
                        for key in ("source_base", "source_head", "merge_sha", "tree")
                    },
                    "owner_completion_comment": dict(completion),
                }
            item = QueueItem(
                number=number,
                work_id=_nonempty_string(
                    raw_item["work_id"], f"queue[{index}].work_id"
                ),
                branch=_nonempty_string(raw_item["branch"], f"queue[{index}].branch"),
                reviewed_subject_base=reviewed_subject_base,
                reviewed_subject_head=reviewed_subject_head,
                stable_patch_id=stable_patch_id,
                semantic_patch_sha256=semantic_patch_digest,
                changed_paths_sha256=changed_paths_sha256,
                reviewed_exact_diff_sha256=reviewed_exact_diff_sha256,
                name_status_sha256=name_status_sha256,
                accepted_integration=accepted,
                allowed_paths=tuple(
                    _validated_pattern(pattern, f"queue[{index}].allowed_paths")
                    for pattern in allowed
                ),
                reviewed_changed_paths=reviewed_changed_paths,
                reviewed_result_entries=reviewed_result_entries,
                refreshable_paths=refreshable_paths,
                locked_paths=locked_paths,
                locked_semantic_patch_sha256=locked_semantic_patch_sha256,
                locked_name_status_sha256=locked_name_status_sha256,
                completion_claim=_nonempty_string(
                    raw_item["completion_claim"],
                    f"queue[{index}].completion_claim",
                ),
            )
            queue.append(item)
        expected_queue = [
            (74, "LIC-01B", "agent/lic01b-reviewed-notices"),
            (75, "OPS-01A", "agent/ops01a-local-data-policy-current"),
            (72, "EDU-01A", "agent/edu01a-educator-kit-current"),
            (73, "PKG-01B", "agent/pkg01b-packaged-startup"),
            (70, "E2E-01", "agent/packaged-e2e"),
            (76, "MAINT-01A", "agent/maint01a-mypy-baseline-current"),
        ]
        actual_queue = [(item.number, item.work_id, item.branch) for item in queue]
        if actual_queue != expected_queue:
            raise HarnessError("fixed integration queue identity or order drift")
        if queue[0].accepted_integration != {
            "source_base": "03499fb3ad974aec3ea28bb8bcce2595b68a0661",
            "source_head": "6cd191f0b87bb582bfde4764234a570a7f601da4",
            "merge_sha": "9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88",
            "tree": "e5625718c0bcd1030bba9ea938a438d927d4033e",
            "owner_completion_comment": {
                "id": 5083778171,
                "marker": (
                    "<!-- protected-integration:manual-v1:pr-74:"
                    "9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88 -->"
                ),
                "body_sha256": (
                    "1fa5077dc746b0997d59d0d5de355d8222c415e2318b5c3d1494e7bb43f3df20"
                ),
                "author_id": 68498184,
                "author_login": "ycpiglet",
                "created_at": "2026-07-26T13:54:54Z",
                "updated_at": "2026-07-26T13:54:54Z",
            },
        }:
            raise HarnessError("PR #74 accepted-integration bootstrap pin drift")
        if any(item.accepted_integration is not None for item in queue[1:]):
            raise HarnessError("pending queue items must not claim accepted integration")
        if queue[0].refreshable_paths:
            raise HarnessError("accepted bootstrap item cannot be subject-refreshable")
        if any(not item.refreshable_paths for item in queue[1:]):
            raise HarnessError(
                "every pending fixed-queue item must have an exact refresh envelope"
            )
        expected_completion_claims = {
            74: "LIC-01B bounded safe-main development baseline",
            75: "OPS-01A bounded safe-main development baseline",
            72: "EDU-01A bounded safe-main development baseline",
            73: "PKG-01 aggregate bounded safe-main development baseline",
            70: "E2E-01 bounded safe-main development baseline",
            76: "MAINT-01A bounded safe-main development baseline",
        }
        if {
            item.number: item.completion_claim for item in queue
        } != expected_completion_claims:
            raise HarnessError("fixed-queue completion claims drift")

        denied_raw = document["denied_paths"]
        capabilities_raw = document["denied_capabilities"]
        if not isinstance(denied_raw, list) or not isinstance(capabilities_raw, list):
            raise HarnessError("denied_paths and denied_capabilities must be arrays")
        denied_paths = tuple(
            _validated_pattern(pattern, "denied_paths") for pattern in denied_raw
        )
        denied_capabilities = tuple(
            _nonempty_string(item, "denied_capabilities item")
            for item in capabilities_raw
        )
        if not SELF_DENIED_PATHS.issubset(denied_paths):
            raise HarnessError("self-amendment paths must remain explicitly denied")
        if not REQUIRED_DENIED_CAPABILITIES.issubset(denied_capabilities):
            raise HarnessError("one or more mandatory denied capabilities is absent")
        for item in queue:
            overlap = [
                pattern for pattern in item.allowed_paths if pattern in SELF_DENIED_PATHS
            ]
            if overlap:
                raise HarnessError(
                    f"queue item {item.number} grants self-amendment paths: {overlap}"
                )
            for path in (
                *item.reviewed_changed_paths,
                *item.refreshable_paths,
                *item.locked_paths,
            ):
                if any(path_matches(path, pattern) for pattern in denied_paths):
                    raise HarnessError(
                        f"queue item {item.number} refresh metadata includes denied "
                        f"path: {path}"
                    )
                if not any(
                    path_matches(path, pattern) for pattern in item.allowed_paths
                ):
                    raise HarnessError(
                        f"queue item {item.number} refresh metadata exceeds its "
                        f"allowed path envelope: {path}"
                    )
        return cls(
            policy_id=document["policy_id"],
            repository=repository,
            base_branch=base_branch,
            ruleset_id=ruleset_id,
            ruleset_name=ruleset_name,
            actions_app_id=actions_app_id,
            required_checks=required_checks,
            queue=tuple(queue),
            denied_paths=denied_paths,
            denied_capabilities=denied_capabilities,
            delegation=delegation,
            review_topology=review_topology,
        )

    def item(self, number: int) -> QueueItem:
        for item in self.queue:
            if item.number == number:
                return item
        raise HarnessError(f"PR #{number} is outside the fixed integration queue")


def _validated_pattern(value: object, label: str) -> str:
    pattern = _nonempty_string(value, label)
    if (
        "\x00" in pattern
        or "\\" in pattern
        or pattern.startswith("/")
        or ".." in PurePosixPath(pattern).parts
    ):
        raise HarnessError(f"{label} contains an unsafe path pattern: {pattern!r}")
    return pattern


def _validated_exact_path(value: object, label: str) -> str:
    path = _validated_pattern(value, label)
    if (
        any(character in path for character in "*?[")
        or path != PurePosixPath(path).as_posix()
        or path in {".", ""}
    ):
        raise HarnessError(f"{label} must be an exact path, not a pattern: {path!r}")
    return path


def path_matches(path: str, pattern: str) -> bool:
    path_parts = PurePosixPath(path).parts
    pattern_parts = PurePosixPath(pattern).parts

    def matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return matches(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and matches(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], pattern_part)
            and matches(path_index + 1, pattern_index + 1)
        )

    return matches(0, 0)


def validate_changed_paths(
    changed_paths: Sequence[str], item: QueueItem, denied_paths: Sequence[str]
) -> None:
    if not changed_paths:
        raise HarnessError("candidate has no changed paths")
    seen: set[str] = set()
    for path in changed_paths:
        if (
            not path
            or path in seen
            or "\x00" in path
            or "\n" in path
            or "\r" in path
            or "\\" in path
            or path.startswith("/")
            or ".." in PurePosixPath(path).parts
        ):
            raise HarnessError(f"invalid or duplicate changed path: {path!r}")
        seen.add(path)
        if any(path_matches(path, pattern) for pattern in denied_paths):
            raise HarnessError(f"changed path is explicitly denied: {path}")
        if not any(path_matches(path, pattern) for pattern in item.allowed_paths):
            raise HarnessError(
                f"changed path is outside PR #{item.number} envelope: {path}"
            )


def validate_ruleset(document: Mapping[str, Any], policy: Policy) -> None:
    if document.get("id") != policy.ruleset_id:
        raise HarnessError("live ruleset ID drift")
    if document.get("name") != policy.ruleset_name:
        raise HarnessError("live ruleset name drift")
    if document.get("enforcement") != "active" or document.get("target") != "branch":
        raise HarnessError("live ruleset is not an active branch ruleset")
    conditions = document.get("conditions")
    if not isinstance(conditions, dict):
        raise HarnessError("live ruleset conditions missing")
    ref_name = conditions.get("ref_name")
    expected_ref = f"refs/heads/{policy.base_branch}"
    if not isinstance(ref_name, dict) or ref_name.get("include") != [expected_ref]:
        raise HarnessError("live ruleset target branch drift")
    if ref_name.get("exclude") != []:
        raise HarnessError("live ruleset has unexpected ref exclusions")
    bypass = document.get("bypass_actors")
    if bypass != [
        {
            "actor_id": 5,
            "actor_type": "RepositoryRole",
            "bypass_mode": "pull_request",
        }
    ]:
        raise HarnessError("live ruleset bypass policy drift")

    rules_raw = document.get("rules")
    if not isinstance(rules_raw, list):
        raise HarnessError("live ruleset rules missing")
    by_type: dict[str, Mapping[str, Any]] = {}
    for raw in rules_raw:
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            raise HarnessError("malformed live ruleset rule")
        rule_type = raw["type"]
        if rule_type in by_type:
            raise HarnessError(f"duplicate live ruleset rule: {rule_type}")
        by_type[rule_type] = raw
    expected_types = {
        "deletion",
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    }
    if set(by_type) != expected_types:
        raise HarnessError("live ruleset rule set drift")

    pull_parameters = by_type["pull_request"].get("parameters")
    if not isinstance(pull_parameters, dict):
        raise HarnessError("pull-request rule parameters missing")
    required_pull_values = {
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
    }
    for key, expected in required_pull_values.items():
        if pull_parameters.get(key) != expected:
            raise HarnessError(f"pull-request rule drift: {key}")

    status_parameters = by_type["required_status_checks"].get("parameters")
    if not isinstance(status_parameters, dict):
        raise HarnessError("required-status-check parameters missing")
    if status_parameters.get("strict_required_status_checks_policy") is not True:
        raise HarnessError("strict/up-to-date status checks are not active")
    checks_raw = status_parameters.get("required_status_checks")
    if not isinstance(checks_raw, list):
        raise HarnessError("ruleset required checks missing")
    observed: list[tuple[str, int]] = []
    for check in checks_raw:
        if not isinstance(check, dict):
            raise HarnessError("malformed ruleset required check")
        observed.append((check.get("context"), check.get("integration_id")))
    expected_checks = [
        (context, policy.actions_app_id) for context in policy.required_checks
    ]
    if observed != expected_checks:
        raise HarnessError("ruleset required check contexts/app/order drift")


def validate_check_runs(
    document: Mapping[str, Any], expected_sha: str, policy: Policy
) -> dict[str, int]:
    total = document.get("total_count")
    runs = document.get("check_runs")
    if type(total) is not int or not isinstance(runs, list):
        raise HarnessError("malformed check-runs response")
    if total < 0 or total > 100:
        raise HarnessError("check-runs total_count is outside the complete-page bound")
    if total != len(runs):
        raise HarnessError("check-runs total_count does not equal returned page length")
    matching: dict[str, list[Mapping[str, Any]]] = {
        context: [] for context in policy.required_checks
    }
    observed_ids: set[int] = set()
    for raw in runs:
        if not isinstance(raw, dict):
            raise HarnessError("malformed check run")
        check_id = _exact_int(raw.get("id"), "check-run id")
        if check_id <= 0:
            raise HarnessError("check-run IDs must be positive")
        if check_id in observed_ids:
            raise HarnessError(f"duplicate check-run ID: {check_id}")
        observed_ids.add(check_id)
        name = raw.get("name")
        if name not in matching:
            continue
        if raw.get("head_sha") != expected_sha:
            raise HarnessError(f"required check {name!r} is bound to the wrong SHA")
        app = raw.get("app")
        if (
            not isinstance(app, dict)
            or type(app.get("id")) is not int
            or app.get("id") != policy.actions_app_id
        ):
            raise HarnessError(f"required check {name!r} has the wrong app identity")
        matching[name].append(raw)

    evidence: dict[str, int] = {}
    pending: list[str] = []
    for context in policy.required_checks:
        candidates = matching[context]
        if not candidates:
            pending.append(f"{context}:missing")
            continue
        if len(candidates) != 1:
            raise HarnessError(f"ambiguous duplicate required check: {context!r}")
        latest = candidates[0]
        check_id = _exact_int(latest["id"], f"check {context} id")
        status = latest.get("status")
        conclusion = latest.get("conclusion")
        if status != "completed":
            pending.append(f"{context}:{status}")
            continue
        if conclusion != "success":
            raise HarnessError(
                f"required check {context!r} completed with {conclusion!r}"
            )
        evidence[context] = check_id
    if pending:
        raise PendingChecks("required checks pending: " + ", ".join(pending))
    if tuple(evidence) != policy.required_checks:
        raise HarnessError("required check evidence order drift")
    return evidence


class GitHubGateway(Protocol):
    def pull(self, number: int) -> Mapping[str, Any]: ...

    def ruleset(self, ruleset_id: int) -> Mapping[str, Any]: ...

    def check_runs(self, sha: str) -> Mapping[str, Any]: ...

    def review_threads(self, number: int) -> Sequence[Mapping[str, Any]]: ...

    def reviews(self, number: int) -> Sequence[Mapping[str, Any]]: ...

    def comments(self, number: int) -> Sequence[Mapping[str, Any]]: ...

    def direct_collaborators(self) -> Sequence[Mapping[str, Any]]: ...

    def authenticated_user(self) -> Mapping[str, Any]: ...

    def mark_ready(self, pull_node_id: str) -> None: ...

    def merge(self, number: int, expected_head: str) -> Mapping[str, Any]: ...

    def ensure_premerge_evidence(
        self, policy: Policy, evidence: CandidateEvidence
    ) -> bool: ...

    def ensure_postmerge_evidence(
        self,
        number: int,
        head: str,
        evidence: Mapping[str, Any],
    ) -> bool: ...

    def ensure_subject_refresh_comment(
        self,
        policy: Policy,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        receipt: IndependentReviewReceipt,
    ) -> bool: ...

    def ensure_refreshed_owner_attestation(
        self,
        policy: Policy,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        refresh: RefreshCertificate,
    ) -> bool: ...


class GitHubClient:
    def __init__(self, runner: Runner, repository: str) -> None:
        self.runner = runner
        self.repository = repository
        self.owner, self.name = repository.split("/", 1)

    def _api(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        fields: Mapping[str, object] | None = None,
    ) -> Any:
        self._validate_api_endpoint(method, endpoint)
        arguments = [
            "gh",
            "api",
            "--hostname",
            "github.com",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            "--method",
            method,
            endpoint,
        ]
        input_text = None
        if fields is not None:
            arguments.extend(["--input", "-"])
            input_text = canonical_json(fields)
        result = self.runner.run(arguments, input_text=input_text)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CommandError(f"GitHub API returned malformed JSON: {endpoint}") from exc

    def _graphql(self, operation: str, variables: Mapping[str, object]) -> Any:
        queries = {
            "review_threads": """
                query($owner:String!, $name:String!, $number:Int!) {
                  repository(owner:$owner, name:$name) {
                    pullRequest(number:$number) {
                      reviewThreads(first:100) {
                        pageInfo { hasNextPage }
                        nodes { id isResolved isOutdated }
                      }
                    }
                  }
                }
            """,
            "mark_ready": """
                mutation($pullRequestId:ID!) {
                  markPullRequestReadyForReview(
                    input:{pullRequestId:$pullRequestId}
                  ) { pullRequest { id isDraft } }
                }
            """,
        }
        try:
            query = queries[operation]
        except KeyError as exc:
            raise HarnessError(f"GraphQL operation is not allowlisted: {operation}") from exc
        payload = {"query": query, "variables": dict(variables)}
        result = self.runner.run(
            [
                "gh",
                "api",
                "--hostname",
                "github.com",
                "-H",
                "Accept: application/vnd.github+json",
                "-H",
                "X-GitHub-Api-Version: 2022-11-28",
                "--method",
                "POST",
                "graphql",
                "--input",
                "-",
            ],
            input_text=canonical_json(payload),
        )
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CommandError("GitHub GraphQL returned malformed JSON") from exc
        if not isinstance(document, dict) or document.get("errors"):
            raise CommandError(f"GitHub GraphQL error: {document!r}")
        return document

    def _validate_api_endpoint(self, method: str, endpoint: str) -> None:
        repository = re.escape(self.repository)
        sha = r"[0-9a-f]{40}"
        number = r"[1-9][0-9]*"
        allowed = {
            (
                "GET",
                rf"repos/{repository}/pulls/{number}",
            ),
            (
                "GET",
                rf"repos/{repository}/rulesets/[1-9][0-9]*",
            ),
            (
                "GET",
                rf"repos/{repository}/commits/{sha}/check-runs"
                r"\?filter=latest&per_page=100",
            ),
            (
                "GET",
                rf"repos/{repository}/pulls/{number}/reviews\?per_page=100",
            ),
            (
                "GET",
                rf"repos/{repository}/issues/{number}/comments\?per_page=100",
            ),
            (
                "GET",
                rf"repos/{repository}/collaborators"
                r"\?affiliation=direct&per_page=100",
            ),
            ("GET", r"user"),
            (
                "POST",
                rf"repos/{repository}/issues/{number}/comments",
            ),
            (
                "PUT",
                rf"repos/{repository}/pulls/{number}/merge",
            ),
        }
        if not any(
            method == candidate and re.fullmatch(pattern, endpoint)
            for candidate, pattern in allowed
        ):
            raise HarnessError(f"GitHub API endpoint is not allowlisted: {method} {endpoint}")

    def pull(self, number: int) -> Mapping[str, Any]:
        result = self._api(f"repos/{self.repository}/pulls/{number}")
        if not isinstance(result, dict):
            raise CommandError("pull response is not an object")
        return result

    def ruleset(self, ruleset_id: int) -> Mapping[str, Any]:
        result = self._api(f"repos/{self.repository}/rulesets/{ruleset_id}")
        if not isinstance(result, dict):
            raise CommandError("ruleset response is not an object")
        return result

    def check_runs(self, sha: str) -> Mapping[str, Any]:
        result = self._api(
            f"repos/{self.repository}/commits/{sha}/check-runs"
            "?filter=latest&per_page=100"
        )
        if not isinstance(result, dict):
            raise CommandError("check-runs response is not an object")
        return result

    def review_threads(self, number: int) -> Sequence[Mapping[str, Any]]:
        result = self._graphql(
            "review_threads",
            {"owner": self.owner, "name": self.name, "number": number},
        )
        try:
            threads = result["data"]["repository"]["pullRequest"]["reviewThreads"]
            page_info = threads["pageInfo"]
            nodes = threads["nodes"]
        except (KeyError, TypeError) as exc:
            raise CommandError("malformed review-thread response") from exc
        if (
            not isinstance(page_info, dict)
            or page_info.get("hasNextPage") is not False
        ):
            raise HarnessError(
                "review-thread pagination is incomplete or malformed"
            )
        if not isinstance(nodes, list) or not all(
            isinstance(node, dict) for node in nodes
        ):
            raise CommandError("malformed review-thread nodes")
        return nodes

    def reviews(self, number: int) -> Sequence[Mapping[str, Any]]:
        result = self._api(
            f"repos/{self.repository}/pulls/{number}/reviews?per_page=100"
        )
        if not isinstance(result, list):
            raise CommandError("reviews response is not an array")
        if len(result) == 100:
            raise HarnessError("review response may be truncated at 100 entries")
        return result

    def mark_ready(self, pull_node_id: str) -> None:
        result = self._graphql("mark_ready", {"pullRequestId": pull_node_id})
        try:
            pull = result["data"]["markPullRequestReadyForReview"]["pullRequest"]
        except (KeyError, TypeError) as exc:
            raise CommandError("malformed mark-ready response") from exc
        if pull.get("id") != pull_node_id or pull.get("isDraft") is not False:
            raise CommandError("GitHub did not confirm ready-for-review state")

    def merge(self, number: int, expected_head: str) -> Mapping[str, Any]:
        result = self._api(
            f"repos/{self.repository}/pulls/{number}/merge",
            method="PUT",
            fields={"merge_method": "merge", "sha": expected_head},
        )
        if not isinstance(result, dict):
            raise CommandError("merge response is not an object")
        return result

    def ensure_premerge_evidence(
        self, policy: Policy, evidence: CandidateEvidence
    ) -> bool:
        payload = evidence.as_dict()
        marker = governed_evidence_marker(
            evidence.number,
            evidence.head_sha,
            "premerge",
            payload,
        )
        body = premerge_evidence_body(policy, marker, evidence)
        return self._ensure_exact_comment(evidence.number, marker, body)

    def ensure_postmerge_evidence(
        self,
        number: int,
        head: str,
        evidence: Mapping[str, Any],
    ) -> bool:
        marker = governed_evidence_marker(
            number,
            head,
            "postmerge",
            evidence,
        )
        body = postmerge_evidence_body(marker, evidence)
        return self._ensure_exact_comment(number, marker, body)

    def ensure_subject_refresh_comment(
        self,
        policy: Policy,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        receipt: IndependentReviewReceipt,
    ) -> bool:
        marker = subject_refresh_marker(item.number, binding.head_sha)
        body = subject_refresh_body(
            policy,
            item,
            binding,
            head_tree,
            receipt,
        )
        return self._ensure_exact_comment(item.number, marker, body)

    def ensure_refreshed_owner_attestation(
        self,
        policy: Policy,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        refresh: RefreshCertificate,
    ) -> bool:
        marker = owner_attestation_marker(item.number, binding.head_sha)
        body = refreshed_owner_attestation_body(
            policy,
            item,
            binding,
            head_tree,
            refresh,
        )
        return self._ensure_exact_comment(item.number, marker, body)

    def _ensure_exact_comment(self, number: int, marker: str, body: str) -> bool:
        comments = self.comments(number)
        if not isinstance(comments, list):
            raise CommandError("issue comments response is not an array")
        if len(comments) == 100:
            raise HarnessError("comment response may be truncated; idempotency unknown")
        for comment in comments:
            if not isinstance(comment, dict):
                raise CommandError("malformed issue comment")
            existing_body = comment.get("body")
            if marker in str(existing_body):
                user = comment.get("user")
                if (
                    existing_body != body
                    or not isinstance(user, dict)
                    or user.get("id") != PINNED_OWNER_ID
                    or user.get("login") != PINNED_OWNER_LOGIN
                    or user.get("type") != "User"
                    or comment.get("author_association") != "OWNER"
                ):
                    raise HarnessError(
                        "evidence comment marker/body/owner collision"
                    )
                return False
        created = self._api(
            f"repos/{self.repository}/issues/{number}/comments",
            method="POST",
            fields={"body": body},
        )
        created_user = created.get("user") if isinstance(created, dict) else None
        if (
            not isinstance(created, dict)
            or type(created.get("id")) is not int
            or created["id"] <= 0
            or created.get("body") != body
            or not isinstance(created_user, dict)
            or created_user.get("id") != PINNED_OWNER_ID
            or created_user.get("login") != PINNED_OWNER_LOGIN
            or created_user.get("type") != "User"
            or created.get("author_association") != "OWNER"
        ):
            raise CommandError("GitHub did not confirm evidence comment creation")
        return True

    def comments(self, number: int) -> Sequence[Mapping[str, Any]]:
        result = self._api(
            f"repos/{self.repository}/issues/{number}/comments?per_page=100"
        )
        if not isinstance(result, list):
            raise CommandError("issue comments response is not an array")
        if len(result) == 100:
            raise HarnessError("comment response may be truncated at 100 entries")
        if not all(isinstance(comment, dict) for comment in result):
            raise CommandError("malformed issue comment")
        return result

    def direct_collaborators(self) -> Sequence[Mapping[str, Any]]:
        result = self._api(
            f"repos/{self.repository}/collaborators?affiliation=direct&per_page=100"
        )
        if not isinstance(result, list):
            raise CommandError("direct collaborators response is not an array")
        if len(result) == 100:
            raise HarnessError("direct collaborator response may be truncated")
        if not all(isinstance(collaborator, dict) for collaborator in result):
            raise CommandError("malformed direct collaborator")
        return result

    def authenticated_user(self) -> Mapping[str, Any]:
        result = self._api("user")
        if not isinstance(result, dict):
            raise CommandError("authenticated-user response is not an object")
        return result


class GitGateway(Protocol):
    common_dir: Path

    def assert_environment(self, repository: str) -> None: ...

    def fetch_candidate(self, item: QueueItem) -> None: ...

    def fetch_integration(self, item: QueueItem) -> None: ...

    def fetch_base(self) -> None: ...

    def authority_matches(self, base: str) -> bool: ...

    def base_sha(self) -> str: ...

    def branch_sha(self, item: QueueItem) -> str: ...

    def integration_head_sha(self, item: QueueItem) -> str: ...

    def merge_sha(self, item: QueueItem) -> str: ...

    def is_ancestor(self, base: str, head: str) -> bool: ...

    def is_first_parent_ancestor(self, base: str, head: str) -> bool: ...

    def changed_paths(self, base: str, head: str) -> Sequence[str]: ...

    def changed_file_modes(
        self, base: str, head: str
    ) -> Sequence[tuple[str, str, str]]: ...

    def stable_patch_id(self, base: str, head: str) -> str: ...

    def semantic_patch_digest(self, base: str, head: str) -> str: ...

    def semantic_patch_digest_for_paths(
        self, base: str, head: str, paths: Sequence[str]
    ) -> str: ...

    def changed_paths_digest(self, base: str, head: str) -> str: ...

    def exact_diff_digest(self, base: str, head: str) -> str: ...

    def name_status_digest(self, base: str, head: str) -> str: ...

    def name_status_digest_for_paths(
        self, base: str, head: str, paths: Sequence[str]
    ) -> str: ...

    def path_identity(self, commit: str, path: str) -> str | None: ...

    def tree(self, commit: str) -> str: ...

    def parents(self, commit: str) -> Sequence[str]: ...


class GitRepository:
    def __init__(self, root: Path, runner: Runner) -> None:
        self.root = root.resolve()
        self.runner = runner
        self.common_dir = self._absolute_git_path(
            self._git("rev-parse", "--git-common-dir").strip()
        )
        self.git_dir = self._absolute_git_path(
            self._git("rev-parse", "--git-dir").strip()
        )

    def _git(self, *arguments: str) -> str:
        return self.runner.run(
            ["git", "--no-replace-objects", *arguments], cwd=self.root
        ).stdout

    def _git_bytes(self, *arguments: str) -> bytes:
        return self.runner.run_bytes(
            ["git", "--no-replace-objects", *arguments], cwd=self.root
        ).stdout

    def _absolute_git_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def assert_environment(self, repository: str) -> None:
        if os.name != "posix":
            raise HarnessError(
                "protected integration is supported only on a POSIX host"
            )
        top = Path(self._git("rev-parse", "--show-toplevel").strip()).resolve()
        if top != self.root:
            raise HarnessError("configured root is not the Git worktree root")
        if self._git("rev-parse", "--is-shallow-repository").strip() != "false":
            raise HarnessError("shallow repositories are not accepted")
        grafts = self.common_dir / "info" / "grafts"
        if grafts.exists() or grafts.is_symlink():
            raise HarnessError("legacy Git grafts are not accepted")
        if self._git("for-each-ref", "--format=%(refname)", "refs/replace").strip():
            raise HarnessError("local Git replace refs are not accepted")
        if self.git_dir == self.common_dir:
            raise HarnessError("primary checkout rejected; use a linked disposable worktree")
        status = self._git("status", "--porcelain=v1", "--untracked-files=all")
        if status:
            raise HarnessError("worktree is not clean")
        remote = self._git("remote", "get-url", "origin").strip()
        normalized = normalize_github_remote(remote)
        if normalized != repository:
            raise HarnessError(
                f"origin repository mismatch: expected {repository}, got {normalized}"
            )

    def fetch_candidate(self, item: QueueItem) -> None:
        self._git(
            "fetch",
            "--no-tags",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            f"+refs/heads/{item.branch}:refs/remotes/origin/{item.branch}",
            f"+refs/pull/{item.number}/head:"
            f"refs/protected-integration/pr-{item.number}-head",
            f"+refs/pull/{item.number}/merge:refs/protected-integration/pr-{item.number}-merge",
        )

    def fetch_integration(self, item: QueueItem) -> None:
        self._git(
            "fetch",
            "--no-tags",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            f"+refs/pull/{item.number}/head:"
            f"refs/protected-integration/pr-{item.number}-head",
        )

    def fetch_base(self) -> None:
        self._git(
            "fetch",
            "--no-tags",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        )

    def authority_matches(self, base: str) -> bool:
        for relative in (POLICY_RELATIVE, SCRIPT_RELATIVE):
            committed = self._git(
                "rev-parse", f"{base}:{relative.as_posix()}"
            ).strip()
            working = self._git(
                "hash-object",
                "--no-filters",
                "--",
                relative.as_posix(),
            ).strip()
            if committed != working:
                return False
        return True

    def base_sha(self) -> str:
        return self._git("rev-parse", "refs/remotes/origin/main").strip()

    def branch_sha(self, item: QueueItem) -> str:
        return self._git(
            "rev-parse", f"refs/remotes/origin/{item.branch}"
        ).strip()

    def integration_head_sha(self, item: QueueItem) -> str:
        return self._git(
            "rev-parse", f"refs/protected-integration/pr-{item.number}-head"
        ).strip()

    def merge_sha(self, item: QueueItem) -> str:
        return self._git(
            "rev-parse", f"refs/protected-integration/pr-{item.number}-merge"
        ).strip()

    def is_ancestor(self, base: str, head: str) -> bool:
        common = self._git("merge-base", base, head).strip()
        return common == base

    def is_first_parent_ancestor(self, base: str, head: str) -> bool:
        if base == head:
            return True
        chain = self._git("rev-list", "--first-parent", head).splitlines()
        return base in chain

    def changed_paths(self, base: str, head: str) -> Sequence[str]:
        return tuple(
            path.decode("utf-8", errors="strict")
            for _status, path in self._name_status_entries(base, head)
        )

    def changed_file_modes(
        self, base: str, head: str
    ) -> Sequence[tuple[str, str, str]]:
        raw = self._git_bytes(
            "-c",
            "core.quotePath=true",
            "diff",
            "--raw",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--no-relative",
            "--submodule=short",
            "--ignore-submodules=none",
            "-z",
            f"{base}..{head}",
            "--",
        )
        fields = raw.split(b"\x00")
        if fields and fields[-1] == b"":
            fields.pop()
        if len(fields) % 2:
            raise HarnessError("malformed raw diff")
        entries: list[tuple[str, str, str]] = []
        for index in range(0, len(fields), 2):
            header = fields[index]
            path = fields[index + 1]
            parts = header.split()
            if (
                len(parts) != 5
                or not parts[0].startswith(b":")
                or not path
            ):
                raise HarnessError("malformed raw diff entry")
            old_mode = parts[0][1:]
            new_mode = parts[1]
            status = parts[4]
            if status not in {b"A", b"D", b"M"}:
                raise HarnessError(f"unsupported Git change status {status!r}: {path}")
            try:
                decoded = path.decode("utf-8", errors="strict")
                old_mode_text = old_mode.decode("ascii", errors="strict")
                new_mode_text = new_mode.decode("ascii", errors="strict")
            except UnicodeDecodeError as exc:
                raise HarnessError("raw diff path or mode is not valid text") from exc
            entries.append((decoded, old_mode_text, new_mode_text))
        return tuple(entries)

    def stable_patch_id(self, base: str, head: str) -> str:
        patch = self._git_bytes(
            *self._canonical_patch_arguments(base, head, unified=3)
        )
        output = self.runner.run_bytes(
            ["git", "--no-replace-objects", "patch-id", "--stable"],
            cwd=self.root,
            input_bytes=patch,
        ).stdout.strip()
        fields = output.split()
        if (
            len(fields) != 2
            or not HEX40.fullmatch(fields[0].decode("ascii", errors="strict"))
        ):
            raise HarnessError("stable patch-id output is malformed or ambiguous")
        return fields[0].decode("ascii")

    def semantic_patch_digest(self, base: str, head: str) -> str:
        raw = self._git_bytes(
            *self._canonical_patch_arguments(base, head, unified=0)
        )
        return semantic_patch_sha256(raw)

    def semantic_patch_digest_for_paths(
        self, base: str, head: str, paths: Sequence[str]
    ) -> str:
        if not paths:
            return hashlib.sha256(b"").hexdigest()
        raw = self._git_bytes(
            *self._canonical_patch_arguments(base, head, unified=0),
            *(self._literal_pathspec(path) for path in sorted(paths)),
        )
        return semantic_patch_sha256(raw)

    def changed_paths_digest(self, base: str, head: str) -> str:
        raw = self._git_bytes(
            "-c",
            "core.quotePath=true",
            "diff",
            "--name-only",
            "--no-renames",
            "--no-relative",
            "--ignore-submodules=none",
            "-z",
            f"{base}..{head}",
            "--",
        )
        paths = [path for path in raw.split(b"\x00") if path]
        if len(paths) != len(set(paths)):
            raise HarnessError("name-only diff contains duplicate paths")
        payload = b"".join(path + b"\x00" for path in sorted(paths))
        return hashlib.sha256(payload).hexdigest()

    def exact_diff_digest(self, base: str, head: str) -> str:
        raw = self._git_bytes(
            *self._canonical_patch_arguments(base, head, unified=3)
        )
        return reviewed_exact_diff_sha256(raw)

    def name_status_digest(self, base: str, head: str) -> str:
        entries = self._name_status_entries(base, head)
        return self._name_status_entries_digest(entries)

    def name_status_digest_for_paths(
        self, base: str, head: str, paths: Sequence[str]
    ) -> str:
        if not paths:
            return hashlib.sha256(b"").hexdigest()
        entries = self._name_status_entries(base, head, paths=paths)
        return self._name_status_entries_digest(entries)

    @staticmethod
    def _name_status_entries_digest(
        entries: Sequence[tuple[bytes, bytes]],
    ) -> str:
        payload = b"".join(
            status + b"\t" + path + b"\n"
            for status, path in sorted(entries, key=lambda entry: entry[1])
        )
        return hashlib.sha256(payload).hexdigest()

    def _name_status_entries(
        self,
        base: str,
        head: str,
        *,
        paths: Sequence[str] = (),
    ) -> tuple[tuple[bytes, bytes], ...]:
        raw = self._git_bytes(
            "-c",
            "core.quotePath=true",
            "diff",
            "--name-status",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--no-relative",
            "--submodule=short",
            "--ignore-submodules=none",
            "-z",
            f"{base}..{head}",
            "--",
            *(self._literal_pathspec(path) for path in sorted(paths)),
        )
        fields = raw.split(b"\x00")
        if fields and fields[-1] == b"":
            fields.pop()
        if len(fields) % 2:
            raise HarnessError("malformed name-status diff")
        entries = []
        for index in range(0, len(fields), 2):
            status, path = fields[index : index + 2]
            if status not in {b"A", b"D", b"M"} or not path:
                raise HarnessError("unsupported or malformed name-status diff")
            entries.append((status, path))
        paths = [path for _status, path in entries]
        if len(paths) != len(set(paths)):
            raise HarnessError("name-status diff contains duplicate paths")
        return tuple(entries)

    def path_identity(self, commit: str, path: str) -> str | None:
        raw = self._git_bytes(
            "ls-tree",
            "-z",
            commit,
            "--",
            self._literal_pathspec(path),
        )
        if not raw:
            return None
        fields = raw.split(b"\x00")
        if fields[-1] == b"":
            fields.pop()
        if len(fields) != 1 or b"\t" not in fields[0]:
            raise HarnessError(f"ambiguous reviewed-result tree entry: {path}")
        metadata, raw_path = fields[0].split(b"\t", 1)
        try:
            decoded_path = raw_path.decode("utf-8", errors="strict")
            decoded_metadata = metadata.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise HarnessError(
                f"reviewed-result tree entry is not valid text: {path}"
            ) from exc
        if decoded_path != path or REVIEWED_RESULT_ENTRY.fullmatch(
            decoded_metadata
        ) is None:
            raise HarnessError(
                f"reviewed-result tree entry identity is invalid: {path}"
            )
        return decoded_metadata

    @staticmethod
    def _literal_pathspec(path: str) -> str:
        return f":(top,literal){path}"

    @staticmethod
    def _canonical_patch_arguments(
        base: str, head: str, *, unified: int
    ) -> tuple[str, ...]:
        return (
            "-c",
            "core.quotePath=true",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--no-renames",
            "--indent-heuristic",
            "--inter-hunk-context=0",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--no-relative",
            "--diff-algorithm=myers",
            "--submodule=short",
            "--ignore-submodules=none",
            "--patch",
            "--binary",
            "--full-index",
            f"--unified={unified}",
            "--output-indicator-new=+",
            "--output-indicator-old=-",
            "--output-indicator-context= ",
            f"{base}..{head}",
            "--",
        )

    def tree(self, commit: str) -> str:
        return self._git("rev-parse", f"{commit}^{{tree}}").strip()

    def parents(self, commit: str) -> Sequence[str]:
        output = self._git("show", "-s", "--format=%P", commit).strip()
        return tuple(output.split()) if output else ()


def normalize_github_remote(remote: str) -> str:
    value = remote.strip()
    patterns = (
        r"^git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return match.group("repo")
    raise HarnessError("origin must be an exact GitHub SSH or HTTPS repository URL")


class StateStore:
    def __init__(self, common_dir: Path) -> None:
        try:
            self.common_dir = common_dir.resolve(strict=True)
        except OSError as exc:
            raise HarnessError(f"Git common directory is unavailable: {exc}") from exc
        if not self.common_dir.is_dir():
            raise HarnessError("Git common directory is not a directory")
        self.directory = self.common_dir / STATE_DIR
        self.lock_path = self.common_dir / LOCK_FILE

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        self._ensure_storage_directory(self.lock_path.parent)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise HarnessError(f"cannot safely open transaction lock: {exc}") from exc
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            os.close(descriptor)
            raise HarnessError(
                "transaction lock must be a non-linked regular file"
            )
        unlock: Any = None
        try:
            if os.name == "posix":
                import fcntl

                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                    raise HarnessError(
                        "protected integration transaction is locked"
                    ) from exc

                def unlock_posix() -> None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)

                unlock = unlock_posix
            elif os.name == "nt":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\x00")
                    os.fsync(descriptor)
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise HarnessError("protected integration transaction is locked") from exc

                def unlock_windows() -> None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

                unlock = unlock_windows
            else:
                raise HarnessError(
                    f"no safe advisory-lock implementation for os.name={os.name!r}"
                )
            owner = (
                json.dumps(
                    {"pid": os.getpid(), "started_at": utc_now()},
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, owner)
            os.fsync(descriptor)
            yield
        finally:
            if unlock is not None:
                with contextlib.suppress(OSError):
                    unlock()
            os.close(descriptor)

    def path(self, number: int) -> Path:
        return self.directory / f"pr-{number}.json"

    def load(self, number: int) -> dict[str, Any] | None:
        path = self.path(number)
        self._ensure_storage_directory(path.parent)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HarnessError(f"cannot safely open transaction state: {exc}") from exc
        state_stat = os.fstat(descriptor)
        if not stat.S_ISREG(state_stat.st_mode) or state_stat.st_nlink != 1:
            os.close(descriptor)
            raise HarnessError(
                "transaction state must be a non-linked regular file"
            )
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                raw = stream.read(64 * 1024 + 1)
        except OSError as exc:
            raise HarnessError(f"cannot read transaction state: {exc}") from exc
        if len(raw) > 64 * 1024:
            raise HarnessError("transaction state exceeds 64 KiB")
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HarnessError("transaction state is malformed") from exc
        if not isinstance(document, dict):
            raise HarnessError("transaction state root must be an object")
        validate_state_shape(document)
        if document.get("schema_version") != 1:
            raise HarnessError("transaction state schema mismatch")
        return document

    def save(self, number: int, document: Mapping[str, Any]) -> None:
        self._ensure_storage_directory(self.directory)
        payload = dict(document)
        payload["schema_version"] = STATE_SCHEMA
        payload["updated_at"] = utc_now()
        validate_state_shape(payload)
        if payload["number"] != number:
            raise HarnessError("transaction state path/number mismatch")
        self._atomic_write(self.path(number), payload)

    def _ensure_storage_directory(self, directory: Path) -> None:
        try:
            relative = directory.relative_to(self.common_dir)
        except ValueError as exc:
            raise HarnessError("state directory escapes the Git common directory") from exc
        current = self.common_dir
        for part in relative.parts:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise HarnessError(
                    f"cannot create protected state directory: {exc}"
                ) from exc
            try:
                current_stat = os.lstat(current)
            except OSError as exc:
                raise HarnessError(
                    f"cannot inspect protected state directory: {exc}"
                ) from exc
            if stat.S_ISLNK(current_stat.st_mode) or not stat.S_ISDIR(
                current_stat.st_mode
            ):
                raise HarnessError(
                    f"protected state path component is not a real directory: {current}"
                )

    @staticmethod
    def _atomic_write(path: Path, document: Mapping[str, Any]) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            StateStore._fsync_directory(path.parent)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            directory_descriptor = os.open(
                directory,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) in {
                1,  # ERROR_INVALID_FUNCTION
                5,  # ERROR_ACCESS_DENIED for directory handles
                50,  # ERROR_NOT_SUPPORTED
                87,  # ERROR_INVALID_PARAMETER
            }:
                return
            raise HarnessError(
                f"cannot open state directory for durability sync: {exc}"
            ) from exc
        try:
            try:
                os.fsync(directory_descriptor)
            except OSError as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) in {
                    1,
                    50,
                    87,
                }:
                    return
                raise HarnessError(
                    f"cannot durability-sync state directory: {exc}"
                ) from exc
        finally:
            os.close(directory_descriptor)


def validate_state_shape(document: Mapping[str, Any]) -> None:
    stage = document.get("stage")
    common = {
        "schema_version",
        "updated_at",
        "policy_id",
        "repository",
        "number",
        "work_id",
        "expected_base",
        "expected_head",
        "head_tree",
        "stage",
    }
    extras = {
        "ready-marked": set(),
        "ready-validated": set(),
        "merge-requested": set(),
        "merge-created": {"merge_sha"},
        "complete": {
            "merge_sha",
            "post_merge_checks",
            "completed_at",
        },
    }
    if stage not in extras:
        raise HarnessError(f"transaction state stage is invalid: {stage!r}")
    _exact_keys(document, common | extras[stage], f"transaction state {stage}")
    if _exact_int(document["schema_version"], "transaction state schema_version") != 1:
        raise HarnessError("transaction state schema_version drift")
    _exact_int(document["number"], "transaction state number")
    for key in ("updated_at", "policy_id", "repository", "work_id"):
        _nonempty_string(document[key], f"transaction state {key}")
    for key in ("expected_base", "expected_head", "head_tree"):
        value = document[key]
        if not isinstance(value, str) or not HEX40.fullmatch(value):
            raise HarnessError(f"transaction state {key} must be lowercase 40-hex")
    if stage in {"merge-created", "complete"}:
        merge_sha = document["merge_sha"]
        if not isinstance(merge_sha, str) or not HEX40.fullmatch(merge_sha):
            raise HarnessError("transaction state merge_sha must be lowercase 40-hex")
    if stage == "complete":
        _nonempty_string(
            document["completed_at"], "transaction state completed_at"
        )
        checks = document["post_merge_checks"]
        if not isinstance(checks, dict):
            raise HarnessError("transaction state post_merge_checks must be an object")
        ids: set[int] = set()
        for context, check_id in checks.items():
            _nonempty_string(context, "transaction state check context")
            exact_id = _exact_int(check_id, "transaction state check ID")
            if exact_id <= 0:
                raise HarnessError("transaction state check IDs must be positive")
            if exact_id in ids:
                raise HarnessError("transaction state has duplicate check-run IDs")
            ids.add(exact_id)


@dataclasses.dataclass(frozen=True)
class ContentBinding:
    base_sha: str
    head_sha: str
    changed_paths: tuple[str, ...]
    stable_patch_id: str
    semantic_patch_sha256: str
    changed_paths_sha256: str
    exact_diff_sha256: str
    name_status_sha256: str
    binding_mode: str
    refreshed_paths: tuple[str, ...]
    removed_reviewed_paths: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class RefreshCertificate:
    comment_id: int
    body_sha256: str
    review_receipt_sha256: str
    reviewer_id: str
    reviewed_at: str


@dataclasses.dataclass(frozen=True)
class CandidateEvidence:
    number: int
    work_id: str
    base_sha: str
    head_sha: str
    head_tree: str
    synthetic_merge_sha: str
    changed_paths: tuple[str, ...]
    stable_patch_id: str
    semantic_patch_sha256: str
    changed_paths_sha256: str
    exact_diff_sha256: str
    name_status_sha256: str
    binding_mode: str
    refreshed_paths: tuple[str, ...]
    removed_reviewed_paths: tuple[str, ...]
    refresh_certificate_comment_id: int | None
    refresh_certificate_body_sha256: str | None
    review_receipt_sha256: str | None
    check_runs: Mapping[str, int]
    ruleset_id: int

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def governed_evidence_marker(
    number: int,
    head: str,
    stage: str,
    evidence: Mapping[str, Any],
) -> str:
    if stage not in {"premerge", "postmerge"}:
        raise HarnessError(f"governed evidence stage is invalid: {stage!r}")
    fingerprint = hashlib.sha256(
        canonical_json(evidence).encode("utf-8")
    ).hexdigest()
    return f"{EVIDENCE_PREFIX}pr-{number}:{head}:{stage}:{fingerprint} -->"


def premerge_evidence_body(
    policy: Policy,
    marker: str,
    evidence: CandidateEvidence,
) -> str:
    checks = "\n".join(
        f"- `{name}`: check run `{check_id}`"
        for name, check_id in evidence.check_runs.items()
    )
    refresh_authority = (
        "- Subject-refresh authority: "
        f"`accepted {policy.delegation['subject_refresh_accepted_date']}; "
        f"generation {policy.delegation['subject_refresh_generation']}`\n"
        if evidence.binding_mode == "refreshed-generation-1"
        else ""
    )
    return (
        f"{marker}\n"
        "Protected integration v1 pre-merge evidence (standing owner delegation "
        "accepted 2026-07-26; fixed queue only).\n\n"
        f"- Work item: `{evidence.work_id}` / PR `#{evidence.number}`\n"
        f"- Completion claim: `{policy.item(evidence.number).completion_claim}`\n"
        f"- Exact base: `{evidence.base_sha}`\n"
        f"- Exact head: `{evidence.head_sha}`\n"
        f"- Exact head tree: `{evidence.head_tree}`\n"
        f"- Binding mode: `{evidence.binding_mode}`\n"
        f"{refresh_authority}"
        f"- Semantic patch SHA-256: `{evidence.semantic_patch_sha256}`\n"
        f"- Current exact diff SHA-256: `{evidence.exact_diff_sha256}`\n"
        f"- Subject refresh comment ID: "
        f"`{evidence.refresh_certificate_comment_id}`\n"
        f"- Independent review receipt SHA-256: "
        f"`{evidence.review_receipt_sha256}`\n"
        f"- Synthetic merge: `{evidence.synthetic_merge_sha}` with exact "
        "base/head parents and head-equivalent tree\n"
        f"- Live ruleset: `{evidence.ruleset_id}`\n"
        f"- Changed paths inside fixed envelope: `{len(evidence.changed_paths)}`\n"
        f"{checks}\n\n"
        "Threads are resolved, no active changes-requested review exists, and "
        "the pull remained ready after settlement. This is not release, signing, "
        "DOI, artifact, learner-output, cleanup, or external-contact authority."
    )


def postmerge_evidence_body(marker: str, evidence: Mapping[str, Any]) -> str:
    return (
        f"{marker}\n"
        "Protected integration v1 exact post-merge evidence\n\n"
        "```json\n"
        f"{canonical_json(evidence)}\n"
        "```\n\n"
        "This fixed transaction is not authority for public beta/promotion, "
        "participant recruitment, release/tag/DOI, signed or package "
        "distribution, signing/release credentials, artifact/package content, "
        "cleanup, repository moves, external contact, or ruleset/security "
        "setting changes."
    )


class IntegrationHarness:
    def __init__(
        self,
        policy: Policy,
        git: GitGateway,
        github: GitHubGateway,
        state: StateStore,
        *,
        sleep: Any = time.sleep,
        monotonic: Any = time.monotonic,
    ) -> None:
        self.policy = policy
        self.git = git
        self.github = github
        self.state = state
        self.sleep = sleep
        self.monotonic = monotonic

    def preflight(
        self, number: int, expected_base: str, expected_head: str
    ) -> CandidateEvidence:
        item = self.policy.item(number)
        self.git.assert_environment(self.policy.repository)
        pull = self.github.pull(number)
        self._validate_open_pull(pull, item, expected_base, expected_head)
        self.git.fetch_candidate(item)
        if self.git.base_sha() != expected_base:
            raise HarnessError("fetched origin/main differs from expected base")
        if self.git.branch_sha(item) != expected_head:
            raise HarnessError("fetched queued branch differs from expected head")
        if not self.git.authority_matches(expected_base):
            raise HarnessError(
                "running policy/harness is not the version accepted at expected base"
            )
        if not self.git.is_first_parent_ancestor(expected_base, expected_head):
            raise HarnessError(
                "candidate head is not strictly first-parent up to date with "
                "expected base"
            )
        self._validate_queue(item, expected_base)
        binding = self._validate_content_binding(item, expected_base, expected_head)
        head_tree = self.git.tree(expected_head)
        synthetic_merge = self.git.merge_sha(item)
        if tuple(self.git.parents(synthetic_merge)) != (expected_base, expected_head):
            raise HarnessError("synthetic merge parents do not equal exact base/head")
        if self.git.tree(synthetic_merge) != head_tree:
            raise HarnessError("synthetic merge tree differs from exact head tree")

        validate_ruleset(self.github.ruleset(self.policy.ruleset_id), self.policy)
        self._validate_reviews(number)
        refresh = self._validate_subject_refresh_certificate(
            item, binding, head_tree
        )
        self._validate_review_topology_and_attestation(
            item,
            binding,
            head_tree,
            refresh,
        )
        checks = validate_check_runs(
            self.github.check_runs(expected_head), expected_head, self.policy
        )
        return CandidateEvidence(
            number=number,
            work_id=item.work_id,
            base_sha=expected_base,
            head_sha=expected_head,
            head_tree=head_tree,
            synthetic_merge_sha=synthetic_merge,
            changed_paths=binding.changed_paths,
            stable_patch_id=binding.stable_patch_id,
            semantic_patch_sha256=binding.semantic_patch_sha256,
            changed_paths_sha256=binding.changed_paths_sha256,
            exact_diff_sha256=binding.exact_diff_sha256,
            name_status_sha256=binding.name_status_sha256,
            binding_mode=binding.binding_mode,
            refreshed_paths=binding.refreshed_paths,
            removed_reviewed_paths=binding.removed_reviewed_paths,
            refresh_certificate_comment_id=(
                refresh.comment_id if refresh is not None else None
            ),
            refresh_certificate_body_sha256=(
                refresh.body_sha256 if refresh is not None else None
            ),
            review_receipt_sha256=(
                refresh.review_receipt_sha256 if refresh is not None else None
            ),
            check_runs=checks,
            ruleset_id=self.policy.ruleset_id,
        )

    def attest_refresh(
        self,
        number: int,
        expected_base: str,
        expected_head: str,
        *,
        review_receipt_json: str,
    ) -> CandidateEvidence:
        receipt_document = parse_canonical_review_receipt(review_receipt_json)
        with self.state.lock():
            self._validate_authenticated_actor()
            item = self.policy.item(number)
            self.git.assert_environment(self.policy.repository)
            pull = self.github.pull(number)
            self._validate_open_pull(pull, item, expected_base, expected_head)
            self.git.fetch_candidate(item)
            if self.git.base_sha() != expected_base:
                raise HarnessError("fetched origin/main differs from expected base")
            if self.git.branch_sha(item) != expected_head:
                raise HarnessError("fetched queued branch differs from expected head")
            if not self.git.authority_matches(expected_base):
                raise HarnessError(
                    "running policy/harness is not the version accepted at "
                    "expected base"
                )
            if not self.git.is_first_parent_ancestor(expected_base, expected_head):
                raise HarnessError(
                    "candidate head is not strictly first-parent up to date with "
                    "expected base"
                )
            self._validate_queue(item, expected_base)
            binding = self._validate_content_binding(
                item, expected_base, expected_head
            )
            if binding.binding_mode != "refreshed-generation-1":
                raise HarnessError(
                    "attest-refresh is only valid for a bounded refreshed subject"
                )
            head_tree = self.git.tree(expected_head)
            synthetic_merge = self.git.merge_sha(item)
            if tuple(self.git.parents(synthetic_merge)) != (
                expected_base,
                expected_head,
            ):
                raise HarnessError(
                    "synthetic merge parents do not equal exact base/head"
                )
            if self.git.tree(synthetic_merge) != head_tree:
                raise HarnessError(
                    "synthetic merge tree differs from exact head tree"
                )
            receipt = self._validate_independent_review_receipt(
                receipt_document,
                item,
                binding,
                head_tree,
            )
            validate_ruleset(
                self.github.ruleset(self.policy.ruleset_id), self.policy
            )
            self._validate_reviews(number)
            validate_check_runs(
                self.github.check_runs(expected_head),
                expected_head,
                self.policy,
            )
            self._validate_collaborator_topology()
            self._validate_authenticated_actor()
            self.github.ensure_subject_refresh_comment(
                self.policy,
                item,
                binding,
                head_tree,
                receipt,
            )
            refresh = self._validate_subject_refresh_certificate(
                item, binding, head_tree
            )
            if refresh is None:
                raise HarnessError("subject refresh certificate was not persisted")
            self._validate_authenticated_actor()
            self.github.ensure_refreshed_owner_attestation(
                self.policy,
                item,
                binding,
                head_tree,
                refresh,
            )
            return self.preflight(number, expected_base, expected_head)

    def mark_ready(
        self,
        number: int,
        expected_base: str,
        expected_head: str,
        *,
        settle_seconds: float,
    ) -> CandidateEvidence:
        with self.state.lock():
            self._validate_authenticated_actor()
            evidence = self.preflight(number, expected_base, expected_head)
            pull = self.github.pull(number)
            self._validate_open_pull(
                pull, self.policy.item(number), expected_base, expected_head
            )
            if pull.get("draft") is True:
                node_id = _nonempty_string(pull.get("node_id"), "pull node_id")
                self._validate_authenticated_actor()
                self.github.mark_ready(node_id)
            elif pull.get("draft") is not False:
                raise HarnessError("pull draft state is not exact boolean")
            self.state.save(
                number,
                {
                    "policy_id": self.policy.policy_id,
                    "repository": self.policy.repository,
                    "number": number,
                    "work_id": evidence.work_id,
                    "expected_base": expected_base,
                    "expected_head": expected_head,
                    "head_tree": evidence.head_tree,
                    "stage": "ready-marked",
                },
            )
            if settle_seconds:
                self.sleep(settle_seconds)
            settled = self.preflight(number, expected_base, expected_head)
            live_pull = self.github.pull(number)
            self._validate_open_pull(
                live_pull, self.policy.item(number), expected_base, expected_head
            )
            if live_pull.get("draft") is not False:
                raise HarnessError("pull did not remain ready after settlement")
            self.state.save(
                number,
                {
                    "policy_id": self.policy.policy_id,
                    "repository": self.policy.repository,
                    "number": number,
                    "work_id": settled.work_id,
                    "expected_base": expected_base,
                    "expected_head": expected_head,
                    "head_tree": settled.head_tree,
                    "stage": "ready-validated",
                },
            )
            self._validate_authenticated_actor()
            self.github.ensure_premerge_evidence(self.policy, settled)
            return settled

    def merge(
        self,
        number: int,
        expected_base: str,
        expected_head: str,
        *,
        settle_seconds: float,
        poll_seconds: float,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        with self.state.lock():
            self._validate_authenticated_actor()
            item = self.policy.item(number)
            self.git.assert_environment(self.policy.repository)
            stored = self.state.load(number)
            if stored is None:
                raise HarnessError("mark-ready transaction state is absent")
            self._validate_state_identity(
                stored, item, expected_base, expected_head
            )
            stage = stored.get("stage")
            if stage == "complete":
                merge_sha = _nonempty_string(
                    stored.get("merge_sha"), "complete merge SHA"
                )
                head_tree, checks = self._validate_live_merged_target(
                    item,
                    expected_base,
                    expected_head,
                    merge_sha,
                    poll_seconds=poll_seconds,
                    timeout_seconds=timeout_seconds,
                    wait_for_checks=False,
                )
                if stored.get("head_tree") != head_tree:
                    raise HarnessError("complete state head tree differs from live Git")
                refreshed = dict(stored)
                refreshed["post_merge_checks"] = checks
                self.state.save(number, refreshed)
                post_evidence = self._post_evidence_payload(refreshed)
                self._validate_authenticated_actor()
                self.github.ensure_postmerge_evidence(
                    number,
                    expected_head,
                    post_evidence,
                )
                self._require_postmerge_evidence_comment(
                    item,
                    expected_base,
                    expected_head,
                    head_tree,
                    merge_sha,
                    checks,
                )
                return refreshed
            if stage not in {"ready-validated", "merge-requested", "merge-created"}:
                raise HarnessError(f"transaction is not mergeable from stage {stage!r}")

            merge_sha: str | None = None
            if stage == "merge-requested":
                pull = self.github.pull(number)
                if pull.get("merged_at"):
                    candidate_merge = pull.get("merge_commit_sha")
                    if not isinstance(candidate_merge, str) or not HEX40.fullmatch(
                        candidate_merge
                    ):
                        raise HarnessError("merged pull has no exact merge SHA")
                    merge_sha = candidate_merge
                elif pull.get("state") != "open":
                    raise HarnessError("merge-requested pull closed without merging")

            if stage in {"ready-validated", "merge-requested"} and merge_sha is None:
                if settle_seconds:
                    self.sleep(settle_seconds)
                evidence = self.preflight(number, expected_base, expected_head)
                pull = self.github.pull(number)
                self._validate_open_pull(
                    pull, item, expected_base, expected_head
                )
                if pull.get("draft") is not False:
                    raise HarnessError("pull returned to draft before merge")
                self._validate_authenticated_actor()
                self.github.ensure_premerge_evidence(self.policy, evidence)
                stored = {
                    "policy_id": self.policy.policy_id,
                    "repository": self.policy.repository,
                    "number": number,
                    "work_id": evidence.work_id,
                    "expected_base": expected_base,
                    "expected_head": expected_head,
                    "head_tree": evidence.head_tree,
                    "stage": "merge-requested",
                }
                self.state.save(number, stored)
                final_pull = self.github.pull(number)
                self._validate_open_pull(
                    final_pull, item, expected_base, expected_head
                )
                if final_pull.get("draft") is not False:
                    raise HarnessError("pull returned to draft at merge mutation")
                self._validate_authenticated_actor()
                response = self.github.merge(number, expected_head)
                if response.get("merged") is not True:
                    raise HarnessError(
                        f"GitHub refused exact-head merge: {response.get('message')!r}"
                    )
                candidate_merge = response.get("sha")
                if not isinstance(candidate_merge, str) or not HEX40.fullmatch(
                    candidate_merge
                ):
                    raise HarnessError("merge response omitted an exact merge SHA")
                merge_sha = candidate_merge

            if stage == "merge-created":
                merge_sha = stored.get("merge_sha")
                if not isinstance(merge_sha, str) or not HEX40.fullmatch(merge_sha):
                    raise HarnessError("resumable state has no exact merge SHA")
            else:
                if merge_sha is None:  # pragma: no cover - guarded above.
                    raise HarnessError("merge SHA recovery failed")
                stored = dict(stored)
                stored.update({"merge_sha": merge_sha, "stage": "merge-created"})
                self.state.save(number, stored)

            head_tree, checks = self._validate_live_merged_target(
                item,
                expected_base,
                expected_head,
                merge_sha,
                poll_seconds=poll_seconds,
                timeout_seconds=timeout_seconds,
                wait_for_checks=True,
            )
            if stored.get("head_tree") != head_tree:
                raise HarnessError("recorded head tree differs from live exact head")
            completed = dict(stored)
            completed.update(
                {
                    "stage": "complete",
                    "post_merge_checks": checks,
                    "completed_at": utc_now(),
                }
            )
            self.state.save(number, completed)
            post_evidence = self._post_evidence_payload(completed)
            self._validate_authenticated_actor()
            self.github.ensure_postmerge_evidence(
                number,
                expected_head,
                post_evidence,
            )
            self._require_postmerge_evidence_comment(
                item,
                expected_base,
                expected_head,
                head_tree,
                merge_sha,
                checks,
            )
            return completed

    def _validate_live_merged_target(
        self,
        item: QueueItem,
        expected_base: str,
        expected_head: str,
        merge_sha: str,
        *,
        poll_seconds: float,
        timeout_seconds: float,
        wait_for_checks: bool,
    ) -> tuple[str, Mapping[str, int]]:
        head_tree, current_exact_diff_sha256 = self._validate_merged_snapshot(
            item, expected_base, expected_head, merge_sha
        )
        validate_ruleset(self.github.ruleset(self.policy.ruleset_id), self.policy)
        self._validate_reviews(item.number)
        binding = self._validate_content_binding(
            item, expected_base, expected_head
        )
        refresh = self._validate_subject_refresh_certificate(
            item, binding, head_tree
        )
        self._validate_review_topology_and_attestation(
            item,
            binding,
            head_tree,
            refresh,
        )
        validate_check_runs(
            self.github.check_runs(expected_head), expected_head, self.policy
        )
        if wait_for_checks:
            self._wait_for_checks(
                merge_sha,
                poll_seconds=poll_seconds,
                timeout_seconds=timeout_seconds,
            )
        else:
            validate_check_runs(
                self.github.check_runs(merge_sha), merge_sha, self.policy
            )

        refreshed_tree, refreshed_exact_diff = self._validate_merged_snapshot(
            item, expected_base, expected_head, merge_sha
        )
        if (
            refreshed_tree != head_tree
            or refreshed_exact_diff != current_exact_diff_sha256
        ):
            raise HarnessError("merged target provenance changed during check wait")
        validate_check_runs(
            self.github.check_runs(expected_head), expected_head, self.policy
        )
        checks = validate_check_runs(
            self.github.check_runs(merge_sha), merge_sha, self.policy
        )
        validate_ruleset(self.github.ruleset(self.policy.ruleset_id), self.policy)
        self._validate_reviews(item.number)
        refreshed_binding = self._validate_content_binding(
            item, expected_base, expected_head
        )
        refreshed_refresh = self._validate_subject_refresh_certificate(
            item, refreshed_binding, refreshed_tree
        )
        self._validate_review_topology_and_attestation(
            item,
            refreshed_binding,
            refreshed_tree,
            refreshed_refresh,
        )
        return refreshed_tree, checks

    def _validate_merged_snapshot(
        self,
        item: QueueItem,
        expected_base: str,
        expected_head: str,
        merge_sha: str,
    ) -> tuple[str, str]:
        pull = self.github.pull(item.number)
        source_base, source_head = self._pull_source_identity(pull, item)
        if (source_base, source_head) != (expected_base, expected_head):
            raise HarnessError("merged pull source base/head differ from transaction")
        if (
            pull.get("state") != "closed"
            or not isinstance(pull.get("merged_at"), str)
            or not pull.get("merged_at")
            or pull.get("merge_commit_sha") != merge_sha
            or not HEX40.fullmatch(merge_sha)
        ):
            raise HarnessError("live pull does not report the exact accepted merge")
        self._validate_merged_by_owner(pull, item.number)
        self.git.fetch_integration(item)
        current_main = self.git.base_sha()
        if not self.git.authority_matches(expected_base):
            raise HarnessError(
                "running policy/harness is not the version accepted at source base"
            )
        if self.git.integration_head_sha(item) != expected_head:
            raise HarnessError("merged pull exact-head ref drift")
        content_binding = self._validate_content_binding(
            item, expected_base, expected_head
        )
        current_exact_diff_sha256 = content_binding.exact_diff_sha256
        head_tree = self.git.tree(expected_head)
        if tuple(self.git.parents(merge_sha)) != (expected_base, expected_head):
            raise HarnessError("accepted merge parents differ from exact base/head")
        if self.git.tree(merge_sha) != head_tree:
            raise HarnessError("accepted merge tree differs from exact head tree")
        if not self.git.is_first_parent_ancestor(merge_sha, current_main):
            raise HarnessError(
                "accepted merge is not on the first-parent history of live main"
            )
        self._validate_queue(item, current_main, target_merged=True)
        return head_tree, current_exact_diff_sha256

    def _wait_for_checks(
        self, sha: str, *, poll_seconds: float, timeout_seconds: float
    ) -> Mapping[str, int]:
        deadline = self.monotonic() + timeout_seconds
        while True:
            try:
                return validate_check_runs(
                    self.github.check_runs(sha), sha, self.policy
                )
            except PendingChecks:
                if self.monotonic() >= deadline:
                    raise HarnessError(
                        f"post-merge checks did not complete within {timeout_seconds}s"
                    )
                self.sleep(poll_seconds)

    def _validate_queue(
        self,
        target: QueueItem,
        expected_base: str,
        *,
        target_merged: bool = False,
    ) -> None:
        target_index = next(
            index
            for index, item in enumerate(self.policy.queue)
            if item.number == target.number
        )
        for index, item in enumerate(self.policy.queue):
            pull = self.github.pull(item.number)
            if index < target_index:
                self._validate_integrated_predecessor(item, pull, expected_base)
                continue
            if index == target_index:
                if target_merged:
                    if (
                        pull.get("state") != "closed"
                        or not isinstance(pull.get("merged_at"), str)
                        or not pull.get("merged_at")
                    ):
                        raise HarnessError(
                            f"target PR #{target.number} is not exactly integrated"
                        )
                elif pull.get("merged_at") is not None:
                    raise HarnessError(
                        f"target PR #{target.number} is already integrated"
                    )
                continue
            self._pull_source_identity(pull, item)
            if pull.get("merged_at") is not None or pull.get("state") != "open":
                raise HarnessError(
                    f"queue successor PR #{item.number} is not open and unmerged"
                )

    def _validate_integrated_predecessor(
        self,
        item: QueueItem,
        pull: Mapping[str, Any],
        expected_base: str,
    ) -> None:
        source_base, source_head = self._pull_source_identity(pull, item)
        merged_at = pull.get("merged_at")
        merge_sha = pull.get("merge_commit_sha")
        if (
            pull.get("state") != "closed"
            or not isinstance(merged_at, str)
            or not merged_at
            or not isinstance(merge_sha, str)
            or not HEX40.fullmatch(merge_sha)
        ):
            raise HarnessError(
                f"queue predecessor PR #{item.number} lacks exact merged identity"
            )
        self._validate_merged_by_owner(pull, item.number)
        accepted = item.accepted_integration
        if accepted is not None:
            if (
                accepted["source_base"] != source_base
                or accepted["source_head"] != source_head
                or accepted["merge_sha"] != merge_sha
            ):
                raise HarnessError(
                    f"queue predecessor PR #{item.number} differs from bootstrap pin"
                )
        self.git.fetch_integration(item)
        if self.git.base_sha() != expected_base:
            raise HarnessError("origin/main drifted while validating queue prefix")
        if self.git.integration_head_sha(item) != source_head:
            raise HarnessError(
                f"queue predecessor PR #{item.number} source-head ref drift"
            )
        if not self.git.is_first_parent_ancestor(source_base, source_head):
            raise HarnessError(
                f"queue predecessor PR #{item.number} source head is not "
                "first-parent based on its recorded source base"
            )
        content_binding = self._validate_content_binding(
            item, source_base, source_head
        )
        head_tree = self.git.tree(source_head)
        if tuple(self.git.parents(merge_sha)) != (source_base, source_head):
            raise HarnessError(
                f"queue predecessor PR #{item.number} merge parents drift"
            )
        if self.git.tree(merge_sha) != head_tree:
            raise HarnessError(
                f"queue predecessor PR #{item.number} merge tree is not source-equivalent"
            )
        if accepted is not None and head_tree != accepted["tree"]:
            raise HarnessError(
                f"queue predecessor PR #{item.number} accepted tree drift"
            )
        if not self.git.is_first_parent_ancestor(merge_sha, expected_base):
            raise HarnessError(
                f"queue predecessor PR #{item.number} merge is not on the "
                "expected base first-parent history"
            )
        validate_check_runs(
            self.github.check_runs(source_head), source_head, self.policy
        )
        checks = validate_check_runs(
            self.github.check_runs(merge_sha), merge_sha, self.policy
        )
        self._validate_reviews(item.number)
        if accepted is not None:
            self._validate_bootstrap_completion_comment(item, accepted)
        else:
            refresh = self._validate_subject_refresh_certificate(
                item, content_binding, head_tree
            )
            self._validate_review_topology_and_attestation(
                item,
                content_binding,
                head_tree,
                refresh,
            )
            self._require_postmerge_evidence_comment(
                item,
                source_base,
                source_head,
                head_tree,
                merge_sha,
                checks,
            )

    def _validate_bootstrap_completion_comment(
        self, item: QueueItem, accepted: Mapping[str, Any]
    ) -> None:
        expected = accepted["owner_completion_comment"]
        matches = []
        for comment in self.github.comments(item.number):
            if comment.get("id") != expected["id"]:
                continue
            body = comment.get("body")
            user = comment.get("user")
            if (
                not isinstance(body, str)
                or expected["marker"] not in body
                or hashlib.sha256(body.encode("utf-8")).hexdigest()
                != expected["body_sha256"]
                or not isinstance(user, dict)
                or user.get("id") != expected["author_id"]
                or user.get("login") != expected["author_login"]
                or user.get("type") != "User"
                or comment.get("author_association") != "OWNER"
                or comment.get("created_at") != expected["created_at"]
                or comment.get("updated_at") != expected["updated_at"]
            ):
                raise HarnessError(
                    f"PR #{item.number} bootstrap completion evidence drift"
                )
            matches.append(comment)
        if len(matches) != 1:
            raise HarnessError(
                f"PR #{item.number} bootstrap owner completion comment is absent "
                "or duplicated"
            )

    def _validate_content_binding(
        self, item: QueueItem, source_base: str, source_head: str
    ) -> ContentBinding:
        changed_paths = tuple(self.git.changed_paths(source_base, source_head))
        validate_changed_paths(changed_paths, item, self.policy.denied_paths)
        changed_path_set = set(changed_paths)
        allowed_mode_transitions = {
            ("000000", "100644"),
            ("100644", "100644"),
        }
        for path, old_mode, new_mode in self.git.changed_file_modes(
            source_base, source_head
        ):
            if path not in changed_path_set:
                raise HarnessError(
                    f"PR #{item.number} raw-diff path is absent from path binding: {path}"
                )
            if (old_mode, new_mode) not in allowed_mode_transitions:
                raise HarnessError(
                    f"PR #{item.number} uses a deletion, executable-bit drift, "
                    "symlink, submodule, or unsupported Git mode at "
                    f"{path}: {old_mode}->{new_mode}"
                )
        patch_id = self.git.stable_patch_id(source_base, source_head)
        semantic_digest = self.git.semantic_patch_digest(source_base, source_head)
        path_digest = self.git.changed_paths_digest(source_base, source_head)
        exact_diff_digest = self.git.exact_diff_digest(source_base, source_head)
        if (
            source_head == item.reviewed_subject_head
            and source_base != item.reviewed_subject_base
        ):
            raise HarnessError(
                f"PR #{item.number} reviewed-subject base provenance drift: "
                f"{source_base} != {item.reviewed_subject_base}"
            )
        if (
            source_head == item.reviewed_subject_head
            and exact_diff_digest != item.reviewed_exact_diff_sha256
        ):
            raise HarnessError(
                f"PR #{item.number} reviewed-subject exact diff provenance drift: "
                f"{exact_diff_digest} != {item.reviewed_exact_diff_sha256}"
            )
        name_status_digest = self.git.name_status_digest(source_base, source_head)
        locked_path_set = set(item.locked_paths)
        refreshable_path_set = set(item.refreshable_paths)
        unexpected_refresh_paths = sorted(
            changed_path_set - locked_path_set - refreshable_path_set
        )
        if unexpected_refresh_paths:
            raise HarnessError(
                f"PR #{item.number} changed paths are outside the exact refresh "
                f"partition: {unexpected_refresh_paths}"
            )
        missing_locked_paths = sorted(locked_path_set - changed_path_set)
        if missing_locked_paths:
            raise HarnessError(
                f"PR #{item.number} locked reviewed paths disappeared: "
                f"{missing_locked_paths}"
            )
        locked_semantic_digest = self.git.semantic_patch_digest_for_paths(
            source_base, source_head, item.locked_paths
        )
        if locked_semantic_digest != item.locked_semantic_patch_sha256:
            raise HarnessError(
                f"PR #{item.number} non-refreshable semantic content drift: "
                f"{locked_semantic_digest} != "
                f"{item.locked_semantic_patch_sha256}"
            )
        locked_name_status_digest = self.git.name_status_digest_for_paths(
            source_base, source_head, item.locked_paths
        )
        if locked_name_status_digest != item.locked_name_status_sha256:
            raise HarnessError(
                f"PR #{item.number} non-refreshable name-status drift: "
                f"{locked_name_status_digest} != "
                f"{item.locked_name_status_sha256}"
            )
        original_binding = (
            patch_id == item.stable_patch_id
            and semantic_digest == item.semantic_patch_sha256
            and path_digest == item.changed_paths_sha256
            and name_status_digest == item.name_status_sha256
        )
        if item.accepted_integration is not None and not original_binding:
            raise HarnessError(
                f"PR #{item.number} accepted bootstrap content cannot be refreshed"
            )
        binding_mode = (
            "original-reviewed-subject"
            if original_binding
            else "refreshed-generation-1"
        )
        refreshed_paths = tuple(
            sorted(changed_path_set & refreshable_path_set)
            if not original_binding
            else ()
        )
        removed_reviewed_paths = tuple(
            sorted(
                (set(item.reviewed_changed_paths) & refreshable_path_set)
                - changed_path_set
            )
            if not original_binding
            else ()
        )
        for path in removed_reviewed_paths:
            expected_result = item.reviewed_result_entries[path]
            observed_base_result = self.git.path_identity(source_base, path)
            if observed_base_result != expected_result:
                raise HarnessError(
                    f"PR #{item.number} reviewed path disappeared without exact "
                    f"base subsumption at {path}: {observed_base_result!r} != "
                    f"{expected_result!r}"
                )
        return ContentBinding(
            base_sha=source_base,
            head_sha=source_head,
            changed_paths=changed_paths,
            stable_patch_id=patch_id,
            semantic_patch_sha256=semantic_digest,
            changed_paths_sha256=path_digest,
            exact_diff_sha256=exact_diff_digest,
            name_status_sha256=name_status_digest,
            binding_mode=binding_mode,
            refreshed_paths=refreshed_paths,
            removed_reviewed_paths=removed_reviewed_paths,
        )

    def _pull_source_identity(
        self, pull: Mapping[str, Any], item: QueueItem
    ) -> tuple[str, str]:
        if pull.get("number") != item.number:
            raise HarnessError(f"PR #{item.number} number identity drift")
        base = pull.get("base")
        head = pull.get("head")
        if not isinstance(base, dict) or not isinstance(head, dict):
            raise HarnessError(f"PR #{item.number} base/head metadata missing")
        base_repo = base.get("repo")
        head_repo = head.get("repo")
        if (
            base.get("ref") != self.policy.base_branch
            or head.get("ref") != item.branch
            or not isinstance(base_repo, dict)
            or base_repo.get("full_name") != self.policy.repository
            or not isinstance(head_repo, dict)
            or head_repo.get("full_name") != self.policy.repository
        ):
            raise HarnessError(f"PR #{item.number} repo/base/branch identity drift")
        source_base = base.get("sha")
        source_head = head.get("sha")
        if (
            not isinstance(source_base, str)
            or not HEX40.fullmatch(source_base)
            or not isinstance(source_head, str)
            or not HEX40.fullmatch(source_head)
        ):
            raise HarnessError(f"PR #{item.number} source SHAs must be lowercase 40-hex")
        return source_base, source_head

    def _validate_open_pull(
        self,
        pull: Mapping[str, Any],
        item: QueueItem,
        expected_base: str,
        expected_head: str,
    ) -> None:
        if pull.get("number") != item.number or pull.get("state") != "open":
            raise HarnessError("target pull identity/state mismatch")
        if pull.get("merged_at") is not None:
            raise HarnessError("target pull is already merged")
        if "auto_merge" not in pull or pull.get("auto_merge") is not None:
            raise HarnessError("target pull must have auto-merge disabled")
        source_base, source_head = self._pull_source_identity(pull, item)
        if source_base != expected_base:
            raise HarnessError("live pull base differs from explicit expected base")
        if source_head != expected_head:
            raise HarnessError("live pull branch/head differs from explicit candidate")
        if pull.get("mergeable") is not True:
            raise HarnessError("pull is not currently confirmed mergeable")

    def _validate_reviews(self, number: int) -> None:
        threads = self.github.review_threads(number)
        unresolved: list[str] = []
        for thread in threads:
            if not isinstance(thread, dict):
                raise HarnessError("malformed review thread")
            thread_id = thread.get("id")
            resolved = thread.get("isResolved")
            if not isinstance(thread_id, str) or not thread_id:
                raise HarnessError("review thread identity malformed")
            if type(resolved) is not bool:
                raise HarnessError("review thread resolved state must be exact boolean")
            if not resolved:
                unresolved.append(thread_id)
        if unresolved:
            raise HarnessError(f"unresolved review threads: {unresolved}")
        latest_by_reviewer: dict[str, tuple[int, str]] = {}
        for review in self.github.reviews(number):
            if not isinstance(review, dict):
                raise HarnessError("malformed review entry")
            user = review.get("user")
            if not isinstance(user, dict):
                raise HarnessError("review user missing")
            reviewer = str(user.get("id") or user.get("login") or "")
            review_id = review.get("id")
            state = review.get("state")
            if not reviewer or type(review_id) is not int or not isinstance(state, str):
                raise HarnessError("review identity/state malformed")
            decisive_state = state.upper()
            if decisive_state not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                continue
            previous = latest_by_reviewer.get(reviewer)
            if previous is None or review_id > previous[0]:
                latest_by_reviewer[reviewer] = (review_id, decisive_state)
        blockers = [
            reviewer
            for reviewer, (_review_id, state) in latest_by_reviewer.items()
            if state == "CHANGES_REQUESTED"
        ]
        if blockers:
            raise HarnessError(f"active changes-requested reviews: {blockers}")
        approvals = [
            reviewer
            for reviewer, (_review_id, state) in latest_by_reviewer.items()
            if state == "APPROVED"
        ]
        if (
            self.policy.review_topology["formal_independent_human_approval"] is False
            and approvals
        ):
            raise HarnessError(
                "formal independent human approval topology drift: "
                f"active approvals from {approvals}"
            )

    def _validate_independent_review_receipt(
        self,
        document: Mapping[str, Any],
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        *,
        certificate_created_at: str | None = None,
    ) -> IndependentReviewReceipt:
        expected_keys = {
            "accessed",
            "binding_mode",
            "blocking_findings",
            "changed_paths",
            "changed_paths_sha256",
            "completion_claim",
            "exact_base",
            "exact_diff_sha256",
            "exact_head",
            "exact_head_tree",
            "external_contact_performed",
            "formal_independent_human_approval",
            "name_status_sha256",
            "policy_id",
            "pull_request",
            "refreshed_paths",
            "removed_reviewed_paths",
            "repository",
            "result",
            "review_scope",
            "reviewed_at",
            "reviewer_task",
            "role",
            "schema_version",
            "semantic_patch_sha256",
            "stable_patch_id",
            "subject_refresh_generation",
            "work_id",
        }
        _exact_keys(document, expected_keys, "independent review receipt")
        accessed = document["accessed"]
        if not isinstance(accessed, dict):
            raise HarnessError("independent review receipt accessed must be an object")
        _exact_keys(
            accessed,
            {"artifact_or_package_content", "credentials", "learner_outputs"},
            "independent review receipt accessed",
        )
        for key, value in accessed.items():
            if value is not False:
                raise HarnessError(
                    "independent review receipt records prohibited content access: "
                    f"{key}"
                )
        reviewer_id = document["reviewer_task"]
        if (
            not isinstance(reviewer_id, str)
            or INDEPENDENT_REVIEWER_ID.fullmatch(reviewer_id) is None
        ):
            raise HarnessError(
                "reviewer task must name a bounded independent /root/<agent> task"
            )
        reviewed_at = document["reviewed_at"]
        reviewed_timestamp = parse_utc_timestamp(
            reviewed_at, "independent review receipt reviewed_at"
        )
        now = dt.datetime.now(dt.timezone.utc)
        if reviewed_timestamp < SUBJECT_REFRESH_NOT_BEFORE:
            raise HarnessError(
                "independent review predates the subject-refresh delegation"
            )
        if reviewed_timestamp > now + REVIEW_CLOCK_SKEW:
            raise HarnessError("independent review timestamp is in the future")
        if certificate_created_at is not None:
            certificate_timestamp = parse_utc_timestamp(
                certificate_created_at,
                "subject refresh certificate created_at",
            )
            if reviewed_timestamp > certificate_timestamp + REVIEW_CLOCK_SKEW:
                raise HarnessError(
                    "independent review occurs after its refresh certificate"
                )
        expected_values = {
            "binding_mode": "refreshed-generation-1",
            "blocking_findings": [],
            "changed_paths": list(binding.changed_paths),
            "changed_paths_sha256": binding.changed_paths_sha256,
            "completion_claim": item.completion_claim,
            "exact_base": binding.base_sha,
            "exact_diff_sha256": binding.exact_diff_sha256,
            "exact_head": binding.head_sha,
            "exact_head_tree": head_tree,
            "external_contact_performed": False,
            "formal_independent_human_approval": "absent",
            "name_status_sha256": binding.name_status_sha256,
            "policy_id": self.policy.policy_id,
            "pull_request": item.number,
            "refreshed_paths": list(binding.refreshed_paths),
            "removed_reviewed_paths": list(binding.removed_reviewed_paths),
            "repository": self.policy.repository,
            "result": "PASS",
            "review_scope": "exact-candidate-source-only",
            "role": "independent-read-only",
            "schema_version": 1,
            "semantic_patch_sha256": binding.semantic_patch_sha256,
            "stable_patch_id": binding.stable_patch_id,
            "subject_refresh_generation": 1,
            "work_id": item.work_id,
        }
        for key, expected in expected_values.items():
            _require_exact_value(
                document[key],
                expected,
                f"independent review receipt {key}",
            )
        payload = dict(document)
        payload_json = canonical_json(payload)
        return IndependentReviewReceipt(
            payload=payload,
            sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
        )

    def _validate_subject_refresh_certificate(
        self,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
    ) -> RefreshCertificate | None:
        marker = subject_refresh_marker(item.number, binding.head_sha)
        matching = []
        for comment in self.github.comments(item.number):
            body = comment.get("body")
            if marker not in str(body):
                continue
            matching.append(comment)
        if binding.binding_mode == "original-reviewed-subject":
            if matching:
                raise HarnessError(
                    "an original reviewed-subject binding cannot claim refresh evidence"
                )
            return None
        if len(matching) != 1:
            raise HarnessError(
                "exact owner-authored generation-1 subject refresh certificate "
                "is absent or duplicated"
            )
        comment = matching[0]
        body = comment.get("body")
        user = comment.get("user")
        prefix = (
            f"{marker}\n"
            "Protected integration v1 subject refresh certificate\n\n"
        )
        if (
            not isinstance(body, str)
            or not body.startswith(prefix)
            or not isinstance(user, dict)
            or user.get("id") != self.policy.review_topology["owner_id"]
            or user.get("login") != self.policy.review_topology["owner_login"]
            or user.get("type") != "User"
            or comment.get("author_association") != "OWNER"
        ):
            raise HarnessError("subject refresh marker/body/author collision")
        comment_id = comment.get("id")
        created_at = comment.get("created_at")
        updated_at = comment.get("updated_at")
        if (
            type(comment_id) is not int
            or comment_id <= 0
            or not isinstance(created_at, str)
            or created_at != updated_at
        ):
            raise HarnessError(
                "subject refresh comment identity or immutable timestamp is invalid"
            )
        created_timestamp = parse_utc_timestamp(
            created_at, "subject refresh certificate created_at"
        )
        if created_timestamp < SUBJECT_REFRESH_NOT_BEFORE:
            raise HarnessError(
                "subject refresh certificate predates its delegation"
            )
        if created_timestamp > dt.datetime.now(dt.timezone.utc) + REVIEW_CLOCK_SKEW:
            raise HarnessError("subject refresh certificate timestamp is in the future")
        try:
            payload = json.loads(body[len(prefix) :])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HarnessError("subject refresh payload is malformed") from exc
        if not isinstance(payload, dict) or canonical_json(payload) != body[len(prefix) :]:
            raise HarnessError("subject refresh payload is not canonical JSON")
        expected_keys = {
            "accessed",
            "binding_mode",
            "changed_paths_sha256",
            "exact_base",
            "exact_diff_sha256",
            "exact_head",
            "exact_head_tree",
            "external_contact_performed",
            "formal_independent_human_approval",
            "independent_read_only_agent_review",
            "name_status_sha256",
            "policy_id",
            "policy_reviewed_subject_base",
            "policy_reviewed_subject_head",
            "pull_request",
            "refresh_generation",
            "refresh_reason",
            "refreshed_paths",
            "removed_reviewed_paths",
            "repository",
            "review_receipt",
            "review_receipt_sha256",
            "semantic_patch_sha256",
            "stable_patch_id",
            "subject_refresh_accepted_date",
            "work_id",
        }
        _exact_keys(payload, expected_keys, "subject refresh payload")
        accessed = payload["accessed"]
        if not isinstance(accessed, dict):
            raise HarnessError("subject refresh accessed record must be an object")
        _exact_keys(
            accessed,
            {"artifact_or_package_content", "credentials", "learner_outputs"},
            "subject refresh accessed",
        )
        if any(value is not False for value in accessed.values()):
            raise HarnessError("subject refresh records prohibited content access")
        receipt_raw = payload["review_receipt"]
        if not isinstance(receipt_raw, dict):
            raise HarnessError("subject refresh review receipt must be an object")
        receipt = self._validate_independent_review_receipt(
            receipt_raw,
            item,
            binding,
            head_tree,
            certificate_created_at=created_at,
        )
        receipt_digest = payload["review_receipt_sha256"]
        if (
            not isinstance(receipt_digest, str)
            or HEX64.fullmatch(receipt_digest) is None
            or receipt_digest != receipt.sha256
        ):
            raise HarnessError("subject refresh review receipt digest is invalid")
        expected_values = {
            "binding_mode": "refreshed-generation-1",
            "changed_paths_sha256": binding.changed_paths_sha256,
            "exact_base": binding.base_sha,
            "exact_diff_sha256": binding.exact_diff_sha256,
            "exact_head": binding.head_sha,
            "exact_head_tree": head_tree,
            "external_contact_performed": False,
            "formal_independent_human_approval": "absent",
            "independent_read_only_agent_review": "PASS",
            "name_status_sha256": binding.name_status_sha256,
            "policy_id": self.policy.policy_id,
            "policy_reviewed_subject_base": item.reviewed_subject_base,
            "policy_reviewed_subject_head": item.reviewed_subject_head,
            "pull_request": item.number,
            "refresh_generation": 1,
            "refresh_reason": "serial-integration-reconciliation",
            "refreshed_paths": list(binding.refreshed_paths),
            "removed_reviewed_paths": list(binding.removed_reviewed_paths),
            "repository": self.policy.repository,
            "semantic_patch_sha256": binding.semantic_patch_sha256,
            "stable_patch_id": binding.stable_patch_id,
            "subject_refresh_accepted_date": self.policy.delegation[
                "subject_refresh_accepted_date"
            ],
            "work_id": item.work_id,
        }
        for key, expected in expected_values.items():
            _require_exact_value(
                payload[key],
                expected,
                f"subject refresh payload {key}",
            )
        return RefreshCertificate(
            comment_id=comment_id,
            body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            review_receipt_sha256=receipt_digest,
            reviewer_id=receipt.reviewer_id,
            reviewed_at=receipt.reviewed_at,
        )

    def _validate_review_topology_and_attestation(
        self,
        item: QueueItem,
        binding: ContentBinding,
        head_tree: str,
        refresh: RefreshCertificate | None,
    ) -> None:
        self._validate_collaborator_topology()
        topology = self.policy.review_topology
        expected_marker = owner_attestation_marker(item.number, binding.head_sha)
        expected_body = (
            owner_attestation_body(
                self.policy,
                item,
                binding.base_sha,
                binding.head_sha,
                head_tree,
                binding.exact_diff_sha256,
            )
            if refresh is None
            else refreshed_owner_attestation_body(
                self.policy,
                item,
                binding,
                head_tree,
                refresh,
            )
        )
        matches = []
        for comment in self.github.comments(item.number):
            body = comment.get("body")
            if expected_marker not in str(body):
                continue
            user = comment.get("user")
            if (
                body != expected_body
                or not isinstance(user, dict)
                or user.get("id") != topology["owner_id"]
                or user.get("login") != topology["owner_login"]
                or user.get("type") != "User"
                or comment.get("author_association") != "OWNER"
            ):
                raise HarnessError("owner attestation marker/body/author collision")
            matches.append(comment)
        if len(matches) != 1:
            raise HarnessError(
                "exact owner-authored independent-agent/risk attestation is absent "
                "or duplicated"
            )

    def _validate_collaborator_topology(self) -> None:
        collaborators = self.github.direct_collaborators()
        topology = self.policy.review_topology
        if len(collaborators) != topology["direct_collaborators"]:
            raise HarnessError("live direct-collaborator count drift")
        collaborator = collaborators[0]
        permissions = collaborator.get("permissions")
        if (
            collaborator.get("id") != topology["owner_id"]
            or collaborator.get("login") != topology["owner_login"]
            or collaborator.get("type") != "User"
            or not isinstance(permissions, dict)
            or permissions.get("admin") is not True
        ):
            raise HarnessError("live direct-collaborator owner/admin topology drift")

    def _validate_authenticated_actor(self) -> None:
        actor = self.github.authenticated_user()
        topology = self.policy.review_topology
        if (
            actor.get("id") != topology["owner_id"]
            or actor.get("login") != topology["owner_login"]
            or actor.get("type") != "User"
        ):
            raise HarnessError(
                "authenticated GitHub actor is not the pinned repository owner"
            )

    def _validate_merged_by_owner(
        self, pull: Mapping[str, Any], number: int
    ) -> None:
        actor = pull.get("merged_by")
        topology = self.policy.review_topology
        if (
            not isinstance(actor, dict)
            or actor.get("id") != topology["owner_id"]
            or actor.get("login") != topology["owner_login"]
            or actor.get("type") != "User"
        ):
            raise HarnessError(
                f"PR #{number} was not merged by the pinned repository owner"
            )

    def _validate_state_identity(
        self,
        document: Mapping[str, Any],
        item: QueueItem,
        expected_base: str,
        expected_head: str,
    ) -> None:
        validate_state_shape(document)
        expected = {
            "policy_id": self.policy.policy_id,
            "repository": self.policy.repository,
            "number": item.number,
            "work_id": item.work_id,
            "expected_base": expected_base,
            "expected_head": expected_head,
        }
        for key, value in expected.items():
            if document.get(key) != value:
                raise HarnessError(f"transaction state identity drift: {key}")
        if document.get("stage") == "complete":
            checks = document.get("post_merge_checks")
            if (
                not isinstance(checks, dict)
                or set(checks) != set(self.policy.required_checks)
                or len(checks) != len(self.policy.required_checks)
            ):
                raise HarnessError("complete state required-check context drift")

    def _post_evidence_payload(
        self, document: Mapping[str, Any]
    ) -> dict[str, Any]:
        item = self.policy.item(_exact_int(document.get("number"), "evidence PR number"))
        expected_base = _nonempty_string(
            document.get("expected_base"), "evidence expected base"
        )
        expected_head = _nonempty_string(
            document.get("expected_head"), "evidence expected head"
        )
        head_tree = _nonempty_string(
            document.get("head_tree"), "evidence head tree"
        )
        binding = self._validate_content_binding(
            item, expected_base, expected_head
        )
        refresh = self._validate_subject_refresh_certificate(
            item, binding, head_tree
        )
        return {
            "policy_id": self.policy.policy_id,
            "number": document.get("number"),
            "work_id": item.work_id,
            "completion_claim": item.completion_claim,
            "expected_base": expected_base,
            "expected_head": expected_head,
            "head_tree": head_tree,
            "merge_sha": document.get("merge_sha"),
            "policy_reviewed_subject_base": item.reviewed_subject_base,
            "policy_reviewed_subject_head": item.reviewed_subject_head,
            "policy_semantic_patch_sha256": item.semantic_patch_sha256,
            "policy_changed_paths_sha256": item.changed_paths_sha256,
            "policy_name_status_sha256": item.name_status_sha256,
            "binding_mode": binding.binding_mode,
            "stable_patch_id": binding.stable_patch_id,
            "semantic_patch_sha256": binding.semantic_patch_sha256,
            "changed_paths_sha256": binding.changed_paths_sha256,
            "current_exact_diff_sha256": binding.exact_diff_sha256,
            "name_status_sha256": binding.name_status_sha256,
            "refreshed_paths": list(binding.refreshed_paths),
            "removed_reviewed_paths": list(binding.removed_reviewed_paths),
            "refresh_certificate_comment_id": (
                refresh.comment_id if refresh is not None else None
            ),
            "refresh_certificate_body_sha256": (
                refresh.body_sha256 if refresh is not None else None
            ),
            "review_receipt_sha256": (
                refresh.review_receipt_sha256 if refresh is not None else None
            ),
            "ruleset_id": self.policy.ruleset_id,
            "post_merge_checks": document.get("post_merge_checks"),
        }

    def _post_evidence_values(
        self,
        item: QueueItem,
        source_base: str,
        source_head: str,
        head_tree: str,
        merge_sha: str,
        checks: Mapping[str, int],
    ) -> dict[str, Any]:
        binding = self._validate_content_binding(item, source_base, source_head)
        refresh = self._validate_subject_refresh_certificate(
            item, binding, head_tree
        )
        return {
            "policy_id": self.policy.policy_id,
            "number": item.number,
            "work_id": item.work_id,
            "completion_claim": item.completion_claim,
            "expected_base": source_base,
            "expected_head": source_head,
            "head_tree": head_tree,
            "merge_sha": merge_sha,
            "policy_reviewed_subject_base": item.reviewed_subject_base,
            "policy_reviewed_subject_head": item.reviewed_subject_head,
            "policy_semantic_patch_sha256": item.semantic_patch_sha256,
            "policy_changed_paths_sha256": item.changed_paths_sha256,
            "policy_name_status_sha256": item.name_status_sha256,
            "binding_mode": binding.binding_mode,
            "stable_patch_id": binding.stable_patch_id,
            "semantic_patch_sha256": binding.semantic_patch_sha256,
            "changed_paths_sha256": binding.changed_paths_sha256,
            "current_exact_diff_sha256": binding.exact_diff_sha256,
            "name_status_sha256": binding.name_status_sha256,
            "refreshed_paths": list(binding.refreshed_paths),
            "removed_reviewed_paths": list(binding.removed_reviewed_paths),
            "refresh_certificate_comment_id": (
                refresh.comment_id if refresh is not None else None
            ),
            "refresh_certificate_body_sha256": (
                refresh.body_sha256 if refresh is not None else None
            ),
            "review_receipt_sha256": (
                refresh.review_receipt_sha256 if refresh is not None else None
            ),
            "ruleset_id": self.policy.ruleset_id,
            "post_merge_checks": dict(checks),
        }

    def _require_postmerge_evidence_comment(
        self,
        item: QueueItem,
        source_base: str,
        source_head: str,
        head_tree: str,
        merge_sha: str,
        checks: Mapping[str, int],
    ) -> None:
        evidence = self._post_evidence_values(
            item,
            source_base,
            source_head,
            head_tree,
            merge_sha,
            checks,
        )
        marker = governed_evidence_marker(
            item.number,
            source_head,
            "postmerge",
            evidence,
        )
        expected_body = postmerge_evidence_body(marker, evidence)
        topology = self.policy.review_topology
        matches = []
        for comment in self.github.comments(item.number):
            body = comment.get("body")
            if marker not in str(body):
                continue
            user = comment.get("user")
            if (
                body != expected_body
                or not isinstance(user, dict)
                or user.get("id") != topology["owner_id"]
                or user.get("login") != topology["owner_login"]
                or user.get("type") != "User"
                or comment.get("author_association") != "OWNER"
            ):
                raise HarnessError("post-merge evidence marker/body/author collision")
            matches.append(comment)
        if len(matches) != 1:
            raise HarnessError(
                f"PR #{item.number} exact post-merge evidence comment is absent "
                "or duplicated"
            )

def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("expected a value greater than zero")
    return parsed


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative value")
    return parsed


def _settle_seconds(value: str) -> float:
    parsed = _nonnegative_float(value)
    if parsed > 60:
        raise argparse.ArgumentTypeError("settlement delay must be at most 60 seconds")
    return parsed


def _poll_seconds(value: str) -> float:
    parsed = _positive_float(value)
    if parsed > 60:
        raise argparse.ArgumentTypeError("poll delay must be at most 60 seconds")
    return parsed


def _timeout_seconds(value: str) -> float:
    parsed = _positive_float(value)
    if parsed > 7200:
        raise argparse.ArgumentTypeError("timeout must be at most 7200 seconds")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed fixed-queue protected-main integration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-policy", help="validate policy without network")

    def transaction(name: str, help_text: str) -> argparse.ArgumentParser:
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--pr", type=int, required=True)
        child.add_argument("--expected-base", type=exact_sha, required=True)
        child.add_argument("--expected-head", type=exact_sha, required=True)
        return child

    transaction("preflight", "run read-only exact candidate gates")
    attest = transaction(
        "attest-refresh",
        "record an independently reviewed generation-1 subject refresh",
    )
    attest.add_argument(
        "--review-receipt-json",
        required=True,
        help=(
            "canonical JSON receipt returned by the independent read-only "
            "exact-candidate reviewer"
        ),
    )
    ready = transaction("mark-ready", "mark ready, settle, and revalidate")
    ready.add_argument("--settle-seconds", type=_settle_seconds, default=5.0)
    merge = transaction("merge", "exact-head merge and post-merge validation")
    merge.add_argument("--settle-seconds", type=_settle_seconds, default=5.0)
    merge.add_argument("--poll-seconds", type=_poll_seconds, default=15.0)
    merge.add_argument("--timeout-seconds", type=_timeout_seconds, default=3600.0)
    return parser


def repository_root(runner: Runner) -> Path:
    result = runner.run(
        ["git", "--no-replace-objects", "rev-parse", "--show-toplevel"]
    )
    return Path(result.stdout.strip()).resolve()


def canonical_repository_context(runner: Runner) -> tuple[Path, Path]:
    root = repository_root(runner)
    try:
        expected_script = (root / SCRIPT_RELATIVE).resolve(strict=True)
        executed_script = Path(__file__).resolve(strict=True)
        policy_path = (root / POLICY_RELATIVE).resolve(strict=True)
    except OSError as exc:
        raise HarnessError(f"canonical harness authority is unavailable: {exc}") from exc
    if executed_script != expected_script:
        raise HarnessError(
            "executed __file__ is not the canonical repository harness script"
        )
    if policy_path != root / POLICY_RELATIVE:
        raise HarnessError("canonical policy resolves through an unexpected link")
    return root, policy_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    runner = SubprocessRunner()
    try:
        root, policy_path = canonical_repository_context(runner)
        policy = Policy.load(policy_path)
        if arguments.command == "validate-policy":
            print(
                json.dumps(
                    {
                        "policy_id": policy.policy_id,
                        "repository": policy.repository,
                        "queue": [item.number for item in policy.queue],
                        "required_checks": list(policy.required_checks),
                        "result": "PASS",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        git = GitRepository(root, runner)
        github = GitHubClient(runner, policy.repository)
        state = StateStore(git.common_dir)
        harness = IntegrationHarness(policy, git, github, state)
        if arguments.command == "preflight":
            with state.lock():
                result: object = harness.preflight(
                    arguments.pr, arguments.expected_base, arguments.expected_head
                ).as_dict()
        elif arguments.command == "attest-refresh":
            result = harness.attest_refresh(
                arguments.pr,
                arguments.expected_base,
                arguments.expected_head,
                review_receipt_json=arguments.review_receipt_json,
            ).as_dict()
        elif arguments.command == "mark-ready":
            result = harness.mark_ready(
                arguments.pr,
                arguments.expected_base,
                arguments.expected_head,
                settle_seconds=arguments.settle_seconds,
            ).as_dict()
        elif arguments.command == "merge":
            result = harness.merge(
                arguments.pr,
                arguments.expected_base,
                arguments.expected_head,
                settle_seconds=arguments.settle_seconds,
                poll_seconds=arguments.poll_seconds,
                timeout_seconds=arguments.timeout_seconds,
            )
        else:  # pragma: no cover - argparse owns the command set.
            raise HarnessError(f"unsupported command: {arguments.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except HarnessError as exc:
        print(f"protected integration refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
