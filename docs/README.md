# Documentation map / 문서 안내

The root [Korean README](../README.md) and [English README](../README.en.md)
are the shortest introductions. Use this page to choose the next document by
role. 루트 README에서 프로젝트를 파악한 뒤, 아래에서 역할에 맞는 문서를
선택하세요.

## Start here

| Audience / 대상 | Document | Use it for |
|---|---|---|
| New learner / 신규 학습자 | [Learner guide](learner_guide.md) | Complete the predict–change–observe–replay loop |
| Instructor / 교육자 | [Educator guide](educator_guide.md) | Plan classroom evidence and review |
| Developer / 개발자 | [Desktop architecture](developer_guide.md) | Understand application boundaries and UI invariants |
| Installer / 설치 담당자 | [Installation and release](installation.md) | Source setup, assets, platforms, and release policy |
| Troubleshooter / 문제 해결 | [Troubleshooting](troubleshooting.md) | Diagnose dependency, GPU, asset, and replay problems |
| Contributor / 기여자 | [Contributing](../CONTRIBUTING.md) | Add code, configs, learning guides, or documentation |

## Lab references

The integrated desktop app is the recommended learner entry point:

```bash
python -m mclab app
```

The lab references explain concepts, evidence plots, headless commands, and
advanced compatibility-viewer workflows.

1. [Lab01 — Mass–spring–damper](lab01_mass_spring_damper.md)
2. [Lab02 — PID control](lab02_pid_control.md)
3. [Lab03 — 2DOF arm, trajectories, Jacobian, and DLS](lab03_trajectory_planning.md)
4. [Lab04 — Franka Panda and virtual-wall contact](lab04_panda_manipulator.md)

## Design, validation, and research

- [Simulator development specification](../SIMULATOR_DEVELOPMENT_SPEC.md):
  original product intent, constraints, and CLI contract
- [UI validation](ui_validation.md): automated desktop, report, accessibility,
  performance, and remaining human/platform gates
- [Tutorial paper workspace](../paper/README.md): Korean long-form theory and
  validation workflow
- [JOSE paper](../jose/paper.md): software-paper draft
- [Active project state](../.agents/CURRENT_STATE.md): current objective and
  handoff pointer
- [2026-07-20 readiness audit](../.agents/reviews/20260720_enterprise_readiness_audit.md):
  release decisions, blockers, evidence, and ordered next actions

## Which interface is current?

The Qt desktop app is the primary experience for new learners. The
`run --viewer` route, the separate `MCLab Interaction` panel, and root
`run_lab*.cmd` or `run_batch*.cmd` files remain supported compatibility
paths for existing lessons and advanced inspection. They are not separate
products.
