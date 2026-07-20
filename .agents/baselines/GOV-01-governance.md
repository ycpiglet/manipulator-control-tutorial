# GOV-01 — Repository Governance Evidence

- Updated: 2026-07-21 KST
- Status: **GOV-01A/B/C PASS; GOV-01 aggregate COMPLETE**
- B1 subject: `f04cca16848316e227df18fe129229b515ae01c7`
- GOV-01A merge: `9f4169f60efb32d6b6d49b9f06d985d8de9c6f70`
- GOV-01C source PR: [#40](https://github.com/ycpiglet/manipulator-control-tutorial/pull/40)
- GOV-01C exact head: `e26c1ab40d77af0d3744c217736477ef2592251c`
- GOV-01C merge: `41be887f21bfb476507d94a089f98c0ef72453c8`
- Ruleset: `Protect main (GOV-01B)`, ID `19209773`, active
- Repository Action policy: `sha_pinning_required=true`

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
| Action reference policy | full-SHA pinning required |

The effective-rules endpoint for `main` returned the same deletion,
non-fast-forward, pull-request, and status-check rules. The durable settings
snapshot is also recorded in the [PR #39 settings comment](https://github.com/ycpiglet/manipulator-control-tutorial/pull/39#issuecomment-5022942731).

Only one direct collaborator exists and has the admin role. Required approvals
therefore remain zero until a second human maintainer is available. PRs,
conversation resolution, six exact checks, CODEOWNERS routing, explicit owner
risk acceptance, and an independent read-only review remain mandatory. This is
not represented as formal independent human approval.

## GOV-01C — Immutable Actions

PR #40 replaced 12 mutable Action uses with these independently rechecked
commits. Each exact-version tag resolved to the listed SHA and the GitHub
commit API returned `verification.verified=true`.

| Action | Version annotation | Full commit SHA |
|---|---|---|
| `actions/checkout` | `v4.3.1` | `34e114876b0b11c390a56381ad16ebd13914f8d5` |
| `actions/setup-python` | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/cache` | `v4.3.0` | `0057852bfaa89a56745cba8c7296529d2fc39830` |
| `actions/upload-artifact` | `v4.6.2` | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `WtfJoke/setup-tectonic` | `v3.1.5` | `8a63d072f8390efdff59da7fa08aa49e3c1f5e1b` |

Additional controls:

- all four checkout steps set `persist-credentials: false`;
- Tectonic is pinned to release `0.16.9`;
- Dependabot checks GitHub Actions weekly without grouping or auto-merge;
- `.agents/validation/check_workflow_action_pins.py` requires full commit SHAs
  for repository Actions and `sha256` digests for Docker Actions, and is called
  by CI;
- tests prove the 12-reference inventory passes while mutable Action tags and
  mutable Docker image tags fail.

The audited Linux Tectonic asset is
`tectonic-0.16.9-x86_64-unknown-linux-gnu.tar.gz`, size 21,568,986 bytes,
release digest
`sha256:f3c825128095dc3399ea11c08c18035b33050a216930c295c79e8eb11bd21de4`.
The third-party setup Action selects the fixed release but does not verify that
digest. Replacing it with an explicit download-and-hash step remains a SUP-01
hardening item; this residual risk is not hidden by the Action source pin.

## Completion Evidence

| Gate | Result | Evidence |
|---|---|---|
| Exact-head required checks | PASS, 6/6 | PR #40 at `e26c1ab40d77af0d3744c217736477ef2592251c` |
| Ruleset merge | PASS | merge `41be887f21bfb476507d94a089f98c0ef72453c8` |
| Post-merge simulator/paper CI | PASS | [run 29749432294](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29749432294) |
| Post-merge desktop matrix | PASS, Windows/Ubuntu/macOS | [run 29749432322](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29749432322) |
| Dependabot activation | PASS | [run 29749436873](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29749436873) |
| Action SHA policy | PASS | API read-back `sha_pinning_required=true` |
| Workflow inventory | PASS, 12/12 | post-merge full-SHA scan |
| Final settings/evidence snapshot | PASS | [PR comment](https://github.com/ycpiglet/manipulator-control-tutorial/pull/40#issuecomment-5023234280) |

These results close GOV-01. They do not close SAFE-01, COMP-01/02, SUP-01, or
the B2 safe-main gate.

## Residual Risk

Some pinned Action releases still declare an internal Node 20 runtime while
GitHub currently executes them through its Node 24 compatibility path. The
references are immutable and the replacement and post-merge runs passed, so
this does not reopen GOV-01. SUP-01 must select, review, pin, and revalidate
newer Action releases before the compatibility path is removed.

## Rollback and Recovery

- If a pinned Action or fixed Tectonic release breaks a required job, use a PR
  to replace it with a previously reviewed full SHA or another reviewed
  immutable implementation. Do not restore a mutable tag merely to reproduce
  the old workflow.
- If an emergency requires reverting to a historical mutable-tag workflow,
  temporarily disable only `sha_pinning_required`, record the API state before
  and after, merge the revert through the still-active ruleset, then land an
  immutable repair and re-enable SHA enforcement after its green run.
- Actions SHA enforcement and ruleset `19209773` are separate controls. Do not
  disable the ruleset to repair an Action pin.
- Do not disable vulnerability alerts, private reporting, secret scanning, or
  push protection to work around an unrelated workflow failure.
