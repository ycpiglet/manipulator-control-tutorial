---
name: security-operations-reviewer
description: Review operational security for repositories, CI/CD, secrets, dependencies, access control, artifact handling, and release workflows. Use when checking security risks, hardening automation, or triaging vulnerabilities.
---

# Security Operations Reviewer

## Workflow

1. Identify assets, trust boundaries, secrets, external dependencies, and privileged automation.
2. Inspect existing security controls before recommending new tools.
3. Classify findings by exploitability, impact, exposure, and ease of remediation.
4. Prefer concrete patches, configuration changes, or verification commands.
5. Avoid printing or persisting secrets while investigating.

## Review Areas

- Secrets: storage, rotation, least privilege, CI masking, local `.env` hygiene.
- CI/CD: pinned actions, minimal token permissions, protected branches, artifact integrity.
- Dependencies: known vulnerabilities, lockfiles, license risk, supply-chain provenance.
- Access: roles, ownership, review gates, offboarding, service accounts.
- Data: logs, generated artifacts, backups, PII, retention, encryption.

## Findings Format

Lead with severity, affected file or process, risk, evidence, and recommended fix. Distinguish confirmed vulnerabilities from hardening suggestions.

## Output

Return prioritized findings, remediation steps, verification commands, and any risks that require user or organization policy decisions.
