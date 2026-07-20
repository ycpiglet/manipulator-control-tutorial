"""Reject mutable external GitHub Action references in workflow files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
USES_RE = re.compile(r"\buses:\s*([^\s#]+)")
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
DOCKER_DIGEST_RE = re.compile(r"docker://[^@\s]+@sha256:[0-9a-f]{64}")


def workflow_files(workflow_root: Path = WORKFLOW_ROOT) -> list[Path]:
    """Return GitHub workflow YAML files in stable order."""

    return sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))


def external_action_references(paths: list[Path]) -> list[tuple[Path, int, str]]:
    """Return external action references, excluding repository-local actions."""

    references: list[tuple[Path, int, str]] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES_RE.search(line)
            if match is None:
                continue
            reference = match.group(1)
            if reference.startswith("./"):
                continue
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


def main() -> int:
    paths = workflow_files()
    references = external_action_references(paths)
    unpinned = unpinned_references(references)

    print(f"workflow files: {len(paths)}")
    print(f"external action references: {len(references)}")
    for path, line_number, reference in unpinned:
        print(f"NOT_PINNED {path.relative_to(ROOT)}:{line_number}: {reference}")
    print("status:", "FAIL" if unpinned else "PASS")
    return 1 if unpinned else 0


if __name__ == "__main__":
    sys.exit(main())
