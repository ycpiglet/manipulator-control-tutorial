# User Actions & Decisions (사용자 결정·행동 필요 항목)

Updated: 2026-07-05 (KST)
자율 루프에서 분리된, 사용자만 할 수 있거나 사용자 결정이 필요한 항목.
에이전트는 초안·조사까지 준비하고 여기서 멈춘다.

## A. 발송 필요 (초안 준비됨 — 아래 첨부)

| # | 대상 | 목적 | 상태 |
|---|---|---|---|
| A1 | 한국로봇학회(KROS) 편집위원회 | 총설(리뷰) 유형 게재 가능 여부 + 독립연구자 소속 표기 + 회원/심사료 안내 | 초안 ↓ |
| A2 | IEEE CSM Editor-in-Chief | 임피던스 튜토리얼 기사 사전 문의(pre-submission inquiry) | 초안 ↓ (영문) |
| A3 | JOSE 편집팀(필요 시) | 공개 이력 요건(레포 공개 2026-06-26) 적용 여부 | 초안 ↓ (영문) — 우선 공식 문서 재확인 후 필요 시만 발송 |

## P. 포트폴리오 패키지 (Track C — 전부 무료, 3분 내외)

| # | 항목 | 방법 | 효과 |
|---|---|---|---|
| P1 | Zenodo DOI 발급 | zenodo.org GitHub 로그인 → 레포 토글 ON → GitHub 릴리스 생성 (`.agents/PORTFOLIO_PACKAGE.md` 절차) | 레포가 인용 가능한 영구 학술 산출물이 됨. DOI 알려주면 배지·CITATION.cff 반영 대행 |
| P2 | 블로그 게시 | `outreach/blog_failure_gallery_ko.md` 를 velog/tistory/GitHub Pages 등에 게시 | 초보자 도달 + "설명 능력" 포트폴리오. 플랫폼 정하면 포맷 조정 대행 |
| P3 (선택) | engrXiv/EdArXiv 프리프린트 | U3(한국어) 또는 U5(영문) 완성본 업로드 (무료 DOI) | 무게이트 "첫 단독 논문" 경험 |

## B. 결제·가입 필요

| # | 항목 | 시점 |
|---|---|---|
| B1 | KROS 회원 가입 + 연회비 (공동저자 전원) | KROS 투고 직전 (A1 회신 후) |
| B2 | (해당 시) MDPI APC CHF 1,800 예산 승인 | U5 투고 시점 (12월~2027 Q1) |

## C. 결정 대기

| # | 결정 | 기본값 (미결정 시) |
|---|---|---|
| C1 | 해외 본편 SCIE 필수 여부 | MDPI Robotics (비SCIE)로 진행 |
| C2 | 실패 사례의 1인칭 서사 수위 | "저자가 실제 로봇에서 겪은 실수" 익명 일반 서사 (현재 적용됨) |
| C3 | README 언어 구조 | 한국어 README.md 유지 + README.en.md 병행 (2026-07-05 적용됨) |
| C4 | JOSE 논문 저자 표기 | `jose/paper.md`의 TODO-AUTHOR-NAME / TODO-ORCID — 출판용 실명(영문)과 ORCID 필요. 없으면 ORCID 무료 발급(orcid.org) 권장 |

## 발송 최종본 (2026-07-06 다듬음 — 복사해서 그대로 발송 가능)

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

### 발송 순서 권고

A3(JOSE)를 먼저 — 회신이 오면 U1 투고가 그날 가능. A1(KROS)은 같은 날 발송
권장(회신까지 수 주 걸릴 수 있음). A2(CSM)는 여유 있게 — U5 착수는 10월.

## 처리 로그

- 2026-07-06: C4 해소 — Youncheol Jung / 정윤철 / ORCID 0009-0000-5282-881X /
  Independent Researcher. jose/paper.md, u3_main.tex 반영.
- 2026-07-06: C1 확정 — SCIE 불요, 무료 우선. U5 1차 = IEEE CSM(무료),
  MDPI는 승인 후 최후 옵션.
- 2026-07-06: C2 확정 — 익명 유지.
- 2026-07-06: B2 갱신 — MDPI APC는 무료 경로 소진 후에만 재상정.
- 2026-07-06: A1~A3 발송문 다듬기 요청 접수 — 채널 조사 후 최종본 제공 예정.
