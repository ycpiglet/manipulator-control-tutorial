---
name: cicd-pipeline-manager
description: Design, review, and troubleshoot CI/CD pipelines for code, simulation labs, documentation, and product releases. Use when adding workflow automation, choosing build/test/deploy gates, fixing pipeline failures, or defining release checks.
---

# CI/CD Pipeline Manager

## Workflow

1. Inspect the repository's existing pipeline files, package metadata, test commands, and deployment conventions before proposing changes.
2. Identify the trigger, target artifact, environment, and required evidence for the requested pipeline.
3. Keep the pipeline reproducible from local commands first, then encode the same commands in CI.
4. Separate fast checks from expensive checks so pull requests get quick feedback while scheduled or release workflows can run deeper validation.
5. Treat generated artifacts, logs, plots, reports, and PDFs as named outputs with retention rules.

## Pipeline Shape

- Use clear stages: checkout, setup, dependency cache, lint/static checks, unit tests, smoke tests, integration tests, build/package, artifact upload, deploy, notify.
- Prefer explicit version pins for runtimes, actions, and toolchains.
- Cache only deterministic dependency directories; avoid caching generated outputs that can hide stale state.
- Add matrix jobs only when they answer a real compatibility question.
- Gate deployment on tests, artifact generation, and configuration validation.

## Failure Triage

- Start from the first failing command, not the last log line.
- Reproduce locally with the same command, environment variables, and working directory where possible.
- Classify failures as code, dependency, environment, secret, timeout, flaky test, quota, or external service.
- Propose the smallest pipeline change that improves reliability without masking the underlying failure.

## Output

Return a compact plan or patch summary containing the pipeline files touched, commands added, expected artifacts, rollback considerations, and any residual risk.
