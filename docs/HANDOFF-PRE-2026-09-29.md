# 재개 인수인계 — 2026-09-28 종료 기준

## 기준과 한계

- 기준: **2026-09-28 23:59:59 KST**. 9월 29일의 변경/대화는 제외했다.
- 기준 원격/커밋: `origin/main` `2c61600` (2026-07-27). 이 문서는 그 지점의 `codex/handoff-pre-20260929` branch에만 있다.
- 채팅 transcript는 없으며 `AGENTS.md`, `.agents/` audit/baseline/ledger, worktree와 Git trail이 재개 가능한 기록이다.

## 제품 목표와 직전 결과

MCLab은 Lab01~04의 제어 파라미터를 바꾸고, 결과를 config/log/report/worksheet/plot evidence로 저장하는 오프라인 로봇 제어 학습실이다. 개발중 v0.1.0이며 산업용 제어기가 아니다.

직전 main은 OPS-01A local-data boundary review follow-up(PR #79)을 통합했다. 그 이전에 repository governance·dependency lock·asset pin·SBOM inputs, bounded package identity, local data policy를 진전시켰다. `.agents/reviews/20260720_enterprise_readiness_finding_status.md`는 append-only ledger이며 B2 safe-main만 제한적으로 선언하고, B3~B6/public beta/release/DOI에는 별도 gate가 남았음을 명확히 한다.

## 중단 지점

단일 활성 claim은 확인되지 않았지만, 의미 있는 독립 worktree가 남아 있다: `agent/pkg01a-package-identity`, `agent/pkg01b-packaged-startup`, `agent/packaged-e2e`, `agent/edu01a-educator-kit-current`, `agent/maint01a-mypy-baseline-current`, `agent/ops01a-local-data-policy-current`, `codex/ops01a-network-boundary-followup`, `codex/self-hosted-ci-20260729`.

이들은 서로 다른 promotion gate를 다룬다. 따라서 하나를 임의로 main에 합치지 않는다. ledger의 최신 relevant event와 각 branch의 exact PR/CI evidence를 먼저 대조해야 한다. 특히 실제 target hardware, assistive tech, novice study는 external-blocked이고, signing/release/SBOM/provenance/publication은 이 저장소 작업만으로 닫히지 않는다.

## 새 세션 순서

1. `AGENTS.md`, `README.md`, `.agents/CURRENT_STATE.md`(존재 시), enterprise finding-status ledger를 읽는다.
2. `git fetch --prune` 후 남은 worktree별 `git status`, merge-base, unmerged commit, claim/PR evidence를 표로 만든다.
3. 하나의 gate (예: PKG/E2E/EDU/MAINT/OPS)만 선택해 새 claim/worktree에서 진행한다. 기존 generated outputs와 evidence ledger를 rewrite하지 않는다.
4. real-output cleanup, external contact, beta/release/tag/DOI, destructive cleanup은 ledger에 적힌 별도 owner authorization 없이는 수행하지 않는다.

## 프롬프트·대화 재구성 정본

`AGENTS.md`는 학습 증거·learner-control·report/worksheet 계약을, README는 제품 및 실행 경로를 정의한다. 작업 대화의 지속 기록은 `.agents/reviews/20260720_enterprise_readiness_finding_status.md`와 `.agents/baselines/`, 각 branch의 commit/PR evidence다.
