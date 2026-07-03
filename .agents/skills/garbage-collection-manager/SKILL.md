---
name: garbage-collection-manager
description: Identify and safely clean stale files, generated artifacts, caches, logs, obsolete branches, unused configs, and redundant outputs. Use when reducing repository clutter, managing output retention, or designing cleanup policies.
---

# Garbage Collection Manager

## Workflow

1. Inventory generated files, caches, logs, temporary directories, old artifacts, duplicate outputs, and obsolete configs.
2. Classify each item as source, generated reproducible artifact, generated non-reproducible artifact, cache, local-only state, or unknown.
3. Never delete unknown or potentially user-authored files without evidence or explicit confirmation.
4. Prefer retention rules and `.gitignore` updates before one-off cleanup.
5. Before deletion or movement, list exact paths, reason, and recovery strategy.

## Safety Rules

- Preserve source files, configs, datasets, model assets, citations, licenses, and provenance records.
- Preserve the newest successful artifact for important demos unless the user asks for a deeper cleanup.
- Use dry-run style reporting when cleanup scope is broad.
- Keep generated outputs reproducible from documented commands.
- On Windows, verify absolute target paths before recursive delete or move operations.

## Cleanup Policy

Define what to keep, for how long, where to archive it, and how to regenerate it. Connect cleanup to version, experiment, or release state when possible.

## Output

Return an inventory, proposed cleanup actions, retained artifacts, ignored patterns, and commands run or ready to run.
