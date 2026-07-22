# User Actions & Decisions (사용자 결정·행동 필요 항목)

Updated: 2026-07-22 (KST)

이 문서는 사용자 결정과 외부 의존성을 기록하는 대기열이다. 항목이 여기에 있다는
사실은 실행 권한이 아니다. 에이전트는 내부 초안·조사까지만 진행하고, 외부 연락,
가입·결제, participant 모집, credential 사용, 공개 게시, release/tag, DOI 발행은
해당 gate와 사용자의 별도 명시적 승인 전에는 실행하지 않는다.

현재 owner의 exact-SHA 위험 수용은 B2 `safe-main` 개발 기준선에만 적용된다.
Public beta, signed distribution, release/DOI publication, real-output cleanup
dry-run, cleanup apply는 승인되지 않았다.

## 현재 결정 대기열

| ID | 필요한 결정 또는 외부 입력 | 현재 기본값 | 선행 gate |
|---|---|---|---|
| UA-01 | 목표 배포 수준과 공식 지원 OS | supervised/source development만 유지 | PKG-01, E2E-01 |
| UA-02 | Windows signing 및 Apple notarization 자격 확보 여부 | 취득·사용하지 않음 | REL-01 뒤 REL-02 |
| UA-03 | 초보자 6명 이상, 교육자 1명, 접근성 검토자와 실제 장비 | 모집·연락하지 않음 | EDU-01, E2E-01 뒤 HUM-01 |
| UA-04 | 첫 prerelease 버전과 공개 지원 채널 | tag/release 생성하지 않음 | G3/REL-01 |
| UA-05 | 외부 license 검토 필요성과 담당자 | 외부 연락하지 않음 | SUP-01 inventory 뒤 LIC-01 |
| UA-06 | Zenodo, preprint, JOSE, KROS/CSM 진행 순서 | 제출·게시·DOI 발행하지 않음 | immutable REL-01 뒤 PUB-01 |
| UA-07 | 실제 learner outputs의 cleanup 계획 검토 | dry-run도 실행하지 않음 | owner 참여 별도 작업 |

## Cleanup 승인 경계

- 실제 learner outputs에 대한 dry-run은 아직 실행되지 않았고 현재 승인도 없다.
- 향후 owner가 별도로 명시 승인하고 참여하는 작업에서만 기본 dry-run을 만들 수
  있다. 원격에는 raw run name이나 사용자 경로를 올리지 않고 inventory hash,
  plan ID, 집계와 제외 사유만 기록한다.
- 같은 exact plan을 owner가 검토한 뒤에도 `--apply`는 자동 승인되지 않는다.
  Owner가 그 plan을 다시 명시적으로 승인해야만 apply가 가능하다.

## 해결된 과거 결정

- 저자 표기: Youncheol Jung / 정윤철 / ORCID
  `0009-0000-5282-881X` / Independent Researcher.
- 해외 본편은 SCIE 필수 아님; 무료 경로 우선, 유료 APC는 별도 승인 전 사용하지 않음.
- 실패 사례의 1인칭 서사는 익명 일반 서사를 유지한다.
- README는 한국어 `README.md`와 영어 `README.en.md`를 병행한다.

## 보존된 발송 초안 — 현재 발송 금지

아래 A1–A3 문안은 2026-07-06에 만든 historical draft다. 주소·정책·원고 수치가
stale할 수 있으며, PUB-01 시점의 공식 정보 재검증과 owner 승인을 거치기 전에는
복사·발송하지 않는다.

### A1. KROS 편집국 → **journal@kros.org** (검증됨: journal.kros.org 안내)

> **제목: [투고 전 문의] 총설(리뷰) 논문 게재 가능 여부 및 독립연구자 투고 절차**
>
> 안녕하세요, 한국로봇학회 논문지 편집국 담당자님.
>
> 임피던스 및 임피던스 제어를 초보자 눈높이에서 다루는 한국어 총설 원고를
> 준비 중인 독립 연구자 정윤철입니다. 원고는 임피던스의 역사적 배경부터
> 전기·기계 임피던스의 기초를 유도 생략 없이 정리한 1부(약 10쪽)로, 공개
> MuJoCo 교육용 시뮬레이터(테스트·CI 포함, Apache-2.0)와 연동되어 모든 수치
> 예제를 독자가 재현할 수 있도록 구성했습니다.
>
> 투고 전에 세 가지를 여쭙고자 합니다.
>
> 1. 로봇학회 논문지에 총설/튜토리얼 성격의 논문 유형이 접수 가능한지요.
>    가능하다면 권장 분량이나 별도 규정이 있는지 안내 부탁드립니다.
> 2. 기관 소속이 없는 독립 연구자의 소속 표기는 어떻게 처리하면 되는지요.
> 3. 투고자 회원 가입 요건과 심사료·게재료의 금액 및 납부 시점을 안내
>    부탁드립니다.
>
> 참고로 전체 유도를 담은 확장판 원고와 시뮬레이터는 공개 저장소
> (https://github.com/ycpiglet/manipulator-control-tutorial)에서 확인하실 수
> 있습니다. 감사합니다.
>
> 정윤철 드림
> 독립 연구자 | ORCID: 0009-0000-5282-881X | ycpiglet@gmail.com

### A2. IEEE CSM 사전 문의 → EIC **Anuradha Annaswamy, aanna@mit.edu** (검증됨: ieeecss.org 편집위 명단; 정식 투고는 css.paperplaza.net)

> **Subject: Pre-submission inquiry — tutorial feature on impedance, from telegraph lines to robot contact control**
>
> Dear Professor Annaswamy,
>
> I am an independent researcher preparing a tutorial-style feature aimed at
> CSM's mission of introducing non-experts to a field. The article traces
> impedance from its historical origin (Heaviside and the distortion problem
> of long telegraph lines) through electrical and mechanical impedance to
> modern robot impedance control, with two distinguishing features: (1) no
> derivation step is skipped — every equation chain is followable by a
> first-year student, and (2) every numeric example is reproducible in an
> accompanying open-source MuJoCo teaching laboratory (tested, CI,
> Apache-2.0), including a "failure gallery" that safely reproduces real
> hardware accidents caused by misconfigured stiffness.
>
> Before preparing a manuscript to CSM's magazine format, I would greatly
> appreciate your guidance on whether this scope fits CSM, and any length or
> structural constraints you would advise. The laboratory and a full-length
> Korean draft are available for inspection at
> https://github.com/ycpiglet/manipulator-control-tutorial.
>
> Thank you for your time.
>
> Youncheol Jung
> Independent Researcher, Republic of Korea | ORCID: 0009-0000-5282-881X

### A3. JOSE 정책 확인 → **admin@theoj.org** (검증됨: jose.theoj.org/about; 대안: github.com/openjournals/jose 이슈)

> **Subject: Eligibility question — public development history requirement**
>
> Dear JOSE editors,
>
> I plan to submit an educational MuJoCo-based robot-control laboratory
> (four graduated labs, pytest+CI, Apache-2.0 code, CC-BY-4.0 content,
> per-config learning guides enforced by the test suite). The repository
> (https://github.com/ycpiglet/manipulator-control-tutorial) was developed
> privately and made public on 2026-06-26. Does JOSE apply a minimum
> public-history requirement similar to JOSS's recent policy, or is the
> submission evaluated on the materials as they stand? Thank you.
>
> Youncheol Jung
> Independent Researcher, Republic of Korea | ORCID: 0009-0000-5282-881X

### Historical sequence note — 실행 지시 아님

과거 초안은 A3, A1, A2 순서를 제안했지만 현재 순서로 사용하지 않는다. PUB-01에서
공식 접수 상태, 연락처, manuscript facts, immutable release identity를 다시 검증한
뒤 owner가 승인한 항목만 발송한다.

## 처리 로그

- 2026-07-06: C4 해소 — Youncheol Jung / 정윤철 / ORCID 0009-0000-5282-881X /
  Independent Researcher. jose/paper.md, u3_main.tex 반영.
- 2026-07-06: C1 확정 — SCIE 불요, 무료 우선. U5 1차 = IEEE CSM(무료),
  MDPI는 승인 후 최후 옵션.
- 2026-07-06: C2 확정 — 익명 유지.
- 2026-07-06: B2 갱신 — MDPI APC는 무료 경로 소진 후에만 재상정.
- 2026-07-06: A1~A3 발송문 초안 정리.
- 2026-07-22: STATE-01에서 A1~A3를 dormant draft로 전환. Release/DOI,
  submission, external contact, real-output dry-run/apply는 승인되지 않음.
