# GOV-01 — Repository Governance Evidence

- Updated: 2026-07-20 KST
- Status: **GOV-01A PASS; GOV-01B PASS; GOV-01C candidate in validation**
- B1 subject: `f04cca16848316e227df18fe129229b515ae01c7`
- GOV-01A merge: `9f4169f60efb32d6b6d49b9f06d985d8de9c6f70`
- GOV-01C implementation commit: `5de658127a392f6802e5c68d099bdbab597f8371`
- GOV-01 aggregate: **INCOMPLETE** until replacement CI, merge, and Action SHA
  enforcement all pass

## GOV-01A — Policy Baseline

PR [#39](https://github.com/ycpiglet/manipulator-control-tutorial/pull/39)
added the B1 declaration, CODEOWNERS, security/support policies, PR template,
safe contribution guidance, and the A/B/C completion split.

- exact-head required checks: 6/6 success;
- changed-document relative links: 8/8 valid;
- independently reproduced B1 multi-root fingerprints: 3/3;
- independent read-only policy review: pass;
- merge commit: `9f4169f60efb32d6b6d49b9f06d985d8de9c6f70`;
- policy merge evidence: [PR comment](https://github.com/ycpiglet/manipulator-control-tutorial/pull/39#issuecomment-5022922361).

Private Vulnerability Reporting was enabled and read back as
`{"enabled": true}` before the policy reached `main`.

## GOV-01B — Live Repository Settings

Post-change API snapshot time: 2026-07-20 22:44 KST.

| Control | Verified state |
|---|---|
| Ruleset | `Protect main (GOV-01B)`, ID `19209773`, active |
| Target | `refs/heads/main` |
| Destructive ref changes | deletion and non-fast-forward blocked |
| Pull requests | required; conversation resolution required; approvals `0` |
| Required checks | six exact contexts, GitHub Actions app ID `15368` |
| Branch freshness | strict/up-to-date required |
| Admin recovery | repository admin bypass is PR-only |
| Vulnerability alerts | enabled |
| Dependabot security updates | enabled, not paused |
| Private vulnerability reporting | enabled |
| Secret scanning / push protection | enabled / enabled |
| Default Actions token | read-only; PR approval disabled |

The effective-rules endpoint for `main` returned the same deletion,
non-fast-forward, pull-request, and status-check rules. The durable settings
snapshot is also recorded in the [PR #39 settings comment](https://github.com/ycpiglet/manipulator-control-tutorial/pull/39#issuecomment-5022942731).

Only one direct collaborator exists and has the admin role. Required approvals
therefore remain zero until a second human maintainer is available. PRs,
conversation resolution, six exact checks, CODEOWNERS routing, explicit owner
risk acceptance, and an independent read-only review remain mandatory. This is
not represented as formal independent human approval.

## GOV-01C — Immutable Action Candidate

The candidate replaces 12 mutable action uses with these independently
rechecked commits. Each exact-version tag resolved to the listed SHA and the
GitHub commit API returned `verification.verified=true`.

| Action | Version annotation | Full commit SHA |
|---|---|---|
| `actions/checkout` | `v4.3.1` | `34e114876b0b11c390a56381ad16ebd13914f8d5` |
| `actions/setup-python` | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/cache` | `v4.3.0` | `0057852bfaa89a56745cba8c7296529d2fc39830` |
| `actions/upload-artifact` | `v4.6.2` | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `WtfJoke/setup-tectonic` | `v3.1.5` | `8a63d072f8390efdff59da7fa08aa49e3c1f5e1b` |

Additional candidate controls:

- all four checkout steps set `persist-credentials: false`;
- Tectonic is pinned to release `0.16.9`;
- Dependabot checks GitHub Actions weekly without grouping or auto-merge;
- `.agents/validation/check_workflow_action_pins.py` requires full commit SHAs
  for repository Actions and `sha256` digests for Docker Actions, and is called
  by CI;
- tests prove the current 12-reference inventory passes while mutable Action
  tags and mutable Docker image tags fail.

The audited Linux Tectonic asset is
`tectonic-0.16.9-x86_64-unknown-linux-gnu.tar.gz`, size 21,568,986 bytes,
release digest
`sha256:f3c825128095dc3399ea11c08c18035b33050a216930c295c79e8eb11bd21de4`.
The third-party setup Action selects the fixed release but does not verify that
digest. Replacing it with an explicit download-and-hash step remains a SUP-01
hardening item; this residual risk is not hidden by the Action source pin.

## Remaining GOV-01C Gate

GOV-01C and aggregate GOV-01 pass only after all of the following are true:

1. checker, YAML parse, Ruff, targeted tests, and all six exact-head GitHub
   checks pass;
2. the candidate is merged through the active ruleset;
3. repository Actions policy is changed to `sha_pinning_required=true`;
4. the API reads that setting back as true and a fresh scan finds 12/12 full
   SHAs on `main`.

Until then, GOV-01 and B2 remain incomplete.

## Rollback and Recovery

- If a pinned Action or fixed Tectonic release breaks a required job, the
  default recovery is a PR that replaces it with a previously reviewed full
  SHA or another reviewed immutable implementation. Do not restore a mutable
  tag merely to reproduce the old workflow.
- Do not enable SHA enforcement before the green replacement run.
- If an emergency requires reverting all the way to the historical mutable-tag
  workflow, temporarily disable only `sha_pinning_required`, record the API
  state before and after, merge the revert through the still-active ruleset,
  then land an immutable repair and re-enable SHA enforcement after its green
  run. The repository must remain in a degraded, explicitly recorded state
  until enforcement is restored.
- Actions SHA enforcement and branch ruleset `19209773` are separate controls.
  Do not disable the ruleset to repair an Action pin. If the ruleset itself
  blocks legitimate recovery, inspect or temporarily disable only that exact
  ruleset, record the change, repair through a PR, and restore active
  enforcement.
- Do not disable vulnerability alerts, private reporting, secret scanning, or
  push protection to work around an unrelated workflow failure.
