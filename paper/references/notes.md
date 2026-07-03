# Reference Notes for Manipulator Control Tutorial Paper

이 문서는 `manipulator-control-tutorial` 저장소의 논문/보고서 초안을 위해 모은 레퍼런스 요약입니다. 핵심 논지는 "정밀 산업용 디지털 트윈"이 아니라 "MuJoCo 기반 교육용 로봇 제어 실험실"입니다.

## Recommended Citation Flow

1. 시뮬레이션 기반 로봇 연구/교육의 필요성: `choi2021simulationrobotics`, `collins2021physicsreview`
2. MuJoCo를 선택한 이유: `todorov2012mujoco`, `tassa2020dmcontrol`, `howell2022predictivesampling`
3. 로봇 조작 시뮬레이션 생태계: `zhu2020robosuite`, `zakka2025mujocoplayground`, `xu2024frankamujocoenvs`
4. 제어 이론 배경: `khatib1987operationalspace`, `hogan1985impedancepart1`, `mistry2011operationalspace`
5. IK/특이점/감쇠 최소제곱 배경: `buss2005sdls`, `schinstock1994robustik`
6. 교육용 실험실 설계 근거: `sartorius2006virtualremote`, `hoenig2016seamless`, `dixon2002matlablab`

## High-Priority Papers

### `todorov2012mujoco`

MuJoCo의 원 논문입니다. 이 프로젝트가 같은 물리 엔진과 로깅/플로팅 파이프라인을 공유하는 교육용 실험실이라는 점을 설명할 때 배경으로 필수입니다. PDF는 자동 다운로드하지 못했지만 DOI 메타데이터는 `refs.bib`에 남겼습니다.

### `tassa2020dmcontrol`

MuJoCo 기반 task/control software layer의 대표 사례입니다. 이 저장소가 DeepMind Control Suite처럼 벤치마크를 제공하려는 것은 아니지만, "재현 가능한 config + 실행 + 기록"이라는 소프트웨어 설계 방향을 뒷받침할 때 인용하기 좋습니다.

### `collins2021physicsreview`

로봇 응용에서 물리 시뮬레이터를 비교/검토하는 리뷰입니다. MuJoCo, Gazebo, V-REP/CoppeliaSim 등 여러 선택지 사이에서 교육 목적과 제어 실험 목적을 구분하는 문맥에 유용합니다.

### `khatib1987operationalspace`

운영공간 제어의 고전 논문입니다. Lab03의 task-space Jacobian transpose control과 Lab04의 Cartesian reach/virtual wall 설명에서 "관절공간에서 작업공간으로 제어 관점을 확장한다"는 연결고리로 쓰기 좋습니다.

### `hogan1985impedancepart1`

임피던스 제어의 핵심 고전 논문입니다. Lab04 virtual wall, stiffness/damping comparison, translational impedance demo의 이론 배경으로 가장 직접적입니다.

### `buss2005sdls`

특이점 부근 IK에서 damped least squares와 selectively damped least squares를 설명하는 데 좋습니다. Lab03의 singularity demo 또는 향후 DLS 비교 과제에 바로 연결됩니다.

## Local PDF Cache Set

The downloaded PDFs are a local verification cache.
They should normally stay ignored by git, with DOI/URL metadata kept in `refs.bib` and source status kept in `sources.md`.
This keeps the paper reproducible without accidentally redistributing third-party PDFs.

### MuJoCo and Simulation Ecosystem

- `tassa2020_dm_control.pdf`: MuJoCo 기반 continuous control 소프트웨어 구조.
- `tassa2018_deepmind_control_suite.pdf`: MuJoCo task benchmark 관점.
- `howell2022_predictive_sampling_mujoco_mpc.pdf`: MuJoCo MPC와 real-time behavior synthesis.
- `zakka2025_mujoco_playground.pdf`: 최신 MuJoCo/JAX 기반 robot learning playground.
- `zhu2020_robosuite.pdf`: MuJoCo 기반 robot manipulation benchmark/framework.
- `xu2024_franka_mujoco_envs.pdf`: Franka manipulator MuJoCo 환경. Lab04 Panda 모델 배경과 직접 관련.
- `collins2021_physics_simulators_review.pdf`: 로봇 물리 시뮬레이터 리뷰.

### Manipulator Control

- `khatib1987_operational_space.pdf`: operational space formulation.
- `hogan1985_impedance_part1.pdf`: impedance control theory.
- `mistry2011_operational_space_constrained_underactuated.pdf`: constrained/underactuated operational space control.
- `buss2005_sdls_ik.pdf`: selectively damped least squares IK.
- `schinstock1994_robust_dls_dynamic_weighting.pdf`: damped least squares with dynamic weighting.

### Robotics and Control Education

- `sartorius2006_virtual_remote_lab_manipulator_control.pdf`: manipulator control remote/virtual lab.
- `hoenig2016_seamless_robot_simulation_education.pdf`: robot simulation integration for education.
- `dixon2002_matlab_control_lab.pdf`: undergraduate control laboratory standardization.

## Draft Paper Angle

이 프로젝트는 기존 robot learning benchmark와 다르게 성능 경쟁이나 정책 학습을 목표로 하지 않습니다. 논문에서는 다음 차별점을 강조하면 좋습니다.

- 1D mass-spring-damper에서 2DOF, 6/7DOF manipulator까지 같은 제어 개념을 점진적으로 확장한다.
- 모든 랩이 YAML config, MuJoCo simulation, CSV/NPZ log, plot artifact를 공유한다.
- 실시간 viewer demo와 headless reproducible run을 모두 지원한다.
- Lab04는 산업용 디지털 트윈이 아니라 Menagerie 기반 교육용 manipulator control demo임을 명확히 한다.
- virtual wall은 contact-force extraction보다 먼저 deterministic wall model로 가르치는 설계 선택이다.

## Gaps to Fill Later

- MuJoCo Menagerie 자체는 현재 코드에서 중요하지만, 논문보다는 software/model repository citation으로 다루는 편이 자연스럽습니다.
- Lab03 DLS 비교를 확장한다면 `buss2005sdls`와 `schinstock1994robustik`를 본문에서 더 적극적으로 사용할 수 있습니다.
- 관련연구를 더 강화하려면 "robotics education with open-source simulators" 키워드로 추가 검색할 가치가 있습니다.
- 현재 `refs.bib`에는 고급 MuJoCo/MPC 및 운영공간 제어 관련 논문(`howell2022predictivesampling`, `mistry2011operationalspace`)이 있지만 본문에서는 아직 직접 인용하지 않습니다. 관련연구 절을 확장할 때 쓰거나, 최종 압축 단계에서 제거할지 결정하면 됩니다.
- Ohm, Faraday, Hooke, Newton의 역사 인용은 일차 사료나 안정적인 디지털 도서관/DOI 출처로 교체했습니다. Leyden jar와 damping 용어처럼 튜토리얼 맥락의 보조 설명은 접근성 좋은 교육/오픈 교재 출처를 유지하되, 최종 제출 전에는 필요하면 학술 역사 연구로 한 번 더 보강합니다.
