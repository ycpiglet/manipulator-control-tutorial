# Current State

Updated: 2026-07-23 KST

## Current Objective

Reconcile the accepted SUP-01 aggregate evidence, then start LIC-01 from that
accepted inventory. PKG-01 may proceed in a disjoint clean branch; E2E-01 waits
for accepted PKG-01 and must run on the exact main containing both aggregates.

This live handoff records the latest accepted implementation subject
`6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1` (PR #66). This documentation
change does not self-certify its own acceptance: exact-head checks, protected
merge, and post-merge checks remain authoritative.

This objective does **not** authorize public beta, signed distribution,
tag/release creation, DOI or preprint publication, real-output cleanup dry-run,
cleanup apply, external contact, participant recruitment, credential use, or
repository moves.

## Current State

- Accepted protected `main` subject: SUP-01 aggregate merge
  `6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1` (PR #66).
- PR #66 source head/tree:
  `387dd331a408d46beffb80483916401bf2e08c73` /
  `ac5d9ba1720911357a02c665787ec50ed50eaf5f`; the accepted merge has the
  same tree, so source/merge tree equivalence is **PASS**.
- Controlled B2 subject: `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`;
  accepted BASE-01 head: `370b10186864e6b9e2bc73978da13671a54628de`.
- B2 `safe-main`: **DECLARED** for development use; G1 **12/12 PASS**.
- STATE-01, IA-00 FREEZE, INT-01 disposition, and launcher in-place repair are
  accepted. IA-01 remains unnecessary through v0.1/B4 unless a superseding ADR
  changes FREEZE to GO.
- SUP-01 is **accepted for its repository supply-chain input-gate scope**:
  reviewed Action/Node24 control, universal hashed Python locks, pinned Panda
  runtime assets, fail-closed vulnerability/license inventory, pinned Ubuntu
  direct-package evidence, and deterministic SBOM inputs.
- That acceptance is deliberately bounded. License evidence remains
  `inventory-complete` / `pending-lic-01`; generated SBOM records are inputs,
  not final per-OS SBOM or release provenance; the Ubuntu manifest freezes 22
  direct packages, not the hosted base image or all native transitive inputs.
- Required approvals remain 0 because the repository has one direct
  collaborator. Formal independent human approval remains false.
- Supervised/source development remains the only accepted distribution scope.
  B3 technical preview, public beta, and signed production remain NO-GO.
- Real learner outputs accessed or modified by STATE/IA/INT/SUP work: **no**.
  Real-root cleanup dry-run/apply: **not run / not run**.
- Local host APT state changed by SUP work: **no**. Package installation and
  verification ran only in the authorized GitHub Ubuntu job.

## Completed Since Last Snapshot

- STATE-01 PR #58, IA-00 PR #59, INT/launcher PRs #60/#61, and SUP-01A/B/C
  PRs #62–#64 each passed exact-head and post-merge required checks **6/6**.
- SUP-01D PR #66 exact head
  `387dd331a408d46beffb80483916401bf2e08c73`, merge
  `6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1`; source/merge trees are
  equivalent.
- PR #66 exact-head CI `29949569945` and desktop `29949569735`, plus
  post-merge CI `29950993214` and desktop `29950992873`, passed the six
  required checks at both SHAs. Both simulator runs reported 1,186 passed,
  12 skipped, 2,648 subtests, and 82.39% coverage.
- Exact SUP evidence covers 8 lock profiles, 213 requirements, 4,465 hashes,
  12 target environments, and 78 scanned dependencies with 0 vulnerability
  findings and 0 waivers. Hosted package-profile license inventories contain
  44 Linux, 47 Windows, and 45 macOS packages and remain `pending-lic-01`.
- The post-merge Ubuntu job verified the official `20260723T000000Z` snapshot,
  22 direct packages, and the pinned Noble keyring. Artifact
  `mclab-supply-chain-Linux` has ID `8542125543` and expires
  `2026-08-05T19:27:49Z`.
- Deterministic exact-head `387dd331a408d46beffb80483916401bf2e08c73`
  SBOM inputs were byte-identical with SHA-256
  `5035ffc306cdad50e89829076288fdfc2b62097b0071a3bce2788e59a24bcc5c`.
- Open PRs, tags, and releases at the accepted SUP snapshot: **0 / 0 / 0**.

## Open Decisions

| Decision | Current default until explicitly decided |
|---|---|
| Distribution target and supported OS | Supervised/source development only |
| Windows signing and Apple notarization credentials | Do not acquire or use |
| Beginner/accessibility/educator validation cohort | Do not recruit or contact |
| First prerelease version and support channel | Undecided; do not tag or publish |
| External license review | Do not contact; complete repository LIC-01 first |
| Zenodo, preprint, JOSE, or KROS publication | Blocked until release/publication gates and owner approval |

## Blockers and Risks

- LIC-01 is next. Current inventory deliberately reports missing license,
  source, text, and NOTICE metadata; Qt/PySide LGPL obligations and
  distribution notices are not approved.
- PKG-01 still needs aligned one-folder/archive metrics, cold-start samples,
  and actual packaged QML evidence.
- E2E-01 must run after accepted PKG-01 on the integrated exact main.
- Final per-OS SBOM/provenance, hosted base-image/native-transitive inventory,
  immutable release evidence, and long-lived retention remain absent.
- OPS-01, EDU-01, and MAINT-01 remain open. REL-01/02, HUM-01, and PUB-01
  remain gated by repository prerequisites and/or external evidence.
- GitHub reports no Dependabot alerts, but no code-scanning analysis exists;
  absence of a CodeQL result is not evidence of zero source findings.
- SUP evidence artifacts have short retention and are development evidence,
  not release provenance. The host OS, APT/dpkg binaries, system CA store, and
  concurrent privileged-root trust remain bounded base-image assumptions.
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
- Supply-chain schema and waiver policy:
  [SBOM-input schema](supply_chain/sbom-inputs.schema.json) and
  [waiver registry](supply_chain/vulnerability-waivers.json)
- Ubuntu direct-package manifest:
  [ubuntu-24.04-amd64.json](../requirements/system/ubuntu-24.04-amd64.json)
- Evidence boundaries: [installation guide](../docs/installation.md)
- IA decision: [IA-00 launcher freeze](decisions/IA-00-launcher-paths.md)
- B2 authority: [declaration](baselines/B2-safe-main-declaration.md) and
  [machine record](baselines/B2-safe-main-declaration.json)
- Historical handoff: [2026-07-22 archive](archive/CURRENT_STATE_ARCHIVE_20260722_9eb8eb19.md)
- External decisions/actions: [USER_ACTIONS.md](USER_ACTIONS.md)

## Next Actions

1. Merge this focused state/ledger reconciliation after exact-head review and
   verify all six post-merge checks.
2. From that accepted clean main, perform LIC-01 without claiming legal approval
   before component text/source/notice and Qt/PySide obligations are closed.
3. Complete PKG-01 in its own clean branch; then run E2E-01 on the exact main
   containing accepted SUP-01 and PKG-01.
4. Run repository-only OPS-01, EDU-01, and small MAINT-01 work in disjoint
   branches. Do not perform external tests, contact, recruitment, or signing.
5. Preserve REL-01/02, HUM-01, PUB-01, and real-output cleanup authorization
   gates. Do not reinterpret SUP input evidence as promotion authority.
