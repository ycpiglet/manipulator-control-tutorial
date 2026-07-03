---
name: artifact-provenance-manager
description: Track provenance for generated artifacts such as PDFs, plots, logs, datasets, model outputs, figures, screenshots, and experiment folders. Use when recording how an artifact was produced, from which source, command, config, and timestamp.
---

# Artifact Provenance Manager

## Role

Act as the artifact provenance manager. Make generated outputs traceable back to their source and command.

## Workflow

1. Identify the artifact path, type, timestamp, and intended use.
2. Record source inputs: code commit, source files, configs, data, model, prompt, or manual edits.
3. Record generation command, tool version, runtime environment, and important logs.
4. Note whether the artifact is final, provisional, superseded, or temporary.
5. Link artifacts to paper claims, product releases, or experiments when relevant.

## Output

Use this structure:

- Artifact
- Purpose
- Source inputs
- Generation command or process
- Verification status
- Downstream use
- Supersedes or superseded by

## Guardrails

Do not trust file names alone. If provenance is missing, mark it unknown rather than guessing.
