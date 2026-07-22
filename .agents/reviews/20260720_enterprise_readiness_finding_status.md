# Enterprise Readiness Finding-Status Ledger

- Ledger status: **active, append-only**
- Initialized: `2026-07-22T12:46:54+09:00` / `2026-07-22T03:46:54Z`
- Evaluated pre-change subject: `origin/main@9eb8eb19cc488d47954268439834667d452d32eb`
- Evaluated tree: `0c9d562bb040920065075e5c30027e4d5d25db6d`
- Read-only source: [`20260720_enterprise_readiness_audit.md`](20260720_enterprise_readiness_audit.md)
- Audit SHA-256: `fffc946c3597ebc3255938fcee656a29117a9cd31db1f75d8420cb0261e349ec`

This file records later status without rewriting the audit. The audit remains
authoritative for finding wording and scope. P1/P2 bullet IDs below are
ledger-local identifiers assigned in source order because the audit gives those
bullets only a shared priority heading.

## Append-Only Rules

1. Finding IDs and initial events in this file are immutable after the STATE-01
   merge. Never edit the audit to make a finding look closed.
2. A later change appends a new event with a new event ID and a `supersedes`
   reference. The latest valid event for a finding is its current status.
3. `closed` means the entire audit finding is satisfied. `closed_for_scope`
   means only the named gate/scope is satisfied; it cannot promote a broader
   release. `partial` means components remain open.
4. Status values are `open`, `partial`, `closed_for_scope`, `closed`,
   `external_blocked`, and `deferred_residual`. `open` means unmet work can
   proceed under its prerequisites. `external_blocked` means repository work
   alone cannot produce the required evidence. `deferred_residual` is a
   documented risk carried only under the event's explicitly named scope; it
   is not general acceptance, closure, or promotion authority.
5. Evidence states are `confirmed` (cited evidence supports the status),
   `pending` (planned or change-local evidence is not yet accepted), `not_run`
   (the named validation has not executed), and `external` (evidence requires
   an actor/resource outside the repository). `confirmed` may confirm either a
   pass or an unresolved gap.
6. Plans and future commands are not evidence. Real learner-output dry-run/apply,
   external contact, public beta, signed distribution, tag/release creation,
   DOI publication, signing, human testing, and repository moves require their
   own authorization and evidence.
7. All initial events inherit the initialized timestamp and evaluated SHA above.
   Every appended event must record its own UTC timestamp, exact evaluated
   commit, status, evidence state, evidence links, remaining gate, and the event
   it supersedes. Use the template below without deleting an earlier row.

Future event template:

```text
event_id: EVENT-ID
recorded_at_utc: RECORDED-AT-UTC
evaluated_commit: EXACT-EVALUATED-SHA
finding_id: FINDING-ID
status: STATUS
evidence_state: EVIDENCE-STATE
evidence_and_scope: EVIDENCE-LINKS-AND-CLOSURE-SCOPE
remaining_gate: REMAINING-WORK-OR-BLOCKED-PROMOTION
supersedes: PRIOR-EVENT-ID
```

## Immutable Finding Registry

### P0 audit findings

| ID | Audit finding | Source |
|---|---|---|
| P0-01 | Unsafe CLI cleanup | [P0-01](20260720_enterprise_readiness_audit.md#p0-01--unsafe-cli-cleanup) |
| P0-02 | Desktop course-completion evidence mismatch | [P0-02](20260720_enterprise_readiness_audit.md#p0-02--desktop-course-completion-evidence-mismatch) |
| P0-03 | No clean release-candidate baseline | [P0-03](20260720_enterprise_readiness_audit.md#p0-03--no-clean-release-candidate-baseline) |
| P0-04 | Distribution compliance and signing are incomplete | [P0-04](20260720_enterprise_readiness_audit.md#p0-04--distribution-compliance-and-signing-are-incomplete) |
| P0-05 | Repository and supply-chain controls are incomplete | [P0-05](20260720_enterprise_readiness_audit.md#p0-05--repository-and-supply-chain-controls-are-incomplete) |

### P1 audit bullets

| ID | Audit bullet, in source order |
|---|---|
| P1-01 | Packaged end-to-end flows on each target OS |
| P1-02 | Actual Windows/macOS hardware, GPU, scaling, and restart checks |
| P1-03 | Human assistive-technology, focus, low-vision, and color-vision checks |
| P1-04 | Beginner think-aloud/SUS study with at least six participants |
| P1-05 | Runtime/build dependency lock plus vulnerability and license scans |
| P1-06 | Branch protection, required checks/review, CODEOWNERS, SECURITY, and SHA-pinned Actions |
| P1-07 | Reconcile the audited 300 MB compressed target and 400 MB uncompressed gate and stale text |

### P2 audit bullets

| ID | Audit bullet, in source order |
|---|---|
| P2-01 | Incremental mypy gate from the audited 225-error/20-file baseline |
| P2-02 | Split oversized reporting and learner-menu modules |
| P2-03 | Resolve Pydantic specification versus manual YAML validation |
| P2-04 | Complete Korean report localization and correct HTML language metadata |
| P2-05 | Expand educator guide, timing, rubric, accessibility fallback, and submission verification |
| P2-06 | Add learner-note and shared-PC local-data/privacy guidance |
| P2-07 | Refresh publication claims/counts/date and release before Zenodo DOI |

All P1 rows map to the seven bullets under [Public-beta readiness](20260720_enterprise_readiness_audit.md#p1--public-beta-readiness);
all P2 rows map to the seven bullets under [Maintainability, teaching operations, and publication](20260720_enterprise_readiness_audit.md#p2--maintainability-teaching-operations-and-publication).

## Initial Status Events

| Event | Finding | Status | Evidence state | Scope/evidence | Remaining work or blocked promotion | Supersedes |
|---|---|---|---|---|---|---|
| FS-20260722-001 | P0-01 | closed_for_scope | confirmed | SAFE-01 and B2/G1; [SAFE record](../baselines/SAFE-01-cleanup.md), [B2 declaration](../baselines/B2-safe-main-declaration.md) | E2E packaged cleanup remains; real-root dry-run not run or authorized, and apply unauthorized | — |
| FS-20260722-002 | P0-02 | closed_for_scope | confirmed | COMP-01/02 and B2/G1; [contract](../baselines/COMP-01-completion-contract.md), [consumers](../baselines/COMP-02-completion-consumers.md) | Preserve parity in packaged E2E and future schemas; no artifact rewrite | — |
| FS-20260722-003 | P0-03 | closed_for_scope | confirmed | Clean B2 safe-main development baseline only; [declaration](../baselines/B2-safe-main-declaration.md) | B3 technical-preview RC requires downstream SUP/PKG/E2E evidence | — |
| FS-20260722-004 | P0-04 | open | confirmed | [B2 declaration](../baselines/B2-safe-main-declaration.md) records unsigned distribution, no immutable release, no complete notices/SBOM/provenance/rollback | Blocks B4/B5; SUP, LIC, PKG, E2E, REL-01, REL-02 | — |
| FS-20260722-005 | P0-05 | partial | confirmed | [GOV-01](../baselines/GOV-01-governance.md) closed repository controls for B2; supply-chain and release components remain below | Blocks B3 transitively through SUP→E2E and B4 through SUP/REL | — |
| FS-20260722-006 | P1-01 | open | not_run | Current CI tests unsigned development folders, not independent install-to-cleanup flows | E2E-01 after merged SUP-01 and PKG-01 | — |
| FS-20260722-007 | P1-02 | external_blocked | external | No actual supported-device matrix evidence | HUM-01; owner must supply/authorize target hardware | — |
| FS-20260722-008 | P1-03 | external_blocked | external | Automated UI checks are not human NVDA/VoiceOver/Orca evidence | HUM-01; assistive technology and human reviewers required | — |
| FS-20260722-009 | P1-04 | external_blocked | external | No six-participant beginner study evidence | EDU-01 may prepare protocol; recruitment/execution needs owner authorization | — |
| FS-20260722-010 | P1-05 | open | confirmed | [B2 declaration](../baselines/B2-safe-main-declaration.md) records no hash-complete runtime/build lock or merged scan gate | SUP-01 then LIC-01 | — |
| FS-20260722-011 | P1-06 | closed_for_scope | confirmed | [GOV-01](../baselines/GOV-01-governance.md) and [B2/G1](../baselines/B2-safe-main-declaration.md) only; one direct collaborator, approvals 0, owner exception accepted | Formal independent human approval remains false; release review gate is not waived | — |
| FS-20260722-012 | P1-07 | open | pending | Post-audit plan normalizes the two distinct thresholds to archive <=300 MiB and one-folder <=400 MiB, but package measurement/text gate is not complete | PKG-01 | — |
| FS-20260722-013 | P2-01 | open | not_run | Audit measured 225 errors/20 files; not remeasured for this subject | MAINT-01 must establish a current incremental no-new-debt gate | — |
| FS-20260722-014 | P2-02 | open | pending | No STATE-01 module refactor; audited large-module debt retained | MAINT-01 in small tested PRs | — |
| FS-20260722-015 | P2-03 | open | pending | No config-contract decision has merged | MAINT-01 ADR/contract work | — |
| FS-20260722-016 | P2-04 | open | pending | STATE-01 does not claim complete Korean reports or corrected language metadata | Localization work and explicit validation remain | — |
| FS-20260722-017 | P2-05 | open | pending | Existing teaching docs do not satisfy the full audited educator package | EDU-01; human educator execution remains external | — |
| FS-20260722-018 | P2-06 | open | pending | No complete local-data/shared-PC policy and restore/deletion proof | OPS-01 | — |
| FS-20260722-019 | P2-07 | open | confirmed | This STATE-01 change gates stale immediate-publication wording; that edit is not evidence on the evaluated pre-change subject. The [B2 declaration](../baselines/B2-safe-main-declaration.md) confirms release identity and DOI evidence remain absent; JOSE claims and venue evidence also remain open. | REL-01 then PUB-01; external publication requires owner approval | — |

## P0-05 Component Events

| Event | Component | Status | Evidence state | Evidence / next gate | Supersedes |
|---|---|---|---|---|---|
| FS-20260722-005-A | P0-05 repository protection/ruleset | closed_for_scope | confirmed | [GOV-01](../baselines/GOV-01-governance.md)/B2; active ruleset `19209773` | — |
| FS-20260722-005-B | P0-05 vulnerability/security repository settings | closed_for_scope | confirmed | [GOV-01](../baselines/GOV-01-governance.md)/B2 settings snapshot | — |
| FS-20260722-005-C | P0-05 dependency lock/constraints | open | confirmed | [B2 declaration](../baselines/B2-safe-main-declaration.md) records the gap; next gate SUP-01 | — |
| FS-20260722-005-D | P0-05 immutable Action refs | closed_for_scope | confirmed | [GOV-01](../baselines/GOV-01-governance.md)/B2; Node-runtime warning remains SUP-01 residual | — |
| FS-20260722-005-E | P0-05 pinned simulator-CI Menagerie source | open | confirmed | [B2 declaration](../baselines/B2-safe-main-declaration.md) records the gap; next gate SUP-01 | — |
| FS-20260722-005-F | P0-05 immutable tag/release | open | confirmed | [B2 declaration](../baselines/B2-safe-main-declaration.md) records zero tags/releases; REL-01 follows G3 prerequisites and no tag/release is authorized now | — |

## Post-Audit Residual Events

| Event | Finding | Status | Evidence state | Evidence / next work | Supersedes |
|---|---|---|---|---|---|
| FS-20260722-020 | RES-P2-COMP-PRODUCER-PIN-01 | deferred_residual | confirmed | The [COMP-02 record](../baselines/COMP-02-completion-consumers.md) and [B2 declaration](../baselines/B2-safe-main-declaration.md) record that producer writes do not hold one long-lived pinned lease; strict readers revalidate and fail closed. This risk is carried only for B2/G1 and should be addressed in a focused writer-hardening PR. | — |

## Promotion Summary

- B2/G1 is declared only for the controlled safe-main development baseline.
- B3 is blocked on every G2 metric and its prerequisites, including the IA/INT
  decisions, SUP-01, PKG-01, and E2E-01.
- B4 is blocked on every G3 metric, including SUP-01, LIC-01, OPS-01, release identity,
  notices, scans, SBOM/provenance, and explicit owner release authority.
- B5 is additionally blocked on every G4 metric: signatures, automated and
  real-assistive-tech accessibility, target hardware/scaling/restarts, novice
  study and learning comprehension, educator adoption, rollback, and
  retention/restore.
- B6/DOI is blocked on every G5 metric: immutable archive integrity, citation
  metadata, tagged-release publication claims, privacy scan, and
  publication-owner action. JOSE remains external-blocked pending dated venue
  verification.
- Real-output cleanup dry-run is not authorized by this ledger. Cleanup apply
  remains prohibited until an owner reviews one exact dry-run plan and then
  separately and explicitly authorizes that same plan.

## Accepted-State Reconciliation Events — 2026-07-23

These events append the accepted PR #58–#64 evidence evaluated at protected
`main@a216ee8b326008ffeae3e139fad65716c19ed341`. They do not rewrite the
initial registry, initial events, audit source, B2 records, or historical
promotion summary above.

| Event | Recorded at UTC | Evaluated commit | Finding/component | Status | Evidence state | Evidence and scope | Remaining gate | Supersedes |
|---|---|---|---|---|---|---|---|---|
| FS-20260723-021 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P0-05 | partial | confirmed | [PR #62](https://github.com/ycpiglet/manipulator-control-tutorial/pull/62), [PR #63](https://github.com/ycpiglet/manipulator-control-tutorial/pull/63), and [PR #64](https://github.com/ycpiglet/manipulator-control-tutorial/pull/64) accepted Node24 Action control, universal hashed Python locks, and pinned Panda runtime assets; each exact head and merge passed required checks 6/6; [live state](../CURRENT_STATE.md) | Vulnerability/license scans, Linux package evidence, SBOM/provenance, and immutable release remain | FS-20260722-005 |
| FS-20260723-022 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P1-05 | partial | confirmed | [PR #63](https://github.com/ycpiglet/manipulator-control-tutorial/pull/63) fixed runtime/build Python versions and hashes; [PR #64](https://github.com/ycpiglet/manipulator-control-tutorial/pull/64) fixed Panda runtime bytes; [current-main CI](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29927483939) and [desktop](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29927484655) passed 6/6 | SUP-01 scan/SBOM/system-package work, then LIC-01 distribution inventory | FS-20260722-010 |
| FS-20260723-023 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P0-05 dependency lock/constraints | closed_for_scope | confirmed | [PR #63](https://github.com/ycpiglet/manipulator-control-tutorial/pull/63) exact head `f754a09aad3ab26a411b5a9d3caaf5cbe565398e`, merge `941925263e478a68678ccaf21cade22cddddc1ff`; exact-head and post-merge checks 6/6 | Preserve lock byte reproducibility; non-Python/system and release inputs remain separate | FS-20260722-005-C |
| FS-20260723-024 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P0-05 pinned simulator-CI Menagerie source | closed_for_scope | confirmed | [PR #64](https://github.com/ycpiglet/manipulator-control-tutorial/pull/64) exact head `316d24973e040c2382efc470c446fa17b6c58fe8`, merge `a216ee8b326008ffeae3e139fad65716c19ed341`; 72 files / 34,333,936 bytes verified and exact-head/post-merge checks 6/6 | Preserve asset manifest/policy; final release SBOM/provenance and notices remain | FS-20260722-005-E |
| FS-20260723-025 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P0-05 immutable Action refs | closed_for_scope | confirmed | [PR #62](https://github.com/ycpiglet/manipulator-control-tutorial/pull/62) accepted 14 full-SHA uses across five verified Node24 Action releases and a machine lock; exact head `b9ae8ccdf2ec015d6c17f1bbb385efb5b4c1c977`, merge `53f9e84e240f70b0d4223fbcd7cd71fe81cc8af2`, checks 6/6 at both | Continue reviewed lock updates; release provenance remains separate | FS-20260722-005-D |
| FS-20260723-026 | 2026-07-22T15:13:38Z | `a216ee8b326008ffeae3e139fad65716c19ed341` | P1-07 | partial | confirmed | [PR #60](https://github.com/ycpiglet/manipulator-control-tutorial/pull/60) structurally excluded source-only Qt audit modules; [exact-head desktop](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29893963327) measured Windows 250.2 MB, Ubuntu 329.0 MB, macOS 186.5 MB, all below 400 MiB; exact-head/post-merge checks passed 6/6 | PKG-01 must measure deterministic archives against 300 MiB, cold launch, and packaged QML; thresholds may not be promoted from this partial evidence | FS-20260722-012 |

### Current promotion summary at this event

- STATE-01 and IA-00 are accepted; IA-00 is FREEZE and IA-01 is not required.
- INT-01 disposition is complete: Draft #37 was superseded by bounded PR #60,
  and Draft #38 was closed without forward-port. Neither was merged wholesale.
- SUP-01 is partial through A/B/C. B3 remains blocked on the remaining SUP-01
  scan/SBOM/system-package work, PKG-01, and E2E-01.
- B4–B6 and real-output cleanup retain every prior authorization and external
  evidence gate; no promotion or destructive-work authority is added here.

## SUP-01 Aggregate Reconciliation Events — 2026-07-23

These events append accepted PR #66 evidence evaluated at protected
`main@6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1`. They do not rewrite the
audit, registry, initial events, B2 records, prior ledger rows, or earlier
promotion summaries.

| Event | Recorded at UTC | Evaluated commit | Finding/component | Status | Evidence state | Evidence and scope | Remaining gate | Supersedes |
|---|---|---|---|---|---|---|---|---|
| FS-20260723-027 | 2026-07-22T19:48:43Z | `6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1` | P0-05 | partial | confirmed | [PR #66](https://github.com/ycpiglet/manipulator-control-tutorial/pull/66) accepted exact head `387dd331a408d46beffb80483916401bf2e08c73`, merge `6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1`, and common source/merge tree `ac5d9ba1720911357a02c665787ec50ed50eaf5f`; exact-head [CI](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29949569945), [desktop](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29949569735), post-merge [CI](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29950993214), and [desktop](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29950992873) passed required checks 6/6; fail-closed scans, pinned Ubuntu direct-package evidence, and deterministic SBOM inputs close the SUP repository input-gate scope | P0-05 remains partial: immutable tag/release is REL-01; final per-OS SBOM/provenance and hosted base/native transitive evidence remain | FS-20260723-021 |
| FS-20260723-028 | 2026-07-22T19:48:43Z | `6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1` | P1-05 | closed_for_scope | confirmed | PR #62–#64 and [PR #66](https://github.com/ycpiglet/manipulator-control-tutorial/pull/66) provide reviewed Action/runtime locks, exact Python hashes, pinned Panda bytes, a 78-dependency vulnerability scan with 0 findings/waivers, hosted package-profile license inventories, 22 pinned Ubuntu direct packages, and deterministic SBOM inputs; post-merge Ubuntu artifact `8542125543` verified snapshot `20260723T000000Z` and expires `2026-08-05T19:27:49Z`; license results remain explicitly `inventory-complete` / `pending-lic-01` | LIC-01 must close reviewed SPDX/copyright/text/source/NOTICE coverage and Qt/PySide obligations; final OS SBOM/provenance and native/base transitive inventory remain release gates | FS-20260723-022 |

### Current promotion summary at SUP-01 aggregate acceptance

- SUP-01 is accepted only for the repository lock, scanner, Ubuntu
  direct-package, and deterministic SBOM-input gate.
- LIC-01 is next. `pending-lic-01` is not legal approval, notice completion, or
  public-distribution authority.
- B3 remains blocked on PKG-01 and integrated E2E-01. B4 remains blocked on
  LIC-01, OPS-01, final SBOM/provenance, immutable release identity, and every
  other G3 condition.
- B5/B6 and real-output cleanup retain every prior authorization and external
  evidence gate. No public-beta, signing, release/DOI, external-contact, or
  destructive-work authority is added here.
