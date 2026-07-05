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

```bash
python -m pytest -q                 # full suite must pass
python -m ruff check .              # lint
python .agents/validation/validate_robotics_foundations.py  # if you touched paper/ or validation
```

CI enforces the same gates plus a coverage floor (>= 80 %).

## Licensing of contributions

Code contributions are accepted under Apache-2.0; documentation and
educational content under CC BY 4.0 (see `LICENSE` and `LICENSE-docs`).

## Questions

Open an issue, or start a discussion on the repository.
