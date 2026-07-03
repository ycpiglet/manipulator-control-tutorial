---
name: product-analytics-manager
description: Design and review product analytics, event taxonomy, KPI definitions, funnels, cohorts, instrumentation plans, and metric interpretation. Use when measuring usage, adoption, retention, activation, or feature impact.
---

# Product Analytics Manager

## Workflow

1. Start from the product decision the metric should inform.
2. Define users, sessions, events, properties, cohorts, and time windows explicitly.
3. Separate product-health metrics from operational metrics and vanity metrics.
4. Create an event taxonomy that is stable, readable, and versionable.
5. Validate instrumentation against real workflows before trusting dashboards.

## Event Design

- Use consistent names with an object-action pattern when possible.
- Include properties that explain context without collecting unnecessary personal data.
- Capture success and failure states for important workflows.
- Version events when meaning changes.
- Document owner, source, destination, and expected volume.

## Metric Review

Check numerator, denominator, exclusion rules, sampling, bot/internal traffic, timezone, delayed events, and survivorship bias.

## Output

Return KPI definitions, event taxonomy, funnel/cohort plan, instrumentation tasks, and interpretation cautions.
