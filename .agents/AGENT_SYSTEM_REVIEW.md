# Agent System Review — 에이전트/스킬/하네스/가드레일 전반 평가

Assessed: 2026-07-04 (KST)
Assessor: Claude Code (측정 기반 검토; 본 문서와 함께 hardening pass가 수행됨)
Scope: 논문 작성·시뮬레이터 제작을 지탱하는 에이전트 운영 체계 전반 —
전역 스킬, 저장소 운영체계(`.agents/`), 프로젝트 하네스(AGENTS.md, 테스트, 검증 스크립트), 가드레일, 기록 시스템

## 1. 총평

3계층 아키텍처가 명확하고 "측정 없이는 완료 없음" 원칙이 실제로 지켜지는 상급 수준의
에이전트 운영 체계이다. 다만 검토 시점 기준으로 강점 대부분이 절차(문서·관례)로만
존재하고 기술적으로 강제되지 않았으며, 한 대의 머신에 강하게 묶여 있었다.
(→ 이 검토 직후의 hardening pass에서 CI 도입, 레지스트리 분리, 스킬 미러링,
경로 이식성 수정이 이루어졌다. 6장 참조.)

| 영역 | 평가(5점) | 근거 요약 |
|---|---|---|
| 아키텍처/역할 분리 | 4.5 | 전역 스킬 ↔ 저장소 운영체계 ↔ 프로젝트 하네스 3계층, 논문/시뮬레이터 트랙 분리 |
| 스킬 설계 | 4 | 48종(논문 23 + 운영 25), 역할·워크플로·가드레일·출력 형식 명세 일관 |
| 시뮬레이터 하네스 | 4.5 | 테스트 340건, bootstrap --verify, doctor, 런처 `.cmd`·모델 XML까지 테스트 |
| 논문 하네스 | 3.5 | 빌드+인용+수식+마커+시각 5중 게이트. 단 마커 방식 취약, (검토 당시) 비이식 |
| 가드레일 | 3 | 규칙은 우수하나 전부 절차적. (검토 당시) CI 강제 없음, sandbox elevated |
| 기록/추적성 | 3.5 | 버전 라벨 20개, 추적표, 검증 요약. 단 (검토 당시) 무한 성장 + 리뷰 원문 미보존 |
| 이식성/온보딩 | 2 | (검토 당시) 스킬·빌드 도구가 사용자 홈 디렉터리 고정, 절대경로 하드코딩 |

## 2. 구성 요소 인벤토리 (측정값)

| 구성 요소 | 위치 | 규모 |
|---|---|---:|
| 전역 스킬 | `~/.codex/skills` (repo 미러: `.agents/skills/`) | 48종 96파일 |
| 운영체계 문서 | `.agents/OPERATING_SYSTEM.md` | 92줄(검토 시점) |
| 프로젝트 하네스 가이드 | `AGENTS.md` | 553줄, Non-Negotiable Rules 8개, 랩별 DoD |
| 검증 스크립트 | `.agents/validation/validate_robotics_foundations.py` | 1,432줄, 체크포인트 함수 약 30개 |
| 지표 레지스트리 | `.agents/VALIDATION_METRICS.yaml` | 557줄(검토 시점) → 183줄(정리 후) |
| 상태 기록 | `.agents/CURRENT_STATE.md` | 3,475줄(검토 시점) → 최신 스냅샷만 유지로 전환 |
| 논문 버전 로그 | `.agents/PAPER_VERSION_LOG.md` | 680줄, 버전 라벨 20개 |
| 추적/감사 문서 | `ROBOTICS_FOUNDATIONS_{PLAN,TRACEABILITY,COMPLETION_AUDIT}.md` | 762/104/222줄 |

## 3. 잘 설계된 부분

1. **3계층 구조**: 전역 스킬(재사용 역할) / 저장소 운영체계(루프·체인·게이트) /
   프로젝트 하네스(도메인 규칙·DoD)가 분리되어 각자 진화 가능.
2. **검증이 실행 코드**: 원고의 수식 주장을 순수 파이썬 수치검증
   (FK/자코비안 유한차분 오차 4e-9, 가상일 항등식 오차 2e-15)까지 수행.
   논문 게이트가 빌드 exit code → 인용 커버리지 → 수식 수치검증 → PDF 마커 →
   렌더링 육안 검사의 5중 구조.
3. **리뷰 체계 실증**: novice/technical 리뷰어 쌍의 다중 에이전트 패스가
   버전 라벨 20개, 게이트 약 40항목으로 축적. 하네스 자체를 테스트
   (`test_launch_scripts.py`, `test_models_xml.py`)하는 문화.
4. **구체적 안전 규칙**: unknown 파일 삭제 0건 게이트, 삭제 전 resolved path 확인,
   3회 연속 blocker 시 중단 선언, third-party 라이선스 보존.

## 4. 약점과 리스크 (검토 시점 측정 근거)

1. **기록 파일 무한 성장**: CURRENT_STATE.md 3,475줄에 108쪽/118쪽 스냅샷이 공존 —
   에이전트가 오래된 수치를 최신으로 오독할 위험. VALIDATION_METRICS.yaml은
   패스별 일회성 게이트(산문 threshold, 기계 판정 불가)가 쌓여 레지스트리 기능 상실.
2. **마커 검증의 취약한 결합**: `text.count("속도 IK 완화식")`식 문구 카운트라서
   예정된 압축 패스에서 문장을 다듬는 순간 체크포인트 연쇄 파손. 원고 진화에 비례해
   검증 스크립트가 부풀어야 하는 구조.
3. **이식성 부재**: 빌드가 `C:\Users\ycpig\.codex\...` 번들 Tectonic, 검증이 번들
   pypdf/Poppler 절대경로 의존(레포 venv에는 pypdf 없음). 스킬은 저장소 밖에만 존재.
   다른 머신·에이전트·CI에서 체계가 재현되지 않음.
4. **가드레일이 전부 절차적**: CI 부재로 어떤 게이트도 자동 강제되지 않고,
   Codex 하네스가 sandbox elevated로 운영되어 기술적 방벽이 사실상 없음.
5. **리뷰 산출물 원문 미보존**: 리뷰어 지적의 요약만 남아 사후 재검토 불가.
   추적 사슬 중 "리뷰 근거" 고리만 약함.

## 5. 권고 (우선순위)

1. CI 도입 (pytest + ruff + 논문 게이트 + Tectonic 빌드) — 절차적 가드레일의 기술적 강제 전환
2. VALIDATION_METRICS를 현행 레지스트리/이력 아카이브로 이분할, CURRENT_STATE 롤링 아카이브
3. 마커 검증을 문구 카운트에서 안정 키(LaTeX `\label`, 커스텀 마커 매크로)로 전환
4. 스킬 48종을 저장소로 미러링해 운영체계 자기완결화
5. 리뷰 패스 원문을 `.agents/reviews/` 등에 보존 (요약과 별도)

## 6. 본 검토 직후 수행된 hardening pass (2026-07-04)

- 권고 1: `.github/workflows/ci.yml` 신설 — simulator(lint+pytest, Menagerie sparse
  checkout+캐시), paper-gates(인용 커버리지 + 수식/마커 검증), paper-build(Tectonic
  빌드 + PDF 아티팩트) 3개 job.
- 권고 2: `.agents/archive/`에 CURRENT_STATE·VALIDATION_METRICS 원본 전문 보존 후
  라이브 파일을 최신 스냅샷/현행 게이트만으로 재작성. 정책은 OPERATING_SYSTEM.md에 명문화.
- 권고 4: `~/.codex/skills` 48종을 `.agents/skills/`로 미러 (벤더 `.system` 제외,
  비밀정보 스캔 통과). VALIDATION_METRICS의 `C:/Users/...` evidence 경로 수정.
- 이식성: `check_citation_coverage.py`(순수 표준 라이브러리) 신설로 PowerShell 스니펫
  대체, paper/README.md에 이식 가능한 `tectonic` 표준 빌드 명령 명시.
- 정리: `validate_robotics_foundations.py`의 ruff F841 1건 제거.
- **보류(의도적)**: 권고 3(마커→안정 키 전환)은 원고 텍스트 수정과 전체 재빌드 검증이
  필요한 대규모 변경이라 이번 패스에서 제외. 압축 패스에 앞서 별도 이터레이션으로
  수행할 것. 권고 5(리뷰 원문 보존)는 다음 리뷰 패스부터 적용 권장.

## 7. 재검토 트리거

다음 중 하나가 발생하면 이 평가를 갱신한다.

- CI가 main에서 1주 이상 red로 방치될 때
- 압축 패스 착수 전(마커→안정 키 전환 선행 여부 결정)
- 스킬 정의가 바뀌었는데 repo 미러와 불일치할 때
- CURRENT_STATE.md가 다시 500줄을 넘을 때
