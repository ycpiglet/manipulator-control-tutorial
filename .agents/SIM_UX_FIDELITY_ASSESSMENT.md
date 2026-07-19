# Simulator UI/UX · 원고 충실도 · 자유도 · 편의성 · 사용자친화성 평가

> **범위 주의 (2026-07-19 추록):** 본 평가의 측정은 PR #32(Qt 데스크톱 앱,
> ko/en 이중언어 UI, 단일 인스턴스, 인프로세스 실행) **머지 이전** 상태를
> 대상으로 한다. 머지로 §4의 교차 요인 중 언어 불일치(데스크톱 앱은 한국어
> 지원)와 백로그 B(단일 창)가 앱 경로에서 해소되었고, F2 메뉴 미노출은
> 같은 날 후속 커밋으로 해소(카드 70→72). Tk 메뉴 경로의 A/C는 잔존 —
> 현황은 `.agents/UX_IMPROVEMENTS.md` 상태 추록 참조.

Assessed: 2026-07-19 (KST)
Assessor: Claude Code — 5차원 측정 에이전트 + 차원별 적대적 검증 에이전트(총 10 에이전트, 읽기 전용)
방법: 모든 수치는 재현 명령 또는 파일:라인 근거 필수. 검증 단계에서 수치 재현·갭 반증을 시도해
수정 18건을 본 문서에 반영했고, 갭 오탐(false positive)은 0건이었다(과거 감사 오탐률 ~1/3 대비 개선).
기준선: `.agents/PAPER_SIM_MATURITY_ASSESSMENT.md`(2026-07-03), `.agents/UX_IMPROVEMENTS.md`(2026-07-07).
기준선 이후 73커밋(`git log --oneline --since='2026-07-03 23:59'`).

## 1. 결론 요약

| 차원 | 점수 /5 | 한 줄 판정 |
|---|---:|---|
| 원고 충실도 (paper–sim 정합) | **4.8** | 인용 40/40 무모순 + 앵커 136/136 기계 강제 + CI 3-job — 사실상 최상급 |
| 자유도 | **4.0** | 폭은 넓고(키 21~75/랩, 제어 ~9계열×궤적 5종×플랜트 3단) 발견 가능하나, 스윕·확장 지점 부재 |
| 시뮬레이터 UI/UX | **3.5** | 구조(GUI 메뉴·라이브 튜닝·학습 루프)는 4~5점급, 실사용 마찰 3종 미해결 + 표면 언어 불일치가 감점 |
| 편의성 | **3.5** | 진입(2단계, 44MB)은 5점급, 반복 사용 루프(버튼 딜레이·창 중복·반복 불가) 마찰 미해결 |
| 사용자친화성 | **3.5** | 교수설계 골격은 우수, 인터랙티브 표면 한글 0자 + 안전 간판 실습(F2) 메뉴 미노출이 감점 |

산술평균 3.86/5. 요약: **콘텐츠와 정합성(원고↔시뮬레이터)은 공개 수준으로 성숙**했고,
남은 감점은 거의 전부 세 가지 교차 요인 — ① 2026-07-07 사용자 피드백 백로그 A/B/C 미구현(사용자 결정 대기 상태),
② 학습자 인터랙티브 표면의 언어 불일치(한글 0자), ③ 안전 북극성 실습(F2)의 메뉴 미노출 — 에 수렴한다.

## 2. 공통 게이트 (이번 세션 실측)

| Gate | Threshold | Measured | Evidence |
|---|---|---|---|
| pytest 전건 통과 | 0 failed | 342 passed + 765 subtests, 55.1 s (기준선 340/760 대비 +2/+5) | `$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m pytest -q` |
| ruff 린트 | 0건 | All checks passed (기준선의 .agents 1건도 해소) | `.venv\Scripts\python.exe -m ruff check .` |
| CLI 스모크 | exit 0 | exit 0, 하위명령 14종 | `.venv\Scripts\python.exe -m mclab --help` |
| main CI | green | 최신 run success (07-07~07-11 red 3건은 #30에서 수복, red 구간에도 paper job은 전건 green) | `gh run list --branch main` + failed run job별 조회 |

## 3. 차원별 상세

### 3.1 시뮬레이터 UI/UX — 3.5/5

| 지표 | 측정값 | 판정 | 근거 |
|---|---|---|---|
| 루트 원클릭 런처(.cmd) | 20개 (START_HERE + 랩별 13 + 배치 6) | PASS | Glob *.cmd |
| 학습자 메뉴 | Tkinter GUI(5,309줄), 시나리오 카드 70개(Lab01 6/Lab02 10/Lab03 30/Lab04 24) + 배치 6, 총 버튼 약 835개 | PASS | learner_menu.py:206-1047, 4394-4922 (배분·총계는 검증자 수치) |
| 학습 경로 안내 | 12단계 LEARNING_PATH + 단계별 완료 조건 추적 + 'Run next' + 경험 커버리지 7타깃 + 리뷰 큐 | PASS | learner_menu.py:258-343, 139-147 |
| CLI 하위명령 | 14종 (list/menu/doctor/coverage/path/next/review/scenarios/params/batches/index/clean/run/batch) | PASS | cli.py:128-238 |
| 랩별 라이브 슬라이더 | Lab01 3 / Lab02 5 / Lab03 4~8 / Lab04 4~9 | PASS | 각 lab의 SliderSpec 전수 |
| 패널 실시간 상태 표시 | Lab01 4 / Lab02 5 / Lab03 최대 9 / Lab04 최대 13 필드 | PASS | lab04_panda.py:363-394 (검증자 수치) |
| 공통 런타임 컨트롤 | 4/4 랩: 리셋·일시정지/스텝·재생속도·A/D 키 외란·튜닝 프리셋 19개(YAML 정의) | PASS | interaction.py:953-1174 |
| doctor 진단 | 6항목, 항목별 OK/WARN/FAIL + Fix + 다음 단계 8줄 | PASS | doctor.py:24-74 |
| `--quick`(빠른 실행) | 없음 — 메뉴 버튼 1회 = 항상 풀 파이프라인(시뮬+플롯+리포트+브라우저) | GAP | cli.py:221-236, learner_menu.py:1050-1085 |
| `--loop`(자동 반복) | 없음 — `while data.time < sim_time` 후 정지, 리셋도 data.time 미초기화라 연장 불가 | GAP | runner.py:22, one_dof.py:52-64 |
| 단일 뷰어 창 | 미구현 — 클릭마다 새 Popen, 이전 프로세스 추적/종료 0건 | GAP | learner_menu.py:1088-1096 |
| 뷰어 내 수치 오버레이 | 없음(3D 마커만) — 수치는 별도 Tk 패널 창 | WARN | mujoco_utils.py:161-230 |
| 학습자 표면 한국어 | 0자 (src/mclab 전체 + docs 4종; 플롯 라벨·리포트 포함) | GAP | `grep '[가-힣]' src/mclab docs` = 0 |

강점: 진입 장벽 최소(원클릭+가드), 4개 랩 동일 인터랙션 문법("움직이며 튜닝" 북극성 직결),
예측→관찰→증거 루프가 interaction_events.json으로 저장되어 메뉴/CLI가 학습 증거를 되짚음.
감점: 2026-07-07 실사용 피드백 잔여 3종(A/B/C) 전부 미구현(0/3), 표면 언어 불일치, 첫 화면 과밀(Low).

### 3.2 원고 충실도 — 4.8/5

| 지표 | 측정값 | 판정 | 근거 |
|---|---|---|---|
| 기준선 37개 참조 재검증 | 37/37 전건 일치 (config 경로 4+4, 신호명 9, 산출물 10, 키 4, 액추에이터 2, Lab04 데모 4) | PASS | 범주별 grep/ls/find 재실행 |
| 기준선 이후 신규 인용 | 3/3 실재 (F2 갤러리 2 + impedance_wall) — 원고 전체경로 인용 7건 MISSING 0 | PASS | 06_impedance_control.tex:1618-1619 등 |
| \vmark 앵커 | 136개(기준선 85 → +51), 중복 0, 검증기 등록 136/136 | PASS | grep + validate_robotics_foundations.py 대조 |
| 검증기 체크포인트 | 36개 함수 (manuscript_* 20 + 수치/파생 16) | INFO | 검증자 재분류 수치 |
| 원고 인쇄 수치 기계검증 | 3건 일치: 벽 평형 3.3cm/8.6N=260×0.033, 출발값 500 N/m, F2 50J/10m/s/13배 | PASS | tex ↔ checkpoint 산술 대조 |
| CI 논문 게이트 | 3-job: simulator(ruff+pytest cov≥80) / paper-gates(인용+수식/마커) / paper-build(Tectonic+PDF>100KB), push·PR 강제 | PASS | .github/workflows/ci.yml |
| 원고 stale 주장 | 0건 — config 수·테스트 수·설치 크기를 하드코딩하지 않아 드리프트 내성 | PASS | grep 무매치 |
| PDF ↔ 기록 정합 | 122쪽 / 1,002,110 B / SHA-256 29E47B3F… = CURRENT_STATE 기록과 전문 일치 | PASS | pypdf + Get-FileHash |
| 파생본 앵커 오염(G6) | 0건 (u3_kros/u5_en/u7_kroc) | PASS | grep vmark paper/derivatives |
| CURRENT_STATE 최신성 | 헤더 2026-07-06, PR #26-31(런처·경량화·clean·red 수복) 미반영 | WARN | CURRENT_STATE.md:3 |

갭(전부 Low, 정합성 훼손 아님): CURRENT_STATE 스냅샷 지연, kinetic/potential_energy 컬럼명이 원고에
한국어 개념어로만 등장(다른 7개 신호는 컬럼명 병기 — 비대칭), 07-07~07-11 main red 이력(paper job은 무결).

### 3.3 자유도 — 4.0/5

| 지표 | 측정값 | 판정 | 근거 |
|---|---|---|---|
| 시나리오 config | 74개 (lab01 8 / lab02 10 / lab03 31 / lab04 25; 기준선 72 → F2 2건 추가) | PASS | find configs |
| 튜너블 leaf 키 | 랩별 21/32/75/52 (메타 키 제외; 검증자가 실제 YAML 파서로 재현) | PASS | 파서 재계수 |
| 제어 방식 계열 | 약 9계열 (수동 MSD~PID~관절/작업공간 PD~DLS~조건수 인지 DLS~위치서보 가상벽), 별칭 mode 문자열 허용 | PASS | lab03_2dof.py:58-61, lab04_panda.py:82-179 |
| 궤적 유형 | 5종 (step/trapezoidal/minimum_jerk/quintic/s_curve) — 3개 랩 공용 + lab01 힘 입력 3종 | PASS | trajectories/__init__.py:26-63 |
| 플랜트 사다리 | 1자유도×2 / 2자유도 / Panda 7+그리퍼2 | PASS | models/, Menagerie |
| 임의 YAML 경로 | `mclab run <lab> --config <경로>` 지원 + `mclab params/scenarios/batches` 발견 명령 | PASS | cli.py:223, 171-199 |
| 튜닝→재현 루프 | 라이브 튜닝 종료 시 learner_tuned_config.yaml 저장 + 재실행 명령줄 출력 | PASS | cli.py:800-811 (검증자 발견 가산 요인) |
| 파라미터 스윕/오버라이드 | 없음 — 배치는 하드코딩 5세트, `--set`류 플래그 부재 (워크플로는 YAML 복사-수정) | GAP(Medium) | batch.py:67, cli.py:238-247 |
| 제어기/궤적 확장 지점 | 없음 — controllers/impedance.py·joint_pd.py·task_space_pd.py는 2줄 스텁, 레지스트리 부재, 궤적 if-체인 | GAP(Medium) | 스텁 3파일 전문, trajectories/__init__.py:63 |
| 모델 교체 경계 | Panda 7+2 하드코딩(qpos[7]/[8], home_q=7, ctrl[7]) — 논문 7장이 한계를 정직 서술 | INFO(Low) | lab04_panda.py:79, 91-92, 504-513, 861-866 |
| 슬라이더 범위 | 코드 리터럴 고정 — 자유도 제한이자 초보자 안전 가드 | INFO | SliderSpec 전수 |

주의: "config 74개"를 자유도 폭으로 읽으면 과대평가(동일 mode의 파라미터 변형 다수) —
실질 폭 지표는 키 수(21~75/랩)와 mode 계열 수(~9)다.

### 3.4 편의성 — 3.5/5

| 지표 | 측정값 | 판정 | 근거 |
|---|---|---|---|
| 첫 시뮬까지 수동 단계 | 2회 (START_HERE.cmd 더블클릭 → 메뉴 버튼 1회), 설치 중 프롬프트 0회 | PASS | START_HERE.cmd:12-27 |
| 설치 다운로드 | Menagerie 실측 44MB (기준선 2.3GB 대비 ~52×; README 고지와 일치), sparse 실패 시 full shallow clone 폴백 | PASS | `du -sm third_party/mujoco_menagerie` = 44 |
| 설치 실패 가드 | 전 런처 단일행 가드, 테스트로 강제 (PR #30 회귀를 이 테스트가 적발) | PASS | tests/test_launch_scripts.py:60-70 |
| 런처 커버리지 | 20개 — 4개 랩 전부 단일+인터랙티브+배치 (lab01 3/lab02 3/lab03 5/lab04 6 + 유틸 3) | PASS | Glob + 테스트 (lab04는 검증자 수치 6종) |
| 산출물 관리 | 실행별 타임스탬프 폴더+충돌 회피, `mclab clean` 기본 20개 보존+확인 프롬프트, 리포트/인덱스 자동 열기 | PASS | logging.py:17-36, cli.py:1152-1194 |
| 백로그 C(버튼 딜레이) | 미구현 — 버튼 1회=풀 파이프라인. 부분 완화: essential 플롯 프리셋, batch --no-plot, 비hands-on 시나리오는 headless 명령 추천 | GAP(Medium) | learner_menu.py:1070-1085, 1143-1159 |
| 백로그 A(자동 반복) | 미구현 — 수동 리셋조차 data.time 미초기화(마찰이 문서 서술보다 오히려 큼) | GAP(Medium) | runner.py:22, mujoco_utils.py:139-158 |
| 백로그 B(단일 창) | 미구현 — Popen 핸들은 상태 표시용 감시 스레드에만 사용 | GAP(Medium) | learner_menu.py:5192-5226 |
| 크로스 플랫폼 | 원클릭은 Windows 전용(.sh 0개) — 비Windows는 영문 README 수동 경로 1줄 | WARN(Low) | README.en.md:107-108 |
| 학습자 설치 범위 | `pip install -e .[dev]`로 pytest/mypy/ruff까지 설치 — 학습자·개발자 경로 미분리 | INFO(Low) | bootstrap_and_run.py:112 |

판정 구조: 진입 경험은 4.5~5점급, 주 사용 루프의 마찰 3종이 매 사용마다 반복되는 비용이라 3.5.
단 A/B/C는 UX_IMPROVEMENTS.md:54에 "사용자가 우선순위/동작을 정하면 착수"로 명시된 의도적 보류 상태.

### 3.5 사용자친화성 — 3.5/5

| 지표 | 측정값 | 판정 | 근거 |
|---|---|---|---|
| 인터랙티브 표면 한국어 | 0자 (src/mclab 41개 .py + docs 4종 — 메뉴·가이드·리포트·워크시트·doctor·오류 메시지·플롯 라벨 전부 영어) | GAP(High) | [가-힣] 문자 카운트 = 0 |
| 온보딩 문서 언어 | README.md 한글 9,145자(한국어 퀵스타트+사용자 가이드) / README.en.md 별도 | PASS | wc + 문자 카운트 |
| 학습 가이드 | config별 74개(8/10/31/25) + 랩 폴백 4 — focus/try/change/watch/next 구조 | PASS | RUN_GUIDES import (배분은 검증자 수치) |
| 진행 추적 | 12단계 코스 + 5 마일스톤 + 7체험군 커버리지(각각 다음 실행 명령 포함) | PASS | course_progress.py, experience_coverage.py |
| 안전 경고(학습자 표면) | 6+건 (README ⚠️행, F2 가이드 10 m/s 스파이크, 리포트 안전 예산 제안 등) — 단 메뉴·docs에는 0건 | WARN | README.md:32, learning_guides.py:540-555, reporting.py:349-353 |
| 안전 콘텐츠(논문) | 실패 갤러리 F1/F2/F3 + 재현 config + 수치 검증 + 튜닝 순서 원칙("안전 한계 먼저, 작은 값부터, 한 번에 하나") + 오독 교정 표 | PASS | 06:1580-1652, 07:360-375 |
| F2 config 메뉴 노출 | 미노출 — MENU_ACTIONS 70개에 f2 0건. 메뉴만 쓰는 초심자는 안전 간판 실습을 못 만남 | GAP(Medium) | MENU_ACTIONS import 검사 |
| 트러블슈팅 | README 한 5건 + 영 5건 + doctor 6검사(Fix 문구 포함) | PASS | README.md:608-614 |
| 오류 메시지 | 샘플 3/3이 원인+해결 행동 제시(전부 영어) | PASS | learner_menu.py:2876-2911 |
| 용어 도입 | 논문 부록 용어 길찾기 2표 18행. DLS는 시뮬레이터 표면에서 풀어쓰나 impedance·Jacobian conditioning은 미정의 사용 | WARN(Low) | A_notation_checklist.tex:20-70 |
| 선행 조건 정직성 | "Python 3.10 이상뿐" 최상단 명시 + doctor 실검사 + 44MB·소요시간 사전 고지 | PASS | README.md:14,76 |
| README 가독성 | 한국어 문단 5,000자 초과 5개(최장 5,662자) — 기능 나열형 | INFO(Low) | awk length 측정 |

## 4. 교차 종합 — 점수를 깎는 3대 요인

1. **UX 백로그 A/B/C 미구현 (UI/UX·편의성·자유도 3개 차원 공통 감점).** 4개 소스(코드 4곳·git 이력·기록 문서)
   교차 검증으로 확정. 단 "방치"가 아니라 UX_IMPROVEMENTS.md에 "사용자가 우선순위/동작을 정하면 착수"로
   기록된 결정 대기 상태이며, 같은 07-07 피드백 5개 증상 중 2개(설치 2.3GB→44MB, outputs 비대→clean)는 해소됨.
2. **언어 불일치 (사용자친화성 High, UI/UX Medium).** 북극성 독자(한국어 일반인)가 README를 지나
   도구를 켜는 순간부터 만나는 모든 표면이 영어(한글 0자). 한국어는 README(9,145자)와 논문에만 존재.
3. **안전 북극성 간판 실습(F2)의 메뉴 미노출 (Medium).** F2 위험판/안전판 config 쌍은 실재하고
   가이드·리포트·README에는 등록됐으나, 주 진입 경로(START_HERE→menu)의 카드 70개에는 없음.

## 5. 권장 다음 행동 (우선순위순 — 착수는 사용자 결정)

1. **백로그 A/B/C 우선순위·동작 확정** — 기존 기록의 권고( C-(1) 빠른 실행 → A 자동 반복 → B 단일 창 )
   그대로 유효. 특히 C는 "체감 개선 가장 큼, 위험 낮음".
2. **학습자 표면 한국어화(단계적)** — 1단계 메뉴 카드 라벨·가이드 74종, 2단계 리포트/워크시트,
   3단계 오류 메시지·doctor. 사용자친화성 3.5→4.5의 최대 지렛대.
3. **F2 실패 갤러리 2종을 메뉴 카드로 노출** — 소규모 변경으로 안전 북극성 직결 갭 해소.
4. **CURRENT_STATE.md 스냅샷 갱신** — PR #26-31 반영(기록 위생, 다음 감사의 오독 방지).
5. (중기) 파라미터 스윕/`--set` 오버라이드, controllers/ 빈 스텁 정리(삭제 또는 실제 플러그인화),
   원고에 kinetic/potential_energy 컬럼명 병기.

## 6. 재현 명령 (핵심)

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe -m pytest -q                     # 342 passed + 765 subtests, 55.1 s
.venv\Scripts\python.exe -m ruff check .                  # All checks passed
.venv\Scripts\python.exe -m mclab --help                  # exit 0, 하위명령 14종
git log --oneline --since='2026-07-03 23:59' | Measure-Object -Line   # 73
```

```bash
grep -rn '[가-힣]' src/mclab docs                          # 0건 (언어 갭)
grep -o '\\vmark{[^}]*}' paper/sections/*.tex | wc -l      # 136 (전건 검증기 등록)
grep -rn 'quick\|loop' src/mclab/cli.py                    # 백로그 A/C 플래그 부재
du -sm third_party/mujoco_menagerie                        # 44 (MB)
find configs -name '*.yaml' | wc -l                        # 74
```

검증 수정 반영 내역(요지): 메뉴 카드 배분 30/24(←33/21), 가이드 배분 31/25(←33/23), 메뉴 그룹 6/10/30/24,
lab04 런처 6종(←7), Lab04 상태필드 최대 13(←11), 체크포인트 분류 20+16(←18+18), 부록 용어표 18행(←20),
"한국어는 논문뿐" 서술 기각(README.md는 한국어 온보딩), src/mclab 커밋 수 명령 기준 명확화(--since 07-03 23:59),
백로그 C 명칭은 '버튼 딜레이'(--quick은 개선안 C-(1)), 튜닝-리플레이 저장 기능은 자유도 가산 요인으로 추가.
