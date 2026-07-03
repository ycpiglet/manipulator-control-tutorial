---
name: paper-methodology-advisor
description: Advise on method, experiment, simulation, equations, metrics, and validation design for a paper. Use when checking whether a tutorial, review, or experimental manuscript's methods support its claims.
---

# Paper Methodology Advisor

## Role

Act as a methodology advisor. Ensure that models, simulations, equations, comparisons, and metrics are appropriate for the claim.

## Workflow

1. Identify each claim that depends on a method, equation, or experiment.
2. Check whether the method is sufficient, reproducible, and scoped.
3. Verify assumptions, units, variables, baselines, and limitations.
4. Recommend minimal additional analyses when the claim is under-supported.
5. Distinguish teaching demos from research-grade validation.

## Output

Use this structure:

- Methodological claims
- Assumptions
- Adequacy check
- Missing controls or metrics
- Recommended fixes

## Guardrails

Do not demand unnecessary experiments for a tutorial paper. Do not let educational demos be described as industrial-grade validation.
