# Current State

Updated: 2026-07-23 KST

## Current Objective

Reconcile the accepted STATE-01, IA-00, INT-01, and SUP-01A/B/C evidence, then
finish SUP-01 with a focused vulnerability/license-scan and SBOM-input change.
LIC-01 follows accepted SUP-01. PKG-01 may proceed independently now that
IA-00 and INT-01 are decided; E2E-01 still requires both SUP-01 and PKG-01.

This live handoff records the latest accepted implementation subject
`a216ee8b326008ffeae3e139fad65716c19ed341`. This documentation change does
not self-certify its own acceptance: exact-head checks, protected merge, and
post-merge checks remain authoritative.

This objective does **not** authorize public beta, signed distribution,
tag/release creation, DOI or preprint publication, real-output cleanup dry-run,
cleanup apply, external contact, participant recruitment, credential use, or
repository moves.

## Current State

- Accepted protected `main` subject: SUP-01C merge
  `a216ee8b326008ffeae3e139fad65716c19ed341` (PR #64).
- Controlled B2 subject: `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`;
  accepted BASE-01 head: `370b10186864e6b9e2bc73978da13671a54628de`.
- B2 `safe-main`: **DECLARED** for development use; G1 **12/12 PASS**.
- STATE-01: **PASS** (PR #58). IA-00: **FREEZE accepted** (PR #59), so
  IA-01 is not required through v0.1/B4 unless a superseding ADR says GO.
- INT-01 dispositions: **complete**. Draft #37 was superseded by the bounded
  package-only PR #60; Draft #38 was closed without forward-port because native
  Windows glyph evidence was absent and the recovered fonts added about
  24.5 MiB. Neither draft was merged wholesale.
- The IA-required in-place `run_mclab.cmd` repair is accepted in PR #61.
- SUP-01 is **partial**: Action/Node24 control (PR #62), universal hashed Python
  locks (PR #63), and the pinned Panda runtime closure (PR #64) are accepted.
  Vulnerability/license scans, Linux system-package inventory/reproducibility,
  and SBOM inputs remain.
- Required approvals remain 0 because the repository has one direct
  collaborator. Formal independent human approval remains false.
- Supervised/source development remains the only accepted distribution scope.
  B3 technical preview, public beta, and signed production remain NO-GO.
- Real learner outputs accessed or modified by STATE/IA/INT/SUP work: **no**.
  Real-root cleanup dry-run/apply: **not run / not run**.

## Completed Since Last Snapshot

- STATE-01 PR #58: exact head `ba74114126ff875be2f11810c5a0064f50b49000`,
  merge `6c06de439fbee22ee2591dc47846194484cad517`; exact-head and
  post-merge required checks **6/6 PASS**.
- IA-00 PR #59: exact head `d7d3c168308c753279c20c4833e29cdd7ef94269`,
  merge `23689849b31302fab5a370a463f8054f438d0057`; checks **6/6** at
  both SHAs. The exact 23 root launcher paths are frozen through v0.1/B4.
- INT/launcher PRs #60/#61 merged as `7b8c49d8b6aebc5cf8458d313b90253dcc09d98b`
  and `bc156c2628145fbfa7313de2eaea2323f44dc551`; both passed exact-head
  and post-merge checks **6/6**.
- SUP-01A PR #62 merged as `53f9e84e240f70b0d4223fbcd7cd71fe81cc8af2`;
  SUP-01B PR #63 as `941925263e478a68678ccaf21cade22cddddc1ff`;
  SUP-01C PR #64 as `a216ee8b326008ffeae3e139fad65716c19ed341`.
  Every exact head and merge SHA passed the six required checks.
- Current-main #64 evidence: CI `29927483939`, desktop `29927484655`,
  required checks **6/6 PASS**; full simulator `1003 passed, 12 skipped,
  2569 subtests`, coverage `82.39%`.
- Open PRs, tags, and releases: **0 / 0 / 0** at this snapshot.

## Open Decisions

| Decision | Current default until explicitly decided |
|---|---|
| Distribution target and supported OS | Supervised/source development only |
| Windows signing and Apple notarization credentials | Do not acquire or use |
| Beginner/accessibility/educator validation cohort | Do not recruit or contact |
| First prerelease version and support channel | Undecided; do not tag or publish |
| External license review | Do not contact; prepare repository inventory first |
| Zenodo, preprint, JOSE, or KROS publication | Blocked until release/publication gates and owner approval |

## Blockers and Risks

- SUP-01 scan/SBOM/system-package work is incomplete; LIC-01 cannot claim a
  complete distribution inventory until that evidence is accepted.
- PKG-01 still needs aligned one-folder/archive metrics, cold-start samples,
  and actual packaged QML evidence. PRs #60/#61 are prerequisites, not PKG-01.
- E2E-01, OPS-01, EDU-01, and MAINT-01 remain open. REL-01/02, HUM-01,
  and PUB-01 remain gated by repository prerequisites and/or external evidence.
- GitHub reports no Dependabot alerts, but no code-scanning analysis exists;
  absence of a CodeQL result is not evidence of zero source findings.
- SUP-01C retains its documented safe-main-only filesystem and UI-refresh
  residuals. The COMP-02 producer still lacks one long-lived pinned lease.
- Actual target hardware, GPU/scaling, assistive technology, novice study,
  educator pilot, signing/notarization, immutable release, rollback, and DOI
  evidence do not exist.
- SAFE-01 passed, but real-output dry-run remains unauthorized. Apply remains
  prohibited until the owner reviews one exact plan and separately approves it.

## Artifacts and Paths

- Authoritative order and gates: [READINESS_EXECUTION_PLAN.md](READINESS_EXECUTION_PLAN.md)
- Read-only audit source: [20260720 enterprise audit](reviews/20260720_enterprise_readiness_audit.md)
- Append-only audit status: [finding-status ledger](reviews/20260720_enterprise_readiness_finding_status.md)
- IA decision: [IA-00 launcher freeze](decisions/IA-00-launcher-paths.md)
- B2 authority: [declaration](baselines/B2-safe-main-declaration.md) and
  [machine record](baselines/B2-safe-main-declaration.json)
- Historical handoff: [2026-07-22 archive](archive/CURRENT_STATE_ARCHIVE_20260722_9eb8eb19.md)
- External decisions/actions: [USER_ACTIONS.md](USER_ACTIONS.md)

## Next Actions

1. Merge this focused state/ledger reconciliation after exact-head review and
   verify all six post-merge checks.
2. From that clean main, complete SUP-01 scan, Linux package, and SBOM-input
   evidence; then append the aggregate SUP-01 status without rewriting B2.
3. Start LIC-01 from the accepted SUP inventory. Complete PKG-01 from its own
   clean branch; E2E-01 follows accepted SUP-01 and PKG-01.
4. Run repository-only OPS-01, EDU-01, and small MAINT-01 work in disjoint
   branches. Do not perform external tests, contact, recruitment, or signing.
5. Preserve REL-01/02, HUM-01, PUB-01, and real-output cleanup authorization
   gates. Do not reinterpret internal preparation as promotion authority.
