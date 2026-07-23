# 데스크톱 UI/UX 검증 기록

이 문서는 초보자 중심 Qt 앱의 반복 개선 근거를 남긴다. 자동 과업은 실제 사람 베타를
대체하지 않으며, 사람 대상 결과와 구분해 기록한다.

> **2026-07-21 안전 계약 변경:** 아래 2026-07-16 기록의 `삭제`, `영구 삭제`,
> `영구 정리` 표현은 당시 UI와 회귀 기준을 보존한 역사적 증거다. SAFE-01 후보는
> 직접·영구 삭제를 복구 가능한 quarantine과 receipt/restore로 대체한다. 이 문서의
> 과거 측정값을 새 동작의 증거로 해석하지 않는다.

## 2026-07-21 SAFE-01 결과 격리 후보 검증

상태는 **로컬 자동 검증 PASS·독립 검토 scoped local GO, 원격 exact-head
gate 대기**다. SAFE-01은 아직 병합되지 않았으므로 `mclab clean`은 계속 실행하지
않는다. 병합 뒤에도 post-merge required check를 재검증하고 SAFE-01 PASS를
기록하기 전에는 실제 outputs root에 dry-run도 실행하지 않는다. PASS 뒤에도
owner가 같은 dry-run plan을 검토하기 전 `--apply PLAN_ID --yes`를 실행하지
않는다.

| 항목 | 기준 | 로컬 후보 결과 |
|---|---:|---:|
| 결과 관리 관련 Qt 감사 | 지정 관련 case 전부 통과 | 18/18 PASS |
| 언어·확대 | 한국어와 영어 200%에서 confirmation·경고 가독 | PASS |
| 확인 입력 | 잘못된 폴더명은 거부, 정확한 전체 폴더명만 허용 | PASS |
| 포커스·접근성 | 44px 이상 입력, focus ring, 전체 target accessible name, 복귀 | PASS |
| 실행 충돌 보호 | active session/batch/replay/rerun backend guard | PASS |
| 무관한 결과 정리 | batch 중 active 결과는 보호하고 무관한 결과만 격리 | PASS |
| 레이아웃 | 관련 case unnamed·undersized·clipped control | 0 |
| 실제 learner outputs | 테스트 중 변경 | 0 |

성공 동작은 정확히 확인한 결과 폴더를 `.mclab-trash` receipt 아래로 이동하며 UI는
backend 성공을 받은 경우에만 모달을 닫는다. bulk와 single-result 모두 JSON integer
schema-1의 strict terminal manifest만 허용한다. legacy·불완전·실행 중·알 수 없는 상태,
잘못된 확인, preserve marker, stale identity는 fail-closed다. 실제 입력 audit hook은
`MCLAB_SELF_TEST=1`일 때만 활성화되며, QML focus→keyboard text→confirm 경로와 별도의
backend guard probe를 구분해 검증했다. 관련 로컬 JSON과 캡처는 임시 디렉터리에
생성됐고 durable release evidence가 아니므로 3-OS desktop workflow의 Linux Xvfb job에서
PR exact-head 증거를 재생성해야 한다.
Linux 감사 단계는 창 활성화와 Dialog 접근성 역할을 검사할 수 있도록 격리된 Xvfb/X11을
사용하며, 나머지 self-test와 빌드는 offscreen을 유지한다.

18번째 `completed_evidence_retry_keyboard_640_ko` case는 명시 output에서 완료 증거를
저장한 뒤 키보드로 재시작한다. 첫 app instance가 명시 경로를 한 번만 소비하고 재시작은
새 기본 경로를 사용하며, 완료 manifest가 비어 있지 않은 기존 경로에 다시 쓰이지 않는지
검증한다. batch 종료 audit은 저장된 strict terminal 상태가 late cancel 또는 transport
error callback보다 우선하는지도 회귀 테스트로 고정한다.

## 2026-07-23 패키지 독립 E2E 계약

기존 source-tree UI 감사와 startup/course 감사는 개발 회귀를 빠르게 찾지만, 실제
패키지가 checkout 밖에서 작동한다는 G2 증거로 대신 쓰지 않는다. Desktop matrix의
package verifier 다음 단계가 수락된 one-folder와 evidence/archive 폴더를 runner temp의
정확한 `dist/MCLab`, `dist/MCLab-package` 구조로 복사하고, 별도 runtime cwd에서 복사된
실행 파일을 절대 경로로 호출한다. checkout-bound 검증과 복사본의 offline consistency
검증은 완전히 같아야 하며, offline 표시는 새 provenance가 아니다.

Workflow가 사용하는 package-evidence subject는 PR에서
`github.event.pull_request.head.sha`, push와 수동 dispatch에서 `github.sha`다. 이
선택은 job env에서 한 번만 하고 checkout도 같은 값을 사용한다. 이후 lowercase 40-hex,
checkout `HEAD` 일치, clean tree를 확인한 뒤
`build/validation/<selected-sha>/g2-<OS>/package_e2e.json`을
`MCLAB_E2E_EVIDENCE`로 한 번 바인딩한다. Audit의 output과 artifact upload는 이 동일한
경로만 사용한다.

실제 packaged QML startup은 OS별로 새 process와 새 settings/state root를 20번 사용한다.
OS file cache는 비우지 않으며, 이 정의를 evidence의 `cold_definition`에 그대로 남긴다.
실패 0개와 nearest-rank p95(20개 중 정렬 rank 19) 5초 이하를 모두 만족해야 한다.
기준을 넘긴 표본을 버리거나 percentile 방식을 바꾸지 않는다.

전체 course 비교는 UI가 실제 child worker를 시작한 뒤 인증된 progress `1..5`를
수신하는 경로로 실행한다. exact 기준은 batch set 5, scenario run 54, report 6,
comparison plot 5개 이상, manifest 60개와 hash error 0, transient transaction 0,
300초 이하, output 150 MiB 이하, UI heartbeat 최대 gap 500 ms 이하다. terminal
settlement 구간도 heartbeat gap에 포함한다. 별도의 cancel/close probe는 인증된 첫
progress와 child PID가 기록된 ready 파일을 확인한 뒤에만 요청을 보낸다. 각 probe는
strict `stopped` manifest와 batch residue 0을 확인하고, PID와 creation marker로 관찰한
GUI/worker descendant가 10초 안에 모두 사라져야 한다. 강제 종료가 필요하면 해당 case는
실패이며 강제 종료는 실패 기록 뒤 runner 정리 용도로만 수행한다.

패키지 실행 중 만들어지는 run, course output, cleanup fixture, process log와 probe는 모두
runner temp에만 존재한다. cleanup 검증은 Lab01 임시 복사본에 대한 dry-run이고, 정확한
schema-1 plan이 `keep=0`으로 그 synthetic run 하나만 선택해야 한다. exit 0이어도 빈 plan이나
no-op plan이면 실패한다. apply를 호출하지 않으며 실제 `outputs/`를 읽거나 쓰지 않는다. durable 결과는 경로·환경 변수
값을 담지 않는 1 MiB 이하 canonical
`build/validation/<selected-sha>/g2-<OS>/package_e2e.json` 하나뿐이고 90일 보존한다. 이 계약은
workflow와 oracle의 정의이며, 이 문서 변경 자체는 3-OS package 실행 PASS를 주장하지
않는다. 실제 matrix evidence가 없거나 하나라도 실패한 OS는 technical preview 지원
목록에 포함할 수 없다. PASS도 public beta, 서명 배포, release/DOI, 실제 learner-output
cleanup, 또는 사람 대상 UI 검증을 승인하지 않는다. 개별 OS의 PASS나 이 계약만으로
G2 완료 또는 B3 baseline을 선언할 수도 없다.

## 반복 실행

```bash
.venv/bin/python scripts/audit_desktop_ui.py --with-gl --output /tmp/mclab-ui-audit
.venv/bin/python scripts/audit_desktop_ui.py --with-gl --case 'gl_*' --output /tmp/mclab-gl-audit
.venv/bin/python scripts/audit_scene_semantics.py --output /tmp/mclab-scene-audit
.venv/bin/python scripts/audit_app_startup.py --output /tmp/mclab-startup-audit
.venv/bin/python scripts/audit_course_comparison.py --output /tmp/mclab-course-comparison-audit
.venv/bin/python scripts/audit_report_ui.py \
  --report run=/path/to/run/report.html \
  --report batch=/path/to/batch/report.html \
  --report course=/path/to/all_batches/report.html \
  --report index=/path/to/outputs/index.html \
  --output /tmp/mclab-report-ui-audit
```

감사 도구는 홈, 학습 경로, 탐색, 결과, 실험, 오류 복구 화면을 한국어/영어 및
640×360, 1280×720, 1920×1080에서 캡처한다. 640×360 논리 공간 대리 조건과 별도로
`QT_SCALE_FACTOR=2`를 적용한 1280×720 물리 캡처에서 홈·실험·완료·오류·펼친
기술 세부정보를 검사한다.

장면 감사 도구는 Lab01~04를 실제 EGL로 각각 두 번 실행한다. 같은 시점의 기본 장면과
학습자 조작 장면을 비교하며, 뷰포트 안의 변화량과 현재·목표·힘·벽·작업공간 마커를
검사한다. 캡처와 JSON 기준선은 지정한 `/tmp` 폴더에 남고 학습자 결과에는 섞이지 않는다.

## 자동 합격 기준

| 항목 | 기준 | 2026-07-16 결과 |
|---|---:|---:|
| 화면 크기 | 요청 크기와 정확히 일치 | software 150/150 + 실제 EGL 12/12 통과 |
| Python 전체 회귀 | 기존 동작과 새 UI 회귀 모두 통과 | 433 tests, failure·error·skip 0 |
| QML 경고와 오류 대화상자 | 정상 과업에서 0건 | 0건 |
| 비실험 화면의 대형 미도색 영역 | 순검정 픽셀 5,000 미만 | 최대 2,888 px(텍스트·포커스 외곽선), 대형 영역 0 |
| 640×360 실험·재생 뷰포트 | 세로 140 px 이상 | 158 px |
| 키보드 홈→실험 | Tab/Shift+Tab/Enter만 사용 | 통과 |
| 실험 일시정지→진행 | Space/Right만 사용 | 통과 |
| 실제 포커스 순서 | 11개 고정 흐름의 이름·역할·창 내부 영역 일치 | 11/11, 죽은/숨은/창 밖 대상 0 |
| 모달 포커스 | 안전한 `닫기`에서 시작, 내부 순환, 원래 조작으로 복귀 | 오류·결과 관리 모두 통과 |
| compact 패널 포커스 | 화면 밖 제어로 이동할 때 자동 스크롤 | 예측 입력·패널·내비게이션과 전체 증거 과업에서 창 밖 대상 0 |
| 스크롤 목록 포커스 | 탐색·결과 카드의 Tab/Shift+Tab 포커스와 카드 문맥을 항상 같은 viewport에 표시 | 양방향 22개 표본, 창 밖 0, 제목-버튼 가림 0 |
| 예측→조작→관찰 | 키보드만으로 순서 완료, 단계와 안내가 즉시 갱신 | `2/5→3/5→4/5→5/5`, 15개 포커스 표본 전부 유효 |
| hands-on 예측 문맥 | 장면 물리와 일치하는 짧은 한·영 가설 예시 | 9/9 scenario, 8개 물리 문맥, 런타임 언어 전환 통과 |
| 200% 예측 가독성 | 핵심 관찰량이 첫 32자 안에 표시 | 한·영 16/16, `Contact force`가 말줄임표 앞에 노출 |
| 작성한 예측 전체 가독성 | 640px·200%에서 가로/세로 넘침 1px 이하, 2~3줄; 1280px에서 1줄 | 48.2px 넘침·1줄 → 0px·2줄, 1280px도 0px·1줄 |
| 240자 예측 경계 | overflow 때만 대비 3:1 scrollbar, 처음↔끝 이동, 저장 손실 0 | EN 640 `10줄/128px`, EN 1280 `7줄/81px`, KO 200% `14줄/200px`; 240/240자 저장 |
| 300자 관찰 근거 경계 | overflow 전용 scrollbar, 고정 접근성 viewport+전체 value, outcome 저장 손실 0 | EN 640 `13줄/190px`, EN 1280 `8줄/108px`, KO 200% `17줄/262px`; 300/300자 저장 |
| 예측 전 결정성 | 예측 확정 전 물리 시간 0.00 s, 확정 뒤 자동 시작 | 초기·Space·Right·재시작 모두 0.00 s, 확정 뒤 양수 시간 |
| 학습 증거 영속화 | prediction·learner control·observation marker를 함께 저장 | prediction 1 + button 1 + 완전한 marker 1, `Ready for review` |
| 완료·증거 경계 | 화면당 파란 주요 행동 1개, 불가능한 제어 0개 | 미완성은 `다시 시작`, 증거 완료는 `저장 결과 보기`; primary 1/1 |
| 실험 단계 행동 위계 | 파란 채움은 현재 단계의 다음 행동 최대 1개, 동료·이동·프레임 조작은 outline | 예측 `2→1`, 첫 조작 `4→1`, 관찰 `4→0/저장 준비 1`, replay `7→1`; 한·영·200%·EGL 통과 |
| 완료 뒤 키보드 복구 | Enter 재시작 뒤 0.00초 예측 입력으로 포커스 | `완료→일시정지`, evidence `2→1`, 포커스 `다시 시작→예측` |
| 라이브/재생 진행 의미 | 라이브는 읽기 전용, 재생만 seek 가능 | ProgressBar 비포커스, Slider `1/61→7/61` |
| 속도 상태 일치 | UI 표시와 실제 session speed가 모든 전환에서 동일 | live 재시작·replay·키보드 9/9 표본 일치 |
| compact 첫 행동 문장 | 실제 버튼·제어 이름, 최대 2줄, 시각적 잘림 0 | 한·영 live + 한국어 replay + 최장 84자 영어 4/4 |
| 화면 이탈 수명주기 | live·예측 대기·replay 이탈 즉시 일시정지, 네 화면에서 복귀/종료 | 8/8, 이탈 뒤 연속 표본 시간 변화 0.0 s |
| scenario 문맥 연속성 | 탐색→실험→배경 pause/replay/saving에서 같은 `LABxx · 제목` 유지 | compact·200%·1280px, 한·영, live·replay·saving 5/5 |
| 화면 이탈 키보드 | 숨은 입력 포커스 금지, Enter로 세션 복귀 | 홈→경로→탐색→결과→복귀 통과, 창 밖 대상 0 |
| 활성 세션 충돌 행동 | 새 실험·재생·재실행·삭제·비교를 사전 차단, 안전 검토 유지 | 탐색 Start 0/70→70/70 비활성, report·folder·close 활성 |
| 전체 비교 중 충돌 행동 (역사적) | 새 실험·재생·재실행과 직접 backend 호출 차단, 안전 정리 유지 | 당시 탐색 Start 0/70→70/70 비활성, 직접 호출 2/2 거부, 무관한 저장 실행 삭제 성공; SAFE-01 격리로 대체 |
| 전체 비교 상태 가시성 | 탐색·결과에서 현재 세트·취소·차단 이유를 바로 확인 | 공통 상태 바, 640×360·1280×720 조작 잘림 0 |
| 완료 worker→전체 비교 | thread 생존과 active busy를 구분 | active probe 0회, 완료·idle probe 1회 |
| 세션 수명주기 | 완료→재시작 3회, 중복 실행 차단, 이전 session/adapter 정리 | 5회 반복·총 15/15 재시작, RSS 최대 41,172 KB/65,536 KB |
| 스레드 격리 GL 과업 | 일반 실행·마우스/키보드 카메라·Panda 재생·live 재시작·교차 scenario 교체·재생 되감기 | 최종 12/12, SIGSEGV·EGL 오류 0 |
| 오류 주입 | 짧은 원인, 복구 행동, 복사/펼치기 제공 | raw `KeyError` 본문 노출 0, 통과 |
| 키보드 포커스 표시 | 노란 면 40 px·검은 외곽 20 px 이상 | 436 px·172 px |
| 네이티브 조작 대상 | 일반 조작 44×44, slider/check/event 24×24 이상 | 전체 접근성 rect 미달 0 |
| 실제 200% 확대 | 첫 둘러보기·홈·배경 pause·탐색 검색·실험·완료·오류·세부정보 물리 1280×720 | 8/8, 가로 잘림·이름 누락 0 |
| 탐색 검색 대비 | placeholder text 4.5:1, 입력 경계 3:1, 실제 token pixel 거리 24 이하 | 5.96:1·4.76:1, 640 KO `6.4/0.0`, 1280 EN `19.7/0.0`, 200% KO `0.0/0.0` |
| 핵심 증거 입력 경계 | 예측·관찰·결과 선택 경계 3:1, 실제 perimeter token 거리 24 이하 | 4.76:1, 640 KO/EN 세 컨트롤 모두 `0.0`, 44px 미달 0 |
| 보조 행동 경계 | 흰색 보조 버튼 경계 3:1, 주요 행동 수·포커스 표시 유지 | 4.76:1, 홈·실험·결과·모달 8개 perimeter `0.0`, primary·focus 회귀 0 |
| 비활성 버튼 위계 | 주요 행동보다 낮은 light surface, 텍스트 4.5:1·경계 3:1 이상 | `#E2E8F0/#475569/#64748B`, 6.15:1·3.86:1, 12/12 상태 통과 |
| 체크박스 상태 | 미선택 경계 3:1, 선택은 색+모양+접근성 상태, 타깃 24px 이상 | 경계 4.76:1·28px indicator·44px control, checked/unchecked 4/4 일치 |
| compact 체크박스 라벨 | 핵심 한·영 라벨의 실제 glyph 세로 범위 22px 이하 | 영어 16.0px·200% 한국어 13.5px, 2/2 한 줄 |
| 결과 수치 라벨 가독성 | 의미색 유지, 접근성 line box 17px 이상, 실제 글자 token 거리 24 이하 | 12px bold·18px line box, 640 KO·1280 EN·200% KO 9개 거리 `0.0`~`3.46` |
| 기록 위치 가독성 | 한·영·200% line box 17px 이상, 타임라인과 위치 문구 겹침 0 | 12px bold·18px line box·token 거리 `0.0`, non-overlap 3/3 |
| 다수 결과 행동 위계 | 화면 전체에서 최신 결과의 다음 행동만 채운 파랑, 오래된 행동은 계속 사용 가능 | 20·40개 공개 상태 모두 primary `1`, 컨트롤 66·126개 유지 |
| 오류 모달 외곽 | 흰 면 대비 3:1 이상, Dialog perimeter 목표색 픽셀 1,000개 이상 | 2px `#64748B` 4.76:1, 200% 목표색 근접 9,585px |
| 결과 관리 모달 외곽 | 오류 모달과 같은 surface token, 640px·200%에서 목표색 perimeter 검출 | 2px `#64748B`·12px radius, 2,824px·11,300px |
| 3D 카메라 발견성 | mouse·keyboard·보조기술에서 회전·이동·확대/축소·초기화 방법 제공 | 영문 hover·한국어 reset focus·영문 장면 focus 3/3, 이름/설명 누락 0 |
| 카메라 포커스 HUD | 조작 중에도 의미 범례와 키 안내를 동시에 표시 | 640 Lab01·wall, 1280 wall, 실제 EGL 4/4, 창 밖·이름 누락 0 |
| 3D 카메라 실제 조작 | EGL에서 mouse와 keyboard orbit·pan·zoom이 각 축을 바꾸고 reset 뒤 최초 시점과 프레임 복원 | 2/2, 카메라 trace 10/10·현재/목표/벽 픽셀 통과 |
| Lab04 실제 EGL 프레이밍 | 640·1280에서 Panda 본체 면적과 현재·목표·벽 마커를 유지 | Panda 2,412·7,135px, 의미 마커·reset·replay 4/4 |
| Lab04 예측 장면 | 첫 물리 step 전에도 설정된 목표·가상 벽을 표시 | 0.00 s에서 target `[0.61, 0, 0.58]`, wall `x=0.57`, 실제 EGL 검출 |
| 완료→저장 결과 | 중복 행동 없이 기록 검토를 다음 주요 행동으로 제시 | `저장 결과 보기 →`, 재시작 1개 |
| 탐색 접근성 트리 | 보이는 컨트롤 이름 누락 0, 고유 실행 버튼 70개 | 78개 중 누락 0, 70/70 고유 |
| 탐색 카드 문맥 제목 | 보이는 제목과 실행 버튼이 같은 Lab 문맥을 제공하고 70개 모두 고유 | 한·영 70/70, 필터 70·9·14·2·0 및 200% 확대 통과 |
| compact 탐색 발견성 | 첫 카드의 목적·CTA를 유지하고 다음 카드 제목을 첫 viewport에 완전히 노출 | 완전 노출 제목 1→2, 다음 제목 y `517~544`→`491~518`(창 하단 519) |
| 탐색 필터 정확성 | 난이도·방식·다중 단어 결합, 실시간 수, 빈 결과 복구 | 전체 70, 직접 조작 9, 중급 직접 조작 2, `lab04 wall` 14, 빈 결과 0→초기화 70 |
| 탐색 필터 키보드 | Search→Level→Mode, 빈 결과 Reset→Search | 포커스 5/5, 창 밖·잘림·이름 누락 0 |
| 탐색 다중 단어·확대 | 모든 단어를 순서 무관 AND 검색, 100%·200% 동일 | `lab04 wall` 14/70, 640×360·1280×720 모두 잘림 0 |
| 실험 접근성 트리 | 핵심 제어 이름·설명·포커스 누락 0 | 초기 14개·증거 완료 17개 중 누락 0 + 읽기 전용 진행률 |
| 라이브 제어 표시 정밀도 | 허용된 최소 한 step 뒤 보이는 값이 반드시 달라지고 단위를 함께 표시 | 38개 제어, 보이지 않던 첫 step 14→0; 한·영·실제 EGL `0.610→0.615 m` 검출 |
| 관찰·핵심 제어 동시 가시성 | 1280×720에서 관찰 입력·결과·저장과 최대 5개 제어를 같은 패널 안에 완전히 표시 | 밖에 있던 값 3개→0; Lab02·Lab04 software/EGL containment 10/10, 마지막 값 glyph 21px |
| reduced motion | 비필수 QML 애니메이션 0개 | 0개 |
| 앱 cold start p95 | 5,000 ms 이하, 새 설정으로 5회 | 523.8 ms |
| 앱 중복 실행 | 두 번째 GUI 0개, 기존 창 활성화 1회, 첫 앱 종료 뒤 재실행 가능 | rc `6`·184.9 ms·activation `1`, 종료 뒤 rc `0` |
| 홈→첫 실험 | 최대 3회 상호작용 | 1회 |
| 첫 viewport 온보딩 | 640×360에서 3단계·건너뛰기·주요 CTA 완전 노출 | 한글·영어·200% 3/3, 창 밖 항목 0 |
| 둘러보기 단계 연결감 | 1280·1920px에서는 대비 3:1 이상 연결선, 640px·200%에서는 연결선 0 | 대비 3.18:1, 연결선 884·2,312 px / compact 0·0 px |
| 둘러보기 키보드 왕복 | 건너뛰기→CTA, 다시 보기→건너뛰기로 포커스 복구 | 포커스 trace 5/5, 노란 링 508~656 px |
| 홈 작업 우선순위 | 설정 오류·활성 실험·전체 비교가 있으면 둘러보기보다 복구 행동 우선 | 3/3, 복귀/종료/취소 첫 viewport 완전 노출 |
| 첫 Lab01 둘러보기 일치 | 0.00초 pause·Push 포커스·핵심 slider 1개·실제 기록 재생 | Push + Damping 저장, 완료 manifest, replay 301프레임 통과 |
| 1D 장면 인지성 | 640×360 안전모드에서도 질량·스프링·댐퍼·평형점을 직접 식별 | 4개 직접 라벨, 밝은 바닥·눈금, 현재/스프링 의미색 거리 0 |
| 대형 1D 장면 초점 | 1920×1080에서 현재·목표·힘 의미색 면적 8,000·320·300px 이상 | 10,746·499·464px, 라벨 4개를 실제 대상 가까이에 배치 |
| 공간 장면 안전모드 | 1D 추종·2DOF·Panda Cartesian/wall을 빈 십자선 없이 설명 | 9/9, 640·1280·1920·200%와 wall 극단 조작 통과 |
| 공간 손끝 직접 라벨 | 비-compact fallback에서 현재·목표 손끝을 대상 옆에 고유 이름으로 표시 | Lab03 1,169·1,258px, Lab04 1,523·1,196px, 겹침 0 |
| 첫 Lab01 CLI 호환 | 앱 전용 준비 상태가 headless 계산을 멈추지 않음 | 501 log 행, 최종 5.002 s, completed |
| 누락 모델 상태 | 성공색 금지, 원인·복구·비활성화 제공 | 황색 4,135 px, 모두 제공 |
| 학습 경로 기본 상태 | 주요 다음 행동 1개, 고유 이름, 설명 제공 | 컨트롤 6개, 이름 누락 0 |
| 학습 경로 부분 완료 | 중단·오류 실행은 완료에서 제외 | 2/12, 다음은 Lab02 자동 데모 |
| 학습 경로 마지막 단계 | 11개 실험 뒤 전체 비교 한 행동만 노출 | 11/12, `전체 비교 시작` 노출 |
| 전체 비교 생명주기 | UI 비차단, 1/5~5/5, 취소·중복·오류 복구 | 실행·중복·중단·재시도 모두 통과 |
| 실제 plotted 전체 비교 | 300 s, UI gap 500 ms, 150 MB 이하 | 154.40 s, 27.2 ms, 52.5 MB |
| 전체 비교 산출물 | 5세트·54실행·6과정 리포트·hash 오류 0 | 5·54·6·0, 비교 plot 33개 |
| HTML report 브라우저 | run/batch/course/index × desktop/mobile | 기존 8/8 + 변경 run/index 4/4 재검증 통과 |
| HTML axe WCAG 2.2 | A/AA·best-practice 위반 0 | 변경 경로 4개 화면 모두 0 |
| HTML 반응형·키보드 | overflow·깨진 이미지·focus 실패 0 | 모두 0, 표 영역 키보드 접근 가능 |
| 실행 중 결과 보호 | 활성 비교 폴더 삭제 금지, 이유·복구 제공 | 관리 비활성 + repository 경계 방어 통과 |
| 학습 경로 전체 완료 | 12번째 비교 성공 뒤 결과 검토로 전환 | 12/12, 경로·홈 모두 `결과 검토` 노출 |
| 학습 경로 누락 모델 | 원인·복구 명령·비활성 행동을 640×360에 노출 | 황색 3,568 px, 이름 누락 0 |
| 손상 리플레이 | 죽은 재생·없는 리포트를 숨기고 재사용 설정으로 바로 복구 | `같은 설정 재실행` enabled·primary, 키보드 Enter 실행 통과 |
| 실행 중 언어 전환 | 탐색 카드·필터·접근성 이름까지 즉시 전환 | 78개 중 누락 0 |
| compact 기록 재생 | 처음/이전/재생/다음/끝·반복·속도 모두 노출 | 컨트롤 19개, 이름 누락 0 |
| 재생 경계·이벤트 이동 | 마지막 프레임 clamp, 이벤트 클릭 후 정확한 프레임 | 61/61 및 16/61 통과 |
| 기록 타임스탬프·속도 | 저장된 간격, 0.5×/2× 배율 사용 | 0.4 s / 0.1 s 단위 회귀 통과 |
| Panda 실제 EGL 기록 재생 | 현재·목표·벽·힘 의미색 거리 80 이하 | 15.2 / 27.6 / 31.3 / 16.3 |
| 빈 결과 화면 | 원인과 첫 실험 CTA를 키보드로 사용 | 컨트롤 6개, 이름 누락 0 |
| 정상 결과 카드 | 한 문장 결과·수치 3개·다음 행동·리포트 | 컨트롤 8개, 이름 누락 0, `기록 재생` primary |
| 결과 행동-안내 일치 | 파란 주 행동이 카드의 `다음` 문장과 같은 과업 | 정상=`기록 재생`, 기록 없음=`같은 설정 재실행`, 각 primary 이름 자동 검증 |
| 결과 관리·영구 정리 (역사적, SAFE-01로 대체) | 고급 실행·폴더·경고·삭제·닫기를 640×360에 노출 | 당시 컨트롤 13개, 삭제 후 빈 상태 6개로 복구 |
| 60개 결과 확장 | 최초 20개, 20개씩 추가, 이름 중복 0 | 174.8 ms, 컨트롤 66→126 |
| 결과 확장 포커스 | 20→40→60 키보드 확장 뒤 첫 새 카드에서 읽기 계속 | `이전 21`·`이전 41` y=449, 최종 185개 컨트롤, 숨은 포커스 0 |

## 2026-07-16 300자 관찰 근거·접근성 viewport 반복

예측 입력의 240자 경계를 고친 뒤 같은 방법으로 관찰 메모를 공격하자, 허용 한도 300자가
13줄이 되면서 `190px`가 잘리고 추가 내용 표시가 전혀 없었다. 관찰은 예측과 실제 결과를
연결하는 최종 학습 근거이므로, 저장 가능 여부만으로는 완료된 UX라 볼 수 없었다.

- red: `outputs/_qt_observation_limit_red/ui_audit.json`에서 영어 300자가 가로 넘침 `0px`,
  세로 넘침 `190px`, 13줄, scrollbar 없음, 입력 길이 300임을 기록했다. 관찰 content와
  viewport, line count, scrollbar·scroll 위치, UI/backend 저장 길이를 별도 metric으로
  추가했다.
- 예측과 관찰의 중복 TextArea를 공용 `EvidenceTextArea.qml`로 추출했다. 두 입력은 같은
  focus ring, 3:1 이상 scrollbar, word wrap, 최대 길이, Tab handoff를 사용하며 각각
  52px·44px 높이와 240자·300자 계약만 전달한다. `EvidenceWorkflow.qml`은 283줄,
  공용 컴포넌트는 99줄로 400줄 한도를 유지한다.
- 첫 green은 44px 관찰 입력의 implicit content 높이가 48px이라 짧은 두 줄에도 scrollbar가
  보였고, 긴 편집기의 접근성 rect가 전체 content 높이로 viewport 밖까지 확장되는 2차
  결함을 드러냈다. scrollbar는 실제 `contentHeight > availableHeight`일 때만 보이도록
  바꾸고, 고정 ScrollView가 `EditableText` 접근성 역할을 맡게 했다.
- 최종 접근성 tree는 긴 관찰도 `188×44px` viewport 안에 두면서 전체 300자 value,
  이름 `Observe/관찰`, 설명, focused/editable/multiline 상태를 유지한다. 짧은 42자는
  2줄·overflow `0px`·scrollbar false이고, 300자일 때만 오른쪽 scrollbar가 나타난다.
- 영어 640px은 13줄·`190px`에서 끝 `202px`, 영어 1280px은 8줄·`108px`에서 끝
  `120px`으로 이동했다. 실제 한글 300자는 200%에서 17줄·`262px`이며 끝을 지난 뒤
  처음 `0px`으로 복귀했다. 한·영 모두 Tab→outcome→`관찰 저장`→첫 조작 포커스와
  `prediction + push + observation` event, note 300/300자를 보존했다.
- `outputs/_qt_observation_scroll_focused_green2/ui_audit.json`에서 짧은/긴 입력, 접근성,
  한·영 IME·키보드·저장을 집중 검증했다. 직접 캡처에서는 입력·outcome·저장 CTA가 같은
  viewport에 남고 scrollbar가 첫 글자를 덮지 않으며 장면/transport 크기가 변하지 않았다.
- 최종 `outputs/_qt_observation_scroll_full_green/ui_audit.json`은 software UI 150/150,
  `outputs/_qt_observation_scroll_gl_green/ui_audit.json`은 실제 EGL 12/12다. Python 433 tests,
  software 반복 RSS 23.5MB·EGL 6.5MB, Ruff·diff check와 architecture gate를 통과했다.

## 2026-07-16 240자 예측·한국어 IME 경계 반복

표준 예측 문장은 두 줄로 모두 보였지만 허용 한도인 240자를 입력하면 52px 입력 영역에
10줄이 생기고 `128px`가 잘렸다. 저장 버튼과 장면은 유지됐으나 더 읽을 내용이 있다는
표시나 이동 수단이 없어, 앞부분만 보이는 상태를 완전한 줄바꿈 수정으로 오판할 수 있었다.

- red: `outputs/_qt_prediction_limit_red/ui_audit.json`에서 영어 240자가 가로 넘침 `0px`,
  세로 넘침 `128px`, 10줄이면서 scrollbar가 없는 상태를 재현했다. 입력 길이, content와
  viewport, line count, scrollbar 표시, scroll 위치, backend 저장 길이를 함께 기록하도록
  oracle을 확장했다.
- 입력 영역을 고정 높이 `ScrollView`로 감싸 CTA와 장면 크기는 바꾸지 않았다. overflow가
  있을 때만 오른쪽에 10px track과 6px thumb를 표시하고, thumb `#64748B`와 track
  `#E2E8F0`은 그래픽 대비 3:1 이상을 유지한다. 짧은 1~2줄 입력에서는 scrollbar가
  완전히 사라진다.
- 영어 640px은 10줄·`128px`에서 끝 `140px`, 영어 1280px은 7줄·`81px`에서 끝
  `93px`으로 이동했다. 실제 한글 240자는 200%에서 14줄·`200px`이며 peak scroll
  `180px` 이상을 지난 뒤 처음 `0px`으로 복귀했다. 모든 경우 가로 넘침은 `0px`이다.
- 첫 한국어 red는 제품이 아니라 beta 도구가 `str.isalpha()`를 ASCII로 가정해 한글을
  잘못된 key code로 만든 `SystemError`였다. 비 ASCII 입력을 실제 IME commit event로
  보내도록 수정하고, 한국어 240자 입력→Tab→`예측 확정`→Enter→첫 실험 조작 포커스를
  검증했다. 한·영 모두 UI 240자와 backend/event 240자가 일치한다.
- `outputs/_qt_prediction_scroll_focused_green2/ui_audit.json`,
  `outputs/_qt_prediction_scroll_persistence_green2/ui_audit.json`,
  `outputs/_qt_prediction_scroll_ime_roundtrip_green/ui_audit.json`에서 짧은 입력·끝/처음 이동·
  키보드·IME·저장을 집중 검증했다. 대표 캡처에서는 scrollbar가 입력 첫 글자를 덮지 않고
  오른쪽에만 나타나며 `예측 확정`과 장면이 그대로 보임을 직접 확인했다.
- 최종 `outputs/_qt_prediction_scroll_full_green/ui_audit.json`은 software UI 144/144,
  `outputs/_qt_prediction_scroll_gl_green/ui_audit.json`은 실제 EGL 12/12다. Python 433 tests,
  software 반복 RSS 18.6MB·EGL 17.7MB, Ruff·diff check와 architecture gate를 통과했다.

## 2026-07-16 200% 예측 문장 전체 가독성 반복

200% 확대에서 긴 예측을 입력하면 단일 행 입력기가 caret 끝으로 가로 스크롤되어 문장
앞부분이 사라졌다. 저장은 가능했지만 학습자는 `무엇을 예측했는지` 다시 읽을 수 없었고,
관찰 결과와 가설을 대조해야 하는 학습 흐름을 시각적으로 끊었다.

- red: `outputs/_qt_prediction_wrap_red3/ui_audit.json`에서 같은 문장을 입력했을 때
  가로 넘침 `48.203125px`, 세로 넘침 `0px`, line count `1`을 기록했다. 첫 두 red 시도는
  대상 case에 trace가 없거나 누락 metric을 `float(None)`으로 읽는 계측 결함도 드러냈다.
  prediction layout 기준을 선언한 case가 `record_backend` trace를 남기지 않으면 반드시
  실패하도록 oracle을 함께 강화했다.
- 예측 입력을 단일 행 `TextField`에서 높이 52px의 `TextArea`로 바꾸고 word wrap을
  적용했다. 240자 제한은 multi-line 문서에 맞게 초과 구간을 제거하며, Tab은 명시적으로
  `예측 확정`으로 이동한다. 관찰 입력과 기존 focus reveal 계약은 그대로 유지했다.
- 집중 green `outputs/_qt_prediction_wrap_green2/ui_audit.json`은 640px 한국어와 200%
  한국어에서 `0px/0px`, 2줄, 1280px 영어에서 `0px/0px`, 1줄을 기록했다. 접근성 초기
  화면과 키보드 증거 과업을 포함한 5/5 case도 통과했다.
- 대표 캡처를 직접 검토해 문장의 시작·끝, 입력 경계, `예측 확정` CTA, 장면과 transport가
  겹치지 않음을 확인했다. 이 평가는 사람 대상 관능 평가가 아니라 자동 베타의 시각 표본
  검토이며, 실제 초보 학습자 think-aloud gate를 대체하지 않는다.
- 최종 `outputs/_qt_prediction_wrap_full_green/ui_audit.json`은 software UI 139/139,
  `outputs/_qt_prediction_wrap_gl_green/ui_audit.json`은 실제 EGL 12/12다. Python 433 tests,
  software 반복 RSS 12.2MB·EGL 11.0MB, Ruff와 예측 입력 정적 계약을 통과했다.

## 2026-07-16 실험 단계별 주요 행동 위계 반복

실험 캡처의 파란 채움 버튼을 전수 대조하자 같은 화면에서 `홈`, `Pull`, `Push`, `재생`이
모두 주요 행동처럼 보였고, replay에서는 홈·처음·이전·재생·다음·끝·반복까지 7개가
동일한 파랑이었다. 키보드 포커스의 노란 링과 별개로, 초보자가 지금 해야 할 한 행동을
색만으로 고를 수 없는 시각 위계 실패였다.

- red: `outputs/_qt_experiment_primary_red/ui_audit.json`에서 예측 작성 2개, 첫 조작 전
  4개, 관찰 작성 중 4개, replay 7개의 filled-blue action을 계측했다. 각 상태의 허용
  최대를 1로 정하고, 예측=`Set prediction`, 조작=`Push`, 저장 준비=`Save observation`,
  replay=`재생`처럼 기대 이름도 함께 고정했다.
- live·replay의 홈은 outline navigation으로 통일했다. action 쌍은 첫 learner action 전
  권장 항목(`push`, `target_x_increase`, 또는 첫 action) 하나만 파랑이고 동료는 outline이다.
  첫 조작 뒤에는 둘 다 outline으로 물러나 관찰 입력을 방해하지 않는다.
- transport의 Play는 직접 조작/관찰 입력이 우선인 동안 outline이고, 저장 가능한 관찰이
  준비되면 `관찰 저장` 하나만 파랑이다. 증거 저장 뒤에는 Play/Pause로 위계를 넘긴다.
  replay의 네 frame 이동 버튼은 outline, Play만 파랑이며 선택된 반복은 파란 CTA 대신
  `✓`와 checked 접근성 상태로 중복 표현한다.
- 첫 green은 목표 개수에 도달했지만 startup의 빈 scenario가 새 bool binding에
  `undefined`를 전달해 QML 경고가 났다. `Boolean(...)` 경계로 초기값을 고정했다. 이어
  완료+증거 미완성 화면에서 조작 우선 조건이 남아 `다시 시작`까지 outline이 되는
  0-primary 엣지를 찾아, completed에서는 이 조건을 끄고 `다시 시작` 하나를 복구했다.
- `outputs/_qt_experiment_primary_bilingual_green/ui_audit.json`과
  `outputs/_qt_experiment_primary_completion_green/ui_audit.json`에서 한·영·640·1280·200%
  예측/조작/저장 준비/미완성 재시작/완료 결과 보기 9개 상태가 기대 primary 1개를
  통과했다. 관찰 입력이 아직 유효하지 않을 때만 의도적으로 0개다.
- 최종 `outputs/_qt_experiment_primary_full_final/ui_audit.json`은 software UI 138/138,
  `outputs/_qt_experiment_primary_gl_full_final/ui_audit.json`은 실제 EGL 12/12다. Python
  432 tests, software 반복 RSS 12.9MB·EGL 7.3MB, Ruff·diff check·doctor 7/7과
  architecture gate를 통과했다.

## 2026-07-16 관찰과 핵심 제어 동시 가시성 반복

첫 learner action 뒤 오른쪽 `관찰` 카드가 세로 공간 대부분을 차지해 1280×720에서도
Lab02의 `Ki`, `Kd`, `Force limit` 세 값이 창 밖으로 밀렸다. 초보자가 현재/목표를
관찰하면서 gain을 바꿔야 하는 단계에서 정작 핵심 slider를 보려면 패널을 다시 스크롤해야
했고, 5개 제어 scenario에서 관찰과 조작을 번갈아 기억하게 만들었다.

- red: `outputs/_qt_core_controls_red/ui_audit.json`은 관찰 입력 뒤 마지막 세 값이 첫 창
  밖임을 재현했다. 첫 `Position` glyph도 목표 파랑과 거리 111.4, 마지막 `Force limit`은
  검출 불가였다. 접근성 좌표만 창 안인지 보는 약한 기준을 보강해 `Core experiment
  controls` pane 안에 각 slider 전체가 containment되는지도 검사한다.
- learner action 뒤에는 장면 위 `지금 해볼 것`과 중복되는 예측 recap·관찰 설명·구분선을
  접고, 44px 관찰 입력은 유지했다. 결과 선택과 저장은 한 행, 핵심 제어는 넓은 화면에서
  두 열로 배치한다. 640px compact는 기존 한 열과 포커스 자동 스크롤을 유지한다.
- 첫 green은 값 다섯 개를 노출했지만 마지막 slider handle이 패널 하단에 걸리고
  `Proportional gain Kp`가 말줄임됐다. 기준을 낮추지 않고 패널을 폭 310~360px의
  responsive 영역으로 조정해 긴 라벨과 마지막 handle을 모두 완전히 표시했다.
- `outputs/_qt_core_controls_focused/ui_audit.json`은 예측·관찰·완료·200%·한영·키보드
  17/17을 통과했다. compact에서 Tab으로 마지막 `Force limit`까지 이동한 trace 6/6,
  값 glyph 21px·색 거리 6.5이며 slider 전체가 pane 안에 있다.
- 실제 Panda `outputs/_qt_core_controls_gl_green/ui_audit.json`은 관찰 카드와 wall 제어
  5개를 동시에 표시하면서 Panda 전경 8,173px, 현재/목표/벽 색 거리
  32.0/27.6/24.2를 유지했다.
- 최종 `outputs/_qt_core_controls_full_final/ui_audit.json`은 software UI 133/133,
  `outputs/_qt_core_controls_gl_full_final/ui_audit.json`은 실제 EGL 12/12다. Python은
  431 tests, 반복 재시작 RSS 증가는 software 15.6MB·EGL 10.9MB이며 Ruff·diff check·
  doctor 7/7과 architecture gate를 통과했다.

## 2026-07-16 라이브 제어 정밀도·단위와 동적 포커스 반복

38개 라이브 제어를 허용 step과 화면 문자열로 대조하자 8개 scenario의 14개 제어가
첫 한 step을 움직여도 표시값이 그대로였다. 모든 값을 소수점 한 자리로 반올림했기 때문에
Lab04 `Target X`는 `0.610→0.615`가 모두 `0.6`으로, DLS damping은 `0.08→0.09`가
모두 `0.1`로 보여 키보드 화살표와 미세 튜닝이 고장 난 것처럼 느껴졌다.

- red: 정적 전수 감사에서 `invisible_first_step=14/38`을 재현했고,
  `outputs/_qt_control_precision_red/ui_audit.json`은 화살표 한 번 뒤 접근성 값
  `Target X: 0.615 m`가 없어서 실패했다.
- 각 제어가 YAML step에서 직접 계산한 표시 자릿수와 물리 단위를 payload로 제공한다.
  패널의 보이는 값, 접근성 이름, 범위·현재값 설명은 같은 formatter를 사용해
  `0.615 m`, `0.09`, `2.0 N·s/m`처럼 일치한다. 38개 모두 최소값과 최소값+step의
  문자열이 달라져 `invisible_first_step=0/38`이 됐다.
- 첫 green에서는 값 자체는 맞았지만 learner action 뒤 `관찰` form이 펼쳐지며 포커스된
  slider와 수치가 compact viewport 아래로 밀렸다. 실제 파란 glyph 검출 gate를 추가해
  이 2차 결함을 red로 고정하고, evidence panel 높이가 변할 때 현재 포커스를 다시
  reveal하도록 했다. `outputs/_qt_control_precision_visibility_green1/ui_audit.json`에서
  수치 glyph 높이 21px·색 거리 0으로 복구됐다.
- 한·영 640/1280 집중 검증
  `outputs/_qt_control_precision_bilingual_green/ui_audit.json`과 실제 Panda EGL
  `outputs/_qt_control_precision_gl_green2/ui_audit.json`은 정확한 `0.615 m`, 현재·목표·벽
  의미색, Panda 전경 2,178px을 함께 통과했다.
- 최종 `outputs/_qt_control_precision_full_final/ui_audit.json`은 software UI 131/131,
  `outputs/_qt_control_precision_gl_full_final/ui_audit.json`은 실제 EGL 11/11이다.
  Python은 430 tests, Ruff·diff check·doctor 7/7과 800줄 Python/400줄 QML architecture
  gate를 통과했다.

## 2026-07-16 카메라 포커스 중 범례 지속성 반복

장면에 키보드 포커스가 들어오면 하단 HUD가 의미 범례 전체를 숨기고 카메라 키 설명으로
교체됐다. 초보자가 현재·목표·힘·벽을 해석하는 바로 그 순간에 범례가 사라져, 키 안내와
마커 의미를 번갈아 기억해야 했다.

- red: `outputs/_qt_camera_legend_persistence_red/ui_audit.json`에서 640 Lab01과 1280
  wall 모두 `Scene markers: ...`와 전체 키 설명을 합친 접근성 항목이 누락됐고 첫 창
  내부 기준도 실패했다. 640 wall의 기존 범례는 약 196px, 전체 키 설명은 272px이라
  단순 병렬 배치는 398px 장면을 넘는 것도 확인했다.
- 75줄 HUD를 392줄 `ExperimentPage`에 더하지 않고 99줄 `SceneHud.qml`로 분리했다.
  범례는 항상 유지하고, 카메라 포커스 시 640px에는 `Keys: arrows·Shift·+/-·0` micro
  안내를, 넓은 화면에는 전체 안내를 같은 캡슐에 추가한다. 보조기술 이름은 화면 크기와
  무관하게 완전한 범례와 전체 키 설명을 함께 제공한다.
- 캡처 관능 대리 평가에서 640 Lab01과 가장 빽빽한 640 wall은 한 줄 안에 완전히 들어가며,
  1280 wall은 전체 키 설명까지 표시한다. 포커스 노란/검은 외곽, 현재·목표·힘·벽 색과
  장면 물체는 그대로 유지된다.
- `outputs/_qt_camera_legend_persistence_green1/ui_audit.json` 2/2,
  `outputs/_qt_camera_legend_persistence_compact_wall/ui_audit.json` 1/1,
  실제 EGL 집중 감사 `outputs/_qt_camera_legend_persistence_gl_focused/ui_audit.json` 1/1을
  통과했다. 최종 `outputs/_qt_camera_legend_persistence_full_final/ui_audit.json`은
  software UI 129/129, `outputs/_qt_camera_legend_persistence_gl_final/ui_audit.json`은
  실제 EGL 10/10이다. Python은 428 tests + 1020 subtests, Ruff와 architecture gate를
  통과했다.

## 2026-07-16 실제 Panda 프레이밍과 compact 안내 합성 반복

Lab04의 MuJoCo 기본 카메라는 자동 거리 `1.9882`를 그대로 사용했다. 1280px에서는 읽을
수 있었지만 640px에서는 장면 위 `지금 해볼 것`과 움직임 칩, 하단 범례가 Panda의 상단·
손끝·베이스를 나누어 가렸다. 단순히 카메라만 당기면 넓은 화면의 벽을 자를 수 있고,
화면 점유율만 재면 안내 글자를 로봇으로 오인할 수 있어 실제 EGL 캡처를 별도 기준으로
삼았다.

- red: `outputs/_qt_panda_framing_red/ui_audit.json`에서 Panda 밝은 전경은 640에서
  1,069px, 1280에서 5,254px으로 사전 하한 1,200·6,100px에 미달했다. 새 unit test도
  교육용 거리 `1.7`과 reset 복원을 요구해 기존 거리에서 실패했다.
- Lab04 기본·reset 거리를 `1.7`로 고정하고, compact 실제 영상만
  `PreserveAspectCrop`으로 카드 폭을 사용하게 했다. 장면 위 중복 과업 문장은 오른쪽
  단계 카드로 옮기고 움직임 칩은 빈 좌상단에 배치해 물리 본체와 손끝을 비웠다. 넓은
  화면의 기존 aspect fit과 안내 합성은 유지했다.
- 과업 문장은 실제 버튼→핵심 값 순서로 한 줄에 줄였고, 예측 전과 replay에서는 오른쪽
  카드가 기존 완전한 `지금 해볼 것/복습` 접근성 이름을 대신 발화한다. 완료 후 재시작할
  때 남아 있던 panel scroll도 0으로 복원해 예측 카드 제목과 입력이 다시 완전히 보인다.
- focused 최종 `outputs/_qt_panda_framing_focused_final/ui_audit.json`은 mouse·keyboard·
  reset·replay 4/4를 통과했다. Panda 전경은 640에서 2,414px, 1280에서 7,135px으로
  증가했고, 캡처 검토에서 로봇 팔·손끝·벽·현재값·다음 조작이 한 viewport에 함께 남았다.
- 최종 `outputs/_qt_panda_framing_full_final3/ui_audit.json`은 software UI 129/129,
  `outputs/_qt_panda_framing_gl_final/ui_audit.json`은 실제 EGL 10/10이다. Python은
  429 tests + 1020 subtests, Ruff와 800줄 Python/400줄 QML architecture gate를 통과했다.

## 2026-07-16 공간 손끝 직접 라벨과 wall 겹침 반복

Lab03 2DOF와 Lab04 Panda 안전모드 도식은 본체·작업공간·벽을 넓은 viewport에 충분히
크게 그렸지만, 현재 손끝과 목표 손끝은 작은 원·마름모와 하단 범례로만 구분했다.
초보자는 움직이는 장면과 범례를 왕복해야 했고, 접근성 트리에도 두 손끝의 고유 이름이
없었다.

- red: `outputs/_qt_wide_spatial_labels_red/ui_audit.json`에서 1920px Lab03의 현재/목표
  면적은 626/599px, Lab04는 868/492px으로 사전 최소 1,000px을 모두 만족하지 못했다.
  `현재 손끝/목표 손끝`, `Current hand/Target hand` 접근성 항목도 네 개 모두 누락됐다.
- 공간 본체는 이미 충분히 커서 확대하지 않았다. 안전모드 비-compact 장면에만 현재와
  목표 손끝 캡슐을 실제 마커 옆에 추가하고, 1920px에서 최대 1.25배 커지는 글자와 3px
  의미색 경계를 사용했다. 관절·Panda·작업공간 라벨도 팔꿈치·베이스·workspace arc
  가까이 옮겼다. compact는 범례와 형태를 유지해 640px·200% 장면 과밀을 피한다.
- 첫 green에서 고유 이름은 생겼지만 면적은 Lab03 793/882px, Lab04 1,035/739px으로
  세 값이 여전히 부족했다. 기준을 낮추지 않고 직접 손끝 라벨에만 굵은 경계를 적용해
  최종 Lab03 1,169/1,258px, Lab04 1,523/1,196px을 확보했다.
- 관능 대리 검토에서 wall 장면의 목표 라벨이 격자와 일부 겹치는 엣지 케이스를 찾아,
  wall에서는 목표 라벨을 마커 왼쪽에 배치했다. target X 0.75·wall X 0.50 동적 주입에서도
  현재/목표/이동 상태가 겹치지 않았고
  `outputs/_qt_wide_spatial_labels_crossed_edge_final/ui_audit.json` 1/1을 통과했다.
- 정상 EGL은 카메라에 따라 3D 투영이 변하므로 고정 2D 라벨을 얹지 않고 기존 3D 구·
  마름모·벽 격자와 범례를 유지한다. 최종
  `outputs/_qt_wide_spatial_labels_full_final/ui_audit.json`은 software UI 127/127,
  `outputs/_qt_wide_spatial_labels_gl_final/ui_audit.json`은 실제 EGL 10/10이다. Python은
  428 tests + 1019 subtests, Ruff와 800줄 Python/400줄 QML architecture gate를 통과했다.

## 2026-07-16 대형 1D 장면 초점과 직접 라벨 반복

1920×1080 안전모드 장면은 1,558×778px의 넓은 뷰포트를 쓰면서도 질량 블록과 힘
화살표를 1280px 장면과 거의 같은 고정 픽셀 크기로 그렸다. 스프링·질량 라벨은 화면
위쪽, 댐퍼·평형점 라벨은 바닥 끝에 남아 실제 대상과 멀어졌고, 중앙 실험 대상보다 빈
공간이 더 강한 시각 초점이 됐다.

- red: `outputs/_qt_wide_scene_prominence_red/ui_audit.json`에서 의미색 실제 면적은
  현재 5,173px(최소 8,000), 목표 212px(최소 320), 힘 183px(최소 300)으로 모두
  실패했다. 단순 색 존재 여부가 아니라 앱 chrome과 오른쪽 제어를 제외한 장면 영역의
  token 픽셀 수를 세는 oracle을 추가했다.
- 640px compact 도식은 그대로 두고, 비-compact `OneDSceneGuide`만 viewport 폭·높이에
  따라 1.0~1.6배 확대한다. 블록, 스프링 진폭·선 굵기, 댐퍼, 목표 마름모, 힘 화살표,
  라벨 글자·캡슐을 같은 비율로 묶어 의미 체계가 따로 흔들리지 않게 했다.
- 스프링·질량 라벨은 각 대상 위, 댐퍼·평형점 라벨은 바닥선 바로 아래에 배치하고 질량
  라벨은 움직이는 블록 중심을 따라간다. 캡처 관능 대리 평가에서 1920px의 빈 공간은
  유지되지만 plant와 힘/목표 관계가 첫 시선에서 읽히며, 1280px에서도 겹침 없이 직접
  라벨 관계가 유지된다.
- green: `outputs/_qt_wide_scene_prominence_full_final/ui_audit.json`은 현재 10,746px,
  목표 499px, 힘 464px이며 software UI 122/122다. 1280·1920·640·200%·키보드 증거
  상태 집중 감사 `outputs/_qt_wide_scene_prominence_focused/ui_audit.json`은 5/5,
  `outputs/_qt_wide_scene_prominence_gl_final/ui_audit.json`은 실제 EGL 10/10이다.
  Python 회귀는 428 tests + 1019 subtests, doctor는 7/7, Ruff와 diff check는 통과했다.

## 2026-07-16 비활성 버튼 위계와 면적 oracle 반복

공용 비활성 버튼은 `#64748B` 면에 흰 bold 글자를 사용해, 파란 주요 행동과 색만 다른
같은 시각 무게를 가졌다. 탐색의 차단된 Start 70개, 예측 전 확인·진행, 없는 튜닝
실행이 모두 강한 채움으로 보여 초보자가 가능한 행동과 불가능한 행동을 먼저 구분하기
어려웠다.

- 사전 토큰을 배경 `#E2E8F0`, 글자 `#475569`, 경계 `#64748B`로 고정했다. 계산 대비는
  각각 6.15:1 텍스트, 3.86:1 그래픽 경계다. 최소 색 거리만 쓰면 흰 글자 안티앨리어싱
  몇 픽셀이 새 배경과 가깝게 보여 오탐하므로, 컨트롤 전체의 목표색 면적 oracle을 추가했다.
- red: `outputs/_qt_disabled_button_hierarchy_red2/ui_audit.json`에서 1280px Start의 목표
  배경은 42px(최소 3,000), 200% `예측 확정`은 214px(최소 10,000)에 불과했고 글자
  token 거리는 둘 다 `54.39`였다. source gate도 dark fill·흰 글자를 재현해 실패했다.
- 공용 `MButton`을 연한 면+진한 글자+2px 경계로 바꿨다. green에서 Start는 배경
  5,039px, 200% 확인 버튼은 31,126px이고 글자·경계 최소 거리는 모두 `0.0`이다.
  누락 asset, 비교 취소 중, 배경 차단, 결과 관리, 640px·200% 실험을 포함한
  `outputs/_qt_disabled_button_hierarchy_states_final/ui_audit.json`은 12/12다.
- 첫 full은 제품과 무관하게 ScrollView의 아직 화면에 표시되지 않은 미래 포커스 대상까지
  전역 window clipping으로 판정한 기존 oracle 때문에 121/122였다. 예측 입력 자체의
  rect·경계 gate는 유지하고 무관한 스크롤 자손을 제외했으며, 독립 재실행 2/2와 최종
  전체 실행에서 다시 통과했다.
- 캡처 관능 대리 평가에서 비활성 Start·예측·튜닝은 파란 복귀/재실행보다 분명히 뒤로
  물러나지만 라벨과 경계는 읽힌다. 최종
  `outputs/_qt_disabled_button_hierarchy_full_final2/ui_audit.json`은 software UI 122/122,
  `outputs/_qt_disabled_button_hierarchy_gl_final/ui_audit.json`은 실제 EGL 10/10이며,
  Python 회귀는 428 tests + 1019 subtests를 통과했다.

## 2026-07-16 탐색 카드 정보 밀도와 다음 문맥 발견성 반복

640×360 탐색의 시나리오 카드는 고정 154px 높이에서 목적 아래 큰 빈 공간을 남기고
시작 버튼을 맨 아래에 분리했다. 첫 카드는 읽을 수 있었지만 다음 카드 제목은 창 하단에
2px만 걸쳐, 스크롤할 선택지가 더 있다는 시각 단서가 거의 없었다.

- red: `outputs/_qt_explore_card_density_red/ui_audit.json`에서 첫 제목은 rect
  `[189,351,524,27]`, 다음 `LAB01 · 저감쇠`는 `[189,517,524,27]`이었다. 창 하단
  519를 넘어 “다음 제목 전체 노출” gate와 반응형 구조 source gate가 함께 실패했다.
- 카드 폭이 560px 이상일 때만 제목 행 아래에 2열 목적+CTA를 사용하고 높이를 128px로
  낮췄다. 더 좁은 다열 카드에서는 154px 세로 구조를 유지해 목적 문장의 가로 공간을
  희생하지 않는다. 목적은 최대 2줄, 버튼은 기존 124×48px, 접근성 이름과 설명은 같다.
- green: `outputs/_qt_explore_card_density_green/ui_audit.json`에서 다음 제목은
  `[189,491,524,27]`로 이동해 하단 518에서 끝난다. 640px의 완전 노출 제목은 1→2,
  1280px에서는 완전한 Start 6개와 제목 8개가 첫 viewport에 보인다.
- 캡처 관능 대리 평가에서 제목→목적→시작의 수평 흐름이 짧아지고 두 열의 CTA 기준선이
  맞는다. 활성 실험 중에는 같은 구조에서 Start만 회색으로 내려가 차단 이유와 카드
  구조가 흔들리지 않는다. KO/EN·100%/200%·검색·필터·키보드 탐색 감사
  `outputs/_qt_explore_card_density_explore_final/ui_audit.json`은 15/15다.
- 최종 `outputs/_qt_explore_card_density_full_final/ui_audit.json`은 software UI
  122/122, `outputs/_qt_explore_card_density_gl_final/ui_audit.json`은 실제 EGL 10/10이며,
  Python 회귀는 428 tests + 1017 subtests를 통과했다.

## 2026-07-16 결과 관리 모달 surface 일관성 반복

오류 모달은 흰색·12px radius·2px `#64748B` 경계를 명시하지만, 저장 결과 관리 모달은
플랫폼 기본 사각형·검은 1px 경계를 사용했다. 삭제·재실행처럼 신뢰가 중요한 작업에서
같은 앱의 두 모달이 서로 다른 제품처럼 보여, 공용 surface 규칙을 적용했다.

- red: `outputs/_qt_result_manage_surface_red/ui_audit.json`에서 640px 한국어와 200%
  영어 Dialog 모두 목표색 최소 거리가 `114.49`, perimeter 픽셀이 `0`이었다. 명시적
  배경·radius·경계를 요구한 source gate도 함께 실패했다.
- `ResultManageDialog`에 흰색 배경, 12px radius, 2px `#64748B` 경계를 추가했다.
  `outputs/_qt_result_manage_surface_green2/ui_audit.json`에서 640px은 2,824px,
  200%는 11,300px의 목표색 perimeter를 검출했고 최소 거리는 모두 `0.0`이다.
- 첫 green을 Python 테스트와 동시에 캡처했을 때 한 번 한국어 glyph 일부가 사라지는
  렌더 타이밍 오염이 관찰됐다. 단독 재캡처에서는 재현되지 않았으며, 이후 UI 캡처는
  다른 Qt/Python 작업과 병렬 실행하지 않는 검증 운영 규칙으로 남겼다.
- 캡처 관능 대리 평가에서 관리 모달이 dim layer·배경 카드와 분명히 분리되고 오류
  모달과 같은 표면 언어를 사용한다. 당시 파란 재실행, 빨간 영구 삭제, 윤곽 닫기의 행동
  위계와 노란+검은 초기 포커스는 유지됐다. 결과 화면 집중 감사
  `outputs/_qt_result_manage_surface_results_final/ui_audit.json`은 18/18이다.
- 최종 `outputs/_qt_result_manage_surface_full_final/ui_audit.json`은 software UI
  122/122, `outputs/_qt_result_manage_surface_gl_final/ui_audit.json`은 실제 EGL 10/10이며,
  Python 회귀는 428 tests + 1017 subtests를 통과했다.

이 단락의 영구 삭제 계약은 역사적 기록이며 2026-07-21 SAFE-01의 recoverable
quarantine + receipt/restore 계약으로 대체됐다.

## 2026-07-16 compact 체크박스 라벨 줄바꿈 반복

640×360 실험의 `Advanced settings`와 200% 오류 모달의 `기술 세부정보 보기`가
44px 체크박스 안에서 두 줄로 접혔다. 주변에는 가로 공간이 남았고 두 라벨 모두 짧은
상태 전환이므로, 두 줄은 정보량이 아니라 공용 `WordWrap` 정책이 만든 시각 잡음이었다.

- red: `outputs/_qt_checkbox_label_wrap_red2/ui_audit.json`에서 두 라벨의 실제 glyph 세로
  범위가 각각 32px였다. 한 줄 상한 22px의 source/render gate가 함께 실패했다.
- 공용 `MCheckBox`를 `Text.NoWrap`으로 바꿨다. 첫 green 캡처에서 한국어는 13px로
  줄었지만 영어는 포커스 링의 오른쪽 검은 세로선을 글자로 집계해 32px로 남았다.
  제품 폭을 불필요하게 늘리지 않고, oracle이 indicator와 focus perimeter를 제외한 뒤
  안티앨리어싱된 body glyph만 측정하도록 보정했다.
- `outputs/_qt_checkbox_label_wrap_green3/ui_audit.json`에서 영어는 16.0px, 200% 한국어는
  13.5px다. checked/unchecked indicator, 세부정보 펼침→접기, 44px 조작 높이도 4/4
  유지됐다.
- 캡처 관능 대리 평가에서 두 문구가 indicator와 한 기준선에 놓이고, 영어 compact
  제어 패널과 한국어 오류 모달 모두 수직 여백이 안정됐다. 노란+검은 키보드 포커스와
  파랑/윤곽 상태 중복 표현도 그대로 보존됐다.
- 최종 `outputs/_qt_checkbox_label_wrap_full_final/ui_audit.json`은 software UI
  121/121, `outputs/_qt_checkbox_label_wrap_gl_final/ui_audit.json`은 실제 EGL 10/10이며,
  Python 회귀는 428 tests + 1017 subtests를 통과했다.

## 2026-07-16 오류 모달 surface 경계와 perimeter oracle 반복

페이지 전환 뒤 노란 내비게이션 링을 먼저 의심했지만 접근성 트리의 실제 focused 항목과
일치했고, 키보드 사용자가 돌아갈 위치를 보존하므로 유지했다. 대신 오류 모달은 흰 면에
1px `#A9B8CE` 외곽을 사용해 계산 대비가 약 2.01:1로, 공용 입력·버튼의 4.76:1
경계보다 흐리고 3:1 비텍스트 UI 기준에도 미달했다.

- 첫 role-aware oracle은 Dialog rect perimeter에서 목표 `#64748B`까지의 최소 거리만
  측정했다. `outputs/_qt_error_dialog_boundary_red/ui_audit.json`이 거리 `8.83`으로
  통과했지만, 이는 둥근 모서리 안티앨리어싱의 우연한 한두 픽셀로도 통과하는 오탐이었다.
- 사전에 200% 2px 경계의 목표색 근접 픽셀을 최소 1,000개로 정하고 면적 oracle을
  추가했다. `outputs/_qt_error_dialog_boundary_red2/ui_audit.json`에서 실제 값은 8px뿐이라
  source gate와 렌더 gate가 함께 실패했다.
- 오류 모달 외곽을 2px `#64748B`로 바꿔 흰 면 대비 4.76:1을 확보했다.
  `outputs/_qt_error_dialog_boundary_green/ui_audit.json`에서 최소 거리는 `0.0`, 목표색
  근접 perimeter는 9,585px로 증가했다.
- 캡처 관능 대리 평가에서 모달은 dim layer와 분명히 분리되지만, amber 복구 행동과
  파란 `닫기`보다 강하게 튀지 않는다. 집중 오류 감사
  `outputs/_qt_error_dialog_boundary_errors_final/ui_audit.json`의 100%·200% 오류,
  세부정보 펼침→접기, 원래 포커스 복귀 5/5도 통과했다.
- 최종 `outputs/_qt_error_dialog_boundary_full_final/ui_audit.json`은 software UI
  121/121, `outputs/_qt_error_dialog_boundary_gl_final/ui_audit.json`은 실제 EGL
  10/10이며, Python 회귀는 428 tests + 1017 subtests를 통과했다.

## 2026-07-16 다수 결과의 전역 주요 행동 위계 반복

캡처에서 흐려 보였던 학습 안내를 먼저 의심했지만, 홈 다음 실험 목적·탐색 카드 목적의
실제 token 거리는 `0.0`, 기록 재생 설명은 `11.58`로 모두 24 기준을 통과했다.
소스 색도 `#334155`·`#475569`라 대비가 충분하므로 보조 본문을 불필요하게 진하게
만드는 가설은 기각했다.

실제 결함은 60개 결과 화면에서 최신 카드와 `이전 2` 카드의 재실행이 동시에 채운
파랑으로 표시돼, 화면 전체의 “지금 할 다음 행동”이 둘로 경쟁한다는 점이었다.

- red: `outputs/_qt_results_primary_hierarchy_red/ui_audit.json`에서 최초 20개와 40개
  공개 상태 모두 primary가 2개였고, 이름은 `Latest`와 `Older 2`의 같은 설정 재실행이었다.
  최신 결과 하나만 primary로 요구한 source gate와 렌더 gate가 함께 실패했다.
- 카드의 행동·이름·설명·키보드 순서는 유지하고, 반복 목록 `index > 0`의 첫 행동만
  공용 고대비 secondary 스타일로 낮췄다. 최신 카드의 다음 행동은 기존 파란 채움을
  그대로 사용한다.
- `outputs/_qt_results_primary_hierarchy_green/ui_audit.json`에서 20개·40개 공개 상태
  모두 primary는 최신 카드의 1개로 줄었고, 접근 가능한 컨트롤은 각각 66·126개로
  유지됐다. `outputs/_qt_results_primary_hierarchy_results_final/ui_audit.json`의 빈 상태,
  정상·손상 결과, batch, 관리, 삭제, 60개 확장과 키보드 왕복 17/17도 통과했다.
- 캡처 관능 대리 평가에서 최신 카드의 파란 다음 행동이 첫 시선을 받고, 오래된 카드의
  재실행·리포트·관리는 같은 2px 윤곽군으로 물러나지만 클릭 가능성은 유지된다.
- 최종 `outputs/_qt_results_primary_hierarchy_full_final/ui_audit.json`은 software UI
  121/121, `outputs/_qt_results_primary_hierarchy_gl_final/ui_audit.json`은 실제 EGL
  10/10이며, Python 회귀는 427 tests + 1017 subtests를 통과했다.

## 2026-07-16 기록 위치 가독성과 타임라인 공간 반복

compact 기록 재생의 `프레임 31 / 61 · 0.50 s` 위치 문구는 9px bold였다. 색은
`#334155`로 충분했지만 실제 640px 캡처에서 타임라인·이벤트 마커보다 지나치게 작아
현재 프레임과 시간을 빠르게 읽기 어려웠다.

- red: `outputs/_qt_replay_position_typography_red/ui_audit.json`에서 한국어·영어·200%
  세 위치 문구의 접근성 line box는 모두 14px였다. 실제 token 거리는 `0.0`~`2.24`라
  대비가 아니라 크기 결함임을 확인했고, source gate도 compact 9px을 재현해 실패했다.
- 첫 11px 시도는 `outputs/_qt_replay_position_typography_green/ui_audit.json`에서
  line box 16px에 그쳐 사전 17px 기준을 통과하지 못했다. 기준을 사후 완화하지 않고
  12px bold를 적용해 line box를 18px로 높였다.
- 12px만 적용한 `outputs/_qt_replay_position_typography_green2`의 200% 캡처에서는
  타임라인 rect `[97,358,612,24]`와 위치 문구 `[597,362,112,18]`가 겹쳐 마지막
  핸들이 `1.00 s` 위를 가리는 2차 심미 결함이 드러났다.
- 위치 문구의 오른쪽 전용 영역을 확보하고 타임라인과 이벤트 마커는 남은 왼쪽 영역을
  같은 비율로 공유하도록 바꿨다. 접근성 rect 두 개가 겹치면 실패하는 non-overlap
  oracle도 추가해 글자 크기를 다시 낮추는 방식으로 회피할 수 없게 했다.
- `outputs/_qt_replay_position_typography_green3/ui_audit.json`은 640px 한국어·영어,
  200% 영어와 밀집 이벤트 4/4를 통과했다. 위치 문구 line box는 18px, token 거리는
  세 환경 모두 `0.0`이고 타임라인과 겹침은 0이다. 기록 재생 전체 변형
  `outputs/_qt_replay_position_regression/ui_audit.json`도 6/6을 통과했다.
- 최종 `outputs/_qt_replay_position_full_final/ui_audit.json`은 software UI 121/121,
  `outputs/_qt_replay_position_gl_final/ui_audit.json`은 실제 EGL 10/10이며, Python
  회귀는 426 tests + 1017 subtests를 통과했다.

## 2026-07-16 결과 수치 라벨 타이포그래피 반복

결과 카드의 `최대 변위`, `기록 시간`, `학습자 조작` 라벨은 source 색이
`#475569`라 흰 카드에서 7.58:1, 수치 배경에서 6.92:1로 충분했다. 따라서 처음의
“보조색 대비가 낮다”는 가설은 기각했다. 실제 결함은 10px regular 글꼴의 접근성
line box가 15px에 그치고, 100% 확대 안티앨리어싱에서 글자 중심이 의미색까지
도달하지 못해 작고 흐리게 보인다는 점이었다.

- red: `outputs/_qt_result_metric_typography_red/ui_audit.json`에서 세 라벨의 line box는
  모두 15px였다. 640px 한국어의 실제 token 거리는 `22.56`~`71.20`, 1280px 영어는
  `102.44`~`119.25`였고, 200% 캡처에서만 `0.0`이었다. source gate도 10px 라벨을
  재현해 실패했다.
- 12px regular는 line box를 18px로 높였지만 100% token 거리가 최대 95여서 충분하지
  않았다. `DemiBold`는 현재 번들 폰트와 Qt 조합에서 렌더링 차이가 없어 제거했다.
  최종적으로 지원이 확인된 12px bold를 사용했다.
- focused green: `outputs/_qt_result_metric_typography_green3/ui_audit.json`에서 640px
  한국어, 1280px 영어, 200% 한국어의 아홉 라벨이 모두 18px이며 token 거리는
  `0.0`~`3.46`이다. 14px bold mono 수치는 크기·색·서체로 계속 우선한다.
- `outputs/_qt_result_metric_results_final/ui_audit.json`은 빈 결과, 정상·손상 결과,
  실행 중·완료·오래된 batch, 10/20/60개 결과, 키보드 스크롤을 포함한 결과 화면
  17/17을 통과했다.
- 최종 `outputs/_qt_result_metric_full_final/ui_audit.json`은 software UI 120/120,
  `outputs/_qt_result_metric_gl_final/ui_audit.json`은 실제 EGL 10/10이며, Python 회귀는
  425 tests + 1017 subtests를 통과했다.

## 2026-07-16 체크박스 상태 인지와 선택→해제 반복

오류 모달의 `기술 세부정보 보기`와 실험 패널의 `고급 설정`은 Qt 기본 체크박스를
사용했다. 미선택 indicator의 `(189,189,189)` 경계는 흰색에서 약 1.88:1이어서
배경과 합쳐졌고, 선택 상태도 흰 면 안의 파란 윤곽에 의존해 상태 변화가 약했다.

- red: `outputs/_qt_checkbox_contrast_red2/ui_audit.json`에서 미선택 `#64748B` 픽셀은
  0개였다. 선택 상태의 파란 픽셀은 832개로 미리 정한 채운 indicator 최소 1,200개에
  못 미쳤고, 공용 high-contrast component source gate도 실패했다.
- 접근성 이름만으로 indicator를 찾는 첫 oracle은 펼쳐진 TextArea가 같은 이름을 써
  체크박스를 덮어쓰는 결함이 있었다. 이름과 `CheckBox` 역할을 함께 요구하도록 고쳐
  실제 native 선택값 832를 정확히 측정했다.
- 새 `MCheckBox`는 전체 높이 44px, indicator 28px, 미선택 2px `#64748B`, 선택
  `#2563EB` 면+흰 `✓`를 사용한다. 포커스의 노랑+검정 외곽과 접근성 checked 상태가
  선택 색·모양과 중복되므로 어느 한 표현만으로 상태를 판단하지 않는다.
- `outputs/_qt_checkbox_contrast_green2/ui_audit.json`은 100% 고급 설정 선택 511px,
  200% 오류 상세 선택 2,131px, 미선택 경계 760px로 3/3 통과했다. 즉시 포커스 기록이
  스크롤 반영 전 좌표를 잡던 smoke timing도 한 이벤트 뒤 기록하도록 보정했다.
- `outputs/_qt_checkbox_state_green/ui_audit.json`은 Space 선택→해제 뒤 상세 원문이
  접히고 포커스가 남으며 checked가 `false`로 복구되는 과업까지 4/4 통과했다.
- 최종 `outputs/_qt_checkbox_full_final/ui_audit.json`은 software UI 119/119,
  `outputs/_qt_checkbox_gl_final/ui_audit.json`은 실제 EGL 10/10이며, Python 회귀는
  424 tests + 1017 subtests를 통과했다.

## 2026-07-16 공용 보조 버튼 대비와 행동 위계 반복

홈의 `건너뛰기`, 실험의 Step·Restart, 결과의 Report·Manage처럼 중요한 보조 행동이
흰 배경 위 1px `#A9B8CE` 윤곽을 사용했다. 계산 대비는 흰색에서 2.01:1,
앱 배경 `#F5F7FB`에서 1.88:1이어서 3:1 UI 기준을 충족하지 못했고, 캡처에서는
버튼보다 텍스트 링크나 비활성 영역처럼 보였다.

- red: `outputs/_qt_secondary_button_contrast_red/ui_audit.json`에서 홈·실험·결과의
  다섯 표본이 목표 `#64748B` perimeter pixel 거리 117.79로 모두 실패했다. 공용
  `MButton` source gate도 1px 저대비 경계를 정확히 재현했다.
- 공용 보조 버튼을 2px `#64748B`로 바꿔 흰 배경 4.76:1, 앱 배경 4.44:1을 확보했다.
  파란 주요 행동의 채움, 흰 보조 배경, hover/pressed 배경, 4px 노랑+2px 검정 포커스,
  빨간 위험 행동은 그대로 유지했다.
- `outputs/_qt_secondary_button_contrast_green/ui_audit.json`은 홈 `건너뛰기`, 실험
  `Advance 0.1 s`·`Restart`, 결과 `View report`·`Manage`를 5/5 통과했다.
  `outputs/_qt_secondary_button_edge_green/ui_audit.json`은 다시 보기, 결과 관리의 폴더,
  200% 오류 복사를 3/3 추가 검증했다. 여덟 경계 모두 pixel 거리 0.0이다.
- 캡처 관능 대리 평가에서 홈은 `다음 실험 시작`, 결과는 `Replay recording`, 실험은
  `Pause` 한 개만 채워진 파랑으로 남았다. 윤곽 버튼은 클릭 가능성이 분명해졌지만
  primary action으로 오분류되지 않았다.
- 최종 `outputs/_qt_secondary_button_full_final/ui_audit.json`은 software UI 117/117,
  `outputs/_qt_secondary_button_gl_final/ui_audit.json`은 실제 EGL 10/10이며, Python
  회귀는 423 tests + 1016 subtests를 통과했다.

## 2026-07-16 핵심 증거 입력 대비와 compact 문구 반복

예측·관찰·예측 결과는 학습 경로를 완료하는 핵심 입력인데도 흰 배경에 1px
`#94A3B8` 경계를 사용했다. 계산 대비는 2.56:1로 비텍스트 UI 3:1 기준에 못 미쳤고,
탐색 검색·필터보다 비활성 영역처럼 보였다. 640px 영어 관찰 카드에서는
`Save observation`과 `Choose an outcome`도 두 열 안에서 잘렸다.

- red: `outputs/_qt_evidence_boundary_red/ui_audit.json`에서 한국어 예측, 영어 관찰,
  영어 결과 선택의 목표 `#64748B` perimeter pixel 거리가 모두 80.86이었다. source
  회귀도 세 컨트롤의 고대비 비활성 경계 부재로 실패했다.
- 세 컨트롤의 비활성 경계를 2px `#64748B`로 통일해 흰 배경 대비를 4.76:1로
  높였다. 포커스 때의 4px 노랑+2px 검정 중복 표시는 그대로 유지한다.
- 접근성 rect의 전체 내부가 아니라 바깥 3px 띠만 측정하는 pixel oracle을 추가했다.
  따라서 같은 `#64748B` placeholder 글자가 잘못된 경계색을 우연히 통과시키지 못한다.
- compact 영문 버튼은 화면에 `Save`, 결과 선택은 `Outcome…`으로 표시하고 접근성 이름은
  각각 `Save observation`, `Prediction outcome` 전체를 유지했다. 한국어도 같은 stable
  translation key를 사용한다.
- 최종 집중 검증 `outputs/_qt_evidence_workflow_focused/ui_audit.json`은 예측→조작→관찰,
  완료·재시작, 200% 한·영 9/9를 통과했다. 전체
  `outputs/_qt_evidence_boundary_full_final/ui_audit.json`은 software UI 117/117,
  `outputs/_qt_evidence_boundary_gl_final/ui_audit.json`은 실제 EGL 10/10이며, Python
  회귀는 423 tests + 1016 subtests를 통과했다.

## 2026-07-16 탐색 검색창 대비와 제어군 일관성 반복

탐색의 난이도·방식 필터는 2px 고대비 윤곽을 사용하지만, 바로 옆 검색창은 Qt 기본
placeholder와 1px 경계를 그대로 사용했다. 실제 캡처의 주 회색은 `(189,189,189)`로
흰 배경 대비가 약 1.88:1뿐이어서 입력 가능한 제어보다 비활성 영역처럼 보였다.

- red: `outputs/_qt_explore_search_contrast_red/ui_audit.json`에서 한국어 640과 영어
  1280 모두 placeholder `#5B6475` pixel 거리가 80.0, 경계 `#64748B` 거리가 57.6으로
  사전 한계 18을 크게 넘었다. source 회귀도 명시적 placeholder·경계 token 부재로 실패했다.
- 검색창에 본문 `#172033`, placeholder `#5B6475`, 흰 배경, 2px `#64748B`, 8px radius,
  12px 좌우 여백을 명시해 옆 필터와 같은 제어군으로 보이게 했다. 계산 대비는 각각
  5.96:1과 4.76:1로 text 4.5:1·UI 3:1 기준을 통과한다.
- 영어의 얇은 획은 software renderer가 지정색을 약 7% 흰색과 혼합해 source token이
  정확해도 최소 pixel 거리가 19.7이었다. Medium/DemiBold probe에서도 값이 같아 색 실패가
  아니라 anti-alias 측정 특성임을 확인했다. source exact+계산 대비 gate를 유지하고 pixel
  oracle만 24로 보정했다. red 80.0과는 충분히 분리된다.
- `outputs/_qt_explore_search_contrast_3size_green/ui_audit.json`은 640 한국어
  `6.4/0.0`, 1280 영어 `19.7/0.0`, 200% 한국어 `0.0/0.0`으로 3/3을 통과했다.
  입력 후 포커스·다중 검색·빈 결과·언어 전환·활성 작업 차단 등 탐색 15/15도 통과했다.
- 최종 `outputs/_qt_explore_search_full_final/ui_audit.json`은 software UI 115/115,
  `outputs/_qt_explore_search_gl_final/ui_audit.json`은 실제 EGL 10/10이며, 전체 Python
  회귀는 422 tests + 1016 subtests를 통과했다.

## 2026-07-16 3D 카메라 발견성과 일시정지 갱신 반복

장면은 마우스로 회전·이동·확대할 수 있었지만 화면과 접근성 트리에 사용법이 없었고,
`카메라 초기화`의 설명도 비어 있었다. 또한 예측 대기처럼 물리가 일시정지된 상태에서는
카메라 값만 초기화되고 마지막으로 움직인 프레임이 계속 보여, 버튼이 작동하지 않는 것처럼
보였다. Lab04는 첫 step 전 `wall_x=10` 임시값을 사용해 예측해야 할 벽도 화면 밖에 있었다.

- red: `outputs/_qt_camera_discovery_red/ui_audit.json`은 영문 hover와 한국어 keyboard
  focus 모두 0/2였다. 장면·버튼 설명에서 drag orbit, right-drag pan, wheel zoom과
  한국어 대응 문구가 누락됐다.
- 첫 green의 툴팁은 장면 위에서 실험 제목을 가리는 심미 결함이 있어 제거했다. 도움말은
  기존 `카메라 초기화` 버튼 hover/focus에 고정하고 장면에는 open/closed-hand cursor만
  남겼다. `outputs/_qt_camera_discovery_regression/ui_audit.json`은 2/2를 통과했다.
- keyboard red: 이름과 달리 기존 회귀는 reset 버튼의 keyboard focus만 검사했다.
  `outputs/_qt_camera_keyboard_red/ui_audit.json`에서 장면 키 입력 5/5의 실제 포커스가
  모두 창 루트 `MCLab`으로 기록됐고 Arrow·Shift+Arrow·`+/-`·`0` 안내와 검정 외곽선도
  누락됐다.
- 장면을 Tab 가능한 `Graphic`으로 만들고 방향키=orbit, Shift+방향키=pan,
  `+/-`=zoom, `0`=reset을 추가했다. 첫 구현의 긴 툴팁은 compact 장면을 158→67px로
  쪼개는 2차 심미 실패를 만들었다. 툴팁 너비를 우측 패널에 고정하고, 장면 포커스 중에는
  하단 범례만 11px 짧은 키 안내로 잠시 교체해 추가 상시 UI 없이 158px를 복원했다.
- 실제 EGL red에서는 orbit `azimuth 120→136.8`, pan `lookat x -0.0045→-0.1476`,
  zoom `distance 1.9882→1.7497`, reset의 내부 값 복원까지 성공했지만 화면은 이동한
  프레임에 남았다. view action 직후 렌더러 소유 worker에서 현재 프레임을 다시 발행하도록
  수정했다.
- Lab04 준비 단계가 configured Cartesian target과 wall 위치를 semantic state에 넣도록
  수정해 0.00초 예측 화면부터 목표와 격자 벽을 보인다. 최종
  mouse 최종 trace는 `outputs/_qt_camera_discovery_gl_final/ui_audit.json`에 보존했다.
- keyboard EGL은 우측 방향키 orbit `azimuth 120→124.2`, Shift+방향키 pan
  `lookat z 0.5283→0.4925`, `+` zoom `distance 1.9882→1.7497`, `0` reset 완전 복원을
  기록했다. 최종 묶음의 일시정지 물리 시간은 다섯 표본 모두 `0.708000 s`여서 기존 Right=Step과의
  중복 실행도 0건이다.
- 최종 전체 software UI는 `outputs/_qt_camera_keyboard_full_final/ui_audit.json`
  114/114, 실제 EGL은 `outputs/_qt_camera_keyboard_gl_final/ui_audit.json` 10/10,
  Python 회귀는 421 tests + 1016 subtests를 통과했다.

## 2026-07-16 실험·배경 세션 Lab 문맥 연속성 반복

탐색 카드에서 `LABxx · 제목`을 제공한 뒤에도 실험에 진입하면 헤더가 `직접 조작 ·
실행 중` 또는 `Interactive · Paused`로 되돌아갔다. 다른 화면으로 이동한 pause/replay
세션 바도 raw 제목만 사용했고, 저장 중 분기는 제목 자체를 버렸다. 같은 이름이 여러
Lab에 존재하므로 초보자가 현재 실험 문맥을 화면 전환마다 다시 추론해야 하는 결함이다.

- red: `outputs/_qt_session_context_red/ui_audit.json`은 compact 한국어 실험,
  200% 영어 pause, 1280px 영어 탐색 배경, compact 영어 replay가 모두 0/4였다.
  각 경로는 크기·포커스·조작 대상 기준은 통과하고 `LAB01` 문맥만 누락했다.
- 상태 전이 red: `outputs/_qt_session_saving_context_red/ui_audit.json`은
  `실험 증거 저장 중…`은 보이지만 상세 문장에 scenario가 없는 것을 별도로 재현했다.
- 수정: catalog가 이미 제공하는 `displayTitle`을 실험 헤더와 공용 `ActiveSessionBar`가
  그대로 사용한다. pause·replay·saving 분기 모두 상세 문장 뒤에 같은 제목을 붙이며,
  별도 문자열 추론이나 번역 중복은 추가하지 않았다.
- 범위 green: `outputs/_qt_session_context_regression/ui_audit.json` 5/5이다.
  640×360 실험 제목은 한 줄, 200% active bar는 두 줄로 자연스럽게 감싸고,
  1280×720 탐색의 70개 카드와 compact replay/result도 잘림·이름 누락·조작 대상 미달
  0건이다.
- 전체 software: `outputs/_qt_session_context_full/ui_audit.json`은 110/111이었다.
  유일한 실패는 제품이 아니라 옛 `… · 직접 조작`을 요구한 감사 oracle 한 곳이며,
  이를 새 공용 규칙으로 고친 뒤
  `outputs/_qt_session_context_full_repair/ui_audit.json` 1/1을 통과해 현재 111-case
  union을 닫았다.
- 실제 GPU: `outputs/_qt_session_context_final_gl/ui_audit.json` 8/8이다. 실제 Lab01
  장면에도 `LAB01 · 직접 조작 · 실행 중`이 한 줄로 남고, 3회 재시작 RSS 증가는
  6,916 KB/65,536 KB, 교차 scenario 교체와 Panda replay의 SIGSEGV/EGL 오류는 0건이다.
- 코드 회귀: `outputs/_qt_session_context_final_validation/pytest.xml`의 418 tests +
  1,016 subtests, 앱 범위 74 tests + 251 subtests, failure·error·skip 0이며 Ruff와
  doctor 7/7도 통과했다.

## 2026-07-16 탐색 Lab 문맥과 EGL 재시작 안정성 반복

캡처와 접근성 트리를 함께 대조하자 실행 버튼은 `Start: LABxx · 제목`으로 고유했지만,
화면에는 `자동 데모`, `Auto demo`, `Interactive` 같은 일반 제목만 보여 초보자가 어느
Lab인지 카드만 보고 구분하기 어려웠다. 같은 반복에서 완료한 실험을 다시 시작할 때
첫 프레임의 `mjr_render`가 간헐적으로 SIGSEGV를 일으키는 네이티브 수명주기 결함도
faulthandler stderr로 확정했다.

- 제목 red: `outputs/_qt_explore_title_context_red/ui_audit.json`은 영어 70개 실행
  버튼이 모두 고유하면서도 대응하는 보이는 문맥 제목은 0/70이었다.
- 제목 green: 표시 제목과 접근성 이름을 같은 `displayTitle` 단일 값으로 묶었다.
  `outputs/_qt_explore_title_context_regression/ui_audit.json` 12/12에서 한·영 전체
  70/70, 직접 조작 9, `lab04 wall` 14, 중급 직접 조작 2, 빈 결과 0→초기화 70을
  100%·200%로 통과했다. 긴 제목이 생략돼도 `LABxx ·` 접두사는 남는다.
- EGL red: `outputs/_qt_explore_title_context_gl/ui_audit.json`은 6/7이었고 저장된
  `gl_restart_cleanup_640_ko_stderr.txt`는 새 세션 첫 `mjr_render`를 실패 지점으로
  기록했다. 스레드별 EGL context만 재사용한 첫 수정도
  `outputs/_qt_egl_context_reuse_stress_2`의 두 번째 반복에서 다시 실패했다.
- EGL green: 같은 scenario/config 재시작은 이전 adapter의 MuJoCo model·data·renderer·
  camera를 물리 스레드 안에서 정확히 인계하고 plant만 reset한다. 다른 scenario는 이전
  worker를 완전히 종료한 뒤 새 QThread에서 새 네이티브 자원을 만든다. 감사 도구는 각
  사례의 stdout·stderr를 별도 저장해 이후 native 실패도 유실하지 않는다.
- 반복 결과: `outputs/_qt_egl_render_resource_handoff_stress_1`~`5`에서 각 3회,
  총 15/15 완료→재시작이 통과했고 RSS 증가는 11,368~41,172 KB로 64 MB 기준 이하다.
  `outputs/_qt_egl_cross_scenario_green/ui_audit.json`은 Lab01 hands-on 완료 뒤 다른
  Lab01 자동 scenario로 worker를 교체하는 경로를 통과했다.
- 최종 실제 GPU 묶음은
  `outputs/_qt_explore_title_context_final_gl/ui_audit.json` 8/8이며 재시작·교차
  scenario·Panda replay의 SIGSEGV/EGL 오류는 0건이다. 전체 회귀는
  `outputs/_qt_explore_title_context_final_validation/pytest.xml`의 418 tests +
  1,016 subtests, failure·error·skip 0이고 Ruff와 doctor 7/7도 통과했다.

## 2026-07-16 큰 화면 둘러보기 연속성 반복

적대적 캡처 검토에서 1280·1920px의 번호·단계 문구가 수백 픽셀씩 떨어져 있으면서
관계를 잇는 표현이 없어, 세 개의 독립 항목처럼 보이는 Gestalt 단절을 찾았다. 작은
화면의 짧은 번호 흐름은 유지하되 큰 화면에만 단계 연결선을 추가했다.

- red: `outputs/_qt_tour_connectors_red_final/ui_audit.json`에서 1280·1920px 모두
  연결선 0 px로 실패했다.
- 첫 green은 연결선 884·2,312 px를 만들었지만 `#BFDBFE`와 흰 카드의 대비가
  1.42:1뿐이었다. 관계를 보강하려고 넣은 선이 저시력 환경에서 사라지는 모순이라
  `#4F8FF7` 3.18:1로 보정했다.
- 최종 green: `outputs/_qt_tour_connectors_contrast_green/ui_audit.json` 7/7이다.
  1280px 영어는 884 px, 1920px 한국어는 2,312 px로 미리 정한 최소·최대 범위 안이고,
  640px 한국어와 실제 200% 확대 영어는 모두 0 px다. 조작 대상 미달·창 밖·이름 누락은
  각각 0이다.
- 키보드 베타 대리 과업: 건너뛰기→다음 실험, 다시 보기→건너뛰기 포커스 trace 5/5,
  노란 포커스 면 508~656 px를 유지했다.
- 실행 중 진단 엣지: 일반 앱을 켠 상태에서 `app --self-test`가 중복 실행 잠금에 막혀
  rc 6이 되는 red를 `outputs/_qt_self_test_instance_red/pytest.xml`로 보존했다.
  self-test만 임시 잠금을 사용하고 원래 환경을 복원하도록 바꾼 뒤
  `outputs/_qt_self_test_instance_green/pytest.xml`이 통과했다.
- 코드 회귀: 실제 앱이 켜진 상태에서
  `outputs/_qt_tour_connectors_validation/pytest.xml`의 415 tests + 1,014 subtests,
  failure·error·skip 0이며 Ruff와 doctor 7/7도 통과했다.
- 실제 GPU: 이 시점의 계측은 `outputs/_qt_tour_connectors_gl_trace/ui_audit.json`
  7/7과 `outputs/_qt_gl_restart_trace_1`~`7` 연속 통과였지만 간헐 SIGSEGV가 남았다.
  위의 후속 반복에서 불충분한 context-only 재사용을 기각하고 renderer 자원 인계와
  교차-scenario worker 교체까지 적용해 원인 경계를 닫았다.

이 반복은 큰 화면에서만 선이 남도록 해 넓은 여백을 학습 순서로 바꾸고, 좁은 화면과
확대 화면에서는 기존의 간결한 `번호 + 짧은 문구` 배치를 그대로 보존한다.

## 2026-07-16 결과 복구 행동 반복

적대적 검토에서 결과 카드가 “같은 설정으로 재실행”을 권하면서도 해당 버튼을 관리
모달 안에 숨기고, 사용할 수 없는 `기록 재생`이 카드 폭을 계속 차지하는 모순을 찾았다.
또 정상 기록에서도 카드 안내는 재생을 권하지만 `리포트 보기`가 파란 주 행동이었다.

- red: `outputs/_qt_results_recovery_red/ui_audit.json`의 2/2 사례가 실패했다. 60개
  결과와 손상 기록 모두 직접 재실행 이름이 없었고 죽은 재생 버튼이 남았다.
- green: `outputs/_qt_results_recovery_full/ui_audit.json` 107/107, 영향 범위 묶음
  `outputs/_qt_results_recovery_regression/ui_audit.json` 20/20을 통과했다.
- 실제 GPU: `outputs/_qt_results_recovery_gl/ui_audit.json` 1/1을 추가해 전체 EGL
  감사가 5/5가 됐다.
- 키보드 베타 대리 과업: 손상 기록 카드의 첫 주 행동에 포커스하고 Enter를 누르면
  새 실험이 열려 0.12 s 시점 `running` 상태가 됐다. 조작 대상 미달·이름 누락은 0개다.
- 코드 회귀: `outputs/_qt_results_recovery_validation/pytest.xml`에서 1,427개
  test/subtest, failure·error·skip 0이며 Ruff와 doctor 7/7도 통과했다.

결과 카드는 이제 정상 기록=`기록 재생`, 기록 없음=`같은 설정 재실행`, 비교
결과=`리포트 보기`를 유일한 파란 주 행동으로 사용한다. 없는 리포트나 불가능한 재생은
숨기며, 재실행·튜닝·폴더·삭제의 전체 도구는 `관리`에서 계속 제공한다.

## 2026-07-16 스크롤 목록 키보드 문맥 반복

검색과 필터의 키보드 순서는 검증돼 있었지만, 그 다음 70개 탐색 카드와 20개 결과
카드를 Tab으로 이동하는 실제 좌표는 검증되지 않았다. 주입 측정 결과 첫 카드 다음부터
ScrollView가 포커스를 따라가지 않아 링이 화면 밖으로 사라졌다.

- red 탐색: `outputs/_qt_explore_card_focus_red/ui_audit.json`에서 저감쇠·과감쇠·높은
  강성 3개 포커스가 창 밖이었다. 버튼 y는 591→757→923까지 내려갔고 노란 링은 0 px였다.
- red 결과: `outputs/_qt_results_card_focus_red/ui_audit.json`에서 두 번째 실행부터 4개
  포커스가 창 밖이었다. 버튼 y는 660·872였고 노란 링은 0 px였다.
- red 관능 검토: 버튼만 보이게 스크롤하면 실행 제목이 앱 헤더 뒤 local y=15에 숨어
  무엇을 관리하는지 잃었다. `outputs/_qt_results_card_context_header_red/ui_audit.json`이
  제목-버튼 문맥 가림을 실패로 잡는다.
- green: 공용 `ScrollFocusHelper`가 버튼 한 개가 아니라 카드 전체를 노출한다. 탐색과
  결과에서 Tab 6회 뒤 Shift+Tab 4회를 되짚은 22개 이름·역할·좌표가 모두 창 안이다.
  최종 결과 제목은 local y=153, `Manage`는 y=289이며 링은 812 px다.
- 회귀: `outputs/_qt_scroll_focus_regression/ui_audit.json`의 탐색·결과 관련 32/32,
  `outputs/_qt_scroll_focus_gl/ui_audit.json`의 실제 EGL 1/1을 통과했다.
- 코드: `outputs/_qt_scroll_focus_validation/pytest.xml`에서 1,428개 test/subtest,
  failure·error·skip 0이며 Ruff와 doctor 7/7도 통과했다.

이 변경은 마우스 스크롤 위치를 강제로 초기화하지 않는다. 키보드 포커스가 새 카드로
이동할 때만 최소 거리로 스크롤하며, 좁은 결과 화면에서는 제목·결과·수치·다음 행동과
포커스 버튼이 한 카드로 함께 보이도록 한다.

## 2026-07-16 결과 점진 공개 포커스 반복

60개 결과의 `20개 더 보기`는 접근성 이름과 20개 단위 공개만 검증했고, 버튼을 실제
키보드로 누른 뒤의 포커스 위치는 검증하지 않았다. 첫 확장에서는 같은 버튼이 새 카드
20개 아래로 이동하고, 두 번째 확장에서는 버튼 자체가 사라져 읽기 위치를 잃었다.

- red: `outputs/_qt_results_load_focus_red/ui_audit.json`에서 확장 전 버튼 y=4,542,
  20→40 뒤 y=8,782, 40→60 뒤 rect=0×0이었다. 네 포커스 표본 모두 창 밖이고 링은 0 px였다.
- 첫 수정은 버튼을 y=463에 노출하고 포커스 이름을 `이전 21/41`로 인계했지만, 새 delegate
  높이 확정 전에 스크롤해 카드는 y=4,688/8,928에 남았다. 레이아웃 다음 이벤트 루프에서
  카드 전체를 reveal하도록 직렬화했다.
- green: `outputs/_qt_results_load_focus_green/ui_audit.json`에서 `더 보기` y=463,
  `이전 21`과 `이전 41` 주 행동 y=449, 링 1,112 px다. 최종 60개 카드의 185개 컨트롤은
  이름 중복·누락·44px 미달이 0이고, 사라진 `더 보기`에 포커스가 남지 않는다.
- 회귀: `outputs/_qt_results_load_regression/ui_audit.json`의 결과 관련 21/21과
  `outputs/_qt_results_load_gl/ui_audit.json` 실제 EGL 1/1을 통과했다.
- 코드: `outputs/_qt_results_load_validation/pytest.xml`에서 1,428개 test/subtest,
  failure·error·skip 0이며 Ruff와 doctor 7/7도 통과했다.

키보드와 포커스를 받은 포인터 클릭은 확장 직후 첫 새 카드로 이동한다. 직접 호출처럼
버튼에 포커스가 없으면 기존 스크롤을 유지하므로 자동화·마우스 보조 경로도 보존한다.

## 실제 전체 비교 베타 실행

가짜 fixture 없이 5개 비교 세트를 실제 앱과 같은 Qt 별도 프로세스로 실행했다. 빠른
생명주기 확인용 무-plot 실행 뒤, plot을 포함한 전체 경로를 두 번 수행해 반복성을 확인했다.
진행 신호는 매번 1/5부터 5/5까지 세트 이름과 함께 순서대로 도착했다.

| 항목 | 결과 |
|---|---:|
| 비교 세트 | 5개 |
| MuJoCo 시나리오 실행 | 54개 |
| 무-plot 벽시계 시간 | 49.22 s |
| plotted 벽시계 시간 | 159.63 s / 154.40 s |
| plotted UI heartbeat 최대 지연 | 27.3 ms / 27.2 ms |
| plotted 최대 RSS | 581,284 KB |
| plotted 저장 용량 | 52.5 MB |
| 생성 리포트 | 과정 6개 + 시나리오 54개 |
| 비교 plot | 33개 |

앱은 이 작업을 `QProcess`에서 실행하므로 진행 중에도 탐색·결과 화면을 사용할 수 있고,
완료 provenance와 artifact hash는 자식 프로세스에서 확정한다. 가장 긴 2DOF·DLS
세트를 처리할 때도 메인 이벤트 루프 지연은 기준의 5.5% 이하였다.

## 실제 GL 장면·색각 감사

| 장면 | 조작 상태 | 뷰포트 변화 픽셀 | 의미 마커 |
|---|---|---:|---|
| Lab01 질량-스프링-감쇠 | 예측 후 Push 외력 | 4.89% | 현재·목표·힘 검출 |
| Lab02 PID | 예측 후 Push 외란 | 1.01% | 현재·목표·힘 검출 |
| Lab03 2DOF | 예측 후 목표 X/Y 변경 | 1.92% | 현재·목표·작업공간 검출 |
| Lab04 가상 벽 | 깊은 목표·가까운 벽 | 16.03% | 현재·목표·벽·접촉 힘 검출 |

색각 이상 대리 검사는 protanopia, deuteranopia, tritanopia 행렬을 적용한다. 의미 색 사이
최소 RGB 거리는 각각 72.91, 58.17, 25.66으로 24 기준을 통과했고, 배경과의 최소 거리는
모두 222 이상이었다. 색만으로 구분하지 않도록 현재=원/실선, 목표=마름모/점선,
힘=화살표, 벽=격자, 작업공간=외곽 원도 함께 사용한다.

## 적대적 검증에서 수정된 결함

| 결함 | 수정 전 | 수정 후 |
|---|---|---|
| 오류 모달 surface 경계 | 흰 면의 1px `#A9B8CE`가 약 2.01:1로 배경·공용 4.76:1 경계보다 흐림 | 2px `#64748B` 4.76:1, 200% Dialog perimeter 목표색 9,585px |
| 모달 perimeter oracle 오탐 | 최소 거리만 측정해 둥근 모서리의 8개 우연 픽셀로 저대비 경계가 통과 | 역할+이름으로 Dialog를 고르고 목표색 근접 픽셀 최소 1,000개를 함께 요구 |
| 다수 결과 primary 경쟁 | 1280px에서 최신과 이전 2 카드의 재실행이 동시에 파란 채움으로 보여 다음 행동이 2개로 경쟁 | 최신 카드만 채운 파랑, 오래된 카드는 고대비 윤곽으로 유지해 20·40개 상태 primary `1` |
| compact 기록 위치 가독성 | 9px bold line box가 14px라 현재 프레임·시간이 타임라인보다 지나치게 작음 | 12px bold·18px line box, 한·영·200% token 거리 `0.0` |
| 확대 시 타임라인-위치 겹침 | 글자만 키우자 200%에서 마지막 핸들이 `1.00 s` 문구 위를 가림 | 위치 전용 영역과 공용 track 영역을 분리하고 접근성 non-overlap 3/3 검증 |
| 결과 수치 라벨 가독성 | 색 대비는 7.58:1이지만 10px regular line box가 15px이고 100% 실제 token 거리가 최대 119.25라 작고 흐림 | 12px bold·18px line box로 올려 한·영·200% 아홉 라벨의 token 거리를 `0.0`~`3.46`으로 축소 |
| 체크박스 미선택·선택 상태 | 기본 1px `(189,189,189)` 경계가 1.88:1이고 선택도 흰 면+파란 외곽이라 변화가 약함 | 28px indicator에 2px `#64748B`, 선택은 파란 면+흰 `✓`, checked 상태를 중복해 선택→해제 4/4 통과 |
| indicator 감사 이름 충돌 | 펼친 TextArea와 CheckBox의 같은 접근성 이름 때문에 뒤 항목이 indicator 측정을 덮어씀 | 이름뿐 아니라 `CheckBox` 역할을 요구해 native 832px와 새 2,131px을 정확히 분리 |
| 공용 보조 버튼 경계 | 흰 버튼의 1px `#A9B8CE`가 흰 카드에서 2.01:1, 앱 배경에서 1.88:1이라 링크·비활성 영역처럼 보임 | 2px `#64748B`로 4.76:1·4.44:1 확보, 홈·실험·결과·모달 8개 실제 perimeter 거리 0.0 |
| 핵심 증거 입력 경계 | 예측·관찰·결과 선택이 흰 배경 위 1px `#94A3B8`로 2.56:1에 그침 | 2px `#64748B` 4.76:1로 통일하고 실제 perimeter token 거리 세 곳 모두 0.0 |
| compact 영문 증거 문구 | `Save observation`과 `Choose an outcome`이 좁은 2열 카드에서 잘림 | 화면은 `Save`·`Outcome…`, 접근성 이름은 전체 문구로 분리해 의미와 공간을 함께 보존 |
| 탐색 검색 placeholder 대비 | Qt 기본 회색 `(189,189,189)`이 흰 배경에서 약 1.88:1이고 필터보다 비활성처럼 보임 | `#5B6475` 5.96:1을 명시하고 실제 640·1280·200% pixel oracle 3/3 통과 |
| 탐색 검색 경계 | 기본 1px 저대비 사각 경계가 옆 2px 둥근 필터와 다른 제어처럼 보임 | 2px `#64748B` 4.76:1·8px radius·12px padding으로 통일, 실제 token 거리 0.0 |
| 3D 카메라 조작 발견성 | 장면은 드래그에 반응하지만 회전·이동·확대 방법과 cursor·보조기술 설명이 없음 | open/closed-hand cursor, 초기화 버튼 hover/focus 도움말, 한·영 접근성 설명을 2/2 검증 |
| 3D 카메라 키보드 대안 | 장면은 Tab 대상이 아니고 reset 외 orbit·pan·zoom이 mouse-only | focus 가능한 Graphic, 방향키·Shift+방향키·`+/-`·`0`, 조건부 짧은 안내와 실제 EGL 1/1 추가 |
| compact 카메라 도움말 | 전체 키 설명을 기본 ToolTip에 넣자 장면을 가로질러 뷰포트가 158→67px로 분할 | ToolTip을 우측 패널 너비로 제한하고 줄바꿈해 장면 158px와 포커스 링 3,677px 보존 |
| 일시정지 카메라 프레임 | orbit/pan/zoom/reset이 camera 값만 바꾸고 다음 물리 render까지 이전 화면 유지 | view action마다 renderer 소유 worker에서 현재 프레임을 즉시 발행하고 paused 회귀·실제 EGL trace 검증 |
| Lab04 첫 예측 장면 | 첫 step 전 wall 임시값이 `x=10`이고 목표=현재라 벽·목표 관계를 예측할 수 없음 | prepare에서 resolved target·wall semantic state를 초기화해 0.00초부터 목표와 격자 벽 표시 |
| 학습 단계 표시 | hands-on 실행도 항상 3/5 `실험`으로 고정 | 예측·실제 조작·관찰 저장 상태에 따라 2/5→5/5 진행 |
| 초보자 증거 흐름 | 단계 이름만 있고 예측·관찰을 입력하거나 저장할 수 없음 | 예측을 먼저 확정하고 한 제어를 사용한 뒤 결과·관찰을 저장하는 3단계 카드 |
| 예측 예시 문맥 | Lab03 팔·특이점과 Lab04 관절·가상 벽에도 Lab01 감쇠/진동 예시를 재사용 | Lab01 감쇠, Lab02 P 게인, Lab03 추종·손 목표·특이점, Lab04 관절·손끝·접촉 힘의 8개 한·영 문맥으로 분리 |
| 200% 예측 말줄임 | 영어 가상 벽 예시의 `Contact force`가 좁은 입력창에서 잘림 | 모든 문장을 관찰량 우선형으로 바꾸고 핵심 용어가 첫 32자 안에 있는지 회귀 검사 |
| 증거 미완성인 채 실행 완료 | 비활성 조작을 계속 요구하고 `결과 보기`·`다시 시작`이 모두 파란색이며 Step으로 예측 전 진행 가능 | 불가능한 조작은 숨기고 Step을 잠금; `다시 시작→예측→한 조작→관찰`만 강조, 결과 보기는 보조 행동 |
| 완료 뒤 재시작 포커스 | 증거와 물리는 초기화되지만 키보드 포커스가 창 루트 `MCLab`으로 이탈 | 실제 Enter 재시작 뒤 0.00초 예측 입력에 노랑+검정 포커스 복원 |
| 예측 중 물리 진행 | learner가 문장을 쓰는 동안 실험 시간이 먼저 소비됨 | 준비 장면만 렌더하고 0.00초에서 대기, 예측 저장과 물리 시작을 같은 worker 명령으로 직렬화 |
| 다른 화면에서 숨은 물리 진행 | 홈 이동 뒤에도 `0.646→1.886→2.506 s`로 물리·기록이 계속됨 | 페이지 변경 전에 worker pause를 큐에 넣고 연속 표본이 같은 시각인지 검증 |
| 실험 이탈 뒤 복귀 경로 | 다른 화면에서는 활성 실험 존재와 종료 방법을 알 수 없음 | 네 화면 공통 세션 바에 상태·복귀·종료/저장을 상시 표시 |
| 화면 이동 뒤 숨은 포커스 | 보이지 않는 예측 입력이 포커스를 유지해 키보드 조작이 사라짐 | 목적지 내비게이션으로 포커스를 옮기고 창 내부 좌표를 검증 |
| 버튼 Enter 동작 | 일부 공용 버튼은 Space만 동작하고 Enter 복귀가 실패 | 공용 버튼이 Enter/Return/Space를 명시적으로 같은 click에 연결 |
| 활성 세션 중 시작 버튼 | 홈·경로·탐색 70개·결과 재생/재실행이 활성이라 누른 뒤 오류로 안내 | 충돌 행동을 미리 비활성화하고 같은 원인을 한·영 접근성 설명으로 제공 |
| 결과 관리 모달의 차단 이유 | 세션 바가 overlay 뒤에 가려져 회색 재실행·삭제 이유를 볼 수 없음 | 모달 안에 파란 원인 문장을 상시 표시하고 folder·close는 계속 활성 |
| 완료 뒤 전체 비교 | persistent worker가 idle이어도 `isRunning()`이 true라 전체 비교를 영구 거부 | thread 생존 대신 `busy` session ownership을 검사해 완료 뒤 즉시 허용 |
| 전체 비교 중 새 작업 | 탐색 70개 Start·결과 첫 실행/기록 재생/재실행이 활성이고 direct replay/rerun도 우회 가능 | 공통 `reject_running_batch`와 QML 선제 차단을 적용하고 direct 호출 2/2도 같은 원인·복구로 거부 |
| 전체 비교 차단 이유 | 탐색의 버튼만 회색이고 현재 작업·취소 경로가 보이지 않음 | 탐색·결과 상단에 현재 세트와 `비교 실행 취소`를 표시하는 공통 상태 바 추가 |
| 전체 비교 중 결과 정리 | 실행 충돌을 막기 위해 모든 관리 행동을 막으면 무관한 오래된 기록도 정리 불가 | 재실행만 차단하고 report·folder·close·무관한 삭제는 유지, 활성 비교 폴더만 backend에서 보호 |
| 활성 중 저장 결과 삭제 | UI를 우회하면 재생/실험 중 결과 폴더 삭제 가능 | QML 비활성화와 backend `has_active_experiment` 삭제 거부를 이중 적용 |
| 라이브 다시 시작 시각 | 위치는 초기화되지만 슬라이더 plant의 MuJoCo time은 유지 | 공용 reset이 time·위치·속도·입력을 함께 0으로 복원하고 예측 단계에서 일시정지 |
| 기록 재생의 예측 게이트 | 원본 hands-on scenario 규칙이 replay transport를 `예측 후 시작`으로 잠금 | live/replay 모드를 명시적으로 분리해 기록은 즉시 Play·frame·timeline 조작 가능 |
| Lab01/02 조작 판정 | 통합 Qt 조작을 generic `learner`로 저장해 리포트가 제어로 인정하지 않음 | button/slider 의미 종류로 저장해 Mission Evidence가 `Ready for review` 판정 |
| 실험 다시 시작 | replay는 지우지만 adapter의 이전 observation event는 남을 수 있음 | recorder와 interaction event를 함께 초기화해 새 과업 증거와 분리 |
| 키보드 베타 타이머 | 고부하에서 텍스트 입력 중 다음 절대 타이머가 재진입 | 각 행동 완료 뒤 다음 행동을 예약하는 순차 체인으로 결정성 확보 |
| 장시간 수명주기 감사 종료 | 3회 재시작의 마지막 교체 대기 중 캡처용 auto-quit가 먼저 발화 가능 | 해당 케이스에만 종료 여유를 두고 idle→replacement→0초 pause를 끝까지 검증 |
| 완료→속도 유지 감사 | 고정 0.8초 지연만 믿어 worker finalization 중 예측 저장이 먼저 실행 가능 | worker idle과 새 paused session을 명시적으로 기다린 뒤 예측을 저장, 2회 반복 통과 |
| compact 완료 안내 | 별도 완료 문장이 뷰포트를 135px까지 축소 | 헤더 버튼 설명으로 통합해 완료 상태도 158px 유지 |
| 200% 확대 실험 뷰포트 | 약 28 px | 158 px, 약 5.6배 |
| 좁은 화면 핵심 실험 버튼 | 화면 밖/스크롤 필요 | 당기기·밀기 첫 행 고정 |
| 정상 화면 현재값 | 3개 중 2개만 노출 | 위치·속도·힘 3개 노출 |
| 결과 카드 | ID와 버튼이 겹침 | 정보 위, 2×2 버튼 아래 |
| UI에서 물리 진행 | EGL 컨텍스트가 다른 스레드에서 실행 | 물리 스레드 명령 큐에서 직렬 실행 |
| 오류 대화상자 | 긴 기술 스택이 본문을 점유 | 짧은 안내, 세부정보는 펼치기/복사 |
| 대형 화면 목차 | 지나치게 넓은 1~2열 | 1920 px에서 3열 |
| Lab03 의미 오버레이 | 작은 목표·현재만 표시 | 작업공간 경계, 관절 1·2, 오차 점선, 특이점 halo |
| Lab04 가상 벽 | 반투명 단일 면, 작은 힘 화살표 | 격자 벽, 접촉 링, 최소 길이 힘 화살표 |
| 모든 장면 범례 | 힘·벽을 항상 표시 | 장면에 실제로 존재하는 의미만 표시 |
| Lab03/04 움직임 상태 | 속도 누락으로 거의 정지 표시 | 손끝 속도 기반 움직임/정지 표시 |
| 200% 확대 장면 범례 | 공간 확보를 위해 완전히 숨김 | 10px 축약 범례를 유지, 뷰포트 158px 보존 |
| 시나리오 실행 접근성 이름 | 70개 버튼이 모두 `Start` | `Start: LABxx · 제목`으로 70개 모두 고유 |
| 탐색 카드의 일반 제목 | 실행 버튼은 Lab 문맥이 있지만 화면에는 `Auto demo`·`Interactive`만 보여 카드 구분이 어려움 | 보이는 제목과 접근성 이름이 같은 `LABxx · 제목`을 사용하고 한·영 70/70 고유성 검증 |
| 실험·배경 세션 제목 | 탐색을 떠나면 `Interactive · Paused`로 Lab 문맥이 사라지고 saving 분기는 제목 자체가 없음 | 실험 헤더와 pause·replay·saving 상태가 같은 catalog `displayTitle`을 사용해 5개 화면 전이 5/5 |
| 슬라이더 접근성 정보 | 이름만 제공 | 범위·현재값·키보드 조작 설명 제공 |
| 비버튼 포커스 | 플랫폼 기본 표시에 의존 | 노란 4px + 검은 2px 공용 FocusRing 적용 |
| 마우스 전용 도움말 | hover일 때만 표시 | 키보드 포커스에서도 표시하고 보조기술 설명 제공 |
| 홈 준비 상태 | 실제 진단과 무관하게 항상 준비 완료 | 70개 config/model·결과 폴더를 검사해 성공/경고 분기 |
| 홈 다음 실험 설명 | 진행 상태와 무관하게 항상 질량-스프링 소개 | 실제 다음 시나리오 제목·목적·난이도·시간 표시 |
| 첫 실행 둘러보기 위치 | 640×360에서 설정 카드와 다음 카드 아래 약 100px 밖에 있어 첫 화면에서 0/4 요소 노출 | 정상 설정 카드를 CTA 뒤로 낮추고 3단계·건너뛰기 4/4와 CTA를 첫 viewport에 배치 |
| 큰 화면 둘러보기 단절 | 번호·문구 3개가 넓은 카드에 독립적으로 흩어져 순서 관계가 약함 | 1280·1920px에 3.18:1 연결선, compact·200%에는 선 0으로 연속성과 밀도를 함께 보존 |
| 둘러보기 건너뛰기 포커스 | 버튼이 사라진 뒤 포커스 복구 계약이 없어 키보드 위치를 잃음 | 건너뛰기→`다음 실험 시작`, 다시 보기→`건너뛰기` 왕복을 명시하고 5개 trace 검증 |
| 홈 상태 우선순위 | 정상 설정 설명이 첫 행동보다 먼저 큰 면적을 점유하고 활성 작업 중에도 둘러보기가 경쟁 | 정상 설정은 CTA 뒤, 오류는 CTA 앞; 활성 실험·비교 중에는 둘러보기를 숨겨 복구 행동만 우선 |
| 둘러보기와 첫 실험 불일치 | 안내는 값 변경을 요구하지만 첫 자동 데모는 제어 0개이고 열자마자 5초 물리를 소비 | 0.00초 pause, Push 포커스, Damping 1개만 공개; Push·Damping event와 301-frame replay를 종단 검증 |
| 1D 안전모드 장면 | GPU 복구 경로가 빈 십자선만 보여 질량·스프링·댐퍼 관계를 설명하지 못함 | 위치·힘에 반응하는 교육용 도식, 밝은 바닥·눈금·목표, 스프링·댐퍼·질량 블록·평형점 직접 라벨 추가 |
| 1D 실제 장면 직접성 | 실제 EGL에 물체는 있으나 640px에서 작고 이름이 없어 초보자가 요소를 추론해야 함 | 실제 장면 위에도 같은 네 라벨을 중복 표시하고 접근성 트리에 의미 이름 제공 |
| Lab03/04 안전모드 장면 | GPU 복구 시 빈 십자선과 범례만 남아 추종·관절·Panda·벽 관계가 사라짐 | 반응형 1D rail, 번호가 있는 2DOF, 단순화한 Panda, 격자 벽·밝은 바닥·현재/목표 도식 추가 |
| 탐색 70개 발견성 | 텍스트 검색만 있어 난이도·직접 조작 여부를 모르는 초보자는 원하는 실험을 좁히기 어려움 | 직접 라벨된 난이도·방식 필터, 실시간 shown/total, 0개 안내와 키보드 초기화 추가 |
| 필터 시각 구분 | 접근성 이름은 있어도 두 선택기가 모두 `전체`로 보여 용도를 눈으로 구분 불가 | `난이도 · 전체` / `방식 · 전체`, 영어 `Level · All` / `Mode · All` 직접 라벨 적용 |
| 다중 단어 검색 | 전체 문장을 하나의 부분 문자열로 찾아 `lab04 wall`이 관련 실험 14개 대신 0개 | 공백 token-AND로 변경해 순서와 무관하게 14개 반환, 실제 키보드·200% 확대 검증 |
| 필터 추가 후 cold start | shown 수 루프가 Python scenario payload를 매 항목 다시 직렬화해 p95 490→3,072ms로 악화 | scenario 목록을 QML에서 한 번 캐시해 O(n²) 제거, 최종 p95 523.8ms로 회복 |
| UI 감사 창 포커스 | 기존 앱·창 관리자 상태에 따라 감사 창의 `focusWindow`가 비어 키보드 19개 사례가 거짓 실패 | 감사 창을 크기 보정 때 명시적으로 raise/activate하고 격리 재실행 97/97 통과 |
| 오류 세부정보 접근성 | 일부 popup 타이밍에서 CheckBox 텍스트가 이름·포커스 상태로 승격되지 않음 | `Accessible.name`·설명을 명시하고 오류/충돌 11개 경로에서 unnamed 0 |
| 잘못된 YAML | catalog 생성 중 앱 자체가 종료될 수 있음 | 해당 카드만 준비 실패로 격리하고 앱은 계속 열림 |
| 손상된 replay.npz | 파일 존재만으로 재생 버튼 활성화 | NPZ index/schema 검사 후 기록 없음으로 선제 표시 |
| 결과 버튼 의미 | 비활성 이유가 hover에만 의존 | 기록·재실행 설정·튜닝 가용성을 텍스트로 상시 표시 |
| 비활성 버튼 대비 | 밝은 회색 위 흰색으로 판독이 약함 | `#64748B` 위 흰색, 4.5:1 이상 |
| 런타임 언어 변경 | 고정 scenario property가 이전 언어를 유지 | scenario/path/results 전체를 같은 변경 신호로 갱신 |
| 기록 재생 속도 | 모델 physics `dt`로 프레임을 재생해 최대 수배 빠름 | 실제 저장 타임스탬프 간격과 0.25×~2× 배율 사용 |
| 재생 scrub/frame 이동 | 이동 직후 계속 재생되어 선택 프레임을 놓침 | 모든 seek·프레임 이동은 일시정지 상태로 고정 |
| compact 재생 transport | 처음/끝·반복 구간이 숨거나 빈 기호로 보임 | 전 버튼 상시 노출, `↻ 반복`과 선택 track으로 의미 표시 |
| 완료된 재생의 주 버튼 | `일시정지`로 표시되지만 실제로는 다시 재생 | `재생`으로 표시하고 첫 프레임부터 시작 |
| 재생 이벤트 마커 | 동일한 일반 이름, hover만 가능 | 이름·시간이 고유한 diamond 버튼, 키보드/클릭으로 정확한 프레임 이동 |
| 재생 중 실험 제어 | live 버튼·slider가 남아 누르면 오류 | 기록 설명·telemetry만 남기고 live 제어 전체 숨김 |
| 재생 학습 단계 | 계속 3/5 `실험`으로 표시 | 5/5 `복습`과 기록 검토 안내로 전환 |
| Lab04 기록 의미 상태 | 목표 Y/Z·벽 위치·벽 힘 누락 | semantic state에 저장하고 격자 벽·접촉 링·최소 길이 힘 화살표 복원 |
| 빈 결과 화면 | 설명 한 줄 뒤 넓은 빈 공간, 시작 행동 없음 | 중앙 empty-state 카드와 `첫 실험 시작` 단일 CTA |
| 결과 카드 제목 | scenario ID와 폴더명이 가장 먼저 보임 | 번역된 `LAB · 제목 · 최신/이전 N`, 기술 ID는 관리 모달로 이동 |
| 결과 해석 순서 | 용량·가용성·재실행 버튼만 노출 | 한 문장 결과 → 의미 기반 수치 3개 → 다음 행동 → 리포트 순서 |
| 결과 행동 위계 | 안내는 재생/재실행을 권하지만 항상 `리포트 보기`가 primary이고 죽은 재생도 자리를 차지 | 정상 기록은 `기록 재생`, 기록 없음은 `같은 설정 재실행`, 비교는 `리포트 보기`를 primary로 자동 판정 |
| 완료/손상 상태 | 초록 `완료`와 `기록 없음` 메시지가 충돌하고 재실행은 관리 모달에 숨음 | amber `기록 없음` 칩·다음 문장·직접 재실행 버튼을 일치시키고 없는 리포트/재생은 숨김 |
| 결과 정리 (역사적, SAFE-01로 대체) | repository 삭제 경계만 있고 UI 연결 없음 | 당시 용량·영구 경고·정확한 폴더 확인을 거친 2단계 삭제와 목록 즉시 갱신 |
| 많은 결과 | 최신 40개에서 조용히 잘려 오래된 결과 접근 불가 | 전체 목록을 보존하고 20개 단위 점진 공개, 실행별 접근성 이름 고유화 |
| 경로 행동 수 | 미래 단계마다 같은 `시작` 버튼 11개 | 권장 다음 단계의 주요 버튼 1개, 나머지는 상태 기반 목차 |
| 경로 완료 판정 | 중단·오류 저장 폴더도 완료로 계산 | manifest 상태가 `completed`인 성공 실행만 계산 |
| 경로 끝 상태 | 11개 실험 뒤 CLI의 12번째 전체 비교가 앱에 없음 | 11/12 전체 비교 실행·진행·취소 뒤 12/12 `결과 검토`로 종료 |
| 경로 진행 막대 | Qt 기본 검정 채움이 의미색과 충돌 | 진행은 파랑, 완료는 초록, 회색 track과 3:1 이상 대비 |
| 경로 설정 실패 | 긴 누락 경로만 보여 복구 방법이 화면 밖 | 원인 아래 `mclab assets install` 복구 행동을 별도 고정 표시 |
| 긴 전체 비교 | GUI 동기 실행 시 약 49초 동안 멈출 위험 | 별도 프로세스, 정확한 1/5~5/5 진행, 취소 후 강제 종료 fallback |
| 전체 비교 중복 | 여러 실행과 산출물 충돌 가능 | 시작 거부, 원인·대기/취소 복구·세부정보 복사 제공 |
| 앱 종료 뒤 running manifest | 다시 열면 영원히 실행 중으로 보일 수 있음 | 활성 프로세스가 없으면 `중단됨`과 재시도 행동으로 표시 |
| 실행 폴더 정리 | 진행 중 결과를 삭제해 자식 프로세스가 실패할 수 있음 | 관리 행동 비활성화와 backend 삭제 경계 이중 적용 |
| 긴 세트의 진행 문구 | `3/5`만 보여 어떤 계산인지 알 수 없음 | `3/5 · 2DOF·DLS`처럼 현재 주제를 직접 표시 |
| 취소 반복 입력 | 중단 요청 뒤 취소 버튼이 계속 활성 | amber `중단 중…`으로 바꾸고 버튼을 비활성화 |
| 실행 중 언어 전환 | 본문은 영어지만 상단 내비게이션은 한국어로 남음 | 132개 QML 번역 binding이 언어 변경을 명시적으로 구독 |
| 언어 전환 감사 범위 | 카드 번역만 확인해 혼합 내비게이션을 놓침 | 양방향 전환에서 nav 이름과 진행 주제까지 검사하고 이전 언어 금지 |
| batch report 표 | 모바일 가로 표 5곳이 키보드로 스크롤 불가 | focus 가능한 표 영역과 노란 3px·검은 2px 표시 추가 |
| run report 산출물 링크 | 높이 17px 링크 4개가 WCAG 2.2 target-size 위반 | 최소 높이 24px로 확대, axe serious 4→0 |
| run report 첫 제목 | `lab04_panda - wall_stiff report` 기술 식별자 노출 | `Lab04 Panda manipulator · Stiff wall report` 사람용 제목 |
| run report 핵심 수치 | `max abs qdot` 같은 raw 이름과 단위 누락 | `Peak joint speed [rad/s]`처럼 의미 이름·단위 표시 |
| outputs index 첫 화면 | 오래된 메뉴 명령 13개가 결과보다 먼저 노출 | 저장 증거를 먼저 표시하고 명령은 접힌 고급 영역으로 이동 |
| outputs index 시작 명령 | Windows 전용 `run_mclab.cmd`를 모든 OS에 표시 | 공통 `python -m mclab app`으로 통일 |
| UI 감사 반복 속도 | 한 결함 확인에도 전체 화면 집합을 재실행 | `--case` glob으로 EGL·경로 같은 위험 집합만 선택 실행 |
| 알 수 없는 런타임 오류 | `KeyError`·내부 action 이름이 초보자 본문에 노출 | 짧은 일반 원인만 본문에 표시하고 raw 정보는 펼치기/복사에만 보존 |
| 실험 완료 후 행동 | 홈 이동과 같은 의미의 재시작 버튼 2개가 강조 | `저장 결과 보기 →`를 다음 행동으로 승격하고 재시작은 1개만 유지 |
| 200% 감사 창 크기 | 전체 순서 부하에서 QML 기본 크기가 늦게 적용되어 간헐적 최대화 | 로드 전 논리 크기 주입 + 실제 크기가 다를 때만 조건부 보정 |
| 확대 캡처 검은 블록 의심 | 이미지 표시기 보간만 보고 렌더 오염으로 오판할 위험 | 원본 RGBA 픽셀·GPU 캡처를 비교해 오탐으로 판정, 불필요한 UI 수정 제외 |
| 라이브 진행 막대 | seek 불가능한데 `Slider`와 “위치 변경” 설명 노출 | 읽기 전용 `실험 진행률`, 저장 기록에서만 `기록 재생 타임라인` 노출 |
| compact 패널 키보드 역순 | 화면 아래 `고급 설정`에 포커스만 가고 링은 0 px | 버튼·slider·check 포커스마다 ScrollView 자동 이동, 링 778 px |
| 탐색·결과 카드 키보드 이동 | 첫 카드 뒤 Tab 포커스가 y=591~923/660~872로 창 밖에 남고 결과 제목도 헤더 뒤로 가림 | 공용 카드 단위 reveal로 Tab·Shift+Tab 22/22 창 안, 제목-버튼 문맥 동시 노출 |
| `20개 더 보기` 포커스 | 확장 때 같은 버튼이 y=4,542→8,782로 이동하고 마지막에는 0×0으로 사라짐 | 20→40은 `이전 21`, 40→60은 `이전 41` 카드 전체로 인계, y=449·링 1,112 px |
| 포커스 trace 좌표 | 양수 rect만 검사해 창 밖 `y=727`도 통과 가능 | 활성 창 경계 안 완전 포함을 검사하고 동일 출력 재실행 전 trace 초기화 |
| 속도 선택 후 새 세션 | UI는 `0.5×`, 새 live 세션은 `1×`로 불일치 | backend 단일 상태를 새 live/replay에 적용, 9/9 전환 표본 일치 |
| 속도 키보드 안내 | ComboBox 값 목록만 설명하고 변경 키는 누락 | Tab→Up으로 `1×→0.5×` 검증, 현재값과 Up/Down 사용법을 함께 발화 |
| compact 상단 조작 대상 | 홈 28×40, 언어 132×42로 44px 기준 미달 | 홈 44×44, 언어 132×44; 다른 nav도 높이 44 |
| 리플레이 세부 조작 대상 | 타임라인 14px, 반복 구간 12px, 이벤트 마커 24×20 | 각각 24px, 24px, 24×24로 확대; 뷰포트 158px 유지 |
| dense 리플레이 이벤트 | legacy 카메라 orbit 119개가 2ms 간격으로 같은 위치에 겹침 | view-only 이벤트 119→0 마커, 연속 slider 10개→`×10` gesture 마커 1개 |
| 완료 뒤 새 EGL 세션 | context만 재사용해도 반복 재시작의 첫 `mjr_render`에서 `SIGSEGV(-11)` | 같은 scenario는 model·data·renderer·camera를 물리 스레드에서 그대로 인계하고 reset, 다른 scenario는 worker를 종료·교체해 총 15/15 재시작과 교차 교체 통과 |
| 완료된 기록 다시 재생 | 새 model/context를 만들어 native 충돌과 메모리 중복 가능 | 같은 replay session·renderer에서 저장 프레임만 처음으로 되감아 재생 |
| 앱 두 개의 EGL 충돌 | 실행 중인 앱과 두 번째 앱이 각각 renderer를 만들면 완료→재시작에서 `SIGSEGV(-11)` 재현 | per-user lock+local IPC로 두 번째 GUI를 만들지 않고 184.9 ms 내 기존 창 활성화; 잠금 해제 뒤 EGL 4/4 |
| 긴 절대 경로 리포트 | command·table이 모바일과 데스크톱에서 477~478px 넘침 | grid item 최소폭 0, command/table 임의 줄바꿈으로 두 viewport 모두 0px |
| 실행 중 새 실행 요청 | 저장 replay나 다른 scenario가 활성 session을 교체할 수 있음 | live worker가 끝날 때까지 거부하고 원인·복구 행동 표시, session ID 불변 검증 |
| compact `지금 해볼 것` | 일반 목적 문장이 한 줄 말줄임되어 첫 행동을 알 수 없음 | 70개 scenario의 실제 버튼·핵심 제어로 문장 생성; 한국어 최대 43자·영어 최대 84자, 최악 사례도 2줄·비잘림 |
| replay 상단 안내 | 긴 물리 재계산 설명이 말줄임되고 우측 설명과 중복 | `타임라인을 움직여 현재/목표가 달라지는 순간 찾기` 한 과업으로 축약, 보조기술 이름도 동일 |

## 심미·관능 대리 평가

아래 점수는 캡처를 대상으로 한 휴리스틱 평가이며 사람의 관능 평가나 SUS 점수가 아니다.

| 기준 | 5점 척도 | 근거 |
|---|---:|---|
| 첫 인상·온보딩 | 4.9 | compact는 번호 3개 → 파란 다음 행동 → 초록 설정 상태, 큰 화면은 대비 3.18:1 선으로 세 단계를 한 흐름으로 읽으며 한·영·200% 잘림 0 |
| 시각적 위계 | 4.9 | 예측→권장 조작→관찰 저장→재생/결과로 파란 채움 하나를 넘기고, Home·동료 action·frame 이동·반복 상태는 4.76:1 outline/체크로 분리 |
| 학습 흐름 인지 | 4.9 | 2/5 예측부터 5/5 복습까지 상단 단계·장면 과업·우측 카드가 같은 상태를 표시 |
| 내비게이션 연속성 | 4.9 | 탐색→실험→pause/replay/saving에서 `LABxx · 제목`을 유지하고, 카드 양방향 이동·20→40→60 확장·다른 scenario worker 교체도 현재 문맥을 보존 |
| 행동 상태 명료성 | 4.9 | 예측·조작·저장 준비·미완성 재시작·완료 결과·replay마다 기대 이름까지 primary 1개를 검증하고, 라이브 값은 한 step마다 자릿수·단위를 갱신 |
| 가독성 | 4.9 | 굵은 Noto Sans KR, 실제 조작명을 쓴 1~2줄 과업, 긴 버튼 무말줄임, 결과·기록 위치 라벨 12px bold와 핵심 수치 14px bold mono의 분명한 층위 |
| 정보 밀도 | 4.9 | 관찰 입력·결과·저장과 최대 5개 핵심 제어를 1280px 한 panel에 유지하고, compact는 한 열 포커스 reveal; 탐색 70개는 검색·두 필터로 축약 |
| 의미 일관성 | 4.9 | 탐색·실험·배경 세션의 Lab 문맥과 현재/목표/힘/제약의 색·모양·선 표현을 각각 단일 의미 소스로 일치시킴 |
| 움직임 인지 | 4.7 | 1D 방향과 2D/3D 손끝 속도를 구분하고 상태 칩과 장면을 함께 갱신 |
| 직접 조작 발견성 | 4.9 | 손 모양 cursor·패널 제한 도움말·포커스 중 하단 키 안내를 조합해 장면을 가리는 상시 설명 없이 mouse/keyboard 카메라 조작을 찾을 수 있음 |
| 폼·surface 일관성 | 4.9 | 입력·선택·보조 버튼·오류 모달은 2px 고대비 윤곽을 공유하고, 체크박스는 28px indicator·파란 면+흰 체크·44px 라벨 타깃으로 같은 명료성을 유지 |
| 친근한 인상 | 4.8 | 번호가 있는 짧은 질문, 예측 예시, 파랑→amber→초록 피드백, 저장 결과 handoff를 사용 |
| 리포트 첫 화면 | 4.8 | 사람용 제목 → 한 문장 결과 → priority plot → 단위가 있는 핵심값 3개 순서 |

## 남은 사람·플랫폼 검증

- plot 포함 전체 비교는 Linux 개발 환경에서 검증했다. Windows/macOS 패키지에서도 같은
  시간·메모리·용량과 중간 취소 후 자식 프로세스 정리를 측정해야 한다.
- 초보 학습자 6명 이상의 think-aloud 과업과 SUS 설문은 실제 참여자가 필요하다.
- Windows 11, Ubuntu 24.04, macOS의 실제 GPU, 200% OS 확대, 스크린리더를 확인해야 한다.
- 홈·실험·오류·결과 관리의 실제 포커스 이름·역할·좌표와 모달 복귀는 자동 통과했지만,
  플랫폼별 포커스 표시의 밝기·두께·인지성에 대한 사람 관능 평가는 남아 있다.
- 색각 이상 행렬과 중복 기호는 자동 통과했지만 실제 저시력·색각 이상 사용자의 판독 평가는 남아 있다.
- Qt 접근성 트리의 이름·설명·포커스는 자동 통과했지만 NVDA, VoiceOver, Orca의 실제 발화 순서는 플랫폼별 확인이 남아 있다.
- Linux 실제 EGL은 최종 묶음 12/12, 같은 scenario 재시작 15/15, 교차 scenario 교체를
  통과했다. Windows/macOS와 다른 GPU·드라이버의 반복 재시작은 각 플랫폼 릴리스
  gate에서 별도로 확인해야 하며, 감사 도구가 보존하는 native stdout·stderr를 함께 검토한다.
