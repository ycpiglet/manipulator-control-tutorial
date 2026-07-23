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
