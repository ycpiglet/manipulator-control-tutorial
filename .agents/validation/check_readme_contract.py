"""Validate the bilingual newcomer README contract without network access.

DOC-01 turns the previously manual README review into a deterministic gate.
The checker intentionally uses only the Python standard library so it can run
before the project package or documentation tooling is installed.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import secrets
import stat
import string
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from html import unescape as html_unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
KOREAN_README = Path("README.md")
ENGLISH_README = Path("README.en.md")
DOC_MAP = Path("docs/README.md")
STRUCTURE_GUIDE = Path("docs/repository_structure.md")

SECTION_CONTRACT = (
    ("이 저장소가 하는 일", "What this repository does"),
    ("학습 내용", "What you learn"),
    ("빠른 시작", "Quick start"),
    ("저장되는 결과", "Saved evidence"),
    ("저장소 구조", "Repository map"),
    ("문서 안내", "Documentation"),
    ("개발 상태", "Development status"),
    ("개발과 기여", "Development and contributing"),
    ("인용과 라이선스", "Citation and licenses"),
)

DOC_MAP_SECTION_CONTRACT = (
    "Start here",
    "Lab references",
    "Design, validation, and research",
    "Which interface is current?",
)

STRUCTURE_SECTION_CONTRACT = (
    "DOC-01 decision: no move",
    "Newcomer entry points",
    "Source and evidence layout",
    "Change rules",
)

REPOSITORY_MAP_CONTRACT = (
    ("src/mclab/",),
    ("src/mclab/controllers/",),
    ("src/mclab/labs/",),
    ("configs/",),
    ("models/", "third_party/"),
    ("tests/",),
    ("docs/",),
    ("paper/", "jose/", "outreach/"),
    (".agents/",),
    ("outputs/",),
)

STRUCTURE_LAYOUT_CONTRACT = (
    ("src/mclab/",),
    ("src/mclab/controllers/",),
    ("src/mclab/labs/",),
    ("configs/",),
    ("models/", "third_party/"),
    ("tests/",),
    ("scripts/",),
    ("docs/",),
    ("paper/", "jose/", "outreach/"),
    (".github/workflows/",),
    (".agents/",),
    ("outputs/",),
)
STRUCTURE_REQUIRED_MARKERS = (
    "A structural decision belongs to IA-00 after the B2 safe-main gate.",
    "Any future consolidation must be a separate compatibility change and must:",
    "keep a working shim for at least one release when a public launcher moves;",
    "The PowerShell verification entry is internal maintainer tooling, not a learner "
    "launcher or a public compatibility path.",
)
STRUCTURE_REQUIRED_CODE_IDENTIFIERS = (
    "run_mclab.cmd",
    "run_lab*.cmd",
    "run_batch*.cmd",
    "run_all_batches.cmd",
    "run_all.ps1",
)

PUBLIC_LAUNCHERS = ("START_HERE.cmd", "start_here.sh", "START_HERE.command")
ROOT_LAUNCHER_INVENTORY = (
    "run_mclab.cmd",
    "run_all_batches.cmd",
    "run_all.ps1",
)
PUBLIC_CLI_PATHS = (
    ("app",),
    ("assets",),
    ("assets", "install"),
    ("doctor",),
    ("run",),
    ("clean",),
)
PUBLIC_CLI_OPTION_CONTRACT = {
    ("app",): {"--self-test": ("flag", False)},
    ("assets", "install"): {"--force": ("flag", False)},
    ("run",): {
        "--config": ("value", True),
        "--headless": ("flag", False),
        "--plot": ("flag", False),
        "--plots": ("value", False),
        "--open-report": ("flag", False),
    },
    ("clean",): {
        "--keep": ("value", False),
        "--apply": ("value", False),
        "--restore": ("value", False),
        "--list-trash": ("flag", False),
        "--yes": ("flag", False),
    },
}
PUBLIC_LAB_NAMES = ("lab01",)
PUBLIC_FILES = ("configs/lab01_msd/default.yaml", "scripts/start_mclab.py")
REQUIRED_COMMAND_LINES = (
    "git clone https://github.com/ycpiglet/manipulator-control-tutorial.git",
    "cd manipulator-control-tutorial",
    "python -m venv .venv",
    r".\.venv\Scripts\Activate.ps1",
    "source .venv/bin/activate",
    "python scripts/install_locked.py app",
    "python -m mclab assets install",
    "python -m mclab doctor",
    "python -m mclab app",
    "python scripts/install_locked.py runtime",
    "python -m mclab run lab01 --config configs/lab01_msd/default.yaml "
    "--headless --plot --plots essential",
    "python -m mclab clean --keep 20",
    "python -m mclab clean --keep 20 --apply PLAN_ID_FROM_DRY_RUN --yes",
    "python -m mclab clean --list-trash",
    "python -m mclab clean --restore RECEIPT_ID_FROM_LIST",
    "python scripts/install_locked.py app-dev",
    "python -m pytest -q --ignore=tests/test_mypy_baseline.py",
    "python -m ruff check src tests scripts .agents/validation",
    "python -m mclab app --self-test",
    "python scripts/install_locked.py dev",
    "python -m pytest -q tests/test_mypy_baseline.py",
    "python .agents/validation/check_mypy_baseline.py --python-version 3.11",
)
DOC_MAP_REQUIRED_COMMAND_LINES = ("python -m mclab app",)

DOCUMENTED_CLI_INVOCATIONS = (
    ("assets", "install"),
    ("doctor",),
    ("app",),
    ("app", "--self-test"),
    (
        "run",
        "lab01",
        "--config",
        "configs/lab01_msd/default.yaml",
        "--headless",
        "--plot",
        "--plots",
        "essential",
    ),
    ("clean", "--keep", "20"),
    (
        "clean",
        "--keep",
        "20",
        "--apply",
        "PLAN_ID_FROM_DRY_RUN",
        "--yes",
    ),
    ("clean", "--list-trash"),
    ("clean", "--restore", "RECEIPT_ID_FROM_LIST"),
)

QUICKSTART_SUCCESS_CONTRACT = (
    (
        "빠른 시작",
        "첫 소스 실행의 자동 검증 기준: Windows, Linux, macOS의 권장 실행기가 설치와 "
        "앱 self-test를 완료하고, doctor와 Lab01이 오류 없이 끝나며, 저장 결과에 "
        "report.html과 하나 이상의 plots/*.png가 생성됩니다. 앱의 저장 결과 보기와 "
        "기록 재생은 위에서 학습자가 직접 확인하는 hands-on 단계입니다.",
    ),
    (
        "Quick start",
        "Automated first source-run criterion: on Windows, Linux, and macOS, the "
        "recommended launcher completes setup and the app self-test, doctor and Lab01 "
        "exit successfully, and the saved result contains report.html plus at least one "
        "plots/*.png. View saved results and Replay recording remain the hands-on learner "
        "checks above.",
    ),
)

CLEANUP_WARNING_CONTRACT = (
    (
        "개발 상태",
        "아래 `--apply` 예시를 바로 복사해 실행하지 마세요. 먼저 기본 dry-run이 "
        "표시한 모든 후보를 검토하고, 별도로 승인한 **동일한 plan ID**에만 "
        "`--apply ... --yes`를 사용하세요.",
    ),
    (
        "Development status",
        "Do not copy and run the `--apply` example immediately. First inspect every "
        "candidate printed by the default dry-run, and use `--apply ... --yes` only for "
        "that **same, separately approved plan ID**.",
    ),
)
CLEANUP_FORBIDDEN_REVERSALS = (
    (
        "개발 상태",
        (
            "별도 승인을 생략",
            "승인 없이 바로 실행",
            "다른 plan ID를 사용",
        ),
    ),
    (
        "Development status",
        (
            "skip separate approval",
            "run immediately without approval",
            "use any plan ID without separate approval",
        ),
    ),
)

REQUIRED_INLINE_IDENTIFIERS = (
    r".\.venv\Scripts\Activate.ps1",
    "source .venv/bin/activate",
    '$env:MCLAB_DATA_DIR = Join-Path $env:LOCALAPPDATA "MCLab"',
    'export MCLAB_DATA_DIR="$HOME/Library/Application Support/MCLab"',
    'export MCLAB_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mclab"',
    "PLAN_ID_FROM_DRY_RUN",
    "RECEIPT_ID_FROM_LIST",
)

LINK_DOCUMENTS = (KOREAN_README, ENGLISH_README, DOC_MAP, STRUCTURE_GUIDE)
REQUIRED_SHARED_LINKS = (
    "docs/installation.md",
    "docs/learner_guide.md",
    "docs/educator_guide.md",
    "docs/developer_guide.md",
    "docs/repository_structure.md",
    "docs/troubleshooting.md",
    "docs/README.md",
    "CONTRIBUTING.md",
    "CITATION.cff",
    ".agents/CURRENT_STATE.md",
    ".agents/READINESS_EXECUTION_PLAN.md",
    ".agents/reviews/20260720_enterprise_readiness_audit.md",
)
DOC_MAP_REQUIRED_LINKS = (
    "README.md",
    "README.en.md",
    "CONTRIBUTING.md",
    "SIMULATOR_DEVELOPMENT_SPEC.md",
    ".agents/CURRENT_STATE.md",
    ".agents/READINESS_EXECUTION_PLAN.md",
    ".agents/reviews/20260720_enterprise_readiness_audit.md",
    "docs/learner_guide.md",
    "docs/educator_guide.md",
    "docs/developer_guide.md",
    "docs/repository_structure.md",
    "docs/installation.md",
    "docs/troubleshooting.md",
    "docs/lab01_mass_spring_damper.md",
    "docs/lab02_pid_control.md",
    "docs/lab03_trajectory_planning.md",
    "docs/lab04_panda_manipulator.md",
    "docs/ui_validation.md",
    "paper/README.md",
    "jose/paper.md",
)

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
FENCE_OPEN_RE = re.compile(r"^( {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
INLINE_LINK_START_RE = re.compile(r"!?\[([^\]\n]*)\]\(")
REFERENCE_LINK_RE = re.compile(r"!?\[[^\]\n]+\]\s*\[[^\]\n]*\]")
REFERENCE_DEFINITION_RE = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*\S+", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
AUTOLINK_RE = re.compile(
    r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^\x00-\x20\x7f<>]*)>"
)
RAW_HTML_URL_ATTRIBUTES = frozenset(
    {
        "action",
        "archive",
        "background",
        "cite",
        "classid",
        "codebase",
        "data",
        "formaction",
        "href",
        "icon",
        "longdesc",
        "manifest",
        "ping",
        "poster",
        "profile",
        "src",
        "srcdoc",
        "srcset",
        "usemap",
    }
)
HTML_BLOCK_TAG_RE = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|"
    r"col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|"
    r"form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|"
    r"menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|"
    r"tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[\t />]|$)",
    re.IGNORECASE,
)
HTML_BLOCK_CLOSED_TAG_RE = re.compile(
    r"^ {0,3}<(script|pre|style|textarea)(?=[\t >]|$)",
    re.IGNORECASE,
)
HTML_BLOCK_DECLARATION_RE = re.compile(r"^ {0,3}<![A-Z]")
MARKDOWN_BLOCK_INTERRUPT_RE = re.compile(
    r"^ {0,3}(?:#{1,6}(?:[ \t]+|$)|>|(?:[-+*]|\d+[.)])[ \t]+|"
    r"(?:[-*_][ \t]*){3,}$|(?:=+|-+)[ \t]*$)"
)
HIDDEN_HTML_TAGS = frozenset(
    {
        "applet",
        "audio",
        "canvas",
        "datalist",
        "dialog",
        "embed",
        "head",
        "iframe",
        "math",
        "noembed",
        "noframes",
        "noscript",
        "object",
        "picture",
        "script",
        "select",
        "style",
        "svg",
        "template",
        "textarea",
        "title",
        "video",
    }
)
RUNTIME_CLI_WORKER_FLAG = "--runtime-cli-worker"
RUNTIME_CLI_WORKER_PREFIX = "MCLAB_README_RUNTIME_CLI"
RUNTIME_CLI_WORKER_TIMEOUT_SECONDS = 30
DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
DEFAULT_IGNORABLE_CODEPOINTS = frozenset(
    codepoint
    for lower, upper in DEFAULT_IGNORABLE_RANGES
    for codepoint in range(lower, upper + 1)
)


@dataclass(frozen=True)
class Metric:
    """One observable contract metric."""

    name: str
    threshold: str
    measured: str
    passed: bool


@dataclass(frozen=True)
class MarkdownScan:
    """Renderable Markdown plus fenced blocks and structural parse errors."""

    body: str
    fenced_blocks: tuple[tuple[str, str], ...]
    errors: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class InlineMarkdownScan:
    """Inline Markdown views with code spans and raw tag tokens separated."""

    without_code: str
    without_tags: str
    without_code_or_tags: str
    code_spans: tuple[tuple[int, int, str], ...]
    raw_tags: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CliOptionContract:
    """One argparse option, including every alias and literal choice."""

    names: tuple[str, ...]
    mode: str
    required: bool
    choices: tuple[str, ...] | None


@dataclass(frozen=True)
class CliPositionalContract:
    """Minimum/maximum arity and literal choices for one positional argument."""

    name: str
    minimum: int
    maximum: int | None
    choices: tuple[str, ...] | None


@dataclass
class CliCommandContract:
    """Static argparse surface for one canonical command path or alias."""

    options: dict[str, CliOptionContract]
    positionals: list[CliPositionalContract]


class RawHtmlContractParser(HTMLParser):
    """Find URL attributes and explicit anchors with real HTML tokenization."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.findings: list[tuple[int, str]] = []
        self.anchors: set[str] = set()
        self.details_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        lowered_tag = tag.casefold()
        if lowered_tag == "details":
            self.details_depth += 1
            if self.details_depth > 1:
                self.findings.append(
                    (self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN")
                )
                return
        if lowered_tag in HIDDEN_HTML_TAGS:
            self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN"))
            return
        for raw_name, value in attrs:
            name = raw_name.casefold()
            if name in {"hidden", "popover"} or (
                name == "aria-hidden"
                and value is not None
                and value.strip().casefold() == "true"
            ):
                self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN"))
                return

        for raw_name, value in attrs:
            name = raw_name.casefold()
            if value and (name == "id" or (lowered_tag == "a" and name == "name")):
                self.anchors.add(unquote(value))

        for raw_name, value in attrs:
            name = raw_name.casefold()
            is_url_attribute = (
                name in RAW_HTML_URL_ATTRIBUTES or name.endswith(":href")
            )
            is_unsupported_style = name == "style"
            is_meta_refresh = (
                lowered_tag == "meta"
                and name == "content"
                and value is not None
                and re.search(r"(?:^|;)\s*url\s*=", value, re.I) is not None
            )
            if is_unsupported_style:
                self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_STYLE"))
                return
            if is_url_attribute or is_meta_refresh:
                self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_LINK"))
                return

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() == "details":
            self.details_depth = max(0, self.details_depth - 1)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "details":
            self.details_depth = max(0, self.details_depth - 1)

    def handle_pi(self, data: str) -> None:
        del data
        self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN"))

    def handle_decl(self, decl: str) -> None:
        del decl
        self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN"))

    def unknown_decl(self, data: str) -> None:
        del data
        self.findings.append((self.getpos()[0], "UNSUPPORTED_HTML_HIDDEN"))


def _read(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _blank_like(text: str) -> str:
    """Mask text while retaining newlines and therefore source line numbers."""

    return "".join(char if char in {"\r", "\n"} else " " for char in text)


def _raw_html_tag_end(text: str, start: int) -> int | None:
    """Return the end of one CommonMark-style raw HTML tag, respecting quotes."""

    if re.match(
        r"</?[A-Za-z][A-Za-z0-9-]*(?=[\t\n\f\r />])", text[start:]
    ) is None:
        return None

    quote = ""
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if quote:
            if char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == ">":
            return cursor + 1
        cursor += 1
    return None


def _html_block_code_mask(text: str) -> tuple[bool, ...]:
    """Mark CommonMark HTML blocks where Markdown syntax stays raw."""

    masked = [False] * len(text)
    blank_terminated_block = False
    closing_pattern: re.Pattern[str] | None = None
    fence_char = ""
    fence_length = 0
    paragraph_open = False
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_char:
            closing_fence = re.compile(
                rf" {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*"
            )
            if closing_fence.fullmatch(content):
                fence_char = ""
                fence_length = 0
            paragraph_open = False
            offset += len(line)
            continue
        if blank_terminated_block and not content.strip():
            blank_terminated_block = False
            paragraph_open = False
        if not blank_terminated_block and closing_pattern is None:
            opening_fence = FENCE_OPEN_RE.fullmatch(content)
            if opening_fence is not None:
                fence = opening_fence.group("fence")
                info = opening_fence.group("info").strip()
                if fence.startswith("~") or "`" not in info:
                    fence_char = fence[0]
                    fence_length = len(fence)
                    paragraph_open = False
                    offset += len(line)
                    continue
            closed_match = HTML_BLOCK_CLOSED_TAG_RE.match(content)
            if closed_match is not None:
                closing_pattern = re.compile(
                    rf"</{re.escape(closed_match.group(1))}[ \t]*>",
                    re.IGNORECASE,
                )
            elif re.match(r"^ {0,3}<!--", content) is not None:
                closing_pattern = re.compile(r"-->")
            elif re.match(r"^ {0,3}<\?", content) is not None:
                closing_pattern = re.compile(r"\?>")
            elif re.match(r"^ {0,3}<!\[CDATA\[", content) is not None:
                closing_pattern = re.compile(r"\]\]>")
            elif HTML_BLOCK_DECLARATION_RE.match(content) is not None:
                closing_pattern = re.compile(r">")
            elif HTML_BLOCK_TAG_RE.match(content) is not None:
                blank_terminated_block = True
            else:
                indent = len(content) - len(content.lstrip(" "))
                tag_end = (
                    _raw_html_tag_end(content, indent) if indent <= 3 else None
                )
                if (
                    not paragraph_open
                    and tag_end is not None
                    and not content[tag_end:].strip()
                ):
                    blank_terminated_block = True
        in_html_block = blank_terminated_block or closing_pattern is not None
        if in_html_block:
            masked[offset : offset + len(line)] = [True] * len(line)
        if closing_pattern is not None and closing_pattern.search(content):
            closing_pattern = None
        if in_html_block:
            paragraph_open = False
        elif not content.strip() or MARKDOWN_BLOCK_INTERRUPT_RE.match(content):
            paragraph_open = False
        else:
            paragraph_open = True
        offset += len(line)
    return tuple(masked)


def _without_html_blocks(text: str) -> str:
    """Mask raw HTML blocks while preserving source line boundaries."""

    html_block_mask = _html_block_code_mask(text)
    return "".join(
        character
        if not html_block_mask[index]
        else character
        if character in {"\r", "\n"}
        else " "
        for index, character in enumerate(text)
    )


def _code_span_end(
    text: str,
    start: int,
    *,
    code_disabled: tuple[bool, ...] | None = None,
) -> tuple[int, str] | None:
    """Return a same-line code-span close outside raw HTML blocks.

    DOC-01 intentionally treats multiline code spans as unsupported so a
    delimiter can never cross a Markdown block boundary and hide a link.
    """

    opening_end = start
    while opening_end < len(text) and text[opening_end] == "`":
        opening_end += 1
    delimiter_length = opening_end - start
    cursor = opening_end
    while cursor < len(text):
        if code_disabled is not None and code_disabled[cursor]:
            return None
        if text[cursor] in {"\r", "\n"}:
            return None
        if text[cursor] != "`":
            cursor += 1
            continue
        closing_end = cursor
        while closing_end < len(text) and text[closing_end] == "`":
            closing_end += 1
        if closing_end - cursor == delimiter_length:
            return closing_end, text[opening_end:cursor]
        cursor = closing_end
    return None


def scan_inline_markdown(text: str) -> InlineMarkdownScan:
    """Separate code spans from raw tags using their left-to-right precedence."""

    without_code = list(text)
    without_tags = list(text)
    without_code_or_tags = list(text)
    code_spans: list[tuple[int, int, str]] = []
    raw_tags: list[tuple[int, int]] = []
    code_disabled = _html_block_code_mask(text)
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "`" and not code_disabled[cursor]:
            code_span = _code_span_end(
                text,
                cursor,
                code_disabled=code_disabled,
            )
            if code_span is not None:
                end, content = code_span
                masked = _blank_like(text[cursor:end])
                without_code[cursor:end] = masked
                without_code_or_tags[cursor:end] = masked
                code_spans.append((cursor, end, content))
                cursor = end
                continue
            while cursor < len(text) and text[cursor] == "`":
                cursor += 1
            continue
        elif text[cursor] == "<":
            tag_end = _raw_html_tag_end(text, cursor)
            if tag_end is not None:
                without_code_or_tags[cursor:tag_end] = _blank_like(
                    text[cursor:tag_end]
                )
                without_tags[cursor:tag_end] = _blank_like(text[cursor:tag_end])
                raw_tags.append((cursor, tag_end))
                cursor = tag_end
                continue
        cursor += 1
    return InlineMarkdownScan(
        "".join(without_code),
        "".join(without_tags),
        "".join(without_code_or_tags),
        tuple(code_spans),
        tuple(raw_tags),
    )


def _mask_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Mask HTML comments on a non-fenced Markdown line."""

    masked = list(line)
    cursor = 0
    while cursor < len(line):
        if in_comment:
            closing = line.find("-->", cursor)
            end = len(line) if closing < 0 else closing + 3
            for index in range(cursor, end):
                if masked[index] not in {"\r", "\n"}:
                    masked[index] = " "
            if closing < 0:
                return "".join(masked), True
            cursor = end
            in_comment = False
            continue
        opening = line.find("<!--", cursor)
        if opening < 0:
            break
        cursor = opening
        in_comment = True
    return "".join(masked), in_comment


def scan_markdown(text: str) -> MarkdownScan:
    """Separate rendered Markdown from comments and CommonMark fenced code."""

    rendered: list[str] = []
    blocks: list[tuple[str, str]] = []
    errors: list[tuple[int, str]] = []
    in_comment = False
    fence_char = ""
    fence_length = 0
    fence_info = ""
    fence_start = 0
    fence_content: list[str] = []
    html_block_mask = _html_block_code_mask(text)
    offset = 0

    lines = text.splitlines(keepends=True)
    for line_number, line in enumerate(lines, 1):
        content_line = line.rstrip("\r\n")
        line_end = offset + len(line)
        in_html_block = any(html_block_mask[offset:line_end])
        offset = line_end
        if fence_char:
            closing_re = re.compile(
                rf" {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*"
            )
            if closing_re.fullmatch(content_line):
                blocks.append((fence_info, "".join(fence_content).strip()))
                fence_char = ""
                fence_length = 0
                fence_info = ""
                fence_content = []
            else:
                fence_content.append(line)
            rendered.append(_blank_like(line))
            continue

        if not in_comment and not in_html_block:
            opening = FENCE_OPEN_RE.fullmatch(content_line)
            if opening is not None:
                fence = opening.group("fence")
                info = opening.group("info").strip()
                if fence.startswith("~") or "`" not in info:
                    fence_char = fence[0]
                    fence_length = len(fence)
                    fence_info = info
                    fence_start = line_number
                    rendered.append(_blank_like(line))
                    continue
            if line.startswith("    ") or line.startswith("\t"):
                errors.append((line_number, "UNSUPPORTED_INDENTED_CODE"))
                rendered.append(_blank_like(line))
                continue

        masked, in_comment = _mask_html_comments(line, in_comment)
        rendered.append(masked)

    if fence_char:
        blocks.append((fence_info, "".join(fence_content).strip()))
        errors.append((fence_start, "UNCLOSED_FENCE"))
    if in_comment:
        errors.append((len(lines) or 1, "UNCLOSED_HTML_COMMENT"))
    return MarkdownScan("".join(rendered), tuple(blocks), tuple(errors))


def h2_headings(text: str) -> tuple[str, ...]:
    """Return second-level Markdown headings in document order."""

    body = _without_html_blocks(scan_markdown(text).body)
    return tuple(match.group(1).strip() for match in H2_RE.finditer(body))


def fenced_blocks(text: str) -> tuple[tuple[str, str], ...]:
    """Return normalized fenced-code language and contents in document order."""

    return scan_markdown(text).fenced_blocks


def visible_markdown_text(text: str) -> str:
    """Return rendered prose plus visible fenced-code contents, excluding comments."""

    scan = scan_markdown(text)
    return rendered_markdown_prose(
        text, include_code=True, include_image_alt=False
    ) + "\n" + "\n".join(
        content for _info, content in scan.fenced_blocks
    )


def _inline_link_spans(text: str) -> tuple[tuple[int, int, int, bool], ...]:
    """Return opening bracket, closing bracket, end, and image status for links."""

    spans: list[tuple[int, int, int, bool]] = []
    masked = scan_inline_markdown(text).without_code_or_tags
    offset = 0
    for raw_line in masked.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        cursor = 0
        while True:
            marker = line.find("](", cursor)
            if marker < 0:
                break
            label_start = _link_label_start(line, marker)
            if _is_escaped(line, marker) or label_start is None:
                cursor = marker + 2
                continue
            parsed = _parse_link_destination(line, marker + 2)
            if parsed is None:
                cursor = marker + 2
                continue
            _destination, end = parsed
            is_image = (
                label_start > 0
                and line[label_start - 1] == "!"
                and not _is_escaped(line, label_start - 1)
            )
            spans.append(
                (
                    offset + label_start,
                    offset + marker,
                    offset + end,
                    is_image,
                )
            )
            cursor = max(end, marker + 2)
        offset += len(raw_line)
    return tuple(spans)


def _autolink_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Return CommonMark URI autolink ranges outside code and raw HTML tags."""

    masked = scan_inline_markdown(text).without_code_or_tags
    return tuple(match.span() for match in AUTOLINK_RE.finditer(masked))


def _without_default_ignorables(text: str) -> str:
    """Remove Unicode Default_Ignorable_Code_Point characters from prose."""

    return "".join(
        character
        for character in text
        if ord(character) not in DEFAULT_IGNORABLE_CODEPOINTS
    )


def rendered_markdown_prose(
    text: str,
    *,
    include_code: bool,
    include_image_alt: bool,
) -> str:
    """Return normalized visible prose without link destinations or raw tag syntax."""

    body = scan_markdown(HTML_COMMENT_RE.sub("", text)).body
    inline = scan_inline_markdown(body)
    characters = list(body)
    code_content = [False] * len(body)
    for start, end, _content in inline.code_spans:
        delimiter_length = 1
        while start + delimiter_length < end and body[start + delimiter_length] == "`":
            delimiter_length += 1
        if include_code:
            for index in range(start + delimiter_length, end - delimiter_length):
                code_content[index] = True
            for index in range(start, start + delimiter_length):
                characters[index] = ""
            for index in range(end - delimiter_length, end):
                characters[index] = ""
        else:
            for index in range(start, end):
                characters[index] = " "
    for start, end in inline.raw_tags:
        for index in range(start, end):
            characters[index] = ""
    for label_start, closing_bracket, end, is_image in _inline_link_spans(body):
        if is_image and not include_image_alt:
            image_start = label_start - 1
            for index in range(image_start, end):
                characters[index] = " "
            continue
        if is_image:
            characters[label_start - 1] = ""
        characters[label_start] = ""
        characters[closing_bracket] = ""
        for index in range(closing_bracket + 1, end):
            characters[index] = ""
    for start, end in _autolink_ranges(body):
        for index in range(start, end):
            characters[index] = " "
    for index, character in enumerate(characters):
        if character in {"*", "_", "~"} and not code_content[index]:
            characters[index] = ""
    rendered = _without_default_ignorables(html_unescape("".join(characters)))
    rendered = _without_default_ignorables(
        unicodedata.normalize("NFKC", rendered)
    )
    return re.sub(r"\s+", " ", rendered).strip()


def inline_code_identifiers(text: str) -> set[str]:
    """Return inline-code tokens while excluding fenced-code delimiters and bodies."""

    body = scan_markdown(text).body
    return {
        content.strip()
        for _start, _end, content in scan_inline_markdown(body).code_spans
    }


def section_body(text: str, heading: str) -> str:
    """Return one H2 section body, or an empty string when it is absent."""

    body = _without_html_blocks(scan_markdown(text).body)
    marker = re.search(rf"^##\s+{re.escape(heading)}\s*$", body, re.MULTILINE)
    if marker is None:
        return ""
    next_heading = H2_RE.search(body, marker.end())
    return body[marker.end() : next_heading.start() if next_heading else len(body)]


def warning_alert_body(text: str, heading: str) -> str:
    """Return the normalized body of one GitHub WARNING alert in an H2 section."""

    lines = section_body(text, heading).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "> [!WARNING]":
            continue
        alert_lines: list[str] = []
        for candidate in lines[index + 1 :]:
            if not candidate.startswith(">"):
                break
            alert_lines.append(candidate.removeprefix(">").lstrip())
        return re.sub(r"\s+", " ", " ".join(alert_lines)).strip()
    return ""


def repository_map_rows(text: str, heading: str) -> tuple[tuple[str, ...], ...]:
    """Extract code-formatted path groups from the first column of a map table."""

    rows: list[tuple[str, ...]] = []
    for line in section_body(text, heading).splitlines():
        if not line.startswith("|") or re.match(r"^\|?\s*:?-+", line):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        keys = tuple(
            content.strip()
            for _start, _end, content in scan_inline_markdown(cells[1]).code_spans
        )
        if keys:
            rows.append(keys)
    return tuple(rows)


def markdown_slug(text: str) -> str:
    """Approximate GitHub's heading slug for local-anchor validation."""

    plain = html_unescape(re.sub(r"<[^>]+>", "", text))
    plain = re.sub(r"[`*_~]", "", plain).strip().lower()
    kept = "".join(
        char
        for char in plain
        if char in {" ", "-", "_"}
        or unicodedata.category(char)[0] in {"L", "M", "N"}
    )
    return re.sub(r"\s", "-", kept)


def _parse_link_destination(line: str, start: int) -> tuple[str, int] | None:
    """Parse an inline-link destination after the opening parenthesis."""

    cursor = start
    while cursor < len(line) and line[cursor] in {" ", "\t"}:
        cursor += 1
    if cursor >= len(line):
        return None

    if line[cursor] == "<":
        closing_angle = line.find(">", cursor + 1)
        if closing_angle < 0:
            return None
        destination = line[cursor + 1 : closing_angle]
        cursor = closing_angle + 1
    else:
        destination_start = cursor
        depth = 0
        escaped = False
        while cursor < len(line):
            char = line[cursor]
            if escaped:
                escaped = False
                cursor += 1
                continue
            if char == "\\":
                escaped = True
                cursor += 1
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    return line[destination_start:cursor], cursor + 1
                depth -= 1
            elif char in {" ", "\t"} and depth == 0:
                break
            cursor += 1
        destination = line[destination_start:cursor]

    quote = ""
    escaped = False
    while cursor < len(line):
        char = line[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == ")":
            return destination, cursor + 1
        cursor += 1
    return None


def unescape_markdown_destination(destination: str) -> str:
    """Apply CommonMark backslash escapes without hiding path separators."""

    result: list[str] = []
    cursor = 0
    while cursor < len(destination):
        char = destination[cursor]
        if (
            char == "\\"
            and cursor + 1 < len(destination)
            and destination[cursor + 1] in string.punctuation
        ):
            result.append(destination[cursor + 1])
            cursor += 2
            continue
        result.append(char)
        cursor += 1
    return "".join(result)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _link_label_start(line: str, closing_bracket: int) -> int | None:
    """Return the matching, non-escaped opening bracket for a ]( marker."""

    depth = 0
    for index in range(closing_bracket - 1, -1, -1):
        char = line[index]
        if _is_escaped(line, index):
            continue
        if char == "]":
            depth += 1
        elif char == "[":
            if depth == 0:
                return index
            depth -= 1
    return None


def _has_link_label(line: str, closing_bracket: int) -> bool:
    """Return whether a ]( marker has a matching, non-escaped opening bracket."""

    return _link_label_start(line, closing_bracket) is not None


def inline_link_destinations(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return inline Markdown link destinations and malformed-link errors."""

    links: list[tuple[int, str]] = []
    errors = multiline_inline_link_errors(text)
    without_code_or_tags = scan_inline_markdown(text).without_code_or_tags
    for line_number, line in enumerate(without_code_or_tags.splitlines(), 1):
        cursor = 0
        while True:
            marker = line.find("](", cursor)
            if marker < 0:
                break
            if _is_escaped(line, marker) or not _has_link_label(line, marker):
                cursor = marker + 2
                continue
            parsed = _parse_link_destination(line, marker + 2)
            if parsed is None:
                errors.append((line_number, "MALFORMED_INLINE_LINK"))
                cursor = marker + 2
                continue
            destination, end = parsed
            links.append((line_number, unescape_markdown_destination(destination)))
            cursor = max(end, marker + 2)
    return links, errors


def multiline_inline_link_errors(text: str) -> list[tuple[int, str]]:
    """Reject multiline link labels outside DOC-01's one-line link grammar."""

    masked = scan_inline_markdown(
        _without_html_blocks(text)
    ).without_code_or_tags
    # CommonMark accepts LF, CRLF, and bare CR as line endings.  Normalize them
    # before the one-pass bracket scan so CRLF counts once and bare CR cannot
    # make a multiline label look like a same-line link.
    masked = masked.replace("\r\n", "\n").replace("\r", "\n")
    findings: list[tuple[int, str]] = []
    bracket_stack: list[tuple[int, int]] = []
    line_number = 1
    line_has_content = False
    escaped = False
    for index, character in enumerate(masked):
        if character == "\n":
            if not line_has_content:
                bracket_stack.clear()
            line_number += 1
            line_has_content = False
            escaped = False
            continue
        if not character.isspace():
            line_has_content = True
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "[":
            bracket_stack.append((index, line_number))
            continue
        if character != "]" or not bracket_stack:
            continue
        _opening_index, opening_line = bracket_stack.pop()
        if (
            index + 1 < len(masked)
            and masked[index + 1] == "("
            and opening_line != line_number
        ):
            findings.append((opening_line, "UNSUPPORTED_MULTILINE_LINK"))
    return findings


def reference_style_errors(text: str) -> list[tuple[int, str]]:
    """Reject reference-style links, which are outside the DOC-01 contract grammar."""

    without_code = scan_inline_markdown(text).without_code_or_tags
    findings: list[tuple[int, str]] = []
    for pattern in (REFERENCE_LINK_RE, REFERENCE_DEFINITION_RE):
        for match in pattern.finditer(without_code):
            line_number = without_code.count("\n", 0, match.start()) + 1
            findings.append((line_number, "UNSUPPORTED_REFERENCE_LINK"))
    return findings


def raw_html_link_errors(text: str) -> list[tuple[int, str]]:
    """Reject raw HTML links so every contract link uses one checked grammar."""

    without_code = scan_inline_markdown(text).without_code
    parser = RawHtmlContractParser()
    parser.feed(without_code)
    parser.close()
    return parser.findings


def autolink_errors(text: str) -> list[tuple[int, str]]:
    """Reject CommonMark URI autolinks whose schemes are outside the contract."""

    masked = scan_inline_markdown(text).without_code_or_tags
    findings: list[tuple[int, str]] = []
    for match in AUTOLINK_RE.finditer(masked):
        rendered_destination = html_unescape(match.group(1))
        destination = unquote(rendered_destination)
        line_number = masked.count("\n", 0, match.start()) + 1
        if any(
            character.isspace()
            or ord(character) < 0x20
            or ord(character) == 0x7F
            or character in {"<", ">"}
            or ord(character) in DEFAULT_IGNORABLE_CODEPOINTS
            for character in rendered_destination
        ):
            findings.append(
                (line_number, "UNSUPPORTED_AUTOLINK_CHARACTER")
            )
            continue
        if "\\" in destination:
            findings.append(
                (
                    line_number,
                    f"BACKSLASH_PATH use forward slashes: {destination}",
                )
            )
            continue
        scheme = urlsplit(rendered_destination).scheme.casefold()
        if scheme not in {"data", "http", "https", "mailto"}:
            findings.append((line_number, f"UNSUPPORTED_SCHEME {destination}"))
    return findings


def rendered_heading_text(text: str) -> str:
    """Reduce heading Markdown to the visible label used for a GitHub slug."""

    rendered = text
    for start, end, content in reversed(scan_inline_markdown(text).code_spans):
        rendered = rendered[:start] + content.strip() + rendered[end:]
    while True:
        match = INLINE_LINK_START_RE.search(rendered)
        if match is None:
            break
        parsed = _parse_link_destination(rendered, match.end())
        if parsed is None:
            break
        _destination, end = parsed
        rendered = rendered[: match.start()] + match.group(1) + rendered[end:]
    return rendered


def document_anchors(path: Path) -> set[str]:
    """Return generated heading anchors and explicit HTML anchors for one Markdown file."""

    text = scan_markdown(path.read_text(encoding="utf-8")).body
    inline_scan = scan_inline_markdown(text)
    html_parser = RawHtmlContractParser()
    html_parser.feed(inline_scan.without_code)
    html_parser.close()
    anchors = set(html_parser.anchors)
    used_slugs: set[str] = set()
    heading_source = _without_html_blocks(text)
    lines = heading_source.splitlines()
    headings: list[str] = []
    for index, line in enumerate(lines):
        atx_match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if atx_match is not None:
            headings.append(atx_match.group(1))
            continue
        if index + 1 >= len(lines) or not line.strip():
            continue
        if re.match(r"^ {0,3}(?:=+|-+)\s*$", lines[index + 1]) is not None:
            headings.append(line.strip())

    for heading in headings:
        base = markdown_slug(rendered_heading_text(heading))
        slug = base
        suffix = 0
        while slug in used_slugs:
            suffix += 1
            slug = f"{base}-{suffix}"
        used_slugs.add(slug)
        anchors.add(slug)
    return anchors


def path_is_within(root: Path, path: Path) -> bool:
    """Return whether a resolved path remains inside the repository root."""

    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def launcher_has_executable_mode(root: Path, name: str) -> bool:
    """Check the Git index mode, with a fixture-friendly POSIX fallback."""

    try:
        result = subprocess.run(
            ["git", "ls-files", "--stage", "--", name],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return result.stdout.split(maxsplit=1)[0] == "100755"
    if os.name == "nt":
        return True
    return bool((root / name).stat().st_mode & stat.S_IXUSR)


def launcher_has_active_delegate(path: Path) -> bool:
    """Require the delegate in the reachable canonical launcher prologue."""

    meaningful_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().replace("\\", "/")
        lowered = line.lower()
        if not line:
            continue
        if path.suffix.lower() == ".cmd":
            without_at = lowered.removeprefix("@").lstrip()
            if without_at.startswith("rem ") or without_at.startswith("::"):
                continue
        elif lowered.startswith("#") and lowered != "#!/bin/sh":
            continue
        meaningful_lines.append(line)

    if path.suffix.lower() == ".cmd":
        expected_prefix = (
            "@echo off",
            "setlocal",
            'cd /d "%~dp0"',
            "echo starting mclab. the first setup can take a few minutes.",
        )
        if tuple(line.casefold() for line in meaningful_lines[:4]) != expected_prefix:
            return False
        if len(meaningful_lines) < 5:
            return False
        delegate_pattern = re.compile(
            r'^@?python(?:\.exe)?\s+["\x27]?scripts/start_mclab\.py["\x27]?\s+%\*\s*$',
            re.I,
        )
        return delegate_pattern.fullmatch(meaningful_lines[4]) is not None

    expected_posix = (
        "#!/bin/sh",
        "set -eu",
        'ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)',
        'cd "$ROOT"',
        'exec python3 scripts/start_mclab.py "$@"',
    )
    return tuple(meaningful_lines) == expected_posix


def local_link_errors(root: Path, documents: tuple[Path, ...]) -> tuple[int, list[str]]:
    """Validate local Markdown link targets and Markdown anchors."""

    checked = 0
    errors: list[str] = []
    resolved_root = root.resolve()
    for relative_document in documents:
        source = root / relative_document
        if not source.is_file():
            errors.append(
                f"{relative_document.as_posix()}: CONTRACT_DOCUMENT_MISSING"
            )
            continue
        if not path_is_within(root, source):
            errors.append(
                f"{relative_document.as_posix()}: CONTRACT_DOCUMENT_OUTSIDE_REPOSITORY"
            )
            continue
        scan = scan_markdown(source.read_text(encoding="utf-8"))
        for line_number, code in scan.errors:
            errors.append(f"{relative_document.as_posix()}:{line_number}: {code}")
        for line_number, code in reference_style_errors(scan.body):
            errors.append(
                f"{relative_document.as_posix()}:{line_number}: {code} use an inline link"
            )
        for line_number, code in raw_html_link_errors(scan.body):
            errors.append(
                f"{relative_document.as_posix()}:{line_number}: {code} use a Markdown link"
            )
        for line_number, code in autolink_errors(scan.body):
            errors.append(f"{relative_document.as_posix()}:{line_number}: {code}")
        links, malformed = inline_link_destinations(scan.body)
        for line_number, code in malformed:
            errors.append(f"{relative_document.as_posix()}:{line_number}: {code}")
        for line_number, destination_raw in links:
            rendered_destination = html_unescape(destination_raw)
            destination = unquote(rendered_destination)
            parsed = urlsplit(rendered_destination)
            if "\\" in destination:
                errors.append(
                    f"{relative_document.as_posix()}:{line_number}: "
                    f"BACKSLASH_PATH use forward slashes: {destination}"
                )
                continue
            if parsed.scheme in {"http", "https", "mailto", "data"}:
                continue
            if parsed.scheme:
                errors.append(
                    f"{relative_document.as_posix()}:{line_number}: "
                    f"UNSUPPORTED_SCHEME {destination}"
                )
                continue
            if parsed.netloc:
                continue
            checked += 1
            target_text = unquote(parsed.path)
            if target_text.startswith("/"):
                errors.append(
                    f"{relative_document.as_posix()}:{line_number}: "
                    f"ABSOLUTE_LOCAL_PATH use a relative repository path: {destination}"
                )
                continue
            target = (source.parent / target_text).resolve() if target_text else source.resolve()
            try:
                target.relative_to(resolved_root)
            except ValueError:
                errors.append(
                    f"{relative_document.as_posix()}:{line_number}: "
                    f"OUTSIDE_REPOSITORY {destination}"
                )
                continue
            if not target.exists():
                errors.append(
                    f"{relative_document.as_posix()}:{line_number}: "
                    f"BROKEN_LINK missing local target: {destination}"
                )
                continue
            fragment = unquote(parsed.fragment)
            if fragment and target.suffix.lower() in {".md", ".markdown"}:
                if fragment not in document_anchors(target):
                    errors.append(
                        f"{relative_document.as_posix()}:{line_number}: MISSING_ANCHOR "
                        f"#{fragment} in {target.relative_to(root).as_posix()}"
                    )
    return checked, errors


def markdown_local_targets(root: Path, relative_document: Path) -> set[str]:
    """Return normalized repository-relative local link targets."""

    source = root / relative_document
    targets: set[str] = set()
    scan = scan_markdown(source.read_text(encoding="utf-8"))
    links, _errors = inline_link_destinations(scan.body)
    for _line_number, destination_raw in links:
        rendered_destination = html_unescape(destination_raw)
        parsed = urlsplit(rendered_destination)
        target_text = unquote(parsed.path)
        if (
            parsed.scheme
            or parsed.netloc
            or not target_text
            or "\\" in unquote(rendered_destination)
        ):
            continue
        if target_text.startswith("/"):
            continue
        target = (source.parent / target_text).resolve()
        try:
            targets.add(target.relative_to(root.resolve()).as_posix())
        except ValueError:
            continue
    return targets


def _literal_string_arguments(call: ast.Call) -> tuple[str, ...]:
    """Return the leading literal string arguments from a call."""

    values: list[str] = []
    for argument in call.args:
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            break
        values.append(argument.value)
    return tuple(values)


def _keyword_node(call: ast.Call, name: str) -> ast.expr | None:
    """Return one keyword AST value."""

    return next(
        (keyword.value for keyword in call.keywords if keyword.arg == name),
        None,
    )


def _literal_keyword(call: ast.Call, name: str) -> object | None:
    """Return one literal keyword value, or None when absent/non-literal."""

    node = _keyword_node(call, name)
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _literal_string_sequence(node: ast.expr | None) -> tuple[str, ...] | None:
    """Return a literal string collection without evaluating source code."""

    if node is None:
        return ()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        values.append(element.value)
    return tuple(values)


def _literal_choices(call: ast.Call) -> tuple[str, ...] | None:
    """Return literal argparse choices; None means no statically provable set."""

    node = _keyword_node(call, "choices")
    if node is None:
        return None
    return _literal_string_sequence(node)


def _cli_option_contract(call: ast.Call, names: tuple[str, ...]) -> CliOptionContract:
    """Classify an argparse option's aliases, arity, requirement, and choices."""

    action = _literal_keyword(call, "action")
    nargs = _literal_keyword(call, "nargs")
    flag_actions = {"store_true", "store_false", "count", "help", "version"}
    mode = "flag" if action in flag_actions or nargs == 0 else "value"
    return CliOptionContract(
        names=names,
        mode=mode,
        required=_literal_keyword(call, "required") is True,
        choices=_literal_choices(call),
    )


def _cli_positional_contract(call: ast.Call, name: str) -> CliPositionalContract:
    """Classify a positional argparse argument without importing the package."""

    nargs = _literal_keyword(call, "nargs")
    if nargs in {"?", "*"}:
        minimum = 0
    elif nargs == "+":
        minimum = 1
    elif isinstance(nargs, int):
        minimum = max(0, nargs)
    else:
        minimum = 1
    if nargs in {"*", "+"}:
        maximum = None
    elif nargs == "?":
        maximum = 1
    elif isinstance(nargs, int):
        maximum = max(0, nargs)
    else:
        maximum = 1
    return CliPositionalContract(
        name=name,
        minimum=minimum,
        maximum=maximum,
        choices=_literal_choices(call),
    )


def _call_is_unconditional_exit(
    call: ast.Call,
    parser_names: frozenset[str],
) -> bool:
    """Recognize calls that cannot return to later argparse declarations."""

    if isinstance(call.func, ast.Name):
        return call.func.id in {"exit", "quit"}
    if not isinstance(call.func, ast.Attribute):
        return False
    owner = call.func.value.id if isinstance(call.func.value, ast.Name) else ""
    return (
        (owner == "sys" and call.func.attr == "exit")
        or (owner == "os" and call.func.attr == "_exit")
        or (owner in parser_names and call.func.attr == "error")
    )


def _block_always_exits(
    statements: list[ast.stmt],
    parser_names: frozenset[str],
) -> bool:
    """Return whether sequential statements provably return or raise."""

    return any(
        _statement_always_exits(statement, parser_names) for statement in statements
    )


def _statement_always_exits(
    statement: ast.stmt,
    parser_names: frozenset[str],
) -> bool:
    """Recognize direct and constant-branch exits in build_parser."""

    if isinstance(statement, (ast.Return, ast.Raise)):
        return True
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        return _call_is_unconditional_exit(statement.value, parser_names)
    if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
        return _call_is_unconditional_exit(statement.value, parser_names)
    if isinstance(statement, ast.If):
        try:
            condition = bool(ast.literal_eval(statement.test))
        except (ValueError, TypeError):
            condition = None
        if condition is True:
            return _block_always_exits(statement.body, parser_names)
        if condition is False:
            return _block_always_exits(statement.orelse, parser_names)
        return (
            bool(statement.orelse)
            and _block_always_exits(statement.body, parser_names)
            and _block_always_exits(statement.orelse, parser_names)
        )
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return _block_always_exits(statement.body, parser_names)
    if isinstance(statement, ast.Try):
        if _block_always_exits(statement.finalbody, parser_names):
            return True
        branches = [statement.body, *[handler.body for handler in statement.handlers]]
        if statement.orelse:
            branches.append(statement.orelse)
        return bool(statement.handlers) and all(
            _block_always_exits(branch, parser_names) for branch in branches
        )
    return False


def cli_parser_contract(
    root: Path,
) -> tuple[
    dict[tuple[str, ...], CliCommandContract],
    tuple[str, ...],
]:
    """Recover argparse command hierarchy and options without importing the package."""

    tree = ast.parse((root / "src" / "mclab" / "cli.py").read_text(encoding="utf-8"))
    build_parser = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_parser"
        ),
        None,
    )
    if build_parser is None:
        return {}, ("build_parser function is missing",)

    parser_paths: dict[str, tuple[str, ...]] = {}
    subparser_parents: dict[str, tuple[str, ...]] = {}
    group_parents: dict[str, tuple[str, ...]] = {}
    contract: dict[tuple[str, ...], CliCommandContract] = {}
    issues: list[str] = []

    for statement in build_parser.body:
        if _statement_always_exits(statement, frozenset(parser_paths)):
            break
        target_name: str | None = None
        call: ast.Call | None = None
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
        ):
            target_name = statement.targets[0].id
            call = statement.value
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
        if call is None or not isinstance(call.func, ast.Attribute):
            continue

        method = call.func.attr
        owner = call.func.value.id if isinstance(call.func.value, ast.Name) else ""
        if method == "ArgumentParser" and target_name:
            parser_paths[target_name] = ()
            contract.setdefault((), CliCommandContract({}, []))
        elif method == "add_subparsers" and target_name and owner in parser_paths:
            subparser_parents[target_name] = parser_paths[owner]
        elif method == "add_parser" and owner in subparser_parents:
            arguments = _literal_string_arguments(call)
            if not arguments:
                continue
            command = arguments[0]
            path = (*subparser_parents[owner], command)
            if path in contract:
                issues.append(f"duplicate parser path: {' '.join(path)}")
                command_contract = contract[path]
            else:
                command_contract = CliCommandContract({}, [])
                contract[path] = command_contract
            aliases_node = _keyword_node(call, "aliases")
            aliases = _literal_string_sequence(aliases_node)
            if aliases is None:
                issues.append(f"non-literal parser aliases on {' '.join(path)}")
                aliases = ()
            for alias in aliases:
                alias_path = (*subparser_parents[owner], alias)
                if alias_path in contract:
                    issues.append(f"duplicate parser path: {' '.join(alias_path)}")
                else:
                    contract[alias_path] = command_contract
            if target_name:
                parser_paths[target_name] = path
        elif (
            method in {"add_mutually_exclusive_group", "add_argument_group"}
            and target_name
            and owner in parser_paths
        ):
            group_parents[target_name] = parser_paths[owner]
        elif method == "add_argument":
            path = parser_paths.get(owner, group_parents.get(owner))
            names = _literal_string_arguments(call)
            if path is None or not names:
                continue
            command_contract = contract.setdefault(
                path, CliCommandContract({}, [])
            )
            if names[0].startswith("-"):
                option_contract = _cli_option_contract(call, names)
                for option in names:
                    if not option.startswith("-"):
                        issues.append(
                            f"invalid option alias on {' '.join(path) or '<root>'}: "
                            f"{option}"
                        )
                    elif option in command_contract.options:
                        issues.append(
                            f"duplicate option on {' '.join(path) or '<root>'}: {option}"
                        )
                    else:
                        command_contract.options[option] = option_contract
            elif len(names) == 1:
                command_contract.positionals.append(
                    _cli_positional_contract(call, names[0])
                )
            else:
                issues.append(
                    f"invalid positional declaration on {' '.join(path) or '<root>'}: "
                    f"{names!r}"
                )
    return contract, tuple(issues)


def static_cli_invocation_errors(
    contract: dict[tuple[str, ...], CliCommandContract],
) -> tuple[str, ...]:
    """Check every documented argv against the statically recovered parser shape."""

    errors: list[str] = []
    for invocation in DOCUMENTED_CLI_INVOCATIONS:
        paths = [
            path
            for path in contract
            if path and tuple(invocation[: len(path)]) == path
        ]
        if not paths:
            errors.append(f"unknown command: {' '.join(invocation)}")
            continue
        path = max(paths, key=len)
        command = contract[path]
        remaining = list(invocation[len(path) :])
        positionals: list[str] = []
        seen_options: set[str] = set()
        index = 0
        while index < len(remaining):
            token = remaining[index]
            option_name, separator, inline_value = token.partition("=")
            option = command.options.get(option_name) if token.startswith("-") else None
            if token.startswith("-") and option is None:
                errors.append(
                    f"{' '.join(invocation)}: unknown option {option_name}"
                )
                index += 1
                continue
            if option is None:
                positionals.append(token)
                index += 1
                continue
            seen_options.update(option.names)
            if option.mode == "flag":
                if separator:
                    errors.append(
                        f"{' '.join(invocation)}: flag {option_name} cannot take a value"
                    )
                index += 1
                continue
            if separator:
                value = inline_value
            elif index + 1 < len(remaining):
                index += 1
                value = remaining[index]
            else:
                errors.append(
                    f"{' '.join(invocation)}: option {option_name} needs a value"
                )
                index += 1
                continue
            if option.choices is not None and value not in option.choices:
                errors.append(
                    f"{' '.join(invocation)}: {option_name} value {value!r} is not in "
                    f"{option.choices!r}"
                )
            index += 1

        unique_options = {id(option): option for option in command.options.values()}
        for option in unique_options.values():
            if option.required and not seen_options.intersection(option.names):
                errors.append(
                    f"{' '.join(invocation)}: missing required option {option.names[-1]}"
                )

        minimum = sum(item.minimum for item in command.positionals)
        maxima = [item.maximum for item in command.positionals]
        maximum = None if any(item is None for item in maxima) else sum(maxima)  # type: ignore[arg-type]
        if len(positionals) < minimum or (
            maximum is not None and len(positionals) > maximum
        ):
            maximum_label = "unbounded" if maximum is None else str(maximum)
            errors.append(
                f"{' '.join(invocation)}: positional arity {len(positionals)} not in "
                f"{minimum}..{maximum_label}"
            )
            continue
        cursor = 0
        for positional_index, positional in enumerate(command.positionals):
            minimum_after = sum(
                item.minimum for item in command.positionals[positional_index + 1 :]
            )
            available = len(positionals) - cursor - minimum_after
            take = available if positional.maximum is None else min(
                positional.maximum, available
            )
            take = max(positional.minimum, take)
            values = positionals[cursor : cursor + take]
            cursor += take
            if positional.choices is not None:
                for value in values:
                    if value not in positional.choices:
                        errors.append(
                            f"{' '.join(invocation)}: {positional.name} value {value!r} "
                            f"is not in {positional.choices!r}"
                        )
    return tuple(errors)


def _runtime_cli_invocation_errors_in_process() -> tuple[str, ...]:
    """Parse documented argv inside the isolated runtime worker."""

    try:
        from mclab.cli import build_parser
    except SystemExit as exc:
        return (f"runtime CLI import exited with {exc.code}",)
    except Exception as exc:  # pragma: no cover - exercised by the pre-install gate
        return (f"could not import installed mclab.cli: {exc}",)

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            parser = build_parser()
    except SystemExit as exc:
        return (f"runtime parser build exited with {exc.code}",)
    except Exception as exc:
        return (f"could not build runtime parser: {exc}",)

    errors: list[str] = []
    for invocation in DOCUMENTED_CLI_INVOCATIONS:
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(list(invocation))
        except SystemExit as exc:
            errors.append(
                f"{' '.join(invocation)}: argparse exited with {exc.code}"
            )
        except Exception as exc:
            errors.append(f"{' '.join(invocation)}: argparse failed: {exc}")
    return tuple(errors)


def _runtime_cli_worker_result(token: str, issues: tuple[str, ...]) -> str:
    """Serialize one authenticated worker result for the parent checker."""

    return (
        f"{RUNTIME_CLI_WORKER_PREFIX}:{token}:"
        f"{json.dumps(list(issues), ensure_ascii=True)}"
    )


def runtime_cli_invocation_errors() -> tuple[str, ...]:
    """Probe the installed CLI in a child process that cannot kill this gate."""

    token = secrets.token_hex(16)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                RUNTIME_CLI_WORKER_FLAG,
                token,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=RUNTIME_CLI_WORKER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            "runtime CLI worker timed out after "
            f"{RUNTIME_CLI_WORKER_TIMEOUT_SECONDS} seconds",
        )
    except OSError as exc:
        return (f"could not start runtime CLI worker: {exc}",)

    prefix = f"{RUNTIME_CLI_WORKER_PREFIX}:{token}:"
    result_lines = [
        line.removeprefix(prefix)
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]
    if completed.returncode != 0:
        return (
            f"runtime CLI worker exited with {completed.returncode} before a result",
        )
    if len(result_lines) != 1:
        return (
            "runtime CLI worker exited with 0 without exactly one authenticated result",
        )
    try:
        payload = json.loads(result_lines[0])
    except json.JSONDecodeError:
        return ("runtime CLI worker returned malformed JSON",)
    if not isinstance(payload, list) or not all(
        isinstance(item, str) for item in payload
    ):
        return ("runtime CLI worker returned an invalid result shape",)
    return tuple(payload)


def cli_lab_names(root: Path) -> set[str]:
    """Read literal lab keys from the CLI's LABS mapping."""

    tree = ast.parse((root / "src" / "mclab" / "cli.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "LABS" or not isinstance(node.value, ast.Dict):
            continue
        return {
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    return set()


def validate(root: Path = ROOT) -> tuple[list[Metric], list[str]]:
    """Evaluate the complete DOC-01 contract."""

    metrics: list[Metric] = []
    errors: list[str] = []
    try:
        korean = _read(root, KOREAN_README)
        english = _read(root, ENGLISH_README)
        docs_text = _read(root, DOC_MAP)
        structure_text = _read(root, STRUCTURE_GUIDE)
    except OSError as exc:
        return [], [str(exc)]

    expected_korean = tuple(pair[0] for pair in SECTION_CONTRACT)
    expected_english = tuple(pair[1] for pair in SECTION_CONTRACT)
    actual_korean = h2_headings(korean)
    actual_english = h2_headings(english)
    section_pass = actual_korean == expected_korean and actual_english == expected_english
    metrics.append(
        Metric(
            "KR/EN semantic H2 contract",
            f"{len(SECTION_CONTRACT)}/{len(SECTION_CONTRACT)} paired in order",
            f"KO {len(actual_korean)}, EN {len(actual_english)}",
            section_pass,
        )
    )
    if actual_korean != expected_korean:
        errors.append(f"SECTION_CONTRACT README.md H2 mismatch: {actual_korean!r}")
    if actual_english != expected_english:
        errors.append(f"SECTION_CONTRACT README.en.md H2 mismatch: {actual_english!r}")

    quickstart_results = tuple(
        expected
        in rendered_markdown_prose(
            section_body(text, heading),
            include_code=True,
            include_image_alt=False,
        )
        for text, (heading, expected) in zip(
            (korean, english), QUICKSTART_SUCCESS_CONTRACT, strict=True
        )
    )
    metrics.append(
        Metric(
            "KR/EN automated quickstart scope",
            "2/2 exact, evidence-bounded success criteria",
            f"{sum(quickstart_results)}/2 present",
            all(quickstart_results),
        )
    )
    errors.extend(
        f"QUICKSTART_SUCCESS_CONTRACT {heading!r} missing or changed"
        for passed, (heading, _expected) in zip(
            quickstart_results, QUICKSTART_SUCCESS_CONTRACT, strict=True
        )
        if not passed
    )

    cleanup_warning_results = (
        warning_alert_body(korean, CLEANUP_WARNING_CONTRACT[0][0]),
        warning_alert_body(english, CLEANUP_WARNING_CONTRACT[1][0]),
    )
    cleanup_warning_pass = all(
        actual == expected
        for actual, (_heading, expected) in zip(
            cleanup_warning_results, CLEANUP_WARNING_CONTRACT, strict=True
        )
    )
    cleanup_reversals = [
        (heading, phrase)
        for text, (heading, phrases) in zip(
            (korean, english), CLEANUP_FORBIDDEN_REVERSALS, strict=True
        )
        for phrase in phrases
        if phrase.casefold()
        in rendered_markdown_prose(
            text,
            include_code=True,
            include_image_alt=True,
        ).casefold()
    ]
    cleanup_warning_pass = cleanup_warning_pass and not cleanup_reversals
    metrics.append(
        Metric(
            "KR/EN cleanup apply warning contract",
            "2/2 exact safety warnings",
            f"{sum(actual == contract[1] for actual, contract in zip(cleanup_warning_results, CLEANUP_WARNING_CONTRACT, strict=True))} present",
            cleanup_warning_pass,
        )
    )
    for actual, (heading, expected) in zip(
        cleanup_warning_results, CLEANUP_WARNING_CONTRACT, strict=True
    ):
        if actual != expected:
            errors.append(
                f"CLEANUP_SAFETY_CONTRACT {heading!r} warning mismatch: {actual!r}"
            )
    errors.extend(
        f"CLEANUP_SAFETY_REVERSAL {heading!r}: forbidden phrase {phrase!r}"
        for heading, phrase in cleanup_reversals
    )

    docs_headings = h2_headings(docs_text)
    docs_section_pass = docs_headings == DOC_MAP_SECTION_CONTRACT
    metrics.append(
        Metric(
            "documentation-map H2 contract",
            f"{len(DOC_MAP_SECTION_CONTRACT)}/{len(DOC_MAP_SECTION_CONTRACT)} in order",
            f"{len(docs_headings)} present",
            docs_section_pass,
        )
    )
    if not docs_section_pass:
        errors.append(f"DOC_MAP_CONTRACT docs/README.md H2 mismatch: {docs_headings!r}")

    structure_headings = h2_headings(structure_text)
    structure_section_pass = structure_headings == STRUCTURE_SECTION_CONTRACT
    metrics.append(
        Metric(
            "repository-structure H2 contract",
            f"{len(STRUCTURE_SECTION_CONTRACT)}/{len(STRUCTURE_SECTION_CONTRACT)} in order",
            f"{len(structure_headings)} present",
            structure_section_pass,
        )
    )
    if not structure_section_pass:
        errors.append(
            f"STRUCTURE_SECTION_CONTRACT mismatch: {structure_headings!r}"
        )

    visible_structure = rendered_markdown_prose(
        structure_text,
        include_code=False,
        include_image_alt=False,
    )
    missing_structure_markers = [
        marker for marker in STRUCTURE_REQUIRED_MARKERS if marker not in visible_structure
    ]
    structure_identifiers = inline_code_identifiers(structure_text)
    missing_structure_identifiers = [
        identifier
        for identifier in STRUCTURE_REQUIRED_CODE_IDENTIFIERS
        if identifier not in structure_identifiers
    ]
    structure_contract_pass = (
        not missing_structure_markers and not missing_structure_identifiers
    )
    metrics.append(
        Metric(
            "no-move compatibility markers",
            f"{len(STRUCTURE_REQUIRED_MARKERS) + len(STRUCTURE_REQUIRED_CODE_IDENTIFIERS)}"
            f"/{len(STRUCTURE_REQUIRED_MARKERS) + len(STRUCTURE_REQUIRED_CODE_IDENTIFIERS)} required",
            f"{len(STRUCTURE_REQUIRED_MARKERS) + len(STRUCTURE_REQUIRED_CODE_IDENTIFIERS) - len(missing_structure_markers) - len(missing_structure_identifiers)} present",
            structure_contract_pass,
        )
    )
    errors.extend(
        f"STRUCTURE_REQUIRED_MARKER {marker}" for marker in missing_structure_markers
    )
    errors.extend(
        f"STRUCTURE_REQUIRED_IDENTIFIER {identifier}"
        for identifier in missing_structure_identifiers
    )

    korean_blocks = fenced_blocks(korean)
    english_blocks = fenced_blocks(english)
    blocks_pass = korean_blocks == english_blocks and bool(korean_blocks)
    metrics.append(
        Metric(
            "KR/EN fenced command parity",
            "100% identical and ordered",
            f"KO {len(korean_blocks)}, EN {len(english_blocks)}",
            blocks_pass,
        )
    )
    if korean_blocks != english_blocks:
        errors.append("COMMAND_PARITY README fenced command blocks differ by locale or order")

    documented_command_lines = {
        line.strip()
        for _language, content in korean_blocks
        for line in content.splitlines()
        if line.strip()
    }
    missing_commands = [
        command for command in REQUIRED_COMMAND_LINES if command not in documented_command_lines
    ]
    command_pass = not missing_commands
    metrics.append(
        Metric(
            "documented public commands",
            f"{len(REQUIRED_COMMAND_LINES)}/{len(REQUIRED_COMMAND_LINES)} required",
            f"{len(REQUIRED_COMMAND_LINES) - len(missing_commands)} present",
            command_pass,
        )
    )
    errors.extend(
        f"MISSING_REQUIRED_COMMAND {command}" for command in missing_commands
    )

    docs_command_lines = {
        line.strip()
        for _language, content in fenced_blocks(docs_text)
        for line in content.splitlines()
        if line.strip()
    }
    missing_docs_commands = [
        command
        for command in DOC_MAP_REQUIRED_COMMAND_LINES
        if command not in docs_command_lines
    ]
    metrics.append(
        Metric(
            "documentation-map public commands",
            f"{len(DOC_MAP_REQUIRED_COMMAND_LINES)}/{len(DOC_MAP_REQUIRED_COMMAND_LINES)} required",
            f"{len(DOC_MAP_REQUIRED_COMMAND_LINES) - len(missing_docs_commands)} present",
            not missing_docs_commands,
        )
    )
    errors.extend(
        f"DOC_MAP_REQUIRED_COMMAND {command}" for command in missing_docs_commands
    )

    korean_identifiers = inline_code_identifiers(korean)
    english_identifiers = inline_code_identifiers(english)
    visible_korean = visible_markdown_text(korean)
    visible_english = visible_markdown_text(english)
    identifier_parity = korean_identifiers == english_identifiers
    missing_identifiers = sorted(
        identifier
        for identifier in REQUIRED_INLINE_IDENTIFIERS
        if identifier not in visible_korean or identifier not in visible_english
    )
    identifier_pass = identifier_parity and not missing_identifiers
    metrics.append(
        Metric(
            "KR/EN inline identifier contract",
            f"identical sets plus {len(REQUIRED_INLINE_IDENTIFIERS)} required",
            f"KO {len(korean_identifiers)}, EN {len(english_identifiers)}",
            identifier_pass,
        )
    )
    if not identifier_parity:
        errors.append(
            "INLINE_IDENTIFIER_PARITY "
            f"KO-only={sorted(korean_identifiers - english_identifiers)!r}; "
            f"EN-only={sorted(english_identifiers - korean_identifiers)!r}"
        )
    errors.extend(
        f"MISSING_REQUIRED_IDENTIFIER {identifier}" for identifier in missing_identifiers
    )

    parser_contract, parser_issues = cli_parser_contract(root)
    missing_cli_paths = [path for path in PUBLIC_CLI_PATHS if path not in parser_contract]
    cli_pass = not missing_cli_paths and not parser_issues
    metrics.append(
        Metric(
            "README CLI entry points",
            f"{len(PUBLIC_CLI_PATHS)}/{len(PUBLIC_CLI_PATHS)} hierarchical paths",
            f"{len(PUBLIC_CLI_PATHS) - len(missing_cli_paths)} present, "
            f"{len(parser_issues)} AST issues",
            cli_pass,
        )
    )
    errors.extend(
        f"CLI_ENTRYPOINT missing from parser: {' '.join(path)}"
        for path in missing_cli_paths
    )
    errors.extend(f"CLI_AST_CONTRACT {issue}" for issue in parser_issues)

    cli_option_mismatches: list[
        tuple[tuple[str, ...], str, tuple[str, bool], tuple[str, bool] | None]
    ] = []
    for path, required_options in PUBLIC_CLI_OPTION_CONTRACT.items():
        command_contract = parser_contract.get(path)
        for option, expected_shape in required_options.items():
            actual_contract = (
                command_contract.options.get(option)
                if command_contract is not None
                else None
            )
            actual_shape = (
                (actual_contract.mode, actual_contract.required)
                if actual_contract is not None
                else None
            )
            if actual_shape != expected_shape:
                cli_option_mismatches.append(
                    (path, option, expected_shape, actual_shape)
                )
    required_option_count = sum(
        len(options) for options in PUBLIC_CLI_OPTION_CONTRACT.values()
    )
    missing_option_count = len(cli_option_mismatches)
    metrics.append(
        Metric(
            "README CLI option contract",
            f"{required_option_count}/{required_option_count} options on exact command paths",
            f"{required_option_count - missing_option_count} present",
            not cli_option_mismatches,
        )
    )
    for path, option, expected_shape, actual_shape in cli_option_mismatches:
        errors.append(
            f"CLI_OPTION_CONTRACT {' '.join(path)} {option}: "
            f"expected={expected_shape!r}, actual={actual_shape!r}"
        )

    invocation_issues = static_cli_invocation_errors(parser_contract)
    metrics.append(
        Metric(
            "documented CLI argv contract",
            f"{len(DOCUMENTED_CLI_INVOCATIONS)} invocations; 0 static parse issues",
            f"{len(invocation_issues)} issues",
            not invocation_issues,
        )
    )
    errors.extend(f"CLI_INVOCATION_CONTRACT {issue}" for issue in invocation_issues)

    lab_names = cli_lab_names(root)
    missing_labs = sorted(set(PUBLIC_LAB_NAMES) - lab_names)
    metrics.append(
        Metric(
            "README CLI lab names",
            f"{len(PUBLIC_LAB_NAMES)}/{len(PUBLIC_LAB_NAMES)} in LABS",
            f"{len(PUBLIC_LAB_NAMES) - len(missing_labs)} present",
            not missing_labs,
        )
    )
    errors.extend(f"CLI_LAB missing from LABS: {name}" for name in missing_labs)

    invalid_public_files = sorted(
        path
        for path in PUBLIC_FILES
        if not (root / path).is_file() or not path_is_within(root, root / path)
    )
    metrics.append(
        Metric(
            "README public file truth",
            f"{len(PUBLIC_FILES)}/{len(PUBLIC_FILES)} exist",
            f"{len(PUBLIC_FILES) - len(invalid_public_files)} exist",
            not invalid_public_files,
        )
    )
    errors.extend(f"PUBLIC_FILE_INVALID {path}" for path in invalid_public_files)

    launcher_missing = [
        name
        for name in PUBLIC_LAUNCHERS
        if not (root / name).is_file() or not path_is_within(root, root / name)
    ]
    launcher_unmentioned = [
        name
        for name in PUBLIC_LAUNCHERS
        if name not in visible_korean or name not in visible_english
    ]
    executable_launchers = ("start_here.sh", "START_HERE.command")
    launcher_not_executable = [
        name
        for name in executable_launchers
        if (root / name).is_file()
        and path_is_within(root, root / name)
        and not launcher_has_executable_mode(root, name)
    ]
    launcher_wrong_delegate = [
        name
        for name in PUBLIC_LAUNCHERS
        if (root / name).is_file()
        and path_is_within(root, root / name)
        and not launcher_has_active_delegate(root / name)
    ]
    launcher_pass = (
        not launcher_missing
        and not launcher_unmentioned
        and not launcher_not_executable
        and not launcher_wrong_delegate
    )
    metrics.append(
        Metric(
            "cross-platform launchers",
            f"{len(PUBLIC_LAUNCHERS)}/{len(PUBLIC_LAUNCHERS)} exist and are bilingual",
            f"{len(PUBLIC_LAUNCHERS) - len(set(launcher_missing + launcher_unmentioned + launcher_not_executable + launcher_wrong_delegate))} valid",
            launcher_pass,
        )
    )
    errors.extend(f"LAUNCHER missing file: {name}" for name in launcher_missing)
    errors.extend(f"LAUNCHER not mentioned in both READMEs: {name}" for name in launcher_unmentioned)
    errors.extend(f"LAUNCHER not executable in Git mode: {name}" for name in launcher_not_executable)
    errors.extend(f"LAUNCHER wrong delegate: {name}" for name in launcher_wrong_delegate)

    missing_root_launchers = [
        name
        for name in ROOT_LAUNCHER_INVENTORY
        if not (root / name).is_file() or not path_is_within(root, root / name)
    ]
    undocumented_root_launchers = [
        name
        for name in ROOT_LAUNCHER_INVENTORY
        if name not in structure_identifiers
    ]
    invalid_root_launchers = sorted(
        set(missing_root_launchers + undocumented_root_launchers)
    )
    metrics.append(
        Metric(
            "root launcher compatibility inventory",
            f"{len(ROOT_LAUNCHER_INVENTORY)}/{len(ROOT_LAUNCHER_INVENTORY)} "
            "exist and are classified",
            f"{len(ROOT_LAUNCHER_INVENTORY) - len(invalid_root_launchers)} valid",
            not invalid_root_launchers,
        )
    )
    errors.extend(
        f"ROOT_LAUNCHER_INVENTORY missing file: {name}"
        for name in missing_root_launchers
    )
    errors.extend(
        f"ROOT_LAUNCHER_INVENTORY not classified: {name}"
        for name in undocumented_root_launchers
    )

    korean_map = repository_map_rows(korean, "저장소 구조")
    english_map = repository_map_rows(english, "Repository map")
    map_pass = korean_map == REPOSITORY_MAP_CONTRACT and english_map == REPOSITORY_MAP_CONTRACT
    metrics.append(
        Metric(
            "KR/EN repository map",
            f"{len(REPOSITORY_MAP_CONTRACT)}/{len(REPOSITORY_MAP_CONTRACT)} shared rows",
            f"KO {len(korean_map)}, EN {len(english_map)}",
            map_pass,
        )
    )
    if korean_map != REPOSITORY_MAP_CONTRACT:
        errors.append(f"REPOSITORY_MAP_PARITY README.md mismatch: {korean_map!r}")
    if english_map != REPOSITORY_MAP_CONTRACT:
        errors.append(f"REPOSITORY_MAP_PARITY README.en.md mismatch: {english_map!r}")

    mapped_paths = {path for row in REPOSITORY_MAP_CONTRACT for path in row}
    missing_paths = sorted(
        path
        for path in mapped_paths
        if not (root / path).is_dir() or not path_is_within(root, root / path)
    )
    path_pass = not missing_paths
    metrics.append(
        Metric(
            "repository-map path truth",
            f"{len(mapped_paths)}/{len(mapped_paths)} exist",
            f"{len(mapped_paths) - len(missing_paths)} exist",
            path_pass,
        )
    )
    errors.extend(f"MISSING_REPOSITORY_PATH {path}" for path in missing_paths)

    structure_map = repository_map_rows(structure_text, "Source and evidence layout")
    structure_map_pass = structure_map == STRUCTURE_LAYOUT_CONTRACT
    metrics.append(
        Metric(
            "repository-structure inventory",
            f"{len(STRUCTURE_LAYOUT_CONTRACT)}/{len(STRUCTURE_LAYOUT_CONTRACT)} rows",
            f"{len(structure_map)} present",
            structure_map_pass,
        )
    )
    if not structure_map_pass:
        errors.append(f"STRUCTURE_LAYOUT_CONTRACT mismatch: {structure_map!r}")

    structure_paths = {path for row in STRUCTURE_LAYOUT_CONTRACT for path in row}
    invalid_structure_paths = sorted(
        path
        for path in structure_paths
        if not (root / path).is_dir() or not path_is_within(root, root / path)
    )
    metrics.append(
        Metric(
            "repository-structure path truth",
            f"{len(structure_paths)}/{len(structure_paths)} exist",
            f"{len(structure_paths) - len(invalid_structure_paths)} exist",
            not invalid_structure_paths,
        )
    )
    errors.extend(
        f"STRUCTURE_PATH_INVALID {path}" for path in invalid_structure_paths
    )

    korean_targets = markdown_local_targets(root, KOREAN_README)
    english_targets = markdown_local_targets(root, ENGLISH_README)
    missing_shared = [
        target
        for target in REQUIRED_SHARED_LINKS
        if target not in korean_targets or target not in english_targets
    ]
    shared_link_pass = not missing_shared
    metrics.append(
        Metric(
            "KR/EN required link parity",
            f"{len(REQUIRED_SHARED_LINKS)}/{len(REQUIRED_SHARED_LINKS)} shared targets",
            f"{len(REQUIRED_SHARED_LINKS) - len(missing_shared)} shared",
            shared_link_pass,
        )
    )
    errors.extend(f"REQUIRED_LINK_PARITY {item}" for item in missing_shared)

    language_switch_missing: list[str] = []
    if "README.en.md" not in korean_targets:
        language_switch_missing.append("README.md -> README.en.md")
    if "README.md" not in english_targets:
        language_switch_missing.append("README.en.md -> README.md")
    metrics.append(
        Metric(
            "README language switch",
            "2/2 reciprocal links",
            f"{2 - len(language_switch_missing)} present",
            not language_switch_missing,
        )
    )
    errors.extend(f"LANGUAGE_SWITCH {item}" for item in language_switch_missing)

    docs_targets = markdown_local_targets(root, DOC_MAP)
    missing_docs_links = [
        target for target in DOC_MAP_REQUIRED_LINKS if target not in docs_targets
    ]
    metrics.append(
        Metric(
            "documentation-map required targets",
            f"{len(DOC_MAP_REQUIRED_LINKS)}/{len(DOC_MAP_REQUIRED_LINKS)} present",
            f"{len(DOC_MAP_REQUIRED_LINKS) - len(missing_docs_links)} present",
            not missing_docs_links,
        )
    )
    errors.extend(f"DOC_MAP_REQUIRED_LINK {item}" for item in missing_docs_links)

    checked_links, link_errors = local_link_errors(root, LINK_DOCUMENTS)
    metrics.append(
        Metric(
            "local links and anchors",
            "0 errors",
            f"{checked_links} checked, {len(link_errors)} errors",
            not link_errors,
        )
    )
    errors.extend(link_errors)

    return metrics, errors


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) == 2 and arguments[0] == RUNTIME_CLI_WORKER_FLAG:
        issues = _runtime_cli_invocation_errors_in_process()
        print(_runtime_cli_worker_result(arguments[1], issues))
        return 0
    if arguments not in ([], ["--runtime-cli"]):
        print("usage: check_readme_contract.py [--runtime-cli]", file=sys.stderr)
        return 2
    metrics, errors = validate()
    if arguments == ["--runtime-cli"]:
        runtime_issues = runtime_cli_invocation_errors()
        metrics.append(
            Metric(
                "installed runtime CLI argv contract",
                f"{len(DOCUMENTED_CLI_INVOCATIONS)} invocations; 0 argparse issues",
                f"{len(runtime_issues)} issues",
                not runtime_issues,
            )
        )
        errors.extend(
            f"RUNTIME_CLI_INVOCATION {issue}" for issue in runtime_issues
        )
    for metric in metrics:
        status = "PASS" if metric.passed else "FAIL"
        print(
            f"{status} {metric.name}: threshold={metric.threshold}; measured={metric.measured}"
        )
    for error in errors:
        print(f"ERROR {error}")
    failed = bool(errors) or any(not metric.passed for metric in metrics)
    print("status:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
