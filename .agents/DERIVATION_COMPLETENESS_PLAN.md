# Derivation Completeness Plan (유도 과정 완전 분해 계획)

Created: 2026-07-05 (KST)
Owner iteration goal: 초보자(고교생, 대학 신입생, 비전공자)가 원고의 모든 수식
유도를 외부 자료 없이 한 단계씩 따라갈 수 있게 만든다. 논문에서 통상 생략되는
전개 지점(치환, 항 정리, 항등식 사용, 극한/미분 규칙 적용)을 명시적으로 채운다.

## Reader Model (독자 가정)

가정하는 사전 지식:

- 기본 삼각함수 (sin, cos, 덧셈정리는 *가정하지 않음* — 사용 시 명시)
- 단일변수 미분의 개념 (연쇄법칙·편미분은 본문에서 설명된 뒤에만 사용)
- 벡터/행렬의 곱셈 정의 수준의 선형대수

가정하지 않는 지식 (사용하려면 본문에서 도입/유도해야 함):

- 라플라스 변환, 전달함수
- 라그랑주 역학, 가상일의 원리
- 행렬 전치/역행렬 항등식, 특이값 분해
- 복소수 지수 표현, 감쇠비/고유진동수 표준형 유도

## Measurable Metrics (측정 가능 지표)

| ID | Metric | Definition | Threshold |
|---|---|---|---|
| D1 | Major derivation gaps | 연속한 두 display 수식 사이에 외부 지식(위 목록) 없이는 따라갈 수 없는 전개가 본문 설명 없이 존재하는 횟수 | 감사 후 High 심각도 0건 |
| D2 | Symbol-first-use coverage | 기호가 정의보다 먼저 사용되는 건수 | 0건 (신규 수정 범위 내) |
| D3 | Numeric check coverage | 핵심 결과식(라벨 있는 식) 중 숫자 대입 예시가 붙은 비율 | 수정 대상 식 100% |
| D4 | Existing gates | LaTeX compile, 페이지 수 확인, validate_robotics_foundations.py, citation coverage, CI | 전부 pass |

Gap 심각도 정의:

- **High**: 가정하지 않는 지식이 유도의 필수 단계인데 본문에 전개가 없음 → 초보자 진행 불가
- **Medium**: 2단계 이상 대수 전개 생략 → 짧은 브리지 문장/중간식으로 해결 가능
- **Low**: 한 단계 생략이지만 처음 보는 독자가 머뭇거릴 수 있음

## Audit Scope and Agent Assignment

| Agent | Files | Focus |
|---|---|---|
| Auditor A | `02_impedance.tex`, `03_lti_system.tex` | 임피던스 정의, LTI 표준형, 라플라스/주파수 응답 유도 |
| Auditor B | `04_electric_system.tex`, `05_mechanical_system.tex` | 회로 방정식, 기계 시스템 운동방정식 유도 |
| Auditor C | `06_impedance_control.tex` + `05b` 잔여 확인 | 임피던스 제어 법칙, 데카르트 임피던스, DLS 유도 |

각 감사자는 read-only로 다음 표를 반환한다:

```text
줄번호 | 식 라벨/문맥 | Gap 유형(D1/D2/D3) | 심각도 | 생략된 단계 | 제안 수정
```

## Iteration Loop (매 반복 공통 절차)

1. **Intake/Plan**: 이 문서의 backlog에서 최고 심각도 항목 선택 (한 번에 하나의 주 목표)
2. **Implement**: 유도 브리지 삽입 — 기존 prose 삭제 금지(additive-first), `\vmark` 앵커 보존/추가
3. **Validate**: Tectonic 컴파일 exit 0, 경고 0, 페이지 수 기록, `validate_robotics_foundations.py` exit 0, 신규 checkpoint 등록
4. **Review**: novice(초보자 관점) + technical(수학적 정확성) 이중 리뷰
5. **Record**: `PAPER_VERSION_LOG.md` 버전 라벨, `CURRENT_STATE.md` 스냅샷, 이 문서의 backlog 상태 갱신, 커밋
6. **Compound**: 반복된 실수/발견 패턴은 이 문서의 Lessons에 축적

## Backlog (audit 결과로 채움)

Auditor A (02_impedance, 03_lti_system) 완료 2026-07-05. 주요 항목:

| # | Section | Item | Severity | Status |
|---|---|---|---|---|
| A1 | 03 (171-180) + 02 (527-542, 84-89, 517-522) | 라플라스 미분 규칙 \(\mathcal{L}\{\dot{x}\}=sX(s)\), \(\mathcal{L}\{\ddot{x}\}=s^2X(s)\)가 유도/도입 없이 사용됨 — 3장에 부분적분 기반 유도(또는 명시적 규칙 소개) 추가 후 2장에서 상호 참조 | High | open |
| A2 | 02 (218-220) | 전신방정식의 편미분 기호가 도입 없이 등장 — 직관 설명 + "물리적 의미만 잡으면 됨" 명시 | High | open |
| A3 | 03 (341-346) | 최종값 정리가 적용 조건 설명 없이 제시 — 수렴 조건 경고 + 숫자 예제 | High | open |
| A4 | 03 (292-301) | \(|H(\jj\omega)|\), \(\angle H\) 복소수 크기/편각 표기 미도입 | High | open |
| A5 | 03 (186-189) | \(s=\sigma+\jj\omega\)에서 \(\jj\), \(\sigma\), \(\omega\) 의미 미명시 | Medium | open |
| A6 | 02 (89, 100-103, 341-345) | 임피던스 식 도출 중간 단계 생략 (MSD→Z_m, 정현파 미분, RLC 직렬 합) | Medium | open |
| A7 | 03 (37-42) | \(i=\dot{q}\) 관계 미명시 | Low | open |
| A8 | 03 (215-217) | 컨볼루션 적분 기호 도입 부족 | Medium | open |

Auditor B (04_electric, 05_mechanical) 완료 2026-07-05. 주요 항목:

| # | Section | Item | Severity | Status |
|---|---|---|---|---|
| B1 | 04 (513-522) | RLC 미분방정식→라플라스 영역 전환에서 변환 규칙 미상기 (A1과 같은 뿌리) | High | open |
| B2 | 05 (789-804) | 근의 공식 결과에 \(b=2\zeta\sqrt{mk}\) 대입해 표준형 근 \(s_{1,2}=-\zeta\omega_n\pm\omega_n\sqrt{\zeta^2-1}\)로 정리하는 대수 전개 생략 | High | open |
| B3 | 05 (808-818) | \(\omega_d=\omega_n\sqrt{1-\zeta^2}\)가 \(\sqrt{\zeta^2-1}=\jj\sqrt{1-\zeta^2}\)에서 나옴을 미명시 | Medium | open |
| B4 | 04 (603-648) | 표준형 계수 비교에서 \(\omega_n\), \(\zeta\) 도출 대수 생략 | Medium | open |
| B5 | 04 (23-36) | 무감쇠 진동 해의 대입 검산 없음 | Medium | open |
| B6 | 05 (917-960) | 오버슈트 공식 숫자 예제, 정착시간 \(\ln 50\) 로그 단계 | Medium | open |
| B7 | 05 (167-527, 다수) | 체인룰/이항/단위 계산 등 한 단계 생략 (Low 묶음) | Low | open |

Auditor C (06_impedance_control, 05b 잔여) 완료 2026-07-05. 주요 항목:

| # | Section | Item | Severity | Status |
|---|---|---|---|---|
| C1 | 06 (605-621) | 작업공간 관성 \(\bm{\Lambda}=(\bm{J}_v\bm{M}_q^{-1}\bm{J}_v^{\mathsf{T}})^{-1}\)이 에너지 대응 유도 없이 제시 | High | open |
| C2 | 06 (1101-1116) | 로봇-환경 직렬 강성에서 접촉력 분배 관계식 \(f=k_d\delta_{\mathrm{robot}}=k_{\mathrm{env}}\delta_{\mathrm{env}}\) 미제시 | Medium | open |
| C3 | 05b (864-874) | 궤적 \(\ddot{\bm{q}}\) 유도에서 곱의 미분 규칙 미명시 | Medium | open |
| C4 | 06 (494-505) | 임피던스 오차 방정식의 \(m_d\) 정규화 중간 단계 생략 | Medium | open |
| C5 | 05b (877-917), 06 (1167-1177) | 직선 경로 2차 미분=0 명시, 시간압축 5/25/125 지수, 감쇠계수 계산 전개 (Low 묶음) | Low | open |

## Iteration 1 Scope (2026-07-05)

단일 주 목표: **High 심각도 격차 전부 제거** — A1(+B1), A2, A3, A4, B2, C1.
Medium 중 같은 문단에 붙은 B3(ω_d)는 B2 수정과 물리적으로 한 덩어리라 포함.
나머지 Medium/Low는 다음 이터레이션.

### Iteration 1 결과 (2026-07-05, version `draft-20260705-derivation-gaps-high`)

수기 검증(감사 결과 원문 대조) 후 판정:

| 항목 | 검증 판정 | 조치 | 상태 |
|---|---|---|---|
| A1+B1 | 확정 High — 라플라스 적분 정의가 논문 전체에 부재(grep 0건) | 03장에 정의 \eqref{eq:laplace-definition} + 곱의 미분 규칙 기반 유도 + 상수함수 검산 + 2계 규칙 2회 적용 + 항별 치환 신설; 02/04장에 항별 치환과 포워드 포인터 | **closed** |
| A2 | 오탐 — 02장 205-212행에 편미분 직관 설명 이미 존재 | 수정 불필요 | closed (false positive) |
| A3 | 오탐 — 03장 338-354행에 수렴 조건·경고·예시 이미 존재 | 수정 불필요 | closed (false positive) |
| A4 | Medium으로 하향 — 의미 설명은 있으나 크기/편각 계산법 미도입 | 03장에 복소수 크기·각도 정의 + H=1-j 예시 추가 | **closed** |
| B2 | 확정 High | 05장에 두 조각 대수 전개(감쇠 조각, 근호 조각) + m=1,b=2,k=4 숫자 검산 추가 | **closed** |
| B3 | 확정 Medium (B2와 한 덩어리) | 05장에 \(\sqrt{-y}=\jj\sqrt{y}\) 일반 규칙 + \(\sqrt{\zeta^2-1}=\jj\sqrt{1-\zeta^2}\) 인수분해 명시 | **closed** |
| C1 | 확정 High | 06장에 힘→가속도 유도(\(\bm{M}_q\ddot{\bm{q}}=\bm{\tau}\), \(\bm{\tau}=\bm{J}_v^{\mathsf{T}}\bm{f}\), 정지 상태 \(\ddot{\bm{x}}=\bm{J}_v\bm{M}_q^{-1}\bm{J}_v^{\mathsf{T}}\bm{f}\)) + 2링크 방향별 유효질량 숫자 검산(x: 0.5 kg, y: 1 kg) 추가 | **closed** |

리뷰: 초보자 리뷰어 Poincare 4건 지적(3건 반영: 정적분 평가 명시, \(\sqrt{-y}\) 미세 단계, 자코비안 전치 상기; 1건 기각: 은유 표현은 취향 문제), 기술 리뷰어 Gauss 6개 검증 항목 전부 CORRECT.

검증: 앵커 15개 checkpoint + 숫자 검산 2건(특성근, 유효질량)을
`validate_robotics_foundations.py`에 추가, 오차 0. 세부 게이트 표는
`.agents/CURRENT_STATE.md` 참고.

남은 backlog: A5-A8, B4-B7, C2-C5 (Medium/Low) — 다음 이터레이션 후보 최우선은
C2(직렬 강성 분배 관계식)와 B4(RLC 표준형 계수 비교), B6(오버슈트 숫자 예제).

### Iteration 2 결과 (2026-07-05, version `draft-20260705-derivation-gaps-medium1`)

| 항목 | 검증 판정 | 조치 | 상태 |
|---|---|---|---|
| C2 | 확정 Medium — 직렬 강성 관계식 부재 | 06장에 \(f=k_d\delta_{\mathrm{robot}}=k_{\mathrm{env}}\delta_{\mathrm{env}}\), 변형 합, 합성 강성 \(f\approx\frac{k_dk_{\mathrm{env}}}{k_d+k_{\mathrm{env}}}\delta_d\) 유도 + 500/500/2cm→5N, 강체 극한→10N 숫자 예시 | **closed** |
| B4 | 부분 확정 — 계수 비교는 이미 단계적, \(\zeta\) 분리 한 단계만 생략 | 04장에 \(\zeta=(R/L)/(2\omega_n)=\frac{R}{2}\sqrt{C/L}\) 4단계 전개 추가 | **closed** |
| B6 | 대부분 오탐 — \(\zeta=0.2/0.7\) 숫자 예시와 \(\ln 50\) 로그 단계 이미 존재; \(M_p(0.7)\) 대입 계산만 미전개 | 05장에 \(\sqrt{0.51}\approx0.714\), \(e^{-3.08}\approx0.046\) 대입 과정 추가 | **closed** |

리뷰: 통합 리뷰어 Euler — 기술 검증 3건 전부 CORRECT, 가독성 FOLLOWABLE,
주변 문단과의 중복 없음(서사→수식 진행 구조 확인).

검증: 앵커 4개(`manuscript_derivation_gap_medium_checkpoint`) + 숫자 검산
2건(`series_stiffness_checkpoint`, `overshoot_formula_checkpoint`) 추가.
교훈: 강체 극한을 유한 대체값(1e9)으로 검사할 때 점근 잔차(~5e-6)를 허용
오차에 반영해야 함 — 첫 실행에서 1e-6 임계값이 이 잔차로 실패했음.

남은 backlog: A5-A8(03장 복소변수 의미, 컨볼루션 적분 도입 등), B5(무감쇠
해 대입 검산), B7/C5(Low 묶음), C3(궤적 곱의 미분 규칙), C4(\(m_d\) 정규화).

### Iteration 3 결과 (2026-07-05, version `draft-20260705-derivation-gaps-medium2`)

| 항목 | 검증 판정 | 조치 | 상태 |
|---|---|---|---|
| A5 | 확정 — \(\jj\)가 02장 첫 사용(s=\(\jj\omega\)) 시점에 미정의 (03장 \(\sigma\), \(\omega\) 의미는 이미 존재) | 02장 첫 사용부에 허수 단위 정의 추가 | **closed** |
| A6 | 부분 확정 — 정현파 속도 미분 단계와 직렬 합 브리지만 부재 (RLC 소자 임피던스 자체는 343-348행에 존재) | \(\dot{x}=-\omega X_0\sin\) 미분 단계 + 직렬(같은 전류, 전압 합) 브리지 추가 | **closed** |
| A7 | 확정 Low | \(i=\dot{q}\), \(\dot{i}=\ddot{q}\) 대응 문장 추가 | **closed** |
| A8 | 오탐(해소됨) — Iteration 1의 라플라스 정의 문단이 적분 기호를 먼저 도입 | 수정 불필요 | closed (resolved by iter 1) |
| B5 | 확정 | 무감쇠 해의 2회 미분 대입 검산 추가 | **closed** |
| C3 | 확정 | \(\ddot{\bm{q}}\) 두 항의 곱의 미분 규칙 기원 설명 추가 | **closed** |
| C4 | 확정 | \(m_d\) 정규화 + 계수 매칭(\(\omega_n^2=k_d/m_d\), \(2\zeta\omega_n=d_d/m_d\)) 브리지 추가, 360행 원 방정식과 일치 확인 | **closed** |

리뷰: 통합 리뷰어 Noether — 7건 전부 CORRECT/FOLLOWABLE, 중복 없음
(\(\jj\) 선행 정의는 후행 언급과 역할이 달라 허용).

검증: 앵커 7개(`manuscript_derivation_gap_medium2_checkpoint`) 추가, 전체
게이트 통과(컴파일 clean, 120페이지 유지, validator failures 0).

**Medium 티어 전체 소진.** 남은 backlog: B7, C5 (Low 묶음 — 한 단계 생략
수준으로 초보자 진행을 막지 않음; 필요 시 후속 이터레이션에서 처리).

## Lessons (compound learning)

- 이전 패스에서 확립: phrase-count 마커는 깨지기 쉬움 → `\vmark` 앵커 사용 (2026-07-05 완료)
- Section 5b의 자코비안 1·2단계와 J^T 유도는 이미 단계 분해 완료 상태 (2026-07-05 감사 확인) — 편미분 계산, 일률 등식, 전치 규칙, 단위 검산, 숫자 예시 모두 존재
- **감사 에이전트의 High 판정은 반드시 원문 대조 후 반영할 것** (2026-07-05):
  Auditor A의 High 5건 중 2건(A2 편미분 직관, A3 최종값 정리 조건)이 오탐 —
  주변 문단에 설명이 이미 존재했음. 오탐 그대로 수정했다면 중복 서술로
  원고 품질이 떨어졌을 것. 반영 전 검증 단계가 루프의 필수 관문.
- 원고에 새로 넣는 숫자 예시는 같은 이터레이션에서 validator의 수치
  checkpoint로도 등록해 기계 검산과 짝을 맞출 것 (2026-07-05:
  `charroot_standard_form_checkpoint`, `effective_mass_direction_checkpoint`).
- 이 세션 환경에는 Poppler/Ghostscript가 없어 페이지 렌더링 검사가 불가 —
  overfull/underfull 0 + additive-only 편집으로 보완하되, 렌더러가 있는
  세션에서는 시각 게이트를 복원할 것.

### Iteration 4 결과 — M3 Low 묶음 (2026-07-06, version `draft-20260706-low-bundle-m3`)

수정 4건 (저비용·고가치만):

| 항목 | 조치 |
|---|---|
| B7 일부: \(b_c\) 양수 근 선택 | 05장에 \(b^2=4mk 	o b=\pm2\sqrt{mk}\), 물리적 양수 근 명시 |
| C5 일부: 직선 경로 2차 미분 | 5b장에 \(x(s)=x_0+s\Delta x\) 2회 미분 한 줄 |
| C5 일부: \(d_d\) 중간 계산 | 06장에 \(\sqrt{500}pprox22.36\) 단계 |
| B7 일부: 커패시터 에너지 | 04장에 \(p_C=Cv\,dv/dt=d(rac{1}{2}Cv^2)/dt\) 스케치 (인덕터와 평행 구조, 중복 아님 확인) |

기각 (사유 기록):

- 시간압축 5/25/125 지수: 이미 본문에 \(\dot{s}\propto1/T\) 등으로 전개되어 있음 (audit 이후 해소)
- 나머지 B7 항목(체인룰 축약, 이항 주석, 적분 더미변수, 삼각형-적분 병행 설명, 댐퍼 일률 대입, \(\dot{E}\) 전개, \(\omega^2\) 분리, 단위 축약, 임피던스 나눗셈): 모두 한 단계 생략이며 주변 문장이 의미를 회복 — 첫 회독 차단 없음, 과잉 전개는 오히려 밀도 저하. **M3 종결.**

리뷰: Gauss-2 — 4건 전부 PASS (문법 흐름, 반올림 정합, 인덕터 유도와의 평행 구조 확인).
