# Portfolio Package — 0원 포트폴리오 별자리 (Track C)

Created: 2026-07-07 (KST)
목표(사용자 진술): 취업 대박이 아니라 **개인 연구·학습의 경험 + 포트폴리오**.
"단독 논문 작성 경험"을 포함해 여러 무료 매체를 엮는다.
원칙: **정당하면서(non-predatory) 무료**. 무료 그 자체보다 신뢰성이 먼저.

이 트랙은 기존 투고 트랙(`.agents/SUBMISSION_PLAN.md`)과 **병렬 추가**이며,
논문 게재 여부와 무관하게 전부 0원으로 완성 가능한 포트폴리오를 만든다.

## 별자리 구성 (전부 0원)

| 매체 | 상태 | 포트폴리오 가치 | 착수 요건 |
|---|---|---|---|
| GitHub 레포 (본체) | ✅ 완료 | 테스트·CI·문서 갖춘 레포 자체가 최상위 포트폴리오 | 이미 public |
| `CITATION.cff` | ✅ 2026-07-07 추가 | GitHub "Cite this repository" 버튼 활성화 + Zenodo 자동 메타데이터 | 완료 |
| Zenodo DOI | ⬜ 사용자 3분 작업 | 레포를 인용 가능한 영구 학술 산출물로 격상 (CERN 운영, 무료) | 아래 절차 |
| 블로그 글 (실패 갤러리) | ✅ 초안 `outreach/blog_failure_gallery_ko.md` | "설명하는 능력" 증명 + 초보자 도달. 논문보다 넓게 읽힘 | 게시 플랫폼 선택 |
| engrXiv/EdArXiv 프리프린트 | ⬜ 즉시 가능 | 무료 DOI + Google Scholar 색인. U3(한국어)도 바로 가능 | 최종 원고 |
| arXiv 프리프린트 | ⬜ U5 영문화 후 | 게이트키핑 없는 학술 문서 | U5 진행 시 |
| JOSE 논문 | ✅ 패키지 완료 | "단독 논문 게재" 경험 그 자체 (무료·정당) | 저자정보 완료, 투고만 |
| YouTube 실물 데모 | ⬜ 2027 로드맵 | 영상 포트폴리오 (실물 RB-Y1 — 익명 유지) | 실물 데이터 획득 후 |
| KRoC 발표 | ⬜ 2027.2 | "학회 발표" 경험 + 네트워킹 | 마감 공지(감시 봇) |

## Zenodo 연결 절차 (사용자 3분, 1회)

Zenodo는 GitHub 릴리스를 자동으로 아카이빙하고 DOI를 발급한다(무료).

1. https://zenodo.org 에 GitHub 계정으로 로그인
2. 상단 계정 → **GitHub** 설정 → 저장소 목록에서
   `ycpiglet/manipulator-control-tutorial` 토글을 **ON**
3. GitHub에서 **릴리스 생성** (예: 태그 `v0.1.0`, 제목 "First public release").
   릴리스가 만들어지는 순간 Zenodo가 스냅샷을 잡고 DOI를 발급
4. 발급된 DOI 배지를 README와 `CITATION.cff`의 `doi:` 필드에 추가
   (에이전트가 배지 삽입까지 대신할 수 있음 — DOI만 알려주면 됨)

`CITATION.cff`가 이미 있으므로 Zenodo는 저자·제목·라이선스를 자동으로 읽는다.

## 블로그 게시 옵션 (택1 또는 복수)

| 플랫폼 | 특징 |
|---|---|
| velog | 국내 개발자 대상, 마크다운·KaTeX 지원, 도달 좋음 |
| tistory | 범용, SEO 강함 |
| 브런치 | 글 중심, 진입장벽(승인) 있음 |
| GitHub Pages | 레포와 한 몸, 완전 통제, 커밋으로 관리 |
| dev.to / Medium | 영문 버전 게시 시 (U5 영문화 자산 재활용) |

초안(`outreach/blog_failure_gallery_ko.md`)은 플랫폼 독립적 마크다운.
수식은 KaTeX/MathJax 지원 플랫폼(velog, GitHub Pages)에서 그대로 렌더된다.
이중게재 이슈 없음(블로그는 학술 게재물이 아니며, 논문에서 블로그를 인용하거나
그 반대도 무해). 단, KROS/CSM 투고 시 "동일 내용 블로그 선공개" 사실을
커버레터에 한 줄 고지하는 것을 권장(안전).

## 신뢰성 확인 습관 (predatory 회피)

무료·저비용 매체를 새로 고를 때 투고 전 반드시 확인:
- **Think. Check. Submit.** (thinkchecksubmit.org) 체크리스트 통과
- 저널이면 **DOAJ**(doaj.org) 등재 여부, 국내면 **KCI 등재**(kci.go.kr) 여부
- "며칠 내 게재", "심사 없이" 광고하면 회피

(추가 무료 매체 후보는 리서치 결과를 이 문서 하단에 축적)

## 추가 무료 매체 리서치 결과 (2026-07-07, 웹 검증)

### 새로 발굴한 무료 프리프린트 (DOI 포함, 게이트키핑 없음)

| 매체 | 비용 | 주는 것 | 신뢰도 |
|---|---|---|---|
| **engrXiv** (Engineering Archive, OSF 기반) | **무료 + DOI** | 공학 특화 프리프린트, 영구 URL, Google Scholar 색인 | 높음 |
| **EdArXiv** (교육 연구 프리프린트, OSF) | **무료** | 원고의 "교육" 프레이밍에 정합 | 높음 |
| **TechRxiv** (IEEE 프리프린트) | **무료** | IEEE 브랜드 프리프린트 신뢰성 | 중간 (플랫폼 이전으로 일시 접수 중단 — 상태 확인 필요) |
| **Zenodo** (CERN/OpenAIRE) | **무료 + DOI** | 시뮬레이터·PDF 아카이빙, GitHub 릴리스 연동, 소프트웨어 인용성 | 높음 |
| **OSF** | **무료** | 프로젝트 호스팅·DOI (engrXiv/EdArXiv의 기반) | 높음 |
| **Hugging Face** | **무료** | 모델·데이터 카드 호스팅. (구 Papers with Code 기능 흡수) | 높음 |

### 국내 튜토리얼/해설 트랙

- **JKIEES 한국전자파학회 — Tutorial & Review 전용 트랙**: 리뷰/튜토리얼을
  위해 정식으로 마련된 드문 국내 트랙. 초청 기반일 가능성 — 편집국에 해설
  기고 제안 이메일 선행 권장. 게재료·초청 조건 UNVERIFIED.
- **제어로봇시스템학회지 / 전자공학회지 (magazine)**: 논문지(유료)와 별개인
  "학회지(매거진)"는 해설·기술기고를 낮은/무 게재료로 싣는 경우가 많음.
  **초청 기반이므로 편집국 문의 선행.** 금액 UNVERIFIED.

### 주의: 폐쇄·회피 대상

- **Papers with Code — 2025년 중반 폐쇄됨.** 타깃 금지 (트래픽은 Hugging
  Face로 이전).
- **Journal of Robotics and Mechatronics** — APC 무료/유료(~170,000 JPY)
  정보 충돌. 직접 확인 전 회피.
- Beall's list는 중단됨 — 블록리스트 대신 DOAJ/Think-Check-Submit/COPE로 검증.

### Track C에 채택 (사용자 목표 최적합)

1. **Zenodo** — 시뮬레이터+리뷰 PDF에 영구 인용 DOI. 위 절차대로.
2. **engrXiv 또는 EdArXiv** — 무료 DOI 프리프린트로 "첫 단독 논문" 경험을
   0원·무게이트로. arXiv 대안이자 교육 프레이밍에 더 맞음. U3(한국어) 또는
   U5(영문) 어느 쪽도 올릴 수 있음.
3. **Hugging Face** — 시뮬레이터/모델 카드로 발견성 확보 (선택).

## 진행 로그

- 2026-07-07: Track C 착수. CITATION.cff 추가, 실패 갤러리 블로그 초안 작성,
  포트폴리오 별자리 정의. Zenodo/블로그 게시는 사용자 액션(아래).
- 2026-07-07 (야간): 블로그 영문판 완성(dev.to/Medium용), U5-EN 11쪽 완성으로
  P3(engrXiv 프리프린트)가 즉시 실행 가능 상태가 됨 — 영문 원고가 준비됐으므로
  engrXiv 업로드는 OSF 계정 생성+PDF 업로드만 남음(사용자 10분).

## 사용자 액션 (USER_ACTIONS.md에도 연동)

- P1: Zenodo GitHub 연동 ON + 첫 릴리스 생성 (3분) → DOI 알려주면 배지 삽입 대행
- P2: 블로그 플랫폼 선택 + 초안 게시 (원하면 플랫폼별 포맷 조정 대행)
