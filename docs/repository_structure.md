# Repository structure and compatibility boundary

[Documentation map](README.md) · [한국어 README](../README.md) ·
[English README](../README.en.md)

This page records the current layout; it is not a directory-migration plan.
현재 구조를 사실대로 기록하는 문서이며, 디렉터리 이동 계획이 아닙니다.
The detailed inventory and change rules below are English-first; the Korean
README summarizes the newcomer-facing decision.

## DOC-01 decision: no move

DOC-01 keeps every public path in place. The core package is already separated
by responsibility, while the root launchers still serve existing classroom
material. Moving them during a README and validation change would mix
documentation risk with compatibility risk.

DOC-01에서는 공개 경로를 이동하지 않습니다. 핵심 패키지는 역할별로 이미
분리되어 있고, 루트 실행기는 기존 수업 자료가 계속 사용합니다. README·검증 변경과
경로 호환성 변경을 한 작업에 섞지 않습니다.

A structural decision belongs to IA-00 after the B2 safe-main gate. Until that
decision, this inventory is the compatibility boundary.

## Newcomer entry points

| Entry point | Current role | Compatibility promise |
|---|---|---|
| `START_HERE.cmd` | Windows guided setup and app launch | Public newcomer path |
| `start_here.sh` | Linux guided setup and app launch | Public newcomer path |
| `START_HERE.command` | macOS guided setup and app launch | Public newcomer path |
| `python -m mclab app` | Source-install desktop entry | Public source path |
| `python -m mclab run ...` | Headless or advanced viewer experiment | Public source path |
| `run_mclab.cmd` | Existing Windows learner-menu shortcut | Compatibility path for at least one release after any future move |
| `run_lab*.cmd`, `run_batch*.cmd`, `run_all_batches.cmd` | Existing lesson and comparison shortcuts | Compatibility paths for at least one release after any future move |
| `run_all.ps1` | Full-suite maintainer verification helper | Internal tooling; not a learner launcher or public compatibility path |

The three `START_HERE` launchers delegate to `scripts/start_mclab.py`. The many
Windows lab and batch shortcuts are not separate products. The PowerShell
verification entry is internal maintainer tooling, not a learner launcher or a
public compatibility path.

## Source and evidence layout

| Path | Owner and contents | Move status |
|---|---|---|
| `src/mclab/` | Python package, CLI, app, shared simulation and reporting | Keep |
| `src/mclab/controllers/` | Readable control laws | Keep |
| `src/mclab/labs/` | Lab-specific MuJoCo and controller assembly | Keep |
| `configs/` | Reproducible public YAML experiment inputs | Keep; public config paths |
| `models/`, `third_party/` | Local scenes and licensed external assets | Keep; preserve provenance |
| `tests/` | Unit, smoke, report, desktop, and contract regression checks | Keep |
| `scripts/` | Setup, packaging, and repository automation | Keep |
| `docs/` | Learner, educator, developer, installation, and support guides | Keep |
| `paper/`, `jose/`, `outreach/` | Research and educational publication workspaces | Keep; publication references depend on these paths |
| `.github/workflows/` | Required CI and cross-platform desktop checks | Keep |
| `.agents/` | State, audits, baselines, plans, and deterministic validation | Internal governance path; keep |
| `outputs/` | Generated local evidence | Never treat as source; Git tracks only `.gitkeep` |

## Change rules

Any future consolidation must be a separate compatibility change and must:

1. start with an IA-00 inventory and decision record after B2;
2. list every old path, new path, caller, documentation link, CI reference,
   package reference, and rollback step;
3. preserve config, model, and publication paths unless a later decision
   explicitly proves a need;
4. keep a working shim for at least one release when a public launcher moves;
5. update both root READMEs and pass
   `python .agents/validation/check_readme_contract.py` before merge.

Because MCLab is still v0.1 and source-first, this boundary prevents accidental
breakage; it does not promise indefinite API or artifact-schema stability.
