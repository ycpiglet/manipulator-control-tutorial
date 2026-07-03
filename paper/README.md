# Paper Workspace Guide

이 폴더는 임피던스/임피던스 제어 튜토리얼 논문 초안을 위한 LaTeX 작업공간이다.
현재 목표는 분량 압축보다 초심자가 논리, 역사, 물리 직관, 수식 의미를 따라갈 수 있게 내용을 충분히 펼치는 것이다.

## Source Files To Keep

다음 파일들은 논문 원본 또는 운영 기록이므로 버전 관리 대상으로 본다.

- `main.tex`: LaTeX 진입점. 패키지, 제목, 장 입력 순서, bibliography만 둔다.
- `sections/*.tex`: 본문 장별 원고.
- `figures/*.tex`: TikZ 기반 개념 그림.
- `figures/figure_plan.md`: 그림 의도와 추가 후보.
- `references/refs.bib`: BibTeX 항목.
- `references/sources.md`: citation provenance와 PDF/cache 상태.
- `references/notes.md`: 레퍼런스 사용 흐름과 남은 gap.
- `README.md`: 이 작업공간 안내 문서.

## Generated Or Local-Only Files

다음 파일들은 생성물 또는 로컬 검증 캐시로 취급한다.

- `main.pdf`: LaTeX 빌드 결과물. 현재 `.gitignore`에서 ignore한다.
- `build*/`, `*.aux`, `*.bbl`, `*.blg`, `*.log`, `*.out`, `*.toc`, `*.xdv`: LaTeX 중간 산출물.
- `references/papers/*.pdf`: 논문 검토용 로컬 PDF 캐시. 재배포 권리가 확실하지 않으므로 commit하지 않는다.
- `tmp/latex_compile_*`, `tmp/pdfs/*_review`: 로컬 논문 검증 scratch. 현재 pass에서 만든 경로이고 resolved path가 workspace 안임을 확인한 뒤에만 삭제한다.

논문 재현성은 PDF 파일 자체가 아니라 `main.tex`, `sections/`, `figures/`, `refs.bib`, `sources.md`로 유지한다.
최신 검토 대상 PDF는 항상 `paper/main.pdf`이다.
오래된 `paper/build/main.pdf`가 있거나 PDF viewer가 잠근 경우 삭제를 강행하지 말고 무시한다.

## Build

이식 가능한 표준 빌드는 Tectonic CLI이다. 어떤 머신에서든 같은 명령으로 빌드하며,
CI(`.github/workflows/ci.yml`의 `paper-build` job)도 같은 명령을 사용한다.
`main.tex`의 `% !TEX program = xelatex` 지시문은 일반 TeX 편집기에서 열 때의 힌트로 남겨 둔다.

```bash
tectonic --keep-logs paper/main.tex
```

Codex LaTeX plugin의 bundled Tectonic을 쓰는 로컬 대안 명령은 다음과 같다
(경로는 이 머신 전용이므로 다른 환경에서는 위의 Tectonic CLI를 사용한다).

```powershell
$env:PYTHONUTF8='1'; python C:\Users\ycpig\.codex\plugins\cache\openai-bundled\latex\0.2.4\scripts\compile_latex.py C:\Users\ycpig\manipulator-control-tutorial\paper\main.tex --compiler tectonic --output-directory C:\Users\ycpig\manipulator-control-tutorial\paper --json
```

성공하면 `paper/main.pdf`가 생성된다.
Tectonic 로그에는 첫 번째 pass의 undefined citation/reference 경고가 보일 수 있지만, 자동 재실행 뒤 PDF가 생성되고 citation coverage check가 통과하면 정상으로 본다.

## Citation And Provenance Checks

본문 citation이 BibTeX와 source manifest에 모두 있는지 확인한다.
표준 검사는 이식 가능한 스크립트이며 CI(`paper-gates` job)에서도 같은 명령을 실행한다.

```bash
python .agents/validation/check_citation_coverage.py
```

아래 PowerShell 스니펫은 같은 검사의 수동 대안으로 남겨 둔다.

```powershell
$tex = rg -o "\\cite\{[^}]+\}" paper\sections paper\main.tex | ForEach-Object { if ($_ -match "\\cite\{([^}]+)\}") { $matches[1].Split(',') | ForEach-Object { $_.Trim() } } } | Sort-Object -Unique
$bib = rg -o "^@[^{}]+\{[^,]+" paper\references\refs.bib | ForEach-Object { ($_ -replace '^@[^{}]+\{','').Trim() } | Sort-Object -Unique
$src = Get-Content paper\references\sources.md | ForEach-Object { if ($_ -match '^\| `([^`]+)` \|') { $matches[1] } } | Sort-Object -Unique
Compare-Object $tex $bib | Where-Object SideIndicator -eq '<='
Compare-Object $tex $src | Where-Object SideIndicator -eq '<='
```

아무 출력이 없으면 본문에서 사용한 citation key가 `refs.bib`와 `sources.md`에 모두 있다는 뜻이다.

## Paper-Only Validation

`paper/` 또는 `.agents/`만 바뀌고 시뮬레이터 코드와 config를 건드리지 않은 경우에는 paper-only validation으로 충분하다.
위의 bundled Tectonic 빌드를 실행한 뒤 citation/provenance check를 돌린다.
통과 기준은 LaTeX exit code 0, 최종 rerun 구간의 citation/reference/rerun/overfull/underfull warning 0, 본문에서 사용한 citation key의 BibTeX/source manifest 누락 0, 그리고 `.agents/CURRENT_STATE.md`에 최신 PDF page count, byte size, 실행 명령, cleanup note가 기록되어 있는 것이다.

## Writing Loop

권장 반복 순서는 다음과 같다.

1. 한 번에 하나의 독자 문제를 고른다. 예: 감쇠비 직관, 평형점, 인덕터의 방해 원리.
2. 관련 section만 수정한다.
3. 수식 주변에 물리적 의미와 단위 감각을 덧붙인다.
4. citation/source manifest가 깨지지 않았는지 확인한다.
5. PDF를 빌드한다.
6. `.agents/CURRENT_STATE.md`에 변경, 검증, 남은 위험을 기록한다.

나중에 formal paper로 압축할 때는 반복 설명, 긴 예시, 일부 표를 appendix로 옮기는 방식이 좋다.
