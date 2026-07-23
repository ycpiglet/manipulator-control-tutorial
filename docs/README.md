# Documentation map / 문서 안내

The root [Korean README](../README.md) and [English README](../README.en.md)
are the shortest introductions. Use this page to choose the next document by
role. 루트 README에서 프로젝트를 파악한 뒤, 아래에서 역할에 맞는 문서를
선택하세요.

Most detailed guides are currently English-first; the table marks their purpose
in both languages. 상세 가이드는 현재 영문 중심이며, 아래 표에서 용도를 한·영으로
함께 표시합니다.

## Start here

| Audience / 대상 | Document | Use it for |
|---|---|---|
| New learner / 신규 학습자 | [Learner guide](learner_guide.md) | Complete the predict–change–observe–replay loop / 예측–변경–관찰–재생 흐름 완주 |
| Learner or shared-PC administrator / 학습자·공용 PC 관리자 | [Local data and privacy / 로컬 데이터와 개인정보](local_data_and_privacy.md) | Locate, copy, sanitize, quarantine, and restore local evidence / 로컬 증거의 위치·복사·익명화·격리·복원 확인 |
| Instructor / 교육자 | [Educator guide](educator_guide.md) | Plan classroom evidence and review / 수업 증거와 복습 설계 |
| Developer / 개발자 | [Desktop architecture](developer_guide.md) | Understand application boundaries and UI invariants / 앱 경계와 UI 불변 조건 파악 |
| Repository maintainer / 저장소 관리자 | [Structure and compatibility](repository_structure.md) | Preserve public paths and plan future consolidation / 공개 경로 보존과 향후 정리 결정 |
| Installer / 설치 담당자 | [Installation and release](installation.md) | Source setup, assets, platforms, and release policy / 소스 설치·asset·플랫폼·배포 정책 |
| Troubleshooter / 문제 해결 | [Troubleshooting](troubleshooting.md) | Diagnose dependency, GPU, asset, and replay problems / 의존성·GPU·asset·재생 문제 진단 |
| Contributor / 기여자 | [Contributing](../CONTRIBUTING.md) | Add code, configs, learning guides, or documentation / 코드·config·학습 가이드·문서 기여 |

## Lab references

After completing [source setup](installation.md#source-setup), the integrated
desktop app is the recommended learner entry point:

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
- [Readiness execution plan](../.agents/READINESS_EXECUTION_PLAN.md):
  authoritative work order, gates, and compatibility sequencing
- [2026-07-20 readiness audit](../.agents/reviews/20260720_enterprise_readiness_audit.md):
  original findings, evidence, and decision snapshot at that time

## Which interface is current?

The Qt desktop app is the primary experience for new learners. The
`run --viewer` route, the separate `MCLab Interaction` panel, and root
`run_lab*.cmd` or `run_batch*.cmd` files remain supported compatibility
paths for existing lessons and advanced inspection. They are not separate
products.
