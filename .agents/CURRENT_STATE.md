# Current State

Updated: 2026-07-22 KST

## Current Objective

Maintain the compact STATE-01 handoff, and record the IA-00 launcher decision
next. The read-only IA inventory recommends freezing existing launcher paths
through v0.1/B4; that recommendation becomes authoritative only when its separate
ADR passes review and merges. After STATE-01, advance only workstreams whose
prerequisites in the execution plan are satisfied.

This document describes the STATE-01 change set; it does not self-certify its
acceptance. Exact-head checks, protected merge, and post-merge checks are the
acceptance authority. IA-00 may merge only after that evidence is complete.

This objective does **not** authorize public beta, signed distribution,
tag/release creation, DOI or preprint publication, real-output cleanup dry-run,
cleanup apply, external contact, participant recruitment, or repository moves.

## Current State

- STATE-01 clean base: protected `main` declaration-record merge
  `9eb8eb19cc488d47954268439834667d452d32eb`.
- Controlled B2 subject: `ae4d40371b9a3fe4d7078822e1fc541a72defe2d`;
  accepted BASE-01 head: `370b10186864e6b9e2bc73978da13671a54628de`.
- B2 `safe-main`: **DECLARED** for development use; G1 **12/12 PASS**.
- B2 declaration record: PR #57, protected-main merge
  `9eb8eb19cc488d47954268439834667d452d32eb`.
- Required approvals remain 0 because the repository has one direct
  collaborator. Owner exact-SHA acceptance closes only the documented B2
  single-maintainer exception; formal independent human approval remains false.
- Supervised Linux classroom/demo and limited technical preview remain
  conditional. General public beta and signed multi-platform production remain
  NO-GO.
- Real learner outputs modified by B2/STATE-01: **no**. Real-root cleanup
  dry-run/apply: **not run / not run**.

## Completed Since Last Snapshot

- BASE-01 PR #56 merged as `ee5b89c4116e789c35c76ec82e61d63fd56e5bc8`
  after exact-head 6/6, owner acceptance, independent read-only review, and
  source/merge tree equivalence; merge-SHA checks also passed 6/6.
- The append-only B2 declaration was independently reviewed and merged in PR
  #57. Exact head `182aa55edbba676e4c3edf0860aa435bb7763d79` and
  merge `9eb8eb19cc488d47954268439834667d452d32eb` each passed the six
  required checks. Their source/merge tree is
  `0c9d562bb040920065075e5c30027e4d5d25db6d`.
- STATE-01 moved the previous 731-line historical handoff into the immutable
  [2026-07-22 archive](archive/CURRENT_STATE_ARCHIVE_20260722_9eb8eb19.md),
  created an append-only [audit finding-status ledger](reviews/20260720_enterprise_readiness_finding_status.md),
  and reduced this file to active state only. The audit source and B2 records
  were not edited.
- Stale user-action and portfolio wording now defers release, DOI, submission,
  external contact, and real-output cleanup to their explicit gates and owner
  authorization.

## Open Decisions

| Decision | Current default until explicitly decided |
|---|---|
| IA-00 launcher disposition | Freeze all current launcher paths through v0.1/B4; no IA-01 |
| Distribution target and supported OS | Supervised/source development only |
| Windows signing and Apple notarization credentials | Do not acquire or use |
| Beginner/accessibility/educator validation cohort | Do not recruit or contact |
| First prerelease version and support channel | Undecided; do not tag or publish |
| Zenodo, preprint, JOSE, or KROS publication | Blocked until the applicable release/publication gates and owner approval |

## Blockers and Risks

- P0-04 distribution compliance/signing remains open. P0-05 is only partial:
  governance and Action pinning are closed for B2, while dependency locking,
  pinned simulator-CI assets, release identity, and related supply-chain work
  remain open.
- SUP-01, LIC-01, PKG-01, E2E-01, OPS-01, EDU-01, HUM-01, REL-01/02,
  MAINT-01, and PUB-01 are not complete. The finding ledger is authoritative
  for exact per-finding scope and evidence.
- The COMP-02 producer lifetime is not protected by one long-lived pinned
  lease. Strict readers revalidate and fail closed; retain this as deferred
  writer-hardening work.
- Actual Windows/macOS hardware, GPU/scaling, assistive technology, novice
  study, educator pilot, signing/notarization, immutable release, rollback, and
  DOI evidence do not exist.
- SAFE-01 passed, but real-output dry-run is currently unauthorized and remains
  a separate owner-participating activity. Apply remains prohibited until the
  owner reviews that exact plan and then gives a second explicit authorization.
- STATE-01 rollback: before any dependent merge, revert the whole focused PR
  through protected main. After downstream records reference it, preserve the
  archive and prior ledger events, append a superseding correction event, fix
  the live pointer, and stop dependent merges until the correction lands.

## Artifacts and Paths

- Authoritative order and gates: [READINESS_EXECUTION_PLAN.md](READINESS_EXECUTION_PLAN.md)
- Read-only audit source: [20260720 enterprise audit](reviews/20260720_enterprise_readiness_audit.md)
- Append-only audit status: [finding-status ledger](reviews/20260720_enterprise_readiness_finding_status.md)
- B2 authority: [declaration](baselines/B2-safe-main-declaration.md) and
  [machine record](baselines/B2-safe-main-declaration.json)
- Historical handoff: [2026-07-22 archive](archive/CURRENT_STATE_ARCHIVE_20260722_9eb8eb19.md)
- External decisions/actions: [USER_ACTIONS.md](USER_ACTIONS.md)
- Manuscript history: [PAPER_VERSION_LOG.md](PAPER_VERSION_LOG.md)

## Next Actions

1. Merge the separate IA-00 no-move ADR after STATE-01. Validate its exact
   launcher inventory and record the recommended v0.1/B4 path freeze.
2. Re-evaluate Draft PRs #37 and #38 under INT-01; never merge either wholesale.
3. Start SUP-01 from the latest clean `origin/main`; LIC-01 follows the merged
   inventory.
4. Run disjoint OPS-01, EDU-01, and MAINT-01 work only from their own clean
   branches. External tests or contacts remain blocked pending owner action.
5. Start PKG-01 only after IA-00 and INT-01 dispositions (and IA-01 only if the
   ADR unexpectedly says GO). Start E2E-01 only after merged SUP-01 and PKG-01.
6. Preserve REL-01/02, HUM-01, and PUB-01 gates. Do not reinterpret B2 or
   STATE-01 as promotion authority.
