---
name: environment-secrets-manager
description: Manage environment variables, secret handling, .env files, configuration separation, rotation notes, and deployment environment hygiene. Use when adding config, auditing secrets, or preparing local/CI/production environments.
---

# Environment Secrets Manager

## Workflow

1. Identify environments: local, test, CI, staging, production, and documentation examples.
2. Separate secrets from non-secret configuration.
3. Keep secret names stable and descriptive; keep example values fake.
4. Check `.gitignore`, CI secret settings, runtime config loading, and docs together.
5. Avoid exposing secret values in logs, command output, screenshots, commits, or generated artifacts.

## Configuration Rules

- Use `.env.example` or documented variables for required local setup.
- Prefer least-privilege credentials per environment.
- Rotate credentials when exposure is suspected.
- Avoid embedding secrets in YAML configs, notebooks, generated reports, or code comments.
- Validate required variables early with clear errors.

## Review Checklist

Check names, owners, scopes, rotation expectations, local setup instructions, CI usage, deployment usage, and fallback behavior.

## Output

Return the variable inventory, required changes, example docs, secret risks, and verification commands.
