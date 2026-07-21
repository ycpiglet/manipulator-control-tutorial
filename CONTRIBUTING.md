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
python .agents/validation/check_readme_contract.py
python .agents/validation/check_citation_coverage.py
python .agents/validation/validate_robotics_foundations.py
```

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
