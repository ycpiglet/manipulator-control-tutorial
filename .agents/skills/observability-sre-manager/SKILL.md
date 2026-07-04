---
name: observability-sre-manager
description: Design and review observability, SRE signals, logs, metrics, traces, dashboards, SLIs, SLOs, and alerting. Use when adding monitoring, investigating reliability, defining service health, or making operations visible.
---

# Observability SRE Manager

## Workflow

1. Identify the user journey or system behavior that must remain healthy.
2. Define signals before dashboards: latency, errors, traffic, saturation, freshness, correctness, or artifact completion.
3. Choose SLIs that can be measured from production-like evidence.
4. Set SLOs only when the target reflects user expectations and operational capacity.
5. Alert only on actionable symptoms, not every internal warning.

## Instrumentation Checklist

- Logs include event name, timestamp, correlation or run id, severity, and enough context to debug without leaking secrets.
- Metrics distinguish counters, gauges, histograms, and derived rates.
- Traces connect slow user paths or background jobs across boundaries.
- Dashboards answer first-response questions quickly: what is broken, who is affected, since when, and how bad.
- Synthetic checks or smoke runs cover critical flows that normal traffic may not exercise.

## Alert Hygiene

- Prefer symptom-based alerts tied to user impact.
- Include runbook links or immediate diagnostic commands.
- Avoid paging for non-actionable warnings, low-volume noise, or self-healing blips.
- Review stale alerts after incidents and releases.

## Output

Return proposed SLIs/SLOs, logs, metrics, dashboard panels, alert rules, and runbook gaps.
