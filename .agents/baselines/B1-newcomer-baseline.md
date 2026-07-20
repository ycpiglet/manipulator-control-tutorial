# B1 — Newcomer Baseline

- Status: **DECLARED — G0 PASS**
- Declared: 2026-07-20 21:55:51 KST / 2026-07-20T12:55:51Z
- Baseline subject: `f04cca16848316e227df18fe129229b515ae01c7`
- Commit tree: `e6cf789034b0b505a1229993083e2784b03bb1cb`
- Pre-merge main: `247c97ed13c2e45e36bb467deb9ec838a22f2f44`
- Source PR: [#35](https://github.com/ycpiglet/manipulator-control-tutorial/pull/35)
- Source head: `52302a255cdea6c7ce05a4b7a577aec55bab6e00`
- Merge strategy: two-parent merge commit
- Tree equivalence: **PASS** — the merge tree equals the source-head tree
- Owner authorization: [exact-head validation record](https://github.com/ycpiglet/manipulator-control-tutorial/pull/35#issuecomment-5022468677) and owner merge
- Formal GitHub review objects: `0` — this is not recorded as formal reviewer approval

## Scope

PR #35 added the newcomer README and information architecture, documentation
map, readiness audit, execution plan, and cross-session work-order records.

- Changed files: 12
- Additions/deletions: `+1168/-206`
- Runtime, tests, configs, models, workflows, and packaging changed by PR #35:
  none
- Whitespace validation: pass

The baseline inherits the product state already present in pre-merge main
`247c97e`; its controlled-item fingerprint is recorded below.

## G0 Evidence

| Gate | Result | Evidence |
|---|---|---|
| Exact-head checks | 6/6 success | PR #35 check rollup |
| Simulator lint/tests | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826286/job/88356768445) |
| Paper citation/formula gates | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826286/job/88356768066) |
| Paper LaTeX build | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826286/job/88356768067) |
| Windows unsigned build | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826317/job/88356763248) |
| Ubuntu unsigned build | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826317/job/88356763283) |
| macOS unsigned build | pass | [job](https://github.com/ycpiglet/manipulator-control-tutorial/actions/runs/29743826317/job/88356763285) |
| Exact-head CI tests | pass | 438 passed, 2 skipped, 1,088 subtests |
| Exact-head CI coverage | pass | 81.04%, floor 80% |
| Exact-head Ruff | pass | 0 findings |
| KR/EN README structure | pass | 9/9 corresponding H2 sections |
| Changed-scope local links | pass | 64 checked, 0 broken |
| Rebase patch equivalence | pass | three documentation patches 1:1 equivalent |

## Controlled-Item Fingerprints

Inventory SHA-256 values hash the canonical output of the listed path set.
Each row is produced by one `git ls-tree` invocation with all of that row's
path arguments passed together; do not concatenate hashes from separate
invocations:

```bash
git ls-tree -r --full-tree f04cca16848316e227df18fe129229b515ae01c7 -- <paths>
```

| Area | Git tree/blob OID | Inventory SHA-256 |
|---|---|---|
| Product `src/mclab` | `b76cbe1edb47d9cca6ad60487029795dfad4c09b` | `bff7e35ddcb1aa85ee5833b6ef6ecc83e86f12045b6151e16e496998f0394db1` |
| Configs | `fe2cbe3a402eaf12944f20198240e99cd246780e` | `b1108fd870d5368ab21afda9cdce8f1dd9d87759dab0e283fe6bb5bfcf624a99` |
| Models | `0e4f3ed4da2ed9d388cc81ac2c254fcfd4842dbd` | `1de2bc233d7f36c07c831b9a74a525a4328fee0b53f1fde002912d151b1ac052` |
| Third-party | `b91d29b1c5a0d8916c390a78c46046162bc796c6` | `fb986ed36f21f275caf0515b236ffbc41c00d74f8cd0a4bc8625d8c9d2152106` |
| Validation: `tests scripts .agents/validation .github/workflows` | tests `abf09dd8`; scripts `c00d31b6`; agent validation `ef3d260b`; workflows `a0c652bf` | `70507a6c909fc2d0d89ed0e83a90fcf91a98e3e54c03a1d486fc91c5ef88417b` |
| Distribution: `packaging pyproject.toml` | packaging `a5b1a9ec`; pyproject `efba9709` | `f56a05e64633517ba558ed9d2a85cf6b1951696e4c1fce2c722866ddcfff84a1` |
| Newcomer: `README.md README.en.md docs` | docs `1c7b0f1c`; README KR `096de1ea`; README EN `910f08bb` | `236482a1e081f6d357d17401866a7dea664725cd02d05ae00318023003b78c3b` |
| Publication: `paper jose CITATION.cff` | paper `8afc23e0`; JOSE `54945f77`; CFF `bd41048c` | `a907013c7f35d8892078e33cb591d511416aa78a551ec3c192d18c5e8d8099e1` |
| All controlled paths listed below | multiple | `0a5aededc48faee733b9a52c13c5ca317246f6f73c02b338c08c0618e85247dc` |

The final row uses this exact path set:

```bash
git ls-tree -r --full-tree f04cca16848316e227df18fe129229b515ae01c7 -- \
  src/mclab configs models third_party tests scripts .agents/validation \
  .github/workflows packaging pyproject.toml README.md README.en.md docs \
  paper jose CITATION.cff | sha256sum
```

The three multi-root values most likely to be reproduced incorrectly can be
checked directly with these single-invocation commands:

```bash
git ls-tree -r --full-tree f04cca16848316e227df18fe129229b515ae01c7 -- \
  packaging pyproject.toml | sha256sum
git ls-tree -r --full-tree f04cca16848316e227df18fe129229b515ae01c7 -- \
  README.md README.en.md docs | sha256sum
```

`pyproject.toml` content SHA-256:
`ebb96cdb9907469c0b1dc45c11e93fb8e974a3c55675721f10d90e35b251a12f`

Dependency lock: **ABSENT**

MuJoCo Menagerie installer pin:

- commit: `71f066ad0be9cd271f7ed58c030243ef157af9f4`
- archive SHA-256:
  `000b9f51abb404efb1de2b88b3c738674c472a85b6c4143168859abc4c98d423`

## Limits and Next Gate

B1 proves the newcomer documentation and handoff baseline only. It is not the
B2 safe-main baseline.

Still open:

- unsafe `mclab clean` P0;
- inconsistent course-completion semantics;
- absent dependency lock;
- mutable simulator-CI Menagerie checkout;
- absent main branch protection/rulesets.

`mclab clean` remains forbidden. The next implementation action after the
governance baseline is SAFE-01 from a clean branch/worktree based on B1.
