# Local data and privacy / 로컬 데이터와 개인정보

This paired English/Korean policy describes the repository behavior controlled by
[`mclab.local-data.v1`](../.agents/operations/local-data-policy.json). It is a
repository-only development contract, not a public-release privacy notice or an
institutional retention policy.

이 영문/국문 병기 정책은
[`mclab.local-data.v1`](../.agents/operations/local-data-policy.json)이 통제하는 저장소
동작을 설명합니다. 저장소 범위의 개발 계약이며, 공개 배포용 개인정보 처리방침이나
기관 보존 정책이 아닙니다.

## Scope / 범위

### English

MCLab is local-first. An ordinary simulation run needs no account, cloud service, or
network connection, and MCLab has no automatic learner-data upload or remote usage
analytics. This statement covers the current supervised, source-development scope. It
does not authorize public beta, signed distribution, release publication, or an external
service commitment.

### 한국어

MCLab은 로컬 우선으로 동작합니다. 일반 시뮬레이션 실행에는 계정, 클라우드 서비스,
네트워크 연결이 필요하지 않으며, 학습자 데이터를 자동 업로드하거나 원격 사용량 분석을
수행하지 않습니다. 이 설명은 현재의 감독된 소스 개발 범위에만 적용됩니다. 공개 베타,
서명 배포, release 발행 또는 외부 서비스 약속을 승인하지 않습니다.

## Storage locations / 저장 위치

### English

By default, saved runs live under one configured `outputs/` root:

| Execution mode | Default location |
|---|---|
| Source checkout | `<repository>/outputs` |
| Explicit override | `<MCLAB_DATA_DIR>/outputs` |
| Frozen Windows app | `%LOCALAPPDATA%/MCLab/outputs` |
| Frozen macOS app | `$HOME/Library/Application Support/MCLab/outputs` |
| Frozen Linux app | `${XDG_DATA_HOME:-$HOME/.local/share}/mclab/outputs` |

`MCLAB_DATA_DIR` is a parent directory; MCLab appends its own `outputs/` child.
The Windows implementation falls back to the current user's local AppData path when
`LOCALAPPDATA` is unavailable or empty. Linux similarly falls back to
`$HOME/.local/share` when `XDG_DATA_HOME` is unavailable or empty. An empty platform
variable is never interpreted as the process current working directory.

The CLI `run` and `batch` commands are an explicit exception: `--output-dir` selects the
exact run or batch directory. An absolute value can be anywhere the current user can
write. A relative value resolves from the repository root in source mode or from the
application-data parent in a frozen bundle. After terminal publication, MCLab attempts a
best-effort parent-index refresh at the sibling `index.html` in the selected directory's
parent. Failure to refresh that derived index does not undo the terminal run or batch.
The selected tree can sit outside the configured `outputs/` root and may not appear in
its default review, index, or cleanup view. Track and sanitize both the selected tree and
any successfully refreshed `<parent-of-explicit---output-dir>/index.html`.

The desktop's non-empty `MCLAB_OUTPUT_DIR` is another exact external destination. It is
consumed once, by the first live scenario started in that desktop process. An absolute
value selects `<MCLAB_OUTPUT_DIR-selected-first-run-directory>` exactly; a relative value
uses the same source/frozen resolution rule as CLI run output. After that run becomes
terminal, MCLab makes the same best-effort attempt to refresh
`<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html`. Later runs return
to the configured outputs root. Neither the external tree nor its derived parent index is
managed by cleanup of the configured root.

The standalone `python -m mclab index --output-dir ARBITRARY_ROOT` command has a
different boundary. It writes directly to
`<standalone-index---output-dir>/index.html`; it does not append a run directory and
does not place the index in the argument's parent. An absolute argument names that root
directly. A relative argument resolves from the process current working directory in both
source and frozen execution, rather than from `PROJECT_ROOT` or the frozen
application-data parent. The selected root must still pass the shared publication safety
boundary: filesystem/drive/share roots, the home/repository/temporary roots or their
ancestors, mount points, link or reparse components, and unsafe run-shaped roots are
rejected. It is therefore not a promise to write in every writable directory.

The desktop also creates local coordination artifacts:

| Surface | Location and lifecycle |
|---|---|
| Default instance lock | `<Qt-AppLocalDataLocation>/mclab-desktop.lock`; unlocked on a normal app exit, but a stale file can remain after abnormal termination |
| Lock override | The exact `MCLAB_INSTANCE_LOCK` path; a relative override uses the process current working directory |
| Unix-like local activation socket | `<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>` when Qt uses a filesystem socket; the previous entry is removed before listening, while an abnormal exit can leave an entry for the next startup to remove |
| Windows local activation endpoint | `\\.\pipe\mclab-<lock-path-sha256-prefix>` in the local named-pipe namespace while the activation server is listening; this is not a filesystem file |
| Desktop preferences | `<Qt-QSettings-UserScope:MCLab/MCLab>` in Qt's OS-native per-user settings backend, with persistent `language` and `tourComplete` keys |

The named pipe and Unix socket exchange only the local `activate` request and `activated`
acknowledgement.

### 한국어

기본적으로 저장된 실행은 설정된 하나의 `outputs/` root 아래에 있습니다.

| 실행 형태 | 기본 위치 |
|---|---|
| 소스 checkout | `<repository>/outputs` |
| 명시적 override | `<MCLAB_DATA_DIR>/outputs` |
| Windows 설치형 앱 | `%LOCALAPPDATA%/MCLab/outputs` |
| macOS 설치형 앱 | `$HOME/Library/Application Support/MCLab/outputs` |
| Linux 설치형 앱 | `${XDG_DATA_HOME:-$HOME/.local/share}/mclab/outputs` |

`MCLAB_DATA_DIR`는 상위 폴더이며 MCLab이 그 아래에 전용 `outputs/`를 덧붙입니다.
Windows에서는 `LOCALAPPDATA`가 없거나 빈 값이면 현재 사용자의 local AppData 경로를
사용하고, Linux에서는 `XDG_DATA_HOME`이 없거나 빈 값이면 `$HOME/.local/share`를
사용합니다. 빈 platform 변수는 process 현재 작업 폴더로 해석하지 않습니다.

CLI의 `run`과 `batch` 명령은 명시적 예외입니다. `--output-dir`는 정확한 run 또는 batch
폴더를 선택합니다. 절대 경로는 현재 사용자가 쓸 수 있는 어느 위치든 지정할 수 있습니다.
상대 경로는 source mode에서 저장소 root, frozen bundle에서는 application-data 상위
폴더를 기준으로 해석됩니다. 종료 상태를 발행한 뒤 MCLab은 선택 폴더 상위의 형제
`index.html` 갱신을 best effort로 시도합니다. 이 파생 index 갱신 실패는 이미 종료된 run
또는 batch를 되돌리지 않습니다. 선택한 tree는 설정된 `outputs/` root 밖에 있을 수 있고
기본 review·index·cleanup 화면에 나타나지 않을 수 있습니다. 따라서 선택한 tree와 실제로
갱신된 `<parent-of-explicit---output-dir>/index.html`을 모두 추적하고 익명화해야 합니다.

Desktop의 비어 있지 않은 `MCLAB_OUTPUT_DIR`도 정확한 외부 대상입니다. 한 desktop
process에서 시작한 첫 live scenario가 한 번만 사용합니다. 절대 경로는
`<MCLAB_OUTPUT_DIR-selected-first-run-directory>`를 그대로 선택하고, 상대 경로는 CLI run과
동일한 source/frozen 규칙으로 해석됩니다. run 종료 뒤에는
`<parent-of-MCLAB_OUTPUT_DIR-selected-first-run-directory>/index.html` 갱신도 best effort로
시도합니다. 이후 run은 설정된 outputs root로 돌아갑니다. 외부 tree와 파생 parent index는
설정 root cleanup의 관리 대상이 아닙니다.

독립 실행형 `python -m mclab index --output-dir ARBITRARY_ROOT` 명령의 경계는
다릅니다. 이 명령은 `<standalone-index---output-dir>/index.html`에 직접 쓰며 run 폴더를
덧붙이거나 인자의 상위 폴더에 index를 두지 않습니다. 절대 경로 인자는 그 root를 직접
가리킵니다. 상대 경로 인자는 source와 frozen 실행 모두에서 `PROJECT_ROOT`나 frozen
application-data 상위 폴더가 아니라 process의 현재 작업 폴더를 기준으로 해석됩니다.
다만 선택 root는 공통 publication 안전 경계를 통과해야 합니다. filesystem/drive/share root,
home·repository·temporary root 또는 그 상위, mount point, link/reparse component와 안전하지
않은 run 형태 root는 거부되므로 모든 쓰기 가능한 폴더를 지원한다는 뜻이 아닙니다.

Desktop은 다음 로컬 조정 artifact도 만듭니다.

| 표면 | 위치와 lifecycle |
|---|---|
| 기본 instance lock | `<Qt-AppLocalDataLocation>/mclab-desktop.lock`; 정상 종료 시 unlock되지만 비정상 종료 뒤 stale file이 남을 수 있음 |
| Lock override | 정확한 `MCLAB_INSTANCE_LOCK` 경로; 상대 override는 process 현재 작업 폴더 기준 |
| Unix 계열 local activation socket | Qt가 filesystem socket을 사용할 때 `<Qt-local-server-runtime-directory>/mclab-<lock-path-sha256-prefix>`; listen 전에 이전 entry를 제거하지만 비정상 종료 시 다음 시작에서 제거할 entry가 남을 수 있음 |
| Windows local activation endpoint | activation server가 listen하는 동안 local named-pipe namespace의 `\\.\pipe\mclab-<lock-path-sha256-prefix>`; filesystem file은 아님 |
| Desktop preference | Qt의 OS-native 사용자별 backend에 있는 `<Qt-QSettings-UserScope:MCLab/MCLab>`; 영속 `language`, `tourComplete` key 포함 |

named pipe와 Unix socket은 로컬 `activate` 요청과 `activated` 응답만 교환합니다.

## Data inventory / 저장 데이터 목록

### English

A run can contain the resolved `config.yaml`; `log.csv`; `states.npz` or its
`states.json` fallback; `summary.json`; generated lesson `notes.md`; `replay.npz`;
`manifest.json`; plots; `report.html`; `worksheet.md`; `interaction_events.json`;
`learner_snapshot.json`; and `learner_tuned_config.yaml`. `notes.md` is generated lesson
content. A learner's prediction and observation note are learner-authored evidence and
must be treated as potentially private. The same files can instead live at the exact
`<MCLAB_OUTPUT_DIR-selected-first-run-directory>` for the desktop's first live run.

A comparison batch also contains `batch_summary.json`, `summary.json`, `manifest.json`,
`report.html`, `worksheet.md`, a nested `index.html`, `comparison_plots/`, and complete
child run or child batch directories. Batch summaries can contain child output paths, so
the complete batch tree and its parent index must be sanitized together. That parent is
`outputs/index.html` for a default run and `<parent-of-explicit---output-dir>/index.html` for an
explicit destination.

Learner evidence is deliberately duplicated for replay and review. Prediction, outcome,
note, control events, and live-status evidence can appear in `interaction_events.json`,
the `events_json` entry inside `replay.npz`, `report.html`, `worksheet.md`, and the
cumulative configured-root, explicit-run/batch-parent, or standalone-command-root
`index.html`. Deleting or moving only `interaction_events.json` does not remove those
derived copies.

`manifest.json` can include runtime and operating-system details, config/model paths,
hashes, and bounded error text. Cleanup receipts can include an absolute output-root path
and run names. Treat both as diagnostic data that must be sanitized before sharing.
The optional `.mclab_progress.json` preference surface is defined but has no current
production writer.

Qt's `QLockFile` can record PID, hostname, application name, machine ID, and boot ID.
Treat the default or overridden lock as potentially private diagnostic data. The local
activation socket name is derived from a SHA-256 prefix of the lock path; its filesystem
entry or Windows named-pipe endpoint can still correlate a machine or installation and
should be treated as potentially private during shared-PC review. The activation payload
itself is limited to the local `activate` request and `activated` acknowledgement; it does
not carry learner notes or run artifacts.

The desktop also persists two non-free-text preferences in
`<Qt-QSettings-UserScope:MCLab/MCLab>`: `language` (`ko` or `en`) and `tourComplete`
(whether the introductory tour was dismissed). They are outside the outputs root, survive
normal app exit, and are not removed by MCLab cleanup.

The machine contract has four precise validation-only exclusions rather than silently
mixing them into ordinary learner storage: maintainer `scripts/audit_*.py` output roots,
the explicit `MCLAB_ACTIVATION_PATH` probe, the explicit `MCLAB_SCREENSHOT_PATH` capture,
and `MCLAB_SELF_TEST=1` accessibility/backend/focus/startup trace destinations. They are
not created by an ordinary learner run, but can contain screenshots, paths, or synthetic
and captured evidence, so a maintainer must still sanitize them before sharing.

### 한국어

한 실행에는 확정 `config.yaml`, `log.csv`, `states.npz` 또는 fallback
`states.json`, `summary.json`, 자동 생성 수업 자료 `notes.md`, `replay.npz`,
`manifest.json`, plot, `report.html`, `worksheet.md`, `interaction_events.json`,
`learner_snapshot.json`, `learner_tuned_config.yaml`이 포함될 수 있습니다.
`notes.md`는 자동 생성 수업 내용입니다. 학습자의 예측과 관찰 메모는 학습자가 작성한
증거이므로 개인정보가 될 수 있는 자료로 취급해야 합니다. Desktop의 첫 live run에서
`MCLAB_OUTPUT_DIR`를 사용하면 같은 파일이 정확한
`<MCLAB_OUTPUT_DIR-selected-first-run-directory>`에 저장될 수 있습니다.

비교 batch에는 `batch_summary.json`, `summary.json`, `manifest.json`, `report.html`,
`worksheet.md`, 내부 `index.html`, `comparison_plots/`와 완전한 하위 run 또는 batch
폴더도 포함됩니다. Batch summary에는 하위 output 경로가 들어갈 수 있으므로 전체 batch
tree와 상위 index를 함께 검토하고 익명화해야 합니다. 기본 실행에서는
`outputs/index.html`, 명시적 대상에서는 `<parent-of-explicit---output-dir>/index.html`입니다.

학습자 증거는 재생과 복습을 위해 의도적으로 여러 곳에 파생 저장됩니다. 예측, 결과,
메모, 조작 event와 live status는 `interaction_events.json`, `replay.npz` 안의
`events_json`, `report.html`, `worksheet.md`, 누적 `outputs/index.html`에 나타날 수
있습니다. 명시적 run/batch 대상에서는 누적 사본이 선택 폴더 상위의 `index.html`에
생기고, 독립 실행형 index 명령에서는 선택한 root의 `index.html`에 직접 생깁니다.
`interaction_events.json` 하나만 삭제하거나 이동해도 이 파생 복사본은 제거되지 않습니다.

`manifest.json`에는 runtime·운영체제 정보, config/model 경로, hash와 제한된 오류
문구가 포함될 수 있습니다. cleanup receipt에는 절대 output-root 경로와 실행 폴더명이
들어갈 수 있습니다. 둘 다 공유 전에 익명화해야 하는 진단 자료로 취급하세요. 선택적
`.mclab_progress.json` 설정 저장 표면은 정의되어 있지만 현재 production writer에는
연결되어 있지 않습니다.

Qt의 `QLockFile`에는 PID, hostname, application name, machine ID와 boot ID가 기록될 수
있습니다. 기본 또는 override lock을 개인정보가 될 수 있는 진단 자료로 취급하세요.
local activation socket 이름은 lock 경로의 SHA-256 prefix에서 파생되지만 filesystem
entry 또는 Windows named-pipe endpoint는 기기나 설치를 연계할 수 있으므로 공용 PC
검토에서 개인정보 가능 자료로 취급해야 합니다. Activation payload는 로컬 `activate`
요청과 `activated` 응답으로 제한되며 학습자 메모나 run artifact를 전달하지 않습니다.

Desktop은 `<Qt-QSettings-UserScope:MCLab/MCLab>`에도 두 가지 자유 서술이 아닌
preference를 영속 저장합니다. `language`는 `ko` 또는 `en`이고, `tourComplete`는 시작
안내를 닫았는지를 나타냅니다. outputs root 밖에 있고 정상 앱 종료 뒤에도 남으며 MCLab
cleanup으로 제거되지 않습니다.

machine contract의 검증 전용 제외 항목은 일반 learner 저장소에 조용히 섞지 않고 네
종류를 정확히 분리합니다. 관리자 `scripts/audit_*.py` output root,
`MCLAB_ACTIVATION_PATH` probe, `MCLAB_SCREENSHOT_PATH` capture,
`MCLAB_SELF_TEST=1` accessibility/backend/focus/startup trace 대상입니다. 일반 learner
run이 만들지는 않지만 screenshot, 경로, 합성 또는 캡처 evidence가 들어갈 수 있으므로
관리자는 공유 전에 익명화해야 합니다.

## Network behavior / 네트워크 동작

### English

The first setup can use the network to install a selected hash-locked Python profile.
`mclab assets install` downloads the pinned, hash-verified Panda asset. A maintainer-only
Ubuntu CI step installs a controlled system-package set. These are explicit acquisition
actions; they do not upload learner runs. Opening or attaching material to a GitHub issue
is also an explicit user action.

The single-instance channel uses a local Qt socket or Windows named pipe. Its server name
is derived from the lock path and it exchanges only activation messages; it is not an
Internet or learner-data upload channel. A Unix-like filesystem socket entry is normally
removed before a new listener starts and closed with the application, but it may remain
after a crash until a later startup removes it. Variables named `telemetry` in the
application carry in-process simulation and live-status values; they are not remote
analytics.

### 한국어

첫 설치에서는 선택한 hash 잠금 Python profile을 설치하기 위해 네트워크를 사용할 수
있습니다. `mclab assets install`은 commit과 hash가 고정된 Panda asset을 내려받습니다.
관리자용 Ubuntu CI 단계는 통제된 system package 묶음을 설치합니다. 모두 사용자가
명시적으로 시작하는 획득 동작이며 학습자 실행 결과를 업로드하지 않습니다. GitHub
issue를 열거나 자료를 첨부하는 것도 사용자가 명시적으로 수행하는 동작입니다.

single-instance 통신은 로컬 Qt socket 또는 Windows named pipe를 사용합니다. Server
이름은 lock 경로에서 파생되고 activation message만 교환하므로 Internet 또는 학습자
데이터 upload channel이 아닙니다. Unix 계열 filesystem socket entry는 새 listener가
시작되기 전에 보통 제거되고 앱과 함께 닫히지만 crash 뒤에는 다음 시작에서 제거될 때까지
남을 수 있습니다. 앱에서 `telemetry`라는 변수는 process 안의 시뮬레이션 및 live-status
값을 뜻하며 원격 분석을 뜻하지 않습니다.

## Export and copying / 내보내기와 복사

### English

MCLab has no account sync or dedicated cloud export. To make a local copy, first close the
run or wait for its terminal status, then copy the complete run directory. For a comparison
batch, copy the complete batch directory so its report, worksheet, child links, and plots
stay together. Preserve `manifest.json` when provenance matters. Review and sanitize the
copy before giving it to another person or service. An explicit-output copy does not
include the sibling parent `index.html`; review that derived file separately before
sharing or handing off the parent directory.

### 한국어

MCLab은 계정 동기화나 전용 cloud export 기능을 제공하지 않습니다. 로컬 복사본이
필요하면 실행을 닫거나 종료 상태가 될 때까지 기다린 뒤 실행 폴더 전체를 복사하세요.
비교 batch는 report, worksheet, 하위 링크와 plot이 함께 유지되도록 batch 폴더 전체를
복사하세요. provenance가 필요하면 `manifest.json`을 보존하세요. 다른 사람이나
서비스에 전달하기 전에는 복사본을 검토하고 익명화해야 합니다. 명시적 output을 복사해도
상위 폴더의 형제 `index.html`은 포함되지 않으므로, 상위 폴더를 공유하거나 넘기기 전에
그 파생 파일도 별도로 검토하세요.

## Cleanup, deletion, and restore / 정리·삭제·복원

### English

MCLab never removes saved runs automatically. CLI cleanup is a read-only plan by default;
an authorized apply requires the exact unchanged plan and separate confirmation. Apply
moves eligible terminal runs under `outputs/.mclab-trash/` with a receipt. It is
recoverable quarantine, not deletion or secure erasure, and it continues to use disk
space. `.mclab-preserve` prevents a run from becoming a cleanup candidate.

MCLab exposes no permanent purge. Quarantined runs, receipts, and a previously generated
`outputs/index.html` may continue to contain learner or path information. Source/venv CLI
restore is supported only on a local filesystem; NFS and SMB are outside the supported
cleanup/restore boundary. This policy does not authorize a real-output dry-run or apply.
Cleanup of the configured root does not manage an explicit output tree outside that root
or its sibling parent `index.html`. After an administrator-approved removal, regenerate
that parent index with `python -m mclab index --output-dir <parent>` or sanitize/remove it
through the same approved local process. This also applies to an external
`MCLAB_OUTPUT_DIR` tree and any successfully refreshed parent index. A standalone index
written directly under a caller-selected, safety-validated root is a derived file, not a
cleanup run candidate, and can likewise persist until it is regenerated, sanitized, or
removed through an approved local process. Cleanup also does not reset QSettings
`language` or `tourComplete`.

### 한국어

MCLab은 저장 결과를 자동으로 제거하지 않습니다. CLI cleanup은 기본적으로 읽기 전용
계획이며, apply에는 변경되지 않은 정확한 plan과 별도 확인이 필요합니다. Apply는 종료된
조건 충족 실행을 receipt와 함께 `outputs/.mclab-trash/` 아래로 옮깁니다. 이는 복구 가능한
격리이며 삭제 또는 안전한 영구 삭제가 아니고 디스크 공간도 계속 사용합니다.
`.mclab-preserve`가 있으면 해당 실행은 cleanup 후보가 되지 않습니다.

MCLab은 영구 purge를 제공하지 않습니다. 격리된 실행, receipt와 이전에 생성된
`outputs/index.html`에는 학습자 정보나 경로 정보가 계속 남아 있을 수 있습니다.
소스/venv CLI 복원은 로컬 파일시스템에서만 지원되며 NFS와 SMB는 cleanup/restore 지원
범위 밖입니다. 이 정책은 실제 output 대상 dry-run이나 apply를 승인하지 않습니다.
설정 root의 cleanup은 그 밖에 둔 명시적 output tree나 상위 형제 `index.html`을 관리하지
않습니다. 관리자가 승인한 제거 뒤에는 `python -m mclab index --output-dir <parent>`로
상위 index를 재생성하거나, 같은 승인된 로컬 절차로 익명화 또는 제거하세요.
외부 `MCLAB_OUTPUT_DIR` tree와 실제 갱신된 parent index에도 같은 원칙이 적용됩니다.
호출자가 선택하고 안전 검사를 통과한 root 바로 아래에 쓴 독립 실행형 index도 파생
파일이지 cleanup run 후보가 아니므로, 승인된 로컬 절차로 재생성·익명화·제거할 때까지
남을 수 있습니다. Cleanup은 QSettings `language` 또는 `tourComplete`도 초기화하지 않습니다.

## Shared PCs / 공용 PC

### English

Use a separate operating-system account or an institution-approved per-user
`MCLAB_DATA_DIR`. Do not put a real name, student identifier, credential, secret, or other
unnecessary personal data in a prediction or observation note. Close MCLab and sign out
after use. Review the complete run, derived index, and any quarantine before sharing or
handing the device to another user. If `--output-dir` was used, include its parent
`index.html` in that review even when the selected run tree has already been copied or
removed; do the same for `MCLAB_OUTPUT_DIR` when its parent index was successfully
refreshed. Also review a standalone-index root, QSettings preferences, validation-only
destinations used by an administrator, and the potentially private QLockFile and local
filesystem-socket or named-pipe endpoint. Closing the app normally is not proof that a
prior crash left no stale filesystem coordination artifact.

The device or institution administrator must separately decide account isolation,
retention, backup, and secure-erasure procedures. MCLab's quarantine is not a substitute
for those controls. If local policy requires clearing the device before handoff, use the
administrator-approved process for the complete per-user data root; do not treat moving a
run to quarantine as completion of that process.

### 한국어

별도 운영체제 계정 또는 기관이 승인한 사용자별 `MCLAB_DATA_DIR`를 사용하세요. 예측이나
관찰 메모에 실명, 학번, credential, secret 또는 불필요한 개인정보를 넣지 마세요. 사용
후에는 MCLab을 닫고 계정에서 로그아웃하세요. 자료를 공유하거나 다음 사용자에게 기기를
넘기기 전에 실행 폴더 전체, 파생 index와 quarantine을 검토하세요.
`--output-dir`를 사용했다면 선택한 run tree를 이미 복사하거나 제거했더라도 상위
`index.html`을 검토 대상에 포함하세요. `MCLAB_OUTPUT_DIR` parent index가 실제 갱신된
경우에도 같습니다. 독립 실행형 index root, QSettings preference, 관리자가 사용한 검증
전용 대상과 개인정보 가능 QLockFile 및 local filesystem-socket 또는 named-pipe
endpoint도 검토하세요. 앱을 정상 종료했다는 사실만으로 이전 crash의 stale filesystem
조정 artifact가 없다고 단정하면 안 됩니다.

기기 또는 기관 관리자는 계정 분리, 보존, backup과 안전한 영구 삭제 절차를 별도로
결정해야 합니다. MCLab의 quarantine은 이런 통제를 대신하지 않습니다.
기기를 다음 사용자에게 넘기기 전에 로컬 정책상 초기화가 필요하다면 사용자별 데이터
root 전체에 기관 관리자가 승인한 절차를 적용해야 하며, 실행을 quarantine으로 옮긴 것을
그 절차의 완료로 간주하면 안 됩니다.

## Sharing, support, and security / 공유·지원·보안

### English

Share only the minimum sanitized excerpt. Remove credentials and tokens, learner
predictions and notes, private output content, live batch-handoff secrets, usernames,
home-directory paths, and other unsanitized absolute paths. Use the
[support guide](../.github/SUPPORT.md) for general issues and the
[private security policy](../.github/SECURITY.md) for a security or data-loss
vulnerability. Submitting either report is a user-initiated transfer; MCLab does not send
it automatically.

### 한국어

필요한 최소한의 익명화된 부분만 공유하세요. credential과 token, 학습자 예측과 메모,
비공개 output 내용, 실행 중인 batch handoff secret, 사용자명, home-directory 경로와 그
밖의 익명화되지 않은 절대 경로를 제거하세요. 일반 문제는
[지원 안내](../.github/SUPPORT.md)를, 보안 또는 데이터 손실 취약점은
[비공개 보안 정책](../.github/SECURITY.md)을 따르세요. 두 신고 모두 사용자가 시작하는
전송이며 MCLab이 자동으로 보내지 않습니다.

## Backup, retention, and external decisions / 백업·보존·외부 결정

### English

OPS-01A sets no retention period, backup owner/location/cadence, release-evidence
retention, shared-PC administration policy, secure-erasure method, support SLA, RPO, or
RTO. Those remain unresolved owner or institutional decisions. Do not infer a backup from
a saved run or quarantine; restoration is not proven until the responsible policy owner
performs and records an authorized restore test on the intended storage.

### 한국어

OPS-01A는 보존 기간, backup 담당자·위치·주기, release evidence 보존, 공용 PC 관리 정책,
안전한 영구 삭제 방법, 지원 SLA, RPO 또는 RTO를 정하지 않습니다. 모두 owner 또는 기관이
결정해야 할 미결정 사항입니다. 저장 실행이나 quarantine이 있다는 이유로 backup이 있다고
간주하지 마세요. 책임 있는 정책 owner가 대상 저장소에서 승인된 복원 시험을 수행하고
기록하기 전에는 복원 가능성이 입증된 것이 아닙니다.

## Validation status and limits / 검증 상태와 한계

### English

The machine contract, schema, documentation links, and temporary-fixture behavior and
cleanup/restore tests are automated. A canonical version-1 source manifest pins the exact
path set and SHA-256 bytes of every Python file under `packaging/`, `scripts/`, and
`src/mclab/`; additions, removals, links, and byte drift fail validation. This is source
integrity for those declared repository roots, not a general proof about unlisted file
types or external services. Controlled repository reads use no-follow file descriptors,
reject POSIX links, Windows reparse points, and special files, compare directory and file
identity across check/open/read, and enforce byte bounds. On Windows, retained
FILE_LIST_DIRECTORY handles without FILE_SHARE_DELETE pin every lexical ancestor against
rename-and-swap-back races while the path-based metadata APIs run. A platform missing the
required safe primitives fails closed. No real learner output was read, dry-run, moved,
restored, or erased for this policy. Repository checks do not prove a particular
institution's shared-PC configuration, backup system, retention rule, or erasure process.

### 한국어

machine contract와 schema, 문서 링크, 임시 fixture 기반 동작 및 cleanup/restore 시험은
자동화됩니다. canonical version-1 source manifest는 `packaging/`, `scripts/`,
`src/mclab/` 아래 모든 Python 파일의 정확한 경로 집합과 SHA-256 byte를 고정하며, 파일
추가·제거·link·byte 변경은 검증에 실패합니다. 이는 선언된 저장소 root의 source integrity
근거이지 목록 밖 파일 형식이나 외부 서비스를 포괄적으로 입증하는 것은 아닙니다. 이 정책을
위한 통제된 저장소 읽기는 no-follow file descriptor를 사용하고 POSIX link, Windows
reparse point와 특수 파일을 거부하며 check/open/read 전후의 폴더·파일 identity와 byte
상한을 확인합니다. Windows에서는 lexical ancestor마다 FILE_SHARE_DELETE 없이 연
FILE_LIST_DIRECTORY handle을 유지하여 path 기반 metadata API가 실행되는 동안
rename-and-swap-back 경합을 막습니다. 필요한 안전 primitive가 없는 platform에서는 fail
closed합니다. 이 정책을 위해 실제 학습자 output을 읽거나, dry-run하거나,
이동·복원·삭제하지 않았습니다. 저장소 검사는 특정 기관의 공용 PC 설정, backup system,
보존 규칙 또는 영구 삭제 절차를 입증하지 않습니다.
