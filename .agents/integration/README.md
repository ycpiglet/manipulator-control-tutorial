# Protected-main integration harness

`scripts/protected_integration.py` is a fail-closed transaction harness for the
fixed queue in `protected-main-v1.json`. It does not grant release or promotion
authority. Its only external write operations are:

- add an exact generation-1 subject-refresh certificate and matching owner
  attestation for a predeclared fixed-queue refresh after an independent
  read-only agent review;
- mark the exact queued pull request ready for review;
- merge that pull request with an exact-head guard; and
- add content-fingerprinted evidence comments to that pull request.

It also writes resumable state below the Git common directory. The transaction
lock is an OS-released advisory file lock, so a hard-killed process does not
leave a stale ownership directory. State is only a resume hint: every resume
and completed-state replay revalidates live Git, GitHub, ruleset, reviews,
checks, and provenance before publishing evidence.

The harness has no public-beta/promotion, participant-recruitment, release,
tag, artifact download, package inspection/distribution, learner-output,
cleanup, external-contact, signing/release credential acquisition or use,
signing/notarization, DOI, repository-move, ruleset/security-setting mutation,
or bypass operation. The sole authentication exception is an already
authenticated `gh` session for the pinned owner account, used only for the
bounded refresh-attestation/ready/comment/merge operations described here.

## Required environment and authority

- a POSIX host, Python 3.10 or newer, Git, and an authenticated `gh` CLI;
- a clean linked/disposable worktree, not the primary checkout;
- `origin` exactly
  `ycpiglet/manipulator-control-tutorial`;
- explicit 40-hex `--expected-base` and `--expected-head` values; and
- no concurrent protected integration in the same Git common directory.

The executed `__file__` must resolve to the canonical repository
`scripts/protected_integration.py`. The policy path is not configurable. Both
that script and the canonical policy blob must equal the versions committed at
the explicit expected base. The script also pins the canonical policy-file
SHA-256, so a policy-only amendment deactivates the harness. Updating this
authority therefore requires an ordinary, separately authorized change to
both files; the fixed queue cannot amend either one.

The policy records each independently reviewed subject base/head pair,
combined stable patch ID, whitespace-preserving/rebase-stable semantic patch SHA-256,
reviewed-subject exact binary-diff SHA-256, name-status SHA-256, sorted-NUL
changed-path SHA-256, branch, exact reviewed/locked/refreshable path sets,
per-refreshable-reviewed-path result blob/mode identities, completion claim,
and path envelope. The stable patch ID is
supplementary; the semantic digest preserves every added/removed byte,
including Python indentation, while normalizing only file order, blob-index
lines, and hunk locations. A legitimate overlapping-base rebase may therefore
have a different exact binary diff while retaining the semantic/path/status
bindings. The reviewed exact-diff digest is enforced only when the candidate
is the original reviewed subject head; it is provenance for that review, not a
false requirement that every later rebase have byte-identical diff framing.
The current candidate's exact diff is instead bound into the exact owner
attestation and transaction evidence.

For the fixed pending queue only, the owner's 2026-07-27 delegation permits
one bounded subject-refresh generation without another human prompt. Every
non-refreshable path must remain present with its separately pinned semantic
and name-status digests. Only exact predeclared refreshable paths may be
added or semantically reconciled, or may cease to appear in the candidate diff
when the new base has the exact pinned reviewed-result blob/mode identity for
that path. A refresh cannot delete a base file or add/change an executable
bit. Patterns, denied paths,
the harness, policy, authority documents, release paths, outputs, and
artifacts cannot be refreshed. A refreshed exact head requires one immutable
owner-authored refresh certificate that stores the full canonical independent
review receipt plus its harness-computed SHA-256. The receipt binds PASS,
zero blockers, the exact base/head/tree, every effective digest and path set,
the independent read-only task identity, and explicit zero prohibited-content
access. That certificate and the matching owner attestation are revalidated
for every predecessor and transaction stage. Generation 2 is unsupported.
This is content renewal inside the fixed envelope, not harness self-amendment;
`self_amendment_authority` remains false.

Unattested refresh, locked content/status drift, base-file deletion,
executable-bit drift, symlink, submodule, binary, denied-path, or envelope
drift stops the transaction. The
already-integrated PR #74 prefix is also pinned to its exact source base/head,
protected merge, equivalent tree, exact-head and post-merge checks, and
immutable owner completion comment.

Every predecessor must be an exact same-repository `main` PR on its fixed
branch. Its source and merge commits are fetched and checked for parent/tree
equivalence, reviewed content/path bindings, ancestry in the new base,
exact-head and post-merge 6/6, pinned-owner `merged_by`, resolved discussions,
and no active changes request or approval.
Harness-era predecessors also require the exact owner-authored post-merge
evidence comment produced by their completed transaction.

All GitHub CLI API and GraphQL calls force `--hostname github.com`, use a
finite command timeout, and pass a small method/endpoint allowlist. Git
provenance commands clear inherited control variables, disable replacement
objects, reject local replacement refs, grafts, and shallow repositories, pin
diff behavior, and compare the authority files without clean filters.
Transaction state and lock files reject symlink/hardlink substitution.

## Required independent review and owner-account attestation

For an unchanged reviewed-subject binding, the orchestrating agent posts the
following exact attestation through the pinned owner account only after a
separate read-only agent reviews the exact candidate and returns `PASS`. For a
generation-1 refresh, `attest-refresh` creates both the canonical refresh
certificate and a corresponding extended owner attestation after exact-head
6/6 and the same review gate. These are durable records of the
independent-agent gate; they do not represent formal independent human
approval and do not require a new per-PR human prompt. Before `preflight`, the
exact target PR comment for an unchanged subject must be:

```text
<!-- protected-integration:v1:owner-attestation:pr-<PR>:<HEAD> -->
Protected integration v1 owner attestation

- Pull request: `#<PR>`
- Work item: `<WORK_ID>`
- Exact base: `<BASE>`
- Exact head: `<HEAD>`
- Exact head tree: `<HEAD_TREE>`
- Reviewed subject base: `<REVIEWED_SUBJECT_BASE>`
- Reviewed subject head: `<REVIEWED_SUBJECT_HEAD>`
- Stable patch ID: `<STABLE_PATCH_ID>`
- Semantic patch SHA-256: `<SEMANTIC_PATCH_SHA256>`
- Current exact diff SHA-256: `<CURRENT_EXACT_DIFF_SHA256>`
- Sorted-NUL changed-path SHA-256: `<CHANGED_PATHS_SHA256>`
- Name-status SHA-256: `<NAME_STATUS_SHA256>`
- Independent read-only agent exact-candidate review: `PASS`
- Formal independent human approval: `absent`
- Required approvals under the single-collaborator exception: `0`
- Standing owner risk acceptance: `accepted 2026-07-26`
- Delegated scope: `fixed protected-main integration queue only`

This attestation does not authorize public beta or promotion, participant recruitment, release/tag/DOI, signed or package distribution, signing or release credential acquisition/use, artifact/package content access, learner-output access, cleanup dry-run/apply, repository moves, external contact, or repository ruleset/security-setting changes.
```

The author must be the immutable GitHub user ID `68498184`, login `ycpiglet`,
type `User`, with issue-comment association `OWNER`. The body is exact and
binds the PR/work item, base, head, tree, reviewed subject base/head, semantic patch,
current exact diff, changed paths, and name-status evidence. The harness reads
back exactly one direct admin collaborator with the same immutable identity,
formal independent human approval `false`, active human approvals `0`,
required approvals `0`, and the live ruleset. `mark-ready` and `merge` also
require the authenticated `gh` actor to be that exact owner before every
external mutation; the pull must have GitHub auto-merge disabled.

For a refreshed subject, `attest-refresh` accepts one UTF-8 canonical JSON
receipt of at most 16 KiB. It requires an exact key set: schema/version,
repository/policy/PR/work/completion identity, reviewer task of the form
`/root/<independent_agent>`, role `independent-read-only`, result `PASS`, an
empty blocker list, exact UTC review time, source-only scope, exact
base/head/tree, binding mode, stable/semantic/path/exact-diff/name-status
digests, changed/refreshed/removed paths, generation 1, formal human approval
absent, prohibited-content access false, and external contact false. The
harness parses a real calendar timestamp, rejects a review before the
2026-07-27 authority or more than five minutes in the future, compares every
receipt field and JSON type to the live candidate, computes the receipt
SHA-256 itself, and stores both object and digest.

No separate reviewer principal, signing key, or Codex-state API exists in this
single-owner repository. The `/root/<agent>` identity is therefore procedural
evidence delivered by the trusted orchestrator, not a cryptographic identity
proof or formal human approval. Persisting the full exact-candidate receipt
closes stale, opaque, or mismatched receipt errors within that trust model.

Before its first comment write, `attest-refresh` revalidates the clean
worktree, branch/base/head, queue, locked content, exact refresh envelope,
synthetic merge, ruleset, reviews, exact-head checks 6/6, collaborator
topology, and authenticated owner. Typed comment writers construct the
certificate and owner attestation from structured evidence; no generic
attestation body writer is exposed. The harness then reads both comments back,
requires the refresh comment's `created_at == updated_at`, validates review
time causality, and reruns full `preflight`. A stale, edited, duplicated,
wrong-owner, wrong-head, noncanonical, type-confused, or generation-2
certificate fails closed.

## Commands

Validate only the canonical committed policy:

```bash
python scripts/protected_integration.py validate-policy
```

Run an exact-candidate read-only preflight:

```bash
python scripts/protected_integration.py preflight \
  --pr 75 \
  --expected-base <40-hex-current-main> \
  --expected-head <40-hex-current-pr-head>
```

After a separate read-only agent returns `PASS` for a bounded refreshed
candidate, persist its exact generation-1 certificate and owner attestation:

```bash
python scripts/protected_integration.py attest-refresh \
  --pr 75 \
  --expected-base <40-hex-current-main> \
  --expected-head <40-hex-current-pr-head> \
  --review-receipt-json '<canonical-one-line-receipt-from-independent-agent>'
```

Mark the same candidate ready, settle, revalidate, and add idempotent
pre-merge evidence:

```bash
python scripts/protected_integration.py mark-ready \
  --pr 75 \
  --expected-base <40-hex-current-main> \
  --expected-head <40-hex-current-pr-head>
```

Merge only after the recorded ready transaction, then verify exact merge
parents/tree and post-merge required checks:

```bash
python scripts/protected_integration.py merge \
  --pr 75 \
  --expected-base <same-40-hex-base> \
  --expected-head <same-40-hex-head>
```

`attest-refresh`, `mark-ready`, and `merge` are separate invocations. All
mutating commands acquire the common-dir lock and revalidate the live
ruleset, exact PR identity, queue/order, locked and effective content/path
digests, review state, synthetic merge provenance, and exact-head 6/6 before
their first write. `attest-refresh` then creates and immediately reads back
the refresh certificate and matching owner attestation before a full
preflight. `mark-ready` and `merge` require that exact attestation before
their mutations. `merge` uses GitHub's expected-head guard, records the merge
request atomically before mutation, and recovers if the process stops after
GitHub accepts it. A completed transaction can be rerun idempotently, but
still repeats the full live queue, exact-head, first-parent, and post-merge
gates.

## GitHub atomicity limit

GitHub's pull-request merge API provides a head-SHA guard but no base-SHA
compare-and-swap. The harness rechecks the base immediately before requesting
the merge and then requires exact merge parents, head-equivalent tree,
first-parent inclusion, pinned-owner `merged_by`, and post-merge 6/6. However,
`main` can still advance in the interval between the last read and GitHub's
merge write. The current ruleset also includes a repository-admin
pull-request bypass. If GitHub accepts a merge against a different base, the
post-write checks refuse completion evidence but cannot undo that merge.
Accordingly, this harness does not claim an atomic fail-before-mutation
base-CAS guarantee.

Native GitHub auto-merge must be disabled before and after `mark-ready`.
External automation could still react to the ready transition; an
owner-mismatch in `merged_by` is refused, but the harness cannot atomically
prevent another actor from writing first. These are documented residual
platform races, not additional authority to modify rulesets, bypass
protections, push directly, or roll back history.

Any SHA drift, stale base, unexpected content or path, missing/ambiguous
attestation, collaborator/ruleset/check/app drift, unresolved thread, active
changes request, failed or ambiguous check, dirty/primary worktree, queue
violation, synthetic merge mismatch, or post-merge mismatch stops the
transaction.
