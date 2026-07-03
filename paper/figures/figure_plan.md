# 그림 계획

이 파일은 임피던스 튜토리얼 논문에 들어가는 그림의 의도와 구현 상태를 기록한다. 그림은 장식이 아니라, 글만으로 붙잡기 어려운 관계를 한눈에 보이게 하는 설명 장치이다.

## 그림 1. 임피던스 개념 지도

**시각적 목적:** 임피던스 개념이 통신선 신호 왜곡에서 RLC 회로, 기계적 임피던스, 로봇 접촉 제어, MuJoCo 실험실로 이어지는 흐름을 보여준다.

**권장 형태:** 작은 대응 설명을 포함한 좌우 방향 개념 타임라인.

**내용 명세:**

- `긴 전보선/전화선`
- `복소 임피던스`
- `RLC의 에너지 저장과 소산`
- `기계적 질량-스프링-댐퍼 임피던스`
- `가상 끝단 임피던스`
- `MuJoCo Lab01-Lab04`

각 단계는 하나의 안내 질문을 포함한다.

- 저항 하나만으로는 왜 부족한가?
- 에너지는 어디에 저장되거나 소산되는가?
- 주어진 힘에 대해 얼마나 움직이는가?
- 강성과 감쇠는 접촉을 어떻게 바꾸는가?

**캡션 초안:** 이 튜토리얼은 임피던스를 하나의 교육용 경로로 따라간다. 긴 통신선의 신호 왜곡은 중요한 역사적 동기이지만, 이 그림은 완전한 연대기가 아니라 개념 지도이다. 위상, 에너지 저장, 에너지 소산이라는 같은 언어는 이후 기계적 임피던스와 로봇 끝단 접촉 거동을 설명하는 데에도 쓰인다.

**구현 메모:** `paper/figures/fig_impedance_roadmap.tex`에 추가됨. 구현된 캡션은 이 그림이 완전한 역사 연대기가 아니라고 명시한다.

**배치:** `paper/sections/01_introduction.tex`의 `이 글의 읽는 순서` 뒤.

**상호참조 대상:** `fig:impedance-roadmap`

## 그림 2. 작용 변수, 흐름 변수, 일률

**시각적 목적:** 포트 비유를 보이게 한다. 작용 변수와 흐름 변수의 곱은 일률이고, 임피던스는 작용 변수를 흐름 변수로 나눈 관계이다.

**권장 형태:** 화살표가 있는 3행 포트 다이어그램 또는 비교표.

**내용 명세:**

| Domain | Effort | Flow | Power | Impedance |
|---|---|---|---|---|
| Electrical | `v` | `i` | `p=vi` | `Z=V/I` |
| Translational mechanical | `f` | `xdot` | `p=f xdot` | `Z=F/V_x` |
| Single-axis rotation | `tau` | `omega = theta_dot` | `p=tau omega` | `Z_r=T/Omega` |

다자유도 로봇 관절에서는 스칼라 나눗셈으로 쓰지 않는다. `p_q = tau^T qdot` 및 `Laplace{tau(t)}=Z_q(s) Omega_q(s)`처럼 벡터/행렬 관계로 표시한다.

에너지를 소산하는 요소와 저장하는 요소를 시각적으로 구분한다.

**캡션 초안:** 임피던스는 선택한 포트 부호 규약에서 작용 변수와 흐름 변수 사이의 비율이다. 두 변수의 곱은 시간영역의 순간 일률이므로, 전기회로, 기계진동, 로봇 접촉에서 같은 구조를 볼 수 있다.

**구현 메모:** `paper/figures/fig_effort_flow_power.tex`에 추가됨. 구현된 그림은 기계 흐름 변수로 `xdot`을 중심에 두고, 다자유도 로봇 관절은 스칼라 표 행에 억지로 넣지 않고 캡션에서 설명한다.

**배치:** `paper/sections/02_impedance.tex`의 `힘, 흐름, 일률` 논의 근처.

**상호참조 대상:** `fig:effort-flow-power`

## 그림 3. 주파수에 따라 달라지는 기계적 임피던스

**시각적 목적:** 기계적 임피던스가 단순한 강성 하나가 아니며, 주파수에 따라 지배적인 항이 달라진다는 점을 보여준다.

**권장 형태:** 정성적 로그 주파수 그래프.

**내용 명세:**

- x-axis: angular frequency `omega`
- y-axis: impedance contribution magnitude
- curves:
  - spring contribution `k/omega`
  - damping contribution `b`
  - mass contribution `omega m`
- callouts:
  - low frequency: spring-dominated
  - middle: damping influence and reactive cancellation near the natural-frequency region
  - high frequency: mass-dominated

**캡션 초안:** 질량-스프링-댐퍼 시스템에서 운동을 방해하는 겉보기 성질은 주파수에 따라 달라진다. 느린 운동에서는 스프링 효과가, 빠른 운동에서는 관성 효과가 커지고, 감쇠는 운동 전반에서 에너지를 소산한다. 이 그림은 전체 임피던스 크기가 아니라 개별 항의 크기를 보여주며, 스프링 항과 질량 항은 반응성 성분에 반대 부호로 들어간다.

**구현 메모:** `paper/figures/fig_mechanical_impedance_frequency.tex`에 추가됨. 구현된 캡션은 개별 항 크기와 전체 $|Z_m(j omega)|$를 구분한다.

**배치:** `paper/sections/05_mechanical_system.tex`의 기계적 임피던스 유도 뒤.

**상호참조 대상:** `fig:mechanical-impedance-frequency`

## 그림 4. 질량-스프링-댐퍼의 에너지 교환

**시각적 목적:** 진동을 단순한 왕복 운동이 아니라 에너지 교환으로 설명한다.

**권장 형태:** 두 패널 그림.

**내용 명세:**

Top panel:

- cart, spring, damper
- three snapshots:
  - maximum displacement: elastic potential energy high, kinetic energy low
  - crossing equilibrium: kinetic energy high, elastic potential energy low
  - after damping: total energy reduced

Bottom panel:

- time traces for `T(t)`, `U(t)`, and `E(t)=T(t)+U(t)`
- compare undamped and damped total energy with subtle line style difference

**캡션 초안:** 질량-스프링-댐퍼 시스템의 자유진동은 운동 에너지와 탄성 퍼텐셜 에너지의 교환이다. 감쇠가 있는 자유응답에서는 `b xdot^2`의 일률로 에너지가 소산되므로 전체 기계 에너지가 줄어든다.

**구현 메모:** `paper/figures/fig_msd_energy_exchange.tex`에 추가됨. 구현된 캡션은 `b xdot^2`를 에너지가 아니라 소산 일률로 다룬다.

**배치:** `paper/sections/05_mechanical_system.tex`의 에너지 교환 논의 뒤.

**상호참조 대상:** `fig:msd-energy-exchange`

## 그림 5. 감쇠비 응답 아틀라스

**시각적 목적:** 초심자가 감쇠비가 오버슈트, 진동, 정착을 어떻게 바꾸는지 볼 수 있게 한다.

**권장 형태:** 정규화된 단위계단 응답의 작은 다중 그래프.

**내용 명세:**

- responses for `zeta = 0`, `0.2`, `0.7`, `1.0`, and `> 1`
- same target line
- `\pm2\%` settling band
- labels:
  - overshoot
  - settling time
  - critical damping
  - overdamped response
- keep `m` and `k` fixed and vary `b`

**캡션 초안:** 표준 2차 질량-스프링-댐퍼 모델의 정규화된 단위계단 응답에서 `m`과 `k`를 고정하고 `b`를 바꾸면 감쇠비 `zeta`와 응답 모양이 달라진다. 낮은 감쇠는 진동과 오버슈트를 만들고, 임계감쇠는 비진동 응답의 경계이며, 과감쇠 예시는 더 느리게 수렴할 수 있다.

**구현 메모:** `paper/figures/fig_damping_ratio_atlas.tex`에 추가됨. 구현된 그림은 하나의 겹친 그래프 대신 작은 다중 그래프를 쓰고, `zeta=1.5`를 구체적인 과감쇠 예시로 표시하며, 자유응답이 아니라 정규화된 단위계단 응답임을 밝힌다.

**배치:** `paper/sections/05_mechanical_system.tex`의 `오버슈트와 정착시간의 의미` 근처.

**상호참조 대상:** `fig:damping-ratio-atlas`

## 그림 6. 직교 임피던스 제어 블록도

**시각적 목적:** 직교 임피던스 제어가 위치/속도 오차를 힘으로 바꾸고, 그 힘을 다시 관절 토크로 변환하는 흐름을 보여준다.

**권장 형태:** 제어 블록도.

**내용 명세:**

- inputs:
  - desired position `x_d`
  - measured position `x`
  - measured velocity `xdot`
- block 1: virtual spring-damper
  - `e = x - x_d`
  - `f_cmd = -K_d e-D_d xdot`
- block 2: Jacobian transpose
  - `tau_cmd = J_v(q)^T f_cmd`
- block 3: robot plus environment
  - output `x`, `xdot`
  - external force `f_ext`
- visually separate task space from joint space

**캡션 초안:** 직교 임피던스 제어는 작업공간 운동 오차에서 가상 스프링-댐퍼 힘을 계산한 뒤, 자코비안 전치를 이용해 그 힘을 관절 토크로 변환한다. 따라서 이 제어기는 위치만 명령하는 것이 아니라 힘과 운동 사이의 관계를 설계한다.

**구현 메모:** `paper/figures/fig_cartesian_impedance_block.tex`에 추가됨. 구현된 그림은 `e=x-x_d`, `f_cmd=-K_d e-D_d xdot`, 병진 자코비안 `J_v(q)^T`를 사용한다. `f_ext`는 환경이 로봇에 가하는 힘으로 표시하고, 정지 목표 가정 `xdot_d=0`을 밝힌다. 전체 운영공간 역동역학, 중력 보상, 토크 제한, 자세 임피던스는 의도적으로 생략했다.

**배치:** `paper/sections/06_impedance_control.tex`에서 `기본 아이디어` 뒤의 단순판 또는 `관절 임피던스와 직교 임피던스` 앞의 완성판.

**상호참조 대상:** `fig:cartesian-impedance-block`

## 그림 7. 가상 퍼텐셜 에너지와 방향별 강성

**시각적 목적:** 강성 행렬이 목표점 주변의 에너지 지형을 만든다는 점을 보여준다.

**권장 형태:** 힘 화살표가 있는 두 패널 등고선 그림.

**내용 명세:**

왼쪽 패널:

- 등방 강성 `k_x = k_y`
- 원형 등고선
- 변위와 반대쪽을 향하는 힘 화살표 `f_k=-K_d e`

오른쪽 패널:

- 이방 강성 `k_x < k_y`
- 길게 늘어난 타원 등고선
- 음의 에너지 기울기로 나타나는 방향별 복원력 화살표
- 설명선: 길게 늘어난 등고선 방향이 더 부드러운 방향
- 주의: 이방 강성에서는 힘 화살표가 보통 에너지 등고선에 수직이며, 항상 목표점을 정확히 향하지 않을 수 있음
- 접촉 좌표계 주의: 법선 방향은 부드럽고 접선 방향은 단단하게 하는 예시는 강성 행렬이 해당 접촉 좌표계에서 표현되었거나 그 좌표계로 회전되었다고 가정함

**캡션 초안:** 강성 행렬은 가상 퍼텐셜 에너지 지형의 모양을 정한다. 등방 강성은 모든 방향에서 같은 복원 거동을 만들고, 이방 강성은 한 방향은 부드럽고 다른 방향은 단단하게 만들 수 있다.

**구현 메모:** `paper/figures/fig_virtual_potential_stiffness.tex`에 추가됨. 구현된 그림은 오차 좌표 `e_x,e_y`를 쓰고, 등고선을 같은 힘이 아니라 같은 가상 퍼텐셜 에너지로 표시한다. 등방 원형 등고선과 이방 타원 등고선을 구분하며, 표시한 힘은 로봇 끝단에 작용하는 가상 복원력이라고 설명한다. 캡션은 끝단을 그 위치에 붙잡기 위해 필요한 외력이 반대 부호임을 덧붙인다.

**배치:** `paper/sections/06_impedance_control.tex`의 `가상 퍼텐셜 에너지와 감쇠` 뒤.

**상호참조 대상:** `fig:virtual-potential-stiffness`

## 그림 8. 결정론적 가상 벽 비교

**시각적 목적:** Lab04 가상 벽 데모를 강성, 감쇠, 침투 깊이, 벽 힘과 연결한다.

**권장 형태:** 세 패널 그림.

**내용 명세:**

Panel 1:

- end-effector point
- wall position `x_wall`
- penetration `delta = max(0, x - x_wall)`
- wall force direction

Panel 2:

- time response for penetration or end-effector position
- compare soft, stiff, and damped settings

Panel 3:

- wall force versus penetration
- use wall-force magnitude `|f_wall|` rather than signed `f_wall`
- slope indicates `k_wall` when `xdot = 0`
- annotation distinguishes stiffness slope from velocity-dependent damping effect

**캡션 초안:** 결정론적 가상 벽은 접촉을 단순한 스프링-댐퍼 관계로 표현한다. 벽 강성은 침투 깊이에 따라 힘이 얼마나 빠르게 커지는지를 정하고, 벽 감쇠는 접촉 순간의 튕김과 진동을 줄인다.

**구현 메모:** `paper/figures/fig_virtual_wall_comparison.tex`에 추가됨. 구현된 그림은 1차원 벽 기하와 침투 깊이, 낮은/높은 감쇠의 침투 응답, 부드러운/단단한 벽에서의 `|f_wall|` 대 `delta` 관계를 세 패널로 보여준다. 부호 혼동을 줄이기 위해 세 번째 패널은 힘의 크기를 쓰고, 캡션에서는 논문의 부호 규약에서 부호 있는 벽 힘이 `-x` 방향임을 설명한다.

**배치:** `paper/sections/06_impedance_control.tex`의 가상 벽 논의 근처에 두고, MuJoCo 실험실 논의에서도 다시 참조한다.

**상호참조 대상:** `fig:virtual-wall-comparison`

## 그림 9. 경로, 궤적, 사다리꼴, S-curve

**시각적 목적:** 경로(path)는 공간에서 지나는 길이고, 궤적(trajectory)은 그 길에 시간표를 붙인 것이라는 차이를 한눈에 보여준다. 동시에 사다리꼴 속도 프로파일과 S-curve에서 속도, 가속도, 저크가 어떻게 다르게 보이는지 초심자가 플롯으로 읽게 한다.

**권장 형태:** 네 패널 개념도.

**내용 명세:**

- Panel 1: 공간 경로 `x-y`, 시작 `s=0`, 끝 `s=1`
- Panel 2: 서로 다른 시간 스케일링 `s(t)` 두 개
- Panel 3: 사다리꼴 속도와 계단형 가속도, 전환점의 jerk 피크
- Panel 4: S-curve 속도와 완만한 가속도 변화

**캡션 초안:** 경로는 공간에서 지나는 길이고, 궤적은 그 길에 시간표를 붙인 것이다. 같은 경로라도 시간 스케일링이 다르면 속도, 가속도, 접촉 순간의 힘 피크가 달라진다. 사다리꼴 속도 프로파일은 단순하지만 이상적인 형태에서는 가속도가 구간 경계에서 점프하므로 저크가 크게 나타난다. S-curve는 저크 크기를 제한해 가속도 변화를 더 부드럽게 만든다.

**구현 메모:** `paper/figures/fig_path_trajectory_profiles.tex`에 추가됨. 구현된 그림은 경로와 시간 스케일링을 분리해서 보여주고, 사다리꼴 속도와 S-curve를 속도/가속도 플롯으로 비교한다.

**배치:** `paper/sections/05b_robotics_foundations.tex`의 `Trapezoidal, S-curve, 그리고 jerk` 설명 뒤.

**상호참조 대상:** `fig:path-trajectory-profiles`

## 그림 10. 2링크 IK branch

**시각적 목적:** 같은 손끝 목표점에 도달하는 두 역기구학 해가 실제로는 다른 팔꿈치 위치와 다른 branch 선택을 뜻한다는 점을 보여준다. 특히 팔꿈치 위쪽/아래쪽이라는 말이 좌표계와 관례에 의존하므로, `q2` 부호 또는 signed side로 branch를 명시해야 한다는 점을 초심자가 눈으로 확인하게 한다.

**권장 형태:** 한 좌표계에 두 2링크 자세를 겹쳐 그린 개념도와 작은 해석 카드.

**내용 명세:**

- shoulder at `(0,0)`
- target at `(1,1)`
- positive branch:
  - elbow `(1,0)`
  - `(q1,q2)=(0, pi/2)`
  - signed side `x_d e_y-y_d e_x=-1`
- negative branch:
  - elbow `(0,1)`
  - `(q1,q2)=(pi/2, -pi/2)`
  - signed side `x_d e_y-y_d e_x=+1`
- dashed shoulder-target line
- note that both branches produce the same FK target but different elbow positions

**캡션 초안:** 2링크 팔에서 같은 목표점 `(1,1)`에 도달하는 두 가지 IK branch이다. `q2>0`인 해와 `q2<0`인 해는 손끝 위치는 같지만 팔꿈치 위치와 어깨--목표선에 대한 signed side가 다르다. 따라서 팔꿈치 위쪽/아래쪽이라는 말은 좌표계와 그림 관례에 의존하며, 실험이나 코드에서는 `q2`의 부호 또는 signed side로 branch를 분명히 정의하는 편이 안전하다.

**구현 메모:** `paper/figures/fig_two_link_ik_branches.tex`에 추가됨. 구현된 그림은 기존 paper TikZ 스타일에 맞춰 같은 좌표계 위에 두 branch를 겹쳐 그리고, 오른쪽 카드에서 손끝 동일성, 팔꿈치 차이, branch 정의 caveat를 설명한다.

**배치:** `paper/sections/05b_robotics_foundations.tex`의 2링크 IK 숫자 예제 뒤.

**상호참조 대상:** `fig:two-link-ik-branches`
