"""Enforce reviewed immutable GitHub Action references in workflow files."""

from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
ACTION_LOCK_PATH = ROOT / ".github" / "actions-lock.json"
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
DOCKER_DIGEST_RE = re.compile(r"docker://[^@\s]+@sha256:[0-9a-f]{64}")
ACTION_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RELEASE_RE = re.compile(r"v[0-9]+(?:\.[0-9]+)+(?:[-+][A-Za-z0-9_.-]+)?")
MINIMUM_ACTIONS_RUNNER = "2.327.1"
LOCK_KEYS = {"schema_version", "minimum_actions_runner", "policy", "actions"}
POLICY_KEYS = {
    "require_full_commit_sha",
    "require_release_comment",
    "required_runtime",
}
ACTION_RECORD_KEYS = {
    "release",
    "runtime",
    "sha",
    "source",
    "upstream_commit_verified",
}


def workflow_files(workflow_root: Path = WORKFLOW_ROOT) -> list[Path]:
    """Return top-level workflow YAML files in stable order."""

    return sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))


def _collect_uses(node: Node, path: Path, references: list[tuple[int, str]]) -> None:
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode) and key_node.value == "uses":
                if not isinstance(value_node, ScalarNode):
                    line_number = value_node.start_mark.line + 1
                    raise ValueError(f"{path}:{line_number}: uses value must be a scalar")
                references.append((value_node.start_mark.line + 1, value_node.value))
            _collect_uses(value_node, path, references)
    elif isinstance(node, SequenceNode):
        for child in node.value:
            _collect_uses(child, path, references)


def _file_uses(path: Path) -> list[tuple[int, str]]:
    try:
        documents = yaml.compose_all(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
        references: list[tuple[int, str]] = []
        for document in documents:
            if document is not None:
                _collect_uses(document, path, references)
        return references
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"could not parse action source {path}: {exc}") from exc


def _resolve_local_action(reference: str, repository_root: Path) -> Path:
    root = repository_root.resolve()
    candidate = (root / reference.removeprefix("./")).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError(f"local action escapes repository root: {reference}")
    if candidate.is_file() and candidate.suffix in {".yml", ".yaml"}:
        return candidate
    if not candidate.is_dir():
        raise ValueError(f"local action path does not exist: {reference}")
    definitions = [
        path
        for path in (candidate / "action.yml", candidate / "action.yaml")
        if path.is_file()
    ]
    if len(definitions) != 1:
        raise ValueError(
            f"local action must contain exactly one action.yml or action.yaml: {reference}"
        )
    definition = definitions[0].resolve()
    if not definition.is_relative_to(root):
        raise ValueError(f"local action definition escapes repository root: {reference}")
    return definition


def external_action_references(
    paths: list[Path],
    *,
    repository_root: Path = ROOT,
) -> list[tuple[Path, int, str]]:
    """Return external refs while recursively validating repository-local actions."""

    references: list[tuple[Path, int, str]] = []
    pending = deque(paths)
    visited: set[Path] = set()
    root = repository_root.resolve()
    while pending:
        path = pending.popleft().resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"action source escapes repository root: {path}")
        if path in visited:
            continue
        visited.add(path)
        for line_number, reference in _file_uses(path):
            if reference.startswith("./"):
                pending.append(_resolve_local_action(reference, repository_root))
            else:
                references.append((path, line_number, reference))
    return references


def unpinned_references(
    references: list[tuple[Path, int, str]],
) -> list[tuple[Path, int, str]]:
    """Return references without a full commit SHA or Docker image digest."""

    unpinned: list[tuple[Path, int, str]] = []
    for path, line_number, reference in references:
        if reference.startswith("docker://"):
            if DOCKER_DIGEST_RE.fullmatch(reference) is None:
                unpinned.append((path, line_number, reference))
            continue
        revision = reference.rsplit("@", 1)[-1] if "@" in reference else ""
        if FULL_SHA_RE.fullmatch(revision) is None:
            unpinned.append((path, line_number, reference))
    return unpinned


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def action_lock_metadata_errors(payload: object) -> list[str]:
    """Return schema and provenance errors in the reviewed Action allowlist."""

    if not isinstance(payload, dict):
        return ["lock root must be a JSON object"]

    errors: list[str] = []
    if set(payload) != LOCK_KEYS:
        errors.append(f"lock keys must be {sorted(LOCK_KEYS)}")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        errors.append("schema_version must equal 1")
    runner_version = payload.get("minimum_actions_runner")
    if runner_version != MINIMUM_ACTIONS_RUNNER:
        errors.append(f"minimum_actions_runner must equal {MINIMUM_ACTIONS_RUNNER}")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("policy must be a JSON object")
        required_runtime = None
    else:
        if set(policy) != POLICY_KEYS:
            errors.append(f"policy keys must be {sorted(POLICY_KEYS)}")
        required_runtime = policy.get("required_runtime")
        if policy.get("require_full_commit_sha") is not True:
            errors.append("policy.require_full_commit_sha must be true")
        if policy.get("require_release_comment") is not True:
            errors.append("policy.require_release_comment must be true")
        if required_runtime != "node24":
            errors.append("policy.required_runtime must equal node24")

    actions = payload.get("actions")
    if not isinstance(actions, dict) or not actions:
        errors.append("actions must be a non-empty JSON object")
        return errors

    for action_name, record in actions.items():
        prefix = f"actions.{action_name}"
        if ACTION_NAME_RE.fullmatch(action_name) is None:
            errors.append(f"{prefix}: invalid owner/repository name")
        if not isinstance(record, dict):
            errors.append(f"{prefix}: record must be a JSON object")
            continue
        if set(record) != ACTION_RECORD_KEYS:
            errors.append(f"{prefix}: record keys must be {sorted(ACTION_RECORD_KEYS)}")
            continue
        release = record["release"]
        sha = record["sha"]
        runtime = record["runtime"]
        source = record["source"]
        if not isinstance(release, str) or RELEASE_RE.fullmatch(release) is None:
            errors.append(f"{prefix}.release: invalid release tag")
        if not isinstance(sha, str) or FULL_SHA_RE.fullmatch(sha) is None:
            errors.append(f"{prefix}.sha: expected a full lowercase commit SHA")
        if runtime != required_runtime:
            errors.append(f"{prefix}.runtime: expected {required_runtime}")
        expected_source = f"https://github.com/{action_name}/releases/tag/{release}"
        if source != expected_source:
            errors.append(f"{prefix}.source: expected {expected_source}")
        if record["upstream_commit_verified"] is not True:
            errors.append(f"{prefix}.upstream_commit_verified: must be true")
    return errors


def load_action_lock(path: Path = ACTION_LOCK_PATH) -> dict[str, Any]:
    """Load the reviewed Action allowlist and reject ambiguous metadata."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"could not load {path}: {exc}") from exc
    errors = action_lock_metadata_errors(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return payload


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def reviewed_reference_errors(
    references: list[tuple[Path, int, str]],
    payload: dict[str, Any],
) -> list[str]:
    """Return workflow references that differ from the reviewed allowlist."""

    actions: dict[str, dict[str, Any]] = payload["actions"]
    referenced_actions: set[str] = set()
    errors: list[str] = []
    line_cache: dict[Path, list[str]] = {}

    for path, line_number, reference in references:
        if reference.startswith("docker://"):
            errors.append(f"UNREVIEWED {_display_path(path)}:{line_number}: {reference}")
            continue
        action_name, separator, revision = reference.rpartition("@")
        location = f"{_display_path(path)}:{line_number}"
        if not separator:
            errors.append(f"UNREVIEWED {location}: {reference}")
            continue
        record = actions.get(action_name)
        if record is None:
            errors.append(f"UNREVIEWED {location}: {reference}")
            continue
        referenced_actions.add(action_name)
        if revision != record["sha"]:
            errors.append(
                f"SHA_MISMATCH {location}: expected {action_name}@{record['sha']}, got {reference}"
            )
        lines = line_cache.setdefault(path, path.read_text(encoding="utf-8").splitlines())
        expected_comment = f"# {record['release']}"
        if line_number > len(lines) or not lines[line_number - 1].rstrip().endswith(expected_comment):
            errors.append(f"RELEASE_COMMENT_MISMATCH {location}: expected {expected_comment}")

    for action_name in sorted(set(actions) - referenced_actions):
        errors.append(f"UNUSED_LOCK actions.{action_name}")
    return errors


def main() -> int:
    paths = workflow_files()
    try:
        references = external_action_references(paths)
    except ValueError as exc:
        print(f"ACTION_SOURCE_INVALID {exc}")
        print("status: FAIL")
        return 1
    unpinned = unpinned_references(references)
    try:
        action_lock = load_action_lock()
    except ValueError as exc:
        action_lock = None
        reviewed_errors = [f"ACTION_LOCK_INVALID {exc}"]
    else:
        reviewed_errors = reviewed_reference_errors(references, action_lock)

    print(f"workflow files: {len(paths)}")
    print(f"external action references: {len(references)}")
    if action_lock is not None:
        print(f"reviewed action repositories: {len(action_lock['actions'])}")
        print(
            "required action runtime:",
            action_lock["policy"]["required_runtime"],
        )
    for path, line_number, reference in unpinned:
        print(f"NOT_PINNED {path.relative_to(ROOT)}:{line_number}: {reference}")
    for error in reviewed_errors:
        print(error)
    failed = bool(unpinned or reviewed_errors)
    print("status:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
