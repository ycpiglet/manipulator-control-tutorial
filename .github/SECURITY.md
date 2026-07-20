# Security Policy

## Supported versions

Security fixes are evaluated against the latest `main` commit and any release
explicitly marked as supported in its release notes. MCLab does not currently
publish a signed production release. Unsigned CI bundles are short-lived
development artifacts and are not supported production distributions.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability. Use
[GitHub private vulnerability reporting](https://github.com/ycpiglet/manipulator-control-tutorial/security/advisories/new).
Repository administrators must keep private vulnerability reporting enabled
whenever this policy is present on the default branch. If GitHub temporarily
cannot open the private form, do not post vulnerability details publicly;
retry after service recovery.

Include only the information needed to reproduce and assess the issue:

- affected commit or release and operating system;
- affected command, launcher, scenario, asset, or packaged application;
- minimal reproduction steps and observed impact;
- whether learner-owned outputs or local files may be affected;
- a sanitized diagnostic excerpt when useful.

Do not attach credentials, tokens, learner predictions or notes, private
outputs, or unsanitized absolute paths. The maintainer handles reports on a
best-effort basis and does not promise a fixed response SLA.

## Security-sensitive scope

Reports are especially important when they concern:

- deletion outside a validated MCLab outputs directory;
- path traversal, unsafe archive extraction, or asset-integrity bypasses;
- arbitrary code execution or command/argument injection;
- packaged-application loading, a future updater mechanism, signing, or
  provenance failures;
- accidental credential, private-path, or learner-data exposure;
- dependency or third-party model vulnerabilities affecting the shipped app.

General simulation bugs, documentation confusion, and feature requests belong
in the public issue tracker unless they create a security or data-loss risk.

---

## 한국어 안내

보안 취약점으로 의심되는 문제는 공개 issue로 올리지 말고 위의 GitHub 비공개 취약점
신고 경로를 사용해 주세요. 영향을 받는 commit/운영체제, 최소 재현 절차, 영향 범위,
학습자 산출물 또는 로컬 파일 손상 가능성을 알려 주세요. 비밀키, token, 학습자의 예측·
메모, 개인 경로가 포함된 원본 진단 결과는 첨부하지 마세요.

검증되지 않은 폴더 삭제, 경로 탈출, archive 압축 해제, asset 무결성, 임의 코드 실행,
패키지 로딩·서명·provenance, 개인정보 노출은 보안 범위에 포함됩니다. 일반적인 사용법
문의나 보안 영향이 없는 시뮬레이션 오류는 공개 issue를 이용해 주세요.
