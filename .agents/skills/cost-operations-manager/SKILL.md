---
name: cost-operations-manager
description: Analyze and manage operational cost for cloud resources, CI minutes, storage, APIs, model calls, artifacts, and experiments. Use when reducing waste, estimating run cost, or adding cost visibility to product operations.
---

# Cost Operations Manager

## Workflow

1. Identify cost drivers: compute, storage, network, CI, third-party APIs, model calls, observability, backups, and long-running jobs.
2. Connect cost to owners, environments, projects, branches, experiments, or releases.
3. Distinguish fixed baseline cost from variable usage cost.
4. Prefer measurement and tagging before optimization.
5. Recommend changes that preserve reliability, reproducibility, and user value.

## Optimization Areas

- CI: cache dependencies, split fast and slow jobs, avoid unnecessary matrix expansion.
- Storage: retention policies, artifact compression, archive tiers, generated-output cleanup.
- Compute: right-sized instances, autoscaling, scheduled shutdown, batch windows.
- APIs/models: request batching, caching, model choice, rate limits, usage budgets.
- Observability: sample noisy logs/traces while preserving incident evidence.

## Guardrails

Do not cut monitoring, backups, tests, or security controls without stating the reliability tradeoff.

## Output

Return current cost drivers, measurement gaps, quick wins, structural changes, and risks.
