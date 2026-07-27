# Support

MCLab is an actively developed, local-first educational project. Support is
best effort; no response-time or platform-service SLA is promised.

## Choose the right channel

- General bug, setup problem, confusing lesson, or feature request: open a
  [GitHub issue](https://github.com/ycpiglet/manipulator-control-tutorial/issues).
- Security or data-loss vulnerability: follow the
  [private security policy](SECURITY.md), not a public issue.
- Contribution proposal: read [`CONTRIBUTING.md`](../CONTRIBUTING.md) before
  opening a pull request.

## Information that helps

Please include:

- MCLab release or commit SHA;
- operating system, architecture, Python version, and launch path;
- Lab/scenario and config path;
- exact reproduction steps, expected result, and observed result;
- the smallest relevant log excerpt;
- sanitized output from `python -m mclab doctor --json` when setup is involved.

Before posting, remove usernames, home-directory paths, credentials, tokens,
learner predictions or notes, and private output content. MCLab keeps runs and
notes locally and does not upload them automatically; sharing them in an issue
is the reporter's explicit action.
Review [Local data and privacy](../docs/local_data_and_privacy.md) before using a
shared PC, copying a run, or attaching any saved artifact. Its confirmed
CPython, Qt QML, and Matplotlib cache list is bounded; broader platform caches
remain open, so it is not complete shared-PC clearance. If an administrator
requires clearing, close MCLab, resolve and review the exact current-user
target, and use only the approved local process. Cache removal is not secure
erasure. Use the applicable interpreter, Qt, Matplotlib, and OS tooling to
resolve each effective cache location at runtime; do not assume the default
path when an override or temporary fallback may apply.
The setup inventory also includes the exact
`mclab-assets-<project-device-inode-sha256>.lock` and
`mclab-install-<environment-prefix-sha256-prefix>.lock` in the effective
temporary directory, plus `.venv/.mclab-lock-state.json` and a possible atomic
staging sibling in each used checkout. Review only exact targets for the
physical checkout and resolved environment; broad lock-name matches do not
establish ownership. The explicit dependency installer removes prior state
before mutation, can leave it absent on failure, writes replacement state on
success, and normally removes atomic staging. Outside that writer lifecycle,
the local-data contract does not authorize manual cleanup, removal, or
truncation of this setup metadata. Confirm that no asset or dependency
installer is running first: a held lock pathname must not be unlinked or
replaced. POSIX dependency locks narrow group/other permission bits; the
standard-library implementation makes no equivalent Windows ACL claim.

## 한국어 안내

일반 오류, 설치 문제, 이해하기 어려운 수업 단계와 기능 제안은 GitHub issue로 알려
주세요. 보안 또는 데이터 손실 위험은 공개 issue 대신 `SECURITY.md`의 비공개 신고
경로를 사용해야 합니다.

재현을 위해 commit 또는 version, 운영체제·아키텍처·Python, 실행 방법, Lab/scenario와
config, 재현 절차, 기대 결과와 실제 결과를 알려 주세요. 설치 문제라면
`python -m mclab doctor --json` 결과에서 사용자명, 홈 경로, 비밀정보, 학습자 예측·메모를
제거한 뒤 필요한 부분만 공유해 주세요.
[로컬 데이터와 개인정보 안내](../docs/local_data_and_privacy.md)에서 공용 PC, 실행 복사와
저장 artifact 공유 전 확인할 항목을 볼 수 있습니다. CPython, Qt QML, Matplotlib의
확인된 cache 목록은 제한된 범위이며 더 넓은 platform cache는 미결 상태이므로 공용 PC
전체 정리 완료를 뜻하지 않습니다. 관리자가 정리를 요구하면 MCLab을 닫고 현재 사용자의
정확한 대상을 확인·검토한 뒤 승인된 로컬 절차만 사용하세요. Cache 제거는 안전한 영구
삭제가 아닙니다. Override 또는 temporary fallback이 적용될 수 있으므로 interpreter,
Qt, Matplotlib과 OS 도구로 runtime에서 각 effective cache 위치를 확인하고 default
경로를 가정하지 마세요.
Setup inventory에는 effective temporary directory의 정확한
`mclab-assets-<project-device-inode-sha256>.lock`,
`mclab-install-<environment-prefix-sha256-prefix>.lock`과 각 사용 checkout의
`.venv/.mclab-lock-state.json` 및 남아 있을 수 있는 atomic staging sibling도
포함됩니다. Physical checkout과 resolved environment에 대응하는 정확한 대상만
검토하고 광범위한 lock 이름 match를 소유권 근거로 사용하면 안 됩니다. 로컬 데이터
계약은 explicit dependency installer가 변경 전에 prior state를 제거하고 실패 시
absent로 남기거나 성공 시 replacement state를 기록하며 atomic staging을 정상 제거하는
writer lifecycle을 인정합니다. 그 밖에서는 이 setup metadata의 수동 cleanup, 삭제
또는 truncate를 승인하지 않습니다. 먼저 asset 또는 dependency installer가 실행 중이지
않은지 확인해야 하며 보유 중인 lock pathname을 unlink 또는 replace하면 안 됩니다.
POSIX dependency lock은 group/other permission bit를 제한하지만 표준 라이브러리
구현은 동등한 Windows ACL 보장을 주장하지 않습니다.
