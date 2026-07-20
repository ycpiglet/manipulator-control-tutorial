# Desktop App Bugfix Pass — 사용자 실사용 버그 3건 (2026-07-20)

Reported: 사용자 실사용 스크린샷 5장 (2026-07-19 밤, 데스크톱 앱 첫 실사용)
Method: 로컬 재현 → 조사 워크플로(조사 2 + 적대 검증 2, 전부 CONFIRMED) → 수정 → 실앱 e2e 재검증

## 1. 버그와 원인

| # | 증상 | 근본 원인 | 수정 |
|---|---|---|---|
| 1 | 한글 폰트 깨짐 (굵은 텍스트가 다른 글자로: 자동 데모→잭댑 덕뫌, Lab01→Labrs) | Windows DirectWrite가 번들 가변 폰트(NotoSansKR[wght])의 글리프 인덱스를 특정 웨이트에서 오매핑. 오프스크린(FreeType)은 정상 → 엔진 문제로 특정 | `qt_fonts.configure_font_environment`: win32에서 `QT_QPA_PLATFORM=windows:fontengine=freetype` 기본값 (QGuiApplication 생성 전) |
| 2 | Lab01 씬에 스프링 2개, 하나는 허공에 부유 | PR #32가 scene.xml에 넣은 정적 장식 geom(spring_visual_1..4, damper_body/rod)과 어댑터의 동적 오버레이가 중복. 정적 쪽은 worldbody 고정이라 블록을 안 따라감. lab02도 댐퍼 동일 | scene.xml 정적 장식 geom 삭제 (lab01 6개, lab02 2개). 물리 영향 0 (contype=0, 삭제 전후 궤적 비트단위 동일) |
| 3 | 1번 완료해도 다음으로 진행 안 됨 | 3중 원인: (a) 완료(복습) 화면에 '다음 시작' 액션 부재 — 유일한 버튼이 '저장 결과 보기'(막다른 길), (b) 완료 후 '실험 다시 시작'류 조작 시 새 세션이 PAUSED로 주차되어 모든 시작 진입점이 영구 비활성, (c) 실행 저장 루트(PROJECT_ROOT/outputs 하드코딩)와 진행률 읽기 루트(default_outputs_root)가 MCLAB_DATA_DIR/frozen 번들에서 불일치 → 완료가 집계 안 됨 | (a) 복습 화면에 '다음 실험 시작' primary 버튼 + 결과 페이지 헤더 버튼(ResultsHeader.qml), (b) qt_lifecycle에 defer_start_for_parked_session/consume_pending_next_scenario — 주차 세션은 자동 종료(증거 보존) 후 다음 시작, (c) logging/batch의 저장 루트를 default_outputs_root()로 통일 |

부수 수정: 평형점 표식 0.72w→0.57w(위치 0 매핑 — 이전엔 도달 불가능 위치), lab02 스프링 라벨/도식 게이팅(전 시나리오 stiffness 0), `qt_available`을 readiness.py로 이동(모듈 800줄 게이트).

## 2. 검증 (Gate | Threshold | Measured | Evidence)

| Gate | Threshold | Measured | Evidence |
|---|---|---|---|
| 폰트 렌더링 (windows 플랫폼) | 한글 전건 정상 | 수정 전 깨짐 재현 → 수정 후 정상 (env 없이 코드 기본값만으로) | 스크린샷 3장 (before/freetype/after) |
| 씬 물리 무영향 | 삭제 전후 궤적 동일 | lab01 2s 시뮬 qpos 동일, ngeom 13→7 | 오프스크린 프로브 + 렌더 PNG (스프링 1개, 블록 추적) |
| 주차 세션 → 다음 시작 | 함정 상태에서 1클릭 전진 | 완료→다시시작(주차)→start_next → 세션 교체 확인(트레이스 session_id) + 실앱 화면 "직접 조작 · 예측 대기" | 백엔드 트레이스 + e2e 스크린샷 |
| 저장/진행률 루트 일치 | 동일 루트 | MCLAB_DATA_DIR 하에 저장·집계 모두 임시 루트, done 1/12·nextId=interactive-pull | 매니페스트 + course_progress_payload 직접 계산 |
| 전체 테스트 | 0 failed, cov ≥80% | 439 passed + 1088 subtests, 81.51% | pytest -q --cov=mclab --cov-fail-under=80 |
| 린트 | 0건 | All checks passed | ruff check src tests |
| 모듈 크기 게이트 | app*.py ≤800줄, *.qml ≤400줄 | 전건 통과 (qt_fonts.py/ResultsHeader.qml 신설로 해소) | test_application.py 게이트 테스트 |

## 3. 남긴 것 (후속)

- lab03 1D 시나리오 라이브 뷰 마커 부재(리플레이와 불일치), 질량 블록 라벨 3D 투영 오차, docs 스크린샷 스테일 — 별도 작업 칩으로 분리 (Low)
- ExplorePage 카드의 launchBlocked는 보수적 정책 유지 (주차 세션 시 카드 비활성)
- 새 회귀 테스트: 주차-디퍼 행동 테스트, 출력 루트 계약 테스트, 폰트 설정 소스 핀, 다음 버튼 소스 핀
