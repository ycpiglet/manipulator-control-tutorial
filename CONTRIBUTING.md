# Contributing

Thanks for your interest in improving the MuJoCo Manipulator Control Lab.

## Ways to contribute

- **Report a problem or confusion**: open a GitHub issue. For learning
  materials, "this step lost me" is a valuable bug report — please say which
  config or manuscript section you were following.
- **Add or improve a lab scenario**: add a YAML under `configs/<lab>/`.
  The test suite requires every config to register a learning guide in
  `src/mclab/learning_guides.py` and next-run suggestions in
  `src/mclab/sim/reporting.py` — this keeps every scenario teachable.
- **Improve the docs**: lab guides live in `docs/` (English); the full
  tutorial manuscript lives in `paper/` (Korean, LaTeX).

## Before opening a pull request

Start from a clean worktree based on the current remote main. Keep unrelated
work in a separate branch/worktree instead of stashing, resetting, or folding
it into the same PR.

```bash
git fetch --prune origin
git status --short --branch
git worktree add -b agent/my-focused-change ../mclab-my-focused-change origin/main
```

Keep one risk and one rollback unit per PR. Do not include generated
`outputs/`, build products, caches, or unrelated local experiments. Cleanup or
retention tests must use temporary fixtures, never real learner outputs.

Run the core checks that are practical in a local source checkout:

```bash
python -m ruff check src tests scripts .agents/validation
python -m pytest -q --cov=mclab --cov-report=term --cov-fail-under=80
python .agents/validation/check_mypy_baseline.py --python-version 3.11
python .agents/validation/check_readme_contract.py
python .agents/validation/check_citation_coverage.py
python .agents/validation/validate_robotics_foundations.py
```

The mypy check is an exact inherited-debt gate, not a claim that the codebase is
type-clean. Its active configuration enables `check_untyped_defs`,
`disallow_untyped_defs`, and `disallow_incomplete_defs` while preserving the
reviewed 264-diagnostic baseline. `disallow_any_explicit` remains disabled: its
781 inherited diagnostics are a named residual and are not folded into the 264.

Run the checker on Linux x86-64 with native CPython 3.10, 3.11, or 3.12 and an
exact `dev` inventory. A dedicated `.venv` is recommended; CI's selected native
interpreter prefix is also supported. The checker records `sys.prefix` and
`sys.base_prefix`, requires every expected distribution root and metadata origin
plus the mypy import origin to resolve under that selected prefix, requires the
native minor version to match `--python-version`, and reports both native and
target versions. This rejects inherited `--system-site-packages` distributions
as well as `app-dev`, `package`, and environments with unpinned distributions.
Its unpinned bootstrap allowlist is empty: `pip`, `setuptools`, and `wheel` are
controlled by the build lock.

The desktop `app-dev` environment may run the general suite with
`python -m pytest -q --ignore=tests/test_mypy_baseline.py`, but that exclusion is
not MAINT-01A evidence. In the clean `dev` environment, run the focused command
`python -m pytest -q tests/test_mypy_baseline.py` and the checker command above
for authoritative evidence.

Normal validation requires exact diagnostic, source-file-count, and typing-
suppression multisets. Thus even a genuine removal or a new clean module fails
with a migration-required result. Additions, multiplicity increases, and
reintroductions always fail. Suppression inventory covers inline `type: ignore`
comments, file-level `mypy` directives, `@no_type_check`, and every repository-
controlled `.py` and `.pyi` under the `src` mypy import root, including sibling
packages. Aliases from `typing` or `typing_extensions` and local re-export chains
cannot hide `@no_type_check`. Ignores and decorators are bound to normalized AST
content plus a line-insensitive parent/field/index structural path, so moving an
ignore between identical statements or branches is a new suppression.

After an intentional debt reduction or source-file inventory change, generate a
candidate separately:

```bash
python .agents/validation/check_mypy_baseline.py --python-version 3.11 \
  --print-migration-candidate \
  --subject-commit COMMIT_40_HEX --subject-tree TREE_40_HEX
```

Generation succeeds only when diagnostic and suppression multisets do not
increase and either debt was removed or the source-file inventory changed. This
lets a reviewed migration admit a new clean module without silently recapturing
debt. A reviewed migration must preserve the immutable prior baseline and every
config it references, append the prior baseline's exact path and SHA-256 to
history, commit a canonical successor, and deliberately update the active
path/hash in the checker. Never replace history or use regeneration to admit a
reintroduction. Mypy version, dependency profile, platform, config, and policy
changes likewise require a dedicated reviewed migration.

MAINT-01A is safe-main development evidence only. It does not authorize public
beta, signed distribution, release/DOI publication, a real-output cleanup
dry-run, or cleanup apply.

Paper checks are required even when a change is expected not to affect the
paper because the current required workflow always runs them. CI additionally
builds `paper/main.tex` with Tectonic and builds and smoke-tests unsigned
development bundles on Windows, Ubuntu, and macOS. Those platform jobs are not
implied by the local commands above. Report every check that was not run as
`not run`; exact-head GitHub CI remains the cross-platform merge evidence.

## Licensing of contributions

Code contributions are accepted under Apache-2.0; documentation and
educational content under CC BY 4.0 (see `LICENSE` and `LICENSE-docs`).

## Questions

For ordinary questions, setup problems, or lesson confusion, read the
[support policy](.github/SUPPORT.md) and open an issue. Report suspected
security or data-loss vulnerabilities privately according to the
[security policy](.github/SECURITY.md).
