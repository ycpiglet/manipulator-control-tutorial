---
name: deployment-rollback-manager
description: Prepare deployment, release, rollback, canary, blue-green, and recovery plans for software or documentation artifacts. Use when shipping changes, defining go/no-go checks, or planning how to safely undo a release.
---

# Deployment Rollback Manager

## Workflow

1. Identify the release artifact, target environment, operator, audience, and blast radius.
2. Confirm pre-deploy checks: tests, migrations, config changes, secrets, compatibility, documentation, and monitoring.
3. Define the rollout strategy: direct, staged, canary, blue-green, feature flag, or manual handoff.
4. Define rollback before deployment starts.
5. After deployment, verify user-facing behavior and operational signals.

## Rollback Plan

- Name the exact artifact or version to restore.
- State which data migrations are reversible, forward-only, or require manual repair.
- Include config and secret rollback, not only code rollback.
- Capture how to validate recovery: health checks, logs, metrics, smoke tests, and user-facing checks.
- Include a stop condition for abandoning rollback and escalating.

## Go/No-Go Checks

- Required tests pass.
- Release notes or change log are ready.
- Observability exists for the changed path.
- Known risks have owners.
- Rollback path has been reviewed.

## Output

Return a deploy checklist, rollback checklist, verification steps, and clear go/no-go recommendation.
