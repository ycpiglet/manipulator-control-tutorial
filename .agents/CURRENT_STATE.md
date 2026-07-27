# Current State

Updated: 2026-07-27 KST

## Current Objective

Accept the bounded GOV-03 subject-refresh extension through an ordinary
protected PR, then use the already accepted fail-closed protected-main harness
to integrate the fixed remaining queue in strict order: PR #75 OPS-01A, PR #72
EDU-01A, PR #73 PKG-01B, PR #70 E2E-01, and PR #76 MAINT-01A. The harness
cannot accept or amend GOV-03 or its authority documents.

Each delegated transaction remains bound to exact base/head SHAs, reviewed,
locked, and refreshable path sets, locked content/status digests, one
generation-1 canonical independent-agent review receipt, immutable owner
certificate and attestation, live ruleset/application/six-check verification,
zero unresolved threads, synthetic merge parent/tree equivalence, an
exact-head guarded merge, and post-merge required checks 6/6. Unattested
refresh, generation 2, locked content/status, SHA, scope, policy, review, or
evidence drift stops the transaction.

This objective does **not** authorize promotion or public beta; package or
signed distribution; tag/release creation; signing, notarization, or
signing/release credential acquisition or use; DOI, preprint, or publication;
external contact or recruitment; actual output enumeration, cleanup
dry-run/apply, quarantine, or restore;
artifact/package download or content access; ruleset/security-setting changes
or bypass; or repository/layout moves.

## Current State

- Accepted protected `main` subject: LIC-01B merge
  `9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88` (PR #74).
- GOV-02 protected-integration harness is accepted on protected `main` at
  merge `957d2edf219db7cbfd29789b4ea4348de04b33e6` (PR #77). Its fixed queue
  remains #75 -> #72 -> #73 -> #70 -> #76, serialized without skips.
- PR #74 source head/tree:
  `6cd191f0b87bb582bfde4764234a570a7f601da4` /
  `e5625718c0bcd1030bba9ea938a438d927d4033e`; the accepted merge has the
  same tree, so source/merge tree equivalence is **PASS**.
- PR #74 exact-head CI/desktop runs `30203394749` / `30203394746`, and
  post-merge CI/desktop runs `30204142834` / `30204142848`, passed required
  checks **6/6** at both SHAs.
- LIC-01B is accepted only for its bounded reviewed notice-corpus and
  safe-main development scope. Aggregate LIC-01, G3, legal approval, and
  public or package distribution remain open.
- The 2026-07-26 fixed-queue standing delegation is active through accepted
  GOV-02. The owner's 2026-07-27 extension authorizes one generation of
  source-only reconciliation on exact predeclared refreshable paths without
  another human prompt, but activates only after the GOV-03 policy, script,
  tests, current-state record, and execution-plan overlay are accepted through
  an ordinary protected PR. `self_amendment_authority` remains false.
- PR #69 source head/tree:
  `aeabf3a852774fc198d56426f4cb507ada498f1d` /
  `2d897fa81506887df863106f118ddeb660880cfd`; the accepted merge has the
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
- LIC-01A is **accepted only as a deterministic pending inventory contract**:
  49 package-lock candidates, 12 target cells, and three hosted observations.
  Legal approval, notice completion, Qt/PySide LGPL disposition, native/base
  closure, and public distribution remain false or pending.
- PKG-01A is **accepted only for unsigned-development package identity and
  size**. All three native jobs verified package self-test, `doctor`, inventory,
  one-folder size, and archive size. Aggregate PKG-01 still lacks an accepted
  20-sample packaged QML startup/cold-launch gate.
- Draft PR #70 exact head
  `a5ed0e8b4fbeda9249cd77efb07a1db7ee68a193` has six green checks and bounded
  Windows/Linux/macOS G2 candidate JSON. It remains draft and is not accepted
  E2E/G2/B3 evidence because the accepted-PKG prerequisite and merge decision
  are unresolved.
- Required approvals remain 0 because the repository has one direct
  collaborator. Formal independent human approval remains false; the owner
  explicitly accepted that residual for the bounded standing delegation, while
  independent read-only agent attestation remains mandatory.
- Supervised/source development remains the only accepted distribution scope.
  B3 technical preview, public beta, and signed production remain NO-GO.
- Real learner outputs accessed or modified by accepted LIC/PKG work: **no**.
  Real-root cleanup dry-run/apply: **not run / not run**.
- Local host APT state changed by SUP work: **no**. Package installation and
  verification ran only in the authorized GitHub Ubuntu job.

## Completed Since Last Snapshot

- PR #77 accepted the fail-closed GOV-02 protected-integration harness on
  protected `main` at merge
  `957d2edf219db7cbfd29789b4ea4348de04b33e6`. It grants only the fixed serial
  queue and cannot amend its own policy, script, tests, or authority documents.
- PR #74 accepted LIC-01B exact head
  `6cd191f0b87bb582bfde4764234a570a7f601da4`, merge
  `9ba5e8e7bfae9ea46e0f9217c07861a4f188ce88`, and common tree
  `e5625718c0bcd1030bba9ea938a438d927d4033e`.
- PR #74 exact-head CI `30203394749` and desktop `30203394746`, plus
  post-merge CI `30204142834` and desktop `30204142848`, passed required
  checks **6/6** at both SHAs. This closes only the bounded reviewed notice
  corpus; it does not close aggregate LIC-01, G3, legal, or distribution
  gates.
- PR #67 reconciled the accepted SUP-01 state. PR #68 accepted LIC-01A exact
  head `c707999a6f0299a9cc8bbf97f1f2ab22217b2011`, merge
  `0ed0efbf75ea2f66a7d3f761734c485a5265b632`, and common tree
  `aee1ee7ddb0840fd6517c0fefa40d5085788d7d2`.
- PR #68 exact-head CI `29961923132` and desktop `29961923217`, plus
  post-merge CI `29963046292` and desktop `29963046307`, passed required
  checks **6/6** at both SHAs. The contract remains `pending-lic-01`; only
  3/12 target cells have accepted short-lived observations.
- PR #69 accepted PKG-01A exact head
  `aeabf3a852774fc198d56426f4cb507ada498f1d`, merge
  `96702b09d7e2b0e3b381b86c5e6e51f95682d346`, and common tree
  `2d897fa81506887df863106f118ddeb660880cfd`.
- PR #69 exact-head CI `29968981476` and desktop `29968981517`, plus
  post-merge CI `29969976213` and desktop `29969976169`, passed required
  checks **6/6** at both SHAs.
- Exact-head package size measurements were below both unchanged limits:
  Windows `259,148,501 / 93,923,818` bytes, Ubuntu
  `342,402,649 / 123,143,362` bytes, and macOS
  `192,875,997 / 65,943,576` bytes for one-folder/archive respectively.
- Pre-existing remote state before opening this reconciliation candidate: one
  open Draft PR (#70), zero tags, and zero releases. The reconciliation
  candidate itself must remain visible as an additional Draft PR until it is
  separately reviewed and accepted.

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

- LIC-01B's bounded reviewed notice corpus is accepted. Aggregate LIC-01 still
  lacks legal approval and distribution closure; Qt/PySide LGPL and G3
  obligations remain open and cannot be inferred from the safe-main result.
- PKG-01A closed deterministic identity and both size thresholds, but aggregate
  PKG-01 still needs accepted 20-sample cold-start and actual packaged QML
  evidence on each supported OS.
- E2E-01 must be accepted only after aggregate PKG-01, on an exact integrated
  commit. Draft #70 cannot satisfy its own prerequisite retroactively.
- Draft #70 generated exact-head candidate evidence without touching real
  learner data in CI. During earlier local diagnosis, an empty temporary-path
  fallback caused one disclosed read-only enumeration of repository `outputs/`;
  it returned zero records and made no write, cleanup plan, deletion, or apply.
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
- LIC-01A pending inventory:
  [license-inventory.json](supply_chain/license-inventory.json)
- Unsigned package contract and evidence boundary:
  [installation guide](../docs/installation.md)
- Ubuntu direct-package manifest:
  [ubuntu-24.04-amd64.json](../requirements/system/ubuntu-24.04-amd64.json)
- IA decision: [IA-00 launcher freeze](decisions/IA-00-launcher-paths.md)
- Conditional standing-delegation authority and transaction implementation:
  [protected-main policy](integration/protected-main-v1.json) and
  [integration harness](../scripts/protected_integration.py)
- B2 authority: [declaration](baselines/B2-safe-main-declaration.md) and
  [machine record](baselines/B2-safe-main-declaration.json)
- Historical handoff: [2026-07-22 archive](archive/CURRENT_STATE_ARCHIVE_20260722_9eb8eb19.md)
- External decisions/actions: [USER_ACTIONS.md](USER_ACTIONS.md)

## Next Actions

1. Accept the 2026-07-27 GOV-03 generation-1 subject-refresh policy, script,
   tests, current state, and execution-plan overlay through an ordinary
   protected PR with independent read-only review, exact-head checks 6/6,
   exact-head guarded merge, and post-merge checks 6/6. The harness may not
   perform this step itself.
2. Once GOV-03 is active, process only #75 OPS-01A -> #72 EDU-01A -> #73
   PKG-01B -> #70 E2E-01 -> #76 MAINT-01A. Preserve every locked path/digest;
   require an exact canonical receipt and owner certificate for any bounded
   refresh; stop on any envelope, generation, digest, path, SHA, ruleset,
   check, thread, review, or synthetic-tree mismatch.
3. Preserve aggregate LIC-01/G3/legal/distribution, REL-01/02, HUM-01, PUB-01,
   actual-output/cleanup, artifact/package content, external-contact,
   signing/release credential, ruleset-setting, and repository-layout gates.
   The standing delegation does not authorize them.
