---
name: incident-response-manager
description: Coordinate software incident response, severity classification, mitigation, timeline building, communication, and postmortems. Use when a system is broken, users are affected, or an operational failure needs structured handling.
---

# Incident Response Manager

## Workflow

1. Stabilize first: identify user impact, severity, current status, owner, and immediate mitigation.
2. Create a timeline using concrete timestamps, commands, alerts, deployments, and user reports.
3. Separate symptoms, hypotheses, evidence, mitigations, and root causes.
4. Prefer reversible mitigation over speculative permanent fixes during active incidents.
5. After recovery, write follow-up actions that prevent recurrence or reduce impact.

## Severity Inputs

- Number and type of users affected.
- Data loss, safety, security, financial, or compliance impact.
- Workaround availability.
- Duration and trend.
- Confidence in the mitigation.

## Communication

- Use concise status updates: impact, start time, current state, mitigation, next update time.
- Avoid blame and unsupported certainty.
- Preserve commands, links, logs, screenshots, and artifact ids as evidence.

## Postmortem

Include impact, detection, timeline, contributing factors, what went well, what went poorly, and action items with owners and due dates.
