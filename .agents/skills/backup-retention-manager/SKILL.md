---
name: backup-retention-manager
description: Plan backup, archive, retention, restore testing, and disaster recovery workflows for code, data, generated artifacts, papers, and product state. Use when defining what must be preserved and how recovery is proven.
---

# Backup Retention Manager

## Workflow

1. Identify critical assets: source, configs, datasets, model files, credentials references, generated artifacts, papers, logs, and release packages.
2. Classify assets by recoverability, sensitivity, size, and required retention period.
3. Define backup location, cadence, retention, access control, and encryption expectations.
4. Define restore tests; a backup is not proven until restoration has been exercised.
5. Record ownership and expiration rules.

## Retention Questions

- What is the recovery point objective and recovery time objective?
- Which artifacts are reproducible and which are expensive or impossible to regenerate?
- Which files contain sensitive or licensed material?
- What must be archived for audit, publication, or release reproducibility?
- What should expire automatically?

## Restore Plan

Include exact source, destination, validation commands, expected checksums or counts, and rollback if restoration fails.

## Output

Return asset classes, retention rules, backup plan, restore test plan, and unresolved policy decisions.
