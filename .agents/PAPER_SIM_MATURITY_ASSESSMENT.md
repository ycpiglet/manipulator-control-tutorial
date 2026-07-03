# Paper–Simulator Correlation And Maturity Assessment

Assessed: 2026-07-03 (KST)
Assessor: Claude Code (read-only measurement pass; no simulator source, config, or paper text edited)
Scope: `paper/` 원고와 `src/mclab` 시뮬레이터 사이의 상호관련성 검증 + 양쪽 성숙도의 측정 가능한 지표 평가

## 1. 결론 요약

| 평가 대상 | 판정 | 근거 요약 |
|---|---|---|
| 논문–시뮬레이터 상호관련성 | **강한 양방향 결합, 검증 가능한 참조 37/37 일치 (100%)** | 논문이 언급한 config 파일, 로그 신호명, 산출물 파일명, 설정 키, 액추에이터 구성이 모두 코드에 실재 |
| 시뮬레이터 성숙도 | **L4 / 5 (외부 공개 준비 단계)** | 테스트 340건 전건 통과, src 린트 0건, 재현 가능한 72개 config, 문서 완비. CI·커버리지 측정 부재로 L5 미달 |
| 논문 성숙도 | **L3 / 5 (내부 검증 완료된 초안)** | 빌드/인용/수식 게이트 전부 통과, 다중 에이전트 리뷰 이력 축적. 단 git 미추적, 저자 미정, 압축 패스 미실시로 L4 미달 |

성숙도 레벨 정의(이 문서에서 사용하는 5단계 기준):

- L1 개념 스케치: 실행/빌드가 불완전
- L2 동작하는 초안: 실행/빌드는 되지만 검증 게이트 없음
- L3 내부 검증 완료: 측정 가능한 게이트를 전부 통과하고 기록이 남음
- L4 외부 공개 준비: 제3자가 재현·검토 가능한 상태(버전관리, 문서, 자동검증 포함)
- L5 공개/출판 완료: 배포(패키지/CI) 또는 심사·출판 절차 완료

## 2. 상호관련성 검증 (paper → simulator 참조 실재성)

논문 본문(특히 `paper/sections/07_mujoco_lab_design.tex`, 초록, 결론)이 언급하는
시뮬레이터 요소를 코드에서 역추적한 결과이다. 전 항목 일치.

| 범주 | 논문에서 언급 | 코드 실재 여부 | 판정 |
|---|---|---|---|
| Config 파일(경로 명시) | `configs/lab03_2dof/{step,trapezoidal,minimum_jerk,s_curve}.yaml` | 4/4 존재 | PASS |
| Config 파일(이름 언급) | `condition_aware_dls_{slow,fast}_command_2dof.yaml`, `wall_{slow,fast}_approach.yaml` | 4/4 존재 | PASS |
| 로그 신호/컬럼명 | `force_virtual_0`, `force_virtual_spring_0`, `force_virtual_damping_0`, `tau_cmd_*`, `current_proxy_*`, `wall_retreat_cm`, `target_wall_gap_m`, `kinetic_energy`, `potential_energy` | 9/9 존재 (`src/mclab/labs/lab04_panda.py` 25회, `lab01_msd.py`, `lab03_2dof.py`, `batch.py`) | PASS |
| 실행 산출물 파일명 | `config.yaml`, `log.csv`, `states.npz`, `summary.json`, `plots/*.png`, `report.html`, `worksheet.md`, `interaction_events.json`, `learner_snapshot.json`, `learner_tuned_config.yaml` | 10/10 존재 (`sim/logging.py`, `sim/reporting.py`, `learner_menu.py`, `cli.py`) | PASS |
| 설정 키 이름 | Lab01 `stiffness`/`damping`, Lab02 `kp`/`ki`/`kd`, Lab03 `task_kp`/`task_kd`, Lab04 `virtual_wall.stiffness`/`virtual_wall.damping` | 4개 랩 키셋 전부 YAML에 실재 | PASS |
| 액추에이터 서술 | Lab03 "torque-actuated", Lab04 "position 계열 actuator (Menagerie Panda)" | Lab03 모델 `<motor>` 6개; Lab04는 `third_party/mujoco_menagerie/franka_emika_panda/scene.xml`의 position-servo `<general>` (kp=4500/kv=450 계열) | PASS (2/2) |
| Lab04 핵심 데모 4종 | 기준 자세 유지, 관절공간 추종, 작업공간 도달, 가상 벽 | `neutral_hold.yaml`, `joint_pd.yaml`+`trajectory_tracking.yaml`, `cartesian_reach.yaml`, `impedance_wall.yaml` | PASS (4/4) |

합계: **37/37 검증 가능 참조 일치.**

구조적 결합 근거(정성):

- 논문 4개 랩 장(Lab01–Lab04) ↔ 시뮬레이터 4개 랩 모듈(`src/mclab/labs/lab01_msd.py`–`lab04_panda.py`) 1:1 대응.
- 논문이 언급한 궤적 프로파일(step/trapezoidal/minimum-jerk/s-curve) ↔ `src/mclab/trajectories/` 5종 구현(quintic은 논문 미언급 여분).
- `.agents/VALIDATION_METRICS.yaml` 하나에 `code_quality`(시뮬레이터)와 `paper_tutorial`(논문) 게이트가 공존하고, `lab04_panda` 수치 임계값(침투 ≤ 5 cm, 벽 힘 ≤ 80 등)이 논문 7장의 플롯 읽기 지침과 같은 신호를 가리킨다.
- 역방향(simulator → paper): `docs/*.md` 4종과 `learning_guides.py`가 논문의 임피던스/DLS 개념 어휘를 사용. 단 learner menu, course progress, doctor, coverage CLI 등 학습 워크플로 기능은 논문에 요약만 등장(간극이 아니라 범위 차이로 판정).

주의(범위 한정이 정확한 지점): 논문 스스로 Lab04를 "position actuator + DLS 목표 후퇴 기반 교육용 데모이며 토크 기반 운영공간 임피던스 검증이 아니다"라고 한정하고 있고, 코드 구현도 실제로 그 범위와 일치한다. 과대 주장 불일치는 발견되지 않았다.

## 3. 시뮬레이터 성숙도 지표 (측정값)

| 지표 | 측정값 | 측정 방법 | 판정 |
|---|---:|---|---|
| 테스트 통과 | 340 passed + 760 subtests, 0 failed (146.6 s) | `.venv\Scripts\python.exe -m pytest -q` | PASS |
| 린트 (src/tests) | 오류 0건 | `python -m ruff check .` (전체 1건은 `.agents/validation/validate_robotics_foundations.py:933` F841 미사용 변수 — 시뮬레이터 외부) | PASS |
| CLI 스모크 | exit 0 | `python -m mclab --help` | PASS |
| 부트스트랩 검증 | exit 0 | `python scripts/bootstrap_and_run.py --verify` | PASS |
| 소스 규모 | src 25,155 LOC / tests 12,531 LOC (39 src 모듈, 21 테스트 파일) | `wc -l` | — |
| 테스트/소스 비율 | 0.50 | 12,531 / 25,155 | 양호 |
| 실험 재현 자산 | config 72개 (lab01 6, lab02 10, lab03 31, lab04 25), 모델 XML 4벌 + Menagerie Panda | `find configs -name "*.yaml"` | 양호 |
| 문서 | 랩 문서 4종(442줄) + README(약 120 KB) + AGENTS.md | `wc -l docs/*.md` | 양호 |
| 개발 이력 | 총 452 커밋 (2026-06-26 ~ 2026-07-03), src 관련 443, tests 관련 448 | `git rev-list --count` | 활발 |
| 테스트 커버리지 | **미측정** (pytest-cov 미설치) | `importlib.util.find_spec('pytest_cov')` → False | GAP |
| CI 파이프라인 | **없음** (`.github/` 부재) | 저장소 루트 확인 | GAP |
| 패키지 배포 | pyproject.toml 존재, 배포 이력 없음 | — | GAP (교육용 로컬 도구로는 허용) |

판정: **L4.** 로컬 재현·검증·문서화는 공개 수준이나, 커버리지 수치와 CI 자동화가 없어 L5(배포 완료)에는 미달.

## 4. 논문 성숙도 지표 (측정값)

| 지표 | 측정값 | 측정 방법 | 판정 |
|---|---:|---|---|
| PDF 산출 | 118쪽, 961,187 bytes | SHA-256 `75EA71A0AE0F967A39C29EB65DF5D8967FAB16CC84869A7BF6E7C4CF7A0D99AD`가 최신 기록 스냅샷(`.agents/CURRENT_STATE.md`)과 일치 | PASS |
| 원고 규모 | 소스 6,667줄, 약 14,060어절(한국어 공백 기준), 본문 10개 장 + 부록 1 | `wc -l`, `wc -w` | — |
| 표/그림 | 표 63개, TikZ 그림 11개 (11/11 본문에서 사용) | `grep -c 'begin{table}'`, `\input` 대조 | PASS |
| 인용 무결성 | `\cite` 33회, 고유 키 29개, BibTeX(31)·출처 목록(31)에 29/29 존재 = 커버리지 100%, 누락 0 | 키 추출 후 `comm` 대조 | PASS |
| 미인용 BibTeX | 2건 (`howell2022predictivesampling`, `mistry2011operationalspace`) — 의도적 보류로 기존 기록과 일치 | 동일 대조 | 허용 |
| 수식/출처 검증 스크립트 | failures 0, exit 0 | `python .agents/validation/validate_robotics_foundations.py` | PASS |
| 리뷰 이력 | 다중 에이전트 리뷰 패스 다수(novice/technical 리뷰어 쌍) + 버전 라벨 `draft-20260703-section6-effort-torque-scope` | `.agents/PAPER_VERSION_LOG.md`, `.agents/CURRENT_STATE.md` | 양호 |
| 버전 관리 | **git 미추적 (paper/ 관련 커밋 0건)** — 이력은 `.agents/PAPER_VERSION_LOG.md` 단일 문서에만 존재 | `git rev-list --count HEAD -- paper` = 0, `git ls-files paper` = 0 | GAP |
| 출판 준비 | 저자 표기 "초안", 소속/투고처 미정, 압축(compression) 패스 미실시, 외부(인간) 심사 이력 없음 | `paper/main.tex`, README 계획 | GAP |

판정: **L3.** 측정 가능한 내부 게이트(빌드, 인용, 수식, 마커, 레이아웃)는 전부 통과하고 기록도 남아 있으나, 원고가 버전관리 밖에 있고 출판 전 단계(압축·저자·외부 심사)가 남아 L4 미달.

## 5. 남은 간극과 권장 다음 행동 (우선순위순)

1. **`paper/`와 `.agents/`를 git에 커밋** — 현재 논문 이력 전체가 워킹트리 유실 시 복구 불가. `.gitignore`가 생성물(PDF, 로컬 논문 캐시)을 이미 걸러내므로 소스만 추적하면 됨. (논문 성숙도 L3→L4의 최소 조건)
2. **pytest-cov 설치 후 커버리지 기준선 측정** — `VALIDATION_METRICS.yaml`의 code_quality 게이트에 커버리지 임계값 추가 가능.
3. **CI(예: GitHub Actions) 도입** — pytest + ruff + (가능하면) 논문 인용 커버리지 체크를 자동화하면 시뮬레이터 L4→L5, 논문 게이트도 회귀 방지.
4. `.agents/validation/validate_robotics_foundations.py:933`의 ruff F841 1건 정리(저위험).
5. 논문 압축 패스와 저자/투고처 확정은 기존 계획(README, CURRENT_STATE의 Next Recommended Action)대로 후속 진행.

## 6. 실행한 측정 명령 (재현용)

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe -m pytest -q                                   # 340 passed, 760 subtests, exit 0
.venv\Scripts\python.exe -m ruff check .                                # 1 error (.agents 내부), src/tests 0
.venv\Scripts\python.exe -m mclab --help                                # exit 0
.venv\Scripts\python.exe scripts/bootstrap_and_run.py --verify          # exit 0
.venv\Scripts\python.exe .agents\validation\validate_robotics_foundations.py  # failures 0
Get-FileHash paper\main.pdf -Algorithm SHA256                           # 75EA71A0... (기록 일치)
```

```bash
# 교차참조 검증: 논문 언급 config/신호/산출물/키를 grep으로 코드와 대조
grep -oh 'configs/[a-z0-9_]*/[a-z0-9_.]*\.yaml' paper/sections/*.tex    # 4건 → 전부 존재
grep -rn "force_virtual_0\|wall_retreat_cm\|target_wall_gap_m\|tau_cmd_\|current_proxy_" src
# 인용 커버리지: 사용 키 29 == bib∩manifest 매칭 29, 누락 0, 미사용 bib 2
# 규모: wc -l (src 25,155 / tests 12,531 / tex 6,667), find configs (72)
# git: rev-list --count HEAD(452) / -- src(443) / -- paper(0)
```
