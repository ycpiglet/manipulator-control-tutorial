from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "protected_integration.py"
POLICY_PATH = ROOT / ".agents" / "integration" / "protected-main-v1.json"
INTEGRATION_README = ROOT / ".agents" / "integration" / "README.md"
SPEC = importlib.util.spec_from_file_location("protected_integration", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
integration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integration
SPEC.loader.exec_module(integration)

BASE = "a" * 40
HEAD = "b" * 40
MERGE = "c" * 40
HEAD_TREE = "d" * 40
SYNTHETIC = "e" * 40
BOOT_BASE = "03499fb3ad974aec3ea28bb8bcce2595b68a0661"
BOOT_HEAD = "6cd191f0b87bb582bfde4764234a570a7f601da4"
BOOT_MERGE = "9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88"
BOOT_TREE = "e5625718c0bcd1030bba9ea938a438d927d4033e"
OWNER_ID = 68498184
BOOT_COMPLETION_BODY = """<!-- protected-integration:manual-v1:pr-74:9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88 -->
Bounded protected-main integration completion record for LIC-01B.

- Exact pre-merge base: `03499fb3ad974aec3ea28bb8bcce2595b68a0661`
- Exact source head: `6cd191f0b87bb582bfde4764234a570a7f601da4`
- Source tree: `e5625718c0bcd1030bba9ea938a438d927d4033e`
- Protected merge: `9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88`
- Merge parents: `[03499fb3ad974aec3ea28bb8bcce2595b68a0661, 6cd191f0b87bb582bfde4764234a570a7f601da4]`
- Merge tree: `e5625718c0bcd1030bba9ea938a438d927d4033e` — source/merge tree equivalence PASS
- Exact-head checks: CI `30203394749`, Desktop `30203394746` — required checks **6/6 PASS**
- Post-merge checks: CI `30204142834`, Desktop `30204142848` — required checks **6/6 PASS**
- Independent read-only agent audits: semantic/provenance/readiness PASS
- Review topology: one direct collaborator, required approvals `0`, unresolved threads `0`; formal independent human approval remains absent
- Actual learner outputs, cleanup plans, package bodies, and artifact contents accessed: **no**

Accepted result: LIC-01B is accepted only for its bounded supervised/safe-main development-baseline scope. LIC aggregate/G3, legal approval, public beta/promotion, signed/notarized or package distribution, signing credentials, tag/release/DOI/preprint publication, external contact/recruitment, ruleset changes/bypass, repository moves, actual-output inspection, and cleanup dry-run/apply/quarantine/restore remain unauthorized."""


def policy() -> Any:
    return integration.Policy.load(POLICY_PATH)


def ruleset_document(current_policy: Any) -> dict[str, Any]:
    return {
        "id": current_policy.ruleset_id,
        "name": current_policy.ruleset_name,
        "enforcement": "active",
        "target": "branch",
        "conditions": {
            "ref_name": {
                "include": ["refs/heads/main"],
                "exclude": [],
            }
        },
        "bypass_actors": [
            {
                "actor_id": 5,
                "actor_type": "RepositoryRole",
                "bypass_mode": "pull_request",
            }
        ],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": True,
                    "required_reviewers": [],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "do_not_enforce_on_create": True,
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {
                            "context": context,
                            "integration_id": current_policy.actions_app_id,
                        }
                        for context in current_policy.required_checks
                    ],
                },
            },
        ],
    }


def check_document(current_policy: Any, sha: str) -> dict[str, Any]:
    runs = [
        {
            "id": index + 100,
            "name": context,
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "app": {"id": current_policy.actions_app_id},
        }
        for index, context in enumerate(current_policy.required_checks)
    ]
    return {"total_count": len(runs), "check_runs": runs}


def pull_document(
    item: Any,
    *,
    base: str = BASE,
    head: str = HEAD,
    merged: bool = False,
    draft: bool = True,
    merge_sha: str = MERGE,
) -> dict[str, Any]:
    return {
        "number": item.number,
        "node_id": f"PR_{item.number}",
        "state": "closed" if merged else "open",
        "draft": False if merged else draft,
        "mergeable": not merged,
        "auto_merge": None,
        "merged_at": "2026-07-26T00:00:00Z" if merged else None,
        "merged_by": (
            {"id": OWNER_ID, "login": "ycpiglet", "type": "User"}
            if merged
            else None
        ),
        "merge_commit_sha": merge_sha if merged else SYNTHETIC,
        "base": {
            "ref": "main",
            "sha": base,
            "repo": {"full_name": "ycpiglet/manipulator-control-tutorial"},
        },
        "head": {
            "ref": item.branch,
            "sha": head,
            "repo": {"full_name": "ycpiglet/manipulator-control-tutorial"},
        },
    }


class FakeGit:
    def __init__(self, current_policy: Any, tmp_path: Path, number: int = 75) -> None:
        self.common_dir = tmp_path / "common.git"
        self.common_dir.mkdir(parents=True)
        self.item = current_policy.item(number)
        self.origin_main = BASE
        self.origin_head = HEAD
        self.synthetic = SYNTHETIC
        self.changed = tuple(self.item.allowed_paths[:2])
        self.trees = {
            HEAD: HEAD_TREE,
            SYNTHETIC: HEAD_TREE,
            MERGE: HEAD_TREE,
            BOOT_HEAD: BOOT_TREE,
            BOOT_MERGE: BOOT_TREE,
        }
        self.parent_map = {
            SYNTHETIC: (BASE, HEAD),
            MERGE: (BASE, HEAD),
            BOOT_MERGE: (BOOT_BASE, BOOT_HEAD),
        }
        self.bindings = {
            (BASE, HEAD): self.item,
            (BOOT_BASE, BOOT_HEAD): current_policy.item(74),
        }
        self.exact_values = {
            pair: item.reviewed_exact_diff_sha256
            for pair, item in self.bindings.items()
        }
        self.semantic_values = {
            pair: item.semantic_patch_sha256
            for pair, item in self.bindings.items()
        }
        self.integration_heads = {74: BOOT_HEAD, number: HEAD}
        self.environment_checks = 0
        self.fetches = 0
        self.authority_ok = True
        self.first_parent_pairs = {
            (BASE, HEAD),
            (BOOT_BASE, BOOT_HEAD),
            (BOOT_MERGE, BASE),
            (BOOT_MERGE, MERGE),
            (MERGE, MERGE),
        }

    def assert_environment(self, repository: str) -> None:
        assert repository == "ycpiglet/manipulator-control-tutorial"
        self.environment_checks += 1

    def fetch_candidate(self, item: Any) -> None:
        assert item == self.item
        self.fetches += 1

    def fetch_integration(self, item: Any) -> None:
        assert item.number in self.integration_heads

    def fetch_base(self) -> None:
        pass

    def authority_matches(self, base: str) -> bool:
        return self.authority_ok and base == BASE

    def base_sha(self) -> str:
        return self.origin_main

    def branch_sha(self, item: Any) -> str:
        assert item == self.item
        return self.origin_head

    def integration_head_sha(self, item: Any) -> str:
        return self.integration_heads[item.number]

    def merge_sha(self, item: Any) -> str:
        assert item == self.item
        return self.synthetic

    def is_ancestor(self, base: str, head: str) -> bool:
        return (base, head) in {
            (BASE, HEAD),
            (BOOT_MERGE, BASE),
            (MERGE, MERGE),
        }

    def is_first_parent_ancestor(self, base: str, head: str) -> bool:
        return (base, head) in self.first_parent_pairs

    def changed_paths(self, base: str, head: str) -> Sequence[str]:
        return tuple(self.bindings[(base, head)].allowed_paths[:2])

    def changed_file_modes(
        self, base: str, head: str
    ) -> Sequence[tuple[str, str, str]]:
        return tuple(
            (path, "100644", "100644")
            for path in self.changed_paths(base, head)
        )

    def stable_patch_id(self, base: str, head: str) -> str:
        return self.bindings[(base, head)].stable_patch_id

    def semantic_patch_digest(self, base: str, head: str) -> str:
        return self.semantic_values[(base, head)]

    def changed_paths_digest(self, base: str, head: str) -> str:
        return self.bindings[(base, head)].changed_paths_sha256

    def exact_diff_digest(self, base: str, head: str) -> str:
        return self.exact_values[(base, head)]

    def name_status_digest(self, base: str, head: str) -> str:
        return self.bindings[(base, head)].name_status_sha256

    def tree(self, commit: str) -> str:
        return self.trees[commit]

    def parents(self, commit: str) -> Sequence[str]:
        return self.parent_map[commit]


class FakeGitHub:
    def __init__(self, current_policy: Any, git: FakeGit, number: int = 75) -> None:
        self.policy = current_policy
        self.git = git
        target_index = next(
            index
            for index, item in enumerate(current_policy.queue)
            if item.number == number
        )
        self.pulls = {}
        for index, item in enumerate(current_policy.queue):
            if item.number == 74 and index < target_index:
                self.pulls[item.number] = pull_document(
                    item,
                    base=BOOT_BASE,
                    head=BOOT_HEAD,
                    merged=True,
                    merge_sha=BOOT_MERGE,
                )
            else:
                self.pulls[item.number] = pull_document(
                    item,
                    base=BASE,
                    head=HEAD if index == target_index else item.reviewed_subject_head,
                    merged=index < target_index,
                    draft=index == target_index,
                )
        self.ruleset_value = ruleset_document(current_policy)
        self.checks = {
            HEAD: check_document(current_policy, HEAD),
            MERGE: check_document(current_policy, MERGE),
            BOOT_HEAD: check_document(current_policy, BOOT_HEAD),
            BOOT_MERGE: check_document(current_policy, BOOT_MERGE),
        }
        self.threads: dict[int, list[dict[str, Any]]] = {
            item.number: [] for item in current_policy.queue
        }
        self.review_values: dict[int, list[dict[str, Any]]] = {
            item.number: [] for item in current_policy.queue
        }
        self.ready_calls: list[str] = []
        self.merge_calls: list[tuple[int, str]] = []
        self.comment_markers: set[str] = set()
        target_item = current_policy.item(number)
        attestation = integration.owner_attestation_body(
            current_policy,
            target_item,
            BASE,
            HEAD,
            HEAD_TREE,
            target_item.reviewed_exact_diff_sha256,
        )
        self.comment_values: dict[int, list[dict[str, Any]]] = {
            item.number: [] for item in current_policy.queue
        }
        self.comment_values[number].append(
            {
                "id": 1,
                "body": attestation,
                "user": {"id": OWNER_ID, "login": "ycpiglet", "type": "User"},
                "author_association": "OWNER",
            }
        )
        self.comment_values[74].append(
            {
                "id": 5083778171,
                "body": BOOT_COMPLETION_BODY,
                "user": {"id": OWNER_ID, "login": "ycpiglet", "type": "User"},
                "author_association": "OWNER",
                "created_at": "2026-07-26T13:54:54Z",
                "updated_at": "2026-07-26T13:54:54Z",
            }
        )
        self.collaborator_values = [
            {
                "id": OWNER_ID,
                "login": "ycpiglet",
                "type": "User",
                "permissions": {"admin": True},
            }
        ]
        self.authenticated_user_value = {
            "id": OWNER_ID,
            "login": "ycpiglet",
            "type": "User",
        }

    def refresh_attestation(
        self,
        number: int,
        *,
        base: str = BASE,
        head: str = HEAD,
        head_tree: str = HEAD_TREE,
    ) -> None:
        item = self.policy.item(number)
        body = integration.owner_attestation_body(
            self.policy,
            item,
            base,
            head,
            head_tree,
            self.git.exact_diff_digest(base, head),
        )
        self.comment_values[number] = [
            comment
            for comment in self.comment_values[number]
            if integration.owner_attestation_marker(number, head)
            not in str(comment.get("body"))
        ]
        self.comment_values[number].append(
            {
                "id": 1,
                "body": body,
                "user": {"id": OWNER_ID, "login": "ycpiglet", "type": "User"},
                "author_association": "OWNER",
            }
        )

    def pull(self, number: int) -> Mapping[str, Any]:
        return self.pulls[number]

    def ruleset(self, ruleset_id: int) -> Mapping[str, Any]:
        assert ruleset_id == self.policy.ruleset_id
        return self.ruleset_value

    def check_runs(self, sha: str) -> Mapping[str, Any]:
        return self.checks[sha]

    def review_threads(self, number: int) -> Sequence[Mapping[str, Any]]:
        return self.threads[number]

    def reviews(self, number: int) -> Sequence[Mapping[str, Any]]:
        return self.review_values[number]

    def comments(self, number: int) -> Sequence[Mapping[str, Any]]:
        return self.comment_values[number]

    def direct_collaborators(self) -> Sequence[Mapping[str, Any]]:
        return self.collaborator_values

    def authenticated_user(self) -> Mapping[str, Any]:
        return self.authenticated_user_value

    def mark_ready(self, pull_node_id: str) -> None:
        self.ready_calls.append(pull_node_id)
        number = int(pull_node_id.removeprefix("PR_"))
        self.pulls[number]["draft"] = False

    def merge(self, number: int, expected_head: str) -> Mapping[str, Any]:
        self.merge_calls.append((number, expected_head))
        target = self.pulls[number]
        target["state"] = "closed"
        target["merged_at"] = "2026-07-26T01:00:00Z"
        target["merge_commit_sha"] = MERGE
        target["merged_by"] = {
            "id": OWNER_ID,
            "login": "ycpiglet",
            "type": "User",
        }
        self.git.origin_main = MERGE
        return {"merged": True, "sha": MERGE, "message": "merged"}

    def ensure_comment(self, number: int, marker: str, body: str) -> bool:
        assert marker in body
        if marker in self.comment_markers:
            return False
        self.comment_markers.add(marker)
        self.comment_values[number].append(
            {
                "id": len(self.comment_markers) + 10,
                "body": body,
                "user": {"id": OWNER_ID, "login": "ycpiglet", "type": "User"},
                "author_association": "OWNER",
            }
        )
        return True


def harness(
    tmp_path: Path, number: int = 75
) -> tuple[Any, FakeGit, FakeGitHub, Any]:
    current_policy = policy()
    git = FakeGit(current_policy, tmp_path, number)
    github = FakeGitHub(current_policy, git, number)
    state = integration.StateStore(git.common_dir)
    subject = integration.IntegrationHarness(
        current_policy,
        git,
        github,
        state,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
    )
    return subject, git, github, state


def mark_fake_merged(git: FakeGit, github: FakeGitHub, number: int = 75) -> None:
    pull = github.pulls[number]
    pull["state"] = "closed"
    pull["draft"] = False
    pull["merged_at"] = "2026-07-26T01:00:00Z"
    pull["merge_commit_sha"] = MERGE
    pull["merged_by"] = {
        "id": OWNER_ID,
        "login": "ycpiglet",
        "type": "User",
    }
    git.origin_main = MERGE


def save_complete_state(state: Any, current_policy: Any) -> None:
    state.save(
        75,
        {
            "policy_id": current_policy.policy_id,
            "repository": current_policy.repository,
            "number": 75,
            "work_id": "OPS-01A",
            "expected_base": BASE,
            "expected_head": HEAD,
            "head_tree": HEAD_TREE,
            "stage": "complete",
            "merge_sha": MERGE,
            "post_merge_checks": {
                context: 900 + index
                for index, context in enumerate(current_policy.required_checks)
            },
            "completed_at": "2026-07-26T01:01:00Z",
        },
    )


class RecordingRunner:
    def __init__(self, responses: Sequence[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[str], str | None]] = []

    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> Any:
        del cwd
        self.calls.append((list(arguments), input_text))
        if not self.responses:
            raise AssertionError("unexpected runner call")
        return integration.CommandResult(stdout=self.responses.pop(0))

    def run_bytes(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
    ) -> Any:
        del arguments, cwd, input_bytes
        raise AssertionError("unexpected binary runner call")


def test_committed_policy_is_exact_and_self_excluding() -> None:
    current_policy = policy()

    assert [item.number for item in current_policy.queue] == [74, 75, 72, 73, 70, 76]
    assert current_policy.repository == "ycpiglet/manipulator-control-tutorial"
    assert current_policy.base_branch == "main"
    assert current_policy.ruleset_id == 19209773
    assert current_policy.actions_app_id == 15368
    assert current_policy.required_checks == integration.EXPECTED_REQUIRED_CHECKS
    assert current_policy.delegation["accepted_date"] == "2026-07-26"
    assert current_policy.delegation["self_amendment_authority"] is False
    assert current_policy.review_topology["owner_id"] == OWNER_ID
    assert all(item.semantic_patch_sha256 for item in current_policy.queue)
    assert all(item.reviewed_exact_diff_sha256 for item in current_policy.queue)
    assert current_policy.item(74).reviewed_subject_base == BOOT_BASE
    assert {
        item.reviewed_subject_base for item in current_policy.queue[1:]
    } == {"96702b09d7e2b0e3b381b86c5e6e51f95682d346"}
    assert (
        current_policy.item(74).accepted_integration["owner_completion_comment"]["id"]
        == 5083778171
    )
    assert integration.SELF_DENIED_PATHS.issubset(current_policy.denied_paths)


def test_policy_only_amendment_deactivates_pinned_harness(tmp_path: Path) -> None:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["queue"][1]["allowed_paths"].append("src/**")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(integration.HarnessError, match="fingerprint"):
        integration.Policy.load(path)


def test_documented_attestation_template_equals_exact_harness_body() -> None:
    current_policy = policy()
    item = current_policy.item(75)
    readme = INTEGRATION_README.read_text(encoding="utf-8")
    template = readme.split("must be:\n\n```text\n", 1)[1].split("\n```", 1)[0]
    replacements = {
        "<PR>": str(item.number),
        "<WORK_ID>": item.work_id,
        "<BASE>": BASE,
        "<HEAD>": HEAD,
        "<HEAD_TREE>": HEAD_TREE,
        "<REVIEWED_SUBJECT_BASE>": item.reviewed_subject_base,
        "<REVIEWED_SUBJECT_HEAD>": item.reviewed_subject_head,
        "<STABLE_PATCH_ID>": item.stable_patch_id,
        "<SEMANTIC_PATCH_SHA256>": item.semantic_patch_sha256,
        "<CURRENT_EXACT_DIFF_SHA256>": item.reviewed_exact_diff_sha256,
        "<CHANGED_PATHS_SHA256>": item.changed_paths_sha256,
        "<NAME_STATUS_SHA256>": item.name_status_sha256,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    assert template == integration.owner_attestation_body(
        current_policy,
        item,
        BASE,
        HEAD,
        HEAD_TREE,
        item.reviewed_exact_diff_sha256,
    )


def test_policy_rejects_queue_or_delegation_drift(tmp_path: Path) -> None:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["queue"][0]["branch"] = "agent/unreviewed"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(integration.HarnessError, match="queue identity or order"):
        integration.Policy.load(path, enforce_canonical_fingerprint=False)

    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["standing_owner_delegation"]["self_amendment_authority"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(integration.HarnessError, match="cannot authorize"):
        integration.Policy.load(path, enforce_canonical_fingerprint=False)

    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["standing_owner_delegation"]["activation"] = "immediately"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(integration.HarnessError, match="activation drift"):
        integration.Policy.load(path, enforce_canonical_fingerprint=False)


def test_exact_sha_rejects_stale_labels_and_abbreviations() -> None:
    assert integration.exact_sha(BASE) == BASE
    for invalid in ("main", "a" * 39, "A" * 40, "a" * 41, HEAD + "^"):
        with pytest.raises(Exception):
            integration.exact_sha(invalid)


def test_cli_rejects_arbitrary_policy_and_nonfinite_timing() -> None:
    parser = integration.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate-policy", "--policy", "/tmp/forged.json"])
    for invalid in ("nan", "inf", "-inf"):
        with pytest.raises(Exception):
            integration._positive_float(invalid)
        with pytest.raises(Exception):
            integration._nonnegative_float(invalid)
    assert integration._settle_seconds("60") == 60
    assert integration._poll_seconds("60") == 60
    assert integration._timeout_seconds("7200") == 7200
    for parser, invalid in (
        (integration._settle_seconds, "60.1"),
        (integration._poll_seconds, "61"),
        (integration._timeout_seconds, "7201"),
        (integration._timeout_seconds, "1e308"),
    ):
        with pytest.raises(Exception):
            parser(invalid)


def test_canonical_context_rejects_copied_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "protected_integration.py"
    copied.write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    runner = RecordingRunner([str(ROOT) + "\n"])
    monkeypatch.setattr(integration, "__file__", str(copied))
    with pytest.raises(integration.HarnessError, match="not the canonical"):
        integration.canonical_repository_context(runner)


def test_semantic_patch_hash_normalizes_only_rebase_locations() -> None:
    original = (
        b"diff --git a/example.py b/example.py\n"
        b"index 1111111..2222222 100644\n"
        b"--- a/example.py\n"
        b"+++ b/example.py\n"
        b"@@ -2,2 +2,2 @@ def run():\n"
        b"-    old = True\n"
        b"+    new = True\n"
    )
    rebased = (
        b"diff --git a/example.py b/example.py\n"
        b"index aaaaaaa..bbbbbbb 100644\n"
        b"--- a/example.py\n"
        b"+++ b/example.py\n"
        b"@@ -202,2 +407,2 @@ def moved():\n"
        b"-    old = True\n"
        b"+    new = True\n"
    )
    assert integration.semantic_patch_sha256(original) == (
        integration.semantic_patch_sha256(rebased)
    )

    indentation_drift = rebased.replace(
        b"+    new = True\n", b"+        new = True\n"
    )
    content_drift = rebased.replace(b"+    new = True\n", b"+    new = False\n")
    assert integration.semantic_patch_sha256(original) != (
        integration.semantic_patch_sha256(indentation_drift)
    )
    assert integration.semantic_patch_sha256(original) != (
        integration.semantic_patch_sha256(content_drift)
    )

    second = (
        b"diff --git a/z.py b/z.py\n"
        b"index 3333333..4444444 100644\n"
        b"--- a/z.py\n"
        b"+++ b/z.py\n"
        b"@@ -1 +9 @@\n"
        b"-before\n"
        b"+after\n"
    )
    assert integration.semantic_patch_sha256(original + second) == (
        integration.semantic_patch_sha256(second + original)
    )
    with pytest.raises(integration.HarnessError, match="duplicate"):
        integration.semantic_patch_sha256(original + original)
    with pytest.raises(integration.HarnessError, match="first file header"):
        integration.semantic_patch_sha256(b"unexpected\n" + original)
    binary = (
        b"diff --git a/blob.bin b/blob.bin\n"
        b"index " + b"a" * 40 + b".." + b"b" * 40 + b" 100644\n"
        b"GIT binary patch\n"
        b"literal 1\n"
        b"Ic$@<O000310RR91\n"
    )
    with pytest.raises(integration.HarnessError, match="binary semantic"):
        integration.semantic_patch_sha256(binary)


def test_reviewed_exact_digest_canonicalizes_full_index_only() -> None:
    raw = (
        b"diff --git a/example.py b/example.py\n"
        b"index " + b"a" * 40 + b".." + b"b" * 40 + b" 100644\n"
        b"--- a/example.py\n"
        b"+++ b/example.py\n"
        b"@@ -1 +1 @@\n"
        b"-old\n"
        b"+new\n"
    )
    legacy = raw.replace(b"a" * 40, b"a" * 7).replace(b"b" * 40, b"b" * 7)
    assert integration.reviewed_exact_diff_sha256(raw) == (
        integration.hashlib.sha256(legacy).hexdigest()
    )
    malformed = raw.replace(b"a" * 40, b"a" * 39)
    with pytest.raises(integration.HarnessError, match="malformed index"):
        integration.reviewed_exact_diff_sha256(malformed)


def test_semantic_git_command_pins_hostile_config_sensitive_flags(
    tmp_path: Path,
) -> None:
    raw = (
        b"diff --git a/example.py b/example.py\n"
        b"index 1111111..2222222 100644\n"
        b"--- a/example.py\n"
        b"+++ b/example.py\n"
        b"@@ -1 +2 @@\n"
        b"-old\n"
        b"+new\n"
    )

    class ByteRunner:
        def __init__(self) -> None:
            self.arguments: list[str] = []

        def run_bytes(
            self,
            arguments: Sequence[str],
            *,
            cwd: Path | None = None,
            input_bytes: bytes | None = None,
        ) -> Any:
            assert cwd == tmp_path
            assert input_bytes is None
            self.arguments = list(arguments)
            return integration.CommandBytesResult(stdout=raw)

    runner = ByteRunner()
    repository = object.__new__(integration.GitRepository)
    repository.root = tmp_path
    repository.runner = runner
    assert repository.semantic_patch_digest(BASE, HEAD) == (
        integration.semantic_patch_sha256(raw)
    )
    assert runner.arguments == [
        "git",
        "--no-replace-objects",
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
        "--unified=0",
        "--output-indicator-new=+",
        "--output-indicator-old=-",
        "--output-indicator-context= ",
        f"{BASE}..{HEAD}",
        "--",
    ]


def test_real_git_diff_opts_cannot_change_semantic_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()

    def git(*arguments: str, env: Mapping[str, str] | None = None) -> bytes:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository_path,
            env=env,
            check=True,
            capture_output=True,
        ).stdout

    git("init", "-q")
    source = repository_path / "example.py"
    source.write_text(
        "".join(f"value_{index} = {index}\n" for index in range(200)),
        encoding="utf-8",
    )
    git("add", "example.py")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "base",
    )
    base = git("rev-parse", "HEAD").decode().strip()
    lines = source.read_text(encoding="utf-8").splitlines()
    lines[100] = "value_100 = 999"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    git("add", "example.py")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "head",
    )
    head = git("rev-parse", "HEAD").decode().strip()
    repository = integration.GitRepository(
        repository_path, integration.SubprocessRunner()
    )
    clean = repository.semantic_patch_digest(base, head)

    hostile_environment = os.environ.copy()
    hostile_environment["GIT_DIFF_OPTS"] = "--unified=99"
    unsafe_raw = git(
        *repository._canonical_patch_arguments(base, head, unified=0),
        env=hostile_environment,
    )
    assert integration.semantic_patch_sha256(unsafe_raw) != clean

    monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=99")
    assert repository.semantic_patch_digest(base, head) == clean


@pytest.mark.skipif(os.name != "posix", reason="POSIX clean-filter regression")
def test_authority_comparison_bypasses_hostile_clean_filter(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository_path,
            text=True,
            check=True,
            capture_output=True,
        ).stdout.strip()

    git("init", "-q")
    (repository_path / ".agents" / "integration").mkdir(parents=True)
    (repository_path / "scripts").mkdir()
    policy_file = repository_path / integration.POLICY_RELATIVE
    script_file = repository_path / integration.SCRIPT_RELATIVE
    policy_file.write_text("policy-original\n", encoding="utf-8")
    script_file.write_text("script-original\n", encoding="utf-8")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "base",
    )
    base = git("rev-parse", "HEAD")
    info = repository_path / ".git" / "info"
    (info / "attributes").write_text(
        "scripts/protected_integration.py filter=restore\n", encoding="utf-8"
    )
    git("config", "filter.restore.clean", "sed s/MODIFIED/original/g")
    git("config", "filter.restore.required", "true")
    script_file.write_text("script-MODIFIED\n", encoding="utf-8")
    committed = git(
        "rev-parse", f"{base}:{integration.SCRIPT_RELATIVE.as_posix()}"
    )
    filtered = git(
        "hash-object",
        f"--path={integration.SCRIPT_RELATIVE.as_posix()}",
        integration.SCRIPT_RELATIVE.as_posix(),
    )
    assert filtered == committed

    repository = integration.GitRepository(
        repository_path, integration.SubprocessRunner()
    )
    assert repository.authority_matches(base) is False


def test_git_replace_objects_are_disabled_and_rejected(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository_path,
            text=True,
            check=True,
            capture_output=True,
        ).stdout.strip()

    git("init", "-q")
    source = repository_path / "value.txt"
    source.write_text("first\n", encoding="utf-8")
    git("add", "value.txt")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "first",
    )
    first = git("rev-parse", "HEAD")
    first_tree = git("rev-parse", f"{first}^{{tree}}")
    source.write_text("second\n", encoding="utf-8")
    git("add", "value.txt")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "second",
    )
    second = git("rev-parse", "HEAD")
    second_tree = git("rev-parse", f"{second}^{{tree}}")
    git("replace", second, first)
    assert git("rev-parse", f"{second}^{{tree}}") == first_tree

    repository = integration.GitRepository(
        repository_path, integration.SubprocessRunner()
    )
    assert repository.tree(second) == second_tree
    with pytest.raises(integration.HarnessError, match="replace refs"):
        repository.assert_environment("ycpiglet/manipulator-control-tutorial")


def test_path_envelope_allows_only_item_paths_and_denies_harness() -> None:
    current_policy = policy()
    item = current_policy.item(74)
    integration.validate_changed_paths(
        [
            ".agents/validation/check_license_review.py",
            "third_party/licenses/corpus/" + "a" * 64 + ".txt",
        ],
        item,
        current_policy.denied_paths,
    )
    with pytest.raises(integration.HarnessError, match="outside"):
        integration.validate_changed_paths(
            ["src/mclab/cli.py"], item, current_policy.denied_paths
        )
    with pytest.raises(integration.HarnessError, match="explicitly denied"):
        integration.validate_changed_paths(
            ["scripts/protected_integration.py"], item, current_policy.denied_paths
        )
    with pytest.raises(integration.HarnessError, match="explicitly denied"):
        integration.validate_changed_paths(
            ["outputs/private/manifest.json"], item, current_policy.denied_paths
        )

    assert integration.path_matches(
        "third_party/licenses/corpus/license.txt",
        "third_party/licenses/corpus/*.txt",
    )
    assert not integration.path_matches(
        "third_party/licenses/corpus/nested/license.txt",
        "third_party/licenses/corpus/*.txt",
    )
    assert integration.path_matches(
        "third_party/licenses/corpus/nested/license.txt",
        "third_party/licenses/**",
    )


def test_ruleset_and_check_validation_fail_closed_on_drift() -> None:
    current_policy = policy()
    live = ruleset_document(current_policy)
    integration.validate_ruleset(live, current_policy)

    drifted = json.loads(json.dumps(live))
    drifted["rules"][3]["parameters"]["required_status_checks"][0][
        "integration_id"
    ] = 999
    with pytest.raises(integration.HarnessError, match="contexts/app/order"):
        integration.validate_ruleset(drifted, current_policy)

    checks = check_document(current_policy, HEAD)
    evidence = integration.validate_check_runs(checks, HEAD, current_policy)
    assert list(evidence) == list(current_policy.required_checks)

    checks["check_runs"][0]["status"] = "in_progress"
    checks["check_runs"][0]["conclusion"] = None
    with pytest.raises(integration.PendingChecks):
        integration.validate_check_runs(checks, HEAD, current_policy)
    checks["check_runs"][0]["status"] = "completed"
    checks["check_runs"][0]["conclusion"] = "failure"
    with pytest.raises(integration.HarnessError, match="failure"):
        integration.validate_check_runs(checks, HEAD, current_policy)


@pytest.mark.parametrize("reported_total", [5, 7])
def test_check_runs_rejects_page_count_mismatch(reported_total: int) -> None:
    current_policy = policy()
    checks = check_document(current_policy, HEAD)
    checks["total_count"] = reported_total
    with pytest.raises(integration.HarnessError, match="total_count"):
        integration.validate_check_runs(checks, HEAD, current_policy)


@pytest.mark.parametrize("invalid_id", [-1, 0, True])
def test_check_runs_rejects_nonpositive_or_bool_ids(invalid_id: object) -> None:
    current_policy = policy()
    checks = check_document(current_policy, HEAD)
    checks["check_runs"][0]["id"] = invalid_id
    with pytest.raises(integration.HarnessError, match="ID|integer"):
        integration.validate_check_runs(checks, HEAD, current_policy)


def test_check_runs_rejects_duplicate_ids_contexts_and_oversized_page() -> None:
    current_policy = policy()
    checks = check_document(current_policy, HEAD)
    checks["check_runs"].append(
        {
            "id": checks["check_runs"][0]["id"],
            "name": "unrelated",
            "head_sha": HEAD,
            "status": "completed",
            "conclusion": "success",
            "app": {"id": current_policy.actions_app_id},
        }
    )
    checks["total_count"] += 1
    with pytest.raises(integration.HarnessError, match="duplicate check-run ID"):
        integration.validate_check_runs(checks, HEAD, current_policy)

    checks = check_document(current_policy, HEAD)
    duplicate = dict(checks["check_runs"][0])
    duplicate["id"] = 999
    checks["check_runs"].append(duplicate)
    checks["total_count"] += 1
    with pytest.raises(integration.HarnessError, match="ambiguous duplicate"):
        integration.validate_check_runs(checks, HEAD, current_policy)

    checks = {
        "total_count": 101,
        "check_runs": [
            {
                "id": index + 1,
                "name": "unrelated",
            }
            for index in range(101)
        ],
    }
    with pytest.raises(integration.HarnessError, match="complete-page bound"):
        integration.validate_check_runs(checks, HEAD, current_policy)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("head_sha", "f" * 40, "wrong SHA"),
        ("app", {"id": 999}, "wrong app"),
        ("app", {"id": True}, "wrong app"),
    ],
)
def test_check_runs_rejects_wrong_sha_or_app(
    field: str, value: object, message: str
) -> None:
    current_policy = policy()
    checks = check_document(current_policy, HEAD)
    checks["check_runs"][0][field] = value
    with pytest.raises(integration.HarnessError, match=message):
        integration.validate_check_runs(checks, HEAD, current_policy)


def test_preflight_binds_sha_paths_reviews_synthetic_merge_and_prefix(
    tmp_path: Path,
) -> None:
    subject, git, github, _state = harness(tmp_path, number=75)

    evidence = subject.preflight(75, BASE, HEAD)

    assert evidence.number == 75
    assert evidence.base_sha == BASE
    assert evidence.head_sha == HEAD
    assert evidence.head_tree == HEAD_TREE
    assert evidence.synthetic_merge_sha == SYNTHETIC
    assert git.environment_checks == 1
    assert github.pulls[74]["merged_at"]


def test_rebased_candidate_allows_current_exact_diff_change_when_attested(
    tmp_path: Path,
) -> None:
    subject, git, github, _state = harness(tmp_path)
    git.exact_values[(BASE, HEAD)] = "f" * 64
    github.refresh_attestation(75)

    evidence = subject.preflight(75, BASE, HEAD)

    assert evidence.exact_diff_sha256 == "f" * 64
    assert evidence.semantic_patch_sha256 == policy().item(75).semantic_patch_sha256


def test_original_reviewed_head_still_requires_exact_diff_provenance(
    tmp_path: Path,
) -> None:
    subject, git, _github, _state = harness(tmp_path)
    item = policy().item(75)
    pair = (BASE, item.reviewed_subject_head)
    git.bindings[pair] = item
    git.semantic_values[pair] = item.semantic_patch_sha256
    git.exact_values[pair] = "f" * 64

    with pytest.raises(integration.HarnessError, match="provenance drift"):
        subject._validate_content_binding(item, *pair)


@pytest.mark.parametrize(
    ("binding_name", "message"),
    [
        ("semantic", "semantic patch drift"),
        ("patch", "stable patch ID drift"),
        ("paths", "changed-path digest drift"),
        ("name_status", "name-status digest drift"),
    ],
)
def test_candidate_rejects_each_content_binding_drift(
    tmp_path: Path, binding_name: str, message: str
) -> None:
    subject, git, _github, _state = harness(tmp_path)
    if binding_name == "semantic":
        git.semantic_values[(BASE, HEAD)] = "f" * 64
    elif binding_name == "patch":
        original = git.bindings[(BASE, HEAD)]
        git.bindings[(BASE, HEAD)] = integration.dataclasses.replace(
            original, stable_patch_id="f" * 40
        )
    elif binding_name == "paths":
        original = git.bindings[(BASE, HEAD)]
        git.bindings[(BASE, HEAD)] = integration.dataclasses.replace(
            original, changed_paths_sha256="f" * 64
        )
    else:
        original = git.bindings[(BASE, HEAD)]
        git.bindings[(BASE, HEAD)] = integration.dataclasses.replace(
            original, name_status_sha256="f" * 64
        )
    with pytest.raises(integration.HarnessError, match=message):
        subject.preflight(75, BASE, HEAD)


def test_candidate_rejects_symlink_or_submodule_modes(tmp_path: Path) -> None:
    subject, git, _github, _state = harness(tmp_path)
    path = git.changed_paths(BASE, HEAD)[0]
    original_modes = git.changed_file_modes
    git.changed_file_modes = lambda base, head: (
        [(path, "100644", "120000")]
        if (base, head) == (BASE, HEAD)
        else original_modes(base, head)
    )
    with pytest.raises(integration.HarnessError, match="symlink, submodule"):
        subject.preflight(75, BASE, HEAD)


def test_preflight_rejects_unaccepted_harness_authority(tmp_path: Path) -> None:
    subject, git, _github, _state = harness(tmp_path)
    git.authority_ok = False
    with pytest.raises(integration.HarnessError, match="not the version accepted"):
        subject.preflight(75, BASE, HEAD)


def test_preflight_rejects_unresolved_or_changes_requested_review(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    github.threads[75] = [
        {"id": "thread-1", "isResolved": False, "isOutdated": False}
    ]
    with pytest.raises(integration.HarnessError, match="unresolved"):
        subject.preflight(75, BASE, HEAD)

    github.threads[75] = []
    github.review_values[75] = [
        {
            "id": 10,
            "state": "CHANGES_REQUESTED",
            "user": {"id": 7, "login": "reviewer"},
        }
    ]
    with pytest.raises(integration.HarnessError, match="changes-requested"):
        subject.preflight(75, BASE, HEAD)
    github.review_values[75].append(
        {
            "id": 11,
            "state": "COMMENTED",
            "user": {"id": 7, "login": "reviewer"},
        }
    )
    with pytest.raises(integration.HarnessError, match="changes-requested"):
        subject.preflight(75, BASE, HEAD)
    github.review_values[75].append(
        {
            "id": 12,
            "state": "DISMISSED",
            "user": {"id": 7, "login": "reviewer"},
        }
    )
    subject.preflight(75, BASE, HEAD)

    github.review_values[75] = [
        {
            "id": 13,
            "state": "APPROVED",
            "user": {"id": 8, "login": "human-reviewer"},
        }
    ]
    with pytest.raises(integration.HarnessError, match="approval topology drift"):
        subject.preflight(75, BASE, HEAD)


@pytest.mark.parametrize("resolved", [None, 0, 1, "", "true", []])
def test_preflight_rejects_non_boolean_review_thread_state(
    tmp_path: Path,
    resolved: object,
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    github.threads[75] = [
        {"id": "thread-1", "isResolved": resolved, "isOutdated": False}
    ]
    with pytest.raises(integration.HarnessError, match="exact boolean"):
        subject.preflight(75, BASE, HEAD)


def test_git_repository_rejects_non_posix_transaction_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = object.__new__(integration.GitRepository)
    monkeypatch.setattr(integration.os, "name", "nt")
    with pytest.raises(integration.HarnessError, match="only on a POSIX host"):
        repository.assert_environment("ycpiglet/manipulator-control-tutorial")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 999),
        ("login", "impostor"),
        ("type", "Bot"),
        ("author_association", "COLLABORATOR"),
        ("body", "forged"),
    ],
)
def test_owner_attestation_rejects_identity_or_body_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    comment = github.comment_values[75][0]
    if field in {"id", "login", "type"}:
        comment["user"][field] = value
    else:
        comment[field] = value
    with pytest.raises(integration.HarnessError, match="attestation"):
        subject.preflight(75, BASE, HEAD)


def test_owner_attestation_must_be_exactly_one(tmp_path: Path) -> None:
    subject, _git, github, _state = harness(tmp_path / "missing")
    github.comment_values[75].clear()
    with pytest.raises(integration.HarnessError, match="absent or duplicated"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "duplicate")
    github.comment_values[75].append(dict(github.comment_values[75][0]))
    with pytest.raises(integration.HarnessError, match="absent or duplicated"):
        subject.preflight(75, BASE, HEAD)


@pytest.mark.parametrize(
    "collaborators",
    [
        [],
        [
            {
                "id": OWNER_ID,
                "login": "ycpiglet",
                "type": "User",
                "permissions": {"admin": True},
            },
            {
                "id": 999,
                "login": "second",
                "type": "User",
                "permissions": {"admin": True},
            },
        ],
        [
            {
                "id": 999,
                "login": "ycpiglet",
                "type": "User",
                "permissions": {"admin": True},
            }
        ],
    ],
)
def test_owner_topology_rejects_collaborator_drift(
    tmp_path: Path, collaborators: list[dict[str, Any]]
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    github.collaborator_values = collaborators
    with pytest.raises(integration.HarnessError, match="collaborator"):
        subject.preflight(75, BASE, HEAD)


def test_preflight_rejects_sha_tree_and_queue_drift(tmp_path: Path) -> None:
    subject, git, github, _state = harness(tmp_path)
    with pytest.raises(integration.HarnessError, match="explicit expected base"):
        subject.preflight(75, "f" * 40, HEAD)

    git.trees[SYNTHETIC] = "f" * 40
    with pytest.raises(integration.HarnessError, match="tree differs"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "queue", number=75)
    github.pulls[74]["merged_at"] = None
    github.pulls[74]["state"] = "open"
    with pytest.raises(integration.HarnessError, match="predecessor"):
        subject.preflight(75, BASE, HEAD)


def test_predecessor_rejects_parent_tree_and_first_parent_drift(
    tmp_path: Path,
) -> None:
    subject, git, _github, _state = harness(tmp_path / "parents")
    git.parent_map[BOOT_MERGE] = (BOOT_HEAD, BOOT_BASE)
    with pytest.raises(integration.HarnessError, match="merge parents"):
        subject.preflight(75, BASE, HEAD)

    subject, git, _github, _state = harness(tmp_path / "tree")
    git.trees[BOOT_MERGE] = "f" * 40
    with pytest.raises(integration.HarnessError, match="source-equivalent"):
        subject.preflight(75, BASE, HEAD)

    subject, git, _github, _state = harness(tmp_path / "first-parent")
    git.first_parent_pairs.remove((BOOT_MERGE, BASE))
    with pytest.raises(integration.HarnessError, match="first-parent"):
        subject.preflight(75, BASE, HEAD)

    subject, git, _github, _state = harness(tmp_path / "source-first-parent")
    git.first_parent_pairs.remove((BOOT_BASE, BOOT_HEAD))
    with pytest.raises(integration.HarnessError, match="first-parent based"):
        subject.preflight(75, BASE, HEAD)


def test_predecessor_rejects_exact_head_check_or_bootstrap_comment_drift(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path / "head-check")
    github.checks[BOOT_HEAD]["check_runs"][0]["conclusion"] = "failure"
    with pytest.raises(integration.HarnessError, match="failure"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "comment")
    github.comment_values[74][0]["body"] += "\nforged"
    with pytest.raises(integration.HarnessError, match="bootstrap completion"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "merged-by")
    github.pulls[74]["merged_by"] = {
        "id": 999,
        "login": "automation",
        "type": "Bot",
    }
    with pytest.raises(integration.HarnessError, match="not merged by"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "author")
    github.comment_values[74][0]["user"]["id"] = 999
    with pytest.raises(integration.HarnessError, match="bootstrap completion"):
        subject.preflight(75, BASE, HEAD)


def test_predecessor_rejects_repo_branch_head_and_merge_identity_drift(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path / "repo")
    github.pulls[74]["head"]["repo"]["full_name"] = "attacker/fork"
    with pytest.raises(integration.HarnessError, match="repo/base/branch"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "branch")
    github.pulls[74]["head"]["ref"] = "agent/other"
    with pytest.raises(integration.HarnessError, match="repo/base/branch"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "head")
    github.pulls[74]["head"]["sha"] = "f" * 40
    with pytest.raises(integration.HarnessError, match="bootstrap pin"):
        subject.preflight(75, BASE, HEAD)

    subject, _git, github, _state = harness(tmp_path / "merge")
    github.pulls[74]["merge_commit_sha"] = "f" * 40
    with pytest.raises(integration.HarnessError, match="bootstrap pin"):
        subject.preflight(75, BASE, HEAD)


def test_mark_ready_is_separate_settled_and_comment_idempotent(
    tmp_path: Path,
) -> None:
    subject, _git, github, state = harness(tmp_path)

    evidence = subject.mark_ready(75, BASE, HEAD, settle_seconds=0)

    assert evidence.head_sha == HEAD
    assert github.ready_calls == ["PR_75"]
    stored = state.load(75)
    assert stored is not None
    assert stored["stage"] == "ready-validated"
    assert len(github.comment_markers) == 1

    subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    assert github.ready_calls == ["PR_75"]
    assert len(github.comment_markers) == 1


def test_mutations_reject_nonowner_authenticated_actor_before_write(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    github.authenticated_user_value = {
        "id": 999,
        "login": "write-capable-impostor",
        "type": "User",
    }
    with pytest.raises(integration.HarnessError, match="authenticated GitHub actor"):
        subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    assert github.ready_calls == []
    assert github.merge_calls == []
    assert github.comment_markers == set()


def test_evidence_comment_rechecks_actor_immediately_before_write(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path)
    calls = 0

    def drifting_actor() -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        if calls < 3:
            return {"id": OWNER_ID, "login": "ycpiglet", "type": "User"}
        return {"id": 999, "login": "impostor", "type": "User"}

    github.authenticated_user = drifting_actor
    with pytest.raises(integration.HarnessError, match="authenticated GitHub actor"):
        subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    assert github.ready_calls == ["PR_75"]
    assert github.comment_markers == set()


def test_mark_ready_rejects_auto_merge_before_mutation_and_after_settlement(
    tmp_path: Path,
) -> None:
    subject, _git, github, _state = harness(tmp_path / "before")
    github.pulls[75]["auto_merge"] = {"enabled_by": {"login": "ycpiglet"}}
    with pytest.raises(integration.HarnessError, match="auto-merge disabled"):
        subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    assert github.ready_calls == []

    subject, _git, github, _state = harness(tmp_path / "settled")
    original_pull = github.pull

    def pull_with_settlement_drift(number: int) -> Mapping[str, Any]:
        pull = original_pull(number)
        if number == 75 and github.ready_calls:
            pull["auto_merge"] = {"enabled_by": {"login": "ycpiglet"}}
        return pull

    github.pull = pull_with_settlement_drift
    with pytest.raises(integration.HarnessError, match="auto-merge disabled"):
        subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    assert github.ready_calls == ["PR_75"]
    assert github.comment_markers == set()


def test_merge_requires_ready_state_and_completes_exact_post_merge_gate(
    tmp_path: Path,
) -> None:
    subject, git, github, state = harness(tmp_path)
    with pytest.raises(integration.HarnessError, match="state is absent"):
        subject.merge(
            75,
            BASE,
            HEAD,
            settle_seconds=0,
            poll_seconds=1,
            timeout_seconds=1,
        )

    subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    completed = subject.merge(
        75,
        BASE,
        HEAD,
        settle_seconds=0,
        poll_seconds=1,
        timeout_seconds=1,
    )

    assert github.merge_calls == [(75, HEAD)]
    assert git.origin_main == MERGE
    assert completed["stage"] == "complete"
    assert completed["merge_sha"] == MERGE
    assert list(completed["post_merge_checks"]) == list(policy().required_checks)
    assert state.load(75)["stage"] == "complete"
    assert len(github.comment_markers) == 2

    repeated = subject.merge(
        75,
        BASE,
        HEAD,
        settle_seconds=0,
        poll_seconds=1,
        timeout_seconds=1,
    )
    assert repeated["stage"] == "complete"
    assert github.merge_calls == [(75, HEAD)]


def test_post_check_wait_revalidates_full_live_snapshot(tmp_path: Path) -> None:
    subject, _git, github, _state = harness(tmp_path)
    subject.mark_ready(75, BASE, HEAD, settle_seconds=0)
    original_check_runs = github.check_runs
    merge_check_calls = 0

    def checks_with_queue_drift(sha: str) -> Mapping[str, Any]:
        nonlocal merge_check_calls
        result = original_check_runs(sha)
        if sha == MERGE:
            merge_check_calls += 1
            if merge_check_calls == 1:
                github.pulls[72]["state"] = "closed"
                github.pulls[72]["merged_at"] = "2026-07-26T02:00:00Z"
        return result

    github.check_runs = checks_with_queue_drift
    with pytest.raises(integration.HarnessError, match="successor"):
        subject.merge(
            75,
            BASE,
            HEAD,
            settle_seconds=0,
            poll_seconds=1,
            timeout_seconds=1,
        )


def test_merge_recovers_if_process_stopped_after_github_accepted_merge(
    tmp_path: Path,
) -> None:
    subject, git, github, state = harness(tmp_path)
    state.save(
        75,
        {
            "policy_id": policy().policy_id,
            "repository": policy().repository,
            "number": 75,
            "work_id": "OPS-01A",
            "expected_base": BASE,
            "expected_head": HEAD,
            "head_tree": HEAD_TREE,
            "stage": "merge-requested",
        },
    )
    git.origin_main = MERGE
    github.pulls[75]["state"] = "closed"
    github.pulls[75]["draft"] = False
    github.pulls[75]["merged_at"] = "2026-07-26T01:00:00Z"
    github.pulls[75]["merge_commit_sha"] = MERGE
    github.pulls[75]["merged_by"] = {
        "id": OWNER_ID,
        "login": "ycpiglet",
        "type": "User",
    }

    completed = subject.merge(
        75,
        BASE,
        HEAD,
        settle_seconds=0,
        poll_seconds=1,
        timeout_seconds=1,
    )

    assert completed["stage"] == "complete"
    assert github.merge_calls == []


def test_forged_complete_state_is_live_revalidated_and_check_ids_refresh(
    tmp_path: Path,
) -> None:
    subject, git, github, state = harness(tmp_path)
    current_policy = policy()
    save_complete_state(state, current_policy)
    mark_fake_merged(git, github)

    completed = subject.merge(
        75,
        BASE,
        HEAD,
        settle_seconds=0,
        poll_seconds=1,
        timeout_seconds=1,
    )

    assert completed["post_merge_checks"] == {
        context: 100 + index
        for index, context in enumerate(current_policy.required_checks)
    }
    assert github.merge_calls == []


def test_complete_resume_rejects_head_check_and_full_queue_drift(
    tmp_path: Path,
) -> None:
    subject, git, github, state = harness(tmp_path / "head-check")
    save_complete_state(state, policy())
    mark_fake_merged(git, github)
    github.checks[HEAD]["check_runs"][0]["conclusion"] = "failure"
    with pytest.raises(integration.HarnessError, match="failure"):
        subject.merge(
            75,
            BASE,
            HEAD,
            settle_seconds=0,
            poll_seconds=1,
            timeout_seconds=1,
        )

    subject, git, github, state = harness(tmp_path / "successor")
    save_complete_state(state, policy())
    mark_fake_merged(git, github)
    github.pulls[72]["state"] = "closed"
    github.pulls[72]["merged_at"] = "2026-07-26T02:00:00Z"
    with pytest.raises(integration.HarnessError, match="successor"):
        subject.merge(
            75,
            BASE,
            HEAD,
            settle_seconds=0,
            poll_seconds=1,
            timeout_seconds=1,
        )

    subject, git, github, state = harness(tmp_path / "merged-by")
    save_complete_state(state, policy())
    mark_fake_merged(git, github)
    github.pulls[75]["merged_by"] = {
        "id": 999,
        "login": "automation",
        "type": "Bot",
    }
    with pytest.raises(integration.HarnessError, match="not merged by"):
        subject.merge(
            75,
            BASE,
            HEAD,
            settle_seconds=0,
            poll_seconds=1,
            timeout_seconds=1,
        )


def test_state_schema_rejects_extra_wrong_work_and_invalid_check_ids(
    tmp_path: Path,
) -> None:
    subject, _git, _github, state = harness(tmp_path)
    current_policy = policy()
    document = {
        "schema_version": 1,
        "updated_at": "2026-07-26T00:00:00Z",
        "policy_id": current_policy.policy_id,
        "repository": current_policy.repository,
        "number": 75,
        "work_id": "OPS-01A",
        "expected_base": BASE,
        "expected_head": HEAD,
        "head_tree": HEAD_TREE,
        "stage": "ready-validated",
    }
    with pytest.raises(integration.HarnessError, match="keys must be exact"):
        integration.validate_state_shape({**document, "forged": True})

    wrong_work = dict(document)
    wrong_work["work_id"] = "FORGED"
    with pytest.raises(integration.HarnessError, match="work_id"):
        subject._validate_state_identity(
            wrong_work, current_policy.item(75), BASE, HEAD
        )

    complete = {
        **document,
        "stage": "complete",
        "merge_sha": MERGE,
        "post_merge_checks": {
            context: 100 + index
            for index, context in enumerate(current_policy.required_checks)
        },
        "completed_at": "2026-07-26T01:00:00Z",
    }
    complete["post_merge_checks"][current_policy.required_checks[0]] = True
    with pytest.raises(integration.HarnessError, match="integer"):
        integration.validate_state_shape(complete)


@pytest.mark.skipif(os.name != "posix", reason="POSIX advisory-lock regression")
def test_advisory_lock_contention_and_release(tmp_path: Path) -> None:
    common_dir = tmp_path / "common.git"
    common_dir.mkdir()
    state = integration.StateStore(common_dir)
    with state.lock():
        with pytest.raises(integration.HarnessError, match="locked"):
            with state.lock():
                raise AssertionError("contended lock unexpectedly acquired")
    with state.lock():
        pass


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow regression")
def test_state_paths_reject_symlinks_without_touching_targets(tmp_path: Path) -> None:
    common_dir = tmp_path / "common.git"
    common_dir.mkdir()
    victim_directory = tmp_path / "victim-directory"
    victim_directory.mkdir()
    (common_dir / "codex").symlink_to(victim_directory, target_is_directory=True)
    state = integration.StateStore(common_dir)
    with pytest.raises(integration.HarnessError, match="not a real directory"):
        with state.lock():
            raise AssertionError("symlinked state directory unexpectedly accepted")

    (common_dir / "codex").unlink()
    lock_parent = common_dir / "codex" / "protected-integration"
    lock_parent.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("must remain intact\n", encoding="utf-8")
    (common_dir / integration.LOCK_FILE).symlink_to(victim)
    with pytest.raises(integration.HarnessError, match="safely open"):
        with state.lock():
            raise AssertionError("symlinked lock unexpectedly accepted")
    assert victim.read_text(encoding="utf-8") == "must remain intact\n"


def test_cli_has_no_expansive_or_destructive_operation() -> None:
    parser = integration.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == {"validate-policy", "preflight", "mark-ready", "merge"}
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "artifacts/" not in source
    assert "outputs/" not in source
    assert "createRelease" not in source
    assert "deleteRef" not in source


def test_github_api_forces_host_headers_and_rejects_unknown_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_HOST", "attacker.example")
    runner = RecordingRunner([json.dumps({"number": 75})])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    assert client.pull(75)["number"] == 75
    arguments = runner.calls[0][0]
    assert arguments[arguments.index("--hostname") + 1] == "github.com"
    assert "Accept: application/vnd.github+json" in arguments
    assert "X-GitHub-Api-Version: 2022-11-28" in arguments
    assert "attacker.example" not in arguments
    with pytest.raises(integration.HarnessError, match="not allowlisted"):
        client._api("repos/ycpiglet/manipulator-control-tutorial/releases")


def test_graphql_forces_host_and_version_headers() -> None:
    response = {
        "data": {
            "markPullRequestReadyForReview": {
                "pullRequest": {"id": "PR_75", "isDraft": False}
            }
        }
    }
    runner = RecordingRunner([json.dumps(response)])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    client.mark_ready("PR_75")
    arguments = runner.calls[0][0]
    assert arguments[arguments.index("--hostname") + 1] == "github.com"
    assert "Accept: application/vnd.github+json" in arguments
    assert "X-GitHub-Api-Version: 2022-11-28" in arguments
    with pytest.raises(integration.HarnessError, match="not allowlisted"):
        client._graphql("forged", {})


@pytest.mark.parametrize("has_next_page", [None, 0, "false"])
def test_review_threads_requires_exact_complete_page(
    has_next_page: object,
) -> None:
    response = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": has_next_page},
                        "nodes": [],
                    }
                }
            }
        }
    }
    runner = RecordingRunner([json.dumps(response)])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    with pytest.raises(integration.HarnessError, match="pagination"):
        client.review_threads(75)


def test_comment_writer_cannot_fabricate_attestation_and_verifies_owner() -> None:
    runner = RecordingRunner([])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    owner_marker = integration.owner_attestation_marker(75, HEAD)
    with pytest.raises(integration.HarnessError, match="pre/post evidence"):
        client.ensure_comment(75, owner_marker, owner_marker + "\nforged")
    assert runner.calls == []

    marker = (
        f"<!-- protected-integration:v1:pr-75:{HEAD}:premerge:"
        f"{'f' * 64} -->"
    )
    body = marker + "\nevidence"
    created = {
        "id": 10,
        "body": body,
        "user": {"id": OWNER_ID, "login": "ycpiglet", "type": "User"},
        "author_association": "OWNER",
    }
    runner = RecordingRunner([json.dumps([]), json.dumps(created)])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    assert client.ensure_comment(75, marker, body) is True

    forged = dict(created)
    forged["user"] = {"id": 999, "login": "impostor", "type": "User"}
    runner = RecordingRunner([json.dumps([]), json.dumps(forged)])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    with pytest.raises(integration.CommandError, match="did not confirm"):
        client.ensure_comment(75, marker, body)


def test_authenticated_user_endpoint_is_exactly_allowlisted() -> None:
    actor = {"id": OWNER_ID, "login": "ycpiglet", "type": "User"}
    runner = RecordingRunner([json.dumps(actor)])
    client = integration.GitHubClient(
        runner, "ycpiglet/manipulator-control-tutorial"
    )
    assert client.authenticated_user() == actor
    assert runner.calls[0][0][-1] == "user"


def test_subprocess_runner_timeout_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=120)

    monkeypatch.setattr(integration.subprocess, "run", time_out)
    runner = integration.SubprocessRunner()
    with pytest.raises(integration.CommandError, match="timed out"):
        runner.run(["git", "status"])
    with pytest.raises(integration.CommandError, match="timed out"):
        runner.run_bytes(["git", "status"])


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        (
            "git@github.com:ycpiglet/manipulator-control-tutorial.git",
            "ycpiglet/manipulator-control-tutorial",
        ),
        (
            "https://github.com/ycpiglet/manipulator-control-tutorial",
            "ycpiglet/manipulator-control-tutorial",
        ),
    ],
)
def test_origin_normalization_is_exact(remote: str, expected: str) -> None:
    assert integration.normalize_github_remote(remote) == expected
    with pytest.raises(integration.HarnessError):
        integration.normalize_github_remote("/tmp/local-repository")
