---
name: dependency-update-manager
description: Manage dependency upgrades, lockfiles, compatibility checks, vulnerability updates, changelog review, and dependency hygiene. Use when updating packages, reducing supply-chain risk, or planning safe version bumps.
---

# Dependency Update Manager

## Workflow

1. Detect package managers, lockfiles, runtime versions, and dependency groups.
2. Classify updates as patch, minor, major, security, runtime, build-tool, or transitive.
3. Read changelogs or release notes for breaking changes when the update is not obviously safe.
4. Update lockfiles with the repository's native tooling.
5. Run the narrowest meaningful test set first, then broaden if shared behavior changed.

## Upgrade Policy

- Prefer small batches for risky libraries and large batches for low-risk patch updates only when tests are strong.
- Keep runtime and package manager versions explicit.
- Do not mix unrelated dependency upgrades with feature work unless required.
- Preserve license notices and third-party attribution.
- Record compatibility notes for user-facing or reproducibility-sensitive changes.

## Vulnerability Triage

Check whether the vulnerable code path is reachable, exposed, authenticated, mitigated, or only a dev dependency. Still update when the fix is low-risk.

## Output

Return updated dependency scope, rationale, changelog highlights, test results, and any follow-up compatibility risks.
